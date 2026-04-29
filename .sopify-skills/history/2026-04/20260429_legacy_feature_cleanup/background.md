# Background: Legacy Feature Cleanup

## 需求背景

`20260429_legacy_feature_cleanup` 是 `20260424_lightweight_pluggable_architecture` 总纲下的清理型收口包，目标不是新增能力，而是把已经被正式主链路替代的遗留能力面彻底移除，降低后续 prompt governance 与 runtime 路由维护成本。

本包完成前，仓库里仍残留两类历史包袱：

1. legacy consult override 路径仍在 router / engine / 测试中保留专属分支，而 `20260428_action_proposal_boundary` 已把只读咨询与副作用边界收敛为正式保护层。
2. `~compare` / `multi_model` 功能面已经不再是当前产品方向，但相关 runtime helper、decision helper、skill 文档、README、配置说明与测试入口仍分散存在。

本包的职责是把这些遗留面从“逻辑上已废弃”推进到“代码与文档层面均已移除”，为后续 host prompt governance 收敛创造干净基线。

## 本轮目标

- 删除只服务 legacy consult override 的专属 classifier、callsite 与测试断言。
- 删除 model compare 相关 runtime / decision / skill / 配置 / 文档 / 测试入口。
- 保留仍有价值的共享信号层，如 `analysis_only_no_write_brake`，避免清理过度影响当前主链路。
- 完成验证与文档收口，并在确认后允许进入 history 归档。

## 影响范围

- runtime 路由与执行主链路：`runtime/router.py`、`runtime/engine.py` 及关联 gate / handoff / output / replay 引用。
- 命令与能力面：`~compare` 命令入口、`multi_model` 配置说明、compare runtime helper / decision helper / builtin skill。
- 文档与测试面：README、Codex / Claude host prompt、design-rules、eval / SLO / baseline / 聚焦测试。

本包不引入新功能，不更改 ActionProposal 主契约，也不扩展 CrossReview 或 prompt governance 的新方案，只清理已确认下线的遗留表面。

## 风险评估

- 风险 1：误删仍被主链路依赖的共享 helper，导致咨询或执行路径行为回退。
  - 缓解：仅删除 legacy override 专属 callsite，保留 `analysis_only_no_write_brake` 与共享 consultation helper。
- 风险 2：compare 功能面删除后残留引用，造成运行时报错或文档失真。
  - 缓解：对 runtime、manifest、prompt、README、eval、测试做残留扫描，并运行 compileall、聚焦测试、全量测试与 `git diff --check`。
- 风险 3：并行文档编辑导致 blueprint / follow-up plan 被意外覆盖。
  - 缓解：本包只收口自身方案文件；`.sopify-skills/blueprint/design.md` 与 `20260429_host_prompt_governance` 的并行编辑保留用户侧控制，不在本包内覆盖。

## 非目标

- 不引入 CrossReview 替代 compare 的新用户口径。
- 不在本包中推进 prompt governance 重构实现。
- 不修改 ActionProposal validator 的能力边界，只消费其已稳定的保护层效果。
