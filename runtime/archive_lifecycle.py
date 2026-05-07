"""Deterministic archive lifecycle for Sopify plan assets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
import shutil
from pathlib import Path
from typing import Any, Mapping

from ._yaml import YamlParseError, load_yaml
from .kb import ensure_blueprint_index
from .knowledge_layout import resolve_path
from .knowledge_sync import KNOWLEDGE_SYNC_KEYS, knowledge_sync_targets, parse_knowledge_sync
from .models import KbArtifact, PlanArtifact, RuntimeConfig
from .plan_registry import PlanRegistryError, remove_plan_entry
from .state import StateStore, iso_now

ARCHIVE_STATUS_COMPLETED = "completed"
ARCHIVE_STATUS_BLOCKED = "blocked"
ARCHIVE_STATUS_ALREADY_ARCHIVED = "already_archived"

_REQUIRED_METADATA_KEYS = (
    "plan_id",
    "feature_key",
    "level",
    "lifecycle_state",
    "knowledge_sync",
    "archive_ready",
)
_SUPPORTED_LEVELS = {"light", "standard", "full"}
_SUPPORTED_LIFECYCLE_STATES = {"active", "ready_for_verify"}
_FRONT_MATTER_RE = re.compile(r"\A---\n(?P<front>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
_PLAN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class ArchiveSubject:
    """Resolved archive target independent of active runtime flow."""

    kind: str
    plan_id: str
    plan_dir: Path | None = None
    relative_plan_dir: str = ""
    artifact: PlanArtifact | None = None
    reason_code: str = ""
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArchiveCheckResult:
    status: str
    subject: ArchiveSubject
    notes: tuple[str, ...] = ()
    knowledge_sync_result: dict[str, object] | None = None


@dataclass(frozen=True)
class ArchiveApplyResult:
    status: str
    subject: ArchiveSubject
    archived_plan: PlanArtifact | None
    kb_artifact: KbArtifact | None
    notes: tuple[str, ...]
    registry_updated: bool = False
    state_cleared: bool = False
    knowledge_sync_result: dict[str, object] | None = None


@dataclass(frozen=True)
class _ManagedArchivePlanDocument:
    plan_dir: Path
    relative_plan_dir: str
    metadata_path: Path
    plan_id: str
    level: str
    knowledge_sync: Mapping[str, str]
    front_matter: str
    body: str


@dataclass(frozen=True)
class _ArchiveWriteResult:
    archived_plan: PlanArtifact | None
    kb_artifact: KbArtifact | None
    notes: tuple[str, ...]
    registry_updated: bool = False
    knowledge_sync_result: dict[str, object] | None = None


@dataclass(frozen=True)
class _KnowledgeSyncStatus:
    blocked_reason: str | None
    notes: tuple[str, ...]
    changed_files: tuple[str, ...] = ()
    review_pending: tuple[str, ...] = ()
    required_missing: tuple[str, ...] = ()


def resolve_archive_subject(
    archive_subject: Mapping[str, Any] | None,
    *,
    config: RuntimeConfig,
    state_store: StateStore | None = None,
    current_plan: PlanArtifact | None = None,
) -> ArchiveSubject:
    """Resolve the archive subject from structured ActionProposal artifacts."""
    if not isinstance(archive_subject, Mapping):
        return ArchiveSubject(
            kind="missing",
            plan_id="",
            reason_code="missing_archive_subject",
            issues=("archive_subject artifact is required",),
        )

    ref_kind = str(archive_subject.get("ref_kind") or "").strip()
    ref_value = str(archive_subject.get("ref_value") or "").strip()

    if ref_kind == "plan_id":
        subject = _subject_from_plan_id(ref_value, config=config)
        if subject is not None:
            return subject
        return ArchiveSubject(
            kind="missing",
            plan_id=ref_value,
            reason_code="plan_not_found",
            issues=("Referenced archive plan_id was not found",),
        )

    if ref_kind == "path":
        return _subject_from_relative_path(ref_value, config=config)

    if ref_kind != "current_plan":
        return ArchiveSubject(
            kind="missing",
            plan_id="",
            reason_code="invalid_archive_subject",
            issues=("archive_subject.ref_kind must be plan_id, path, or current_plan",),
        )

    active_plan = current_plan
    if active_plan is None and state_store is not None:
        active_plan = state_store.get_current_plan()
    if active_plan is not None:
        plan_dir = config.workspace_root / active_plan.path
        return _subject_from_plan_dir(plan_dir, config=config, artifact=active_plan)

    return ArchiveSubject(
        kind="missing",
        plan_id="",
        reason_code="plan_not_found",
        issues=("No current plan is available for archive_subject.ref_kind=current_plan",),
    )


def check_archive_subject(subject: ArchiveSubject, *, config: RuntimeConfig) -> ArchiveCheckResult:
    """Return whether an archive subject is ready for apply."""
    if subject.kind == "archived":
        return ArchiveCheckResult(status="already_archived", subject=subject, notes=("archive.already_archived",))
    if subject.kind == "missing":
        return ArchiveCheckResult(status="plan_not_found", subject=subject, notes=subject.issues)
    if subject.kind == "ambiguous":
        return ArchiveCheckResult(status="ambiguous_subject", subject=subject, notes=subject.issues)
    if subject.kind == "legacy":
        return ArchiveCheckResult(status="migration_required", subject=subject, notes=subject.issues)
    if subject.kind != "managed" or subject.artifact is None:
        return ArchiveCheckResult(status="plan_not_found", subject=subject, notes=subject.issues)

    scratch_store = StateStore(config)
    result = _apply_managed_archive(config=config, state_store=scratch_store, current_plan=subject.artifact, dry_run=True)
    if result.archived_plan is not None:
        return ArchiveCheckResult(status="ready", subject=subject, notes=result.notes, knowledge_sync_result=result.knowledge_sync_result)
    if any("归档目标已存在" in note or "Archive target already exists" in note for note in result.notes):
        return ArchiveCheckResult(status="archive_target_conflict", subject=subject, notes=result.notes, knowledge_sync_result=result.knowledge_sync_result)
    return ArchiveCheckResult(status="blocked", subject=subject, notes=result.notes, knowledge_sync_result=result.knowledge_sync_result)


def apply_archive_subject(
    subject: ArchiveSubject,
    *,
    config: RuntimeConfig,
    state_store: StateStore | None = None,
) -> ArchiveApplyResult:
    """Archive a ready subject into history."""
    check = check_archive_subject(subject, config=config)
    if check.status == "already_archived":
        return ArchiveApplyResult(
            status=ARCHIVE_STATUS_ALREADY_ARCHIVED,
            subject=subject,
            archived_plan=subject.artifact,
            kb_artifact=None,
            notes=check.notes,
        )
    if check.status != "ready" or subject.artifact is None:
        return ArchiveApplyResult(
            status=ARCHIVE_STATUS_BLOCKED,
            subject=subject,
            archived_plan=None,
            kb_artifact=None,
            notes=check.notes,
            knowledge_sync_result=check.knowledge_sync_result,
        )

    apply_store = state_store or StateStore(config)
    active_plan = apply_store.get_current_plan() if state_store is not None else None
    should_clear_state = _same_plan(active_plan, subject.artifact)
    result = _apply_managed_archive(
        config=config,
        state_store=apply_store,
        current_plan=subject.artifact,
        clear_state=should_clear_state,
    )
    state_cleared = False
    if result.archived_plan is not None and state_store is not None and should_clear_state:
        state_cleared = apply_store.get_current_plan() is None and apply_store.get_current_run() is None
    return ArchiveApplyResult(
        status=ARCHIVE_STATUS_COMPLETED if result.archived_plan is not None else ARCHIVE_STATUS_BLOCKED,
        subject=subject,
        archived_plan=result.archived_plan,
        kb_artifact=result.kb_artifact,
        notes=result.notes,
        registry_updated=result.registry_updated,
        state_cleared=state_cleared,
        knowledge_sync_result=result.knowledge_sync_result,
    )


def _same_plan(left: PlanArtifact | None, right: PlanArtifact | None) -> bool:
    if left is None or right is None:
        return False
    return left.plan_id == right.plan_id and left.path == right.path


def archive_status_payload(
    *,
    status: str,
    subject: ArchiveSubject,
    notes: tuple[str, ...] = (),
    changed_files: tuple[str, ...] = (),
    state_cleared: bool = False,
    knowledge_sync_result: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "archive_status": status,
        "archive_subject_kind": subject.kind,
        "archive_subject_plan_id": subject.plan_id,
        "archive_subject_path": subject.relative_plan_dir,
        "archive_notes": list(notes),
        "archive_changed_files": list(changed_files),
        "state_cleared": state_cleared,
    }
    if knowledge_sync_result is not None:
        payload["knowledge_sync_result"] = knowledge_sync_result
    return payload


def _apply_managed_archive(
    *,
    config: RuntimeConfig,
    state_store: StateStore,
    current_plan: PlanArtifact | None,
    dry_run: bool = False,
    clear_state: bool = True,
) -> _ArchiveWriteResult:
    if current_plan is None:
        return _ArchiveWriteResult(
            archived_plan=None,
            kb_artifact=None,
            notes=(_text(config.language, "no_archive_subject"),),
        )

    plan_dir = config.workspace_root / current_plan.path
    if not plan_dir.exists() or not plan_dir.is_dir():
        return _ArchiveWriteResult(
            archived_plan=None,
            kb_artifact=None,
            notes=(_text(config.language, "missing_plan_dir", path=current_plan.path),),
        )

    managed_plan = _load_managed_plan(plan_dir, config=config)
    if managed_plan is None:
        return _ArchiveWriteResult(
            archived_plan=None,
            kb_artifact=None,
            notes=(_text(config.language, "metadata_missing"),),
        )

    if managed_plan.plan_id != current_plan.plan_id:
        return _ArchiveWriteResult(
            archived_plan=None,
            kb_artifact=None,
            notes=(
                _text(
                    config.language,
                    "metadata_mismatch",
                    state_plan_id=current_plan.plan_id,
                    document_plan_id=managed_plan.plan_id,
                ),
            ),
        )

    contract_status = _evaluate_knowledge_sync(
        config=config,
        managed_plan=managed_plan,
        created_at=current_plan.created_at,
    )
    sync_result = _knowledge_sync_result(contract_status, managed_plan.knowledge_sync)
    if contract_status.blocked_reason is not None:
        return _ArchiveWriteResult(
            archived_plan=None,
            kb_artifact=None,
            notes=(*contract_status.notes, contract_status.blocked_reason),
            knowledge_sync_result=sync_result,
        )

    archive_dir = _archive_target_dir(config=config, plan_id=managed_plan.plan_id)
    if archive_dir.exists():
        return _ArchiveWriteResult(
            archived_plan=None,
            kb_artifact=None,
            notes=(
                _text(
                    config.language,
                    "archive_exists",
                    path=str(archive_dir.relative_to(config.workspace_root)),
                ),
            ),
            knowledge_sync_result=sync_result,
        )

    if dry_run:
        return _ArchiveWriteResult(
            archived_plan=PlanArtifact(
                plan_id=current_plan.plan_id,
                title=current_plan.title,
                summary=current_plan.summary,
                level=current_plan.level,
                path=str(archive_dir.relative_to(config.workspace_root)),
                files=_archived_files(current_plan=current_plan, archive_dir=archive_dir, workspace_root=config.workspace_root),
                created_at=current_plan.created_at,
                topic_key=current_plan.topic_key,
            ),
            kb_artifact=None,
            notes=contract_status.notes,
            knowledge_sync_result=sync_result,
        )

    archive_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(plan_dir), str(archive_dir))

    archived_metadata_path = archive_dir / managed_plan.metadata_path.name
    archived_text = _render_document(
        _normalize_archived_front_matter(managed_plan.front_matter),
        managed_plan.body,
    )
    archived_metadata_path.write_text(archived_text, encoding="utf-8")

    archived_plan = PlanArtifact(
        plan_id=current_plan.plan_id,
        title=current_plan.title,
        summary=current_plan.summary,
        level=current_plan.level,
        path=str(archive_dir.relative_to(config.workspace_root)),
        files=_archived_files(current_plan=current_plan, archive_dir=archive_dir, workspace_root=config.workspace_root),
        created_at=current_plan.created_at,
        topic_key=current_plan.topic_key,
    )

    history_index_path = _update_history_index(config=config, archived_plan=archived_plan)
    ensure_blueprint_index(config)
    readme_path = resolve_path(config=config, key="blueprint_index")

    registry_notes: tuple[str, ...] = ()
    registry_updated = False
    try:
        registry_updated = remove_plan_entry(config=config, plan_id=current_plan.plan_id)
    except PlanRegistryError:
        registry_notes = (_text(config.language, "registry_sync_failed"),)

    if clear_state:
        state_store.reset_active_flow()

    kb_files = tuple(
        path
        for path in (
            str(readme_path.relative_to(config.workspace_root)),
            str(history_index_path.relative_to(config.workspace_root)),
        )
    )
    notes = [
        *contract_status.notes,
        _text(config.language, "archived", path=archived_plan.path),
    ]
    if clear_state:
        notes.append(_text(config.language, "state_cleared"))
    notes.extend(registry_notes)
    return _ArchiveWriteResult(
        archived_plan=archived_plan,
        kb_artifact=KbArtifact(mode=config.kb_init, files=kb_files, created_at=iso_now()),
        notes=tuple(notes),
        registry_updated=registry_updated,
        knowledge_sync_result=sync_result,
    )


def _subject_from_plan_id(plan_id: str, *, config: RuntimeConfig) -> ArchiveSubject | None:
    if not _is_plain_plan_id(plan_id):
        return None
    candidate = config.plan_root / plan_id
    if candidate.exists():
        return _subject_from_plan_dir(candidate, config=config)
    history_root = resolve_path(config=config, key="history_root")
    if history_root.exists():
        matches = [path for path in history_root.glob(f"*/{plan_id}") if path.is_dir()]
        if len(matches) == 1:
            return _subject_from_plan_dir(matches[0], config=config)
        if len(matches) > 1:
            return ArchiveSubject(
                kind="ambiguous",
                plan_id=plan_id,
                reason_code="ambiguous_subject",
                issues=tuple(str(path.relative_to(config.workspace_root)) for path in matches),
            )
    return None


def _subject_from_relative_path(relative_path: str, *, config: RuntimeConfig) -> ArchiveSubject:
    plan_dir = (config.workspace_root / relative_path).resolve()
    try:
        plan_dir.relative_to(config.workspace_root)
    except ValueError:
        return ArchiveSubject(kind="missing", plan_id="", reason_code="plan_not_found", issues=("Path is outside workspace",))
    if not _is_archive_subject_path(plan_dir, config=config):
        return ArchiveSubject(kind="missing", plan_id=plan_dir.name, reason_code="plan_not_found", issues=("Plan path must be under plan or history root",))
    if not plan_dir.exists() or not plan_dir.is_dir():
        return ArchiveSubject(kind="missing", plan_id=plan_dir.name, reason_code="plan_not_found", issues=("Plan path does not exist",))
    return _subject_from_plan_dir(plan_dir, config=config)


def _is_plain_plan_id(plan_id: str) -> bool:
    return bool(_PLAN_ID_RE.fullmatch(plan_id or ""))


def _is_archive_subject_path(plan_dir: Path, *, config: RuntimeConfig) -> bool:
    roots = (config.plan_root.resolve(), resolve_path(config=config, key="history_root").resolve())
    for root in roots:
        try:
            plan_dir.relative_to(root)
        except ValueError:
            continue
        return plan_dir != root
    return False


def _load_managed_plan(plan_dir: Path, *, config: RuntimeConfig) -> _ManagedArchivePlanDocument | None:
    metadata_path = _pick_metadata_file(plan_dir)
    if metadata_path is None:
        return None

    raw_text = metadata_path.read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(raw_text)
    if match is None:
        return None

    front_matter = match.group("front")
    body = match.group("body")
    try:
        metadata = load_yaml(front_matter)
    except YamlParseError:
        return None
    if not isinstance(metadata, Mapping):
        return None
    if any(key not in metadata for key in _REQUIRED_METADATA_KEYS):
        return None
    knowledge_sync = parse_knowledge_sync(metadata.get("knowledge_sync"))
    if knowledge_sync is None:
        return None

    level = str(metadata["level"])
    lifecycle_state = str(metadata["lifecycle_state"])
    if level not in _SUPPORTED_LEVELS or lifecycle_state not in _SUPPORTED_LIFECYCLE_STATES:
        return None

    return _ManagedArchivePlanDocument(
        plan_dir=plan_dir,
        relative_plan_dir=str(plan_dir.relative_to(config.workspace_root)),
        metadata_path=metadata_path,
        plan_id=metadata["plan_id"],
        level=level,
        knowledge_sync=knowledge_sync,
        front_matter=front_matter,
        body=body,
    )


def _subject_from_plan_dir(plan_dir: Path, *, config: RuntimeConfig, artifact: PlanArtifact | None = None) -> ArchiveSubject:
    relative = str(plan_dir.relative_to(config.workspace_root))
    managed_plan = _load_managed_plan(plan_dir, config=config)
    loaded_artifact = artifact or _artifact_from_plan_dir(plan_dir, config=config)
    if relative.startswith(f"{config.plan_directory}/history/"):
        return ArchiveSubject(
            kind="archived",
            plan_id=(loaded_artifact.plan_id if loaded_artifact is not None else plan_dir.name),
            plan_dir=plan_dir,
            relative_plan_dir=relative,
            artifact=loaded_artifact,
        )
    if managed_plan is not None and loaded_artifact is not None:
        return ArchiveSubject(
            kind="managed",
            plan_id=managed_plan.plan_id,
            plan_dir=plan_dir,
            relative_plan_dir=relative,
            artifact=loaded_artifact,
        )
    return ArchiveSubject(
        kind="legacy",
        plan_id=plan_dir.name,
        plan_dir=plan_dir,
        relative_plan_dir=relative,
        artifact=loaded_artifact,
        reason_code="migration_required",
        issues=("Plan is missing required archive metadata",),
    )


def _artifact_from_plan_dir(plan_dir: Path, *, config: RuntimeConfig) -> PlanArtifact | None:
    if not plan_dir.exists() or not plan_dir.is_dir():
        return None
    metadata_path = _pick_metadata_file(plan_dir)
    body = ""
    metadata: Mapping[str, object] = {}
    if metadata_path is not None:
        raw = metadata_path.read_text(encoding="utf-8")
        match = _FRONT_MATTER_RE.match(raw)
        if match is not None:
            body = match.group("body")
            try:
                loaded = load_yaml(match.group("front"))
            except YamlParseError:
                loaded = {}
            if isinstance(loaded, Mapping):
                metadata = loaded
        else:
            body = raw
    plan_id = str(metadata.get("plan_id") or plan_dir.name)
    level = str(metadata.get("level") or _legacy_level(plan_dir))
    title = _extract_title(body) or plan_id
    return PlanArtifact(
        plan_id=plan_id,
        title=title,
        summary=_extract_summary(body, fallback=title),
        level=level,
        path=str(plan_dir.relative_to(config.workspace_root)),
        files=tuple(str(path.relative_to(config.workspace_root)) for path in _collect_plan_files(plan_dir)),
        created_at=_path_created_at(metadata_path or plan_dir),
        topic_key=str(metadata.get("topic_key") or metadata.get("feature_key") or plan_id),
    )


def _pick_metadata_file(plan_dir: Path) -> Path | None:
    for filename in ("plan.md", "tasks.md"):
        candidate = plan_dir / filename
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _normalize_archived_front_matter(front_matter: str) -> str:
    normalized = front_matter
    normalized = _upsert_front_matter_scalar(normalized, "lifecycle_state", "archived")
    normalized = _upsert_front_matter_mapping(
        normalized,
        "knowledge_sync",
        {key: "skip" for key in KNOWLEDGE_SYNC_KEYS},
    )
    normalized = _delete_front_matter_key(normalized, "blueprint_obligation")
    normalized = _upsert_front_matter_scalar(normalized, "archive_ready", "true")
    normalized = _upsert_front_matter_scalar(normalized, "plan_status", "completed")
    return normalized


def _upsert_front_matter_scalar(front_matter: str, key: str, value: str) -> str:
    return _upsert_front_matter_entry(front_matter, key, [f"{key}: {value}"])


def _upsert_front_matter_mapping(front_matter: str, key: str, values: Mapping[str, str]) -> str:
    lines = [f"{key}:", *(f"  {nested_key}: {nested_value}" for nested_key, nested_value in values.items())]
    return _upsert_front_matter_entry(front_matter, key, lines)


def _upsert_front_matter_entry(front_matter: str, key: str, replacement: list[str]) -> str:
    entries = _split_front_matter_entries(front_matter)
    for index, entry in enumerate(entries):
        if _front_matter_entry_key(entry) == key:
            entries[index] = replacement
            break
    else:
        entries.append(replacement)
    return "\n".join(line for entry in entries for line in entry)


def _delete_front_matter_key(front_matter: str, key: str) -> str:
    entries = [
        entry
        for entry in _split_front_matter_entries(front_matter)
        if _front_matter_entry_key(entry) != key
    ]
    return "\n".join(line for entry in entries for line in entry)


def _split_front_matter_entries(front_matter: str) -> list[list[str]]:
    entries: list[list[str]] = []
    current: list[str] = []
    for line in front_matter.splitlines():
        if current and line and not line.startswith(" "):
            entries.append(current)
            current = [line]
            continue
        current.append(line)
    if current:
        entries.append(current)
    return entries


def _front_matter_entry_key(entry: list[str]) -> str:
    head = entry[0] if entry else ""
    key, _, _ = head.partition(":")
    return key.strip()


def _render_document(front_matter: str, body: str) -> str:
    return f"---\n{front_matter}\n---\n{body}"


def _legacy_level(plan_dir: Path) -> str:
    return "light" if (plan_dir / "plan.md").exists() else "standard"


def _collect_plan_files(plan_dir: Path) -> list[Path]:
    return sorted(path for path in plan_dir.rglob("*") if path.is_file())


def _extract_title(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _extract_summary(body: str, *, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return fallback


def _path_created_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().replace(microsecond=0).isoformat()


def _evaluate_knowledge_sync(
    *,
    config: RuntimeConfig,
    managed_plan: _ManagedArchivePlanDocument,
    created_at: str,
) -> _KnowledgeSyncStatus:
    plan_created_at = _parse_created_at(created_at)
    plan_document_time = datetime.fromtimestamp(managed_plan.metadata_path.stat().st_mtime, tz=plan_created_at.tzinfo)
    reference_time = max(plan_created_at, plan_document_time)
    targets = knowledge_sync_targets(config=config)
    changed_files: list[str] = []
    review_pending: list[str] = []
    required_missing: list[str] = []

    for key in KNOWLEDGE_SYNC_KEYS:
        mode = managed_plan.knowledge_sync[key]
        if mode == "skip":
            continue
        path = targets[key]
        updated = path.exists() and datetime.fromtimestamp(path.stat().st_mtime, tz=reference_time.tzinfo) > reference_time
        relative_path = str(path.relative_to(config.workspace_root))
        if updated:
            changed_files.append(relative_path)
            continue
        if mode == "required":
            required_missing.append(relative_path)
        else:
            review_pending.append(relative_path)

    if required_missing:
        return _KnowledgeSyncStatus(
            blocked_reason=_text(config.language, "knowledge_sync_required_blocked", paths=", ".join(required_missing)),
            notes=(),
            required_missing=tuple(required_missing),
        )

    notes: list[str] = []
    if changed_files:
        notes.append(_text(config.language, "knowledge_sync_updated", paths=", ".join(changed_files)))
    if review_pending:
        notes.append(_text(config.language, "knowledge_sync_review_warning", paths=", ".join(review_pending)))

    return _KnowledgeSyncStatus(
        blocked_reason=None,
        notes=tuple(notes),
        changed_files=tuple(changed_files),
        review_pending=tuple(review_pending),
    )


def _parse_created_at(value: str) -> datetime:
    if value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now().astimezone()


def _knowledge_sync_result(
    status: _KnowledgeSyncStatus,
    sync_config: Mapping[str, str],
) -> dict[str, object]:
    """Build a structured knowledge_sync_result for the archive receipt."""
    outcome = "blocked" if status.blocked_reason else "passed"
    result: dict[str, object] = {
        "outcome": outcome,
        "sync_level": dict(sync_config),
    }
    if status.changed_files:
        result["changed_files"] = list(status.changed_files)
    if status.review_pending:
        result["review_pending"] = list(status.review_pending)
    if status.required_missing:
        result["required_missing"] = list(status.required_missing)
    return result


def _archive_target_dir(*, config: RuntimeConfig, plan_id: str) -> Path:
    archive_month = datetime.now().strftime("%Y-%m")
    return resolve_path(config=config, key="history_root") / archive_month / plan_id


def _archived_files(*, current_plan: PlanArtifact, archive_dir: Path, workspace_root: Path) -> tuple[str, ...]:
    source_root = current_plan.path.rstrip("/")
    target_root = str(archive_dir.relative_to(workspace_root))
    archived_files: list[str] = []
    for path in current_plan.files:
        if path.startswith(source_root):
            archived_files.append(path.replace(source_root, target_root, 1))
        else:
            archived_files.append(path)
    return tuple(archived_files)


def _update_history_index(*, config: RuntimeConfig, archived_plan: PlanArtifact) -> Path:
    history_index = resolve_path(config=config, key="history_root") / "index.md"
    history_index.parent.mkdir(parents=True, exist_ok=True)
    existing = history_index.read_text(encoding="utf-8") if history_index.exists() else _history_index_stub(config.language)
    updated = _render_history_index(existing, archived_plan=archived_plan, language=config.language)
    if updated != existing:
        history_index.write_text(updated, encoding="utf-8")
    return history_index


def _render_history_index(existing: str, *, archived_plan: PlanArtifact, language: str) -> str:
    entry = _history_entry(archived_plan=archived_plan, language=language)
    if language == "en-US":
        header = "# Change History Index\n\nRecords completed plan archives for future lookup.\n\n## Index\n\n"
        placeholder = "No archived plans yet."
    else:
        header = "# 变更历史索引\n\n记录已归档的方案，便于后续查询。\n\n## 索引\n\n"
        placeholder = "当前暂无已归档方案。"

    body = existing
    if "## Index" in existing or "## 索引" in existing:
        _, _, remainder = existing.partition("## Index\n\n" if language == "en-US" else "## 索引\n\n")
        body = remainder
    lines = [line for line in body.splitlines() if line.strip() and line.strip() != placeholder]
    lines = [line for line in lines if archived_plan.plan_id not in line]
    lines.insert(0, entry)
    return header + "\n".join(lines) + "\n"


def _history_entry(*, archived_plan: PlanArtifact, language: str) -> str:
    date_text = datetime.now().strftime("%Y-%m-%d")
    link = archived_plan.path.removeprefix(".sopify-skills/history/")
    if language == "en-US":
        return f"- `{date_text}` [`{archived_plan.plan_id}`]({link}/) - {archived_plan.level} - {archived_plan.title}"
    return f"- `{date_text}` [`{archived_plan.plan_id}`]({link}/) - {archived_plan.level} - {archived_plan.title}"


def _history_index_stub(language: str) -> str:
    if language == "en-US":
        return "# Change History Index\n\nRecords completed plan archives for future lookup.\n\n## Index\n\nNo archived plans yet.\n"
    return "# 变更历史索引\n\n记录已归档的方案，便于后续查询。\n\n## 索引\n\n当前暂无已归档方案。\n"


def _text(language: str, key: str, **kwargs: str) -> str:
    messages = {
        "en-US": {
            "no_archive_subject": "No archive subject is available",
            "missing_plan_dir": "Archive subject directory is missing: {path}",
            "metadata_missing": "Archive subject is missing required metadata",
            "metadata_mismatch": "Plan metadata mismatch: state plan_id={state_plan_id} but document plan_id={document_plan_id}",
            "archive_exists": "Archive target already exists: {path}",
            "archived": "Plan archived to {path}",
            "state_cleared": "Active runtime state cleared",
            "registry_sync_failed": "The plan was archived, but the plan registry could not be updated automatically",
            "knowledge_sync_updated": "Detected knowledge_sync document updates after plan creation: {paths}",
            "knowledge_sync_review_warning": "Knowledge_sync review reminder: review items were not updated after plan creation: {paths}",
            "knowledge_sync_required_blocked": "Archive blocked: required knowledge_sync documents were not updated after plan creation: {paths}",
        },
        "zh-CN": {
            "no_archive_subject": "当前没有可归档的 archive subject",
            "missing_plan_dir": "归档主体目录不存在：{path}",
            "metadata_missing": "归档主体缺少必需 metadata",
            "metadata_mismatch": "方案元数据不一致：state plan_id={state_plan_id}，文档 plan_id={document_plan_id}",
            "archive_exists": "归档目标已存在：{path}",
            "archived": "方案已归档到 {path}",
            "state_cleared": "已清理活动运行时状态",
            "registry_sync_failed": "plan 已归档，但 plan registry 未能自动同步更新",
            "knowledge_sync_updated": "已检测到 plan 创建后的 knowledge_sync 文档更新：{paths}",
            "knowledge_sync_review_warning": "knowledge_sync 复核提醒：以下 review 文档在 plan 创建后尚未更新：{paths}",
            "knowledge_sync_required_blocked": "归档被阻断：以下 knowledge_sync.required 文档在 plan 创建后尚未更新：{paths}",
        },
    }
    locale = "en-US" if language == "en-US" else "zh-CN"
    template = messages[locale][key]
    return template.format(**kwargs)
