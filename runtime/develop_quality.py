"""Structured quality-loop contracts shared by develop runtime surfaces.

The host still owns real code changes during `continue_host_develop`, but the
quality loop needs a stable machine-readable contract so handoff, replay, and
checkpoint callbacks can agree on the same fields and value domains.
"""

from __future__ import annotations

from typing import Any, Mapping

DEVELOP_QUALITY_SCHEMA_VERSION = "1"
DEVELOP_QUALITY_CONTEXT_FIELDS = (
    "task_refs",
    "changed_files",
    "working_summary",
    "verification_todo",
)
DEVELOP_VERIFICATION_SOURCES = (
    "project_contract",
    "project_native",
    "not_configured",
)
DEVELOP_VERIFICATION_RESULTS = (
    "passed",
    "retried",
    "failed",
    "skipped",
    "replan_required",
)
DEVELOP_ROOT_CAUSES = (
    "logic_regression",
    "environment_or_dependency",
    "missing_test_infra",
    "scope_or_design_mismatch",
)
DEVELOP_REVIEW_STAGES = (
    "spec_compliance",
    "code_quality",
)
DEVELOP_REVIEW_STATUSES = (
    "passed",
    "failed",
    "not_run",
)
DEVELOP_CALLBACK_TRIGGER_RESULTS = ("replan_required",)
DEVELOP_CALLBACK_TRIGGER_ROOT_CAUSES = ("scope_or_design_mismatch",)


class DevelopQualityError(ValueError):
    """Raised when a develop quality payload violates the stable contract."""


def build_develop_quality_contract() -> dict[str, Any]:
    """Return the stable host-visible quality-loop contract for develop flows."""
    return {
        "schema_version": DEVELOP_QUALITY_SCHEMA_VERSION,
        "verification_discovery_order": list(DEVELOP_VERIFICATION_SOURCES),
        "verification_sources": list(DEVELOP_VERIFICATION_SOURCES),
        "result_values": list(DEVELOP_VERIFICATION_RESULTS),
        "root_cause_values": list(DEVELOP_ROOT_CAUSES),
        "review_stages": list(DEVELOP_REVIEW_STAGES),
        "review_status_values": list(DEVELOP_REVIEW_STATUSES),
        "max_retry_count": 1,
        "required_quality_fields": [
            "verification_source",
            "command",
            "scope",
            "result",
            "reason_code",
            "retry_count",
            "root_cause",
            "review_result",
        ],
        "required_context_fields": list(DEVELOP_QUALITY_CONTEXT_FIELDS),
        "checkpoint_trigger": {
            "result_values": list(DEVELOP_CALLBACK_TRIGGER_RESULTS),
            "root_cause_values": list(DEVELOP_CALLBACK_TRIGGER_ROOT_CAUSES),
            "required_helper": "develop_callback",
        },
    }


