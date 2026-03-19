"""Checkpoint-request materialization helpers.

The materializer keeps one conversion path from generic checkpoint requests
back into concrete runtime state files and host actions.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ClarificationState, DecisionCheckpoint, DecisionField, DecisionRecommendation, DecisionState, ExecutionSummary, RuntimeConfig
from .state import iso_now
from .checkpoint_request import CheckpointRequest, normalize_checkpoint_request


@dataclass(frozen=True)
class CheckpointMaterialization:
    """Concrete runtime objects created from a normalized checkpoint request."""

    request: CheckpointRequest
    required_host_action: str
    clarification_state: ClarificationState | None = None
    decision_state: DecisionState | None = None
    execution_summary: ExecutionSummary | None = None


def materialize_checkpoint_request(
    raw_request: CheckpointRequest | dict[str, object],
    *,
    config: RuntimeConfig,
) -> CheckpointMaterialization:
    """Create concrete runtime state from a generic checkpoint request."""
    request = normalize_checkpoint_request(raw_request)
    if request.checkpoint_kind == "clarification":
        return CheckpointMaterialization(
            request=request,
            required_host_action="answer_questions",
            clarification_state=_materialize_clarification_state(request),
        )
    if request.checkpoint_kind == "decision":
        return CheckpointMaterialization(
            request=request,
            required_host_action="confirm_decision",
            decision_state=_materialize_decision_state(request),
        )
    return CheckpointMaterialization(
        request=request,
        required_host_action="confirm_execute",
        execution_summary=request.execution_summary,
    )


def _materialize_clarification_state(request: CheckpointRequest) -> ClarificationState:
    now = request.updated_at or request.created_at or iso_now()
    created_at = request.created_at or now
    return ClarificationState(
        clarification_id=request.checkpoint_id,
        feature_key=request.feature_key or request.checkpoint_id,
        phase=request.source_stage,
        status="pending",
        summary=request.summary or request.question,
        questions=request.questions,
        missing_facts=request.missing_facts,
        context_files=request.context_files,
        resume_route=request.resume_route or request.source_route,
        request_text=request.request_text,
        requested_plan_level=request.requested_plan_level,
        capture_mode=request.capture_mode,
        candidate_skill_ids=request.candidate_skill_ids,
        resume_context=request.resume_context or {},
        created_at=created_at,
        updated_at=now,
    )


def _materialize_decision_state(request: CheckpointRequest) -> DecisionState:
    checkpoint = request.checkpoint or _fallback_checkpoint(request)
    options = request.options or _options_from_checkpoint(checkpoint)
    now = request.updated_at or request.created_at or iso_now()
    created_at = request.created_at or now
    return DecisionState(
        schema_version="2",
        decision_id=request.checkpoint_id,
        feature_key=request.feature_key or request.checkpoint_id,
        phase=request.source_stage,
        status="pending",
        decision_type=request.decision_type or "design_choice",
        question=request.question or request.summary,
        summary=request.summary or request.question,
        options=options,
        checkpoint=checkpoint,
        recommended_option_id=request.recommended_option_id or _recommended_option_id(checkpoint),
        default_option_id=request.default_option_id or _default_option_id(checkpoint),
        context_files=request.context_files,
        resume_route=request.resume_route or request.source_route,
        request_text=request.request_text,
        requested_plan_level=request.requested_plan_level,
        capture_mode=request.capture_mode,
        candidate_skill_ids=request.candidate_skill_ids,
        policy_id=request.policy_id,
        trigger_reason=request.trigger_reason,
        resume_context=request.resume_context or {},
        created_at=created_at,
        updated_at=now,
    )


def _fallback_checkpoint(request: CheckpointRequest) -> DecisionCheckpoint:
    recommendation = None
    if request.recommended_option_id:
        recommendation = DecisionRecommendation(
            field_id="selected_option_id",
            option_id=request.recommended_option_id,
            summary=request.summary,
            reason=request.summary,
        )
    return DecisionCheckpoint(
        checkpoint_id=request.checkpoint_id,
        title=request.question or request.summary or request.decision_type or "Decision",
        message=request.summary or request.question,
        fields=(
            DecisionField(
                field_id="selected_option_id",
                field_type="select",
                label=request.question or "Decision",
                description=request.summary,
                required=True,
                options=request.options,
                default_value=request.default_option_id or request.recommended_option_id,
            ),
        ),
        primary_field_id="selected_option_id",
        recommendation=recommendation,
        blocking=request.blocking,
        allow_text_fallback=request.text_fallback_allowed,
    )


def _options_from_checkpoint(checkpoint: DecisionCheckpoint) -> tuple:
    for field in checkpoint.fields:
        if field.field_type in {"select", "multi_select"} and field.options:
            return field.options
    return ()


def _recommended_option_id(checkpoint: DecisionCheckpoint) -> str | None:
    recommendation = checkpoint.recommendation
    if recommendation is None:
        return None
    return recommendation.option_id


def _default_option_id(checkpoint: DecisionCheckpoint) -> str | None:
    for field in checkpoint.fields:
        if field.field_id == checkpoint.primary_field_id:
            return field.default_value if isinstance(field.default_value, str) else None
    return None
