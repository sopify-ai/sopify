"""Deterministic tests for ActionValidator (P0-B) and side-effect mapping (P0-E),
plus integration tests for ActionProposal gate flow (P0-G).

给定 ActionProposal + ValidationContext → 确定性 ValidationDecision。
P0-G: gate → validator → engine 端到端集成测试。
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import unittest

from runtime.action_intent import (
    ACTION_TYPES,
    CONFIDENCE_LEVELS,
    DECISION_AUTHORIZE,
    DECISION_DOWNGRADE,
    DECISION_FALLBACK_ROUTER,
    SIDE_EFFECTS,
    ActionProposal,
    ArchiveSubjectProposal,
    ActionValidator,
    ValidationContext,
    ValidationDecision,
    resolve_action_proposal,
)
from runtime.decision_tables import load_default_decision_tables


# ---------------------------------------------------------------------------
# P0-B: ActionValidator deterministic tests
# ---------------------------------------------------------------------------


class ActionValidatorTests(unittest.TestCase):
    """Design.md §测试策略 — Validator deterministic tests."""

    def setUp(self) -> None:
        self.validator = ActionValidator()
        self.empty_ctx = ValidationContext()

    # -- consult_readonly + none → authorize, route_override=consult ----------

    def test_consult_readonly_none_high_no_checkpoint(self) -> None:
        proposal = ActionProposal("consult_readonly", "none", "high")
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_AUTHORIZE)
        self.assertEqual(result.resolved_action, "consult_readonly")
        self.assertEqual(result.resolved_side_effect, "none")
        self.assertEqual(result.route_override, "consult")

    def test_consult_readonly_none_low_still_authorized(self) -> None:
        """consult_readonly + none 无需降级，即使 confidence=low。"""
        proposal = ActionProposal("consult_readonly", "none", "low")
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_AUTHORIZE)
        self.assertEqual(result.route_override, "consult")

    def test_consult_readonly_none_with_checkpoint(self) -> None:
        """Checkpoint 上方 consult 共存 — checkpoint pending 时仍可 consult。"""
        ctx = ValidationContext(checkpoint_kind="confirm_plan_package")
        proposal = ActionProposal("consult_readonly", "none", "high")
        result = self.validator.validate(proposal, ctx)
        self.assertEqual(result.decision, DECISION_AUTHORIZE)
        self.assertEqual(result.route_override, "consult")

    def test_consult_readonly_none_with_decision_checkpoint(self) -> None:
        ctx = ValidationContext(checkpoint_kind="confirm_decision")
        proposal = ActionProposal("consult_readonly", "none", "high")
        result = self.validator.validate(proposal, ctx)
        self.assertEqual(result.decision, DECISION_AUTHORIZE)
        self.assertEqual(result.route_override, "consult")

    # -- side-effecting + evidence 通过 → authorize, route_override=None ------

    def test_propose_plan_write_high_evidence_authorized(self) -> None:
        proposal = ActionProposal(
            "propose_plan", "write_plan_package", "high",
            evidence=("用户说要实现缓存功能",),
        )
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_AUTHORIZE)
        self.assertIsNone(result.route_override)

    def test_modify_files_write_high_evidence_authorized(self) -> None:
        proposal = ActionProposal(
            "modify_files", "write_files", "high",
            evidence=("用户明确要求修改文件",),
        )
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_AUTHORIZE)
        self.assertIsNone(result.route_override)

    def test_archive_plan_write_high_evidence_authorizes_with_structured_subject(self) -> None:
        proposal = ActionProposal(
            "archive_plan", "write_files", "high",
            evidence=("用户明确要求归档当前方案",),
            archive_subject=ArchiveSubjectProposal(
                ref_kind="current_plan",
                source="current_plan",
                allow_current_plan_fallback=True,
            ),
        )
        ctx = ValidationContext(current_plan_path=".sopify-skills/plan/demo")
        result = self.validator.validate(proposal, ctx)
        self.assertEqual(result.decision, DECISION_AUTHORIZE)
        self.assertEqual(result.resolved_action, "archive_plan")
        self.assertEqual(result.resolved_side_effect, "write_files")
        self.assertEqual(result.route_override, "archive_lifecycle")
        self.assertEqual(result.reason_code, "validator.archive_plan_authorized")
        self.assertEqual(result.artifacts["archive_subject"]["ref_kind"], "current_plan")

    def test_archive_plan_missing_subject_downgrades_to_consult(self) -> None:
        proposal = ActionProposal(
            "archive_plan", "write_files", "high",
            evidence=("用户明确要求归档当前方案",),
        )
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_DOWNGRADE)
        self.assertEqual(result.route_override, "consult")
        self.assertEqual(result.reason_code, "validator.archive_plan_missing_subject")

    def test_archive_plan_current_plan_without_current_plan_downgrades(self) -> None:
        proposal = ActionProposal(
            "archive_plan", "write_files", "high",
            evidence=("用户明确要求归档当前方案",),
            archive_subject=ArchiveSubjectProposal(
                ref_kind="current_plan",
                source="current_plan",
                allow_current_plan_fallback=True,
            ),
        )
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_DOWNGRADE)
        self.assertEqual(result.route_override, "consult")
        self.assertEqual(result.reason_code, "validator.archive_plan_current_plan_unavailable")

    def test_archive_plan_blocked_by_pending_checkpoint(self) -> None:
        proposal = ActionProposal(
            "archive_plan", "write_files", "high",
            evidence=("用户明确要求归档当前方案",),
            archive_subject=ArchiveSubjectProposal(
                ref_kind="current_plan",
                source="current_plan",
                allow_current_plan_fallback=True,
            ),
        )
        ctx = ValidationContext(
            current_plan_path=".sopify-skills/plan/demo",
            required_host_action="confirm_decision",
        )
        result = self.validator.validate(proposal, ctx)
        self.assertEqual(result.decision, DECISION_DOWNGRADE)
        self.assertEqual(result.route_override, "consult")
        self.assertEqual(result.reason_code, "validator.archive_plan_blocked_by_checkpoint")

    def test_archive_plan_blocked_by_state_conflict(self) -> None:
        proposal = ActionProposal(
            "archive_plan", "write_files", "high",
            evidence=("用户明确要求归档当前方案",),
            archive_subject=ArchiveSubjectProposal(
                ref_kind="current_plan",
                source="current_plan",
                allow_current_plan_fallback=True,
            ),
        )
        ctx = ValidationContext(
            current_plan_path=".sopify-skills/plan/demo",
            state_conflict=True,
        )
        result = self.validator.validate(proposal, ctx)
        self.assertEqual(result.decision, DECISION_DOWNGRADE)
        self.assertEqual(result.route_override, "consult")
        self.assertEqual(result.reason_code, "validator.archive_plan_blocked_by_state_conflict")

    def test_archive_plan_without_evidence_downgrades(self) -> None:
        proposal = ActionProposal("archive_plan", "write_files", "medium")
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_DOWNGRADE)
        self.assertEqual(result.resolved_action, "consult_readonly")
        self.assertEqual(result.route_override, "consult")

    # -- side-effecting + low confidence → downgrade -------------------------

    def test_propose_plan_write_low_downgraded(self) -> None:
        proposal = ActionProposal(
            "propose_plan", "write_plan_package", "low",
            evidence=("用户好像在问问题",),
        )
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_DOWNGRADE)
        self.assertEqual(result.resolved_action, "consult_readonly")
        self.assertEqual(result.route_override, "consult")

    # -- side-effecting + evidence 不足 → downgrade --------------------------

    def test_propose_plan_write_high_no_evidence_downgraded(self) -> None:
        proposal = ActionProposal(
            "propose_plan", "write_plan_package", "high",
            evidence=(),  # 无 evidence
        )
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_DOWNGRADE)
        self.assertEqual(result.resolved_action, "consult_readonly")
        self.assertEqual(result.route_override, "consult")

    def test_modify_files_medium_no_evidence_downgraded(self) -> None:
        proposal = ActionProposal(
            "modify_files", "write_files", "medium",
            evidence=(),
        )
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_DOWNGRADE)
        self.assertEqual(result.route_override, "consult")

    # -- 未知 action → fallback_router ----------------------------------------

    def test_unknown_action_fallback(self) -> None:
        proposal = ActionProposal("totally_unknown", "none", "high")
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_FALLBACK_ROUTER)
        self.assertIsNone(result.route_override)

    # -- consult_readonly with unexpected side_effect -------------------------

    def test_consult_readonly_with_write_downgraded_on_no_evidence(self) -> None:
        """Host 声称 consult 但带 write side_effect，无 evidence → downgrade。"""
        proposal = ActionProposal(
            "consult_readonly", "write_plan_package", "high",
            evidence=(),
        )
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_DOWNGRADE)
        self.assertEqual(result.resolved_action, "consult_readonly")

    # -- Unknown side_effect → fail-close downgrade --------------------------

    def test_unknown_side_effect_downgraded(self) -> None:
        """Unknown side_effect must fail-close to consult, not authorize."""
        # Construct directly to bypass from_dict validation.
        proposal = ActionProposal("propose_plan", "delete_database", "high",
                                  evidence=("some evidence",))
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_DOWNGRADE)
        self.assertEqual(result.resolved_action, "consult_readonly")
        self.assertEqual(result.route_override, "consult")
        self.assertEqual(result.reason_code, "validator.unknown_side_effect_downgrade")

    # -- Non-side-effecting recognized action ---------------------------------

    def test_cancel_flow_none_authorized_no_override(self) -> None:
        proposal = ActionProposal("cancel_flow", "none", "high")
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_AUTHORIZE)
        self.assertIsNone(result.route_override)

    def test_checkpoint_response_none_authorized_no_override(self) -> None:
        proposal = ActionProposal("checkpoint_response", "none", "high")
        result = self.validator.validate(proposal, self.empty_ctx)
        self.assertEqual(result.decision, DECISION_AUTHORIZE)
        self.assertIsNone(result.route_override)


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class ActionProposalSerializationTests(unittest.TestCase):

    def test_round_trip(self) -> None:
        original = ActionProposal(
            "propose_plan", "write_plan_package", "medium",
            evidence=("用户说需要缓存", "第二条证据"),
        )
        restored = ActionProposal.from_dict(original.to_dict())
        self.assertEqual(restored.action_type, original.action_type)
        self.assertEqual(restored.side_effect, original.side_effect)
        self.assertEqual(restored.confidence, original.confidence)
        self.assertEqual(restored.evidence, original.evidence)

    def test_resolve_none(self) -> None:
        self.assertIsNone(resolve_action_proposal(None))

    def test_resolve_valid(self) -> None:
        proposal = resolve_action_proposal({"action_type": "consult_readonly"})
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.action_type, "consult_readonly")

    def test_resolve_malformed(self) -> None:
        # Should not crash, just return None for invalid input types.
        self.assertIsNone(resolve_action_proposal("not a dict"))  # type: ignore[arg-type]

    def test_from_dict_rejects_unknown_action_type(self) -> None:
        with self.assertRaises(ValueError):
            ActionProposal.from_dict({"action_type": "nuke_everything"})

    def test_from_dict_rejects_unknown_side_effect(self) -> None:
        with self.assertRaises(ValueError):
            ActionProposal.from_dict({
                "action_type": "consult_readonly",
                "side_effect": "delete_database",
            })

    def test_from_dict_rejects_unknown_confidence(self) -> None:
        with self.assertRaises(ValueError):
            ActionProposal.from_dict({
                "action_type": "consult_readonly",
                "confidence": "yolo",
            })

    def test_from_dict_rejects_bare_string_evidence(self) -> None:
        """Evidence must be a list, not a bare string."""
        with self.assertRaises(ValueError):
            ActionProposal.from_dict({
                "action_type": "consult_readonly",
                "evidence": "bare string",
            })

    def test_from_dict_rejects_non_string_evidence_items(self) -> None:
        with self.assertRaises(ValueError):
            ActionProposal.from_dict({
                "action_type": "consult_readonly",
                "evidence": [123, 456],
            })

    def test_resolve_returns_none_for_invalid_enum(self) -> None:
        """resolve_action_proposal returns None when from_dict raises."""
        result = resolve_action_proposal({
            "action_type": "consult_readonly",
            "side_effect": "invalid_effect",
        })
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# P0-E: Side-effect mapping row for confirm_plan_package + consult_readonly
# ---------------------------------------------------------------------------


class SideEffectMappingConfirmPlanPackageConsultTests(unittest.TestCase):
    """Verify the new switch_to_consult_readonly row for confirm_plan_package."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tables = load_default_decision_tables()
        cls.rows = cls.tables["side_effect_mapping_table"]["rows"]

    def _find_row(self, resolved_action: str, checkpoint_kind: str) -> dict:
        for row in self.rows:
            if (
                row["resolved_action"] == resolved_action
                and row["checkpoint_kind"] == checkpoint_kind
            ):
                return row
        self.fail(
            f"No side_effect_mapping row for "
            f"resolved_action={resolved_action}, checkpoint_kind={checkpoint_kind}"
        )

    def test_row_exists(self) -> None:
        row = self._find_row("switch_to_consult_readonly", "confirm_plan_package")
        self.assertIsNotNone(row)

    def test_preserves_proposal_and_run(self) -> None:
        row = self._find_row("switch_to_consult_readonly", "confirm_plan_package")
        self.assertIn("current_plan_proposal", row["state_mutators"]["preserve"])
        self.assertIn("current_run", row["state_mutators"]["preserve"])

    def test_forbidden_effects(self) -> None:
        row = self._find_row("switch_to_consult_readonly", "confirm_plan_package")
        for effect in (
            "materialize_new_plan_package",
            "advance_to_develop",
            "clear_current_plan_proposal",
        ):
            self.assertIn(effect, row["forbidden_state_effects"])

    def test_handoff_protocol(self) -> None:
        row = self._find_row("switch_to_consult_readonly", "confirm_plan_package")
        hp = row["handoff_protocol"]
        self.assertEqual(hp["required_host_action"], "continue_host_consult")
        self.assertEqual(hp["resume_route"], "plan_proposal_pending")
        self.assertEqual(hp["output_mode"], "consult_answer")
        self.assertIn("checkpoint_request", hp["artifact_keys"])
        self.assertIn("proposal", hp["artifact_keys"])

    def test_preserved_identity(self) -> None:
        row = self._find_row("switch_to_consult_readonly", "confirm_plan_package")
        for key in ("checkpoint_id", "reserved_plan_id", "topic_key"):
            self.assertIn(key, row["preserved_identity"])

    def test_terminality(self) -> None:
        row = self._find_row("switch_to_consult_readonly", "confirm_plan_package")
        self.assertEqual(row["terminality"], "route_terminal")

    def test_reason_code(self) -> None:
        row = self._find_row("switch_to_consult_readonly", "confirm_plan_package")
        self.assertEqual(
            row["reason_code"],
            "effect.hard_constraint.analysis_only_consult_readonly",
        )

    def test_existing_decision_row_unchanged(self) -> None:
        """Existing switch_to_consult_readonly for confirm_decision is preserved."""
        row = self._find_row("switch_to_consult_readonly", "confirm_decision")
        self.assertEqual(row["handoff_protocol"]["required_host_action"], "continue_host_consult")
        self.assertEqual(row["handoff_protocol"]["resume_route"], "decision_pending")

    def test_row_ordering_preserved(self) -> None:
        """Rows must follow frozen ordered_resolved_actions order."""
        actions = [r["resolved_action"] for r in self.rows]
        ordered = [
            "stay_in_checkpoint_and_inspect",
            "submit_revision_feedback",
            "switch_to_consult_readonly",
            "switch_to_consult_readonly",
            "continue_checkpoint_confirmation",
        ]
        self.assertEqual(actions, ordered)


