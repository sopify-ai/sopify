"""Selective context recovery for active runtime flows."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .models import RecoveredContext, RouteDecision, RuntimeConfig
from .state import StateStore

_SUMMARY_CANDIDATES = ("README.md", "plan.md", "tasks.md")


def recover_context(
    decision: RouteDecision,
    *,
    config: RuntimeConfig,
    state_store: StateStore,
) -> RecoveredContext:
    """Recover the minimum context needed for the current route.

    Args:
        decision: Current route decision.
        config: Runtime configuration.
        state_store: State accessor.

    Returns:
        Recovered context, limited to active state files and one plan summary.
    """
    current_run = state_store.get_current_run()
    current_plan = state_store.get_current_plan()
    current_decision = state_store.get_current_decision()
    last_route = state_store.get_last_route()

    if not decision.should_recover_context:
        return RecoveredContext(
            current_run=current_run,
            current_plan=current_plan,
            current_decision=current_decision,
            last_route=last_route,
        )

    loaded_files: List[str] = []
    documents: Dict[str, str] = {}

    if current_plan is not None:
        plan_root = config.workspace_root / current_plan.path
        summary_file = _pick_summary_file(plan_root)
        if summary_file is not None:
            documents[str(summary_file.relative_to(config.workspace_root))] = summary_file.read_text(encoding="utf-8")
            loaded_files.append(str(summary_file.relative_to(config.workspace_root)))

    return RecoveredContext(
        loaded_files=tuple(loaded_files),
        current_run=current_run,
        current_plan=current_plan,
        current_decision=current_decision,
        last_route=last_route,
        documents=documents,
    )


def _pick_summary_file(plan_root: Path) -> Path | None:
    if not plan_root.exists():
        return None
    for name in _SUMMARY_CANDIDATES:
        candidate = plan_root / name
        if candidate.exists() and candidate.is_file():
            return candidate
    return None
