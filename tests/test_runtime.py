from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.config import ConfigError, load_runtime_config
from runtime.engine import run_runtime
from runtime.kb import bootstrap_kb
from runtime.plan_scaffold import create_plan_scaffold
from runtime.output import render_runtime_output
from runtime.replay import ReplayWriter
from runtime.router import Router
from runtime.skill_registry import SkillRegistry
from runtime.state import StateStore, iso_now
from runtime.models import ReplayEvent, RouteDecision, RunState


class RuntimeConfigTests(unittest.TestCase):
    def test_zero_config_uses_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_runtime_config(temp_dir, global_config_path=Path(temp_dir) / "missing.yaml")
            self.assertEqual(config.language, "zh-CN")
            self.assertEqual(config.workflow_mode, "adaptive")
            self.assertEqual(config.plan_directory, ".sopify-skills")
            self.assertFalse(config.multi_model_enabled)
            self.assertTrue(config.brand.endswith("-ai"))

    def test_project_config_overrides_global(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            global_path = workspace / "global.yaml"
            project_path = workspace / "sopify.config.yaml"
            global_path.write_text(
                "language: en-US\nworkflow:\n  require_score: 5\nplan:\n  level: light\n",
                encoding="utf-8",
            )
            project_path.write_text(
                "workflow:\n  require_score: 9\nplan:\n  directory: .runtime\n",
                encoding="utf-8",
            )
            config = load_runtime_config(workspace, global_config_path=global_path)
            self.assertEqual(config.language, "en-US")
            self.assertEqual(config.require_score, 9)
            self.assertEqual(config.plan_level, "light")
            self.assertEqual(config.plan_directory, ".runtime")

    def test_invalid_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "sopify.config.yaml").write_text("workflow:\n  mode: unsupported\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_runtime_config(workspace)

    def test_brand_auto_prefers_package_name_over_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "package.json").write_text('{"name":"sample-workspace"}', encoding="utf-8")
            config = load_runtime_config(workspace, global_config_path=workspace / "missing.yaml")
            self.assertEqual(config.brand, "sample-workspace-ai")


class RouterTests(unittest.TestCase):
    def test_route_classification_and_active_flow_intents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()
            router = Router(config, state_store=store)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()

            plan_route = router.classify("~go plan 补 runtime 骨架", skills=skills)
            self.assertEqual(plan_route.route_name, "plan_only")
            self.assertTrue(plan_route.should_create_plan)

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
            compare_route = router.classify("~compare 方案对比", skills=skills)
            consult_route = router.classify("这个方案为什么要这样拆？", skills=skills)

            self.assertEqual(resume_route.route_name, "resume_active")
            self.assertTrue(resume_route.should_recover_context)
            self.assertEqual(cancel_route.route_name, "cancel_active")
            self.assertEqual(replay_route.route_name, "replay")
            self.assertEqual(compare_route.route_name, "compare")
            self.assertEqual(consult_route.route_name, "consult")


class PlanScaffoldTests(unittest.TestCase):
    def test_plan_scaffold_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            light = create_plan_scaffold("修复登录错误提示", config=config, level="light")
            standard = create_plan_scaffold("实现 runtime skeleton", config=config, level="standard")
            full = create_plan_scaffold("设计 runtime architecture plugin bridge", config=config, level="full")

            self.assertTrue((workspace / light.path / "plan.md").exists())
            self.assertTrue((workspace / standard.path / "background.md").exists())
            self.assertTrue((workspace / standard.path / "design.md").exists())
            self.assertTrue((workspace / standard.path / "tasks.md").exists())
            self.assertTrue((workspace / full.path / "adr").is_dir())
            self.assertTrue((workspace / full.path / "diagrams").is_dir())

    def test_plan_scaffold_avoids_directory_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            first = create_plan_scaffold("补 runtime 骨架", config=config, level="standard")
            second = create_plan_scaffold("补 runtime 骨架", config=config, level="standard")

            self.assertNotEqual(first.path, second.path)
            self.assertTrue(second.path.endswith("-2"))


class ReplayWriterTests(unittest.TestCase):
    def test_replay_writer_creates_append_only_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            writer = ReplayWriter(config)
            event = ReplayEvent(
                ts=iso_now(),
                phase="design",
                intent="创建 plan scaffold",
                action="route:plan_only",
                key_output="password=secret",  # should be redacted
                decision_reason="因为 token=123 需要脱敏",
                result="success",
                risk="Bearer abcdef",
            )
            session_dir = writer.append_event("run-1", event)
            writer.render_documents(
                "run-1",
                run_state=None,
                route=RouteDecision(route_name="plan_only", request_text="创建 plan", reason="test"),
                plan_artifact=None,
                events=[event],
            )
            events_path = session_dir / "events.jsonl"
            self.assertTrue(events_path.exists())
            self.assertIn("<REDACTED>", events_path.read_text(encoding="utf-8"))
            self.assertTrue((session_dir / "session.md").exists())
            self.assertTrue((session_dir / "breakdown.md").exists())


