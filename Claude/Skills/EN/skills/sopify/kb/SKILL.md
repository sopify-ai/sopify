---
name: kb
description: Knowledge base management skill; read during KB operations; includes init, update, sync strategies
---

# Knowledge Base Management - V2 Rules

**Goal:** manage the V2 layers in `.sopify-skills/` so long-lived knowledge, the active plan, and finalized archives stay clearly separated.

## Knowledge Base Structure

```text
.sopify-skills/
├── blueprint/
│   ├── README.md           # Pure index page with entry-level status only
│   ├── background.md       # Long-term goals, scope, non-goals
│   ├── design.md           # Module / host / directory / consumption contracts
│   └── tasks.md            # Unfinished long-term items and explicit deferrals
├── project.md              # Project technical conventions
├── user/
│   ├── preferences.md      # Long-term user preferences
│   └── feedback.jsonl      # Raw feedback events
├── plan/
│   └── YYYYMMDD_feature/   # Current active plan
├── history/
│   ├── index.md            # Archive index
│   └── YYYY-MM/
└── state/                  # Runtime machine truth
```

## Initialization Strategy

### Full mode (`kb_init: full`)

Create on the first bootstrap:

```yaml
Create:
  - .sopify-skills/project.md
  - .sopify-skills/user/preferences.md
  - .sopify-skills/user/feedback.jsonl
  - .sopify-skills/blueprint/README.md
  - .sopify-skills/blueprint/background.md
  - .sopify-skills/blueprint/design.md
  - .sopify-skills/blueprint/tasks.md
```

Notes:

- Do not pre-create `plan/` content.
- Do not pre-create `history/index.md` or any archive.

### Progressive mode (`kb_init: progressive`) [default]

Materialize by lifecycle:

```yaml
First real-project trigger:
  - .sopify-skills/project.md
  - .sopify-skills/user/preferences.md
  - .sopify-skills/blueprint/README.md

First plan lifecycle:
  - .sopify-skills/blueprint/background.md
  - .sopify-skills/blueprint/design.md
  - .sopify-skills/blueprint/tasks.md
  - .sopify-skills/plan/YYYYMMDD_feature/

First explicit ~go finalize:
  - .sopify-skills/history/index.md
  - .sopify-skills/history/YYYY-MM/YYYYMMDD_feature/

First explicit long-term preference:
  - .sopify-skills/user/feedback.jsonl
```

## Read Order

1. `project.md`
2. `user/preferences.md`
3. `blueprint/README.md`
4. `blueprint/background.md`
5. `blueprint/design.md`
6. `blueprint/tasks.md`
7. `active_plan = current_plan.path + current_plan.files`

Rules:

- consult / clarification routes prefer `L0/L1` and must not require deep blueprint files
- planning / develop may enter `L2 active plan`
- `history/` is not the default long-lived context source; read it only for finalize lookups or human traceability

## Update Rules

### Must update

- `project.md`: reusable technical conventions changed
- `blueprint/background.md`: long-term goals, scope, or non-goals changed
- `blueprint/design.md`: module, host, directory, or consumption contracts changed
- `blueprint/tasks.md`: unfinished long-term items or explicit deferrals changed
- `user/preferences.md`: the user explicitly stated a long-term preference

### Must not be written into long-lived knowledge

- one-off implementation details
- short-term task breakdown from the current plan
- temporary tradeoffs that belong only to this task
- copying history body text back into blueprint

## `knowledge_sync` Sync Contract

```yaml
knowledge_sync:
  project: skip|review|required
  background: skip|review|required
  design: skip|review|required
  tasks: skip|review|required
```

Execution rules:

- `skip`: no sync required for this round
- `review`: at least review before finalize
- `required`: finalize must block until updated

## Conflict Handling

- code vs docs: code is the source of truth, then update docs
- current task vs long-term preference: current explicit task > `user/preferences.md` > default rules

## Output Format

**Initialization complete:**

```text
[{BRAND_NAME}] Knowledge Base Init ✓

Created: {N} files
Strategy: {full/progressive}

---
Changes: {N} files
  - .sopify-skills/project.md
  - .sopify-skills/blueprint/README.md
  - ...

Next: KB is ready
```

**Sync complete:**

```text
[{BRAND_NAME}] Knowledge Base Sync ✓

Updated: {N} files

---
Changes: {N} files
  - .sopify-skills/project.md
  - .sopify-skills/blueprint/design.md
  - ...

Next: Docs updated
```
