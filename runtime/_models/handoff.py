"""Recovered-context, handoff, replay, and result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .artifacts import KbArtifact, PlanArtifact
from .core import RouteDecision, RunState, SkillMeta, _json_mapping
from .decision import ClarificationState, DecisionState


@dataclass(frozen=True)
class RecoveredContext:
    """Minimal context recovered from filesystem state."""

    loaded_files: tuple[str, ...] = ()
    current_run: Optional[RunState] = None
    current_plan: Optional[PlanArtifact] = None
    current_handoff: Optional["RuntimeHandoff"] = None
    current_clarification: Optional[ClarificationState] = None
    current_decision: Optional[DecisionState] = None
    last_route: Optional[RouteDecision] = None
    documents: Mapping[str, str] = field(default_factory=dict)
    quarantined_items: tuple[Mapping[str, Any], ...] = ()
    state_conflict: Mapping[str, Any] = field(default_factory=dict)
    resolution_id: str = ""

    @property
    def has_active_run(self) -> bool:
        return self.current_run is not None and self.current_run.is_active

    def to_dict(self) -> dict[str, Any]:
        return {
            "loaded_files": list(self.loaded_files),
            "current_run": self.current_run.to_dict() if self.current_run else None,
            "current_plan": self.current_plan.to_dict() if self.current_plan else None,
            "current_handoff": self.current_handoff.to_dict() if self.current_handoff else None,
            "current_clarification": self.current_clarification.to_dict() if self.current_clarification else None,
            "current_decision": self.current_decision.to_dict() if self.current_decision else None,
            "last_route": self.last_route.to_dict() if self.last_route else None,
            "documents": dict(self.documents),
            "quarantined_items": [dict(item) for item in self.quarantined_items],
            "state_conflict": dict(self.state_conflict),
            "resolution_id": self.resolution_id,
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
    required_host_action: str = "continue_host_develop"
    recommended_skill_ids: tuple[str, ...] = ()
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    observability: Mapping[str, Any] = field(default_factory=dict)
    resolution_id: str = ""

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
            "observability": _json_mapping(self.observability),
            "resolution_id": self.resolution_id,
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
            required_host_action=str(data.get("required_host_action") or "continue_host_develop"),
            recommended_skill_ids=tuple(data.get("recommended_skill_ids") or ()),
            artifacts=dict(artifacts) if isinstance(artifacts, Mapping) else {},
            notes=tuple(data.get("notes") or ()),
            observability=_json_mapping(data.get("observability")),
            resolution_id=str(data.get("resolution_id") or ""),
        )


@dataclass(frozen=True)
class SkillActivation:
    """Structured activation fact shared by output, replay, and daily summary."""

    skill_id: str
    skill_name: str
    activated_at: str
    activated_local_day: str
    display_time: str
    activation_source: str
    run_id: str
    route_name: str
    timezone: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "activated_at": self.activated_at,
            "activated_local_day": self.activated_local_day,
            "display_time": self.display_time,
            "activation_source": self.activation_source,
            "run_id": self.run_id,
            "route_name": self.route_name,
            "timezone": self.timezone,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SkillActivation":
        return cls(
            skill_id=str(data.get("skill_id") or ""),
            skill_name=str(data.get("skill_name") or ""),
            activated_at=str(data.get("activated_at") or ""),
            activated_local_day=str(data.get("activated_local_day") or ""),
            display_time=str(data.get("display_time") or ""),
            activation_source=str(data.get("activation_source") or ""),
            run_id=str(data.get("run_id") or ""),
            route_name=str(data.get("route_name") or ""),
            timezone=str(data.get("timezone") or ""),
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
    highlights: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

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
            "highlights": list(self.highlights),
            "artifacts": list(self.artifacts),
            "metadata": _json_mapping(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReplayEvent":
        return cls(
            ts=str(data.get("ts") or ""),
            phase=str(data.get("phase") or ""),
            intent=str(data.get("intent") or ""),
            action=str(data.get("action") or ""),
            key_output=str(data.get("key_output") or ""),
            decision_reason=str(data.get("decision_reason") or ""),
            result=str(data.get("result") or ""),
            risk=str(data.get("risk") or ""),
            alternatives=tuple(str(item) for item in (data.get("alternatives") or ()) if str(item).strip()),
            highlights=tuple(str(item) for item in (data.get("highlights") or ()) if str(item).strip()),
            artifacts=tuple(str(item) for item in (data.get("artifacts") or ()) if str(item).strip()),
            metadata=_json_mapping(data.get("metadata")),
        )


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
    activation: Optional[SkillActivation] = None
    generated_files: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route.to_dict(),
            "recovered_context": self.recovered_context.to_dict(),
            "discovered_skills": [skill.to_dict() for skill in self.discovered_skills],
            "kb_artifact": self.kb_artifact.to_dict() if self.kb_artifact else None,
            "plan_artifact": self.plan_artifact.to_dict() if self.plan_artifact else None,
            "skill_result": _json_mapping(self.skill_result),
            "replay_session_dir": self.replay_session_dir,
            "handoff": self.handoff.to_dict() if self.handoff else None,
            "activation": self.activation.to_dict() if self.activation else None,
            "generated_files": list(self.generated_files),
            "notes": list(self.notes),
        }
