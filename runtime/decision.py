"""Deterministic decision-checkpoint helpers for design-stage branching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
import re
from typing import Optional

from .models import DecisionOption, DecisionSelection, DecisionState, RouteDecision, RuntimeConfig

CURRENT_DECISION_FILENAME = "current_decision.json"
CURRENT_DECISION_RELATIVE_PATH = f".sopify-skills/state/{CURRENT_DECISION_FILENAME}"

_PLANNING_ROUTES = {"plan_only", "workflow", "light_iterate"}
_ARCHITECTURE_KEYWORDS = (
    "runtime",
    "bundle",
    "payload",
    "manifest",
    "handoff",
    "workspace",
    "host",
    "blueprint",
    "history",
    "plan",
    "state",
    "目录",
    "契约",
    "蓝图",
    "归档",
    "宿主",
    "工作区",
    "根目录",
)
_ALTERNATIVE_PATTERNS = (
    re.compile(r"(?P<left>.+?)\s+还是\s+(?P<right>.+)", re.IGNORECASE),
    re.compile(r"(?P<left>.+?)\s+vs\.?\s+(?P<right>.+)", re.IGNORECASE),
    re.compile(r"(?P<left>.+?)\s+or\s+(?P<right>.+)", re.IGNORECASE),
)
_DECIDE_COMMAND_RE = re.compile(r"^~decide(?:\s+(?P<verb>status|cancel|choose))?(?:\s+(?P<body>.+))?$", re.IGNORECASE)
_STATUS_ALIASES = {"status", "查看决策", "查看当前决策", "decision status"}
_CONTINUE_ALIASES = {"继续", "继续执行", "下一步", "resume", "continue", "next"}
_CANCEL_ALIASES = {"取消", "停止", "终止", "abort", "cancel", "stop"}
_PUNCTUATION_RE = re.compile(r"[\s`'\"“”‘’.,:;!?(){}\[\]<>/\\|_-]+")


@dataclass(frozen=True)
class DecisionResponse:
    """Normalized interpretation of a user response to a pending decision."""

    action: str
    option_id: Optional[str] = None
    source: str = "text"
    message: str = ""


def should_trigger_decision_checkpoint(route: RouteDecision) -> bool:
    """Return True when the current planning route should pause for a decision."""
    if route.route_name not in _PLANNING_ROUTES:
        return False
    text = route.request_text.strip()
    if not text:
        return False
    if not _contains_architecture_keywords(text):
        return False
    return _extract_alternatives(text) is not None


def build_decision_state(route: RouteDecision, *, config: RuntimeConfig) -> DecisionState | None:
    """Create a deterministic decision packet from a planning request."""
    if not should_trigger_decision_checkpoint(route):
        return None

    extracted = _extract_alternatives(route.request_text)
    if extracted is None:
        return None
    left, right = extracted

    created_at = iso_now()
    feature_key = _feature_key(route.request_text)
    options = (
        _build_option("option_1", left, recommended=True, language=config.language),
        _build_option("option_2", right, recommended=False, language=config.language),
    )
    context_files = _context_files(config)

    return DecisionState(
        decision_id=_decision_id(route.request_text),
        feature_key=feature_key,
        phase="design",
        status="pending",
        decision_type="architecture_choice",
        question=route.request_text.strip(),
        summary=_summary_for_language(config.language),
        options=options,
        recommended_option_id=options[0].option_id,
        default_option_id=options[0].option_id,
        context_files=context_files,
        resume_route=route.route_name,
        request_text=route.request_text,
        requested_plan_level=route.plan_level,
        capture_mode=route.capture_mode,
        candidate_skill_ids=route.candidate_skill_ids,
        created_at=created_at,
        updated_at=created_at,
    )


def parse_decision_response(decision_state: DecisionState, user_input: str) -> DecisionResponse:
    """Interpret a raw user response against the current decision packet."""
    text = user_input.strip()
    if not text:
        return DecisionResponse(action="invalid", message="Empty decision response")

    command_match = _DECIDE_COMMAND_RE.match(text)
    if command_match:
        verb = (command_match.group("verb") or "status").lower()
        body = (command_match.group("body") or "").strip()
        if verb == "status":
            return DecisionResponse(action="status", source="debug_override")
        if verb == "cancel":
            return DecisionResponse(action="cancel", source="debug_override")
        if verb == "choose":
            option_id = _match_option(decision_state, body)
            if option_id is None:
                return DecisionResponse(action="invalid", source="debug_override", message=f"Unknown option: {body or '<empty>'}")
            return DecisionResponse(action="choose", option_id=option_id, source="debug_override")

    normalized = text.casefold()
    if normalized in {alias.casefold() for alias in _STATUS_ALIASES}:
        return DecisionResponse(action="status")
    if normalized in {alias.casefold() for alias in _CANCEL_ALIASES}:
        return DecisionResponse(action="cancel")
    if decision_state.status == "confirmed" and normalized in {alias.casefold() for alias in _CONTINUE_ALIASES}:
        return DecisionResponse(action="materialize")

    option_id = _match_option(decision_state, text)
    if option_id is not None:
        return DecisionResponse(action="choose", option_id=option_id, source="text")

    return DecisionResponse(action="invalid", message=f"Unrecognized decision response: {text}")


def confirm_decision(decision_state: DecisionState, *, option_id: str, source: str, raw_input: str) -> DecisionState:
    """Mark a decision as confirmed while preserving recovery data."""
    now = iso_now()
    return DecisionState(
        decision_id=decision_state.decision_id,
        feature_key=decision_state.feature_key,
        phase=decision_state.phase,
        status="confirmed",
        decision_type=decision_state.decision_type,
        question=decision_state.question,
        summary=decision_state.summary,
        options=decision_state.options,
        recommended_option_id=decision_state.recommended_option_id,
        default_option_id=decision_state.default_option_id,
        context_files=decision_state.context_files,
        resume_route=decision_state.resume_route,
        request_text=decision_state.request_text,
        requested_plan_level=decision_state.requested_plan_level,
        capture_mode=decision_state.capture_mode,
        candidate_skill_ids=decision_state.candidate_skill_ids,
        selection=DecisionSelection(option_id=option_id, source=source, raw_input=raw_input),
        created_at=decision_state.created_at,
        updated_at=now,
        confirmed_at=now,
        consumed_at=None,
    )


def consume_decision(decision_state: DecisionState) -> DecisionState:
    """Mark a decision as consumed before clearing it from current state."""
    now = iso_now()
    return DecisionState(
        decision_id=decision_state.decision_id,
        feature_key=decision_state.feature_key,
        phase=decision_state.phase,
        status="consumed",
        decision_type=decision_state.decision_type,
        question=decision_state.question,
        summary=decision_state.summary,
        options=decision_state.options,
        recommended_option_id=decision_state.recommended_option_id,
        default_option_id=decision_state.default_option_id,
        context_files=decision_state.context_files,
        resume_route=decision_state.resume_route,
        request_text=decision_state.request_text,
        requested_plan_level=decision_state.requested_plan_level,
        capture_mode=decision_state.capture_mode,
        candidate_skill_ids=decision_state.candidate_skill_ids,
        selection=decision_state.selection,
        created_at=decision_state.created_at,
        updated_at=now,
        confirmed_at=decision_state.confirmed_at,
        consumed_at=now,
    )


def stale_decision(decision_state: DecisionState) -> DecisionState:
    """Return a stale copy when a pending checkpoint is superseded."""
    now = iso_now()
    return DecisionState(
        decision_id=decision_state.decision_id,
        feature_key=decision_state.feature_key,
        phase=decision_state.phase,
        status="stale",
        decision_type=decision_state.decision_type,
        question=decision_state.question,
        summary=decision_state.summary,
        options=decision_state.options,
        recommended_option_id=decision_state.recommended_option_id,
        default_option_id=decision_state.default_option_id,
        context_files=decision_state.context_files,
        resume_route=decision_state.resume_route,
        request_text=decision_state.request_text,
        requested_plan_level=decision_state.requested_plan_level,
        capture_mode=decision_state.capture_mode,
        candidate_skill_ids=decision_state.candidate_skill_ids,
        selection=decision_state.selection,
        created_at=decision_state.created_at,
        updated_at=now,
        confirmed_at=decision_state.confirmed_at,
        consumed_at=decision_state.consumed_at,
    )


def option_by_id(decision_state: DecisionState, option_id: str) -> DecisionOption | None:
    """Return the option matching the given id."""
    for option in decision_state.options:
        if option.option_id == option_id:
            return option
    return None


def _contains_architecture_keywords(text: str) -> bool:
    lowered = text.casefold()
    return any(keyword.casefold() in lowered for keyword in _ARCHITECTURE_KEYWORDS)


def _extract_alternatives(text: str) -> tuple[str, str] | None:
    stripped = text.strip().rstrip("？?。.")
    for pattern in _ALTERNATIVE_PATTERNS:
        match = pattern.search(stripped)
        if not match:
            continue
        left = _clean_option(match.group("left"))
        right = _clean_option(match.group("right"))
        if left and right and left.casefold() != right.casefold():
            return left, right
    return None


def _clean_option(value: str) -> str:
    cleaned = value.strip().strip("：:")
    cleaned = re.sub(r"^(决策|选择|方案|option)\s*[：:]\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned[:120].rstrip()


def _build_option(option_id: str, raw_text: str, *, recommended: bool, language: str) -> DecisionOption:
    summary = raw_text
    if language == "en-US":
        tradeoffs = ("Will change the downstream plan shape and long-lived docs.",)
        impacts = ("Requires explicit confirmation before a formal plan is generated.",)
    else:
        tradeoffs = ("会改变后续 plan 结构与长期蓝图写入。",)
        impacts = ("需要先确认，再生成唯一正式 plan。",)
    return DecisionOption(
        option_id=option_id,
        title=raw_text,
        summary=summary,
        tradeoffs=tradeoffs,
        impacts=impacts,
        recommended=recommended,
    )


def _decision_id(request_text: str) -> str:
    digest = sha1(request_text.encode("utf-8")).hexdigest()[:8]
    return f"decision_{digest}"


def _feature_key(request_text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", request_text.casefold()).strip("-")
    if not normalized:
        return "decision"
    return normalized[:48].rstrip("-")


def _context_files(config: RuntimeConfig) -> tuple[str, ...]:
    candidates = (
        config.runtime_root / "project.md",
        config.runtime_root / "blueprint" / "README.md",
        config.runtime_root / "wiki" / "overview.md",
    )
    found: list[str] = []
    for candidate in candidates:
        if candidate.exists():
            found.append(str(candidate.relative_to(config.workspace_root)))
    return tuple(found)


def _summary_for_language(language: str) -> str:
    if language == "en-US":
        return "Detected an explicit design split that should be confirmed before creating the formal plan."
    return "检测到会影响正式 plan 与长期契约的设计分叉，需要先确认再继续。"


def _match_option(decision_state: DecisionState, raw_text: str) -> str | None:
    text = raw_text.strip()
    if not text:
        return None

    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(decision_state.options):
            return decision_state.options[index].option_id

    normalized = _normalize_text(text)
    for option in decision_state.options:
        if normalized == option.option_id.casefold():
            return option.option_id
        if normalized == _normalize_text(option.title):
            return option.option_id
        if normalized == _normalize_text(option.summary):
            return option.option_id
    return None


def _normalize_text(value: str) -> str:
    return _PUNCTUATION_RE.sub("", value.casefold())


def iso_now() -> str:
    """Return a stable UTC timestamp without importing the state module."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
