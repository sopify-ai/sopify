"""Deterministic execution gate evaluator for runtime-managed plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

from ._yaml import YamlParseError, load_yaml
from .knowledge_sync import parse_knowledge_sync
from .models import ClarificationState, DecisionState, ExecutionGate, PlanArtifact, RouteDecision, RuntimeConfig

_FRONT_MATTER_RE = re.compile(r"\A---\n(?P<front>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
_REQUIRED_METADATA_KEYS = (
    "plan_id",
    "feature_key",
    "level",
    "lifecycle_state",
    "knowledge_sync",
    "archive_ready",
)
_PLACEHOLDER_TOKENS = (
    "待分析",
    "待补充",
    "待确认",
    "todo",
    "tbd",
    "placeholder",
    "to be analyzed",
    "to be determined",
)
_RISK_RULES = (
    (
        "destructive_change",
        ("删除生产数据", "drop table", "truncate", "breaking delete", "破坏性删除", "不可逆删除"),
        ("回滚", "rollback", "备份", "backup", "shadow copy", "只读", "non-destructive", "不删除生产数据"),
    ),
    (
        "auth_boundary",
        ("认证", "授权", "auth", "oauth", "rbac", "permission", "权限边界", "token"),
        ("保持现有权限", "不改认证", "不改授权", "沿用现有", "read-only", "no auth changes", "reuse existing auth"),
    ),
    (
        "schema_change",
        ("schema", "migration", "ddl", "数据库结构", "表结构", "字段类型", "schema change", "索引变更"),
        ("兼容", "向后兼容", "双写", "回滚", "rollback", "expand-contract", "non-breaking", "迁移脚本"),
    ),
    (
        "scope_tradeoff",
        ("范围取舍", "tradeoff", "trade-off", "待拍板", "待确认", "open question", "可选方案"),
        ("已确认", "confirmed", "selected option", "选定", "最终方案", "single path"),
    ),
)


@dataclass(frozen=True)
class _ManagedPlanDocument:
    plan_dir: Path
    metadata_path: Path
    metadata: Mapping[str, Any]
    knowledge_sync: Mapping[str, str]
    body: str
    documents: Mapping[str, str]


@dataclass(frozen=True)
class _CompletenessStatus:
    plan_completion: str
    notes: tuple[str, ...]


def evaluate_execution_gate(
    *,
    decision: RouteDecision,
    plan_artifact: PlanArtifact | None,
    current_clarification: ClarificationState | None,
    current_decision: DecisionState | None,
    config: RuntimeConfig,
) -> ExecutionGate:
    """Evaluate whether the current plan may progress beyond planning."""
    if current_clarification is not None and current_clarification.status == "pending":
        return ExecutionGate(
            gate_status="blocked",
            blocking_reason="missing_info",
            plan_completion="incomplete",
            next_required_action="answer_questions",
            notes=(_text(config.language, "clarification_pending"),),
        )

    if current_decision is not None and current_decision.status in {"pending", "collecting", "cancelled", "timed_out"}:
        return ExecutionGate(
            gate_status="decision_required",
            blocking_reason="unresolved_decision",
            plan_completion="incomplete",
            next_required_action="confirm_decision",
            notes=(_text(config.language, "decision_pending"),),
        )

    if plan_artifact is None:
        return ExecutionGate(
            gate_status="blocked",
            blocking_reason="missing_info",
            plan_completion="incomplete",
            next_required_action="continue_host_develop",
            notes=(_text(config.language, "missing_plan"),),
        )

    managed_plan = _load_managed_plan(plan_artifact=plan_artifact, config=config)
    if managed_plan is None:
        return ExecutionGate(
            gate_status="blocked",
            blocking_reason="missing_info",
            plan_completion="incomplete",
            next_required_action="continue_host_develop",
            notes=(_text(config.language, "invalid_plan_metadata"),),
        )

    completeness = _evaluate_plan_completeness(managed_plan, language=config.language)
    if completeness.plan_completion != "complete":
        return ExecutionGate(
            gate_status="blocked",
            blocking_reason="missing_info",
            plan_completion=completeness.plan_completion,
            next_required_action="continue_host_develop",
            notes=completeness.notes,
        )

    unresolved = _detect_unresolved_risk(
        managed_plan,
        current_decision=current_decision,
        request_text=decision.request_text,
        language=config.language,
    )
    if unresolved is not None:
        return unresolved

    return ExecutionGate(
        gate_status="ready",
        blocking_reason="none",
        plan_completion="complete",
        next_required_action="continue_host_develop",
        notes=(_text(config.language, "gate_ready"),),
    )


def _load_managed_plan(*, plan_artifact: PlanArtifact, config: RuntimeConfig) -> _ManagedPlanDocument | None:
    plan_dir = config.workspace_root / plan_artifact.path
    metadata_path = _pick_metadata_file(plan_dir)
    if metadata_path is None:
        return None

    raw_text = metadata_path.read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(raw_text)
    if match is None:
        return None

    try:
        metadata = load_yaml(match.group("front"))
    except YamlParseError:
        return None
    if not isinstance(metadata, Mapping):
        return None
    knowledge_sync = parse_knowledge_sync(metadata.get("knowledge_sync"))
    if knowledge_sync is None:
        return None

    documents: dict[str, str] = {
        metadata_path.name: raw_text,
    }
    for filename in ("background.md", "design.md", "tasks.md", "plan.md"):
        candidate = plan_dir / filename
        if candidate.exists() and candidate.is_file() and filename not in documents:
            documents[filename] = candidate.read_text(encoding="utf-8")

    return _ManagedPlanDocument(
        plan_dir=plan_dir,
        metadata_path=metadata_path,
        metadata=metadata,
        knowledge_sync=knowledge_sync,
        body=match.group("body"),
        documents=documents,
    )


def _pick_metadata_file(plan_dir: Path) -> Path | None:
    for filename in ("plan.md", "tasks.md"):
        candidate = plan_dir / filename
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _evaluate_plan_completeness(managed_plan: _ManagedPlanDocument, *, language: str) -> _CompletenessStatus:
    metadata = managed_plan.metadata
    if any(key not in metadata for key in _REQUIRED_METADATA_KEYS):
        return _CompletenessStatus("incomplete", (_text(language, "missing_metadata"),))
    if parse_knowledge_sync(metadata.get("knowledge_sync")) is None:
        return _CompletenessStatus("incomplete", (_text(language, "invalid_knowledge_sync"),))

    level = str(metadata.get("level") or "")
    if level not in {"light", "standard", "full"}:
        return _CompletenessStatus("incomplete", (_text(language, "invalid_level"),))

    checkpoint = metadata.get("decision_checkpoint")
    if isinstance(checkpoint, Mapping):
        selected_option_id = str(checkpoint.get("selected_option_id") or "").strip()
        checkpoint_status = str(checkpoint.get("status") or "").strip()
        if not selected_option_id or checkpoint_status not in {"confirmed", "consumed"}:
            return _CompletenessStatus("incomplete", (_text(language, "decision_not_persisted"),))

    if level == "light":
        plan_text = managed_plan.documents.get("plan.md", managed_plan.metadata_path.read_text(encoding="utf-8"))
        if "## 任务" not in plan_text or "- [ ]" not in plan_text:
            return _CompletenessStatus("incomplete", (_text(language, "missing_tasks"),))
        if not _section_is_resolved(plan_text, "## 变更文件"):
            return _CompletenessStatus("incomplete", (_text(language, "missing_scope"),))
        return _CompletenessStatus("complete", ())

    background_text = managed_plan.documents.get("background.md", "")
    design_text = managed_plan.documents.get("design.md", "")
    tasks_text = managed_plan.documents.get("tasks.md", "")
    if not background_text or not design_text or not tasks_text:
        return _CompletenessStatus("incomplete", (_text(language, "missing_plan_files"),))
    if "- [ ]" not in tasks_text:
        return _CompletenessStatus("incomplete", (_text(language, "missing_tasks"),))
    if not _section_is_resolved(background_text, "## 影响范围"):
        return _CompletenessStatus("incomplete", (_text(language, "missing_scope"),))
    if not _section_is_resolved(background_text, "## 风险评估"):
        return _CompletenessStatus("incomplete", (_text(language, "missing_risk"),))
    return _CompletenessStatus("complete", ())


def _section_is_resolved(text: str, heading: str) -> bool:
    section = _extract_section(text, heading)
    if not section:
        return False
    lowered = section.casefold()
    return not any(token in lowered for token in _PLACEHOLDER_TOKENS)


def _extract_section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    start = text.find("\n", start)
    if start < 0:
        return ""
    tail = text[start + 1 :]
    for marker in ("\n## ", "\n# "):
        boundary = tail.find(marker)
        if boundary >= 0:
            tail = tail[:boundary]
            break
    return tail.strip()


def _detect_unresolved_risk(
    managed_plan: _ManagedPlanDocument,
    *,
    current_decision: DecisionState | None,
    request_text: str,
    language: str,
) -> ExecutionGate | None:
    metadata_checkpoint = managed_plan.metadata.get("decision_checkpoint")
    if isinstance(metadata_checkpoint, Mapping):
        selected_option_id = str(metadata_checkpoint.get("selected_option_id") or "").strip()
        checkpoint_status = str(metadata_checkpoint.get("status") or "").strip()
        if checkpoint_status == "pending" or (metadata_checkpoint.get("required") and not selected_option_id):
            return ExecutionGate(
                gate_status="decision_required",
                blocking_reason="unresolved_decision",
                plan_completion="complete",
                next_required_action="confirm_decision",
                notes=(_text(language, "decision_pending"),),
            )

    aggregate_text = "\n".join(
        [request_text, *managed_plan.documents.values()]
    ).casefold()
    for blocking_reason, keywords, mitigation_keywords in _RISK_RULES:
        if not any(keyword.casefold() in aggregate_text for keyword in keywords):
            continue
        if _decision_resolves(blocking_reason, current_decision=current_decision, metadata_checkpoint=metadata_checkpoint):
            continue
        if any(keyword.casefold() in aggregate_text for keyword in mitigation_keywords):
            continue
        return ExecutionGate(
            gate_status="decision_required",
            blocking_reason=blocking_reason,
            plan_completion="complete",
            next_required_action="confirm_decision",
            notes=(_text(language, "risk_requires_decision", reason=blocking_reason),),
        )
    return None


def _decision_resolves(
    blocking_reason: str,
    *,
    current_decision: DecisionState | None,
    metadata_checkpoint: Any,
) -> bool:
    if current_decision is not None and current_decision.status == "confirmed" and current_decision.selection is not None:
        if current_decision.decision_type == "architecture_choice" and blocking_reason == "scope_tradeoff":
            return True
        if current_decision.decision_type == f"execution_gate_{blocking_reason}":
            return True

    if not isinstance(metadata_checkpoint, Mapping):
        return False
    checkpoint_status = str(metadata_checkpoint.get("status") or "").strip()
    selected_option_id = str(metadata_checkpoint.get("selected_option_id") or "").strip()
    return blocking_reason == "scope_tradeoff" and checkpoint_status in {"confirmed", "consumed"} and bool(selected_option_id)


def _text(language: str, key: str, **values: str) -> str:
    locale = "en-US" if language == "en-US" else "zh-CN"
    messages = {
        "zh-CN": {
            "clarification_pending": "当前仍缺执行前所需的关键事实信息。",
            "decision_pending": "当前仍有待确认的设计或风险决策。",
            "missing_plan": "当前没有可评估的活动 plan。",
            "invalid_plan_metadata": "当前 plan 缺少可评估的 metadata-managed 结构。",
            "missing_metadata": "plan 元数据不完整，尚不能进入执行门禁。",
            "invalid_knowledge_sync": "plan 的 knowledge_sync 契约非法，尚不能进入执行门禁。",
            "invalid_level": "plan level 非法，尚不能进入执行门禁。",
            "decision_not_persisted": "决策结果尚未稳定写入 plan metadata。",
            "missing_tasks": "plan 缺少可执行任务清单。",
            "missing_scope": "plan 还没有收口明确的执行范围。",
            "missing_risk": "plan 还没有收口关键风险与缓解说明。",
            "risk_requires_decision": "plan 中仍存在需要拍板的阻塞风险：{reason}。",
            "gate_ready": "plan 已通过机器执行门禁。",
        },
        "en-US": {
            "clarification_pending": "Critical facts are still missing before execution may proceed.",
            "decision_pending": "A design or risk decision is still pending.",
            "missing_plan": "No active plan is available for execution-gate evaluation.",
            "invalid_plan_metadata": "The current plan is not a valid metadata-managed plan package.",
            "missing_metadata": "The plan metadata is incomplete and cannot pass the execution gate yet.",
            "invalid_knowledge_sync": "The plan knowledge_sync contract is invalid and cannot pass the execution gate yet.",
            "invalid_level": "The plan level is invalid and cannot pass the execution gate yet.",
            "decision_not_persisted": "The confirmed decision has not been persisted into the plan metadata yet.",
            "missing_tasks": "The plan does not contain an actionable task list yet.",
            "missing_scope": "The plan does not describe a concrete execution scope yet.",
            "missing_risk": "The plan does not explain the key risks and mitigations yet.",
            "risk_requires_decision": "The plan still contains a blocking risk that needs confirmation: {reason}.",
            "gate_ready": "The plan passed the machine execution gate.",
        },
    }
    return messages[locale][key].format(**values)
