"""Minimal knowledge-base bootstrap for Sopify runtime."""

from __future__ import annotations

from pathlib import Path
import re

from .knowledge_layout import materialization_stage
from .models import KbArtifact, RuntimeConfig
from .state import iso_now


def bootstrap_kb(config: RuntimeConfig) -> KbArtifact:
    """Create the minimum knowledge-base skeleton for the current workspace.

    The bootstrap is idempotent: existing files are preserved and only missing
    files are created.
    """
    root = config.runtime_root
    _ensure_directories(root)

    created_files: list[str] = []
    for relative_path, content in _bootstrap_files(config).items():
        target = root / relative_path
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created_files.append(str(target.relative_to(config.workspace_root)))

    if _should_bootstrap_blueprint_index(config):
        created_files.extend(ensure_blueprint_index(config))

    return KbArtifact(
        mode=config.kb_init,
        files=tuple(created_files),
        created_at=iso_now(),
    )


def _ensure_directories(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)


def ensure_blueprint_index(config: RuntimeConfig) -> tuple[str, ...]:
    """Create or refresh the lightweight blueprint index."""
    path = refresh_blueprint_index(config)
    return (str(path.relative_to(config.workspace_root)),)


def refresh_blueprint_index(config: RuntimeConfig) -> Path:
    """Render the shared blueprint index for the current materialization stage."""
    root = config.runtime_root
    readme = root / "blueprint" / "README.md"
    content = render_blueprint_index(config)
    if readme.exists():
        if readme.read_text(encoding="utf-8") == content:
            return readme
        readme.write_text(content, encoding="utf-8")
        return readme
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(content, encoding="utf-8")
    return readme


def ensure_blueprint_scaffold(config: RuntimeConfig) -> tuple[str, ...]:
    """Populate the full blueprint skeleton once the workspace enters plan lifecycle."""
    created: list[str] = []
    root = config.runtime_root / "blueprint"
    files = {
        root / "background.md": _blueprint_background_stub(config.language),
        root / "design.md": _blueprint_design_stub(config.language),
        root / "tasks.md": _blueprint_tasks_stub(config.language),
    }
    for path, content in files.items():
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(str(path.relative_to(config.workspace_root)))
    created.extend(ensure_blueprint_index(config))
    return tuple(created)


def _bootstrap_files(config: RuntimeConfig) -> dict[Path, str]:
    project_name = config.workspace_root.name or "project"
    if config.kb_init == "full":
        return _full_files(config, project_name)
    return _progressive_files(config, project_name)


def _progressive_files(config: RuntimeConfig, project_name: str) -> dict[Path, str]:
    return {
        Path("project.md"): _project_stub(config, project_name),
        Path("user/preferences.md"): _preferences_stub(config.language),
    }


def _full_files(config: RuntimeConfig, project_name: str) -> dict[Path, str]:
    files = _progressive_files(config, project_name)
    files.update(
        {
            Path("blueprint/background.md"): _blueprint_background_stub(config.language),
            Path("blueprint/design.md"): _blueprint_design_stub(config.language),
            Path("blueprint/tasks.md"): _blueprint_tasks_stub(config.language),
            Path("user/feedback.jsonl"): "",
        }
    )
    return files


