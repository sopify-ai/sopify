"""Deterministic route classifier for Sopify runtime."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .clarification import has_submitted_clarification, parse_clarification_response
from .context_snapshot import ContextResolvedSnapshot, resolve_context_snapshot, snapshot_state_conflict_artifacts
from .decision import has_submitted_decision, parse_decision_response
from .entry_guard import DIRECT_EDIT_BLOCKED_RUNTIME_REQUIRED_REASON_CODE
from .plan_scaffold import find_plan_by_request_reference, request_explicitly_wants_new_plan
from .models import ClarificationState, DecisionState, RouteDecision, RuntimeConfig, SkillMeta
from .skill_resolver import resolve_route_candidate_skills, resolve_runtime_skill_id
from .state import StateStore

_COMMAND_PATTERNS = (
    (re.compile(r"^~summary(?:\s+(?P<body>.+))?$", re.IGNORECASE), "~summary"),
    (re.compile(r"^~go\s+plan(?:\s+(?P<body>.+))?$", re.IGNORECASE), "~go plan"),
    (re.compile(r"^~go\s+exec(?:\s+(?P<body>.+))?$", re.IGNORECASE), "~go exec"),
    (re.compile(r"^~go(?:\s+(?P<body>.+))?$", re.IGNORECASE), "~go"),
)
SUPPORTED_ROUTE_NAMES = (
    "plan_only",
    "workflow",
    "light_iterate",
    "quick_fix",
    "clarification_pending",
    "clarification_resume",
    "resume_active",
    "exec_plan",
    "cancel_active",
    "archive_lifecycle",
    "decision_pending",
    "decision_resume",
    "state_conflict",
    "summary",
    "replay",
    "consult",
)

_REPLAY_KEYWORDS = (
    "回放",
    "回看",
    "重放",
    "复盘",
    "回顾实现",
    "总结这次实现",
    "为什么这么做",
    "为什么选这个方案",
    "why did",
    "replay",
    "review the implementation",
)
_CONTINUE_KEYWORDS = {"继续", "下一步", "继续执行", "继续吧", "go on", "continue", "resume", "next"}
_CANCEL_KEYWORDS = {"取消", "强制取消", "停止", "终止", "算了", "放弃", "abort", "cancel", "stop", "force cancel"}
_ARCHITECTURE_KEYWORDS = ("架构", "系统", "runtime", "workflow", "engine", "adapter", "plugin", "新功能", "重构", "refactor")
_ACTION_KEYWORDS = (
    "补",
    "修",
    "修复",
    "实现",
    "添加",
    "新增",
    "修改",
    "重构",
    "优化",
    "删除",
    "fix",
    "implement",
    "add",
    "update",
    "refactor",
    "remove",
    "create",
)
_QUESTION_PREFIXES = (
    "为什么",
    "如何",
    "怎么",
    "解释",
    "说明",
    "看下",
    "看看",
    "what",
    "why",
    "how",
    "是否",
    "能否",
    "可以",
)
_STRONG_INTERROGATIVE_PREFIXES = (
    "为什么",
    "为何",
    "如何",
    "怎么",
    "解释",
    "说明",
    "what",
    "why",
    "how",
)
_SHORT_ACTION_REQUEST_THRESHOLD = 80
_FOLLOWUP_ACTION_CONNECTORS = ("并", "再", "然后", "顺便", "and", "then")
_ACTION_IMPACT_QUESTION_KEYWORDS = ("影响", "风险", "后果", "依赖", "波及")
_FILE_REF_RE = re.compile(r"(?:[\w.-]+/)+[\w.-]+|[\w.-]+\.(?:ts|tsx|js|jsx|py|md|json|yaml|yml|vue|rs|go)")
_PROCESS_FORCE_KEYWORDS_EN = ("design", "develop", "decision", "checkpoint", "handoff")
_PROCESS_FORCE_KEYWORDS_ZH = ("规划", "方案设计", "开发实施", "决策", "检查点", "交接", "门禁", "蓝图")
_PROCESS_FORCE_PATTERNS = (
    re.compile(
        rf"(?<![\w-])(?:{'|'.join(re.escape(keyword) for keyword in _PROCESS_FORCE_KEYWORDS_EN)})(?![\w-])",
        re.IGNORECASE,
    ),
    re.compile(rf"(?:{'|'.join(re.escape(keyword) for keyword in _PROCESS_FORCE_KEYWORDS_ZH)})"),
)
RUNTIME_FIRST_PROTECTED_PATH_PREFIXES = (".sopify-skills/plan/",)
_PROTECTED_PLAN_ASSET_RE = re.compile(r"(^|[\s'\"`])(?:\./)?\.sopify-skills/plan/[^\s'\"`]+", re.IGNORECASE)
_TRADEOFF_FORCE_KEYWORDS = ("tradeoff", "trade-off", "取舍", "分叉", "长期", "long-term", "contract", "契约", "策略分歧")
_TRADEOFF_FORCE_PATTERNS = (
    re.compile(r"(trade[\s-]?off|取舍|分叉|长期|long[\s-]?term|contract|契约|策略分歧)", re.IGNORECASE),
)
_LONG_TERM_CONTRACT_HINTS = (
    "架构",
    "蓝图",
    "contract",
    "契约",
    "policy",
    "策略",
    "入口",
    "runtime",
    "权限",
    "catalog",
    "slo",
    "长期",
)
_ACTIVE_PLAN_META_REVIEW_CUES = (
    "review",
    "分析下",
    "评估下",
    "解释下",
    "看看",
    "critique",
    "风险",
    "risk",
    "score",
    "评分",
    "打分",
    "优化点",
    "状态",
    "当前状态",
    "现在状态",
    "状态如何",
    "有什么问题",
    "还有什么问题",
)
_ACTIVE_PLAN_FOLLOWUP_EDIT_CUES = (
    "改一下",
    "改下",
    "改成",
    "改为",
    "修改",
    "补一下",
    "补下",
    "修一下",
    "修下",
    "调整",
    "edit",
    "change",
    "update",
    "fix",
    "adjust",
    "modify",
)
_PLAN_MATERIALIZATION_META_DEBUG_PATTERNS = (
    re.compile(r"(为什么|为何|why).*(生成|创建|create).*(plan|方案)", re.IGNORECASE),
    re.compile(r"(不要|别再|不要再|stop|don't).*(生成|创建|create).*(plan|方案)", re.IGNORECASE),
    re.compile(r"(分析下|解释下|看看|review).*(命中|hit).*(guard|plan|方案)", re.IGNORECASE),
)
_EXPLICIT_PLAN_PACKAGE_PATTERNS = (
    re.compile(r"(写到|写入|落到).*(background\.md|design\.md|tasks\.md)", re.IGNORECASE),
    re.compile(r"(写到|写入|落到).*(\.sopify-skills/plan/)", re.IGNORECASE),
    re.compile(r"(create|write).*(plan package|background\.md|design\.md|tasks\.md)", re.IGNORECASE),
)
_LIGHT_EDIT_HINTS = ("readme", "注释", "comment", "typo", "文案", "assert", "断言", "路径说明")
@dataclass(frozen=True)
class _ComplexitySignal:
    level: str
    reason: str
    plan_level: str | None


def build_runtime_first_hints() -> dict[str, object]:
    """Publish stable host-facing hints for requests that should enter via the gate."""
    return {
        "force_route_name": "workflow",
        "entry_guard_reason_code": DIRECT_EDIT_BLOCKED_RUNTIME_REQUIRED_REASON_CODE,
        "required_entry": "scripts/runtime_gate.py",
        "required_subcommand": "enter",
        "direct_entry_block_error_code": "runtime_gate_required",
        "debug_bypass_flag": "--allow-direct-entry",
        "protected_path_prefixes": list(RUNTIME_FIRST_PROTECTED_PATH_PREFIXES),
        "process_semantic_keywords": list(_PROCESS_FORCE_KEYWORDS_EN + _PROCESS_FORCE_KEYWORDS_ZH),
        "tradeoff_keywords": list(_TRADEOFF_FORCE_KEYWORDS),
        "long_term_contract_keywords": list(_LONG_TERM_CONTRACT_HINTS),
    }


def match_runtime_first_guard(text: str) -> dict[str, str] | None:
    """Return the matched runtime-first guard, if this request should not enter direct edit paths."""
    if _is_protected_plan_asset_request(text):
        return {
            "guard_kind": "protected_plan_asset",
            "reason": "Blocked direct-edit path because the request targets protected .sopify-skills/plan assets",
        }
    if _has_process_semantic_intent(text):
        return {
            "guard_kind": "process_semantic_intent",
            "reason": "Blocked direct-edit path because process-semantic keywords require runtime-first routing",
        }
    if _has_tradeoff_or_contract_split(text):
        return {
            "guard_kind": "tradeoff_contract_split",
            "reason": "Blocked direct-edit path because tradeoff or long-term contract split requires runtime-first routing",
        }
    return None


class Router:
    """Classify user input into deterministic runtime routes."""

    def __init__(self, config: RuntimeConfig, *, state_store: StateStore, global_state_store: StateStore | None = None) -> None:
        self.config = config
        self.state_store = state_store
        self.global_state_store = global_state_store or state_store

    def classify(
        self,
        user_input: str,
        *,
        skills: Iterable[SkillMeta],
        snapshot: ContextResolvedSnapshot | None = None,
    ) -> RouteDecision:
        text = user_input.strip()
        if snapshot is None:
            snapshot = resolve_context_snapshot(
                config=self.config,
                review_store=self.state_store,
                global_store=self.global_state_store,
            )

        current_clarification = snapshot.current_clarification
        current_decision = snapshot.current_decision
        review_active_run = snapshot.current_run
        execution_active_run = snapshot.execution_active_run
        global_active_run = execution_active_run if snapshot.preferred_state_scope == "global" else None
        if review_active_run is global_active_run:
            review_active_run = None
        execution_current_plan = snapshot.execution_current_plan
        current_plan = snapshot.current_plan
        current_last_route = snapshot.last_route

        decide_decision = _classify_decide_command(text, skills=skills)
        if decide_decision is not None:
            return self._with_capture(decide_decision)

        command_decision = _classify_command(text, skills=skills, config=self.config)
        if snapshot.is_conflict:
            return self._with_capture(
                _classify_state_conflict(
                    text,
                    command_decision=command_decision,
                    snapshot=snapshot,
                    skills=skills,
                )
            )

        if current_clarification is not None and current_clarification.status == "pending":
            pending_clarification = _classify_pending_clarification(
                text,
                current_clarification,
                command_decision=command_decision,
                skills=skills,
            )
            if pending_clarification is not None:
                return self._with_capture(pending_clarification)

        if current_decision is not None and current_decision.status in {"pending", "collecting", "confirmed", "cancelled", "timed_out"}:
            pending_decision = _classify_pending_decision(
                text,
                current_decision,
                command_decision=command_decision,
                skills=skills,
            )
            if pending_decision is not None:
                return self._with_capture(pending_decision)

        if _contains_intent(text, _REPLAY_KEYWORDS):
            return RouteDecision(
                route_name="replay",
                request_text=text,
                reason="Matched replay or review intent keywords",
                candidate_skill_ids=_candidate_skills("replay", skills, "workflow-learning"),
                should_recover_context=True,
                runtime_skill_id=_runtime_skill("replay", skills, "workflow-learning"),
            )

        if (global_active_run is not None or review_active_run is not None) and _normalize(text) in _CANCEL_KEYWORDS:
            return RouteDecision(
                route_name="cancel_active",
                request_text=text,
                reason="Matched active-flow cancellation intent",
                complexity="simple",
                should_recover_context=True,
                active_run_action="cancel",
                artifacts={
                    "cancel_scope": "global" if global_active_run is not None else "session",
                },
            )


        if command_decision is not None:
            return self._with_capture(command_decision)

        if execution_active_run is not None and _normalize(text) in _CONTINUE_KEYWORDS:
            return self._with_capture(
                RouteDecision(
                    route_name="resume_active",
                    request_text=text,
                    reason="Matched active-flow continuation intent",
                    complexity="medium",
                    should_recover_context=True,
                    candidate_skill_ids=_candidate_skills("resume_active", skills, "develop"),
                    active_run_action="resume",
                )
            )

        plan_meta_debug_route = _classify_plan_materialization_meta_debug(
            text,
            skills=skills,
        )
        if plan_meta_debug_route is not None:
            return self._with_capture(plan_meta_debug_route)

        runtime_first_guard = match_runtime_first_guard(text)
        if runtime_first_guard is not None:
            return self._with_capture(
                RouteDecision(
                    route_name="workflow",
                    request_text=text,
                    reason=runtime_first_guard["reason"],
                    complexity="complex",
                    plan_level="standard",
                    plan_package_policy=_plan_package_policy_for_route("workflow", text, config=self.config),
                    candidate_skill_ids=_candidate_skills("workflow", skills, "analyze", "design", "develop"),
                    artifacts={
                        "entry_guard_reason_code": DIRECT_EDIT_BLOCKED_RUNTIME_REQUIRED_REASON_CODE,
                        "direct_edit_guard_kind": runtime_first_guard["guard_kind"],
                        "direct_edit_guard_trigger": runtime_first_guard["reason"],
                    },
                )
            )

        if _is_consultation(text) and not _should_bypass_consult_for_active_plan_followup_edit(
            text,
            current_plan=current_plan,
        ):
            return RouteDecision(
                route_name="consult",
                request_text=text,
                reason="Looks like a direct question without change intent",
                complexity="simple",
            )

        signal = _estimate_complexity(text)
        if signal.level == "simple":
            return self._with_capture(
                RouteDecision(
                    route_name="quick_fix",
                    request_text=text,
                    reason=signal.reason,
                    complexity=signal.level,
                    candidate_skill_ids=_candidate_skills("quick_fix", skills, "develop"),
                )
            )
        if signal.level == "medium":
            return self._with_capture(
                RouteDecision(
                    route_name="light_iterate",
                    request_text=text,
                    reason=signal.reason,
                    complexity=signal.level,
                    plan_level=signal.plan_level,
                    plan_package_policy=_plan_package_policy_for_route("light_iterate", text, config=self.config),
                    candidate_skill_ids=_candidate_skills("light_iterate", skills, "design", "develop"),
                )
            )
        return self._with_capture(
            RouteDecision(
                route_name="workflow",
                request_text=text,
                reason=signal.reason,
                complexity=signal.level,
                plan_level=signal.plan_level,
                plan_package_policy=_plan_package_policy_for_route("workflow", text, config=self.config),
                candidate_skill_ids=_candidate_skills("workflow", skills, "analyze", "design", "develop"),
            )
        )

    def _with_capture(self, decision: RouteDecision) -> RouteDecision:
        if decision.route_name == "summary":
            capture_mode = "off"
        else:
            capture_mode = _decide_capture_mode(self.config.workflow_learning_auto_capture, decision.complexity)
        return RouteDecision(
            route_name=decision.route_name,
            request_text=decision.request_text,
            reason=decision.reason,
            command=decision.command,
            complexity=decision.complexity,
            plan_level=decision.plan_level,
            candidate_skill_ids=decision.candidate_skill_ids,
            should_recover_context=decision.should_recover_context,
            plan_package_policy=decision.plan_package_policy,
            should_create_plan=decision.should_create_plan,
            capture_mode=capture_mode,
            runtime_skill_id=decision.runtime_skill_id,
            active_run_action=decision.active_run_action,
            artifacts=decision.artifacts,
        )


def _classify_command(text: str, *, skills: Iterable[SkillMeta], config: RuntimeConfig) -> RouteDecision | None:
    for pattern, command in _COMMAND_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        body = (match.groupdict().get("body") or "").strip()
        request_text = body or text
        if command == "~summary":
            return RouteDecision(
                route_name="summary",
                request_text=request_text,
                reason="Matched explicit daily-summary command",
                command=command,
                complexity="simple",
                should_recover_context=True,
            )
        if command == "~go plan":
            return RouteDecision(
                route_name="plan_only",
                request_text=request_text,
                reason="Matched explicit planning command",
                command=command,
                complexity="complex",
                plan_level="standard",
                plan_package_policy="immediate",
                candidate_skill_ids=_candidate_skills("plan_only", skills, "analyze", "design"),
            )
        if command == "~go exec":
            return RouteDecision(
                route_name="exec_plan",
                request_text=request_text,
                reason="Matched explicit execute-plan command",
                command=command,
                complexity="medium",
                should_recover_context=True,
                candidate_skill_ids=_candidate_skills("exec_plan", skills, "develop"),
                active_run_action="resume",
            )
        if command == "~go":
            return RouteDecision(
                route_name="workflow",
                request_text=request_text,
                reason="Matched explicit workflow command",
                command=command,
                complexity="complex",
                plan_level="standard",
                plan_package_policy=_plan_package_policy_for_route("workflow", request_text, config=config),
                candidate_skill_ids=_candidate_skills("workflow", skills, "analyze", "design", "develop"),
            )
    return None


def _classify_state_conflict(
    text: str,
    *,
    command_decision: RouteDecision | None,
    snapshot: ContextResolvedSnapshot,
    skills: Iterable[SkillMeta],
) -> RouteDecision:
    normalized = _normalize(text)
    if normalized in _CANCEL_KEYWORDS:
        reason = "State conflict cleanup requested explicitly"
        active_run_action = "abort_conflict"
    else:
        reason = snapshot.conflict_message or "A conflicting runtime state blocks further routing until it is cleaned up"
        active_run_action = "inspect_conflict"
    artifacts = {
        **snapshot_state_conflict_artifacts(snapshot),
        "entry_guard_reason_code": "entry_guard_state_conflict",
    }
    return RouteDecision(
        route_name="state_conflict",
        request_text=text,
        reason=reason,
        command=command_decision.command if command_decision is not None else None,
        complexity="simple",
        should_recover_context=True,
        candidate_skill_ids=_candidate_skills("state_conflict", skills, "analyze", "develop"),
        active_run_action=active_run_action,
        artifacts=artifacts,
    )


def _classify_decide_command(text: str, *, skills: Iterable[SkillMeta]) -> RouteDecision | None:
    stripped = text.strip()
    lowered = stripped.lower()
    if not lowered.startswith("~decide"):
        return None
    if lowered.startswith("~decide status") or lowered == "~decide":
        return RouteDecision(
            route_name="decision_pending",
            request_text=stripped,
            reason="Matched explicit decision status command",
            complexity="medium",
            should_recover_context=True,
            candidate_skill_ids=_candidate_skills("decision_pending", skills, "design"),
            active_run_action="inspect_decision",
        )
    return RouteDecision(
        route_name="decision_resume",
        request_text=stripped,
        reason="Matched explicit decision response command",
        complexity="medium",
        should_recover_context=True,
        candidate_skill_ids=_candidate_skills("decision_resume", skills, "design"),
        active_run_action="decision_response",
    )


def _classify_pending_decision(
    text: str,
    current_decision: DecisionState,
    *,
    command_decision: RouteDecision | None,
    skills: Iterable[SkillMeta],
) -> RouteDecision | None:
    if (
        current_decision.status in {"pending", "collecting", "cancelled", "timed_out"}
        and has_submitted_decision(current_decision)
        and (command_decision is None or command_decision.route_name != "decision_pending")
    ):
        return RouteDecision(
            route_name="decision_resume",
            request_text=text,
            reason="Structured decision submission is ready to be resumed",
            complexity="medium",
            should_recover_context=True,
            candidate_skill_ids=_candidate_skills("decision_resume", skills, "design"),
            active_run_action="resume_submitted_decision",
        )

    if command_decision is not None:
        if command_decision.route_name in {"plan_only", "workflow", "light_iterate"}:
            return None
        if command_decision.route_name == "exec_plan":
            if current_decision.status == "pending":
                return RouteDecision(
                    route_name="decision_pending",
                    request_text=text,
                    reason="Pending decision checkpoint must be resolved before exec recovery can continue",
                    complexity="medium",
                    should_recover_context=True,
                    candidate_skill_ids=_candidate_skills("decision_pending", skills, "design"),
                    active_run_action="inspect_decision",
                )
            return RouteDecision(
                route_name="decision_resume",
                request_text=text,
                reason="Confirmed decision checkpoint is being materialized through the exec recovery entry",
                command=command_decision.command,
                complexity="medium",
                should_recover_context=True,
                candidate_skill_ids=_candidate_skills("decision_resume", skills, "design"),
                active_run_action="materialize_confirmed_decision",
            )

    response = parse_decision_response(current_decision, text)
    if response.action == "status":
        return RouteDecision(
            route_name="decision_pending",
            request_text=text,
            reason="Pending decision checkpoint is waiting for confirmation",
            complexity="medium",
            should_recover_context=True,
            candidate_skill_ids=_candidate_skills("decision_pending", skills, "design"),
            active_run_action="inspect_decision",
        )
    if response.action in {"choose", "materialize", "cancel", "invalid"}:
        return RouteDecision(
            route_name="decision_resume",
            request_text=text,
            reason="Matched a response for the pending decision checkpoint",
            complexity="medium",
            should_recover_context=True,
            candidate_skill_ids=_candidate_skills("decision_resume", skills, "design"),
            active_run_action="decision_response",
        )
    return None




def _classify_pending_clarification(
    text: str,
    current_clarification: ClarificationState,
    *,
    command_decision: RouteDecision | None,
    skills: Iterable[SkillMeta],
) -> RouteDecision | None:
    if command_decision is not None:
        if command_decision.route_name in {"plan_only", "workflow", "light_iterate"}:
            return None
        if command_decision.route_name == "exec_plan":
            return RouteDecision(
                route_name="clarification_pending",
                request_text=text,
                reason="Pending clarification must be answered before execution can continue",
                complexity="medium",
                should_recover_context=True,
                candidate_skill_ids=_candidate_skills("clarification_pending", skills, "analyze", "design"),
                active_run_action="inspect_clarification",
            )

    if has_submitted_clarification(current_clarification) and _normalize(text) in _CONTINUE_KEYWORDS:
        return RouteDecision(
            route_name="clarification_resume",
            request_text=text,
            reason="Restoring planning from structured clarification answers",
            complexity="medium",
            should_recover_context=True,
            candidate_skill_ids=_candidate_skills("clarification_resume", skills, "analyze", "design"),
            active_run_action="clarification_response_from_state",
        )

    response = parse_clarification_response(current_clarification, text)
    if response.action == "status":
        return RouteDecision(
            route_name="clarification_pending",
            request_text=text,
            reason="Pending clarification is still waiting for factual details",
            complexity="medium",
            should_recover_context=True,
            candidate_skill_ids=_candidate_skills("clarification_pending", skills, "analyze", "design"),
            active_run_action="inspect_clarification",
        )
    if response.action == "cancel":
        return RouteDecision(
            route_name="cancel_active",
            request_text=text,
            reason="Clarification cancelled by user",
            complexity="simple",
            should_recover_context=True,
            active_run_action="cancel",
        )
    if response.action == "answer":
        return RouteDecision(
            route_name="clarification_resume",
            request_text=text,
            reason="Received supplemental facts for the pending clarification",
            complexity="medium",
            should_recover_context=True,
            candidate_skill_ids=_candidate_skills("clarification_resume", skills, "analyze", "design"),
            active_run_action="clarification_response",
        )
    return RouteDecision(
        route_name="clarification_pending",
        request_text=text,
        reason=response.message or "Clarification still needs more factual details",
        complexity="medium",
        should_recover_context=True,
        candidate_skill_ids=_candidate_skills("clarification_pending", skills, "analyze", "design"),
        active_run_action="inspect_clarification",
    )




def _estimate_complexity(text: str) -> _ComplexitySignal:
    lowered = text.lower()
    file_refs = len(_FILE_REF_RE.findall(text))
    has_arch = any(keyword.lower() in lowered for keyword in _ARCHITECTURE_KEYWORDS)
    has_action = any(keyword.lower() in lowered for keyword in _ACTION_KEYWORDS)

    if has_action and any(token in lowered for token in _LIGHT_EDIT_HINTS):
        return _ComplexitySignal("simple", "Detected a bounded docs/tests wording tweak", None)
    if has_arch or file_refs > 5:
        plan_level = "full" if has_arch and any(token in lowered for token in ("架构", "system", "plugin", "adapter")) else "standard"
        return _ComplexitySignal("complex", "Detected architecture-scale or broad change intent", plan_level)
    if has_action and 3 <= file_refs <= 5:
        return _ComplexitySignal("medium", "Detected multi-file but bounded implementation request", "light")
    if has_action and file_refs == 0:
        if len(text.strip()) < _SHORT_ACTION_REQUEST_THRESHOLD:
            return _ComplexitySignal("medium", "Short action request without explicit file scope", "light")
        return _ComplexitySignal("complex", "Detected change intent without bounded file scope", "standard")
    if has_action:
        return _ComplexitySignal("simple", "Detected focused implementation request with limited scope", None)
    return _ComplexitySignal("medium", "Defaulted to medium because the request is action-oriented but underspecified", "light")



def _classify_plan_materialization_meta_debug(
    text: str,
    *,
    skills: Iterable[SkillMeta],
) -> RouteDecision | None:
    if not any(pattern.search(text) is not None for pattern in _PLAN_MATERIALIZATION_META_DEBUG_PATTERNS):
        return None
    return RouteDecision(
        route_name="consult",
        request_text=text,
        reason="Matched plan-materialization meta-debug intent and bypassed workflow routing",
        complexity="simple",
        should_recover_context=False,
        candidate_skill_ids=_candidate_skills("consult", skills, "analyze"),
    )


def _is_consultation(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return True
    has_action = any(keyword.lower() in normalized for keyword in _ACTION_KEYWORDS)
    if has_action:
        if normalized.startswith(("解释", "说明")) and _has_followup_action_clause(normalized):
            return False
        if normalized.startswith(_STRONG_INTERROGATIVE_PREFIXES):
            return True
        if (text.endswith("?") or text.endswith("？")) and _looks_like_action_impact_question(normalized):
            return True
        return False
    if text.endswith("?") or text.endswith("？"):
        return True
    return normalized.startswith(_QUESTION_PREFIXES)


def _has_followup_action_clause(normalized: str) -> bool:
    for connector in _FOLLOWUP_ACTION_CONNECTORS:
        index = normalized.find(connector)
        if index >= 0:
            tail = normalized[index + len(connector) :]
            if any(keyword.lower() in tail for keyword in _ACTION_KEYWORDS):
                return True
    return False


def _looks_like_action_impact_question(normalized: str) -> bool:
    return any(keyword in normalized for keyword in _ACTION_IMPACT_QUESTION_KEYWORDS)


def _is_protected_plan_asset_request(text: str) -> bool:
    return _PROTECTED_PLAN_ASSET_RE.search(text) is not None


def _has_process_semantic_intent(text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in _PROCESS_FORCE_PATTERNS)


def _plan_package_policy_for_route(route_name: str, request_text: str, *, config: RuntimeConfig) -> str:
    if route_name == "plan_only":
        return "immediate"
    if route_name not in {"workflow", "light_iterate"}:
        return "none"
    return "immediate"


def _request_explicitly_materializes_plan(request_text: str, *, config: RuntimeConfig) -> bool:
    if find_plan_by_request_reference(request_text, config=config) is not None:
        return False
    if request_explicitly_wants_new_plan(request_text):
        return True
    return any(pattern.search(request_text) is not None for pattern in _EXPLICIT_PLAN_PACKAGE_PATTERNS)


def _has_tradeoff_or_contract_split(text: str) -> bool:
    lowered = text.lower()
    if any(pattern.search(text) is not None for pattern in _TRADEOFF_FORCE_PATTERNS):
        return True
    split_signal = "还是" in text or "二选一" in text or "vs" in lowered or " or " in lowered
    if not split_signal:
        return False
    return any(token in lowered for token in _LONG_TERM_CONTRACT_HINTS)



def _active_plan_meta_review_has_followup_edit(text: str) -> bool:
    fragments = _split_active_plan_review_fragments(text)
    review_seen = False
    edit_seen = False
    for fragment in fragments:
        lowered = fragment.casefold()
        has_review = any(cue.casefold() in lowered for cue in _ACTIVE_PLAN_META_REVIEW_CUES)
        has_edit = any(cue.casefold() in lowered for cue in _ACTIVE_PLAN_FOLLOWUP_EDIT_CUES)
        if has_review and has_edit:
            return True
        if (review_seen and has_edit) or (edit_seen and has_review):
            return True
        review_seen = review_seen or has_review
        edit_seen = edit_seen or has_edit
    return False


def _should_bypass_consult_for_active_plan_followup_edit(text: str, *, current_plan) -> bool:
    if current_plan is None:
        return False
    return _active_plan_meta_review_has_followup_edit(text)


def _split_active_plan_review_fragments(text: str) -> tuple[str, ...]:
    fragments: list[str] = []
    current: list[str] = []
    for char in str(text or ""):
        if char in ",，;；:：.!！？?\n":
            fragment = "".join(current).strip()
            if fragment:
                fragments.append(fragment)
            current = []
            continue
        current.append(char)
    fragment = "".join(current).strip()
    if fragment:
        fragments.append(fragment)
    return tuple(fragments)




def _contains_intent(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _candidate_skills(route_name: str, skills: Iterable[SkillMeta], *preferred: str) -> tuple[str, ...]:
    return resolve_route_candidate_skills(
        route_name,
        skills,
        fallback_preferred=tuple(preferred),
    )


def _runtime_skill(route_name: str, skills: Iterable[SkillMeta], skill_id: str) -> str | None:
    return resolve_runtime_skill_id(
        route_name,
        skills,
        fallback_preferred=skill_id,
    )


def _decide_capture_mode(policy: str, complexity: str) -> str:
    if policy == "always":
        return "full"
    if policy == "manual" or policy == "off":
        return "off"
    if complexity == "simple":
        return "off"
    if complexity == "medium":
        return "summary"
    return "full"
