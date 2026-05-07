# Design: P3a Contract-Aligned Surface Cleanup

## 总体策略

三阶段顺序推进 + 一个独立旁路：

```
A: review_or_execute_plan 最终删除（14 runtime targets）
    ↓
B: Execution routing 收敛（validator AUTHORIZE → deterministic route）
    ↓
C: Runtime 减重（dead path pruning, 目标 26K→<20K）

D: knowledge_sync audit trail（独立，可穿插在任意阶段间）
```

## Phase A: `review_or_execute_plan` 最终删除

### 替代 contract 已到位

P2 定义的替代链路：
- host 提交 `execute_existing_plan` ActionProposal（含 plan_subject）
- Validator 做 subject binding + pairing + evidence 检查
- AUTHORIZE → engine 走 `resume_active` route（`exec_plan` 的 `_should_emit_handoff` 为 debug-only，不产出 handoff）
- 执行前 gate: `evaluate_execution_gate()` → ExecutionAuthorizationReceipt

旧链路（`review_or_execute_plan` as `required_host_action`）完全被替代。

### Plan review 语义迁移方案

`review_or_execute_plan` 不是单纯一个 host action name，它承载了完整的 plan-review 机器面（guard、projection、boundary）。删除时必须迁移这些语义，不能只清字面量。

**迁移策略：plan review 状态改由现有机器事实组合表达，不再靠专用 host action name 区分。**

| 维度 | 旧（`review_or_execute_plan`） | 新 |
|------|-----|-----|
| handoff action | `required_host_action = "review_or_execute_plan"` | `required_host_action = "continue_host_develop"` |
| 状态判定 | `required_host_action == "review_or_execute_plan"` | `route_name == "plan_only"` + `current_run.stage == "plan_generated"` + `handoff.plan_path` 必填 |
| guard 判定 | `deterministic_guard.py` 独立 entry | 合入 `continue_host_develop` guard，当 `current_run.stage == "plan_generated"` 时走 plan review 子逻辑 |
| projection | `action_projection.py` 独立 builder（含 plan_path / execution_summary） | 合入 `continue_host_develop` projection，当检测到 plan_generated 状态时追加 plan review 字段 |
| boundary | `vnext_phase_boundary.py` 独立 entry | 从 supported set 移除（plan review 不再需要独立 boundary entry） |
| resume | `resume_after = "review_or_execute_plan"` → 回退 plan review | `resume_after` 收窄为仅 `"continue_host_develop"`；需要退回 plan review 时改用 `resume_route = "plan_only"`，由恢复逻辑按 `resume_route` 判定回到 plan_only。**注意：只有原先语义等价于 `resume_after="review_or_execute_plan"` 的 callback（即 `_submit_quality_checkpoint` 中的 quality replan 路径，develop_callback.py:484）才设置 `resume_route="plan_only"`；通用 checkpoint 创建路径（develop_callback.py:372）默认仍为 `resume_route="resume_active"`，不改。** |
| orchestrator | `_STABLE_HOST_ACTIONS = {"review_or_execute_plan"}` | 改为 `required_host_action == "continue_host_develop"` **且** `current_run.stage == "plan_generated"`（两条件同时满足才视为 stable plan review；不得仅用 plan_artifact 存在性判定，否则会误停非 plan_only 的 planning route） |
| resolution_planner | `supports_resolution_planner("review_or_execute_plan")` → 从 signal_priority_table 按 action key 加载行 | **直接删除，不迁移。** 旧 plan review 的 signal rows 本身是 no-op（`supported_resolved_actions=[]`），删除后 plan_only 场景直接不产出 resolution_planner artifact。 |
| sidecar_classifier_boundary | `supports_sidecar_classifier_boundary("review_or_execute_plan")` → 同上 | **直接删除，不迁移。** 旧 plan review 的 sidecar boundary 本身 `v1_enabled=false`，行为为 no-op。删除后 plan_only 场景直接不产出 sidecar artifact。 |

**逐文件迁移明细**：

