#!/usr/bin/env python3
"""Internal helper for host-side plan registry inspection and priority confirmation.

This helper does not replace the default Sopify runtime entry. Hosts may call
it to inspect `.sopify-skills/plan/_registry.yaml` or persist a user-confirmed
priority. It never switches `current_plan`.
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
from runtime.plan_registry import PlanRegistryError, confirm_plan_priority, inspect_plan_registry


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the plan registry helper."""
    parser = argparse.ArgumentParser(description="Inspect or update Sopify plan registry priority state.")
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

    inspect_parser = subparsers.add_parser("inspect", help="Read the current registry contract.")
    inspect_parser.add_argument("--plan-id", default=None, help="Optional target plan id.")
    inspect_parser.add_argument(
        "--request-text",
        default="",
        help="Optional request text used to refresh read-only suggested priority.",
    )

    confirm_parser = subparsers.add_parser("confirm-priority", help="Persist a user-confirmed plan priority.")
    confirm_parser.add_argument("--plan-id", required=True, help="Target plan id.")
    confirm_parser.add_argument("--priority", required=True, choices=("p1", "p2", "p3"))
    confirm_parser.add_argument("--note", default=None, help="Optional confirmation note.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace_root = Path(args.workspace_root).resolve()

    try:
        config = load_runtime_config(workspace_root, global_config_path=args.global_config_path)
        if args.command == "inspect":
            payload = inspect_plan_registry(
                config=config,
                plan_id=args.plan_id,
                request_text=args.request_text,
            )
        elif args.command == "confirm-priority":
            payload = _confirm_priority(
                config=config,
                plan_id=args.plan_id,
                priority=args.priority,
                note=args.note,
            )
        else:
            raise ValueError(f"Unsupported command: {args.command}")
    except (ConfigError, PlanRegistryError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _confirm_priority(*, config, plan_id: str, priority: str, note: str | None) -> dict[str, object]:
    confirmed = confirm_plan_priority(
        config=config,
        plan_id=plan_id,
        priority=priority,
        note=note,
    )
    inspected = inspect_plan_registry(config=config, plan_id=plan_id)
    governance = dict(confirmed.get("governance") or {})
    return {
        "status": "written",
        "plan_id": plan_id,
        "registry_path": inspected["registry_path"],
        "confirmed_priority": governance.get("priority"),
        "priority_source": governance.get("priority_source"),
        "priority_confirmed_at": governance.get("priority_confirmed_at"),
        "selected_plan": inspected["selected_plan"],
        "current_plan": inspected["current_plan"],
        "execution_truth": inspected["execution_truth"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
