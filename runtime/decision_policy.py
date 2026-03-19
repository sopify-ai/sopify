"""Deterministic policies deciding when runtime should enter a decision checkpoint."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .models import DecisionOption, RouteDecision

PLANNING_DECISION_ROUTES = {"plan_only", "workflow", "light_iterate"}
TRADEOFF_CANDIDATES_ARTIFACT_KEY = "decision_candidates"

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


@dataclass(frozen=True)
class DecisionPolicyMatch:
    """Normalized trigger result returned by a decision policy."""

    policy_id: str
    template_id: str
    decision_type: str
    question: str
    summary: str = ""
    options: tuple[DecisionOption, ...] = ()
    option_texts: tuple[str, ...] = ()
    recommended_option_index: int = 0
    default_option_index: int = 0
    trigger_reason: str = ""
    context_files: tuple[str, ...] = ()


def should_trigger_decision_policy(route: RouteDecision) -> bool:
    return match_decision_policy(route) is not None


def has_tradeoff_checkpoint_signal(payload: Mapping[str, Any]) -> bool:
    """Return True when payload carries an unresolved user-facing tradeoff signal."""
    if not isinstance(payload, Mapping):
        return False
    if _has_candidate_tradeoff_signal(payload):
        return True
    if _has_options_tradeoff_signal(payload.get("options")):
        return True
    checkpoint = payload.get("checkpoint")
    if not isinstance(checkpoint, Mapping):
        checkpoint = payload.get("decision_checkpoint")
    return isinstance(checkpoint, Mapping) and _checkpoint_has_multiple_select_options(checkpoint)


def match_decision_policy(route: RouteDecision) -> DecisionPolicyMatch | None:
    """Match the highest-priority decision policy for the current route."""
    if route.route_name not in PLANNING_DECISION_ROUTES:
        return None

    structured_match = _match_structured_tradeoff_policy(route)
    if structured_match is not None:
        return structured_match

    return _match_planning_semantic_split(route)


def _match_planning_semantic_split(route: RouteDecision) -> DecisionPolicyMatch | None:
    """Keep the current planning-request trigger as the conservative baseline."""
    text = route.request_text.strip()
    if not text or not contains_architecture_keywords(text):
        return None

    alternatives = extract_alternatives(text)
    if alternatives is None:
        return None

    return DecisionPolicyMatch(
        policy_id="planning_semantic_split",
        template_id="strategy_pick",
        decision_type="architecture_choice",
        question=text,
        summary="",
        options=(),
        option_texts=alternatives,
        recommended_option_index=0,
        default_option_index=0,
        trigger_reason="explicit_architecture_split",
    )


def _match_structured_tradeoff_policy(route: RouteDecision) -> DecisionPolicyMatch | None:
    """Prefer structured design tradeoff candidates when the host/runtime provides them."""
    artifacts = route.artifacts
    options = _coerce_tradeoff_candidates(artifacts.get(TRADEOFF_CANDIDATES_ARTIFACT_KEY))
    if len(options) < 2:
        return None
    if _should_suppress_tradeoff_decision(artifacts):
        return None
    if not _has_significant_tradeoffs(artifacts, options):
        return None

    recommended_index = _resolve_option_index(
        option_id=artifacts.get("decision_recommended_option_id"),
        options=options,
    )
    if recommended_index is None:
        recommended_index = next((index for index, option in enumerate(options) if option.recommended), 0)

    default_index = _resolve_option_index(
        option_id=artifacts.get("decision_default_option_id"),
        options=options,
    )
    if default_index is None:
        default_index = recommended_index

    question = _text_value(artifacts.get("decision_question")) or route.request_text.strip() or "Confirm the design direction"
    summary = _text_value(artifacts.get("decision_summary")) or _default_tradeoff_summary(question)

    return DecisionPolicyMatch(
        policy_id="design_tradeoff_candidates",
        template_id="strategy_pick",
        decision_type=_text_value(artifacts.get("decision_type")) or "design_tradeoff",
        question=question,
        summary=summary,
        options=options,
        option_texts=tuple(option.title for option in options),
        recommended_option_index=recommended_index,
        default_option_index=default_index,
        trigger_reason="structured_tradeoff_candidates",
        context_files=_coerce_string_tuple(artifacts.get("decision_context_files")),
    )


def contains_architecture_keywords(text: str) -> bool:
    lowered = text.casefold()
    return any(keyword.casefold() in lowered for keyword in _ARCHITECTURE_KEYWORDS)


def extract_alternatives(text: str) -> tuple[str, str] | None:
    stripped = text.strip().rstrip("？?。.")
    for pattern in _ALTERNATIVE_PATTERNS:
        match = pattern.search(stripped)
        if not match:
            continue
        left = _clean_option(match.group("left"))
        right = _clean_option(match.group("right"))
        if left and right and left.casefold() != right.casefold():
            return (left, right)
    return None


def _clean_option(value: str) -> str:
    cleaned = value.strip().strip("：:")
    cleaned = re.sub(r"^(决策|选择|方案|option)\s*[：:]\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned[:120].rstrip()


def _should_suppress_tradeoff_decision(artifacts: Mapping[str, Any]) -> bool:
    suppression_flags = (
        "decision_suppress",
        "decision_preference_locked",
        "decision_single_obvious",
        "decision_information_only",
    )
    return any(bool(artifacts.get(flag, False)) for flag in suppression_flags)


def _has_candidate_tradeoff_signal(payload: Mapping[str, Any]) -> bool:
    options = _coerce_tradeoff_candidates(payload.get(TRADEOFF_CANDIDATES_ARTIFACT_KEY))
    if len(options) < 2:
        return False
    if _should_suppress_tradeoff_decision(payload):
        return False
    explicit = payload.get("decision_tradeoff_significant")
    if isinstance(explicit, bool):
        return explicit
    if _text_value(payload.get("decision_question")) or _text_value(payload.get("decision_summary")):
        return True
    return _has_significant_tradeoffs(payload, options)


def _has_options_tradeoff_signal(raw_options: Any) -> bool:
    return len(_coerce_tradeoff_candidates(raw_options)) >= 2


def _checkpoint_has_multiple_select_options(checkpoint: Mapping[str, Any]) -> bool:
    fields = checkpoint.get("fields")
    if not isinstance(fields, (list, tuple)):
        return False
    for field in fields:
        if not isinstance(field, Mapping):
            continue
        field_type = _text_value(field.get("field_type")).lower().replace("-", "_")
        if field_type not in {"select", "multi_select"}:
            continue
        if _has_options_tradeoff_signal(field.get("options")):
            return True
    return False


def _coerce_tradeoff_candidates(raw_candidates: Any) -> tuple[DecisionOption, ...]:
    if not isinstance(raw_candidates, (list, tuple)):
        return ()
    return tuple(
        option
        for index, candidate in enumerate(raw_candidates, start=1)
        if (option := _coerce_tradeoff_option(candidate, index=index)) is not None
    )


def _has_significant_tradeoffs(artifacts: Mapping[str, Any], options: tuple[DecisionOption, ...]) -> bool:
    explicit = artifacts.get("decision_tradeoff_significant")
    if isinstance(explicit, bool):
        return explicit
    informative_options = sum(1 for option in options if option.tradeoffs or option.impacts)
    return informative_options >= 2


def _coerce_tradeoff_option(candidate: Any, *, index: int) -> DecisionOption | None:
    if not isinstance(candidate, Mapping):
        return None
    option_id = _text_value(candidate.get("id") or candidate.get("option_id")) or f"option_{index}"
    title = _text_value(candidate.get("title") or candidate.get("name")) or option_id
    summary = _text_value(candidate.get("summary") or candidate.get("description")) or title
    return DecisionOption(
        option_id=option_id,
        title=title,
        summary=summary,
        tradeoffs=_coerce_string_tuple(candidate.get("tradeoffs")),
        impacts=_coerce_string_tuple(candidate.get("impacts")),
        recommended=bool(candidate.get("recommended", False)),
    )


def _resolve_option_index(*, option_id: Any, options: tuple[DecisionOption, ...]) -> int | None:
    normalized = _text_value(option_id)
    if not normalized:
        return None
    for index, option in enumerate(options):
        if option.option_id == normalized:
            return index
    return None


def _coerce_string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if not isinstance(value, (list, tuple)):
        return ()
    normalized: list[str] = []
    for item in value:
        text = _text_value(item)
        if text:
            normalized.append(text)
    return tuple(normalized)


def _text_value(value: Any) -> str:
    return str(value or "").strip()


def _default_tradeoff_summary(question: str) -> str:
    lowered = question.casefold()
    if any(token in lowered for token in ("why", "how", "compare", "tradeoff", "choose", "confirm")):
        return "Multiple executable candidates are available and the long-term direction still needs confirmation."
    return "存在多个可执行方案，需要先确认长期方向。"
