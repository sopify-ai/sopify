from __future__ import annotations

from tests.runtime_test_support import *


class KnowledgeLayoutTests(unittest.TestCase):
    def test_consult_profile_returns_l0_index_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "package.json").write_text('{"name":"sample-app"}', encoding="utf-8")
            config = load_runtime_config(workspace)
            bootstrap_kb(config)

            selection = resolve_context_profile(config=config, profile="consult")

            self.assertEqual(selection.materialization_stage, "L0 bootstrap")
            self.assertEqual(
                selection.files,
                (
                    ".sopify-skills/project.md",
                    ".sopify-skills/blueprint/README.md",
                ),
            )

    def test_plan_profile_fail_opens_when_deep_blueprint_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "package.json").write_text('{"name":"sample-app"}', encoding="utf-8")
            config = load_runtime_config(workspace)
            bootstrap_kb(config)

            selection = resolve_context_profile(config=config, profile="plan")

            self.assertEqual(selection.materialization_stage, "L0 bootstrap")
            self.assertEqual(
                selection.files,
                (
                    ".sopify-skills/project.md",
                    ".sopify-skills/blueprint/README.md",
                ),
            )

    def test_detached_plan_directory_does_not_count_as_l2_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "sopify.config.yaml").write_text("advanced:\n  kb_init: full\n", encoding="utf-8")
            config = load_runtime_config(workspace)
            bootstrap_kb(config)
            create_plan_scaffold("重构支付模块", config=config, level="standard")

            selection = resolve_context_profile(config=config, profile="plan")

            self.assertEqual(selection.materialization_stage, "L1 blueprint-ready")

    def test_clarification_profile_fail_opens_under_l0_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "package.json").write_text('{"name":"sample-app"}', encoding="utf-8")
            config = load_runtime_config(workspace)
            bootstrap_kb(config)

            selection = resolve_context_profile(config=config, profile="clarification")

            self.assertEqual(selection.materialization_stage, "L0 bootstrap")
            self.assertEqual(
                selection.files,
                (
                    ".sopify-skills/project.md",
                    ".sopify-skills/blueprint/README.md",
                ),
            )

    def test_decision_profile_includes_active_plan_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "sopify.config.yaml").write_text("advanced:\n  kb_init: full\n", encoding="utf-8")
            config = load_runtime_config(workspace)
            bootstrap_kb(config)
            plan_artifact = create_plan_scaffold("重构支付模块", config=config, level="standard")

            selection = resolve_context_profile(config=config, profile="decision", current_plan=plan_artifact)

            self.assertEqual(selection.materialization_stage, "L2 plan-active")
            self.assertEqual(
                selection.files,
                (
                    ".sopify-skills/project.md",
                    ".sopify-skills/blueprint/design.md",
                    plan_artifact.path,
                    *plan_artifact.files,
                ),
            )

    def test_archive_profile_resolves_l3_context_without_history_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "sopify.config.yaml").write_text("advanced:\n  kb_init: full\n", encoding="utf-8")
            config = load_runtime_config(workspace)
            bootstrap_kb(config)
            plan_artifact = create_plan_scaffold("重构支付模块", config=config, level="standard")
            history_index = workspace / ".sopify-skills" / "history" / "index.md"
            history_index.parent.mkdir(parents=True, exist_ok=True)
            history_index.write_text("# 变更历史索引\n", encoding="utf-8")

            selection = resolve_context_profile(config=config, profile="archive", current_plan=plan_artifact)

            self.assertEqual(materialization_stage(config=config, current_plan=plan_artifact), "L3 history-ready")
            self.assertEqual(selection.materialization_stage, "L3 history-ready")
            self.assertEqual(
                selection.files,
                (
                    plan_artifact.path,
                    *plan_artifact.files,
                    ".sopify-skills/project.md",
                    ".sopify-skills/blueprint/README.md",
                    ".sopify-skills/blueprint/background.md",
                    ".sopify-skills/blueprint/design.md",
                    ".sopify-skills/blueprint/tasks.md",
                ),
            )

    def test_build_decision_state_uses_v2_resolver_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "sopify.config.yaml").write_text("advanced:\n  kb_init: full\n", encoding="utf-8")
            config = load_runtime_config(workspace)
            bootstrap_kb(config)

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

            decision_state = build_decision_state(route, config=config)

            self.assertIsNotNone(decision_state)
            assert decision_state is not None
            self.assertEqual(
                decision_state.context_files,
                (
                    ".sopify-skills/project.md",
                    ".sopify-skills/blueprint/design.md",
                ),
            )
            self.assertNotIn(".sopify-skills/wiki/overview.md", decision_state.context_files)

    def test_build_clarification_state_uses_v2_resolver_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "package.json").write_text('{"name":"sample-app"}', encoding="utf-8")
            config = load_runtime_config(workspace)
            bootstrap_kb(config)

            route = RouteDecision(
                route_name="workflow",
                request_text="帮我优化一下",
                reason="test",
                complexity="complex",
                plan_level="standard",
            )

            clarification_state = build_clarification_state(route, config=config)

            self.assertIsNotNone(clarification_state)
            assert clarification_state is not None
            self.assertEqual(
                clarification_state.context_files,
                (
                    ".sopify-skills/project.md",
                    ".sopify-skills/blueprint/README.md",
                ),
            )
            self.assertNotIn(".sopify-skills/blueprint/tasks.md", clarification_state.context_files)
