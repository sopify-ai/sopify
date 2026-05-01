# 蓝图路线图与待办

本文定位: 只记录未完成长期项与明确延后项。已完成项不保留。不替代当前 plan 的执行任务清单。

## 执行优先级（已确认）

以下顺序是硬约束。前一项未稳定前，不进入后一项实现。

| 优先级 | 任务 | 前置条件 | 说明 |
|--------|------|---------|------|
| P0 | Blueprint rebaseline | 无 | 本轮。重写 blueprint，实体化 ADR，定义削减目标 |
| P1 | existing_plan_subject_binding | P0 | 统一"操作的是谁"的主体解析 |
| P2 | checkpoint_local_actions | P1 | 收敛 continue/revise/cancel/inspect 局部动作 |
| P3 | runtime_surface_cleanup | P2 | 基于稳定 contract 删旧 route/alias/projection/tests |
| P4 | host_prompt_governance | P3 | prompt 治理只消费稳定 contract，不定义 machine truth |

### P0: Blueprint Rebaseline（已基本完成）

- ✅ 重写 blueprint/{background,design,tasks}.md
- ✅ 实体化 ADR-013/016/017 到 blueprint/architecture-decision-records/
- ✅ 定义削减预算表和目标词汇表
- ✅ 降级并删除 20260424_lightweight_pluggable_architecture（证据留 git history）
- ✅ 迁移 ADR 到 blueprint/architecture-decision-records/
- 遗留：竞品边界表已更新；最小协议文档待提取（见 P1 前置）

### P1: existing_plan_subject_binding

- 统一 review/revise/execute/plan 对 existing plan 的主体绑定口径
- 定义主体取证优先级：explicit reference → self-reference → new-plan intent → stable handoff evidence → current-plan anchor
- 不定义局部动作 contract，不治理 prompt

### P2: checkpoint_local_actions

- 收敛 continue/revise/cancel/inspect 的局部动作 contract
- 动作层只消费已绑定主体
- 不回头吸收主体歧义问题

### P3: runtime_surface_cleanup

- 清理旧 route/alias/reason phrasing/phase label 特判
- 清理 handoff/output/replay 旧兼容投影
- 清理 failure recovery/deterministic guard/decision tables 旧分支
- 清理 tests 中只验证旧概念的断言
- 不新增 checkpoint type、不扩 ActionProposal schema、不重做 gate 架构

### P4: host_prompt_governance

- prompt 不定义机器契约、不维护路由表
- 每条规则通过删除测试
- 渐进式披露：Layer 0 Protocol ≤120 行 → Layer 1 Gate → Layer 2 Phase → Layer 3 Reference（不进 prompt）

## 未完成长期项

- [ ] 补宿主级 first-hop ingress proof / diagnostics
- [ ] `~compare` shortlist facade 收敛进默认主链路
- [ ] `workflow-learning` 独立 helper 与更稳定 replay retrieval
- [ ] blueprint 索引摘要更细粒度自动刷新
- [ ] history feature_key 聚合视图
- [ ] Protocol Step 1：提取最小协议文档与行为契约 case
- [ ] CrossReview Phase 4a：advisory skill 接入 develop 后审查
- [ ] Plan intake checklist：每个新 plan 必须声明 blueprint alignment、budget impact（是否新增/删除 action/route/state/checkpoint）、ADR impact

## 明确延后项

- [-] runtime 全接管 develop orchestrator
- [-] 非 CLI 宿主图形化表单
- [-] history 正文纳入默认长期上下文
- [-] daily index
- [-] ~replay 更多入口
- [-] runtime 独立 preferences_artifact
- [-] 偏好自动归纳/提炼
