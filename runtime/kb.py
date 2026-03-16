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

    return KbArtifact(
        mode=config.kb_init,
        files=tuple(created_files),
        created_at=iso_now(),
    )


def _ensure_directories(root: Path) -> None:
    for relative_dir in (
        Path("wiki"),
        Path("wiki/modules"),
        Path("user"),
        Path("history"),
    ):
        (root / relative_dir).mkdir(parents=True, exist_ok=True)


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
