"""Shared cancel-intent parsing for pending checkpoint prompts."""

from __future__ import annotations

import re
from typing import Collection

_NEGATED_CANCEL_HEAD_RE = re.compile(
    r"^(?:不要|先不要|别|先别|暂不)\s*(?:取消|停止|终止)|^(?:do\s*not|don't|dont|not)\s+(?:cancel|stop|abort)",
    re.IGNORECASE,
)
_CANCEL_PREFIXES = ("", "请", "麻烦", "帮我", "请你", "please ", "pls ")
_CANCEL_TAIL_SEPARATORS_RE = re.compile(r"^[\s`'\"“”‘’(){}\[\]<>/\\|_-]+")
_CANCEL_TAIL_TOKENS = ("checkpoint", "这个", "this", "一下吧", "一下", "please", "pls", "此", "吧")
_CANCEL_COMMA_SUCCESS_BOUNDARY_CHARS = ",，"
_CANCEL_TERMINAL_SUCCESS_BOUNDARY_CHARS = "!！…"
_CANCEL_CONDITIONAL_SUCCESS_BOUNDARY_CHARS = ".。;；:："
_CANCEL_FAIL_CLOSED_BOUNDARY_CHARS = "?？"


def is_checkpoint_cancel_intent(text: str, *, cancel_aliases: Collection[str]) -> bool:
    """Return True only for explicit, locally scoped cancel commands."""
    stripped = str(text or "").strip()
    if not stripped:
        return False
    normalized = stripped.casefold()
    normalized_aliases = {str(alias).casefold() for alias in cancel_aliases}
    if normalized in normalized_aliases:
        return True
    for prefix in _CANCEL_PREFIXES:
        prefix_cf = prefix.casefold()
        if prefix_cf and not normalized.startswith(prefix_cf):
            continue
        remainder = normalized[len(prefix_cf):]
        if _NEGATED_CANCEL_HEAD_RE.match(remainder):
            return False
        for alias in sorted(normalized_aliases, key=len, reverse=True):
            if not remainder.startswith(alias):
                continue
            if _matches_cancel_tail(remainder[len(alias):]):
                return True
    return False


def _matches_cancel_tail(tail: str) -> bool:
    remainder = tail.casefold()
    while remainder:
        if remainder[0] in _CANCEL_FAIL_CLOSED_BOUNDARY_CHARS:
            return False
        if remainder[0] in _CANCEL_COMMA_SUCCESS_BOUNDARY_CHARS or remainder[0] in _CANCEL_TERMINAL_SUCCESS_BOUNDARY_CHARS:
            return True
        if remainder[0] in _CANCEL_CONDITIONAL_SUCCESS_BOUNDARY_CHARS:
            return _conditional_boundary_allows_cancel(remainder[1:])
        separator_match = _CANCEL_TAIL_SEPARATORS_RE.match(remainder)
        if separator_match is not None:
            remainder = remainder[separator_match.end():]
            if not remainder:
                return True
            if remainder[0] in _CANCEL_FAIL_CLOSED_BOUNDARY_CHARS:
                return False
            if remainder[0] in _CANCEL_COMMA_SUCCESS_BOUNDARY_CHARS or remainder[0] in _CANCEL_TERMINAL_SUCCESS_BOUNDARY_CHARS:
                return True
            if remainder[0] in _CANCEL_CONDITIONAL_SUCCESS_BOUNDARY_CHARS:
                return _conditional_boundary_allows_cancel(remainder[1:])
            continue
        matched_token = next((token for token in _CANCEL_TAIL_TOKENS if remainder.startswith(token)), None)
        if matched_token is None:
            return False
        remainder = remainder[len(matched_token):]
    return True


def _conditional_boundary_allows_cancel(remainder: str) -> bool:
    trailing = remainder.casefold()
    while trailing:
        separator_match = _CANCEL_TAIL_SEPARATORS_RE.match(trailing)
        if separator_match is None:
            return False
        trailing = trailing[separator_match.end():]
    return True
