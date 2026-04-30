#!/usr/bin/env python3
"""Default repo-local entry for routing raw user input through Sopify runtime."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.cli import build_runtime_parser, execute_runtime_cli
from runtime.config import ConfigError, load_runtime_config
from runtime.entry_guard import DIRECT_EDIT_BLOCKED_RUNTIME_REQUIRED_REASON_CODE
from runtime.gate import CURRENT_GATE_RECEIPT_FILENAME, ERROR_VISIBLE_RETRY, GATE_SCHEMA_VERSION, write_gate_receipt
from runtime.output import render_runtime_error
from runtime.router import match_runtime_first_guard
from runtime.state import iso_now, stable_request_sha1, summarize_request_text

DIRECT_ENTRY_BLOCKED_ERROR_CODE = "runtime_gate_required"
_FINALIZE_ALIAS_RE = re.compile(r"^~go\s+finalize(?:\s+.+)?$", re.IGNORECASE)


def _render_direct_entry_block(
    *,
    request: str,
    workspace_root: Path,
    global_config_path: str | None,
    no_color: bool,
    as_json: bool,
    guard: dict[str, str],
) -> int:
    message = (
        "Direct raw-request entry is blocked for runtime-first traffic. "
        "Use `scripts/runtime_gate.py enter --workspace-root <cwd> --request \"<raw user request>\"` first, "
        "or rerun with `--allow-direct-entry` for local debug only. "
        f"[reason_code={DIRECT_EDIT_BLOCKED_RUNTIME_REQUIRED_REASON_CODE}, "
        f"guard_kind={guard.get('guard_kind', '<unknown>')}, request={request}]"
    )
    config = None
    try:
        config = load_runtime_config(workspace_root, global_config_path=global_config_path)
    except ConfigError:
        config = None

    receipt_path = (
        config.state_dir / CURRENT_GATE_RECEIPT_FILENAME
        if config is not None
        else workspace_root / ".sopify-skills" / "state" / CURRENT_GATE_RECEIPT_FILENAME
    )
    contract = {
        "schema_version": GATE_SCHEMA_VERSION,
        "status": "error",
        "gate_passed": False,
        "workspace_root": str(workspace_root),
        "preflight": {},
        "preferences": {
            "status": "missing",
            "injected": False,
        },
        "runtime": {
            "route_name": "workflow",
            "reason": guard.get("reason"),
        },
        "handoff": {},
        "trigger_evidence": {
            "entry_guard_reason_code": DIRECT_EDIT_BLOCKED_RUNTIME_REQUIRED_REASON_CODE,
            "direct_edit_guard_kind": guard.get("guard_kind"),
            "direct_edit_guard_trigger": guard.get("reason"),
        },
        "observability": {
            "receipt_kind": "direct_entry_block",
            "ingress_mode": "default_runtime_entry_blocked",
            "written_at": iso_now(),
            "request_excerpt": summarize_request_text(request),
            "request_sha1": stable_request_sha1(request),
            "guard_kind": guard.get("guard_kind"),
        },
        "allowed_response_mode": ERROR_VISIBLE_RETRY,
        "evidence": {
            "manifest_found": (workspace_root / ".sopify-runtime" / "manifest.json").is_file(),
            "handoff_found": False,
            "strict_runtime_entry": False,
            "handoff_source_kind": "missing",
            "current_request_produced_handoff": False,
            "persisted_handoff_matches_current_request": False,
        },
        "error_code": DIRECT_ENTRY_BLOCKED_ERROR_CODE,
        "message": message,
        "required_entry": "scripts/runtime_gate.py",
        "required_subcommand": "enter",
        "debug_bypass_flag": "--allow-direct-entry",
        "entry_guard_reason_code": DIRECT_EDIT_BLOCKED_RUNTIME_REQUIRED_REASON_CODE,
        "receipt_path": str(receipt_path),
    }
    write_gate_receipt(receipt_path, contract)
    if as_json:
        print(json.dumps(contract, ensure_ascii=False, indent=2))
        return 2

    print(
        render_runtime_error(
            message,
            brand=config.brand if config is not None else "evidentloop",
            language=config.language if config is not None else "zh-CN",
            title_color=config.title_color if config is not None else "none",
            use_color=not no_color,
        )
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = build_runtime_parser(
        description="Run the default repo-local Sopify runtime entry for raw user input.",
        request_help="Raw user input to route through Sopify runtime.",
    )
    parser.add_argument(
        "--allow-direct-entry",
        action="store_true",
        help="Bypass runtime-first miswire protection for local debug only.",
    )
    args = parser.parse_args(argv)
    request = " ".join(args.request)
    guard = (
        {
            "guard_kind": "side_effecting_command_alias",
            "reason": "~go finalize must be mapped by runtime gate",
        }
        if _FINALIZE_ALIAS_RE.match(request.strip())
        else match_runtime_first_guard(request)
    )
    workspace_root = Path(args.workspace_root).resolve()
    if guard is not None and not args.allow_direct_entry:
        return _render_direct_entry_block(
            request=request,
            workspace_root=workspace_root,
            global_config_path=args.global_config_path,
            no_color=args.no_color,
            as_json=args.json,
            guard=guard,
        )
    return execute_runtime_cli(
        request,
        workspace_root=workspace_root,
        global_config_path=args.global_config_path,
        as_json=args.json,
        no_color=args.no_color,
    )


if __name__ == "__main__":
    raise SystemExit(main())
