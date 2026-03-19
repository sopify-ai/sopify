"""User-facing output rendering for Sopify runtime."""

from __future__ import annotations

import os
import sys

from .clarification import CURRENT_CLARIFICATION_RELATIVE_PATH
from .decision import CURRENT_DECISION_RELATIVE_PATH
from .handoff import CURRENT_HANDOFF_RELATIVE_PATH
from .models import RuntimeResult

_PHASE_LABELS = {
    "zh-CN": {
        "clarification_pending": "需求分析",
        "clarification_resume": "需求分析",
        "execution_confirm_pending": "开发实施",
        "plan_only": "方案设计",
        "workflow": "方案设计",
        "light_iterate": "轻量迭代",
        "quick_fix": "快速修复",
        "resume_active": "开发实施",
        "exec_plan": "开发实施",
        "cancel_active": "命令完成",
        "finalize_active": "开发实施",
        "decision_pending": "方案设计",
        "decision_resume": "方案设计",
        "compare": "模型对比",
        "replay": "咨询问答",
        "consult": "咨询问答",
        "default": "命令完成",
    },
    "en-US": {
        "clarification_pending": "Requirements Analysis",
        "clarification_resume": "Requirements Analysis",
        "execution_confirm_pending": "Development",
        "plan_only": "Solution Design",
        "workflow": "Solution Design",
        "light_iterate": "Light Iteration",
        "quick_fix": "Quick Fix",
        "resume_active": "Development",
        "exec_plan": "Development",
        "cancel_active": "Command Complete",
        "finalize_active": "Development",
        "decision_pending": "Solution Design",
        "decision_resume": "Solution Design",
        "compare": "Model Compare",
        "replay": "Q&A",
        "consult": "Q&A",
        "default": "Command Complete",
    },
}

