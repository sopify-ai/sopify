from __future__ import annotations

from tests.runtime_test_support import *
from runtime.archive_lifecycle import apply_archive_subject, resolve_archive_subject


class PlanRegistryTests(unittest.TestCase):
    def test_plan_scaffold_auto_upserts_registry_with_suggested_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            artifact = create_plan_scaffold("实现 runtime skeleton", config=config, level="standard")

            registry_file = workspace / registry_relative_path(config)
            self.assertTrue(registry_file.exists())

            read_result = read_plan_registry(config)
            self.assertEqual(read_result.payload["mode"], "observe_only")
            self.assertEqual(read_result.payload["selection_policy"], "explicit_only")
            self.assertEqual(read_result.payload["priority_policy"], "heuristic_v1")

            entry_result = get_plan_entry(config=config, plan_id=artifact.plan_id)
            self.assertIsNotNone(entry_result.entry)
            assert entry_result.entry is not None
            self.assertEqual(entry_result.entry["snapshot"]["path"], artifact.path)
            self.assertEqual(entry_result.entry["snapshot"]["title"], artifact.title)
            self.assertIsNone(entry_result.entry["governance"]["priority"])
            self.assertIsNone(entry_result.entry["governance"]["priority_source"])
            self.assertEqual(entry_result.entry["governance"]["status"], "todo")
            self.assertEqual(entry_result.entry["advice"]["suggested_priority"], "p2")
            self.assertTrue(entry_result.entry["advice"]["suggested_reason"])

    def test_missing_registry_backfills_existing_plan_dirs_on_next_create(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            first = create_plan_scaffold("补 runtime 骨架", config=config, level="standard")
            registry_file = workspace / registry_relative_path(config)
            registry_file.unlink()

            second = create_plan_scaffold("实现 runtime skeleton", config=config, level="standard")

            read_result = read_plan_registry(config)
            plan_ids = {entry["plan_id"] for entry in read_result.payload["plans"]}
            self.assertEqual(plan_ids, {first.plan_id, second.plan_id})

    def test_reconcile_updates_snapshot_without_overwriting_confirmed_governance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            artifact = create_plan_scaffold("实现 runtime skeleton", config=config, level="standard")
            confirm_plan_priority(
                config=config,
                plan_id=artifact.plan_id,
                priority="p1",
                note="用户确认先做",
            )

            plan_dir = workspace / artifact.path
            renamed_dir = plan_dir.with_name(f"{plan_dir.name}-renamed")
            plan_dir.rename(renamed_dir)
            tasks_path = renamed_dir / "tasks.md"
            tasks_text = tasks_path.read_text(encoding="utf-8")
            tasks_text = tasks_text.replace("level: standard", "level: full")
            tasks_text = tasks_text.replace("feature_key: runtime-skeleton", "feature_key: runtime-renamed")
            tasks_text = tasks_text.replace("# 任务清单: 实现 runtime skeleton", "# 任务清单: 重命名后的方案标题")
            tasks_path.write_text(tasks_text, encoding="utf-8")

            entry_result = get_plan_entry(config=config, plan_id=artifact.plan_id, reconcile=True)
            self.assertIsNotNone(entry_result.entry)
            assert entry_result.entry is not None
            self.assertTrue(entry_result.drift_notice)
            self.assertEqual(
                entry_result.entry["snapshot"]["path"],
                str(renamed_dir.relative_to(workspace)),
            )
            self.assertEqual(entry_result.entry["snapshot"]["title"], "重命名后的方案标题")
            self.assertEqual(entry_result.entry["snapshot"]["level"], "full")
            self.assertEqual(entry_result.entry["snapshot"]["topic_key"], "runtime-renamed")
            self.assertEqual(entry_result.entry["governance"]["priority"], "p1")
            self.assertEqual(entry_result.entry["governance"]["priority_source"], "user_confirmed")
            self.assertEqual(entry_result.entry["governance"]["note"], "用户确认先做")

    def test_archive_removes_entry_from_active_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            artifact = create_plan_scaffold("实现 runtime skeleton", config=config, level="standard")
            store.set_current_plan(artifact)

            result = apply_archive_subject(
                config=config,
                state_store=store,
                subject=resolve_archive_subject(
                    {
                        "ref_kind": "current_plan",
                        "ref_value": "",
                        "source": "current_plan",
                        "allow_current_plan_fallback": True,
                    },
                    config=config,
                    state_store=store,
                    current_plan=artifact,
                ),
            )

            self.assertIsNotNone(result.archived_plan)
            self.assertTrue(result.registry_updated)
            read_result = read_plan_registry(config)
            plan_ids = {entry["plan_id"] for entry in read_result.payload["plans"]}
            self.assertNotIn(artifact.plan_id, plan_ids)

    def test_readonly_recommendations_keep_current_plan_and_explain_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            current_plan = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
            store.set_current_plan(current_plan)
            backlog_plan = create_plan_scaffold("补 runtime 骨架", config=config, level="standard")

            recommendations = recommend_plan_candidates(config=config)

            self.assertTrue(recommendations)
            self.assertEqual(recommendations[0].plan_id, current_plan.plan_id)
            self.assertEqual(store.get_current_plan().plan_id, current_plan.plan_id)
            backlog = next(item for item in recommendations if item.plan_id == backlog_plan.plan_id)
            self.assertEqual(backlog.suggested_priority, "p3")
            self.assertTrue(any("不建议直接切换" in reason for reason in backlog.reasons))

    def test_recommendations_prefer_user_confirmed_priority_over_unconfirmed_suggestion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            suggested_plan = create_plan_scaffold("紧急修 runtime blocker", config=config, level="standard")
            confirmed_plan = create_plan_scaffold("补 runtime 骨架", config=config, level="standard")
            confirm_plan_priority(
                config=config,
                plan_id=confirmed_plan.plan_id,
                priority="p2",
                note="用户确认先做",
            )

            recommendations = recommend_plan_candidates(config=config, request_text="紧急修 runtime blocker")

            self.assertEqual(recommendations[0].plan_id, confirmed_plan.plan_id)
            self.assertEqual(recommendations[0].priority_source, "user_confirmed")
            self.assertEqual(recommendations[1].plan_id, suggested_plan.plan_id)
            self.assertEqual(recommendations[1].suggested_priority, "p1")

    def test_inspect_plan_registry_does_not_rewrite_registry_when_advice_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            artifact = create_plan_scaffold("实现 runtime skeleton", config=config, level="standard")

            registry_file = workspace / registry_relative_path(config)
            before = registry_file.read_text(encoding="utf-8")

            with mock.patch("runtime.plan_registry.iso_now", return_value="2099-01-01T00:00:00+00:00"):
                payload = inspect_plan_registry(config=config, plan_id=artifact.plan_id)

            after = registry_file.read_text(encoding="utf-8")
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(before, after)

    def test_runtime_output_shows_suggested_priority_and_registry_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            result = run_runtime(
                "~go plan 实现 runtime skeleton",
                workspace_root=workspace,
                user_home=workspace / "home",
            )
            output = render_runtime_output(
                result,
                brand="test-ai",
                language="zh-CN",
                title_color="none",
                use_color=False,
            )

            self.assertIn("优先级: 建议 p2（待用户确认）", output)
            self.assertIn(".sopify-skills/plan/_registry.yaml", output)

    def test_runtime_output_does_not_report_registry_when_registry_sync_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with mock.patch("runtime.plan_scaffold.upsert_plan_entry", side_effect=PlanRegistryError("boom")):
                result = run_runtime(
                    "~go plan 实现 runtime skeleton",
                    workspace_root=workspace,
                    user_home=workspace / "home",
                )

            output = render_runtime_output(
                result,
                brand="test-ai",
                language="zh-CN",
                title_color="none",
                use_color=False,
            )

            self.assertNotIn(".sopify-skills/plan/_registry.yaml", result.generated_files)
            self.assertNotIn(".sopify-skills/plan/_registry.yaml", output)

    def test_plan_registry_script_inspect_and_confirm_priority_for_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)

            artifact = create_plan_scaffold("实现 runtime skeleton", config=config, level="standard")
            script_path = REPO_ROOT / "scripts" / "plan_registry_runtime.py"

            inspected = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--workspace-root",
                    str(workspace),
                    "inspect",
                    "--plan-id",
                    artifact.plan_id,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(inspected.returncode, 0, msg=inspected.stderr)
            inspect_payload = json.loads(inspected.stdout)
            self.assertEqual(inspect_payload["status"], "ready")
            self.assertEqual(inspect_payload["registry_path"], ".sopify-skills/plan/_registry.yaml")
            self.assertTrue(inspect_payload["execution_truth"]["current_plan_is_machine_truth"])
            self.assertTrue(inspect_payload["execution_truth"]["registry_is_observe_only"])
            self.assertEqual(inspect_payload["selected_plan"]["plan_id"], artifact.plan_id)
            self.assertEqual(inspect_payload["selected_plan"]["advice"]["suggested_priority"], "p2")

            confirmed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--workspace-root",
                    str(workspace),
                    "confirm-priority",
                    "--plan-id",
                    artifact.plan_id,
                    "--priority",
                    "p1",
                    "--note",
                    "用户确认先做",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(confirmed.returncode, 0, msg=confirmed.stderr)
            confirm_payload = json.loads(confirmed.stdout)
            self.assertEqual(confirm_payload["status"], "written")
            self.assertEqual(confirm_payload["plan_id"], artifact.plan_id)
            self.assertEqual(confirm_payload["confirmed_priority"], "p1")
            self.assertEqual(confirm_payload["priority_source"], "user_confirmed")
            self.assertEqual(confirm_payload["selected_plan"]["governance"]["priority"], "p1")
            self.assertEqual(confirm_payload["selected_plan"]["governance"]["note"], "用户确认先做")
            self.assertTrue(confirm_payload["priority_confirmed_at"])

            entry_result = get_plan_entry(config=config, plan_id=artifact.plan_id)
            self.assertIsNotNone(entry_result.entry)
            assert entry_result.entry is not None
            self.assertEqual(entry_result.entry["governance"]["priority"], "p1")
            self.assertEqual(entry_result.entry["governance"]["priority_source"], "user_confirmed")

    def test_inspect_plan_registry_exposes_recommendations_without_switching_current_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            current_plan = create_plan_scaffold("第一性原理协作规则分层落地", config=config, level="standard")
            store.set_current_plan(current_plan)
            backlog_plan = create_plan_scaffold("补 runtime 骨架", config=config, level="standard")

            payload = inspect_plan_registry(config=config, plan_id=backlog_plan.plan_id)

            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["current_plan"]["plan_id"], current_plan.plan_id)
            self.assertEqual(payload["selected_plan"]["plan_id"], backlog_plan.plan_id)
            self.assertTrue(payload["execution_truth"]["current_plan_is_machine_truth"])
            self.assertTrue(any(item["plan_id"] == current_plan.plan_id for item in payload["recommendations"]))
            self.assertEqual(store.get_current_plan().plan_id, current_plan.plan_id)

    def test_archive_receipt_includes_knowledge_sync_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            artifact = create_plan_scaffold("test sync audit", config=config, level="standard")
            store.set_current_plan(artifact)

            result = apply_archive_subject(
                config=config,
                state_store=store,
                subject=resolve_archive_subject(
                    {
                        "ref_kind": "current_plan",
                        "ref_value": "",
                        "source": "current_plan",
                        "allow_current_plan_fallback": True,
                    },
                    config=config,
                    state_store=store,
                    current_plan=artifact,
                ),
            )

            self.assertIsNotNone(result.archived_plan)
            self.assertIsNotNone(result.knowledge_sync_result)
            sync = result.knowledge_sync_result
            self.assertEqual(sync["outcome"], "passed")
            self.assertIn("sync_level", sync)
            self.assertIsInstance(sync["sync_level"], dict)
            # standard level: all keys are "review", no files updated → all in review_pending
            self.assertIn("review_pending", sync)
            self.assertGreater(len(sync["review_pending"]), 0)

    def test_archive_blocked_by_knowledge_sync_preserves_audit_trail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            store = StateStore(config)
            store.ensure()

            artifact = create_plan_scaffold("test blocked audit", config=config, level="full")
            store.set_current_plan(artifact)

            result = apply_archive_subject(
                config=config,
                state_store=store,
                subject=resolve_archive_subject(
                    {
                        "ref_kind": "current_plan",
                        "ref_value": "",
                        "source": "current_plan",
                        "allow_current_plan_fallback": True,
                    },
                    config=config,
                    state_store=store,
                    current_plan=artifact,
                ),
            )

            self.assertIsNone(result.archived_plan)
            self.assertEqual(result.status, "blocked")
            self.assertIsNotNone(result.knowledge_sync_result)
            sync = result.knowledge_sync_result
            self.assertEqual(sync["outcome"], "blocked")
            self.assertIn("required_missing", sync)
            self.assertGreater(len(sync["required_missing"]), 0)