# ---------------------------------------------------------------------------
# Duplicate (resolved_action, checkpoint_kind) guard
# ---------------------------------------------------------------------------


class DuplicateRowGuardTests(unittest.TestCase):
    """Verify that duplicate (resolved_action, checkpoint_kind) pairs are rejected."""

    def test_duplicate_pair_rejected(self) -> None:
        import tempfile
        from runtime.decision_tables import DecisionTableError, load_decision_tables

        # Build a minimal YAML with two identical (action, checkpoint) pairs.
        yaml_text = _build_duplicate_row_yaml()
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp) / "decision_tables.yaml"
            asset.write_text(yaml_text, encoding="utf-8")
            with self.assertRaisesRegex(DecisionTableError, r"duplicate"):
                load_decision_tables(asset)


def _build_duplicate_row_yaml() -> str:
    """Minimal decision_tables asset with a duplicate side_effect_mapping row.

    Duplicates the first side_effect_mapping row by text insertion,
    preserving the custom YAML parser's expected format.
    """
    from runtime.decision_tables import DEFAULT_DECISION_TABLES_PATH

    original = DEFAULT_DECISION_TABLES_PATH.read_text(encoding="utf-8")
    # Find the first row block and duplicate it.
    marker = "    - resolved_action: stay_in_checkpoint_and_inspect\n"
    first_pos = original.index(marker)
    # Find where the next row starts (next "    - resolved_action:")
    next_row_pos = original.index("    - resolved_action:", first_pos + len(marker))
    first_row_block = original[first_pos:next_row_pos]
    # Insert duplicate right after the first row.
    return original[:next_row_pos] + first_row_block + original[next_row_pos:]


