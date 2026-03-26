#!/usr/bin/env python3
"""Validate host-facing consult and gate doc contracts in Codex source docs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class DocSpec:
    path: Path
    route_label: str
    flow_prefix: str
    forbidden_answer: str
    required_behavior_terms: tuple[str, ...]
    required_rule_snippets: tuple[str, ...]
    fail_closed_snippets: tuple[str, ...]


DOC_SPECS = (
    DocSpec(
        path=REPO_ROOT / "Codex/Skills/CN/AGENTS.md",
        route_label="咨询问答",
        flow_prefix="├─ 咨询问答 →",
        forbidden_answer="直接回答",
        required_behavior_terms=("gate", "consult handoff", "宿主"),
        required_rule_snippets=(
            "required_host_action == continue_host_consult",
            "不得在 gate 前自行路由，也不得在 gate 后再次重判",
        ),
        fail_closed_snippets=(
            "当前消息回合",
            "tool call",
            "scripts/runtime_gate.py enter",
            ".sopify-skills/state/current_gate_receipt.json",
        ),
    ),
    DocSpec(
        path=REPO_ROOT / "Codex/Skills/EN/AGENTS.md",
        route_label="Q&A",
        flow_prefix="├─ Q&A →",
        forbidden_answer="Direct answer",
        required_behavior_terms=("gate", "consult handoff", "host"),
        required_rule_snippets=(
            "required_host_action == continue_host_consult",
            "must not self-route before the gate",
            "must not re-decide consult vs non-consult after the gate",
        ),
        fail_closed_snippets=(
            "current message turn",
            "tool call",
            "scripts/runtime_gate.py enter",
            ".sopify-skills/state/current_gate_receipt.json",
        ),
    ),
)


def _extract_route_table_row(text: str, route_label: str) -> tuple[str, str]:
    table_match = re.search(
        r"(?ms)^\*\*(?:路由类型：?|Route Types:?)\*\*\n\n(?P<table>(?:\|.*\n)+)",
        text,
    )
    if not table_match:
        raise ValueError("missing Route Types table")

    table = table_match.group("table")
    for raw_line in table.splitlines():
        if not raw_line.startswith("|"):
            continue
        cells = [cell.strip() for cell in raw_line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] != route_label:
            continue
        return raw_line, cells[2]
    raise ValueError(f"missing route table row for {route_label}")


def _extract_flow_line(text: str, flow_prefix: str) -> str:
    for raw_line in text.splitlines():
        if raw_line.startswith(flow_prefix):
            return raw_line
    raise ValueError(f"missing flow line starting with {flow_prefix!r}")


def validate_doc(spec: DocSpec) -> list[str]:
    errors: list[str] = []
    text = spec.path.read_text(encoding="utf-8")

    try:
        flow_line = _extract_flow_line(text, spec.flow_prefix)
    except ValueError as exc:
        errors.append(str(exc))
    else:
        if spec.forbidden_answer in flow_line:
            errors.append(f"flow line still contains forbidden answer text: {flow_line}")
        for term in spec.required_behavior_terms:
            if term not in flow_line:
                errors.append(f"flow line missing term {term!r}: {flow_line}")

    try:
        row_line, behavior = _extract_route_table_row(text, spec.route_label)
    except ValueError as exc:
        errors.append(str(exc))
    else:
        if spec.forbidden_answer in behavior:
            errors.append(f"route table behavior still contains forbidden answer text: {behavior}")
        for term in spec.required_behavior_terms:
            if term not in behavior:
                errors.append(f"route table behavior missing term {term!r}: {row_line}")

    for snippet in spec.required_rule_snippets:
        if snippet not in text:
            errors.append(f"missing consult rule snippet: {snippet}")

    for snippet in spec.fail_closed_snippets:
        if snippet not in text:
            errors.append(f"missing fail-closed snippet: {snippet}")

    return errors


def main() -> int:
    failures: list[str] = []
    for spec in DOC_SPECS:
        errors = validate_doc(spec)
        if not errors:
            continue
        failures.append(f"[{spec.path.relative_to(REPO_ROOT)}]")
        failures.extend(f"  - {error}" for error in errors)

    if failures:
        print("Host doc contract check failed:")
        print("\n".join(failures))
        return 1

    checked = ", ".join(str(spec.path.relative_to(REPO_ROOT)) for spec in DOC_SPECS)
    print(f"Host doc contract check passed: {checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
