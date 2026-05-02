from __future__ import annotations

from tests.runtime_test_support import *


class RouterTests(unittest.TestCase):
    def test_strong_interrogative_action_question_prefers_consult(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("删除操作会影响哪些表？", skills=skills)

            self.assertEqual(route.route_name, "consult")

    def test_request_like_question_with_action_does_not_route_to_consult(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("能否帮我修改这段代码？", skills=skills)

            self.assertNotEqual(route.route_name, "consult")

    def test_question_mark_edit_request_does_not_route_to_consult(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("帮我删除这个文件？", skills=skills)

            self.assertNotEqual(route.route_name, "consult")

    def test_short_action_request_without_file_scope_routes_to_light_iterate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("帮我添加日志", skills=skills)

            self.assertEqual(route.route_name, "light_iterate")
            self.assertEqual(route.plan_level, "light")

    def test_short_architecture_action_request_still_routes_to_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("重构整个认证模块，把 session 改成 JWT", skills=skills)

            self.assertEqual(route.route_name, "workflow")

    def test_quick_fix_and_consult_output_hide_repo_local_runtime_wording(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            quick_fix_output = render_runtime_output(
                run_runtime("修改 README.md 的错别字", workspace_root=workspace, user_home=workspace / "home"),
                brand="demo-ai",
                language="zh-CN",
            )
            consult_output = render_runtime_output(
                run_runtime("为什么删除操作会影响这些表？", workspace_root=workspace, user_home=workspace / "home"),
                brand="demo-ai",
                language="zh-CN",
            )

            self.assertNotIn("repo-local runtime", quick_fix_output)
            self.assertNotIn("repo-local runtime", consult_output)
            self.assertNotIn("未执行代码修改", quick_fix_output)
            self.assertNotIn("不生成正文回答", consult_output)
            self.assertIn("快速修复", quick_fix_output)
            self.assertIn("咨询问答", consult_output)

    def test_route_classification_and_active_flow_intents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            plan_route = router.classify("~go plan 补 runtime 骨架", skills=skills)
            archive_route = router.classify("~go finalize", skills=skills)
            self.assertEqual(plan_route.route_name, "plan_only")
            self.assertTrue(plan_route.should_create_plan)
            self.assertEqual(archive_route.route_name, "workflow")
            self.assertEqual(archive_route.command, "~go")

            run_state = RunState(
                run_id="run-1",
                status="active",
                stage="plan_ready",
                route_name="workflow",
                title="Runtime",
                created_at=iso_now(),
                updated_at=iso_now(),
            )
            store.set_current_run(run_state)
            resume_route = router.classify("继续", skills=skills)
            cancel_route = router.classify("取消", skills=skills)
            replay_route = router.classify("回放最近一次实现", skills=skills)
            summary_route = router.classify("~summary", skills=skills)
            consult_route = router.classify("这个方案为什么要这样拆？", skills=skills)

            self.assertEqual(resume_route.route_name, "resume_active")
            self.assertTrue(resume_route.should_recover_context)
            self.assertEqual(cancel_route.route_name, "cancel_active")
            self.assertEqual(replay_route.route_name, "replay")
            self.assertEqual(summary_route.route_name, "summary")
            self.assertEqual(summary_route.capture_mode, "off")
            self.assertEqual(consult_route.route_name, "consult")

    def test_consult_guard_for_process_semantics_forces_runtime_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("design 阶段现在怎么收口？", skills=skills)

            self.assertEqual(route.route_name, "workflow")
            self.assertEqual(route.plan_package_policy, "immediate")
            self.assertTrue(route.should_create_plan)
            self.assertEqual(
                route.artifacts.get("entry_guard_reason_code"),
                DIRECT_EDIT_BLOCKED_RUNTIME_REQUIRED_REASON_CODE,
            )

    def test_negated_new_plan_phrase_does_not_force_immediate_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("~go 不要新建新的 plan 包，直接在当前 plan 上细化 tasks", skills=skills)

            self.assertEqual(route.route_name, "workflow")
            self.assertEqual(route.plan_package_policy, "immediate")
            self.assertTrue(route.should_create_plan)

    def test_consult_guard_falls_back_when_tradeoff_or_long_term_split_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("长期契约上是继续手写 catalog 还是改成生成链？", skills=skills)

            self.assertEqual(route.route_name, "workflow")
            self.assertIn("tradeoff or long-term contract split", route.reason)
            self.assertEqual(
                route.artifacts.get("entry_guard_reason_code"),
                DIRECT_EDIT_BLOCKED_RUNTIME_REQUIRED_REASON_CODE,
            )

    def test_active_plan_meta_review_with_followup_edit_does_not_route_to_consult(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            plan_artifact = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
            store.set_current_plan(plan_artifact)
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("review 一下然后改一下 tasks", skills=skills)

            self.assertIn(route.route_name, {"workflow", "light_iterate"})

    def test_active_plan_meta_review_with_punctuated_followup_edit_does_not_route_to_consult(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            plan_artifact = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
            store.set_current_plan(plan_artifact)
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("review 一下，然后改一下 tasks", skills=skills)

            self.assertIn(route.route_name, {"workflow", "light_iterate"})

    def test_active_plan_meta_review_with_reverse_order_edit_does_not_route_to_consult(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            plan_artifact = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
            store.set_current_plan(plan_artifact)
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("改一下 tasks，然后 review 一下", skills=skills)

            self.assertIn(route.route_name, {"workflow", "light_iterate"})

    def test_active_plan_risk_review_without_plan_anchor_stays_light_iterate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            plan_artifact = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
            store.set_current_plan(plan_artifact)
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("分析下风险", skills=skills)

            self.assertEqual(route.route_name, "light_iterate")

    def test_active_plan_design_risk_without_plan_anchor_stays_light_iterate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            plan_artifact = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
            store.set_current_plan(plan_artifact)
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("分析下设计风险", skills=skills)

            self.assertEqual(route.route_name, "light_iterate")

    def test_active_plan_meta_review_with_neutral_middle_fragment_and_followup_edit_does_not_route_to_consult(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            plan_artifact = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
            store.set_current_plan(plan_artifact)
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("review 一下，先确认风险，再改一下 tasks", skills=skills)

            self.assertIn(route.route_name, {"workflow", "light_iterate"})

    def test_active_plan_risk_review_with_followup_edit_does_not_route_to_consult(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            plan_artifact = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
            store.set_current_plan(plan_artifact)
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("看下风险，再改一下 tasks", skills=skills)

            self.assertIn(route.route_name, {"workflow", "light_iterate"})

    def test_active_plan_status_review_with_followup_edit_does_not_route_to_consult(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            plan_artifact = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
            store.set_current_plan(plan_artifact)
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("状态如何，再改一下 tasks", skills=skills)

            self.assertIn(route.route_name, {"workflow", "light_iterate"})

    def test_active_plan_natural_status_review_with_followup_edit_does_not_route_to_consult(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            plan_artifact = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
            store.set_current_plan(plan_artifact)
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("看下这个方案状态，再改下 tasks", skills=skills)

            self.assertNotEqual(route.route_name, "consult")

    def test_plan_materialization_meta_debug_does_not_hijack_normal_issue_fix_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            route = router.classify("这是一个性能问题，需要优化数据库查询", skills=skills)

            self.assertEqual(route.route_name, "light_iterate")
            self.assertNotIn("meta-debug", route.reason)

    def test_ready_plan_routes_continue_and_exec_into_execution_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config, store, _ = _prepare_ready_plan_state(workspace)
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            continue_route = router.classify("继续", skills=skills)
            exec_route = router.classify("~go exec", skills=skills)
            revise_route = router.classify("先把风险部分再展开一点", skills=skills)

            self.assertEqual(continue_route.route_name, "execution_confirm_pending")
            self.assertEqual(continue_route.active_run_action, "confirm_execution")
            self.assertEqual(exec_route.route_name, "execution_confirm_pending")
            self.assertEqual(exec_route.active_run_action, "inspect_execution_confirm")
            self.assertEqual(revise_route.route_name, "execution_confirm_pending")
            self.assertEqual(revise_route.active_run_action, "revise_execution")

    def test_ready_plan_does_not_hijack_unrelated_requests_into_execution_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config, store, _ = _prepare_ready_plan_state(workspace)
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            quick_fix_route = router.classify("修改 README 里的 helper 路径说明", skills=skills)
            consult_route = router.classify("解释一下 execution_confirm_pending 和 decision_pending 的区别", skills=skills)

            self.assertEqual(quick_fix_route.route_name, "quick_fix")
            self.assertIsNone(quick_fix_route.active_run_action)
            self.assertEqual(consult_route.route_name, "consult")
            self.assertIsNone(consult_route.active_run_action)

    def test_pending_clarification_intercepts_exec_and_accepts_answers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            run_runtime("~go plan 优化一下", workspace_root=workspace, user_home=workspace / "home")

            blocked_exec = router.classify("~go exec", skills=skills)
            answer = router.classify("目标是 runtime/router.py，预期结果是补状态骨架", skills=skills)

            self.assertEqual(blocked_exec.route_name, "clarification_pending")
            self.assertEqual(answer.route_name, "clarification_resume")

    def test_pending_clarification_submission_routes_to_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            run_runtime("~go plan 优化一下", workspace_root=workspace, user_home=workspace / "home")

            store = StateStore(load_runtime_config(workspace))
            store.set_current_clarification_response(
                response_text="目标范围：runtime/router.py\n预期结果：补结构化 clarification bridge。",
                response_fields={
                    "target_scope": "runtime/router.py",
                    "expected_outcome": "补结构化 clarification bridge。",
                },
                response_source="cli",
                response_message="host form submitted",
            )

            resumed = router.classify("继续", skills=skills)

            self.assertEqual(resumed.route_name, "clarification_resume")
            self.assertEqual(resumed.active_run_action, "clarification_response_from_state")

    def test_pending_decision_intercepts_exec_until_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            blocked_exec = router.classify("~go exec", skills=skills)
            self.assertEqual(blocked_exec.route_name, "decision_pending")
            self.assertEqual(blocked_exec.active_run_action, "inspect_decision")

    def test_state_conflict_routes_to_inspect_until_user_cancels(self) -> None:
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

            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            inspect_route = router.classify("看看状态", skills=skills)
            cancel_route = router.classify("强制取消", skills=skills)

            self.assertEqual(inspect_route.route_name, "state_conflict")
            self.assertEqual(inspect_route.active_run_action, "inspect_conflict")
            self.assertEqual(inspect_route.artifacts["state_conflict"]["code"], "resolution_id_mismatch")
            self.assertEqual(cancel_route.route_name, "state_conflict")
            self.assertEqual(cancel_route.active_run_action, "abort_conflict")

    def test_pending_decision_submission_routes_to_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            store.set_current_decision_submission(
                DecisionSubmission(
                    status="submitted",
                    source="cli",
                    answers={"selected_option_id": "option_1"},
                    submitted_at=iso_now(),
                    resume_action="submit",
                )
            )

            resumed = router.classify("继续", skills=skills)

            self.assertEqual(resumed.route_name, "decision_resume")
            self.assertEqual(resumed.active_run_action, "resume_submitted_decision")

    def test_route_skill_resolution_prefers_declarative_supports_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            user_home = workspace / "home"
            custom_skill = workspace / "skills" / "decision-helper"
            custom_skill.mkdir(parents=True)
            (custom_skill / "SKILL.md").write_text(
                "---\nname: decision-helper\ndescription: custom pending decision helper\n---\n\n# decision-helper\n",
                encoding="utf-8",
            )
            (custom_skill / "skill.yaml").write_text(
                "id: decision-helper\n"
                "mode: advisory\n"
                "supports_routes:\n"
                "  - decision_pending\n"
                "  - decision_resume\n"
                "metadata:\n"
                "  priority: 1\n",
                encoding="utf-8",
            )

            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=user_home,
            )

            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=user_home).discover()

            blocked_exec = router.classify("~go exec", skills=skills)

            self.assertEqual(blocked_exec.route_name, "decision_pending")
            self.assertEqual(blocked_exec.candidate_skill_ids, ("decision-helper",))

    def test_route_skill_resolution_falls_back_when_supports_routes_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            user_home = workspace / "home"
            custom_skill = workspace / "skills" / "decision-helper"
            custom_skill.mkdir(parents=True)
            (custom_skill / "SKILL.md").write_text(
                "---\nname: decision-helper\ndescription: custom helper without route metadata\n---\n\n# decision-helper\n",
                encoding="utf-8",
            )
            (custom_skill / "skill.yaml").write_text(
                "id: decision-helper\n"
                "mode: advisory\n",
                encoding="utf-8",
            )

            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=user_home,
            )

            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=user_home).discover()

            blocked_exec = router.classify("~go exec", skills=skills)

            self.assertEqual(blocked_exec.route_name, "decision_pending")
            self.assertEqual(blocked_exec.candidate_skill_ids, ("design",))

    def test_route_skill_resolution_prefers_workspace_declarative_workflow_over_builtin_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            user_home = workspace / "home"
            custom_skill = workspace / ".agents" / "skills" / "custom-workflow"
            custom_skill.mkdir(parents=True)
            (custom_skill / "SKILL.md").write_text(
                "---\nname: custom-workflow\ndescription: custom workflow helper\n---\n\n# custom-workflow\n",
                encoding="utf-8",
            )
            (custom_skill / "skill.yaml").write_text(
                "id: custom-workflow\n"
                "mode: workflow\n"
                "supports_routes:\n"
                "  - workflow\n"
                "metadata:\n"
                "  priority: 1\n",
                encoding="utf-8",
            )

            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=user_home).discover()

            decision = router.classify("重构 runtime adapter 和 workflow 引擎", skills=skills)

            self.assertEqual(decision.route_name, "workflow")
            self.assertEqual(decision.candidate_skill_ids, ("custom-workflow", "analyze", "design", "develop"))

    def test_runtime_skill_resolution_prefers_workspace_runtime_skill_over_builtin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            user_home = workspace / "home"
            custom_skill = workspace / ".agents" / "skills" / "custom-replay"
            custom_skill.mkdir(parents=True)
            (custom_skill / "SKILL.md").write_text(
                "---\nname: custom-replay\ndescription: custom replay helper\n---\n\n# custom-replay\n",
                encoding="utf-8",
            )
            (custom_skill / "skill.yaml").write_text(
                "id: custom-replay\n"
                "mode: runtime\n"
                "runtime_entry: custom_runtime.py\n"
                "supports_routes:\n"
                "  - replay\n"
                "host_support:\n"
                "  - codex\n"
                "permission_mode: dual\n"
                "metadata:\n"
                "  priority: 1\n",
                encoding="utf-8",
            )
            (custom_skill / "custom_runtime.py").write_text(
                "def run_skill(**kwargs):\n    return {'ok': True}\n",
                encoding="utf-8",
            )

            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=user_home).discover()

            decision = router.classify("回放最近一次实现", skills=skills)

            self.assertEqual(decision.route_name, "replay")
            self.assertEqual(decision.candidate_skill_ids, ("custom-replay", "workflow-learning"))
            self.assertEqual(decision.runtime_skill_id, "custom-replay")

    def test_runtime_handoff_preserves_direct_edit_runtime_required_reason_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            result = run_runtime(
                "design 阶段现在怎么收口？",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            self.assertIsNotNone(result.handoff)
            assert result.handoff is not None
            self.assertEqual(
                result.handoff.artifacts.get("entry_guard_reason_code"),
                DIRECT_EDIT_BLOCKED_RUNTIME_REQUIRED_REASON_CODE,
            )

    def test_runtime_state_files_expose_request_observability(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            run_runtime(
                "~go plan 补 runtime gate 骨架",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            current_run_payload = json.loads((workspace / ".sopify-skills" / "state" / "current_run.json").read_text(encoding="utf-8"))
            current_handoff_payload = json.loads((workspace / ".sopify-skills" / "state" / "current_handoff.json").read_text(encoding="utf-8"))

            self.assertIn("补 runtime gate 骨架", current_run_payload["request_excerpt"])
            self.assertTrue(current_run_payload["request_sha1"])
            self.assertEqual(current_run_payload["observability"]["state_kind"], "current_run")
            self.assertIn("补 runtime gate 骨架", current_handoff_payload["observability"]["request_excerpt"])
            self.assertTrue(current_handoff_payload["observability"]["request_sha1"])
            self.assertEqual(current_handoff_payload["observability"]["state_kind"], "current_handoff")
