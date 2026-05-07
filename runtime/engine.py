"""Top-level orchestration for Sopify runtime."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha1
from pathlib import Path
import re
from typing import Any, Mapping, Optional
from uuid import uuid4

from .checkpoint_materializer import materialize_checkpoint_request
from .checkpoint_request import checkpoint_request_from_clarification_state, checkpoint_request_from_decision_state
from .clarification import build_clarification_state, has_submitted_clarification, merge_clarification_request, parse_clarification_response, stale_clarification
from .config import load_runtime_config
from .context_snapshot import ContextResolvedSnapshot, resolve_context_snapshot
from .context_recovery import recover_context
from .decision import (
    ACTIVE_PLAN_ATTACH_OPTION_ID,
    ACTIVE_PLAN_BINDING_DECISION_TYPE,
    ACTIVE_PLAN_NEW_OPTION_ID,
    build_active_plan_binding_decision_state,
    build_decision_state,
    build_execution_gate_decision_state,
    confirm_decision,
    consume_decision,
    has_submitted_decision,
    parse_decision_response,
    response_from_submission,
    stale_decision,
)
from .develop_callback import develop_resume_after, is_develop_callback_state
from .execution_gate import evaluate_execution_gate
from .archive_lifecycle import (
    ARCHIVE_STATUS_ALREADY_ARCHIVED,
    ARCHIVE_STATUS_BLOCKED,
    archive_status_payload,
    apply_archive_subject,
    check_archive_subject,
    resolve_archive_subject,
)
from .handoff import build_runtime_handoff
from .kb import bootstrap_kb, ensure_blueprint_index, ensure_blueprint_scaffold
from .models import ClarificationState, DecisionState, ExecutionGate, KbArtifact, PlanArtifact, RecoveredContext, ReplayEvent, RouteDecision, RunState, RuntimeConfig, RuntimeHandoff, RuntimeResult, SkillActivation, SkillMeta
from .plan_registry import (
    PlanRegistryError,
    encode_priority_note_event,
    get_plan_entry,
    priority_note_for_plan,
    registry_relative_path,
)
from .plan_scaffold import (
    create_plan_scaffold,
    find_plan_by_request_reference,
    reserve_plan_identity,
    request_explicitly_wants_new_plan,
)
from .replay import ReplayWriter, build_decision_replay_event
from .router import Router, estimate_complexity, decide_capture_mode
from .skill_resolver import resolve_route_candidate_skills
from .action_intent import (
    ActionProposal,
    ActionValidator,
    ExecutionAuthorizationReceipt,
    ValidationContext,
    DECISION_AUTHORIZE,
    DECISION_REJECT,
    generate_proposal_id,
)
from .skill_registry import SkillRegistry
from .skill_runner import SkillExecutionError, run_runtime_skill
from .state import (
    StateStore,
    iso_now,
    local_day_now,
    local_display_now,
    local_iso_now,
    local_timezone_name,
    stable_request_sha1,
    summarize_request_text,
)
from .state_invariants import stamp_handoff_resolution_id

_CURRENT_PLAN_ANCHOR_PATTERNS = (
    re.compile(r"(当前|这个|该)\s*(plan|方案)", re.IGNORECASE),
    re.compile(r"(current|active)\s+plan", re.IGNORECASE),
    re.compile(r"(继续|回到|基于|沿用|挂到|并入|写进|写入).*(plan|方案)", re.IGNORECASE),
)
_HOST_FACING_TRUTH_KIND_ENGINE_RUNTIME_HANDOFF = "engine_runtime_handoff"
_HOST_FACING_TRUTH_KIND_PROMOTION_GLOBAL_EXECUTION = "promotion_global_execution"
_ABORTABLE_CLARIFICATION_STATUSES = frozenset({"pending", "collecting"})
_ABORTABLE_DECISION_STATUSES = frozenset({"pending", "collecting", "cancelled", "timed_out"})

# Canonical route families (blueprint design.md §Route Families).
# Internal consumers should reference families, not enumerate individual route names.
_CANONICAL_ROUTE_FAMILIES: dict[str, str] = {
    "plan_only": "plan", "workflow": "plan", "light_iterate": "plan",
    "quick_fix": "develop", "resume_active": "develop", "exec_plan": "develop",
    "consult": "consult", "replay": "consult",
    "archive_lifecycle": "archive",
    "clarification_pending": "clarification", "clarification_resume": "clarification",
    "decision_pending": "decision", "decision_resume": "decision",
}
_NON_FAMILY_SURFACES = frozenset({"state_conflict", "cancel_active", "summary", "proposal_rejected"})

_ABORTABLE_HANDOFF_ACTIONS = frozenset(
    {
        "answer_questions",
        "confirm_decision",
        "resolve_state_conflict",
    }
)
_ABORTABLE_RUN_STAGES = frozenset(
    {
        "clarification_pending",
        "decision_pending",
    }
)
# These routes operate on the single root-scoped execution truth once review
# state is explicitly promoted out of a session.
_GLOBAL_EXECUTION_ROUTES = frozenset({"resume_active", "exec_plan", "archive_lifecycle"})
# Only stable review checkpoints may be promoted into the global execution
# truth consumed by resume and archive lifecycle.
_PROMOTABLE_REVIEW_STAGES = frozenset({"plan_generated", "ready_for_execution", "develop_pending"})

# -- Phase B: action_type → route mapping for authorized proposals -----------

_ACTION_TYPE_TO_ROUTE: dict[str, str] = {
    "consult_readonly": "consult",
    "propose_plan": "plan_only",
    "execute_existing_plan": "resume_active",
    # cancel_flow handled inline (needs snapshot for cancel_scope).
}


def _derive_route_from_authorized_proposal(
    proposal: ActionProposal,
    user_input: str,
    *,
    skills: tuple[SkillMeta, ...],
    config: RuntimeConfig,
    snapshot: ContextResolvedSnapshot | None,
) -> RouteDecision:
    """Deterministically map an authorized ActionProposal to a RouteDecision.

    Called only when ``validation_decision.decision == DECISION_AUTHORIZE``
    and there is no ``route_override``.  Falls through to Router.classify()
    is NOT expected — every recognized action_type produces a route here.
    """
    action = proposal.action_type

    # --- cancel_flow: snapshot-driven cancel_scope ---
    if action == "cancel_flow":
        has_global = _snapshot_global_execution_run(snapshot) is not None
        route = RouteDecision(
            route_name="cancel_active",
            request_text=user_input,
            reason="action_proposal_derive: cancel_flow",
            complexity="simple",
            should_recover_context=True,
            active_run_action="cancel",
            artifacts={"cancel_scope": "global" if has_global else "session"},
        )
    # --- checkpoint_response: snapshot-driven ---
    elif action == "checkpoint_response":
        route = _derive_checkpoint_response_route(user_input, snapshot=snapshot, skills=skills)
    # --- modify_files: complexity-driven ---
    elif action == "modify_files":
        route = _derive_modify_files_route(user_input, skills=skills)
    # --- propose_plan: complexity for plan_level, immediate materialization ---
    elif action == "propose_plan":
        signal = estimate_complexity(user_input)
        route = RouteDecision(
            route_name="plan_only",
            request_text=user_input,
            reason=f"action_proposal_derive: propose_plan ({signal.reason})",
            complexity="complex",
            plan_level=signal.plan_level or "standard",
            plan_package_policy="immediate",
            candidate_skill_ids=resolve_route_candidate_skills(
                "plan_only", skills, fallback_preferred=("analyze", "design"),
            ),
        )
    else:
        # --- static mappings ---
        route_name = _ACTION_TYPE_TO_ROUTE.get(action)
        if route_name is not None:
            route = _build_static_route(route_name, action, user_input, skills=skills)
        else:
            # Unreachable for valid ACTION_TYPES (archive_plan handled by route_override).
            route = RouteDecision(
                route_name="consult",
                request_text=user_input,
                reason=f"action_proposal_derive: unknown action_type {action!r}, falling back to consult",
                complexity="simple",
            )

    # Apply capture_mode normalization — shared with Router.classify _with_capture.
    capture = decide_capture_mode(config.workflow_learning_auto_capture, route.complexity)
    if capture != route.capture_mode:
        route = RouteDecision(
            route_name=route.route_name,
            request_text=route.request_text,
            reason=route.reason,
            command=route.command,
            complexity=route.complexity,
            plan_level=route.plan_level,
            candidate_skill_ids=route.candidate_skill_ids,
            should_recover_context=route.should_recover_context,
            plan_package_policy=route.plan_package_policy,
            should_create_plan=route.should_create_plan,
            capture_mode=capture,
            runtime_skill_id=route.runtime_skill_id,
            active_run_action=route.active_run_action,
            artifacts=route.artifacts,
        )
    return route


def _derive_checkpoint_response_route(
    user_input: str,
    *,
    snapshot: ContextResolvedSnapshot | None,
    skills: tuple[SkillMeta, ...],
) -> RouteDecision:
    """Route checkpoint_response based on active checkpoint state in snapshot."""
    if snapshot is not None:
        clarification = snapshot.current_clarification
        if clarification is not None and clarification.status == "pending":
            return RouteDecision(
                route_name="clarification_resume",
                request_text=user_input,
                reason="action_proposal_derive: checkpoint_response with pending clarification",
                complexity="medium",
                should_recover_context=True,
                candidate_skill_ids=resolve_route_candidate_skills(
                    "clarification_resume", skills, fallback_preferred=("analyze", "design"),
                ),
                active_run_action="clarification_response",
            )
        decision = snapshot.current_decision
        if decision is not None and decision.status in {"pending", "collecting"}:
            return RouteDecision(
                route_name="decision_resume",
                request_text=user_input,
                reason="action_proposal_derive: checkpoint_response with active decision",
                complexity="medium",
                should_recover_context=True,
                candidate_skill_ids=resolve_route_candidate_skills(
                    "decision_resume", skills, fallback_preferred=("design",),
                ),
                active_run_action="decision_response",
            )
    # No active checkpoint → REJECT (fail-closed)
    return RouteDecision(
        route_name="proposal_rejected",
        request_text=user_input,
        reason="action_proposal_derive: checkpoint_response but no active pending/collecting checkpoint",
        complexity="simple",
        should_recover_context=False,
        artifacts={"reject_reason_code": "checkpoint_response.no_active_checkpoint"},
    )


def _derive_modify_files_route(
    user_input: str,
    *,
    skills: tuple[SkillMeta, ...],
) -> RouteDecision:
    """Route modify_files based on text complexity analysis."""
    signal = estimate_complexity(user_input)
    if signal.level == "simple":
        return RouteDecision(
            route_name="quick_fix",
            request_text=user_input,
            reason=f"action_proposal_derive: modify_files ({signal.reason})",
            complexity=signal.level,
            candidate_skill_ids=resolve_route_candidate_skills(
                "quick_fix", skills, fallback_preferred=("develop",),
            ),
        )
    if signal.level == "medium":
        return RouteDecision(
            route_name="light_iterate",
            request_text=user_input,
            reason=f"action_proposal_derive: modify_files ({signal.reason})",
            complexity=signal.level,
            plan_level=signal.plan_level,
            plan_package_policy="authorized_only",
            candidate_skill_ids=resolve_route_candidate_skills(
                "light_iterate", skills, fallback_preferred=("design", "develop"),
            ),
        )
    return RouteDecision(
        route_name="workflow",
        request_text=user_input,
        reason=f"action_proposal_derive: modify_files ({signal.reason})",
        complexity=signal.level,
        plan_level=signal.plan_level,
        plan_package_policy="authorized_only",
        candidate_skill_ids=resolve_route_candidate_skills(
            "workflow", skills, fallback_preferred=("analyze", "design", "develop"),
        ),
    )


def _build_static_route(
    route_name: str,
    action_type: str,
    user_input: str,
    *,
    skills: tuple[SkillMeta, ...],
) -> RouteDecision:
    """Build a RouteDecision for action types with a fixed route mapping."""
    if route_name in {"cancel_active", "resume_active"}:
        return RouteDecision(
            route_name=route_name,
            request_text=user_input,
            reason=f"action_proposal_derive: {action_type}",
            complexity="simple" if route_name == "cancel_active" else "medium",
            should_recover_context=True,
            active_run_action="cancel" if route_name == "cancel_active" else "resume",
            candidate_skill_ids=resolve_route_candidate_skills(
                route_name, skills, fallback_preferred=("develop",),
            ) if route_name == "resume_active" else (),
        )
    # consult_readonly
    return RouteDecision(
        route_name="consult",
        request_text=user_input,
        reason=f"action_proposal_derive: {action_type}",
        complexity="simple",
    )


@dataclass(frozen=True)
class _PlanSelection:
    """Describe whether planning should reuse an existing plan or create a new one."""

    action: str
    plan_artifact: PlanArtifact | None = None
    reason_note: str = ""


@dataclass(frozen=True)
class _PlanningContext:
    """Single captured planning truth used by deep planning helpers.

    Main runtime flow should pass this explicitly from recovered context so the
    helper chain does not re-open state files mid-decision. A capture helper
    remains only as a narrow compatibility bridge for direct helper tests and
    internal restart points that must intentionally refresh local state once.
    """

    current_run: RunState | None = None
    current_plan: PlanArtifact | None = None
    current_clarification: ClarificationState | None = None
    current_decision: DecisionState | None = None
    last_route: RouteDecision | None = None


def _capture_planning_context(state_store: StateStore) -> _PlanningContext:
    return _PlanningContext(
        current_run=state_store.get_current_run(),
        current_plan=state_store.get_current_plan(),
        current_clarification=state_store.get_current_clarification(),
        current_decision=state_store.get_current_decision(),
        last_route=state_store.get_last_route(),
    )




def _snapshot_has_global_execution_truth(snapshot: ContextResolvedSnapshot | None) -> bool:
    if snapshot is None:
        return False
    return snapshot.preferred_state_scope == "global" and snapshot.execution_active_run is not None


def _snapshot_global_execution_run(snapshot: ContextResolvedSnapshot | None) -> RunState | None:
    if not _snapshot_has_global_execution_truth(snapshot):
        return None
    return snapshot.execution_active_run


def _snapshot_review_run(snapshot: ContextResolvedSnapshot | None) -> RunState | None:
    if snapshot is None or snapshot.current_run is None:
        return None
    global_run = _snapshot_global_execution_run(snapshot)
    if global_run is not None and snapshot.current_run == global_run:
        return None
    return snapshot.current_run


def _recovery_store_for_route(
    decision: RouteDecision,
    *,
    review_store: StateStore,
    global_store: StateStore,
    snapshot: ContextResolvedSnapshot | None = None,
) -> StateStore:
    if decision.route_name == "state_conflict" and snapshot is not None and snapshot.preferred_state_scope == "global":
        return global_store
    if decision.route_name in _GLOBAL_EXECUTION_ROUTES and _snapshot_has_global_execution_truth(snapshot):
        return global_store
    return review_store


def _handle_cancel_active(
    decision: RouteDecision,
    *,
    review_store: StateStore,
    global_store: StateStore,
    review_run: RunState | None,
    global_run: RunState | None,
) -> tuple[StateStore, bool, list[str]]:
    cancel_scope = str(decision.artifacts.get("cancel_scope") or "").strip()
    if cancel_scope != "session" and global_run is not None:
        global_store.reset_active_flow()
        if review_store is global_store or review_run is None:
            return (global_store, False, ["Global execution flow cleared"])
        return (global_store, True, ["Global execution flow cleared; session review state preserved"])
    review_store.reset_active_flow()
    return (review_store, False, ["Session review flow cleared"])


def _handle_state_conflict(
    decision: RouteDecision,
    *,
    review_store: StateStore,
    global_store: StateStore,
    snapshot: ContextResolvedSnapshot,
) -> tuple[StateStore, ContextResolvedSnapshot, list[str]]:
    # `state_conflict` only models user-recoverable resolved-state skew.
    # Writer-side contract breaks must keep surfacing as invariant errors
    # instead of being silently downcast into this cleanup path.
    target_store = global_store if snapshot.preferred_state_scope == "global" else review_store
    if decision.active_run_action != "abort_conflict":
        return (target_store, snapshot, list(snapshot.notes))

    notes = ["Conflict cleanup started via explicit abort"]
    processed_roots: set[str] = set()
    for store in (review_store, global_store):
        root_key = str(store.root)
        if root_key in processed_roots:
            continue
        processed_roots.add(root_key)
        notes.extend(_clear_conflict_carriers(store, snapshot=snapshot))
        notes.extend(_clear_abortable_negotiation_state(store))

    next_snapshot = resolve_context_snapshot(
        config=review_store.config,
        review_store=review_store,
        global_store=global_store,
    )
    notes.append("Conflict cleanup completed")
    if next_snapshot.is_conflict:
        notes.append("Conflict cleanup left a remaining conflict that still requires inspection")
    return (
        global_store if next_snapshot.preferred_state_scope == "global" else review_store,
        next_snapshot,
        notes,
    )


def _clear_abortable_negotiation_state(store: StateStore) -> list[str]:
    notes: list[str] = []
    clarification = store.get_current_clarification()
    if _is_abortable_clarification(clarification):
        store.clear_current_clarification()
        notes.append(f"Cleared pending clarification from {store.scope} scope")
    decision = store.get_current_decision()
    if _is_abortable_decision(decision):
        store.clear_current_decision()
        notes.append(f"Cleared unconsumed decision from {store.scope} scope")
    elif decision is not None and decision.status == "confirmed" and decision.selection is not None:
        # A confirmed decision can be the last valid user-owned checkpoint after
        # a crash or session restart. Abort should abandon the live negotiation
        # state around it, but not erase the confirmed choice itself.
        notes.append(f"Preserved confirmed decision in {store.scope} scope")
    handoff = store.get_current_handoff()
    if handoff is not None and handoff.required_host_action in _ABORTABLE_HANDOFF_ACTIONS:
        store.clear_current_handoff()
        notes.append(f"Cleared checkpoint handoff from {store.scope} scope")
    current_run = store.get_current_run()
    current_plan = store.get_current_plan()
    if current_run is not None and current_run.stage in _ABORTABLE_RUN_STAGES:
        if current_plan is None:
            store.clear_current_run()
            notes.append(f"Cleared orphaned negotiation run from {store.scope} scope")
        else:
            store.set_current_run(_normalize_run_after_abort(current_run))
            notes.append(f"Normalized run stage back to stable planning truth in {store.scope} scope")
    return notes


def _clear_conflict_carriers(store: StateStore, *, snapshot: ContextResolvedSnapshot) -> list[str]:
    notes: list[str] = []
    conflict_paths = {
        detail.path
        for detail in snapshot.conflict_items
        if detail.state_scope == store.scope and detail.path
    }
    handoff_path = store.relative_path(store.current_handoff_path)
    if handoff_path in conflict_paths and store.get_current_handoff() is not None:
        # The handoff is a derived carrier for route/run truth. When the
        # snapshot proves it is the conflicted file, we clear only that carrier
        # so the next pass can rebuild a fresh pair without wiping plan/run.
        store.clear_current_handoff()
        notes.append(f"Tombstoned conflicting handoff carrier from {store.scope} scope")
    return notes


def _is_abortable_clarification(clarification: ClarificationState | None) -> bool:
    if clarification is None:
        return False
    return clarification.status in _ABORTABLE_CLARIFICATION_STATUSES


def _is_abortable_decision(decision: DecisionState | None) -> bool:
    if decision is None:
        return False
    return decision.status in _ABORTABLE_DECISION_STATUSES


def _normalize_run_after_abort(current_run: RunState) -> RunState:
    gate = current_run.execution_gate
    stable_stage = "ready_for_execution" if gate is not None and gate.gate_status == "ready" else "plan_generated"
    return RunState(
        run_id=current_run.run_id,
        status=current_run.status,
        stage=stable_stage,
        route_name=current_run.route_name,
        title=current_run.title,
        created_at=current_run.created_at,
        updated_at=iso_now(),
        plan_id=current_run.plan_id,
        plan_path=current_run.plan_path,
        execution_gate=current_run.execution_gate,
        execution_authorization_receipt=current_run.execution_authorization_receipt,
        request_excerpt=current_run.request_excerpt,
        request_sha1=current_run.request_sha1,
        owner_session_id=current_run.owner_session_id,
        owner_host=current_run.owner_host,
        owner_run_id=current_run.owner_run_id,
        resolution_id=current_run.resolution_id,
    )


def _is_zero_write_conflict_inspect(route: RouteDecision) -> bool:
    # Conflict inspection is intentionally observational. Keep it out of
    # last_route.json as well so "inspect" does not mutate any state file.
    return route.route_name == "state_conflict" and route.active_run_action != "abort_conflict"


def _resolve_execution_state_store(
    decision: RouteDecision,
    *,
    config: RuntimeConfig,
    review_store: StateStore,
    global_store: StateStore,
    recovered_context: RecoveredContext,
    session_id: str | None,
) -> tuple[StateStore, Any, list[str]]:
    global_execution_context = recover_context(
        decision,
        config=config,
        state_store=global_store,
        global_state_store=global_store,
    )
    if global_execution_context.current_run is not None and global_execution_context.current_plan is not None:
        # Re-resolve against the global store alone so execution routes only see
        # the single global execution truth instead of the mixed review/global
        # composite snapshot used at the router boundary.
        return (global_store, global_execution_context, [])

    promoted, promotion_notes = _promote_review_state_to_global_execution(
        review_store=review_store,
        global_store=global_store,
        review_plan=recovered_context.current_plan,
        review_run=recovered_context.current_run,
        review_handoff=recovered_context.current_handoff,
        existing_global_run=global_execution_context.current_run,
        session_id=session_id,
        resolution_id=recovered_context.resolution_id,
    )
    recovery_store = global_store if promoted else review_store
    recovered = recover_context(
        decision,
        config=config,
        state_store=recovery_store,
        global_state_store=global_store,
    )
    return (recovery_store, recovered, promotion_notes)


def _promote_review_state_to_global_execution(
    *,
    review_store: StateStore,
    global_store: StateStore,
    review_plan: PlanArtifact | None,
    review_run: RunState | None,
    review_handoff: RuntimeHandoff | None,
    existing_global_run: RunState | None,
    session_id: str | None,
    resolution_id: str,
) -> tuple[bool, list[str]]:
    if review_store is global_store:
        return (False, [])
    if review_plan is None or review_run is None:
        return (False, [])
    if review_run.stage not in _PROMOTABLE_REVIEW_STAGES:
        return (False, [])

    notes: list[str] = []
    owner_warning = _soft_execution_ownership_warning(existing_global_run=existing_global_run, session_id=session_id)
    if owner_warning is not None:
        notes.append(owner_warning)

    # Promotion is the explicit handoff point from session review state into the
    # single global execution truth used by execution-confirm / resume / archive lifecycle.
    global_store.set_current_plan(review_plan)
    global_run = _with_global_run_ownership(review_run, session_id=session_id)
    if review_handoff is not None:
        global_run, _ = global_store.set_host_facing_truth(
            run_state=global_run,
            handoff=_with_global_handoff_ownership(
                review_handoff,
                current_run=global_run,
                session_id=session_id,
            ),
            resolution_id=_derived_resolution_id(
                resolved_resolution_id=resolution_id,
                current_run=global_run,
                current_handoff=review_handoff,
            ),
            truth_kind=_HOST_FACING_TRUTH_KIND_PROMOTION_GLOBAL_EXECUTION,
        )
    else:
        global_store.set_current_run(global_run)
    notes.append(f"Promoted session review state to global execution truth from {review_store.root.name}")
    return (True, notes)


def _soft_execution_ownership_warning(
    *,
    existing_global_run: RunState | None,
    session_id: str | None,
) -> str | None:
    if (
        existing_global_run is not None
        and existing_global_run.owner_session_id
        and session_id
        and existing_global_run.owner_session_id != session_id
    ):
        return (
            f"Soft ownership warning: overwriting global execution context "
            f"owned by session {existing_global_run.owner_session_id}"
        )
    return None


def _set_execution_run_state(
    state_store: StateStore,
    run_state: RunState,
    *,
    session_id: str | None,
) -> None:
    if state_store.session_id is not None:
        state_store.set_current_run(run_state)
        return
    state_store.set_current_run(_with_global_run_ownership(run_state, session_id=session_id))


def _persist_execution_gate_checkpoint(
    *,
    state_store: StateStore,
    config: RuntimeConfig,
    current_plan: PlanArtifact,
    next_run_state: RunState,
    gate_decision: DecisionState,
) -> tuple[StateStore, list[str]]:
    # Execution-gate checkpoints are part of the single execution truth used by
    # confirm/resume flows. When planning runs inside a session review scope, we
    # still persist the gate checkpoint globally so later recovery does not see
    # a session-scoped execution decision that fails provenance loading.
    notes: list[str] = []
    execution_store = state_store
    if state_store.session_id is not None:
        execution_store = StateStore(config)
        execution_store.ensure()
        owner_warning = _soft_execution_ownership_warning(
            existing_global_run=execution_store.get_current_run(),
            session_id=state_store.session_id,
        )
        if owner_warning is not None:
            notes.append(owner_warning)
        execution_store.set_current_plan(current_plan)
    _set_execution_run_state(
        execution_store,
        next_run_state,
        session_id=state_store.session_id,
    )
    execution_store.set_current_decision(gate_decision)
    if execution_store is not state_store:
        # Once execution truth is promoted globally, the review-scoped run and
        # handoff are stale carriers. Keeping them would let snapshot recovery
        # pick a checkpoint from the session side while a global checkpoint
        # already exists, which could fail-close into a state conflict.
        state_store.clear_current_run()
        state_store.clear_current_handoff()
    return (execution_store, notes)


def _with_global_run_ownership(run_state: RunState, *, session_id: str | None) -> RunState:
    owner_session_id = str(session_id or run_state.owner_session_id or "").strip()
    return RunState(
        run_id=run_state.run_id,
        status=run_state.status,
        stage=run_state.stage,
        route_name=run_state.route_name,
        title=run_state.title,
        created_at=run_state.created_at,
        updated_at=run_state.updated_at,
        plan_id=run_state.plan_id,
        plan_path=run_state.plan_path,
        execution_gate=run_state.execution_gate,
        execution_authorization_receipt=run_state.execution_authorization_receipt,
        request_excerpt=run_state.request_excerpt,
        request_sha1=run_state.request_sha1,
        owner_session_id=owner_session_id,
        owner_host=run_state.owner_host or "runtime",
        owner_run_id=run_state.owner_run_id or run_state.run_id,
        resolution_id=run_state.resolution_id,
    )


def _with_global_handoff_ownership(
    handoff: RuntimeHandoff,
    *,
    current_run: RunState | None,
    session_id: str | None,
) -> RuntimeHandoff:
    observability = dict(handoff.observability)
    owner_session_id = ""
    if current_run is not None:
        owner_session_id = current_run.owner_session_id
    if not owner_session_id:
        owner_session_id = str(session_id or "").strip()
    if owner_session_id:
        observability["owner_session_id"] = owner_session_id
    if current_run is not None:
        if current_run.owner_host:
            observability["owner_host"] = current_run.owner_host
        if current_run.owner_run_id:
            observability["owner_run_id"] = current_run.owner_run_id
    return RuntimeHandoff(
        schema_version=handoff.schema_version,
        route_name=handoff.route_name,
        run_id=handoff.run_id,
        plan_id=handoff.plan_id,
        plan_path=handoff.plan_path,
        handoff_kind=handoff.handoff_kind,
        required_host_action=handoff.required_host_action,
        recommended_skill_ids=handoff.recommended_skill_ids,
        artifacts=handoff.artifacts,
        notes=handoff.notes,
        observability=observability,
        resolution_id=handoff.resolution_id,
    )


def _result_state_store_for_route(
    decision: RouteDecision,
    *,
    review_store: StateStore,
    global_store: StateStore,
    canceled_store: StateStore | None,
    preserved_review_after_cancel: bool = False,
    current_clarification: ClarificationState | None = None,
    current_decision: DecisionState | None = None,
    snapshot: ContextResolvedSnapshot | None = None,
) -> StateStore:
    if canceled_store is not None:
        if canceled_store is global_store and preserved_review_after_cancel:
            return review_store
        return canceled_store
    if decision.route_name == "state_conflict" and snapshot is not None and snapshot.preferred_state_scope == "global":
        return global_store
    if decision.route_name in _GLOBAL_EXECUTION_ROUTES:
        return global_store
    if decision.route_name in {"decision_pending", "decision_resume"}:
        if current_decision is not None and current_decision.phase in {"execution_gate", "develop"}:
            return global_store
        return review_store
    if decision.route_name in {"clarification_pending", "clarification_resume"}:
        if current_clarification is not None and current_clarification.phase == "develop":
            return global_store
        return review_store
    return review_store


def run_runtime(
    user_input: str,
    *,
    workspace_root: str | Path = ".",
    global_config_path: str | Path | None = None,
    session_id: str | None = None,
    user_home: Path | None = None,
    runtime_payloads: Optional[Mapping[str, Mapping[str, Any]]] = None,
    action_proposal: ActionProposal | None = None,
) -> RuntimeResult:
    """Run the Sopify runtime pipeline for a single input.

    Args:
        user_input: Raw user input.
        workspace_root: Project root.
        global_config_path: Optional global config override.
        user_home: Optional home override for tests.
        runtime_payloads: Optional runtime-skill payload map keyed by skill id.
        action_proposal: Optional ActionProposal from the host LLM. When
            provided the pre-route validator may override or constrain
            the route before the Router runs.

    Returns:
        Standardized runtime result.
    """
    config = load_runtime_config(workspace_root, global_config_path=global_config_path)
    review_store = StateStore(config, session_id=session_id)
    global_store = StateStore(config)
    review_store.ensure()
    global_store.ensure()
    kb_artifact: KbArtifact | None = bootstrap_kb(config)

    skills = SkillRegistry(config, user_home=user_home).discover()
    router = Router(config, state_store=review_store, global_state_store=global_store)
    snapshot = resolve_context_snapshot(
        config=config,
        review_store=review_store,
        global_store=global_store,
    )

    # --- P0: ActionProposal pre-route interceptor ---
    # When the host provides a validated ActionProposal, run it through the
    # ActionValidator *before* the Router.  If the validator returns an
    # authoritative route_override (e.g. "consult"), construct a synthetic
    # RouteDecision and skip Router classification entirely.
    proposal_override_route: RouteDecision | None = None
    plan_materialization_authorized = False
    execution_auth_receipt: ExecutionAuthorizationReceipt | None = None
    _receipt_ingredients: dict[str, str] | None = None
    if action_proposal is not None:
        validator = ActionValidator()
        _run = snapshot.current_run
        _handoff = snapshot.current_handoff
        active_plan_for_validator = snapshot.execution_current_plan or snapshot.current_plan
        required_host_action = getattr(_handoff, "required_host_action", "") or "" if _handoff else ""
        if not required_host_action:
            required_host_action = _pending_required_host_action(snapshot)
        ctx = ValidationContext(
            stage=getattr(_run, "stage", "") or "" if _run else "",
            required_host_action=required_host_action,
            current_plan_path=getattr(active_plan_for_validator, "path", "") or "" if active_plan_for_validator else "",
            state_conflict=snapshot.is_conflict,
            workspace_root=str(config.workspace_root) if config is not None else None,
            existing_receipt=getattr(_run, "execution_authorization_receipt", None) if _run else None,
            current_gate_status=getattr(getattr(_run, "execution_gate", None), "gate_status", None) if _run else None,
        )
        validation_decision = validator.validate(action_proposal, ctx)
        if validation_decision.decision == DECISION_REJECT:
            # P1.5-A: validator explicitly rejected — independent reject surface.
            # No state mutation on reject: stale receipt stays until an explicit
            # re-authorization path (e.g. new planning flow) replaces it.
            proposal_override_route = RouteDecision(
                route_name="proposal_rejected",
                request_text=user_input,
                reason=f"action_proposal_rejected: {validation_decision.reason_code}",
                complexity="simple",
                should_recover_context=False,
                artifacts={"reject_reason_code": validation_decision.reason_code},
            )
        elif validation_decision.route_override:
            proposal_override_route = RouteDecision(
                route_name=validation_decision.route_override,
                request_text=user_input,
                reason=f"action_proposal_validator: {validation_decision.reason_code}",
                complexity="simple",
                should_recover_context=validation_decision.route_override == "archive_lifecycle",
                candidate_skill_ids=("develop", "kb") if validation_decision.route_override == "archive_lifecycle" else (),
                active_run_action="archive" if validation_decision.route_override == "archive_lifecycle" else None,
                artifacts=validation_decision.artifacts,
            )
        # P1.5: derive plan materialization authorization from Validator result.
        if (
            validation_decision.decision == DECISION_AUTHORIZE
            and action_proposal.side_effect == "write_plan_package"
        ):
            plan_materialization_authorized = True
        # P1.5-B: capture receipt ingredients for execute_existing_plan.
        # Actual receipt creation is deferred to after evaluate_execution_gate()
        # so that gate_status reflects the final truth of THIS turn.
        if (
            validation_decision.decision == DECISION_AUTHORIZE
            and action_proposal.action_type == "execute_existing_plan"
            and action_proposal.plan_subject is not None
        ):
            _plan_subject = action_proposal.plan_subject
            _proposal_id = generate_proposal_id(
                action_type=action_proposal.action_type,
                side_effect=action_proposal.side_effect,
                subject_ref=_plan_subject.subject_ref,
                revision_digest=_plan_subject.revision_digest,
                request_hash=stable_request_sha1(user_input),
            )
            _receipt_ingredients = {
                "plan_path": _plan_subject.subject_ref,
                "revision_digest": _plan_subject.revision_digest,
                "proposal_id": _proposal_id,
                "request_sha1": stable_request_sha1(user_input),
            }

    if proposal_override_route is not None:
        classified_route = proposal_override_route
    elif action_proposal is not None and validation_decision.decision == DECISION_AUTHORIZE:
        classified_route = _derive_route_from_authorized_proposal(
            action_proposal, user_input, skills=skills, config=config, snapshot=snapshot,
        )
    else:
        # Legacy text-classification path: used when no ActionProposal is
        # provided (bare text requests).  Will be removed when all hosts
        # emit ActionProposal.
        classified_route = router.classify(user_input, skills=skills, snapshot=snapshot)
    recovered = recover_context(
        classified_route,
        config=config,
        state_store=_recovery_store_for_route(
            classified_route,
            review_store=review_store,
            global_store=global_store,
            snapshot=snapshot,
        ),
        global_state_store=global_store,
        snapshot=snapshot,
    )

    notes: list[str] = list(snapshot.notes)
    plan_artifact: PlanArtifact | None = None
    skill_result: Mapping[str, Any] | None = None
    replay_session_dir: str | None = None
    handoff: RuntimeHandoff | None = None
    activation: SkillActivation | None = None
    generated_files: tuple[str, ...] = ()
    replay_events: list[ReplayEvent] = []
    effective_route = classified_route
    confirmed_decision_for_replay: DecisionState | None = None
    registry_changed_hint = False

    current_clarification = recovered.current_clarification
    if (
        current_clarification is not None
        and effective_route.route_name in {"plan_only", "workflow", "light_iterate"}
        and effective_route.route_name not in {"clarification_pending", "clarification_resume"}
    ):
        # A new planning request supersedes the previous pending clarification.
        stale_state = stale_clarification(current_clarification)
        review_store.set_current_clarification(stale_state)
        review_store.clear_current_clarification()
        notes.append(f"Superseded pending clarification: {stale_state.clarification_id}")
        current_clarification = None

    current_decision = recovered.current_decision
    if (
        current_decision is not None
        and effective_route.route_name in {"plan_only", "workflow", "light_iterate"}
        and effective_route.route_name not in {"decision_pending", "decision_resume"}
    ):
        # A new planning request supersedes the previous pending checkpoint.
        stale_state = stale_decision(current_decision)
        review_store.set_current_decision(stale_state)
        review_store.clear_current_decision()
        notes.append(f"Superseded pending decision checkpoint: {stale_state.decision_id}")
        current_decision = None

    canceled_store: StateStore | None = None
    preserved_review_after_cancel = False
    if effective_route.route_name == "cancel_active":
        canceled_store, preserved_review_after_cancel, cancel_notes = _handle_cancel_active(
            effective_route,
            review_store=review_store,
            global_store=global_store,
            review_run=_snapshot_review_run(snapshot),
            global_run=_snapshot_global_execution_run(snapshot),
        )
        notes.extend(cancel_notes)
    elif effective_route.route_name == "archive_lifecycle":
        archive_state_store = _archive_state_store_for_current_plan(
            current_plan=recovered.current_plan,
            review_store=review_store,
            global_store=global_store,
        )
        archive_subject = resolve_archive_subject(
            effective_route.artifacts.get("archive_subject"),
            config=config,
            state_store=archive_state_store,
            current_plan=recovered.current_plan,
        )
        archive_check = check_archive_subject(archive_subject, config=config)
        archive_payload: Mapping[str, Any]
        if archive_check.status == "ready":
            archive_result = apply_archive_subject(archive_subject, config=config, state_store=archive_state_store)
            plan_artifact = archive_result.archived_plan
            registry_changed_hint = archive_result.registry_updated
            if archive_result.kb_artifact is not None:
                kb_artifact = archive_result.kb_artifact
            notes.extend(archive_result.notes)
            archive_payload = archive_status_payload(
                status=archive_result.status,
                subject=archive_subject,
                notes=archive_result.notes,
                state_cleared=archive_result.state_cleared,
            )
        elif archive_check.status == "migration_required":
            notes.extend(archive_check.notes)
            archive_payload = archive_status_payload(
                status=archive_check.status,
                subject=archive_subject,
                notes=archive_check.notes,
            )
        elif archive_check.status == "already_archived":
            notes.extend(archive_check.notes)
            plan_artifact = archive_subject.artifact
            archive_payload = archive_status_payload(
                status=ARCHIVE_STATUS_ALREADY_ARCHIVED,
                subject=archive_subject,
                notes=archive_check.notes,
            )
        else:
            notes.extend(archive_check.notes)
            archive_payload = archive_status_payload(
                status=archive_check.status or ARCHIVE_STATUS_BLOCKED,
                subject=archive_subject,
                notes=archive_check.notes,
            )
        effective_route = _with_route_artifacts(
            effective_route,
            {"archive_lifecycle": archive_payload},
        )
    elif effective_route.route_name == "clarification_resume":
        effective_route, plan_artifact, clarification_notes, kb_artifact = _handle_clarification_resume(
            effective_route,
            state_store=review_store,
            current_clarification=recovered.current_clarification,
            current_decision=recovered.current_decision,
            current_plan=recovered.current_plan,
            current_run=recovered.current_run,
            config=config,
            kb_artifact=kb_artifact,
        )
        notes.extend(clarification_notes)
    elif effective_route.route_name == "decision_resume":
        effective_route, plan_artifact, decision_notes, kb_artifact, confirmed_decision_for_replay = _handle_decision_resume(
            effective_route,
            state_store=review_store,
            current_decision=recovered.current_decision,
            current_plan=recovered.current_plan,
            current_run=recovered.current_run,
            config=config,
            kb_artifact=kb_artifact,
        )
        notes.extend(decision_notes)
    elif effective_route.route_name == "state_conflict":
        result_store, snapshot, conflict_notes = _handle_state_conflict(
            effective_route,
            review_store=review_store,
            global_store=global_store,
            snapshot=snapshot,
        )
        recovered = recover_context(
            effective_route,
            config=config,
            state_store=result_store,
            global_state_store=global_store,
            snapshot=snapshot,
        )
        notes.extend(conflict_notes)
    elif effective_route.route_name in {"plan_only", "workflow", "light_iterate"}:
        effective_route, plan_artifact, planning_notes, kb_artifact = _advance_planning_route(
            effective_route,
            state_store=review_store,
            config=config,
            kb_artifact=kb_artifact,
            planning_context=_PlanningContext(
                current_run=recovered.current_run,
                current_plan=recovered.current_plan,
                current_clarification=recovered.current_clarification,
                current_decision=recovered.current_decision,
                last_route=recovered.last_route,
            ),
            plan_materialization_authorized=plan_materialization_authorized,
        )
        notes.extend(planning_notes)
    elif effective_route.route_name in {"resume_active", "exec_plan"}:
        execution_store, execution_recovered, promotion_notes = _resolve_execution_state_store(
            effective_route,
            config=config,
            review_store=review_store,
            global_store=global_store,
            recovered_context=recovered,
            session_id=session_id,
        )
        notes.extend(promotion_notes)
        if execution_recovered.current_clarification is not None:
            effective_route = _clarification_pending_route(
                effective_route,
                reason="Pending clarification must be answered before execution can continue",
            )
            notes.append("Blocked execution because clarification is still pending")
        else:
            current_plan = execution_recovered.current_plan
            if current_plan is None:
                if effective_route.route_name == "exec_plan":
                    effective_route = _exec_plan_unavailable_route(
                        effective_route,
                        reason="Advanced exec recovery is unavailable because no active plan or confirmed recovery state exists",
                    )
                    notes.append("Rejected ~go exec because no active plan or confirmed recovery state is available")
                else:
                    notes.append("No active plan available to resume")
            else:
                gate = evaluate_execution_gate(
                    decision=effective_route,
                    plan_artifact=current_plan,
                    current_clarification=None,
                    current_decision=(
                        execution_recovered.current_decision
                        if execution_recovered.current_decision is not None
                        and execution_recovered.current_decision.status == "confirmed"
                        and execution_recovered.current_decision.selection is not None
                        else None
                    ),
                    config=config,
                )
                # P1.5-B: generate receipt AFTER gate eval so gate_status is final truth.
                if _receipt_ingredients is not None:
                    execution_auth_receipt = ExecutionAuthorizationReceipt.create(
                        plan_path=_receipt_ingredients["plan_path"],
                        plan_revision_digest=_receipt_ingredients["revision_digest"],
                        gate_status=gate.gate_status,
                        action_proposal_id=_receipt_ingredients["proposal_id"],
                        request_sha1=_receipt_ingredients["request_sha1"],
                    )
                # Resolve receipt dict: new receipt wins; otherwise carry forward.
                _prev_run = execution_recovered.current_run
                _receipt_dict = (
                    execution_auth_receipt.to_dict()
                    if execution_auth_receipt is not None
                    else (_prev_run.execution_authorization_receipt if _prev_run is not None else None)
                )
                if gate.gate_status == "decision_required" and gate.blocking_reason != "unresolved_decision":
                    current_run = execution_recovered.current_run
                    next_run_state = RunState(
                        run_id=current_run.run_id if current_run is not None else _make_run_id(effective_route.request_text),
                        status="active",
                        stage="decision_pending",
                        route_name=effective_route.route_name,
                        title=current_plan.title,
                        created_at=current_run.created_at if current_run is not None else current_plan.created_at,
                        updated_at=iso_now(),
                        plan_id=current_plan.plan_id,
                        plan_path=current_plan.path,
                        execution_gate=gate,
                        execution_authorization_receipt=_receipt_dict,
                        request_excerpt=summarize_request_text(effective_route.request_text),
                        request_sha1=stable_request_sha1(effective_route.request_text),
                    )
                    gate_decision = _build_route_native_gate_decision_state(
                        effective_route,
                        gate=gate,
                        current_plan=current_plan,
                        current_run=next_run_state,
                        config=config,
                    )
                    if gate_decision is not None:
                        _set_execution_run_state(
                            execution_store,
                            next_run_state,
                            session_id=session_id,
                        )
                        execution_store.set_current_decision(gate_decision)
                        effective_route = _decision_pending_route(
                            effective_route,
                            reason="Execution gate found a blocking risk that still requires confirmation",
                        )
                        notes.extend(gate.notes)
                        notes.append(f"Execution gate requested a new decision: {gate_decision.decision_id}")
                    else:
                        notes.append("Execution gate requires a decision before develop can continue")
                elif gate.gate_status != "ready":
                    _set_execution_run_state(
                        execution_store,
                        _make_run_state(
                            effective_route,
                            current_plan,
                            stage="plan_generated",
                            execution_gate=gate,
                            execution_authorization_receipt=_receipt_dict,
                        ),
                        session_id=session_id,
                    )
                    notes.extend(gate.notes)
                    notes.append("Blocked execution because the execution gate is not ready")
                else:
                    current_run = execution_recovered.current_run
                    _set_execution_run_state(
                        execution_store,
                        RunState(
                            run_id=current_run.run_id if current_run is not None else _make_run_id(effective_route.request_text),
                            status="active",
                            stage="develop_pending",
                            route_name=effective_route.route_name,
                            title=current_plan.title,
                            created_at=current_run.created_at if current_run is not None else current_plan.created_at,
                            updated_at=iso_now(),
                            plan_id=current_plan.plan_id,
                            plan_path=current_plan.path,
                            execution_gate=gate,
                            execution_authorization_receipt=_receipt_dict,
                            request_excerpt=current_run.request_excerpt if current_run is not None else summarize_request_text(effective_route.request_text),
                            request_sha1=current_run.request_sha1 if current_run is not None else stable_request_sha1(effective_route.request_text),
                        ),
                        session_id=session_id,
                    )
                    notes.extend(gate.notes)
                    notes.append("Active run resumed")
        recovered = execution_recovered

    if not _is_zero_write_conflict_inspect(effective_route):
        review_store.set_last_route(effective_route)

    # Resolve once after all route-side mutations, then let store selection,
    # handoff, replay, and output consume the same fresh post-route truth.
    result_snapshot = resolve_context_snapshot(
        config=config,
        review_store=review_store,
        global_store=global_store,
    )
    result_store = _result_state_store_for_route(
        effective_route,
        review_store=review_store,
        global_store=global_store,
        canceled_store=canceled_store,
        preserved_review_after_cancel=preserved_review_after_cancel,
        current_clarification=result_snapshot.current_clarification,
        current_decision=result_snapshot.current_decision,
        snapshot=result_snapshot,
    )
    resolved_result_context = recover_context(
        effective_route,
        config=config,
        state_store=result_store,
        global_state_store=global_store,
    )

    if effective_route.runtime_skill_id is not None:
        skill = _find_skill(skills, effective_route.runtime_skill_id)
        payload = dict((runtime_payloads or {}).get(effective_route.runtime_skill_id, {}))
        if skill is None:
            notes.append(f"Runtime skill not found: {effective_route.runtime_skill_id}")
        elif not payload:
            notes.append(f"Runtime payload missing for skill: {effective_route.runtime_skill_id}")
        else:
            try:
                skill_result = run_runtime_skill(skill, payload=payload)
            except SkillExecutionError as exc:
                notes.append(str(exc))

    activation = _build_skill_activation(
        decision=effective_route,
        run_state=resolved_result_context.current_run,
        current_clarification=resolved_result_context.current_clarification,
        current_decision=resolved_result_context.current_decision,
    )

    if effective_route.capture_mode != "off":
        writer = ReplayWriter(config)
        run_state = resolved_result_context.current_run
        run_id = run_state.run_id if run_state is not None else _make_run_id(effective_route.request_text)
        replay_event = ReplayEvent(
            ts=iso_now(),
            phase=_phase_for_route(effective_route),
            intent=effective_route.request_text or effective_route.route_name,
            action=f"route:{effective_route.route_name}",
            key_output=(plan_artifact.summary if plan_artifact is not None else effective_route.reason),
            decision_reason=effective_route.reason,
            result="success",
            artifacts=tuple(plan_artifact.files if plan_artifact is not None else ()),
            metadata={"activation": activation.to_dict()} if activation is not None else {},
        )
        replay_events.append(replay_event)
        current_decision = resolved_result_context.current_decision
        if current_decision is not None and effective_route.route_name == "decision_pending":
            replay_events.append(
                build_decision_replay_event(
                    current_decision,
                    language=config.language,
                    action="checkpoint_created",
                )
            )
        if confirmed_decision_for_replay is not None:
            replay_events.append(
                build_decision_replay_event(
                    confirmed_decision_for_replay,
                    language=config.language,
                    action="confirmed",
                )
            )
        session_dir = writer.append_event(run_id, replay_event)
        for extra_event in replay_events[1:]:
            writer.append_event(run_id, extra_event)
        writer.render_documents(
            run_id,
            run_state=resolved_result_context.current_run,
            route=effective_route,
            plan_artifact=plan_artifact or resolved_result_context.current_plan,
            events=replay_events,
        )
        replay_session_dir = str(session_dir.relative_to(config.workspace_root))

    if effective_route.route_name == "cancel_active":
        handoff = None
    else:
        current_run = resolved_result_context.current_run
        current_plan = plan_artifact or resolved_result_context.current_plan
        if effective_route.route_name == "archive_lifecycle" and current_plan is None:
            # A blocked archive lifecycle may still need to expose the review-scoped plan
            # that prevented archival, even though the host-facing handoff is
            # persisted under the global execution store.
            current_plan = recovered.current_plan
        archive_lifecycle_payload = effective_route.artifacts.get("archive_lifecycle")
        archive_cleared_active_state = (
            isinstance(archive_lifecycle_payload, Mapping)
            and bool(archive_lifecycle_payload.get("state_cleared", False))
        )
        if effective_route.route_name == "archive_lifecycle" and plan_artifact is not None and archive_cleared_active_state:
            # Archiving the active plan clears active-flow state. Archiving another
            # plan must keep the active run/handoff intact and write a receipt.
            current_run = None
            current_plan = plan_artifact
        handoff_context = (
            replace(resolved_result_context, current_run=None)
            if effective_route.route_name == "archive_lifecycle"
            else resolved_result_context
        )
        handoff = build_runtime_handoff(
            config=config,
            decision=effective_route,
            run_id=(
                _make_run_id(effective_route.request_text)
                if effective_route.route_name == "archive_lifecycle"
                else (current_run.run_id if current_run is not None else _make_run_id(effective_route.request_text))
            ),
            resolved_context=handoff_context,
            current_plan=current_plan,
            kb_artifact=kb_artifact,
            replay_session_dir=replay_session_dir,
            skill_result=skill_result,
            notes=notes,
        )
        if handoff is not None:
            if result_store is global_store:
                handoff = _with_global_handoff_ownership(
                    handoff,
                    current_run=current_run,
                    session_id=session_id,
                )
            derived_resolution_id = _derived_resolution_id(
                resolved_resolution_id=resolved_result_context.resolution_id,
                current_run=current_run,
                current_handoff=handoff,
            )
            if effective_route.route_name == "state_conflict":
                if effective_route.active_run_action == "abort_conflict":
                    if current_run is not None:
                        current_run, handoff = result_store.set_host_facing_truth(
                            run_state=current_run,
                            handoff=handoff,
                            resolution_id=derived_resolution_id,
                            truth_kind=_HOST_FACING_TRUTH_KIND_ENGINE_RUNTIME_HANDOFF,
                        )
                    else:
                        # Conflict abort must still persist a stable handoff even
                        # when no run truth survives the cleanup. Otherwise the
                        # gate sees a current-request handoff with no persisted
                        # carrier and fail-closes as current_request_not_persisted.
                        handoff = stamp_handoff_resolution_id(
                            handoff,
                            resolution_id=derived_resolution_id,
                        )
                        result_store.set_current_handoff(handoff)
                else:
                    # Conflict inspection must remain strictly read-only so the
                    # host can inspect the exact skew that triggered routing.
                    pass
            elif effective_route.route_name == "archive_lifecycle":
                handoff = stamp_handoff_resolution_id(
                    handoff,
                    resolution_id=derived_resolution_id,
                )
                if current_run is None:
                    # Archiving the active plan clears global active-flow truth, so
                    # the archive handoff becomes the new host-facing handoff.
                    result_store.clear_current_archive_receipt()
                    result_store.set_current_handoff(handoff)
                else:
                    # Archiving some other plan must not evict the current active
                    # workflow handoff; persist a route-scoped receipt instead.
                    result_store.set_current_archive_receipt(handoff)
            elif current_run is not None:
                current_run, handoff = result_store.set_host_facing_truth(
                    run_state=current_run,
                    handoff=handoff,
                    resolution_id=derived_resolution_id,
                    truth_kind=_HOST_FACING_TRUTH_KIND_ENGINE_RUNTIME_HANDOFF,
                )
            else:
                handoff = stamp_handoff_resolution_id(
                    handoff,
                    resolution_id=derived_resolution_id,
                )
                result_store.set_current_handoff(handoff)
        else:
            result_store.clear_current_handoff()

    generated_files = _augment_generated_files(
        generated_files,
        config=config,
        route_name=effective_route.route_name,
        plan_artifact=plan_artifact,
        notes=tuple(notes),
        registry_changed_hint=registry_changed_hint,
    )
    # Re-resolve once after persisting the handoff so callers observe the
    # stamped host-facing truth (including paired-write resolution ids).
    latest_context = recover_context(
        effective_route,
        config=config,
        state_store=result_store,
        global_state_store=global_store,
    )
    return RuntimeResult(
        route=effective_route,
        recovered_context=latest_context,
        discovered_skills=skills,
        kb_artifact=kb_artifact,
        plan_artifact=plan_artifact,
        skill_result=skill_result,
        replay_session_dir=replay_session_dir,
        handoff=handoff,
        activation=activation,
        generated_files=generated_files,
        notes=tuple(notes),
    )


def _default_plan_level(decision: RouteDecision) -> str:
    if decision.complexity == "medium":
        return "light"
    return "standard"


def _new_resolution_id() -> str:
    return uuid4().hex


def _derived_resolution_id(
    *,
    resolved_resolution_id: str = "",
    current_run: RunState | None = None,
    current_handoff: RuntimeHandoff | None = None,
) -> str:
    # Host-facing writes should reuse the resolution batch from the snapshot
    # that produced the derived checkpoint truth whenever it is available.
    for candidate in (
        resolved_resolution_id,
        current_run.resolution_id if current_run is not None else "",
        current_handoff.resolution_id if current_handoff is not None else "",
    ):
        normalized = str(candidate or "").strip()
        if normalized:
            return normalized
    return _new_resolution_id()


def _with_route_artifacts(decision: RouteDecision, artifacts: Mapping[str, Any]) -> RouteDecision:
    merged = {**dict(decision.artifacts), **dict(artifacts)}
    return replace(decision, artifacts=merged)


def _same_plan_artifact(left: PlanArtifact | None, right: PlanArtifact | None) -> bool:
    return left is not None and right is not None and left.plan_id == right.plan_id and left.path == right.path


def _archive_state_store_for_current_plan(
    *,
    current_plan: PlanArtifact | None,
    review_store: StateStore,
    global_store: StateStore,
) -> StateStore:
    if _same_plan_artifact(current_plan, global_store.get_current_plan()):
        return global_store
    if _same_plan_artifact(current_plan, review_store.get_current_plan()):
        return review_store
    return global_store


def _pending_required_host_action(snapshot) -> str:
    if snapshot.current_clarification is not None and snapshot.current_clarification.status in {"pending", "collecting"}:
        return "answer_questions"
    if snapshot.current_decision is not None and snapshot.current_decision.status in {"pending", "collecting", "confirmed", "cancelled", "timed_out"}:
        return "confirm_decision"
    return ""


def _augment_generated_files(
    generated_files: tuple[str, ...],
    *,
    config: RuntimeConfig,
    route_name: str,
    plan_artifact: PlanArtifact | None,
    notes: tuple[str, ...],
    registry_changed_hint: bool = False,
) -> tuple[str, ...]:
    items = list(generated_files)
    if _registry_file_should_be_reported(
        config=config,
        route_name=route_name,
        plan_artifact=plan_artifact,
        notes=notes,
        registry_changed_hint=registry_changed_hint,
    ):
        registry_file = registry_relative_path(config)
        if registry_file not in items:
            items.append(registry_file)
    return tuple(items)


def _registry_file_should_be_reported(
    *,
    config: RuntimeConfig,
    route_name: str,
    plan_artifact: PlanArtifact | None,
    notes: tuple[str, ...],
    registry_changed_hint: bool,
) -> bool:
    if route_name == "archive_lifecycle":
        return registry_changed_hint
    if plan_artifact is None:
        return False
    if not any(note.startswith("Plan scaffold created at ") for note in notes):
        return False
    try:
        # Only surface the registry as a changed artifact when the new plan entry
        # is actually observable after the scaffold step.
        entry_result = get_plan_entry(config=config, plan_id=plan_artifact.plan_id)
    except PlanRegistryError:
        return False
    return entry_result.entry is not None


def _make_run_state(
    decision: RouteDecision,
    plan_artifact: PlanArtifact,
    *,
    stage: str = "plan_generated",
    execution_gate: ExecutionGate | None = None,
    execution_authorization_receipt: Mapping[str, Any] | None = None,
) -> RunState:
    now = iso_now()
    return RunState(
        run_id=_make_run_id(decision.request_text),
        status="active",
        stage=stage,
        route_name=decision.route_name,
        title=plan_artifact.title,
        created_at=now,
        updated_at=now,
        plan_id=plan_artifact.plan_id,
        plan_path=plan_artifact.path,
        execution_gate=execution_gate,
        execution_authorization_receipt=execution_authorization_receipt,
        request_excerpt=summarize_request_text(decision.request_text),
        request_sha1=stable_request_sha1(decision.request_text),
        owner_session_id="",
        owner_host="",
        owner_run_id="",
    )


def _make_decision_run_state(decision: RouteDecision, decision_state: DecisionState, *, execution_gate: ExecutionGate | None = None) -> RunState:
    now = iso_now()
    return RunState(
        run_id=_make_run_id(decision.request_text),
        status="active",
        stage="decision_pending",
        route_name=decision_state.resume_route or decision.route_name,
        title=decision_state.question,
        created_at=now,
        updated_at=now,
        plan_id=None,
        plan_path=None,
        execution_gate=execution_gate,
        request_excerpt=summarize_request_text(decision.request_text),
        request_sha1=stable_request_sha1(decision.request_text),
        owner_session_id="",
        owner_host="",
        owner_run_id="",
    )


def _make_clarification_run_state(
    decision: RouteDecision,
    clarification_state: ClarificationState,
    *,
    execution_gate: ExecutionGate | None = None,
) -> RunState:
    now = iso_now()
    return RunState(
        run_id=_make_run_id(decision.request_text),
        status="active",
        stage="clarification_pending",
        route_name=clarification_state.resume_route or decision.route_name,
        title=clarification_state.summary,
        created_at=now,
        updated_at=now,
        plan_id=None,
        plan_path=None,
        execution_gate=execution_gate,
        request_excerpt=summarize_request_text(decision.request_text),
        request_sha1=stable_request_sha1(decision.request_text),
        owner_session_id="",
        owner_host="",
        owner_run_id="",
    )




def _make_run_id(request_text: str) -> str:
    timestamp = iso_now().replace(":", "").replace("-", "")[:15]
    digest = sha1(request_text.encode("utf-8")).hexdigest()[:6]
    return f"{timestamp}_{digest}"




def _find_skill(skills: tuple[SkillMeta, ...], skill_id: str) -> SkillMeta | None:
    for skill in skills:
        if skill.skill_id == skill_id:
            return skill
    return None


def _phase_for_route(decision: RouteDecision) -> str:
    if decision.route_name in {"plan_only", "workflow", "light_iterate", "clarification_pending", "clarification_resume", "decision_pending", "decision_resume"}:
        return "design"
    if decision.route_name in {"resume_active", "exec_plan", "quick_fix"}:
        return "develop"
    return "analysis"


def _build_skill_activation(
    *,
    decision: RouteDecision,
    run_state: RunState | None,
    current_clarification: ClarificationState | None,
    current_decision: DecisionState | None,
) -> SkillActivation:
    skill_id, skill_name = _activation_target(
        decision=decision,
        current_clarification=current_clarification,
        current_decision=current_decision,
    )
    return SkillActivation(
        skill_id=skill_id,
        skill_name=skill_name,
        activated_at=local_iso_now(),
        activated_local_day=local_day_now(),
        display_time=local_display_now(),
        activation_source="runtime_skill" if decision.runtime_skill_id else "route_phase",
        run_id=run_state.run_id if run_state is not None else _make_run_id(decision.request_text),
        route_name=decision.route_name,
        timezone=local_timezone_name(),
    )


def _activation_target(
    *,
    decision: RouteDecision,
    current_clarification: ClarificationState | None,
    current_decision: DecisionState | None,
) -> tuple[str, str]:
    if decision.runtime_skill_id == "workflow-learning" or decision.route_name == "replay":
        return ("workflow-learning", "复盘学习")
    if decision.route_name in {"resume_active", "exec_plan", "quick_fix", "archive_lifecycle"}:
        return ("develop", "开发实施")
    if decision.route_name in {"clarification_pending", "clarification_resume"}:
        if current_clarification is not None and current_clarification.phase == "develop":
            return ("develop", "开发实施")
        return ("analyze", "需求分析")
    if decision.route_name in {"decision_pending", "decision_resume"}:
        if current_decision is not None and current_decision.phase == "develop":
            return ("develop", "开发实施")
        return ("design", "方案设计")
    if decision.route_name in {"plan_only", "workflow", "light_iterate"}:
        return ("design", "方案设计")
    return ("consult", "咨询问答")


def _handle_clarification_resume(
    decision: RouteDecision,
    *,
    state_store: StateStore,
    current_clarification: ClarificationState | None,
    current_decision: DecisionState | None,
    current_plan: PlanArtifact | None,
    current_run: RunState | None,
    config: RuntimeConfig,
    kb_artifact: KbArtifact | None,
) -> tuple[RouteDecision, PlanArtifact | None, list[str], KbArtifact | None]:
    notes: list[str] = []
    if current_clarification is None:
        return (
            _clarification_pending_route(decision, reason="No pending clarification was found"),
            None,
            ["No pending clarification to resume"],
            kb_artifact,
        )

    if decision.active_run_action == "clarification_response_from_state" and has_submitted_clarification(current_clarification):
        resumed_request = merge_clarification_request(current_clarification, current_clarification.response_text or "")
        notes.append("Clarification response restored from structured submission")
    else:
        response = parse_clarification_response(current_clarification, decision.request_text)
        if response.action == "status":
            return (_clarification_pending_route(decision, reason="Clarification is still waiting for factual details"), None, notes, kb_artifact)

        if response.action == "cancel":
            state_store.reset_active_flow()
            return (
                RouteDecision(
                    route_name="cancel_active",
                    request_text=decision.request_text,
                    reason="Clarification cancelled by user",
                    complexity="simple",
                    should_recover_context=True,
                ),
                None,
                ["Clarification cancelled"],
                kb_artifact,
            )

        if response.action != "answer":
            notes.append(response.message or "Invalid clarification response")
            return (_clarification_pending_route(decision, reason="Clarification still requires factual details"), None, notes, kb_artifact)

        resumed_request = merge_clarification_request(current_clarification, response.text)
    if is_develop_callback_state(current_clarification):
        return _resume_from_develop_clarification(
            state_store=state_store,
            current_clarification=current_clarification,
            current_plan=current_plan,
            current_run=current_run,
            resumed_request=resumed_request,
            notes=notes,
            kb_artifact=kb_artifact,
        )

    resumed_route = RouteDecision(
        route_name=current_clarification.resume_route or "plan_only",
        request_text=resumed_request,
        reason="Clarification answered and planning resumed",
        command=None,
        complexity="complex",
        plan_level=current_clarification.requested_plan_level,
        candidate_skill_ids=current_clarification.candidate_skill_ids,
        should_recover_context=False,
        plan_package_policy=current_clarification.plan_package_policy,
        capture_mode=current_clarification.capture_mode,
        artifacts={"planning_resume_source": "clarification"},
    )
    state_store.clear_current_clarification()
    confirmed_decision = (
        current_decision
        if current_decision is not None and current_decision.status == "confirmed" and current_decision.selection is not None
        else None
    )
    planning_route, plan_artifact, planning_notes, kb_artifact = _advance_planning_route(
        resumed_route,
        state_store=state_store,
        config=config,
        kb_artifact=kb_artifact,
        confirmed_decision=confirmed_decision,
        planning_context=_PlanningContext(
            current_run=current_run,
            current_plan=current_plan,
            current_decision=current_decision,
        ),
        plan_materialization_authorized=True,
    )
    notes.extend(planning_notes)
    return (planning_route, plan_artifact, notes, kb_artifact)


def _handle_decision_resume(
    decision: RouteDecision,
    *,
    state_store: StateStore,
    current_decision: DecisionState | None,
    current_plan: PlanArtifact | None,
    current_run: RunState | None,
    config: RuntimeConfig,
    kb_artifact: KbArtifact | None,
) -> tuple[RouteDecision, PlanArtifact | None, list[str], KbArtifact | None, DecisionState | None]:
    notes: list[str] = []
    if current_decision is None:
        return (
            _decision_pending_route(decision, reason="No pending decision checkpoint was found"),
            None,
            ["No pending decision checkpoint to resume"],
            kb_artifact,
            None,
        )

    if decision.active_run_action == "materialize_confirmed_decision":
        response_action = "materialize"
        response_option_id = None
        response_source = "command_override"
        response_message = ""
    else:
        response = None
        if current_decision.status in {"pending", "collecting", "cancelled", "timed_out"} and has_submitted_decision(current_decision):
            response = response_from_submission(current_decision)
            if response is not None:
                notes.append("Decision response restored from structured submission")
        if response is None:
            response = parse_decision_response(current_decision, decision.request_text)
        response_action = response.action
        response_option_id = response.option_id
        response_source = response.source
        response_message = response.message

    if response_action == "status":
        return (_decision_pending_route(decision, reason="Decision checkpoint is still waiting for confirmation"), None, notes, kb_artifact, None)

    if response_action == "cancel":
        state_store.reset_active_flow()
        return (
            RouteDecision(
                route_name="cancel_active",
                request_text=decision.request_text,
                reason="Decision checkpoint cancelled by user",
                complexity="simple",
                should_recover_context=True,
            ),
            None,
            ["Decision checkpoint cancelled"],
            kb_artifact,
            None,
        )

    if response_action == "invalid":
        notes.append(response_message or "Invalid decision response")
        return (_decision_pending_route(decision, reason="Decision checkpoint still requires a valid selection"), None, notes, kb_artifact, None)

    if response_action == "choose":
        raw_input = decision.request_text
        if current_decision.submission is not None and response_source == current_decision.submission.source:
            raw_input = current_decision.submission.raw_input or raw_input
        current_decision = confirm_decision(
            current_decision,
            option_id=response_option_id or "",
            source=response_source,
            raw_input=raw_input,
        )
        state_store.set_current_decision(current_decision)
        notes.append(f"Decision confirmed: {current_decision.selected_option_id}")

    if current_decision.status != "confirmed" or current_decision.selection is None:
        notes.append("Decision checkpoint has not reached a confirmed state yet")
        return (_decision_pending_route(decision, reason="Decision checkpoint is still pending"), None, notes, kb_artifact, None)

    if is_develop_callback_state(current_decision):
        return _resume_from_develop_decision(
            state_store=state_store,
            current_decision=current_decision,
            current_plan=current_plan,
            current_run=current_run,
            notes=notes,
            kb_artifact=kb_artifact,
        )

    if current_decision.decision_type == ACTIVE_PLAN_BINDING_DECISION_TYPE:
        return _resume_from_active_plan_binding_decision(
            state_store=state_store,
            current_decision=current_decision,
            current_plan=current_plan,
            notes=notes,
            kb_artifact=kb_artifact,
            config=config,
        )

    confirmed_decision = current_decision
    planning_route, plan_artifact, planning_notes, kb_artifact = _advance_planning_route(
        RouteDecision(
            route_name=current_decision.resume_route or "plan_only",
            request_text=current_decision.request_text,
            reason="Decision confirmed and planning resumed",
            command=None,
            complexity="complex",
            plan_level=current_decision.requested_plan_level,
            candidate_skill_ids=current_decision.candidate_skill_ids,
            should_recover_context=False,
            plan_package_policy=current_decision.plan_package_policy,
            capture_mode=current_decision.capture_mode,
        ),
        state_store=state_store,
        config=config,
        kb_artifact=kb_artifact,
        confirmed_decision=current_decision,
        planning_context=_PlanningContext(
            current_run=current_run,
            current_plan=current_plan,
            current_decision=current_decision,
        ),
        plan_materialization_authorized=True,
    )
    notes.extend(planning_notes)
    return (planning_route, plan_artifact, notes, kb_artifact, confirmed_decision)


def _resume_from_develop_clarification(
    *,
    state_store: StateStore,
    current_clarification: ClarificationState,
    current_plan: PlanArtifact | None,
    current_run: RunState | None,
    resumed_request: str,
    notes: list[str],
    kb_artifact: KbArtifact | None,
) -> tuple[RouteDecision, PlanArtifact | None, list[str], KbArtifact | None]:
    if current_plan is None or current_run is None:
        notes.append("Develop clarification could not resume because the active run context is missing")
        return (_clarification_pending_route(RouteDecision(route_name="clarification_resume", request_text=resumed_request, reason="missing develop context"), reason="Develop clarification still requires an active plan context"), None, notes, kb_artifact)

    resume_after = develop_resume_after(current_clarification.resume_context)
    resume_route = str((current_clarification.resume_context or {}).get("resume_route") or "").strip()
    state_store.clear_current_clarification()
    if resume_route == "plan_only":
        run_state = _copy_run_state(current_run, stage="plan_generated")
        state_store.set_current_run(run_state)
        notes.append("Develop clarification answered; host must review the plan before continuing")
        return (
            RouteDecision(
                route_name="plan_only",
                request_text=resumed_request,
                reason="Develop clarification changed scope and returned the flow to plan review",
                complexity="complex",
                plan_level=current_plan.level,
                candidate_skill_ids=("design", "develop"),
                should_recover_context=False,
                should_create_plan=False,
                capture_mode=current_clarification.capture_mode,
            ),
            current_plan,
            notes,
            kb_artifact,
        )

    run_state = _copy_run_state(
        current_run,
        stage=str(current_clarification.resume_context.get("active_run_stage") or "executing"),
    )
    state_store.set_current_run(run_state)
    notes.append("Develop clarification answered; host-side implementation may continue")
    return (
        RouteDecision(
            route_name="resume_active",
            request_text=resumed_request,
            reason="Develop clarification answered and host-side implementation may continue",
            complexity="medium",
            plan_level=current_plan.level,
            candidate_skill_ids=current_clarification.candidate_skill_ids or ("develop",),
            should_recover_context=True,
            should_create_plan=False,
            capture_mode=current_clarification.capture_mode,
            active_run_action="resume",
        ),
        current_plan,
        notes,
        kb_artifact,
    )




def _resume_from_develop_decision(
    *,
    state_store: StateStore,
    current_decision: DecisionState,
    current_plan: PlanArtifact | None,
    current_run: RunState | None,
    notes: list[str],
    kb_artifact: KbArtifact | None,
) -> tuple[RouteDecision, PlanArtifact | None, list[str], KbArtifact | None, DecisionState | None]:
    if current_plan is None or current_run is None:
        notes.append("Develop decision could not resume because the active run context is missing")
        return (_decision_pending_route(RouteDecision(route_name="decision_resume", request_text=current_decision.request_text, reason="missing develop context"), reason="Develop decision still requires an active plan context"), None, notes, kb_artifact, None)

    resume_after = develop_resume_after(current_decision.resume_context)
    resume_route = str((current_decision.resume_context or {}).get("resume_route") or "").strip()
    _consume_current_decision(state_store, current_decision)
    if resume_route == "plan_only":
        run_state = _copy_run_state(current_run, stage="plan_generated")
        state_store.set_current_run(run_state)
        notes.append("Develop decision confirmed; host must review the plan before continuing")
        return (
            RouteDecision(
                route_name="plan_only",
                request_text=current_decision.request_text,
                reason="Develop decision changed scope and returned the flow to plan review",
                complexity="complex",
                plan_level=current_plan.level,
                candidate_skill_ids=("design", "develop"),
                should_recover_context=False,
                should_create_plan=False,
                capture_mode=current_decision.capture_mode,
            ),
            current_plan,
            notes,
            kb_artifact,
            current_decision,
        )

    run_state = _copy_run_state(
        current_run,
        stage=str(current_decision.resume_context.get("active_run_stage") or "executing"),
    )
    state_store.set_current_run(run_state)
    notes.append("Develop decision confirmed; host-side implementation may continue")
    return (
        RouteDecision(
            route_name="resume_active",
            request_text=current_decision.request_text,
            reason="Develop decision confirmed and host-side implementation may continue",
            complexity="medium",
            plan_level=current_plan.level,
            candidate_skill_ids=current_decision.candidate_skill_ids or ("develop",),
            should_recover_context=True,
            should_create_plan=False,
            capture_mode=current_decision.capture_mode,
            active_run_action="resume",
        ),
        current_plan,
        notes,
        kb_artifact,
        current_decision,
    )


def _resume_from_active_plan_binding_decision(
    *,
    state_store: StateStore,
    current_decision: DecisionState,
    current_plan: PlanArtifact | None,
    notes: list[str],
    kb_artifact: KbArtifact | None,
    config: RuntimeConfig,
) -> tuple[RouteDecision, PlanArtifact | None, list[str], KbArtifact | None, DecisionState | None]:
    selected_option_id = current_decision.selected_option_id or ""
    resume_route = current_decision.resume_route or "plan_only"
    _consume_current_decision(state_store, current_decision)
    notes.append(f"Active-plan routing decision confirmed: {selected_option_id or '<unknown>'}")

    resumed_route = RouteDecision(
        route_name=resume_route,
        request_text=current_decision.request_text,
        reason="Active-plan routing decision confirmed and planning resumed",
        complexity="complex",
        plan_level=current_decision.requested_plan_level,
        candidate_skill_ids=current_decision.candidate_skill_ids or ("design", "develop"),
        should_recover_context=False,
        plan_package_policy=current_decision.plan_package_policy,
        capture_mode=current_decision.capture_mode,
        artifacts={
            "active_plan_binding_selection": selected_option_id,
        },
    )
    planning_route, plan_artifact, planning_notes, kb_artifact = _advance_planning_route(
        resumed_route,
        state_store=state_store,
        config=config,
        kb_artifact=kb_artifact,
        planning_context=_PlanningContext(
            current_plan=current_plan,
        ),
        plan_materialization_authorized=True,
    )
    notes.extend(planning_notes)
    return (planning_route, plan_artifact, notes, kb_artifact, current_decision)



def _exec_plan_unavailable_route(decision: RouteDecision, *, reason: str) -> RouteDecision:
    return RouteDecision(
        route_name="exec_plan",
        request_text=decision.request_text,
        reason=reason,
        command=decision.command,
        complexity=decision.complexity,
        plan_level=decision.plan_level,
        candidate_skill_ids=decision.candidate_skill_ids or ("develop",),
        should_recover_context=True,
        should_create_plan=False,
        capture_mode=decision.capture_mode,
        runtime_skill_id=None,
        active_run_action="inspect_exec_recovery",
        artifacts=decision.artifacts,
    )


def _clarification_pending_route(decision: RouteDecision, *, reason: str) -> RouteDecision:
    return RouteDecision(
        route_name="clarification_pending",
        request_text=decision.request_text,
        reason=reason,
        command=decision.command,
        complexity=decision.complexity,
        plan_level=decision.plan_level,
        candidate_skill_ids=decision.candidate_skill_ids,
        should_recover_context=True,
        should_create_plan=False,
        capture_mode=decision.capture_mode,
        runtime_skill_id=None,
        active_run_action="inspect_clarification",
        artifacts=decision.artifacts,
    )


def _decision_pending_route(decision: RouteDecision, *, reason: str) -> RouteDecision:
    return RouteDecision(
        route_name="decision_pending",
        request_text=decision.request_text,
        reason=reason,
        command=decision.command,
        complexity=decision.complexity,
        plan_level=decision.plan_level,
        candidate_skill_ids=decision.candidate_skill_ids,
        should_recover_context=True,
        should_create_plan=False,
        capture_mode=decision.capture_mode,
        runtime_skill_id=None,
        active_run_action="inspect_decision",
        artifacts=decision.artifacts,
    )


def _plan_review_route(
    decision: RouteDecision,
    *,
    reason: str,
    plan_level: str | None,
) -> RouteDecision:
    return RouteDecision(
        route_name="plan_only",
        request_text=decision.request_text,
        reason=reason,
        command=decision.command,
        complexity=decision.complexity,
        plan_level=plan_level,
        candidate_skill_ids=decision.candidate_skill_ids or ("design", "develop"),
        should_recover_context=False,
        plan_package_policy="none",
        should_create_plan=False,
        capture_mode=decision.capture_mode,
        runtime_skill_id=None,
        artifacts=decision.artifacts,
    )


def _normalized_plan_package_policy(decision: RouteDecision, *, config: RuntimeConfig) -> str:
    """Fail closed: unknown or missing policy → none. No implicit immediate."""
    policy = str(decision.plan_package_policy or "none").strip() or "none"
    return policy


def _resume_active_route(*, request_text: str, candidate_skill_ids: tuple[str, ...]) -> RouteDecision:
    return RouteDecision(
        route_name="resume_active",
        request_text=request_text,
        reason="Execution confirmed and develop may start",
        complexity="medium",
        should_recover_context=True,
        candidate_skill_ids=candidate_skill_ids,
        active_run_action="resume",
    )


def _copy_run_state(
    current_run: RunState,
    *,
    stage: str,
    execution_gate: ExecutionGate | None | object = None,
) -> RunState:
    next_execution_gate = current_run.execution_gate if execution_gate is None else execution_gate
    return RunState(
        run_id=current_run.run_id,
        status=current_run.status,
        stage=stage,
        route_name=current_run.route_name,
        title=current_run.title,
        created_at=current_run.created_at,
        updated_at=iso_now(),
        plan_id=current_run.plan_id,
        plan_path=current_run.plan_path,
        execution_gate=next_execution_gate,
        execution_authorization_receipt=current_run.execution_authorization_receipt,
        request_excerpt=current_run.request_excerpt,
        request_sha1=current_run.request_sha1,
        owner_session_id=current_run.owner_session_id,
        owner_host=current_run.owner_host,
        owner_run_id=current_run.owner_run_id,
    )


def _advance_planning_route(
    decision: RouteDecision,
    *,
    state_store: StateStore,
    config: RuntimeConfig,
    kb_artifact: KbArtifact | None,
    confirmed_decision: DecisionState | None = None,
    planning_context: _PlanningContext | None = None,
    plan_materialization_authorized: bool = False,
) -> tuple[RouteDecision, PlanArtifact | None, list[str], KbArtifact | None]:
    notes: list[str] = []
    context = planning_context or _capture_planning_context(state_store)
    plan_package_policy = _normalized_plan_package_policy(decision, config=config)
    kb_artifact = _merge_kb_artifacts(kb_artifact, ensure_blueprint_scaffold(config), config=config)

    pending_clarification = _build_route_native_clarification_state(decision, config=config)
    if pending_clarification is not None:
        state_store.set_current_clarification(pending_clarification)
        _preserve_or_clear_current_plan_for_pending_planning_checkpoint(
            decision,
            current_plan=context.current_plan,
            state_store=state_store,
            config=config,
        )
        clarification_gate = evaluate_execution_gate(
            decision=decision,
            plan_artifact=None,
            current_clarification=pending_clarification,
            current_decision=None,
            config=config,
        )
        state_store.set_current_run(
            _make_clarification_run_state(
                decision,
                pending_clarification,
                execution_gate=clarification_gate,
            )
        )
        if confirmed_decision is not None and confirmed_decision.status == "confirmed":
            state_store.set_current_decision(confirmed_decision)
        notes.append(f"Clarification created: {pending_clarification.clarification_id}")
        return (
            _clarification_pending_route(
                decision,
                reason="Detected missing factual details that must be clarified before planning can continue",
            ),
            None,
            notes,
            kb_artifact,
        )

    if confirmed_decision is None:
        current_plan = context.current_plan
        if current_plan is not None and _should_create_active_plan_binding_decision(
            decision,
            current_plan=current_plan,
            config=config,
        ):
            pending_decision = build_active_plan_binding_decision_state(
                decision,
                current_plan=current_plan,
                config=config,
            )
            state_store.set_current_decision(pending_decision)
            current_run = context.current_run
            state_store.set_current_run(
                RunState(
                    run_id=current_run.run_id if current_run is not None else _make_run_id(decision.request_text),
                    status="active",
                    stage="decision_pending",
                    route_name=decision.route_name,
                    title=pending_decision.question,
                    created_at=current_run.created_at if current_run is not None else iso_now(),
                    updated_at=iso_now(),
                    plan_id=current_plan.plan_id,
                    plan_path=current_plan.path,
                    execution_gate=current_run.execution_gate if current_run is not None else None,
                    request_excerpt=summarize_request_text(decision.request_text),
                    request_sha1=stable_request_sha1(decision.request_text),
                )
            )
            notes.append(f"Decision checkpoint created: {pending_decision.decision_id}")
            return (
                _decision_pending_route(
                    decision,
                    reason="A non-anchored complex request arrived while another plan is active",
                ),
                None,
                notes,
                kb_artifact,
            )

        pending_decision = _build_route_native_decision_state(decision, config=config)
        if pending_decision is not None:
            state_store.set_current_decision(pending_decision)
            _preserve_or_clear_current_plan_for_pending_planning_checkpoint(
                decision,
                current_plan=context.current_plan,
                state_store=state_store,
                config=config,
            )
            decision_gate = evaluate_execution_gate(
                decision=decision,
                plan_artifact=None,
                current_clarification=None,
                current_decision=pending_decision,
                config=config,
            )
            state_store.set_current_run(
                _make_decision_run_state(
                    decision,
                    pending_decision,
                    execution_gate=decision_gate,
                )
            )
            notes.append(f"Decision checkpoint created: {pending_decision.decision_id}")
            return (
                _decision_pending_route(decision, reason="Detected an explicit design split that requires confirmation"),
                None,
            notes,
            kb_artifact,
        )

    level = decision.plan_level or _default_plan_level(decision)
    selection = _resolve_plan_for_request(
        decision,
        current_plan=context.current_plan,
        state_store=state_store,
        config=config,
        confirmed_decision=confirmed_decision,
    )
    if selection.action == "reuse_existing":
        plan_artifact = selection.plan_artifact
        if plan_artifact is None:
            raise RuntimeError("Plan selection resolved to reuse_existing without an artifact")
        state_store.set_current_plan(plan_artifact)
        if selection.reason_note:
            notes.append(selection.reason_note)
        routed_decision, plan_artifact, gate_notes = _apply_execution_gate_to_plan(
            decision,
            plan_artifact=plan_artifact,
            state_store=state_store,
            config=config,
            decision_context=confirmed_decision,
        )
        notes.extend(gate_notes)
        return (routed_decision, plan_artifact, notes, kb_artifact)

    # Authorization boundary: authorized_only blocks plan materialization
    # unless the Validator explicitly authorized write_plan_package.
    # When blocked, downgrade to consult so handoff reflects reality.
    if plan_package_policy == "authorized_only" and not plan_materialization_authorized:
        notes.append("Plan materialization blocked: policy is authorized_only but no authorization present")
        # Preserve guard artifacts (e.g. direct_edit_guard_kind) from the
        # original decision so the gate contract still surfaces them.
        blocked_artifacts: dict[str, Any] = {}
        orig_artifacts = decision.artifacts or {}
        for key in ("entry_guard_reason_code", "direct_edit_guard_kind", "direct_edit_guard_trigger"):
            val = orig_artifacts.get(key)
            if val:
                blocked_artifacts[key] = val
        blocked_decision = RouteDecision(
            route_name="consult",
            request_text=decision.request_text,
            reason=f"Plan materialization not authorized (original route: {decision.route_name})",
            complexity=decision.complexity,
            should_recover_context=False,
            plan_package_policy="none",
            artifacts=blocked_artifacts or {},
        )
        return (blocked_decision, None, notes, kb_artifact)

    created = create_plan_scaffold(
        decision.request_text,
        config=config,
        level=level,
        decision_state=confirmed_decision,
    )
    state_store.set_current_plan(created)
    kb_artifact = _merge_kb_artifacts(kb_artifact, ensure_blueprint_index(config), config=config)
    notes.extend(
        _created_plan_notes(
            created,
            config=config,
            base_note=_created_plan_base_note(created.path, selection.reason_note),
        )
    )

    routed_decision, plan_artifact, gate_notes = _apply_execution_gate_to_plan(
        decision,
        plan_artifact=created,
        state_store=state_store,
        config=config,
        decision_context=confirmed_decision,
    )
    notes.extend(gate_notes)
    return (routed_decision, plan_artifact, notes, kb_artifact)


def _resolve_plan_for_request(
    decision: RouteDecision,
    *,
    current_plan: PlanArtifact | None,
    state_store: StateStore,
    config: RuntimeConfig,
    confirmed_decision: DecisionState | None,
) -> _PlanSelection:
    active_plan_binding_selection = str(decision.artifacts.get("active_plan_binding_selection") or "").strip()

    if confirmed_decision is not None:
        if confirmed_decision.decision_type == ACTIVE_PLAN_BINDING_DECISION_TYPE:
            selected_option_id = confirmed_decision.selected_option_id or ""
            if selected_option_id == ACTIVE_PLAN_ATTACH_OPTION_ID and current_plan is not None:
                return _PlanSelection(
                    action="reuse_existing",
                    plan_artifact=current_plan,
                    reason_note=f"Attached the request back to active plan {current_plan.path} after decision confirmation",
                )
            if selected_option_id == ACTIVE_PLAN_NEW_OPTION_ID or current_plan is None:
                return _PlanSelection(
                    action="create_new",
                    reason_note="after active-plan routing confirmation",
                )

        if current_plan is not None:
            return _PlanSelection(
                action="reuse_existing",
                plan_artifact=current_plan,
                reason_note=f"Reused active plan {current_plan.path} after decision confirmation",
            )
        return _PlanSelection(
            action="create_new",
            reason_note="after decision confirmation",
        )

    explicit_plan = find_plan_by_request_reference(decision.request_text, config=config)
    explicit_new_plan = request_explicitly_wants_new_plan(decision.request_text)

    if active_plan_binding_selection == ACTIVE_PLAN_NEW_OPTION_ID:
        return _PlanSelection(
            action="create_new",
            reason_note="(selected new-plan routing)",
        )

    if explicit_plan is not None:
        if current_plan is not None and explicit_plan.plan_id == current_plan.plan_id:
            return _PlanSelection(
                action="reuse_existing",
                plan_artifact=current_plan,
                reason_note=f"Reused active plan {current_plan.path} (explicit self-reference)",
            )
        return _PlanSelection(
            action="reuse_existing",
            plan_artifact=explicit_plan,
            reason_note=f"Rebound planning context to existing plan {explicit_plan.path} (explicit plan reference)",
        )

    if explicit_new_plan:
        return _PlanSelection(
            action="create_new",
            reason_note="(explicit new-plan request)",
        )

    if current_plan is not None:
        if active_plan_binding_selection == ACTIVE_PLAN_ATTACH_OPTION_ID:
            return _PlanSelection(
                action="reuse_existing",
                plan_artifact=current_plan,
                reason_note=f"Reused active plan {current_plan.path} (selected current-plan routing)",
            )
        if _request_anchors_current_plan(decision.request_text, current_plan=current_plan):
            return _PlanSelection(
                action="reuse_existing",
                plan_artifact=current_plan,
                reason_note=f"Reused active plan {current_plan.path} (implicit current-plan anchor)",
            )
        return _PlanSelection(
            action="reuse_existing",
            plan_artifact=current_plan,
            reason_note=f"Reused active plan {current_plan.path} under strict single-active-plan policy",
        )

    return _PlanSelection(
        action="create_new",
        reason_note="",
    )


def _created_plan_notes(created: PlanArtifact, *, config: RuntimeConfig, base_note: str) -> list[str]:
    notes = [base_note]
    priority_note = priority_note_for_plan(
        config=config,
        plan_id=created.plan_id,
        language=config.language,
    )
    if priority_note:
        notes.append(encode_priority_note_event(priority_note))
    return notes


def _created_plan_base_note(plan_path: str, reason_note: str) -> str:
    base = f"Plan scaffold created at {plan_path}"
    if reason_note:
        return f"{base} {reason_note}"
    return base


def _should_create_active_plan_binding_decision(
    decision: RouteDecision,
    *,
    current_plan: PlanArtifact,
    config: RuntimeConfig,
) -> bool:
    if decision.route_name not in {"plan_only", "workflow", "light_iterate"}:
        return False
    if decision.complexity != "complex":
        return False
    if str(decision.artifacts.get("active_plan_binding_selection") or "").strip():
        return False
    if str(decision.artifacts.get("planning_resume_source") or "").strip():
        return False
    if find_plan_by_request_reference(decision.request_text, config=config) is not None:
        return False
    if request_explicitly_wants_new_plan(decision.request_text):
        return False
    return not _request_anchors_current_plan(decision.request_text, current_plan=current_plan)


def _request_anchors_current_plan(request_text: str, *, current_plan: PlanArtifact) -> bool:
    text = request_text.strip()
    if not text:
        return False

    lowered = text.casefold()
    for anchor in (current_plan.plan_id, current_plan.path, current_plan.title):
        candidate = str(anchor or "").strip().casefold()
        if candidate and candidate in lowered:
            return True

    compact = lowered.replace(" ", "")
    if any(token in compact for token in ("当前plan", "这个plan", "该plan", "activeplan", "currentplan")):
        return True
    if any(token in compact for token in ("当前方案", "这个方案", "该方案")):
        return True
    return any(pattern.search(text) is not None for pattern in _CURRENT_PLAN_ANCHOR_PATTERNS)


def _preserve_or_clear_current_plan_for_pending_planning_checkpoint(
    decision: RouteDecision,
    *,
    current_plan: PlanArtifact | None,
    state_store: StateStore,
    config: RuntimeConfig,
) -> None:
    if current_plan is None:
        return

    explicit_plan = find_plan_by_request_reference(decision.request_text, config=config)
    if explicit_plan is not None and explicit_plan.plan_id != current_plan.plan_id:
        state_store.set_current_plan(explicit_plan)
        return

    if request_explicitly_wants_new_plan(decision.request_text):
        state_store.clear_current_plan()
        return


def _apply_execution_gate_to_plan(
    decision: RouteDecision,
    *,
    plan_artifact: PlanArtifact,
    state_store: StateStore,
    config: RuntimeConfig,
    decision_context: DecisionState | None,
) -> tuple[RouteDecision, PlanArtifact, list[str]]:
    review_route = _plan_review_route(
        decision,
        reason="Plan materialized and is waiting for review before execution",
        plan_level=plan_artifact.level,
    )
    if str(decision.artifacts.get("active_plan_binding_selection") or "").strip() == ACTIVE_PLAN_ATTACH_OPTION_ID:
        gate = ExecutionGate(
            gate_status="blocked",
            blocking_reason="missing_info",
            plan_completion="incomplete",
            next_required_action="continue_host_develop",
            notes=("Attached the new request to the current plan; review and update that plan before execution continues.",),
        )
        state_store.set_current_run(
            _make_run_state(
                _plan_review_route(
                    decision,
                    reason="Attached request to the current plan and returned it to plan review",
                    plan_level=decision.plan_level or plan_artifact.level,
                ),
                plan_artifact,
                stage="plan_generated",
                execution_gate=gate,
            )
        )
        return (
            _plan_review_route(
                decision,
                reason="Attached request to the current plan and returned it to plan review",
                plan_level=decision.plan_level or plan_artifact.level,
            ),
            plan_artifact,
            list(gate.notes),
        )

    gate = evaluate_execution_gate(
        decision=decision,
        plan_artifact=plan_artifact,
        current_clarification=None,
        current_decision=decision_context,
        config=config,
    )
    notes = list(gate.notes)

    if decision_context is not None and decision_context.status == "confirmed" and decision_context.selection is not None:
        _consume_current_decision(state_store, decision_context)
        notes.append(f"Decision consumed: {decision_context.decision_id}")

    if gate.gate_status == "decision_required" and gate.blocking_reason != "unresolved_decision":
        next_run_state = RunState(
            run_id=_make_run_id(decision.request_text),
            status="active",
            stage="decision_pending",
            route_name=decision.route_name,
            title=plan_artifact.title,
            created_at=plan_artifact.created_at,
            updated_at=iso_now(),
            plan_id=plan_artifact.plan_id,
            plan_path=plan_artifact.path,
            execution_gate=gate,
            request_excerpt=summarize_request_text(decision.request_text),
            request_sha1=stable_request_sha1(decision.request_text),
        )
        gate_decision = _build_route_native_gate_decision_state(
            decision,
            gate=gate,
            current_plan=plan_artifact,
            current_run=next_run_state,
            config=config,
        )
        if gate_decision is not None:
            checkpoint_store, checkpoint_notes = _persist_execution_gate_checkpoint(
                state_store=state_store,
                config=config,
                current_plan=plan_artifact,
                next_run_state=next_run_state,
                gate_decision=gate_decision,
            )
            notes.extend(checkpoint_notes)
            if checkpoint_store is not state_store:
                notes.append("Promoted execution gate checkpoint to global execution truth")
            notes.append(f"Execution gate requested a new decision: {gate_decision.decision_id}")
            return (
                _decision_pending_route(decision, reason="Execution gate found a blocking risk that still requires confirmation"),
                plan_artifact,
                notes,
            )

    stage = "ready_for_execution" if gate.gate_status == "ready" else "plan_generated"
    state_store.set_current_run(
        _make_run_state(
            review_route,
            plan_artifact,
            stage=stage,
            execution_gate=gate,
        )
    )
    return (
        review_route,
        plan_artifact,
        notes,
    )


def _consume_current_decision(state_store: StateStore, decision_state: DecisionState) -> None:
    consumed = consume_decision(decision_state)
    state_store.set_current_decision(consumed)
    state_store.clear_current_decision()


def _consume_current_decision_if_confirmed_match(
    state_store: StateStore,
    decision_state: DecisionState | None,
    *,
    current_decision: DecisionState | None,
) -> bool:
    if decision_state is None or decision_state.status != "confirmed" or decision_state.selection is None:
        return False
    if current_decision is None:
        return False
    if current_decision.decision_id != decision_state.decision_id:
        return False
    if current_decision.status != "confirmed" or current_decision.selection is None:
        return False
    _consume_current_decision(state_store, current_decision)
    return True


def _confirmed_decision_context(*, current_decision: DecisionState | None) -> DecisionState | None:
    if current_decision is None or current_decision.status != "confirmed" or current_decision.selection is None:
        return None
    return current_decision


def _merge_kb_artifacts(kb_artifact: KbArtifact | None, extra_files: tuple[str, ...], *, config: RuntimeConfig) -> KbArtifact | None:
    if kb_artifact is None and not extra_files:
        return None
    base_files = kb_artifact.files if kb_artifact is not None else ()
    merged_files = tuple(dict.fromkeys((*base_files, *extra_files)))
    return KbArtifact(
        mode=config.kb_init,
        files=merged_files,
        created_at=kb_artifact.created_at if kb_artifact is not None else iso_now(),
    )


def _build_route_native_clarification_state(
    decision: RouteDecision,
    *,
    config: RuntimeConfig,
) -> ClarificationState | None:
    """Route planning-mode clarification through the generic checkpoint contract."""
    clarification_state = build_clarification_state(decision, config=config)
    if clarification_state is None:
        return None
    request = checkpoint_request_from_clarification_state(
        clarification_state,
        config=config,
        source_route=decision.route_name,
    )
    materialized = materialize_checkpoint_request(request.to_dict(), config=config)
    return materialized.clarification_state


def _build_route_native_decision_state(
    decision: RouteDecision,
    *,
    config: RuntimeConfig,
) -> DecisionState | None:
    """Route planning-mode design decisions through the generic checkpoint contract."""
    decision_state = build_decision_state(decision, config=config)
    if decision_state is None:
        return None
    request = checkpoint_request_from_decision_state(
        decision_state,
        source_route=decision.route_name,
    )
    materialized = materialize_checkpoint_request(request.to_dict(), config=config)
    return materialized.decision_state


def _build_route_native_gate_decision_state(
    decision: RouteDecision,
    *,
    gate: ExecutionGate,
    current_plan: PlanArtifact,
    current_run: RunState | None,
    config: RuntimeConfig,
) -> DecisionState | None:
    """Create execution-bound gate decisions without downcasting their phase.

    Generic checkpoint requests only expose public source stages like design /
    develop. Execution-gate decisions are internal execution-bound checkpoints,
    so routing them through the generic materializer would both reject the
    source stage and erase the execution-gate phase we need for liveness.
    """
    decision_state = build_execution_gate_decision_state(
        decision,
        gate=gate,
        current_plan=current_plan,
        config=config,
    )
    if decision_state is None:
        return None
    return replace(
        decision_state,
        resume_context=_execution_gate_decision_resume_context(
            decision_state=decision_state,
            current_plan=current_plan,
            current_run=current_run,
            gate=gate,
        ),
    )


def _execution_gate_decision_resume_context(
    *,
    decision_state: DecisionState,
    current_plan: PlanArtifact,
    current_run: RunState | None,
    gate: ExecutionGate,
) -> Mapping[str, Any]:
    resume_context = dict(decision_state.resume_context)
    resume_context.setdefault("active_run_stage", current_run.stage if current_run is not None else "decision_pending")
    resume_context.setdefault("current_plan_path", current_plan.path)
    resume_context["task_refs"] = list(resume_context.get("task_refs") or [])
    resume_context["changed_files"] = list(resume_context.get("changed_files") or [])
    resume_context.setdefault(
        "working_summary",
        f"Execution gate is waiting for a blocking-risk decision before develop continues: {gate.blocking_reason}",
    )
    resume_context["verification_todo"] = list(resume_context.get("verification_todo") or [])
    resume_context.setdefault("resume_after", "continue_host_develop")
    return resume_context