_LABELS = {
    "zh-CN": {
        "plan": "方案",
        "summary": "概要",
        "replay": "回放",
        "route": "路由",
        "reason": "原因",
        "status": "状态",
        "archive": "归档",
        "question": "问题",
        "questions": "问题",
        "options": "选项",
        "decision": "决策",
        "handoff": "交接",
        "current_plan": "当前方案",
        "stage": "阶段",
        "task_count": "任务数",
        "risk_level": "风险级别",
        "risk": "关键风险",
        "mitigation": "缓解",
        "entry_guard_reason": "守卫原因码",
        "execution_gate": "门禁",
        "missing_facts": "缺口",
        "missing": "未生成",
        "none": "无",
        "cleared": "已清理当前活跃流程",
        "clarification_handoff": "已进入澄清等待，当前请求仍缺进入规划所需的事实信息",
        "execution_confirm_handoff": "已进入执行前确认，当前应先由用户确认是否开始落代码",
        "workflow_handoff": "已生成方案骨架，后续开发仍需宿主继续",
        "light_handoff": "已生成 light 方案，后续改动仍需宿主继续",
        "quick_fix_handoff": "已识别 quick_fix 路由，当前 repo-local runtime 未执行代码修改",
        "consult_handoff": "已识别咨询问答路由，当前 repo-local runtime 不生成正文回答",
        "compare_handoff": "已识别 compare 路由，当前通用入口未构造 compare runtime payload",
        "compare_ready": "compare runtime 已返回结构化结果",
        "replay_handoff": "已识别 replay 路由，当前仍需 workflow-learning 专用链路",
        "resume_handoff": "已恢复当前流程，当前 repo-local runtime 未执行 develop bridge",
        "exec_handoff": "已进入 ~go exec 高级恢复入口，当前仅用于检查或恢复已有 plan，不作为普通开发主链路",
        "finalize_success": "已完成活动方案收口、归档与状态清理",
        "finalize_blocked": "当前无法完成收口事务",
        "default_handoff": "已识别路由，当前 repo-local runtime 未执行后续动作",
        "decision_pending_handoff": "已进入决策确认，正式 plan 会在用户拍板后生成",
        "gate_ready_status": "plan 已通过机器执行门禁，后续可进入执行确认",
        "gate_blocked_status": "plan 已生成，但机器执行门禁仍阻断后续执行",
        "gate_decision_status": "plan 已生成，但仍有阻塞性风险需要继续拍板",
        "next_retry": "检查输入、配置或运行时状态后重试",
        "next_answer_questions": "回复补充信息继续规划，或输入 取消 终止本轮设计",
        "next_confirm_execute": "回复 继续 / next / 开始 确认执行，或直接回复修改意见",
        "next_plan": "在宿主会话中继续评审或执行方案，或直接回复修改意见",
        "next_workflow": "在宿主会话中继续执行后续阶段，或显式使用 ~go plan 只规划",
        "next_light_iterate": "在宿主会话中继续执行轻量迭代，或回复修改意见",
        "next_resume": "在宿主会话中继续 develop 阶段",
        "next_exec": "仅在已有活动 plan 或恢复态时使用 ~go exec；普通开发流继续按宿主会话推进",
        "next_cancel": "如需继续，重新发起 ~go plan 或 ~go",
        "next_finalize_success": "请验证 blueprint 索引与 history 归档结果",
        "next_finalize_retry": "补齐 blueprint 更新或切换到 metadata-managed plan 后重试",
        "next_compare": "人工选择候选结果并继续",
        "next_compare_bridge": "继续使用宿主侧 ~compare 专用桥接",
        "next_replay": "继续使用 workflow-learning 回放链路",
        "next_quick_fix": "在宿主会话中继续执行快速修复",
        "next_consult": "在宿主会话中继续问答，或改成明确变更请求",
        "next_decision": "回复 1/2（或 ~decide choose <option_id>）确认方案，或输入 取消 终止本轮设计",
        "handoff_review_or_execute_plan": "已写入 plan handoff，宿主可继续评审方案或执行",
        "handoff_continue_host_workflow": "已写入 workflow handoff，后续阶段需宿主继续",
        "handoff_answer_questions": "已写入 clarification handoff，宿主应先补齐缺失事实信息",
        "handoff_confirm_execute": "已写入 execution-confirm handoff，宿主应先征求用户执行确认",
        "handoff_continue_host_develop": "已写入 develop handoff，后续开发需宿主继续",
        "handoff_continue_host_quick_fix": "已写入 quick-fix handoff，当前 runtime 未直接改代码",
        "handoff_confirm_decision": "已写入 decision handoff，宿主应先确认当前设计分叉",
        "handoff_host_compare_bridge_required": "已写入 compare handoff，当前仍需宿主侧 compare bridge",
        "handoff_review_compare_results": "已写入 compare handoff，可在宿主侧继续选择结果",
        "handoff_host_replay_bridge_required": "已写入 replay handoff，当前仍需 workflow-learning 专用链路",
        "handoff_continue_host_consult": "已写入 consult handoff，当前 runtime 不生成正文回答",
    },
    "en-US": {
        "plan": "Plan",
        "summary": "Summary",
        "replay": "Replay",
        "route": "Route",
        "reason": "Reason",
        "status": "Status",
        "archive": "Archive",
        "question": "Question",
        "questions": "Questions",
        "options": "Options",
        "decision": "Decision",
        "handoff": "Handoff",
        "current_plan": "Current Plan",
        "stage": "Stage",
        "task_count": "Task Count",
        "risk_level": "Risk Level",
        "risk": "Key Risk",
        "mitigation": "Mitigation",
        "entry_guard_reason": "Entry Guard Reason",
        "execution_gate": "Gate",
        "missing_facts": "Missing Facts",
        "missing": "not generated",
        "none": "none",
        "cleared": "active flow cleared",
        "clarification_handoff": "Clarification is pending because the current request still lacks the minimum facts needed for planning",
        "execution_confirm_handoff": "Execution confirmation is pending; user confirmation is still required before implementation starts",
        "workflow_handoff": "Plan scaffold generated; downstream development still needs the host flow",
        "light_handoff": "Light plan generated; downstream changes still need the host flow",
        "quick_fix_handoff": "quick_fix route recognized; the repo-local runtime has not modified code",
        "consult_handoff": "Consult route recognized; the repo-local runtime does not generate full answers",
        "compare_handoff": "compare route recognized; the generic entry did not construct compare runtime payloads",
        "compare_ready": "compare runtime returned structured results",
        "replay_handoff": "replay route recognized; workflow-learning still needs its dedicated bridge",
        "resume_handoff": "Active flow restored; the repo-local runtime has not executed the develop bridge",
        "exec_handoff": "~go exec entered the advanced recovery entry; it is only used to inspect or recover an existing plan, not as the default implementation path",
        "finalize_success": "The active plan has been closed out, archived, and its runtime state was cleared",
        "finalize_blocked": "The close-out transaction could not be completed",
        "default_handoff": "Route recognized; the repo-local runtime has not executed the downstream action",
        "decision_pending_handoff": "Decision checkpoint is pending; the formal plan will be created after user confirmation",
        "gate_ready_status": "The plan passed the machine execution gate and may move toward execution confirmation",
        "gate_blocked_status": "The plan was generated, but the machine execution gate still blocks downstream execution",
        "gate_decision_status": "The plan was generated, but a blocking risk still needs a decision",
        "next_retry": "Check the input, config, or runtime state and retry",
        "next_answer_questions": "Reply with the missing facts to continue planning, or type cancel to stop this round",
        "next_confirm_execute": "Reply with continue / next / start to confirm execution, or send feedback to revise the plan",
        "next_plan": "Continue plan review or execution in the host session, or reply with feedback",
        "next_workflow": "Continue the downstream stages in the host session, or use ~go plan for planning only",
        "next_light_iterate": "Continue the light iteration in the host session, or reply with feedback",
        "next_resume": "Continue the develop stage in the host session",
        "next_exec": "Use ~go exec only when an active plan or recovery state already exists; otherwise continue through the host flow",
        "next_cancel": "Start a new ~go plan or ~go flow when ready",
        "next_finalize_success": "Review the blueprint index refresh and the history archive",
        "next_finalize_retry": "Update the blueprint or switch to a metadata-managed plan and retry",
        "next_compare": "Review the candidate outputs and continue",
        "next_compare_bridge": "Use the host-side ~compare bridge for compare execution",
        "next_replay": "Use the workflow-learning replay flow",
        "next_quick_fix": "Continue the quick-fix flow in the host session",
        "next_consult": "Continue the discussion in the host session, or restate it as a change request",
        "next_decision": "Reply with 1/2 (or `~decide choose <option_id>`) to confirm, or type cancel to abort this design round",
        "handoff_review_or_execute_plan": "plan handoff written; the host can review the plan or execute it",
        "handoff_continue_host_workflow": "workflow handoff written; downstream stages still need the host flow",
        "handoff_answer_questions": "clarification handoff written; the host should gather the missing factual details first",
        "handoff_confirm_execute": "execution-confirm handoff written; the host should ask for user confirmation first",
        "handoff_continue_host_develop": "develop handoff written; downstream implementation still needs the host flow",
        "handoff_continue_host_quick_fix": "quick-fix handoff written; the runtime did not modify code directly",
        "handoff_confirm_decision": "decision handoff written; the host should confirm the current design split first",
        "handoff_host_compare_bridge_required": "compare handoff written; the host-side compare bridge is still required",
        "handoff_review_compare_results": "compare handoff written; candidate results are ready for host-side review",
        "handoff_host_replay_bridge_required": "replay handoff written; workflow-learning still needs its dedicated bridge",
        "handoff_continue_host_consult": "consult handoff written; the runtime does not generate a full answer body",
    },
}

