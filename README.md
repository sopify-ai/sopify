# Sopify

<div align="center">

<img src="./assets/logo.svg" width="120" alt="Sopify Logo" />

**Resumable, traceable AI coding — decisions and history stay with the project**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE)
[![Docs](https://img.shields.io/badge/docs-CC%20BY%204.0-green.svg)](./LICENSE-docs)
[![Version](https://img.shields.io/badge/version-2026--05--07.143021-orange.svg)](#version-history)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)

English · [简体中文](./README.zh-CN.md) · [Quick Start](#quick-start) · [Configuration](#configuration) · [Contributors](./CONTRIBUTORS.md)

</div>

---

## Why Sopify?

As repositories grow, AI-assisted development runs into a hidden problem: decision context stays trapped in chat history, each new session re-derives the project state, and the user's mental model, the AI's understanding, and the codebase start to drift apart.

Sopify uses project-level conventions to make critical steps visible: when facts are missing, it stops and asks for them; when a branch needs a decision, it waits for confirmation; when work is interrupted, it resumes from current state instead of improvising. The basic process record is generated automatically, but the long-term compounding value still depends on consistently closing out work and maintaining project knowledge.

### What You'll Actually Notice

- After an interruption, work resumes from the last stopping point — even when you switch to a different AI host or model.
- Complex changes can be independently reviewed in an isolated pass before execution.
- When a plan changes after execution was authorized, the AI cannot silently proceed — it re-confirms with you first.
- Plans, decisions, and review outcomes accumulate as reusable project assets, not disposable chat history.
- The AI pauses when facts are missing or a path needs your confirmation; simple tasks stay lightweight.

### What Kinds of Projects Benefit Most

- Multi-stage work that keeps moving in the same repository instead of one-off edits
- You're willing to manage progress with plan / blueprint artifacts and close out each stage

### What Your AI Host Doesn't Solve

| Gap | Sopify's answer |
|-----|-----------------|
| State is trapped in a single host's chat session | Portable project state — switch hosts mid-task |
| No independent quality gate | An isolated, independent review pass before execution |
| Decisions are invisible and non-auditable | Plan changes force re-confirmation — the AI cannot silently proceed |
| Each session's learning is disposable | Plans, decisions, and reviews persist as reusable project assets |

## Quick Start

Two ways to start, depending on your repo:

### Already using Sopify? Try it directly

If your repo has `.sopify-skills/`, open any AI host (Claude, Cursor, Codex…) and ask it to continue an unfinished task — it picks up from the last stopping point, not from scratch. That's the protocol working, no runtime needed.

Full Convention walkthrough: [protocol.md §4](./.sopify-skills/blueprint/protocol.md#4-典型生命周期样例)

### First time? Install first

```bash
# Recommended: official stable one-liner
curl -fsSL https://github.com/evidentloop/sopify/releases/latest/download/install.sh | bash -s -- --target codex:en-US

# Two-step install: download first, review, then run
curl -fsSL -o sopify-install.sh https://github.com/evidentloop/sopify/releases/latest/download/install.sh
sed -n '1,40p' sopify-install.sh
bash sopify-install.sh --target codex:en-US
```

Windows PowerShell can download the same stable asset and run it locally:

```powershell
iwr https://github.com/evidentloop/sopify/releases/latest/download/install.ps1 -OutFile sopify-install.ps1
Get-Content sopify-install.ps1 -TotalCount 40
.\sopify-install.ps1 --target codex:en-US
```

The repo-local / source install path remains available for developers and maintainers, but is no longer the first-screen entry:

```bash
bash scripts/install-sopify.sh --target codex:en-US
python3 scripts/install_sopify.py --target claude:en-US --workspace /path/to/project
```

Install targets:

- `codex:zh-CN`
- `codex:en-US`
- `claude:zh-CN`
- `claude:en-US`

The protocol (Convention mode) works with any host. Verified runtime integrations today:

| Host | Install target | Availability | Validation coverage | Notes |
|------|----------------|--------------|---------------------|-------|
| `codex` | `codex:zh-CN` / `codex:en-US` | Deep verified | Host install flow, workspace bootstrap, and runtime package smoke are verified | Suitable for daily use |
| `claude` | `claude:zh-CN` / `claude:en-US` | Deep verified | Host install flow, workspace bootstrap, and runtime package smoke are verified | Suitable for daily use |

Notes:

- Use `sopify status` / `sopify doctor` for detailed capability claims and live diagnostics
- `Availability` expresses the current delivery tier, while `Validation coverage` describes what has already been validated

Installer behavior:

- Installs the selected host prompt layer and the Sopify payload
- A standard install makes your host ready to run Sopify; most users do not need `--workspace`
- Sopify prepares `.sopify-runtime/` the first time you trigger it in a project workspace
- `--workspace` is an advanced prewarm path for maintainers, CI, or explicit repository setup

### How Your Workflow Changes After Install

- Use `~go` when you want Sopify to manage the full task workflow for you.
- Interrupt anytime — come back (even in a different tool) and resume from where you left off.
- Complex changes can get an independent review before execution starts.
- Run `status` to see current progress, `doctor` to troubleshoot.

### Verify Your Install

```bash
python3 scripts/sopify_status.py --format text
python3 scripts/sopify_doctor.py --format text
```

- `will bootstrap on first project trigger`: the host install is ready and the project-local runtime has not been prepared yet
- `workspace outcome: stub_selected [continue]`: the workspace runtime entry is healthy
- Payload or bundle corruption errors (for example `global_bundle_missing`, `global_bundle_incompatible`, or `global_index_corrupted`): repair the install and retry

### Choose an Entry by Task Size

| Task Type | Sopify Path |
|-----------|-------------|
| Simple change (≤2 files) | Direct execution |
| Medium task (3-5 files) | Light plan + execution |
| Complex work (>5 files / architecture change) | Full three-phase workflow |

### First Use

After install, open your selected host inside a repository and paste one of the prompts below.

```bash
# Simple task
"Fix the typo on line 42 in src/utils.ts"

# Medium task
"Add error handling to login, signup, and password reset"

# Complex task
"~go Add user authentication with JWT"

# Plan only
"~go plan Refactor the database layer"

# Replay / retrospective
"Replay the latest implementation and explain why this approach was chosen"
```

### What It Looks Like (Illustrative)

```text
[my-app-ai] Solution Design ✓

Plan: .sopify-skills/plan/20260323_auth/
Summary: JWT auth + token refresh + route guards
Tasks: 5 items

---
Next: Reply "continue" to start implementation
```

This is only a placeholder example of the pacing and format, not a fixed output contract; simple tasks are shorter, and complex tasks pause at checkpoints for confirmation.

For runtime gate, checkpoints, and plan lifecycle details, see [How Sopify Works](./docs/how-sopify-works.en.md).

### Recommended Workflow

```text
○ User Input
│
◆ Runtime Gate
│
◇ Routing Decision
├── ▸ Q&A / replay ───────────────────→ Direct output
└── ▸ Code task
    │
    ◇ Complexity Decision
    ├── Simple (≤2 files) ────────────→ Direct execution
    ├── Medium (3-5 files) ───────────→ Light plan package
    │                                   (single-file `plan.md`)
    └── Complex (>5 files / architecture change)
        ├── Requirements ··· Fact checkpoint
        ├── Design ··· Decision checkpoint
        └── Standard plan package
            (`background.md` / `design.md` / `tasks.md`)
            │
            ◆ Execution confirmation ··· User confirms
            │
            ◆ Implementation
            │
            ◆ Summary + handoff
            │
            ◇ Optional: ~go finalize
            ├── Refresh blueprint index
            ├── Clean active state
            └── Archive → history/
```

> ◆ = execution node　◇ = decision node　··· = checkpoint (pauses, then resumes after user input)
>
> See [How Sopify Works](./docs/how-sopify-works.en.md) for full details on checkpoints and plan lifecycle.

## Configuration

Start from the example config:

```bash
cp examples/sopify.config.yaml ./sopify.config.yaml
```

Most commonly used settings:

```yaml
brand: auto
language: en-US

workflow:
  mode: adaptive
  require_score: 7

plan:
  directory: .sopify-skills
```

Notes:

- `workflow.mode` supports `strict / adaptive / minimal`
- `plan.directory` only affects newly created knowledge and plan directories

## Command Reference

| Command | Description |
|---------|-------------|
| `~go` | Automatically route and run the full workflow |
| `~go plan` | Plan only |
| `~go exec` | Advanced restore/debug entry, not the default user path |
| `~go finalize` | Close out the current metadata-managed plan |

Most users only need `~go` and `~go plan`; maintainer validation commands live in [CONTRIBUTING.md](./CONTRIBUTING.md).

## Sub-skills

- `workflow-learning`: replay, retrospective, and step-by-step explanation
  Docs: [CN](./Codex/Skills/CN/skills/sopify/workflow-learning/SKILL.md) / [EN](./Codex/Skills/EN/skills/sopify/workflow-learning/SKILL.md)

Claude uses the mirrored `Claude/Skills/{CN,EN}/...` layout; the links above use the Codex tree as the canonical doc entry.

## Directory Structure

```text
sopify/
├── scripts/               # install, diagnostics, and maintainer scripts
├── examples/              # configuration examples
├── docs/                  # workflow guides and developer references
├── runtime/               # built-in runtime / skill packages
├── .sopify-skills/        # project knowledge base
│   ├── blueprint/         # design baseline, reduction targets
│   │   └── architecture-decision-records/  # ADR entity files
│   ├── plan/              # active plans
│   └── history/           # archived plans
├── Codex/                 # Codex host prompt layer
└── Claude/                # Claude host prompt layer
```

This is a simplified view of the core layout. See [docs/how-sopify-works.en.md](./docs/how-sopify-works.en.md) for the full workflow, checkpoints, and knowledge layout.

## FAQ

### Q: How do I switch language?

Update `sopify.config.yaml`:

```yaml
language: zh-CN  # or en-US
```

### Q: Where are plan packages stored?

By default they live under `.sopify-skills/` in the project root. To change that:

```yaml
plan:
  directory: .my-custom-dir
```

This only affects newly created directories; existing history is not migrated automatically.

### Q: When should I use `--workspace` prewarm?

Most users do not need it. A default install is already complete; Sopify bootstraps `.sopify-runtime/` automatically on the first project trigger.

Use `--workspace` only for maintainer validation, CI, or when you explicitly want to prewarm `.sopify-runtime/` for a specific repository ahead of time. For this advanced path, use the repo-local installer:

```bash
python3 scripts/install_sopify.py --target codex:en-US --workspace /path/to/project
```

### Q: How do I reset learned preferences?

Delete or clear `.sopify-skills/user/preferences.md`; keep `feedback.jsonl` only if you still want the audit trail.

### Q: When should I run sync scripts?

When you change `Codex/Skills/{CN,EN}`, the mirrored `Claude/Skills/{CN,EN}` content, or `runtime/builtin_skill_packages/*/skill.yaml`, follow the validation steps in [CONTRIBUTING.md](./CONTRIBUTING.md).

## Version History

- See [CHANGELOG.md](./CHANGELOG.md) for the detailed history

## License

This repository uses dual licensing:

- Code and config: Apache 2.0, see [LICENSE](./LICENSE)
- Documentation: CC BY 4.0, see [LICENSE-docs](./LICENSE-docs)

## Contributing

For user-visible behavior changes, update both `README.md` and `README.zh-CN.md` when needed, then follow [CONTRIBUTING.md](./CONTRIBUTING.md) for validation.
