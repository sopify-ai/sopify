"""Helpers for syncing the Sopify runtime bundle into a workspace."""

from __future__ import annotations

from pathlib import Path
import subprocess

from installer.models import InstallError

DEFAULT_BUNDLE_DIRNAME = ".sopify-runtime"


def sync_runtime_bundle(repo_root: Path, workspace_root: Path, *, bundle_dirname: str = DEFAULT_BUNDLE_DIRNAME) -> Path:
    """Sync the runtime bundle into the target workspace using the existing sync script."""
    sync_script = repo_root / "scripts" / "sync-runtime-assets.sh"
    if not sync_script.is_file():
        raise InstallError(f"Missing runtime sync script: {sync_script}")

    completed = subprocess.run(
        ["bash", str(sync_script), str(workspace_root), bundle_dirname],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "unknown sync failure"
        raise InstallError(f"Runtime bundle sync failed: {details}")

    bundle_root = workspace_root / bundle_dirname
    required_paths = (
        bundle_root / "manifest.json",
        bundle_root / "runtime" / "__init__.py",
        bundle_root / "runtime" / "clarification_bridge.py",
        bundle_root / "runtime" / "cli_interactive.py",
        bundle_root / "runtime" / "develop_checkpoint.py",
        bundle_root / "runtime" / "decision_bridge.py",
        bundle_root / "scripts" / "sopify_runtime.py",
        bundle_root / "scripts" / "clarification_bridge_runtime.py",
        bundle_root / "scripts" / "develop_checkpoint_runtime.py",
        bundle_root / "scripts" / "decision_bridge_runtime.py",
        bundle_root / "scripts" / "check-runtime-smoke.sh",
        bundle_root / "tests" / "test_runtime.py",
    )
    missing = [path for path in required_paths if not path.exists()]
    if missing:
        raise InstallError(f"Runtime bundle sync incomplete: {missing[0]}")
    return bundle_root
