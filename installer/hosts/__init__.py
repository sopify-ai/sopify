"""Host adapters for Sopify installer."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from installer.models import HostCapability

from .base import HostAdapter, HostRegistration
from .claude import CLAUDE_ADAPTER, CLAUDE_HOST
from .codex import CODEX_ADAPTER, CODEX_HOST
from .trae_cn import TRAE_CN_ADAPTER, TRAE_CN_HOST

_REGISTRATIONS = {
    CODEX_HOST.capability.host_id: CODEX_HOST,
    CLAUDE_HOST.capability.host_id: CLAUDE_HOST,
    TRAE_CN_HOST.capability.host_id: TRAE_CN_HOST,
}


def get_host_adapter(host_name: str) -> HostAdapter:
    """Return the registered host adapter."""
    try:
        return _REGISTRATIONS[host_name].adapter
    except KeyError as exc:
        raise ValueError(f"Unsupported host adapter: {host_name}") from exc


def get_host_capability(host_id: str) -> HostCapability:
    """Return the product capability declaration for one host."""
    try:
        return _REGISTRATIONS[host_id].capability
    except KeyError as exc:
        raise ValueError(f"Unsupported host capability: {host_id}") from exc


def iter_installable_hosts() -> Iterator[HostCapability]:
    """Yield registry entries that are allowed into the installer mainline."""
    for registration in _REGISTRATIONS.values():
        if registration.capability.install_enabled:
            yield registration.capability


def iter_declared_hosts() -> Iterator[HostCapability]:
    """Yield every declared host capability entry."""
    for registration in _REGISTRATIONS.values():
        yield registration.capability


def iter_host_registrations() -> Iterator[HostRegistration]:
    """Yield every full host registration entry."""
    for registration in _REGISTRATIONS.values():
        yield registration


def resolve_host_payload_root(*, home_root: Path, host_id: str) -> Path:
    """Resolve the registered payload root for one host."""
    return get_host_adapter(host_id).payload_root(home_root)


def iter_host_payload_manifest_candidates(*, home_root: Path) -> Iterator[tuple[str, Path]]:
    """Yield registered payload manifest candidates rooted under one home directory."""
    for registration in _REGISTRATIONS.values():
        yield (
            registration.capability.host_id,
            registration.adapter.payload_root(home_root) / "payload-manifest.json",
        )
