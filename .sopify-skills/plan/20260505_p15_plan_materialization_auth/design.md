# 技术设计: P1.5 Plan Materialization Authorization Boundary

## 核心策略

plan 包物化不再由 route 隐式触发，改为受 ActionProposal → Validator 授权约束。

## 设计决策

**D1: plan_package_policy 默认值从 immediate 改为 authorized_only**

当前 `_plan_package_policy_for_route` 对 plan_only/workflow/light_iterate 返回 `"immediate"`。
改为返回 `"authorized_only"`。含义：只有经过 Validator 授权（host 提交的 ActionProposal 包含 `propose_plan` + `write_plan_package` + 足够 evidence）才允许物化。

不恢复 `"confirm"` 策略。`confirm` 在 Wave 3a 已被退化为 `immediate`（engine.py:1909），
复用它会引入语义歧义。`authorized_only` 是新语义，明确表达"需授权"。

**D1-a: `runtime/_models/core.py` 模型闭环**

`PLAN_PACKAGE_POLICIES = ("none", "confirm", "immediate")` 是 RouteDecision 归一化的允许值白名单。
`__post_init__` 中 `_normalize_keyword(derived_policy, allowed=PLAN_PACKAGE_POLICIES, default="none")` 会把不在白名单中的值降级为 `"none"`。
因此 `authorized_only` 必须先加入白名单，否则从 router 到 engine 的整条链路都无法传递新策略。

改动：`PLAN_PACKAGE_POLICIES` 改为 `("none", "immediate", "authorized_only")`。`confirm` 直接删除——当前线上无用户，无需兼容旧输入。任何传入 `confirm` 的外部调用会被归一化为 `"none"`（fail-closed）。

**D2: engine `_normalized_plan_package_policy` 去掉兜底 immediate**

当前兜底逻辑（engine.py:1913-1916）会把缺省/空 policy 再硬编码回 `"immediate"`。
改为：缺省/空 → `"none"`。不再有任何路径隐式物化 plan。

**D3: `authorized_only` 的语义定义**

当 `plan_package_policy == "authorized_only"` 时，engine 的 `_advance_planning_route` 行为：
- 如果当前 request 经过了 ActionProposal → Validator，且 Validator 返回 `DECISION_AUTHORIZE`，且 proposal 包含 `side_effect="write_plan_package"` → 允许物化
- 否则 → 降级到 consult surface。不触发 `create_plan_scaffold` 等写盘操作，不创建 plan 目录。原始 guard artifacts（如 `direct_edit_guard_kind`）保留到降级后的 RouteDecision，确保 gate contract 仍能暴露 guard 信息

降级到 consult 是当前 P1.5-C 的最小安全实现：handoff 正确返回 `continue_host_consult`，host 不会收到不存在 plan 的 `review_or_execute_plan` 指令。

**D4: 传递 Validator 授权结果到 planning 流程**

当前 Validator 结果只影响 `proposal_override_route`（engine.py:634-672），不传递到 `_advance_planning_route`。
需要把 Validator 的 authorization 状态（authorized / not_authorized / no_proposal）
作为参数传入 `_advance_planning_route`，让它判断是否允许物化。

不新增 action type。已有 `propose_plan` + `write_plan_package` 足够。

**D5: router L1 止血 — 去掉单字 ACTION_KEYWORDS**

`_ACTION_KEYWORDS` 中的单字"修"和"补"做 substring match 误伤率过高。
"修" 会命中"必须修"、"怎么修复"、"先别修改"等分析语句。
"补" 会命中"补充"、"补一句"等非变更表达。

最小改法：直接删除单字"修"和"补"，不新增替代 pattern。"修复"已在列表中覆盖合法用法。
不新增 pattern，不堆语义特判。

**D6: `~go plan` 显式命令保持 immediate — 本轮显式兼容例外**

`~go plan` 是用户显式发出的 plan 命令（router.py:435-444），属于本轮保留的 host-side exception / compatibility path。
保留原因：用户通过显式命令表达物化意图，产品层面无歧义。
边界限定：此例外仅适用于 `~go plan` 命令路径，不上升为"显式命令天然免授权"的一般性原则。
后续如需扩展其他命令的 exemption，应单独评审。

