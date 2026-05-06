# 技术设计: P1.5-B Authorization Contract Spec

## 核心策略

以 ADR-017 ExecutionAuthorizationReceipt 为唯一 receipt shape，做 5 项 contract 提升 + 最小 runtime 闭环。
产出以 spec（protocol.md / ADR-017 normative wording）为主体，最小实现只做到"能生成 + 能失效 + 有测试"。

## Plan Intake Checklist

1. **命中蓝图里程碑**：P1.5（主）
2. **改动性质**：contract acceptance boundary（进 blueprint）+ 最小 runtime 实现
3. **新增 machine truth**：是 — ExecutionAuthorizationReceipt 从"方向"升格为 normative contract
4. **Legacy surface 影响**：不动 ExecutionGate（相邻但不同的 gate truth，P3a 再评估是否收敛）
5. **Core/validator authority 影响**：Validator 在 execute_existing_plan 授权通过时生成 receipt，receipt 作为 machine truth 暴露给 handoff/state

---

## 设计决策

### D1: ExecutionAuthorizationReceipt 作为独立 dataclass，不扩展 ExecutionGate

ExecutionGate（`_models/core.py:178`）回答"plan 可否继续"（gate_status / blocking_reason / plan_completion / next_required_action）。
ExecutionAuthorizationReceipt 回答"execute_existing_plan 被谁、基于哪个 revision、通过什么授权"。

两者是相邻但不同的 truth：
- ExecutionGate 是 plan 生命周期 truth（每轮更新）
- ExecutionAuthorizationReceipt 是 action 授权 truth（一次性生成，stale 时失效）

不合并、不互相嵌套。Receipt 新建独立 dataclass。

### D2: Receipt 字段严格对齐 ADR-017，不增不减

| 字段 | 来源 | 实现说明 |
|------|------|---------|
| `plan_id` | plan 目录名（如 `20260501_dark_mode`） | 从 PlanSubjectProposal.subject_ref 提取 |
| `plan_path` | workspace-relative plan 目录路径 | = PlanSubjectProposal.subject_ref |
| `plan_revision_digest` | plan.md 的 SHA-256 hex | = PlanSubjectProposal.revision_digest（**此字段是 `revision_digest` 在 plan subject 场景的特化命名，不是独立概念**） |
| `gate_status` | ExecutionGate.gate_status 当前值 | 从 ValidationContext 或 gate 评估结果读取 |
| `action_proposal_id` | 本次 ActionProposal 的唯一标识 | 新增字段，见 D4 |
| `authorization_source` | `{ kind: "request_hash", request_sha1: string }` | 从 gate 入口参数构建 |
| `fingerprint` | `sha256(canonical_json({plan_id, plan_path, plan_revision_digest, gate_status, action_proposal_id}))` | 确定性生成 |
| `authorized_at` | ISO 8601 时间戳 | 生成时取 UTC |

### D3: Receipt 生成位点 — engine pre-route authorization 通过时

当 Validator 对 `execute_existing_plan` 返回 `DECISION_AUTHORIZE` 时，engine 在 pre-route interceptor（`engine.py:629-678`）生成 receipt。

Receipt 写入路径：
1. 作为 `ValidationDecision.artifacts["execution_authorization_receipt"]` 传递
2. handoff 暴露 receipt（machine truth，宿主可消费）
3. state 持久化 receipt（跨 session 可恢复）

### D4: action_proposal_id 生成规则

ActionProposal 新增 `proposal_id` 字段（可选，由 Validator/engine 注入，不由 host 生成）。

生成规则：`sha256(canonical_json({action_type, side_effect, plan_subject.subject_ref, plan_subject.revision_digest, request_hash}))[:16]`

- 确定性：相同输入产生相同 ID（幂等）
- 唯一性保证范围：同一 plan revision 的同一 action type 不重复
- 不跨 plan revision：revision_digest 变更后 ID 自然不同
- **Host 传入 proposal_id 一律 reject**：parse 时如检测到 host 提供的 `proposal_id` 字段则 raise ValueError。只有 engine 内部生成的 ID 有效。不预留 future extensibility 口子。

### D5: Stale receipt 检测与 fail-closed

**Receipt 生命周期与入口链路：**

1. Receipt 在 `execute_existing_plan` + `DECISION_AUTHORIZE` 时生成
2. Receipt **MUST 持久化到 state 文件**（不可选——stale 检测的数据来源）
3. 下一次 `execute_existing_plan` 请求进入 Validator 时，Validator **从 state 读取**已有 receipt（不从 ActionProposal 携带——host 不感知 receipt 内部结构）
4. Validator 比较已有 receipt 字段与当前文件事实，判定 stale 或 valid

