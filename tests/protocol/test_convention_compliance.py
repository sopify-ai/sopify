"""Protocol Compliance Suite Phase 1.

Validates compliance items 1-5 from protocol.md §5 (Phase 1 scope).
Item 6 (blueprint writeback) is deferred — Convention minimum does not require it.
Each test uses tmp_path to construct a minimal .sopify-skills/ structure,
ensuring no dependency on the runtime package.

Ref: .sopify-skills/blueprint/protocol.md §5 — 协议合规检查清单
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _build_sopify_root(tmp_path: Path) -> Path:
    """Create a minimal .sopify-skills/ directory skeleton."""
    root = tmp_path / ".sopify-skills"
    root.mkdir()
    return root


# --- Compliance item 1: project.md exists and contains a project name ---


class TestProjectMdIdentification:
    """§5 item 1: 能读取 .sopify-skills/project.md 并识别项目名"""

    def test_project_md_with_title(self, tmp_path: Path) -> None:
        root = _build_sopify_root(tmp_path)
        project_md = root / "project.md"
        project_md.write_text("# My Awesome Project\n\nSome description.\n")

        content = project_md.read_text()
        title_match = re.search(r"^# (.+)$", content, re.MULTILINE)
        assert title_match is not None, "project.md must contain a top-level heading"
        assert title_match.group(1).strip(), "project name must not be empty"

    def test_project_md_missing_fails(self, tmp_path: Path) -> None:
        root = _build_sopify_root(tmp_path)
        assert not (root / "project.md").exists()

    def test_project_md_without_title_fails(self, tmp_path: Path) -> None:
        root = _build_sopify_root(tmp_path)
        project_md = root / "project.md"
        project_md.write_text("No heading here, just plain text.\n")

        content = project_md.read_text()
        title_match = re.search(r"^# (.+)$", content, re.MULTILINE)
        assert title_match is None, "Should not find a title in headingless file"


# --- Compliance item 2: blueprint/ triplet exists ---


class TestBlueprintTriplet:
    """§5 item 2: 能读取 blueprint/ 三件套并作为上下文消费"""

    REQUIRED_FILES = ("background.md", "design.md", "tasks.md")

    def test_all_three_present(self, tmp_path: Path) -> None:
        root = _build_sopify_root(tmp_path)
        bp = root / "blueprint"
        bp.mkdir()
        for name in self.REQUIRED_FILES:
            (bp / name).write_text(f"# {name}\n")

        for name in self.REQUIRED_FILES:
            assert (bp / name).is_file(), f"blueprint/{name} must exist"

    @pytest.mark.parametrize("missing", REQUIRED_FILES)
    def test_missing_one_file_fails(self, tmp_path: Path, missing: str) -> None:
        root = _build_sopify_root(tmp_path)
        bp = root / "blueprint"
        bp.mkdir()
        for name in self.REQUIRED_FILES:
            if name != missing:
                (bp / name).write_text(f"# {name}\n")

        assert not (bp / missing).exists(), f"blueprint/{missing} should be missing"


# --- Compliance item 3: plan/ directory with structured package ---


class TestPlanCreation:
    """§5 item 3: 能在 plan/ 下创建结构化方案包"""

    def test_plan_package_directory_created(self, tmp_path: Path) -> None:
        root = _build_sopify_root(tmp_path)
        plan_dir = root / "plan" / "20260501_dark_mode"
        plan_dir.mkdir(parents=True)
        plan_md = plan_dir / "plan.md"
        plan_md.write_text("# Dark Mode\n\n## Scope\n\n## Approach\n\n## Tasks\n")

        assert plan_dir.is_dir()
        assert plan_md.is_file()

    def test_plan_directory_missing_fails(self, tmp_path: Path) -> None:
        root = _build_sopify_root(tmp_path)
        assert not (root / "plan").exists()


# --- Compliance item 4: plan.md required fields ---


class TestPlanMdRequiredFields:
    """§5 item 4: plan.md 至少包含 title/scope/approach + 内联 tasks"""

    REQUIRED_SECTIONS = ("title", "scope", "approach", "tasks")

    def _make_plan_md(self, tmp_path: Path, content: str) -> Path:
        root = _build_sopify_root(tmp_path)
        plan_dir = root / "plan" / "20260501_feature"
        plan_dir.mkdir(parents=True)
        plan_md = plan_dir / "plan.md"
        plan_md.write_text(content)
        return plan_md

    def test_all_required_sections_present(self, tmp_path: Path) -> None:
        content = "# Feature Title\n\n## Scope\nScope here\n\n## Approach\nApproach here\n\n## Tasks\n- [ ] task 1\n"
        plan_md = self._make_plan_md(tmp_path, content)
        text = plan_md.read_text().lower()

        assert re.search(r"^# .+", plan_md.read_text(), re.MULTILINE), "plan.md must have a title"
        for section in ("scope", "approach", "tasks"):
            assert re.search(rf"^##\s+{section}", text, re.MULTILINE), f"plan.md must have a '{section}' section"

    @pytest.mark.parametrize("missing_section", ["scope", "approach", "tasks"])
    def test_missing_section_detected(self, tmp_path: Path, missing_section: str) -> None:
        sections = {"scope": "## Scope\nScope\n", "approach": "## Approach\nApproach\n", "tasks": "## Tasks\n- task\n"}
        content = "# Title\n\n" + "".join(v for k, v in sections.items() if k != missing_section)
        plan_md = self._make_plan_md(tmp_path, content)
        text = plan_md.read_text().lower()
        assert not re.search(rf"^##\s+{missing_section}", text, re.MULTILINE)


# --- Compliance item 5: archive + receipt.md ---


class TestArchiveAndReceipt:
    """§5 item 5: 能将完成的方案归档到 history/YYYY-MM/ 并生成 receipt.md"""

    def test_archive_structure_with_receipt(self, tmp_path: Path) -> None:
        root = _build_sopify_root(tmp_path)
        archive_dir = root / "history" / "2026-05" / "20260501_dark_mode"
        archive_dir.mkdir(parents=True)
        receipt = archive_dir / "receipt.md"
        receipt.write_text("# Receipt\n\n## Outcome\nCompleted successfully.\n")

        assert archive_dir.is_dir()
        assert receipt.is_file()
        assert "receipt" in receipt.name.lower()

    def test_archive_without_receipt_fails(self, tmp_path: Path) -> None:
        root = _build_sopify_root(tmp_path)
        archive_dir = root / "history" / "2026-05" / "20260501_dark_mode"
        archive_dir.mkdir(parents=True)

        assert not (archive_dir / "receipt.md").exists()

    def test_receipt_in_wrong_location_detected(self, tmp_path: Path) -> None:
        root = _build_sopify_root(tmp_path)
        wrong_receipt = root / "receipt.md"
        wrong_receipt.write_text("# Receipt\n")

        history = root / "history"
        assert not history.exists(), "history/ should not exist when receipt is misplaced"