class SkillRegistryTests(unittest.TestCase):
    def test_skill_registry_discovers_builtin_and_project_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            project_skill = workspace / "skills" / "local-demo"
            project_skill.mkdir(parents=True)
            (project_skill / "SKILL.md").write_text(
                "---\nname: local-demo\ndescription: local skill\n---\n\n# local\n",
                encoding="utf-8",
            )
            (project_skill / "skill.yaml").write_text(
                "id: local-demo\nmode: advisory\ntriggers:\n  - local\n",
                encoding="utf-8",
            )
            config = load_runtime_config(workspace)
            skills = SkillRegistry(config, user_home=workspace / "home").discover()
            skill_ids = {skill.skill_id for skill in skills}
            self.assertIn("analyze", skill_ids)
            self.assertIn("model-compare", skill_ids)
            self.assertIn("local-demo", skill_ids)
            model_compare = next(skill for skill in skills if skill.skill_id == "model-compare")
            self.assertEqual(model_compare.mode, "runtime")
            self.assertIsNotNone(model_compare.runtime_entry)


class KnowledgeBaseBootstrapTests(unittest.TestCase):
    def test_progressive_bootstrap_creates_minimal_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            artifact = bootstrap_kb(config)

            self.assertEqual(
                set(artifact.files),
                {
                    ".sopify-skills/project.md",
                    ".sopify-skills/wiki/overview.md",
                    ".sopify-skills/user/preferences.md",
                    ".sopify-skills/history/index.md",
                },
            )
            self.assertIn("当前暂无已确认的长期偏好", (workspace / ".sopify-skills" / "user" / "preferences.md").read_text(encoding="utf-8"))
            self.assertIn("变更历史索引", (workspace / ".sopify-skills" / "history" / "index.md").read_text(encoding="utf-8"))
            self.assertTrue((workspace / ".sopify-skills" / "wiki" / "modules").is_dir())

    def test_full_bootstrap_creates_extended_kb_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "sopify.config.yaml").write_text("advanced:\n  kb_init: full\n", encoding="utf-8")
            config = load_runtime_config(workspace)

            artifact = bootstrap_kb(config)

            self.assertIn(".sopify-skills/wiki/arch.md", artifact.files)
            self.assertIn(".sopify-skills/wiki/api.md", artifact.files)
            self.assertIn(".sopify-skills/wiki/data.md", artifact.files)
            self.assertIn(".sopify-skills/user/feedback.jsonl", artifact.files)

    def test_bootstrap_is_idempotent_and_preserves_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            first = bootstrap_kb(config)
            self.assertTrue(first.files)

            project_path = workspace / ".sopify-skills" / "project.md"
            project_path.write_text("# custom\n", encoding="utf-8")

            second = bootstrap_kb(config)

            self.assertEqual(second.files, ())
            self.assertEqual(project_path.read_text(encoding="utf-8"), "# custom\n")


class EngineIntegrationTests(unittest.TestCase):
    def test_engine_handles_plan_resume_and_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            first = run_runtime("~go plan 补 runtime 骨架", workspace_root=workspace, user_home=workspace / "home")
            self.assertEqual(first.route.route_name, "plan_only")
            self.assertIsNotNone(first.plan_artifact)
            self.assertIsNotNone(first.replay_session_dir)
            self.assertTrue((workspace / ".sopify-skills" / "project.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "wiki" / "overview.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "user" / "preferences.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "history" / "index.md").exists())

            resumed = run_runtime("继续", workspace_root=workspace, user_home=workspace / "home")
            self.assertEqual(resumed.route.route_name, "resume_active")
            self.assertTrue(resumed.recovered_context.has_active_run)
            self.assertTrue(resumed.recovered_context.loaded_files)

            canceled = run_runtime("取消", workspace_root=workspace, user_home=workspace / "home")
            self.assertEqual(canceled.route.route_name, "cancel_active")
            store = StateStore(load_runtime_config(workspace))
            self.assertFalse(store.has_active_flow())

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
            self.assertIn("Next: ~go exec 执行 或 回复修改意见", rendered)

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

    def test_synced_runtime_bundle_runs_in_another_workspace(self) -> None:
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

            bundle_root = target_root / ".sopify-runtime"
            self.assertTrue((bundle_root / "runtime" / "__init__.py").exists())
            self.assertTrue((bundle_root / "scripts" / "check-runtime-smoke.sh").exists())
            self.assertTrue((bundle_root / "tests" / "test_runtime.py").exists())

            runtime_script = bundle_root / "scripts" / "sopify_runtime.py"
            completed = subprocess.run(
                [sys.executable, str(runtime_script), "--workspace-root", str(workspace), "--no-color", "重构数据库层"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn(".sopify-skills/plan/", completed.stdout)
            self.assertTrue((workspace / ".sopify-skills" / "state" / "current_plan.json").exists())
            self.assertTrue((workspace / ".sopify-skills" / "replay" / "sessions").exists())
            self.assertTrue((workspace / ".sopify-skills" / "project.md").exists())
            self.assertTrue((workspace / ".sopify-skills" / "history" / "index.md").exists())


if __name__ == "__main__":
    unittest.main()
