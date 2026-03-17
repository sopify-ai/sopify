"""Filesystem-backed state storage for Sopify runtime."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Optional

from .handoff import read_runtime_handoff, write_runtime_handoff
from .models import DecisionState, PlanArtifact, RouteDecision, RunState, RuntimeConfig, RuntimeHandoff


class StateStore:
    """Read and write runtime state files under `.sopify-skills/state/`."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.root = config.state_dir
        self.current_run_path = self.root / "current_run.json"
        self.last_route_path = self.root / "last_route.json"
        self.current_plan_path = self.root / "current_plan.json"
        self.current_handoff_path = self.root / "current_handoff.json"
        self.current_decision_path = self.root / "current_decision.json"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def get_current_run(self) -> Optional[RunState]:
        payload = self._read_json(self.current_run_path)
        return RunState.from_dict(payload) if payload else None

    def set_current_run(self, run_state: RunState) -> None:
        self.ensure()
        self._write_json(self.current_run_path, run_state.to_dict())

    def clear_current_run(self) -> None:
        self.current_run_path.unlink(missing_ok=True)

    def get_last_route(self) -> Optional[RouteDecision]:
        payload = self._read_json(self.last_route_path)
        return RouteDecision.from_dict(payload) if payload else None

    def set_last_route(self, decision: RouteDecision) -> None:
        self.ensure()
        payload = decision.to_dict()
        payload["updated_at"] = iso_now()
        self._write_json(self.last_route_path, payload)

    def get_current_plan(self) -> Optional[PlanArtifact]:
        payload = self._read_json(self.current_plan_path)
        return PlanArtifact.from_dict(payload) if payload else None

    def set_current_plan(self, artifact: PlanArtifact) -> None:
        self.ensure()
        self._write_json(self.current_plan_path, artifact.to_dict())

    def clear_current_plan(self) -> None:
        self.current_plan_path.unlink(missing_ok=True)

    def get_current_decision(self) -> Optional[DecisionState]:
        payload = self._read_json(self.current_decision_path)
        return DecisionState.from_dict(payload) if payload else None

    def set_current_decision(self, decision_state: DecisionState) -> None:
        self.ensure()
        self._write_json(self.current_decision_path, decision_state.to_dict())

    def clear_current_decision(self) -> None:
        self.current_decision_path.unlink(missing_ok=True)

    def get_current_handoff(self) -> Optional[RuntimeHandoff]:
        return read_runtime_handoff(self.current_handoff_path)

    def set_current_handoff(self, handoff: RuntimeHandoff) -> None:
        self.ensure()
        write_runtime_handoff(self.current_handoff_path, handoff)

    def clear_current_handoff(self) -> None:
        self.current_handoff_path.unlink(missing_ok=True)

    def has_active_flow(self) -> bool:
        current_run = self.get_current_run()
        return current_run is not None and current_run.is_active

    def reset_active_flow(self) -> None:
        self.clear_current_run()
        self.clear_current_plan()
        self.clear_current_handoff()
        self.clear_current_decision()

    def update_active_run(self, *, stage: Optional[str] = None, status: Optional[str] = None) -> Optional[RunState]:
        current = self.get_current_run()
        if current is None:
            return None
        updated = RunState(
            run_id=current.run_id,
            status=status or current.status,
            stage=stage or current.stage,
            route_name=current.route_name,
            title=current.title,
            created_at=current.created_at,
            updated_at=iso_now(),
            plan_id=current.plan_id,
            plan_path=current.plan_path,
        )
        self.set_current_run(updated)
        return updated

    def _read_json(self, path: Path) -> Optional[dict[str, Any]]:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(path)


def iso_now() -> str:
    """Return a stable UTC ISO timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