| 文件 | 引用上下文 | 处置 |
|------|-----------|------|
| `handoff.py` | `plan_only → "review_or_execute_plan"` | 改为 `return "continue_host_develop"` |
| `develop_callback.py` | `resume_after = "review_or_execute_plan"` (L484) | **仅 `_submit_quality_checkpoint` 中的 quality replan 路径**：改为 `resume_after = "continue_host_develop"` + `resume_route = "plan_only"`。通用 checkpoint 创建路径（L372）`resume_route="resume_active"` 保持不变。 |
| `output.py` | handoff message 渲染时匹配该 action (L509) | 删除 `review_or_execute_plan` 独立 case；在 `continue_host_develop` 分支内新增 `route_name == "plan_only"` 检查 → 返回 `labels["next_plan"]`（否则会 fallthrough 到 `next_workflow`）。 |
| `checkpoint_request.py` | `DEVELOP_RESUME_AFTER_ACTIONS` 包含该值 | 从 allowlist 移除（只保留 `"continue_host_develop"`） |
| `deterministic_guard.py` | 独立 guard entry + normalization + plan review 子逻辑 | 移除独立 entry；plan review guard 逻辑合入 `continue_host_develop` 分支（以 `current_run.stage == "plan_generated"` 判定） |
| `action_projection.py` | 独立 `_build_plan_review_fields` builder | 移除独立 entry；plan review 字段合入 `continue_host_develop` projection（以 plan_generated 状态条件触发） |
| `plan_orchestrator.py` | `_STABLE_HOST_ACTIONS = {"review_or_execute_plan"}` | 改为 `required_host_action == "continue_host_develop"` **且** `current_run.stage == "plan_generated"` 双条件判定（不得仅用 plan_artifact 存在） |
| `vnext_phase_boundary.py` | supported action set 包含该值 | 从 set 移除 |
| `engine.py:1740/1803` | `resume_after == "review_or_execute_plan"` → 回退 plan review | 改为检查 `resume_route == "plan_only"` 判定是否回退到 plan review |
| `engine.py:2401` | `next_required_action="review_or_execute_plan"` | 改为 `"continue_host_develop"` |
| `contracts/failure_recovery_table.yaml` | recovery entry 引用该 action | 删除 entry（fail-closed） |
| `contracts/decision_tables.yaml` | decision table row 引用该 action | 删除 row |
| `contracts/failure_recovery_table.schema.json` | `host_actions` enum 包含该值 | 从 enum 移除 |
| `contracts/decision_tables.schema.json` | `host_actions` enum + proof 引用 | 从 enum 移除 + 删除 proof 引用 |
| `contracts/signal_priority_table.schema.json` | `host_actions` enum 包含该值 | 从 enum 移除 |

**Persisted state 处理**：不做兼容迁移。如果 state 文件中 `required_host_action` 或 `resume_after` 仍为 `review_or_execute_plan`，runtime 走 fail-closed（state_conflict / inspect-required）。

### 验证标准

- grep `review_or_execute_plan` 在 `runtime/` = 0 hits
- grep `review_or_execute_plan` 在活跃 `.sopify-skills/blueprint/` 仅限 informative / 已收口注释（sunset table、protocol informative mapping）
- grep `review_or_execute_plan` 在 `tests/` 仅限 fail-closed / compatibility coverage 保留（allowlist 管理，见下方）
- 全量测试通过
- 无新增 required_host_action 值
- plan_only route → `continue_host_develop` handoff + plan_generated stage + plan artifacts 完整
- deterministic guard 在 plan_generated 状态下仍正确允许 continue/inspect/revise/cancel
- action projection 在 plan_generated 状态下仍暴露 plan_path / execution_summary
- develop resume 通过 `resume_route = "plan_only"` 正确回退到 plan review
- state 中残留 `review_or_execute_plan` → fail-closed 行为有测试覆盖
- resolution_planner / sidecar_classifier_boundary 的 plan-review-specific artifacts 已删除（旧 rows 为 no-op）；plan_only 场景直接不产出这些 artifact
- output.py 的 `_handoff_next_hint` 在 plan_only + continue_host_develop 场景下返回 `next_plan`（不是 `next_workflow`）
- plan_orchestrator stable action 判定使用 `required_host_action == "continue_host_develop"` 且 `current_run.stage == "plan_generated"` 双条件（非 plan_only route 不会误停）

