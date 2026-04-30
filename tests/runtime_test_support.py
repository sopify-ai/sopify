from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.config import ConfigError, load_runtime_config
from runtime._yaml import load_yaml
from runtime.checkpoint_materializer import materialize_checkpoint_request
from runtime.checkpoint_request import (
    CHECKPOINT_REASON_MISSING_BUT_TRADEOFF_DETECTED,
    CheckpointRequestError,
    DEVELOP_RESUME_CONTEXT_REQUIRED_FIELDS,
    checkpoint_request_from_clarification_state,
    checkpoint_request_from_decision_state,
)
from runtime.clarification import build_clarification_state
from runtime.clarification_bridge import (
    ClarificationBridgeError,
    build_cli_clarification_bridge,
    load_clarification_bridge_context,
    prompt_cli_clarification_submission,
)
from runtime.develop_checkpoint import DevelopCheckpointError, inspect_develop_checkpoint_context, submit_develop_checkpoint
from runtime.develop_checkpoint import submit_develop_quality_report
from runtime.develop_quality import build_develop_quality_contract
from runtime.decision import build_decision_state, build_execution_gate_decision_state, confirm_decision, response_from_submission
from runtime.decision_bridge import (
    DecisionBridgeError,
    DecisionBridgeContext,
    build_cli_decision_bridge,
    load_decision_bridge_context,
    prompt_cli_decision_submission,
)
from runtime.decision_policy import match_decision_policy
from runtime.decision_templates import CUSTOM_OPTION_ID, PRIMARY_OPTION_FIELD_ID, build_strategy_pick_template
from runtime.daily_summary import render_daily_summary_markdown
from runtime.engine import run_runtime
from runtime.entry_guard import DIRECT_EDIT_BLOCKED_RUNTIME_REQUIRED_REASON_CODE
from runtime.execution_gate import evaluate_execution_gate
from runtime.action_intent import ActionProposal, ArchiveSubjectProposal
from runtime.handoff import build_runtime_handoff
from runtime.kb import bootstrap_kb, ensure_blueprint_index
from runtime.knowledge_layout import materialization_stage, resolve_context_profile
from runtime.plan_registry import (
    PlanRegistryError,
    confirm_plan_priority,
    get_plan_entry,
    inspect_plan_registry,
    read_plan_registry,
    recommend_plan_candidates,
    registry_relative_path,
)
from runtime.plan_scaffold import create_plan_scaffold, request_explicitly_wants_new_plan
from runtime.output import render_runtime_output
from runtime.plan_orchestrator import (
    PLAN_ORCHESTRATOR_CANCELLED_EXIT,
    PLAN_ORCHESTRATOR_PENDING_EXIT,
    PlanOrchestratorError,
    run_plan_loop,
)
from runtime.preferences import preload_preferences, preload_preferences_for_workspace
from runtime.replay import ReplayWriter, build_decision_replay_event, build_develop_quality_replay_event
from runtime.router import Router
from runtime.skill_registry import SkillRegistry
from runtime.skill_runner import SkillExecutionError, run_runtime_skill
from runtime.state import StateStore, iso_now, local_day_now
from runtime.state_invariants import HOST_FACING_TRUTH_WRITE_KINDS, InvariantViolationError
from runtime.models import (
    ClarificationState,
    DailySummaryArtifact,
    DecisionCheckpoint,
    DecisionCondition,
    DecisionField,
    DecisionOption,
    DecisionRecommendation,
    DecisionSelection,
    DecisionState,
    DecisionSubmission,
    DecisionValidation,
    ExecutionGate,
    PlanArtifact,
    PlanProposalState,
    RecoveredContext,
    ReplayEvent,
    RouteDecision,
    RuntimeHandoff,
    RunState,
    SkillMeta,
    SummaryCodeChangeFact,
    SummaryDecisionFact,
    SummaryFacts,
    SummaryGitCommitRef,
    SummaryGitRefs,
    SummaryGoalFact,
    SummaryIssueFact,
    SummaryLessonFact,
    SummaryNextStepFact,
    SummaryQualityChecks,
    SummaryReplaySessionRef,
    SummaryScope,
    SummarySourceRefFile,
    SummarySourceRefs,
    SummarySourceWindow,
)

DEFAULT_RUNTIME_WORKFLOW_TEST_FILE = "tests/test_runtime_engine.py"
_FOOTER_TIME_LABELS = ("Generated At:", "生成时间:")


