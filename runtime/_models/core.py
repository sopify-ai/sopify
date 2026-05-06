"""Core runtime contracts and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

DECISION_CONDITION_OPERATORS = ("equals", "not_equals", "in", "not_in")
DECISION_FIELD_TYPES = ("select", "multi_select", "confirm", "input", "textarea")
DECISION_SUBMISSION_STATUSES = ("empty", "draft", "collecting", "submitted", "confirmed", "cancelled", "timed_out")
DECISION_STATE_STATUSES = ("pending", "collecting", "confirmed", "consumed", "cancelled", "timed_out", "stale")
PLAN_PACKAGE_POLICIES = ("none", "immediate", "authorized_only")


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
    tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    allowed_paths: tuple[str, ...] = ()
    requires_network: bool = False
    host_support: tuple[str, ...] = ()
    permission_mode: str = "default"

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
            "tools": list(self.tools),
            "disallowed_tools": list(self.disallowed_tools),
            "allowed_paths": list(self.allowed_paths),
            "requires_network": self.requires_network,
            "host_support": list(self.host_support),
            "permission_mode": self.permission_mode,
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
    plan_package_policy: str = "none"
    should_create_plan: bool = False
    capture_mode: str = "off"
    runtime_skill_id: Optional[str] = None
    active_run_action: Optional[str] = None
    artifacts: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # `should_create_plan` remains as the compatibility projection for the
        # old immediate-materialization path while new callers switch to the
        # richer `plan_package_policy` contract.
        derived_policy = self.plan_package_policy
        if not str(derived_policy or "").strip():
            derived_policy = "immediate" if self.should_create_plan else "none"
        normalized_policy = _normalize_keyword(
            derived_policy,
            allowed=PLAN_PACKAGE_POLICIES,
            default="none",
        )
        object.__setattr__(self, "plan_package_policy", normalized_policy)
        object.__setattr__(self, "should_create_plan", normalized_policy == "immediate")

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
            "plan_package_policy": self.plan_package_policy,
            "should_create_plan": self.should_create_plan,
            "capture_mode": self.capture_mode,
            "runtime_skill_id": self.runtime_skill_id,
            "active_run_action": self.active_run_action,
            "artifacts": _json_mapping(self.artifacts),
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
            plan_package_policy=str(
                data.get("plan_package_policy")
                or ("immediate" if bool(data.get("should_create_plan", False)) else "none")
            ),
            should_create_plan=bool(data.get("should_create_plan", False)),
            capture_mode=str(data.get("capture_mode") or "off"),
            runtime_skill_id=data.get("runtime_skill_id") or None,
            active_run_action=data.get("active_run_action") or None,
            artifacts=_json_mapping(data.get("artifacts")),
        )


@dataclass(frozen=True)
class ExecutionGate:
    """Deterministic machine contract describing whether a plan can progress."""

    gate_status: str
    blocking_reason: str
    plan_completion: str
    next_required_action: str
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_status": self.gate_status,
            "blocking_reason": self.blocking_reason,
            "plan_completion": self.plan_completion,
            "next_required_action": self.next_required_action,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionGate":
        return cls(
            gate_status=str(data.get("gate_status") or "blocked"),
            blocking_reason=str(data.get("blocking_reason") or "none"),
            plan_completion=str(data.get("plan_completion") or "incomplete"),
            next_required_action=str(data.get("next_required_action") or "continue_host_develop"),
            notes=tuple(data.get("notes") or ()),
        )


@dataclass(frozen=True)
class ExecutionSummary:
    """Minimum summary shown before execution confirmation."""

    plan_path: str
    summary: str
    task_count: int
    risk_level: str
    key_risk: str
    mitigation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_path": self.plan_path,
            "summary": self.summary,
            "task_count": self.task_count,
            "risk_level": self.risk_level,
            "key_risk": self.key_risk,
            "mitigation": self.mitigation,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionSummary":
        return cls(
            plan_path=str(data.get("plan_path") or ""),
            summary=str(data.get("summary") or ""),
            task_count=int(data.get("task_count") or 0),
            risk_level=str(data.get("risk_level") or "medium"),
            key_risk=str(data.get("key_risk") or ""),
            mitigation=str(data.get("mitigation") or ""),
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
    execution_gate: Optional[ExecutionGate] = None
    execution_authorization_receipt: Optional[Mapping[str, Any]] = None
    request_excerpt: str = ""
    request_sha1: str = ""
    owner_session_id: str = ""
    owner_host: str = ""
    owner_run_id: str = ""
    resolution_id: str = ""

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
            "execution_gate": self.execution_gate.to_dict() if self.execution_gate else None,
            "execution_authorization_receipt": dict(self.execution_authorization_receipt) if self.execution_authorization_receipt else None,
            "request_excerpt": self.request_excerpt,
            "request_sha1": self.request_sha1,
            "owner_session_id": self.owner_session_id,
            "owner_host": self.owner_host,
            "owner_run_id": self.owner_run_id,
            "resolution_id": self.resolution_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunState":
        execution_gate = data.get("execution_gate")
        raw_receipt = data.get("execution_authorization_receipt")
        return cls(
            run_id=str(data.get("run_id") or ""),
            status=str(data.get("status") or "idle"),
            stage=str(data.get("stage") or ""),
            route_name=str(data.get("route_name") or ""),
            title=str(data.get("title") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            plan_id=data.get("plan_id") or None,
            plan_path=data.get("plan_path") or None,
            execution_gate=ExecutionGate.from_dict(execution_gate) if isinstance(execution_gate, Mapping) else None,
            execution_authorization_receipt=dict(raw_receipt) if isinstance(raw_receipt, Mapping) else None,
            request_excerpt=str(data.get("request_excerpt") or ""),
            request_sha1=str(data.get("request_sha1") or ""),
            owner_session_id=str(data.get("owner_session_id") or ""),
            owner_host=str(data.get("owner_host") or ""),
            owner_run_id=str(data.get("owner_run_id") or ""),
            resolution_id=str(data.get("resolution_id") or ""),
        )


# Keep these helpers in `core.py` so the internal split stays within the approved
# module budget instead of introducing a thin shared-utility layer.
def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _json_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _json_value(item) for key, item in value.items()}


def _normalize_keyword(value: Any, *, allowed: tuple[str, ...], default: str) -> str:
    normalized = str(value or default).strip().casefold().replace("-", "_")
    for candidate in allowed:
        if normalized == candidate.casefold():
            return candidate
    return default
