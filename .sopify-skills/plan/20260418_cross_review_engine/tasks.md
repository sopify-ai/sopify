---
plan_id: 20260418_cross_review_engine
feature_key: cross_review_engine
level: standard
lifecycle_state: draft
knowledge_sync:
  project: review
  background: review
  design: review
  tasks: review
archive_ready: false
---

# 任务清单: Cross-Review 独立内核方案

## 当前阶段目标

本方案包当前处于“方案持续打磨”阶段，目标不是立刻实现，而是逐步把以下关键决策收敛到可执行状态：

1. 名称与定位是否稳定
2. 独立内核与 Sopify adapter 的边界是否清晰
3. `review` 是否进入 plan 的正式资产层
4. artifact / finding / verdict / policy 的 schema 是否足够稳定
5. 首期集成顺序是否合理

> 当前原则：
> 本文件中的 `Q1-Q7` 在用户明确确认前，全部视为**待拍板事项**。
> 可以继续细化背景、影响面、推荐方向，但不默认视为已决策。

## Phase 0 — 现状与定位收敛

- [ ] 0.1 明确命名策略
  - 在 `sopify-cross-review`、`cross-review` 与 `verification-loop` 之间确认：
    - 产品名称
    - 用户面能力名
    - 内核模块名称
    - 配置键名称
    - 未来命令名称
  - 目标：避免 compare / review / verification / quality 命名漂移

- [ ] 0.1a 整理命名备选清单
  - 已产出 `naming-options.md`
  - 当前目标：
    - 把方法型 / 对象型 / 品牌型命名拆开
    - 不提前替用户定名
  - 目标：让后续命名评审有统一输入文档

- [ ] 0.2 确认产品边界
  - 明确它是否为：
    - 独立产品内核
    - Sopify 官方内建能力
    - 外部 skill / runtime extension
    - 上述三者的组合
  - 目标：确定仓库落点与生命周期管理策略

- [ ] 0.2a 确认仓库形态是否以“未来独立仓库”为目标
  - 当前倾向：
    - `sopify-cross-review` 按独立产品设计
    - 目标形态可演进为独立仓库
    - 但不提前钉死当前就必须分仓
  - 目标：把“独立边界”和“立即分仓”两个问题拆开

- [ ] 0.2b 校验产品尺度是否保持“小而集中”
  - 校验原则：
    - 不把 `sopify-cross-review` 做成新的 workflow host
    - 不把 plan lifecycle / gate / history 主流程收进 core
    - 保持 `Sopify > sopify-cross-review > sopify-code-review`
  - 目标：避免产品边界后续膨胀

- [ ] 0.3 统一与现有能力的关系
  - 明确 `cross-review` 与以下能力的分工：
    - `multi_model`
    - `~compare`
    - `develop_quality`
    - `decision facade`
    - `execution gate`
  - 目标：避免职责重叠

- [ ] 0.4 确认 `cross-review` 与 `code-review` 的层级关系
  - 备选：
    - `sopify-cross-review > sopify-code-review`
    - `sopify-code-review > sopify-cross-review`
    - 二者并列
  - 当前倾向：
    - `sopify-cross-review` 是总产品 / 总内核
    - `sopify-code-review` 是代码工件 vertical
  - 目标：避免后续产品线和模块线反向依赖

- [ ] 0.5 确认 review 是否作为 plan 一等资产
  - 明确是否新增：
    - `review.md`
    - `reviews/design-review.md`
    - `reviews/tasks/Tn-review.md`
    - `reviews/final-audit.md`
  - 目标：让评审报告进入 tracked plan/history，而不只停留在 state

## Phase 1 — 领域模型与 contract 收敛

- [ ] 1.1 确认 artifact taxonomy
  - 候选：
    - `plan_package`
    - `task_result`
    - `code_diff`
    - `design_summary`
    - `consult_answer`
    - `command_result`
  - 目标：锁定 MVP artifact 集

- [ ] 1.2 确认 review pack schema
  - 明确必填字段：
    - task.request
    - acceptance_criteria
    - constraints
    - artifact payload
    - evidence
    - policy_context
  - 目标：后续实现时不再反复改输入 contract

- [ ] 1.3 确认 finding schema
  - 明确：
    - severity
    - category
    - evidence 形式
    - confidence 是否保留
    - reviewer source 标识
  - 目标：与 future replay / handoff / UI 兼容

- [ ] 1.4 确认 verdict schema
  - 明确：
    - `pass / concerns / block / inconclusive`
    - recommended_action
    - 与 develop_quality 的映射方式
  - 目标：形成可执行的最终裁决 contract