_TITLE_COLORS = {
    "green": "\033[32m",
    "blue": "\033[34m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
}
_RESET = "\033[0m"


def render_runtime_output(
    result: RuntimeResult,
    *,
    brand: str,
    language: str,
    title_color: str = "none",
    use_color: bool | None = None,
) -> str:
    """Render a runtime result into the Sopify summary format."""
    locale = _normalize_language(language)
    labels = _LABELS[locale]
    phase = _phase_label(result, locale)
    status = _status_symbol(result)
    title = _colorize(f"[{brand}] {phase} {status}", title_color=title_color, use_color=use_color)
    changes = _collect_changes(result)
    body = _core_lines(result, locale)
    next_hint = _next_hint(result, locale)

    lines = [title, ""]
    lines.extend(body)
    lines.extend(["", "---", f"Changes: {len(changes)} files"])
    if changes:
        lines.extend(f"  - {path}" for path in changes)
    else:
        lines.append(f"  - {labels['none']}")
    lines.extend(["", f"Next: {next_hint}"])
    return "\n".join(lines)


def render_runtime_error(
    message: str,
    *,
    brand: str,
    language: str,
    title_color: str = "none",
    use_color: bool | None = None,
) -> str:
    """Render a non-runtime exception into the same summary format."""
    locale = _normalize_language(language)
    labels = _LABELS[locale]
    phase = _PHASE_LABELS[locale]["default"]
    title = _colorize(f"[{brand}] {phase} ×", title_color=title_color, use_color=use_color)
    lines = [
        title,
        "",
        f"{labels['reason']}: {message}",
        "",
        "---",
        "Changes: 0 files",
        f"  - {labels['none']}",
        "",
        f"Next: {labels['next_retry']}",
    ]
    return "\n".join(lines)