def _project_stub(config: RuntimeConfig, project_name: str) -> str:
    manifests = _detect_manifests(config.workspace_root)
    directories = _detect_directories(config.workspace_root)
    root_config = "sopify.config.yaml" if config.project_config_path is not None else None

    if config.language == "en-US":
        manifest_text = ", ".join(manifests) if manifests else "none detected"
        directory_text = ", ".join(directories) if directories else "none detected"
        root_config_text = root_config or "not detected"
        return (
            "# Project Technical Conventions\n\n"
            "## Runtime Snapshot\n"
            f"- Project: {project_name}\n"
            f"- Workspace: `{config.workspace_root}`\n"
            f"- Runtime root: `{config.runtime_root.relative_to(config.workspace_root)}`\n"
            f"- Root config: `{root_config_text}`\n"
            f"- Detected manifests: {manifest_text}\n"
            f"- Detected top-level directories: {directory_text}\n\n"
            "## Working Agreement\n"
            "- Keep this file focused on stable technical conventions.\n"
            "- Prefer updating this file only when a convention becomes reusable across tasks.\n"
            "- Do not treat one-off implementation choices as project-wide rules.\n"
        )

    manifest_text = "、".join(manifests) if manifests else "暂未识别"
    directory_text = "、".join(directories) if directories else "暂未识别"
    root_config_text = root_config or "未检测到项目级配置"
    return (
        "# 项目技术约定\n\n"
        "## Runtime 快照\n"
        f"- 项目名：{project_name}\n"
        f"- 工作目录：`{config.workspace_root}`\n"
        f"- 运行时目录：`{config.runtime_root.relative_to(config.workspace_root)}`\n"
        f"- 根配置：`{root_config_text}`\n"
        f"- 已识别清单：{manifest_text}\n"
        f"- 已识别顶层目录：{directory_text}\n\n"
        "## 使用约定\n"
        "- 这里只沉淀可复用的长期技术约定。\n"
        "- 一次性实现细节不默认写入本文件。\n"
        "- 当约定发生变化时，应以代码现状为准并同步更新。\n"
    )


def _preferences_stub(language: str) -> str:
    if language == "en-US":
        return (
            "# Long-Term User Preferences\n\n"
            "> Record only explicitly stated long-term preferences. One-off instructions stay out of this file.\n\n"
            "## Preference List\n\n"
            "No confirmed long-term preferences yet.\n\n"
            "## Notes\n"
            "- Priority: current task requirement > this file > default rules.\n"
            "- New preferences must be restatable, verifiable, and reversible.\n"
        )

    return (
        "# 用户长期偏好\n\n"
        "> 仅记录用户明确声明的长期偏好；一次性指令不入库。\n\n"
        "## 偏好列表\n\n"
        "当前暂无已确认的长期偏好。\n\n"
        "## 备注\n"
        "- 优先级：当前任务明确要求 > 本文件偏好 > 默认规则。\n"
        "- 新偏好需要可复述、可验证、可撤销。\n"
    )


def _detect_manifests(workspace_root: Path) -> list[str]:
    manifest_names = (
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
    )
    return [name for name in manifest_names if (workspace_root / name).exists()]


def _detect_directories(workspace_root: Path) -> list[str]:
    dir_names = ("src", "app", "lib", "tests", "docs", "scripts")
    return [name for name in dir_names if (workspace_root / name).is_dir()]


def _is_real_project_workspace(workspace_root: Path) -> bool:
    return (
        (workspace_root / ".git").exists()
        or bool(_detect_manifests(workspace_root))
        or bool(_detect_directories(workspace_root))
    )


def _should_bootstrap_blueprint_index(config: RuntimeConfig) -> bool:
    return config.kb_init == "full" or _is_real_project_workspace(config.workspace_root)


def _blueprint_stage(config: RuntimeConfig) -> str:
    return materialization_stage(config=config)


