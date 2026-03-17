"""Minimal knowledge-base bootstrap for Sopify runtime."""

from __future__ import annotations

from pathlib import Path

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

    if _is_real_project_workspace(config.workspace_root):
        created_files.extend(ensure_blueprint_index(config))

    return KbArtifact(
        mode=config.kb_init,
        files=tuple(created_files),
        created_at=iso_now(),
    )


def _ensure_directories(root: Path) -> None:
    for relative_dir in (
        Path("blueprint"),
        Path("wiki"),
        Path("wiki/modules"),
        Path("user"),
        Path("history"),
    ):
        (root / relative_dir).mkdir(parents=True, exist_ok=True)


def ensure_blueprint_index(config: RuntimeConfig) -> tuple[str, ...]:
    """Create the lightweight blueprint index for real project workspaces."""
    root = config.runtime_root
    readme = root / "blueprint" / "README.md"
    if readme.exists():
        return ()
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(_blueprint_readme_stub(config), encoding="utf-8")
    return (str(readme.relative_to(config.workspace_root)),)


def ensure_blueprint_scaffold(config: RuntimeConfig) -> tuple[str, ...]:
    """Populate the full blueprint skeleton once the workspace enters plan lifecycle."""
    created = list(ensure_blueprint_index(config))
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
    return tuple(created)


def _bootstrap_files(config: RuntimeConfig) -> dict[Path, str]:
    project_name = config.workspace_root.name or "project"
    if config.kb_init == "full":
        return _full_files(config, project_name)
    return _progressive_files(config, project_name)


def _progressive_files(config: RuntimeConfig, project_name: str) -> dict[Path, str]:
    return {
        Path("project.md"): _project_stub(config, project_name),
        Path("wiki/overview.md"): _overview_stub(config, project_name),
        Path("user/preferences.md"): _preferences_stub(config.language),
        Path("history/index.md"): _history_stub(config.language),
    }


