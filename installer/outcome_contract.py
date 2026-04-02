"""Shared outcome-contract helpers for installer/preflight diagnostics."""

from __future__ import annotations

from typing import Any, Mapping

ACTION_CONTINUE = "continue"
ACTION_WARN = "warn"
ACTION_CONFIRM = "confirm"
ACTION_FAIL_CLOSED = "fail_closed"

PRIMARY_CODE_STUB_SELECTED = "stub_selected"
PRIMARY_CODE_STUB_INVALID = "stub_invalid"
PRIMARY_CODE_GLOBAL_BUNDLE_MISSING = "global_bundle_missing"
PRIMARY_CODE_GLOBAL_BUNDLE_INCOMPATIBLE = "global_bundle_incompatible"
PRIMARY_CODE_GLOBAL_INDEX_CORRUPTED = "global_index_corrupted"
PRIMARY_CODE_LEGACY_FALLBACK_SELECTED = "legacy_fallback_selected"
PRIMARY_CODE_HOST_MISMATCH = "host_mismatch"
PRIMARY_CODE_INGRESS_CONTRACT_INVALID = "ingress_contract_invalid"
PRIMARY_CODE_ROOT_CONFIRM_REQUIRED = "root_confirm_required"
PRIMARY_CODE_READONLY = "readonly"
PRIMARY_CODE_NON_INTERACTIVE = "non_interactive"

DIAGNOSTIC_NON_GIT_WORKSPACE = "non_git_workspace"
DIAGNOSTIC_IGNORE_WRITTEN = "ignore_written"
DIAGNOSTIC_ROOT_REUSE_ANCESTOR_MARKER = "root_reuse_ancestor_marker"
DIAGNOSTIC_INVALID_ANCESTOR_MARKER = "invalid_ancestor_marker"
DIAGNOSTIC_LEGACY_FALLBACK_BLOCKED = "legacy_fallback_blocked"

_PRIMARY_CODE_BY_REASON = {
    "STUB_SELECTED": PRIMARY_CODE_STUB_SELECTED,
    "STUB_INVALID": PRIMARY_CODE_STUB_INVALID,
    "GLOBAL_BUNDLE_MISSING": PRIMARY_CODE_GLOBAL_BUNDLE_MISSING,
    "GLOBAL_BUNDLE_INCOMPATIBLE": PRIMARY_CODE_GLOBAL_BUNDLE_INCOMPATIBLE,
    "GLOBAL_INDEX_CORRUPTED": PRIMARY_CODE_GLOBAL_INDEX_CORRUPTED,
    "LEGACY_FALLBACK_SELECTED": PRIMARY_CODE_LEGACY_FALLBACK_SELECTED,
    "HOST_MISMATCH": PRIMARY_CODE_HOST_MISMATCH,
    "INGRESS_CONTRACT_INVALID": PRIMARY_CODE_INGRESS_CONTRACT_INVALID,
    "ROOT_CONFIRM_REQUIRED": PRIMARY_CODE_ROOT_CONFIRM_REQUIRED,
    "READONLY": PRIMARY_CODE_READONLY,
    "NON_INTERACTIVE": PRIMARY_CODE_NON_INTERACTIVE,
}

_ACTION_LEVEL_BY_PRIMARY = {
    PRIMARY_CODE_STUB_SELECTED: ACTION_CONTINUE,
    PRIMARY_CODE_STUB_INVALID: ACTION_FAIL_CLOSED,
    PRIMARY_CODE_GLOBAL_BUNDLE_MISSING: ACTION_FAIL_CLOSED,
    PRIMARY_CODE_GLOBAL_BUNDLE_INCOMPATIBLE: ACTION_FAIL_CLOSED,
    PRIMARY_CODE_GLOBAL_INDEX_CORRUPTED: ACTION_FAIL_CLOSED,
    PRIMARY_CODE_LEGACY_FALLBACK_SELECTED: ACTION_WARN,
    PRIMARY_CODE_HOST_MISMATCH: ACTION_FAIL_CLOSED,
    PRIMARY_CODE_INGRESS_CONTRACT_INVALID: ACTION_FAIL_CLOSED,
    PRIMARY_CODE_ROOT_CONFIRM_REQUIRED: ACTION_CONFIRM,
    PRIMARY_CODE_READONLY: ACTION_FAIL_CLOSED,
    PRIMARY_CODE_NON_INTERACTIVE: ACTION_FAIL_CLOSED,
}

