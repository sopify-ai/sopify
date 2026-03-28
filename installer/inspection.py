"""Shared installer inspection helpers for status, doctor, and install surfaces."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from installer.bootstrap_workspace import _classify_workspace_bundle
from installer.hosts import iter_host_registrations
from installer.hosts.base import HostAdapter, HostRegistration
from installer.models import HostCapability, InstallError
from installer.validate import run_bundle_smoke_check, validate_host_install, validate_payload_install
from runtime.config import ConfigError, load_runtime_config
from runtime.context_snapshot import resolve_context_snapshot
from runtime.state import SESSIONS_DIRNAME, StateStore

STATUS_SCHEMA_VERSION = "2"
DOCTOR_SCHEMA_VERSION = "1"
CHECK_PASS = "pass"
CHECK_WARN = "warn"
CHECK_FAIL = "fail"
CHECK_SKIP = "skip"
STATUS_YES = "yes"
STATUS_NO = "no"
STATUS_NOT_REQUESTED = "not_requested"
REASON_OK = "ok"
REASON_WORKSPACE_NOT_REQUESTED = "WORKSPACE_NOT_REQUESTED"
REASON_RUNTIME_STATE_CONFLICT = "RUNTIME_STATE_CONFLICT"
REASON_QUARANTINED_RUNTIME_STATE = "QUARANTINED_RUNTIME_STATE"
REASON_RUNTIME_INSPECTION_UNAVAILABLE = "RUNTIME_INSPECTION_UNAVAILABLE"
STATUS_READY_STATES = {"READY", "NEWER_THAN_GLOBAL"}
STATUS_WARN_STATES = {"MISSING", "OUTDATED_COMPATIBLE"}
_STATE_CONFLICT_EXPLANATIONS = {
    "multiple_pending_checkpoints": "Multiple review checkpoints are simultaneously active and need manual cleanup.",
    "pending_checkpoint_handoff_mismatch": "The active handoff points to one pending checkpoint type, but the persisted state contains another.",
    "execution_confirm_review_checkpoint_conflict": "Execution confirmation is contaminated by residual review-checkpoint state.",
    "run_stage_handoff_mismatch": "The persisted run stage and handoff action disagree about the current checkpoint.",
    "resolution_id_mismatch": "current_run and current_handoff were written by different resolution batches.",
    "resolution_id_mixed_presence": "current_run and current_handoff disagree on whether resolution tracking is present.",
    "proposal_missing_for_pending_handoff": "The handoff expects a plan proposal checkpoint, but no valid proposal state was found.",
    "clarification_missing_for_pending_handoff": "The handoff expects a clarification checkpoint, but no valid clarification state was found.",
    "decision_missing_for_pending_handoff": "The handoff expects a decision checkpoint, but no valid decision state was found.",
}


@dataclass(frozen=True)
class InspectionCheck:
    """One stable inspection result item."""

    check_id: str
    status: str
    reason_code: str
    evidence: tuple[str, ...] = ()
    recommendation: str | None = None
    host_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "check_id": self.check_id,
            "status": self.status,
            "reason_code": self.reason_code,
        }
        if self.host_id is not None:
            payload["host_id"] = self.host_id
        if self.evidence:
            payload["evidence"] = list(self.evidence)
        if self.recommendation:
            payload["recommendation"] = self.recommendation
        return payload


@dataclass(frozen=True)
class HostInspection:
    """All shared inspection facts for one host."""

    registration: HostRegistration
    host_prompt: InspectionCheck
    payload: InspectionCheck
    workspace_bundle: InspectionCheck
    handoff_first: InspectionCheck
    preferences_preload: InspectionCheck
    smoke: InspectionCheck

    @property
    def capability(self) -> HostCapability:
        return self.registration.capability

    @property
    def adapter(self) -> HostAdapter:
        return self.registration.adapter

    def to_status_dict(self) -> dict[str, object]:
        configured = self.payload.status == CHECK_PASS
        workspace_bundle_healthy = STATUS_NO
        if self.workspace_bundle.reason_code == REASON_WORKSPACE_NOT_REQUESTED:
            workspace_bundle_healthy = STATUS_NOT_REQUESTED
        elif self.workspace_bundle.status == CHECK_PASS:
            workspace_bundle_healthy = STATUS_YES
        return {
            **self.capability.to_dict(),
            "state": {
                "installed": STATUS_YES if self.host_prompt.status == CHECK_PASS else STATUS_NO,
                "configured": STATUS_YES if configured else STATUS_NO,
                "workspace_bundle_healthy": workspace_bundle_healthy,
            },
        }

    def doctor_checks(self) -> tuple[InspectionCheck, ...]:
        return (
            self.host_prompt,
            self.payload,
            self.workspace_bundle,
            self.handoff_first,
            self.preferences_preload,
            self.smoke,
        )


def inspect_all_hosts(
    *,
    home_root: Path,
    workspace_root: Path | None,
    include_smoke: bool,
) -> tuple[HostInspection, ...]:
    """Collect shared inspection facts for every declared host."""
    inspections = []
    for registration in iter_host_registrations():
        inspections.append(
            inspect_host(
                registration=registration,
                home_root=home_root,
                workspace_root=workspace_root,
                include_smoke=include_smoke,
            )
        )
    return tuple(inspections)


def inspect_host(
    *,
    registration: HostRegistration,
    home_root: Path,
    workspace_root: Path | None,
    include_smoke: bool,
) -> HostInspection:
    """Inspect one registered host."""
    adapter = registration.adapter
    capability = registration.capability
    if _host_is_absent(adapter=adapter, home_root=home_root):
        skipped = InspectionCheck(
            host_id=capability.host_id,
            check_id="host_prompt_present",
            status=CHECK_SKIP,
            reason_code=REASON_OK,
            recommendation=f"Install Sopify for {capability.host_id} to enable host-local diagnostics.",
        )
        return HostInspection(
            registration=registration,
            host_prompt=skipped,
            payload=InspectionCheck(
                host_id=capability.host_id,
                check_id="payload_present",
                status=CHECK_SKIP,
                reason_code=REASON_OK,
                recommendation=f"Install Sopify for {capability.host_id} to provision the global payload.",
            ),
            workspace_bundle=InspectionCheck(
                host_id=capability.host_id,
                check_id="workspace_bundle_manifest",
                status=CHECK_SKIP,
                reason_code=REASON_OK,
                recommendation=f"Install Sopify for {capability.host_id} before checking workspace bundle health.",
            ),
            handoff_first=InspectionCheck(
                host_id=capability.host_id,
                check_id="workspace_handoff_first",
                status=CHECK_SKIP,
                reason_code=REASON_OK,
            ),
            preferences_preload=InspectionCheck(
                host_id=capability.host_id,
                check_id="workspace_preferences_preload",
                status=CHECK_SKIP,
                reason_code=REASON_OK,
            ),
            smoke=InspectionCheck(
                host_id=capability.host_id,
                check_id="bundle_smoke",
                status=CHECK_SKIP,
                reason_code=REASON_OK,
            ),
        )
    host_prompt = _inspect_host_prompt(adapter=adapter, capability=capability, home_root=home_root)
    payload = _inspect_payload(adapter=adapter, capability=capability, home_root=home_root)
    if workspace_root is None:
        workspace_bundle = InspectionCheck(
            host_id=capability.host_id,
            check_id="workspace_bundle_manifest",
            status=CHECK_SKIP,
            reason_code=REASON_WORKSPACE_NOT_REQUESTED,
            recommendation="Workspace bootstrap was not requested. Trigger Sopify in a project workspace to bootstrap on demand, or reinstall with `--workspace <path>`.",
        )
        handoff_first = InspectionCheck(
            host_id=capability.host_id,
            check_id="workspace_handoff_first",
            status=CHECK_SKIP,
            reason_code=REASON_WORKSPACE_NOT_REQUESTED,
            recommendation="Trigger Sopify in a project workspace to bootstrap on demand, or reinstall with `--workspace <path>`.",
        )
        preferences_preload = InspectionCheck(
            host_id=capability.host_id,
            check_id="workspace_preferences_preload",
            status=CHECK_SKIP,
            reason_code=REASON_WORKSPACE_NOT_REQUESTED,
            recommendation="Trigger Sopify in a project workspace to bootstrap on demand, or reinstall with `--workspace <path>`.",
        )
        smoke = _inspect_smoke(
            adapter=adapter,
            capability=capability,
            home_root=home_root,
            include_smoke=include_smoke,
        )
        return HostInspection(
            registration=registration,
            host_prompt=host_prompt,
            payload=payload,
            workspace_bundle=workspace_bundle,
            handoff_first=handoff_first,
            preferences_preload=preferences_preload,
            smoke=smoke,
        )
    bundle_manifest = _read_json(workspace_root / ".sopify-runtime" / "manifest.json")
    workspace_bundle = _inspect_workspace_bundle(
        adapter=adapter,
        capability=capability,
        home_root=home_root,
        workspace_root=workspace_root,
    )
    handoff_first = _inspect_workspace_capability(
        capability=capability,
        workspace_bundle=workspace_bundle,
        bundle_manifest=bundle_manifest,
        check_id="workspace_handoff_first",
        manifest_key="writes_handoff_file",
        recommendation="Refresh the workspace bundle so handoff-first runtime contracts stay available.",
    )
    preferences_preload = _inspect_workspace_capability(
        capability=capability,
        workspace_bundle=workspace_bundle,
        bundle_manifest=bundle_manifest,
        check_id="workspace_preferences_preload",
        manifest_key="preferences_preload",
        recommendation="Refresh the workspace bundle so preferences preload stays available.",
    )
    smoke = _inspect_smoke(
        adapter=adapter,
        capability=capability,
        home_root=home_root,
        include_smoke=include_smoke,
    )
    return HostInspection(
        registration=registration,
        host_prompt=host_prompt,
        payload=payload,
        workspace_bundle=workspace_bundle,
        handoff_first=handoff_first,
        preferences_preload=preferences_preload,
        smoke=smoke,
    )


def inspect_workspace_state(workspace_root: Path | None) -> dict[str, object]:
    """Return a lightweight, static view of current workspace runtime state."""
    if workspace_root is None:
        return {
            "requested": False,
            "root": None,
            "bootstrap_mode": "on_first_project_trigger",
            "sopify_skills_present": None,
            "active_plan": None,
            "current_run_stage": None,
            "pending_checkpoint": None,
            "quarantine_count": 0,
            "quarantined_items": [],
            "state_conflicts": [],
            "runtime_notes": [],
        }
    runtime_state = _inspect_runtime_workspace_state(workspace_root)
    return {
        "requested": True,
        "root": str(workspace_root),
        "bootstrap_mode": "prewarmed",
        "sopify_skills_present": (workspace_root / ".sopify-skills").is_dir(),
        "active_plan": runtime_state["active_plan"],
        "current_run_stage": runtime_state["current_run_stage"],
        "pending_checkpoint": runtime_state["pending_checkpoint"],
        "quarantine_count": runtime_state["quarantine_count"],
        "quarantined_items": runtime_state["quarantined_items"],
        "state_conflicts": runtime_state["state_conflicts"],
        "runtime_notes": runtime_state["runtime_notes"],
    }


def build_status_payload(*, home_root: Path, workspace_root: Path | None) -> dict[str, object]:
    """Build the machine contract for `sopify status`."""
    inspections = inspect_all_hosts(home_root=home_root, workspace_root=workspace_root, include_smoke=False)
    hosts = [inspection.to_status_dict() for inspection in inspections]
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "hosts": hosts,
        "state": _build_status_summary(hosts),
        "workspace_state": inspect_workspace_state(workspace_root),
    }


def build_doctor_payload(*, home_root: Path, workspace_root: Path | None) -> dict[str, object]:
    """Build the machine contract for `sopify doctor`."""
    inspections = inspect_all_hosts(home_root=home_root, workspace_root=workspace_root, include_smoke=True)
    checks = [check.to_dict() for inspection in inspections for check in inspection.doctor_checks()]
    workspace_state = inspect_workspace_state(workspace_root)
    checks.extend(check.to_dict() for check in _runtime_workspace_checks(workspace_state))
    return {
        "schema_version": DOCTOR_SCHEMA_VERSION,
        "checks": checks,
        "summary": _build_doctor_summary(checks),
    }


def render_status_text(payload: dict[str, object]) -> str:
    """Render a concise text summary for `sopify status`."""
    lines = [
        "Sopify status:",
        f"  overall: {payload['state']['overall_status']}",
        "Hosts:",
    ]
    for host in payload["hosts"]:
        state = host["state"]
        lines.append(
            "  - {host_id}: tier={support_tier}, installed={installed}, configured={configured}, workspace_bundle_healthy={workspace_bundle_healthy}".format(
                host_id=host["host_id"],
                support_tier=host["support_tier"],
                installed=state["installed"],
                configured=state["configured"],
                workspace_bundle_healthy=state["workspace_bundle_healthy"],
            )
        )
    workspace_state = payload["workspace_state"]
    lines.append("Workspace:")
    if not workspace_state["requested"]:
        lines.extend(
            [
                "  requested: no",
                "  bootstrap_mode: on_first_project_trigger",
                "  state: will bootstrap on first project trigger",
            ]
        )
    else:
        lines.extend(
            [
                "  requested: yes",
                f"  root: {workspace_state['root']}",
                f"  sopify_skills_present: {workspace_state['sopify_skills_present']}",
                f"  active_plan: {workspace_state['active_plan'] or '(none)'}",
                f"  current_run_stage: {workspace_state['current_run_stage'] or '(none)'}",
                f"  pending_checkpoint: {workspace_state['pending_checkpoint'] or '(none)'}",
            ]
        )
        if workspace_state["quarantine_count"]:
            lines.append(f"  quarantine_count: {workspace_state['quarantine_count']}")
            for item in workspace_state["quarantined_items"][:3]:
                lines.append(
                    "  quarantined: {state_kind} {path} ({reason})".format(
                        state_kind=item.get("state_kind") or "unknown",
                        path=item.get("path") or "(unknown)",
                        reason=item.get("reason") or "unknown",
                    )
                )
        if workspace_state["state_conflicts"]:
            lines.append(f"  state_conflict_count: {len(workspace_state['state_conflicts'])}")
            first_conflict = workspace_state["state_conflicts"][0]
            lines.append(
                "  state_conflict: {code} @ {path}".format(
                    code=first_conflict.get("code") or "unknown",
                    path=first_conflict.get("path") or "(unknown)",
                )
            )
            explanation = str(first_conflict.get("explanation") or "").strip()
            if explanation:
                lines.append(f"  state_conflict_explanation: {explanation}")
    return "\n".join(lines)


def render_doctor_text(payload: dict[str, object]) -> str:
    """Render a concise text summary for `sopify doctor`."""
    lines = [
        "Sopify doctor:",
        f"  overall_status: {payload['summary']['overall_status']}",
        f"  pass: {payload['summary']['pass_count']}",
        f"  warn: {payload['summary']['warn_count']}",
        f"  fail: {payload['summary']['fail_count']}",
        f"  skip: {payload['summary']['skip_count']}",
        "Checks:",
    ]
    for check in payload["checks"]:
        prefix = f"{check.get('host_id')}:" if check.get("host_id") else ""
        line = f"  - {prefix}{check['check_id']} -> {check['status']} ({check['reason_code']})"
        if check.get("recommendation"):
            line += f" | {check['recommendation']}"
        lines.append(line)
    return "\n".join(lines)


def _inspect_runtime_workspace_state(workspace_root: Path) -> dict[str, object]:
    fallback_state_root = workspace_root / ".sopify-skills" / "state"
    fallback_run = _read_json(fallback_state_root / "current_run.json")
    fallback_handoff = _read_json(fallback_state_root / "current_handoff.json")
    fallback_payload = {
        "active_plan": str(fallback_run.get("plan_path") or fallback_run.get("plan_id") or "") or None,
        "current_run_stage": fallback_run.get("stage"),
        "pending_checkpoint": fallback_handoff.get("required_host_action"),
        "quarantine_count": 0,
        "quarantined_items": [],
        "state_conflicts": [],
        "runtime_notes": [],
    }
    try:
        config = load_runtime_config(workspace_root)
    except (ConfigError, ValueError) as exc:
        fallback_payload["runtime_notes"] = [f"Runtime inspection unavailable: {exc}"]
        return fallback_payload

    global_store = StateStore(config)
    snapshots = [
        resolve_context_snapshot(
            config=config,
            review_store=global_store,
            global_store=global_store,
        )
    ]
    sessions_root = config.state_dir / SESSIONS_DIRNAME
    if sessions_root.is_dir():
        for session_dir in sorted(sessions_root.iterdir(), key=lambda item: item.name):
            if not session_dir.is_dir():
                continue
            try:
                session_store = StateStore(config, session_id=session_dir.name)
            except ValueError:
                continue
            snapshots.append(
                resolve_context_snapshot(
                    config=config,
                    review_store=session_store,
                    global_store=global_store,
                )
            )

    primary_snapshot = snapshots[0]
    quarantined_items: dict[tuple[str, str, str, str, str], dict[str, object]] = {}
    state_conflicts: dict[tuple[str, str, str, str], dict[str, object]] = {}
    runtime_notes: list[str] = []
    for snapshot in snapshots:
        for item in snapshot.quarantined_items:
            key = (item.state_kind, item.path, item.reason, item.provenance_status, item.state_scope)
            quarantined_items.setdefault(key, item.to_dict())
        for item in snapshot.conflict_items:
            key = (item.code, item.message, item.path, item.state_scope)
            payload = item.to_dict()
            payload["explanation"] = _describe_state_conflict(item.code)
            state_conflicts.setdefault(key, payload)
        for note in snapshot.notes:
            if note not in runtime_notes:
                runtime_notes.append(note)

    current_run = primary_snapshot.current_run
    current_plan = primary_snapshot.current_plan
    current_handoff = primary_snapshot.current_handoff
    active_plan = None
    if current_run is not None:
        active_plan = str(current_run.plan_path or current_run.plan_id or "") or None
    elif current_plan is not None:
        active_plan = str(current_plan.path or current_plan.plan_id or "") or None

    return {
        "active_plan": active_plan,
        "current_run_stage": current_run.stage if current_run is not None else None,
        "pending_checkpoint": current_handoff.required_host_action if current_handoff is not None else None,
        "quarantine_count": len(quarantined_items),
        "quarantined_items": list(quarantined_items.values()),
        "state_conflicts": list(state_conflicts.values()),
        "runtime_notes": runtime_notes,
    }


def _runtime_workspace_checks(workspace_state: dict[str, object]) -> tuple[InspectionCheck, ...]:
    checks: list[InspectionCheck] = []
    quarantined_items = workspace_state.get("quarantined_items") or []
    if isinstance(quarantined_items, list) and quarantined_items:
        checks.append(
            InspectionCheck(
                check_id="workspace_runtime_quarantine",
                status=CHECK_WARN,
                reason_code=REASON_QUARANTINED_RUNTIME_STATE,
                evidence=tuple(
                    "{path} ({reason})".format(
                        path=item.get("path") or "(unknown)",
                        reason=item.get("reason") or "unknown",
                    )
                    for item in quarantined_items[:5]
                    if isinstance(item, dict)
                ),
                recommendation="Review the quarantined runtime files via status/doctor before resuming planning or execution.",
            )
        )
    state_conflicts = workspace_state.get("state_conflicts") or []
    if isinstance(state_conflicts, list) and state_conflicts:
        checks.append(
            InspectionCheck(
                check_id="workspace_runtime_state_conflict",
                status=CHECK_FAIL,
                reason_code=REASON_RUNTIME_STATE_CONFLICT,
                evidence=tuple(
                    "{code} @ {path}: {explanation}".format(
                        code=item.get("code") or "unknown",
                        path=item.get("path") or "(unknown)",
                        explanation=item.get("explanation") or _describe_state_conflict(str(item.get("code") or "")),
                    )
                    for item in state_conflicts[:5]
                    if isinstance(item, dict)
                ),
                recommendation="Clear the conflicting negotiation state before resuming runtime execution.",
            )
        )
    runtime_notes = workspace_state.get("runtime_notes") or []
    if not checks and isinstance(runtime_notes, list):
        unavailable_notes = [note for note in runtime_notes if isinstance(note, str) and note.startswith("Runtime inspection unavailable:")]
        if unavailable_notes:
            checks.append(
                InspectionCheck(
                    check_id="workspace_runtime_inspection",
                    status=CHECK_WARN,
                    reason_code=REASON_RUNTIME_INSPECTION_UNAVAILABLE,
                    evidence=tuple(unavailable_notes[:3]),
                    recommendation="Fix the workspace runtime configuration so status/doctor can inspect runtime state health.",
                )
            )
    return tuple(checks)


def _describe_state_conflict(code: str) -> str:
    normalized = str(code or "").strip()
    if not normalized:
        return "A runtime state conflict requires manual cleanup before execution can continue."
    return _STATE_CONFLICT_EXPLANATIONS.get(
        normalized,
        "A runtime state conflict requires manual cleanup before execution can continue.",
    )


def _inspect_host_prompt(*, adapter: HostAdapter, capability: HostCapability, home_root: Path) -> InspectionCheck:
    try:
        paths = validate_host_install(adapter, home_root=home_root)
        return InspectionCheck(
            host_id=capability.host_id,
            check_id="host_prompt_present",
            status=CHECK_PASS,
            reason_code=REASON_OK,
            evidence=tuple(str(path) for path in paths),
        )
    except InstallError as exc:
        return InspectionCheck(
            host_id=capability.host_id,
            check_id="host_prompt_present",
            status=CHECK_FAIL,
            reason_code=_reason_code_from_install_error(exc),
            evidence=_paths_from_error(exc),
            recommendation=f"Run python3 scripts/install_sopify.py --target {capability.host_id}:zh-CN to install the host prompt layer.",
        )


def _inspect_payload(*, adapter: HostAdapter, capability: HostCapability, home_root: Path) -> InspectionCheck:
    payload_root = adapter.payload_root(home_root)
    try:
        paths = validate_payload_install(payload_root)
        return InspectionCheck(
            host_id=capability.host_id,
            check_id="payload_present",
            status=CHECK_PASS,
            reason_code=REASON_OK,
            evidence=tuple(str(path) for path in paths),
        )
    except InstallError as exc:
        return InspectionCheck(
            host_id=capability.host_id,
            check_id="payload_present",
            status=CHECK_FAIL,
            reason_code=_reason_code_from_install_error(exc),
            evidence=_paths_from_error(exc),
            recommendation=f"Run python3 scripts/install_sopify.py --target {capability.host_id}:zh-CN to refresh the host payload.",
        )


def _inspect_workspace_bundle(
    *,
    adapter: HostAdapter,
    capability: HostCapability,
    home_root: Path,
    workspace_root: Path,
) -> InspectionCheck:
    payload_root = adapter.payload_root(home_root)
    payload_manifest_path = payload_root / "payload-manifest.json"
    bundle_manifest_path = payload_root / "bundle" / "manifest.json"
    payload_manifest = _read_json(payload_manifest_path)
    bundle_manifest = _read_json(bundle_manifest_path)
    bundle_root = workspace_root / ".sopify-runtime"
    current_manifest_path = bundle_root / "manifest.json"
    current_manifest = _read_json(current_manifest_path)

    if not payload_manifest or not bundle_manifest:
        return InspectionCheck(
            host_id=capability.host_id,
            check_id="workspace_bundle_manifest",
            status=CHECK_FAIL,
            reason_code="MISSING_REQUIRED_FILE",
            evidence=tuple(str(path) for path in (payload_manifest_path, bundle_manifest_path) if path.exists()),
            recommendation=f"Install or refresh the {capability.host_id} payload before inspecting workspace bundle health.",
        )

    state, reason_code, message, _from_version = _classify_workspace_bundle(
        current_manifest=current_manifest,
        payload_manifest=payload_manifest,
        bundle_manifest=bundle_manifest,
        current_manifest_path=current_manifest_path,
        bundle_root=bundle_root,
    )
    status = CHECK_FAIL
    if state in STATUS_READY_STATES:
        status = CHECK_PASS
    elif state in STATUS_WARN_STATES:
        status = CHECK_WARN
    evidence = tuple(
        str(path)
        for path in (current_manifest_path, bundle_root)
        if path.exists()
    )
    return InspectionCheck(
        host_id=capability.host_id,
        check_id="workspace_bundle_manifest",
        status=status,
        reason_code=reason_code,
        evidence=evidence,
        recommendation=_workspace_bundle_recommendation(capability.host_id, workspace_root, reason_code, message),
    )


def _inspect_workspace_capability(
    *,
    capability: HostCapability,
    workspace_bundle: InspectionCheck,
    bundle_manifest: dict[str, Any],
    check_id: str,
    manifest_key: str,
    recommendation: str,
) -> InspectionCheck:
    if workspace_bundle.status != CHECK_PASS:
        return InspectionCheck(
            host_id=capability.host_id,
            check_id=check_id,
            status=workspace_bundle.status,
            reason_code=workspace_bundle.reason_code,
            evidence=workspace_bundle.evidence,
            recommendation=recommendation,
        )
    current_capabilities = bundle_manifest.get("capabilities") or {}
    if current_capabilities.get(manifest_key):
        return InspectionCheck(
            host_id=capability.host_id,
            check_id=check_id,
            status=CHECK_PASS,
            reason_code=REASON_OK,
        )
    return InspectionCheck(
        host_id=capability.host_id,
        check_id=check_id,
        status=CHECK_FAIL,
        reason_code="MISSING_REQUIRED_CAPABILITY",
        recommendation=recommendation,
    )


def _inspect_smoke(
    *,
    adapter: HostAdapter,
    capability: HostCapability,
    home_root: Path,
    include_smoke: bool,
) -> InspectionCheck:
    if not include_smoke:
        return InspectionCheck(
            host_id=capability.host_id,
            check_id="bundle_smoke",
            status=CHECK_SKIP,
            reason_code=REASON_OK,
        )

    bundle_root = adapter.payload_root(home_root) / "bundle"
    try:
        stdout = run_bundle_smoke_check(bundle_root)
        evidence = (stdout.splitlines()[0],) if stdout else ()
        return InspectionCheck(
            host_id=capability.host_id,
            check_id="bundle_smoke",
            status=CHECK_PASS,
            reason_code=REASON_OK,
            evidence=evidence,
        )
    except InstallError as exc:
        return InspectionCheck(
            host_id=capability.host_id,
            check_id="bundle_smoke",
            status=CHECK_FAIL,
            reason_code=_reason_code_from_install_error(exc, default="UNEXPECTED_ERROR"),
            evidence=_paths_from_error(exc),
            recommendation=f"Refresh the {capability.host_id} payload bundle and rerun the bundled smoke check.",
        )


def _build_status_summary(hosts: list[dict[str, object]]) -> dict[str, object]:
    installed_hosts = [host["host_id"] for host in hosts if host["state"]["installed"] == STATUS_YES]
    configured_hosts = [host["host_id"] for host in hosts if host["state"]["configured"] == STATUS_YES]
    workspace_bundle_healthy_hosts = [
        host["host_id"] for host in hosts if host["state"]["workspace_bundle_healthy"] == STATUS_YES
    ]
    installable_hosts = [host["host_id"] for host in hosts if host["install_enabled"]]
    overall_status = "missing"
    if workspace_bundle_healthy_hosts:
        overall_status = "ready"
    elif installed_hosts or configured_hosts:
        overall_status = "partial"
    return {
        "overall_status": overall_status,
        "installable_hosts": installable_hosts,
        "installed_hosts": installed_hosts,
        "configured_hosts": configured_hosts,
        "workspace_bundle_healthy_hosts": workspace_bundle_healthy_hosts,
    }


def _build_doctor_summary(checks: list[dict[str, object]]) -> dict[str, object]:
    pass_count = sum(1 for check in checks if check["status"] == CHECK_PASS)
    warn_count = sum(1 for check in checks if check["status"] == CHECK_WARN)
    fail_count = sum(1 for check in checks if check["status"] == CHECK_FAIL)
    skip_count = sum(1 for check in checks if check["status"] == CHECK_SKIP)
    overall_status = CHECK_PASS
    if fail_count:
        overall_status = CHECK_FAIL
    elif warn_count:
        overall_status = CHECK_WARN
    elif skip_count and not pass_count:
        overall_status = CHECK_SKIP
    return {
        "overall_status": overall_status,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "skip_count": skip_count,
    }


def _workspace_bundle_recommendation(host_id: str, workspace_root: Path, reason_code: str, message: str) -> str:
    if reason_code in {"MISSING_BUNDLE", "WORKSPACE_BUNDLE_OUTDATED"}:
        return (
            f"Trigger Sopify inside {workspace_root} or run "
            f"python3 scripts/install_sopify.py --target {host_id}:zh-CN --workspace {workspace_root}"
        )
    return message


def _reason_code_from_install_error(exc: InstallError, *, default: str = "MISSING_REQUIRED_FILE") -> str:
    message = str(exc)
    if "schema" in message.lower():
        return "SCHEMA_VERSION_MISMATCH"
    if "capabilit" in message.lower():
        return "MISSING_REQUIRED_CAPABILITY"
    if "missing" in message.lower() or "verification failed" in message.lower():
        return "MISSING_REQUIRED_FILE"
    return default


def _paths_from_error(exc: InstallError) -> tuple[str, ...]:
    message = str(exc)
    if "[" in message and "]" in message:
        start = message.find("[")
        end = message.rfind("]")
        if start >= 0 and end > start:
            return tuple(part.strip(" []'") for part in message[start + 1 : end].split(",") if part.strip(" []'"))
    if ":" in message:
        candidate = message.rsplit(":", 1)[-1].strip()
        if candidate.startswith("/"):
            return (candidate,)
    return ()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _host_is_absent(*, adapter: HostAdapter, home_root: Path) -> bool:
    return not adapter.destination_root(home_root).exists() and not adapter.payload_root(home_root).exists()