**tests/ 字面量 allowlist**（仅以下场景允许保留 `review_or_execute_plan`）：

| 允许场景 | 典型位置 | 理由 |
|---------|---------|------|
| fail-closed 测试输入 fixture | `tests/fixtures/fail_close_case_matrix.yaml` | 验证 legacy state → state_conflict 行为 |
| fail-closed contract 定义 | `tests/fixtures/context_fail_close_contract.yaml` | 定义 fail-close contract |
| fail-closed 交叉引用 fixture | `tests/fixtures/sample_invariant_gate_matrix.yaml` | A-5/A-8 的 `contract_ref` 必须与 fail_close_case_matrix 保持一致 |
| compatibility coverage 断言 | `tests/test_runtime_failure_recovery.py`, `tests/pytest_entries/fail_close_contract_entry.py` | 验证 recovery table 迁移后 fail-closed 正确触发 |

allowlist 之外的 tests/ 引用必须在 A4 中删除或改写为新 contract 语义。

## Phase B: Execution Routing 收敛

### 当前架构

```
ActionProposal → Validator.validate()
    │
    ├─ REJECT → proposal_rejected (synthetic route)
    ├─ route_override → synthetic RouteDecision (e.g. archive_lifecycle)
    └─ AUTHORIZE (no override) → Router.classify(user_input) ← 这是问题点
```

### 目标架构

```
ActionProposal → Validator.validate()
    │
    ├─ REJECT → proposal_rejected
    ├─ route_override → synthetic RouteDecision
    └─ AUTHORIZE (no override) → derive_route_from_proposal(action_proposal) ← 新增
                                       │
                                       └─ modify_files 仍需 complexity → Router._estimate_complexity()
```

### 实现要点

1. **新增 `_derive_route_from_authorized_proposal()`** 在 `engine.py` 中（~40 行 mapping + snapshot fact reading）
2. **`modify_files` 特殊处理**：该 action_type 的 route 取决于请求复杂度（quick_fix / light_iterate / workflow）。提取 Router 的 `_estimate_complexity()` 为独立函数，不再需要完整 classify()。
3. **`checkpoint_response` 特殊处理**：读 snapshot 中 active decision checkpoint 分流：
   - `snapshot.current_clarification.status == "pending"` → `clarification_resume`
   - `snapshot.current_decision.status in {"pending", "collecting"}` → `decision_resume`
   - 其余情况（含 confirmed/cancelled/timed_out/consumed/stale 以及两者都不满足）→ REJECT（无 active checkpoint 却声称 checkpoint_response）
4. **`propose_plan` 元数据处理**：derive 返回 route_name="plan_only" 时，不从 ActionProposal 取新字段（不扩展 schema）。plan_level 通过 `_estimate_complexity(user_input)` 推导（可产出 full/standard/light）；derive 阶段 plan_package_policy 设为 "immediate"（触发 plan materialization）。注意：plan 物化完成后引擎会经 `_plan_review_route()` 归一为 plan_package_policy="none"（等待 review），这是现有行为，不应改变。验收应断言最终 runtime result 的可观察行为（route_name + plan_artifact.level + handoff），不要只盯 derive 中间值。
5. **Router.classify() 退化为 fallback**：只在无 ActionProposal 时调用。注释标注 "legacy text-classification path, will be removed when all hosts emit ActionProposal"。
6. **不删 Router**：裸文本请求仍需它。但其职责明确收窄为"无结构化意图时的兜底分类"。

### Gate chain 变更

engine.py ~L712-715 从：
```python
if proposal_override_route is not None:
    classified_route = proposal_override_route
else:
    classified_route = router.classify(user_input, skills=skills, snapshot=snapshot)
```

