"""Top-level orchestration for Sopify runtime."""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path
from typing import Any, Mapping, Optional

from .config import load_runtime_config
from .context_recovery import recover_context
from .kb import bootstrap_kb
from .models import KbArtifact, PlanArtifact, ReplayEvent, RouteDecision, RunState, RuntimeResult, SkillMeta
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
    decision = router.classify(user_input, skills=skills)
    recovered = recover_context(decision, config=config, state_store=state_store)

    state_store.set_last_route(decision)

    notes: list[str] = []
    plan_artifact: PlanArtifact | None = None
    skill_result: Mapping[str, Any] | None = None
    replay_session_dir: str | None = None
    replay_events: list[ReplayEvent] = []

    if decision.route_name == "cancel_active":
        state_store.reset_active_flow()
        notes.append("Active flow cleared")
    elif decision.should_create_plan:
        level = decision.plan_level or _default_plan_level(decision)
        plan_artifact = create_plan_scaffold(decision.request_text, config=config, level=level)
        run_state = _make_run_state(decision, plan_artifact)
        state_store.set_current_plan(plan_artifact)
        state_store.set_current_run(run_state)
        notes.append(f"Plan scaffold created at {plan_artifact.path}")
    elif decision.route_name in {"resume_active", "exec_plan"}:
        updated_run = state_store.update_active_run(stage="develop_pending")
        if updated_run is None and recovered.current_plan is not None:
            synthetic_run = _make_run_state(decision, recovered.current_plan)
            state_store.set_current_run(synthetic_run)
            notes.append("Synthetic active run created from current plan")
        elif updated_run is None:
            notes.append("No active plan available to resume")
        else:
            notes.append("Active run resumed")

    if decision.runtime_skill_id is not None:
        skill = _find_skill(skills, decision.runtime_skill_id)
        payload = dict((runtime_payloads or {}).get(decision.runtime_skill_id, {}))
        if skill is None:
            notes.append(f"Runtime skill not found: {decision.runtime_skill_id}")
        elif not payload:
            notes.append(f"Runtime payload missing for skill: {decision.runtime_skill_id}")
        else:
            try:
                skill_result = run_runtime_skill(skill, payload=payload)
            except SkillExecutionError as exc:
                notes.append(str(exc))

    if decision.capture_mode != "off":
        writer = ReplayWriter(config)
        run_state = state_store.get_current_run() or recovered.current_run
        run_id = run_state.run_id if run_state is not None else _make_run_id(decision.request_text)
        replay_event = ReplayEvent(
            ts=iso_now(),
            phase=_phase_for_route(decision),
            intent=decision.request_text or decision.route_name,
            action=f"route:{decision.route_name}",
            key_output=(plan_artifact.summary if plan_artifact is not None else decision.reason),
            decision_reason=decision.reason,
            result="success",
            artifacts=tuple(plan_artifact.files if plan_artifact is not None else ()),
        )
        replay_events.append(replay_event)
        session_dir = writer.append_event(run_id, replay_event)
        writer.render_documents(
            run_id,
            run_state=state_store.get_current_run(),
            route=decision,
            plan_artifact=plan_artifact or recovered.current_plan,
            events=replay_events,
        )
        replay_session_dir = str(session_dir.relative_to(config.workspace_root))

    latest_context = recover_context(decision, config=config, state_store=state_store)
    return RuntimeResult(
        route=decision,
        recovered_context=latest_context,
        discovered_skills=skills,
        kb_artifact=kb_artifact,
        plan_artifact=plan_artifact,
        skill_result=skill_result,
        replay_session_dir=replay_session_dir,
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
    if decision.route_name in {"plan_only", "workflow", "light_iterate"}:
        return "design"
    if decision.route_name in {"resume_active", "exec_plan", "quick_fix"}:
        return "develop"
    if decision.route_name == "compare":
        return "analysis"
    return "analysis"