实现方式：`_classify_command` 返回的 `plan_only` RouteDecision 仍携带 `plan_package_policy="immediate"`。
只有 `_estimate_complexity` / 非命令路径产出的 planning route 才走 `authorized_only`。

**D7: `confirm` 直接删除**

`confirm` 是 `PLAN_PACKAGE_POLICIES` 中的历史值，在 Wave 3a（engine.py:1909）被退化为 `immediate`。
当前线上无用户，无需做兼容迁移。

处理方式：
1. `PLAN_PACKAGE_POLICIES` 删除 `"confirm"`
2. `_normalized_plan_package_policy` 中 `confirm → immediate` 退化逻辑直接删除
3. 3 处测试中 `plan_package_policy="confirm"` 改为 `"authorized_only"` 或 `"immediate"`（按测试意图选择）
4. 任何外部传入 `"confirm"` 会被 `_normalize_keyword` 归一化为 `"none"`（fail-closed，符合蓝图方向）

---

## In-scope

- `runtime/_models/core.py` — `PLAN_PACKAGE_POLICIES` 替换：删 `confirm`，增 `authorized_only`
- `_plan_package_policy_for_route` 改默认值
- `_normalized_plan_package_policy` 去掉兜底 immediate + 删除 `confirm` 退化逻辑
- engine 增加 authorization check 控制物化
- router `_ACTION_KEYWORDS` 去掉单字误伤
- 测试：授权边界 + consult 误判回归 + confirm 存量测试更新

## Out-of-scope

- 不改 protocol 主 schema
- 不新增 action type
- 不重做 Validator 架构
- 不处理 DECISION_REJECT surface
- 不扩到 P2 动作层

---

## 影响范围

| 切片 | 文件 | 操作 | 说明 |
|------|------|------|------|
| L2 | runtime/_models/core.py | 编辑 | `PLAN_PACKAGE_POLICIES` 替换：删 `confirm`，增 `authorized_only` |
| L2 | runtime/router.py | 编辑 | `_plan_package_policy_for_route` 默认改为 `authorized_only` |
| L2 | runtime/engine.py | 编辑 | `_normalized_plan_package_policy` 去兜底; `confirm` 直接删除; `_advance_planning_route` 增加 authorization check，unauthorized 降级到 consult |
| L1 | runtime/router.py | 编辑 | `_ACTION_KEYWORDS` 去单字 |
| T  | tests/test_action_intent.py | 编辑 | 更新 feature request regression tests 匹配 consult 降级行为 |
| T  | tests/test_runtime_engine.py | 编辑 | `plan_package_policy="confirm"` 存量改为 `"authorized_only"`; 增加 `_propose_plan_action()` helper |
| T  | tests/test_runtime_router.py | 编辑 | `"immediate"` 断言改为 `"authorized_only"` |
| T  | tests/test_runtime_gate.py | 编辑 | archive failure test 增加 `action_proposal_json` |
| T  | scripts/check-prompt-runtime-gate-smoke.py | 编辑 | `protected_plan_asset` scenario 匹配 consult 降级行为 |

---

## 验收标准

1. `_plan_package_policy_for_route("plan_only", ...)` 对非命令路径返回 `"authorized_only"`
2. `_normalized_plan_package_policy` 不再有任何路径隐式返回 `"immediate"`（除 `~go plan` 显式命令）
3. 当 host 未提交 ActionProposal 时，planning route 降级到 consult，不创建 plan 目录
4. 当 host 提交 `propose_plan` + `write_plan_package` + high confidence + evidence 时，planning route 正常创建 plan
5. "批判看下哪些必须修，等我确认" 不再被 `_is_consultation` 判为 change intent
6. `~go plan <request>` 仍正常创建 plan（显式命令不受影响）
7. 全量 pytest 通过

## Known Debt

**resume path `plan_materialization_authorized=True` 写死（3 处）**

当前 3 处 checkpoint 恢复路径（engine.py clarification resume / decision resume / run resume）硬编码 `plan_materialization_authorized=True`。
这些路径只从已授权或显式 plan flow（`~go plan` / `immediate`）产生的 checkpoint 恢复时才到达，当前上游生成 checkpoint 的方式保证了安全性。
但 contract 本身没有绑定 authorization provenance——它依赖上游恰好安全，而不是自身校验。
更细的 authorization provenance binding（在 checkpoint state 中记录授权来源，resume 时验证）留给 P1.5-B / P2 收敛。
