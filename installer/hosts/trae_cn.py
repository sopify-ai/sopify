"""Trae CN host adapter."""

from __future__ import annotations

from installer.models import EntryMode, FeatureId, HostCapability, SupportTier

from .base import HostAdapter, HostRegistration

TRAE_CN_ADAPTER = HostAdapter(
    host_name="trae-cn",
    source_dirname="TraeCn",
    destination_dirname=".trae-cn",
    header_filename="user_rules/sopify.md",
)

TRAE_CN_CAPABILITY = HostCapability(
    host_id="trae-cn",
    support_tier=SupportTier.EXPERIMENTAL,
    install_enabled=True,
    declared_features=(
        FeatureId.PROMPT_INSTALL,
        FeatureId.PAYLOAD_INSTALL,
        FeatureId.WORKSPACE_BOOTSTRAP,
        FeatureId.RUNTIME_GATE,
        FeatureId.PREFERENCES_PRELOAD,
        FeatureId.HANDOFF_FIRST,
    ),
    verified_features=(
        FeatureId.PROMPT_INSTALL,
        FeatureId.PAYLOAD_INSTALL,
    ),
    entry_modes=(EntryMode.PROMPT_ONLY,),
    doctor_checks=(
        "host_prompt_present",
        "payload_present",
        "workspace_bundle_manifest",
        "workspace_ingress_proof",
        "workspace_handoff_first",
        "workspace_preferences_preload",
        "bundle_smoke",
    ),
    smoke_targets=("bundle_runtime_smoke",),
)

TRAE_CN_HOST = HostRegistration(adapter=TRAE_CN_ADAPTER, capability=TRAE_CN_CAPABILITY)
