"""Shared knowledge-sync contract helpers for runtime-managed plans."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .knowledge_layout import resolve_path
from .models import RuntimeConfig

KNOWLEDGE_SYNC_KEYS = ("project", "background", "design", "tasks")
KNOWLEDGE_SYNC_MODES = {"skip", "review", "required"}


def default_knowledge_sync(level: str) -> dict[str, str]:
    if level == "light":
        return {
            "project": "skip",
            "background": "skip",
            "design": "review",
            "tasks": "skip",
        }
    if level == "full":
        return {
            "project": "review",
            "background": "required",
            "design": "required",
            "tasks": "review",
        }
    return {
        "project": "review",
        "background": "review",
        "design": "review",
        "tasks": "review",
    }


def render_knowledge_sync_front_matter(level: str) -> list[str]:
    contract = default_knowledge_sync(level)
    return [
        "knowledge_sync:",
        *(f"  {key}: {contract[key]}" for key in KNOWLEDGE_SYNC_KEYS),
    ]


def parse_knowledge_sync(payload: Any) -> dict[str, str] | None:
    if not isinstance(payload, Mapping):
        return None

    normalized: dict[str, str] = {}
    for key in KNOWLEDGE_SYNC_KEYS:
        value = str(payload.get(key) or "").strip()
        if value not in KNOWLEDGE_SYNC_MODES:
            return None
        normalized[key] = value

    return normalized


def knowledge_sync_targets(*, config: RuntimeConfig) -> dict[str, Path]:
    return {
        "project": resolve_path(config=config, key="project"),
        "background": resolve_path(config=config, key="blueprint_background"),
        "design": resolve_path(config=config, key="blueprint_design"),
        "tasks": resolve_path(config=config, key="blueprint_tasks"),
    }
