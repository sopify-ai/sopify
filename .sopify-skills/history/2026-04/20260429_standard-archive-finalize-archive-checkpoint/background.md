# 变更提案: 显式主体与生命周期收敛（第一子切片）

## 需求背景

Sopify 的总纲已经确认 `Protocol-first / Runtime-optional` 方向：Protocol 是不可替代内核，Validator 承担 `validate/authorize/emit artifacts` 的 pre-write 授权边界，deterministic core 承担 `check/apply`，Runtime 只保留过程控制增强。当前现实却仍有一条旧边界没有收敛：`archive/finalize` 仍被实现为 runtime 活动态的一部分，而不是协议资产生命周期能力。

这一点在 `20260429_legacy_feature_cleanup` 的跨 session 归档中已经暴露出结构性问题：

1. `~go finalize` 只认当前活动 `current_plan`，不认显式指定的 existing plan。
2. 旧 plan 即使内容已完成，只要不是 metadata-managed，就无法直接归档。
3. 现状为了归档一个既有 plan，宿主必须先把它重新绑定成 active plan，再穿过 `execution_confirm_pending → resume_active → finalize_active` 的旧运行时链路。
4. 这条旧链路是本包要删除的问题来源，不是目标行为；它与 archive 的真实目标不一致，并且在跨 session 场景下出现了 `execution_confirm_pending` / handoff 契约错位。

在“没有线上用户，可以一刀切删改”的前提下，继续把 archive 语义挂在重 runtime 上没有收益，只会让后续 prompt governance、protocol 文档和局部语境扩展围绕错误边界继续演化。

## 本轮目标

- 将 `archive/finalize` 从“活动 develop 流的收口动作”改为“面向显式主体的协议级归档操作”。
- 将 archive 的入口收敛为结构化 `ActionProposal(action_type="archive_plan")` 协议：host 负责把用户自然语言映射成 action，runtime/validator 只校验结构化事实。
- 为 archive 引入最小的结构化主体字段：支持 explicit plan id/path、唯一 active/current plan fallback；runtime 不再从 raw request 正则猜主体。
- 将 archive 所需的 deterministic 能力收敛成薄 core，不再依赖 `current_run/current_plan` 才能工作，也不在 runtime 内扩出迁移平台。
- 删除 archive 复用 `execution_confirm_pending / resume_active / review_or_execute_plan / state_conflict` 的旧绕行。
- 保持 runtime 仍可作为入口/适配层存在，但不再独占 archive 生命周期语义。

## 影响范围

- archive action boundary 与 handler：`runtime/action_intent.py`、`runtime/engine.py`、必要时 `runtime/archive_lifecycle.py`
- plan 解析与主体绑定：由 `ActionProposal.archive_subject` 承载，runtime 仅做存在性/唯一性校验；必要时读取 `runtime/plan_registry.py`
- 交接与输出：`runtime/handoff.py`、`runtime/output.py`
- deterministic core / helper：新增或重构 archive `check/apply` 能力；validator 只做 `validate/authorize/emit artifacts`；migration/repair 不在本包执行路径内，只返回 `migration_required/archive_review`
- protocol 资产：plan/history lifecycle 语义、错误模型、场景覆盖说明

本包只做“第一子切片”：
- 覆盖 archive/finalize 收敛
- 覆盖 archive 所需的结构化主体校验
- 覆盖旧 archive 链路删除

本包不做：
- 不统一全部 checkpoint 本地动作
- 不做 engine 大拆分
- 不做 prompt 单源生成
- 不做完整 validator 平台化；只扩 `archive_plan` 的最小协议字段与校验

## 风险评估

- 风险 1：一刀切删除旧 finalize 链路后，现有 `~go finalize` 的隐式行为会变化。
  - 缓解：把 `~go finalize` 降为 host/CLI alias，映射成同一个 `archive_plan` proposal；runtime 内部不保留第二条命令归档语义。
- 风险 2：archive 下沉时把 runtime 应保留的过程控制一起删掉，导致职责反向失衡。
  - 缓解：明确边界是“去 runtime 状态机依赖”，不是“去 runtime 文件目录”；gate / checkpoint / resume 仍保留在 runtime。
- 风险 3：把“显式主体与生命周期收敛”做成过大的通用框架，范围失控。
  - 缓解：本包只服务 `archive_plan` action；existing plan review/revise/execute 和 checkpoint local actions 后置到后续子切片。
