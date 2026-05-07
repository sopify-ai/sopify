from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

import pytest

from runtime.decision_tables import load_decision_tables, load_default_decision_tables
from runtime.failure_recovery import (
    FailureRecoveryError,
    evaluate_failure_recovery_case,
    load_default_failure_recovery_table,
    load_failure_recovery_case_matrix,
    load_failure_recovery_table,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASE_MATRIX_PATH = REPO_ROOT / "tests" / "fixtures" / "fail_close_case_matrix.yaml"
_CASE_MATRIX_LOAD_ERROR_KEY = "__case_matrix_load_error__"


def _get_path_from_env(key: str) -> str | None:
    value = os.environ.get(key)
    if not value:
        return None
    return str(Path(value).resolve())


def _load_decision_tables_from_env() -> dict[str, object]:
    asset_path = _get_path_from_env("FAIL_CLOSE_DECISION_ASSET")
    schema_path = _get_path_from_env("FAIL_CLOSE_DECISION_SCHEMA")
    if asset_path:
        return load_decision_tables(asset_path, schema_path=schema_path)
    return load_default_decision_tables(schema_path=schema_path)


def _load_recovery_table_from_env() -> dict[str, object]:
    recovery_asset_path = _get_path_from_env("FAIL_CLOSE_RECOVERY_ASSET")
    recovery_schema_path = _get_path_from_env("FAIL_CLOSE_RECOVERY_SCHEMA")
    decision_asset_path = _get_path_from_env("FAIL_CLOSE_DECISION_ASSET")
    if recovery_asset_path:
        return load_failure_recovery_table(
            recovery_asset_path,
            schema_path=recovery_schema_path,
            decision_tables_path=decision_asset_path,
        )
    return load_default_failure_recovery_table(
        schema_path=recovery_schema_path,
        decision_tables_path=decision_asset_path,
    )


def _load_case_matrix_from_env() -> dict[str, object]:
    case_matrix_path = _get_path_from_env("FAIL_CLOSE_CASE_MATRIX") or str(
        DEFAULT_CASE_MATRIX_PATH.resolve()
    )
    recovery_schema_path = _get_path_from_env("FAIL_CLOSE_RECOVERY_SCHEMA")
    return load_failure_recovery_case_matrix(case_matrix_path, schema_path=recovery_schema_path)


@lru_cache(maxsize=1)
def _load_decision_tables_cached() -> dict[str, object]:
    return _load_decision_tables_from_env()


@lru_cache(maxsize=1)
def _load_recovery_table_cached() -> dict[str, object]:
    return _load_recovery_table_from_env()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "case" not in metafunc.fixturenames:
        return

    try:
        case_matrix = _load_case_matrix_from_env()
        cases = case_matrix["cases"]
        metafunc.parametrize("case", cases, ids=[str(case["case_id"]) for case in cases])
    except Exception as exc:  # pragma: no cover - exercised via pytest runtime.
        metafunc.parametrize(
            "case",
            [pytest.param({_CASE_MATRIX_LOAD_ERROR_KEY: f"{type(exc).__name__}: {exc}"}, id="case-matrix-load-error")],
        )


def test_fail_close_case_matrix_contract(case: dict[str, object]) -> None:
    if _CASE_MATRIX_LOAD_ERROR_KEY in case:
        pytest.fail(f"Failed to load fail-close case matrix: {case[_CASE_MATRIX_LOAD_ERROR_KEY]}")

    try:
        decision_tables = _load_decision_tables_cached()
    except Exception as exc:
        pytest.fail(f"Failed to load decision tables: {type(exc).__name__}: {exc}")

    try:
        recovery_table = _load_recovery_table_cached()
    except Exception as exc:
        pytest.fail(f"Failed to load failure recovery table: {type(exc).__name__}: {exc}")

    if case.get("required_host_action") == "review_or_execute_plan":
        with pytest.raises(
            FailureRecoveryError,
            match=r"No recovery row for .*required_host_action=review_or_execute_plan",
        ):
            evaluate_failure_recovery_case(
                case,
                decision_tables=decision_tables,
                recovery_table=recovery_table,
            )
        return

    result = evaluate_failure_recovery_case(
        case,
        decision_tables=decision_tables,
        recovery_table=recovery_table,
    )
    expected = case["expected"]
    for key, expected_value in expected.items():
        assert result[key] == expected_value
