# 技术设计: 显式主体与生命周期收敛（第一子切片）

## 设计结论

本包不做“去 runtime 化”，做的是“archive 生命周期语义从 runtime 状态机中回收并下沉”：

- **Protocol 层** 定义 archive 的主体、场景、错误模型和 lifecycle 语义。
- **Deterministic core** 承担 `archive/check`、`archive/doctor`、`archive/apply`。
- **Runtime 层** 只保留入口适配：识别 `~go finalize` / 相关命令，调用 deterministic core，并生成 handoff/output。

核心原则：

1. archive 是协议资产治理，不是 develop 交互流程。
2. archive 依赖显式主体解析，不依赖 active run 状态机。
3. runtime 可调用 archive core，但不再拥有 archive 语义。
4. 在无线上用户前提下，旧 finalize 绕行链路允许直接删除，而不是长期兼容。

---

## 当前问题建模

### 1. 错误的语义归属

当前 `~go finalize` 被路由为 `finalize_active`，随后 engine 直接对 `recovered.current_plan` 做 finalize。这意味着：

- finalize 面向的是“当前活动 plan”
- 不是“用户显式请求的 archive 主体”
- 没有 active plan 时，即使 request 中明确点名某个 plan，也不能直接归档

这会把 archive 错误地纳入 `execution_confirm_pending / resume_active / state_conflict` 等运行时交互语义。

### 2. 错误的主体解析

archive 需要回答的问题是：

- 当前归档对象是谁？
- 它是 managed plan、legacy plan、还是已归档 plan？
- 是否存在歧义？

而不是：

- 当前有没有 active run？
- 当前 handoff 要不要继续 develop？

现状把“主体选择”混在 active flow 里，导致跨 session 场景下 archive 先被强行翻译成执行态恢复问题。

### 3. 错误的删除策略

如果继续保留旧 finalize 语义，同时再补 archive/validator，会出现双轨：

- 一条是 runtime finalize_active
- 一条是 protocol archive/check|doctor|apply

在无线上用户前提下，这是典型的过度兼容。应该直接收敛到单轨。

---

## 目标语义

### 1. archive 操作面

本包将 archive 收敛为三个 deterministic 操作：

```text
archive/check
archive/doctor
archive/apply
```

含义：

- `check`：只读检查一个 archive 主体能否归档，给出错误码、缺失项、迁移需求、目标路径冲突等。
- `doctor`：对 legacy / 不完整 metadata plan 执行最小 adopt/migrate，使其满足 archive 前置条件。
- `apply`：真正归档到 history，并更新相关索引与状态清理。

`~go finalize` 不再直接等价于“活动流 finalize_active”，而是宿主侧的 archive 入口命令，默认调用 `check`，在条件满足时进入 `apply`。

### 2. 显式主体解析

archive 专属主体解析规则只覆盖本包需要的最小集合：

1. request 显式包含 `plan_id` 或 `plan_path` → 直接选中该主体。
2. 未显式指定，但当前只有一个可判定 active/current plan → 允许默认选中。
3. request 指向已归档 plan → 返回 `already_archived`，视为幂等成功或只读提示。
4. request 指向 legacy plan → `check` 返回 `migration_required`，`doctor` 可尝试 adopt。
5. request 主体不唯一 → 返回 `ambiguous_subject`，不做写入。
6. request 无法解析任何主体 → 返回 `plan_not_found`。

本包不扩展到：

- active plan review/revise/execute 的通用解析
- checkpoint 局部动作的全局主体解析

### 3. Runtime 新边界

runtime 继续负责：

- gate / preflight / host capability
- command routing
- output / handoff / replay
- process checkpoint state machine

runtime 不再负责：

- 把 archive 强行建模成 develop 活动流
- 为 archive 物化 execution confirm / resume active
- 依赖 `current_run/current_plan` 作为 archive 的唯一主体来源

---

## 实现方案

### A. 新的 archive core

建议新增一个 deterministic 核心模块，名字可以是：

- `runtime/archive_ops.py`
或
- `runtime/archive_lifecycle.py`

职责：

