"""Planning-mode orchestrator for repo-local `go_plan_runtime.py`.

The default runtime entry stays unchanged. This module only automates the
planning-mode clarification/decision checkpoints and intentionally stops at
stable handoff points such as `review_or_execute_plan` and `confirm_execute`.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping

from .clarification_bridge import prompt_cli_clarification_submission
from .cli_interactive import InteractiveSessionFactory, TerminalInteractiveSession
from .config import load_runtime_config
from .decision_bridge import prompt_cli_decision_submission
from .engine import run_runtime
from .models import RuntimeConfig, RuntimeResult

PLAN_ORCHESTRATOR_PENDING_EXIT = 2
PLAN_ORCHESTRATOR_CANCELLED_EXIT = 3
PLAN_ORCHESTRATOR_DEFAULT_MAX_LOOPS = 8
_STABLE_HOST_ACTIONS = {"review_or_execute_plan", "confirm_execute"}
_BRIDGED_HOST_ACTIONS = {"answer_questions", "confirm_decision"}

PromptReader = Callable[[str], str]
PromptWriter = Callable[[str], None]


class PlanOrchestratorError(RuntimeError):
    """Raised when planning-mode orchestration cannot complete safely."""


@dataclass(frozen=True)
class PlanOrchestratorResult:
    """Outcome returned by the planning-mode orchestrator."""

    runtime_result: RuntimeResult
    exit_code: int
    loop_count: int
    stopped_reason: str
    preflight: Mapping[str, Any] | None = None


def normalize_planning_request(raw_text: str) -> str:
    """Normalize bare planning text into a `~go plan` request."""
    text = raw_text.strip()
    if not text:
        raise ValueError("Planning request cannot be empty")
    lowered = text.lower()
    if lowered.startswith("~go plan"):
        return text
    if text.startswith("~"):
        raise ValueError("go_plan_runtime only accepts bare planning text or `~go plan ...`")
    return f"~go plan {text}"


def preflight_workspace_runtime(
    workspace_root: Path,
    *,
    payload_manifest_path: str | Path | None = None,
) -> Mapping[str, Any] | None:
    """Best-effort repo-local workspace preflight using the installed payload helper.

    The vendored bundle flow should already have been selected by the host via
    manifest-first preflight, so a bundle-local orchestrator intentionally skips
    self-updating the workspace bundle it is currently executing from.
    """

    repo_root = Path(__file__).resolve().parents[1]
    bundle_root = workspace_root / ".sopify-runtime"
    if repo_root == bundle_root:
        return {
            "action": "skipped",
            "reason_code": "RUNNING_FROM_WORKSPACE_BUNDLE",
            "message": "Current entry is already running from the workspace bundle; host preflight remains authoritative.",
        }

    manifest_candidates: list[Path] = []
    if payload_manifest_path is not None:
        manifest_candidates.append(Path(payload_manifest_path).expanduser().resolve())
    env_manifest = (os.environ.get("SOPIFY_PAYLOAD_MANIFEST") or "").strip()
    if env_manifest:
        manifest_candidates.append(Path(env_manifest).expanduser().resolve())
    home = Path.home()
    manifest_candidates.extend(
        [
            home / ".codex" / "sopify" / "payload-manifest.json",
            home / ".claude" / "sopify" / "payload-manifest.json",
        ]
    )

    payload_manifest = None
    payload_manifest_file = None
    for candidate in manifest_candidates:
        if not candidate.is_file():
            continue
        try:
            payload_manifest = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PlanOrchestratorError(f"Invalid payload manifest: {candidate}") from exc
        if isinstance(payload_manifest, dict):
            payload_manifest_file = candidate
            break
    if payload_manifest is None or payload_manifest_file is None:
        return {
            "action": "skipped",
            "reason_code": "PAYLOAD_MANIFEST_NOT_FOUND",
            "message": "No installed host payload was found; continuing with repo-local planning entry.",
        }

    helper_entry = str(payload_manifest.get("helper_entry") or "").strip()
    if not helper_entry:
        raise PlanOrchestratorError(f"Payload manifest is missing helper_entry: {payload_manifest_file}")
    payload_root = payload_manifest_file.parent
    helper_path = (payload_root / helper_entry).resolve()
    if not helper_path.is_file():
        raise PlanOrchestratorError(f"Workspace bootstrap helper is missing: {helper_path}")

    completed = subprocess.run(
        [sys.executable, str(helper_path), "--workspace-root", str(workspace_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout.strip()
    try:
        result = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError as exc:
        raise PlanOrchestratorError(f"Workspace bootstrap returned invalid JSON: {stdout or completed.stderr.strip()}") from exc
    if completed.returncode != 0 or str(result.get("action") or "").strip() == "failed":
        message = str(result.get("message") or completed.stderr.strip() or stdout or "unknown bootstrap failure")
        raise PlanOrchestratorError(f"Workspace preflight failed: {message}")
    return result


def run_plan_loop(
    raw_request: str,
    *,
    workspace_root: str | Path = ".",
    global_config_path: str | Path | None = None,
    bridge_loop: bool = True,
    max_loops: int = PLAN_ORCHESTRATOR_DEFAULT_MAX_LOOPS,
    payload_manifest_path: str | Path | None = None,
    input_reader: PromptReader | None = None,
    output_writer: PromptWriter | None = None,
    interactive_session_factory: InteractiveSessionFactory | None = None,
) -> PlanOrchestratorResult:
    """Run planning mode until it reaches a stable host stop or fails closed."""
    workspace = Path(workspace_root).resolve()
    config = load_runtime_config(workspace, global_config_path=global_config_path)
    request = normalize_planning_request(raw_request)
    preflight = preflight_workspace_runtime(workspace, payload_manifest_path=payload_manifest_path)

    if not bridge_loop:
        result = run_runtime(request, workspace_root=workspace, global_config_path=global_config_path)
        return PlanOrchestratorResult(
            runtime_result=result,
            exit_code=0,
            loop_count=1,
            stopped_reason="bridge_loop_disabled",
            preflight=preflight,
        )

    reader = input_reader or _default_prompt_reader
    writer = output_writer or _default_prompt_writer
    session_factory = interactive_session_factory or _default_interactive_session_factory

    current_request = request
    last_result: RuntimeResult | None = None
    seen_signatures: dict[str, int] = {}

    for iteration in range(1, max_loops + 1):
        result = run_runtime(current_request, workspace_root=workspace, global_config_path=global_config_path)
        last_result = result
        handoff = result.handoff
        if handoff is None:
            exit_code = 0
            stop_reason = "no_handoff"
            if result.route.route_name in {"clarification_pending", "decision_pending", "execution_confirm_pending"}:
                exit_code = PLAN_ORCHESTRATOR_PENDING_EXIT
                stop_reason = "missing_handoff_for_pending_checkpoint"
            return PlanOrchestratorResult(
                runtime_result=result,
                exit_code=exit_code,
                loop_count=iteration,
                stopped_reason=stop_reason,
                preflight=preflight,
            )

        host_action = handoff.required_host_action
        if host_action in _STABLE_HOST_ACTIONS:
            return PlanOrchestratorResult(
                runtime_result=result,
                exit_code=0,
                loop_count=iteration,
                stopped_reason=host_action,
                preflight=preflight,
            )

        if host_action not in _BRIDGED_HOST_ACTIONS:
            exit_code = 0
            if result.route.route_name not in {"plan_only", "workflow", "light_iterate", "execution_confirm_pending"}:
                exit_code = PLAN_ORCHESTRATOR_PENDING_EXIT
            return PlanOrchestratorResult(
                runtime_result=result,
                exit_code=exit_code,
                loop_count=iteration,
                stopped_reason=host_action or "unhandled_handoff",
                preflight=preflight,
            )

        signature = _handoff_signature(handoff)
        seen_signatures[signature] = seen_signatures.get(signature, 0) + 1
        if seen_signatures[signature] > 2:
            return PlanOrchestratorResult(
                runtime_result=result,
                exit_code=PLAN_ORCHESTRATOR_PENDING_EXIT,
                loop_count=iteration,
                stopped_reason="repeated_checkpoint",
                preflight=preflight,
            )

        try:
            _consume_planning_handoff(
                config=config,
                result=result,
                input_reader=reader,
                output_writer=writer,
                interactive_session_factory=session_factory,
            )
        except (EOFError, KeyboardInterrupt):
            return PlanOrchestratorResult(
                runtime_result=result,
                exit_code=PLAN_ORCHESTRATOR_PENDING_EXIT,
                loop_count=iteration,
                stopped_reason="checkpoint_input_unavailable",
                preflight=preflight,
            )
        except PlanOrchestratorError:
            return PlanOrchestratorResult(
                runtime_result=result,
                exit_code=PLAN_ORCHESTRATOR_CANCELLED_EXIT,
                loop_count=iteration,
                stopped_reason="bridge_cancelled",
                preflight=preflight,
            )

        current_request = "继续"

    if last_result is None:  # pragma: no cover - defensive guard
        raise PlanOrchestratorError("Planning orchestrator terminated before runtime executed")
    return PlanOrchestratorResult(
        runtime_result=last_result,
        exit_code=PLAN_ORCHESTRATOR_PENDING_EXIT,
        loop_count=max_loops,
        stopped_reason="max_loops_exceeded",
        preflight=preflight,
    )


def _consume_planning_handoff(
    *,
    config: RuntimeConfig,
    result: RuntimeResult,
    input_reader: PromptReader,
    output_writer: PromptWriter,
    interactive_session_factory: InteractiveSessionFactory,
) -> None:
    handoff = result.handoff
    if handoff is None:
        return
    renderer = _preferred_renderer()
    if handoff.required_host_action == "answer_questions":
        prompt_cli_clarification_submission(
            config=config,
            renderer=renderer,
            input_reader=input_reader,
            output_writer=output_writer,
            interactive_session_factory=interactive_session_factory,
        )
        return
    if handoff.required_host_action == "confirm_decision":
        prompt_cli_decision_submission(
            config=config,
            renderer=renderer,
            input_reader=input_reader,
            output_writer=output_writer,
            interactive_session_factory=interactive_session_factory,
        )
        return
    raise PlanOrchestratorError(f"Unsupported planning handoff action: {handoff.required_host_action}")


def _preferred_renderer() -> str:
    if hasattr(sys.stdin, "isatty") and hasattr(sys.stdout, "isatty") and sys.stdin.isatty() and sys.stdout.isatty():
        return "auto"
    return "text"


def _handoff_signature(handoff: Any) -> str:
    artifacts = getattr(handoff, "artifacts", {})
    checkpoint_id = None
    if isinstance(artifacts, Mapping):
        checkpoint_request = artifacts.get("checkpoint_request")
        if isinstance(checkpoint_request, Mapping):
            checkpoint_id = checkpoint_request.get("checkpoint_id")
        checkpoint_id = checkpoint_id or artifacts.get("clarification_id") or artifacts.get("decision_id")
    return f"{getattr(handoff, 'required_host_action', '')}:{checkpoint_id or '<none>'}"


def _default_prompt_writer(message: str) -> None:
    print(message, file=sys.stderr)


def _default_prompt_reader(prompt: str) -> str:
    if prompt:
        print(prompt, end="", file=sys.stderr, flush=True)
    line = sys.stdin.readline()
    if line == "":
        raise EOFError("stdin is exhausted")
    return line.rstrip("\n")


def _default_interactive_session_factory() -> TerminalInteractiveSession:
    return TerminalInteractiveSession(input_stream=sys.stdin, output_stream=sys.stderr)
