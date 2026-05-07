from __future__ import annotations

from tests.runtime_test_support import *
from runtime.decision import parse_decision_response


class DecisionContractTests(unittest.TestCase):
    def test_shared_cancel_parser_respects_fail_closed_questions_and_explicit_boundaries(self) -> None:
        decision_state = DecisionState(
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

        self.assertEqual(parse_decision_response(decision_state, "取消这个 checkpoint").action, "cancel")
        self.assertEqual(parse_decision_response(decision_state, "不要取消这个 checkpoint").action, "invalid")
        self.assertEqual(parse_decision_response(decision_state, "取消这个 checkpoint。").action, "cancel")
        self.assertEqual(parse_decision_response(decision_state, "取消这个 checkpoint。为什么还会回到 pending").action, "invalid")
        self.assertEqual(parse_decision_response(decision_state, "取消这个 checkpoint: 为什么还会回到 pending").action, "invalid")
        self.assertEqual(parse_decision_response(decision_state, "取消这个 checkpoint；为什么还会回到 pending").action, "invalid")
        self.assertEqual(parse_decision_response(decision_state, "取消这个 checkpoint?").action, "invalid")
        self.assertEqual(parse_decision_response(decision_state, "取消这个 checkpoint？为什么还会回到 pending").action, "invalid")
        self.assertEqual(parse_decision_response(decision_state, "取消这个 checkpoint，不要取消全部").action, "cancel")
        self.assertEqual(parse_decision_response(decision_state, "取消这个 checkpoint！").action, "cancel")
        self.assertEqual(parse_decision_response(decision_state, "取消这个 checkpoint…").action, "cancel")

    def test_decision_policy_keeps_current_planning_semantic_baseline(self) -> None:
        route = RouteDecision(
            route_name="plan_only",
            request_text="payload 放 host root 还是 workspace/.sopify-runtime",
            reason="test",
            complexity="complex",
            plan_level="standard",
        )

        match = match_decision_policy(route)

        self.assertIsNotNone(match)
        self.assertEqual(match.template_id, "strategy_pick")
        self.assertEqual(match.decision_type, "architecture_choice")
        self.assertEqual(match.option_texts, ("payload 放 host root", "workspace/.sopify-runtime"))

    def test_decision_policy_ignores_non_architecture_alternatives(self) -> None:
        route = RouteDecision(
            route_name="workflow",
            request_text="按钮改红色还是蓝色",
            reason="test",
            complexity="complex",
            plan_level="standard",
        )

        self.assertIsNone(match_decision_policy(route))

    def test_decision_policy_prefers_structured_tradeoff_candidates(self) -> None:
        route = RouteDecision(
            route_name="workflow",
            request_text="重构支付模块",
            reason="test",
            complexity="complex",
            plan_level="standard",
            artifacts={
                "decision_question": "确认支付模块改造路径",
                "decision_summary": "存在两个可执行方案，需要先确认长期方向。",
                "decision_context_files": [
                    ".sopify-skills/blueprint/design.md",
                    ".sopify-skills/project.md",
                ],
                "decision_candidates": [
                    {
                        "id": "incremental",
                        "title": "渐进改造",
                        "summary": "低风险拆分现有支付链路。",
                        "tradeoffs": ["迁移周期更长"],
                        "impacts": ["兼容当前发布节奏"],
                    },
                    {
                        "id": "rewrite",
                        "title": "整体重写",
                        "summary": "统一支付边界与数据模型。",
                        "tradeoffs": ["一次性变更面更大"],
                        "impacts": ["长期一致性更强"],
                        "recommended": True,
                    },
                ],
            },
        )

        match = match_decision_policy(route)

        self.assertIsNotNone(match)
        self.assertEqual(match.policy_id, "design_tradeoff_candidates")
        self.assertEqual(match.question, "确认支付模块改造路径")
        self.assertEqual(match.context_files, (".sopify-skills/blueprint/design.md", ".sopify-skills/project.md"))
        self.assertEqual(match.options[1].option_id, "rewrite")
        self.assertEqual(match.recommended_option_index, 1)

    def test_decision_policy_suppresses_structured_tradeoff_when_preference_locked(self) -> None:
        route = RouteDecision(
            route_name="workflow",
            request_text="重构支付模块",
            reason="test",
            complexity="complex",
            plan_level="standard",
            artifacts={
                "decision_preference_locked": True,
                "decision_candidates": [
                    {"id": "option_1", "title": "方案一", "summary": "低风险", "tradeoffs": ["慢"]},
                    {"id": "option_2", "title": "方案二", "summary": "高一致性", "tradeoffs": ["快但风险高"]},
                ],
            },
        )

        self.assertIsNone(match_decision_policy(route))

    def test_decision_policy_matches_four_standard_policy_choices(self) -> None:
        cases = (
            ("route->skill 声明式 resolver 还是继续硬编码 skill 绑定？", "skill_selection_policy_choice"),
            ("权限执行主体走 host + runtime 双保险还是仅 runtime 自验？", "permission_enforcement_mode_choice"),
            ("catalog 生成时机选构建期静态生成还是运行期动态生成？", "catalog_generation_timing_choice"),
            ("eval SLO 阈值走严格阻断还是仅告警提示？", "eval_slo_threshold_choice"),
        )
        for request_text, expected_policy_id in cases:
            with self.subTest(policy_id=expected_policy_id):
                route = RouteDecision(
                    route_name="workflow",
                    request_text=request_text,
                    reason="test",
                    complexity="complex",
                    plan_level="standard",
                )

                match = match_decision_policy(route)

                self.assertIsNotNone(match)
                assert match is not None
                self.assertEqual(match.policy_id, expected_policy_id)
                self.assertEqual(match.template_id, "strategy_pick")
                self.assertEqual(len(match.option_texts), 2)

    def test_decision_policy_does_not_trigger_standard_policy_without_tradeoff_split(self) -> None:
        cases = (
            "请说明当前 skill 选择策略",
            "请说明权限执行策略",
            "请说明 catalog 生成策略",
            "请说明 eval SLO 阈值策略",
        )
        for request_text in cases:
            with self.subTest(request_text=request_text):
                route = RouteDecision(
                    route_name="workflow",
                    request_text=request_text,
                    reason="test",
                    complexity="complex",
                    plan_level="standard",
                )
                self.assertIsNone(match_decision_policy(route))

    def test_decision_policy_honors_explicit_standard_policy_id_from_artifacts(self) -> None:
        route = RouteDecision(
            route_name="workflow",
            request_text="请确认策略方向",
            reason="test",
            complexity="complex",
            plan_level="standard",
            artifacts={
                "decision_policy_id": "catalog_generation_timing_choice",
                "decision_candidates": [
                    {
                        "id": "build_time",
                        "title": "构建期静态生成",
                        "summary": "发布时生成 catalog。",
                        "tradeoffs": ["发布流水线增加一次生成步骤"],
                    },
                    {
                        "id": "runtime_time",
                        "title": "运行期动态生成",
                        "summary": "按需动态构建 catalog。",
                        "tradeoffs": ["运行期开销更高"],
                    },
                ],
            },
        )

        match = match_decision_policy(route)

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.policy_id, "catalog_generation_timing_choice")
        self.assertEqual(match.trigger_reason, "explicit_standard_policy_id")
        self.assertEqual(match.option_texts, ("构建期静态生成", "运行期动态生成"))

    def test_strategy_pick_template_supports_custom_and_constraint_fields(self) -> None:
        rendered = build_strategy_pick_template(
            checkpoint_id="decision_template_1",
            question="确认方案",
            summary="请选择本轮方向",
            options=(
                DecisionOption(option_id="option_1", title="方案一", summary="保守路径", recommended=True),
                DecisionOption(option_id="option_2", title="方案二", summary="激进路径"),
            ),
            language="zh-CN",
            recommended_option_id="option_1",
            default_option_id="option_1",
            allow_custom_option=True,
            constraint_field_type="input",
        )

        self.assertEqual(len(rendered.options), 3)
        self.assertEqual(rendered.options[-1].option_id, CUSTOM_OPTION_ID)
        self.assertEqual(len(rendered.checkpoint.fields), 3)
        self.assertEqual(rendered.checkpoint.fields[0].field_id, PRIMARY_OPTION_FIELD_ID)
        self.assertEqual(rendered.checkpoint.fields[1].field_type, "textarea")
        self.assertEqual(rendered.checkpoint.fields[1].when[0].value, CUSTOM_OPTION_ID)
        self.assertEqual(rendered.checkpoint.fields[2].field_type, "input")

    def test_cli_decision_bridge_exposes_interactive_contract_and_text_fallback(self) -> None:
        rendered = build_strategy_pick_template(
            checkpoint_id="decision_template_cli",
            question="确认方案",
            summary="请选择本轮方向",
            options=(
                DecisionOption(option_id="option_1", title="方案一", summary="保守路径", recommended=True),
                DecisionOption(option_id="option_2", title="方案二", summary="激进路径"),
            ),
            language="zh-CN",
            recommended_option_id="option_1",
            default_option_id="option_1",
            allow_custom_option=True,
            constraint_field_type="confirm",
        )
        state_store = mock.Mock(spec=StateStore)
        state_store.scope = "global"
        state_store.session_id = None
        state_store.current_handoff_path = Path(".sopify-skills/state/current_handoff.json")
        state_store.current_decision_path = Path(".sopify-skills/state/current_decision.json")
        state_store.relative_path.side_effect = lambda path: str(path)
        context = DecisionBridgeContext(
            state_store=state_store,
            handoff=None,
            decision_state=DecisionState(
                schema_version="2",
                decision_id="decision_template_cli",
                feature_key="decision",
                phase="design",
                status="pending",
                decision_type="architecture_choice",
                question="确认方案",
                summary="请选择本轮方向",
                options=rendered.options,
                checkpoint=rendered.checkpoint,
                recommended_option_id=rendered.recommended_option_id,
                default_option_id=rendered.default_option_id,
            ),
            checkpoint=rendered.checkpoint,
            submission_state={"status": "empty", "has_answers": False, "answer_keys": []},
        )

        bridge = build_cli_decision_bridge(context, language="zh-CN")

        self.assertEqual(bridge["host_kind"], "cli")
        self.assertEqual(bridge["presentation"]["recommended_mode"], "interactive_form")
        self.assertEqual(bridge["steps"][0]["renderer"], "cli.select")
        self.assertEqual(bridge["steps"][0]["fallback_renderer"], "text")
        self.assertEqual(bridge["steps"][1]["ui_kind"], "textarea")
        self.assertEqual(bridge["steps"][1]["fallback_renderer"], "text")
        self.assertEqual(bridge["steps"][2]["ui_kind"], "confirm")

    def test_decision_checkpoint_roundtrip_normalizes_contract_fields(self) -> None:
        checkpoint = DecisionCheckpoint(
            checkpoint_id="decision_contract_1",
            title="选择方案",
            message="请选择最终执行路径",
            fields=(
                DecisionField(
                    field_id="selected_option_id",
                    field_type="select",
                    label="方案",
                    required=True,
                    options=(
                        DecisionOption(option_id="option_1", title="方案一", summary="保守路径", recommended=True),
                        DecisionOption(option_id="option_2", title="方案二", summary="激进路径"),
                    ),
                    validations=(DecisionValidation(rule="required", message="必须选择一个方案"),),
                ),
                DecisionField(
                    field_id="custom_reason",
                    field_type="textarea",
                    label="补充说明",
                    when=(DecisionCondition(field_id="selected_option_id", operator="not_in", value=["option_1"]),),
                ),
            ),
            primary_field_id="selected_option_id",
            recommendation=DecisionRecommendation(
                field_id="selected_option_id",
                option_id="option_1",
                summary="默认推荐方案一",
                reason="风险最低",
            ),
        )

        payload = checkpoint.to_dict()
        payload["fields"][0]["field_type"] = "SELECT"
        payload["fields"][1]["field_type"] = "TEXTAREA"
        payload["fields"][1]["when"][0]["operator"] = "NOT-IN"
        restored = DecisionCheckpoint.from_dict(payload)

        self.assertEqual(restored.fields[0].field_type, "select")
        self.assertEqual(restored.fields[1].field_type, "textarea")
        self.assertEqual(restored.fields[1].when[0].operator, "not_in")
        self.assertEqual(restored.recommendation.option_id, "option_1")

    def test_checkpoint_request_roundtrip_materializes_decision_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            rendered = build_strategy_pick_template(
                checkpoint_id="decision_request_1",
                question="确认方案",
                summary="请选择本轮方向",
                options=(
                    DecisionOption(option_id="option_1", title="方案一", summary="保守路径", recommended=True),
                    DecisionOption(option_id="option_2", title="方案二", summary="激进路径"),
                ),
                language="zh-CN",
                recommended_option_id="option_1",
                default_option_id="option_1",
            )
            decision_state = DecisionState(
                schema_version="2",
                decision_id="decision_request_1",
                feature_key="runtime",
                phase="design",
                status="pending",
                decision_type="architecture_choice",
                question="确认方案",
                summary="请选择本轮方向",
                options=rendered.options,
                checkpoint=rendered.checkpoint,
                recommended_option_id="option_1",
                default_option_id="option_1",
                context_files=("runtime/engine.py",),
                resume_route="workflow",
                request_text="确认方案",
                requested_plan_level="standard",
                capture_mode="summary",
                candidate_skill_ids=("design",),
                policy_id="planning_semantic_split",
                trigger_reason="explicit_architecture_split",
                created_at=iso_now(),
                updated_at=iso_now(),
            )

            request = checkpoint_request_from_decision_state(decision_state)
            materialized = materialize_checkpoint_request(request.to_dict(), config=config)

            self.assertEqual(materialized.required_host_action, "confirm_decision")
            self.assertEqual(materialized.decision_state.decision_id, "decision_request_1")
            self.assertEqual(materialized.decision_state.active_checkpoint.primary_field_id, "selected_option_id")
            self.assertEqual(materialized.decision_state.options[0].option_id, "option_1")

    def test_checkpoint_request_roundtrip_materializes_clarification_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            result = run_runtime("~go plan 优化一下", workspace_root=workspace, user_home=workspace / "home")
            clarification_state = StateStore(load_runtime_config(workspace)).get_current_clarification()

            self.assertEqual(result.route.route_name, "clarification_pending")
            self.assertIsNotNone(clarification_state)

            request = checkpoint_request_from_clarification_state(clarification_state, config=config)
            materialized = materialize_checkpoint_request(request.to_dict(), config=config)

            self.assertEqual(materialized.required_host_action, "answer_questions")
            self.assertEqual(materialized.clarification_state.clarification_id, clarification_state.clarification_id)
            self.assertEqual(materialized.clarification_state.missing_facts, clarification_state.missing_facts)

    def test_materialize_checkpoint_request_rejects_invalid_decision_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            with self.assertRaises(CheckpointRequestError):
                materialize_checkpoint_request(
                    {
                        "schema_version": "1",
                        "checkpoint_kind": "decision",
                        "checkpoint_id": "broken_decision",
                        "source_stage": "design",
                        "source_route": "workflow",
                        "question": "确认方案",
                        "summary": "缺少 options 和 checkpoint。",
                    },
                    config=config,
                )

    def test_materialize_checkpoint_request_rejects_develop_callback_without_resume_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            with self.assertRaisesRegex(CheckpointRequestError, "resume_context"):
                materialize_checkpoint_request(
                    {
                        "schema_version": "1",
                        "checkpoint_kind": "decision",
                        "checkpoint_id": "develop_decision_missing_resume",
                        "source_stage": "develop",
                        "source_route": "resume_active",
                        "question": "继续怎么改？",
                        "summary": "开发中需要用户确认。",
                        "options": [
                            {"id": "option_1", "title": "方案一", "summary": "保守"},
                            {"id": "option_2", "title": "方案二", "summary": "激进"},
                        ],
                    },
                    config=config,
                )

    def test_checkpoint_request_roundtrip_preserves_develop_resume_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            rendered = build_strategy_pick_template(
                checkpoint_id="develop_decision_1",
                question="认证边界是否移动到 adapter 层？",
                summary="开发中已经命中实现分叉，需要用户拍板。",
                options=(
                    DecisionOption(option_id="option_1", title="保持现状", summary="边界不动", recommended=True),
                    DecisionOption(option_id="option_2", title="移动边界", summary="改到 adapter 层"),
                ),
                language="zh-CN",
                recommended_option_id="option_1",
                default_option_id="option_1",
            )
            resume_context = {
                "active_run_stage": "executing",
                "current_plan_path": ".sopify-skills/plan/20260319_feature",
                "task_refs": ["2.1", "2.2"],
                "changed_files": ["runtime/engine.py"],
                "working_summary": "已经接上 develop callback，需要确认认证边界。",
                "verification_todo": ["补 checkpoint contract 测试"],
                "resume_after": "continue_host_develop",
            }
            decision_state = DecisionState(
                schema_version="2",
                decision_id="develop_decision_1",
                feature_key="runtime",
                phase="develop",
                status="pending",
                decision_type="develop_choice",
                question="认证边界是否移动到 adapter 层？",
                summary="开发中已经命中实现分叉，需要用户拍板。",
                options=rendered.options,
                checkpoint=rendered.checkpoint,
                recommended_option_id="option_1",
                default_option_id="option_1",
                context_files=("runtime/engine.py",),
                resume_route="resume_active",
                request_text="继续 develop callback",
                requested_plan_level="standard",
                capture_mode="summary",
                candidate_skill_ids=("develop",),
                policy_id="develop_callback",
                trigger_reason="host_callback",
                resume_context=resume_context,
                created_at=iso_now(),
                updated_at=iso_now(),
            )

            request = checkpoint_request_from_decision_state(decision_state)
            materialized = materialize_checkpoint_request(request.to_dict(), config=config)

            self.assertEqual(materialized.required_host_action, "confirm_decision")
            self.assertEqual(materialized.decision_state.phase, "develop")
            self.assertEqual(materialized.decision_state.resume_context["working_summary"], resume_context["working_summary"])
            self.assertEqual(
                set(DEVELOP_RESUME_CONTEXT_REQUIRED_FIELDS),
                set(materialized.decision_state.resume_context.keys()) & set(DEVELOP_RESUME_CONTEXT_REQUIRED_FIELDS),
            )

    def test_state_store_persists_structured_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            store = StateStore(load_runtime_config(workspace))
            updated = store.set_current_decision_submission(
                DecisionSubmission(
                    status="collecting",
                    source="cli",
                    answers={"selected_option_id": "option_2"},
                    submitted_at=iso_now(),
                    resume_action="submit",
                )
            )

            self.assertIsNotNone(updated)
            self.assertEqual(updated.status, "collecting")
            reloaded = store.get_current_decision()
            self.assertEqual(reloaded.status, "collecting")
            self.assertEqual(reloaded.submission.answers["selected_option_id"], "option_2")

    def test_response_from_submission_uses_legacy_answer_key_fallback(self) -> None:
        decision_state = DecisionState(
            schema_version="2",
            decision_id="decision_submission_1",
            feature_key="decision",
            phase="design",
            status="pending",
            decision_type="architecture_choice",
            question="确认方案",
            summary="请选择方向",
            options=(
                DecisionOption(option_id="option_1", title="方案一", summary="保守路径", recommended=True),
                DecisionOption(option_id="option_2", title="方案二", summary="激进路径"),
            ),
            checkpoint=DecisionCheckpoint(
                checkpoint_id="decision_submission_1",
                title="确认方案",
                message="请选择方向",
                fields=(),
                primary_field_id=None,
            ),
            submission=DecisionSubmission(
                status="submitted",
                source="cli",
                answers={"selected_option_id": "option_2"},
                submitted_at=iso_now(),
                resume_action="submit",
            ),
        )

        response = response_from_submission(decision_state)

        self.assertIsNotNone(response)
        self.assertEqual(response.action, "choose")
        self.assertEqual(response.option_id, "option_2")

    def test_handoff_includes_decision_checkpoint_and_submission_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            pending = run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            self.assertIn("decision_checkpoint", pending.handoff.artifacts)
            self.assertEqual(pending.handoff.artifacts["checkpoint_request"]["checkpoint_kind"], "decision")
            self.assertEqual(pending.handoff.artifacts["decision_submission_state"]["status"], "empty")
            self.assertTrue(pending.handoff.artifacts["entry_guard"]["strict_runtime_entry"])
            self.assertEqual(pending.handoff.artifacts["entry_guard_reason_code"], "entry_guard_decision_pending")

            store = StateStore(load_runtime_config(workspace))
            store.set_current_decision_submission(
                DecisionSubmission(
                    status="submitted",
                    source="cli",
                    answers={"selected_option_id": "option_1"},
                    submitted_at=iso_now(),
                    resume_action="submit",
                )
            )

            inspected = run_runtime("~decide status", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(inspected.route.route_name, "decision_pending")
            self.assertEqual(inspected.handoff.artifacts["decision_checkpoint"]["primary_field_id"], "selected_option_id")
            self.assertEqual(inspected.handoff.artifacts["checkpoint_request"]["checkpoint_id"], inspected.handoff.artifacts["decision_id"])
            self.assertEqual(inspected.handoff.artifacts["decision_submission_state"]["status"], "submitted")
            self.assertEqual(inspected.handoff.artifacts["decision_submission_state"]["answer_keys"], ["selected_option_id"])

    def test_handoff_marks_missing_checkpoint_request_when_tradeoff_candidates_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            decision = RouteDecision(
                route_name="workflow",
                request_text="确认支付模块改造路径",
                reason="test",
                complexity="complex",
                plan_level="standard",
            )

            handoff = build_runtime_handoff(
                config=config,
                decision=decision,
                run_id="run-missing-checkpoint",
                resolved_context=RecoveredContext(),
                current_plan=None,
                kb_artifact=None,
                replay_session_dir=None,
                skill_result={
                    "decision_candidates": [
                        {
                            "id": "incremental",
                            "title": "渐进改造",
                            "summary": "低风险拆分现有支付链路。",
                            "tradeoffs": ["迁移周期更长"],
                        },
                        {
                            "id": "rewrite",
                            "title": "整体重写",
                            "summary": "统一支付边界与数据模型。",
                            "tradeoffs": ["一次性变更面更大"],
                        },
                    ]
                },
                notes=("test",),
            )

            self.assertIsNotNone(handoff)
            self.assertEqual(
                handoff.artifacts.get("checkpoint_request_reason_code"),
                CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED,
            )
            self.assertEqual(
                handoff.artifacts.get("checkpoint_request_error"),
                CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED,
            )

    def test_cli_text_bridge_collects_submission_and_runtime_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            config = load_runtime_config(workspace)
            answers = iter(("1",))

            submission, used_renderer = prompt_cli_decision_submission(
                config=config,
                renderer="auto",
                input_reader=lambda _prompt: next(answers),
                output_writer=lambda _message: None,
            )

            self.assertEqual(used_renderer, "text")
            self.assertEqual(submission.answers["selected_option_id"], "option_1")
            store = StateStore(config)
            updated = store.get_current_decision()
            self.assertIsNotNone(updated)
            self.assertEqual(updated.submission.status, "submitted")
            self.assertEqual(updated.submission.answers["selected_option_id"], "option_1")

            resumed = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(resumed.route.route_name, "plan_only")
            self.assertIsNotNone(resumed.plan_artifact)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_decision.json").exists())

    def test_cli_interactive_bridge_collects_submission_without_text_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            config = load_runtime_config(workspace)

            submission, used_renderer = prompt_cli_decision_submission(
                config=config,
                renderer="interactive",
                input_reader=lambda _prompt: "",
                output_writer=lambda _message: None,
                interactive_session_factory=lambda: _FakeInteractiveSession(single_choice="option_2"),
            )

            self.assertEqual(used_renderer, "interactive")
            self.assertEqual(submission.answers["selected_option_id"], "option_2")
            self.assertEqual(submission.source, "cli_interactive")

    def test_fake_interactive_session_confirm_is_available_for_confirm_fields(self) -> None:
        session = _FakeInteractiveSession(confirm_value=False)

        self.assertFalse(
            session.confirm(
                title="确认方案",
                yes_label="是",
                no_label="否",
                default_value=True,
                instructions="请选择",
            )
        )

    def test_decision_bridge_script_inspect_and_submit_for_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            script_path = REPO_ROOT / "scripts" / "decision_bridge_runtime.py"

            inspected = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
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
            self.assertEqual(inspect_payload["status"], "ready")
            self.assertEqual(inspect_payload["bridge"]["host_kind"], "cli")
            self.assertEqual(inspect_payload["bridge"]["steps"][0]["renderer"], "cli.select")

            submitted = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
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

            self.assertEqual(submitted.returncode, 0, msg=submitted.stderr)
            submit_payload = json.loads(submitted.stdout)
            self.assertEqual(submit_payload["status"], "written")
            self.assertEqual(submit_payload["submission"]["answers"]["selected_option_id"], "option_1")

            store = StateStore(load_runtime_config(workspace))
            updated = store.get_current_decision()
            self.assertIsNotNone(updated)
            self.assertEqual(updated.submission.status, "submitted")
            self.assertEqual(updated.submission.answers["selected_option_id"], "option_1")

    def test_decision_bridge_script_allows_cancel_submission_without_selected_option(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            script_path = REPO_ROOT / "scripts" / "decision_bridge_runtime.py"

            submitted = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--workspace-root",
                    str(workspace),
                    "submit",
                    "--answers-json",
                    "{}",
                    "--status",
                    "cancelled",
                    "--resume-action",
                    "cancel",
                    "--raw-input",
                    "取消这个 checkpoint",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(submitted.returncode, 0, msg=submitted.stderr)
            submit_payload = json.loads(submitted.stdout)
            self.assertEqual(submit_payload["status"], "written")
            self.assertEqual(submit_payload["submission"]["status"], "cancelled")
            self.assertEqual(submit_payload["submission"]["resume_action"], "cancel")
            self.assertEqual(submit_payload["submission"]["answers"], {})

            store = StateStore(load_runtime_config(workspace))
            updated = store.get_current_decision()
            self.assertIsNotNone(updated)
            self.assertIsNotNone(updated.submission)
            self.assertEqual(updated.submission.status, "cancelled")
            self.assertEqual(updated.submission.resume_action, "cancel")
            self.assertEqual(updated.submission.answers, {})
            response = response_from_submission(updated)
            self.assertIsNotNone(response)
            self.assertEqual(response.action, "cancel")

    def test_decision_bridge_rejects_handoff_without_strict_entry_guard_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            config = load_runtime_config(workspace)
            store = StateStore(config)
            handoff = store.get_current_handoff()
            self.assertIsNotNone(handoff)

            payload = handoff.to_dict()
            artifacts = dict(payload.get("artifacts") or {})
            artifacts.pop("entry_guard", None)
            payload["artifacts"] = artifacts
            store.current_handoff_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(DecisionBridgeError, "decision_bridge_handoff_mismatch"):
                load_decision_bridge_context(config=config)

    def test_clarification_bridge_rejects_handoff_with_mismatched_clarification_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime("~go plan 优化一下", workspace_root=workspace, user_home=workspace / "home")
            config = load_runtime_config(workspace)
            store = StateStore(config)
            handoff = store.get_current_handoff()
            self.assertIsNotNone(handoff)

            payload = handoff.to_dict()
            artifacts = dict(payload.get("artifacts") or {})
            artifacts["clarification_id"] = "clarification_fake_001"
            payload["artifacts"] = artifacts
            store.current_handoff_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ClarificationBridgeError, "clarification_bridge_handoff_mismatch"):
                load_clarification_bridge_context(config=config)

    def test_cli_clarification_bridge_exposes_interactive_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime("~go plan 优化一下", workspace_root=workspace, user_home=workspace / "home")
            config = load_runtime_config(workspace)

            context = load_clarification_bridge_context(config=config)
            bridge = build_cli_clarification_bridge(context, language="zh-CN")

            self.assertEqual(bridge["host_kind"], "cli")
            self.assertEqual(bridge["required_host_action"], "answer_questions")
            self.assertEqual(bridge["presentation"]["recommended_mode"], "interactive_form")
            self.assertEqual([step["field_id"] for step in bridge["steps"]], ["target_scope", "expected_outcome"])
            self.assertEqual(bridge["steps"][0]["renderer"], "cli.input")
            self.assertEqual(bridge["steps"][1]["fallback_renderer"], "text")

    def test_cli_clarification_bridge_collects_submission_and_runtime_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime("~go plan 优化一下", workspace_root=workspace, user_home=workspace / "home")
            config = load_runtime_config(workspace)
            answers = iter(("runtime/router.py", "补结构化 clarification bridge。", "."))

            submission, used_renderer = prompt_cli_clarification_submission(
                config=config,
                renderer="auto",
                input_reader=lambda _prompt: next(answers),
                output_writer=lambda _message: None,
            )

            self.assertEqual(used_renderer, "text")
            self.assertEqual(submission["response_fields"]["target_scope"], "runtime/router.py")
            self.assertIn("预期结果", submission["response_text"])
            store = StateStore(config)
            updated = store.get_current_clarification()
            self.assertIsNotNone(updated)
            self.assertEqual(updated.response_source, "cli_text")
            self.assertEqual(updated.response_fields["expected_outcome"], "补结构化 clarification bridge。")

            resumed = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home")

            self.assertEqual(resumed.route.route_name, "plan_only")
            self.assertIsNotNone(resumed.plan_artifact)
            self.assertFalse((workspace / ".sopify-skills" / "state" / "current_clarification.json").exists())

    def test_clarification_bridge_script_inspect_and_submit_for_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_runtime("~go plan 优化一下", workspace_root=workspace, user_home=workspace / "home")
            script_path = REPO_ROOT / "scripts" / "clarification_bridge_runtime.py"

            inspected = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
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
            self.assertEqual(inspect_payload["status"], "ready")
            self.assertEqual(inspect_payload["bridge"]["host_kind"], "cli")
            self.assertEqual(inspect_payload["bridge"]["presentation"]["recommended_mode"], "interactive_form")

            submitted = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--workspace-root",
                    str(workspace),
                    "submit",
                    "--answers-json",
                    '{"target_scope":"runtime/router.py","expected_outcome":"补结构化 clarification bridge。"}',
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(submitted.returncode, 0, msg=submitted.stderr)
            submit_payload = json.loads(submitted.stdout)
            self.assertEqual(submit_payload["status"], "written")
            self.assertEqual(submit_payload["submission"]["response_fields"]["target_scope"], "runtime/router.py")

            store = StateStore(load_runtime_config(workspace))
            updated = store.get_current_clarification()
            self.assertIsNotNone(updated)
            self.assertEqual(updated.response_source, "cli")
            self.assertEqual(updated.response_fields["expected_outcome"], "补结构化 clarification bridge。")

    def test_session_scoped_decision_bridge_reads_and_writes_review_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            session_id = "session-a"
            run_runtime(
                "~go plan payload 放 host root 还是 workspace/.sopify-runtime",
                workspace_root=workspace,
                session_id=session_id,
                user_home=workspace / "home",
            )
            config = load_runtime_config(workspace)

            context = load_decision_bridge_context(config=config, session_id=session_id)
            bridge = build_cli_decision_bridge(context, language="zh-CN")

            self.assertEqual(bridge["state_scope"], "session")
            self.assertEqual(bridge["session_id"], session_id)
            self.assertIn(f"/sessions/{session_id}/", bridge["decision_file"])

            submission, used_renderer = prompt_cli_decision_submission(
                config=config,
                session_id=session_id,
                renderer="text",
                input_reader=lambda _prompt: "1",
                output_writer=lambda _message: None,
            )

            self.assertEqual(used_renderer, "text")
            self.assertEqual(submission.answers["selected_option_id"], "option_1")
            updated = StateStore(config, session_id=session_id).get_current_decision()
            self.assertIsNotNone(updated)
            self.assertEqual(updated.submission.answers["selected_option_id"], "option_1")

    def test_session_scoped_clarification_bridge_reads_and_writes_review_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            session_id = "session-b"
            run_runtime(
                "~go plan 优化一下",
                workspace_root=workspace,
                session_id=session_id,
                user_home=workspace / "home",
            )
            config = load_runtime_config(workspace)

            context = load_clarification_bridge_context(config=config, session_id=session_id)
            bridge = build_cli_clarification_bridge(context, language="zh-CN")

            self.assertEqual(bridge["state_scope"], "session")
            self.assertEqual(bridge["session_id"], session_id)
            self.assertIn(f"/sessions/{session_id}/", bridge["clarification_file"])

            answers = iter(("runtime/router.py", "补结构化 clarification bridge。", "."))
            submission, used_renderer = prompt_cli_clarification_submission(
                config=config,
                session_id=session_id,
                renderer="text",
                input_reader=lambda _prompt: next(answers),
                output_writer=lambda _message: None,
            )

            self.assertEqual(used_renderer, "text")
            self.assertEqual(submission["response_fields"]["target_scope"], "runtime/router.py")
            updated = StateStore(config, session_id=session_id).get_current_clarification()
            self.assertIsNotNone(updated)
            self.assertEqual(updated.response_fields["expected_outcome"], "补结构化 clarification bridge。")

    def test_runtime_without_session_id_keeps_review_state_global(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            result = run_runtime("~go plan 补 runtime 骨架", workspace_root=workspace, user_home=workspace / "home")

            config = load_runtime_config(workspace)
            store = StateStore(config)
            self.assertEqual(result.route.route_name, "plan_only")
            self.assertEqual(store.scope, "global")
            self.assertIsNotNone(store.get_current_run())
            self.assertIsNotNone(store.get_current_plan())
            self.assertFalse((config.state_dir / "sessions").exists())

    def test_state_store_rejects_session_ids_with_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            with self.assertRaisesRegex(ValueError, "Session ID"):
                StateStore(config, session_id="../escape")

    def test_decision_bridge_falls_back_from_session_review_to_global_execution_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            session_id = "session-a"
            config, _, _ = _prepare_ready_plan_state(workspace, session_id=session_id)
            run_runtime(
                "继续",
                workspace_root=workspace,
                session_id=session_id,
                user_home=workspace / "home",
            )

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
                        "task_refs": ["3.1"],
                        "changed_files": ["runtime/engine.py"],
                        "working_summary": "用户反馈可能超出当前 plan 边界。",
                        "verification_todo": ["回到 plan review 后重新整理任务"],
                        "resume_after": "continue_host_develop",
                        "resume_route": "plan_only",
                    },
                },
                config=config,
            )

            context = load_decision_bridge_context(config=config, session_id=session_id)
            bridge = build_cli_decision_bridge(context, language="zh-CN")
            submission, used_renderer = prompt_cli_decision_submission(
                config=config,
                session_id=session_id,
                renderer="text",
                input_reader=lambda _prompt: "1",
                output_writer=lambda _message: None,
            )

            self.assertEqual(context.state_store.scope, "global")
            self.assertIsNone(context.state_store.session_id)
            self.assertEqual(bridge["state_scope"], "global")
            self.assertEqual(bridge["decision_file"], ".sopify-skills/state/current_decision.json")
            self.assertEqual(used_renderer, "text")
            self.assertEqual(submission.answers["selected_option_id"], "option_1")
            updated = StateStore(config).get_current_decision()
            self.assertIsNotNone(updated)
            self.assertEqual(updated.submission.answers["selected_option_id"], "option_1")
            self.assertIsNone(StateStore(config, session_id=session_id).get_current_decision())