def render_blueprint_index(config: RuntimeConfig) -> str:
    project_name = config.workspace_root.name or "project"
    stage = _blueprint_stage(config)
    root = config.runtime_root
    has_deep_blueprint = stage != "L0 bootstrap"
    has_history = stage == "L3 history-ready"
    has_active_plan = stage == "L2 plan-active"
    latest_archive = _latest_archive_hint(config)
    if config.language == "en-US":
        goal_block = (
            "- Long-lived blueprint goals are not materialized yet; the first plan lifecycle will create the deeper blueprint docs.\n"
            if not has_deep_blueprint
            else "- Long-lived goals and scope live in `./background.md`; this index stays brief and only points to current entry docs.\n"
        )
        focus_block = (
            f"- History archive: available; latest archive is `{latest_archive}`.\n"
            if latest_archive is not None
            else "- History archive: not generated yet.\n"
        )
        read_next = ["- [Technical Conventions](../project.md)"]
        if has_deep_blueprint:
            read_next.extend(
                [
                    "- [Blueprint Background](./background.md)",
                    "- [Blueprint Design](./design.md)",
                    "- [Blueprint Tasks](./tasks.md)",
                ]
            )
        else:
            read_next.append("- Deeper blueprint docs will be created on the first plan lifecycle.")
        if has_history:
            read_next.append("- [Change History](../history/index.md)")
        else:
            read_next.append("- History becomes available after the first explicit `~go finalize`.")
        if has_active_plan:
            read_next.append("- Active plan directory: `../plan/`")
        elif latest_archive is not None:
            read_next.append(f"- Latest archive: `{latest_archive}`")
        return "".join(
            [
                "# Project Blueprint Index\n\n",
                f"Status: {stage}\n",
                f"Workspace: `{config.workspace_root}`\n",
                f"Runtime root: `{root.relative_to(config.workspace_root)}`\n",
                "Maintenance: Sopify refreshes managed sections; free-text notes may be edited manually.\n\n",
                "## Current Goal\n\n",
                "<!-- sopify:auto:goal:start -->\n",
                f"- Project: `{project_name}`.\n",
                goal_block,
                "<!-- sopify:auto:goal:end -->\n\n",
                "## Project Overview\n\n",
                "<!-- sopify:auto:overview:start -->\n",
                "- blueprint: tracked long-lived project facts\n",
                "- plan: active working plans created on demand\n",
                "- history: finalized archives created on close-out\n",
                "- replay: optional replay capability\n",
                "<!-- sopify:auto:overview:end -->\n\n",
                "## Architecture Map\n\n",
                "<!-- sopify:auto:architecture:start -->\n",
                "```text\n",
                ".sopify-skills/\n",
                "├── blueprint/\n",
                "├── plan/\n",
                "├── history/\n",
                "├── state/\n",
                "└── replay/\n",
                "```\n",
                "<!-- sopify:auto:architecture:end -->\n\n",
                "## Key Contracts\n\n",
                "<!-- sopify:auto:contracts:start -->\n",
                "- Bootstrap creates only the minimum long-lived KB skeleton.\n",
                "- Deeper blueprint files appear on the first plan lifecycle, or earlier when `kb_init: full` is configured.\n",
                "- History is generated only during explicit `~go finalize` close-out.\n",
                "<!-- sopify:auto:contracts:end -->\n\n",
                "## Current Focus\n\n",
                "<!-- sopify:auto:focus:start -->\n",
                f"- Active plan: {'present' if has_active_plan else 'none'}.\n",
                focus_block,
                "<!-- sopify:auto:focus:end -->\n\n",
                "## Read Next\n\n",
                "<!-- sopify:auto:read-next:start -->\n",
                "\n".join(read_next),
                "\n",
                "<!-- sopify:auto:read-next:end -->\n",
            ]
        )

    goal_block = (
        "- 当前尚未物化长期目标摘要；首次进入 plan 生命周期后会补齐深层 blueprint 文档。\n"
        if not has_deep_blueprint
        else "- 长期目标与范围收敛到 `./background.md`；本索引只保留入口与状态，不展开正文。\n"
    )
    focus_block = (
        f"- history 归档：已可用；最近归档为 `{latest_archive}`。\n"
        if latest_archive is not None
        else "- history 归档：尚未生成。\n"
    )
    read_next = ["- [项目技术约定](../project.md)"]
    if has_deep_blueprint:
        read_next.extend(
            [
                "- [蓝图背景](./background.md)",
                "- [蓝图设计](./design.md)",
                "- [蓝图任务](./tasks.md)",
            ]
        )
    else:
        read_next.append("- 深层 blueprint 文档会在首次进入 plan 生命周期后生成。")
    if has_history:
        read_next.append("- [变更历史](../history/index.md)")
    else:
        read_next.append("- 首次显式 `~go finalize` 后才会出现 history。")
    if has_active_plan:
        read_next.append("- 当前活动方案目录：`../plan/`")
    elif latest_archive is not None:
        read_next.append(f"- 最近归档：`{latest_archive}`")
    return "".join(
        [
            "# 项目蓝图索引\n\n",
            f"状态: {stage}\n",
            f"工作目录: `{config.workspace_root}`\n",
            f"运行时目录: `{root.relative_to(config.workspace_root)}`\n",
            "维护方式: Sopify 托管自动区块，说明区块允许人工补充。\n\n",
            "## 当前目标\n\n",
            "<!-- sopify:auto:goal:start -->\n",
            f"- 项目：`{project_name}`。\n",
            goal_block,
            "<!-- sopify:auto:goal:end -->\n\n",
            "## 项目概览\n\n",
            "<!-- sopify:auto:overview:start -->\n",
            "- blueprint: 长期项目真相，默认入库\n",
            "- plan: 按需创建的活动方案\n",
            "- history: 收口后生成的历史归档\n",
            "- replay: 可选回放能力\n",
            "<!-- sopify:auto:overview:end -->\n\n",
            "## 架构地图\n\n",
            "<!-- sopify:auto:architecture:start -->\n",
            "```text\n",
            ".sopify-skills/\n",
            "├── blueprint/\n",
            "├── plan/\n",
            "├── history/\n",
            "├── state/\n",
            "└── replay/\n",
            "```\n",
            "<!-- sopify:auto:architecture:end -->\n\n",
            "## 关键契约\n\n",
            "<!-- sopify:auto:contracts:start -->\n",
            "- bootstrap 只创建最小长期知识骨架\n",
            "- 深层 blueprint 文件在首次进入 plan 生命周期时补齐，或在 `kb_init: full` 下提前物化\n",
            "- 仅在显式 `~go finalize` 收口时生成 history\n",
            "<!-- sopify:auto:contracts:end -->\n\n",
            "## 当前焦点\n\n",
            "<!-- sopify:auto:focus:start -->\n",
            f"- 当前活动 plan：{'存在' if has_active_plan else '暂无'}。\n",
            focus_block,
            "<!-- sopify:auto:focus:end -->\n\n",
            "## 深入阅读入口\n\n",
            "<!-- sopify:auto:read-next:start -->\n",
            "\n".join(read_next),
            "\n",
            "<!-- sopify:auto:read-next:end -->\n",
        ]
    )


