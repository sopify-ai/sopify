"""Text rendering for runtime-gate contracts."""

from __future__ import annotations

from typing import Any, Mapping

try:
    from installer.outcome_contract import render_outcome_summary
except ModuleNotFoundError as exc:
    if not str(exc.name or "").startswith("installer"):
        raise

    def render_outcome_summary(payload: Mapping[str, object]) -> str:
        primary_code = str(payload.get("primary_code") or "").strip()
        action_level = str(payload.get("action_level") or "").strip()
        if not primary_code and not action_level:
            return ""
        if primary_code and action_level:
            return f"{primary_code} [{action_level}]"
        return primary_code or action_level

_HINTS = {
    "stub_selected": "Selected global bundle is ready for this workspace.",
    "stub_invalid": "Repair or recreate `.sopify-runtime/manifest.json`, then retry.",
    "global_bundle_missing": "Refresh the installed payload because the selected global bundle is missing.",
    "global_bundle_incompatible": "Refresh the installed payload because the selected global bundle is incomplete or incompatible.",
    "global_index_corrupted": "Refresh the installed payload because the global bundle index is invalid or inconsistent.",
    "legacy_fallback_selected": "The workspace is still running through the legacy bundle layout; refresh the payload to migrate.",
    "host_mismatch": "Use the matching payload_root for this host, or omit host_id.",
    "ingress_contract_invalid": "Fix the invalid ingress arguments and rerun runtime_gate.",
    "root_confirm_required": "Choose an activation_root and rerun the same gate request.",
    "readonly": "Fix write permissions for the target workspace before retrying.",
    "non_interactive": "Open an interactive session before enabling Sopify here.",
}

_FIELD_HINTS = {
    "activation_root": {
        "missing": "Provide an activation_root.",
        "invalid_value": "Use a valid activation_root value.",
        "invalid_path": "Use a normalized activation_root path.",
        "not_found": "Point activation_root to an existing directory.",
        "unreadable": "Ensure activation_root can be read and entered as a directory.",
    },
    "host_id": {
        "missing": "Provide host_id only when you need audit validation.",
        "invalid_value": "Use one of the supported host ids.",
        "invalid_path": "Remove path-like content from host_id.",
        "not_found": "Use an installed host payload or omit host_id.",
        "unreadable": "Use a readable host payload selection.",
    },
    "payload_root": {
        "missing": "Pass payload_root explicitly when host selection is ambiguous.",
        "invalid_value": "Use a valid payload_root.",
        "invalid_path": "Use a normalized payload_root path.",
        "not_found": "Point payload_root to an existing Sopify payload directory.",
        "unreadable": "Ensure payload_root contains a readable payload-manifest.json.",
    },
}


def render_gate_text(payload: Mapping[str, Any]) -> str:
    status = str(payload.get("status") or "error")
    allowed_response_mode = str(payload.get("allowed_response_mode") or "error_visible_retry")
    runtime = payload.get("runtime") if isinstance(payload.get("runtime"), Mapping) else {}
    preflight = payload.get("preflight") if isinstance(payload.get("preflight"), Mapping) else {}
    lines = [
        "Sopify runtime gate:",
        f"  status: {status}",
        f"  allowed_response_mode: {allowed_response_mode}",
    ]
    if runtime:
        route_name = str(runtime.get("route_name") or "").strip()
        reason = str(runtime.get("reason") or "").strip()
        if route_name:
            lines.append(f"  route: {route_name}")
        if reason:
            lines.append(f"  reason: {reason}")
    if preflight:
        reason_code = str(preflight.get("reason_code") or "").strip()
        if reason_code:
            lines.append(f"  preflight_reason: {reason_code}")
        summary = render_outcome_summary(preflight)
        if summary:
            lines.append(f"  preflight_outcome: {summary}")
        for detail in _render_preflight_details(preflight):
            lines.append(f"  {detail}")
    message = str(payload.get("message") or "").strip()
    if message:
        lines.append(f"  message: {message}")
    return "\n".join(lines)


def _render_preflight_details(preflight: Mapping[str, Any]) -> tuple[str, ...]:
    primary_code = str(preflight.get("primary_code") or "").strip()
    evidence = preflight.get("evidence")
    lines: list[str] = []
    if primary_code == "ingress_contract_invalid" and isinstance(evidence, Mapping):
        violations = evidence.get("violations")
        if isinstance(violations, list):
            for item in violations:
                if not isinstance(item, Mapping):
                    continue
                field_name = str(item.get("field") or "unknown")
                error_kind = str(item.get("error_kind") or "invalid_value")
                actual_kind = str(item.get("actual_kind") or "").strip()
                hint = _FIELD_HINTS.get(field_name, {}).get(error_kind, "Fix this field and retry.")
                detail = f"{field_name}: {error_kind}"
                if actual_kind:
                    detail += f" ({actual_kind})"
                lines.append(detail)
                lines.append(f"hint: {hint}")
        return tuple(lines)
    if primary_code == "host_mismatch" and isinstance(evidence, Mapping):
        requested_host_id = str(evidence.get("requested_host_id") or "").strip()
        selected_host_id = str(evidence.get("selected_host_id") or "").strip()
        selection_source = str(evidence.get("selection_source") or "").strip()
        if requested_host_id:
            lines.append(f"requested_host_id: {requested_host_id}")
        if selected_host_id:
            lines.append(f"selected_host_id: {selected_host_id}")
        if selection_source:
            lines.append(f"selection_source: {selection_source}")
    hint = _HINTS.get(primary_code)
    if hint:
        lines.append(f"hint: {hint}")
    return tuple(lines)