def _core_lines(result: RuntimeResult, language: str) -> list[str]:
    labels = _LABELS[language]
    route_name = result.route.route_name

    if route_name == "plan_only" and result.plan_artifact is not None:
        replay_value = result.replay_session_dir or labels["missing"]
        current_run = result.recovered_context.current_run
        return [
            f"{labels['plan']}: {result.plan_artifact.path}",
            f"{labels['summary']}: {result.plan_artifact.summary}",
            f"{labels['stage']}: {current_run.stage if current_run is not None else labels['missing']}",
            _execution_gate_line(result, language),
            f"{labels['handoff']}: {_handoff_label(result, language)}",
            f"{labels['replay']}: {replay_value}",
        ]

    if route_name == "clarification_pending" and result.recovered_context.current_clarification is not None:
        current_clarification = result.recovered_context.current_clarification
        question_text = " | ".join(
            f"[{index}] {question}"
            for index, question in enumerate(current_clarification.questions, start=1)
        )
        missing_facts = ", ".join(current_clarification.missing_facts) or labels["missing"]
        lines = [
            f"{labels['summary']}: {current_clarification.summary}",
            f"{labels['missing_facts']}: {missing_facts}",
            f"{labels['questions']}: {question_text or labels['missing']}",
        ]
        _append_entry_guard_reason_line(lines, result=result, language=language)
        return lines

    if route_name == "decision_pending" and result.recovered_context.current_decision is not None:
        current_decision = result.recovered_context.current_decision
        recommended = current_decision.recommended_option_id or labels["missing"]
        option_text = " | ".join(
            f"[{index}] {option.title}"
            for index, option in enumerate(current_decision.options, start=1)
        )
        lines = [
            f"{labels['question']}: {current_decision.question}",
            f"{labels['options']}: {option_text or labels['missing']}",
            f"{labels['status']}: {_decision_pending_status(language, recommended)}",
        ]
        _append_entry_guard_reason_line(lines, result=result, language=language)
        return lines

    if route_name == "execution_confirm_pending":
        summary = _execution_summary(result)
        lines = [
            f"{labels['plan']}: {summary.get('plan_path') or labels['missing']}",
            f"{labels['summary']}: {summary.get('summary') or labels['missing']}",
            f"{labels['task_count']}: {summary.get('task_count') if summary else 0}",
            f"{labels['risk_level']}: {summary.get('risk_level') or labels['missing']}",
            f"{labels['risk']}: {summary.get('key_risk') or labels['missing']}",
            f"{labels['mitigation']}: {summary.get('mitigation') or labels['missing']}",
        ]
        _append_entry_guard_reason_line(lines, result=result, language=language)
        return lines

    if route_name == "finalize_active":
        if result.plan_artifact is not None:
            return [
                f"{labels['archive']}: {result.plan_artifact.path}",
                f"{labels['summary']}: {result.plan_artifact.summary}",
                f"{labels['status']}: {labels['finalize_success']}",
            ]
        return [
            f"{labels['route']}: {route_name}",
            f"{labels['status']}: {labels['finalize_blocked']}",
            f"{labels['reason']}: {_diagnostic_reason(result)}",
        ]

    if route_name in {"workflow", "light_iterate"} and result.plan_artifact is not None:
        current_run = result.recovered_context.current_run
        return [
            f"{labels['plan']}: {result.plan_artifact.path}",
            f"{labels['summary']}: {result.plan_artifact.summary}",
            f"{labels['stage']}: {current_run.stage if current_run is not None else labels['missing']}",
            _execution_gate_line(result, language),
            f"{labels['status']}: {_status_message(result, language)}",
        ]

    if route_name in {"resume_active", "exec_plan"} and result.recovered_context.current_run is not None:
        current_plan = result.recovered_context.current_plan
        return [
            f"{labels['current_plan']}: {current_plan.path if current_plan is not None else labels['missing']}",
            f"{labels['stage']}: {result.recovered_context.current_run.stage}",
            _execution_gate_line(result, language),
            f"{labels['status']}: {_status_message(result, language)}",
        ]

    if route_name == "cancel_active":
        return [
            f"{labels['status']}: {labels['cleared']}",
            f"{labels['route']}: {route_name}",
            f"{labels['replay']}: {result.replay_session_dir or labels['missing']}",
        ]

    return [
        f"{labels['route']}: {route_name}",
        f"{labels['status']}: {_status_message(result, language)}",
        f"{labels['reason']}: {_diagnostic_reason(result)}",
    ]


