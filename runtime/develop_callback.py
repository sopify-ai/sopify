"""Structured develop-stage checkpoint callback helpers.

Hosts still own code changes during `continue_host_develop`, but once they hit
an end-user fork they must route back through this callback entry so runtime
can emit the same checkpoint contract used elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from typing import Any, Mapping

from .checkpoint_materializer import CheckpointMaterialization, materialize_checkpoint_request
from .checkpoint_request import (
    CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED,
    CHECKPOINT_REQUEST_SCHEMA_VERSION,
    DEVELOP_RESUME_AFTER_ACTIONS,
    DEVELOP_RESUME_CONTEXT_REQUIRED_FIELDS,
    CheckpointRequest,
    CheckpointRequestError,
    normalize_checkpoint_request,
)
from .develop_quality import (
    DEVELOP_QUALITY_CONTEXT_FIELDS,
    DEVELOP_QUALITY_SCHEMA_VERSION,
    DevelopQualityError,
    attach_develop_quality_artifacts,
    build_develop_quality_contract,
    extract_develop_quality_result,
    normalize_develop_quality_context,
    normalize_develop_quality_result,
    requires_develop_callback,
)
from .decision_policy import has_tradeoff_checkpoint_signal
from .handoff import build_runtime_handoff
from .context_snapshot import resolve_context_snapshot
from .models import PlanArtifact, RecoveredContext, RouteDecision, RunState, RuntimeConfig, RuntimeHandoff
from .replay import ReplayWriter, build_develop_quality_replay_event
from .state import StateStore, iso_now

_HOST_FACING_TRUTH_KIND_DEVELOP_CALLBACK = "develop_callback"

DEVELOP_CALLBACK_SCHEMA_VERSION = "1"
DEVELOP_CALLBACK_ALLOWED_KINDS = ("decision", "clarification")
DEVELOP_CALLBACK_ACTIVE_STAGES = {"develop_pending", "executing"}
DEVELOP_CALLBACK_SOURCE_SKILL_ID = "develop_callback"


class DevelopCallbackError(ValueError):
    """Raised when a host tries to create an invalid develop callback checkpoint."""


@dataclass(frozen=True)
class ActiveDevelopContext:
    """Runtime state that proves the host is currently inside develop execution."""

    state_store: StateStore
    current_run: RunState
    current_plan: PlanArtifact
    current_handoff: RuntimeHandoff
    resolution_id: str


@dataclass(frozen=True)
class DevelopCallbackSubmission:
    """Normalized develop callback output written back into runtime state."""

    request: CheckpointRequest
    materialized: CheckpointMaterialization
    run_state: RunState
    route: RouteDecision
    handoff: RuntimeHandoff


@dataclass(frozen=True)
class DevelopQualitySubmission:
    """Normalized develop quality-loop report written back into runtime state."""

    quality_context: Mapping[str, Any]
    quality_result: Mapping[str, Any]
    run_state: RunState
    handoff: RuntimeHandoff
    replay_session_dir: str | None
    delegated_callback: DevelopCallbackSubmission | None = None


def inspect_develop_callback_context(*, config: RuntimeConfig) -> Mapping[str, Any]:
    """Return the current develop context expected by the host callback entry."""
    context = load_active_develop_context(config=config)
    execution_gate = context.current_run.execution_gate
    return {
        "status": "ready",
        "required_host_action": context.current_handoff.required_host_action,
        "active_run": {
            "run_id": context.current_run.run_id,
            "stage": context.current_run.stage,
            "route_name": context.current_run.route_name,
            "title": context.current_run.title,
            "plan_id": context.current_run.plan_id,
            "plan_path": context.current_run.plan_path,
            "execution_gate": execution_gate.to_dict() if execution_gate is not None else None,
        },
        "plan": {
            "plan_id": context.current_plan.plan_id,
            "path": context.current_plan.path,
            "level": context.current_plan.level,
        },
        "required_resume_context_fields": list(DEVELOP_RESUME_CONTEXT_REQUIRED_FIELDS),
        "allowed_resume_after": list(DEVELOP_RESUME_AFTER_ACTIONS),
        "quality_contract": build_develop_quality_contract(),
        "quality_context_fields": list(DEVELOP_QUALITY_CONTEXT_FIELDS),
    }


def load_active_develop_context(*, config: RuntimeConfig) -> ActiveDevelopContext:
    """Load the minimum runtime state required before a host may emit a develop callback."""
    state_store = StateStore(config)
    snapshot = resolve_context_snapshot(
        config=config,
        review_store=state_store,
        global_store=state_store,
    )
    if snapshot.is_conflict:
        raise DevelopCallbackError("develop callback is unavailable while runtime state_conflict is active")
    current_run = snapshot.current_run
    current_plan = snapshot.current_plan
    current_handoff = snapshot.current_handoff

    if current_run is None or current_plan is None or current_handoff is None:
        raise DevelopCallbackError(
            "develop callback requires an active plan, run, and handoff from continue_host_develop"
        )
    if current_handoff.required_host_action != "continue_host_develop":
        raise DevelopCallbackError(
            "develop callback is only allowed after current_handoff.required_host_action == continue_host_develop"
        )
    if current_run.stage not in DEVELOP_CALLBACK_ACTIVE_STAGES:
        raise DevelopCallbackError(
            f"develop callback is only allowed during {sorted(DEVELOP_CALLBACK_ACTIVE_STAGES)}, got {current_run.stage}"
        )

    existing_clarification = snapshot.current_clarification
    if existing_clarification is not None and existing_clarification.status in {"pending", "collecting"}:
        raise DevelopCallbackError("a clarification checkpoint is already pending; resume it before creating another")

    existing_decision = snapshot.current_decision
    if existing_decision is not None and existing_decision.status in {"pending", "collecting"}:
        raise DevelopCallbackError("a decision checkpoint is already pending; resume it before creating another")

    return ActiveDevelopContext(
        state_store=state_store,
        current_run=current_run,
        current_plan=current_plan,
        current_handoff=current_handoff,
        resolution_id=snapshot.resolution_id,
    )


def submit_develop_callback(
    raw_payload: Mapping[str, Any],
    *,
    config: RuntimeConfig,
) -> DevelopCallbackSubmission:
    """Normalize a host callback payload into runtime checkpoint state and handoff."""
    context = load_active_develop_context(config=config)
    request = build_develop_callback_request(raw_payload, config=config, context=context)
    materialized = materialize_checkpoint_request(request.to_dict(), config=config)

    route = _develop_callback_route(request=request, current_plan=context.current_plan)
    run_state = _develop_callback_run_state(
        context=context,
        request=request,
        materialized=materialized,
    )

    state_store = context.state_store
    if materialized.clarification_state is not None:
        state_store.clear_current_decision()
        state_store.set_current_clarification(materialized.clarification_state)
    if materialized.decision_state is not None:
        state_store.clear_current_clarification()
        state_store.set_current_decision(materialized.decision_state)

    handoff = build_runtime_handoff(
        config=config,
        decision=route,
        run_id=run_state.run_id,
        resolved_context=RecoveredContext(
            current_run=run_state,
            current_plan=context.current_plan,
            current_handoff=context.current_handoff,
            current_clarification=materialized.clarification_state,
            current_decision=materialized.decision_state,
        ),
        current_plan=context.current_plan,
        kb_artifact=None,
        replay_session_dir=None,
        skill_result={"checkpoint_request": request.to_dict()},
        notes=(
            f"Develop callback created: {request.checkpoint_id}",
            f"Develop callback resume_after={develop_resume_after(request.resume_context)}",
        ),
    )
    if handoff is None:  # pragma: no cover - defensive guard
        raise DevelopCallbackError("develop callback could not build a runtime handoff")

    run_state, handoff = state_store.set_host_facing_truth(
        run_state=run_state,
        handoff=handoff,
        resolution_id=context.resolution_id,
        truth_kind=_HOST_FACING_TRUTH_KIND_DEVELOP_CALLBACK,
    )
    state_store.set_last_route(route)
    return DevelopCallbackSubmission(
        request=request,
        materialized=materialized,
        run_state=run_state,
        route=route,
        handoff=handoff,
    )


def submit_develop_quality_report(
    raw_payload: Mapping[str, Any],
    *,
    config: RuntimeConfig,
) -> DevelopQualitySubmission:
    """Persist a structured develop quality-loop result for the active host flow."""
    context = load_active_develop_context(config=config)
    if not isinstance(raw_payload, Mapping):
        raise DevelopCallbackError("develop quality payload must be an object")

    payload_version = str(raw_payload.get("schema_version") or DEVELOP_QUALITY_SCHEMA_VERSION).strip()
    if payload_version != DEVELOP_QUALITY_SCHEMA_VERSION:
        raise DevelopCallbackError(
            f"unsupported develop quality payload schema_version: {payload_version or '<missing>'}"
        )

    try:
        quality_context = normalize_develop_quality_context(raw_payload)
        raw_quality_result = raw_payload.get("quality_result")
        if isinstance(raw_quality_result, Mapping):
            quality_result = normalize_develop_quality_result(raw_quality_result)
        else:
            quality_result = normalize_develop_quality_result(raw_payload)
    except DevelopQualityError as exc:
        raise DevelopCallbackError(str(exc)) from exc

    if requires_develop_callback(quality_result):
        delegated = _submit_quality_checkpoint(
            raw_payload,
            context=context,
            quality_context=quality_context,
            quality_result=quality_result,
            config=config,
        )
        replay_session_dir = _record_develop_quality_replay(
            config=config,
            context=context,
            quality_context=quality_context,
            quality_result=quality_result,
            run_state=delegated.run_state,
        )
        return DevelopQualitySubmission(
            quality_context=quality_context,
            quality_result=quality_result,
            run_state=delegated.run_state,
            handoff=delegated.handoff,
            replay_session_dir=replay_session_dir,
            delegated_callback=delegated,
        )

    state_store = context.state_store
    run_state = _copy_run_state(context.current_run)
    state_store.set_current_run(run_state)
    handoff = _with_quality_handoff(
        context.current_handoff,
        quality_context=quality_context,
        quality_result=quality_result,
    )
    state_store.set_current_handoff(handoff)
    replay_session_dir = _record_develop_quality_replay(
        config=config,
        context=context,
        quality_context=quality_context,
        quality_result=quality_result,
        run_state=run_state,
    )
    return DevelopQualitySubmission(
        quality_context=quality_context,
        quality_result=quality_result,
        run_state=run_state,
        handoff=handoff,
        replay_session_dir=replay_session_dir,
    )


def build_develop_callback_request(
    raw_payload: Mapping[str, Any],
    *,
    config: RuntimeConfig,
    context: ActiveDevelopContext,
) -> CheckpointRequest:
    """Convert a host callback payload into the generic checkpoint request contract."""
    if not isinstance(raw_payload, Mapping):
        raise DevelopCallbackError("develop callback payload must be an object")

    payload_version = str(raw_payload.get("schema_version") or DEVELOP_CALLBACK_SCHEMA_VERSION)
    if payload_version != DEVELOP_CALLBACK_SCHEMA_VERSION:
        raise DevelopCallbackError(
            f"unsupported develop callback payload schema_version: {payload_version or '<missing>'}"
        )

    tradeoff_signal = has_tradeoff_checkpoint_signal(raw_payload)
    checkpoint_kind = str(raw_payload.get("checkpoint_kind") or "").strip()
    if checkpoint_kind not in DEVELOP_CALLBACK_ALLOWED_KINDS:
        if tradeoff_signal:
            raise DevelopCallbackError(
                f"{CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED}: unsupported develop callback payload kind: {checkpoint_kind or '<missing>'}"
            )
        raise DevelopCallbackError(
            f"unsupported develop callback payload kind: {checkpoint_kind or '<missing>'}"
        )

    now = iso_now()
    resume_context = _normalize_resume_context(raw_payload, context=context)
    summary = str(raw_payload.get("summary") or resume_context.get("working_summary") or "").strip()
    question = str(raw_payload.get("question") or summary).strip()
    checkpoint_id = str(raw_payload.get("checkpoint_id") or "").strip() or _default_checkpoint_id(
        checkpoint_kind=checkpoint_kind,
        run_id=context.current_run.run_id,
        seed_text=question or summary or context.current_plan.plan_id,
    )
    context_files = _normalize_string_list(raw_payload.get("context_files"))
    if not context_files:
        context_files = tuple(
            dict.fromkeys(
                item
                for item in (
                    context.current_plan.path,
                    *context.current_plan.files,
                    *_normalize_string_list(resume_context.get("changed_files")),
                )
                if item
            )
        )

    raw_request = {
        "schema_version": CHECKPOINT_REQUEST_SCHEMA_VERSION,
        "checkpoint_kind": checkpoint_kind,
        "checkpoint_id": checkpoint_id,
        "source_stage": "develop",
        "source_route": str(raw_payload.get("source_route") or context.current_run.route_name or "resume_active"),
        "blocking": bool(raw_payload.get("blocking", True)),
        "source_skill_id": DEVELOP_CALLBACK_SOURCE_SKILL_ID,
        "policy_id": str(raw_payload.get("policy_id") or "develop_callback"),
        "trigger_reason": str(raw_payload.get("trigger_reason") or "host_callback"),
        "feature_key": context.current_plan.plan_id,
        "question": question,
        "summary": summary,
        "context_files": list(context_files),
        "options": raw_payload.get("options") or [],
        "checkpoint": raw_payload.get("checkpoint"),
        "decision_type": str(raw_payload.get("decision_type") or "develop_choice"),
        "recommended_option_id": raw_payload.get("recommended_option_id") or None,
        "default_option_id": raw_payload.get("default_option_id") or None,
        "questions": _normalize_string_list(raw_payload.get("questions")),
        "missing_facts": _normalize_string_list(raw_payload.get("missing_facts")),
        "clarification_form": raw_payload.get("clarification_form"),
        "text_fallback_allowed": bool(raw_payload.get("text_fallback_allowed", True)),
        "resume_route": "resume_active",
        "resume_action": "resume_checkpoint",
        "resume_context": resume_context,
        "request_text": str(raw_payload.get("request_text") or context.current_plan.summary or context.current_run.title),
        "requested_plan_level": context.current_plan.level,
        "capture_mode": str(raw_payload.get("capture_mode") or "off"),
        "candidate_skill_ids": list(_normalize_string_list(raw_payload.get("candidate_skill_ids")) or ("develop",)),
        "created_at": str(raw_payload.get("created_at") or now),
        "updated_at": now,
    }

    try:
        return normalize_checkpoint_request(raw_request)
    except CheckpointRequestError as exc:
        if tradeoff_signal:
            raise DevelopCallbackError(f"{CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED}: {exc}") from exc
        raise DevelopCallbackError(str(exc)) from exc


def is_develop_callback_state(checkpoint_state: Any) -> bool:
    """Return True when a clarification/decision state came from the develop callback path."""
    phase = str(getattr(checkpoint_state, "phase", "") or "").strip()
    resume_context = getattr(checkpoint_state, "resume_context", None)
    return phase == "develop" and isinstance(resume_context, Mapping) and bool(resume_context)


def develop_resume_after(resume_context: Mapping[str, Any] | None) -> str:
    """Return the post-confirmation route target for a develop callback checkpoint."""
    if not isinstance(resume_context, Mapping):
        return "continue_host_develop"
    resume_after = str(resume_context.get("resume_after") or "continue_host_develop")
    if resume_after not in DEVELOP_RESUME_AFTER_ACTIONS:
        return "continue_host_develop"
    return resume_after


def _normalize_resume_context(
    raw_payload: Mapping[str, Any],
    *,
    context: ActiveDevelopContext,
) -> Mapping[str, Any]:
    resume_context = raw_payload.get("resume_context")
    if not isinstance(resume_context, Mapping):
        raise DevelopCallbackError("develop callback payload.resume_context is required")

    normalized = {str(key): value for key, value in resume_context.items()}
    normalized.setdefault("active_run_stage", context.current_run.stage)
    normalized.setdefault("current_plan_path", context.current_plan.path)
    normalized.setdefault("current_run_id", context.current_run.run_id)
    normalized.setdefault("current_route_name", context.current_run.route_name)
    normalized.setdefault("current_plan_id", context.current_plan.plan_id)
    normalized.setdefault("plan_level", context.current_plan.level)
    normalized.setdefault("resume_after", "continue_host_develop")
    normalized.setdefault("required_host_action", context.current_handoff.required_host_action)
    normalized.setdefault("captured_at", iso_now())
    if context.current_run.execution_gate is not None:
        normalized.setdefault("execution_gate", context.current_run.execution_gate.to_dict())

    raw_quality_result = raw_payload.get("quality_result")
    if isinstance(raw_quality_result, Mapping):
        try:
            normalized["develop_quality_result"] = normalize_develop_quality_result(raw_quality_result)
        except DevelopQualityError as exc:
            raise DevelopCallbackError(str(exc)) from exc
    else:
        inherited_quality_result = extract_develop_quality_result(context.current_handoff.artifacts)
        if inherited_quality_result is not None:
            # Preserve the latest stable quality summary across user-facing
            # develop callbacks so resume-active handoffs do not lose it.
            normalized["develop_quality_result"] = inherited_quality_result

    for list_field in ("task_refs", "changed_files", "verification_todo"):
        if list_field in normalized:
            normalized[list_field] = list(_normalize_string_list(normalized.get(list_field)))

    missing = [field for field in DEVELOP_RESUME_CONTEXT_REQUIRED_FIELDS if field not in normalized]
    if missing:
        raise DevelopCallbackError(
            f"develop callback payload.resume_context is missing required fields: {', '.join(missing)}"
        )
    if not str(normalized.get("working_summary") or "").strip():
        raise DevelopCallbackError("develop callback payload.resume_context.working_summary is required")

    resume_after = develop_resume_after(normalized)
    normalized["resume_after"] = resume_after
    return normalized


def _submit_quality_checkpoint(
    raw_payload: Mapping[str, Any],
    *,
    context: ActiveDevelopContext,
    quality_context: Mapping[str, Any],
    quality_result: Mapping[str, Any],
    config: RuntimeConfig,
) -> DevelopCallbackSubmission:
    checkpoint_kind = str(raw_payload.get("checkpoint_kind") or "").strip()
    if checkpoint_kind not in DEVELOP_CALLBACK_ALLOWED_KINDS:
        raise DevelopCallbackError(
            "develop quality replan_required requires checkpoint_kind=decision|clarification so runtime can route through develop_callback"
        )

    checkpoint_payload = {
        key: value
        for key, value in raw_payload.items()
        if key not in {"task_refs", "changed_files", "working_summary", "verification_todo", "quality_result"}
    }
    resume_context = dict(checkpoint_payload.get("resume_context") or {})
    resume_context.setdefault("task_refs", list(quality_context["task_refs"]))
    resume_context.setdefault("changed_files", list(quality_context["changed_files"]))
    resume_context.setdefault("working_summary", quality_context["working_summary"])
    resume_context.setdefault("verification_todo", list(quality_context["verification_todo"]))
    resume_context.setdefault("resume_after", "review_or_execute_plan")
    resume_context["develop_quality_result"] = quality_result
    checkpoint_payload["resume_context"] = resume_context
    checkpoint_payload["quality_result"] = quality_result
    checkpoint_payload.setdefault("summary", quality_context["working_summary"])
    checkpoint_payload.setdefault("request_text", context.current_run.request_excerpt or context.current_plan.summary)
    return submit_develop_callback(checkpoint_payload, config=config)


def _develop_callback_route(*, request: CheckpointRequest, current_plan: PlanArtifact) -> RouteDecision:
    route_name = "decision_pending" if request.checkpoint_kind == "decision" else "clarification_pending"
    reason = (
        "Develop callback requires user confirmation before host-side implementation can continue"
        if request.checkpoint_kind == "decision"
        else "Develop callback requires missing facts before host-side implementation can continue"
    )
    return RouteDecision(
        route_name=route_name,
        request_text=request.request_text,
        reason=reason,
        complexity="medium",
        plan_level=current_plan.level,
        candidate_skill_ids=request.candidate_skill_ids or ("develop",),
        should_recover_context=True,
        should_create_plan=False,
        capture_mode=request.capture_mode,
        active_run_action="inspect_decision" if route_name == "decision_pending" else "inspect_clarification",
    )


def _with_quality_handoff(
    current_handoff: RuntimeHandoff,
    *,
    quality_context: Mapping[str, Any],
    quality_result: Mapping[str, Any],
) -> RuntimeHandoff:
    artifacts = dict(current_handoff.artifacts)
    artifacts["develop_quality_contract"] = build_develop_quality_contract()
    attach_develop_quality_artifacts(
        artifacts,
        quality_result=quality_result,
        quality_context=quality_context,
    )

    notes = tuple(
        dict.fromkeys(
            (
                *current_handoff.notes,
                f"Develop quality result recorded: {quality_result['result']}",
            )
        )
    )
    observability = dict(current_handoff.observability)
    observability["develop_quality_result"] = quality_result["result"]
    observability["updated_at"] = iso_now()
    return RuntimeHandoff(
        schema_version=current_handoff.schema_version,
        route_name=current_handoff.route_name,
        run_id=current_handoff.run_id,
        plan_id=current_handoff.plan_id,
        plan_path=current_handoff.plan_path,
        handoff_kind=current_handoff.handoff_kind,
        required_host_action=current_handoff.required_host_action,
        recommended_skill_ids=current_handoff.recommended_skill_ids,
        artifacts=artifacts,
        notes=notes,
        observability=observability,
        resolution_id=current_handoff.resolution_id,
    )


def _record_develop_quality_replay(
    *,
    config: RuntimeConfig,
    context: ActiveDevelopContext,
    quality_context: Mapping[str, Any],
    quality_result: Mapping[str, Any],
    run_state: RunState | None = None,
) -> str:
    payload = dict(quality_context)
    payload["develop_quality_result"] = quality_result
    writer = ReplayWriter(config)
    event = build_develop_quality_replay_event(
        ts=iso_now(),
        payload=payload,
        language=config.language,
    )
    run_state = run_state or context.current_run
    session_dir = writer.append_event(run_state.run_id, event)
    writer.render_documents(
        run_state.run_id,
        run_state=run_state,
        route=RouteDecision(
            route_name="resume_active",
            request_text=quality_context["working_summary"],
            reason="Develop quality result recorded",
            complexity="medium",
            candidate_skill_ids=("develop",),
            should_recover_context=True,
            should_create_plan=False,
        ),
        plan_artifact=context.current_plan,
        events=writer.load_events(run_state.run_id),
    )
    return str(session_dir.relative_to(config.workspace_root))


def _develop_callback_run_state(
    *,
    context: ActiveDevelopContext,
    request: CheckpointRequest,
    materialized: CheckpointMaterialization,
) -> RunState:
    stage = "decision_pending" if request.checkpoint_kind == "decision" else "clarification_pending"
    title = context.current_plan.title
    if materialized.decision_state is not None:
        title = materialized.decision_state.question or title
    elif materialized.clarification_state is not None:
        title = materialized.clarification_state.summary or title
    return RunState(
        run_id=context.current_run.run_id,
        status="active",
        stage=stage,
        route_name=context.current_run.route_name,
        title=title,
        created_at=context.current_run.created_at,
        updated_at=iso_now(),
        plan_id=context.current_plan.plan_id,
        plan_path=context.current_plan.path,
        execution_gate=context.current_run.execution_gate,
        request_excerpt=context.current_run.request_excerpt,
        request_sha1=context.current_run.request_sha1,
        owner_session_id=context.current_run.owner_session_id,
        owner_host=context.current_run.owner_host,
        owner_run_id=context.current_run.owner_run_id,
        resolution_id=context.current_run.resolution_id,
    )


def _copy_run_state(current_run: RunState) -> RunState:
    """Keep coarse execution truth stable while refreshing the updated timestamp."""
    return RunState(
        run_id=current_run.run_id,
        status=current_run.status,
        stage=current_run.stage,
        route_name=current_run.route_name,
        title=current_run.title,
        created_at=current_run.created_at,
        updated_at=iso_now(),
        plan_id=current_run.plan_id,
        plan_path=current_run.plan_path,
        execution_gate=current_run.execution_gate,
        request_excerpt=current_run.request_excerpt,
        request_sha1=current_run.request_sha1,
        owner_session_id=current_run.owner_session_id,
        owner_host=current_run.owner_host,
        owner_run_id=current_run.owner_run_id,
        resolution_id=current_run.resolution_id,
    )
def _default_checkpoint_id(*, checkpoint_kind: str, run_id: str, seed_text: str) -> str:
    digest = sha1(f"{run_id}:{checkpoint_kind}:{seed_text}".encode("utf-8")).hexdigest()[:10]
    return f"develop_{checkpoint_kind}_{digest}"


def _normalize_string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())
