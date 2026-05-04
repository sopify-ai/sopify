from __future__ import annotations

from tests.runtime_test_support import *


class ExecutionGateTests(unittest.TestCase):
    def test_execution_gate_blocks_scaffold_until_scope_is_concrete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            plan_artifact = create_plan_scaffold("实现 runtime skeleton", config=config, level="standard")
            route = RouteDecision(
                route_name="workflow",
                request_text="实现 runtime skeleton",
                reason="test",
                complexity="complex",
                plan_level="standard",
            )

            gate = evaluate_execution_gate(
                decision=route,
                plan_artifact=plan_artifact,
                current_clarification=None,
                current_decision=None,
                config=config,
            )

            self.assertEqual(gate.gate_status, "blocked")
            self.assertEqual(gate.blocking_reason, "missing_info")
            self.assertEqual(gate.plan_completion, "incomplete")
            self.assertEqual(gate.next_required_action, "continue_host_develop")

    def test_execution_gate_marks_complete_plan_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            plan_artifact = create_plan_scaffold("实现 runtime skeleton", config=config, level="standard")
            _rewrite_background_scope(
                workspace,
                plan_artifact,
                scope_lines=("runtime/router.py, runtime/engine.py", "runtime/router.py, runtime/engine.py, tests/test_runtime_engine.py"),
            )
            route = RouteDecision(
                route_name="workflow",
                request_text="实现 runtime skeleton",
                reason="test",
                complexity="complex",
                plan_level="standard",
            )

            gate = evaluate_execution_gate(
                decision=route,
                plan_artifact=plan_artifact,
                current_clarification=None,
                current_decision=None,
                config=config,
            )

            self.assertEqual(gate.gate_status, "ready")
            self.assertEqual(gate.blocking_reason, "none")
            self.assertEqual(gate.plan_completion, "complete")
            self.assertEqual(gate.next_required_action, "continue_host_develop")

    def test_execution_gate_rejects_plan_without_knowledge_sync_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
            plan_artifact = create_plan_scaffold("实现 runtime skeleton", config=config, level="standard")
            tasks_path = workspace / plan_artifact.path / "tasks.md"
            tasks_text = tasks_path.read_text(encoding="utf-8")
            tasks_text = tasks_text.replace(
                "knowledge_sync:\n  project: review\n  background: review\n  design: review\n  tasks: review\n",
                "blueprint_obligation: review_required\n",
            )
            tasks_path.write_text(tasks_text, encoding="utf-8")
            _rewrite_background_scope(
                workspace,
                plan_artifact,
                scope_lines=("runtime/router.py, runtime/engine.py", "runtime/router.py, runtime/engine.py, tests/test_runtime_engine.py"),
            )
            route = RouteDecision(
                route_name="workflow",
                request_text="实现 runtime skeleton",
                reason="test",
                complexity="complex",
                plan_level="standard",
            )

            gate = evaluate_execution_gate(
                decision=route,
                plan_artifact=plan_artifact,
                current_clarification=None,
                current_decision=None,
                config=config,
            )

            self.assertEqual(gate.gate_status, "blocked")
            self.assertEqual(gate.blocking_reason, "missing_info")
            self.assertEqual(gate.plan_completion, "incomplete")

    def test_execution_gate_requires_decision_for_auth_boundary_risk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config = load_runtime_config(workspace)
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
            )

            gate = evaluate_execution_gate(
                decision=route,
                plan_artifact=plan_artifact,
                current_clarification=None,
                current_decision=None,
                config=config,
            )

            self.assertEqual(gate.gate_status, "decision_required")
            self.assertEqual(gate.blocking_reason, "auth_boundary")
            self.assertEqual(gate.plan_completion, "complete")
            self.assertEqual(gate.next_required_action, "confirm_decision")
