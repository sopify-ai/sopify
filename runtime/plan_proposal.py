"""Plan-proposal helpers for proposal-first planning materialization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Mapping

from .checkpoint_cancel import is_checkpoint_cancel_intent
from .models import DecisionState, PlanProposalState, RouteDecision

CURRENT_PLAN_PROPOSAL_FILENAME = "current_plan_proposal.json"
CURRENT_PLAN_PROPOSAL_RELATIVE_PATH = f".sopify-skills/state/{CURRENT_PLAN_PROPOSAL_FILENAME}"

_STATUS_ALIASES = {"status", "查看状态", "查看 proposal", "proposal status", "inspect"}
_CONFIRM_ALIASES = {"继续", "继续吧", "下一步", "continue", "next", "resume"}
_CANCEL_ALIASES = {"取消", "停止", "终止", "cancel", "stop", "abort"}
_FILE_REF_RE = re.compile(r"(?:[\w.-]+/)+[\w.-]+|[\w.-]+\.(?:ts|tsx|js|jsx|py|md|json|yaml|yml|vue|rs|go)")
_EXPLICIT_REVISION_VERB_PATTERNS = (
    re.compile(r"(改成|改为|调整|补充|增加|新增|删除|移除|去掉|展开|收敛|拆成|拆分|纳入|加入|补一下|改一下|补下|改下)", re.IGNORECASE),
    re.compile(r"\b(change|update|revise|edit|adjust|add|remove|drop|expand|split|include|exclude)\b", re.IGNORECASE),
)
_EXPLICIT_REVISION_TARGET_PATTERNS = (
    re.compile(r"(level|path|summary|risk|scope|background|design|task(?:s)?|proposal|package|file|files|module)", re.IGNORECASE),
    re.compile(r"(级别|路径|摘要|概要|风险|范围|背景|设计|任务|方案|方案包|文件|模块|拆分)", re.IGNORECASE),
)
_REVISION_MARKERS = ("修订意见:", "revision feedback:")
_HAS_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LEVEL_LABELS_ZH = {"light": "轻量", "standard": "标准", "full": "完整"}
_LEVEL_LABELS_EN = {"light": "light", "standard": "standard", "full": "full"}


@dataclass(frozen=True)
class PlanProposalResponse:
    """Normalized interpretation of a proposal-pending user reply."""

    action: str
    message: str = ""


def parse_plan_proposal_response(user_input: str) -> PlanProposalResponse:
    """Interpret a raw user reply while a plan proposal is pending."""
    text = str(user_input or "").strip()
    if not text:
        return PlanProposalResponse(action="inspect", message="Empty proposal response")
    normalized = text.casefold()
    if normalized in {alias.casefold() for alias in _CONFIRM_ALIASES}:
        return PlanProposalResponse(action="confirm")
    if normalized in {alias.casefold() for alias in _STATUS_ALIASES}:
        return PlanProposalResponse(action="inspect")
    if is_checkpoint_cancel_intent(text, cancel_aliases=_CANCEL_ALIASES):
        return PlanProposalResponse(action="cancel")
    if _looks_like_revision_feedback(text):
        return PlanProposalResponse(action="revise")
    return PlanProposalResponse(action="inspect", message="No explicit revision intent detected")


def merge_plan_proposal_request(proposal_state: PlanProposalState, feedback_text: str) -> str:
    """Merge the original planning request with revision feedback."""
    original = proposal_state.request_text.strip()
    feedback = str(feedback_text or "").strip()
    if not original:
        return feedback
    if not feedback:
        return original
    return f"{original}\n\n修订意见:\n{feedback}"


def build_plan_proposal_state(
    route: RouteDecision,
    *,
    request_text: str,
    proposed_level: str,
    checkpoint_id: str,
    reserved_plan_id: str,
    topic_key: str,
    proposed_path: str,
    confirmed_decision: DecisionState | None = None,
    created_at: str | None = None,
) -> PlanProposalState:
    """Create the persistent proposal state before a plan package is materialized."""
    now = created_at or iso_now()
    normalized_request = " ".join(str(request_text or "").split()).strip()
    candidate_files = extract_candidate_files(normalized_request)
    return PlanProposalState(
        schema_version="1",
        checkpoint_id=checkpoint_id,
        reserved_plan_id=reserved_plan_id,
        topic_key=topic_key,
        proposed_level=proposed_level,
        proposed_path=proposed_path,
        analysis_summary=build_plan_proposal_summary(
            normalized_request,
            proposed_level=proposed_level,
            candidate_files=candidate_files,
        ),
        estimated_task_count=estimate_task_count(proposed_level),
        candidate_files=candidate_files,
        request_text=normalized_request,
        resume_route=route.route_name,
        capture_mode=route.capture_mode,
        candidate_skill_ids=route.candidate_skill_ids,
        confirmed_decision=confirmed_decision.to_dict() if confirmed_decision is not None else {},
        created_at=now,
        updated_at=now,
    )


def refresh_plan_proposal_state(
    current: PlanProposalState,
    *,
    request_text: str,
    proposed_level: str,
) -> PlanProposalState:
    """Refresh proposal content without drifting proposal identity/path."""
    normalized_request = " ".join(str(request_text or "").split()).strip()
    candidate_files = extract_candidate_files(normalized_request)
    return PlanProposalState(
        schema_version=current.schema_version,
        checkpoint_id=current.checkpoint_id,
        reserved_plan_id=current.reserved_plan_id,
        topic_key=current.topic_key,
        proposed_level=proposed_level,
        proposed_path=current.proposed_path,
        analysis_summary=build_plan_proposal_summary(
            normalized_request,
            proposed_level=proposed_level,
            candidate_files=candidate_files,
        ),
        estimated_task_count=estimate_task_count(proposed_level),
        candidate_files=candidate_files,
        request_text=normalized_request,
        resume_route=current.resume_route,
        capture_mode=current.capture_mode,
        candidate_skill_ids=current.candidate_skill_ids,
        confirmed_decision=dict(current.confirmed_decision),
        created_at=current.created_at,
        updated_at=iso_now(),
    )


def extract_candidate_files(request_text: str) -> tuple[str, ...]:
    """Return stable file candidates mentioned in the request text."""
    seen: list[str] = []
    for match in _FILE_REF_RE.findall(str(request_text or "")):
        candidate = str(match).strip()
        if candidate and candidate not in seen:
            seen.append(candidate)
    return tuple(seen)


def _looks_like_revision_feedback(text: str) -> bool:
    if not any(pattern.search(text) is not None for pattern in _EXPLICIT_REVISION_VERB_PATTERNS):
        return False
    if _FILE_REF_RE.search(text) is not None:
        return True
    return any(pattern.search(text) is not None for pattern in _EXPLICIT_REVISION_TARGET_PATTERNS)


def build_plan_proposal_summary(
    request_text: str,
    *,
    proposed_level: str,
    candidate_files: tuple[str, ...],
) -> str:
    """Render a stable human summary for proposal confirmation checkpoints."""
    headline = _proposal_headline(request_text)
    revised = _contains_revision_feedback(request_text)
    if _HAS_CJK_RE.search(request_text):
        summary = f"围绕“{headline}”准备{_LEVEL_LABELS_ZH.get(proposed_level, '标准')}方案包"
        scope = _scope_summary_zh(candidate_files)
        if scope:
            summary = f"{summary}，重点涉及 {scope}"
        if revised:
            summary = f"{summary}，并纳入修订意见"
        return summary

    summary = f"Prepare a {_LEVEL_LABELS_EN.get(proposed_level, 'standard')} plan package for {headline}"
    scope = _scope_summary_en(candidate_files)
    if scope:
        summary = f"{summary}; focus on {scope}"
    if revised:
        summary = f"{summary}; includes updated revision feedback"
    return summary


def _proposal_headline(request_text: str) -> str:
    cleaned = str(request_text or "").strip()
    if not cleaned:
        return "the requested change"
    lowered = cleaned.casefold()
    cut = len(cleaned)
    for marker in _REVISION_MARKERS:
        position = lowered.find(marker.casefold())
        if position != -1:
            cut = min(cut, position)
    cleaned = cleaned[:cut].strip(" \n:;,.") or str(request_text or "").strip()
    return _summarize_text(cleaned, limit=48) or "the requested change"


def _contains_revision_feedback(request_text: str) -> bool:
    lowered = str(request_text or "").casefold()
    return any(marker.casefold() in lowered for marker in _REVISION_MARKERS)


def _scope_summary_zh(candidate_files: tuple[str, ...]) -> str:
    if not candidate_files:
        return ""
    if len(candidate_files) <= 3:
        return "、".join(candidate_files)
    return f"{'、'.join(candidate_files[:3])} 等 {len(candidate_files)} 个文件"


def _scope_summary_en(candidate_files: tuple[str, ...]) -> str:
    if not candidate_files:
        return ""
    if len(candidate_files) == 1:
        return candidate_files[0]
    if len(candidate_files) <= 3:
        return ", ".join(candidate_files)
    return f"{', '.join(candidate_files[:3])}, and {len(candidate_files) - 3} more files"


def _summarize_text(text: str, *, limit: int) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    if limit <= 3:
        return compact[:limit]
    return compact[: limit - 3].rstrip() + "..."


def estimate_task_count(plan_level: str) -> int:
    """Keep proposal summaries stable before the real scaffold exists."""
    return {
        "light": 3,
        "standard": 5,
        "full": 7,
    }.get(str(plan_level or "standard"), 5)


def confirmed_decision_from_proposal(proposal_state: PlanProposalState) -> DecisionState | None:
    """Rehydrate confirmed decision context carried through proposal state."""
    payload = proposal_state.confirmed_decision
    if not isinstance(payload, Mapping) or not payload:
        return None
    decision_state = DecisionState.from_dict(payload)
    if decision_state.status != "confirmed" or decision_state.selection is None:
        return None
    return decision_state


def iso_now() -> str:
    """Return a stable UTC ISO timestamp without importing runtime.state."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
