"""Deterministic route classifier for Sopify runtime."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .decision import parse_decision_response
from .models import DecisionState, RouteDecision, RuntimeConfig, SkillMeta
from .state import StateStore

_COMMAND_PATTERNS = (
    (re.compile(r"^~go\s+plan(?:\s+(?P<body>.+))?$", re.IGNORECASE), "~go plan"),
    (re.compile(r"^~go\s+exec(?:\s+(?P<body>.+))?$", re.IGNORECASE), "~go exec"),
    (re.compile(r"^~go(?:\s+(?P<body>.+))?$", re.IGNORECASE), "~go"),
    (re.compile(r"^~compare(?:\s+(?P<body>.+))?$", re.IGNORECASE), "~compare"),
)
SUPPORTED_ROUTE_NAMES = (
    "plan_only",
    "workflow",
    "light_iterate",
    "quick_fix",
    "resume_active",
    "exec_plan",
    "cancel_active",
    "decision_pending",
    "decision_resume",
    "compare",
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
_CANCEL_KEYWORDS = {"取消", "停止", "终止", "abort", "cancel", "stop"}
_ARCHITECTURE_KEYWORDS = ("架构", "系统", "runtime", "workflow", "engine", "adapter", "plugin", "新功能", "重构", "refactor")
_ACTION_KEYWORDS = (
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
    "what",
    "why",
    "how",
    "是否",
    "能否",
    "可以",
)
_FILE_REF_RE = re.compile(r"(?:[\w.-]+/)+[\w.-]+|[\w.-]+\.(?:ts|tsx|js|jsx|py|md|json|yaml|yml|vue|rs|go)")


@dataclass(frozen=True)
class _ComplexitySignal:
    level: str
    reason: str
    plan_level: str | None


class Router:
    """Classify user input into deterministic runtime routes."""

    def __init__(self, config: RuntimeConfig, *, state_store: StateStore) -> None:
        self.config = config
        self.state_store = state_store

    def classify(self, user_input: str, *, skills: Iterable[SkillMeta]) -> RouteDecision:
        text = user_input.strip()
        active_run = self.state_store.get_current_run()
        current_decision = self.state_store.get_current_decision()

        decide_decision = _classify_decide_command(text)
        if decide_decision is not None:
            return self._with_capture(decide_decision)

        command_decision = _classify_command(text)
        if command_decision is not None:
            return self._with_capture(command_decision)

        if _contains_intent(text, _REPLAY_KEYWORDS):
            return RouteDecision(
                route_name="replay",
                request_text=text,
                reason="Matched replay or review intent keywords",
                candidate_skill_ids=_candidate_skills(skills, "workflow-learning"),
                should_recover_context=True,
                runtime_skill_id=_runtime_skill(skills, "workflow-learning"),
            )

        if active_run is not None and _normalize(text) in _CANCEL_KEYWORDS:
            return RouteDecision(
                route_name="cancel_active",
                request_text=text,
                reason="Matched active-flow cancellation intent",
                complexity="simple",
                should_recover_context=True,
                active_run_action="cancel",
            )

        if current_decision is not None and current_decision.status in {"pending", "confirmed"}:
            pending_decision = _classify_pending_decision(text, current_decision, skills=skills)
            if pending_decision is not None:
                return self._with_capture(pending_decision)

        if active_run is not None and _normalize(text) in _CONTINUE_KEYWORDS:
            return self._with_capture(
                RouteDecision(
                    route_name="resume_active",
                    request_text=text,
                    reason="Matched active-flow continuation intent",
                    complexity="medium",
                    should_recover_context=True,
                    candidate_skill_ids=_candidate_skills(skills, "develop"),
                    active_run_action="resume",
                )
            )

        compare_intent = text.startswith("对比分析：") or text.lower().startswith("compare:")
        if compare_intent:
            body = text.split("：", 1)[1] if "：" in text else text.split(":", 1)[1]
            return RouteDecision(
                route_name="compare",
                request_text=body.strip(),
                reason="Matched explicit compare-analysis prefix",
                candidate_skill_ids=_candidate_skills(skills, "model-compare"),
                should_recover_context=False,
                runtime_skill_id=_runtime_skill(skills, "model-compare"),
            )

        if _is_consultation(text):
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
                    candidate_skill_ids=_candidate_skills(skills, "develop"),
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
                    should_create_plan=True,
                    candidate_skill_ids=_candidate_skills(skills, "design", "develop"),
                )
            )
        return self._with_capture(
            RouteDecision(
                route_name="workflow",
                request_text=text,
                reason=signal.reason,
                complexity=signal.level,
                plan_level=signal.plan_level,
                should_create_plan=True,
                candidate_skill_ids=_candidate_skills(skills, "analyze", "design", "develop"),
            )
        )

    def _with_capture(self, decision: RouteDecision) -> RouteDecision:
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
            should_create_plan=decision.should_create_plan,
            capture_mode=capture_mode,
            runtime_skill_id=decision.runtime_skill_id,
            active_run_action=decision.active_run_action,
        )


def _classify_command(text: str) -> RouteDecision | None:
    for pattern, command in _COMMAND_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        body = (match.groupdict().get("body") or "").strip()
        request_text = body or text
        if command == "~go plan":
            return RouteDecision(
                route_name="plan_only",
                request_text=request_text,
                reason="Matched explicit planning command",
                command=command,
                complexity="complex",
                plan_level="standard",
                should_create_plan=True,
                candidate_skill_ids=("analyze", "design"),
            )
        if command == "~go exec":
            return RouteDecision(
                route_name="exec_plan",
                request_text=request_text,
                reason="Matched explicit execute-plan command",
                command=command,
                complexity="medium",
                should_recover_context=True,
                candidate_skill_ids=("develop",),
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
                should_create_plan=True,
                candidate_skill_ids=("analyze", "design", "develop"),
            )
        if command == "~compare":
            return RouteDecision(
                route_name="compare",
                request_text=request_text,
                reason="Matched explicit compare command",
                command=command,
                candidate_skill_ids=("model-compare",),
                runtime_skill_id="model-compare",
            )
    return None


def _classify_decide_command(text: str) -> RouteDecision | None:
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
            candidate_skill_ids=("design",),
            active_run_action="inspect_decision",
        )
    return RouteDecision(
        route_name="decision_resume",
        request_text=stripped,
        reason="Matched explicit decision response command",
        complexity="medium",
        should_recover_context=True,
        candidate_skill_ids=("design",),
        active_run_action="decision_response",
    )


def _classify_pending_decision(text: str, current_decision: DecisionState, *, skills: Iterable[SkillMeta]) -> RouteDecision | None:
    response = parse_decision_response(current_decision, text)
    if response.action == "status":
        return RouteDecision(
            route_name="decision_pending",
            request_text=text,
            reason="Pending decision checkpoint is waiting for confirmation",
            complexity="medium",
            should_recover_context=True,
            candidate_skill_ids=_candidate_skills(skills, "design"),
            active_run_action="inspect_decision",
        )
    if response.action in {"choose", "materialize", "cancel", "invalid"}:
        return RouteDecision(
            route_name="decision_resume",
            request_text=text,
            reason="Matched a response for the pending decision checkpoint",
            complexity="medium",
            should_recover_context=True,
            candidate_skill_ids=_candidate_skills(skills, "design"),
            active_run_action="decision_response",
        )
    return None


def _estimate_complexity(text: str) -> _ComplexitySignal:
    lowered = text.lower()
    file_refs = len(_FILE_REF_RE.findall(text))
    has_arch = any(keyword.lower() in lowered for keyword in _ARCHITECTURE_KEYWORDS)
    has_action = any(keyword.lower() in lowered for keyword in _ACTION_KEYWORDS)

    if has_arch or file_refs > 5:
        plan_level = "full" if has_arch and any(token in lowered for token in ("架构", "system", "plugin", "adapter")) else "standard"
        return _ComplexitySignal("complex", "Detected architecture-scale or broad change intent", plan_level)
    if has_action and 3 <= file_refs <= 5:
        return _ComplexitySignal("medium", "Detected multi-file but bounded implementation request", "light")
    if has_action and file_refs == 0:
        return _ComplexitySignal("complex", "Detected change intent without bounded file scope", "standard")
    if has_action:
        return _ComplexitySignal("simple", "Detected focused implementation request with limited scope", None)
    return _ComplexitySignal("medium", "Defaulted to medium because the request is action-oriented but underspecified", "light")


def _is_consultation(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return True
    if any(keyword.lower() in normalized for keyword in _ACTION_KEYWORDS):
        return False
    if text.endswith("?") or text.endswith("？"):
        return True
    return normalized.startswith(_QUESTION_PREFIXES)


def _contains_intent(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _candidate_skills(skills: Iterable[SkillMeta], *preferred: str) -> tuple[str, ...]:
    available = {skill.skill_id for skill in skills}
    return tuple(skill_id for skill_id in preferred if skill_id in available)


def _runtime_skill(skills: Iterable[SkillMeta], skill_id: str) -> str | None:
    for skill in skills:
        if skill.skill_id == skill_id and skill.mode == "runtime":
            return skill_id
    return None


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
