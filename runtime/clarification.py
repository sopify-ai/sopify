"""Deterministic clarification helpers for missing planning facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
import re
from typing import Any, Mapping, Optional

from .models import ClarificationState, RouteDecision, RuntimeConfig

CURRENT_CLARIFICATION_FILENAME = "current_clarification.json"
CURRENT_CLARIFICATION_RELATIVE_PATH = f".sopify-skills/state/{CURRENT_CLARIFICATION_FILENAME}"
SCOPE_CLARIFY_TEMPLATE_ID = "scope_clarify"
TARGET_SCOPE_FIELD_ID = "target_scope"
EXPECTED_OUTCOME_FIELD_ID = "expected_outcome"

_PLANNING_ROUTES = {"plan_only", "workflow", "light_iterate"}
_QUESTION_ALIASES = {"查看问题", "查看澄清", "查看当前问题", "clarification status", "status"}
_CONTINUE_ALIASES = {"继续", "继续执行", "下一步", "resume", "continue", "next"}
_CANCEL_ALIASES = {"取消", "停止", "终止", "abort", "cancel", "stop"}
_GENERIC_NOUNS = {
    "问题",
    "功能",
    "模块",
    "代码",
    "逻辑",
    "东西",
    "内容",
    "部分",
    "处理",
    "改动",
    "方案",
    "task",
    "issue",
    "thing",
    "logic",
    "module",
    "feature",
    "change",
}
_DEMONSTRATIVES = {"这个", "那个", "这里", "那里", "这边", "那边", "it", "this", "that"}
_ACTION_WORDS = {
    "修复",
    "实现",
    "添加",
    "新增",
    "修改",
    "重构",
    "优化",
    "删除",
    "处理",
    "调整",
    "补",
    "补齐",
    "梳理",
    "接入",
    "fix",
    "implement",
    "add",
    "update",
    "refactor",
    "optimize",
    "remove",
    "adjust",
}
_TOKEN_SPLIT_RE = re.compile(r"[\s`'\"“”‘’.,:;!?(){}\[\]<>/\\|_+-]+")
_FILE_REF_RE = re.compile(r"(?:[\w.-]+/)+[\w.-]+|[\w.-]+\.(?:ts|tsx|js|jsx|py|md|json|yaml|yml|vue|rs|go)")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")


@dataclass(frozen=True)
class ClarificationResponse:
    """Normalized interpretation of a clarification reply."""

    action: str
    text: str = ""
    message: str = ""


def should_trigger_clarification(route: RouteDecision) -> bool:
    """Return True when the current planning route lacks minimal factual anchors."""
    if route.route_name not in _PLANNING_ROUTES:
        return False
    return bool(_missing_facts(route.request_text))


def build_clarification_state(route: RouteDecision, *, config: RuntimeConfig) -> ClarificationState | None:
    """Create a deterministic clarification packet from a planning request."""
    missing_facts = _missing_facts(route.request_text)
    if not missing_facts:
        return None

    created_at = iso_now()
    return ClarificationState(
        clarification_id=_clarification_id(route.request_text),
        feature_key=_feature_key(route.request_text),
        phase="analyze",
        status="pending",
        summary=_summary_for_language(config.language),
        questions=_questions_for_facts(missing_facts, language=config.language),
        missing_facts=tuple(missing_facts),
        context_files=_context_files(config),
        resume_route=route.route_name,
        request_text=route.request_text,
        requested_plan_level=route.plan_level,
        capture_mode=route.capture_mode,
        candidate_skill_ids=route.candidate_skill_ids,
        created_at=created_at,
        updated_at=created_at,
    )


def parse_clarification_response(clarification_state: ClarificationState, user_input: str) -> ClarificationResponse:
    """Interpret a raw user response against the current clarification packet."""
    text = user_input.strip()
    if not text:
        return ClarificationResponse(action="invalid", message="Empty clarification response")

    normalized = text.casefold()
    if normalized in {alias.casefold() for alias in _QUESTION_ALIASES | _CONTINUE_ALIASES}:
        return ClarificationResponse(action="status")
    if normalized in {alias.casefold() for alias in _CANCEL_ALIASES}:
        return ClarificationResponse(action="cancel")
    return ClarificationResponse(action="answer", text=text)


def has_submitted_clarification(clarification_state: ClarificationState) -> bool:
    """Return True when the host already wrote structured clarification answers."""
    return clarification_state.has_response


def merge_clarification_request(clarification_state: ClarificationState, response_text: str) -> str:
    """Merge the original planning request with user-provided clarification text."""
    original = clarification_state.request_text.strip()
    supplement = response_text.strip()
    if not original:
        return supplement
    return f"{original}\n\n补充信息:\n{supplement}"


def build_scope_clarification_form(clarification_state: ClarificationState, *, language: str) -> Mapping[str, Any]:
    """Build the lightweight host-facing scope-clarify form contract."""
    fields = [_field_for_missing_fact(fact, language=language) for fact in clarification_state.missing_facts]
    return {
        "template_id": SCOPE_CLARIFY_TEMPLATE_ID,
        "title": _form_text(language, "title"),
        "message": clarification_state.summary,
        "fields": fields,
        "text_fallback": {
            "allowed": True,
            "examples": list(_text_fallback_examples(language)),
        },
    }


def normalize_clarification_answers(
    clarification_state: ClarificationState,
    answers: Mapping[str, Any],
) -> Mapping[str, str]:
    """Validate and normalize structured clarification answers."""
    normalized: dict[str, str] = {}
    errors: list[str] = []
    for field in build_scope_clarification_form(clarification_state, language="en-US")["fields"]:
        field_id = str(field["field_id"])
        raw_value = answers.get(field_id)
        value = str(raw_value or "").strip()
        if not value:
            errors.append(f"{field_id}: required")
            continue
        normalized[field_id] = value
    if errors:
        raise ValueError("; ".join(errors))
    return normalized


def render_clarification_response_text(
    clarification_state: ClarificationState,
    *,
    answers: Mapping[str, Any],
    language: str,
) -> str:
    """Render normalized structured clarification answers back into resume text."""
    normalized = normalize_clarification_answers(clarification_state, answers)
    lines: list[str] = []
    if TARGET_SCOPE_FIELD_ID in normalized:
        lines.append(_form_text(language, "target_scope_line").format(value=normalized[TARGET_SCOPE_FIELD_ID]))
    if EXPECTED_OUTCOME_FIELD_ID in normalized:
        lines.append(_form_text(language, "expected_outcome_line").format(value=normalized[EXPECTED_OUTCOME_FIELD_ID]))
    return "\n".join(lines).strip()


def clarification_submission_state_payload(clarification_state: ClarificationState) -> Mapping[str, Any]:
    """Summarize whether the host already wrote structured clarification answers."""
    answer_keys = sorted(str(key) for key in clarification_state.response_fields.keys())
    payload: dict[str, Any] = {
        "status": "submitted" if clarification_state.has_response else "empty",
        "source": clarification_state.response_source,
        "submitted_at": clarification_state.response_submitted_at,
        "has_answers": bool(answer_keys),
        "answer_keys": answer_keys,
    }
    if clarification_state.response_message:
        payload["message"] = clarification_state.response_message
    return payload


def stale_clarification(clarification_state: ClarificationState) -> ClarificationState:
    """Return a stale copy when a pending clarification is superseded."""
    now = iso_now()
    return ClarificationState(
        clarification_id=clarification_state.clarification_id,
        feature_key=clarification_state.feature_key,
        phase=clarification_state.phase,
        status="stale",
        summary=clarification_state.summary,
        questions=clarification_state.questions,
        missing_facts=clarification_state.missing_facts,
        context_files=clarification_state.context_files,
        resume_route=clarification_state.resume_route,
        request_text=clarification_state.request_text,
        requested_plan_level=clarification_state.requested_plan_level,
        capture_mode=clarification_state.capture_mode,
        candidate_skill_ids=clarification_state.candidate_skill_ids,
        resume_context=clarification_state.resume_context,
        response_text=clarification_state.response_text,
        response_fields=clarification_state.response_fields,
        response_source=clarification_state.response_source,
        response_message=clarification_state.response_message,
        response_submitted_at=clarification_state.response_submitted_at,
        created_at=clarification_state.created_at,
        updated_at=now,
        answered_at=clarification_state.answered_at,
        consumed_at=clarification_state.consumed_at,
    )


def _missing_facts(request_text: str) -> tuple[str, ...]:
    text = request_text.strip()
    missing: list[str] = []
    if not _has_target_anchor(text):
        missing.append("target_scope")
    if _is_bodyless_command(text) or _is_generic_outcome(text):
        missing.append("expected_outcome")
    return tuple(dict.fromkeys(missing))


def _has_target_anchor(text: str) -> bool:
    if not text:
        return False
    if _FILE_REF_RE.search(text):
        return True
    lowered = text.casefold()
    if any(anchor in lowered for anchor in ("runtime", "router", "engine", "manifest", "handoff", "blueprint", "history", "bundle", "workspace")):
        return True
    tokens = _meaningful_tokens(text)
    return bool(tokens)


def _is_bodyless_command(text: str) -> bool:
    lowered = text.casefold()
    return lowered in {"~go", "~go plan", "~go exec"}


def _is_generic_outcome(text: str) -> bool:
    normalized = text.strip().casefold()
    if normalized in {word.casefold() for word in _ACTION_WORDS}:
        return True
    if normalized in {word.casefold() for word in _DEMONSTRATIVES | _GENERIC_NOUNS}:
        return True
    return bool(re.fullmatch(r"(?:帮我)?(?:优化|修改|处理|重构|实现|补齐|fix|implement|refactor|update)(?:一下|下)?", normalized))


def _meaningful_tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in _TOKEN_SPLIT_RE.split(text):
        candidate = _strip_action_affixes(token.strip())
        if not candidate:
            continue
        lowered = candidate.casefold()
        if lowered in {word.casefold() for word in _ACTION_WORDS | _GENERIC_NOUNS | _DEMONSTRATIVES}:
            continue
        if _CJK_RE.fullmatch(candidate) or len(lowered) >= 3:
            tokens.append(candidate)
    return tuple(tokens)


def _questions_for_facts(missing_facts: tuple[str, ...], *, language: str) -> tuple[str, ...]:
    if language == "en-US":
        mapping = {
            "target_scope": "Please name the concrete target: module, file, command entry, or workflow boundary.",
            "expected_outcome": "Please state the expected result: what should be planned, changed, or delivered after this round.",
        }
    else:
        mapping = {
            "target_scope": "请明确要改动的对象：模块、文件、命令入口或流程边界。",
            "expected_outcome": "请说明预期结果：这轮规划完成后，应该产出什么变化或交付物。",
        }
    return tuple(mapping[fact] for fact in missing_facts if fact in mapping)


def _strip_action_affixes(token: str) -> str:
    candidate = token
    for action in sorted(_ACTION_WORDS, key=len, reverse=True):
        if candidate.startswith(action):
            candidate = candidate[len(action):]
            break
    for suffix in ("一下", "一下子", "下", "一下吧"):
        if candidate.endswith(suffix):
            candidate = candidate[: -len(suffix)]
            break
    return candidate.strip()


def _summary_for_language(language: str) -> str:
    if language == "en-US":
        return "The current request is missing the minimum factual anchors needed for planning."
    return "当前请求缺少进入规划所需的最小事实信息。"


def _field_for_missing_fact(missing_fact: str, *, language: str) -> Mapping[str, Any]:
    if missing_fact == "target_scope":
        return {
            "field_id": TARGET_SCOPE_FIELD_ID,
            "field_type": "input",
            "label": _form_text(language, "target_scope_label"),
            "description": _form_text(language, "target_scope_description"),
            "required": True,
            "multiline": False,
        }
    return {
        "field_id": EXPECTED_OUTCOME_FIELD_ID,
        "field_type": "textarea",
        "label": _form_text(language, "expected_outcome_label"),
        "description": _form_text(language, "expected_outcome_description"),
        "required": True,
        "multiline": True,
    }


def _text_fallback_examples(language: str) -> tuple[str, ...]:
    if language == "en-US":
        return (
            "Target scope: runtime/router.py\nExpected outcome: add a structured clarification bridge contract.",
        )
    return (
        "目标范围：runtime/router.py\n预期结果：补一个结构化 clarification bridge 契约。",
    )


def _form_text(language: str, key: str) -> str:
    locale = "en-US" if language == "en-US" else "zh-CN"
    messages = {
        "zh-CN": {
            "title": "补充规划所需信息",
            "target_scope_label": "目标范围",
            "target_scope_description": "请写明模块、文件、命令入口或流程边界。",
            "expected_outcome_label": "预期结果",
            "expected_outcome_description": "请写明这轮规划结束后应产出的变化或交付物。",
            "target_scope_line": "目标范围：{value}",
            "expected_outcome_line": "预期结果：{value}",
        },
        "en-US": {
            "title": "Provide the missing planning facts",
            "target_scope_label": "Target scope",
            "target_scope_description": "Name the module, file, command entry, or workflow boundary.",
            "expected_outcome_label": "Expected outcome",
            "expected_outcome_description": "State what this planning round should produce or change.",
            "target_scope_line": "Target scope: {value}",
            "expected_outcome_line": "Expected outcome: {value}",
        },
    }
    return messages[locale][key]


def _clarification_id(request_text: str) -> str:
    return f"clarify-{sha1(request_text.encode('utf-8')).hexdigest()[:8]}"


def _feature_key(request_text: str) -> str:
    digest = sha1(request_text.encode("utf-8")).hexdigest()[:8]
    return f"clarification-{digest}"


def _context_files(config: RuntimeConfig) -> tuple[str, ...]:
    candidates = (
        config.runtime_root / "blueprint" / "README.md",
        config.runtime_root / "blueprint" / "tasks.md",
        config.runtime_root / "project.md",
    )
    return tuple(
        str(path.relative_to(config.workspace_root))
        for path in candidates
        if path.exists()
    )


def iso_now() -> str:
    """Return a stable UTC timestamp without importing the state module."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