def normalize_develop_quality_context(raw_context: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the durable context paired with a develop quality result."""
    if not isinstance(raw_context, Mapping):
        raise DevelopQualityError("develop quality context must be an object")

    task_refs = list(_normalize_string_list(raw_context.get("task_refs")))
    changed_files = list(_normalize_string_list(raw_context.get("changed_files")))
    verification_todo = list(_normalize_string_list(raw_context.get("verification_todo")))
    working_summary = str(raw_context.get("working_summary") or "").strip()
    if not task_refs:
        raise DevelopQualityError("develop quality context.task_refs must contain at least one task reference")
    if not working_summary:
        raise DevelopQualityError("develop quality context.working_summary is required")

    return {
        "task_refs": task_refs,
        "changed_files": changed_files,
        "working_summary": working_summary,
        "verification_todo": verification_todo,
    }


def normalize_develop_quality_result(raw_result: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a task-level develop quality result."""
    if not isinstance(raw_result, Mapping):
        raise DevelopQualityError("develop quality result must be an object")

    schema_version = str(raw_result.get("schema_version") or DEVELOP_QUALITY_SCHEMA_VERSION).strip()
    if schema_version != DEVELOP_QUALITY_SCHEMA_VERSION:
        raise DevelopQualityError(
            f"unsupported develop quality schema_version: {schema_version or '<missing>'}"
        )

    verification_source = _normalize_keyword(
        raw_result.get("verification_source"),
        allowed=DEVELOP_VERIFICATION_SOURCES,
        field_name="verification_source",
    )
    command = str(raw_result.get("command") or "").strip()
    scope = str(raw_result.get("scope") or "").strip()
    if not scope:
        raise DevelopQualityError("develop quality result.scope is required")

    result = _normalize_keyword(
        raw_result.get("result"),
        allowed=DEVELOP_VERIFICATION_RESULTS,
        field_name="result",
    )
    reason_code = str(raw_result.get("reason_code") or "").strip()
    retry_count = _normalize_retry_count(raw_result.get("retry_count"))
    raw_root_cause = str(raw_result.get("root_cause") or "").strip()
    root_cause = ""
    if raw_root_cause:
        root_cause = _normalize_keyword(
            raw_root_cause,
            allowed=DEVELOP_ROOT_CAUSES,
            field_name="root_cause",
        )

    review_result = normalize_develop_review_result(raw_result.get("review_result"))

    if not command and verification_source != "not_configured":
        raise DevelopQualityError(
            "develop quality result.command is required unless verification_source == not_configured"
        )
    if verification_source == "not_configured" and result not in {"skipped", "replan_required"}:
        raise DevelopQualityError(
            "develop quality result.not_configured may only produce skipped or replan_required"
        )
    if result == "passed" and retry_count != 0:
        raise DevelopQualityError("develop quality result.passed must use retry_count == 0")
    if result == "retried" and retry_count != 1:
        raise DevelopQualityError("develop quality result.retried must use retry_count == 1")
    if retry_count == 1 and result not in {"retried", "failed", "replan_required"}:
        raise DevelopQualityError(
            "develop quality retry_count == 1 is only allowed for retried, failed, or replan_required"
        )
    if result in {"skipped", "replan_required"} and not reason_code:
        raise DevelopQualityError(
            "develop quality result.reason_code is required for skipped and replan_required states"
        )
    if verification_source == "not_configured" and not reason_code:
        raise DevelopQualityError(
            "develop quality result.reason_code is required when verification_source == not_configured"
        )
    if result in {"retried", "failed", "replan_required"} and not root_cause:
        raise DevelopQualityError(
            "develop quality result.root_cause is required for retried, failed, and replan_required"
        )
    if root_cause == "scope_or_design_mismatch" and result != "replan_required":
        raise DevelopQualityError(
            "develop quality root_cause scope_or_design_mismatch must use result == replan_required"
        )
    if result == "replan_required" and root_cause != "scope_or_design_mismatch":
        raise DevelopQualityError(
            "develop quality result.replan_required must use root_cause == scope_or_design_mismatch"
        )

    spec_status = review_result["spec_compliance"]["status"]
    code_status = review_result["code_quality"]["status"]
    if result in {"passed", "retried"} and (spec_status != "passed" or code_status != "passed"):
        raise DevelopQualityError(
            "develop quality passed/retried results require spec_compliance and code_quality to both pass"
        )
    if "failed" in {spec_status, code_status} and result in {"passed", "retried", "skipped"}:
        raise DevelopQualityError(
            "develop quality review failures must surface as failed or replan_required"
        )

    normalized = {
        "schema_version": DEVELOP_QUALITY_SCHEMA_VERSION,
        "verification_source": verification_source,
        "command": command,
        "scope": scope,
        "result": result,
        "reason_code": reason_code,
        "retry_count": retry_count,
        "root_cause": root_cause,
        "review_result": review_result,
    }
    notes = str(raw_result.get("notes") or "").strip()
    if notes:
        normalized["notes"] = notes
    return normalized


def normalize_develop_review_result(raw_review: Any) -> dict[str, dict[str, str]]:
    """Normalize the two-stage review payload embedded in a quality result."""
    if not isinstance(raw_review, Mapping):
        raise DevelopQualityError("develop quality result.review_result must be an object")

    normalized: dict[str, dict[str, str]] = {}
    unknown_stages = [
        str(stage).strip()
        for stage in raw_review.keys()
        if str(stage).strip() and str(stage).strip() not in DEVELOP_REVIEW_STAGES
    ]
    if unknown_stages:
        raise DevelopQualityError(
            f"develop quality review_result contains unsupported stages: {', '.join(sorted(unknown_stages))}"
        )

    for stage in DEVELOP_REVIEW_STAGES:
        if stage not in raw_review:
            raise DevelopQualityError(f"develop quality review_result.{stage} is required")
        value = raw_review.get(stage)
        if isinstance(value, str):
            status = _normalize_keyword(value, allowed=DEVELOP_REVIEW_STATUSES, field_name=f"review_result.{stage}")
            normalized[stage] = {"status": status, "summary": ""}
            continue
        if not isinstance(value, Mapping):
            raise DevelopQualityError(f"develop quality review_result.{stage} must be a string or object")
        status = _normalize_keyword(
            value.get("status"),
            allowed=DEVELOP_REVIEW_STATUSES,
            field_name=f"review_result.{stage}.status",
        )
        normalized[stage] = {
            "status": status,
            "summary": str(value.get("summary") or "").strip(),
        }
    return normalized


def requires_develop_callback(quality_result: Mapping[str, Any]) -> bool:
    """Return True when a quality result must route back through a checkpoint."""
    result = str(quality_result.get("result") or "").strip()
    root_cause = str(quality_result.get("root_cause") or "").strip()
    return (
        result in DEVELOP_CALLBACK_TRIGGER_RESULTS
        or root_cause in DEVELOP_CALLBACK_TRIGGER_ROOT_CAUSES
    )


def attach_develop_quality_artifacts(
    artifacts: dict[str, Any],
    *,
    quality_result: Mapping[str, Any],
    quality_context: Mapping[str, Any] | None = None,
) -> None:
    """Attach the stable develop quality summary onto handoff-like artifacts."""
    normalized_result = normalize_develop_quality_result(quality_result)
    normalized_context = (
        normalize_develop_quality_context(quality_context)
        if isinstance(quality_context, Mapping) and quality_context
        else None
    )

    artifacts["develop_quality_result"] = normalized_result
    for key in (
        "verification_source",
        "command",
        "scope",
        "result",
        "reason_code",
        "retry_count",
        "root_cause",
        "review_result",
    ):
        artifacts[key] = normalized_result[key]

    if "notes" in normalized_result:
        artifacts["quality_notes"] = normalized_result["notes"]

    if normalized_context is not None:
        artifacts["task_refs"] = list(normalized_context["task_refs"])
        artifacts["changed_files"] = list(normalized_context["changed_files"])
        artifacts["working_summary"] = normalized_context["working_summary"]
        artifacts["verification_todo"] = list(normalized_context["verification_todo"])


def carry_forward_develop_quality_artifacts(
    artifacts: dict[str, Any],
    *,
    source: Mapping[str, Any] | None,
) -> None:
    """Carry forward the last stable develop quality summary when present."""
    if not isinstance(source, Mapping):
        return
    quality_result = extract_develop_quality_result(source)
    if quality_result is None:
        return
    quality_context = extract_develop_quality_context(source)
    attach_develop_quality_artifacts(
        artifacts,
        quality_result=quality_result,
        quality_context=quality_context,
    )


def extract_develop_quality_result(source: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Best-effort extraction of a develop quality result from nested or flat artifacts."""
    if not isinstance(source, Mapping):
        return None
    candidate = source.get("develop_quality_result")
    if isinstance(candidate, Mapping):
        try:
            return normalize_develop_quality_result(candidate)
        except DevelopQualityError:
            return None

    required_keys = {
        "verification_source",
        "command",
        "scope",
        "result",
        "retry_count",
        "review_result",
    }
    if not required_keys.issubset(source.keys()):
        return None
    try:
        return normalize_develop_quality_result(
            {
                "schema_version": source.get("schema_version") or DEVELOP_QUALITY_SCHEMA_VERSION,
                "verification_source": source.get("verification_source"),
                "command": source.get("command"),
                "scope": source.get("scope"),
                "result": source.get("result"),
                "reason_code": source.get("reason_code"),
                "retry_count": source.get("retry_count"),
                "root_cause": source.get("root_cause"),
                "review_result": source.get("review_result"),
                "notes": source.get("quality_notes") or source.get("notes"),
            }
        )
    except DevelopQualityError:
        return None


def extract_develop_quality_context(source: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Best-effort extraction of develop quality context from nested or flat artifacts."""
    if not isinstance(source, Mapping):
        return None
    candidate = source.get("develop_quality_context")
    if isinstance(candidate, Mapping):
        try:
            return normalize_develop_quality_context(candidate)
        except DevelopQualityError:
            return None

    context_payload = {
        "task_refs": source.get("task_refs"),
        "changed_files": source.get("changed_files"),
        "working_summary": source.get("working_summary"),
        "verification_todo": source.get("verification_todo"),
    }
    if not any(context_payload.values()):
        return None
    try:
        return normalize_develop_quality_context(context_payload)
    except DevelopQualityError:
        return None


def _normalize_string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _normalize_retry_count(value: Any) -> int:
    try:
        retry_count = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise DevelopQualityError("develop quality result.retry_count must be an integer") from exc
    if retry_count not in {0, 1}:
        raise DevelopQualityError("develop quality result.retry_count must be 0 or 1")
    return retry_count


def _normalize_keyword(value: Any, *, allowed: tuple[str, ...], field_name: str) -> str:
    normalized = str(value or "").strip().casefold().replace("-", "_")
    for candidate in allowed:
        if normalized == candidate.casefold():
            return candidate
    allowed_text = ", ".join(allowed)
    raise DevelopQualityError(
        f"unsupported develop quality {field_name}: {value or '<missing>'}; allowed: {allowed_text}"
    )
