from __future__ import annotations

from dataclasses import replace

from tests.runtime_test_support import *
from runtime.engine import _advance_planning_route


_FRONT_MATTER_RE = re.compile(r"\A---\n(?P<front>.*?)\n---\n", re.DOTALL)


def _archive_current_plan_action() -> ActionProposal:
    return ActionProposal(
        "archive_plan",
        "write_files",
        "high",
        evidence=("test: archive current plan",),
        archive_subject=ArchiveSubjectProposal(
            ref_kind="current_plan",
            source="current_plan",
            allow_current_plan_fallback=True,
        ),
    )


def _propose_plan_action() -> ActionProposal:
    """Create an ActionProposal that authorizes plan materialization."""
    return ActionProposal(
        "propose_plan",
        "write_plan_package",
        "high",
        evidence=("test: authorized plan creation",),
    )


def _archive_plan_id_proposal(plan_id: str) -> ActionProposal:
    return ActionProposal(
        "archive_plan",
        "write_files",
        "high",
        evidence=("test: archive explicit plan",),
        archive_subject=ArchiveSubjectProposal(
            ref_kind="plan_id",
            ref_value=plan_id,
            source="host_explicit",
        ),
    )


def _archive_path_proposal(path: str) -> ActionProposal:
    return ActionProposal(
        "archive_plan",
        "write_files",
        "high",
        evidence=("test: archive explicit path",),
        archive_subject=ArchiveSubjectProposal(
            ref_kind="path",
            ref_value=path,
            source="host_explicit",
        ),
    )


def _load_markdown_front_matter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(text)
    if match is None:
        raise AssertionError(f"Missing front matter: {path}")
    metadata = load_yaml(match.group("front"))
    if not isinstance(metadata, dict):
        raise AssertionError(f"Invalid front matter payload: {path}")
    return metadata