def _collect_changes(result: RuntimeResult) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in result.kb_artifact.files if result.kb_artifact is not None else ():
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    for path in result.plan_artifact.files if result.plan_artifact is not None else ():
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    for path in result.recovered_context.loaded_files:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    if result.recovered_context.current_clarification is not None and CURRENT_CLARIFICATION_RELATIVE_PATH not in seen:
        seen.add(CURRENT_CLARIFICATION_RELATIVE_PATH)
        ordered.append(CURRENT_CLARIFICATION_RELATIVE_PATH)
    if result.recovered_context.current_decision is not None and CURRENT_DECISION_RELATIVE_PATH not in seen:
        seen.add(CURRENT_DECISION_RELATIVE_PATH)
        ordered.append(CURRENT_DECISION_RELATIVE_PATH)
    if result.handoff is not None and CURRENT_HANDOFF_RELATIVE_PATH not in seen:
        seen.add(CURRENT_HANDOFF_RELATIVE_PATH)
        ordered.append(CURRENT_HANDOFF_RELATIVE_PATH)
    return ordered


def _next_hint(result: RuntimeResult, language: str) -> str:
    labels = _LABELS[language]
    if result.handoff is not None:
        return _handoff_next_hint(result, language)
    if result.route.route_name == "finalize_active":
        return labels["next_finalize_success"] if result.plan_artifact is not None else labels["next_finalize_retry"]
    if result.route.route_name == "clarification_pending":
        return labels["next_answer_questions"]
    if result.route.route_name == "decision_pending":
        return labels["next_decision"]
    if result.route.route_name == "exec_plan":
        return labels["next_exec"]
    if result.route.route_name == "cancel_active":
        return labels["next_cancel"]
    return labels["next_retry"]


def _status_symbol(result: RuntimeResult) -> str:
    route_name = result.route.route_name
    if route_name == "plan_only":
        return "✓" if result.plan_artifact is not None else "!"
    if route_name == "finalize_active":
        return "✓" if result.plan_artifact is not None else "!"
    if route_name in {"clarification_pending", "execution_confirm_pending"}:
        return "?"
    if route_name == "decision_pending":
        return "?"
    if route_name == "cancel_active":
        return "✓"
    if route_name == "compare" and result.skill_result:
        return "✓"
    if route_name in {"workflow", "light_iterate", "quick_fix", "consult", "replay", "resume_active", "exec_plan", "compare"}:
        return "!"
    if result.notes:
        return "!"
    return "✓"


def _status_message(result: RuntimeResult, language: str) -> str:
    labels = _LABELS[language]
    if result.handoff is not None:
        key = f"handoff_{result.handoff.required_host_action}"
        if key in labels:
            return labels[key]
    route_name = result.route.route_name
    current_gate = _execution_gate(result)
    if current_gate is not None:
        if current_gate.gate_status == "ready":
            return labels["gate_ready_status"]
        if current_gate.gate_status == "decision_required":
            return labels["gate_decision_status"]
        if current_gate.gate_status == "blocked":
            return labels["gate_blocked_status"]
    if route_name == "workflow":
        return labels["workflow_handoff"]
    if route_name == "light_iterate":
        return labels["light_handoff"]
    if route_name == "clarification_pending":
        return labels["clarification_handoff"]
    if route_name == "execution_confirm_pending":
        return labels["execution_confirm_handoff"]
    if route_name == "quick_fix":
        return labels["quick_fix_handoff"]
    if route_name == "consult":
        return labels["consult_handoff"]
    if route_name == "compare":
        return labels["compare_ready"] if result.skill_result else labels["compare_handoff"]
    if route_name == "replay":
        return labels["replay_handoff"]
    if route_name == "decision_pending":
        return labels["decision_pending_handoff"]
    if route_name == "resume_active":
        return labels["resume_handoff"]
    if route_name == "exec_plan":
        return labels["exec_handoff"]
    if route_name == "finalize_active":
        return labels["finalize_success"] if result.plan_artifact is not None else labels["finalize_blocked"]
    return labels["default_handoff"]


def _handoff_label(result: RuntimeResult, language: str) -> str:
    if result.handoff is None:
        return _LABELS[language]["missing"]
    return CURRENT_HANDOFF_RELATIVE_PATH