def _latest_archive_hint(config: RuntimeConfig) -> str | None:
    history_root = config.runtime_root / "history"
    if not history_root.exists():
        return None
    history_index = history_root / "index.md"
    if history_index.exists():
        latest_from_index = _latest_archive_hint_from_index(history_index)
        if latest_from_index is not None:
            return latest_from_index
    archive_dirs = sorted(path for path in history_root.glob("*/*") if path.is_dir())
    if not archive_dirs:
        return None
    latest = archive_dirs[-1]
    return "../" + str(latest.relative_to(config.runtime_root))


def _latest_archive_hint_from_index(history_index: Path) -> str | None:
    link_pattern = re.compile(r"\[[^\]]+\]\((?P<link>[^)]+)\)")
    for line in history_index.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        match = link_pattern.search(stripped)
        if match is None:
            continue
        link = match.group("link").strip().rstrip("/")
        if not link:
            continue
        normalized = link.removeprefix("./").lstrip("/")
        return f"../history/{normalized}"
    return None


def _blueprint_background_stub(language: str) -> str:
    if language == "en-US":
        return (
            "# Blueprint Background\n\n"
            "## Goals\n"
            "- Document long-lived goals, constraints, and non-goals.\n\n"
            "## Scope\n"
            "- In scope: to be refined.\n"
            "- Out of scope: to be refined.\n"
        )
    return (
        "# 蓝图背景\n\n"
        "## 目标\n"
        "- 记录长期目标、约束与非目标。\n\n"
        "## 范围\n"
        "- 范围内：待补充。\n"
        "- 范围外：待补充。\n"
    )


def _blueprint_design_stub(language: str) -> str:
    if language == "en-US":
        return (
            "# Blueprint Design\n\n"
            "## Stable Contracts\n"
            "- Module boundaries: to be refined.\n"
            "- Host contracts: to be refined.\n"
            "- Directory contracts: to be refined.\n"
        )
    return (
        "# 蓝图设计\n\n"
        "## 稳定契约\n"
        "- 模块边界：待补充。\n"
        "- 宿主契约：待补充。\n"
        "- 目录契约：待补充。\n"
    )


def _blueprint_tasks_stub(language: str) -> str:
    if language == "en-US":
        return (
            "# Blueprint Tasks\n\n"
            "- [ ] Document long-lived contracts.\n"
            "- [ ] Review blueprint updates at task close-out.\n"
        )
    return (
        "# 蓝图任务\n\n"
        "- [ ] 补齐长期稳定契约。\n"
        "- [ ] 在任务收口时回看 blueprint 是否需要更新。\n"
    )
