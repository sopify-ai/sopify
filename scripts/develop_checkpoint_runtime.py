#!/usr/bin/env python3
"""Internal helper for develop-stage checkpoint callbacks.

Hosts may call this helper only after runtime already handed control back with
`current_handoff.json.required_host_action == continue_host_develop`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.config import ConfigError, load_runtime_config
from runtime.develop_checkpoint import (
    DevelopCheckpointError,
    inspect_develop_checkpoint_context,
    submit_develop_checkpoint,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the internal develop checkpoint helper."""
    parser = argparse.ArgumentParser(description="Inspect or create a Sopify develop-stage checkpoint callback.")
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Target workspace root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--global-config-path",
        default=None,
        help="Optional override for the global sopify config path.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect", help="Inspect whether the current workspace is ready for a develop callback.")

    submit_parser = subparsers.add_parser("submit", help="Write a structured develop callback payload.")
    submit_parser.add_argument("--payload-json", required=True, help="Structured develop callback payload as a JSON object.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace_root = Path(args.workspace_root).resolve()

    try:
        config = load_runtime_config(workspace_root, global_config_path=args.global_config_path)
        if args.command == "inspect":
            payload = inspect_develop_checkpoint_context(config=config)
        else:
            payload = _submit_callback(config=config, payload_json=args.payload_json)
    except (ConfigError, DevelopCheckpointError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _submit_callback(*, config, payload_json: str) -> dict[str, object]:
    raw_payload = json.loads(payload_json)
    if not isinstance(raw_payload, dict):
        raise ValueError("payload-json must decode to an object")

    submission = submit_develop_checkpoint(raw_payload, config=config)
    checkpoint_file = (
        ".sopify-skills/state/current_decision.json"
        if submission.request.checkpoint_kind == "decision"
        else ".sopify-skills/state/current_clarification.json"
    )
    return {
        "status": "written",
        "checkpoint_kind": submission.request.checkpoint_kind,
        "checkpoint_id": submission.request.checkpoint_id,
        "required_host_action": submission.handoff.required_host_action,
        "route_name": submission.route.route_name,
        "checkpoint_file": checkpoint_file,
        "handoff_file": ".sopify-skills/state/current_handoff.json",
        "resume_after": submission.request.resume_context.get("resume_after")
        if isinstance(submission.request.resume_context, dict)
        else None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
