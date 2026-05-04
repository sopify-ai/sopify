"""Structured handoff contract for downstream host execution."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any, Mapping, Sequence

from .checkpoint_request import (
    CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED,
    checkpoint_request_from_clarification_state,
    checkpoint_request_from_decision_state,
    normalize_checkpoint_request,
)
from .action_projection import ActionProjectionError, build_action_projection, supports_action_projection
from .clarification import CURRENT_CLARIFICATION_RELATIVE_PATH, build_scope_clarification_form, clarification_submission_state_payload
from .deterministic_guard import (
    evaluate_deterministic_guard,
    expected_allowed_response_mode,
    supports_deterministic_guard,
)
from .develop_quality import build_develop_quality_contract, carry_forward_develop_quality_artifacts
from .decision_policy import has_tradeoff_checkpoint_signal
from .decision import CURRENT_DECISION_RELATIVE_PATH
from .entry_guard import build_entry_guard_contract

from .resolution_planner import (
    ResolutionPlannerError,
    build_resolution_planner,
    supports_resolution_planner,
)
from .sidecar_classifier_boundary import (
    SidecarClassifierBoundaryError,
    build_sidecar_classifier_boundary,
    supports_sidecar_classifier_boundary,
)
from .vnext_phase_boundary import (
    VNextPhaseBoundaryError,
    build_vnext_phase_boundary,
    supports_vnext_phase_boundary,
)
from .models import ExecutionSummary, KbArtifact, PlanArtifact, RecoveredContext, RouteDecision, RunState, RuntimeConfig, RuntimeHandoff

HANDOFF_SCHEMA_VERSION = "1"
CURRENT_HANDOFF_FILENAME = "current_handoff.json"
CURRENT_HANDOFF_RELATIVE_PATH = f".sopify-skills/state/{CURRENT_HANDOFF_FILENAME}"

# Canonical route → family mapping (blueprint design.md §Route Families).
# 6 canonical families + non-family surfaces. Wave 3a/3b entries kept as-is.
_ROUTE_HANDOFF_KIND = {
    # plan family
    "plan_only": "plan",
    "workflow": "plan",
    "light_iterate": "plan",
    # develop family
    "quick_fix": "develop",
    "resume_active": "develop",
    "exec_plan": "develop",
    # consult family
    "consult": "consult",
    "replay": "consult",
    # archive family
    "archive_lifecycle": "archive",
    # clarification family
    "clarification_pending": "clarification",
    "clarification_resume": "clarification",
    # decision family
    "decision_pending": "decision",
    "decision_resume": "decision",
    # non-family surface
    "state_conflict": "state_conflict",
}

_STATE_CONFLICT_ABORT_RESUME_ACTIONS = {
    "clarification_pending": "answer_questions",
    "decision_pending": "confirm_decision",
    # Wave 3b: ready_for_execution exits pending-checkpoint negotiation surface,
    # gate ready routes directly to develop.
    "ready_for_execution": "continue_host_develop",
    "develop_pending": "continue_host_develop",
    "executing": "continue_host_develop",
}


def build_runtime_handoff(
    *,
    config: RuntimeConfig,
    decision: RouteDecision,
    run_id: str,
    resolved_context: RecoveredContext,
    current_plan: PlanArtifact | None,
    kb_artifact: KbArtifact | None,
    replay_session_dir: str | None,
    skill_result: Mapping[str, Any] | None,
    notes: Sequence[str],
) -> RuntimeHandoff | None:
    """Build the structured host handoff for an actionable route."""
    # Handoff assembly must consume one resolved context snapshot. The engine
    # may mutate state before this point, but once we start building host-facing
    # truth we must not re-read ad hoc checkpoint files and risk split-brain.
    current_run = resolved_context.current_run
    resolved_plan = current_plan or resolved_context.current_plan
    handoff_kind = _ROUTE_HANDOFF_KIND.get(decision.route_name)
    if handoff_kind is None:
        return None
    if not _should_emit_handoff(decision=decision, current_run=current_run, current_plan=resolved_plan):
        return None

    normalized_notes = tuple(note.strip() for note in notes if note and note.strip())
    if not normalized_notes and decision.reason:
        normalized_notes = (decision.reason,)
    required_host_action = _required_host_action(
        decision,
        current_run=current_run,
        skill_result_present=bool(skill_result),
    )
    artifacts = _collect_handoff_artifacts(
        config=config,
        decision=decision,
        current_run=current_run,
        current_plan=resolved_plan,
        kb_artifact=kb_artifact,
        replay_session_dir=replay_session_dir,
        skill_result=skill_result,
        current_clarification=resolved_context.current_clarification,
        current_decision=resolved_context.current_decision,
        required_host_action=required_host_action,
        previous_handoff=resolved_context.current_handoff,
    )
    guard_reason_code = str(artifacts.get("entry_guard_reason_code") or "").strip()
    if guard_reason_code:
        note = f"entry_guard_reason_code={guard_reason_code}"
        if note not in normalized_notes:
            normalized_notes = (*normalized_notes, note)

    observability = {
        "source": "runtime_handoff",
        "generated_at": _iso_now(),
        "request_excerpt": _summarize_request_text(decision.request_text),
        "request_sha1": _stable_request_sha1(decision.request_text),
        "decision_reason": decision.reason,
        "required_host_action": required_host_action,
    }
    v1_stats = _build_v1_observability_stats(
        required_host_action=required_host_action,
        artifacts=artifacts,
    )
    if v1_stats is not None:
        observability["v1_stats"] = v1_stats

    return RuntimeHandoff(
        schema_version=HANDOFF_SCHEMA_VERSION,
        route_name=decision.route_name,
        run_id=run_id,
        plan_id=resolved_plan.plan_id if resolved_plan is not None else None,
        plan_path=resolved_plan.path if resolved_plan is not None else None,
        handoff_kind=handoff_kind,
        required_host_action=required_host_action,
        recommended_skill_ids=tuple(decision.candidate_skill_ids),
        artifacts=artifacts,
        notes=normalized_notes,
        observability=observability,
    )


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_request_sha1(text: str) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return ""
    return sha1(normalized.encode("utf-8")).hexdigest()[:12]


def _summarize_request_text(text: str, *, limit: int = 120) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    if limit <= 3:
        return compact[:limit]
    return compact[: limit - 3].rstrip() + "..."


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


def _required_host_action(
    decision: RouteDecision,
    *,
    current_run: RunState | None,
    skill_result_present: bool,
) -> str:
    route_name = decision.route_name
    if route_name == "plan_only":
        return "review_or_execute_plan"
    if route_name in {"workflow", "light_iterate"}:
        return "continue_host_develop"
    if route_name == "archive_lifecycle":
        return "continue_host_consult"
    if route_name in {"clarification_pending", "clarification_resume"}:
        return "answer_questions"
    if route_name in {"resume_active", "exec_plan"}:
        return "continue_host_develop"
    if route_name == "quick_fix":
        return "continue_host_develop"
    if route_name in {"decision_pending", "decision_resume"}:
        return "confirm_decision"
    if route_name == "state_conflict":
        if decision.active_run_action != "abort_conflict":
            return "resolve_state_conflict"
        if current_run is not None:
            resume_action = _STATE_CONFLICT_ABORT_RESUME_ACTIONS.get(str(current_run.stage or "").strip())
            if resume_action:
                return resume_action
        return "continue_host_develop"
    if route_name == "consult" or route_name == "replay":
        return "continue_host_consult"
    return "continue_host_develop"


def _collect_handoff_artifacts(
    *,
    config: RuntimeConfig,
    decision: RouteDecision,
    current_run: RunState | None,
    current_plan: PlanArtifact | None,
    kb_artifact: KbArtifact | None,
    replay_session_dir: str | None,
    skill_result: Mapping[str, Any] | None,
    current_clarification: Any | None,
    current_decision: Any | None,
    required_host_action: str,
    previous_handoff: RuntimeHandoff | None,
) -> Mapping[str, Any]:
    artifacts: dict[str, Any] = {}
    entry_guard = build_entry_guard_contract(required_host_action=required_host_action)
    artifacts["entry_guard"] = entry_guard
    explicit_guard_reason_code = str(decision.artifacts.get("entry_guard_reason_code") or "").strip()
    guard_reason_code = str(entry_guard.get("reason_code") or "").strip()
    if explicit_guard_reason_code:
        artifacts["entry_guard_reason_code"] = explicit_guard_reason_code
    elif guard_reason_code:
        artifacts["entry_guard_reason_code"] = guard_reason_code
    direct_edit_guard_kind = str(decision.artifacts.get("direct_edit_guard_kind") or "").strip()
    if direct_edit_guard_kind:
        artifacts["direct_edit_guard_kind"] = direct_edit_guard_kind
    direct_edit_guard_trigger = str(decision.artifacts.get("direct_edit_guard_trigger") or "").strip()
    if direct_edit_guard_trigger:
        artifacts["direct_edit_guard_trigger"] = direct_edit_guard_trigger
    consult_mode = str(decision.artifacts.get("consult_mode") or "").strip()
    if consult_mode:
        artifacts["consult_mode"] = consult_mode
    consult_override_reason_code = str(decision.artifacts.get("consult_override_reason_code") or "").strip()
    if consult_override_reason_code:
        artifacts["consult_override_reason_code"] = consult_override_reason_code
    state_conflict_payload = decision.artifacts.get("state_conflict")
    if required_host_action == "resolve_state_conflict" and isinstance(state_conflict_payload, Mapping):
        artifacts["state_conflict"] = dict(state_conflict_payload)
    raw_quarantined_items = decision.artifacts.get("quarantined_items")
    if isinstance(raw_quarantined_items, list):
        artifacts["quarantined_items"] = list(raw_quarantined_items)
    execution_summary_payload = None
    if current_run is not None:
        artifacts["run_stage"] = current_run.stage
        if current_run.execution_gate is not None:
            artifacts["execution_gate"] = current_run.execution_gate.to_dict()
    if current_plan is not None and _should_attach_execution_summary(decision=decision, current_run=current_run):
        execution_summary_payload = build_execution_summary(
            plan_artifact=current_plan,
            config=config,
        )
        artifacts["execution_summary"] = execution_summary_payload.to_dict()
    if current_plan is not None and current_plan.files:
        artifacts["plan_files"] = list(current_plan.files)
    if required_host_action == "continue_host_develop":
        artifacts["develop_quality_contract"] = build_develop_quality_contract()
        carry_forward_develop_quality_artifacts(artifacts, source=decision.artifacts)
        if (
            previous_handoff is not None
            and current_plan is not None
            and previous_handoff.plan_id == current_plan.plan_id
        ):
            carry_forward_develop_quality_artifacts(artifacts, source=previous_handoff.artifacts)
    if decision.route_name == "archive_lifecycle":
        archive_lifecycle = decision.artifacts.get("archive_lifecycle")
        if isinstance(archive_lifecycle, Mapping):
            artifacts["archive_lifecycle"] = dict(archive_lifecycle)
            archive_status = str(archive_lifecycle.get("archive_status") or "").strip()
            subject_path = str(archive_lifecycle.get("archive_subject_path") or "").strip()
            # Canonical two-value receipt status for host consumption.
            artifacts["archive_receipt_status"] = (
                "completed" if archive_status in {"completed", "already_archived"} else "review_required"
            )
            if archive_status in {"completed", "already_archived"}:
                if current_plan is not None:
                    artifacts["archived_plan_path"] = current_plan.path
                elif subject_path:
                    artifacts["archived_plan_path"] = subject_path
            elif subject_path:
                artifacts["active_plan_path"] = subject_path
            elif current_plan is not None:
                artifacts["active_plan_path"] = current_plan.path
            artifacts["state_cleared"] = bool(archive_lifecycle.get("state_cleared", False))
    if kb_artifact is not None and kb_artifact.files:
        artifacts["kb_files"] = list(kb_artifact.files)
        archive_lifecycle = artifacts.get("archive_lifecycle")
        archive_status = (
            str(archive_lifecycle.get("archive_status") or "").strip()
            if isinstance(archive_lifecycle, Mapping)
            else ""
        )
        if decision.route_name == "archive_lifecycle" and archive_status == "completed":
            history_index = next((path for path in kb_artifact.files if path.endswith("history/index.md")), None)
            if history_index:
                artifacts["history_index_path"] = history_index
    if replay_session_dir:
        artifacts["replay_session_dir"] = replay_session_dir
    if skill_result:
        artifacts["skill_result_keys"] = sorted(skill_result.keys())
        tradeoff_signal = has_tradeoff_checkpoint_signal(skill_result)
        raw_checkpoint_request = skill_result.get("checkpoint_request")
        if isinstance(raw_checkpoint_request, Mapping):
            try:
                normalized_request = normalize_checkpoint_request(raw_checkpoint_request)
                artifacts["checkpoint_request"] = normalized_request.to_dict()
                _attach_resume_context_artifacts(
                    artifacts,
                    resume_context=normalized_request.resume_context,
                    phase=normalized_request.source_stage,
                )
            except ValueError:
                # Keep the handoff stable even when a skill emits malformed data.
                error_code = "invalid_skill_checkpoint_request"
                if tradeoff_signal:
                    error_code = CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED
                    artifacts["checkpoint_request_reason_code"] = CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED
                artifacts["checkpoint_request_error"] = error_code
        elif tradeoff_signal:
            artifacts["checkpoint_request_error"] = CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED
            artifacts["checkpoint_request_reason_code"] = CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED
    if current_clarification is not None:
        artifacts["clarification_file"] = CURRENT_CLARIFICATION_RELATIVE_PATH
        artifacts["clarification_id"] = getattr(current_clarification, "clarification_id", None)
        artifacts["clarification_status"] = getattr(current_clarification, "status", None)
        artifacts["missing_facts"] = list(getattr(current_clarification, "missing_facts", ()))
        artifacts["questions"] = list(getattr(current_clarification, "questions", ()))
        artifacts["clarification_form"] = build_scope_clarification_form(
            current_clarification,
            language=config.language,
        )
        artifacts["clarification_submission_state"] = clarification_submission_state_payload(current_clarification)
        artifacts["checkpoint_request"] = checkpoint_request_from_clarification_state(
            current_clarification,
            config=config,
            source_route=decision.route_name,
        ).to_dict()
        _attach_resume_context_artifacts(
            artifacts,
            resume_context=getattr(current_clarification, "resume_context", None),
            phase=getattr(current_clarification, "phase", None),
        )
    if current_decision is not None:
        artifacts["decision_file"] = CURRENT_DECISION_RELATIVE_PATH
        artifacts["decision_id"] = getattr(current_decision, "decision_id", None)
        artifacts["decision_status"] = getattr(current_decision, "status", None)
        artifacts["decision_option_ids"] = [getattr(option, "option_id", "") for option in getattr(current_decision, "options", ())]
        artifacts["recommended_option_id"] = getattr(current_decision, "recommended_option_id", None)
        artifacts["decision_primary_field_id"] = getattr(current_decision, "primary_field_id", None)
        artifacts["selected_option_id"] = getattr(current_decision, "selected_option_id", None)
        artifacts["decision_policy_id"] = getattr(current_decision, "policy_id", None)
        artifacts["decision_trigger_reason"] = getattr(current_decision, "trigger_reason", None)
        checkpoint = getattr(current_decision, "active_checkpoint", None)
        if checkpoint is not None and hasattr(checkpoint, "to_dict"):
            artifacts["decision_checkpoint"] = checkpoint.to_dict()
        artifacts["decision_submission_state"] = _decision_submission_state(current_decision)
        artifacts["checkpoint_request"] = checkpoint_request_from_decision_state(
            current_decision,
            source_route=decision.route_name,
            source_stage="develop" if getattr(current_decision, "phase", None) == "execution_gate" else None,
        ).to_dict()
        _attach_resume_context_artifacts(
            artifacts,
            resume_context=getattr(current_decision, "resume_context", None),
            phase=getattr(current_decision, "phase", None),
        )
    # Archive lifecycle is a terminal receipt surface — it expresses results
    # via archive_lifecycle artifact + archive_receipt_status, not via the
    # consult guard/projection surface it borrows as transport label.
    if decision.route_name != "archive_lifecycle":
        _attach_v1_guardrail_artifacts(
            artifacts,
            required_host_action=required_host_action,
            current_run=current_run,
            current_plan=current_plan,
        )
    return artifacts


def _decision_submission_state(current_decision: Any) -> Mapping[str, Any]:
    submission = getattr(current_decision, "submission", None)
    if submission is None:
        return {
            "status": "empty",
            "source": None,
            "resume_action": None,
            "submitted_at": None,
            "has_answers": False,
            "answer_keys": [],
        }

    answers = getattr(submission, "answers", {})
    answer_keys = sorted(str(key) for key in answers.keys()) if isinstance(answers, Mapping) else []
    payload: dict[str, Any] = {
        "status": getattr(submission, "status", "empty"),
        "source": getattr(submission, "source", None),
        "resume_action": getattr(submission, "resume_action", None),
        "submitted_at": getattr(submission, "submitted_at", None),
        "has_answers": bool(answer_keys),
        "answer_keys": answer_keys,
    }
    message = str(getattr(submission, "message", "") or "").strip()
    if message:
        payload["message"] = message
    return payload


def _attach_resume_context_artifacts(
    artifacts: dict[str, Any],
    *,
    resume_context: Any,
    phase: Any,
) -> None:
    if not isinstance(resume_context, Mapping) or not resume_context:
        return
    normalized = dict(resume_context)
    artifacts["resume_context"] = normalized
    if str(phase or "").strip() == "develop":
        artifacts["develop_resume_context"] = normalized
        carry_forward_develop_quality_artifacts(artifacts, source=normalized)


def _should_attach_execution_summary(*, decision: RouteDecision, current_run: RunState | None) -> bool:
    if current_run is None:
        return False
    if current_run.stage in {"ready_for_execution", "executing"}:
        return True
    execution_gate = current_run.execution_gate
    return execution_gate is not None and execution_gate.gate_status == "ready"


# ── Plan execution summary helpers (migrated from execution_confirm.py, Wave 3b) ──

_TASK_RE = re.compile(r"^- \[(?: |x|!|-)\]\s+", re.MULTILINE)
_RISK_LEVEL_KEYWORDS = {
    "high": ("认证", "授权", "auth", "schema", "migration", "删除", "drop", "truncate", "权限"),
    "medium": ("边界", "兼容", "回滚", "rollback", "范围", "scope", "tradeoff", "trade-off"),
}


def build_execution_summary(*, plan_artifact: PlanArtifact, config: RuntimeConfig) -> ExecutionSummary:
    """Build the minimum plan summary required before execution."""
    plan_dir = config.workspace_root / plan_artifact.path
    task_text = _read_first_existing(plan_dir, "tasks.md", "plan.md")
    risk_text = _read_first_existing(plan_dir, "background.md", "plan.md", "design.md")

    key_risk = _extract_prefixed_line(risk_text, "- 风险:", "- Risk:") or _default_risk(config.language)
    mitigation = _extract_prefixed_line(risk_text, "- 缓解:", "- Mitigation:") or _default_mitigation(config.language)
    return ExecutionSummary(
        plan_path=plan_artifact.path,
        summary=plan_artifact.summary,
        task_count=len(_TASK_RE.findall(task_text)),
        risk_level=_infer_risk_level(key_risk, mitigation),
        key_risk=key_risk,
        mitigation=mitigation,
    )


def _read_first_existing(plan_dir: Path, *filenames: str) -> str:
    for filename in filenames:
        candidate = plan_dir / filename
        if candidate.exists() and candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return ""


def _extract_prefixed_line(text: str, *prefixes: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        for prefix in prefixes:
            if stripped.casefold().startswith(prefix.casefold()):
                return stripped[len(prefix) :].strip()
    return ""


def _infer_risk_level(key_risk: str, mitigation: str) -> str:
    aggregate_text = f"{key_risk}\n{mitigation}".casefold()
    for level, keywords in _RISK_LEVEL_KEYWORDS.items():
        if any(keyword.casefold() in aggregate_text for keyword in keywords):
            return level
    return "low"


def _default_risk(language: str) -> str:
    if language == "en-US":
        return "No standalone risk was recorded; execution should still stay within the documented scope."
    return "当前未单独记录额外风险，执行时仍需严格约束在已确认范围内。"


def _default_mitigation(language: str) -> str:
    if language == "en-US":
        return "Keep the change minimal, re-check the file scope, and finish with focused verification."
    return "保持最小改动，复核文件范围，并在收口前完成针对性验证。"


def _attach_v1_guardrail_artifacts(
    artifacts: dict[str, Any],
    *,
    required_host_action: str,
    current_run: RunState | None,
    current_plan: PlanArtifact | None,
) -> None:
    if not supports_deterministic_guard(required_host_action):
        return

    allowed_response_mode = expected_allowed_response_mode(required_host_action)
    if not allowed_response_mode:
        return

    guard = evaluate_deterministic_guard(
        allowed_response_mode=allowed_response_mode,
        required_host_action=required_host_action,
        current_run=current_run,
        current_plan=current_plan,
        plan_id=current_plan.plan_id if current_plan is not None else None,
        plan_path=current_plan.path if current_plan is not None else None,
        checkpoint_request=artifacts.get("checkpoint_request")
        if isinstance(artifacts.get("checkpoint_request"), Mapping)
        else None,
        execution_gate=current_run.execution_gate if current_run is not None else artifacts.get("execution_gate"),
    )
    artifacts["deterministic_guard"] = guard.to_dict()

    if supports_action_projection(required_host_action):
        try:
            projection = build_action_projection(
                guard,
                plan_id=current_plan.plan_id if current_plan is not None else None,
                plan_path=current_plan.path if current_plan is not None else None,
                current_run=current_run,
                artifacts=artifacts,
            )
        except ActionProjectionError as exc:
            artifacts["action_projection_error"] = str(exc)
        else:
            artifacts["action_projection"] = projection.to_dict()

    planner = None
    if supports_resolution_planner(required_host_action):
        try:
            planner = build_resolution_planner(guard)
        except ResolutionPlannerError as exc:
            artifacts["resolution_planner_error"] = str(exc)
        else:
            artifacts["resolution_planner"] = planner.to_dict()

    if supports_sidecar_classifier_boundary(required_host_action):
        if planner is None:
            artifacts["sidecar_classifier_boundary_error"] = (
                "Resolution planner unavailable for sidecar boundary"
            )
        else:
            try:
                boundary = build_sidecar_classifier_boundary(guard, planner)
            except SidecarClassifierBoundaryError as exc:
                artifacts["sidecar_classifier_boundary_error"] = str(exc)
            else:
                artifacts["sidecar_classifier_boundary"] = boundary.to_dict()

    if not supports_vnext_phase_boundary(required_host_action):
        return
    try:
        phase_boundary = build_vnext_phase_boundary(guard)
    except VNextPhaseBoundaryError as exc:
        artifacts["vnext_phase_boundary_error"] = str(exc)
        return
    artifacts["vnext_phase_boundary"] = phase_boundary.to_dict()


def _build_v1_observability_stats(
    *,
    required_host_action: str,
    artifacts: Mapping[str, Any],
) -> Mapping[str, str] | None:
    guard = artifacts.get("deterministic_guard")
    if not isinstance(guard, Mapping):
        return None

    checkpoint_kind = str(guard.get("checkpoint_kind") or "").strip() or str(
        required_host_action or ""
    ).strip()
    truth_status = str(guard.get("truth_status") or "").strip()
    unresolved_outcome_family = str(guard.get("unresolved_outcome_family") or "").strip()
    fallback_path = ""
    outcome = "ready"
    if truth_status != "stable":
        outcome = unresolved_outcome_family or "fail_closed"
        fallback_path = str(guard.get("fallback_action") or "").strip()
    else:
        resolution_planner = artifacts.get("resolution_planner")
        if isinstance(resolution_planner, Mapping):
            default_no_candidate = resolution_planner.get("default_no_candidate_recovery")
            if isinstance(default_no_candidate, Mapping):
                fallback_path = str(default_no_candidate.get("fallback_action") or "").strip()

    return {
        "reason_code": str(guard.get("reason_code") or "").strip(),
        "outcome": outcome,
        "fallback_path": fallback_path or "none",
        "checkpoint_kind": checkpoint_kind or "unknown",
    }


def _should_emit_handoff(*, decision: RouteDecision, current_run: RunState | None, current_plan: PlanArtifact | None) -> bool:
    if decision.route_name == "archive_lifecycle":
        return current_plan is not None or "archive_lifecycle" in decision.artifacts
    if decision.route_name != "exec_plan":
        return True
    # ~go exec is an advanced recovery/debug entry; when it does not converge
    # back into the standard checkpoints, avoid emitting a misleading develop handoff.
    return False
