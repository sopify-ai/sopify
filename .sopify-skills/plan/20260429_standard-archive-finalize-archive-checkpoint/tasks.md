---
plan_id: 20260429_standard-archive-finalize-archive-checkpoint
feature_key: standard-archive-finalize-archive-checkpoint
level: standard
lifecycle_state: active
knowledge_sync:
  project: review
  background: review
  design: review
  tasks: review
archive_ready: false
---

# 任务清单: 为“显式主体与生命周期收敛”主题写第一子切片方案文档：新建 standard 方案包，只覆...

> **父方案包**：`20260424_lightweight_pluggable_architecture`
> **主题定位**：显式主体与生命周期收敛的第一子切片
> **优先级定位**：当前最高优先级；先于 `20260429_host_prompt_governance`

## 1. 协议与边界

- [ ] 1.1 明确 archive/finalize 的新语义：从“活动流收口”改为“面向显式主体的协议级归档操作”
- [ ] 1.2 定义 archive subject contract：managed / legacy / archived / ambiguous / missing
- [ ] 1.3 定义 `archive/check`、`archive/doctor`、`archive/apply` 的输入/输出与错误码
- [ ] 1.4 明确 runtime / validator / protocol 三层职责边界，确认 archive 不再依赖 `current_run/current_plan`

## 2. 显式主体解析

- [ ] 2.1 实现 archive 专属主体解析：显式 plan id/path 优先
- [ ] 2.2 支持唯一 active/current plan 的默认解析
- [ ] 2.3 支持已归档主体的幂等识别
- [ ] 2.4 支持 legacy plan 的 deterministic adopt/migrate 前置判断
- [ ] 2.5 为歧义主体和不存在主体给出 fail-close 结果

## 3. Archive Core

- [ ] 3.1 新建 deterministic archive core（check / doctor / apply）
- [ ] 3.2 将 `finalize.py` 收敛为 archive apply 底层写入器，而不是 active-flow 语义入口
- [ ] 3.3 将 history index / blueprint README 更新挂到 archive apply，而不是 activity close-out 语义
- [ ] 3.4 保证 archive core 可脱离 active runtime flow 独立运行

## 4. Runtime Cutover

- [ ] 4.1 调整 `~go finalize` 的 route/engine 语义，改为调用 archive core
- [ ] 4.2 删除 archive 对 `execution_confirm_pending` 的依赖
- [ ] 4.3 删除 archive 对 `resume_active` / `review_or_execute_plan` 的复用
- [ ] 4.4 删除 archive 触发的旧 `state_conflict` 绕行场景
- [ ] 4.5 更新 handoff / output / replay，使 archive 成为独立 lifecycle 操作

## 5. 测试与验证

- [ ] 5.1 补 deterministic tests：subject 解析、doctor migrate、apply/history update、错误码
- [ ] 5.2 补 integration tests：跨 session archive existing plan 不再经过 execution confirm
- [ ] 5.3 补 legacy plan archive 测试：doctor 后可直接 apply
- [ ] 5.4 补幂等 / 冲突测试：already_archived / archive_target_conflict
- [ ] 5.5 跑全量测试，确认 consult_readonly / checkpoint 主链路不回退

## 6. 文档与收口

- [ ] 6.1 更新总纲 tasks.md：将本包提升为 archive/lifecycle 第一子切片
- [ ] 6.2 在 blueprint/design.md 或 protocol 文档中补 archive contract 摘要
- [ ] 6.3 标记 `20260429_host_prompt_governance` 为后续收口包，不再作为当前排头兵
- [ ] 6.4 在总纲中明确后续子切片顺序：`existing plan` 显式主体绑定 → `checkpoint local actions` → `host_prompt_governance`
