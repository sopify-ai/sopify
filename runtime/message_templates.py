"""Host-facing message template selection and safe rendering."""

from __future__ import annotations

from copy import deepcopy
from string import Formatter
from typing import Any, Mapping


MESSAGE_TEMPLATE_RENDER_FAILED = "message_template_render_failed"
SAFE_FALLBACK_MESSAGES = {
    "zh-CN": "当前动作已识别，但暂时不能安全继续；请修复契约或补充更明确输入后重试。",
    "en-US": "The action was identified, but it still cannot continue safely. Fix the contract or provide a more explicit input and retry.",
}

_FORMATTER = Formatter()


class MessageTemplateError(ValueError):
    """Raised when a message template contract is malformed at call time."""


def load_default_host_message_templates(
    *,
    decision_tables_path: str | None = None,
    schema_path: str | None = None,
) -> dict[str, Any]:
    """Load the repository-default host-facing template contract."""

    from .decision_tables import load_decision_tables, load_default_decision_tables

    if decision_tables_path is not None:
        tables = load_decision_tables(decision_tables_path, schema_path=schema_path)
    else:
        tables = load_default_decision_tables(schema_path=schema_path)
    return deepcopy(tables["host_message_templates"])


def render_host_message(
    *,
    reason_code: str,
    prompt_mode: str,
    variables: Mapping[str, Any] | None = None,
    locale: str | None = None,
    templates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Render a host-facing message with frozen lookup order and safe fallback."""

    if templates is None:
        templates = load_default_host_message_templates()
    if not isinstance(templates, Mapping):
        raise MessageTemplateError("templates must be a mapping")

    template_contract = dict(templates)
    template_rows = template_contract.get("templates")
    fallback_map = template_contract.get("prompt_mode_fallbacks")
    default_locale = template_contract.get("default_locale")
    lookup_order = template_contract.get("lookup_order")
    allowed_variables = template_contract.get("allowed_variables")
    if not isinstance(template_rows, list) or not isinstance(fallback_map, Mapping):
        raise MessageTemplateError("templates contract is missing templates or prompt_mode_fallbacks")
    if not isinstance(default_locale, str) or not default_locale.strip():
        raise MessageTemplateError("templates.default_locale must be a non-empty string")
    if not isinstance(lookup_order, list) or not lookup_order:
        raise MessageTemplateError("templates.lookup_order must be a non-empty list")
    if not isinstance(allowed_variables, list):
        raise MessageTemplateError("templates.allowed_variables must be a list")

    render_variables = dict(variables or {})
    resolved_locale = _resolve_locale(locale, templates=template_contract, default_locale=default_locale)
    selected = _select_template(
        reason_code=reason_code,
        prompt_mode=prompt_mode,
        locale=resolved_locale,
        templates=template_rows,
        fallback_map=fallback_map,
        lookup_order=lookup_order,
        default_locale=default_locale,
    )
    rendered = _render_template_text(
        selected["text"],
        variables=render_variables,
        allowed_variables=allowed_variables,
    )
    render_events: list[str] = []
    source_kind = selected["source_kind"]
    match_value = selected["match_value"]

    if rendered is None:
        render_events.append(MESSAGE_TEMPLATE_RENDER_FAILED)
        fallback_selected = _select_prompt_mode_fallback(
            prompt_mode=prompt_mode,
            locale=resolved_locale,
            fallback_map=fallback_map,
            default_locale=default_locale,
        )
        fallback_rendered = _render_template_text(
            fallback_selected["text"],
            variables=render_variables,
            allowed_variables=allowed_variables,
        )
        if fallback_rendered is not None:
            rendered = fallback_rendered
            source_kind = fallback_selected["source_kind"]
            match_value = fallback_selected["match_value"]
        else:
            source_kind = "safe_fallback"
            match_value = prompt_mode
            rendered = SAFE_FALLBACK_MESSAGES.get(
                resolved_locale,
                SAFE_FALLBACK_MESSAGES.get(default_locale, next(iter(SAFE_FALLBACK_MESSAGES.values()))),
            )

    return {
        "text": rendered,
        "locale": resolved_locale,
        "source_kind": source_kind,
        "match_value": match_value,
        "render_events": render_events,
    }


def _resolve_locale(
    locale: str | None,
    *,
    templates: Mapping[str, Any],
    default_locale: str,
) -> str:
    if locale is None:
        return default_locale
    prompt_mode_fallbacks = templates.get("prompt_mode_fallbacks")
    if not isinstance(prompt_mode_fallbacks, Mapping):
        return default_locale
    for localized_text in prompt_mode_fallbacks.values():
        if isinstance(localized_text, Mapping) and locale in localized_text:
            return locale
    return default_locale


def _select_template(
    *,
    reason_code: str,
    prompt_mode: str,
    locale: str,
    templates: list[Any],
    fallback_map: Mapping[str, Any],
    lookup_order: list[Any],
    default_locale: str,
) -> dict[str, str]:
    for lookup_kind in lookup_order:
        if lookup_kind == "exact_reason_code":
            for template in templates:
                if not isinstance(template, Mapping):
                    continue
                if (
                    template.get("match_kind") == "exact_reason_code"
                    and template.get("match_value") == reason_code
                    and prompt_mode in template.get("prompt_modes", ())
                ):
                    return {
                        "text": _select_locale_text(template.get("locales"), locale, default_locale),
                        "source_kind": "exact_reason_code",
                        "match_value": str(template.get("match_value")),
                    }
        elif lookup_kind == "reason_code_family_prefix":
            prefix_matches: list[Mapping[str, Any]] = []
            for template in templates:
                if not isinstance(template, Mapping):
                    continue
                match_value = template.get("match_value")
                if (
                    template.get("match_kind") == "reason_code_family_prefix"
                    and isinstance(match_value, str)
                    and reason_code.startswith(match_value)
                    and prompt_mode in template.get("prompt_modes", ())
                ):
                    prefix_matches.append(template)
            if prefix_matches:
                chosen = max(prefix_matches, key=lambda item: len(str(item.get("match_value", ""))))
                return {
                    "text": _select_locale_text(chosen.get("locales"), locale, default_locale),
                    "source_kind": "reason_code_family_prefix",
                    "match_value": str(chosen.get("match_value")),
                }
        elif lookup_kind == "prompt_mode_fallback":
            return _select_prompt_mode_fallback(
                prompt_mode=prompt_mode,
                locale=locale,
                fallback_map=fallback_map,
                default_locale=default_locale,
            )

    return _select_prompt_mode_fallback(
        prompt_mode=prompt_mode,
        locale=locale,
        fallback_map=fallback_map,
        default_locale=default_locale,
    )


def _select_prompt_mode_fallback(
    *,
    prompt_mode: str,
    locale: str,
    fallback_map: Mapping[str, Any],
    default_locale: str,
) -> dict[str, str]:
    localized = fallback_map.get(prompt_mode)
    return {
        "text": _select_locale_text(localized, locale, default_locale),
        "source_kind": "prompt_mode_fallback",
        "match_value": prompt_mode,
    }


def _select_locale_text(value: Any, locale: str, default_locale: str) -> str:
    if isinstance(value, Mapping):
        candidate = value.get(locale)
        if isinstance(candidate, str) and candidate.strip():
            return candidate
        default_candidate = value.get(default_locale)
        if isinstance(default_candidate, str) and default_candidate.strip():
            return default_candidate
    return SAFE_FALLBACK_MESSAGES.get(
        locale,
        SAFE_FALLBACK_MESSAGES.get(default_locale, next(iter(SAFE_FALLBACK_MESSAGES.values()))),
    )


def _render_template_text(
    template: str,
    *,
    variables: Mapping[str, Any],
    allowed_variables: list[Any],
) -> str | None:
    try:
        required_fields = _collect_required_fields(template, allowed_variables=allowed_variables)
    except ValueError:
        return None
    missing_fields = [
        field_name
        for field_name in required_fields
        if field_name not in variables or variables[field_name] is None
    ]
    if missing_fields:
        return None
    try:
        return template.format_map({field: variables[field] for field in required_fields})
    except (KeyError, ValueError):
        return None


def _collect_required_fields(template: str, *, allowed_variables: list[Any]) -> list[str]:
    required_fields: list[str] = []
    allowed = {item for item in allowed_variables if isinstance(item, str)}
    for _, field_name, format_spec, conversion in _FORMATTER.parse(template):
        if field_name is None:
            continue
        if conversion is not None or format_spec:
            raise ValueError("format conversion and format specifiers are not supported")
        if field_name not in allowed:
            raise ValueError(f"unsupported placeholder: {field_name}")
        if field_name not in required_fields:
            required_fields.append(field_name)
    return required_fields
