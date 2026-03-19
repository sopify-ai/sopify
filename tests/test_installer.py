from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from installer.hosts.codex import CODEX_ADAPTER
from installer.models import InstallPhaseResult, InstallResult, parse_install_target
from installer.payload import _payload_is_current, install_global_payload
from scripts.install_sopify import render_result


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _create_incomplete_payload(*, home_root: Path, version: str) -> Path:
    payload_root = CODEX_ADAPTER.payload_root(home_root)
    bundle_root = payload_root / "bundle"

    _write_json(
        payload_root / "payload-manifest.json",
        {
            "schema_version": "1",
            "payload_version": version,
            "bundle_version": version,
            "bundle_manifest": "bundle/manifest.json",
            "bundle_template_dir": "bundle",
            "helper_entry": "helpers/bootstrap_workspace.py",
        },
    )
    _write_json(
        bundle_root / "manifest.json",
        {
            "schema_version": "1",
            "bundle_version": version,
            "capabilities": {
                "bundle_role": "control_plane",
                "manifest_first": True,
                "writes_handoff_file": True,
            },
        },
    )
    helper_path = payload_root / "helpers" / "bootstrap_workspace.py"
    helper_path.parent.mkdir(parents=True, exist_ok=True)
    helper_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return payload_root


class PayloadInstallTests(unittest.TestCase):
    def test_payload_is_current_rejects_incomplete_bundle_even_when_versions_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_root = Path(temp_dir)
            payload_root = _create_incomplete_payload(home_root=home_root, version="2026-02-13")

            self.assertFalse(_payload_is_current(payload_root, "2026-02-13"))

    def test_install_global_payload_updates_incomplete_existing_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_root = Path(temp_dir)
            payload_root = _create_incomplete_payload(home_root=home_root, version="2026-02-13")

            result = install_global_payload(
                CODEX_ADAPTER,
                repo_root=REPO_ROOT,
                home_root=home_root,
            )

            self.assertEqual(result.action, "updated")
            self.assertEqual(result.root, payload_root)
            self.assertTrue((payload_root / "bundle" / "scripts" / "clarification_bridge_runtime.py").exists())
            self.assertTrue((payload_root / "bundle" / "scripts" / "decision_bridge_runtime.py").exists())


class InstallRenderTests(unittest.TestCase):
    def test_render_result_reports_already_current_for_noop_install(self) -> None:
        result = _build_install_result(host_action="skipped", payload_action="skipped")

        rendered = render_result(result)

        self.assertTrue(rendered.startswith("Sopify already current:"))
        self.assertIn("No reinstall needed. Trigger Sopify inside any project workspace to bootstrap `.sopify-runtime/` on demand.", rendered)
        self.assertNotIn("Installed Sopify successfully:", rendered)

    def test_render_result_keeps_success_title_when_changes_applied(self) -> None:
        result = _build_install_result(host_action="updated", payload_action="skipped")

        rendered = render_result(result)

        self.assertTrue(rendered.startswith("Installed Sopify successfully:"))
        self.assertIn("Trigger Sopify inside any project workspace to bootstrap `.sopify-runtime/` on demand.", rendered)


def _build_install_result(*, host_action: str, payload_action: str) -> InstallResult:
    host_root = Path("/tmp/home/.codex")
    payload_root = host_root / "sopify"
    return InstallResult(
        target=parse_install_target("codex:zh-CN"),
        workspace_root=None,
        host_root=host_root,
        payload_root=payload_root,
        bundle_root=None,
        host_install=InstallPhaseResult(
            action=host_action,
            root=host_root,
            version="2026-02-13",
            paths=(host_root / "AGENTS.md",),
        ),
        payload_install=InstallPhaseResult(
            action=payload_action,
            root=payload_root,
            version="2026-02-13",
            paths=(payload_root / "payload-manifest.json",),
        ),
        workspace_bootstrap=None,
        smoke_output="Runtime smoke check passed",
    )


if __name__ == "__main__":
    unittest.main()
