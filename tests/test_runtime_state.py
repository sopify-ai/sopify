from __future__ import annotations

from tests.runtime_test_support import *
from runtime.context_snapshot import (
    _collect_pending_items,
    _collect_run_handoff_conflicts,
    _provenance_status_for_reason,
    resolve_context_snapshot,
)
from runtime.state_invariants import validate_phase


class StateStoreInvariantTests(unittest.TestCase):
    def test_decision_write_requires_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)

            with self.assertRaises(InvariantViolationError):
                store.set_current_decision(
                    DecisionState(
                        schema_version="2",
                        decision_id="decision-1",
                        feature_key="runtime",
                        phase="",
                        status="pending",
                        decision_type="design_choice",
                        question="question",
                        summary="summary",
                        options=(
                            DecisionOption(
                                option_id="option_1",
                                title="option 1",
                                summary="summary",
                            ),
                        ),
                        created_at=iso_now(),
                        updated_at=iso_now(),
                    )
                )

    def test_clarification_write_requires_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)

            with self.assertRaises(InvariantViolationError):
                store.set_current_clarification(
                    ClarificationState(
                        clarification_id="clarify-1",
                        feature_key="runtime",
                        phase="",
                        status="pending",
                        summary="summary",
                        questions=("q1",),
                        missing_facts=("scope",),
                        created_at=iso_now(),
                        updated_at=iso_now(),
                    )
                )

    def test_decision_write_rejects_unsupported_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)

            with self.assertRaises(InvariantViolationError):
                store.set_current_decision(
                    DecisionState(
                        schema_version="2",
                        decision_id="decision-1",
                        feature_key="runtime",
                        phase="legacy_phase",
                        status="pending",
                        decision_type="design_choice",
                        question="question",
                        summary="summary",
                        options=(
                            DecisionOption(
                                option_id="option_1",
                                title="option 1",
                                summary="summary",
                            ),
                        ),
                        created_at=iso_now(),
                        updated_at=iso_now(),
                    )
                )

    def test_clarification_write_rejects_unsupported_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)

            with self.assertRaises(InvariantViolationError):
                store.set_current_clarification(
                    ClarificationState(
                        clarification_id="clarify-1",
                        feature_key="runtime",
                        phase="legacy_phase",
                        status="pending",
                        summary="summary",
                        questions=("q1",),
                        missing_facts=("scope",),
                        created_at=iso_now(),
                        updated_at=iso_now(),
                    )
                )

    def test_develop_clarification_write_requires_complete_resume_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)

            with self.assertRaises(InvariantViolationError):
                store.set_current_clarification(
                    ClarificationState(
                        clarification_id="clarify-1",
                        feature_key="runtime",
                        phase="develop",
                        status="pending",
                        summary="summary",
                        questions=("q1",),
                        missing_facts=("scope",),
                        resume_context={"resume_after": "continue_host_develop"},
                        created_at=iso_now(),
                        updated_at=iso_now(),
                    )
                )

    def test_execution_gate_decision_write_requires_complete_resume_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)

            with self.assertRaises(InvariantViolationError):
                store.set_current_decision(
                    DecisionState(
                        schema_version="2",
                        decision_id="decision-1",
                        feature_key="runtime",
                        phase="execution_gate",
                        status="pending",
                        decision_type="execution_gate_missing_info",
                        question="question",
                        summary="summary",
                        options=(
                            DecisionOption(
                                option_id="option_1",
                                title="option 1",
                                summary="summary",
                            ),
                        ),
                        trigger_reason="missing_info",
                        created_at=iso_now(),
                        updated_at=iso_now(),
                    )
                )

    def test_paired_host_facing_truth_write_stamps_shared_resolution_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            resolution_id = "resolution-123"
            run_state = RunState(
                run_id="run-1",
                status="active",
                stage="plan_generated",
                route_name="workflow",
                title="Runtime",
                created_at=iso_now(),
                updated_at=iso_now(),
            )
            handoff = RuntimeHandoff(
                schema_version="1",
                route_name="workflow",
                run_id="run-1",
                handoff_kind="plan",
                required_host_action="review_or_execute_plan",
            )

            stored_run, stored_handoff = store.set_host_facing_truth(
                run_state=run_state,
                handoff=handoff,
                resolution_id=resolution_id,
                truth_kind=HOST_FACING_TRUTH_WRITE_KINDS[0],
            )

            self.assertEqual(stored_run.resolution_id, resolution_id)
            self.assertEqual(stored_handoff.resolution_id, resolution_id)
            self.assertEqual(store.get_current_run().resolution_id, resolution_id)
            self.assertEqual(store.get_current_handoff().resolution_id, resolution_id)

    def test_paired_host_facing_truth_write_rejects_scope_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            run_state = RunState(
                run_id="run-1",
                status="active",
                stage="plan_generated",
                route_name="workflow",
                title="Runtime",
                created_at=iso_now(),
                updated_at=iso_now(),
            )
            handoff = RuntimeHandoff(
                schema_version="1",
                route_name="workflow",
                run_id="run-1",
                handoff_kind="plan",
                required_host_action="review_or_execute_plan",
            )

            with self.assertRaises(InvariantViolationError):
                store.set_host_facing_truth(
                    run_state=run_state,
                    handoff=handoff,
                    resolution_id="resolution-123",
                    truth_kind="update_active_run",
                )


