# Develop 详细规则

## 目标

按任务清单实施开发，维护任务状态，按 `knowledge_sync` 同步 V2 长期知识，并通过 task-level 质量循环确保“有验证证据才算完成”。

## 总流程

1. 读取任务清单。
2. 对每个任务按固定质量循环执行：实现修改 -> 发现验证 -> 执行验证 -> 必要时一次重试 -> 两阶段复审。仅在质量结果满足最小 contract 后更新任务状态。
3. 若工作区存在 `post_develop` advisory skill 且前置条件满足，执行一次 post-develop advisory review。
4. 按 `knowledge_sync` 同步知识库与偏好信息。
5. 迁移方案包到 `history/`。
6. 输出执行结果摘要。

## 步骤 1：读取任务清单

来源：

- `.sopify-skills/plan/{current_plan}/tasks.md`
- `.sopify-skills/plan/{current_plan}/plan.md`（light）

处理规则：

1. 提取 `[ ]` 待执行任务。
2. 按任务编号顺序执行。
3. 先检查显式依赖再执行。

## 步骤 2：执行任务

### 2.1 任务级质量循环

每个任务按以下顺序执行：

1. 定位目标文件。
2. 理解当前实现。
3. 实施修改。
4. 发现验证命令。
5. 执行验证。
6. 首次失败时允许带失败上下文自动重试一次。
7. 对失败收口做结构化根因分类。
8. 执行两阶段复审：`spec_compliance` -> `code_quality`。
9. 只有质量结果满足最小 contract 后才更新状态。

硬性约束：

- 没有验证证据，不算完成。
- `overbuild`、`underbuild`、`应该没问题` 这类主观判断不能替代验证或复审结果。
- 不允许静默跳过验证，也不允许无限重试。

### 2.2 最小 verify contract

develop 阶段统一使用以下字段名，不再混用 `discovery_source`、`status`、`configured`、`discovered` 等别名：

1. `verification_source`
   - 只表达验证来源，允许值固定为：
   - `project_contract`
   - `project_native`
   - `not_configured`
2. `command`
   - 记录本次尝试执行的验证命令。
   - 若没有稳定命令，允许为空，但必须补 `reason_code`，不能伪装为已验证。
3. `scope`
   - 记录验证覆盖的任务、文件或模块范围。
4. `result`
   - 固定使用：
   - `passed`
   - `retried`
   - `failed`
   - `skipped`
   - `replan_required`
5. `reason_code`
   - 当无法执行、显式降级、跳过或回退 plan review 时必须存在。
6. `retry_count`
   - v1 只允许 `0` 或 `1`。
7. `root_cause`
   - 失败收口或重试路径上必须存在。
8. `review_result`
   - 必须至少包含 `spec_compliance` 与 `code_quality` 两阶段结论。

补充说明：

- `.sopify-skills/project.md` 的 `verify` 约定是后续长期落点；当它已存在时，作为最高优先级来源，但不是当前 v1 落地前提。
- `verification_source` 只表示来源，不复用为结果态；“是否跳过/为何降级”统一通过 `result + reason_code` 表达。

### 2.3 验证发现顺序

固定优先级：

1. `project_contract`
   - 即 `.sopify-skills/project.md` 中已显式定义的 `verify` 约定。
2. `project_native`
   - 项目原生脚本或配置，例如 `package.json`、`pyproject.toml`、`Makefile`、`justfile` 中稳定的验证入口。
3. `not_configured`
   - 当仓库没有稳定命令时，必须可见降级，并写明 `reason_code`；不能把“没有找到命令”视为默认通过。

### 2.4 失败处理与根因分类

失败处理口径：

1. 第一次验证失败后，允许自动重试一次。
2. 第二次仍失败时，必须停止自动重试。
3. 第二次失败或显式放弃重试时，必须写入 `root_cause`。

`root_cause` 允许值固定为：

- `logic_regression`
- `environment_or_dependency`
- `missing_test_infra`
- `scope_or_design_mismatch`

分流约束：

