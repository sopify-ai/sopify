#!/usr/bin/env python3
"""Plan-only helper for repo-local Sopify runtime."""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import json

from runtime.cli import build_runtime_parser
from runtime.config import ConfigError, load_runtime_config
from runtime.output import render_runtime_error, render_runtime_output
from runtime.plan_orchestrator import PlanOrchestratorError, run_plan_loop


def main(argv: list[str] | None = None) -> int:
    parser = build_runtime_parser(
        description="Run the repo-local Sopify planning orchestrator for the `~go plan` path.",
        request_help="Planning request text, with or without the `~go plan` prefix.",
    )
    parser.add_argument(
        "--no-bridge-loop",
        action="store_true",
        help="Disable automatic clarification/decision bridge consumption and run a single planning pass.",
    )
    args = parser.parse_args(argv)
    workspace_root = Path(args.workspace_root).resolve()

    try:
        orchestrated = run_plan_loop(
            " ".join(args.request),
            workspace_root=workspace_root,
            global_config_path=args.global_config_path,
            bridge_loop=not args.no_bridge_loop,
        )
    except (PlanOrchestratorError, ValueError, ConfigError) as exc:
        config = None
        try:
            config = load_runtime_config(workspace_root, global_config_path=args.global_config_path)
        except Exception:
            config = None
        print(
            render_runtime_error(
                str(exc),
                brand=config.brand if config is not None else "sopify-ai",
                language=config.language if config is not None else "zh-CN",
                title_color=config.title_color if config is not None else "none",
                use_color=not args.no_color,
            )
        )
        return 1

    config = load_runtime_config(workspace_root, global_config_path=args.global_config_path)
    result = orchestrated.runtime_result
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(
            render_runtime_output(
                result,
                brand=config.brand,
                language=config.language,
                title_color=config.title_color,
                use_color=not args.no_color,
            )
        )
    return orchestrated.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
