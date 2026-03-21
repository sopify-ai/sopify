---
name: templates
description: Document template collection; read when creating docs; includes all KB templates and plan file templates
---

# Document Template Collection

**Usage notes:**
1. Replace `{...}` with actual content.
2. Formal plan packages include the scoring block by default.
3. `blueprint/README.md` stays as a lightweight index only.

## A1 | Knowledge Base Templates

### project.md

```markdown
# Project Technical Conventions

## Tech Stack
- Core: {language version} / {framework version}
- Build: {build tool}
- Test: {test framework}

## Working Agreement
- Keep this file focused on reusable technical conventions.
- Do not treat one-off implementation choices as project-wide rules.

## Document Boundaries
- `project.md`: reusable conventions
- `blueprint/background.md`: long-term goals, scope, non-goals
- `blueprint/design.md`: module / host / directory / consumption contracts
- `blueprint/tasks.md`: unfinished long-term items and explicit deferrals
```

### blueprint/README.md

```markdown
# Project Blueprint Index

Status: {current status}
Maintenance: keep only entry-level index rows; move long explanations into other blueprint files

| Entry | Meaning | Status |
|-----|------|------|
| `../project.md` | Project-level technical conventions | active |
| `./background.md` | Long-term goals, scope, non-goals | active |
| `./design.md` | Module / host / directory / consumption contracts | active |
| `./tasks.md` | Unfinished long-term items and explicit deferrals | active |
| `../plan/` | Current active plan | on-demand |
| `../history/index.md` | Archive index | on-demand |
```

### blueprint/background.md

```markdown
# Blueprint Background

## Long-Term Goals
- {goal1}
- {goal2}

## Scope
- In scope: {content}
- Out of scope: {content}

## Non-Goals
- {content}
```

### blueprint/design.md

```markdown
# Blueprint Design

## Formal Contracts
- `knowledge_sync` is the only formal sync contract.
- `active_plan = current_plan.path + current_plan.files`.

## Consumption Contract

| Context Profile | Reads | Fail-open Rule | Notes |
|-----|------|------|------|
| `consult` | `project.md`, `preferences.md`, `blueprint/README.md` | missing deep blueprint does not fail | do not force plan materialization |
| `plan` | `L1` + `active_plan` | materialize deep blueprint by lifecycle when missing | history is not default context |
| `finalize` | `active_plan`, `knowledge_sync`, `blueprint/*`, `history/index.md` | create `history/index.md` on demand when missing | block when `required` sync is not satisfied |
```

### blueprint/tasks.md

```markdown
# Blueprint Tasks

## Unfinished Long-Term Items
- [ ] {long-term item}

## Explicit Deferrals
- [-] {deferred item}
```

### history/index.md

```markdown
# Change History Index

| Timestamp | Feature | Status | Plan Package |
|-----------|---------|--------|--------------|
| {YYYYMMDD} | {feature} | ✓ | [Link](YYYY-MM/...) |
```

### user/preferences.md

```markdown
# Long-Term User Preferences

> Record only explicitly stated long-term preferences. One-off instructions stay out of this file.

No confirmed long-term preferences yet.
```

### user/feedback.jsonl

```json
{"timestamp":"2026-01-15T10:30:00Z","source":"chat","message":"Use the smallest change list by default going forward","scope":"planning","promote_to_preference":true,"preference_id":"pref-002"}
{"timestamp":"2026-01-15T11:10:00Z","source":"chat","message":"Make the output more detailed for this task","scope":"current_task","promote_to_preference":false}
```

## A2 | Plan Package Templates

### Light Level - plan.md

```markdown
# {Feature Name}

## Background
{1-2 sentences describing the requirement background}

Scoring:
- Solution quality: {X}/10
- Implementation readiness: {Y}/10

Scoring rationale:
- Strengths: {1 line}
- Deductions: {1 line}

## Solution
- {technical point 1}
- {technical point 2}

## Tasks
- [ ] {task1}
- [ ] {task2}

## Changed Files
- {file1}
- {file2}
```

### Standard Level - background.md

```markdown
# Change Proposal: {Feature Name}

## Requirement Background
{Describe the current state, pain points, and change drivers}

Scoring:
- Solution quality: {X}/10
- Implementation readiness: {Y}/10

Scoring rationale:
- Strengths: {1 line}
- Deductions: {1 line}

## Change Content
1. {change point 1}
2. {change point 2}

## Impact Scope
- Modules: {list}
- Files: {list}

## Risk Assessment
- Risk: {description}
- Mitigation: {measures}
```

### Standard Level - design.md

```markdown
# Technical Design: {Feature Name}

## Technical Solution
- Core technology: {language/framework/library}
- Implementation points:
  - {point1}
  - {point2}

## Architecture Design
{Include a mermaid diagram when the architecture changes}

## Security and Performance
- Security: {measures}
- Performance: {optimizations}
```

### Standard Level - tasks.md

```markdown
# Task List: {Feature Name}

Directory: `.sopify-skills/plan/{YYYYMMDD}_{feature}/`

## 1. {Module Name}
- [ ] 1.1 Implement {feature} in `{file path}`
- [ ] 1.2 Implement {feature} in `{file path}`

## 2. Testing
- [ ] 2.1 {test task}

## 3. Documentation Update
- [ ] 3.1 Update `project.md / blueprint/background.md / blueprint/design.md / blueprint/tasks.md`
```

### Full Level - adr/{NNN}-{title}.md

```markdown
# ADR-{NNN}: {Decision Title}

## Status
Adopted | Pending | Deprecated

## Date
{YYYY-MM-DD}

## Context
{Background and problem statement}

## Decision
{Core decision content}
```

## A3 | Task Markers

| Marker | Meaning |
|--------|---------|
| `[ ]` | Pending |
| `[x]` | Completed |
| `[-]` | Skipped |
| `[!]` | Blocked |
