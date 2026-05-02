"""Action/Effect Boundary — pre-route authorization gate (ADR-017 P0).

Validator 是唯一授权者。Host LLM 生成 ActionProposal，Validator 基于
ActionProposal + ValidationContext 输出统一 ValidationDecision。

P0 只激活 consult_readonly route override；side-effecting action 做最小
evidence proof 授权但不接管路由；未知 action 回落现有 Router。
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
        "confirm_execute",
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

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "action_type": self.action_type,
            "side_effect": self.side_effect,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }
        if self.archive_subject is not None:
            payload["archive_subject"] = self.archive_subject.to_dict()
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

        return cls(
            action_type=action_type,
            side_effect=side_effect,
            confidence=confidence,
            evidence=evidence,
            archive_subject=archive_subject,
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
