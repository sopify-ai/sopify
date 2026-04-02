#!/usr/bin/env python3
"""Smoke-check installer, global payload bundle, and workspace thin stub in isolation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from installer.hosts import get_host_adapter
from installer.inspection import build_status_payload
from installer.inspection import inspect_payload_bundle_resolution
from installer.models import InstallError, parse_install_target
from installer.outcome_contract import render_outcome_summary
from installer.validate import (
    resolve_payload_bundle_root,
    run_bundle_smoke_check,
    validate_bundle_install,
    validate_host_install,
    validate_payload_install,
    validate_workspace_stub_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an isolated smoke check for install -> global payload bundle -> workspace stub bootstrap."
    )
    parser.add_argument(
        "--target",
        default="codex:zh-CN",
        help="Install target in <host:lang> format. Default: codex:zh-CN",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write the structured smoke result as JSON.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep the temporary home/workspace for inspection instead of deleting it.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    temp_root = Path(tempfile.mkdtemp(prefix="sopify-install-payload-bundle."))
    try:
        result = run_smoke(target_value=args.target, temp_root=temp_root)
        if args.output_json:
            output_path = Path(args.output_json).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (InstallError, RuntimeError, ValueError) as exc:
        failure = {
            "passed": False,
            "target": args.target,
            "error": str(exc),
            "temp_root": str(temp_root),
        }
        if args.output_json:
            output_path = Path(args.output_json).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(failure, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(failure, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        if args.keep_temp:
            print(f"Kept temp root: {temp_root}", file=sys.stderr)
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


def run_smoke(*, target_value: str, temp_root: Path) -> dict[str, Any]:
    target = parse_install_target(target_value)
    adapter = get_host_adapter(target.host)
    temp_home = temp_root / "home"
    workspace_root = temp_root / "workspace"
    temp_home.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)

    install_stdout = _run_install_cli(target_value=target.value, temp_home=temp_home)
    host_root = adapter.destination_root(temp_home)
    payload_root = adapter.payload_root(temp_home)
    bundle_root = workspace_root / ".sopify-runtime"
    helper_path = payload_root / "helpers" / "bootstrap_workspace.py"

    host_paths = validate_host_install(adapter, home_root=temp_home)
    payload_paths = validate_payload_install(payload_root)
    payload_bundle = inspect_payload_bundle_resolution(payload_root=payload_root, host_id=target.host)

    if bundle_root.exists():
        raise RuntimeError("Workspace bundle should not exist before trigger-time bootstrap.")
    if payload_bundle.source_kind != "global_active":
        raise RuntimeError(f"Unexpected payload bundle source_kind: {payload_bundle.source_kind!r}")
    if payload_bundle.reason_code != "PAYLOAD_BUNDLE_READY":
        raise RuntimeError(f"Unexpected payload bundle reason_code: {payload_bundle.reason_code!r}")

    bootstrap_stdout = _run_workspace_bootstrap(helper_path=helper_path, workspace_root=workspace_root)
    workspace_stub_path, workspace_manifest = validate_workspace_stub_manifest(bundle_root)
    global_bundle_root = resolve_payload_bundle_root(payload_root)
    global_bundle_paths = validate_bundle_install(global_bundle_root)
    smoke_stdout = run_bundle_smoke_check(
        global_bundle_root,
        payload_manifest_path=payload_root / "payload-manifest.json",
    )
    status_payload = build_status_payload(home_root=temp_home, workspace_root=workspace_root)
    host_status = next(
        host for host in status_payload["hosts"] if host["host_id"] == target.host
    )
    workspace_bundle = host_status.get("workspace_bundle") or {}
    bundle_manifest = json.loads((global_bundle_root / "manifest.json").read_text(encoding="utf-8"))
    default_entry = str(bundle_manifest.get("default_entry") or "")
    plan_only_entry = str(bundle_manifest.get("plan_only_entry") or "")
    runtime_gate_entry = str(bundle_manifest.get("limits", {}).get("runtime_gate_entry") or "")
    entry_guard = bundle_manifest.get("limits", {}).get("entry_guard", {})

    if default_entry != "scripts/sopify_runtime.py":
        raise RuntimeError(f"Unexpected default_entry: {default_entry!r}")
    if plan_only_entry != "scripts/go_plan_runtime.py":
        raise RuntimeError(f"Unexpected plan_only_entry: {plan_only_entry!r}")
    if runtime_gate_entry != "scripts/runtime_gate.py":
        raise RuntimeError(f"Unexpected runtime_gate_entry: {runtime_gate_entry!r}")
    if entry_guard.get("default_runtime_entry") != default_entry:
        raise RuntimeError("Manifest limits.entry_guard.default_runtime_entry drifted from default_entry.")
    if workspace_bundle.get("reason_code") != "STUB_SELECTED":
        raise RuntimeError(
            "Unexpected workspace bundle reason_code after bootstrap: {!r}".format(
                workspace_bundle.get("reason_code")
            )
        )

    return {
        "passed": True,
        "target": target.value,
        "temp_root": str(temp_root),
        "temp_home": str(temp_home),
        "workspace_root": str(workspace_root),
        "host_root": str(host_root),
        "payload_root": str(payload_root),
        "bundle_root": str(bundle_root),
        "global_bundle_root": str(global_bundle_root),
        "payload_bundle": payload_bundle.to_status_dict(),
        "workspace_bundle": workspace_bundle,
        "path_summary": {
            "payload_source_kind": payload_bundle.source_kind,
            "payload_reason_code": payload_bundle.reason_code,
            "payload_outcome": render_outcome_summary(payload_bundle.to_status_dict()) or None,
            "workspace_reason_code": workspace_bundle.get("reason_code"),
            "workspace_outcome": render_outcome_summary(workspace_bundle) or None,
        },
        "checks": {
            "single_install_command_only": True,
            "workspace_bundle_absent_before_trigger": True,
            "runtime_bootstrap_on_project_trigger": True,
            "default_runtime_entry_preserved": True,
            "plan_only_helper_preserved": True,
            "runtime_gate_entry_preserved": True,
            "workspace_stub_selected_after_bootstrap": True,
            "bundle_smoke_passed": True,
        },
        "manifest": {
            "default_entry": default_entry,
            "plan_only_entry": plan_only_entry,
            "runtime_gate_entry": runtime_gate_entry,
            "entry_guard_default_runtime_entry": entry_guard.get("default_runtime_entry"),
        },
        "install_stdout": install_stdout,
        "bootstrap_stdout": bootstrap_stdout,
        "bundle_smoke_stdout": smoke_stdout,
        "verified_paths": {
            "host": [str(path) for path in host_paths],
            "payload": [str(path) for path in payload_paths],
            "workspace_stub": [str(workspace_stub_path)],
            "global_bundle": [str(path) for path in global_bundle_paths],
        },
    }


def _run_install_cli(*, target_value: str, temp_home: Path) -> str:
    env = dict(os.environ)
    env["HOME"] = str(temp_home)
    completed = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "install-sopify.sh"), "--target", target_value],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "unknown install failure"
        raise InstallError(f"Installer CLI failed: {details}")
    return completed.stdout.strip()


def _run_workspace_bootstrap(*, helper_path: Path, workspace_root: Path) -> str:
    if not helper_path.is_file():
        raise InstallError(f"Missing installed workspace helper: {helper_path}")
    completed = subprocess.run(
        [sys.executable, str(helper_path), "--workspace-root", str(workspace_root)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "unknown bootstrap failure"
        raise InstallError(f"Workspace bootstrap helper failed: {details}")
    return completed.stdout.strip()

if __name__ == "__main__":
    raise SystemExit(main())
