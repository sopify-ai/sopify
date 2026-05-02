"""Resolved runtime state snapshot with quarantine/conflict diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

from .checkpoint_request import develop_resume_context_issue
from .models import (
    ClarificationState,
    DecisionState,
    PlanArtifact,
    RouteDecision,
    RunState,
    RuntimeConfig,
    RuntimeHandoff,
)
from .state import StateStore
from .state_invariants import is_supported_phase

_NEGOTIATION_RUN_STAGE_ACTIONS = {
    "clarification_pending": "answer_questions",
    "decision_pending": "confirm_decision",
    "ready_for_execution": "confirm_execute",
    "execution_confirm_pending": "confirm_execute",
}
_DECISION_CONFLICT_STATUSES = {"pending", "collecting", "confirmed", "cancelled", "timed_out"}
_CLARIFICATION_CONFLICT_STATUSES = {"pending", "collecting"}
_PENDING_HOST_ACTIONS = {"answer_questions", "confirm_decision", "confirm_execute"}
_PENDING_ACTION_EXPECTED_STATE_KINDS = {
    "answer_questions": {"current_clarification"},
    "confirm_decision": {"current_decision"},
}
_CONFLICT_ALLOWED_USER_INTENTS = ("cancel", "force_cancel")
_CONFLICT_ALLOWED_INTERNAL_ACTIONS = ("abort_negotiation",)
_PRIMARY_SCOPE = "primary"


@dataclass(frozen=True)
class QuarantinedStateItem:
    state_kind: str
    path: str
    reason: str
    provenance_status: str
    state_scope: str

    def to_dict(self) -> dict[str, str]:
        return {
            "state_kind": self.state_kind,
            "path": self.path,
            "reason": self.reason,
            "provenance_status": self.provenance_status,
            "state_scope": self.state_scope,
        }


@dataclass(frozen=True)
class StateConflictDetail:
    code: str
    message: str
    path: str = ""
    state_scope: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "state_scope": self.state_scope,
        }


@dataclass(frozen=True)
class ContextResolvedSnapshot:
    resolution_id: str
    current_run: RunState | None = None
    current_plan: PlanArtifact | None = None
    current_plan_proposal: Any | None = None  # Wave 3a: field kept for structural compat, always None
    current_clarification: ClarificationState | None = None
    current_decision: DecisionState | None = None
    current_handoff: RuntimeHandoff | None = None
    last_route: RouteDecision | None = None
    execution_active_run: RunState | None = None
    execution_current_plan: PlanArtifact | None = None
    quarantined_items: tuple[QuarantinedStateItem, ...] = ()
    conflict_items: tuple[StateConflictDetail, ...] = ()
    notes: tuple[str, ...] = ()
    preferred_state_scope: str = "session"
    is_conflict: bool = False
    conflict_code: str = ""
    conflict_message: str = ""
    conflict_artifacts: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


def resolve_context_snapshot(
    *,
    config: RuntimeConfig,
    review_store: StateStore,
    global_store: StateStore,
) -> ContextResolvedSnapshot:
    """Resolve runtime state exactly once and quarantine/flag invalid combinations."""
    same_scope_store = (
        review_store.root == global_store.root
        and review_store.session_id == global_store.session_id
    )
    review_scope = _PRIMARY_SCOPE if same_scope_store else "session"
    review_run = review_store.get_current_run()
    review_plan = review_store.get_current_plan()
    review_handoff = review_store.get_current_handoff()
    review_last_route = review_store.get_last_route()

    global_run = None if same_scope_store else global_store.get_current_run()
    global_plan = None if same_scope_store else global_store.get_current_plan()
    global_handoff = None if same_scope_store else global_store.get_current_handoff()
    global_last_route = None if same_scope_store else global_store.get_last_route()

    quarantined: list[QuarantinedStateItem] = []
    conflicts: list[StateConflictDetail] = []
    notes: list[str] = []

    review_clarification = _load_clarification(
        store=review_store,
        scope=review_scope,
        active_run=review_run,
        quarantined=quarantined,
    )
    global_clarification = None
    if not same_scope_store:
        global_clarification = _load_clarification(
            store=global_store,
            scope="global",
            active_run=global_run,
            quarantined=quarantined,
        )

    review_decision = _load_decision(
        store=review_store,
        scope=review_scope,
        active_run=review_run,
        quarantined=quarantined,
    )
    global_decision = None
    if not same_scope_store:
        global_decision = _load_decision(
            store=global_store,
            scope="global",
            active_run=global_run,
            quarantined=quarantined,
        )

    if not same_scope_store and _should_ignore_legacy_global_review_state(
        current_run=global_run,
        current_plan=global_plan,
        current_handoff=global_handoff,
    ):
        if global_run is not None:
            quarantined.append(
                _quarantined_item(
                    store=global_store,
                    path=global_store.current_run_path,
                    state_kind="current_run",
                    reason="legacy_global_review_state_requires_session_scope",
                    provenance_status="scope_mismatch",
                )
            )
        if global_handoff is not None:
            quarantined.append(
                _quarantined_item(
                    store=global_store,
                    path=global_store.current_handoff_path,
                    state_kind="current_handoff",
                    reason="legacy_global_review_state_requires_session_scope",
                    provenance_status="scope_mismatch",
                )
            )
        global_run = None
        global_handoff = None
        global_last_route = None

    conflicts.extend(
        _collect_run_handoff_conflicts(
            store=review_store,
            scope=review_store.scope,
            current_run=review_run,
            current_handoff=review_handoff,
            current_clarification=review_clarification,
            current_decision=review_decision,
        )
    )
    if not same_scope_store:
        conflicts.extend(
            _collect_run_handoff_conflicts(
                store=global_store,
                scope="global",
                current_run=global_run,
                current_handoff=global_handoff,
                current_clarification=global_clarification,
                current_decision=global_decision,
            )
        )

    pending_items = _collect_pending_items(
        review_store=review_store,
        global_store=global_store,
        review_clarification=review_clarification,
        review_decision=review_decision,
        global_clarification=global_clarification,
        global_decision=global_decision,
    )
    active_pending_action, active_pending_store, active_pending_path, active_pending_source = _resolve_active_pending_context(
        review_store=review_store,
        global_store=global_store,
        review_run=review_run,
        global_run=global_run,
        review_handoff=review_handoff,
        global_handoff=global_handoff,
    )
    effective_pending_items = _filter_pending_items_for_active_action(
        pending_items,
        active_pending_action=active_pending_action,
        review_store=review_store,
        global_store=global_store,
        review_decision=review_decision,
        global_decision=global_decision,
    )
    execution_confirm_conflict = _execution_confirm_review_checkpoint_conflict(
        active_pending_action=active_pending_action,
        active_pending_store=active_pending_store,
        active_pending_path=active_pending_path,
        review_clarification=review_clarification,
        review_decision=review_decision,
        global_clarification=global_clarification,
        global_decision=global_decision,
    )
    if not conflicts and execution_confirm_conflict is not None:
        conflicts.append(execution_confirm_conflict)
    pending_mismatch = _pending_checkpoint_handoff_mismatch(
        active_pending_action=active_pending_action,
        active_pending_store=active_pending_store,
        active_pending_path=active_pending_path,
        active_pending_source=active_pending_source,
        pending_items=effective_pending_items,
    )
    if not conflicts and pending_mismatch is not None:
        conflicts.append(pending_mismatch)
    if not conflicts and len(effective_pending_items) > 1:
        conflicts.append(
            StateConflictDetail(
                code="multiple_pending_checkpoints",
                message="Multiple valid pending checkpoints are simultaneously active",
            )
        )
    if not conflicts:
        conflicts.extend(
            _rehydrate_handoff_state_conflict(
                store=review_store,
                scope=review_store.scope,
                current_handoff=review_handoff,
            )
        )
    if not conflicts and not same_scope_store:
        conflicts.extend(
            _rehydrate_handoff_state_conflict(
                store=global_store,
                scope="global",
                current_handoff=global_handoff,
            )
        )

    if quarantined:
        notes.append(f"Quarantined {len(quarantined)} stale or invalid state file(s)")
    if conflicts:
        notes.append(f"Detected state conflict: {conflicts[0].code}")

    current_run = review_run or global_run
    current_plan = review_plan or global_plan
    current_handoff = review_handoff or global_handoff
    execution_active_run = global_run or review_run
    execution_current_plan = global_plan or review_plan
    current_last_route = review_last_route or global_last_route
    preferred_scope = review_store.scope if same_scope_store else _preferred_state_scope(global_run=global_run, global_handoff=global_handoff)
    conflict_code = conflicts[0].code if conflicts else ""
    conflict_message = conflicts[0].message if conflicts else ""
    return ContextResolvedSnapshot(
        resolution_id=uuid4().hex,
        current_run=current_run,
        current_plan=current_plan,
        current_clarification=review_clarification or global_clarification,
        current_decision=review_decision or global_decision,
        current_handoff=current_handoff,
        last_route=current_last_route,
        execution_active_run=execution_active_run,
        execution_current_plan=execution_current_plan,
        quarantined_items=tuple(quarantined),
        conflict_items=tuple(conflicts),
        notes=tuple(notes),
        preferred_state_scope=preferred_scope,
        is_conflict=bool(conflicts),
        conflict_code=conflict_code,
        conflict_message=conflict_message,
        conflict_artifacts=_freeze_mapping(
            {
                "state_conflict": {
                    "code": conflict_code,
                    "message": conflict_message,
                    "items": [item.to_dict() for item in conflicts],
                    "allowed_user_intents": list(_CONFLICT_ALLOWED_USER_INTENTS),
                    "allowed_internal_actions": list(_CONFLICT_ALLOWED_INTERNAL_ACTIONS),
                },
                "quarantined_items": [item.to_dict() for item in quarantined],
            }
            if conflicts or quarantined
            else {}
        ),
    )


def snapshot_state_conflict_artifacts(snapshot: ContextResolvedSnapshot) -> dict[str, Any]:
    return {
        "state_conflict": {
            "code": snapshot.conflict_code,
            "message": snapshot.conflict_message,
            "items": [item.to_dict() for item in snapshot.conflict_items],
            "allowed_user_intents": list(_CONFLICT_ALLOWED_USER_INTENTS),
            "allowed_internal_actions": list(_CONFLICT_ALLOWED_INTERNAL_ACTIONS),
        },
        "quarantined_items": [item.to_dict() for item in snapshot.quarantined_items],
    }


def _load_clarification(
    *,
    store: StateStore,
    scope: str,
    active_run: RunState | None,
    quarantined: list[QuarantinedStateItem],
) -> ClarificationState | None:
    payload, payload_error = _read_json_payload(store.current_clarification_path)
    if payload_error is not None:
        quarantined.append(
            _quarantined_item(
                store=store,
                path=store.current_clarification_path,
                state_kind="current_clarification",
                reason=payload_error,
                provenance_status="invalid_payload",
            )
        )
        return None
    if payload is None:
        return None
    phase = str(payload.get("phase") or "").strip()
    if not phase:
        quarantined.append(
            _quarantined_item(
                store=store,
                path=store.current_clarification_path,
                state_kind="current_clarification",
                reason="phase_missing",
                provenance_status="legacy_unknown",
            )
        )
        return None
    if not is_supported_phase(state_kind="current_clarification", phase=phase):
        quarantined.append(
            _quarantined_item(
                store=store,
                path=store.current_clarification_path,
                state_kind="current_clarification",
                reason="phase_unsupported",
                provenance_status="invalid_payload",
            )
        )
        return None
    clarification = ClarificationState.from_dict(payload)
    resume_context = _resume_context(payload)
    if phase == "analyze" and scope not in {"session", _PRIMARY_SCOPE}:
        quarantined.append(
            _quarantined_item(
                store=store,
                path=store.current_clarification_path,
                state_kind="current_clarification",
                reason="design_clarification_requires_session_scope",
                provenance_status="scope_mismatch",
            )
        )
        return None
    if phase == "develop":
        if scope not in {"global", _PRIMARY_SCOPE}:
            quarantined.append(
                _quarantined_item(
                    store=store,
                    path=store.current_clarification_path,
                    state_kind="current_clarification",
                    reason="develop_clarification_requires_global_scope",
                    provenance_status="scope_mismatch",
                )
            )
            return None
        resume_issue = develop_resume_context_issue(resume_context)
        if resume_issue is not None:
            quarantined.append(
                _quarantined_item(
                    store=store,
                    path=store.current_clarification_path,
                    state_kind="current_clarification",
                    reason=resume_issue,
                    provenance_status=_provenance_status_for_reason(resume_issue),
                )
            )
            return None
        provenance_reason = _develop_clarification_provenance_issue(
            clarification=clarification,
            resume_context=resume_context,
            active_run=active_run,
            store=store,
            scope=scope,
        )
        if provenance_reason is not None:
            quarantined.append(
                _quarantined_item(
                    store=store,
                    path=store.current_clarification_path,
                    state_kind="current_clarification",
                    reason=provenance_reason,
                    provenance_status=_provenance_status_for_reason(provenance_reason),
                )
            )
            return None
    return clarification


def _load_decision(
    *,
    store: StateStore,
    scope: str,
    active_run: RunState | None,
    quarantined: list[QuarantinedStateItem],
) -> DecisionState | None:
    payload, payload_error = _read_json_payload(store.current_decision_path)
    if payload_error is not None:
        quarantined.append(
            _quarantined_item(
                store=store,
                path=store.current_decision_path,
                state_kind="current_decision",
                reason=payload_error,
                provenance_status="invalid_payload",
            )
        )
        return None
    if payload is None:
        return None
    phase = str(payload.get("phase") or "").strip()
    if not phase:
        quarantined.append(
            _quarantined_item(
                store=store,
                path=store.current_decision_path,
                state_kind="current_decision",
                reason="phase_missing",
                provenance_status="legacy_unknown",
            )
        )
        return None
    if not is_supported_phase(state_kind="current_decision", phase=phase):
        quarantined.append(
            _quarantined_item(
                store=store,
                path=store.current_decision_path,
                state_kind="current_decision",
                reason="phase_unsupported",
                provenance_status="invalid_payload",
            )
        )
        return None
    decision = DecisionState.from_dict(payload)
    resume_context = _resume_context(payload)
    if phase == "design" and scope not in {"session", _PRIMARY_SCOPE}:
        quarantined.append(
            _quarantined_item(
                store=store,
                path=store.current_decision_path,
                state_kind="current_decision",
                reason="design_decision_requires_session_scope",
                provenance_status="scope_mismatch",
            )
        )
        return None
    if phase == "design":
        provenance_reason = _design_decision_provenance_issue(
            decision=decision,
            resume_context=resume_context,
            store=store,
            scope=scope,
        )
        if provenance_reason is not None:
            quarantined.append(
                _quarantined_item(
                    store=store,
                    path=store.current_decision_path,
                    state_kind="current_decision",
                    reason=provenance_reason,
                    provenance_status=_provenance_status_for_reason(provenance_reason),
                )
            )
            return None
    if phase in {"execution_gate", "develop"}:
        if scope not in {"global", _PRIMARY_SCOPE}:
            quarantined.append(
                _quarantined_item(
                    store=store,
                    path=store.current_decision_path,
                    state_kind="current_decision",
                    reason="execution_decision_requires_global_scope",
                    provenance_status="scope_mismatch",
                )
            )
            return None
        resume_issue = develop_resume_context_issue(resume_context)
        if resume_issue is not None:
            quarantined.append(
                _quarantined_item(
                    store=store,
                    path=store.current_decision_path,
                    state_kind="current_decision",
                    reason=resume_issue,
                    provenance_status=_provenance_status_for_reason(resume_issue),
                )
            )
            return None
        provenance_reason = _execution_decision_provenance_issue(
            decision=decision,
            resume_context=resume_context,
            active_run=active_run,
            store=store,
            scope=scope,
        )
        if provenance_reason is not None:
            quarantined.append(
                _quarantined_item(
                    store=store,
                    path=store.current_decision_path,
                    state_kind="current_decision",
                    reason=provenance_reason,
                    provenance_status=_provenance_status_for_reason(provenance_reason),
                )
            )
            return None
    return decision


def _resume_context(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    raw_resume_context = payload.get("resume_context")
    if not isinstance(raw_resume_context, Mapping):
        return {}
    return raw_resume_context


def _design_decision_provenance_issue(
    *,
    decision: DecisionState,
    resume_context: Mapping[str, Any],
    store: StateStore,
    scope: str,
) -> str | None:
    # Design checkpoints stay session-local. Their liveness is structural:
    # checkpoint identity must stay coherent and, when a real session exists,
    # the stamped owner_session_id must still match that review scope.
    checkpoint_id = _decision_checkpoint_id(decision=decision, resume_context=resume_context)
    if not checkpoint_id:
        return "design_decision_checkpoint_missing"
    if checkpoint_id != decision.decision_id:
        return "design_decision_checkpoint_mismatch"
    if scope != _PRIMARY_SCOPE and store.session_id:
        owner_session_id = str(resume_context.get("owner_session_id") or "").strip()
        if not owner_session_id:
            return "design_decision_owner_session_missing"
        if owner_session_id != store.session_id:
            return "design_decision_owner_session_mismatch"
    return None


def _execution_decision_provenance_issue(
    *,
    decision: DecisionState,
    resume_context: Mapping[str, Any],
    active_run: RunState | None,
    store: StateStore,
    scope: str,
) -> str | None:
    # Execution/develop checkpoints are not allowed to float freely. They only
    # stay live when their stamped owner provenance still matches the active run.
    if active_run is None:
        return "execution_decision_orphaned_from_active_run"

    checkpoint_id = _decision_checkpoint_id(decision=decision, resume_context=resume_context)
    if not checkpoint_id:
        return "execution_decision_checkpoint_missing"
    if checkpoint_id != decision.decision_id:
        return "execution_decision_checkpoint_mismatch"

    owner_run_id = str(resume_context.get("owner_run_id") or "").strip()
    if not owner_run_id:
        return "execution_decision_owner_run_missing"
    expected_owner_run_id = _expected_owner_run_id(active_run=active_run, scope=scope)
    if not expected_owner_run_id:
        return "execution_decision_active_run_owner_missing"
    if owner_run_id != expected_owner_run_id:
        return "execution_decision_owner_run_mismatch"

    owner_session_id = str(resume_context.get("owner_session_id") or "").strip()
    expected_owner_session_id = _expected_owner_session_id(active_run=active_run, store=store, scope=scope)
    if expected_owner_session_id:
        if not owner_session_id:
            return "execution_decision_owner_session_missing"
        if owner_session_id != expected_owner_session_id:
            return "execution_decision_owner_session_mismatch"

    if decision.phase == "execution_gate":
        gate = active_run.execution_gate
        if gate is None or gate.gate_status != "decision_required":
            return "execution_gate_decision_topology_disconnected"
        blocking_reason = str(gate.blocking_reason or "").strip()
        expected_reason = str(decision.trigger_reason or "").strip()
        if expected_reason and blocking_reason != expected_reason:
            return "execution_gate_decision_topology_disconnected"
    return None


def _develop_clarification_provenance_issue(
    *,
    clarification: ClarificationState,
    resume_context: Mapping[str, Any],
    active_run: RunState | None,
    store: StateStore,
    scope: str,
) -> str | None:
    # Develop clarifications ride on the execution chain, so we bind them to the
    # active run identity instead of adopting any matching-looking JSON blob.
    if active_run is None:
        return "develop_clarification_orphaned_from_active_run"

    checkpoint_id = str(resume_context.get("checkpoint_id") or "").strip()
    if not checkpoint_id:
        return "develop_clarification_checkpoint_missing"
    if checkpoint_id != clarification.clarification_id:
        return "develop_clarification_checkpoint_mismatch"

    owner_run_id = str(resume_context.get("owner_run_id") or "").strip()
    if not owner_run_id:
        return "develop_clarification_owner_run_missing"
    expected_owner_run_id = _expected_owner_run_id(active_run=active_run, scope=scope)
    if not expected_owner_run_id:
        return "develop_clarification_active_run_owner_missing"
    if owner_run_id != expected_owner_run_id:
        return "develop_clarification_owner_run_mismatch"

    owner_session_id = str(resume_context.get("owner_session_id") or "").strip()
    expected_owner_session_id = _expected_owner_session_id(active_run=active_run, store=store, scope=scope)
    if expected_owner_session_id:
        if not owner_session_id:
            return "develop_clarification_owner_session_missing"
        if owner_session_id != expected_owner_session_id:
            return "develop_clarification_owner_session_mismatch"

    return None


def _decision_checkpoint_id(*, decision: DecisionState, resume_context: Mapping[str, Any]) -> str:
    checkpoint_id = str(resume_context.get("checkpoint_id") or "").strip()
    if checkpoint_id:
        return checkpoint_id
    checkpoint = decision.checkpoint
    if checkpoint is None:
        return ""
    return str(checkpoint.checkpoint_id or "").strip()


def _expected_owner_run_id(*, active_run: RunState, scope: str) -> str:
    owner_run_id = str(active_run.owner_run_id or "").strip()
    if owner_run_id:
        return owner_run_id
    if scope == _PRIMARY_SCOPE:
        return str(active_run.run_id or "").strip()
    return ""


def _expected_owner_session_id(*, active_run: RunState, store: StateStore, scope: str) -> str:
    owner_session_id = str(active_run.owner_session_id or "").strip()
    if owner_session_id:
        return owner_session_id
    if scope == _PRIMARY_SCOPE:
        return str(store.session_id or "").strip()
    return ""


def _provenance_status_for_reason(reason: str) -> str:
    if reason.endswith("_missing"):
        return "provenance_missing"
    if reason.endswith("_mismatch") or "disconnected" in reason:
        return "provenance_mismatch"
    if reason.endswith("_orphaned_from_active_run"):
        return "orphaned"
    return "invalid_payload"


def _collect_run_handoff_conflicts(
    *,
    store: StateStore,
    scope: str,
    current_run: RunState | None,
    current_handoff: RuntimeHandoff | None,
    current_clarification: ClarificationState | None,
    current_decision: DecisionState | None,
) -> list[StateConflictDetail]:
    conflicts: list[StateConflictDetail] = []
    if current_run is not None and current_handoff is not None:
        run_resolution = str(current_run.resolution_id or "").strip()
        handoff_resolution = str(current_handoff.resolution_id or "").strip()
        if bool(run_resolution) != bool(handoff_resolution):
            conflicts.append(
                StateConflictDetail(
                    code="resolution_id_mixed_presence",
                    message="current_run and current_handoff do not agree on resolution_id presence",
                    path=store.relative_path(store.current_handoff_path),
                    state_scope=scope,
                )
            )
        elif run_resolution and handoff_resolution and run_resolution != handoff_resolution:
            conflicts.append(
                StateConflictDetail(
                    code="resolution_id_mismatch",
                    message="current_run and current_handoff were written by different resolution batches",
                    path=store.relative_path(store.current_handoff_path),
                    state_scope=scope,
                )
            )

    if current_handoff is None:
        return conflicts
    required_host_action = str(current_handoff.required_host_action or "").strip()
    if required_host_action == "resolve_state_conflict":
        return conflicts

    if current_run is not None:
        expected_action = _NEGOTIATION_RUN_STAGE_ACTIONS.get(current_run.stage)
        if expected_action and required_host_action != expected_action:
            conflicts.append(
                StateConflictDetail(
                    code="run_stage_handoff_mismatch",
                    message=f"run.stage={current_run.stage} conflicts with handoff.required_host_action={required_host_action}",
                    path=store.relative_path(store.current_handoff_path),
                    state_scope=scope,
                )
            )

    if required_host_action == "answer_questions" and current_clarification is None:
        conflicts.append(
            StateConflictDetail(
                code="clarification_missing_for_pending_handoff",
                message="Handoff requires clarification answers but no valid clarification is available",
                path=store.relative_path(store.current_handoff_path),
                state_scope=scope,
            )
        )
    if required_host_action == "confirm_decision" and current_decision is None:
        conflicts.append(
            StateConflictDetail(
                code="decision_missing_for_pending_handoff",
                message="Handoff requires a decision confirmation but no valid decision is available",
                path=store.relative_path(store.current_handoff_path),
                state_scope=scope,
            )
        )
    return conflicts


def _collect_pending_items(
    *,
    review_store: StateStore,
    global_store: StateStore,
    review_clarification: ClarificationState | None,
    review_decision: DecisionState | None,
    global_clarification: ClarificationState | None,
    global_decision: DecisionState | None,
) -> list[tuple[str, str]]:
    pending: list[tuple[str, str]] = []
    if review_clarification is not None and review_clarification.status in _CLARIFICATION_CONFLICT_STATUSES:
        pending.append(("current_clarification", review_store.relative_path(review_store.current_clarification_path)))
    if global_clarification is not None and global_clarification.status in _CLARIFICATION_CONFLICT_STATUSES:
        pending.append(("current_clarification", global_store.relative_path(global_store.current_clarification_path)))
    if review_decision is not None and review_decision.status in _DECISION_CONFLICT_STATUSES:
        pending.append(("current_decision", review_store.relative_path(review_store.current_decision_path)))
    if global_decision is not None and global_decision.status in _DECISION_CONFLICT_STATUSES:
        pending.append(("current_decision", global_store.relative_path(global_store.current_decision_path)))
    return pending


def _resolve_active_pending_context(
    *,
    review_store: StateStore,
    global_store: StateStore,
    review_run: RunState | None,
    global_run: RunState | None,
    review_handoff: RuntimeHandoff | None,
    global_handoff: RuntimeHandoff | None,
) -> tuple[str, StateStore | None, str, str]:
    if review_handoff is not None:
        required_action = str(review_handoff.required_host_action or "").strip()
        if required_action in _PENDING_HOST_ACTIONS:
            return (required_action, review_store, review_store.relative_path(review_store.current_handoff_path), "handoff")
        return ("", None, "", "")
    if global_handoff is not None:
        required_action = str(global_handoff.required_host_action or "").strip()
        if required_action in _PENDING_HOST_ACTIONS:
            return (required_action, global_store, global_store.relative_path(global_store.current_handoff_path), "handoff")
        return ("", None, "", "")
    if review_run is not None:
        required_action = _NEGOTIATION_RUN_STAGE_ACTIONS.get(review_run.stage, "")
        if required_action in _PENDING_HOST_ACTIONS:
            return (required_action, review_store, review_store.relative_path(review_store.current_run_path), "run")
    if global_run is not None:
        required_action = _NEGOTIATION_RUN_STAGE_ACTIONS.get(global_run.stage, "")
        if required_action in _PENDING_HOST_ACTIONS:
            return (required_action, global_store, global_store.relative_path(global_store.current_run_path), "run")
    return ("", None, "", "")


def _filter_pending_items_for_active_action(
    pending_items: list[tuple[str, str]],
    *,
    active_pending_action: str,
    review_store: StateStore,
    global_store: StateStore,
    review_decision: DecisionState | None,
    global_decision: DecisionState | None,
) -> list[tuple[str, str]]:
    if active_pending_action != "answer_questions":
        return pending_items

    filtered: list[tuple[str, str]] = []
    review_decision_path = review_store.relative_path(review_store.current_decision_path)
    global_decision_path = global_store.relative_path(global_store.current_decision_path)
    for kind, path in pending_items:
        if kind != "current_decision":
            filtered.append((kind, path))
            continue
        if review_decision is not None and review_decision.status == "confirmed" and path == review_decision_path:
            continue
        if global_decision is not None and global_decision.status == "confirmed" and path == global_decision_path:
            continue
        filtered.append((kind, path))
    return filtered


def _execution_confirm_review_checkpoint_conflict(
    *,
    active_pending_action: str,
    active_pending_store: StateStore | None,
    active_pending_path: str,
    review_clarification: ClarificationState | None,
    review_decision: DecisionState | None,
    global_clarification: ClarificationState | None,
    global_decision: DecisionState | None,
) -> StateConflictDetail | None:
    if active_pending_action != "confirm_execute" or active_pending_store is None:
        return None

    observed_kinds: set[str] = set()
    if review_clarification is not None and review_clarification.status in _CLARIFICATION_CONFLICT_STATUSES:
        observed_kinds.add("current_clarification")
    if global_clarification is not None and global_clarification.status in _CLARIFICATION_CONFLICT_STATUSES:
        observed_kinds.add("current_clarification")
    if review_decision is not None:
        observed_kinds.add("current_decision")
    if global_decision is not None:
        observed_kinds.add("current_decision")
    if not observed_kinds:
        return None

    observed = ",".join(sorted(observed_kinds))
    return StateConflictDetail(
        code="execution_confirm_review_checkpoint_conflict",
        message=f"execution confirmation cannot coexist with review checkpoint carriers [{observed}]",
        path=active_pending_path,
        state_scope=active_pending_store.scope,
    )


def _pending_checkpoint_handoff_mismatch(
    *,
    active_pending_action: str,
    active_pending_store: StateStore | None,
    active_pending_path: str,
    active_pending_source: str,
    pending_items: list[tuple[str, str]],
) -> StateConflictDetail | None:
    if active_pending_store is None or active_pending_source != "handoff" or not pending_items:
        return None

    expected_kinds = _PENDING_ACTION_EXPECTED_STATE_KINDS.get(active_pending_action)
    if expected_kinds is None:
        return None

    observed_kinds = {kind for kind, _path in pending_items}
    if observed_kinds.issubset(expected_kinds):
        return None

    expected = ",".join(sorted(expected_kinds))
    observed = ",".join(sorted(observed_kinds))
    return StateConflictDetail(
        code="pending_checkpoint_handoff_mismatch",
        message=(
            f"required_host_action={active_pending_action} expects [{expected}] "
            f"but observed pending checkpoints [{observed}]"
        ),
        path=active_pending_path,
        state_scope=active_pending_store.scope,
    )


def _rehydrate_handoff_state_conflict(
    *,
    store: StateStore,
    scope: str,
    current_handoff: RuntimeHandoff | None,
) -> list[StateConflictDetail]:
    if current_handoff is None:
        return []
    if str(current_handoff.required_host_action or "").strip() != "resolve_state_conflict":
        return []
    payload = current_handoff.artifacts.get("state_conflict")
    if not isinstance(payload, Mapping):
        return []
    code = str(payload.get("code") or "").strip()
    message = str(payload.get("message") or "").strip()
    if not code:
        return []
    return [
        StateConflictDetail(
            code=code,
            message=message or "A previously detected runtime state conflict still requires cleanup",
            path=store.relative_path(store.current_handoff_path),
            state_scope=scope,
        )
    ]


def _preferred_state_scope(*, global_run: RunState | None, global_handoff: RuntimeHandoff | None) -> str:
    if global_run is not None or global_handoff is not None:
        return "global"
    return "session"


def _should_ignore_legacy_global_review_state(
    *,
    current_run: RunState | None,
    current_plan: PlanArtifact | None,
    current_handoff: RuntimeHandoff | None,
) -> bool:
    if current_run is None or current_handoff is None:
        return False
    if current_plan is not None:
        return False
    if str(current_run.owner_session_id or "").strip():
        return False
    if str(current_run.owner_run_id or "").strip():
        return False
    if current_run.stage not in _NEGOTIATION_RUN_STAGE_ACTIONS:
        return False
    return str(current_handoff.required_host_action or "").strip() in _PENDING_HOST_ACTIONS


def _quarantined_item(
    *,
    store: StateStore,
    path: Path,
    state_kind: str,
    reason: str,
    provenance_status: str,
) -> QuarantinedStateItem:
    return QuarantinedStateItem(
        state_kind=state_kind,
        path=store.relative_path(path),
        reason=reason,
        provenance_status=provenance_status,
        state_scope=store.scope,
    )


def _read_json_payload(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return (None, None)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (None, "invalid_json")
    if not isinstance(payload, dict):
        return (None, "invalid_payload_shape")
    return (payload, None)




def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            frozen[str(key)] = _freeze_mapping(item)
        elif isinstance(item, list):
            frozen[str(key)] = tuple(item)
        else:
            frozen[str(key)] = item
    return MappingProxyType(frozen)
