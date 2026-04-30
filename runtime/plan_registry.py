"""Plan registry governance layer for multi-plan observation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any, Mapping, Sequence

from ._yaml import YamlParseError, load_yaml
from .models import PlanArtifact, RuntimeConfig
from .state import StateStore, iso_now

REGISTRY_FILENAME = "_registry.yaml"
REGISTRY_VERSION = 1
REGISTRY_MODE = "observe_only"
REGISTRY_SELECTION_POLICY = "explicit_only"
REGISTRY_PRIORITY_POLICY = "heuristic_v1"
REGISTRY_PRIORITY_FALLBACK = "p2"

_SUPPORTED_PLAN_LEVELS = {"light", "standard", "full"}
_SUPPORTED_LIFECYCLE_STATES = {"active", "ready_for_verify", "archived"}
_FRONT_MATTER_RE = re.compile(r"\A---\n(?P<front>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
_TITLE_PREFIX_RE = re.compile(
    r"^(?:任务清单|技术设计|变更提案|Task List|Technical Design|Change Proposal)\s*[:：]\s*",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_PRIORITY_ORDER = {"p1": 1, "p2": 2, "p3": 3}
_PRIORITY_NOTE_EVENT_PREFIX = "__plan_registry_priority_note__:"
_URGENT_PATTERNS = (
    re.compile(r"(紧急|阻塞|必须今天|今天必须|先做|优先|马上|立即)"),
    re.compile(r"\b(urgent|blocker|blocking|asap|must\s+today|priority)\b", re.IGNORECASE),
)


class PlanRegistryError(RuntimeError):
    """Raised when the registry cannot be read or written safely."""


@dataclass(frozen=True)
class PlanRegistryReadResult:
    """Registry payload plus read-time drift diagnostics."""

    payload: Mapping[str, Any]
    drift_notice: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class PlanRegistryEntryResult:
    """Single registry entry view plus read-time drift diagnostics."""

    entry: Mapping[str, Any] | None
    drift_notice: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanRegistryRecommendation:
    """Read-only plan ranking suggestion."""

    plan_id: str
    path: str
    title: str
    status: str
    is_current_plan: bool
    effective_priority: str
    priority_source: str
    confirmed_priority: str | None
    suggested_priority: str | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "path": self.path,
            "title": self.title,
            "status": self.status,
            "is_current_plan": self.is_current_plan,
            "effective_priority": self.effective_priority,
            "priority_source": self.priority_source,
            "confirmed_priority": self.confirmed_priority,
            "suggested_priority": self.suggested_priority,
            "reasons": list(self.reasons),
        }


def encode_priority_note_event(note: str) -> str:
    """Attach a stable machine tag so renderers do not depend on localized prefixes."""
    return f"{_PRIORITY_NOTE_EVENT_PREFIX}{note}"


def extract_priority_note_event(note: str) -> str | None:
    """Return the user-facing priority note from a tagged runtime note."""
    if not note.startswith(_PRIORITY_NOTE_EVENT_PREFIX):
        return None
    payload = note[len(_PRIORITY_NOTE_EVENT_PREFIX) :].strip()
    return payload or None


def inspect_plan_registry(
    *,
    config: RuntimeConfig,
    plan_id: str | None = None,
    request_text: str = "",
) -> dict[str, Any]:
    """Build a host-facing inspect contract for the plan registry."""
    read_result = read_plan_registry(
        config,
        reconcile=True,
        refresh_advice=True,
        request_text=request_text,
        create_if_missing=True,
        backfill_if_missing=True,
    )
    current_plan = StateStore(config).get_current_plan()
    recommendations = recommend_plan_candidates(
        config=config,
        request_text=request_text,
    )
    selected_entry = None
    if plan_id is not None:
        selected_entry = _entry_by_plan_id(read_result.payload.get("plans") or (), plan_id)
        if selected_entry is None:
            raise PlanRegistryError(f"Unknown plan_id: {plan_id}")

    return {
        "status": "ready",
        "registry_path": registry_relative_path(config),
        "current_plan": current_plan.to_dict() if current_plan is not None else None,
        "registry": _clone_registry(read_result.payload),
        "drift_notice": {key: list(value) for key, value in read_result.drift_notice.items()},
        "recommendations": [item.to_dict() for item in recommendations],
        "selected_plan": selected_entry,
        "execution_truth": {
            "current_plan_is_machine_truth": True,
            "registry_is_observe_only": True,
        },
    }


def registry_path(config: RuntimeConfig) -> Path:
    """Return the absolute registry path."""
    return config.plan_root / REGISTRY_FILENAME


def registry_relative_path(config: RuntimeConfig) -> str:
    """Return the workspace-relative registry path."""
    return str(registry_path(config).relative_to(config.workspace_root))


def read_plan_registry(
    config: RuntimeConfig,
    *,
    reconcile: bool = False,
    refresh_advice: bool = False,
    request_text: str = "",
    create_if_missing: bool = False,
    backfill_if_missing: bool = False,
) -> PlanRegistryReadResult:
    """Read the registry and optionally reconcile deterministic fields."""
    try:
        path = registry_path(config)
        if not path.exists():
            payload = _empty_registry()
            if create_if_missing:
                if backfill_if_missing:
                    payload, _ = _backfill_missing_entries(payload, config=config, request_text=request_text)
                _write_registry(path, payload)
            return PlanRegistryReadResult(payload=payload, drift_notice={})

        payload = _read_registry(path)
        drift_notice: dict[str, tuple[str, ...]] = {}
        changed = False

        if reconcile:
            payload, drift_notice, reconcile_changed = _reconcile_snapshot_fields(payload, config=config)
            changed = changed or reconcile_changed
        if refresh_advice:
            payload, refresh_changed = _refresh_advice_fields(payload, config=config, request_text=request_text)
            changed = changed or refresh_changed

        if changed:
            _write_registry(path, payload)

        return PlanRegistryReadResult(payload=payload, drift_notice=drift_notice)
    except (OSError, YamlParseError, ValueError) as exc:
        raise PlanRegistryError(str(exc)) from exc


def upsert_plan_entry(
    *,
    config: RuntimeConfig,
    artifact: PlanArtifact,
    request_text: str = "",
    source: str = "runtime_auto",
) -> Mapping[str, Any]:
    """Upsert one plan entry after create/archive-adjacent events."""
    try:
        read_result = read_plan_registry(
            config,
            create_if_missing=True,
            backfill_if_missing=True,
        )
        payload = _clone_registry(read_result.payload)
        entry = _build_entry(
            artifact=artifact,
            config=config,
            existing_entries=tuple(payload.get("plans") or ()),
            request_text=request_text,
            existing_entry=_entry_by_plan_id(payload.get("plans") or (), artifact.plan_id),
            source=source,
        )
        payload["plans"] = _replace_entry(payload.get("plans") or (), entry)
        _write_registry(registry_path(config), payload)
        return entry
    except (OSError, YamlParseError, ValueError) as exc:
        raise PlanRegistryError(str(exc)) from exc


def remove_plan_entry(*, config: RuntimeConfig, plan_id: str) -> bool:
    """Remove one active entry after archive succeeds."""
    try:
        path = registry_path(config)
        if not path.exists():
            return False
        payload = _read_registry(path)
        plans = list(payload.get("plans") or ())
        filtered = [entry for entry in plans if str(entry.get("plan_id") or "") != plan_id]
        if len(filtered) == len(plans):
            return False
        payload["plans"] = filtered
        _write_registry(path, payload)
        return True
    except (OSError, YamlParseError, ValueError) as exc:
        raise PlanRegistryError(str(exc)) from exc


def get_plan_entry(
    *,
    config: RuntimeConfig,
    plan_id: str,
    reconcile: bool = False,
    refresh_advice: bool = False,
    request_text: str = "",
) -> PlanRegistryEntryResult:
    """Read one entry by plan id."""
    read_result = read_plan_registry(
        config,
        reconcile=reconcile,
        refresh_advice=refresh_advice,
        request_text=request_text,
    )
    entry = _entry_by_plan_id(read_result.payload.get("plans") or (), plan_id)
    return PlanRegistryEntryResult(
        entry=entry,
        drift_notice=tuple(read_result.drift_notice.get(plan_id) or ()),
    )


def confirm_plan_priority(
    *,
    config: RuntimeConfig,
    plan_id: str,
    priority: str,
    note: str | None = None,
) -> Mapping[str, Any]:
    """Persist a user-confirmed final priority without changing advice."""
    normalized_priority = _normalize_priority_value(priority) or REGISTRY_PRIORITY_FALLBACK
    try:
        path = registry_path(config)
        read_result = read_plan_registry(
            config,
            create_if_missing=True,
            backfill_if_missing=True,
            reconcile=True,
        )
        payload = _clone_registry(read_result.payload)
        entry = _entry_by_plan_id(payload.get("plans") or (), plan_id)
        if entry is None:
            artifact = _artifact_by_plan_id(config=config, plan_id=plan_id)
            if artifact is None:
                raise PlanRegistryError(f"Unknown plan_id: {plan_id}")
            entry = _build_entry(
                artifact=artifact,
                config=config,
                existing_entries=tuple(payload.get("plans") or ()),
                request_text=artifact.summary,
                existing_entry=None,
                source="runtime_backfill",
            )
        entry = _clone_entry(entry)
        governance = _normalize_governance(entry.get("governance"))
        governance["priority"] = normalized_priority
        governance["priority_source"] = "user_confirmed"
        governance["priority_confirmed_at"] = iso_now()
        if note is not None:
            governance["note"] = str(note)
        entry["governance"] = governance
        entry["meta"] = _normalize_meta(entry.get("meta"), source=str(entry.get("meta", {}).get("source") or "runtime_auto"))
        entry["meta"]["updated_at"] = iso_now()
        payload["plans"] = _replace_entry(payload.get("plans") or (), entry)
        _write_registry(path, payload)
        return entry
    except (OSError, YamlParseError, ValueError) as exc:
        raise PlanRegistryError(str(exc)) from exc


def recommend_plan_candidates(
    *,
    config: RuntimeConfig,
    request_text: str = "",
) -> tuple[PlanRegistryRecommendation, ...]:
    """Return read-only plan ranking suggestions with explanations."""
    read_result = read_plan_registry(
        config,
        reconcile=True,
        refresh_advice=True,
        request_text=request_text,
        create_if_missing=False,
        backfill_if_missing=False,
    )
    current_plan = StateStore(config).get_current_plan()
    recommendations: list[PlanRegistryRecommendation] = []

    for entry in read_result.payload.get("plans") or ():
        plan_id = str(entry.get("plan_id") or "")
        snapshot = _normalize_snapshot(entry.get("snapshot"))
        governance = _normalize_governance(entry.get("governance"))
        advice = _normalize_advice(entry.get("advice"))

        confirmed_priority = None
        priority_source = "suggested"
        if governance.get("priority") and governance.get("priority_source") == "user_confirmed":
            confirmed_priority = str(governance.get("priority"))
            priority_source = "user_confirmed"
        suggested_priority = str(advice.get("suggested_priority") or "") or None
        effective_priority = confirmed_priority or suggested_priority or REGISTRY_PRIORITY_FALLBACK
        status = str(governance.get("status") or "todo")
        is_current_plan = current_plan is not None and current_plan.plan_id == plan_id

        reasons: list[str] = []
        if is_current_plan:
            reasons.append("当前 active plan 未完成，不建议切换")
        elif current_plan is not None:
            reasons.append("当前 active plan 未完成，不建议直接切换")

        if confirmed_priority is not None:
            reasons.append(f"已确认 {confirmed_priority} 优先级，优先于系统建议")
        elif suggested_priority is not None:
            reasons.append(f"尚未人工确认，先按建议优先级 {suggested_priority} 观察")

        if status in {"blocked", "done", "archived"}:
            reasons.append(f"当前状态为 {status}，不建议作为首个执行候选")

        for reason in advice.get("suggested_reason") or ():
            candidate = str(reason).strip()
            if candidate and candidate not in reasons:
                reasons.append(candidate)

        recommendations.append(
            PlanRegistryRecommendation(
                plan_id=plan_id,
                path=str(snapshot.get("path") or ""),
                title=str(snapshot.get("title") or plan_id),
                status=status,
                is_current_plan=is_current_plan,
                effective_priority=effective_priority,
                priority_source=priority_source,
                confirmed_priority=confirmed_priority,
                suggested_priority=suggested_priority,
                reasons=tuple(reasons),
            )
        )

    return tuple(sorted(recommendations, key=_recommendation_sort_key))


def priority_note_for_plan(*, config: RuntimeConfig, plan_id: str, language: str) -> str | None:
    """Render a user-facing priority hint line for output summaries."""
    result = get_plan_entry(config=config, plan_id=plan_id, reconcile=True, refresh_advice=False)
    if result.entry is None:
        return None
    governance = _normalize_governance(result.entry.get("governance"))
    advice = _normalize_advice(result.entry.get("advice"))
    confirmed_priority = str(governance.get("priority") or "").strip()
    if governance.get("priority_source") == "user_confirmed" and confirmed_priority:
        if language == "en-US":
            return f"Priority: {confirmed_priority} (user confirmed)"
        return f"优先级: {confirmed_priority}（用户已确认）"

    suggested_priority = str(advice.get("suggested_priority") or "").strip()
    if suggested_priority:
        if language == "en-US":
            return f"Priority: suggested {suggested_priority} (pending user confirmation)"
        return f"优先级: 建议 {suggested_priority}（待用户确认）"
    return None


def _recommendation_sort_key(item: PlanRegistryRecommendation) -> tuple[int, int, int, int, str]:
    current_rank = 0 if item.is_current_plan and item.status not in {"done", "archived"} else 1
    status_rank = 1 if item.status in {"blocked", "done", "archived"} else 0
    source_rank = 0 if item.priority_source == "user_confirmed" else 1
    priority_rank = _priority_rank(item.effective_priority)
    return (current_rank, status_rank, source_rank, priority_rank, item.path)


def _empty_registry() -> dict[str, Any]:
    return {
        "version": REGISTRY_VERSION,
        "mode": REGISTRY_MODE,
        "selection_policy": REGISTRY_SELECTION_POLICY,
        "priority_policy": REGISTRY_PRIORITY_POLICY,
        "priority_fallback": REGISTRY_PRIORITY_FALLBACK,
        "plans": [],
    }


def _clone_registry(payload: Mapping[str, Any]) -> dict[str, Any]:
    cloned = _empty_registry()
    cloned["version"] = int(payload.get("version") or REGISTRY_VERSION)
    cloned["mode"] = str(payload.get("mode") or REGISTRY_MODE)
    cloned["selection_policy"] = str(payload.get("selection_policy") or REGISTRY_SELECTION_POLICY)
    cloned["priority_policy"] = str(payload.get("priority_policy") or REGISTRY_PRIORITY_POLICY)
    cloned["priority_fallback"] = _normalize_priority_value(payload.get("priority_fallback")) or REGISTRY_PRIORITY_FALLBACK
    cloned["plans"] = [_clone_entry(entry) for entry in payload.get("plans") or ()]
    return cloned


def _clone_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "plan_id": str(entry.get("plan_id") or ""),
        "snapshot": _normalize_snapshot(entry.get("snapshot")),
        "governance": _normalize_governance(entry.get("governance")),
        "advice": _normalize_advice(entry.get("advice")),
        "meta": _normalize_meta(entry.get("meta"), source=str((entry.get("meta") or {}).get("source") or "runtime_auto")),
    }


def _read_registry(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    loaded = load_yaml(raw_text)
    if not isinstance(loaded, Mapping):
        raise ValueError(f"Plan registry at {path} must be a mapping")
    return _clone_registry(loaded)


def _write_registry(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = "\n".join(_dump_yaml(_clone_registry(payload))) + "\n"
    with NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
        handle.write(serialized)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _dump_yaml(value: Any, *, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, Mapping):
        lines: list[str] = []
        for key, item in value.items():
            key_text = str(key)
            if _is_scalar(item):
                lines.append(f"{prefix}{key_text}: {_yaml_scalar(item)}")
            else:
                lines.append(f"{prefix}{key_text}:")
                lines.extend(_dump_yaml(item, indent=indent + 2))
        return lines
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        lines = []
        for item in value:
            if isinstance(item, Mapping):
                mapping_items = list(item.items())
                if not mapping_items:
                    lines.append(f"{prefix}- {{}}")
                    continue
                first_key, first_value = mapping_items[0]
                if _is_scalar(first_value):
                    lines.append(f"{prefix}- {first_key}: {_yaml_scalar(first_value)}")
                else:
                    lines.append(f"{prefix}- {first_key}:")
                    lines.extend(_dump_yaml(first_value, indent=indent + 4))
                for key, value_item in mapping_items[1:]:
                    child_prefix = " " * (indent + 2)
                    if _is_scalar(value_item):
                        lines.append(f"{child_prefix}{key}: {_yaml_scalar(value_item)}")
                    else:
                        lines.append(f"{child_prefix}{key}:")
                        lines.extend(_dump_yaml(value_item, indent=indent + 4))
                continue
            if _is_scalar(item):
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
            else:
                lines.append(f"{prefix}-")
                lines.extend(_dump_yaml(item, indent=indent + 2))
        return lines
    return [f"{prefix}{_yaml_scalar(value)}"]


def _is_scalar(value: Any) -> bool:
    return not isinstance(value, Mapping) and not (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    )


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _normalize_snapshot(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, Mapping) else {}
    level = str(data.get("level") or "standard")
    if level not in _SUPPORTED_PLAN_LEVELS:
        level = "standard"
    lifecycle_state = str(data.get("lifecycle_state") or "active")
    if lifecycle_state not in _SUPPORTED_LIFECYCLE_STATES:
        lifecycle_state = "active"
    return {
        "path": str(data.get("path") or ""),
        "title": str(data.get("title") or ""),
        "level": level,
        "topic_key": str(data.get("topic_key") or ""),
        "lifecycle_state": lifecycle_state,
        "created_at": str(data.get("created_at") or ""),
    }


def _normalize_governance(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, Mapping) else {}
    return {
        "priority": _normalize_priority_value(data.get("priority")),
        "priority_source": str(data.get("priority_source") or "") or None,
        "priority_confirmed_at": str(data.get("priority_confirmed_at") or "") or None,
        "status": str(data.get("status") or "todo"),
        "note": str(data.get("note") or ""),
    }


def _normalize_advice(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, Mapping) else {}
    reasons = tuple(str(item) for item in data.get("suggested_reason") or () if str(item).strip())
    return {
        "suggested_priority": _normalize_priority_value(data.get("suggested_priority")),
        "suggested_source": str(data.get("suggested_source") or REGISTRY_PRIORITY_POLICY),
        "suggested_reason": reasons,
        "suggested_at": str(data.get("suggested_at") or "") or None,
    }


def _normalize_meta(raw: Any, *, source: str) -> dict[str, Any]:
    data = raw if isinstance(raw, Mapping) else {}
    return {
        "source": str(data.get("source") or source or "runtime_auto"),
        "updated_at": str(data.get("updated_at") or "") or iso_now(),
    }


def _normalize_priority_value(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in _PRIORITY_ORDER:
        return normalized
    return None


def _replace_entry(entries: Sequence[Mapping[str, Any]], entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    normalized_entry = _clone_entry(entry)
    target_id = str(normalized_entry.get("plan_id") or "")
    replaced = False
    updated: list[dict[str, Any]] = []
    for item in entries:
        if str(item.get("plan_id") or "") == target_id:
            updated.append(normalized_entry)
            replaced = True
        else:
            updated.append(_clone_entry(item))
    if not replaced:
        updated.append(normalized_entry)
    return updated


def _entry_by_plan_id(entries: Sequence[Mapping[str, Any]], plan_id: str) -> dict[str, Any] | None:
    for item in entries:
        if str(item.get("plan_id") or "") == plan_id:
            return _clone_entry(item)
    return None


def _build_entry(
    *,
    artifact: PlanArtifact,
    config: RuntimeConfig,
    existing_entries: Sequence[Mapping[str, Any]],
    request_text: str,
    existing_entry: Mapping[str, Any] | None,
    source: str,
) -> dict[str, Any]:
    snapshot = _snapshot_from_artifact(artifact=artifact, config=config)
    governance = _normalize_governance(existing_entry.get("governance") if existing_entry else None)
    advice = _merge_advice(
        existing_entry.get("advice") if existing_entry else None,
        _suggest_advice(
            plan_id=artifact.plan_id,
            snapshot=snapshot,
            request_text=request_text,
            existing_entries=existing_entries,
            current_plan=StateStore(config).get_current_plan(),
        ),
    )
    meta = _normalize_meta(existing_entry.get("meta") if existing_entry else None, source=source)
    meta["source"] = source or meta["source"]
    meta["updated_at"] = iso_now()
    return {
        "plan_id": artifact.plan_id,
        "snapshot": snapshot,
        "governance": governance,
        "advice": advice,
        "meta": meta,
    }


def _snapshot_from_artifact(*, artifact: PlanArtifact, config: RuntimeConfig) -> dict[str, Any]:
    plan_dir = config.workspace_root / artifact.path
    plan_snapshot = _load_plan_snapshot(plan_dir, config=config)
    if plan_snapshot is not None:
        return plan_snapshot
    return {
        "path": artifact.path,
        "title": _normalize_title(artifact.title or artifact.plan_id),
        "level": artifact.level if artifact.level in _SUPPORTED_PLAN_LEVELS else "standard",
        "topic_key": artifact.topic_key or _slugify(artifact.title or artifact.plan_id),
        "lifecycle_state": "active",
        "created_at": artifact.created_at or iso_now(),
    }


def _reconcile_snapshot_fields(
    payload: Mapping[str, Any],
    *,
    config: RuntimeConfig,
) -> tuple[dict[str, Any], dict[str, tuple[str, ...]], bool]:
    cloned = _clone_registry(payload)
    drift_notice: dict[str, tuple[str, ...]] = {}
    changed = False
    reconciled: list[dict[str, Any]] = []

    for raw_entry in cloned.get("plans") or ():
        entry = _clone_entry(raw_entry)
        plan_id = str(entry.get("plan_id") or "")
        existing_snapshot = _normalize_snapshot(entry.get("snapshot"))
        plan_dir = _resolve_plan_dir(config=config, plan_id=plan_id, snapshot=existing_snapshot)
        if plan_dir is None:
            reconciled.append(entry)
            continue

        actual_snapshot = _load_plan_snapshot(plan_dir, config=config)
        if actual_snapshot is None:
            reconciled.append(entry)
            continue

        notices: list[str] = []
        for key in ("title", "level", "path", "topic_key", "lifecycle_state"):
            before = str(existing_snapshot.get(key) or "")
            after = str(actual_snapshot.get(key) or "")
            if before != after:
                notices.append(f"{key}: {before or '<empty>'} -> {after or '<empty>'}")
                existing_snapshot[key] = after
                changed = True

        entry["snapshot"] = existing_snapshot
        if notices:
            drift_notice[plan_id] = tuple(notices)
        reconciled.append(entry)

    cloned["plans"] = reconciled
    return cloned, drift_notice, changed


def _refresh_advice_fields(
    payload: Mapping[str, Any],
    *,
    config: RuntimeConfig,
    request_text: str,
) -> tuple[dict[str, Any], bool]:
    cloned = _clone_registry(payload)
    current_plan = StateStore(config).get_current_plan()
    changed = False
    refreshed: list[dict[str, Any]] = []

    for raw_entry in cloned.get("plans") or ():
        entry = _clone_entry(raw_entry)
        plan_id = str(entry.get("plan_id") or "")
        snapshot = _normalize_snapshot(entry.get("snapshot"))
        old_advice = _normalize_advice(entry.get("advice"))
        new_advice = _merge_advice(
            old_advice,
            _suggest_advice(
                plan_id=plan_id,
                snapshot=snapshot,
                request_text=request_text,
                existing_entries=tuple(cloned.get("plans") or ()),
                current_plan=current_plan,
            ),
        )
        if new_advice != old_advice:
            entry["advice"] = new_advice
            entry["meta"]["updated_at"] = iso_now()
            changed = True
        refreshed.append(entry)

    cloned["plans"] = refreshed
    return cloned, changed


def _backfill_missing_entries(
    payload: Mapping[str, Any],
    *,
    config: RuntimeConfig,
    request_text: str,
) -> tuple[dict[str, Any], bool]:
    cloned = _clone_registry(payload)
    known_plan_ids = {str(entry.get("plan_id") or "") for entry in cloned.get("plans") or ()}
    changed = False

    if not config.plan_root.exists():
        return cloned, changed

    for plan_dir in sorted(config.plan_root.iterdir()):
        if not plan_dir.is_dir():
            continue
        artifact = _artifact_from_plan_dir(plan_dir, config=config)
        if artifact is None or artifact.plan_id in known_plan_ids:
            continue
        entry = _build_entry(
            artifact=artifact,
            config=config,
            existing_entries=tuple(cloned.get("plans") or ()),
            request_text=request_text or artifact.summary,
            existing_entry=None,
            source="runtime_backfill",
        )
        cloned["plans"] = _replace_entry(cloned.get("plans") or (), entry)
        known_plan_ids.add(artifact.plan_id)
        changed = True

    return cloned, changed


def _suggest_advice(
    *,
    plan_id: str,
    snapshot: Mapping[str, Any],
    request_text: str,
    existing_entries: Sequence[Mapping[str, Any]],
    current_plan: PlanArtifact | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    normalized_request = _normalize_text(request_text)

    if _has_duplicate_plan(plan_id=plan_id, snapshot=snapshot, existing_entries=existing_entries):
        suggested_priority = "p3"
        reasons.append("与已有 active plan 主题接近，建议先复用或合并")
    elif _has_urgent_signal(normalized_request):
        suggested_priority = "p1"
        reasons.append("请求中出现明确紧急或阻塞信号")
    elif current_plan is not None and current_plan.plan_id != plan_id:
        suggested_priority = "p3"
        reasons.append("当前 active plan 未完成")
        reasons.append("新 plan 暂不建议直接抢占执行顺序")
    elif _active_plan_count(existing_entries=existing_entries, excluding_plan_id=plan_id) >= 3:
        suggested_priority = "p3"
        reasons.append("当前活动 plan 较多，建议先收口存量")
    else:
        suggested_priority = REGISTRY_PRIORITY_FALLBACK
        reasons.append("未识别明确紧急或降级信号，先按默认建议观察")

    return {
        "suggested_priority": suggested_priority,
        "suggested_source": REGISTRY_PRIORITY_POLICY,
        "suggested_reason": tuple(reasons),
        "suggested_at": iso_now(),
    }


def _merge_advice(existing: Any, candidate: Mapping[str, Any]) -> dict[str, Any]:
    normalized_existing = _normalize_advice(existing)
    normalized_candidate = _normalize_advice(candidate)
    # inspect/refresh is observe-only: if the recommendation itself did not change,
    # keep the original timestamp so reads do not rewrite the registry.
    if _advice_identity(normalized_existing) == _advice_identity(normalized_candidate):
        existing_suggested_at = normalized_existing.get("suggested_at")
        if existing_suggested_at:
            normalized_candidate["suggested_at"] = existing_suggested_at
    return normalized_candidate


def _advice_identity(advice: Mapping[str, Any]) -> tuple[str | None, str, tuple[str, ...]]:
    normalized = _normalize_advice(advice)
    return (
        _normalize_priority_value(normalized.get("suggested_priority")),
        str(normalized.get("suggested_source") or REGISTRY_PRIORITY_POLICY),
        tuple(str(item) for item in normalized.get("suggested_reason") or ()),
    )


def _has_duplicate_plan(
    *,
    plan_id: str,
    snapshot: Mapping[str, Any],
    existing_entries: Sequence[Mapping[str, Any]],
) -> bool:
    topic_key = str(snapshot.get("topic_key") or "").strip()
    title = _normalize_text(str(snapshot.get("title") or ""))
    for entry in existing_entries:
        existing_plan_id = str(entry.get("plan_id") or "")
        if not existing_plan_id or existing_plan_id == plan_id:
            continue
        existing_snapshot = _normalize_snapshot(entry.get("snapshot"))
        if topic_key and topic_key == str(existing_snapshot.get("topic_key") or "").strip():
            return True
        if title and title == _normalize_text(str(existing_snapshot.get("title") or "")):
            return True
    return False


def _has_urgent_signal(normalized_request: str) -> bool:
    if not normalized_request:
        return False
    return any(pattern.search(normalized_request) is not None for pattern in _URGENT_PATTERNS)


def _active_plan_count(*, existing_entries: Sequence[Mapping[str, Any]], excluding_plan_id: str) -> int:
    count = 0
    for entry in existing_entries:
        plan_id = str(entry.get("plan_id") or "")
        if not plan_id or plan_id == excluding_plan_id:
            continue
        snapshot = _normalize_snapshot(entry.get("snapshot"))
        if snapshot.get("lifecycle_state") == "archived":
            continue
        count += 1
    return count


def _resolve_plan_dir(
    *,
    config: RuntimeConfig,
    plan_id: str,
    snapshot: Mapping[str, Any],
) -> Path | None:
    declared_path = str(snapshot.get("path") or "").strip()
    if declared_path:
        candidate = config.workspace_root / declared_path
        if candidate.exists() and candidate.is_dir():
            identity = _load_plan_identity(candidate)
            if identity == plan_id:
                return candidate

    default_candidate = config.plan_root / plan_id
    if default_candidate.exists() and default_candidate.is_dir():
        return default_candidate

    if not config.plan_root.exists():
        return None
    for plan_dir in config.plan_root.iterdir():
        if not plan_dir.is_dir():
            continue
        if _load_plan_identity(plan_dir) == plan_id:
            return plan_dir
    return None


def _artifact_by_plan_id(*, config: RuntimeConfig, plan_id: str) -> PlanArtifact | None:
    for plan_dir in sorted(config.plan_root.iterdir()) if config.plan_root.exists() else ():
        if not plan_dir.is_dir():
            continue
        artifact = _artifact_from_plan_dir(plan_dir, config=config)
        if artifact is not None and artifact.plan_id == plan_id:
            return artifact
    return None


def _artifact_from_plan_dir(plan_dir: Path, *, config: RuntimeConfig) -> PlanArtifact | None:
    plan_document = _load_plan_document(plan_dir)
    if plan_document is None:
        return None
    metadata_path, metadata, body = plan_document
    plan_id = str(metadata.get("plan_id") or plan_dir.name)
    snapshot = _load_plan_snapshot(plan_dir, config=config)
    if snapshot is None:
        return None
    title = str(snapshot.get("title") or plan_id)
    summary = _extract_summary(body, fallback=title)
    files = tuple(str(path.relative_to(config.workspace_root)) for path in _collect_plan_files(plan_dir))
    return PlanArtifact(
        plan_id=plan_id,
        title=title,
        summary=summary,
        level=str(snapshot.get("level") or "standard"),
        path=str(snapshot.get("path") or plan_dir.relative_to(config.workspace_root)),
        files=files,
        created_at=str(snapshot.get("created_at") or _path_created_at(metadata_path)),
        topic_key=str(snapshot.get("topic_key") or ""),
    )


def _load_plan_snapshot(plan_dir: Path, *, config: RuntimeConfig) -> dict[str, Any] | None:
    plan_document = _load_plan_document(plan_dir)
    if plan_document is None:
        return None
    metadata_path, metadata, body = plan_document
    title = _normalize_title(_extract_title(body) or str(metadata.get("plan_id") or plan_dir.name))
    level = str(metadata.get("level") or ("light" if metadata_path.name == "plan.md" else "standard"))
    if level not in _SUPPORTED_PLAN_LEVELS:
        level = "standard"
    lifecycle_state = str(metadata.get("lifecycle_state") or "active")
    if lifecycle_state not in _SUPPORTED_LIFECYCLE_STATES:
        lifecycle_state = "active"
    topic_key = str(metadata.get("topic_key") or metadata.get("feature_key") or _slugify(title))
    created_at = str(metadata.get("created_at") or "") or _path_created_at(metadata_path)
    return {
        "path": str(plan_dir.relative_to(config.workspace_root)),
        "title": title,
        "level": level,
        "topic_key": topic_key,
        "lifecycle_state": lifecycle_state,
        "created_at": created_at,
    }


def _load_plan_document(plan_dir: Path) -> tuple[Path, Mapping[str, Any], str] | None:
    metadata_path = _pick_metadata_file(plan_dir)
    if metadata_path is None:
        return None
    raw_text = metadata_path.read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(raw_text)
    if match is None:
        return None
    metadata = load_yaml(match.group("front"))
    if not isinstance(metadata, Mapping):
        return None
    return metadata_path, metadata, match.group("body")


def _load_plan_identity(plan_dir: Path) -> str | None:
    plan_document = _load_plan_document(plan_dir)
    if plan_document is None:
        return None
    _, metadata, _ = plan_document
    return str(metadata.get("plan_id") or plan_dir.name)


def _pick_metadata_file(plan_dir: Path) -> Path | None:
    for filename in ("plan.md", "tasks.md"):
        candidate = plan_dir / filename
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _collect_plan_files(plan_dir: Path) -> list[Path]:
    return sorted(path for path in plan_dir.iterdir())


def _extract_title(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _extract_summary(body: str, *, fallback: str) -> str:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return fallback
    for index, line in enumerate(lines):
        if line.startswith("# "):
            if index + 1 < len(lines):
                return lines[index + 1]
            break
    return lines[0]


def _normalize_title(title: str) -> str:
    stripped = _TITLE_PREFIX_RE.sub("", str(title or "").strip())
    return stripped or str(title or "").strip()


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "").strip()).lower()


def _slugify(value: str) -> str:
    normalized = _SLUG_RE.sub("-", _normalize_text(value)).strip("-")
    return normalized or "task"


def _priority_rank(value: str) -> int:
    return _PRIORITY_ORDER.get(str(value or "").strip().lower(), 99)


def _path_created_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
