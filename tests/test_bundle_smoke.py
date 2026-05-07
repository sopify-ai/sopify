from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.config import load_runtime_config
from runtime.engine import run_runtime
from runtime.gate import enter_runtime_gate


SMOKE_REQUEST = "~go plan 重构数据库层"


class BundleSmokeTests(unittest.TestCase):
    def test_install_payload_bundle_smoke_script_passes(self) -> None:
        script_path = REPO_ROOT / "scripts" / "check-install-payload-bundle-smoke.py"

        completed = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["script"], "scripts/check-install-payload-bundle-smoke.py")
        self.assertTrue(payload["checks"]["single_install_command_only"])
        self.assertTrue(payload["install_surface"]["checks"]["install_output_exposes_global_path"])
        self.assertTrue(payload["legacy_fallback_visibility"]["checks"]["legacy_workspace_fallback_visible"])
        self.assertTrue(payload["legacy_fallback_visibility"]["checks"]["global_bundle_missing_visible"])

    def test_import_runtime_entry(self) -> None:
        self.assertTrue(callable(run_runtime))

    def test_route_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            result = run_runtime(
                SMOKE_REQUEST,
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            self.assertEqual(result.route.route_name, "plan_only")
            self.assertIsNotNone(result.plan_artifact)
            self.assertIsNotNone(result.handoff)
            self.assertEqual(result.handoff.required_host_action, "continue_host_develop")

    def test_gate_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            payload = enter_runtime_gate(
                SMOKE_REQUEST,
                workspace_root=workspace,
                user_home=workspace / "home",
            )

            self.assertEqual(payload["status"], "ready")
            self.assertTrue(payload["gate_passed"])
            self.assertEqual(payload["runtime"]["route_name"], "plan_only")
            self.assertEqual(payload["handoff"]["required_host_action"], "continue_host_develop")
            self.assertEqual(payload["allowed_response_mode"], "normal_runtime_followup")

    def test_config_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "sopify.config.yaml").write_text("plan:\n  directory: .runtime\n", encoding="utf-8")

            config = load_runtime_config(workspace)

            self.assertEqual(config.plan_directory, ".runtime")
            self.assertEqual(config.runtime_root, workspace.resolve() / ".runtime")
