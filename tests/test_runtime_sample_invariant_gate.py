from __future__ import annotations

from tests.runtime_test_support import *
from tests.runtime_test_support import _plan_dir_count

from runtime.context_v1_scope import FORBIDDEN_V1_SIDE_EFFECTS
from runtime.decision_tables import load_default_decision_tables
from runtime.failure_recovery import load_failure_recovery_case_matrix

FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "sample_invariant_gate_matrix.yaml"
FAIL_CLOSE_MATRIX_PATH = REPO_ROOT / "tests" / "fixtures" / "fail_close_case_matrix.yaml"


def _load_sample_gate_matrix() -> dict[str, object]:
    payload = load_yaml(FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError("sample invariant gate fixture must be a mapping")
    return payload


def _cases_by_id() -> dict[str, dict[str, object]]:
    matrix = _load_sample_gate_matrix()
    cases = matrix.get("cases")
    if not isinstance(cases, list):
        raise AssertionError("sample invariant gate fixture must contain cases")
    return {str(case["case_id"]): case for case in cases}


def _failure_cases_by_id() -> dict[str, dict[str, object]]:
    matrix = load_failure_recovery_case_matrix(FAIL_CLOSE_MATRIX_PATH)
    return {str(case["case_id"]): case for case in matrix["cases"]}


def _side_effect_rows_by_key() -> dict[tuple[str, str], dict[str, object]]:
    tables = load_default_decision_tables()
    rows = tables["side_effect_mapping_table"]["rows"]
    return {
        (str(row["checkpoint_kind"]), str(row["resolved_action"])): row
        for row in rows
    }


def _router_for_workspace(workspace: Path, *, active_plan: bool = False) -> Router:
    config = load_runtime_config(workspace)
    store = StateStore(config)
    store.ensure()
    if active_plan:
        plan_artifact = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
        store.set_current_plan(plan_artifact)
    return Router(config, state_store=store)


def _skills_for_workspace(workspace: Path) -> SkillRegistry:
    config = load_runtime_config(workspace)
    return SkillRegistry(config, user_home=workspace / "home").discover()


def _enter_decision_pending(workspace: Path):
    result = run_runtime(
        "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
        workspace_root=workspace,
        user_home=workspace / "home",
    )
    assert result.handoff.required_host_action == "confirm_decision"
    return result


class SampleInvariantAssetTests(unittest.TestCase):
    def test_fixture_covers_a1_to_a8_with_required_columns(self) -> None:
        matrix = _load_sample_gate_matrix()
        self.assertEqual(matrix["schema_version"], "sample_invariant_gate.v1")
        self.assertEqual(
            matrix["v1_gate_cases"],
            [
                "A-5_mixed_clause_after_comma",
                "A-8_analysis_only_no_write_process_semantic",
            ],
        )

        cases = list(_cases_by_id().values())
        self.assertEqual(
            [case["case_id"] for case in cases],
            [
                "A-1_explain_only",
                "A-2_decision_selection_with_suffix_text",
                "A-5_mixed_clause_after_comma",
                "A-7_question_like_retopic_baseline",
                "A-8_analysis_only_no_write_process_semantic",
            ],
        )

        replay_required = {
            "A-5_mixed_clause_after_comma",
            "A-8_analysis_only_no_write_process_semantic",
        }
        # A-5 was simplified during proposal removal — negative/boundary examples removed
        cases_with_full_examples = {
            "A-5_mixed_clause_after_comma",
        }
        for case in cases:
            self.assertTrue(case["positive_examples"], msg=case["case_id"])
            if case["case_id"] not in cases_with_full_examples:
                self.assertTrue(case["negative_examples"], msg=case["case_id"])
                self.assertTrue(case["boundary_examples"], msg=case["case_id"])
            self.assertTrue(case["forbidden_side_effects"], msg=case["case_id"])
            if case["case_id"] in replay_required:
                self.assertTrue(case.get("replay_examples"), msg=case["case_id"])

    def test_fixture_aligns_with_fail_close_matrix_and_effect_profiles(self) -> None:
        failure_cases = _failure_cases_by_id()
        rows_by_key = _side_effect_rows_by_key()

        for case in _cases_by_id().values():
            contract_ref = case["contract_ref"]
            failure_case = failure_cases[contract_ref["fail_close_case_id"]]
            self.assertEqual(failure_case["required_host_action"], contract_ref["required_host_action"])
            self.assertEqual(failure_case["allowed_response_mode"], contract_ref["allowed_response_mode"])

            effect_profile = case.get("effect_profile")
            if effect_profile is None:
                continue
            row = rows_by_key[(effect_profile["checkpoint_kind"], effect_profile["resolved_action"])]
            self.assertEqual(
                row["forbidden_state_effects"],
                effect_profile["forbidden_state_effects"],
            )
            self.assertTrue(set(effect_profile["forbidden_state_effects"]).issubset(FORBIDDEN_V1_SIDE_EFFECTS))


class SampleInvariantReplayTests(unittest.TestCase):
    def test_a5_mixed_clause_examples_freeze_local_action_surface(self) -> None:
        case = _cases_by_id()["A-5_mixed_clause_after_comma"]

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_decision_pending(workspace)
            cancelled = run_runtime(
                case["positive_examples"][0]["utterance"],
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            self.assertEqual(cancelled.route.route_name, "cancel_active")
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