class _FakeInteractiveSession:
    def __init__(self, *, single_choice: object = None, multi_choice: list[object] | None = None, confirm_value: bool = True) -> None:
        self.single_choice = single_choice
        self.multi_choice = list(multi_choice or [])
        self.confirm_value = confirm_value

    def is_available(self) -> bool:
        return True

    def select(self, *, title: str, items, instructions: str, initial_value=None):
        return self.single_choice if self.single_choice is not None else list(items)[0]["value"]

    def multi_select(self, *, title: str, items, instructions: str, initial_values=(), required: bool = False):
        if self.multi_choice:
            return list(self.multi_choice)
        if required:
            return [list(items)[0]["value"]]
        return list(initial_values)

    def confirm(self, *, title: str, yes_label: str, no_label: str, default_value=None, instructions: str) -> bool:
        return self.confirm_value


def _plan_dir_count(workspace: Path) -> int:
    plan_root = workspace / ".sopify-skills" / "plan"
    if not plan_root.exists():
        return 0
    return sum(1 for path in plan_root.iterdir() if path.is_dir())


def _rewrite_background_scope(
    workspace: Path,
    plan_artifact: PlanArtifact,
    *,
    scope_lines: tuple[str, str],
    risk_lines: tuple[str, str] | None = None,
) -> None:
    background_path = workspace / plan_artifact.path / "background.md"
    text = background_path.read_text(encoding="utf-8")
    text = text.replace(
        "- 模块: 待分析\n- 文件: 待分析",
        f"- 模块: {scope_lines[0]}\n- 文件: {scope_lines[1]}",
    )
    if risk_lines is not None:
        text = re.sub(
            r"- 风险: .+\n- 缓解: .+",
            f"- 风险: {risk_lines[0]}\n- 缓解: {risk_lines[1]}",
            text,
        )
    background_path.write_text(text, encoding="utf-8")


def _prepare_ready_plan_state(
    workspace: Path,
    *,
    request_text: str = "补 runtime 骨架",
    session_id: str | None = None,
) -> tuple[object, StateStore, PlanArtifact]:
    config = load_runtime_config(workspace)
    store = StateStore(config, session_id=session_id)
    store.ensure()
    plan_artifact = create_plan_scaffold(request_text, config=config, level="standard")
    _rewrite_background_scope(
        workspace,
        plan_artifact,
        scope_lines=("runtime/router.py, runtime/engine.py", f"runtime/router.py, runtime/engine.py, {DEFAULT_RUNTIME_WORKFLOW_TEST_FILE}"),
        risk_lines=("需要确保执行前确认不会误触发 develop", "统一通过 execution_confirm_pending 与 gate ready 再进入执行"),
    )
    gate = evaluate_execution_gate(
        decision=RouteDecision(
            route_name="workflow",
            request_text=request_text,
            reason="test",
            complexity="complex",
            plan_level="standard",
            candidate_skill_ids=("develop",),
        ),
        plan_artifact=plan_artifact,
        current_clarification=None,
        current_decision=None,
        config=config,
    )
    store.set_current_plan(plan_artifact)
    store.set_current_run(
        RunState(
            run_id="run-ready",
            status="active",
            stage="ready_for_execution",
            route_name="workflow",
            title=plan_artifact.title,
            created_at=iso_now(),
            updated_at=iso_now(),
            plan_id=plan_artifact.plan_id,
            plan_path=plan_artifact.path,
            execution_gate=gate,
        )
    )
    return config, store, plan_artifact


def _enter_active_develop_context(workspace: Path) -> None:
    _prepare_ready_plan_state(workspace)
    run_runtime("~go exec", workspace_root=workspace, user_home=workspace / "home")
    result = run_runtime("开始", workspace_root=workspace, user_home=workspace / "home")
    assert result.handoff is not None
    assert result.handoff.required_host_action == "continue_host_develop"


def _git_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    # Git hooks export repo-local environment variables. Clear them so tests
    # that create foreign temp repos do not get redirected back to this repo.
    for key in (
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_GRAFT_FILE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_SUPER_PREFIX",
        "GIT_WORK_TREE",
    ):
        env.pop(key, None)
    return env


def _run_git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(workspace), *args],
        capture_output=True,
        text=True,
        check=True,
        env=_git_subprocess_env(),
    )


def _init_git_workspace(workspace: Path) -> None:
    _run_git(workspace, "init")
    _run_git(workspace, "config", "user.name", "Test User")
    _run_git(workspace, "config", "user.email", "test@example.com")


def _assert_rendered_footer_contract(
    testcase: unittest.TestCase,
    rendered: str,
    *,
    next_prefix: str,
) -> None:
    lines = rendered.rstrip().splitlines()
    testcase.assertGreaterEqual(len(lines), 2)
    testcase.assertEqual(lines[-2], "", msg=rendered)
    testcase.assertTrue(lines[-1].startswith(next_prefix), msg=rendered)
    for label in _FOOTER_TIME_LABELS:
        testcase.assertNotIn(label, rendered)


__all__ = [name for name in globals() if not name.startswith("__")]
