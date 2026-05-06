# 技术设计: P1.5-A DECISION_REJECT Surface 收口

## 核心策略

把 DECISION_REJECT 从伪装为 consult 的 4 层语义谎言中剥出来，建立独立的 reject host-facing surface。
不新增 required_host_action（预算 5 不破），不新增 state 文件，不新增 checkpoint type。

## Plan Intake Checklist

1. **命中蓝图里程碑**：P1.5（A 包）
2. **改动性质**：contract acceptance boundary（进 blueprint Non-family Surfaces 表）+ runtime 表面修正
3. **新增 machine truth**：否 — reject 已是 machine truth（DECISION_REJECT），本轮只修正 host-facing surface 对齐
4. **Legacy surface 影响**：不动 authorized_only blocked consult（`engine.py:2165` 那类是不同语义）
5. **Core/validator authority 影响**：无 — Validator 判定逻辑不改，只改 engine→handoff→output 的 reject 表面投影

---

## 设计决策

### D1: route_name = "proposal_rejected"（non-family surface）

新增 `"proposal_rejected"` 作为 non-family surface，与 `state_conflict` 同类（跨路由错误面）。

命名理由：
- 不叫 `"reject"` — 太泛，可能与 future gate/auth reject 混淆
- 叫 `"proposal_rejected"` — 明确来源是 ActionProposal 链路的 Validator reject

不进 `_CANONICAL_ROUTE_FAMILIES`（非 resumable workflow continuation），进 `_NON_FAMILY_SURFACES`。

### D2: handoff_kind = "reject"

新增 handoff_kind 值 `"reject"`。

宿主可通过 switch-case `handoff_kind` 做拒绝展示，与 `"consult"` 明确区分。

### D3: required_host_action 保持 "continue_host_consult"

不新增 canonical action。预算维持 5。

理由：reject 后宿主实际行为 IS "继续对话告知用户为什么被拒"。
reject 的"被拒绝"语义通过 handoff_kind + artifacts 传达，不需要 host_action 维度承载。

### D4: artifacts 注入 reject 结构化信息

engine.py reject 分支写入 `RouteDecision.artifacts`：

```python
{
    "reject_reason_code": validation_decision.reason_code,
}
```

handoff artifacts 通过 `_collect_handoff_artifacts` 传递（需确保 reject 分支的 artifacts 被转发）。

### D5: output.py reject 投影

三个位点全部需要覆盖：

1. `_PHASE_LABELS`（L14/L33）：新增 `"proposal_rejected"` 阶段标签（中："操作被拒绝" / 英："Action Rejected"）
2. `_status_message()`（L447）：在 handoff required_host_action 查表之前，拦截 `route_name == "proposal_rejected"` 分支，返回 reject 专用文案（不让它落入 `handoff_continue_host_consult`）
3. `_handoff_next_hint()`（L493）：当 `handoff_kind == "reject"` 时，返回 reject 提示而非 consult 提示

对应 _LABELS 需新增 label key：
- `"reject_status"`: "操作被拒绝，请查看原因" / "Action rejected; review the reason"
- `"next_reject"`: "操作被拒绝，请查看原因后重新提交" / "Action rejected; review the reason and resubmit"

### D6: 不动 ExecutionGate / authorized_only / state

- `engine.py:2165` 的 authorized_only blocked → consult 是不同语义（plan materialization 授权缺失，不是 Validator reject），不碰
- 不新增 `current_reject.json` — reject 不做 state mutation（engine.py:662 注释已明确）
- 不改 gate mode、不断开 continue_host_consult 这条 host action

---

## In-scope

| 层 | 范围 |
|----|------|
| **Engine** | engine.py: reject 分支 route_name 改为 "proposal_rejected"；artifacts 注入 reject_reason_code |
| **Engine** | engine.py: _NON_FAMILY_SURFACES 扩口 |
| **Handoff** | handoff.py: _ROUTE_HANDOFF_KIND 新增 "proposal_rejected" → "reject" |
| **Handoff** | handoff.py: _required_host_action 新增 "proposal_rejected" → "continue_host_consult" |
| **Output** | output.py: _PHASE_LABELS 阶段标签 + _status_message reject 拦截 + _handoff_next_hint reject 分支 + _LABELS 新增 label key |
| **Blueprint** | design.md: Non-family Surfaces 表新增 proposal_rejected |
| **Tests** | 现有 reject 断言更新 + 新增回归测试 |

## Out-of-scope

- 不碰 authorized_only blocked consult（engine.py:2165）
- 不新增 required_host_action（预算 5 不破）
- 不新增 checkpoint type（预算 2 不破）
- 不新增 state 文件
- 不改 ExecutionGate / ExecutionAuthorizationReceipt
- 不碰 ADR-017 / protocol.md receipt 语义
- 不做 generic fail-close surface / retry pattern
- 不做 archive transport label

---

## 影响范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `runtime/engine.py` | 编辑 | :664 route_name → "proposal_rejected"; artifacts 注入; :103 _NON_FAMILY_SURFACES 扩口 |
| `runtime/handoff.py` | 编辑 | _ROUTE_HANDOFF_KIND 新增; _required_host_action 新增分支 |
| `runtime/output.py` | 编辑 | _PHASE_LABELS 阶段标签 + _status_message reject 拦截 + _handoff_next_hint reject 分支 + _LABELS 新增 label key |
| `tests/test_action_intent.py` | 编辑 | 现有 reject 测试断言更新 + 新增回归测试 |
| `blueprint/design.md` | 编辑 | Non-family Surfaces 表新增 proposal_rejected |
| `blueprint/tasks.md` | 编辑 | A 状态标记 |

---

## 验收标准

1. DECISION_REJECT 场景 `route_name == "proposal_rejected"`（不是 "consult"）
2. `handoff_kind == "reject"`
3. `handoff.artifacts` 包含 `reject_reason_code`（结构化原因）
4. `required_host_action == "continue_host_consult"`（预算不破）
5. output 投影显示拒绝语义（阶段标签 + 状态文案 + next hint + 状态符 `!`，不是 consult 文案/`✓`）
6. 正常 consult 路径无回归（真 consult 仍然 route_name="consult"、handoff_kind="consult"）
7. digest mismatch admission reject 走新 surface（stale receipt run-level proof 延后到 T5-C follow-up）
8. `_NON_FAMILY_SURFACES` 包含 `"proposal_rejected"`
9. `design.md` Non-family Surfaces 表已更新
10. 全量 pytest 通过
