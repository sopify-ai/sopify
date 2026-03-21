"""Stage-aware knowledge layout resolver for Sopify KB V2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import PlanArtifact, RuntimeConfig

KB_LAYOUT_VERSION = "2"
_RUNTIME_RELATIVE_PATHS = {
    "project": Path("project.md"),
    "blueprint_index": Path("blueprint/README.md"),
    "blueprint_background": Path("blueprint/background.md"),
    "blueprint_design": Path("blueprint/design.md"),
    "blueprint_tasks": Path("blueprint/tasks.md"),
    "plan_root": Path("plan"),
    "history_root": Path("history"),
}
KNOWLEDGE_PATHS = {
    key: f".sopify-skills/{relative_path.as_posix()}"
    for key, relative_path in _RUNTIME_RELATIVE_PATHS.items()
}
CONTEXT_PROFILES = {
    "consult": ("project", "blueprint_index"),
    "plan": ("project", "blueprint_index", "blueprint_background", "blueprint_design"),
    "clarification": ("project", "blueprint_index", "blueprint_tasks"),
    "decision": ("project", "blueprint_design", "active_plan"),
    "develop": ("active_plan", "project", "blueprint_design"),
    "finalize": (
        "active_plan",
        "project",
        "blueprint_index",
        "blueprint_background",
        "blueprint_design",
        "blueprint_tasks",
    ),
    "history_lookup": ("history_root",),
}


@dataclass(frozen=True)
class KnowledgeSelection:
    """Resolved context files for a profile at the current materialization stage."""

    profile: str
    materialization_stage: str
    files: tuple[str, ...]


def resolve_path(*, config: RuntimeConfig, key: str) -> Path:
    """Resolve a V2 knowledge key to a workspace path."""
    relative_path = _RUNTIME_RELATIVE_PATHS.get(key)
    if relative_path is None:
        raise ValueError(f"Unsupported knowledge path key: {key}")
    return config.runtime_root / relative_path


def materialization_stage(*, config: RuntimeConfig, current_plan: PlanArtifact | None = None) -> str:
    """Return the current KB disclosure/materialization stage."""
    effective_current_plan = _effective_current_plan(config=config, current_plan=current_plan)
    deep_blueprint_ready = all(
        resolve_path(config=config, key=key).exists()
        for key in ("blueprint_background", "blueprint_design", "blueprint_tasks")
    )
    history_ready = (resolve_path(config=config, key="history_root") / "index.md").exists()
    active_plan_ready = _has_active_plan(config=config, current_plan=effective_current_plan)

    if history_ready:
        return "L3 history-ready"
    if active_plan_ready:
        return "L2 plan-active"
    if deep_blueprint_ready:
        return "L1 blueprint-ready"
    return "L0 bootstrap"


def resolve_context_profile(
    *,
    config: RuntimeConfig,
    profile: str,
    current_plan: PlanArtifact | None = None,
) -> KnowledgeSelection:
    """Resolve the current file set for a V2 context profile.

    Missing deep blueprint files are ignored so early lifecycle routes may
    continue under `L0 bootstrap` without additional guards.
    """
    entries = CONTEXT_PROFILES.get(profile)
    if entries is None:
        raise ValueError(f"Unsupported context profile: {profile}")

    effective_current_plan = _effective_current_plan(config=config, current_plan=current_plan)
    files: list[str] = []
    for entry in entries:
        if entry == "active_plan":
            files.extend(_active_plan_files(config=config, current_plan=effective_current_plan))
            continue
        path = resolve_path(config=config, key=entry)
        if path.exists():
            files.append(str(path.relative_to(config.workspace_root)))

    return KnowledgeSelection(
        profile=profile,
        materialization_stage=materialization_stage(config=config, current_plan=effective_current_plan),
        files=tuple(dict.fromkeys(files)),
    )


def _has_active_plan(*, config: RuntimeConfig, current_plan: PlanArtifact | None) -> bool:
    if current_plan is None:
        return False
    plan_dir = config.workspace_root / current_plan.path
    return plan_dir.exists() and plan_dir.is_dir()


def _effective_current_plan(*, config: RuntimeConfig, current_plan: PlanArtifact | None) -> PlanArtifact | None:
    if current_plan is not None:
        return current_plan
    from .state import StateStore

    return StateStore(config).get_current_plan()


def _active_plan_files(*, config: RuntimeConfig, current_plan: PlanArtifact | None) -> list[str]:
    if current_plan is None:
        return []

    plan_dir = config.workspace_root / current_plan.path
    if not plan_dir.exists() or not plan_dir.is_dir():
        return []

    files = [current_plan.path]
    files.extend(current_plan.files)
    return list(dict.fromkeys(files))