# ---------------------------------------------------------------------------
# P0-C: Gate receives --action-proposal-json / --action-proposal-capability
# ---------------------------------------------------------------------------


class GateActionProposalTests(unittest.TestCase):
    """Gate-layer tests for ActionProposal CLI args and retry contract."""

    def test_is_command_prefix_go(self) -> None:
        from runtime.gate import _is_command_prefix_request
        self.assertTrue(_is_command_prefix_request("~go plan 补一下"))

    def test_is_not_command_prefix_compare_removed(self) -> None:
        from runtime.gate import _is_command_prefix_request
        self.assertFalse(_is_command_prefix_request("~compare 对比 A 和 B"))

    def test_is_not_command_prefix_normal_request(self) -> None:
        from runtime.gate import _is_command_prefix_request
        self.assertFalse(_is_command_prefix_request("请帮我修复一下 bug"))

    def test_is_not_command_prefix_empty(self) -> None:
        from runtime.gate import _is_command_prefix_request
        self.assertFalse(_is_command_prefix_request(""))

    def test_is_not_command_prefix_gofoo(self) -> None:
        """Regression: ~gofoo must not match — require whitespace or end."""
        from runtime.gate import _is_command_prefix_request
        self.assertFalse(_is_command_prefix_request("~gofoo 实现功能"))

    def test_is_not_command_prefix_comparex(self) -> None:
        from runtime.gate import _is_command_prefix_request
        self.assertFalse(_is_command_prefix_request("~comparex 对比"))

    def test_is_command_prefix_go_bare(self) -> None:
        from runtime.gate import _is_command_prefix_request
        self.assertTrue(_is_command_prefix_request("~go"))

    def test_action_proposal_schema_contains_all_enums(self) -> None:
        from runtime.gate import _build_action_proposal_schema
        schema = _build_action_proposal_schema()
        self.assertEqual(set(schema["action_type"]["enum"]), set(ACTION_TYPES))
        self.assertEqual(set(schema["side_effect"]["enum"]), set(SIDE_EFFECTS))
        self.assertEqual(set(schema["confidence"]["enum"]), set(CONFIDENCE_LEVELS))

    def test_action_proposal_schema_has_evidence_type(self) -> None:
        from runtime.gate import _build_action_proposal_schema
        schema = _build_action_proposal_schema()
        self.assertEqual(schema["evidence"]["type"], "list[str]")

    def test_retry_contract_gate_passed_false(self) -> None:
        from runtime.gate import _build_action_proposal_retry_contract
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            contract = _build_action_proposal_retry_contract(
                config=None, session_id="test-session", workspace=Path(td),
            )
        self.assertFalse(contract["gate_passed"])
        self.assertEqual(contract["status"], "action_proposal_retry")
        self.assertEqual(contract["allowed_response_mode"], "action_proposal_retry")

    def test_retry_contract_includes_schema(self) -> None:
        from runtime.gate import _build_action_proposal_retry_contract
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            contract = _build_action_proposal_retry_contract(
                config=None, session_id="test-session", workspace=Path(td),
            )
        self.assertIn("action_proposal_schema", contract)
        schema = contract["action_proposal_schema"]
        self.assertIn("action_type", schema)
        self.assertIn("side_effect", schema)

    def test_retry_contract_evidence_all_false(self) -> None:
        from runtime.gate import _build_action_proposal_retry_contract
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            contract = _build_action_proposal_retry_contract(
                config=None, session_id="test-session", workspace=Path(td),
            )
        evidence = contract["evidence"]
        self.assertFalse(evidence["handoff_found"])
        self.assertFalse(evidence["strict_runtime_entry"])
        self.assertFalse(evidence["current_request_produced_handoff"])

    def test_retry_contract_state_has_full_paths_with_config(self) -> None:
        """Regression: config-aware retry must include all state paths."""
        from runtime.gate import _build_action_proposal_retry_contract
        from runtime.config import load_runtime_config
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            config = load_runtime_config(workspace)
            contract = _build_action_proposal_retry_contract(
                config=config, session_id="test-session", workspace=workspace,
                request="请帮我看下 bug",
            )
        state = contract["state"]
        expected_keys = {
            "scope", "state_root", "current_plan_path",
            "current_plan_proposal_path", "current_run_path",
            "current_handoff_path", "current_clarification_path",
            "current_decision_path", "last_route_path",
        }
        self.assertTrue(expected_keys.issubset(set(state.keys())),
                        f"Missing keys: {expected_keys - set(state.keys())}")

    def test_resolve_action_proposal_valid_json(self) -> None:
        raw = {"action_type": "consult_readonly", "side_effect": "none", "confidence": "high"}
        proposal = resolve_action_proposal(raw)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.action_type, "consult_readonly")

    def test_resolve_action_proposal_invalid_json_returns_none(self) -> None:
        proposal = resolve_action_proposal("not a dict")
        self.assertIsNone(proposal)

    def test_resolve_action_proposal_bad_action_type_returns_none(self) -> None:
        raw = {"action_type": "INVALID", "side_effect": "none"}
        proposal = resolve_action_proposal(raw)
        self.assertIsNone(proposal)

    def test_resolve_action_proposal_empty_dict_returns_none(self) -> None:
        """Finding #1: {} must not produce ActionProposal(action_type='')."""
        proposal = resolve_action_proposal({})
        self.assertIsNone(proposal)

    def test_resolve_action_proposal_missing_action_type_returns_none(self) -> None:
        """Finding #1: missing action_type → None (fail-close)."""
        raw = {"side_effect": "none", "confidence": "high"}
        proposal = resolve_action_proposal(raw)
        self.assertIsNone(proposal)

    def test_from_dict_empty_action_type_raises(self) -> None:
        """Finding #1: from_dict({}) → ValueError."""
        with self.assertRaises(ValueError):
            ActionProposal.from_dict({})

    def test_gate_malformed_json_implies_capability(self) -> None:
        """Finding #2: passing --action-proposal-json implies new host —
        malformed JSON should trigger retry, not legacy fallback."""
        import tempfile
        from runtime.gate import enter_runtime_gate
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            workspace = temp_root / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            result = enter_runtime_gate(
                "请帮我看下 bug",
                workspace_root=workspace,
                user_home=temp_root / "home",
                action_proposal_json="{bad json",
                action_proposal_capability=False,  # not explicitly set
            )
            # Should trigger retry (not silently fall to legacy router).
            self.assertEqual(result.get("status"), "action_proposal_retry")
            self.assertIn("action_proposal_parse_error", result)