def _handoff_next_hint(result: RuntimeResult, language: str) -> str:
    labels = _LABELS[language]
    handoff = result.handoff
    if handoff is None:
        return labels["next_retry"]
    if handoff.handoff_kind == "plan":
        return labels["next_plan"]
    if handoff.handoff_kind == "workflow":
        return labels["next_workflow"]
    if handoff.handoff_kind == "light_iterate":
        return labels["next_light_iterate"]
    if handoff.handoff_kind == "clarification":
        return labels["next_answer_questions"]
    if handoff.handoff_kind == "execution_confirm":
        if handoff.required_host_action == "review_or_execute_plan":
            return labels["next_plan"]
        return labels["next_confirm_execute"]
    if handoff.handoff_kind == "develop":
        return labels["next_resume"] if result.route.route_name == "resume_active" else labels["next_exec"]
    if handoff.handoff_kind == "quick_fix":
        return labels["next_quick_fix"]
    if handoff.handoff_kind == "decision":
        return labels["next_decision"]
    if handoff.handoff_kind == "compare":
        return labels["next_compare"] if handoff.required_host_action == "review_compare_results" else labels["next_compare_bridge"]
    if handoff.handoff_kind == "replay":
        return labels["next_replay"]
    if handoff.handoff_kind == "consult":
        return labels["next_consult"]
    return labels["next_retry"]


def _diagnostic_reason(result: RuntimeResult) -> str:
    if result.notes:
        return result.notes[0]
    if result.route.reason:
        return result.route.reason
    return result.route.route_name


def _execution_gate(result: RuntimeResult):
    current_run = result.recovered_context.current_run
    if current_run is not None and current_run.execution_gate is not None:
        return current_run.execution_gate
    if result.handoff is not None:
        execution_gate = result.handoff.artifacts.get("execution_gate")
        if isinstance(execution_gate, dict):
            return execution_gate
    return None


def _execution_summary(result: RuntimeResult) -> dict[str, object]:
    if result.handoff is not None:
        summary = result.handoff.artifacts.get("execution_summary")
        if isinstance(summary, dict):
            return summary
    return {}


def _append_entry_guard_reason_line(lines: list[str], *, result: RuntimeResult, language: str) -> None:
    reason_code = _entry_guard_reason_code(result)
    if not reason_code:
        return
    labels = _LABELS[language]
    lines.append(f"{labels['entry_guard_reason']}: {reason_code}")


def _entry_guard_reason_code(result: RuntimeResult) -> str | None:
    handoff = result.handoff
    if handoff is None:
        return None
    value = handoff.artifacts.get("entry_guard_reason_code")
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _execution_gate_line(result: RuntimeResult, language: str) -> str:
    labels = _LABELS[language]
    current_gate = _execution_gate(result)
    if current_gate is None:
        return f"{labels['execution_gate']}: {labels['missing']}"
    if hasattr(current_gate, "gate_status"):
        gate_status = current_gate.gate_status
        blocking_reason = current_gate.blocking_reason
        plan_completion = current_gate.plan_completion
    else:
        gate_status = str(current_gate.get("gate_status") or "blocked")
        blocking_reason = str(current_gate.get("blocking_reason") or "none")
        plan_completion = str(current_gate.get("plan_completion") or "incomplete")
    return f"{labels['execution_gate']}: {gate_status} / {blocking_reason} / {plan_completion}"


def _decision_pending_status(language: str, recommended_option_id: str) -> str:
    if language == "en-US":
        return f"awaiting confirmation (recommended `{recommended_option_id}`)"
    return f"等待确认（推荐 `{recommended_option_id}`）"


def _phase_label(result: RuntimeResult, language: str) -> str:
    route_name = result.route.route_name
    labels = _PHASE_LABELS[language]
    if route_name in {"clarification_pending", "clarification_resume"}:
        current_clarification = result.recovered_context.current_clarification
        if current_clarification is not None and current_clarification.phase == "develop":
            return labels["resume_active"]
    if route_name in {"decision_pending", "decision_resume"}:
        current_decision = result.recovered_context.current_decision
        if current_decision is not None and current_decision.phase == "develop":
            return labels["resume_active"]
    return labels.get(route_name, labels["default"])


def _normalize_language(language: str) -> str:
    return "en-US" if language == "en-US" else "zh-CN"


def _colorize(text: str, *, title_color: str, use_color: bool | None) -> str:
    if title_color == "none":
        return text
    if use_color is None:
        use_color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    if not use_color:
        return text
    color_code = _TITLE_COLORS.get(title_color)
    if color_code is None:
        return text
    return f"{color_code}{text}{_RESET}"