变为：
```python
if proposal_override_route is not None:
    classified_route = proposal_override_route
elif action_proposal is not None and validation_decision.decision == DECISION_AUTHORIZE:
    classified_route = _derive_route_from_authorized_proposal(
        action_proposal, user_input, skills=skills, config=config, snapshot=snapshot
    )
else:
    classified_route = router.classify(user_input, skills=skills, snapshot=snapshot)
```

### 验证标准

- Authorized ActionProposal 不再依赖 Router.classify() 做主路由判定（modify_files 仅允许调用提取后的 `_estimate_complexity()` helper，不经完整 classify 链路）
- 裸文本请求（无 ActionProposal）行为不变
- modify_files 的 complexity 分级结果与旧 Router 一致（回归测试）
- propose_plan 最终 runtime result 可观察行为与旧路径一致：断言 plan_artifact.level（full/standard/light）+ 最终 route handoff 状态，不要只验证 derive 中间值
- checkpoint_response 正确分流到 clarification_resume / decision_resume（snapshot 驱动，仅 active checkpoint 状态可 resume）
- checkpoint_response 在无 active checkpoint 时 REJECT（含 terminal 状态 confirmed/cancelled/timed_out）

## Phase C: Runtime 减重

### 原则

- **删除 dead path**（A/B 之后不可达的分支）
- **剪恢复厚度**（过度防御性的 fallback/retry 链路，线上无用户可激进删）
- **裁兼容防御**（为已删除宿主/旧 wire format 的 compat shim）
- **薄化上下文层**（context_snapshot 中只服务于旧 route 的字段/逻辑）
- **裁窄观察面**（replay / capture 等观察面如果 dead 则删）

### 候选模块

| 模块 | 当前行数 | 潜在减重来源 |
|------|---------|-------------|
| `engine.py` | 2,624 | A/B 后的 dead branches + 旧 resume 逻辑 |
| `decision_tables.py` | 1,632 | 基于旧 route/action 的 table entries |
| `router.py` | ~900 | B 后 classify() 内的 validated-proposal 路径可删 |
| `deterministic_guard.py` | ~600 | `review_or_execute_plan` entry + 可能的其他旧 guard |
| `context_snapshot.py` | 973 | 旧 state promotion / conflict 逻辑如果只服务已删 route |
| `action_projection.py` | ~400 | plan-review projection 如果整体可删 |

### 目标

- 26K → <20K（减 ≥6K）
- 每次删除伴随测试通过确认
- 不引入新模块/新抽象

## Phase D: knowledge_sync audit trail（尾项，不与 A/B/C 绑死）

### 前置条件

- 几乎零成本挂接（不涉及 finalize 路径重构）
- 如果需要重构 finalize 路径，defer 到 P3b

### 设计

archive finalize 时，`knowledge_sync` 评估结果以 `knowledge_sync_result` 字段写入 archive handoff artifacts（`archive_lifecycle` 子对象）。无论归档成功还是因 knowledge_sync 阻断，audit trail 均保留。

```yaml
knowledge_sync_result:
  outcome: "passed"          # "passed" | "blocked"
  sync_level:                # plan 前端 matter 中的 knowledge_sync 配置快照
    project: "review"
    background: "review"
    design: "review"
    tasks: "review"
  changed_files:             # 在 plan 创建后有更新的蓝图文件（可选，非空时出现）
    - ".sopify-skills/blueprint/design.md"
  review_pending:            # review 模式但未更新的文件（可选，非空时出现）
    - ".sopify-skills/blueprint/tasks.md"
  required_missing:          # required 模式但未更新的文件（可选，blocked 时出现）
    - ".sopify-skills/blueprint/background.md"
```

### 实现位置

- `runtime/archive_lifecycle.py` — `_knowledge_sync_result()` 组装、`ArchiveCheckResult` / `ArchiveApplyResult` 透传
- `runtime/engine.py` — 成功路径和 blocked 路径均传入 `archive_status_payload()`
- handoff artifacts `archive_lifecycle.knowledge_sync_result` 自动透传到宿主

### 验证

- 有 sync 时 receipt 含该字段
- 无 sync 时 receipt 无该字段（不插空结构）
