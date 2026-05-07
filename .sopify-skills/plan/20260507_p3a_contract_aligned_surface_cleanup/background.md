# Background: P3a Contract-Aligned Surface Cleanup

## 前置里程碑

| 里程碑 | 状态 | 交付 |
|--------|------|------|
| P0 | ✅ | ActionProposal validator thin slice + consult_readonly |
| P1 | ✅ | Subject identity binding（plan_subject + workspace root + SHA-256 digest） |
| P1.5 | ✅ | 授权脊柱（reject surface + plan materialization auth + execution receipt + verifier normative） |
| P2 | ✅ | Admission contract closure（subject binding 泛化 + delta schema + canonical pairing） |

## 问题陈述

P2 完成后，runtime 处于"上层 contract 收敛、下层实现分裂"的状态：

1. **Validator 授权后仍经 Router 分类**：ActionProposal 已通过 validator 的全链条检查（subject + delta + pairing），但 AUTHORIZE 后仍 fallthrough 到 `Router.classify()` 做文本意图分类。Validator 的授权结论被浪费——路由决定仍取决于关键词匹配而非已授权的结构化意图。
2. **`review_or_execute_plan` 遗留面**：P2 已用 ActionProposal `execute_existing_plan` + ExecutionAuthorizationReceipt 替代了这个 required_host_action，但该字面量仍散布在 9 个 runtime 文件中（handoff / develop_callback / output / checkpoint_request / deterministic_guard / action_projection / plan_orchestrator / vnext_phase_boundary / engine）。
3. **Runtime 26K 行、目标 <20K**：P2 新增 ~200 行 validator 逻辑是必要的复杂度；需要通过删除替代品已到位的旧代码来补偿。

## 当前数字

- runtime/*.py 合计 26,055 LOC
- engine.py 2,624 | decision_tables.py 1,632 | router.py ~900 | plan_registry.py 1,012 | context_snapshot.py 973 | workspace_preflight.py 945
- `review_or_execute_plan` 引用：9 files
- 非 canonical route_name 变体：16 个（quick_fix, workflow, light_iterate, exec_plan, resume_active, plan_only, replay, cancel_active, state_conflict, clarification_pending/resume, decision_pending/resume, archive_lifecycle, proposal_rejected）

## 关键约束（来自 tasks.md）

- 不新增 checkpoint type / module / ActionProposal schema 字段
- 不重构 engine 架构
- 不重做 gate 架构
- 蓝图定义删减原则与边界；模块级删除清单由方案包定义

## Decisions

### D1: Slice ordering — sequential, not parallel

A（review_or_execute_plan 删除）→ B（execution routing 收敛）→ C（runtime 减重）。原因：A 清理遗留面让 B 可以安全缩窄 Router 职责；B 缩窄后才知道哪些分支变 dead code。D（knowledge_sync audit trail）独立于 ABC，可穿插。

### D2: Routing convergence scope — validator-authorized proposals only

只对携带 ActionProposal 且 validator 返回 DECISION_AUTHORIZE 的请求做 route derivation 收敛。无 ActionProposal 的裸文本请求继续走 Router.classify()。理由：Convention 模式宿主已发 ActionProposal，legacy 宿主或降级场景仍需文本分类兜底。

### D3: Route derivation from action_type — thin mapping + snapshot fact reading

收敛路由用 action_type + snapshot 机器事实，不引入新的 RouteDerivation 类型。映射表：

| action_type | derived route_name | 依据 |
|---|---|---|
| consult_readonly | consult | 确定性 |
| propose_plan | plan_only | 确定性 |
| execute_existing_plan | exec_plan | 确定性 |
| modify_files | quick_fix / light_iterate / workflow | 保留 complexity 分级 |
| checkpoint_response | clarification_resume / decision_resume | 读 snapshot.current_clarification / current_decision 判定 |
| cancel_flow | cancel_active | 确定性 |
| archive_plan | archive_lifecycle | 确定性 |

两个非确定性 action_type：
- `modify_files`：需 complexity estimation（提取 Router 的 `_estimate_complexity()`）
- `checkpoint_response`：需读 snapshot 中 active checkpoint 状态。如果 current_clarification.status == "pending" → clarification_resume；如果 current_decision.status in {"pending", "collecting"} → decision_resume。其余情况（含 terminal 状态 confirmed/cancelled/timed_out）→ REJECT（无 active checkpoint 却声称 checkpoint_response 是非法的）

### D4: Weight reduction strategy — delete, don't abstract

减重以"删除 dead path"为手段，不以"抽取通用层"为手段。目标是行数↓ + 分支数↓，不引入新抽象。

### D5: knowledge_sync audit trail — tail item, handoff artifact

降为尾项（不与 A/B/C 绑死）。archive handoff artifacts 增 `knowledge_sync_result` 可选字段（嵌入 `archive_lifecycle` 子对象）。先记账不判责。成功路径和 blocked 路径均保留审计链。

### D6: Persisted state with old review_or_execute_plan — fail-closed

线上无用户，不做兼容迁移。如果 state 文件中 `required_host_action` 或 `resume_after` 仍为 `review_or_execute_plan`，runtime 走 fail-closed：state_conflict / inspect-required。迫使重新进入干净流程。