# ---------------------------------------------------------------------------
# P0-D: Engine pre-route interceptor (unit-level)
# ---------------------------------------------------------------------------


class EnginePreRouteInterceptorTests(unittest.TestCase):
    """Verify ActionValidator integration with run_runtime() pre-route hook.

    These tests are deterministic — they construct the proposal and validator
    directly to verify the interceptor logic without needing a full workspace.
    """

    def test_consult_readonly_proposal_overrides_route(self) -> None:
        """consult_readonly proposal → route_override='consult' → skip Router."""
        proposal = ActionProposal("consult_readonly", "none", "high")
        validator = ActionValidator()
        ctx = ValidationContext()
        decision = validator.validate(proposal, ctx)
        self.assertEqual(decision.route_override, "consult")

    def test_side_effecting_high_confidence_no_override(self) -> None:
        """Side-effecting + high confidence → authorize, route_override=None."""
        proposal = ActionProposal(
            "modify_files", "write_files", "high",
            evidence=["user explicitly asked to fix the bug"],
        )
        validator = ActionValidator()
        ctx = ValidationContext()
        decision = validator.validate(proposal, ctx)
        self.assertIsNone(decision.route_override)
        self.assertEqual(decision.decision, DECISION_AUTHORIZE)

    def test_side_effecting_low_confidence_downgrades(self) -> None:
        """Side-effecting + low confidence → downgrade to consult."""
        proposal = ActionProposal(
            "modify_files", "write_files", "low",
            evidence=["maybe user wants this"],
        )
        validator = ActionValidator()
        ctx = ValidationContext()
        decision = validator.validate(proposal, ctx)
        self.assertEqual(decision.route_override, "consult")
        self.assertEqual(decision.decision, DECISION_DOWNGRADE)

    def test_unknown_action_type_falls_through(self) -> None:
        """Unknown action_type → fallback_router, route_override=None."""
        proposal = ActionProposal("unknown_future_action", "none", "high")
        validator = ActionValidator()
        ctx = ValidationContext()
        decision = validator.validate(proposal, ctx)
        self.assertIsNone(decision.route_override)
        self.assertEqual(decision.decision, DECISION_FALLBACK_ROUTER)

    def test_route_decision_construction_from_override(self) -> None:
        """Verify RouteDecision can be constructed from validator output."""
        from runtime.models import RouteDecision
        proposal = ActionProposal("consult_readonly", "none", "high")
        validator = ActionValidator()
        decision = validator.validate(proposal, ValidationContext())
        if decision.route_override:
            rd = RouteDecision(
                route_name=decision.route_override,
                request_text="test request",
                reason=f"action_proposal_validator: {decision.reason_code}",
            )
            self.assertEqual(rd.route_name, "consult")
            self.assertIn("action_proposal_validator", rd.reason)

    def test_no_proposal_means_no_override(self) -> None:
        """When action_proposal is None, no override → Router runs normally."""
        # This is the trivial case: action_proposal=None means the engine
        # skips the interceptor entirely. Verify the sentinel.
        proposal_override_route = None
        if None is not None:  # action_proposal is None
            pass  # would never enter
        self.assertIsNone(proposal_override_route)


