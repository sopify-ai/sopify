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
    entry_kind: Optional[str] = None
    handoff_kind: Optional[str] = None
    contract_version: str = "1"
    supports_routes: tuple[str, ...] = ()

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
            "entry_kind": self.entry_kind,
            "handoff_kind": self.handoff_kind,
            "contract_version": self.contract_version,
            "supports_routes": list(self.supports_routes),
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
class DecisionOption:
    """A concrete option presented by a decision checkpoint."""

    option_id: str
    title: str
    summary: str
    tradeoffs: tuple[str, ...] = ()
    impacts: tuple[str, ...] = ()
    recommended: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.option_id,
            "title": self.title,
            "summary": self.summary,
            "tradeoffs": list(self.tradeoffs),
            "impacts": list(self.impacts),
            "recommended": self.recommended,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DecisionOption":
        return cls(
            option_id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            summary=str(data.get("summary") or ""),
            tradeoffs=tuple(data.get("tradeoffs") or ()),
            impacts=tuple(data.get("impacts") or ()),
            recommended=bool(data.get("recommended", False)),
        )


@dataclass(frozen=True)
class DecisionSelection:
    """User-confirmed selection captured by the checkpoint."""

    option_id: str
    source: str
    raw_input: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "option_id": self.option_id,
            "source": self.source,
            "raw_input": self.raw_input,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DecisionSelection":
        return cls(
            option_id=str(data.get("option_id") or ""),
            source=str(data.get("source") or "text"),
            raw_input=str(data.get("raw_input") or ""),
        )


@dataclass(frozen=True)
class DecisionState:
    """Filesystem-backed pending design decision."""

    decision_id: str
    feature_key: str
    phase: str
    status: str
    decision_type: str
    question: str
    summary: str
    options: tuple[DecisionOption, ...]
    recommended_option_id: Optional[str] = None
    default_option_id: Optional[str] = None
    context_files: tuple[str, ...] = ()
    resume_route: Optional[str] = None
    request_text: str = ""
    requested_plan_level: Optional[str] = None
    capture_mode: str = "off"
    candidate_skill_ids: tuple[str, ...] = ()
    selection: Optional[DecisionSelection] = None
    created_at: str = ""
    updated_at: str = ""
    confirmed_at: Optional[str] = None
    consumed_at: Optional[str] = None

    @property
    def selected_option_id(self) -> Optional[str]:
        return self.selection.option_id if self.selection is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "feature_key": self.feature_key,
            "phase": self.phase,
            "status": self.status,
            "decision_type": self.decision_type,
            "question": self.question,
            "summary": self.summary,
            "options": [option.to_dict() for option in self.options],
            "recommended_option_id": self.recommended_option_id,
            "default_option_id": self.default_option_id,
            "context_files": list(self.context_files),
            "resume_route": self.resume_route,
            "request_text": self.request_text,
            "requested_plan_level": self.requested_plan_level,
            "capture_mode": self.capture_mode,
            "candidate_skill_ids": list(self.candidate_skill_ids),
            "selection": self.selection.to_dict() if self.selection else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "confirmed_at": self.confirmed_at,
            "consumed_at": self.consumed_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DecisionState":
        selection = data.get("selection")
        return cls(
            decision_id=str(data.get("decision_id") or ""),
            feature_key=str(data.get("feature_key") or ""),
            phase=str(data.get("phase") or "design"),
            status=str(data.get("status") or "pending"),
            decision_type=str(data.get("decision_type") or "design_choice"),
            question=str(data.get("question") or ""),
            summary=str(data.get("summary") or ""),
            options=tuple(DecisionOption.from_dict(option) for option in (data.get("options") or ())),
            recommended_option_id=data.get("recommended_option_id") or None,
            default_option_id=data.get("default_option_id") or None,
            context_files=tuple(data.get("context_files") or ()),
            resume_route=data.get("resume_route") or None,
            request_text=str(data.get("request_text") or ""),
            requested_plan_level=data.get("requested_plan_level") or None,
            capture_mode=str(data.get("capture_mode") or "off"),
            candidate_skill_ids=tuple(data.get("candidate_skill_ids") or ()),
            selection=DecisionSelection.from_dict(selection) if isinstance(selection, Mapping) else None,
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            confirmed_at=data.get("confirmed_at") or None,
            consumed_at=data.get("consumed_at") or None,
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
    current_decision: Optional[DecisionState] = None
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
            "current_decision": self.current_decision.to_dict() if self.current_decision else None,
            "last_route": self.last_route.to_dict() if self.last_route else None,
            "documents": dict(self.documents),
        }


@dataclass(frozen=True)
class RuntimeHandoff:
    """Structured machine handoff for downstream host execution."""

    schema_version: str
    route_name: str
    run_id: str
    plan_id: Optional[str] = None
    plan_path: Optional[str] = None
    handoff_kind: str = "default"
    required_host_action: str = "continue_host_workflow"
    recommended_skill_ids: tuple[str, ...] = ()
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "route_name": self.route_name,
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "plan_path": self.plan_path,
            "handoff_kind": self.handoff_kind,
            "required_host_action": self.required_host_action,
            "recommended_skill_ids": list(self.recommended_skill_ids),
            "artifacts": dict(self.artifacts),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuntimeHandoff":
        artifacts = data.get("artifacts")
        return cls(
            schema_version=str(data.get("schema_version") or "1"),
            route_name=str(data.get("route_name") or "consult"),
            run_id=str(data.get("run_id") or ""),
            plan_id=data.get("plan_id") or None,
            plan_path=data.get("plan_path") or None,
            handoff_kind=str(data.get("handoff_kind") or "default"),
            required_host_action=str(data.get("required_host_action") or "continue_host_workflow"),
            recommended_skill_ids=tuple(data.get("recommended_skill_ids") or ()),
            artifacts=dict(artifacts) if isinstance(artifacts, Mapping) else {},
            notes=tuple(data.get("notes") or ()),
        )


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
    handoff: Optional[RuntimeHandoff] = None
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
            "handoff": self.handoff.to_dict() if self.handoff else None,
            "notes": list(self.notes),
        }
