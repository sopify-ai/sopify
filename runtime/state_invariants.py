"""Domain-level validators for runtime checkpoint state writes."""

from __future__ import annotations

from dataclasses import replace

from .models import RunState, RuntimeHandoff

# Keep this whitelist explicit so paired-write scope cannot quietly spread.
HOST_FACING_TRUTH_WRITE_KINDS = (
    "engine_runtime_handoff",
    "promotion_global_execution",
    "develop_callback",
)
ALLOWED_PHASES_BY_STATE_KIND = {
    "current_clarification": frozenset({"analyze", "develop"}),
    "current_decision": frozenset({"design", "execution_gate", "develop"}),
}


class InvariantViolationError(ValueError):
    """Raised when runtime state writers violate a frozen Hotfix contract."""


def validate_phase(*, state_kind: str, phase: str) -> str:
    normalized = str(phase or "").strip()
    if not normalized:
        raise InvariantViolationError(f"{state_kind} writes must include a non-empty phase")
    allowed = ALLOWED_PHASES_BY_STATE_KIND.get(state_kind)
    if allowed is None or normalized in allowed:
        return normalized
    allowed_values = ", ".join(sorted(allowed))
    raise InvariantViolationError(f"{state_kind} phase must be one of: {allowed_values}; got {normalized}")


def is_supported_phase(*, state_kind: str, phase: str) -> bool:
    normalized = str(phase or "").strip()
    allowed = ALLOWED_PHASES_BY_STATE_KIND.get(state_kind)
    if allowed is None:
        return bool(normalized)
    return normalized in allowed


def validate_host_facing_truth_write_kind(truth_kind: str) -> str:
    normalized = str(truth_kind or "").strip()
    if normalized in HOST_FACING_TRUTH_WRITE_KINDS:
        return normalized
    allowed = ", ".join(HOST_FACING_TRUTH_WRITE_KINDS)
    raise InvariantViolationError(
        f"paired host-facing truth writes are restricted to: {allowed}; got {normalized or '<missing>'}"
    )


def stamp_run_resolution_id(run_state: RunState, *, resolution_id: str) -> RunState:
    normalized = validate_resolution_id(resolution_id)
    return replace(run_state, resolution_id=normalized)


def stamp_handoff_resolution_id(
    handoff: RuntimeHandoff,
    *,
    resolution_id: str,
    truth_kind: str | None = None,
) -> RuntimeHandoff:
    normalized = validate_resolution_id(resolution_id)
    observability = dict(handoff.observability)
    observability["resolution_id"] = normalized
    if truth_kind:
        observability["host_truth_write_kind"] = truth_kind
        observability["host_truth_paired_write"] = True
    return replace(handoff, resolution_id=normalized, observability=observability)


def validate_paired_host_truth_write(
    *,
    run_state: RunState,
    handoff: RuntimeHandoff,
    resolution_id: str,
    truth_kind: str,
) -> str:
    normalized_resolution_id = validate_resolution_id(resolution_id)
    normalized_truth_kind = validate_host_facing_truth_write_kind(truth_kind)
    if str(run_state.run_id or "").strip() != str(handoff.run_id or "").strip():
        raise InvariantViolationError(
            "paired host-facing truth write requires current_run.run_id to match current_handoff.run_id"
        )
    return normalized_truth_kind


def validate_resolution_id(resolution_id: str) -> str:
    normalized = str(resolution_id or "").strip()
    if normalized:
        return normalized
    raise InvariantViolationError("paired host-facing truth writes require a non-empty resolution_id")
