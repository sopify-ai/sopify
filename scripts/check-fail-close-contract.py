#!/usr/bin/env python3
"""Offline validation for the frozen fail-close decision table asset."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.decision_tables import DecisionTableError, load_default_decision_tables
from runtime.failure_recovery import (
    LEGACY_FAILURE_RECOVERY_TABLE_PATH,
    FailureRecoveryError,
    assert_failure_recovery_tables_consistent,
    evaluate_case_matrix,
    load_default_failure_recovery_table,
    load_failure_recovery_case_matrix,
    load_failure_recovery_table,
)
from runtime.message_templates import render_host_message

DEFAULT_CASE_MATRIX_PATH = REPO_ROOT / "tests" / "fixtures" / "fail_close_case_matrix.yaml"
DEFAULT_PYTEST_ENTRY_PATH = REPO_ROOT / "tests" / "pytest_entries" / "fail_close_contract_entry.py"
_TEMPLATE_SMOKE_VARIABLES = {
    "required_host_action_label": "当前 checkpoint",
    "checkpoint_kind_label": "plan package",
    "checkpoint_id": "checkpoint-smoke",
    "plan_id": "plan-smoke",
    "plan_path": ".sopify-skills/plan/smoke",
    "resume_target_kind": "checkpoint",
    "truth_status": "contract_invalid",
    "primary_failure_type": "truth_layer_contract_invalid",
    "unresolved_outcome_family": "fail_closed",
    "analysis_summary": "smoke summary",
    "risk_level": "medium",
    "key_risk": "contract drift",
    "missing_facts_summary": "missing scope",
    "decision_question": "继续吗",
    "escape_hatch_hint": "执行恢复动作",
    "contract_fix_hint": "修复契约",
    "rephrase_hint": "换一种更明确的说法",
    "safe_retry_hint": "修复后重试",
}


def _is_missing_default_case_matrix(case_matrix_arg: str, *, error_text: str) -> bool:
    if "Fail-close case matrix not found" not in error_text:
        return False
    try:
        requested_path = Path(case_matrix_arg).resolve()
    except OSError:
        return False
    return requested_path == DEFAULT_CASE_MATRIX_PATH.resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a frozen fail-close decision table asset.")
    parser.add_argument(
        "--asset",
        default=None,
        help="Optional asset path. Defaults to the repository-default decision table asset.",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="Optional schema path. Defaults to the repository-default decision table schema asset.",
    )
    parser.add_argument(
        "--recovery-asset",
        default=None,
        help="Optional failure recovery asset path. Defaults to the repository-default recovery asset.",
    )
    parser.add_argument(
        "--recovery-schema",
        default=None,
        help="Optional failure recovery schema path. Defaults to the repository-default recovery schema asset.",
    )
    parser.add_argument(
        "--case-matrix",
        default=str(DEFAULT_CASE_MATRIX_PATH),
        help="Optional fail-close case matrix path. Defaults to the repository-default case matrix.",
    )
    parser.add_argument(
        "--runner",
        choices=("auto", "native", "pytest"),
        default="auto",
        help="Validation runner. auto prefers pytest parametrize when available, then falls back to native.",
    )
    parser.add_argument(
        "--pytest-entry",
        default=str(DEFAULT_PYTEST_ENTRY_PATH),
        help="Pytest entry path for matrix-driven contract checks.",
    )
    return parser


def _resolve_runner(preferred: str) -> tuple[str, str | None]:
    if preferred == "native":
        return "native", None
    if preferred == "pytest":
        return "pytest", None
    if importlib.util.find_spec("pytest") is not None:
        return "pytest", None
    return "native", "pytest_not_installed"


def _load_and_evaluate_contracts(
    args: argparse.Namespace,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], list[dict[str, object]]]:
    tables, recovery_table, case_matrix = _load_contract_assets(args)
    results = evaluate_case_matrix(
        case_matrix,
        decision_tables=tables,
        recovery_table=recovery_table,
    )
    return tables, recovery_table, case_matrix, results


def _load_contract_assets(
    args: argparse.Namespace,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    if args.asset:
        from runtime.decision_tables import load_decision_tables

        tables = load_decision_tables(args.asset, schema_path=args.schema)
    else:
        tables = load_default_decision_tables(schema_path=args.schema)

    if args.recovery_asset:
        recovery_table = load_failure_recovery_table(
            args.recovery_asset,
            schema_path=args.recovery_schema,
            decision_tables_path=args.asset,
        )
    else:
        recovery_table = load_default_failure_recovery_table(
            schema_path=args.recovery_schema,
            decision_tables_path=args.asset,
        )

    case_matrix = load_failure_recovery_case_matrix(
        args.case_matrix,
        schema_path=args.recovery_schema,
    )
    return tables, recovery_table, case_matrix


def _validate_legacy_recovery_snapshot_consistency(args: argparse.Namespace) -> None:
    if args.asset or args.recovery_asset:
        return
    legacy_recovery_table = load_failure_recovery_table(
        LEGACY_FAILURE_RECOVERY_TABLE_PATH,
        schema_path=args.recovery_schema,
    )
    embedded_recovery_table = load_default_failure_recovery_table(
        schema_path=args.recovery_schema,
    )
    assert_failure_recovery_tables_consistent(
        embedded_recovery_table,
        legacy_recovery_table,
    )


def _run_pytest_entry(args: argparse.Namespace) -> tuple[int, str]:
    entry_path = Path(args.pytest_entry).resolve()
    if not entry_path.is_file():
        raise FailureRecoveryError(f"Pytest entry not found: {entry_path}")

    env = os.environ.copy()
    env["FAIL_CLOSE_CASE_MATRIX"] = str(Path(args.case_matrix).resolve())
    if args.asset:
        env["FAIL_CLOSE_DECISION_ASSET"] = str(Path(args.asset).resolve())
    if args.schema:
        env["FAIL_CLOSE_DECISION_SCHEMA"] = str(Path(args.schema).resolve())
    if args.recovery_asset:
        env["FAIL_CLOSE_RECOVERY_ASSET"] = str(Path(args.recovery_asset).resolve())
    if args.recovery_schema:
        env["FAIL_CLOSE_RECOVERY_SCHEMA"] = str(Path(args.recovery_schema).resolve())

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(entry_path)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined_output = "\n".join(
        fragment.rstrip()
        for fragment in (completed.stdout, completed.stderr)
        if fragment and fragment.strip()
    ).strip()
    return completed.returncode, combined_output


def _validate_host_message_template_rendering(tables: dict[str, object]) -> int:
    template_contract = tables.get("host_message_templates")
    if not isinstance(template_contract, dict):
        raise FailureRecoveryError("decision_tables.host_message_templates must be a mapping")
    templates = template_contract.get("templates")
    if not isinstance(templates, list) or not templates:
        raise FailureRecoveryError("decision_tables.host_message_templates.templates must be a non-empty list")

    rendered_count = 0
    default_locale = str(template_contract.get("default_locale", "zh-CN"))
    for entry in templates:
        if not isinstance(entry, dict):
            raise FailureRecoveryError("decision_tables.host_message_templates.templates contains a non-mapping row")
        prompt_modes = entry.get("prompt_modes")
        if not isinstance(prompt_modes, list) or not prompt_modes:
            raise FailureRecoveryError("host message template prompt_modes must be a non-empty list")
        reason_code = str(entry.get("match_value", ""))
        if entry.get("match_kind") == "reason_code_family_prefix":
            reason_code = f"{reason_code}.smoke"
        for prompt_mode in prompt_modes:
            result = render_host_message(
                reason_code=reason_code,
                prompt_mode=str(prompt_mode),
                variables=_TEMPLATE_SMOKE_VARIABLES,
                locale=default_locale,
                templates=template_contract,
            )
            if not isinstance(result.get("text"), str) or not str(result["text"]).strip():
                raise FailureRecoveryError("Host message template render produced an empty message")
            rendered_count += 1

    fallback_result = render_host_message(
        reason_code="recovery.unknown_reason.smoke",
        prompt_mode="reask_confirm_execute",
        variables=_TEMPLATE_SMOKE_VARIABLES,
        locale=default_locale,
        templates=template_contract,
    )
    if not isinstance(fallback_result.get("text"), str) or not str(fallback_result["text"]).strip():
        raise FailureRecoveryError("Prompt-mode fallback render produced an empty message")
    return rendered_count + 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    resolved_runner, fallback_reason = _resolve_runner(args.runner)

    try:
        case_count = 0
        template_render_count = 0
        if resolved_runner == "pytest":
            pytest_return_code, pytest_output = _run_pytest_entry(args)
            if pytest_return_code != 0:
                detail = f"; details: {pytest_output}" if pytest_output else ""
                raise FailureRecoveryError(
                    f"Pytest fail-close matrix entry failed at {Path(args.pytest_entry).resolve()}{detail}"
                )
            tables, recovery_table, case_matrix = _load_contract_assets(args)
            case_count = len(case_matrix["cases"])
        else:
            tables, recovery_table, case_matrix, results = _load_and_evaluate_contracts(args)
            case_count = len(results)
        _validate_legacy_recovery_snapshot_consistency(args)
        template_render_count = _validate_host_message_template_rendering(tables)
    except (DecisionTableError, FailureRecoveryError) as exc:
        print(f"Fail-close contract check failed: {exc}")
        if _is_missing_default_case_matrix(args.case_matrix, error_text=str(exc)):
            print(
                "Hint: default --case-matrix points to a development fixture. "
                "If this workspace is not bootstrapped yet, run bootstrap first "
                "or pass an explicit --case-matrix path."
            )
        return 1

    print(
        "Fail-close contract check passed: "
        f"decision_tables={tables['schema_version']} @ {tables['source_path']} "
        f"(schema: {tables['schema_source_path']}), "
        f"failure_recovery={recovery_table['schema_version']} @ {recovery_table['source_path']} "
        f"(schema: {recovery_table['schema_source_path']}), "
        f"host_message_templates={tables['host_message_templates']['schema_version']} "
        f"@ {tables['host_message_templates']['source_path']} "
        f"(schema: {tables['host_message_templates']['schema_source_path']}, renders: {template_render_count}), "
        f"case_matrix={case_matrix['source_path']} ({case_count} cases), "
        f"runner={resolved_runner}"
    )
    if fallback_reason:
        print(f"Runner note: auto fallback to native ({fallback_reason}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
