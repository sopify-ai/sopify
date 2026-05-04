"""Generic checkpoint request contract shared by runtime and hosts.

Phase 1 keeps the planning-mode producers authoritative, but it normalizes
their actionable checkpoints through this schema so later skill-native
producers can emit the same contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .clarification import build_scope_clarification_form
from .models import (
    ClarificationState,
    DecisionCheckpoint,
    DecisionOption,
    DecisionRecommendation,
    DecisionState,
    ExecutionSummary,
    PlanArtifact,
    RouteDecision,
    RuntimeConfig,
)

CHECKPOINT_REQUEST_SCHEMA_VERSION = "1"
CHECKPOINT_KINDS = ("clarification", "decision")
CHECKPOINT_SOURCE_STAGES = ("analyze", "design", "develop", "replay", "consult", "custom")
CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED = "checkpoint_request_missing_but_tradeoff_detected"
DEVELOP_RESUME_CONTEXT_REQUIRED_FIELDS = (
    "active_run_stage",
    "current_plan_path",
    "task_refs",
    "changed_files",
    "working_summary",
    "verification_todo",
)
DEVELOP_RESUME_AFTER_ACTIONS = ("continue_host_develop", "review_or_execute_plan")


class CheckpointRequestError(ValueError):
    """Raised when a checkpoint request is malformed or incomplete."""


def develop_resume_context_issue(resume_context: Mapping[str, Any] | None) -> str | None:
    """Return a stable issue code when develop resume context is incomplete."""
    if not isinstance(resume_context, Mapping):
        return "develop_resume_context_missing"

    missing_fields = [field for field in DEVELOP_RESUME_CONTEXT_REQUIRED_FIELDS if field not in resume_context]
    if missing_fields:
        return "develop_resume_context_required_fields_missing"
    if not str(resume_context.get("active_run_stage") or "").strip():
        return "develop_resume_context_active_run_stage_missing"
    if not str(resume_context.get("current_plan_path") or "").strip():
        return "develop_resume_context_current_plan_path_missing"
    if not str(resume_context.get("working_summary") or "").strip():
        return "develop_resume_context_working_summary_missing"
    for list_field in ("task_refs", "changed_files", "verification_todo"):
        if not isinstance(resume_context.get(list_field), (list, tuple)):
            return f"develop_resume_context_{list_field}_not_array"
    resume_after = str(resume_context.get("resume_after") or "continue_host_develop")
    if resume_after not in DEVELOP_RESUME_AFTER_ACTIONS:
        return "develop_resume_context_resume_after_invalid"
    return None


def validate_develop_resume_context(
    resume_context: Mapping[str, Any] | None,
    *,
    field_prefix: str = "develop checkpoint_request.resume_context",
) -> None:
    """Raise a domain error when develop resume context violates the contract."""
    issue = develop_resume_context_issue(resume_context)
    if issue is None:
        return

    if not isinstance(resume_context, Mapping):
        raise CheckpointRequestError(f"{field_prefix} is required")
    if issue == "develop_resume_context_required_fields_missing":
        missing_fields = [field for field in DEVELOP_RESUME_CONTEXT_REQUIRED_FIELDS if field not in resume_context]
        raise CheckpointRequestError(
            f"{field_prefix} is missing required fields: {', '.join(missing_fields)}"
        )
    if issue == "develop_resume_context_active_run_stage_missing":
        raise CheckpointRequestError(f"{field_prefix}.active_run_stage is required")
    if issue == "develop_resume_context_current_plan_path_missing":
        raise CheckpointRequestError(f"{field_prefix}.current_plan_path is required")
    if issue == "develop_resume_context_working_summary_missing":
        raise CheckpointRequestError(f"{field_prefix}.working_summary is required")
    if issue == "develop_resume_context_task_refs_not_array":
        raise CheckpointRequestError(f"{field_prefix}.task_refs must be an array")
    if issue == "develop_resume_context_changed_files_not_array":
        raise CheckpointRequestError(f"{field_prefix}.changed_files must be an array")
    if issue == "develop_resume_context_verification_todo_not_array":
        raise CheckpointRequestError(f"{field_prefix}.verification_todo must be an array")
    if issue == "develop_resume_context_resume_after_invalid":
        resume_after = str(resume_context.get("resume_after") or "continue_host_develop")
        raise CheckpointRequestError(
            f"Unsupported {field_prefix}.resume_after: {resume_after or '<missing>'}"
        )
    raise CheckpointRequestError(f"{field_prefix} is invalid")


@dataclass(frozen=True)
class CheckpointRequest:
    """Stable, host-visible checkpoint request emitted by runtime producers."""

    schema_version: str
    checkpoint_kind: str
    checkpoint_id: str
    source_stage: str
    source_route: str
    blocking: bool = True
    source_skill_id: Optional[str] = None
    policy_id: str = ""
    trigger_reason: str = ""
    feature_key: str = ""
    question: str = ""
    summary: str = ""
    context_files: tuple[str, ...] = ()
    options: tuple[DecisionOption, ...] = ()
    checkpoint: Optional[DecisionCheckpoint] = None
    decision_type: str = ""
    recommended_option_id: Optional[str] = None
    default_option_id: Optional[str] = None
    questions: tuple[str, ...] = ()
    missing_facts: tuple[str, ...] = ()
    clarification_form: Optional[Mapping[str, Any]] = None
    execution_summary: Optional[ExecutionSummary] = None
    text_fallback_allowed: bool = True
    resume_route: Optional[str] = None
    resume_action: str = "resume_checkpoint"
    resume_context: Optional[Mapping[str, Any]] = None
    request_text: str = ""
    requested_plan_level: Optional[str] = None
    plan_package_policy: str = "none"
    capture_mode: str = "off"
    candidate_skill_ids: tuple[str, ...] = ()
    confirmed_decision: Optional[Mapping[str, Any]] = None
    proposed_path: str = ""
    reserved_plan_id: str = ""
    estimated_task_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "checkpoint_kind": self.checkpoint_kind,
            "checkpoint_id": self.checkpoint_id,
            "source_stage": self.source_stage,
            "source_route": self.source_route,
            "blocking": self.blocking,
            "source_skill_id": self.source_skill_id,
            "policy_id": self.policy_id,
            "trigger_reason": self.trigger_reason,
            "feature_key": self.feature_key,
            "question": self.question,
            "summary": self.summary,
            "context_files": list(self.context_files),
            "options": [option.to_dict() for option in self.options],
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint is not None else None,
            "decision_type": self.decision_type,
            "recommended_option_id": self.recommended_option_id,
            "default_option_id": self.default_option_id,
            "questions": list(self.questions),
            "missing_facts": list(self.missing_facts),
            "clarification_form": dict(self.clarification_form) if isinstance(self.clarification_form, Mapping) else None,
            "execution_summary": self.execution_summary.to_dict() if self.execution_summary is not None else None,
            "text_fallback_allowed": self.text_fallback_allowed,
            "resume_route": self.resume_route,
            "resume_action": self.resume_action,
            "resume_context": _json_mapping(self.resume_context),
            "request_text": self.request_text,
            "requested_plan_level": self.requested_plan_level,
            "plan_package_policy": self.plan_package_policy,
            "capture_mode": self.capture_mode,
            "candidate_skill_ids": list(self.candidate_skill_ids),
            "confirmed_decision": _json_mapping(self.confirmed_decision) if isinstance(self.confirmed_decision, Mapping) else None,
            "proposed_path": self.proposed_path,
            "reserved_plan_id": self.reserved_plan_id,
            "estimated_task_count": self.estimated_task_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CheckpointRequest":
        checkpoint = data.get("checkpoint")
        execution_summary = data.get("execution_summary")
        clarification_form = data.get("clarification_form")
        return cls(
            schema_version=str(data.get("schema_version") or CHECKPOINT_REQUEST_SCHEMA_VERSION),
            checkpoint_kind=str(data.get("checkpoint_kind") or ""),
            checkpoint_id=str(data.get("checkpoint_id") or ""),
            source_stage=str(data.get("source_stage") or "custom"),
            source_route=str(data.get("source_route") or ""),
            blocking=bool(data.get("blocking", True)),
            source_skill_id=str(data.get("source_skill_id") or "").strip() or None,
            policy_id=str(data.get("policy_id") or ""),
            trigger_reason=str(data.get("trigger_reason") or ""),
            feature_key=str(data.get("feature_key") or ""),
            question=str(data.get("question") or ""),
            summary=str(data.get("summary") or ""),
            context_files=tuple(str(item) for item in (data.get("context_files") or ()) if str(item).strip()),
            options=tuple(DecisionOption.from_dict(option) for option in (data.get("options") or ())),
            checkpoint=DecisionCheckpoint.from_dict(checkpoint) if isinstance(checkpoint, Mapping) else None,
            decision_type=str(data.get("decision_type") or ""),
            recommended_option_id=data.get("recommended_option_id") or None,
            default_option_id=data.get("default_option_id") or None,
            questions=tuple(str(item) for item in (data.get("questions") or ()) if str(item).strip()),
            missing_facts=tuple(str(item) for item in (data.get("missing_facts") or ()) if str(item).strip()),
            clarification_form=dict(clarification_form) if isinstance(clarification_form, Mapping) else None,
            execution_summary=ExecutionSummary.from_dict(execution_summary) if isinstance(execution_summary, Mapping) else None,
            text_fallback_allowed=bool(data.get("text_fallback_allowed", True)),
            resume_route=str(data.get("resume_route") or "").strip() or None,
            resume_action=str(data.get("resume_action") or "resume_checkpoint"),
            resume_context=_json_mapping(data.get("resume_context")) if isinstance(data.get("resume_context"), Mapping) else None,
            request_text=str(data.get("request_text") or ""),
            requested_plan_level=str(data.get("requested_plan_level") or "").strip() or None,
            plan_package_policy=str(data.get("plan_package_policy") or "none"),
            capture_mode=str(data.get("capture_mode") or "off"),
            candidate_skill_ids=tuple(str(item) for item in (data.get("candidate_skill_ids") or ()) if str(item).strip()),
            confirmed_decision=_json_mapping(data.get("confirmed_decision")) if isinstance(data.get("confirmed_decision"), Mapping) else None,
            proposed_path=str(data.get("proposed_path") or ""),
            reserved_plan_id=str(data.get("reserved_plan_id") or ""),
            estimated_task_count=int(data.get("estimated_task_count") or 0),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )


def normalize_checkpoint_request(raw_request: Mapping[str, Any] | CheckpointRequest) -> CheckpointRequest:
    """Validate and normalize an arbitrary checkpoint request payload."""
    request = raw_request if isinstance(raw_request, CheckpointRequest) else CheckpointRequest.from_dict(raw_request)
    _validate_checkpoint_request(request)
    return request


def checkpoint_request_from_decision_state(
    decision_state: DecisionState,
    *,
    source_stage: Optional[str] = None,
    source_route: Optional[str] = None,
) -> CheckpointRequest:
    """Project an actionable decision state into the generic checkpoint schema."""
    checkpoint = decision_state.active_checkpoint
    return normalize_checkpoint_request(
        CheckpointRequest(
            schema_version=CHECKPOINT_REQUEST_SCHEMA_VERSION,
            checkpoint_kind="decision",
            checkpoint_id=decision_state.decision_id,
            source_stage=source_stage or decision_state.phase or "design",
            source_route=source_route or decision_state.resume_route or "workflow",
            blocking=checkpoint.blocking,
            policy_id=decision_state.policy_id,
            trigger_reason=decision_state.trigger_reason,
            feature_key=decision_state.feature_key,
            question=decision_state.question,
            summary=decision_state.summary,
            context_files=decision_state.context_files,
            options=decision_state.options,
            checkpoint=checkpoint,
            decision_type=decision_state.decision_type,
            recommended_option_id=decision_state.recommended_option_id,
            default_option_id=decision_state.default_option_id,
            text_fallback_allowed=checkpoint.allow_text_fallback,
            resume_route=decision_state.resume_route,
            request_text=decision_state.request_text,
            requested_plan_level=decision_state.requested_plan_level,
            plan_package_policy=decision_state.plan_package_policy,
            capture_mode=decision_state.capture_mode,
            candidate_skill_ids=decision_state.candidate_skill_ids,
            resume_context=decision_state.resume_context,
            created_at=decision_state.created_at,
            updated_at=decision_state.updated_at,
        )
    )


def checkpoint_request_from_clarification_state(
    clarification_state: ClarificationState,
    *,
    config: RuntimeConfig,
    source_stage: Optional[str] = None,
    source_route: Optional[str] = None,
) -> CheckpointRequest:
    """Project an actionable clarification state into the generic checkpoint schema."""
    clarification_form = build_scope_clarification_form(clarification_state, language=config.language)
    text_fallback = clarification_form.get("text_fallback")
    text_fallback_allowed = True
    if isinstance(text_fallback, Mapping):
        text_fallback_allowed = bool(text_fallback.get("allowed", True))
    return normalize_checkpoint_request(
        CheckpointRequest(
            schema_version=CHECKPOINT_REQUEST_SCHEMA_VERSION,
            checkpoint_kind="clarification",
            checkpoint_id=clarification_state.clarification_id,
            source_stage=source_stage or clarification_state.phase or "analyze",
            source_route=source_route or clarification_state.resume_route or "workflow",
            blocking=True,
            feature_key=clarification_state.feature_key,
            question=clarification_state.summary,
            summary=clarification_state.summary,
            context_files=clarification_state.context_files,
            questions=clarification_state.questions,
            missing_facts=clarification_state.missing_facts,
            clarification_form=clarification_form,
            text_fallback_allowed=text_fallback_allowed,
            resume_route=clarification_state.resume_route,
            request_text=clarification_state.request_text,
            requested_plan_level=clarification_state.requested_plan_level,
            plan_package_policy=clarification_state.plan_package_policy,
            capture_mode=clarification_state.capture_mode,
            candidate_skill_ids=clarification_state.candidate_skill_ids,
            resume_context=clarification_state.resume_context,
            created_at=clarification_state.created_at,
            updated_at=clarification_state.updated_at,
        )
    )



def _validate_checkpoint_request(request: CheckpointRequest) -> None:
    if request.schema_version != CHECKPOINT_REQUEST_SCHEMA_VERSION:
        raise CheckpointRequestError(
            f"Unsupported checkpoint_request.schema_version: {request.schema_version or '<missing>'}"
        )
    if request.checkpoint_kind not in CHECKPOINT_KINDS:
        raise CheckpointRequestError(
            f"Unsupported checkpoint_request.checkpoint_kind: {request.checkpoint_kind or '<missing>'}"
        )
    if request.source_stage not in CHECKPOINT_SOURCE_STAGES:
        raise CheckpointRequestError(
            f"Unsupported checkpoint_request.source_stage: {request.source_stage or '<missing>'}"
        )
    if not request.checkpoint_id.strip():
        raise CheckpointRequestError("checkpoint_request.checkpoint_id is required")
    if not request.source_route.strip():
        raise CheckpointRequestError("checkpoint_request.source_route is required")
    if request.source_stage == "develop" and request.checkpoint_kind in {"decision", "clarification"}:
        _validate_develop_resume_context(request)
    if request.checkpoint_kind == "decision":
        _validate_decision_request(request)
    elif request.checkpoint_kind == "clarification":
        _validate_clarification_request(request)
    # Wave 3b: fail-close on unknown checkpoint kinds — no more execution_confirm fallback.


def _validate_decision_request(request: CheckpointRequest) -> None:
    checkpoint = request.checkpoint
    if checkpoint is None and len(request.options) < 2:
        raise CheckpointRequestError("decision checkpoint_request must provide a checkpoint or at least two options")
    if checkpoint is not None and not checkpoint.fields:
        raise CheckpointRequestError("decision checkpoint_request.checkpoint.fields cannot be empty")
    if checkpoint is not None and request.options and checkpoint.fields:
        primary_field = next((field for field in checkpoint.fields if field.field_id == checkpoint.primary_field_id), checkpoint.fields[0])
        if primary_field.field_type in {"select", "multi_select"} and not primary_field.options and request.options:
            raise CheckpointRequestError("decision checkpoint_request.checkpoint primary field is missing options")
    if not (request.question.strip() or request.summary.strip()):
        raise CheckpointRequestError("decision checkpoint_request must provide question or summary")


def _validate_clarification_request(request: CheckpointRequest) -> None:
    if not request.summary.strip():
        raise CheckpointRequestError("clarification checkpoint_request.summary is required")
    if not request.missing_facts and not request.questions:
        raise CheckpointRequestError("clarification checkpoint_request requires missing_facts or questions")



def _validate_develop_resume_context(request: CheckpointRequest) -> None:
    validate_develop_resume_context(request.resume_context)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _json_mapping(value: Any) -> Optional[dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    return {str(key): _json_value(item) for key, item in value.items()}
