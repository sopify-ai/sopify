---
plan_id: 20260429_standard-archive-finalize-archive-checkpoint
feature_key: standard-archive-finalize-archive-checkpoint
level: standard
lifecycle_state: archived
knowledge_sync:
  project: skip
  background: skip
  design: skip
  tasks: skip
archive_ready: true
plan_status: completed
---

# 任务清单: 为“显式主体与生命周期收敛”主题写第一子切片方案文档：新建 standard 方案包，只覆...

> **父方案包**：`20260424_lightweight_pluggable_architecture`
> **主题定位**：显式主体与生命周期收敛的第一子切片
> **优先级定位**：当前最高优先级；先于 `20260429_host_prompt_governance`

## 1. Archive Contract

- [x] 1.1 明确 archive/finalize 新语义：从“活动流收口”改为“`archive_plan` action 驱动的协议级归档操作”
- [x] 1.2 定义最小 archive subject：managed / legacy / archived / ambiguous / missing
- [x] 1.3 钉死 `ActionProposal.archive_plan` 最小 schema：`archive_subject.ref_kind/ref_value/source/allow_current_plan_fallback`
- [x] 1.4 钉死 `ValidationDecision -> Engine` contract：validator 必须产出 `route_override=archive_lifecycle` 与 `artifacts.archive_subject`
- [x] 1.5 定义两层边界：validator = `validate/authorize/emit artifacts`；core = `check/apply`
- [x] 1.6 定义轻量 guard：单一 `archive_plan` action、单一 `archive_lifecycle` route、最小 helper

## 2. Archive Core

- [x] 2.1 收缩 `runtime/archive_lifecycle.py`，只接收已验证的结构化 subject，不从 raw request 正则解析主体
- [x] 2.2 让 archive core 可脱离 active runtime flow 独立运行
- [x] 2.3 清理 archive/finalize helper 边界：删除 `runtime/finalize.py`，不新增 migration/repair 平台
- [x] 2.4 legacy/metadata 不完整时返回 `migration_required/archive_review`，本包不自动补写骨架

## 3. Runtime Cutover

- [x] 3.1 `archive_plan` 经 validator 授权后进入 `archive_lifecycle`，engine 禁止从 raw `request_text` 二次解析 subject
- [x] 3.2 `~go finalize` 仅作为 host/CLI thin alias，映射为同一个 `archive_plan` proposal；不作为 runtime routing 事实
- [x] 3.3 清理旧 `finalize_active` / active close-out 文案和测试断言
- [x] 3.4 handoff/output/replay 只暴露 `archive_lifecycle.archive_status`，不再暴露 `finalize_status`
- [x] 3.5 删除 runtime raw-text archive subject regex 与 pending 特例，避免重建局部语境
- [x] 3.6 保持 `archive_review` 为 handoff outcome，不新增第二个 action 或第二条 archive route
- [x] 3.7 遇到旧 finalize/runtime 冗余路径直接删除，不保留 wrapper、adapter 或 legacy 双轨 fallback

## 4. Minimal Verification

- [x] 4.1 deterministic/integration tests：structured subject、managed/already-archived、apply/history、冲突
- [x] 4.2 integration tests：跨 session archive existing plan 不经过 execution confirm
- [x] 4.3 legacy tests：返回 `migration_required/archive_review`，不自动 migration/repair
- [x] 4.4 guard tests：`archive_plan` 有结构化 subject 才能授权；无 proposal 的自然语言不进 archive
- [x] 4.5 smoke：consult_readonly、普通 develop checkpoint、history index / blueprint README 不回退
- [x] 4.6 contract tests：validator 输出的 `artifacts.archive_subject` 是 engine 唯一 archive subject 来源
- [x] 4.7 deletion tests/review：确认不存在 `finalize_active`、`finalize_status`、runtime raw-text archive regex、automatic migration/repair auto-apply 双轨残留
- [x] 4.8 boundary tests/review：validator 失败只产出 `blocking_reason/block_code`，`archive_status` 只由 archive core / handoff receipt 生成

## 5. 文档收口

- [x] 5.1 更新总纲 archive contract 摘要
- [x] 5.2 同步总纲 `Runtime state scope` 与 `Context Profile`：用 archive lifecycle / archive subject 替换旧 `finalize_active` / `active_plan` 口径
- [x] 5.3 压缩方案正文，只保留边界、删除面、验收口径