**Receipt 不由 host 传入的原因：** host 是 proposal source，不是 receipt authority。让 host 携带 receipt 会打破"Validator 是唯一授权者"不变量，且创造 receipt 伪造攻击面。

Receipt 失效条件（任一成立即 stale）：
1. `plan_revision_digest` 与当前 plan.md 实际 SHA-256 不匹配
2. `gate_status` 与当前 ExecutionGate.gate_status 不匹配
3. `plan_path` 指向的 plan 目录不存在

Stale 处置：Validator 返回 `DECISION_REJECT`（不降级 consult，不自动 re-authorize）。
host 需要重新提交 ActionProposal 触发新授权。

### D6: 命名对齐正式写入 spec

- protocol.md §7 通用 subject identity 使用 `revision_digest`（不改）
- ExecutionAuthorizationReceipt 使用 `plan_revision_digest`（ADR-017 原始命名）
- 两者关系正式写入 protocol.md：`plan_revision_digest` 是 `revision_digest` 在 plan subject 场景的特化命名
- runtime 中 PlanSubjectProposal 保留 `revision_digest` 字段名（它是通用 subject identity 的消费方），receipt 中使用 `plan_revision_digest`（它是 receipt 的字段）
- 不做批量 rename，不做运行时别名

### D7: 不动 ExecutionGate，不做通用 receipt framework

- ExecutionGate 保持原样——它的 gate_status 是 receipt 的一个输入字段，但两者职责不同
- 不新增 `ReceiptBase` / `ReceiptFactory` 等抽象——只有一个 receipt shape
- 不在本轮为 archive_plan / propose_plan 等其他 action type 生成 receipt（那是 P2 的事）

---

## In-scope

| 层 | 范围 |
|----|------|
| **Spec** | protocol.md: receipt 字段从 informative 升格 normative；命名对齐注释 |
| **Spec** | ADR-017: "方向"标注改为 normative，补充 fail-closed 语义 |
| **Runtime** | `action_intent.py`: `ExecutionAuthorizationReceipt` dataclass + `action_proposal_id` 生成 |
| **Runtime** | `engine.py`: pre-route auth 通过时生成 receipt，传递到 handoff/state |
| **Runtime** | Stale receipt 检测：Validator 校验 receipt + digest 一致性 |
| **Tests** | receipt 生成 + stale fail-closed + fingerprint 确定性 + authorization context |

## Out-of-scope

- 不动 ExecutionGate（相邻但不同的 gate truth）
- 不做通用 receipt framework
- 不为 archive_plan / propose_plan 生成 receipt（P2）
- 不扩 non-plan subject
- 不做 review wire contract
- 不做 engine.py 架构重构
- 不做双命名长期并存（明确关系后不再讨论）

---

## 影响范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `blueprint/protocol.md` | 编辑 | §6 receipt 字段升格 normative；§7 命名对齐注释 |
| `blueprint/architecture-decision-records/ADR-017.md` | 编辑 | "方向"改 normative；补 fail-closed 语义 |
| `runtime/action_intent.py` | 编辑 | 新增 `ExecutionAuthorizationReceipt` dataclass + `generate_proposal_id()` |
| `runtime/engine.py` | 编辑 | pre-route auth 通过时生成 receipt；传递到 ValidationDecision.artifacts |
| `runtime/handoff.py` | 编辑 | 暴露 receipt 到 handoff output |
| `runtime/_models/core.py` | 可能编辑 | 如需在 PlanArtifact/RouteDecision 中挂载 receipt 引用 |
| `runtime/state.py` | 可能编辑 | receipt 持久化 |
| tests/ | 新增+编辑 | receipt 生成、stale 检测、fingerprint 确定性、全量回归 |

---

## 验收标准

1. `ExecutionAuthorizationReceipt` dataclass 存在，字段与 ADR-017 一一对应（8 个字段）
2. `execute_existing_plan` + `DECISION_AUTHORIZE` 时生成 receipt，handoff 可见
3. plan.md 内容变更后，已有 receipt 的 `plan_revision_digest` 不匹配 → Validator 返回 `DECISION_REJECT`
4. `action_proposal_id` 确定性生成：相同输入 → 相同 ID
5. `fingerprint` 确定性生成：`sha256(canonical_json(...))` 可独立重算验证
6. protocol.md receipt 字段标注 normative（RFC 2119 表述）
7. ADR-017 ExecutionAuthorizationReceipt 节标注 normative
8. 命名对齐注释写入 protocol.md / ADR-017
9. 全量 pytest 通过

## Known Debt (carried forward)

- P1.5-C 遗留：resume path `plan_materialization_authorized=True` 写死（3 处）。本轮如果 receipt 引入了 authorization provenance，可评估是否顺带修复。不作为本轮硬目标。