class ContextSnapshotTests(unittest.TestCase):
    def test_provenance_status_reason_classifier_is_stable(self) -> None:
        self.assertEqual(_provenance_status_for_reason("phase_missing"), "provenance_missing")
        self.assertEqual(_provenance_status_for_reason("develop_clarification_owner_run_mismatch"), "provenance_mismatch")
        self.assertEqual(_provenance_status_for_reason("decision_orphaned_from_active_run"), "orphaned")
        self.assertEqual(_provenance_status_for_reason("invalid_json"), "invalid_payload")

    def test_collect_run_handoff_conflicts_supports_legacy_and_detects_split_brain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            no_conflicts = _collect_run_handoff_conflicts(
                store=store,
                scope="session",
                current_run=RunState(
                    run_id="run-1",
                    status="active",
                    stage="plan_generated",
                    route_name="workflow",
                    title="Runtime",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                ),
                current_handoff=RuntimeHandoff(
                    schema_version="1",
                    route_name="workflow",
                    run_id="run-1",
                    handoff_kind="plan",
                    required_host_action="review_or_execute_plan",
                ),
                current_clarification=None,
                current_decision=None,
            )
            self.assertFalse(no_conflicts)

            conflicts = _collect_run_handoff_conflicts(
                store=store,
                scope="session",
                current_run=RunState(
                    run_id="run-1",
                    status="active",
                    stage="decision_pending",
                    route_name="workflow",
                    title="Runtime",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    resolution_id="resolution-a",
                ),
                current_handoff=RuntimeHandoff(
                    schema_version="1",
                    route_name="workflow",
                    run_id="run-1",
                    handoff_kind="plan",
                    required_host_action="confirm_decision",
                ),
                current_clarification=None,
                current_decision=None,
            )

            self.assertEqual(
                [detail.code for detail in conflicts],
                ["resolution_id_mixed_presence", "decision_missing_for_pending_handoff"],
            )

    def test_state_conflict_classification_is_not_writer_invariant_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            with self.assertRaises(InvariantViolationError):
                validate_phase(state_kind="current_decision", phase="")

            conflicts = _collect_run_handoff_conflicts(
                store=store,
                scope="session",
                current_run=RunState(
                    run_id="run-1",
                    status="active",
                    stage="decision_pending",
                    route_name="workflow",
                    title="Runtime",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                ),
                current_handoff=RuntimeHandoff(
                    schema_version="1",
                    route_name="workflow",
                    run_id="run-1",
                    handoff_kind="plan",
                    required_host_action="answer_questions",
                ),
                current_clarification=None,
                current_decision=DecisionState(
                    schema_version="2",
                    decision_id="decision-1",
                    feature_key="runtime",
                    phase="design",
                    status="pending",
                    decision_type="design_choice",
                    question="继续哪个选项？",
                    summary="pending decision",
                    options=(DecisionOption(option_id="option_1", title="option 1", summary="summary"),),
                    created_at=iso_now(),
                    updated_at=iso_now(),
                ),
            )

            self.assertEqual(
                [detail.code for detail in conflicts],
                ["run_stage_handoff_mismatch", "clarification_missing_for_pending_handoff"],
            )

    def test_missing_phase_decision_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            review_store = StateStore(config, session_id="session-a")
            global_store = StateStore(config)
            review_store.ensure()
            global_store.ensure()

            review_store.current_decision_path.write_text(
                json.dumps(
                    {
                        "schema_version": "2",
                        "decision_id": "decision-1",
                        "feature_key": "runtime",
                        "status": "pending",
                        "decision_type": "design_choice",
                        "question": "继续哪个选项？",
                        "summary": "missing phase",
                        "options": [{"option_id": "option_1", "title": "option 1", "summary": "summary"}],
                        "created_at": iso_now(),
                        "updated_at": iso_now(),
                    }
                ),
                encoding="utf-8",
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=review_store,
                global_store=global_store,
            )

            self.assertIsNone(snapshot.current_decision)
            self.assertEqual(len(snapshot.quarantined_items), 1)
            self.assertEqual(snapshot.quarantined_items[0].reason, "phase_missing")

    def test_design_decision_missing_owner_session_or_checkpoint_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            review_store = StateStore(config, session_id="session-a")
            global_store = StateStore(config)
            review_store.ensure()
            global_store.ensure()

            review_store.current_decision_path.write_text(
                json.dumps(
                    {
                        "schema_version": "2",
                        "decision_id": "decision-1",
                        "feature_key": "runtime",
                        "phase": "design",
                        "status": "pending",
                        "decision_type": "design_choice",
                        "question": "继续哪个选项？",
                        "summary": "missing design provenance",
                        "options": [{"option_id": "option_1", "title": "option 1", "summary": "summary"}],
                        "checkpoint": {"checkpoint_id": "decision-other", "title": "Decision", "message": "msg", "fields": []},
                        "resume_context": {},
                        "created_at": iso_now(),
                        "updated_at": iso_now(),
                    }
                ),
                encoding="utf-8",
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=review_store,
                global_store=global_store,
            )

            self.assertIsNone(snapshot.current_decision)
            self.assertEqual(len(snapshot.quarantined_items), 1)
            self.assertEqual(snapshot.quarantined_items[0].reason, "design_decision_checkpoint_mismatch")

    def test_develop_clarification_owner_binding_mismatch_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            review_store = StateStore(config, session_id="session-b")
            global_store = StateStore(config)
            review_store.ensure()
            global_store.ensure()

            global_store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="clarification_pending",
                    route_name="resume_active",
                    title="Develop clarification",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id="plan-runtime",
                    plan_path=".sopify-skills/plan/runtime",
                    owner_session_id="session-a",
                    owner_run_id="owner-run-1",
                )
            )
            global_store.current_clarification_path.write_text(
                json.dumps(
                    {
                        "clarification_id": "clarify-1",
                        "feature_key": "runtime",
                        "phase": "develop",
                        "status": "pending",
                        "summary": "clarify develop scope",
                        "questions": ["需要确认哪个权限边界？"],
                        "missing_facts": ["auth_boundary"],
                        "resume_context": {
                            "checkpoint_id": "clarify-1",
                            "owner_session_id": "session-a",
                            "owner_run_id": "owner-run-other",
                            "active_run_stage": "clarification_pending",
                            "current_plan_path": ".sopify-skills/plan/runtime",
                            "task_refs": [],
                            "changed_files": [],
                            "working_summary": "clarify develop scope",
                            "verification_todo": [],
                            "resume_after": "continue_host_develop",
                        },
                        "created_at": iso_now(),
                        "updated_at": iso_now(),
                    }
                ),
                encoding="utf-8",
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=review_store,
                global_store=global_store,
            )

            self.assertIsNone(snapshot.current_clarification)
            self.assertEqual(len(snapshot.quarantined_items), 1)
            self.assertEqual(snapshot.quarantined_items[0].reason, "develop_clarification_owner_run_mismatch")

    def test_develop_clarification_missing_resume_contract_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            review_store = StateStore(config, session_id="session-b")
            global_store = StateStore(config)
            review_store.ensure()
            global_store.ensure()

            global_store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="clarification_pending",
                    route_name="resume_active",
                    title="Develop clarification",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id="plan-runtime",
                    plan_path=".sopify-skills/plan/runtime",
                    owner_session_id="session-a",
                    owner_run_id="owner-run-1",
                )
            )
            global_store.current_clarification_path.write_text(
                json.dumps(
                    {
                        "clarification_id": "clarify-1",
                        "feature_key": "runtime",
                        "phase": "develop",
                        "status": "pending",
                        "summary": "resume contract missing",
                        "questions": ["q1"],
                        "missing_facts": ["scope"],
                        "resume_context": {
                            "checkpoint_id": "clarify-1",
                            "owner_session_id": "session-a",
                            "owner_run_id": "owner-run-1",
                            "resume_after": "continue_host_develop",
                        },
                        "created_at": iso_now(),
                        "updated_at": iso_now(),
                    }
                ),
                encoding="utf-8",
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=review_store,
                global_store=global_store,
            )

            self.assertIsNone(snapshot.current_clarification)
            self.assertEqual(len(snapshot.quarantined_items), 1)
            self.assertEqual(snapshot.quarantined_items[0].reason, "develop_resume_context_required_fields_missing")

    def test_unsupported_phase_clarification_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config, session_id="session-a")
            store.ensure()
            store.current_clarification_path.write_text(
                '{\n'
                '  "clarification_id": "clarify-1",\n'
                '  "feature_key": "runtime",\n'
                '  "phase": "legacy_phase",\n'
                '  "status": "pending",\n'
                '  "summary": "summary",\n'
                '  "questions": ["q1"],\n'
                '  "missing_facts": ["scope"]\n'
                '}\n',
                encoding="utf-8",
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=store,
                global_store=store,
            )

            self.assertIsNone(snapshot.current_clarification)
            self.assertEqual(len(snapshot.quarantined_items), 1)
            self.assertEqual(snapshot.quarantined_items[0].reason, "phase_unsupported")

    def test_resolution_id_mismatch_enters_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="plan_generated",
                    route_name="workflow",
                    title="Runtime",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    resolution_id="resolution-a",
                )
            )
            store.set_current_handoff(
                RuntimeHandoff(
                    schema_version="1",
                    route_name="workflow",
                    run_id="run-1",
                    handoff_kind="plan",
                    required_host_action="review_or_execute_plan",
                    resolution_id="resolution-b",
                )
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=store,
                global_store=store,
            )

            self.assertTrue(snapshot.is_conflict)
            self.assertEqual(snapshot.conflict_code, "resolution_id_mismatch")
            self.assertEqual(snapshot.conflict_items[0].state_scope, "global")

    def test_missing_resolution_ids_on_both_run_and_handoff_stay_legacy_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="plan_generated",
                    route_name="workflow",
                    title="Runtime",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                )
            )
            store.set_current_handoff(
                RuntimeHandoff(
                    schema_version="1",
                    route_name="workflow",
                    run_id="run-1",
                    handoff_kind="plan",
                    required_host_action="review_or_execute_plan",
                )
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=store,
                global_store=store,
            )

            self.assertFalse(snapshot.is_conflict)

    def test_cross_session_develop_decision_survives_when_owner_binding_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            review_store = StateStore(config, session_id="session-b")
            global_store = StateStore(config)
            review_store.ensure()
            global_store.ensure()

            global_store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="decision_pending",
                    route_name="resume_active",
                    title="Develop decision",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id="plan-runtime",
                    plan_path=".sopify-skills/plan/runtime",
                    owner_session_id="session-a",
                    owner_run_id="owner-run-1",
                )
            )
            global_store.set_current_decision(
                DecisionState(
                    schema_version="2",
                    decision_id="decision-1",
                    feature_key="runtime",
                    phase="develop",
                    status="pending",
                    decision_type="develop_choice",
                    question="继续哪个开发方案？",
                    summary="develop checkpoint should survive across sessions",
                    options=(DecisionOption(option_id="option_1", title="option 1", summary="summary"),),
                    resume_context={
                        "resume_after": "continue_host_develop",
                        "active_run_stage": "executing",
                        "current_plan_path": ".sopify-skills/plan/runtime",
                        "task_refs": ["2.1"],
                        "changed_files": ["runtime/engine.py"],
                        "working_summary": "develop checkpoint should survive across sessions",
                        "verification_todo": ["补 cross-session checkpoint 回归"],
                    },
                    created_at=iso_now(),
                    updated_at=iso_now(),
                )
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=review_store,
                global_store=global_store,
            )

            self.assertIsNotNone(snapshot.current_decision)
            self.assertEqual(snapshot.current_decision.phase, "develop")
            self.assertFalse(snapshot.quarantined_items)

    def test_execution_gate_decision_requires_connected_gate_topology(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            review_store = StateStore(config, session_id="session-b")
            global_store = StateStore(config)
            review_store.ensure()
            global_store.ensure()

            global_store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="decision_pending",
                    route_name="resume_active",
                    title="Execution gate decision",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id="plan-runtime",
                    plan_path=".sopify-skills/plan/runtime",
                    execution_gate=ExecutionGate(
                        gate_status="ready",
                        blocking_reason="none",
                        plan_completion="ready",
                        next_required_action="continue_host_develop",
                    ),
                    owner_session_id="session-a",
                    owner_run_id="owner-run-1",
                )
            )
            global_store.set_current_decision(
                DecisionState(
                    schema_version="2",
                    decision_id="decision-1",
                    feature_key="runtime",
                    phase="execution_gate",
                    status="pending",
                    decision_type="execution_gate_missing_info",
                    question="是否继续执行？",
                    summary="gate topology must stay connected",
                    options=(DecisionOption(option_id="option_1", title="option 1", summary="summary"),),
                    trigger_reason="missing_info",
                    resume_context={
                        "resume_after": "continue_host_develop",
                        "active_run_stage": "decision_pending",
                        "current_plan_path": ".sopify-skills/plan/runtime",
                        "task_refs": [],
                        "changed_files": [],
                        "working_summary": "gate topology must stay connected",
                        "verification_todo": [],
                    },
                    created_at=iso_now(),
                    updated_at=iso_now(),
                )
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=review_store,
                global_store=global_store,
            )

            self.assertIsNone(snapshot.current_decision)
            self.assertEqual(len(snapshot.quarantined_items), 1)
            self.assertEqual(snapshot.quarantined_items[0].reason, "execution_gate_decision_topology_disconnected")

    def test_execution_gate_decision_missing_resume_contract_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            review_store = StateStore(config, session_id="session-b")
            global_store = StateStore(config)
            review_store.ensure()
            global_store.ensure()

            global_store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="decision_pending",
                    route_name="resume_active",
                    title="Execution gate decision",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id="plan-runtime",
                    plan_path=".sopify-skills/plan/runtime",
                    execution_gate=ExecutionGate(
                        gate_status="decision_required",
                        blocking_reason="missing_info",
                        plan_completion="blocked",
                        next_required_action="confirm_decision",
                    ),
                    owner_session_id="session-a",
                    owner_run_id="owner-run-1",
                )
            )
            global_store.current_decision_path.write_text(
                json.dumps(
                    {
                        "schema_version": "2",
                        "decision_id": "decision-1",
                        "feature_key": "runtime",
                        "phase": "execution_gate",
                        "status": "pending",
                        "decision_type": "execution_gate_missing_info",
                        "question": "是否继续执行？",
                        "summary": "resume contract missing",
                        "options": [{"option_id": "option_1", "title": "option 1", "summary": "summary"}],
                        "trigger_reason": "missing_info",
                        "resume_context": {
                            "checkpoint_id": "decision-1",
                            "owner_session_id": "session-a",
                            "owner_run_id": "owner-run-1",
                            "resume_after": "continue_host_develop",
                        },
                        "created_at": iso_now(),
                        "updated_at": iso_now(),
                    }
                ),
                encoding="utf-8",
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=review_store,
                global_store=global_store,
            )

            self.assertIsNone(snapshot.current_decision)
            self.assertEqual(len(snapshot.quarantined_items), 1)
            self.assertEqual(snapshot.quarantined_items[0].reason, "develop_resume_context_required_fields_missing")

    def test_run_stage_handoff_mismatch_enters_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="decision_pending",
                    route_name="workflow",
                    title="Runtime",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                )
            )
            store.set_current_handoff(
                RuntimeHandoff(
                    schema_version="1",
                    route_name="workflow",
                    run_id="run-1",
                    handoff_kind="plan",
                    required_host_action="review_or_execute_plan",
                )
            )
            store.set_current_decision(
                DecisionState(
                    schema_version="2",
                    decision_id="decision-1",
                    feature_key="runtime",
                    phase="design",
                    status="pending",
                    decision_type="design_choice",
                    question="继续哪个选项？",
                    summary="pending decision",
                    options=(DecisionOption(option_id="option_1", title="option 1", summary="summary"),),
                    created_at=iso_now(),
                    updated_at=iso_now(),
                )
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=store,
                global_store=store,
            )

            self.assertTrue(snapshot.is_conflict)
            self.assertEqual(snapshot.conflict_code, "run_stage_handoff_mismatch")

    def test_answer_questions_allows_preserved_confirmed_decision_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            store.set_current_handoff(
                RuntimeHandoff(
                    schema_version="1",
                    route_name="clarification_pending",
                    run_id="run-1",
                    handoff_kind="checkpoint",
                    required_host_action="answer_questions",
                )
            )
            store.set_current_clarification(
                ClarificationState(
                    clarification_id="clar-1",
                    feature_key="runtime",
                    phase="analyze",
                    status="pending",
                    summary="need facts",
                    questions=("缺少哪类事实？",),
                    missing_facts=("fact",),
                    request_text="补充事实",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                )
            )
            store.set_current_decision(
                confirm_decision(
                    DecisionState(
                        schema_version="2",
                        decision_id="decision-1",
                        feature_key="runtime",
                        phase="design",
                        status="pending",
                        decision_type="design_choice",
                        question="继续哪个选项？",
                        summary="confirmed decision should be preserved during clarification",
                        options=(DecisionOption(option_id="option_1", title="option 1", summary="summary"),),
                        created_at=iso_now(),
                        updated_at=iso_now(),
                    ),
                    option_id="option_1",
                    source="text",
                    raw_input="1",
                )
            )

            snapshot = resolve_context_snapshot(
                config=config,
                review_store=store,
                global_store=store,
            )

            self.assertFalse(snapshot.is_conflict)
            self.assertIsNotNone(snapshot.current_clarification)
            self.assertIsNotNone(snapshot.current_decision)
            self.assertEqual(snapshot.current_decision.status, "confirmed")