- `resolve_archive_subject(request_text, config, state_store?)`
- `check_archive_subject(subject, config)`
- `doctor_archive_subject(subject, config)`
- `apply_archive_subject(subject, config, state_store?)`

说明：

- 物理上可以先放在 `runtime/`，因为仓库尚未完成 Validator 独立分发。
- 语义上它属于 Validator 层能力，不依赖 runtime 活动态。

### B. finalize.py 重构

`runtime/finalize.py` 不再以“当前 active managed plan finalize”为中心，而是：

- 保留底层 move/history/index 更新逻辑
- 移除“只能从 current_plan 进入”的假设
- 让 archive core 明确传入一个 normalized archive subject

换言之，`finalize.py` 可以退化成 archive apply 的底层写入器，而不是路由语义承载体。

### C. router / engine cutover

`~go finalize` 的 cutover 方案：

1. Router 仍识别 `~go finalize`
2. 但 RouteDecision 的语义不再是 `finalize_active = active flow close-out`
3. Engine 收到该路由时，优先走 archive core：
   - 解析主体
   - check
   - 需要 migrate → 给出 archive/doctor 结果或继续 apply
   - 满足条件 → apply

删除项：

- archive 借用 `execution_confirm_pending`
- archive 借用 `resume_active`
- archive 借用 `review_or_execute_plan`
- archive 触发的 state_conflict 恢复链

### D. legacy adopt/migrate 策略

为了避免“legacy plan 内容已完成却无法归档”，doctor 至少支持：

- tasks.md / plan.md front matter 补齐
- `background.md` 缺失时生成最小模板
- `knowledge_sync` 默认值收敛
- `lifecycle_state` / `archive_ready` / `plan_status` 对齐

约束：

- 只做 deterministic、可回放的最小修复
- 不做语义润色或大规模内容重写
- doctor 输出必须可解释：哪些字段补了、哪些文件新建了、哪些仍需人工确认

---

## 场景覆盖

本包至少覆盖以下 8 个场景：

1. 显式 managed active plan → `check` ready → `apply`
2. 显式 managed inactive plan → `check` ready → `apply`
3. 显式 legacy plan → `check` migration_required → `doctor` → `apply`
4. 显式已归档 plan → `already_archived`
5. 未显式指定，唯一 active/current plan → `check/apply`
6. 未显式指定，多个候选主体 → `ambiguous_subject`
7. request 指向不存在主体 → `plan_not_found`
8. archive 目标目录已存在 → `archive_target_conflict`

本包不覆盖：

- checkpoint pending 下 continue/revise/cancel 的统一 action schema
- active plan review/revise/execute 的统一显式主体解析

---

## 测试策略

### Deterministic tests

- archive subject 解析测试
- managed/legacy/already-archived 分类测试
- doctor migrate 输出测试
- history index 更新测试
- 幂等与冲突测试

### Integration tests

- 跨 session 显式 archive existing plan，不经过 `execution_confirm_pending`
- legacy plan 在一轮 doctor 后可 archive
- archive 不污染 `current_run/current_plan`
- `~go finalize` 不再触发 resume_active 路径

### Regression tests

- 现有 consult_readonly / ActionProposal P0 行为不回退
- 普通 develop active flow 的 checkpoint 行为不回退
- history index / blueprint README 更新仍正确

---

## 删除顺序

1. 先补 archive subject / check contract 和 tests
2. 再补 doctor/apply contract 和 tests
3. 再接入 runtime cutover
4. 最后删除旧 finalize 绕行

删除目标：

- finalize 对 `recovered.current_plan` 的唯一依赖
- archive 借 execution confirm 的路径
- archive 相关旧文案和 handoff 语义

---

## 与后续子切片关系

本包完成后，才适合继续：

- `existing_plan_subject_binding`：统一 review/revise/execute 的显式主体解析
- `checkpoint_local_actions`：统一 continue / revise / cancel / inspect 的局部动作
- `host_prompt_governance`：基于新 contract 做提示层收口

本包不抢这些后续能力，只为它们提供一个正确的 lifecycle 边界。