class EngineIntegrationTests(unittest.TestCase):
    def test_session_review_state_is_isolated_between_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            run_runtime(
                "实现 runtime plugin bridge",
                workspace_root=workspace,
                session_id="session-a",
                user_home=workspace / "home",
                action_proposal=_propose_plan_action(),
            )
            run_runtime(
                "实现 runtime gate receipt compaction",
                workspace_root=workspace,
                session_id="session-b",
                user_home=workspace / "home",
                action_proposal=_propose_plan_action(),
            )

            config = load_runtime_config(workspace)
            session_a_store = StateStore(config, session_id="session-a")
            session_b_store = StateStore(config, session_id="session-b")
            global_store = StateStore(config)

            self.assertIsNotNone(session_a_store.get_current_plan())
            self.assertIsNotNone(session_b_store.get_current_plan())
            self.assertNotEqual(
                session_a_store.get_current_plan().plan_id,
                session_b_store.get_current_plan().plan_id,
            )

    def test_engine_enters_clarification_before_plan_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            result = run_runtime("~go plan 优化一下", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(result.route.route_name, "clarification_pending")
            self.assertIsNone(result.plan_artifact)
            self.assertIsNotNone(result.recovered_context.current_clarification)
            self.assertEqual(result.handoff.handoff_kind, "clarification")
            self.assertEqual(result.handoff.required_host_action, "answer_questions")
            self.assertIn("clarification_form", result.handoff.artifacts)
            self.assertEqual(result.handoff.artifacts["clarification_form"]["template_id"], "scope_clarify")
            self.assertEqual(result.handoff.artifacts["clarification_submission_state"]["status"], "empty")
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_clarification.json").exists())
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_plan.json").exists())

    def test_engine_resumes_planning_after_clarification_answer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime("~go plan 优化一下", workspace_root=workspace, user_home=workspace / "home")

            result = run_runtime(
                "目标是 runtime/router.py 和 runtime/engine.py，预期结果是接入 clarification_pending 状态骨架。",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            self.assertEqual(result.route.route_name, "plan_only")
            self.assertIsNotNone(result.plan_artifact)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_clarification.json").exists())
            self.assertTrue((workspace / result.plan_artifact.path / "tasks.md").exists())

    def test_advance_planning_route_fail_closed_when_workflow_policy_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            routed, plan_artifact, notes, _ = _advance_planning_route(
                RouteDecision(
                    route_name="workflow",
                    request_text="实现 runtime plugin bridge",
                    reason="legacy route payload without plan_package_policy",
                    complexity="complex",
                    plan_level="standard",
                ),
                state_store=store,
                config=config,
                kb_artifact=None,
            )

            self.assertEqual(routed.route_name, "plan_only")
            self.assertIsNotNone(plan_artifact)
            self.assertIsNotNone(store.get_current_plan())
            self.assertEqual(_plan_dir_count(workspace), 1)
            self.assertTrue(any("Plan scaffold created" in note for note in notes))

    def test_exec_plan_is_blocked_while_clarification_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime("~go plan 优化一下", workspace_root=workspace, user_home=workspace / "home")

            result = run_runtime("~go exec", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(result.route.route_name, "clarification_pending")
            self.assertIsNone(result.plan_artifact)
            self.assertEqual(result.handoff.required_host_action, "answer_questions")
            self.assertEqual(result.recovered_context.current_run.stage, "clarification_pending")

    def test_exec_plan_is_unavailable_without_active_recovery_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            result = run_runtime("~go exec", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(result.route.route_name, "exec_plan")
            self.assertIsNone(result.recovered_context.current_plan)
            self.assertIsNone(result.handoff)
            self.assertTrue(any("~go exec" in note for note in result.notes))
            rendered = render_runtime_output(
                result,
                brand="demo-ai",
                language="zh-CN",
                title_color="none",
                use_color=False,
            )
            self.assertIn("高级恢复入口", rendered)
            self.assertIn("Next: 仅在已有活动 plan 或恢复态时使用 ~go exec", rendered)

    def test_exec_plan_respects_execution_gate_before_develop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            run_runtime("1", workspace_root=workspace, user_home=workspace / "home")

            result = run_runtime("~go exec", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(result.route.route_name, "exec_plan")
            self.assertEqual(result.recovered_context.current_run.stage, "plan_generated")
            self.assertEqual(result.recovered_context.current_run.execution_gate.gate_status, "blocked")
            self.assertEqual(result.recovered_context.current_run.execution_gate.blocking_reason, "missing_info")
            self.assertIsNone(result.handoff)

    def test_session_review_plan_promotes_to_global_execution_truth_on_exec(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config, _, _ = _prepare_ready_plan_state(workspace, session_id="session-a")

            result = run_runtime(
                "~go exec",
                workspace_root=workspace,
                session_id="session-a",
                user_home=workspace / "home",
            )

            global_store = StateStore(config)
            global_run = global_store.get_current_run()
            self.assertIn(result.route.route_name, {"exec_plan", "resume_active"})
            self.assertIsNotNone(global_store.get_current_plan())
            self.assertEqual(global_run.owner_session_id, "session-a")
            self.assertEqual(global_run.owner_host, "runtime")
            self.assertEqual(global_run.owner_run_id, global_run.run_id)
            self.assertTrue(any("Promoted session review state to global execution truth" in note for note in result.notes))

    def test_soft_ownership_warning_is_emitted_when_promotion_replaces_existing_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config, _, _ = _prepare_ready_plan_state(workspace, session_id="session-a")
            run_runtime(
                "~go exec",
                workspace_root=workspace,
                session_id="session-a",
                user_home=workspace / "home",
            )
            global_store = StateStore(config)
            global_store.clear_current_plan()
            _prepare_ready_plan_state(
                workspace,
                request_text="实现 runtime plugin bridge",
                session_id="session-b",
            )

            result = run_runtime(
                "~go exec",
                workspace_root=workspace,
                session_id="session-b",
                user_home=workspace / "home",
            )

            global_run = global_store.get_current_run()
            self.assertIn(result.route.route_name, {"exec_plan", "resume_active"})
            self.assertTrue(any("Soft ownership warning" in note for note in result.notes))
            self.assertIsNotNone(global_run)
            self.assertEqual(global_run.owner_session_id, "session-b")

    def test_execution_gate_promotion_warns_when_replacing_other_session_global_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config, _, _ = _prepare_ready_plan_state(workspace, request_text="session-a plan", session_id="session-a")
            run_runtime(
                "~go exec",
                workspace_root=workspace,
                session_id="session-a",
                user_home=workspace / "home",
            )

            session_b_store = StateStore(config, session_id="session-b")
            plan_artifact = create_plan_scaffold("调整 auth boundary", config=config, level="standard")
            _rewrite_background_scope(
                workspace,
                plan_artifact,
                scope_lines=("runtime/engine.py", "runtime/engine.py, runtime/router.py"),
                risk_lines=("本轮会调整认证与权限边界", "需要先明确批准路径"),
            )
            gate = evaluate_execution_gate(
                decision=RouteDecision(
                    route_name="workflow",
                    request_text="调整 auth boundary",
                    reason="test",
                    complexity="complex",
                    plan_level="standard",
                    candidate_skill_ids=("develop",),
                ),
                plan_artifact=plan_artifact,
                current_clarification=None,
                current_decision=None,
                config=config,
            )
            session_b_store.set_current_plan(plan_artifact)
            session_b_store.set_current_run(
                RunState(
                    run_id="run-b",
                    status="active",
                    stage="ready_for_execution",
                    route_name="workflow",
                    title=plan_artifact.title,
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id=plan_artifact.plan_id,
                    plan_path=plan_artifact.path,
                    execution_gate=gate,
                )
            )

            routed, resolved_plan, notes, _ = _advance_planning_route(
                RouteDecision(
                    route_name="workflow",
                    request_text=f"分析下 {plan_artifact.plan_id} 是否可以执行",
                    reason="test",
                    complexity="medium",
                    plan_package_policy="authorized_only",
                    capture_mode="summary",
                ),
                state_store=session_b_store,
                config=config,
                kb_artifact=None,
            )

            global_run = StateStore(config).get_current_run()
            self.assertEqual(routed.route_name, "decision_pending")
            self.assertIsNotNone(resolved_plan)
            self.assertTrue(any("Soft ownership warning" in note for note in notes))
            self.assertIsNotNone(global_run)
            self.assertEqual(global_run.owner_session_id, "session-b")

    def test_cancel_active_clears_session_active_plan_binding_checkpoint_without_touching_global_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config, _, _ = _prepare_ready_plan_state(workspace, session_id="session-a")
            run_runtime(
                "~go exec",
                workspace_root=workspace,
                session_id="session-a",
                user_home=workspace / "home",
            )
            run_runtime(
                "实现 runtime plugin bridge",
                workspace_root=workspace,
                session_id="session-b",
                user_home=workspace / "home",
            )

            result = run_runtime(
                "取消",
                workspace_root=workspace,
                session_id="session-b",
                user_home=workspace / "home",
            )

            global_store = StateStore(config)
            review_store = StateStore(config, session_id="session-b")
            self.assertEqual(result.route.route_name, "cancel_active")
            self.assertIsNotNone(global_store.get_current_run())
            self.assertIsNotNone(global_store.get_current_plan())
            self.assertIsNone(review_store.get_current_run())
            self.assertIsNone(review_store.get_current_decision())
            self.assertTrue(any("Decision checkpoint cancelled" in note for note in result.notes))

    def test_cancel_active_clears_only_session_review_when_global_execution_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config, _, _ = _prepare_ready_plan_state(workspace, session_id="session-a")

            result = run_runtime(
                "取消",
                workspace_root=workspace,
                session_id="session-a",
                user_home=workspace / "home",
            )

            global_store = StateStore(config)
            review_store = StateStore(config, session_id="session-a")
            self.assertEqual(result.route.route_name, "cancel_active")
            self.assertIsNone(global_store.get_current_run())
            self.assertIsNone(global_store.get_current_plan())
            self.assertIsNone(review_store.get_current_run())
            self.assertIsNone(review_store.get_current_plan())
            self.assertTrue(any("Session review flow cleared" in note for note in result.notes))

    def test_state_conflict_is_visible_and_cancel_can_clear_negotiation_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            store.set_current_clarification(
                ClarificationState(
                    clarification_id="clarify-1",
                    feature_key="runtime",
                    phase="analyze",
                    status="pending",
                    summary="pending clarification",
                    questions=("q1",),
                    missing_facts=("scope",),
                    created_at=iso_now(),
                    updated_at=iso_now(),
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

            conflicted = run_runtime("看看状态", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(conflicted.route.route_name, "state_conflict")
            self.assertEqual(conflicted.handoff.required_host_action, "resolve_state_conflict")
            self.assertEqual(conflicted.recovered_context.state_conflict["code"], "multiple_pending_checkpoints")
            rendered_conflict = render_runtime_output(
                conflicted,
                brand="demo-ai",
                language="zh-CN",
                title_color="none",
                use_color=False,
            )
            self.assertIn("状态冲突", rendered_conflict)
            self.assertIn("取消 / 强制取消", rendered_conflict)
            self.assertNotIn("~go abort", rendered_conflict)

            cleared = run_runtime("取消", workspace_root=workspace, user_home=workspace / "home")
            after_store = StateStore(load_runtime_config(workspace))

            self.assertEqual(cleared.route.route_name, "state_conflict")
            self.assertEqual(cleared.route.active_run_action, "abort_conflict")
            self.assertEqual(cleared.handoff.required_host_action, "continue_host_develop")
            self.assertFalse(cleared.recovered_context.state_conflict)
            self.assertIsNone(after_store.get_current_clarification())
            self.assertIsNone(after_store.get_current_decision())
            rendered_cleared = render_runtime_output(
                cleared,
                brand="demo-ai",
                language="zh-CN",
                title_color="none",
                use_color=False,
            )
            self.assertIn("已放弃当前协商并恢复到稳定主线", rendered_cleared)
            self.assertIn("Next: 在宿主会话中继续执行后续阶段", rendered_cleared)
            self.assertNotIn("~go abort", rendered_cleared)

    def test_state_conflict_surfaces_handoff_pending_kind_mismatch_before_generic_multiple_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            store.set_current_handoff(
                RuntimeHandoff(
                    schema_version="1",
                    route_name="decision_pending",
                    run_id="run-1",
                    handoff_kind="checkpoint",
                    required_host_action="confirm_decision",
                    artifacts={},
                )
            )
            store.set_current_clarification(
                ClarificationState(
                    clarification_id="clarify-1",
                    feature_key="runtime",
                    phase="analyze",
                    status="pending",
                    summary="pending clarification",
                    questions=("q1",),
                    missing_facts=("scope",),
                    created_at=iso_now(),
                    updated_at=iso_now(),
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

            conflicted = run_runtime("看看状态", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(conflicted.route.route_name, "state_conflict")
            self.assertEqual(conflicted.handoff.required_host_action, "resolve_state_conflict")
            self.assertEqual(conflicted.recovered_context.state_conflict["code"], "pending_checkpoint_handoff_mismatch")

    def test_state_conflict_abort_preserves_confirmed_decision_and_stable_plan_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            plan_artifact = create_plan_scaffold("补 runtime 状态机 hotfix", config=config, level="standard")
            store.set_current_plan(plan_artifact)
            store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="plan_generated",
                    route_name="workflow",
                    title=plan_artifact.title,
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id=plan_artifact.plan_id,
                    plan_path=plan_artifact.path,
                )
            )
            store.set_current_clarification(
                ClarificationState(
                    clarification_id="clarify-1",
                    feature_key="runtime",
                    phase="analyze",
                    status="pending",
                    summary="pending clarification",
                    questions=("q1",),
                    missing_facts=("scope",),
                    created_at=iso_now(),
                    updated_at=iso_now(),
                )
            )
            confirmed_decision = confirm_decision(
                DecisionState(
                    schema_version="2",
                    decision_id="decision-1",
                    feature_key="runtime",
                    phase="design",
                    status="pending",
                    decision_type="design_choice",
                    question="继续哪个选项？",
                    summary="confirmed decision should survive abort cleanup",
                    options=(DecisionOption(option_id="option_1", title="option 1", summary="summary"),),
                    created_at=iso_now(),
                    updated_at=iso_now(),
                ),
                option_id="option_1",
                source="text",
                raw_input="1",
            )
            store.set_current_decision(confirmed_decision)

            conflicted = run_runtime("看看状态", workspace_root=workspace, user_home=workspace / "home")
            self.assertEqual(conflicted.route.route_name, "state_conflict")
            self.assertEqual(conflicted.recovered_context.state_conflict["code"], "multiple_pending_checkpoints")

            cleared = run_runtime("取消", workspace_root=workspace, user_home=workspace / "home")
            after_store = StateStore(load_runtime_config(workspace))
            surviving_decision = after_store.get_current_decision()
            surviving_run = after_store.get_current_run()

            self.assertEqual(cleared.route.route_name, "state_conflict")
            self.assertEqual(cleared.route.active_run_action, "abort_conflict")
            self.assertFalse(cleared.recovered_context.state_conflict)
            self.assertIsNone(after_store.get_current_clarification())
            self.assertIsNotNone(surviving_decision)
            self.assertEqual(surviving_decision.status, "confirmed")
            self.assertEqual(surviving_decision.selected_option_id, "option_1")
            self.assertIsNotNone(after_store.get_current_plan())
            self.assertIsNotNone(surviving_run)
            self.assertEqual(surviving_run.stage, "plan_generated")

    def test_state_conflict_abort_tombstones_conflicting_handoff_without_resetting_plan_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            plan_artifact = create_plan_scaffold("补 runtime 状态机 hotfix", config=config, level="standard")
            store.set_current_plan(plan_artifact)
            store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="plan_generated",
                    route_name="plan_only",
                    title=plan_artifact.title,
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id=plan_artifact.plan_id,
                    plan_path=plan_artifact.path,
                    resolution_id="run-resolution",
                )
            )
            store.set_current_handoff(
                RuntimeHandoff(
                    schema_version="1",
                    route_name="plan_only",
                    run_id="run-1",
                    plan_id=plan_artifact.plan_id,
                    plan_path=plan_artifact.path,
                    handoff_kind="plan_only",
                    required_host_action="continue_host_develop",
                    resolution_id="handoff-resolution",
                )
            )

            conflicted = run_runtime("看看状态", workspace_root=workspace, user_home=workspace / "home")
            inspected_store = StateStore(load_runtime_config(workspace))
            self.assertEqual(conflicted.route.route_name, "state_conflict")
            self.assertEqual(conflicted.recovered_context.state_conflict["code"], "resolution_id_mismatch")
            self.assertEqual(inspected_store.get_current_handoff().resolution_id, "handoff-resolution")
            self.assertEqual(inspected_store.get_current_run().resolution_id, "run-resolution")
            self.assertIsNone(inspected_store.get_last_route())

            cleared = run_runtime("强制取消", workspace_root=workspace, user_home=workspace / "home")
            after_store = StateStore(load_runtime_config(workspace))
            current_run = after_store.get_current_run()
            current_handoff = after_store.get_current_handoff()
            current_plan = after_store.get_current_plan()

            self.assertEqual(cleared.route.route_name, "state_conflict")
            self.assertEqual(cleared.route.active_run_action, "abort_conflict")
            self.assertFalse(cleared.recovered_context.state_conflict)
            self.assertIsNotNone(current_plan)
            self.assertIsNotNone(current_run)
            self.assertIsNotNone(current_handoff)
            self.assertEqual(current_run.run_id, "run-1")
            self.assertEqual(current_handoff.run_id, "run-1")
            self.assertTrue(current_run.resolution_id)
            self.assertEqual(current_run.resolution_id, current_handoff.resolution_id)

    def test_state_conflict_abort_restores_develop_handoff_for_executing_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_active_develop_context(workspace)

            store = StateStore(load_runtime_config(workspace))
            current_handoff = store.get_current_handoff()
            assert current_handoff is not None

            stale_handoff = current_handoff.to_dict()
            stale_handoff["resolution_id"] = "stale-resolution-id"
            store.current_handoff_path.write_text(
                json.dumps(stale_handoff, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            conflicted = run_runtime("看看状态", workspace_root=workspace, user_home=workspace / "home")
            self.assertEqual(conflicted.route.route_name, "state_conflict")
            self.assertEqual(conflicted.recovered_context.state_conflict["code"], "resolution_id_mismatch")

            cleared = run_runtime("取消", workspace_root=workspace, user_home=workspace / "home")
            after_store = StateStore(load_runtime_config(workspace))
            current_run = after_store.get_current_run()
            restored_handoff = after_store.get_current_handoff()

            self.assertEqual(cleared.route.route_name, "state_conflict")
            self.assertEqual(cleared.route.active_run_action, "abort_conflict")
            self.assertFalse(cleared.recovered_context.state_conflict)
            self.assertIsNotNone(current_run)
            self.assertEqual(current_run.stage, "develop_pending")
            self.assertIsNotNone(restored_handoff)
            self.assertEqual(restored_handoff.required_host_action, "continue_host_develop")

    def test_cross_session_owner_bound_confirmed_decision_survives_conflict_abort(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            global_store = StateStore(config)
            review_store = StateStore(config, session_id="session-b")
            global_store.ensure()
            review_store.ensure()

            plan_artifact = create_plan_scaffold("补 runtime 状态机 hotfix", config=config, level="standard")
            global_store.set_current_plan(plan_artifact)
            global_store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="decision_pending",
                    route_name="resume_active",
                    title=plan_artifact.title,
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id=plan_artifact.plan_id,
                    plan_path=plan_artifact.path,
                    owner_session_id="session-a",
                    owner_run_id="owner-run-1",
                )
            )
            confirmed_decision = confirm_decision(
                DecisionState(
                    schema_version="2",
                    decision_id="decision-1",
                    feature_key="runtime",
                    phase="develop",
                    status="pending",
                    decision_type="develop_choice",
                    question="继续哪个开发方案？",
                    summary="owner-bound confirmed develop decision should survive conflict cleanup",
                    options=(DecisionOption(option_id="option_1", title="option 1", summary="summary"),),
                    resume_context={
                        "resume_after": "continue_host_develop",
                        "active_run_stage": "executing",
                        "current_plan_path": plan_artifact.path,
                        "task_refs": ["5.3", "6.9"],
                        "changed_files": ["runtime/engine.py"],
                        "working_summary": "cross-session develop decision remains valid after resume",
                        "verification_todo": ["补 cross-session recoverable decision 回归"],
                    },
                    created_at=iso_now(),
                    updated_at=iso_now(),
                ),
                option_id="option_1",
                source="text",
                raw_input="1",
            )
            global_store.set_current_decision(confirmed_decision)

            review_store.set_current_clarification(
                ClarificationState(
                    clarification_id="clarify-1",
                    feature_key="runtime",
                    phase="analyze",
                    status="pending",
                    summary="pending clarification",
                    questions=("q1",),
                    missing_facts=("scope",),
                    created_at=iso_now(),
                    updated_at=iso_now(),
                )
            )

            conflicted = run_runtime(
                "看看状态",
                workspace_root=workspace,
                session_id="session-b",
                user_home=workspace / "home",
            )
            self.assertEqual(conflicted.route.route_name, "state_conflict")

            cleared = run_runtime(
                "取消",
                workspace_root=workspace,
                session_id="session-b",
                user_home=workspace / "home",
            )

            surviving_decision = StateStore(load_runtime_config(workspace)).get_current_decision()
            self.assertEqual(cleared.route.route_name, "state_conflict")
            self.assertFalse(cleared.recovered_context.state_conflict)
            self.assertIsNone(StateStore(load_runtime_config(workspace), session_id="session-b").get_current_clarification())
            self.assertIsNotNone(surviving_decision)
            self.assertEqual(surviving_decision.status, "confirmed")
            self.assertEqual(surviving_decision.phase, "develop")
            self.assertEqual(surviving_decision.selected_option_id, "option_1")

    def test_natural_language_exec_starts_executing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _prepare_ready_plan_state(workspace)

            result = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(result.route.route_name, "resume_active")
            self.assertEqual(result.recovered_context.current_run.stage, "develop_pending")
            self.assertEqual(result.handoff.required_host_action, "continue_host_develop")
            self.assertEqual(
                result.handoff.artifacts["develop_quality_contract"]["verification_discovery_order"],
                ["project_contract", "project_native", "not_configured"],
            )

    def test_exec_surfaces_new_gate_decision_in_same_round_result_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _prepare_ready_plan_state(workspace)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            current_plan = store.get_current_plan()
            self.assertIsNotNone(current_plan)
            _rewrite_background_scope(
                workspace,
                current_plan,
                scope_lines=("runtime/router.py, runtime/engine.py", "runtime/router.py, runtime/engine.py"),
                risk_lines=("范围取舍仍待拍板", "继续推进前需要先明确最终选项"),
            )

            run_runtime("~go exec", workspace_root=workspace, user_home=workspace / "home")
            result = run_runtime("开始", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(result.route.route_name, "decision_pending")
            self.assertIsNotNone(result.recovered_context.current_decision)
            self.assertEqual(result.recovered_context.current_decision.phase, "execution_gate")
            self.assertEqual(result.recovered_context.current_run.stage, "decision_pending")
            self.assertEqual(result.handoff.required_host_action, "confirm_decision")
            persisted_decision = StateStore(config).get_current_decision()
            self.assertIsNotNone(persisted_decision)
            self.assertEqual(persisted_decision.phase, "execution_gate")

    def test_session_plan_reference_persists_execution_gate_decision_in_global_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            session_id = "session-a"
            config, store, plan_artifact = _prepare_ready_plan_state(
                workspace,
                request_text="调整 auth boundary",
                session_id=session_id,
            )
            _rewrite_background_scope(
                workspace,
                plan_artifact,
                scope_lines=("runtime/engine.py", "runtime/engine.py, runtime/router.py"),
                risk_lines=("本轮会调整认证与权限边界", "需要先明确批准路径"),
            )

            routed, resolved_plan, notes, _ = _advance_planning_route(
                RouteDecision(
                    route_name="workflow",
                    request_text=f"分析下 {plan_artifact.plan_id} 是否可以执行",
                    reason="test",
                    complexity="medium",
                    plan_package_policy="authorized_only",
                    capture_mode="summary",
                ),
                state_store=store,
                config=config,
                kb_artifact=None,
            )

            self.assertEqual(routed.route_name, "decision_pending")
            self.assertIsNotNone(resolved_plan)
            self.assertEqual(resolved_plan.plan_id, plan_artifact.plan_id)
            self.assertTrue(any("Promoted execution gate checkpoint to global execution truth" in note for note in notes))

            session_store = StateStore(config, session_id=session_id)
            global_store = StateStore(config)
            self.assertIsNone(session_store.get_current_decision())
            self.assertIsNone(session_store.get_current_run())
            self.assertIsNone(session_store.get_current_handoff())

            persisted_decision = global_store.get_current_decision()
            self.assertIsNotNone(persisted_decision)
            self.assertEqual(persisted_decision.phase, "execution_gate")
            self.assertEqual(global_store.get_current_run().stage, "decision_pending")

    def test_session_plan_reference_followup_runtime_turn_does_not_conflict_after_global_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            session_id = "session-a"
            config, store, plan_artifact = _prepare_ready_plan_state(
                workspace,
                request_text="调整 auth boundary",
                session_id=session_id,
            )
            _rewrite_background_scope(
                workspace,
                plan_artifact,
                scope_lines=("runtime/engine.py", "runtime/engine.py, runtime/router.py"),
                risk_lines=("本轮会调整认证与权限边界", "需要先明确批准路径"),
            )

            _advance_planning_route(
                RouteDecision(
                    route_name="workflow",
                    request_text=f"分析下 {plan_artifact.plan_id} 是否可以执行",
                    reason="test",
                    complexity="medium",
                    plan_package_policy="authorized_only",
                    capture_mode="summary",
                ),
                state_store=store,
                config=config,
                kb_artifact=None,
            )

            followup = run_runtime(
                "继续",
                workspace_root=workspace,
                session_id=session_id,
                user_home=workspace / "home",
            )

            self.assertNotEqual(followup.route.route_name, "state_conflict")
            self.assertFalse(followup.recovered_context.state_conflict)
            self.assertEqual(followup.route.route_name, "decision_pending")
            self.assertEqual(followup.handoff.required_host_action, "confirm_decision")

    def test_develop_callback_helper_writes_decision_checkpoint_and_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_active_develop_context(workspace)
            config = load_runtime_config(workspace)

            inspected = inspect_develop_callback_context(config=config)
            self.assertEqual(inspected["status"], "ready")
            self.assertEqual(inspected["required_host_action"], "continue_host_develop")
            self.assertEqual(inspected["quality_contract"]["max_retry_count"], 1)

            submission = submit_develop_callback(
                {
                    "schema_version": "1",
                    "checkpoint_kind": "decision",
                    "question": "认证边界是否移动到 adapter 层？",
                    "summary": "开发中已经形成两条可执行路径，需要用户拍板。",
                    "options": [
                        {"id": "option_1", "title": "保持现状", "summary": "边界继续留在当前层", "recommended": True},
                        {"id": "option_2", "title": "移动边界", "summary": "把认证边界下推到 adapter 层"},
                    ],
                    "resume_context": {
                        "active_run_stage": "executing",
                        "current_plan_path": ".sopify-skills/plan/20260319_feature",
                        "task_refs": ["2.1", "2.2"],
                        "changed_files": ["runtime/engine.py", "runtime/handoff.py"],
                        "working_summary": "develop callback 已接入，需要确认认证边界。",
                        "verification_todo": ["补 develop checkpoint contract 测试"],
                        "resume_after": "continue_host_develop",
                    },
                },
                config=config,
            )

            self.assertEqual(submission.handoff.required_host_action, "confirm_decision")
            self.assertEqual(submission.route.route_name, "decision_pending")
            store = StateStore(config)
            current_run = store.get_current_run()
            current_decision = store.get_current_decision()
            current_handoff = store.get_current_handoff()
            self.assertIsNotNone(current_decision)
            self.assertIsNotNone(current_run)
            self.assertIsNotNone(current_handoff)
            self.assertEqual(current_decision.phase, "develop")
            self.assertEqual(current_decision.resume_context["resume_after"], "continue_host_develop")
            self.assertTrue(submission.run_state.resolution_id)
            self.assertEqual(submission.run_state.resolution_id, submission.handoff.resolution_id)
            self.assertEqual(current_run.resolution_id, current_handoff.resolution_id)
            self.assertEqual(current_handoff.artifacts["resume_context"]["working_summary"], "develop callback 已接入，需要确认认证边界。")

    def test_develop_quality_report_updates_handoff_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_active_develop_context(workspace)
            config = load_runtime_config(workspace)

            submission = submit_develop_quality_report(
                {
                    "schema_version": "1",
                    "task_refs": ["2.1"],
                    "changed_files": ["runtime/engine.py", "runtime/handoff.py"],
                    "working_summary": "已把 develop 质量 contract 接到继续开发 handoff。",
                    "verification_todo": ["补 develop replay 断言"],
                    "quality_result": {
                        "schema_version": "1",
                        "verification_source": "project_native",
                        "command": "python -m unittest tests.test_runtime_engine -v",
                        "scope": "runtime/engine.py, runtime/handoff.py",
                        "result": "passed",
                        "retry_count": 0,
                        "review_result": {
                            "spec_compliance": {"status": "passed", "summary": "满足当前任务范围"},
                            "code_quality": {"status": "passed", "summary": "修改面与任务规模匹配"},
                        },
                    },
                },
                config=config,
            )

            self.assertIsNone(submission.delegated_callback)
            self.assertEqual(submission.handoff.required_host_action, "continue_host_develop")
            store = StateStore(config)
            handoff = store.get_current_handoff()
            self.assertEqual(handoff.artifacts["task_refs"], ["2.1"])
            self.assertEqual(handoff.artifacts["verification_source"], "project_native")
            self.assertEqual(handoff.artifacts["result"], "passed")
            self.assertEqual(handoff.artifacts["retry_count"], 0)
            self.assertEqual(handoff.artifacts["review_result"]["spec_compliance"]["status"], "passed")
            self.assertIn("develop_quality_contract", handoff.artifacts)
            session_text = (workspace / submission.replay_session_dir / "session.md").read_text(encoding="utf-8")
            breakdown_text = (workspace / submission.replay_session_dir / "breakdown.md").read_text(encoding="utf-8")
            self.assertIn("质量结果=passed", session_text)
            self.assertIn("任务: 2.1", breakdown_text)

    def test_develop_quality_report_requires_checkpoint_for_scope_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_active_develop_context(workspace)
            config = load_runtime_config(workspace)

            with self.assertRaisesRegex(DevelopCallbackError, "requires checkpoint_kind"):
                submit_develop_quality_report(
                    {
                        "schema_version": "1",
                        "task_refs": ["3.1"],
                        "changed_files": ["runtime/engine.py"],
                        "working_summary": "当前改动已经超出原始范围。",
                        "verification_todo": ["回到 plan review 重新整理任务"],
                        "quality_result": {
                            "schema_version": "1",
                            "verification_source": "project_native",
                            "command": "python -m unittest tests.test_runtime_engine -v",
                            "scope": "runtime/engine.py",
                            "result": "replan_required",
                            "reason_code": "scope_changed",
                            "retry_count": 1,
                            "root_cause": "scope_or_design_mismatch",
                            "review_result": {
                                "spec_compliance": {"status": "failed", "summary": "用户反馈已超出当前 plan 边界"},
                                "code_quality": {"status": "not_run", "summary": "等待新的范围决策"},
                            },
                        },
                    },
                    config=config,
                )

    def test_develop_quality_report_can_delegate_to_plan_review_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_active_develop_context(workspace)
            config = load_runtime_config(workspace)

            submission = submit_develop_quality_report(
                {
                    "schema_version": "1",
                    "task_refs": ["3.1"],
                    "changed_files": ["runtime/engine.py", "README.md"],
                    "working_summary": "质量闭环确认当前改动已经超出原始范围。",
                    "verification_todo": ["回到 plan review 重新整理任务"],
                    "quality_result": {
                        "schema_version": "1",
                        "verification_source": "project_native",
                        "command": "python -m unittest tests.test_runtime_engine -v",
                        "scope": "runtime/engine.py, README.md",
                        "result": "replan_required",
                        "reason_code": "scope_changed",
                        "retry_count": 1,
                        "root_cause": "scope_or_design_mismatch",
                        "review_result": {
                            "spec_compliance": {"status": "failed", "summary": "已超出当前 plan 边界"},
                            "code_quality": {"status": "not_run", "summary": "等待新的范围确认"},
                        },
                    },
                    "checkpoint_kind": "decision",
                    "question": "是否扩大本轮改动范围？",
                    "summary": "质量闭环识别出 scope_or_design_mismatch，需要用户拍板。",
                    "options": [
                        {"id": "option_1", "title": "维持原范围", "summary": "回到 plan review", "recommended": True},
                        {"id": "option_2", "title": "扩大范围", "summary": "进入新范围评审"},
                    ],
                },
                config=config,
            )

            self.assertIsNotNone(submission.delegated_callback)
            self.assertEqual(submission.handoff.required_host_action, "confirm_decision")
            store = StateStore(config)
            handoff = store.get_current_handoff()
            self.assertEqual(handoff.artifacts["result"], "replan_required")
            self.assertEqual(handoff.artifacts["root_cause"], "scope_or_design_mismatch")
            self.assertEqual(handoff.artifacts["resume_context"]["resume_after"], "continue_host_develop")
            self.assertEqual(
                handoff.artifacts["resume_context"]["develop_quality_result"]["result"],
                "replan_required",
            )

    def test_develop_quality_result_is_carried_forward_after_decision_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_active_develop_context(workspace)
            config = load_runtime_config(workspace)

            submit_develop_quality_report(
                {
                    "schema_version": "1",
                    "task_refs": ["2.2"],
                    "changed_files": ["runtime/engine.py"],
                    "working_summary": "最近一次 develop task 已通过质量闭环。",
                    "verification_todo": [],
                    "quality_result": {
                        "schema_version": "1",
                        "verification_source": "project_native",
                        "command": "python -m unittest tests.test_runtime_engine -v",
                        "scope": "runtime/engine.py",
                        "result": "passed",
                        "retry_count": 0,
                        "review_result": {
                            "spec_compliance": {"status": "passed", "summary": "满足任务目标"},
                            "code_quality": {"status": "passed", "summary": "代码风格一致"},
                        },
                    },
                },
                config=config,
            )
            submit_develop_callback(
                {
                    "schema_version": "1",
                    "checkpoint_kind": "decision",
                    "question": "认证边界是否移动到 adapter 层？",
                    "summary": "开发中已经形成两条可执行路径，需要用户拍板。",
                    "options": [
                        {"id": "option_1", "title": "保持现状", "summary": "边界继续留在当前层", "recommended": True},
                        {"id": "option_2", "title": "移动边界", "summary": "把认证边界下推到 adapter 层"},
                    ],
                    "resume_context": {
                        "active_run_stage": "executing",
                        "current_plan_path": ".sopify-skills/plan/20260319_feature",
                        "task_refs": ["2.2"],
                        "changed_files": ["runtime/engine.py"],
                        "working_summary": "认证边界待确认。",
                        "verification_todo": [],
                        "resume_after": "continue_host_develop",
                    },
                },
                config=config,
            )

            resumed = run_runtime("1", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(resumed.handoff.required_host_action, "continue_host_develop")
            self.assertEqual(resumed.handoff.artifacts["result"], "passed")
            self.assertEqual(resumed.handoff.artifacts["task_refs"], ["2.2"])

    def test_develop_callback_missing_kind_with_tradeoff_payload_emits_reason_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_active_develop_context(workspace)
            config = load_runtime_config(workspace)

            with self.assertRaisesRegex(DevelopCallbackError, CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED):
                submit_develop_callback(
                    {
                        "schema_version": "1",
                        "question": "认证边界是否移动到 adapter 层？",
                        "summary": "开发中已经形成两条可执行路径，需要用户拍板。",
                        "options": [
                            {"id": "option_1", "title": "保持现状", "summary": "边界继续留在当前层"},
                            {"id": "option_2", "title": "移动边界", "summary": "把认证边界下推到 adapter 层"},
                        ],
                        "resume_context": {
                            "active_run_stage": "executing",
                            "current_plan_path": ".sopify-skills/plan/20260319_feature",
                            "task_refs": ["2.1"],
                            "changed_files": ["runtime/develop_callback.py"],
                            "working_summary": "发现开发中分叉但 payload 未声明 checkpoint_kind。",
                            "verification_todo": ["补 develop callback payload 校验"],
                            "resume_after": "continue_host_develop",
                        },
                    },
                    config=config,
                )

    def test_develop_decision_resume_returns_continue_host_develop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_active_develop_context(workspace)
            config = load_runtime_config(workspace)

            submit_develop_callback(
                {
                    "schema_version": "1",
                    "checkpoint_kind": "decision",
                    "question": "认证边界是否移动到 adapter 层？",
                    "summary": "开发中已经形成两条可执行路径，需要用户拍板。",
                    "options": [
                        {"id": "option_1", "title": "保持现状", "summary": "边界继续留在当前层", "recommended": True},
                        {"id": "option_2", "title": "移动边界", "summary": "把认证边界下推到 adapter 层"},
                    ],
                    "resume_context": {
                        "active_run_stage": "executing",
                        "current_plan_path": ".sopify-skills/plan/20260319_feature",
                        "task_refs": ["2.1"],
                        "changed_files": ["runtime/engine.py"],
                        "working_summary": "认证边界待确认。",
                        "verification_todo": ["补 bundle contract 测试"],
                        "resume_after": "continue_host_develop",
                    },
                },
                config=config,
            )

            resumed = run_runtime("1", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(resumed.route.route_name, "resume_active")
            self.assertEqual(resumed.handoff.required_host_action, "continue_host_develop")
            self.assertEqual(resumed.recovered_context.current_run.stage, "executing")
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_develop_decision_resume_can_fallback_to_plan_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_active_develop_context(workspace)
            config = load_runtime_config(workspace)

            submit_develop_callback(
                {
                    "schema_version": "1",
                    "checkpoint_kind": "decision",
                    "question": "是否扩大本轮改动范围？",
                    "summary": "用户反馈已经改变本轮 plan 范围，需要退回 plan review。",
                    "options": [
                        {"id": "option_1", "title": "维持原范围", "summary": "继续当前 plan", "recommended": True},
                        {"id": "option_2", "title": "扩大范围", "summary": "回退到 plan review 重新评审"},
                    ],
                    "resume_context": {
                        "active_run_stage": "executing",
                        "current_plan_path": ".sopify-skills/plan/20260319_feature",
                        "task_refs": ["3.1"],
                        "changed_files": ["runtime/engine.py", "README.md"],
                        "working_summary": "用户反馈超出了当前 plan 边界。",
                        "verification_todo": ["回到 plan review 后重新整理任务"],
                        "resume_after": "continue_host_develop",
                        "resume_route": "plan_only",
                    },
                },
                config=config,
            )

            resumed = run_runtime("2", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(resumed.route.route_name, "plan_only")
            self.assertEqual(resumed.handoff.required_host_action, "continue_host_develop")
            self.assertEqual(resumed.recovered_context.current_run.stage, "plan_generated")
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_develop_clarification_resume_returns_continue_host_develop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_active_develop_context(workspace)
            config = load_runtime_config(workspace)

            submit_develop_callback(
                {
                    "schema_version": "1",
                    "checkpoint_kind": "clarification",
                    "summary": "需要补齐验收口径后才能继续开发。",
                    "missing_facts": ["acceptance_scope"],
                    "questions": ["本轮是否需要兼容旧版 adapter？"],
                    "resume_context": {
                        "active_run_stage": "executing",
                        "current_plan_path": ".sopify-skills/plan/20260319_feature",
                        "task_refs": ["4.2"],
                        "changed_files": ["runtime/develop_callback.py"],
                        "working_summary": "缺少 adapter 兼容性口径。",
                        "verification_todo": ["补 compatibility case"],
                        "resume_after": "continue_host_develop",
                    },
                },
                config=config,
            )

            resumed = run_runtime("需要兼容旧版 adapter。", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(resumed.route.route_name, "resume_active")
            self.assertEqual(resumed.handoff.required_host_action, "continue_host_develop")
            self.assertEqual(resumed.recovered_context.current_run.stage, "executing")
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_clarification.json").exists())

    def test_develop_pending_decision_does_not_bypass_checkpoint_when_resume_bridge_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            _enter_active_develop_context(workspace)
            config = load_runtime_config(workspace)

            submit_develop_callback(
                {
                    "schema_version": "1",
                    "checkpoint_kind": "decision",
                    "question": "是否扩大本轮改动范围？",
                    "summary": "开发中命中范围分叉，需要用户拍板。",
                    "options": [
                        {"id": "option_1", "title": "维持范围", "summary": "继续当前改动", "recommended": True},
                        {"id": "option_2", "title": "扩大范围", "summary": "回退到 plan review"},
                    ],
                    "resume_context": {
                        "active_run_stage": "executing",
                        "current_plan_path": ".sopify-skills/plan/20260319_feature",
                        "task_refs": ["3.6"],
                        "changed_files": ["runtime/engine.py"],
                        "working_summary": "decision checkpoint 已创建，等待桥接提交。",
                        "verification_todo": ["确认缺失 bridge 时 fail-closed"],
                        "resume_after": "continue_host_develop",
                    },
                },
                config=config,
            )

            still_pending = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home")
            blocked_exec = run_runtime("~go exec", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(still_pending.route.route_name, "decision_pending")
            self.assertEqual(still_pending.handoff.required_host_action, "confirm_decision")
            self.assertEqual(blocked_exec.route.route_name, "decision_pending")
            self.assertEqual(blocked_exec.handoff.required_host_action, "confirm_decision")
            self.assertEqual(blocked_exec.recovered_context.current_run.stage, "decision_pending")
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_decision_pending_cancel_prefix_cancels_checkpoint_with_negation_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            cancelled = run_runtime("取消这个 checkpoint", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(cancelled.route.route_name, "cancel_active")
            self.assertTrue(any("Decision checkpoint cancelled" in note for note in cancelled.notes))
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            negated = run_runtime("不要取消这个 checkpoint", workspace_root=workspace, user_home=workspace / "home")
            soft_negated = run_runtime("先别取消", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(negated.route.route_name, "decision_pending")
            self.assertEqual(negated.handoff.required_host_action, "confirm_decision")
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())
            self.assertEqual(soft_negated.route.route_name, "decision_pending")
            self.assertEqual(soft_negated.handoff.required_host_action, "confirm_decision")

    def test_decision_pending_cancel_prefix_without_boundary_does_not_cancel_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            result = run_runtime("取消后为什么还会回到 pending", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(result.route.route_name, "decision_pending")
            self.assertEqual(result.handoff.required_host_action, "confirm_decision")
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_decision_pending_question_mark_cancel_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            state_root = workspace / ".sopify-skills" / "state"
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            bare_question = run_runtime("取消这个 checkpoint?", workspace_root=workspace, user_home=workspace / "home")
            trailing_question = run_runtime(
                "取消这个 checkpoint？为什么还会回到 pending",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            emphatic = run_runtime("取消这个 checkpoint！", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(bare_question.route.route_name, "decision_pending")
            self.assertEqual(bare_question.handoff.required_host_action, "confirm_decision")
            self.assertEqual(trailing_question.route.route_name, "decision_pending")
            self.assertEqual(trailing_question.handoff.required_host_action, "confirm_decision")
            self.assertEqual(emphatic.route.route_name, "cancel_active")
            self.assertFalse((state_root / "current_decision.json").exists())

    def test_decision_pending_period_and_clause_punctuation_are_fail_closed_when_text_follows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            state_root = workspace / ".sopify-skills" / "state"
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            period_route = run_runtime(
                "取消这个 checkpoint。为什么还会回到 pending",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            colon_route = run_runtime(
                "取消这个 checkpoint: 为什么还会回到 pending",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            semicolon_route = run_runtime(
                "取消这个 checkpoint；为什么还会回到 pending",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            bare_period_route = run_runtime(
                "取消这个 checkpoint。",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            self.assertEqual(period_route.route.route_name, "decision_pending")
            self.assertEqual(period_route.handoff.required_host_action, "confirm_decision")
            self.assertEqual(colon_route.route.route_name, "decision_pending")
            self.assertEqual(colon_route.handoff.required_host_action, "confirm_decision")
            self.assertEqual(semicolon_route.route.route_name, "decision_pending")
            self.assertEqual(semicolon_route.handoff.required_host_action, "confirm_decision")
            self.assertEqual(bare_period_route.route.route_name, "cancel_active")
            self.assertFalse((state_root / "current_decision.json").exists())

    def test_mixed_sentence_cancel_keeps_local_cancel_intent_for_both_pending_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            state_root = workspace / ".sopify-skills" / "state"

            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            decision_cancelled = run_runtime(
                "取消这个 checkpoint，不要取消全部",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            self.assertEqual(decision_cancelled.route.route_name, "cancel_active")
            self.assertFalse((state_root / "current_decision.json").exists())

            run_runtime("取消", workspace_root=workspace, user_home=workspace / "home")
            run_runtime("~go plan 优化一下", workspace_root=workspace, user_home=workspace / "home")
            self.assertTrue((state_root / "current_clarification.json").exists())
            clarification_cancelled = run_runtime(
                "取消这个 checkpoint，不要取消全部",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            self.assertFalse((state_root / "current_clarification.json").exists())

    def test_engine_handles_plan_resume_and_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            first = run_runtime("~go plan 补 runtime 骨架", workspace_root=workspace, user_home=workspace / "home")
            self.assertEqual(first.route.route_name, "plan_only")
            self.assertIsNotNone(first.plan_artifact)
            self.assertIsNotNone(first.replay_session_dir)
            self.assertTrue((workspace / ".sopify-skills" / "project.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "blueprint" / "README.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "blueprint" / "background.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "blueprint" / "design.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "blueprint" / "tasks.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "user" / "preferences.md").exists())
            self.assertFalse((workspace / ".sopify-skills" / "history" / "index.md").exists())
            self.assertFalse((workspace / ".sopify-skills" / "wiki").exists())
            self.assertEqual(first.handoff.required_host_action, "continue_host_develop")
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_handoff.json").exists())

            resumed = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home")
            self.assertEqual(resumed.route.route_name, "resume_active")
            self.assertTrue(resumed.recovered_context.has_active_run)
            self.assertTrue(resumed.recovered_context.loaded_files)
            self.assertIsNotNone(resumed.handoff)
            self.assertEqual(resumed.handoff.handoff_kind, "develop")
            self.assertEqual(resumed.handoff.required_host_action, "continue_host_develop")

            canceled = run_runtime("取消", workspace_root=workspace, user_home=workspace / "home")
            self.assertEqual(canceled.route.route_name, "cancel_active")
            store = StateStore(load_runtime_config(workspace))
            self.assertFalse(store.has_active_flow())
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_handoff.json").exists())

    def test_engine_populates_blueprint_scaffold_on_first_plan_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            result = run_runtime("~go plan 补 runtime 骨架", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(result.route.route_name, "plan_only")
            self.assertTrue((workspace / ".sopify-skills" / "blueprint" / "README.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "blueprint" / "background.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "blueprint" / "design.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "blueprint" / "tasks.md").exists())
            blueprint_readme = (workspace / ".sopify-skills" / "blueprint" / "README.md").read_text(encoding="utf-8")
            self.assertIn("状态: L2 plan-active", blueprint_readme)
            self.assertIn("当前活动方案目录：`../plan/`", blueprint_readme)
            self.assertNotIn("../history/index.md", blueprint_readme)

    def test_engine_archives_metadata_managed_plan_into_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            first = run_runtime("~go plan 补 runtime 骨架", workspace_root=workspace, user_home=workspace / "home")
            self.assertIsNotNone(first.plan_artifact)

            result = run_runtime("归档当前 plan", workspace_root=workspace, user_home=workspace / "home", action_proposal=_archive_current_plan_action())

            self.assertEqual(result.route.route_name, "archive_lifecycle")
            self.assertIsNotNone(result.plan_artifact)
            self.assertTrue(result.plan_artifact.path.startswith(".sopify-skills/history/"))
            self.assertFalse((workspace / first.plan_artifact.path).exists())
            self.assertTrue((workspace / result.plan_artifact.path).exists())
            self.assertTrue(any("knowledge_sync" in note for note in result.notes))
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_plan.json").exists())
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_run.json").exists())
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_handoff.json").exists())
            self.assertIsNotNone(result.handoff)
            self.assertEqual(result.handoff.required_host_action, "continue_host_consult")
            self.assertEqual(result.handoff.handoff_kind, "archive")
            self.assertEqual(result.handoff.artifacts["archived_plan_path"], result.plan_artifact.path)
            self.assertEqual(result.handoff.artifacts["history_index_path"], ".sopify-skills/history/index.md")
            self.assertTrue(result.handoff.artifacts["state_cleared"])
            self.assertEqual(result.handoff.artifacts["archive_lifecycle"]["archive_status"], "completed")
            self.assertEqual(result.handoff.artifacts["archive_receipt_status"], "completed")
            # Archive is a terminal receipt surface — must not carry consult guard/projection.
            self.assertNotIn("deterministic_guard", result.handoff.artifacts)
            self.assertNotIn("action_projection", result.handoff.artifacts)

            history_index = (workspace / ".sopify-skills" / "history" / "index.md").read_text(encoding="utf-8")
            self.assertIn(first.plan_artifact.plan_id, history_index)
            self.assertNotIn("当前暂无已归档方案。", history_index)

            archived_metadata = _load_markdown_front_matter(workspace / result.plan_artifact.path / "tasks.md")
            self.assertEqual(archived_metadata["lifecycle_state"], "archived")
            self.assertEqual(
                archived_metadata["knowledge_sync"],
                {
                    "project": "skip",
                    "background": "skip",
                    "design": "skip",
                    "tasks": "skip",
                },
            )
            self.assertTrue(archived_metadata["archive_ready"])
            self.assertEqual(archived_metadata["plan_status"], "completed")
            self.assertNotIn("blueprint_obligation", archived_metadata)

            blueprint_readme = (workspace / ".sopify-skills" / "blueprint" / "README.md").read_text(encoding="utf-8")
            self.assertIn("状态: L3 history-ready", blueprint_readme)
            self.assertIn("../history/index.md", blueprint_readme)
            self.assertIn("最近归档", blueprint_readme)
            self.assertIn("当前活动 plan：暂无", blueprint_readme)

    def test_archive_current_session_plan_clears_session_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            session_id = "review-session"
            config = load_runtime_config(workspace)
            store = StateStore(config, session_id=session_id)
            store.ensure()
            plan = create_plan_scaffold("会话内方案", config=config, level="standard")
            store.set_current_plan(plan)
            store.set_current_run(
                RunState(
                    run_id="session-run",
                    status="active",
                    stage="develop_pending",
                    route_name="resume_active",
                    title=plan.title,
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id=plan.plan_id,
                    plan_path=plan.path,
                )
            )

            result = run_runtime(
                "归档当前 plan",
                workspace_root=workspace,
                session_id=session_id,
                user_home=workspace / "home",
                action_proposal=_archive_current_plan_action(),
            )

            self.assertEqual(result.route.route_name, "archive_lifecycle")
            self.assertIsNotNone(result.plan_artifact)
            self.assertFalse((workspace / plan.path).exists())
            self.assertIsNone(store.get_current_plan())
            self.assertIsNone(store.get_current_run())
            self.assertTrue(result.handoff.artifacts["state_cleared"])

    def test_archive_handoff_does_not_synthesize_status_without_engine_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            archived_plan = PlanArtifact(
                plan_id="demo_plan",
                title="Demo Plan",
                summary="demo",
                level="standard",
                path=".sopify-skills/history/2026-04/demo_plan",
                files=(".sopify-skills/history/2026-04/demo_plan/tasks.md",),
                created_at=iso_now(),
            )

            handoff = build_runtime_handoff(
                config=config,
                decision=RouteDecision(
                    route_name="archive_lifecycle",
                    request_text="archive test",
                    reason="missing engine payload",
                    artifacts={},
                ),
                run_id="run-archive-missing-payload",
                resolved_context=RecoveredContext(),
                current_plan=archived_plan,
                kb_artifact=None,
                replay_session_dir=None,
                skill_result=None,
                notes=(),
            )

            self.assertIsNotNone(handoff)
            assert handoff is not None
            self.assertEqual(handoff.required_host_action, "continue_host_consult")
            self.assertNotIn("archive_lifecycle", handoff.artifacts)
            self.assertNotIn("archived_plan_path", handoff.artifacts)
            self.assertNotIn("state_cleared", handoff.artifacts)

    def test_archive_normalizes_legacy_archive_front_matter_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            first = run_runtime("~go plan 补 runtime 骨架", workspace_root=workspace, user_home=workspace / "home")
            self.assertIsNotNone(first.plan_artifact)

            tasks_path = workspace / first.plan_artifact.path / "tasks.md"
            tasks_text = tasks_path.read_text(encoding="utf-8")
            tasks_text = tasks_text.replace(
                "archive_ready: false\n",
                "blueprint_obligation: review_required\narchive_ready: false\nplan_status: design_active\n",
            )
            tasks_path.write_text(tasks_text, encoding="utf-8")

            result = run_runtime("归档当前 plan", workspace_root=workspace, user_home=workspace / "home", action_proposal=_archive_current_plan_action())

            archived_metadata = _load_markdown_front_matter(workspace / result.plan_artifact.path / "tasks.md")
            self.assertEqual(
                archived_metadata["knowledge_sync"],
                {
                    "project": "skip",
                    "background": "skip",
                    "design": "skip",
                    "tasks": "skip",
                },
            )
            self.assertEqual(archived_metadata["plan_status"], "completed")
            self.assertNotIn("blueprint_obligation", archived_metadata)

    def test_archive_lifecycle_prefers_archive_subject_over_active_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            active_plan = create_plan_scaffold("当前活动任务", config=config, level="standard")
            store.set_current_plan(active_plan)

            legacy_dir = workspace / ".sopify-skills" / "plan" / "legacy_plan"
            legacy_dir.mkdir(parents=True)
            (legacy_dir / "tasks.md").write_text("# legacy plan\n", encoding="utf-8")

            result = run_runtime(
                "归档旧方案",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=_archive_plan_id_proposal("legacy_plan"),
            )

            self.assertEqual(result.route.route_name, "archive_lifecycle")
            self.assertIsNotNone(result.handoff)
            self.assertEqual(result.handoff.required_host_action, "continue_host_consult")
            self.assertEqual(result.handoff.artifacts["archive_lifecycle"]["archive_subject_plan_id"], "legacy_plan")
            self.assertEqual(result.handoff.artifacts["archive_lifecycle"]["archive_subject_path"], ".sopify-skills/plan/legacy_plan")
            self.assertEqual(result.handoff.artifacts["archive_receipt_status"], "review_required")
            self.assertEqual(store.get_current_plan().plan_id, active_plan.plan_id)

    def test_archive_blocks_full_plan_without_deep_blueprint_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            first = run_runtime("实现 runtime plugin bridge", workspace_root=workspace, user_home=workspace / "home", action_proposal=_propose_plan_action())
            self.assertIsNotNone(first.plan_artifact)
            self.assertEqual(first.plan_artifact.level, "full")

            result = run_runtime("归档当前 plan", workspace_root=workspace, user_home=workspace / "home", action_proposal=_archive_current_plan_action())

            self.assertEqual(result.route.route_name, "archive_lifecycle")
            self.assertIsNone(result.plan_artifact)
            self.assertTrue(any("knowledge_sync.required" in note for note in result.notes))
            self.assertTrue((workspace / first.plan_artifact.path).exists())
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_plan.json").exists())
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_handoff.json").exists())
            self.assertIsNotNone(result.handoff)
            self.assertEqual(result.handoff.required_host_action, "continue_host_consult")
            self.assertEqual(result.handoff.handoff_kind, "archive")
            self.assertEqual(result.handoff.artifacts["archive_lifecycle"]["archive_status"], "blocked")
            self.assertEqual(result.handoff.artifacts["archive_receipt_status"], "review_required")
            self.assertEqual(result.handoff.artifacts["active_plan_path"], first.plan_artifact.path)
            self.assertFalse(result.handoff.artifacts["state_cleared"])
            self.assertNotIn("deterministic_guard", result.handoff.artifacts)
            self.assertNotIn("action_projection", result.handoff.artifacts)

    def test_archive_allows_review_and_blocks_required_by_knowledge_sync(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            review_plan = create_plan_scaffold("实现 runtime skeleton", config=config, level="standard")
            store.set_current_plan(review_plan)
            review_result = run_runtime("归档当前 plan", workspace_root=workspace, user_home=workspace / "home", action_proposal=_archive_current_plan_action())
            self.assertIsNotNone(review_result.plan_artifact)
            self.assertTrue(any("knowledge_sync" in note for note in review_result.notes))
            self.assertTrue((workspace / ".sopify-skills" / "history" / "index.md").exists())

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            required_plan = create_plan_scaffold("设计 runtime architecture plugin bridge", config=config, level="full")
            store.set_current_plan(required_plan)
            required_result = run_runtime("归档当前 plan", workspace_root=workspace, user_home=workspace / "home", action_proposal=_archive_current_plan_action())
            self.assertIsNone(required_result.plan_artifact)
            self.assertTrue(any("knowledge_sync.required" in note for note in required_result.notes))

    def test_archive_blocks_legacy_plan_without_auto_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            legacy_dir = workspace / ".sopify-skills" / "plan" / "legacy_plan"
            legacy_dir.mkdir(parents=True)
            legacy_tasks = legacy_dir / "tasks.md"
            legacy_tasks.write_text("# legacy plan\n", encoding="utf-8")

            store.set_current_plan(
                PlanArtifact(
                    plan_id="legacy_plan",
                    title="Legacy Plan",
                    summary="legacy",
                    level="standard",
                    path=".sopify-skills/plan/legacy_plan",
                    files=(".sopify-skills/plan/legacy_plan/tasks.md",),
                    created_at=iso_now(),
                )
            )
            store.set_current_run(
                RunState(
                    run_id="legacy-run",
                    status="active",
                    stage="plan_ready",
                    route_name="workflow",
                    title="Legacy Plan",
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id="legacy_plan",
                    plan_path=".sopify-skills/plan/legacy_plan",
                )
            )

            result = run_runtime("归档当前 plan", workspace_root=workspace, user_home=workspace / "home", action_proposal=_archive_current_plan_action())

            self.assertEqual(result.route.route_name, "archive_lifecycle")
            self.assertIsNone(result.plan_artifact)
            self.assertIn("Plan is missing required archive metadata", result.notes)
            self.assertTrue(legacy_tasks.exists())
            self.assertFalse((legacy_dir / "background.md").exists())
            self.assertTrue(legacy_dir.exists())
            self.assertEqual(legacy_tasks.read_text(encoding="utf-8"), "# legacy plan\n")
            self.assertIsNotNone(result.handoff)
            self.assertEqual(result.handoff.required_host_action, "continue_host_consult")
            self.assertEqual(result.handoff.artifacts["archive_lifecycle"]["archive_status"], "migration_required")
            self.assertEqual(result.handoff.artifacts["archive_receipt_status"], "review_required")
            self.assertEqual(result.handoff.artifacts["archive_lifecycle"]["archive_changed_files"], [])
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_plan.json").exists())

    def test_archive_keeps_legacy_plan_blocked_after_session_interruption(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            legacy_dir = workspace / ".sopify-skills" / "plan" / "legacy_plan"
            legacy_dir.mkdir(parents=True)
            (legacy_dir / "tasks.md").write_text("# legacy plan\n", encoding="utf-8")

            first = run_runtime("归档 legacy_plan", workspace_root=workspace, user_home=workspace / "home", action_proposal=_archive_plan_id_proposal("legacy_plan"))
            self.assertIsNone(first.plan_artifact)
            self.assertEqual(first.route.artifacts["archive_lifecycle"]["archive_status"], "migration_required")
            self.assertTrue(legacy_dir.exists())
            self.assertFalse((legacy_dir / "background.md").exists())

            store = StateStore(config)
            store.reset_active_flow()
            second = run_runtime("归档 legacy_plan", workspace_root=workspace, user_home=workspace / "home", action_proposal=_archive_plan_id_proposal("legacy_plan"))

            self.assertEqual(second.route.route_name, "archive_lifecycle")
            self.assertIsNone(second.plan_artifact)
            self.assertTrue(legacy_dir.exists())
            self.assertEqual(second.route.artifacts["archive_lifecycle"]["archive_status"], "migration_required")
            self.assertEqual(second.handoff.required_host_action, "continue_host_consult")
            self.assertFalse(second.handoff.artifacts["state_cleared"])
            self.assertFalse((workspace / ".sopify-skills" / "history" / "index.md").exists())

    def test_archive_explicit_non_current_plan_preserves_active_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            current_plan = create_plan_scaffold("当前活动任务", config=config, level="standard")
            other_plan = create_plan_scaffold("旁路可归档任务", config=config, level="standard")
            store.set_current_plan(current_plan)
            store.set_current_run(
                RunState(
                    run_id="active-run",
                    status="active",
                    stage="develop_pending",
                    route_name="resume_active",
                    title=current_plan.title,
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id=current_plan.plan_id,
                    plan_path=current_plan.path,
                )
            )

            result = run_runtime("归档指定 plan", workspace_root=workspace, user_home=workspace / "home", action_proposal=_archive_plan_id_proposal(other_plan.plan_id))

            self.assertEqual(result.route.route_name, "archive_lifecycle")
            self.assertIsNotNone(result.plan_artifact)
            self.assertEqual(result.plan_artifact.plan_id, other_plan.plan_id)
            self.assertTrue((workspace / current_plan.path).exists())
            self.assertFalse((workspace / other_plan.path).exists())
            self.assertEqual(store.get_current_plan().plan_id, current_plan.plan_id)
            self.assertEqual(store.get_current_run().plan_id, current_plan.plan_id)
            self.assertEqual(result.handoff.required_host_action, "continue_host_consult")
            self.assertFalse(result.handoff.artifacts["state_cleared"])
            self.assertNotIn("run_stage", result.handoff.artifacts)
            self.assertNotIn("execution_gate", result.handoff.artifacts)
            self.assertIsNotNone(store.get_current_archive_receipt())
            self.assertEqual(store.get_current_archive_receipt().required_host_action, "continue_host_consult")
            self.assertNotIn("run_stage", store.get_current_archive_receipt().artifacts)

            resumed = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(resumed.route.route_name, "resume_active")
            self.assertEqual(resumed.recovered_context.current_plan.plan_id, current_plan.plan_id)
            self.assertIsNotNone(resumed.handoff)
            self.assertEqual(resumed.handoff.required_host_action, "continue_host_develop")

    def test_archive_missing_explicit_subject_preserves_archive_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            result = run_runtime(
                "归档缺失 plan",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=_archive_path_proposal(".sopify-skills/plan/missing_plan"),
            )

            self.assertEqual(result.route.route_name, "archive_lifecycle")
            self.assertIsNone(result.plan_artifact)
            self.assertEqual(result.handoff.required_host_action, "continue_host_consult")
            archive_lifecycle = result.handoff.artifacts["archive_lifecycle"]
            self.assertEqual(archive_lifecycle["archive_status"], "plan_not_found")
            self.assertEqual(result.handoff.artifacts["archive_receipt_status"], "review_required")

    def test_archive_rejects_path_outside_plan_or_history_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            blueprint_dir = workspace / ".sopify-skills" / "blueprint"
            blueprint_dir.mkdir(parents=True)
            (blueprint_dir / "tasks.md").write_text(
                "\n".join(
                    [
                        "---",
                        "plan_id: blueprint",
                        "feature_key: blueprint",
                        "level: standard",
                        "lifecycle_state: active",
                        "knowledge_sync:",
                        "  project: skip",
                        "  background: skip",
                        "  design: skip",
                        "  tasks: skip",
                        "archive_ready: true",
                        "---",
                        "# Blueprint",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_runtime(
                "归档 blueprint",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=_archive_path_proposal(".sopify-skills/blueprint"),
            )

            self.assertEqual(result.route.route_name, "archive_lifecycle")
            self.assertIsNone(result.plan_artifact)
            self.assertEqual(result.handoff.artifacts["archive_lifecycle"]["archive_status"], "plan_not_found")
            self.assertTrue(blueprint_dir.exists())

    def test_archive_rejects_plan_id_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            blueprint_dir = workspace / ".sopify-skills" / "blueprint"
            blueprint_dir.mkdir(parents=True)
            (blueprint_dir / "tasks.md").write_text("# not a plan\n", encoding="utf-8")

            result = run_runtime(
                "归档 traversal",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=_archive_plan_id_proposal("../blueprint"),
            )

            self.assertEqual(result.route.route_name, "archive_lifecycle")
            self.assertIsNone(result.plan_artifact)
            self.assertEqual(result.handoff.artifacts["archive_lifecycle"]["archive_status"], "plan_not_found")
            self.assertTrue(blueprint_dir.exists())

    def test_engine_creates_decision_checkpoint_before_materializing_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            result = run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            self.assertEqual(result.route.route_name, "decision_pending")
            self.assertIsNone(result.plan_artifact)
            self.assertIsNotNone(result.recovered_context.current_decision)
            self.assertEqual(result.handoff.handoff_kind, "decision")
            self.assertEqual(result.handoff.required_host_action, "confirm_decision")
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_plan.json").exists())
            self.assertTrue((workspace / ".sopify-skills" / "blueprint" / "design.md").exists())

    def test_engine_materializes_plan_after_decision_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            result = run_runtime("1", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(result.route.route_name, "plan_only")
            self.assertIsNotNone(result.plan_artifact)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())
            self.assertEqual(result.recovered_context.current_run.stage, "plan_generated")
            self.assertEqual(result.recovered_context.current_run.execution_gate.gate_status, "blocked")
            self.assertEqual(result.handoff.artifacts["execution_gate"]["blocking_reason"], "missing_info")
            tasks_path = workspace / result.plan_artifact.path / "tasks.md"
            design_path = workspace / result.plan_artifact.path / "design.md"
            self.assertIn("decision_checkpoint:", tasks_path.read_text(encoding="utf-8"))
            self.assertIn("## 决策确认", design_path.read_text(encoding="utf-8"))

    def test_engine_accepts_explicit_option_id_command_for_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            result = run_runtime("~decide choose option_1", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(result.route.route_name, "plan_only")
            self.assertIsNotNone(result.plan_artifact)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_engine_materializes_plan_after_structured_decision_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            store = StateStore(load_runtime_config(workspace))
            store.set_current_decision_submission(
                DecisionSubmission(
                    status="submitted",
                    source="cli",
                    answers={
                        "selected_option_id": "option_1",
                        "implementation_notes": "继续保持 manifest-first 与默认入口不变",
                    },
                    submitted_at=iso_now(),
                    resume_action="submit",
                )
            )

            result = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(result.route.route_name, "plan_only")
            self.assertIsNotNone(result.plan_artifact)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())
            self.assertEqual(result.recovered_context.current_run.stage, "plan_generated")
            self.assertTrue(any("structured submission" in note for note in result.notes))

    def test_confirmed_decision_can_resume_after_interruption(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            pending = run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            config = load_runtime_config(workspace)
            store = StateStore(config)
            confirmed = confirm_decision(
                pending.recovered_context.current_decision,
                option_id="option_1",
                source="text",
                raw_input="1",
            )
            store.set_current_decision(confirmed)

            resumed = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(resumed.route.route_name, "plan_only")
            self.assertIsNotNone(resumed.plan_artifact)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_confirmed_decision_can_materialize_through_exec_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            pending = run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            config = load_runtime_config(workspace)
            store = StateStore(config)
            confirmed = confirm_decision(
                pending.recovered_context.current_decision,
                option_id="option_1",
                source="text",
                raw_input="1",
            )
            store.set_current_decision(confirmed)

            resumed = run_runtime("~go exec", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(resumed.route.route_name, "plan_only")
            self.assertIsNotNone(resumed.plan_artifact)
            self.assertEqual(resumed.recovered_context.current_run.stage, "plan_generated")
            self.assertEqual(resumed.recovered_context.current_run.execution_gate.blocking_reason, "missing_info")
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_confirmed_gate_decision_reenters_execution_gate_on_existing_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            plan_artifact = create_plan_scaffold("调整 auth boundary", config=config, level="standard")
            _rewrite_background_scope(
                workspace,
                plan_artifact,
                scope_lines=("runtime/engine.py", "runtime/engine.py, runtime/router.py"),
                risk_lines=("本轮会调整认证与权限边界", "需要先明确批准路径"),
            )
            route = RouteDecision(
                route_name="workflow",
                request_text="调整 auth boundary",
                reason="test",
                complexity="complex",
                plan_level="standard",
                candidate_skill_ids=("design", "develop"),
            )
            gate = evaluate_execution_gate(
                decision=route,
                plan_artifact=plan_artifact,
                current_clarification=None,
                current_decision=None,
                config=config,
            )
            gate_decision = build_execution_gate_decision_state(
                route,
                gate=gate,
                current_plan=plan_artifact,
                config=config,
            )
            self.assertIsNotNone(gate_decision)
            self.assertEqual(gate_decision.phase, "execution_gate")
            store.set_current_plan(plan_artifact)
            store.set_current_run(
                RunState(
                    run_id="run-1",
                    status="active",
                    stage="decision_pending",
                    route_name="workflow",
                    title=plan_artifact.title,
                    created_at=iso_now(),
                    updated_at=iso_now(),
                    plan_id=plan_artifact.plan_id,
                    plan_path=plan_artifact.path,
                    execution_gate=gate,
                )
            )
            confirmed = confirm_decision(
                replace(
                    gate_decision,
                    resume_context={
                        "resume_after": "continue_host_develop",
                        "active_run_stage": "decision_pending",
                        "current_plan_path": plan_artifact.path,
                        "task_refs": [],
                        "changed_files": [],
                        "working_summary": "Execution gate decision was confirmed on the existing plan",
                        "verification_todo": [],
                    },
                ),
                option_id="option_1",
                source="text",
                raw_input="1",
            )
            store.set_current_decision(confirmed)

            resumed = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(resumed.route.route_name, "plan_only")
            self.assertIsNotNone(resumed.plan_artifact)
            self.assertEqual(resumed.plan_artifact.path, plan_artifact.path)
            self.assertEqual(resumed.recovered_context.current_run.stage, "ready_for_execution")
            self.assertEqual(resumed.recovered_context.current_run.execution_gate.gate_status, "ready")
            self.assertEqual(resumed.handoff.required_host_action, "continue_host_develop")
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_engine_handoff_contracts_cover_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            replay = run_runtime("回放最近一次实现", workspace_root=workspace, user_home=workspace / "home")
            self.assertIsNotNone(replay.handoff)
            self.assertEqual(replay.handoff.handoff_kind, "consult")
            self.assertEqual(replay.handoff.required_host_action, "continue_host_consult")

    def test_rendered_plan_output_and_repo_local_helper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            result = run_runtime("~go plan 补 runtime 骨架", workspace_root=workspace, user_home=workspace / "home")
            rendered = render_runtime_output(
                result,
                brand="demo-ai",
                language="zh-CN",
                title_color="none",
                use_color=False,
            )

            self.assertIn("[demo-ai] 方案设计 ✓", rendered)
            self.assertIn("方案: .sopify-skills/plan/", rendered)
            self.assertIn("交接: .sopify-skills/state/current_handoff.json", rendered)
            self.assertIn("Next: 在宿主会话中继续评审或执行方案，或直接回复修改意见", rendered)
            _assert_rendered_footer_contract(
                self,
                rendered,
                next_prefix="Next:",
            )

            events_path = workspace / result.replay_session_dir / "events.jsonl"
            event_payload = json.loads(events_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(event_payload["metadata"]["activation"]["skill_id"], "design")
            self.assertEqual(event_payload["metadata"]["activation"]["route_name"], "plan_only")
            self.assertIn("display_time", event_payload["metadata"]["activation"])

            script_path = REPO_ROOT / "scripts" / "go_plan_runtime.py"
            completed = subprocess.run(
                [sys.executable, str(script_path), "--workspace-root", str(workspace), "--no-color", "补 runtime 骨架"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("[tmp", completed.stdout)
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_plan.json").exists())
            self.assertTrue((workspace / ".sopify-skills" / "replay" / "sessions").exists())
            self.assertTrue((workspace / ".sopify-skills" / "project.md").exists())
            self.assertIn(".sopify-skills/project.md", rendered)

    def test_run_plan_loop_auto_resolves_decision_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            orchestrated = run_plan_loop(
                "payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                input_reader=lambda _prompt: "1",
                output_writer=lambda _message: None,
                interactive_session_factory=lambda: None,
            )

            self.assertEqual(orchestrated.exit_code, 0)
            self.assertEqual(orchestrated.runtime_result.route.route_name, "plan_only")
            self.assertIsNotNone(orchestrated.runtime_result.plan_artifact)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_run_plan_loop_auto_resolves_clarification_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            answers = iter(("runtime/router.py", "补结构化 clarification bridge。", "."))

            orchestrated = run_plan_loop(
                "优化一下",
                workspace_root=workspace,
                input_reader=lambda _prompt: next(answers),
                output_writer=lambda _message: None,
                interactive_session_factory=lambda: None,
            )

            self.assertEqual(orchestrated.exit_code, 0)
            self.assertEqual(orchestrated.runtime_result.route.route_name, "plan_only")
            self.assertIsNotNone(orchestrated.runtime_result.plan_artifact)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_clarification.json").exists())

    def test_run_plan_loop_fail_closes_repeated_checkpoint_signatures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            checkpoint_result = run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            self.assertEqual(checkpoint_result.handoff.required_host_action, "confirm_decision")

            with mock.patch("runtime.plan_orchestrator.run_runtime", return_value=checkpoint_result), mock.patch(
                "runtime.plan_orchestrator._consume_planning_handoff",
                return_value=None,
            ):
                orchestrated = run_plan_loop(
                    "payload 放 host root 还是 workspace/.sopify-runtime",
                    workspace_root=workspace,
                    input_reader=lambda _prompt: "1",
                    output_writer=lambda _message: None,
                    interactive_session_factory=lambda: None,
                )

            self.assertEqual(orchestrated.exit_code, PLAN_ORCHESTRATOR_PENDING_EXIT)
            self.assertEqual(orchestrated.stopped_reason, "repeated_checkpoint")
            self.assertEqual(orchestrated.loop_count, 3)

    def test_run_plan_loop_fail_closes_when_bridge_cannot_complete_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            checkpoint_result = run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            with mock.patch("runtime.plan_orchestrator.run_runtime", return_value=checkpoint_result), mock.patch(
                "runtime.plan_orchestrator._consume_planning_handoff",
                side_effect=PlanOrchestratorError("bridge missing submit/resume"),
            ):
                orchestrated = run_plan_loop(
                    "payload 放 host root 还是 workspace/.sopify-runtime",
                    workspace_root=workspace,
                    input_reader=lambda _prompt: "1",
                    output_writer=lambda _message: None,
                    interactive_session_factory=lambda: None,
                )

            self.assertEqual(orchestrated.exit_code, PLAN_ORCHESTRATOR_CANCELLED_EXIT)
            self.assertEqual(orchestrated.stopped_reason, "bridge_cancelled")
            self.assertEqual(orchestrated.runtime_result.handoff.required_host_action, "confirm_decision")

    def test_run_plan_loop_stops_with_max_loops_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            checkpoint_result = run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            counter = iter(range(1, 10))

            with mock.patch("runtime.plan_orchestrator.run_runtime", return_value=checkpoint_result), mock.patch(
                "runtime.plan_orchestrator._consume_planning_handoff",
                return_value=None,
            ), mock.patch(
                "runtime.plan_orchestrator._handoff_signature",
                side_effect=lambda _handoff: f"sig-{next(counter)}",
            ):
                orchestrated = run_plan_loop(
                    "payload 放 host root 还是 workspace/.sopify-runtime",
                    workspace_root=workspace,
                    max_loops=2,
                    input_reader=lambda _prompt: "1",
                    output_writer=lambda _message: None,
                    interactive_session_factory=lambda: None,
                )

            self.assertEqual(orchestrated.exit_code, PLAN_ORCHESTRATOR_PENDING_EXIT)
            self.assertEqual(orchestrated.stopped_reason, "max_loops_exceeded")
            self.assertEqual(orchestrated.loop_count, 2)

    def test_go_plan_helper_fail_closes_pending_decision_without_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            script_path = REPO_ROOT / "scripts" / "go_plan_runtime.py"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    "payload",
                    "放",
                    "host",
                    "root",
                    "还是",
                    "workspace/.sopify-runtime",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, PLAN_ORCHESTRATOR_PENDING_EXIT, msg=completed.stderr)
            self.assertIn("方案设计 ?", completed.stdout)
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_go_plan_helper_debug_bypass_keeps_single_pass_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            script_path = REPO_ROOT / "scripts" / "go_plan_runtime.py"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--workspace-root",
                    str(workspace),
                    "--no-bridge-loop",
                    "--no-color",
                    "优化一下",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("需求分析 ?", completed.stdout)
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_clarification.json").exists())

    def test_synced_runtime_bundle_runs_in_another_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            target_root = temp_root / "target"
            workspace = temp_root / "workspace"
            target_root.mkdir()
            workspace.mkdir()
            git_init = subprocess.run(
                ["git", "init", str(workspace)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(git_init.returncode, 0, msg=git_init.stderr)

            sync_script = REPO_ROOT / "scripts" / "sync-runtime-assets.sh"
            sync_completed = subprocess.run(
                ["bash", str(sync_script), str(target_root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(sync_completed.returncode, 0, msg=sync_completed.stderr)

            bundle_root = target_root / ".sopify-runtime"
            manifest_path = bundle_root / "manifest.json"
            self.assertTrue((bundle_root / "runtime" / "__init__.py").exists())
            self.assertTrue((bundle_root / "runtime" / "clarification_bridge.py").exists())
            self.assertTrue((bundle_root / "runtime" / "cli_interactive.py").exists())
            self.assertTrue((bundle_root / "runtime" / "develop_callback.py").exists())
            self.assertTrue((bundle_root / "runtime" / "decision_bridge.py").exists())
            self.assertTrue((bundle_root / "runtime" / "gate.py").exists())
            self.assertTrue((bundle_root / "runtime" / "workspace_preflight.py").exists())
            self.assertTrue((bundle_root / "scripts" / "check-runtime-smoke.sh").exists())
            self.assertTrue((bundle_root / "scripts" / "clarification_bridge_runtime.py").exists())
            self.assertTrue((bundle_root / "scripts" / "develop_callback_runtime.py").exists())
            self.assertTrue((bundle_root / "scripts" / "decision_bridge_runtime.py").exists())
            self.assertTrue((bundle_root / "scripts" / "plan_registry_runtime.py").exists())
            self.assertTrue((bundle_root / "scripts" / "preferences_preload_runtime.py").exists())
            self.assertTrue((bundle_root / "scripts" / "runtime_gate.py").exists())
            self.assertTrue((bundle_root / "tests" / "test_runtime.py").exists())
            self.assertTrue(manifest_path.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "1")
            self.assertEqual(manifest["kb_layout_version"], "2")
            self.assertEqual(
                manifest["knowledge_paths"],
                {
                    "project": ".sopify-skills/project.md",
                    "blueprint_index": ".sopify-skills/blueprint/README.md",
                    "blueprint_background": ".sopify-skills/blueprint/background.md",
                    "blueprint_design": ".sopify-skills/blueprint/design.md",
                    "blueprint_tasks": ".sopify-skills/blueprint/tasks.md",
                    "plan_root": ".sopify-skills/plan",
                    "history_root": ".sopify-skills/history",
                },
            )
            self.assertEqual(
                manifest["context_profiles"]["consult"],
                ["project", "blueprint_index"],
            )
            self.assertEqual(
                manifest["context_profiles"]["plan"],
                ["project", "blueprint_index", "blueprint_background", "blueprint_design"],
            )
            self.assertEqual(
                manifest["context_profiles"]["clarification"],
                ["project", "blueprint_index", "blueprint_tasks"],
            )
            self.assertEqual(
                manifest["context_profiles"]["decision"],
                ["project", "blueprint_design", "active_plan"],
            )
            self.assertEqual(
                manifest["context_profiles"]["develop"],
                ["active_plan", "project", "blueprint_design"],
            )
            self.assertEqual(
                manifest["context_profiles"]["archive"],
                [
                    "active_plan",
                    "project",
                    "blueprint_index",
                    "blueprint_background",
                    "blueprint_design",
                    "blueprint_tasks",
                ],
            )
            self.assertEqual(manifest["context_profiles"]["history_lookup"], ["history_root"])
            self.assertNotIn("history_root", manifest["context_profiles"]["plan"])
            self.assertNotIn("history_root", manifest["context_profiles"]["develop"])
            self.assertEqual(manifest["default_entry"], "scripts/sopify_runtime.py")
            self.assertEqual(manifest["plan_only_entry"], "scripts/go_plan_runtime.py")
            self.assertEqual(manifest["handoff_file"], ".sopify-skills/state/current_handoff.json")
            self.assertEqual(manifest["dependency_model"]["mode"], "stdlib_only")
            self.assertEqual(manifest["dependency_model"]["runtime_dependencies"], [])
            self.assertEqual(manifest["capabilities"]["bundle_role"], "control_plane")
            self.assertTrue(manifest["capabilities"]["writes_handoff_file"])
            self.assertTrue(manifest["capabilities"]["clarification_checkpoint"])
            self.assertTrue(manifest["capabilities"]["clarification_bridge"])
            self.assertTrue(manifest["capabilities"]["writes_clarification_file"])
            self.assertTrue(manifest["capabilities"]["decision_checkpoint"])
            self.assertTrue(manifest["capabilities"]["decision_bridge"])
            self.assertTrue(manifest["capabilities"]["develop_callback"])
            self.assertTrue(manifest["capabilities"]["develop_quality_feedback"])
            self.assertTrue(manifest["capabilities"]["develop_resume_context"])
            self.assertTrue(manifest["capabilities"]["execution_gate"])
            self.assertTrue(manifest["capabilities"]["plan_registry"])
            self.assertTrue(manifest["capabilities"]["plan_registry_priority_confirm"])
            self.assertTrue(manifest["capabilities"]["planning_mode_orchestrator"])
            self.assertTrue(manifest["capabilities"]["preferences_preload"])
            self.assertTrue(manifest["capabilities"]["runtime_gate"])
            self.assertTrue(manifest["capabilities"]["runtime_entry_guard"])
            self.assertTrue(manifest["capabilities"]["session_scoped_review_state"])
            self.assertTrue(manifest["capabilities"]["soft_execution_ownership"])
            self.assertTrue(manifest["capabilities"]["writes_decision_file"])
            self.assertEqual(manifest["runtime_first_hints"]["force_route_name"], "workflow")
            self.assertEqual(
                manifest["runtime_first_hints"]["entry_guard_reason_code"],
                "direct_edit_blocked_runtime_required",
            )
            self.assertEqual(manifest["runtime_first_hints"]["required_entry"], "scripts/runtime_gate.py")
            self.assertEqual(manifest["runtime_first_hints"]["required_subcommand"], "enter")
            self.assertEqual(manifest["runtime_first_hints"]["direct_entry_block_error_code"], "runtime_gate_required")
            self.assertEqual(manifest["runtime_first_hints"]["debug_bypass_flag"], "--allow-direct-entry")
            self.assertIn(".sopify-skills/plan/", manifest["runtime_first_hints"]["protected_path_prefixes"])
            self.assertIn("蓝图", manifest["runtime_first_hints"]["process_semantic_keywords"])
            self.assertIn("contract", manifest["runtime_first_hints"]["tradeoff_keywords"])
            self.assertIn("runtime", manifest["runtime_first_hints"]["long_term_contract_keywords"])
            self.assertIn("plan_only", manifest["limits"]["host_required_routes"])
            self.assertIn("clarification_pending", manifest["limits"]["host_required_routes"])
            self.assertIn("clarification_resume", manifest["limits"]["host_required_routes"])
            self.assertIn("decision_pending", manifest["limits"]["host_required_routes"])
            self.assertTrue(manifest["limits"]["entry_guard"]["strict_runtime_entry"])
            self.assertEqual(manifest["limits"]["entry_guard"]["default_runtime_entry"], "scripts/sopify_runtime.py")
            self.assertIn("~go exec", manifest["limits"]["entry_guard"]["bypass_blocked_commands"])
            self.assertEqual(manifest["limits"]["session_state"]["review_scope"], "session")
            self.assertEqual(manifest["limits"]["session_state"]["execution_scope"], "global")
            self.assertEqual(manifest["limits"]["session_state"]["source"], "host_supplied_or_runtime_gate_generated")
            self.assertEqual(manifest["limits"]["session_state"]["followup_session_id"], "required_for_review_followups")
            self.assertEqual(manifest["limits"]["session_state"]["cleanup_days"], 7)
            self.assertIn("archive_lifecycle", manifest["supported_routes"])
            self.assertNotIn("compare", manifest["supported_routes"])
            self.assertIn("exec_plan", manifest["limits"]["host_required_routes"])
            self.assertEqual(manifest["limits"]["clarification_file"], ".sopify-skills/state/current_clarification.json")
            self.assertEqual(manifest["limits"]["clarification_bridge_entry"], "scripts/clarification_bridge_runtime.py")
            self.assertEqual(manifest["limits"]["clarification_bridge_hosts"]["cli"]["preferred_mode"], "interactive_form")
            self.assertEqual(manifest["limits"]["decision_file"], ".sopify-skills/state/current_decision.json")
            self.assertEqual(manifest["limits"]["decision_bridge_entry"], "scripts/decision_bridge_runtime.py")
            self.assertEqual(manifest["limits"]["decision_bridge_hosts"]["cli"]["preferred_mode"], "interactive_form")
            self.assertEqual(manifest["limits"]["decision_bridge_hosts"]["cli"]["select"], "interactive_select")
            self.assertEqual(manifest["limits"]["develop_callback_entry"], "scripts/develop_callback_runtime.py")
            self.assertEqual(manifest["limits"]["develop_callback_hosts"]["cli"]["preferred_mode"], "structured_callback")
            self.assertEqual(manifest["limits"]["develop_callback_hosts"]["cli"]["submit_quality"], "json_payload")
            self.assertIn("working_summary", manifest["limits"]["develop_resume_context_required_fields"])
            self.assertIn("continue_host_develop", manifest["limits"]["develop_resume_after_actions"])
            self.assertEqual(manifest["limits"]["develop_quality_contract_version"], "1")
            self.assertEqual(manifest["limits"]["plan_registry_entry"], "scripts/plan_registry_runtime.py")
            self.assertEqual(manifest["limits"]["plan_registry_hosts"]["cli"]["preferred_mode"], "inspect_only_summary")
            self.assertEqual(
                manifest["limits"]["plan_registry_hosts"]["cli"]["trigger_points"],
                ["post_plan_review", "manual_plan_registry_review"],
            )
            self.assertEqual(manifest["limits"]["plan_registry_hosts"]["cli"]["mount_scope"], "review_only")
            self.assertEqual(manifest["limits"]["plan_registry_hosts"]["cli"]["blocked_scopes"], ["develop", "execute"])
            self.assertEqual(manifest["limits"]["plan_registry_hosts"]["cli"]["default_surface"], "inspect_contract")
            self.assertEqual(manifest["limits"]["plan_registry_hosts"]["cli"]["confirm_priority_trigger"], "explicit_user_action")
            self.assertEqual(
                manifest["limits"]["plan_registry_hosts"]["cli"]["display_fields"],
                ["current_plan", "selected_plan", "recommendations", "drift_notice", "execution_truth"],
            )
            self.assertEqual(
                manifest["limits"]["plan_registry_hosts"]["cli"]["allowed_actions"],
                ["confirm_suggested", "set_p1", "set_p2", "set_p3", "dismiss"],
            )
            self.assertTrue(manifest["limits"]["plan_registry_hosts"]["cli"]["note_optional"])
            self.assertEqual(
                manifest["limits"]["plan_registry_hosts"]["cli"]["confirm_payload_fields"],
                ["plan_id", "priority", "note"],
            )
            self.assertEqual(
                manifest["limits"]["plan_registry_hosts"]["cli"]["success_behavior"],
                {
                    "refresh_scope": "selected_card",
                    "stay_in_context": "review",
                    "auto_execute": False,
                    "auto_switch_current_plan": False,
                },
            )
            self.assertEqual(
                manifest["limits"]["plan_registry_hosts"]["cli"]["failure_behavior"],
                {
                    "inspect_failure": "hide_card_non_blocking",
                    "confirm_failure": "show_retryable_error",
                },
            )
            self.assertEqual(
                manifest["limits"]["plan_registry_hosts"]["cli"]["copy"],
                {
                    "title": "Plan 优先级建议",
                    "summary": "当前 active plan、当前评审 plan 与建议优先级",
                    "boundary_notice": "确认优先级只会更新 registry，不会切换 current_plan",
                    "success_notice": "已记录到 plan registry",
                    "pending_notice": "已保留系统建议，暂未写入最终优先级",
                },
            )
            self.assertEqual(manifest["limits"]["plan_registry_hosts"]["cli"]["raw_registry_visibility"], "advanced_only")
            self.assertTrue(manifest["limits"]["plan_registry_hosts"]["cli"]["observe_only"])
            self.assertEqual(manifest["limits"]["plan_registry_hosts"]["cli"]["execution_truth"], "current_plan")
            self.assertEqual(manifest["limits"]["preferences_preload_entry"], "scripts/preferences_preload_runtime.py")
            self.assertEqual(manifest["limits"]["preferences_preload_contract_version"], "1")
            self.assertEqual(
                manifest["limits"]["preferences_preload_statuses"],
                ["loaded", "missing", "invalid", "read_error"],
            )
            self.assertEqual(manifest["limits"]["runtime_gate_entry"], "scripts/runtime_gate.py")
            self.assertEqual(manifest["limits"]["runtime_gate_contract_version"], "1")
            self.assertEqual(
                manifest["limits"]["runtime_gate_allowed_response_modes"],
                ["normal_runtime_followup", "checkpoint_only", "error_visible_retry", "action_proposal_retry"],
            )
            self.assertEqual(manifest["limits"]["runtime_payload_required_skill_ids"], [])
            self.assertEqual(len(manifest["builtin_skills"]), 6)
            self.assertNotIn("model-compare", {skill["skill_id"] for skill in manifest["builtin_skills"]})

            runtime_script = bundle_root / "scripts" / "sopify_runtime.py"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(runtime_script),
                    "--allow-direct-entry",
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    "~go plan 重构数据库层",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)

            preferences_script = bundle_root / "scripts" / "preferences_preload_runtime.py"
            preferences_workspace = temp_root / "preferences-workspace"
            preferences_workspace.mkdir()
            preference_file = preferences_workspace / ".sopify-skills" / "user" / "preferences.md"
            preference_file.parent.mkdir(parents=True, exist_ok=True)
            preference_file.write_text("# 用户长期偏好\n\n- 严谨输出。\n", encoding="utf-8")
            preloaded = subprocess.run(
                [sys.executable, str(preferences_script), "--workspace-root", str(preferences_workspace), "inspect"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(preloaded.returncode, 0, msg=preloaded.stderr)
            preload_payload = json.loads(preloaded.stdout)
            self.assertEqual(preload_payload["status"], "ready")
            self.assertEqual(preload_payload["preferences"]["status"], "loaded")
            self.assertIn("严谨输出。", preload_payload["preferences"]["injection_text"])

            runtime_gate_script = bundle_root / "scripts" / "runtime_gate.py"
            gated = subprocess.run(
                [
                    sys.executable,
                    str(runtime_gate_script),
                    "enter",
                    "--workspace-root",
                    str(workspace),
                    "--request",
                    "~go plan 重构数据库层",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(gated.returncode, 0, msg=gated.stderr)
            gate_payload = json.loads(gated.stdout)
            self.assertEqual(gate_payload["status"], "ready")
            self.assertTrue(gate_payload["gate_passed"])
            self.assertEqual(gate_payload["allowed_response_mode"], "normal_runtime_followup")
            self.assertEqual(gate_payload["handoff"]["required_host_action"], "continue_host_develop")
            self.assertIn(".sopify-skills/plan/", completed.stdout)
            self.assertTrue((workspace / gate_payload["state"]["current_handoff_path"]).exists())
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_gate_receipt.json").exists())
            self.assertTrue((workspace / gate_payload["state"]["current_plan_path"]).exists())
            self.assertTrue((workspace / ".sopify-skills" / "replay" / "sessions").exists())
            self.assertTrue((workspace / ".sopify-skills" / "project.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "blueprint" / "README.md").exists())
            self.assertFalse((workspace / ".sopify-skills" / "history" / "index.md").exists())
            bundle_blueprint_readme = (workspace / ".sopify-skills" / "blueprint" / "README.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("状态: L2 plan-active", bundle_blueprint_readme)
            self.assertIn("当前活动 plan：存在", bundle_blueprint_readme)
            self.assertNotIn("../history/index.md", bundle_blueprint_readme)

    def test_synced_runtime_bundle_supports_decision_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            target_root = temp_root / "target"
            workspace = temp_root / "workspace"
            target_root.mkdir()
            workspace.mkdir()

            sync_script = REPO_ROOT / "scripts" / "sync-runtime-assets.sh"
            sync_completed = subprocess.run(
                ["bash", str(sync_script), str(target_root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(sync_completed.returncode, 0, msg=sync_completed.stderr)

            runtime_script = target_root / ".sopify-runtime" / "scripts" / "sopify_runtime.py"
            bridge_script = target_root / ".sopify-runtime" / "scripts" / "decision_bridge_runtime.py"
            pending = subprocess.run(
                [
                    sys.executable,
                    str(runtime_script),
                    "--allow-direct-entry",
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    "~go",
                    "plan",
                    "payload",
                    "放",
                    "host",
                    "root",
                    "还是",
                    "workspace/.sopify-runtime",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(pending.returncode, 0, msg=pending.stderr)
            self.assertIn("方案设计 ?", pending.stdout)
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

            inspected = subprocess.run(
                [
                    sys.executable,
                    str(bridge_script),
                    "--workspace-root",
                    str(workspace),
                    "inspect",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(inspected.returncode, 0, msg=inspected.stderr)
            inspect_payload = json.loads(inspected.stdout)
            self.assertEqual(inspect_payload["bridge"]["host_kind"], "cli")
            self.assertEqual(inspect_payload["bridge"]["steps"][0]["renderer"], "cli.select")

            confirmed = subprocess.run(
                [
                    sys.executable,
                    str(bridge_script),
                    "--workspace-root",
                    str(workspace),
                    "submit",
                    "--answers-json",
                    '{"selected_option_id":"option_1"}',
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(confirmed.returncode, 0, msg=confirmed.stderr)
            confirmed_payload = json.loads(confirmed.stdout)
            self.assertEqual(confirmed_payload["status"], "written")

            resumed = subprocess.run(
                [
                    sys.executable,
                    str(runtime_script),
                    "--allow-direct-entry",
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    "继续",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(resumed.returncode, 0, msg=resumed.stderr)
            self.assertIn(".sopify-skills/plan/", resumed.stdout)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_plan.json").exists())

    def test_synced_runtime_bundle_supports_develop_callback_helper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            target_root = temp_root / "target"
            workspace = temp_root / "workspace"
            target_root.mkdir()
            workspace.mkdir()

            sync_script = REPO_ROOT / "scripts" / "sync-runtime-assets.sh"
            sync_completed = subprocess.run(
                ["bash", str(sync_script), str(target_root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(sync_completed.returncode, 0, msg=sync_completed.stderr)

            runtime_script = target_root / ".sopify-runtime" / "scripts" / "sopify_runtime.py"
            helper_script = target_root / ".sopify-runtime" / "scripts" / "develop_callback_runtime.py"

            _prepare_ready_plan_state(workspace)
            started = subprocess.run(
                [
                    sys.executable,
                    str(runtime_script),
                    "--allow-direct-entry",
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    "继续",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(started.returncode, 0, msg=started.stderr)
            self.assertIn("continue_host_develop", (workspace / ".sopify-skills" / "state" / "current_handoff.json").read_text(encoding="utf-8"))

            inspected = subprocess.run(
                [sys.executable, str(helper_script), "--workspace-root", str(workspace), "inspect"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(inspected.returncode, 0, msg=inspected.stderr)
            inspect_payload = json.loads(inspected.stdout)
            self.assertEqual(inspect_payload["status"], "ready")
            self.assertEqual(inspect_payload["required_host_action"], "continue_host_develop")
            self.assertEqual(inspect_payload["quality_contract"]["max_retry_count"], 1)

            quality_submitted = subprocess.run(
                [
                    sys.executable,
                    str(helper_script),
                    "--workspace-root",
                    str(workspace),
                    "submit-quality",
                    "--payload-json",
                    json.dumps(
                        {
                            "schema_version": "1",
                            "task_refs": ["5.1"],
                            "changed_files": ["runtime/develop_callback.py"],
                            "working_summary": "已记录 develop 质量结果。",
                            "verification_todo": ["补 bundle helper 测试"],
                            "quality_result": {
                                "schema_version": "1",
                                "verification_source": "project_native",
                                "command": "python -m unittest tests.test_runtime_engine -v",
                                "scope": "runtime/develop_callback.py",
                                "result": "passed",
                                "retry_count": 0,
                                "review_result": {
                                    "spec_compliance": {"status": "passed", "summary": "满足当前任务范围"},
                                    "code_quality": {"status": "passed", "summary": "修改面合理"},
                                },
                            },
                        }
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(quality_submitted.returncode, 0, msg=quality_submitted.stderr)
            quality_payload = json.loads(quality_submitted.stdout)
            self.assertEqual(quality_payload["result"], "passed")
            self.assertEqual(quality_payload["required_host_action"], "continue_host_develop")

            submitted = subprocess.run(
                [
                    sys.executable,
                    str(helper_script),
                    "--workspace-root",
                    str(workspace),
                    "submit",
                    "--payload-json",
                    json.dumps(
                        {
                            "schema_version": "1",
                            "checkpoint_kind": "decision",
                            "question": "认证边界是否移动到 adapter 层？",
                            "summary": "开发中已经形成两条可执行路径，需要用户拍板。",
                            "options": [
                                {"id": "option_1", "title": "保持现状", "summary": "边界继续留在当前层", "recommended": True},
                                {"id": "option_2", "title": "移动边界", "summary": "把认证边界下推到 adapter 层"},
                            ],
                            "resume_context": {
                                "active_run_stage": "executing",
                                "current_plan_path": ".sopify-skills/plan/20260319_feature",
                                "task_refs": ["5.1"],
                                "changed_files": ["runtime/develop_callback.py"],
                                "working_summary": "需要确认认证边界。",
                                "verification_todo": ["补 bundle helper 测试"],
                                "resume_after": "continue_host_develop",
                            },
                        }
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(submitted.returncode, 0, msg=submitted.stderr)
            submit_payload = json.loads(submitted.stdout)
            self.assertEqual(submit_payload["status"], "written")
            self.assertEqual(submit_payload["required_host_action"], "confirm_decision")
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_synced_runtime_bundle_supports_cli_decision_bridge_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            target_root = temp_root / "target"
            workspace = temp_root / "workspace"
            target_root.mkdir()
            workspace.mkdir()

            sync_script = REPO_ROOT / "scripts" / "sync-runtime-assets.sh"
            sync_completed = subprocess.run(
                ["bash", str(sync_script), str(target_root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(sync_completed.returncode, 0, msg=sync_completed.stderr)

            runtime_script = target_root / ".sopify-runtime" / "scripts" / "sopify_runtime.py"
            bridge_script = target_root / ".sopify-runtime" / "scripts" / "decision_bridge_runtime.py"
            pending = subprocess.run(
                [
                    sys.executable,
                    str(runtime_script),
                    "--allow-direct-entry",
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    "~go",
                    "plan",
                    "payload",
                    "放",
                    "host",
                    "root",
                    "还是",
                    "workspace/.sopify-runtime",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(pending.returncode, 0, msg=pending.stderr)
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

            prompted = subprocess.run(
                [
                    sys.executable,
                    str(bridge_script),
                    "--workspace-root",
                    str(workspace),
                    "prompt",
                    "--renderer",
                    "text",
                ],
                input="1\n",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(prompted.returncode, 0, msg=prompted.stderr)
            prompted_payload = json.loads(prompted.stdout)
            self.assertEqual(prompted_payload["status"], "written")
            self.assertEqual(prompted_payload["used_renderer"], "text")
            self.assertEqual(prompted_payload["submission"]["answers"]["selected_option_id"], "option_1")

            resumed = subprocess.run(
                [
                    sys.executable,
                    str(runtime_script),
                    "--allow-direct-entry",
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    "继续",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(resumed.returncode, 0, msg=resumed.stderr)
            self.assertIn(".sopify-skills/plan/", resumed.stdout)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_synced_runtime_bundle_supports_clarification_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            target_root = temp_root / "target"
            workspace = temp_root / "workspace"
            target_root.mkdir()
            workspace.mkdir()

            sync_script = REPO_ROOT / "scripts" / "sync-runtime-assets.sh"
            sync_completed = subprocess.run(
                ["bash", str(sync_script), str(target_root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(sync_completed.returncode, 0, msg=sync_completed.stderr)

            runtime_script = target_root / ".sopify-runtime" / "scripts" / "sopify_runtime.py"
            pending = subprocess.run(
                [
                    sys.executable,
                    str(runtime_script),
                    "--allow-direct-entry",
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    "~go",
                    "plan",
                    "优化一下",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(pending.returncode, 0, msg=pending.stderr)
            self.assertIn("需求分析 ?", pending.stdout)
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_clarification.json").exists())

            answered = subprocess.run(
                [
                    sys.executable,
                    str(runtime_script),
                    "--allow-direct-entry",
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    "目标是 runtime/router.py，预期结果是补 clarification_pending 状态骨架",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(answered.returncode, 0, msg=answered.stderr)
            self.assertIn(".sopify-skills/plan/", answered.stdout)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_clarification.json").exists())
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_plan.json").exists())

    def test_repo_local_runtime_entry_blocks_runtime_first_requests_without_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runtime_script = REPO_ROOT / "scripts" / "sopify_runtime.py"
            request = "分析下 .sopify-skills/plan/20260320_kb_layout_v2/tasks.md 的当前任务，并整理 README 职责表边界"

            blocked = subprocess.run(
                [
                    sys.executable,
                    str(runtime_script),
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    request,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(blocked.returncode, 2, msg=blocked.stderr)
            self.assertIn("scripts/runtime_gate.py enter", blocked.stdout)
            self.assertIn("direct_edit_blocked_runtime_required", blocked.stdout)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_handoff.json").exists())
            receipt_payload = json.loads((workspace / ".sopify-skills" / "state" / "current_gate_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt_payload["error_code"], "runtime_gate_required")
            self.assertEqual(receipt_payload["required_entry"], "scripts/runtime_gate.py")
            self.assertEqual(receipt_payload["required_subcommand"], "enter")
            self.assertEqual(receipt_payload["observability"]["ingress_mode"], "default_runtime_entry_blocked")
            self.assertEqual(receipt_payload["trigger_evidence"]["direct_edit_guard_kind"], "protected_plan_asset")

            allowed = subprocess.run(
                [
                    sys.executable,
                    str(runtime_script),
                    "--allow-direct-entry",
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    request,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(allowed.returncode, 0, msg=allowed.stderr)
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_handoff.json").exists())

    def test_repo_local_runtime_entry_blocks_finalize_alias_without_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runtime_script = REPO_ROOT / "scripts" / "sopify_runtime.py"

            blocked = subprocess.run(
                [
                    sys.executable,
                    str(runtime_script),
                    "--workspace-root",
                    str(workspace),
                    "--no-color",
                    "--json",
                    "~go finalize",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(blocked.returncode, 2, msg=blocked.stderr)
            payload = json.loads(blocked.stdout)
            self.assertEqual(payload["error_code"], "runtime_gate_required")
            self.assertEqual(payload["required_entry"], "scripts/runtime_gate.py")
            self.assertEqual(payload["trigger_evidence"]["direct_edit_guard_kind"], "side_effecting_command_alias")
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_handoff.json").exists())


# ---------------------------------------------------------------------------
# P1.5 debt: ExecutionAuthorizationReceipt engine/handoff integration (T5-C)
# ---------------------------------------------------------------------------


class ReceiptEngineHandoffIntegrationTests(unittest.TestCase):
    """P1.5-B debt — run-level proof that receipt flows through engine → state → handoff."""

    def _authorized_exec_result(self, workspace: Path, plan_artifact: PlanArtifact):
        """Run execute_existing_plan with valid plan_subject and return result."""
        import hashlib
        from runtime.action_intent import PlanSubjectProposal

        plan_md = workspace / plan_artifact.path / "plan.md"
        if not plan_md.exists():
            plan_md.write_text("# Test Plan\nGenerated for receipt integration test.\n", encoding="utf-8")
        digest = hashlib.sha256(plan_md.read_bytes()).hexdigest()
        plan_subject = PlanSubjectProposal(
            subject_ref=plan_artifact.path,
            revision_digest=digest,
        )
        proposal = ActionProposal(
            "execute_existing_plan", "write_files", "high",
            evidence=("test: authorized execution",),
            plan_subject=plan_subject,
        )
        return run_runtime(
            "继续",
            workspace_root=workspace,
            user_home=workspace / "home",
            action_proposal=proposal,
        )

    def test_receipt_persisted_in_run_state(self) -> None:
        """Authorized execute_existing_plan → receipt persisted in RunState."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            _config, _store, plan_artifact = _prepare_ready_plan_state(workspace)

            result = self._authorized_exec_result(workspace, plan_artifact)

            self.assertNotIn("action_proposal_rejected", result.route.reason)
            config = load_runtime_config(workspace)
            run = StateStore(config).get_current_run()
            self.assertIsNotNone(run, "current_run must exist after authorized execution")
            self.assertIsNotNone(
                run.execution_authorization_receipt,
                "receipt must be persisted in RunState",
            )
            receipt = run.execution_authorization_receipt
            self.assertEqual(receipt["plan_path"], plan_artifact.path)

    def test_receipt_exposed_in_handoff_artifacts(self) -> None:
        """Authorized execute_existing_plan → handoff artifacts include receipt."""
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            _config, _store, plan_artifact = _prepare_ready_plan_state(workspace)

            plan_md = workspace / plan_artifact.path / "plan.md"
            if not plan_md.exists():
                plan_md.write_text("# Test Plan\nGenerated for receipt integration test.\n", encoding="utf-8")
            digest = hashlib.sha256(plan_md.read_bytes()).hexdigest()

            result = self._authorized_exec_result(workspace, plan_artifact)

            self.assertIsNotNone(result.handoff, "handoff must be emitted")
            self.assertIn(
                "execution_authorization_receipt",
                result.handoff.artifacts,
                "receipt must appear in handoff artifacts",
            )
            receipt = result.handoff.artifacts["execution_authorization_receipt"]
            self.assertEqual(receipt["plan_path"], plan_artifact.path)
            self.assertEqual(receipt["plan_revision_digest"], digest)
            self.assertIn("authorization_source", receipt)
            self.assertEqual(receipt["authorization_source"]["kind"], "request_hash")

    def test_receipt_8_normative_fields_present(self) -> None:
        """Receipt in handoff must contain all 8 normative fields."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            _config, _store, plan_artifact = _prepare_ready_plan_state(workspace)

            result = self._authorized_exec_result(workspace, plan_artifact)

            self.assertIsNotNone(result.handoff)
            receipt = result.handoff.artifacts.get("execution_authorization_receipt")
            self.assertIsNotNone(receipt, "receipt must be in handoff")
            for field in (
                "plan_id", "plan_path", "plan_revision_digest", "gate_status",
                "action_proposal_id", "authorization_source", "fingerprint", "authorized_at",
            ):
                self.assertIn(field, receipt, f"normative field '{field}' must be present")
                self.assertTrue(receipt[field], f"normative field '{field}' must not be empty")

    # -- T5-C item 3: negative paths must NOT produce receipt ----------------

    def test_consult_readonly_no_receipt(self) -> None:
        """consult_readonly path must NOT create a receipt."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            result = run_runtime(
                "你好",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            self.assertIn(result.route.route_name, ("consult", "consult_readonly"))
            config = load_runtime_config(workspace)
            run = StateStore(config).get_current_run()
            if run is not None:
                self.assertIsNone(
                    run.execution_authorization_receipt,
                    "consult_readonly must not produce a receipt",
                )

    def test_propose_plan_no_receipt(self) -> None:
        """propose_plan path must NOT create a receipt."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            result = run_runtime(
                "帮我做一个方案",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=_propose_plan_action(),
            )
            config = load_runtime_config(workspace)
            run = StateStore(config).get_current_run()
            if run is not None:
                self.assertIsNone(
                    run.execution_authorization_receipt,
                    "propose_plan must not produce a receipt",
                )

    # -- T5-C item 4: resume carry-forward receipt ---------------------------

    def test_resume_carry_forward_receipt_preserved(self) -> None:
        """Resume without new ActionProposal → receipt from previous run preserved."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            _config, _store, plan_artifact = _prepare_ready_plan_state(workspace)

            # Run 1: authorized execution → receipt created
            result1 = self._authorized_exec_result(workspace, plan_artifact)
            self.assertNotIn("action_proposal_rejected", result1.route.reason)

            config = load_runtime_config(workspace)
            run1 = StateStore(config).get_current_run()
            self.assertIsNotNone(run1)
            self.assertIsNotNone(
                run1.execution_authorization_receipt,
                "receipt must exist after Run 1",
            )
            receipt1 = run1.execution_authorization_receipt

            # Run 2: resume without ActionProposal → receipt should carry forward
            result2 = run_runtime(
                "继续",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            config2 = load_runtime_config(workspace)
            run2 = StateStore(config2).get_current_run()
            self.assertIsNotNone(run2)
            self.assertIsNotNone(
                run2.execution_authorization_receipt,
                "receipt must be preserved on resume without new ActionProposal",
            )
            self.assertEqual(
                run2.execution_authorization_receipt.get("fingerprint"),
                receipt1.get("fingerprint"),
                "carried-forward receipt must have same fingerprint",
            )


# ---------------------------------------------------------------------------
# P1.5 debt: Stale receipt cross-run integration (A follow-up)
# ---------------------------------------------------------------------------


class StaleReceiptCrossRunIntegrationTests(unittest.TestCase):
    """P1.5-A debt — run-level proof that plan mutation triggers stale receipt → reject."""

    def test_stale_receipt_triggers_proposal_rejected(self) -> None:
        """Run 1 authorizes → mutate plan.md → Run 2 hits stale receipt → proposal_rejected."""
        import hashlib
        from runtime.action_intent import PlanSubjectProposal

        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            _config, _store, plan_artifact = _prepare_ready_plan_state(workspace)

            plan_md = workspace / plan_artifact.path / "plan.md"
            if not plan_md.exists():
                plan_md.write_text("# Test Plan\nGenerated for receipt integration test.\n", encoding="utf-8")
            digest1 = hashlib.sha256(plan_md.read_bytes()).hexdigest()

            # Run 1: authorize with correct digest → receipt created
            plan_subject1 = PlanSubjectProposal(
                subject_ref=plan_artifact.path,
                revision_digest=digest1,
            )
            proposal1 = ActionProposal(
                "execute_existing_plan", "write_files", "high",
                evidence=("test: first authorization",),
                plan_subject=plan_subject1,
            )
            result1 = run_runtime(
                "继续",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=proposal1,
            )
            self.assertNotIn("action_proposal_rejected", result1.route.reason)

            # Verify receipt persisted after Run 1
            config = load_runtime_config(workspace)
            run_after_1 = StateStore(config).get_current_run()
            self.assertIsNotNone(run_after_1)
            self.assertIsNotNone(
                run_after_1.execution_authorization_receipt,
                "receipt must be persisted after Run 1",
            )

            # Mutate plan.md externally (simulating external edit)
            plan_md.write_text(
                plan_md.read_text(encoding="utf-8") + "\n## Mutated section\n",
                encoding="utf-8",
            )
            digest2 = hashlib.sha256(plan_md.read_bytes()).hexdigest()
            self.assertNotEqual(digest1, digest2, "digest must change after mutation")

            # Run 2: submit with NEW correct digest → stale receipt detected → reject
            plan_subject2 = PlanSubjectProposal(
                subject_ref=plan_artifact.path,
                revision_digest=digest2,
            )
            proposal2 = ActionProposal(
                "execute_existing_plan", "write_files", "high",
                evidence=("test: second authorization attempt",),
                plan_subject=plan_subject2,
            )
            result2 = run_runtime(
                "继续执行",
                workspace_root=workspace,
                user_home=workspace / "home",
                action_proposal=proposal2,
            )

            # Stale receipt → proposal_rejected surface
            self.assertEqual(result2.route.route_name, "proposal_rejected")
            self.assertIn("stale_receipt", result2.route.reason)

            # Handoff must be reject, not consult
            self.assertIsNotNone(result2.handoff, "reject must emit handoff")
            self.assertEqual(result2.handoff.handoff_kind, "reject")
            self.assertNotEqual(result2.handoff.handoff_kind, "consult")


class RoutingConvergenceTests(unittest.TestCase):
    """Phase B — action_type→route_name convergence & capture_mode parity."""

    def _make_plan_subject(self, workspace: Path, plan_artifact: PlanArtifact):
        """Create a valid PlanSubjectProposal for the given plan.

        Creates plan.md (required by validator) with front matter from tasks.md,
        then computes digest from plan.md.
        """
        import hashlib
        from runtime.action_intent import PlanSubjectProposal
        plan_dir = workspace / plan_artifact.path
        plan_md = plan_dir / "plan.md"
        if not plan_md.exists():
            tasks_md = plan_dir / "tasks.md"
            plan_md.write_text(tasks_md.read_text(encoding="utf-8"), encoding="utf-8")
        digest = hashlib.sha256(plan_md.read_bytes()).hexdigest()
        return PlanSubjectProposal(subject_ref=plan_artifact.path, revision_digest=digest)

    def _make_minimal_plan_subject(self, workspace: Path):
        """Create a minimal plan dir with plan.md for plan_subject validation only."""
        import hashlib
        from runtime.action_intent import PlanSubjectProposal
        plan_dir = workspace / ".sopify-skills" / "plan" / "20260507_test"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_md = plan_dir / "plan.md"
        plan_md.write_text("---\nlevel: standard\n---\n# Test Plan\n", encoding="utf-8")
        digest = hashlib.sha256(plan_md.read_bytes()).hexdigest()
        rel_path = str(plan_dir.relative_to(workspace))
        return PlanSubjectProposal(subject_ref=rel_path, revision_digest=digest)

    def test_consult_readonly_routes_to_consult(self) -> None:
        proposal = ActionProposal("consult_readonly", "none", "high", evidence=("test",))
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            result = run_runtime("解释下 router 模块", workspace_root=workspace, user_home=workspace / "home", action_proposal=proposal)
        self.assertEqual(result.route.route_name, "consult")

    def test_propose_plan_routes_to_plan_only(self) -> None:
        proposal = _propose_plan_action()
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            result = run_runtime("重构 router 和 engine 之间的交互", workspace_root=workspace, user_home=workspace / "home", action_proposal=proposal)
        self.assertEqual(result.route.route_name, "plan_only")

    def test_execute_existing_plan_routes_to_resume_active(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            _config, _store, plan_artifact = _prepare_ready_plan_state(workspace)
            plan_subject = self._make_plan_subject(workspace, plan_artifact)
            proposal = ActionProposal(
                "execute_existing_plan", "write_files", "high",
                evidence=("test",),
                plan_subject=plan_subject,
            )
            result = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home", action_proposal=proposal)
        self.assertEqual(result.route.route_name, "resume_active")

    def test_execute_existing_plan_does_not_call_router_classify(self) -> None:
        """Authorized execute_existing_plan must go through derive, not Router.classify."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            _config, _store, plan_artifact = _prepare_ready_plan_state(workspace)
            plan_subject = self._make_plan_subject(workspace, plan_artifact)
            proposal = ActionProposal(
                "execute_existing_plan", "write_files", "high",
                evidence=("test",),
                plan_subject=plan_subject,
            )
            with mock.patch.object(
                Router, "classify",
                side_effect=AssertionError("Router.classify must not be called for authorized proposals"),
            ):
                result = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home", action_proposal=proposal)
        self.assertEqual(result.route.route_name, "resume_active")

    def test_cancel_flow_routes_to_cancel_active(self) -> None:
        proposal = ActionProposal("cancel_flow", "none", "high", evidence=("test",))
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            result = run_runtime("取消", workspace_root=workspace, user_home=workspace / "home", action_proposal=proposal)
        self.assertEqual(result.route.route_name, "cancel_active")
        # No global run → cancel_scope must be "session", not empty/global.
        self.assertEqual(result.route.artifacts.get("cancel_scope"), "session")

    def test_cancel_flow_global_scope_when_global_run_exists(self) -> None:
        """Derive: cancel_flow with global execution run → cancel_scope="global"."""
        from runtime.engine import _derive_route_from_authorized_proposal
        from runtime.context_snapshot import ContextResolvedSnapshot
        fake_run = RunState(
            run_id="run-global", status="active", stage="develop_pending",
            route_name="workflow", title="t", created_at=iso_now(),
            updated_at=iso_now(), plan_id="p", plan_path="p",
        )
        snapshot = ContextResolvedSnapshot(
            resolution_id="test",
            preferred_state_scope="global",
            execution_active_run=fake_run,
        )
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            config = load_runtime_config(workspace)
            proposal = ActionProposal("cancel_flow", "none", "high", evidence=("test",))
            route = _derive_route_from_authorized_proposal(
                proposal, "取消", skills=(), config=config, snapshot=snapshot,
            )
        self.assertEqual(route.route_name, "cancel_active")
        self.assertEqual(route.artifacts.get("cancel_scope"), "global")

    def test_modify_files_derive_simple_quick_fix(self) -> None:
        """Derive: simple modify_files → quick_fix."""
        from runtime.engine import _derive_route_from_authorized_proposal
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            config = load_runtime_config(workspace)
            proposal = ActionProposal("modify_files", "write_files", "high", evidence=("test",))
            route = _derive_route_from_authorized_proposal(
                proposal, "修改 router.py 增加 timeout 参数",
                skills=(), config=config, snapshot=None,
            )
        self.assertEqual(route.route_name, "quick_fix")

    def test_modify_files_derive_complex_workflow(self) -> None:
        """Derive: complex modify_files → workflow."""
        from runtime.engine import _derive_route_from_authorized_proposal
        complex_text = (
            "重构整个 runtime 架构：\n"
            "1. 拆分 engine.py 为 engine_core.py 和 engine_routing.py\n"
            "2. 重写 router.py 的分类逻辑\n"
            "3. 迁移 handoff.py 中所有 guard 逻辑到独立模块\n"
            "4. 更新 tests/test_runtime_engine.py\n"
            "5. 更新 tests/test_runtime_router.py\n"
            "6. 确保所有契约文件一致\n"
        )
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            config = load_runtime_config(workspace)
            proposal = ActionProposal("modify_files", "write_files", "high", evidence=("test",))
            route = _derive_route_from_authorized_proposal(
                proposal, complex_text,
                skills=(), config=config, snapshot=None,
            )
        self.assertIn(route.route_name, {"workflow", "light_iterate"})

    def test_modify_files_capture_mode_parity(self) -> None:
        """Derive path must produce same capture_mode as decide_capture_mode for its complexity."""
        from runtime.engine import _derive_route_from_authorized_proposal
        from runtime.router import decide_capture_mode
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            config = load_runtime_config(workspace)
            proposal = ActionProposal("modify_files", "write_files", "high", evidence=("test",))
            route = _derive_route_from_authorized_proposal(
                proposal, "修改 router.py 增加 timeout 参数",
                skills=(), config=config, snapshot=None,
            )
            expected = decide_capture_mode(config.workflow_learning_auto_capture, route.complexity)
        self.assertEqual(route.capture_mode, expected)

    # -- B6: checkpoint_response active/terminal split --

    def test_checkpoint_response_no_active_checkpoint_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            plan_subject = self._make_minimal_plan_subject(workspace)
            proposal = ActionProposal(
                "checkpoint_response", "write_runtime_state", "high",
                evidence=("test",), plan_subject=plan_subject,
            )
            result = run_runtime("确认", workspace_root=workspace, user_home=workspace / "home", action_proposal=proposal)
        self.assertEqual(result.route.route_name, "proposal_rejected")

    def test_checkpoint_response_pending_clarification_routes_to_clarification_resume(self) -> None:
        """Active pending clarification → clarification_resume."""
        from runtime.engine import _derive_route_from_authorized_proposal
        from runtime.context_snapshot import ContextResolvedSnapshot
        clarification = ClarificationState(
            clarification_id="c-1", feature_key="test", phase="develop",
            status="pending", summary="need info", questions=("q1",),
            missing_facts=("f1",),
        )
        snapshot = ContextResolvedSnapshot(
            resolution_id="test", current_clarification=clarification,
        )
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            config = load_runtime_config(workspace)
            proposal = ActionProposal("checkpoint_response", "write_runtime_state", "high", evidence=("test",))
            route = _derive_route_from_authorized_proposal(
                proposal, "回答澄清问题", skills=(), config=config, snapshot=snapshot,
            )
        self.assertEqual(route.route_name, "clarification_resume")

    def test_checkpoint_response_pending_decision_routes_to_decision_resume(self) -> None:
        """Active pending decision → decision_resume."""
        from runtime.engine import _derive_route_from_authorized_proposal
        from runtime.context_snapshot import ContextResolvedSnapshot
        decision = DecisionState(
            schema_version="1", decision_id="d-1", feature_key="test",
            phase="develop", status="pending", decision_type="design",
            question="which approach?", summary="pick one", options=(),
        )
        snapshot = ContextResolvedSnapshot(
            resolution_id="test", current_decision=decision,
        )
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            config = load_runtime_config(workspace)
            proposal = ActionProposal("checkpoint_response", "write_runtime_state", "high", evidence=("test",))
            route = _derive_route_from_authorized_proposal(
                proposal, "选择方案 A", skills=(), config=config, snapshot=snapshot,
            )
        self.assertEqual(route.route_name, "decision_resume")

    def test_checkpoint_response_collecting_decision_routes_to_decision_resume(self) -> None:
        """Active collecting decision → decision_resume."""
        from runtime.engine import _derive_route_from_authorized_proposal
        from runtime.context_snapshot import ContextResolvedSnapshot
        decision = DecisionState(
            schema_version="1", decision_id="d-2", feature_key="test",
            phase="develop", status="collecting", decision_type="design",
            question="which approach?", summary="pick one", options=(),
        )
        snapshot = ContextResolvedSnapshot(
            resolution_id="test", current_decision=decision,
        )
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            config = load_runtime_config(workspace)
            proposal = ActionProposal("checkpoint_response", "write_runtime_state", "high", evidence=("test",))
            route = _derive_route_from_authorized_proposal(
                proposal, "补充信息", skills=(), config=config, snapshot=snapshot,
            )
        self.assertEqual(route.route_name, "decision_resume")

    def test_checkpoint_response_terminal_decision_rejects(self) -> None:
        """Terminal decision (confirmed) → REJECT, not decision_resume."""
        from runtime.engine import _derive_route_from_authorized_proposal
        from runtime.context_snapshot import ContextResolvedSnapshot
        for terminal_status in ("confirmed", "cancelled", "timed_out"):
            with self.subTest(status=terminal_status):
                decision = DecisionState(
                    schema_version="1", decision_id="d-t", feature_key="test",
                    phase="develop", status=terminal_status, decision_type="design",
                    question="q", summary="s", options=(),
                )
                snapshot = ContextResolvedSnapshot(
                    resolution_id="test", current_decision=decision,
                )
                with tempfile.TemporaryDirectory() as td:
                    workspace = Path(td)
                    (workspace / ".sopify-skills").mkdir(parents=True)
                    config = load_runtime_config(workspace)
                    proposal = ActionProposal("checkpoint_response", "write_runtime_state", "high", evidence=("test",))
                    route = _derive_route_from_authorized_proposal(
                        proposal, "确认", skills=(), config=config, snapshot=snapshot,
                    )
                self.assertEqual(route.route_name, "proposal_rejected",
                    f"terminal status {terminal_status!r} must REJECT")

    # -- B8: bare text request fallback --

    def test_propose_plan_produces_plan_artifact(self) -> None:
        proposal = _propose_plan_action()
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            result = run_runtime("设计一个缓存模块", workspace_root=workspace, user_home=workspace / "home", action_proposal=proposal)
        self.assertEqual(result.route.route_name, "plan_only")
        self.assertIsNotNone(result.handoff, "propose_plan must produce handoff")
        self.assertEqual(result.handoff.handoff_kind, "plan")

    # -- B8: bare text request fallback --

    def test_bare_text_request_uses_router_classify(self) -> None:
        """No ActionProposal → Router.classify fallback."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            result = run_runtime("解释 router 的工作原理", workspace_root=workspace, user_home=workspace / "home")
        self.assertEqual(result.route.route_name, "consult")

    def test_bare_text_modify_uses_router_classify(self) -> None:
        """No ActionProposal, modify request → Router.classify determines route."""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".sopify-skills").mkdir(parents=True)
            result = run_runtime(
                "修改 runtime/router.py 文件中的 classify 函数，增加 timeout 参数",
                workspace_root=workspace, user_home=workspace / "home",
            )
        # Router classifies based on text heuristics; exact route depends on
        # complexity scoring.  We just verify it goes through Router, not derive.
        self.assertIn(result.route.route_name, {"quick_fix", "light_iterate", "workflow", "consult"})