def _full_files(config: RuntimeConfig, project_name: str) -> dict[Path, str]:
    files = _progressive_files(config, project_name)
    files.update(
        {
            Path("wiki/arch.md"): _generic_doc_stub(config.language, "架构设计", "Architecture Notes"),
            Path("wiki/api.md"): _generic_doc_stub(config.language, "API 手册", "API Notes"),
            Path("wiki/data.md"): _generic_doc_stub(config.language, "数据模型", "Data Notes"),
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


def _overview_stub(config: RuntimeConfig, project_name: str) -> str:
    if config.language == "en-US":
        return (
            f"# {project_name}\n\n"
            "> Minimal project overview bootstrapped by Sopify runtime. See `modules/` for detailed module docs.\n\n"
            "## Project Overview\n\n"
            "### Goals & Background\n"
            "- To be documented.\n\n"
            "### Scope\n"
            "- In scope: to be documented.\n"
            "- Out of scope: to be documented.\n\n"
            "## Module Index\n\n"
            "| Module Name | Responsibility | Status | Docs |\n"
            "|-------------|----------------|--------|------|\n"
            "| pending | pending | planned | pending |\n\n"
            "## Quick Links\n"
            "- [Technical Conventions](../project.md)\n"
            "- [Change History](../history/index.md)\n"
        )

    return (
        f"# {project_name}\n\n"
        "> 由 Sopify runtime 初始化的最小项目概述。详细模块文档见 `modules/` 目录。\n\n"
        "## 项目概述\n\n"
        "### 目标与背景\n"
        "- 待补充。\n\n"
        "### 范围\n"
        "- 范围内：待补充。\n"
        "- 范围外：待补充。\n\n"
        "## 模块索引\n\n"
        "| 模块名称 | 职责 | 状态 | 文档 |\n"
        "|---------|------|------|------|\n"
        "| 待补充 | 待补充 | 规划中 | 待补充 |\n\n"
        "## 快速链接\n"
        "- [技术约定](../project.md)\n"
        "- [变更历史](../history/index.md)\n"
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


def _history_stub(language: str) -> str:
    if language == "en-US":
        return (
            "# Change History Index\n\n"
            "Records completed plan archives for future lookup.\n\n"
            "## Index\n\n"
            "No archived plans yet.\n"
        )

    return (
        "# 变更历史索引\n\n"
        "记录已归档的方案，便于后续查询。\n\n"
        "## 索引\n\n"
        "当前暂无已归档方案。\n"
    )


def _generic_doc_stub(language: str, zh_title: str, en_title: str) -> str:
    if language == "en-US":
        return f"# {en_title}\n\nTo be documented.\n"
    return f"# {zh_title}\n\n待补充。\n"


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


def _blueprint_readme_stub(config: RuntimeConfig) -> str:
    project_name = config.workspace_root.name or "project"
    if config.language == "en-US":
        return (
            "# Project Blueprint Index\n\n"
            "Status: initialized\n"
            "Maintenance: Sopify refreshes managed sections; free-text notes may be edited manually.\n\n"
            "## Current Goal\n\n"
            "<!-- sopify:auto:goal:start -->\n"
            f"- Build a stable long-lived blueprint for `{project_name}`.\n"
            "- Keep the active plan and history separate from long-lived docs.\n"
            "<!-- sopify:auto:goal:end -->\n\n"
            "## Project Overview\n\n"
            "<!-- sopify:auto:overview:start -->\n"
            "- blueprint: tracked long-lived project facts\n"
            "- plan: active working plan\n"
            "- history: finalized archives\n"
            "- replay: optional replay capability\n"
            "<!-- sopify:auto:overview:end -->\n\n"
            "## Architecture Map\n\n"
            "<!-- sopify:auto:architecture:start -->\n"
            "```text\n"
            ".sopify-skills/\n"
            "├── blueprint/\n"
            "├── plan/\n"
            "├── history/\n"
            "├── state/\n"
            "└── replay/\n"
            "```\n"
            "<!-- sopify:auto:architecture:end -->\n\n"
            "## Key Contracts\n\n"
            "<!-- sopify:auto:contracts:start -->\n"
            "- Create `blueprint/README.md` on the first real-project trigger.\n"
            "- Populate deeper blueprint files on the first plan lifecycle.\n"
            "- Archive plans into `history/` only during close-out.\n"
            "<!-- sopify:auto:contracts:end -->\n\n"
            "## Current Focus\n\n"
            "<!-- sopify:auto:focus:start -->\n"
            "- Track stable contracts here and keep task execution inside `plan/`.\n"
            "<!-- sopify:auto:focus:end -->\n\n"
            "## Read Next\n\n"
            "<!-- sopify:auto:read-next:start -->\n"
            "- [Technical Conventions](../project.md)\n"
            "- [Project Overview](../wiki/overview.md)\n"
            "- Active plan: `../plan/`\n"
            "<!-- sopify:auto:read-next:end -->\n"
        )

    return (
        "# 项目蓝图索引\n\n"
        "状态: 已初始化\n"
        "维护方式: Sopify 托管自动区块，说明区块允许人工补充。\n\n"
        "## 当前目标\n\n"
        "<!-- sopify:auto:goal:start -->\n"
        f"- 为 `{project_name}` 建立稳定的长期蓝图入口。\n"
        "- 把活动 plan 与长期蓝图、历史归档分层维护。\n"
        "<!-- sopify:auto:goal:end -->\n\n"
        "## 项目概览\n\n"
        "<!-- sopify:auto:overview:start -->\n"
        "- blueprint: 长期项目真相，默认入库\n"
        "- plan: 当前活动方案\n"
        "- history: 收口后的历史归档\n"
        "- replay: 可选回放能力\n"
        "<!-- sopify:auto:overview:end -->\n\n"
        "## 架构地图\n\n"
        "<!-- sopify:auto:architecture:start -->\n"
        "```text\n"
        ".sopify-skills/\n"
        "├── blueprint/\n"
        "├── plan/\n"
        "├── history/\n"
        "├── state/\n"
        "└── replay/\n"
        "```\n"
        "<!-- sopify:auto:architecture:end -->\n\n"
        "## 关键契约\n\n"
        "<!-- sopify:auto:contracts:start -->\n"
        "- 首次真实项目触发时创建 `blueprint/README.md`\n"
        "- 首次进入 plan 生命周期时补齐深层 blueprint 文件\n"
        "- 仅在任务收口时归档到 `history/`\n"
        "<!-- sopify:auto:contracts:end -->\n\n"
        "## 当前焦点\n\n"
        "<!-- sopify:auto:focus:start -->\n"
        "- 长期契约写 blueprint，任务执行细节写 plan。\n"
        "<!-- sopify:auto:focus:end -->\n\n"
        "## 深入阅读入口\n\n"
        "<!-- sopify:auto:read-next:start -->\n"
        "- [项目技术约定](../project.md)\n"
        "- [项目概览](../wiki/overview.md)\n"
        "- 当前活动方案: `../plan/`\n"
        "<!-- sopify:auto:read-next:end -->\n"
    )


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