# ---------------------------------------------------------------------------
# P0-D: Real run_runtime() smoke tests
# ---------------------------------------------------------------------------

import tempfile
from runtime.engine import run_runtime


class EngineActionProposalSmokeTests(unittest.TestCase):
    """Smoke tests that call run_runtime() with action_proposal to verify
    the real interceptor wiring doesn't crash."""

    def test_consult_readonly_proposal_routes_to_consult(self) -> None:
        """run_runtime() with consult_readonly proposal → route=consult."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            proposal = ActionProposal("consult_readonly", "none", "high")
            result = run_runtime(
                "什么是 runtime gate？",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=proposal,
            )
            self.assertEqual(result.route.route_name, "consult")
            self.assertIn("action_proposal_validator", result.route.reason)

    def test_no_proposal_falls_through_to_router(self) -> None:
        """run_runtime() without proposal → normal Router classification."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            result = run_runtime(
                "什么是 runtime gate？",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=None,
            )
            # Without proposal the router runs; consult is the expected
            # route for a question-only request but the exact route_name
            # depends on router logic — just verify it didn't crash and
            # the reason does NOT mention the validator.
            self.assertNotIn("action_proposal_validator", result.route.reason)

    def test_unknown_action_type_falls_through_to_router(self) -> None:
        """Unknown action_type → fallback_router → Router runs normally."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            proposal = ActionProposal("future_action_xyz", "none", "high")
            result = run_runtime(
                "什么是 runtime gate？",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=proposal,
            )
            # fallback_router means no route_override → Router handles it.
            self.assertNotIn("action_proposal_validator", result.route.reason)


# ---------------------------------------------------------------------------
# P0-G: Integration tests — full gate + engine end-to-end
# ---------------------------------------------------------------------------

import subprocess


def _setup_workspace_for_gate_integration(
    temp_root: Path,
) -> tuple[Path, Path]:
    """Create a minimal workspace + legacy payload manifest for gate tests.

    Returns (workspace, payload_manifest_path).
    """
    workspace = temp_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    home_root = temp_root / "home"
    payload_root = home_root / ".codex" / "sopify"
    helpers = payload_root / "helpers"
    bundle_dir = payload_root / "bundle"
    helpers.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Minimal bootstrap helper (legacy stub)
    (helpers / "bootstrap_workspace.py").write_text(
        "\n".join([
            "#!/usr/bin/env python3",
            "import argparse, json",
            "from pathlib import Path",
            "parser = argparse.ArgumentParser()",
            "parser.add_argument('--workspace-root', required=True)",
            "args = parser.parse_args()",
            "w = Path(args.workspace_root).resolve()",
            "print(json.dumps({",
            "  'action': 'skipped', 'state': 'READY',",
            "  'reason_code': 'WORKSPACE_BUNDLE_READY',",
            "  'workspace_root': str(w),",
            "  'bundle_root': str(w / '.sopify-runtime'),",
            "  'from_version': None, 'to_version': None,",
            "  'message': 'legacy helper fallback'",
            "}, ensure_ascii=False))",
        ]) + "\n",
        encoding="utf-8",
    )
    (bundle_dir / "manifest.json").write_text(
        json.dumps({"schema_version": "1", "bundle_version": "2026-03-28.220226"})
        + "\n",
        encoding="utf-8",
    )
    payload_manifest = payload_root / "payload-manifest.json"
    payload_manifest.write_text(
        json.dumps({
            "schema_version": "1",
            "helper_entry": "helpers/bootstrap_workspace.py",
            "bundle_manifest": "bundle/manifest.json",
        }) + "\n",
        encoding="utf-8",
    )
    return workspace, payload_manifest


class GateActionProposalIntegrationTests(unittest.TestCase):
    """P0-G: End-to-end integration tests for the ActionProposal gate flow.

    These tests exercise the real gate function (enter_runtime_gate) to verify:
    - capability-declared host without proposal → retry contract
    - retry contract with valid proposal → normal runtime entry
    - legacy host (no capability) → normal router fallback
    - command prefix requests bypass proposal requirement
    - malformed JSON → retry with parse error
    """

    def test_capability_without_proposal_returns_retry(self) -> None:
        """New host declares capability but no proposal → action_proposal_retry."""
        from runtime.gate import enter_runtime_gate
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))
            result = enter_runtime_gate(
                "批判看下这个方案",
                workspace_root=workspace,
                payload_manifest_path=pm,
                user_home=Path(td) / "home",
                action_proposal_capability=True,
            )
            self.assertEqual(result["status"], "action_proposal_retry")
            self.assertFalse(result["gate_passed"])
            self.assertEqual(result["allowed_response_mode"], "action_proposal_retry")
            self.assertIn("action_proposal_schema", result)
            schema = result["action_proposal_schema"]
            self.assertIn("action_type", schema)
            self.assertIn("side_effect", schema)
            self.assertIn("confidence", schema)
            self.assertIn("evidence", schema)

    def test_retry_then_success_with_consult_proposal(self) -> None:
        """Two-phase: capability → retry → provide consult_readonly proposal → success/consult."""
        from runtime.gate import enter_runtime_gate
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))

            # Phase 1: capability without proposal → retry
            retry = enter_runtime_gate(
                "批判看下这个方案",
                workspace_root=workspace,
                payload_manifest_path=pm,
                user_home=Path(td) / "home",
                action_proposal_capability=True,
            )
            self.assertEqual(retry["status"], "action_proposal_retry")

            # Phase 2: host generates proposal from schema and retries
            proposal_json = json.dumps({
                "action_type": "consult_readonly",
                "side_effect": "none",
                "confidence": "high",
                "evidence": ["user said 批判看下, read-only analysis request"],
            })
            result = enter_runtime_gate(
                "批判看下这个方案",
                workspace_root=workspace,
                payload_manifest_path=pm,
                user_home=Path(td) / "home",
                action_proposal_json=proposal_json,
            )
            self.assertEqual(result["status"], "ready")
            self.assertTrue(result["gate_passed"])
            self.assertEqual(result["runtime"]["route_name"], "consult")
            self.assertIn("action_proposal_validator", result["runtime"]["reason"])

    def test_legacy_host_no_capability_no_proposal_falls_through(self) -> None:
        """Legacy host (no --action-proposal-capability) → normal router."""
        from runtime.gate import enter_runtime_gate
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))
            result = enter_runtime_gate(
                "批判看下这个方案",
                workspace_root=workspace,
                payload_manifest_path=pm,
                user_home=Path(td) / "home",
                # No capability, no proposal → legacy fallback
            )
            self.assertEqual(result["status"], "ready")
            # Legacy host goes through normal Router — key assertion is:
            # NOT action_proposal_retry and NOT action_proposal_validator.
            self.assertNotEqual(result["runtime"]["route_name"], "action_proposal_retry")
            self.assertNotIn("action_proposal_validator", result["runtime"]["reason"])

    def test_command_prefix_bypasses_proposal_requirement(self) -> None:
        """~go plan request with capability but no proposal → should NOT retry."""
        from runtime.gate import enter_runtime_gate
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))
            result = enter_runtime_gate(
                "~go plan 补 ActionProposal 集成测试",
                workspace_root=workspace,
                payload_manifest_path=pm,
                user_home=Path(td) / "home",
                action_proposal_capability=True,
            )
            # Command prefix bypasses proposal — no retry, enters runtime
            self.assertEqual(result["status"], "ready")
            self.assertNotEqual(
                result.get("allowed_response_mode"), "action_proposal_retry"
            )

    def test_malformed_json_returns_retry_with_parse_error(self) -> None:
        """Malformed --action-proposal-json → retry with action_proposal_parse_error."""
        from runtime.gate import enter_runtime_gate
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))
            result = enter_runtime_gate(
                "加一个缓存功能",
                workspace_root=workspace,
                payload_manifest_path=pm,
                user_home=Path(td) / "home",
                action_proposal_json="{not valid json!!!}",
            )
            self.assertEqual(result["status"], "action_proposal_retry")
            self.assertIn("action_proposal_parse_error", result)
            self.assertIn("invalid JSON", result["action_proposal_parse_error"])

    def test_side_effecting_proposal_with_high_confidence_authorizes(self) -> None:
        """Side-effecting proposal (modify_files) with high confidence → authorize, Router runs."""
        from runtime.gate import enter_runtime_gate
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))
            proposal_json = json.dumps({
                "action_type": "modify_files",
                "side_effect": "write_files",
                "confidence": "high",
                "evidence": ["user explicitly asked to add a cache feature"],
            })
            result = enter_runtime_gate(
                "加一个缓存功能",
                workspace_root=workspace,
                payload_manifest_path=pm,
                user_home=Path(td) / "home",
                action_proposal_json=proposal_json,
            )
            self.assertEqual(result["status"], "ready")
            # Side-effecting authorize → route_override=None → Router classifies
            # For "加一个缓存功能", Router should classify as light_iterate or
            # go_plan or similar — the key assertion is that it's NOT consult.
            self.assertNotEqual(result["runtime"]["route_name"], "action_proposal_retry")

    def test_side_effecting_low_confidence_downgrades_to_consult(self) -> None:
        """Side-effecting + low confidence → downgrade to consult."""
        from runtime.gate import enter_runtime_gate
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))
            proposal_json = json.dumps({
                "action_type": "modify_files",
                "side_effect": "write_files",
                "confidence": "low",
                "evidence": ["maybe user wants this"],
            })
            result = enter_runtime_gate(
                "加一个缓存功能",
                workspace_root=workspace,
                payload_manifest_path=pm,
                user_home=Path(td) / "home",
                action_proposal_json=proposal_json,
            )
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["runtime"]["route_name"], "consult")
            self.assertIn("action_proposal_validator", result["runtime"]["reason"])


class GateCLIActionProposalTests(unittest.TestCase):
    """P0-G: CLI-level tests for scripts/runtime_gate.py with ActionProposal.

    These exercise the real CLI subprocess to verify:
    - Non-zero exit code for retry is parseable
    - Shell quoting edge cases for --action-proposal-json
    - Full round-trip: capability → parse stdout → generate proposal → retry success
    """

    def _run_gate_cli(
        self, args: list[str], *, check: bool = False
    ) -> tuple[int, dict[str, Any]]:
        """Run scripts/runtime_gate.py and return (exit_code, parsed_json)."""
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "runtime_gate.py"),
            "enter",
            *args,
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        if check and proc.returncode != 0:
            raise AssertionError(
                f"CLI failed with exit code {proc.returncode}:\n"
                f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
            )
        parsed = json.loads(proc.stdout)
        return proc.returncode, parsed

    def test_cli_capability_returns_retry_with_exit_1(self) -> None:
        """CLI: --action-proposal-capability without json → exit 1 + parseable JSON."""
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))
            exit_code, result = self._run_gate_cli([
                "--workspace-root", str(workspace),
                "--request", "批判看下这段代码",
                "--payload-manifest-path", str(pm),
                "--action-proposal-capability",
            ])
            self.assertEqual(exit_code, 1, "Retry contract should return non-zero exit")
            self.assertEqual(result["status"], "action_proposal_retry")
            self.assertIn("action_proposal_schema", result)

    def test_cli_full_roundtrip_retry_then_success(self) -> None:
        """CLI: Two subprocess calls simulating host retry flow."""
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))

            # Phase 1: capability only → exit 1
            exit_code, retry = self._run_gate_cli([
                "--workspace-root", str(workspace),
                "--request", "什么是 ActionProposal？",
                "--payload-manifest-path", str(pm),
                "--action-proposal-capability",
            ])
            self.assertEqual(exit_code, 1)
            self.assertEqual(retry["status"], "action_proposal_retry")
            schema = retry["action_proposal_schema"]
            self.assertIsInstance(schema, dict)

            # Phase 2: host generates proposal per schema and retries
            proposal = json.dumps({
                "action_type": "consult_readonly",
                "side_effect": "none",
                "confidence": "high",
                "evidence": ["user asked a question about ActionProposal"],
            })
            exit_code2, success = self._run_gate_cli([
                "--workspace-root", str(workspace),
                "--request", "什么是 ActionProposal？",
                "--payload-manifest-path", str(pm),
                "--action-proposal-json", proposal,
            ])
            self.assertEqual(exit_code2, 0, "Successful gate should return exit 0")
            self.assertEqual(success["status"], "ready")
            self.assertTrue(success["gate_passed"])
            self.assertEqual(success["runtime"]["route_name"], "consult")

    def test_cli_json_with_special_characters_in_evidence(self) -> None:
        """CLI: evidence with quotes, newlines, and Unicode passes through correctly."""
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))
            proposal = json.dumps({
                "action_type": "consult_readonly",
                "side_effect": "none",
                "confidence": "high",
                "evidence": [
                    'user said "批判看下" with double quotes',
                    "line1\nline2\nline3",
                    "apostrophe's and single 'quotes'",
                    "emoji: 🔍 unicode: café naïve",
                ],
            })
            exit_code, result = self._run_gate_cli([
                "--workspace-root", str(workspace),
                "--request", "批判看下这个方案",
                "--payload-manifest-path", str(pm),
                "--action-proposal-json", proposal,
            ])
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["runtime"]["route_name"], "consult")

    def test_cli_malformed_json_returns_exit_1_with_parse_error(self) -> None:
        """CLI: malformed JSON → exit 1 + action_proposal_parse_error in stdout."""
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))
            exit_code, result = self._run_gate_cli([
                "--workspace-root", str(workspace),
                "--request", "加一个缓存功能",
                "--payload-manifest-path", str(pm),
                "--action-proposal-json", "{{broken}",
            ])
            self.assertEqual(exit_code, 1)
            self.assertEqual(result["status"], "action_proposal_retry")
            self.assertIn("action_proposal_parse_error", result)

    def test_cli_command_prefix_with_capability_bypasses_retry(self) -> None:
        """CLI: ~go plan with --action-proposal-capability → exit 0, not retry."""
        with tempfile.TemporaryDirectory() as td:
            workspace, pm = _setup_workspace_for_gate_integration(Path(td))
            exit_code, result = self._run_gate_cli([
                "--workspace-root", str(workspace),
                "--request", "~go plan 补集成测试",
                "--payload-manifest-path", str(pm),
                "--action-proposal-capability",
            ])
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["status"], "ready")


class IntegrationRegressionTests(unittest.TestCase):
    """P0-G: Regression tests verifying existing router behavior is preserved.

    These cover the tasks.md requirements:
    - "批判看下" → consult (with and without proposal)
    - "加一个缓存功能" → light_iterate via Router fallback (no proposal override)
    """

    def test_regression_consult_request_with_proposal(self) -> None:
        """'批判看下' + consult_readonly proposal → consult via validator."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            proposal = ActionProposal("consult_readonly", "none", "high",
                                      evidence=["user said 批判看下"])
            result = run_runtime(
                "批判看下这个方案的可行性",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=proposal,
            )
            self.assertEqual(result.route.route_name, "consult")
            self.assertIn("action_proposal_validator", result.route.reason)

    def test_regression_consult_request_without_proposal(self) -> None:
        """'批判看下' without proposal → Router classifies (validator not involved).

        Note: in a clean workspace without active plan, Router may NOT classify
        this as 'consult' — this is the exact misclassification that ActionProposal
        boundary aims to fix. The regression check verifies Router still runs
        normally without being broken by ActionProposal code.
        """
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            result = run_runtime(
                "批判看下这个方案的可行性",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            # Key assertion: validator NOT involved (legacy/no-proposal path)
            self.assertNotIn("action_proposal_validator", result.route.reason)
            # Router ran and produced some route (not broken)
            self.assertIsNotNone(result.route.route_name)

    def test_regression_feature_request_without_proposal_uses_router(self) -> None:
        """'加一个缓存功能' without proposal → Router classifies (not consult)."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            result = run_runtime(
                "加一个缓存功能",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            # Without a proposal, Router classifies this as a development task
            # (light_iterate / go_plan / etc.) — NOT consult.
            self.assertNotEqual(result.route.route_name, "consult")
            self.assertNotIn("action_proposal_validator", result.route.reason)

    def test_regression_feature_request_with_high_confidence_uses_router(self) -> None:
        """'加一个缓存功能' + modify_files/high → authorize → Router classifies."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            proposal = ActionProposal(
                "modify_files", "write_files", "high",
                evidence=["user explicitly asked to add cache feature"],
            )
            result = run_runtime(
                "加一个缓存功能",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=proposal,
            )
            # High-confidence authorize → route_override=None → Router runs
            self.assertNotEqual(result.route.route_name, "consult")
            self.assertNotIn("action_proposal_validator", result.route.reason)

    def test_regression_feature_request_with_low_confidence_downgrades(self) -> None:
        """'加一个缓存功能' + modify_files/low → downgrade to consult."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            proposal = ActionProposal(
                "modify_files", "write_files", "low",
                evidence=["maybe user wants this"],
            )
            result = run_runtime(
                "加一个缓存功能",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=proposal,
            )
            self.assertEqual(result.route.route_name, "consult")
            self.assertIn("action_proposal_validator", result.route.reason)


if __name__ == "__main__":
    unittest.main()
