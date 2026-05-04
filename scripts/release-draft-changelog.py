#!/usr/bin/env python3
"""Auto-draft root CHANGELOG [Unreleased] notes from staged release-relevant files.

Output structure (per release entry):
  1. Summary   — 1-3 sentence user-visible impact
  2. Plan pkgs — grouped by plan_id / feature_key / lifecycle_state
  3. Details   — file list in <details> collapsible block
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path


UNRELEASED_HEADER = "## [Unreleased]"

SECTION_DEFINITIONS = (
    ("Docs", "Refined public documentation"),
    ("Runtime", "Updated runtime internals"),
    ("Scripts", "Adjusted maintenance scripts"),
    ("Skills", "Synced prompt-layer skills"),
    ("Tests", "Updated automated coverage"),
    ("Changed", "Updated project files"),
)

# .sopify-skills/ paths that ARE eligible for changelog (plan package attribution)
_SOPIFY_WHITELIST_PREFIXES = (
    ".sopify-skills/plan/",
    ".sopify-skills/history/",
)

# Paths to always exclude from changelog (noise)
_ALWAYS_EXCLUDE = {
    "CHANGELOG.md",
}

# Pattern to extract plan_id from whitelisted .sopify-skills/ paths
_PLAN_ID_RE = re.compile(
    r"^\.sopify-skills/(?:plan|history/\d{4}-\d{2})/(\d{8}_[^/]+)/"
)


def _repo_matches_current_git_env(root: Path) -> bool:
    env = os.environ
    work_tree = (env.get("GIT_WORK_TREE") or "").strip()
    if work_tree:
        try:
            return Path(work_tree).resolve() == root.resolve()
        except OSError:
            return False

    git_dir = (env.get("GIT_DIR") or "").strip()
    if git_dir:
        try:
            return Path(git_dir).resolve() == (root / ".git").resolve()
        except OSError:
            return False
    return False


def git_command_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    if _repo_matches_current_git_env(root):
        return env
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draft CHANGELOG.md [Unreleased] notes from staged files.")
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--changelog-path",
        default=None,
        help="Optional explicit changelog path. Defaults to <root>/CHANGELOG.md.",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Explicit changed file path. Repeatable. When omitted, reads staged files from git.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    changelog_path = Path(args.changelog_path).resolve() if args.changelog_path else root / "CHANGELOG.md"

    changed_files = [path for path in args.file if str(path).strip()]
    if not changed_files:
        changed_files = staged_files(root)
    if not changed_files:
        changed_files = working_tree_files(root)

    result = draft_changelog(changelog_path, changed_files, root)
    print(result)
    return 0


def staged_files(root: Path) -> list[str]:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "diff.renames=false",
            "diff",
            "--cached",
            "--name-only",
            "--no-renames",
            "--no-ext-diff",
            "--diff-filter=ACMRDTUXB",
            "--",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=git_command_env(root),
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr.strip() or "Failed to collect staged files.")
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def working_tree_files(root: Path) -> list[str]:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "diff.renames=false",
            "diff",
            "--name-only",
            "--no-renames",
            "--no-ext-diff",
            "HEAD",
            "--",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=git_command_env(root),
    )
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def draft_changelog(changelog_path: Path, changed_files: list[str], root: Path) -> str:
    if not changelog_path.is_file():
        raise SystemExit(f"Missing changelog: {changelog_path}")

    text = changelog_path.read_text(encoding="utf-8")
    start, end = unreleased_bounds(text)
    unreleased_body = text[start:end].strip()
    if unreleased_body:
        return "CHANGELOG [Unreleased] already has content. Skipped auto-draft."

    normalized_files = dedupe_paths(changed_files)
    if not normalized_files:
        return "No changed files found. Skipped auto-draft."

    eligible_files = [path for path in normalized_files if include_in_changelog(path)]
    if not eligible_files:
        return "No release-note-eligible changed files found. Skipped auto-draft."

    draft = render_draft(eligible_files, root)
    updated = text[:start] + "\n\n" + draft + "\n" + text[end:]
    changelog_path.write_text(updated, encoding="utf-8")
    return f"Auto-drafted CHANGELOG [Unreleased] from {len(eligible_files)} changed files."


def unreleased_bounds(text: str) -> tuple[int, int]:
    header_start = text.find(UNRELEASED_HEADER)
    if header_start < 0:
        raise SystemExit(f"Missing section: {UNRELEASED_HEADER}")
    body_start = header_start + len(UNRELEASED_HEADER)
    next_header = text.find("\n## [", body_start)
    if next_header < 0:
        next_header = len(text)
    return body_start, next_header


def dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in paths:
        path = str(raw).strip().replace("\\", "/")
        if not path or path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def include_in_changelog(path: str) -> bool:
    normalized = path.strip().replace("\\", "/")
    if normalized in _ALWAYS_EXCLUDE:
        return False
    if normalized.startswith(".sopify-skills/"):
        # Only plan package paths (matching YYYYMMDD_slug pattern) are eligible
        return bool(_PLAN_ID_RE.match(normalized))
    return True


def _detect_plan_lifecycle(plan_id: str, path: str, root: Path) -> str:
    """Detect lifecycle state of a plan package: archived / active / unknown."""
    if "/history/" in path:
        return "archived"
    plan_dir = root / ".sopify-skills" / "plan" / plan_id
    if plan_dir.is_dir():
        for candidate in ("tasks.md", "plan.md"):
            meta_file = plan_dir / candidate
            if meta_file.is_file():
                try:
                    content = meta_file.read_text(encoding="utf-8")[:500]
                    if "lifecycle_state: archived" in content or "plan_status: completed" in content:
                        return "archived"
                except OSError:
                    pass
        return "active"
    return "unknown"


def classify_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    if normalized.startswith(("README", "CONTRIBUTING", "docs/", "LICENSE")):
        return "Docs"
    if normalized.startswith("runtime/"):
        return "Runtime"
    if normalized.startswith("scripts/"):
        return "Scripts"
    if normalized.startswith(("Codex/", "Claude/")):
        return "Skills"
    if normalized.startswith("tests/"):
        return "Tests"
    return "Changed"


def _extract_plan_packages(files: list[str], root: Path) -> dict[str, dict]:
    """Extract plan package info from whitelisted .sopify-skills/ paths."""
    packages: dict[str, dict] = {}
    for path in files:
        m = _PLAN_ID_RE.match(path)
        if m:
            plan_id = m.group(1)
            if plan_id not in packages:
                lifecycle = _detect_plan_lifecycle(plan_id, path, root)
                packages[plan_id] = {"lifecycle": lifecycle, "files": []}
            packages[plan_id]["files"].append(path)
    return packages


def render_draft(changed_files: list[str], root: Path) -> str:
    plan_packages = _extract_plan_packages(changed_files, root)

    non_plan_files = [
        f for f in changed_files
        if not f.startswith(".sopify-skills/")
    ]

    grouped: dict[str, list[str]] = {title: [] for title, _ in SECTION_DEFINITIONS}
    for path in non_plan_files:
        grouped[classify_path(path)].append(path)

    blocks: list[str] = []

    # Layer 1: Summary placeholder
    summary_parts: list[str] = []
    if plan_packages:
        archived = [pid for pid, info in plan_packages.items() if info["lifecycle"] == "archived"]
        active = [pid for pid, info in plan_packages.items() if info["lifecycle"] == "active"]
        if archived:
            summary_parts.append(f"Archived {len(archived)} plan package(s)")
        if active:
            summary_parts.append(f"Updated {len(active)} active plan package(s)")
    non_empty_sections = [title for title, _ in SECTION_DEFINITIONS if grouped[title]]
    if non_empty_sections:
        summary_parts.append(f"Changes across: {', '.join(non_empty_sections)}")
    if summary_parts:
        blocks.append("### Summary\n\n- " + "; ".join(summary_parts) + ".")

    # Layer 2: Plan packages
    if plan_packages:
        pkg_lines = ["### Plan Packages", ""]
        for plan_id in sorted(plan_packages):
            info = plan_packages[plan_id]
            pkg_lines.append(f"- `{plan_id}` ({info['lifecycle']})")
        blocks.append("\n".join(pkg_lines))

    # Layer 3: File details in collapsible block
    detail_lines: list[str] = []
    for title, summary in SECTION_DEFINITIONS:
        if grouped[title]:
            detail_lines.append(f"**{title}** — {summary}:")
            detail_lines.extend(f"  - `{path}`" for path in grouped[title])
            detail_lines.append("")
    if plan_packages:
        detail_lines.append("**Plan package files**:")
        for plan_id in sorted(plan_packages):
            for f in plan_packages[plan_id]["files"]:
                detail_lines.append(f"  - `{f}`")
        detail_lines.append("")

    if detail_lines:
        blocks.append(
            "<details>\n<summary>File details</summary>\n\n"
            + "\n".join(detail_lines)
            + "\n</details>"
        )

    return "\n\n".join(blocks)


if __name__ == "__main__":
    raise SystemExit(main())