_ACTION_LEVEL_BY_REASON = {
    "BRAKE_LAYER_BLOCKED": ACTION_FAIL_CLOSED,
    "FIRST_WRITE_NOT_AUTHORIZED": ACTION_FAIL_CLOSED,
    "COMMAND_NOT_BOOTSTRAP_AUTHORIZED": ACTION_FAIL_CLOSED,
    "CONFIRM_BOOTSTRAP_REQUIRED": ACTION_CONFIRM,
}

_DIAGNOSTIC_IDENTIFIER_MAP = {
    "NON_GIT_WORKSPACE": DIAGNOSTIC_NON_GIT_WORKSPACE,
    "ROOT_REUSE_ANCESTOR_MARKER": DIAGNOSTIC_ROOT_REUSE_ANCESTOR_MARKER,
    "INVALID_ANCESTOR_MARKER": DIAGNOSTIC_INVALID_ANCESTOR_MARKER,
    "LEGACY_FALLBACK_BLOCKED": DIAGNOSTIC_LEGACY_FALLBACK_BLOCKED,
}


def primary_code_for_reason(reason_code: str | None) -> str | None:
    normalized = str(reason_code or "").strip().upper()
    if not normalized:
        return None
    return _PRIMARY_CODE_BY_REASON.get(normalized)


def action_level_for(reason_code: str | None, *, primary_code: str | None = None) -> str | None:
    normalized_primary = str(primary_code or "").strip()
    if normalized_primary:
        return _ACTION_LEVEL_BY_PRIMARY.get(normalized_primary)
    normalized_reason = str(reason_code or "").strip().upper()
    if normalized_reason in _ACTION_LEVEL_BY_REASON:
        return _ACTION_LEVEL_BY_REASON[normalized_reason]
    fallback_primary = primary_code_for_reason(normalized_reason)
    if fallback_primary is None:
        return None
    return _ACTION_LEVEL_BY_PRIMARY.get(fallback_primary)


def annotate_outcome_payload(
    payload: dict[str, Any],
    *,
    reason_code: str | None = None,
    message_hint: str | None = None,
) -> dict[str, Any]:
    effective_reason = str(reason_code or payload.get("reason_code") or "").strip()
    primary_code = primary_code_for_reason(effective_reason)
    action_level = action_level_for(effective_reason, primary_code=primary_code)
    if primary_code:
        payload.setdefault("primary_code", primary_code)
    if action_level:
        payload.setdefault("action_level", action_level)
    normalized_hint = str(message_hint or payload.get("message_hint") or "").strip()
    if normalized_hint:
        payload.setdefault("message_hint", normalized_hint)
    return payload


def render_outcome_summary(payload: Mapping[str, object]) -> str:
    primary_code = str(payload.get("primary_code") or "").strip()
    action_level = str(payload.get("action_level") or "").strip()
    if not primary_code and not action_level:
        return ""
    if primary_code and action_level:
        return f"{primary_code} [{action_level}]"
    return primary_code or action_level


def normalize_diagnostic_identifier(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    return _DIAGNOSTIC_IDENTIFIER_MAP.get(normalized.upper())


def diagnostic_identifiers_from_evidence(evidence: object) -> tuple[str, ...]:
    diagnostics: list[str] = []
    values: tuple[Any, ...]
    if isinstance(evidence, (list, tuple)):
        values = tuple(evidence)
    else:
        values = ()
    for item in values:
        identifier = normalize_diagnostic_identifier(str(item or "").strip())
        if identifier and identifier not in diagnostics:
            diagnostics.append(identifier)
    return tuple(diagnostics)
