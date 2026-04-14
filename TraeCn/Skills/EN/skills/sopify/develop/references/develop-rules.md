# Develop Detailed Rules

## Goal

Implement the task list, maintain task state, sync V2 long-lived knowledge through `knowledge_sync`, and enforce a task-level quality loop so work is not treated as complete without verification evidence.

## Overall flow

1. Read the task list.
2. Execute each task through the fixed quality loop: implement change -> discover verification -> run verification -> retry once when needed -> perform two-stage review.
3. Update task markers only after the minimum quality contract is satisfied.
4. Sync KB and preference data through `knowledge_sync`.
5. Move the completed plan into `history/`.
6. Render the execution summary.

## Step 1: Read the task list

Sources:

- `.sopify-skills/plan/{current_plan}/tasks.md`
- `.sopify-skills/plan/{current_plan}/plan.md` (light)

Handling rules:

1. Extract `[ ]` pending tasks.
2. Execute by task number order.
3. Check explicit dependencies before execution.

## Step 2: Execute tasks

### 2.1 Task-level quality loop

Process each task in this order:

1. Locate the target file.
2. Understand the current implementation.
3. Implement the change.
4. Discover the verification command.
5. Run verification.
6. If the first verification run fails, allow one automatic retry with failure context.
7. Classify the failure close-out with a structured root cause.
8. Run the two-stage review: `spec_compliance` -> `code_quality`.
9. Update the task marker only after the minimum quality contract is satisfied.

Hard requirements:

- No verification evidence means the task is not complete.
- Subjective claims such as `overbuild`, `underbuild`, or "it should be fine" never replace verification or review evidence.
- Do not silently skip verification and do not retry indefinitely.

### 2.2 Minimum verify contract

Use the following field names consistently in develop flows. Do not introduce aliases such as `discovery_source`, `status`, `configured`, or `discovered`:

1. `verification_source`
   - Only expresses where the verification came from. Allowed values are:
   - `project_contract`
   - `project_native`
   - `not_configured`
2. `command`
   - Records the verification command attempted for this task.
   - It may be empty when no stable command exists, but `reason_code` is then required and the task must not be presented as verified.
3. `scope`
   - Records the task, file, or module scope covered by verification.
4. `result`
   - Must use:
   - `passed`
   - `retried`
   - `failed`
   - `skipped`
   - `replan_required`
5. `reason_code`
   - Required whenever verification cannot run, degrades visibly, is skipped, or routes back to plan review.
6. `retry_count`
   - v1 only allows `0` or `1`.
7. `root_cause`
   - Required for failed close-out paths and retry close-out paths.
8. `review_result`
   - Must contain at least the stage conclusions for `spec_compliance` and `code_quality`.

Additional rules:

- `.sopify-skills/project.md` is the future long-term home for a project-level `verify` contract. When present, it has the highest priority, but it is not a prerequisite for v1.
- `verification_source` is a source field only. Degrade/skip outcomes must be expressed through `result + reason_code`.

### 2.3 Verification discovery order

Use this fixed priority:

1. `project_contract`
   - A `verify` contract already defined in `.sopify-skills/project.md`.
2. `project_native`
   - Stable native project entry points such as `package.json`, `pyproject.toml`, `Makefile`, or `justfile`.
3. `not_configured`
   - If no stable command exists, degrade visibly and record `reason_code`; do not treat "no command found" as an implicit pass.

### 2.4 Failure handling and root cause classification

Failure handling rules:

1. Allow one automatic retry after the first failed verification run.
2. Stop automatic retries after the second failure.
3. Record `root_cause` whenever the second failure happens or retry is explicitly abandoned.

Allowed `root_cause` values:

- `logic_regression`
- `environment_or_dependency`
- `missing_test_infra`
- `scope_or_design_mismatch`

Routing constraints:

- `logic_regression`: stay in develop, but continue with concrete failure context.
- `environment_or_dependency`: make the environment limitation visible and do not present the task as verified.
- `missing_test_infra`: keep the task unverified and record the missing-test follow-up explicitly.
- `scope_or_design_mismatch`: do not keep patching blindly; return to plan review, a decision checkpoint, or another host confirmation path.

### 2.5 Two-stage review

Stage A `spec_compliance` must at least check:

1. Whether the task goal and boundaries were met.
2. Whether there is obvious `overbuild` or `underbuild`.
3. Whether the change introduced a new scope shift or a user-facing decision branch.

Stage B `code_quality` must at least check:

1. Consistency with the existing code style.
2. No obvious security, stability, or maintainability regression.
3. Whether the change size, comments, tests, and KB sync meet the minimum standard for the task.

State transitions:

- Success: `[ ] -> [x]` is allowed only when `verification_source / result / review_result` satisfy the minimum contract
- Skipped: `[ ] -> [-]`
- Blocked: `[ ] -> [!]`

Security baseline:

- Do not introduce common vulnerabilities (XSS / SQL injection / etc.).
- Do not break existing behavior.
- Keep the project style consistent.

## Step 3: Sync the knowledge base

Sync timing:

1. After each module-level task batch.
2. Once again during phase close-out.

Sync targets:

- `project.md`
- `blueprint/background.md`
- `blueprint/design.md`
- `blueprint/tasks.md`
- `user/preferences.md` (long-term preferences only)
- `user/feedback.jsonl`

Formal rule:

- `knowledge_sync.skip`: no sync required
- `knowledge_sync.review`: at least review before finalize
- `knowledge_sync.required`: finalize must block until updated

Conservative preference writes:

Allowed:

- Explicit long-term user preferences such as "use this by default going forward".

Disallowed:

- One-off instructions.
- Guesses from incomplete context.
- Generalized conclusions unrelated to the task.

## Step 4: Plan migration

Migration path:

```text
.sopify-skills/plan/YYYYMMDD_feature/
  -> .sopify-skills/history/YYYY-MM/YYYYMMDD_feature/
```

Create and update `.sopify-skills/history/index.md` on demand during the first explicit finalize.

## Output templates

Choose the result format from `assets/`:

1. `assets/output-success.md`
2. `assets/output-partial.md`
3. `assets/output-quick-fix.md`

## Special cases

Execution interruption:

1. Mark completed tasks as `[x]`.
2. Keep the current task as `[ ]`.
3. Render the interruption summary and wait for host recovery.

Task failure:

1. Mark the task as `[!]` with the reason.
2. For any closed-out failure path, record `reason_code`, and add `root_cause` plus `review_result` when required.
3. Continue only with independent tasks that are not blocked by the failure.

Rollback request:

1. Use git rollback only when the user explicitly requests it.
2. Keep the plan package in `plan/` instead of migrating it.
3. Render rollback confirmation.