- `logic_regression`：允许继续 develop，但必须带失败上下文修复。
- `environment_or_dependency`：可见标记环境无法证明通过，不把任务伪装为已验证完成。
- `missing_test_infra`：允许保留任务未验证完成，并显式写出补测要求。
- `scope_or_design_mismatch`：不得继续盲修，应优先回到 plan review、decision checkpoint 或其他宿主确认链路。

### 2.5 两阶段复审

Stage A `spec_compliance` 至少检查：

1. 是否满足当前任务目标与边界。
2. 是否存在明显 `overbuild` 或 `underbuild`。
3. 是否引入新的范围变化或需要用户拍板的分叉。

Stage B `code_quality` 至少检查：

1. 是否与现有代码风格一致。
2. 是否存在明显安全性、稳定性或可维护性回退。
3. 修改面、注释、测试与知识同步是否达到当前任务最低标准。

状态迁移：

- 成功：只有当 `verification_source / result / review_result` 满足最小 contract 时，才允许 `[ ] -> [x]`
- 跳过：`[ ] -> [-]`
- 阻塞：`[ ] -> [!]`

安全底线：

- 不引入常见漏洞（XSS / SQL 注入等）。
- 不破坏既有功能。
- 保持项目代码风格一致。

## 步骤 3：Post-develop advisory review

开发任务完成、验证与两阶段复审通过后，若工作区 `.agents/skills/` 下存在 triggers 包含 `post_develop` 且 mode 为 `advisory` 的技能，可按其 SKILL.md 执行一次 post-develop advisory review。当前仅 CrossReview Phase 4a 纳入此路径。

触发条件：

1. 所有任务已通过质量循环（Step 2 完成）。
2. 工作区存在未评审的代码变更（已提交的 review range `git diff <REF>..HEAD` 非空，或存在未提交变更须按 advisory skill Step 0 确认处理）。
3. 对应 advisory skill 的前置条件满足（如 CLI 已安装，且 host-integrated 审查所需的隔离执行上下文可用）。

执行约束：

- 执行失败或结果 `inconclusive` 不阻断主流程。
- `concerns` / `needs_human_triage` 只展示并等待用户决定，不自动写 checkpoint、不自动改代码。
- 若前置条件不满足（如 CLI 未安装），跳过并记录原因，不阻断。
- 注释：Phase 4a 仅采用 Convention 模式；这里不引入 `bridge.py`、`pipeline_hooks` 或 runtime lifecycle hook。

## 步骤 4：知识库同步

同步时机：

1. 每完成一个模块任务后。
2. 阶段收尾时做统一复核。

同步目标：

- `project.md`
- `blueprint/background.md`
- `blueprint/design.md`
- `blueprint/tasks.md`
- `user/preferences.md`（仅长期偏好）
- `user/feedback.jsonl`

正式判断口径：

- `knowledge_sync.skip`：本轮不要求同步。
- `knowledge_sync.review`：finalize 前至少复核。
- `knowledge_sync.required`：未更新则 finalize 阻断。

偏好写入（保守策略）：

允许写入：

- 用户明确表达长期偏好（如“以后默认...”）。

禁止写入：

- 一次性指令。
- 上下文不完整的猜测。
- 与任务无关的泛化结论。

## 步骤 5：方案迁移

迁移路径：

```text
.sopify-skills/plan/YYYYMMDD_feature/
  -> .sopify-skills/history/YYYY-MM/YYYYMMDD_feature/
```

索引更新：在首次显式 finalize 时按需创建并更新 `.sopify-skills/history/index.md`。

## 输出模板

按结果类型选择 `assets/`：

1. `assets/output-success.md`
2. `assets/output-partial.md`
3. `assets/output-quick-fix.md`

## 特殊情况

执行中断：

1. 已完成任务标记 `[x]`。
2. 当前任务保持 `[ ]`。
3. 输出中断摘要，等待宿主恢复。

任务失败：

1. 标记 `[!]` 并注明原因。
2. 若存在失败收口，必须补 `reason_code`，并在需要时补 `root_cause` 与 `review_result`。
3. 仅继续不受阻塞的独立任务。

回滚请求：

1. 使用 git 回滚（仅在用户明确要求时）。
2. 保留方案包在 `plan/`，不迁移。
3. 输出回滚确认。
