"""Plan scaffold generator for Sopify runtime."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha1
from pathlib import Path
import re
from typing import Iterable, List, Sequence

from .decision import option_by_id
from .knowledge_sync import render_knowledge_sync_front_matter
from .models import DecisionState, PlanArtifact, RuntimeConfig
from .state import iso_now


def create_plan_scaffold(
    request_text: str,
    *,
    config: RuntimeConfig,
    level: str,
    decision_state: DecisionState | None = None,
) -> PlanArtifact:
    """Create a deterministic plan package scaffold.

    Args:
        request_text: User request without command prefix.
        config: Runtime config.
        level: One of `light`, `standard`, `full`.

    Returns:
        The generated plan artifact metadata.
    """
    if level not in {"light", "standard", "full"}:
        raise ValueError(f"Unsupported plan level: {level}")

    title = _derive_title(request_text)
    plan_id = _make_plan_id(title, plan_root=config.plan_root)
    plan_dir = config.plan_root / plan_id
    plan_dir.mkdir(parents=True, exist_ok=False)

    summary = request_text.strip() or title
    files: List[str] = []

    if level == "light":
        plan_path = plan_dir / "plan.md"
        plan_path.write_text(
            _render_light_plan(
                title,
                summary,
                plan_id=plan_id,
                feature_key=_feature_key_from_plan_id(plan_id),
                decision_state=decision_state,
            ),
            encoding="utf-8",
        )
        files.append(str(plan_path.relative_to(config.workspace_root)))
    else:
        background = plan_dir / "background.md"
        design = plan_dir / "design.md"
        tasks = plan_dir / "tasks.md"
        background.write_text(_render_background(title, summary), encoding="utf-8")
        design.write_text(_render_design(title, summary, level, decision_state=decision_state), encoding="utf-8")
        tasks.write_text(
            _render_tasks(
                title,
                plan_id=plan_id,
                feature_key=_feature_key_from_plan_id(plan_id),
                level=level,
                decision_state=decision_state,
            ),
            encoding="utf-8",
        )
        files.extend(
            str(path.relative_to(config.workspace_root))
            for path in (background, design, tasks)
        )
        if level == "full":
            adr_dir = plan_dir / "adr"
            diagrams_dir = plan_dir / "diagrams"
            adr_dir.mkdir()
            diagrams_dir.mkdir()
            files.extend(
                str(path.relative_to(config.workspace_root))
                for path in (adr_dir, diagrams_dir)
            )

    return PlanArtifact(
        plan_id=plan_id,
        title=title,
        summary=summary,
        level=level,
        path=str(plan_dir.relative_to(config.workspace_root)),
        files=tuple(files),
        created_at=iso_now(),
    )


def _derive_title(request_text: str) -> str:
    cleaned = request_text.strip()
    if not cleaned:
        return "Untitled Plan"
    first_line = cleaned.splitlines()[0].strip()
    if len(first_line) <= 48:
        return first_line
    return first_line[:45].rstrip() + "..."


def _make_plan_id(title: str, *, plan_root: Path) -> str:
    date_prefix = datetime.now().strftime("%Y%m%d")
    slug = _slugify(title)
    if slug == "task":
        slug = f"task-{sha1(title.encode('utf-8')).hexdigest()[:6]}"
    base = f"{date_prefix}_{slug}"
    candidate = base
    suffix = 2
    while (plan_root / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _slugify(value: str) -> str:
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return ascii_slug or "task"


def _feature_key_from_plan_id(plan_id: str) -> str:
    parts = plan_id.split("_", 1)
    return parts[1] if len(parts) == 2 else plan_id


def _render_light_plan(title: str, summary: str, *, plan_id: str, feature_key: str, decision_state: DecisionState | None) -> str:
    return (
        _render_plan_front_matter(plan_id=plan_id, feature_key=feature_key, level="light", decision_state=decision_state)
        +
        f"# {title}\n\n"
        "## 背景\n"
        f"{summary}\n\n"
        f"{_render_decision_section(decision_state)}"
        "## 方案\n"
        "- 明确改动范围与边界\n"
        "- 实现最小必要变更\n"
        "- 补充验证与回放记录\n\n"
        "## 任务\n"
        "- [ ] 梳理当前上下文与目标文件\n"
        "- [ ] 实施并验证最小改动\n"
        "- [ ] 同步状态与后续说明\n\n"
        "## 变更文件\n"
        "- 待分析\n"
    )


def _render_background(title: str, summary: str) -> str:
    return (
        f"# 变更提案: {title}\n\n"
        "## 需求背景\n"
        f"{summary}\n\n"
        "## 变更内容\n"
        "1. 收口运行时边界\n"
        "2. 明确状态与产物路径\n"
        "3. 保持主流程可恢复\n\n"
        "## 影响范围\n"
        "- 模块: 待分析\n"
        "- 文件: 待分析\n\n"
        "## 风险评估\n"
        "- 风险: 需要避免把主流程做重\n"
        "- 缓解: 先实现最小闭环，再扩展\n"
    )


def _render_design(title: str, summary: str, level: str, *, decision_state: DecisionState | None) -> str:
    extra = "\n## ADR / 图表\n仅在 full 级别下继续补充。\n" if level == "full" else ""
    return (
        f"# 技术设计: {title}\n\n"
        f"{_render_decision_section(decision_state)}"
        "## 技术方案\n"
        f"- 核心目标: {summary}\n"
        "- 实现要点:\n"
        "  - 保持模块职责清晰\n"
        "  - 以文件系统状态作为单一事实源\n"
        "  - 把可重复控制点收口到 runtime\n\n"
        "## 架构设计\n"
        "- 入口负责引导，不承载业务细节\n"
        "- 路由、状态、上下文恢复、产物生成分层实现\n\n"
        "## 安全与性能\n"
        "- 安全: 不做全量自动加载知识库\n"
        "- 性能: 只读取最小必要上下文\n"
        f"{extra}"
    )


def _render_tasks(title: str, *, plan_id: str, feature_key: str, level: str, decision_state: DecisionState | None) -> str:
    return (
        _render_plan_front_matter(plan_id=plan_id, feature_key=feature_key, level=level, decision_state=decision_state)
        +
        f"# 任务清单: {title}\n\n"
        "## 1. runtime\n"
        "- [ ] 1.1 明确模块职责与边界\n"
        "- [ ] 1.2 实现核心状态与路由逻辑\n"
        "- [ ] 1.3 验证跨会话恢复路径\n\n"
        "## 2. 测试\n"
        "- [ ] 2.1 补充行为测试\n\n"
        "## 3. 文档\n"
        "- [ ] 3.1 同步蓝图与任务状态\n"
    )


def _render_plan_front_matter(
    *,
    plan_id: str,
    feature_key: str,
    level: str,
    decision_state: DecisionState | None,
) -> str:
    lines = [
        "---",
        f"plan_id: {plan_id}",
        f"feature_key: {feature_key}",
        f"level: {level}",
        "lifecycle_state: active",
        *render_knowledge_sync_front_matter(level),
        "archive_ready: false",
    ]
    if decision_state is not None:
        selected_option = decision_state.selected_option_id or ""
        lines.extend(
            [
                "decision_checkpoint:",
                "  required: true",
                f"  decision_id: {decision_state.decision_id}",
                f"  selected_option_id: {selected_option}",
                f"  status: {decision_state.status}",
            ]
        )
    lines.extend(["---", "", ""])
    return "\n".join(lines)


def _render_decision_section(decision_state: DecisionState | None) -> str:
    if decision_state is None:
        return ""

    selected_option = option_by_id(decision_state, decision_state.selected_option_id or "")
    selected_title = selected_option.title if selected_option is not None else "待确认"
    options = "\n".join(
        f"- `{option.option_id}`: {option.title}"
        + (" (推荐)" if option.recommended else "")
        for option in decision_state.options
    )
    return (
        "## 决策确认\n"
        f"- 问题: {decision_state.question}\n"
        f"- 结果: {selected_title}\n"
        f"- 决策 ID: `{decision_state.decision_id}`\n"
        "- 候选方案:\n"
        f"{options}\n\n"
    )
