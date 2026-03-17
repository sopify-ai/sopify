"""Structured handoff contract for downstream host execution."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping, Sequence

from .decision import CURRENT_DECISION_RELATIVE_PATH
from .models import KbArtifact, PlanArtifact, RouteDecision, RuntimeHandoff

HANDOFF_SCHEMA_VERSION = "1"
CURRENT_HANDOFF_FILENAME = "current_handoff.json"
CURRENT_HANDOFF_RELATIVE_PATH = f".sopify-skills/state/{CURRENT_HANDOFF_FILENAME}"

_ROUTE_HANDOFF_KIND = {
    "plan_only": "plan",
    "workflow": "workflow",
    "light_iterate": "light_iterate",
    "quick_fix": "quick_fix",
    "resume_active": "develop",
    "exec_plan": "develop",
    "decision_pending": "decision",
    "decision_resume": "decision",
    "compare": "compare",
    "replay": "replay",
    "consult": "consult",
}


def build_runtime_handoff(
    *,
    decision: RouteDecision,
    run_id: str,
    current_plan: PlanArtifact | None,
    kb_artifact: KbArtifact | None,
    replay_session_dir: str | None,
    skill_result: Mapping[str, Any] | None,
    current_decision: Any | None,
    notes: Sequence[str],
) -> RuntimeHandoff | None:
    """Build the structured host handoff for an actionable route."""
    handoff_kind = _ROUTE_HANDOFF_KIND.get(decision.route_name)
    if handoff_kind is None:
        return None

    normalized_notes = tuple(note.strip() for note in notes if note and note.strip())
    if not normalized_notes and decision.reason:
        normalized_notes = (decision.reason,)

    return RuntimeHandoff(
        schema_version=HANDOFF_SCHEMA_VERSION,
        route_name=decision.route_name,
        run_id=run_id,
        plan_id=current_plan.plan_id if current_plan is not None else None,
        plan_path=current_plan.path if current_plan is not None else None,
        handoff_kind=handoff_kind,
        required_host_action=_required_host_action(
            decision.route_name,
            skill_result_present=bool(skill_result),
        ),
        recommended_skill_ids=tuple(decision.candidate_skill_ids),
        artifacts=_collect_handoff_artifacts(
            current_plan=current_plan,
            kb_artifact=kb_artifact,
            replay_session_dir=replay_session_dir,
            skill_result=skill_result,
            current_decision=current_decision,
        ),
        notes=normalized_notes,
    )


def read_runtime_handoff(path: Path) -> RuntimeHandoff | None:
    """Read a handoff file if it exists."""
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return RuntimeHandoff.from_dict(payload)


def write_runtime_handoff(path: Path, handoff: RuntimeHandoff) -> None:
    """Persist a handoff file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
        json.dump(handoff.to_dict(), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _required_host_action(route_name: str, *, skill_result_present: bool) -> str:
    if route_name == "plan_only":
        return "review_or_execute_plan"
    if route_name in {"workflow", "light_iterate"}:
        return "continue_host_workflow"
    if route_name in {"resume_active", "exec_plan"}:
        return "continue_host_develop"
    if route_name == "quick_fix":
        return "continue_host_quick_fix"
    if route_name in {"decision_pending", "decision_resume"}:
        return "confirm_decision"
    if route_name == "compare":
        return "review_compare_results" if skill_result_present else "host_compare_bridge_required"
    if route_name == "replay":
        return "host_replay_bridge_required"
    if route_name == "consult":
        return "continue_host_consult"
    return "continue_host_workflow"


def _collect_handoff_artifacts(
    *,
    current_plan: PlanArtifact | None,
    kb_artifact: KbArtifact | None,
    replay_session_dir: str | None,
    skill_result: Mapping[str, Any] | None,
    current_decision: Any | None,
) -> Mapping[str, Any]:
    artifacts: dict[str, Any] = {}
    if current_plan is not None and current_plan.files:
        artifacts["plan_files"] = list(current_plan.files)
    if kb_artifact is not None and kb_artifact.files:
        artifacts["kb_files"] = list(kb_artifact.files)
    if replay_session_dir:
        artifacts["replay_session_dir"] = replay_session_dir
    if skill_result:
        artifacts["skill_result_keys"] = sorted(skill_result.keys())
    if current_decision is not None:
        artifacts["decision_file"] = CURRENT_DECISION_RELATIVE_PATH
        artifacts["decision_id"] = getattr(current_decision, "decision_id", None)
        artifacts["decision_status"] = getattr(current_decision, "status", None)
        artifacts["decision_option_ids"] = [getattr(option, "option_id", "") for option in getattr(current_decision, "options", ())]
        artifacts["recommended_option_id"] = getattr(current_decision, "recommended_option_id", None)
    return artifacts