- [ ] 1.5 确认 review 资产 schema
  - 明确：
    - `review.md` 总览字段
    - design review 报告结构
    - task review 报告结构
    - final audit 报告结构
  - 目标：把 review 从运行时信号提升为可归档资产

## Phase 2 — 执行模型与 policy 收敛

- [ ] 2.1 确认 reviewer 策略
  - 首期是否支持：
    - 同模型 fresh session
    - 跨模型 reviewer
    - deterministic checker
  - 目标：避免 MVP 一开始做得过宽

- [ ] 2.2 确认 adjudicator 策略
  - 是否坚持确定性裁决
  - 是否允许后续引入 LLM adjudicator
  - 目标：先保稳定，再考虑复杂智能裁决

- [ ] 2.3 确认 policy model
  - 明确 advisory / required / block 的层次
  - 明确按风险标签、改动规模、测试缺失等条件自动升级 review 的规则
  - 目标：让 cross-review 成为工程 policy，而不是偶发动作

- [ ] 2.4 确认 task review 触发策略
  - 选项：
    - 每个 task 完成后默认触发
    - 仅高风险 task 触发
    - 用户手动触发 + policy 升级
  - 目标：在成本与稳定性之间找到可持续策略

## Phase 3 — Sopify 集成路径收敛

- [ ] 3.1 明确 design 集成切入点
  - plan package 完成后是否立即生成设计评审报告
  - 是否在 `confirm_execute` 前阻断
  - 是否要求 `review.md` 在 design 阶段就初始化
  - 目标：把设计评审正式纳入 plan 生命周期

- [ ] 3.2 明确 develop 集成切入点
  - task 完成后 review，还是 develop 整体结束后 review
  - review 结果写入：
    - `handoff.artifacts.cross_review_report`
    - `develop_quality.review_result`
    - `reviews/tasks/Tn-review.md`
    - `review.md`
  - 目标：先接一条最稳定主链路

- [ ] 3.3 明确 finalize 集成切入点
  - 是否在归档前强制执行 final audit
  - 是否要求 review 资产闭环后才能进 history
  - 目标：让 history 具备审计意义

- [ ] 3.4 暂缓 analyze 集成并定义前置条件
  - 只有在 design / develop 路径稳定后再评估 analyze advisory review
  - 目标：控制噪音

## Phase 4 — 实施前准备

- [ ] 4.1 评估是否需要 `full` 级方案包
  - 若 schema 与集成点稳定，再决定是否补：
    - `adr/`
    - `diagrams/`
  - 目标：在实现前把关键决策沉淀到更强文档结构

- [ ] 4.2 拆分第一版实现切片
  - 候选切片：
    - 切片 A: config + schema
    - 切片 B: core engine + CLI
    - 切片 C: repo/package split preparation
    - 切片 D: Sopify runtime adapter
    - 切片 E: develop integration
  - 目标：确认后再进入开发实施

- [ ] 4.3 确认测试策略
  - 至少覆盖：
    - config validation
    - review pack normalization
    - finding / verdict contract
    - policy decision
    - develop integration handoff
  - 目标：避免产品一开始就停留在 prompt 级实验

## 当前待讨论问题

- [ ] Q1: 产品名是否正式采用 `sopify-cross-review`
- [ ] Q2: `cross-review` 是否固定为能力名，`verification-loop` 是否固定为内核语义名
- [ ] Q3: `cross_review` 是否作为新的顶层配置键
- [ ] Q4: `sopify-cross-review` 与 `sopify-code-review` 是否采用“总产品 / 垂直产品”关系
- [ ] Q5: plan 是否新增 `review.md + reviews/` 作为正式资产层
- [ ] Q6: 第一版是否做 `plan_package + task_result/code_diff`
- [ ] Q7: 第一版是否先接 `design + develop`
- [ ] Q8: `sopify-cross-review` 是否最终采用独立仓库形态，以及何时分仓
- [ ] Q9: 主品牌是否保留 `sopify-` 前缀，还是改为更中立/更语义化的名字

## 决策约束

在 `Q1-Q8` 未明确确认前：

- 可以继续补充背景、设计、利弊比较与 contract 草案
- 不把推荐方向写成“已确定规则”
- 不进入实现阶段
- 不把命名、配置键、资产层结构视为冻结契约

对 `Q8` 的特别约束：

- 可以继续描述独立仓库目标形态与 core / adapter 边界
- 但不把“立即分仓”视为当前阶段前置条件
