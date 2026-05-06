"""Action/Effect Boundary — pre-route authorization gate (ADR-017).

Validator 是唯一授权者。Host LLM 生成 ActionProposal，Validator 基于
ActionProposal + ValidationContext 输出统一 ValidationDecision。

ExecutionAuthorizationReceipt 是 execute_existing_plan 授权通过后生成的
机器事实（P1.5-B normative）。Receipt 持久化到 authoritative runtime state，
Validator 从 state 读取已有 receipt 做 stale 检测。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

# -- Action types recognized by P0 -------------------------------------------

ACTION_TYPES = (
    "consult_readonly",
    "archive_plan",
    "propose_plan",
    "execute_existing_plan",
    "modify_files",
    "checkpoint_response",
    "cancel_flow",
)

SIDE_EFFECTS = (
    "none",
    "write_runtime_state",
    "write_plan_package",
    "write_files",
    "execute_command",
)

CONFIDENCE_LEVELS = ("high", "medium", "low")
ARCHIVE_SUBJECT_REF_KINDS = ("plan_id", "path", "current_plan")
ARCHIVE_SUBJECT_SOURCES = ("host_explicit", "current_plan")
ARCHIVE_BLOCKING_HOST_ACTIONS = frozenset(
    {
        "answer_questions",
        "confirm_decision",
        "resolve_state_conflict",
    }
)

# Side effects that require positive evidence proof to authorize.
_SIDE_EFFECTING = frozenset(SIDE_EFFECTS) - {"none"}

# -- Validation decision codes ------------------------------------------------

DECISION_AUTHORIZE = "authorize"
DECISION_DOWNGRADE = "downgrade"
DECISION_REJECT = "reject"
DECISION_FALLBACK_ROUTER = "fallback_router"


# -- Data contracts -----------------------------------------------------------


@dataclass(frozen=True)
class PlanSubjectProposal:
    """Action-specific subject payload for execute_existing_plan.

    Minimal field block: workspace-relative plan directory path + content digest.
    Follows the same pattern as ArchiveSubjectProposal — scene-specific, not generic.
    """

    subject_ref: str  # workspace-relative plan directory path
    revision_digest: str  # SHA-256 hex of plan.md content

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_ref": self.subject_ref,
            "revision_digest": self.revision_digest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanSubjectProposal":
        subject_ref = str(data.get("subject_ref") or "").strip()
        revision_digest = str(data.get("revision_digest") or "").strip()
        if not subject_ref:
            raise ValueError("plan_subject.subject_ref is required")
        if not revision_digest:
            raise ValueError("plan_subject.revision_digest is required")
        return cls(subject_ref=subject_ref, revision_digest=revision_digest)


@dataclass(frozen=True)
class ArchiveSubjectProposal:
    """Action-specific payload for archive_plan.

    This is intentionally not a generic ActionProposal schema expansion.
    """

    ref_kind: str
    ref_value: str = ""
    source: str = "host_explicit"
    allow_current_plan_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_kind": self.ref_kind,
            "ref_value": self.ref_value,
            "source": self.source,
            "allow_current_plan_fallback": self.allow_current_plan_fallback,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArchiveSubjectProposal":
        ref_kind = str(data.get("ref_kind") or "").strip()
        ref_value = str(data.get("ref_value") or "").strip()
        source = str(data.get("source") or "").strip()
        allow_current_plan_fallback = bool(data.get("allow_current_plan_fallback", False))

        if ref_kind not in ARCHIVE_SUBJECT_REF_KINDS:
            raise ValueError(f"unknown archive_subject.ref_kind: {ref_kind!r}")
        if source not in ARCHIVE_SUBJECT_SOURCES:
            raise ValueError(f"unknown archive_subject.source: {source!r}")
        if ref_kind in {"plan_id", "path"}:
            if not ref_value:
                raise ValueError("archive_subject.ref_value is required for plan_id/path")
            if source != "host_explicit":
                raise ValueError("archive_subject.source must be host_explicit for plan_id/path")
            if allow_current_plan_fallback:
                raise ValueError("allow_current_plan_fallback is only valid for current_plan")
        if ref_kind == "current_plan":
            if ref_value:
                raise ValueError("archive_subject.ref_value must be empty for current_plan")
            if source != "current_plan":
                raise ValueError("archive_subject.source must be current_plan for current_plan fallback")
            if not allow_current_plan_fallback:
                raise ValueError("allow_current_plan_fallback must be true for current_plan")
        return cls(
            ref_kind=ref_kind,
            ref_value=ref_value,
            source=source,
            allow_current_plan_fallback=allow_current_plan_fallback,
        )


@dataclass(frozen=True)
class ActionProposal:
    """Host-generated structured intent (proposal source, not authorizer)."""

    action_type: str
    side_effect: str = "none"
    confidence: str = "high"
    evidence: tuple[str, ...] = ()
    archive_subject: ArchiveSubjectProposal | None = None
    plan_subject: PlanSubjectProposal | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "action_type": self.action_type,
            "side_effect": self.side_effect,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }
        if self.archive_subject is not None:
            payload["archive_subject"] = self.archive_subject.to_dict()
        if self.plan_subject is not None:
            payload["plan_subject"] = self.plan_subject.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionProposal":
        action_type = str(data.get("action_type") or "").strip()
        side_effect = str(data.get("side_effect") or "none")
        confidence = str(data.get("confidence") or "high")

        # Missing/empty action_type is invalid — fail-close.
        if not action_type:
            raise ValueError("action_type is required and must not be empty")
        # Strict enum validation — reject unknown values at parse time.
        if action_type not in ACTION_TYPES:
            raise ValueError(f"unknown action_type: {action_type!r}")
        if side_effect not in SIDE_EFFECTS:
            raise ValueError(f"unknown side_effect: {side_effect!r}")
        if confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"unknown confidence: {confidence!r}")

        # Evidence must be a list of strings, not a bare string.
        raw_evidence = data.get("evidence")
        if raw_evidence is None:
            evidence: tuple[str, ...] = ()
        elif isinstance(raw_evidence, list):
            if not all(isinstance(e, str) for e in raw_evidence):
                raise ValueError("evidence must be a list of strings")
            evidence = tuple(raw_evidence)
        else:
            raise ValueError(f"evidence must be a list, got {type(raw_evidence).__name__}")

        raw_archive_subject = data.get("archive_subject")
        archive_subject: ArchiveSubjectProposal | None = None
        if action_type == "archive_plan":
            if raw_archive_subject is None:
                raise ValueError("archive_subject is required for archive_plan")
            if not isinstance(raw_archive_subject, dict):
                raise ValueError("archive_subject must be an object")
            archive_subject = ArchiveSubjectProposal.from_dict(raw_archive_subject)
        elif raw_archive_subject is not None:
            raise ValueError("archive_subject is only valid for archive_plan")

        # plan_subject: optional for execute_existing_plan, rejected at validator if missing.
        # Parse-layer allows None — validator does the fail-closed check.
        raw_plan_subject = data.get("plan_subject")
        plan_subject: PlanSubjectProposal | None = None
        if raw_plan_subject is not None:
            if action_type != "execute_existing_plan":
                raise ValueError("plan_subject is only valid for execute_existing_plan")
            if not isinstance(raw_plan_subject, dict):
                raise ValueError("plan_subject must be an object")
            plan_subject = PlanSubjectProposal.from_dict(raw_plan_subject)

        # proposal_id: engine-generated only, host MUST NOT supply.
        if data.get("proposal_id") is not None:
            raise ValueError("proposal_id must not be supplied by host — engine generates it")

        return cls(
            action_type=action_type,
            side_effect=side_effect,
            confidence=confidence,
            evidence=evidence,
            archive_subject=archive_subject,
            plan_subject=plan_subject,
        )


# -- Execution Authorization Receipt (ADR-017 / P1.5-B normative) -----------


def generate_proposal_id(
    action_type: str,
    side_effect: str,
    subject_ref: str,
    revision_digest: str,
    request_hash: str,
) -> str:
    """Deterministic action_proposal_id — same inputs always produce same ID.

    Engine-generated only; host MUST NOT supply this value.
    """
    payload = json.dumps(
        {
            "action_type": action_type,
            "side_effect": side_effect,
            "subject_ref": subject_ref,
            "revision_digest": revision_digest,
            "request_hash": request_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _receipt_fingerprint(
    plan_id: str,
    plan_path: str,
    plan_revision_digest: str,
    gate_status: str,
    action_proposal_id: str,
) -> str:
    """Deterministic fingerprint per ADR-017 spec."""
    payload = json.dumps(
        {
            "plan_id": plan_id,
            "plan_path": plan_path,
            "plan_revision_digest": plan_revision_digest,
            "gate_status": gate_status,
            "action_proposal_id": action_proposal_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutionAuthorizationReceipt:
    """Machine truth: who authorized this execute_existing_plan, on which revision.

    Fields strictly follow ADR-017 normative spec (8 fields, no more, no less).
    Persisted in authoritative runtime state; Validator reads it for stale detection.
    """

    plan_id: str
    plan_path: str
    plan_revision_digest: str  # plan subject specialization of revision_digest
    gate_status: str
    action_proposal_id: str
    authorization_source: dict[str, str]  # { kind: "request_hash", request_sha1: str }
    fingerprint: str
    authorized_at: str  # ISO 8601 UTC

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_path": self.plan_path,
            "plan_revision_digest": self.plan_revision_digest,
            "gate_status": self.gate_status,
            "action_proposal_id": self.action_proposal_id,
            "authorization_source": dict(self.authorization_source),
            "fingerprint": self.fingerprint,
            "authorized_at": self.authorized_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionAuthorizationReceipt":
        plan_id = str(data.get("plan_id") or "")
        plan_path = str(data.get("plan_path") or "")
        plan_revision_digest = str(data.get("plan_revision_digest") or "")
        gate_status = str(data.get("gate_status") or "")
        action_proposal_id = str(data.get("action_proposal_id") or "")
        raw_source = data.get("authorization_source")
        if not isinstance(raw_source, Mapping):
            raw_source = {}
        authorization_source = {str(k): str(v) for k, v in raw_source.items()}
        fingerprint = str(data.get("fingerprint") or "")
        authorized_at = str(data.get("authorized_at") or "")
        return cls(
            plan_id=plan_id,
            plan_path=plan_path,
            plan_revision_digest=plan_revision_digest,
            gate_status=gate_status,
            action_proposal_id=action_proposal_id,
            authorization_source=authorization_source,
            fingerprint=fingerprint,
            authorized_at=authorized_at,
        )

    @classmethod
    def create(
        cls,
        plan_path: str,
        plan_revision_digest: str,
        gate_status: str,
        action_proposal_id: str,
        request_sha1: str,
    ) -> "ExecutionAuthorizationReceipt":
        """Factory: generate receipt with deterministic fingerprint and UTC timestamp."""
        # plan_id = last component of plan_path (directory name)
        plan_id = Path(plan_path).name
        fingerprint = _receipt_fingerprint(
            plan_id=plan_id,
            plan_path=plan_path,
            plan_revision_digest=plan_revision_digest,
            gate_status=gate_status,
            action_proposal_id=action_proposal_id,
        )
        return cls(
            plan_id=plan_id,
            plan_path=plan_path,
            plan_revision_digest=plan_revision_digest,
            gate_status=gate_status,
            action_proposal_id=action_proposal_id,
            authorization_source={"kind": "request_hash", "request_sha1": request_sha1},
            fingerprint=fingerprint,
            authorized_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )


@dataclass(frozen=True)
class ValidationContext:
    """Read-only view projected from context_snapshot / current_handoff / current_run.

    不新造完整模型；只取 Validator 需要的最小字段。
    """

    checkpoint_kind: Optional[str] = None
    checkpoint_id: Optional[str] = None
    stage: Optional[str] = None
    required_host_action: Optional[str] = None
    current_plan_path: Optional[str] = None
    state_conflict: bool = False
    workspace_root: Optional[str] = None  # project root for file-level checks
    # P1.5-B: receipt from state for stale detection.
    existing_receipt: Optional[Mapping[str, Any]] = None
    current_gate_status: Optional[str] = None


@dataclass(frozen=True)
class ValidationDecision:
    """Validator 统一输出。"""

    decision: str  # authorize | downgrade | reject | fallback_router
    resolved_action: str
    resolved_side_effect: str
    route_override: Optional[str] = None  # "consult" or None
    reason_code: str = ""
    artifacts: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "resolved_action": self.resolved_action,
            "resolved_side_effect": self.resolved_side_effect,
            "route_override": self.route_override,
            "reason_code": self.reason_code,
            "artifacts": dict(self.artifacts),
        }


# -- Validator ----------------------------------------------------------------


class ActionValidator:
    """Pre-write authorization gate (Verify-A).

    P0 硬规则：
    - consult_readonly + none → authorize, route_override=consult
    - side-effecting + evidence 通过 → authorize, route_override=None (Router 继续)
    - side-effecting + evidence 不足/low confidence → downgrade consult_readonly
    - 未知 action → fallback_router
    """

    def validate(
        self,
        proposal: ActionProposal,
        context: ValidationContext,
    ) -> ValidationDecision:
        # Unknown action type → fall back to existing Router.
        if proposal.action_type not in ACTION_TYPES:
            return ValidationDecision(
                decision=DECISION_FALLBACK_ROUTER,
                resolved_action=proposal.action_type,
                resolved_side_effect=proposal.side_effect,
                route_override=None,
                reason_code="validator.unknown_action_type",
            )

        # Unknown side_effect → fail-close: downgrade to consult.
        if proposal.side_effect not in SIDE_EFFECTS:
            return ValidationDecision(
                decision=DECISION_DOWNGRADE,
                resolved_action="consult_readonly",
                resolved_side_effect="none",
                route_override="consult",
                reason_code="validator.unknown_side_effect_downgrade",
            )

        # consult_readonly + none: always authorize, regardless of confidence.
        if proposal.action_type == "consult_readonly" and proposal.side_effect == "none":
            return ValidationDecision(
                decision=DECISION_AUTHORIZE,
                resolved_action="consult_readonly",
                resolved_side_effect="none",
                route_override="consult",
                reason_code="validator.consult_readonly_authorized",
            )

        # consult_readonly with unexpected side_effect → treat as side-effecting.
        # (Host claimed readonly but declared write — evidence must prove it.)

        # Side-effecting actions: require confidence + evidence proof.
        if proposal.side_effect in _SIDE_EFFECTING:
            if not _evidence_proves_write_intent(proposal):
                return ValidationDecision(
                    decision=DECISION_DOWNGRADE,
                    resolved_action="consult_readonly",
                    resolved_side_effect="none",
                    route_override="consult",
                    reason_code="validator.insufficient_evidence_downgrade",
                )
            if proposal.action_type == "archive_plan":
                if context.state_conflict:
                    return ValidationDecision(
                        decision=DECISION_DOWNGRADE,
                        resolved_action="consult_readonly",
                        resolved_side_effect="none",
                        route_override="consult",
                        reason_code="validator.archive_plan_blocked_by_state_conflict",
                    )
                if (context.required_host_action or "").strip() in ARCHIVE_BLOCKING_HOST_ACTIONS:
                    return ValidationDecision(
                        decision=DECISION_DOWNGRADE,
                        resolved_action="consult_readonly",
                        resolved_side_effect="none",
                        route_override="consult",
                        reason_code="validator.archive_plan_blocked_by_checkpoint",
                    )
                archive_subject = proposal.archive_subject
                if archive_subject is None:
                    return ValidationDecision(
                        decision=DECISION_DOWNGRADE,
                        resolved_action="consult_readonly",
                        resolved_side_effect="none",
                        route_override="consult",
                        reason_code="validator.archive_plan_missing_subject",
                    )
                if archive_subject.ref_kind == "current_plan" and not context.current_plan_path:
                    return ValidationDecision(
                        decision=DECISION_DOWNGRADE,
                        resolved_action="consult_readonly",
                        resolved_side_effect="none",
                        route_override="consult",
                        reason_code="validator.archive_plan_current_plan_unavailable",
                    )
                return ValidationDecision(
                    decision=DECISION_AUTHORIZE,
                    resolved_action="archive_plan",
                    resolved_side_effect="write_files",
                    route_override="archive_lifecycle",
                    reason_code="validator.archive_plan_authorized",
                    artifacts={
                        "archive_subject": archive_subject.to_dict(),
                    },
                )
            if proposal.action_type == "execute_existing_plan":
                decision = _validate_plan_subject(proposal, context)
                if decision is not None:
                    return decision
                # P1.5-B stale receipt detection: if state has an existing receipt,
                # compare its fields against current facts. Reject if stale.
                stale_decision = _check_stale_receipt(proposal, context)
                if stale_decision is not None:
                    return stale_decision
            # Evidence sufficient → authorize, let Router decide route.
            return ValidationDecision(
                decision=DECISION_AUTHORIZE,
                resolved_action=proposal.action_type,
                resolved_side_effect=proposal.side_effect,
                route_override=None,
                reason_code="validator.side_effect_authorized",
            )

        # Non-side-effecting recognized action (e.g. cancel_flow with none).
        # Authorize and let Router handle.
        return ValidationDecision(
            decision=DECISION_AUTHORIZE,
            resolved_action=proposal.action_type,
            resolved_side_effect=proposal.side_effect,
            route_override=None,
            reason_code="validator.action_authorized",
        )


def _evidence_proves_write_intent(proposal: ActionProposal) -> bool:
    """P0 最小 evidence proof: confidence 不能是 low，且 evidence 非空。

    判定标准是"evidence 能否正向证明写入意图"，不列举具体话术词表。
    fail-close: 允许误降级为 consult，不允许误升级为写入。
    """
    if proposal.confidence == "low":
        return False
    if not proposal.evidence:
        return False
    return True


def _validate_plan_subject(
    proposal: ActionProposal,
    context: ValidationContext,
) -> ValidationDecision | None:
    """P1 subject admission for execute_existing_plan.

    Returns a DECISION_REJECT if plan_subject is missing/invalid, or None to
    continue with normal authorization flow.
    """
    plan_subject = proposal.plan_subject
    if plan_subject is None:
        return ValidationDecision(
            decision=DECISION_REJECT,
            resolved_action="execute_existing_plan",
            resolved_side_effect=proposal.side_effect,
            route_override=None,
            reason_code="validator.execute_existing_plan_missing_subject",
        )
    if not context.workspace_root:
        return ValidationDecision(
            decision=DECISION_REJECT,
            resolved_action="execute_existing_plan",
            resolved_side_effect=proposal.side_effect,
            route_override=None,
            reason_code="validator.execute_existing_plan_no_workspace",
        )
    # subject_ref boundary: reject absolute path, traversal, non-plan prefix.
    ref = plan_subject.subject_ref
    if os.path.isabs(ref):
        return ValidationDecision(
            decision=DECISION_REJECT,
            resolved_action="execute_existing_plan",
            resolved_side_effect=proposal.side_effect,
            route_override=None,
            reason_code="validator.execute_existing_plan_invalid_subject_ref",
        )
    if ".." in Path(ref).parts:
        return ValidationDecision(
            decision=DECISION_REJECT,
            resolved_action="execute_existing_plan",
            resolved_side_effect=proposal.side_effect,
            route_override=None,
            reason_code="validator.execute_existing_plan_invalid_subject_ref",
        )
    _PLAN_PREFIX = ".sopify-skills/plan/"
    normalized = ref.replace("\\", "/")
    if not normalized.startswith(_PLAN_PREFIX):
        return ValidationDecision(
            decision=DECISION_REJECT,
            resolved_action="execute_existing_plan",
            resolved_side_effect=proposal.side_effect,
            route_override=None,
            reason_code="validator.execute_existing_plan_invalid_subject_ref",
        )
    plan_dir = Path(context.workspace_root) / plan_subject.subject_ref
    plan_file = plan_dir / "plan.md"
    if not plan_file.is_file():
        return ValidationDecision(
            decision=DECISION_REJECT,
            resolved_action="execute_existing_plan",
            resolved_side_effect=proposal.side_effect,
            route_override=None,
            reason_code="validator.execute_existing_plan_subject_not_found",
        )
    actual_digest = hashlib.sha256(plan_file.read_bytes()).hexdigest()
    if actual_digest != plan_subject.revision_digest:
        return ValidationDecision(
            decision=DECISION_REJECT,
            resolved_action="execute_existing_plan",
            resolved_side_effect=proposal.side_effect,
            route_override=None,
            reason_code="validator.execute_existing_plan_digest_mismatch",
        )
    return None


def _check_stale_receipt(
    proposal: ActionProposal,
    context: ValidationContext,
) -> ValidationDecision | None:
    """P1.5-B stale receipt detection for execute_existing_plan.

    If state has an existing receipt, validate:
    1. Receipt integrity: required fields present (fail-closed on malformed)
    2. Binding: receipt must reference the same plan as the current proposal
    3. Freshness: receipt facts must match current filesystem / gate truth

    Any violation → DECISION_REJECT (no consult downgrade, no auto re-authorize).
    No receipt in state → None (first-time authorization, proceed normally).
    """
    receipt_data = context.existing_receipt
    if receipt_data is None:
        return None

    plan_subject = proposal.plan_subject
    if plan_subject is None:
        return None  # already caught by _validate_plan_subject

    _REQUIRED_STR_FIELDS = (
        "plan_id", "plan_path", "plan_revision_digest", "gate_status",
        "action_proposal_id", "fingerprint", "authorized_at",
    )

    def _reject(reason_code: str) -> ValidationDecision:
        return ValidationDecision(
            decision=DECISION_REJECT,
            resolved_action="execute_existing_plan",
            resolved_side_effect=proposal.side_effect,
            route_override=None,
            reason_code=reason_code,
        )

    # 1. Integrity: fail-closed on malformed receipt (all 8 normative fields).
    for field_name in _REQUIRED_STR_FIELDS:
        if not str(receipt_data.get(field_name) or "").strip():
            return _reject("validator.execute_existing_plan_stale_receipt_malformed")
    auth_source = receipt_data.get("authorization_source")
    if (
        not isinstance(auth_source, Mapping)
        or auth_source.get("kind") != "request_hash"
        or not isinstance(auth_source.get("request_sha1"), str)
        or not auth_source["request_sha1"].strip()
    ):
        return _reject("validator.execute_existing_plan_stale_receipt_malformed")

    receipt_plan_path = str(receipt_data["plan_path"])
    receipt_digest = str(receipt_data["plan_revision_digest"])
    receipt_gate_status = str(receipt_data["gate_status"])

    # 2. Binding: receipt must reference the same plan as the current proposal.
    if receipt_plan_path != plan_subject.subject_ref:
        return _reject("validator.execute_existing_plan_stale_receipt_plan_mismatch")

    # 3a. Freshness — plan path still exists on filesystem.
    if context.workspace_root:
        plan_dir = Path(context.workspace_root) / receipt_plan_path
        plan_file = plan_dir / "plan.md"
        if not plan_file.is_file():
            return _reject("validator.execute_existing_plan_stale_receipt_path_gone")
        # 3b. Freshness — plan content digest matches receipt's recorded value.
        actual_digest = hashlib.sha256(plan_file.read_bytes()).hexdigest()
        if actual_digest != receipt_digest:
            return _reject("validator.execute_existing_plan_stale_receipt_digest")

    # 3c. Freshness — gate_status matches current ExecutionGate truth.
    current_gate = str(context.current_gate_status or "").strip()
    if not current_gate:
        # Receipt exists but no current gate truth — state inconsistency, fail-closed.
        return _reject("validator.execute_existing_plan_stale_receipt_gate_missing")
    if receipt_gate_status != current_gate:
        return _reject("validator.execute_existing_plan_stale_receipt_gate")

    return None


# -- Deterministic fallback adapter -------------------------------------------


def resolve_action_proposal(
    raw_json: Optional[dict[str, Any]],
) -> Optional[ActionProposal]:
    """Parse raw JSON into ActionProposal, or None if absent/invalid.

    None 表示无 proposal — engine 应回落现有 Router。
    """
    if raw_json is None:
        return None
    try:
        return ActionProposal.from_dict(raw_json)
    except (TypeError, KeyError, ValueError, AttributeError):
        return None
