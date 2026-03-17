"""Top-level orchestration for Sopify runtime."""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path
from typing import Any, Mapping, Optional

from .config import load_runtime_config
from .context_recovery import recover_context
from .decision import build_decision_state, confirm_decision, consume_decision, parse_decision_response, stale_decision
from .handoff import build_runtime_handoff
from .kb import bootstrap_kb, ensure_blueprint_scaffold
from .models import DecisionState, KbArtifact, PlanArtifact, ReplayEvent, RouteDecision, RunState, RuntimeHandoff, RuntimeResult, SkillMeta
from .plan_scaffold import create_plan_scaffold
from .replay import ReplayWriter
from .router import Router
from .skill_registry import SkillRegistry
from .skill_runner import SkillExecutionError, run_runtime_skill
from .state import StateStore, iso_now


def run_runtime(
    user_input: str,
    *,
    workspace_root: str | Path = ".",
    global_config_path: str | Path | None = None,
    user_home: Path | None = None,
    runtime_payloads: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> RuntimeResult:
    """Run the Sopify runtime pipeline for a single input.

    Args:
        user_input: Raw user input.
        workspace_root: Project root.
        global_config_path: Optional global config override.
        user_home: Optional home override for tests.
        runtime_payloads: Optional runtime-skill payload map keyed by skill id.

    Returns:
        Standardized runtime result.
    """
    config = load_runtime_config(workspace_root, global_config_path=global_config_path)
    state_store = StateStore(config)
    state_store.ensure()
    kb_artifact: KbArtifact | None = bootstrap_kb(config)

    skills = SkillRegistry(config, user_home=user_home).discover()
    router = Router(config, state_store=state_store)
    classified_route = router.classify(user_input, skills=skills)
    recovered = recover_context(classified_route, config=config, state_store=state_store)

    notes: list[str] = []
    plan_artifact: PlanArtifact | None = None
    skill_result: Mapping[str, Any] | None = None
    replay_session_dir: str | None = None
    handoff: RuntimeHandoff | None = None
    replay_events: list[ReplayEvent] = []
    effective_route = classified_route

    current_decision = state_store.get_current_decision()
    if (
        current_decision is not None
        and effective_route.route_name in {"plan_only", "workflow", "light_iterate"}
        and effective_route.route_name not in {"decision_pending", "decision_resume"}
    ):
        # A new planning request supersedes the previous pending checkpoint.
        stale_state = stale_decision(current_decision)
        state_store.set_current_decision(stale_state)
        state_store.clear_current_decision()
        notes.append(f"Superseded pending decision checkpoint: {stale_state.decision_id}")
        current_decision = None

    if effective_route.route_name == "cancel_active":
        state_store.reset_active_flow()
        notes.append("Active flow cleared")
    elif effective_route.route_name == "decision_resume":
        effective_route, plan_artifact, decision_notes, kb_artifact = _handle_decision_resume(
            effective_route,
            state_store=state_store,
            config=config,
            kb_artifact=kb_artifact,
        )
        notes.extend(decision_notes)
    elif effective_route.should_create_plan:
        kb_artifact = _merge_kb_artifacts(kb_artifact, ensure_blueprint_scaffold(config), config=config)
        pending_decision = build_decision_state(effective_route, config=config)
        if pending_decision is not None:
            state_store.set_current_decision(pending_decision)
            state_store.clear_current_plan()
            state_store.set_current_run(_make_decision_run_state(effective_route, pending_decision))
            effective_route = _decision_pending_route(effective_route, reason="Detected an explicit design split that requires confirmation")
            notes.append(f"Decision checkpoint created: {pending_decision.decision_id}")
        else:
            level = effective_route.plan_level or _default_plan_level(effective_route)
            plan_artifact = create_plan_scaffold(effective_route.request_text, config=config, level=level)
            run_state = _make_run_state(effective_route, plan_artifact)
            state_store.set_current_plan(plan_artifact)
            state_store.set_current_run(run_state)
            notes.append(f"Plan scaffold created at {plan_artifact.path}")
    elif effective_route.route_name in {"resume_active", "exec_plan"}:
        updated_run = state_store.update_active_run(stage="develop_pending")
        if updated_run is None and recovered.current_plan is not None:
            synthetic_run = _make_run_state(effective_route, recovered.current_plan)
            state_store.set_current_run(synthetic_run)
            notes.append("Synthetic active run created from current plan")
        elif updated_run is None:
            notes.append("No active plan available to resume")
        else:
            notes.append("Active run resumed")

    state_store.set_last_route(effective_route)

    if effective_route.runtime_skill_id is not None:
        skill = _find_skill(skills, effective_route.runtime_skill_id)
        payload = dict((runtime_payloads or {}).get(effective_route.runtime_skill_id, {}))
        if skill is None:
            notes.append(f"Runtime skill not found: {effective_route.runtime_skill_id}")
        elif not payload:
            notes.append(f"Runtime payload missing for skill: {effective_route.runtime_skill_id}")
        else:
            try:
                skill_result = run_runtime_skill(skill, payload=payload)
            except SkillExecutionError as exc:
                notes.append(str(exc))

    if effective_route.capture_mode != "off":
        writer = ReplayWriter(config)
        run_state = state_store.get_current_run() or recovered.current_run
        run_id = run_state.run_id if run_state is not None else _make_run_id(effective_route.request_text)
        replay_event = ReplayEvent(
            ts=iso_now(),
            phase=_phase_for_route(effective_route),
            intent=effective_route.request_text or effective_route.route_name,
            action=f"route:{effective_route.route_name}",
            key_output=(plan_artifact.summary if plan_artifact is not None else effective_route.reason),
            decision_reason=effective_route.reason,
            result="success",
            artifacts=tuple(plan_artifact.files if plan_artifact is not None else ()),
        )
        replay_events.append(replay_event)
        session_dir = writer.append_event(run_id, replay_event)
        writer.render_documents(
            run_id,
            run_state=state_store.get_current_run(),
            route=effective_route,
            plan_artifact=plan_artifact or recovered.current_plan,
            events=replay_events,
        )
        replay_session_dir = str(session_dir.relative_to(config.workspace_root))

    if effective_route.route_name == "cancel_active":
        handoff = None
    else:
        current_run = state_store.get_current_run() or recovered.current_run
        current_plan = plan_artifact or state_store.get_current_plan() or recovered.current_plan
        handoff = build_runtime_handoff(
            decision=effective_route,
            run_id=(current_run.run_id if current_run is not None else _make_run_id(effective_route.request_text)),
            current_plan=current_plan,
            kb_artifact=kb_artifact,
            replay_session_dir=replay_session_dir,
            skill_result=skill_result,
            current_decision=state_store.get_current_decision(),
            notes=notes,
        )
        if handoff is not None:
            state_store.set_current_handoff(handoff)
        else:
            state_store.clear_current_handoff()

    latest_context = recover_context(effective_route, config=config, state_store=state_store)
    return RuntimeResult(
        route=effective_route,
        recovered_context=latest_context,
        discovered_skills=skills,
        kb_artifact=kb_artifact,
        plan_artifact=plan_artifact,
        skill_result=skill_result,
        replay_session_dir=replay_session_dir,
        handoff=handoff,
        notes=tuple(notes),
    )


def _default_plan_level(decision: RouteDecision) -> str:
    if decision.complexity == "medium":
        return "light"
    return "standard"


def _make_run_state(decision: RouteDecision, plan_artifact: PlanArtifact) -> RunState:
    now = iso_now()
    return RunState(
        run_id=_make_run_id(decision.request_text),
        status="active",
        stage="plan_ready",
        route_name=decision.route_name,
        title=plan_artifact.title,
        created_at=now,
        updated_at=now,
        plan_id=plan_artifact.plan_id,
        plan_path=plan_artifact.path,
    )


def _make_decision_run_state(decision: RouteDecision, decision_state: DecisionState) -> RunState:
    now = iso_now()
    return RunState(
        run_id=_make_run_id(decision.request_text),
        status="active",
        stage="decision_pending",
        route_name=decision_state.resume_route or decision.route_name,
        title=decision_state.question,
        created_at=now,
        updated_at=now,
        plan_id=None,
        plan_path=None,
    )


def _make_run_id(request_text: str) -> str:
    timestamp = iso_now().replace(":", "").replace("-", "")[:15]
    digest = sha1(request_text.encode("utf-8")).hexdigest()[:6]
    return f"{timestamp}_{digest}"


def _find_skill(skills: tuple[SkillMeta, ...], skill_id: str) -> SkillMeta | None:
    for skill in skills:
        if skill.skill_id == skill_id:
            return skill
    return None


def _phase_for_route(decision: RouteDecision) -> str:
    if decision.route_name in {"plan_only", "workflow", "light_iterate", "decision_pending", "decision_resume"}:
        return "design"
    if decision.route_name in {"resume_active", "exec_plan", "quick_fix"}:
        return "develop"
    if decision.route_name == "compare":
        return "analysis"
    return "analysis"


def _handle_decision_resume(
    decision: RouteDecision,
    *,
    state_store: StateStore,
    config: RuntimeConfig,
    kb_artifact: KbArtifact | None,
) -> tuple[RouteDecision, PlanArtifact | None, list[str], KbArtifact | None]:
    current_decision = state_store.get_current_decision()
    notes: list[str] = []
    if current_decision is None:
        return (
            _decision_pending_route(decision, reason="No pending decision checkpoint was found"),
            None,
            ["No pending decision checkpoint to resume"],
            kb_artifact,
        )

    response = parse_decision_response(current_decision, decision.request_text)
    if response.action == "status":
        return (_decision_pending_route(decision, reason="Decision checkpoint is still waiting for confirmation"), None, notes, kb_artifact)

    if response.action == "cancel":
        state_store.reset_active_flow()
        return (
            RouteDecision(
                route_name="cancel_active",
                request_text=decision.request_text,
                reason="Decision checkpoint cancelled by user",
                complexity="simple",
                should_recover_context=True,
            ),
            None,
            ["Decision checkpoint cancelled"],
            kb_artifact,
        )

    if response.action == "invalid":
        notes.append(response.message or "Invalid decision response")
        return (_decision_pending_route(decision, reason="Decision checkpoint still requires a valid selection"), None, notes, kb_artifact)

    if response.action == "choose":
        current_decision = confirm_decision(
            current_decision,
            option_id=response.option_id or "",
            source=response.source,
            raw_input=decision.request_text,
        )
        state_store.set_current_decision(current_decision)
        notes.append(f"Decision confirmed: {current_decision.selected_option_id}")

    if current_decision.status != "confirmed" or current_decision.selection is None:
        notes.append("Decision checkpoint has not reached a confirmed state yet")
        return (_decision_pending_route(decision, reason="Decision checkpoint is still pending"), None, notes, kb_artifact)

    kb_artifact = _merge_kb_artifacts(kb_artifact, ensure_blueprint_scaffold(config), config=config)
    level = current_decision.requested_plan_level or _default_plan_level(
        RouteDecision(
            route_name=current_decision.resume_route or "plan_only",
            request_text=current_decision.request_text,
            reason="Recovered decision checkpoint",
            complexity="complex",
        )
    )
    plan_artifact = create_plan_scaffold(
        current_decision.request_text,
        config=config,
        level=level,
        decision_state=current_decision,
    )
    state_store.set_current_plan(plan_artifact)
    state_store.set_current_run(
        RunState(
            run_id=_make_run_id(current_decision.request_text),
            status="active",
            stage="plan_ready",
            route_name=current_decision.resume_route or "plan_only",
            title=plan_artifact.title,
            created_at=current_decision.created_at or iso_now(),
            updated_at=iso_now(),
            plan_id=plan_artifact.plan_id,
            plan_path=plan_artifact.path,
        )
    )
    consumed = consume_decision(current_decision)
    state_store.set_current_decision(consumed)
    state_store.clear_current_decision()
    notes.append(f"Plan scaffold created at {plan_artifact.path}")

    return (
        RouteDecision(
            route_name=current_decision.resume_route or "plan_only",
            request_text=current_decision.request_text,
            reason="Decision confirmed and formal plan materialized",
            command=None,
            complexity="complex",
            plan_level=level,
            candidate_skill_ids=current_decision.candidate_skill_ids,
            should_recover_context=False,
            should_create_plan=False,
            capture_mode=current_decision.capture_mode,
        ),
        plan_artifact,
        notes,
        kb_artifact,
    )


def _decision_pending_route(decision: RouteDecision, *, reason: str) -> RouteDecision:
    return RouteDecision(
        route_name="decision_pending",
        request_text=decision.request_text,
        reason=reason,
        command=decision.command,
        complexity=decision.complexity,
        plan_level=decision.plan_level,
        candidate_skill_ids=decision.candidate_skill_ids,
        should_recover_context=True,
        should_create_plan=False,
        capture_mode=decision.capture_mode,
        runtime_skill_id=None,
        active_run_action="inspect_decision",
    )


def _merge_kb_artifacts(kb_artifact: KbArtifact | None, extra_files: tuple[str, ...], *, config: RuntimeConfig) -> KbArtifact | None:
    if kb_artifact is None and not extra_files:
        return None
    base_files = kb_artifact.files if kb_artifact is not None else ()
    merged_files = tuple(dict.fromkeys((*base_files, *extra_files)))
    return KbArtifact(
        mode=config.kb_init,
        files=merged_files,
        created_at=kb_artifact.created_at if kb_artifact is not None else iso_now(),
    )
