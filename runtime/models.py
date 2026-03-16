"""Shared runtime contracts for Sopify."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class RuntimeConfig:
    """Normalized runtime configuration."""

    workspace_root: Path
    project_config_path: Optional[Path]
    global_config_path: Optional[Path]
    brand: str
    language: str
    output_style: str
    title_color: str
    workflow_mode: str
    require_score: int
    auto_decide: bool
    workflow_learning_auto_capture: str
    plan_level: str
    plan_directory: str
    multi_model_enabled: bool
    multi_model_trigger: str
    multi_model_timeout_sec: int
    multi_model_max_parallel: int
    multi_model_include_default_model: bool
    ehrb_level: str
    kb_init: str
    cache_project: bool

    @property
    def runtime_root(self) -> Path:
        return self.workspace_root / self.plan_directory

    @property
    def state_dir(self) -> Path:
        return self.runtime_root / "state"

    @property
    def plan_root(self) -> Path:
        return self.runtime_root / "plan"

    @property
    def replay_root(self) -> Path:
        return self.runtime_root / "replay" / "sessions"


@dataclass(frozen=True)
class SkillMeta:
    """Minimal metadata discovered from a skill directory."""

    skill_id: str
    name: str
    description: str
    path: Path
    source: str
    mode: str = "advisory"
    runtime_entry: Optional[Path] = None
    triggers: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "path": str(self.path),
            "source": self.source,
            "mode": self.mode,
            "runtime_entry": str(self.runtime_entry) if self.runtime_entry else None,
            "triggers": list(self.triggers),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RouteDecision:
    """Deterministic route classification result."""

    route_name: str
    request_text: str
    reason: str
    command: Optional[str] = None
    complexity: str = "simple"
    plan_level: Optional[str] = None
    candidate_skill_ids: tuple[str, ...] = ()
    should_recover_context: bool = False
    should_create_plan: bool = False
    capture_mode: str = "off"
    runtime_skill_id: Optional[str] = None
    active_run_action: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_name": self.route_name,
            "request_text": self.request_text,
            "reason": self.reason,
            "command": self.command,
            "complexity": self.complexity,
            "plan_level": self.plan_level,
            "candidate_skill_ids": list(self.candidate_skill_ids),
            "should_recover_context": self.should_recover_context,
            "should_create_plan": self.should_create_plan,
            "capture_mode": self.capture_mode,
            "runtime_skill_id": self.runtime_skill_id,
            "active_run_action": self.active_run_action,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RouteDecision":
        return cls(
            route_name=str(data.get("route_name") or "consult"),
            request_text=str(data.get("request_text") or ""),
            reason=str(data.get("reason") or ""),
            command=data.get("command") or None,
            complexity=str(data.get("complexity") or "simple"),
            plan_level=data.get("plan_level") or None,
            candidate_skill_ids=tuple(data.get("candidate_skill_ids") or ()),
            should_recover_context=bool(data.get("should_recover_context", False)),
            should_create_plan=bool(data.get("should_create_plan", False)),
            capture_mode=str(data.get("capture_mode") or "off"),
            runtime_skill_id=data.get("runtime_skill_id") or None,
            active_run_action=data.get("active_run_action") or None,
        )


@dataclass(frozen=True)
class RunState:
    """Persistent state for the active runtime flow."""

    run_id: str
    status: str
    stage: str
    route_name: str
    title: str
    created_at: str
    updated_at: str
    plan_id: Optional[str] = None
    plan_path: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "stage": self.stage,
            "route_name": self.route_name,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "plan_id": self.plan_id,
            "plan_path": self.plan_path,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunState":
        return cls(
            run_id=str(data.get("run_id") or ""),
            status=str(data.get("status") or "inactive"),
            stage=str(data.get("stage") or "idle"),
            route_name=str(data.get("route_name") or "consult"),
            title=str(data.get("title") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            plan_id=data.get("plan_id") or None,
            plan_path=data.get("plan_path") or None,
        )


@dataclass(frozen=True)
class PlanArtifact:
    """Generated plan package metadata."""

    plan_id: str
    title: str
    summary: str
    level: str
    path: str
    files: tuple[str, ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "title": self.title,
            "summary": self.summary,
            "level": self.level,
            "path": self.path,
            "files": list(self.files),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanArtifact":
        return cls(
            plan_id=str(data.get("plan_id") or ""),
            title=str(data.get("title") or ""),
            summary=str(data.get("summary") or ""),
            level=str(data.get("level") or "light"),
            path=str(data.get("path") or ""),
            files=tuple(data.get("files") or ()),
            created_at=str(data.get("created_at") or ""),
        )


@dataclass(frozen=True)
class KbArtifact:
    """Minimal knowledge-base files created by the runtime."""

    mode: str
    files: tuple[str, ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "files": list(self.files),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RecoveredContext:
    """Minimal context recovered from filesystem state."""

    loaded_files: tuple[str, ...] = ()
    current_run: Optional[RunState] = None
    current_plan: Optional[PlanArtifact] = None
    last_route: Optional[RouteDecision] = None
    documents: Mapping[str, str] = field(default_factory=dict)

    @property
    def has_active_run(self) -> bool:
        return self.current_run is not None and self.current_run.is_active

    def to_dict(self) -> dict[str, Any]:
        return {
            "loaded_files": list(self.loaded_files),
            "current_run": self.current_run.to_dict() if self.current_run else None,
            "current_plan": self.current_plan.to_dict() if self.current_plan else None,
            "last_route": self.last_route.to_dict() if self.last_route else None,
            "documents": dict(self.documents),
        }


@dataclass(frozen=True)
class ReplayEvent:
    """Append-only replay event payload."""

    ts: str
    phase: str
    intent: str
    action: str
    key_output: str
    decision_reason: str
    result: str
    risk: str = ""
    alternatives: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "phase": self.phase,
            "intent": self.intent,
            "action": self.action,
            "key_output": self.key_output,
            "decision_reason": self.decision_reason,
            "result": self.result,
            "risk": self.risk,
            "alternatives": list(self.alternatives),
            "artifacts": list(self.artifacts),
        }


@dataclass(frozen=True)
class RuntimeResult:
    """Top-level runtime result returned by the engine."""

    route: RouteDecision
    recovered_context: RecoveredContext
    discovered_skills: tuple[SkillMeta, ...] = ()
    kb_artifact: Optional[KbArtifact] = None
    plan_artifact: Optional[PlanArtifact] = None
    skill_result: Optional[Mapping[str, Any]] = None
    replay_session_dir: Optional[str] = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route.to_dict(),
            "recovered_context": self.recovered_context.to_dict(),
            "discovered_skills": [skill.to_dict() for skill in self.discovered_skills],
            "kb_artifact": self.kb_artifact.to_dict() if self.kb_artifact else None,
            "plan_artifact": self.plan_artifact.to_dict() if self.plan_artifact else None,
            "skill_result": dict(self.skill_result or {}),
            "replay_session_dir": self.replay_session_dir,
            "notes": list(self.notes),
        }
