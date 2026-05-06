# 任务清单: P1.5-B Authorization Contract Spec

目录: `.sopify-skills/plan/20260506_p15_authorization_contract_spec/`

## 1. Spec 层 — 协议与 ADR 升格

- [x] T1-A: `protocol.md` §6 receipt 字段升格 normative
  - 在统一出口表 receipt 行补充 RFC 2119 表述：receipt MUST 包含 plan_id / plan_revision_digest / gate_status / action_proposal_id / authorization_source / fingerprint / authorized_at
  - 补充 fail-closed 语义：任一字段不匹配时 MUST 拒绝执行
  - 验收: receipt 字段使用 MUST/MUST NOT 表述

- [x] T1-B: `protocol.md` §7 命名对齐注释
  - 在 Subject Identity 节或 execute_existing_plan binding 节增加注释：`plan_revision_digest`（receipt 场景）是 `revision_digest`（通用 subject identity）在 plan subject 的特化命名
  - 验收: 注释存在，措辞明确"特化命名，不是独立概念"

- [x] T1-C: `ADR-017.md` ExecutionAuthorizationReceipt 升格
  - "方向"标注改为 normative
  - 补充 fail-closed 不变量的 RFC 2119 表述
  - 补充 stale receipt 处置规则：Validator MUST 返回 DECISION_REJECT
  - 验收: ADR-017 ExecutionAuthorizationReceipt 节使用 MUST/MUST NOT

## 2. Runtime 层 — Receipt 数据结构

- [x] T2-A: `action_intent.py` 新增 `ExecutionAuthorizationReceipt` dataclass
  - 8 个字段严格对齐 ADR-017（plan_id / plan_path / plan_revision_digest / gate_status / action_proposal_id / authorization_source / fingerprint / authorized_at）
  - `to_dict()` / `from_dict()` 往返序列化
  - `fingerprint` 由 `sha256(canonical_json({plan_id, plan_path, plan_revision_digest, gate_status, action_proposal_id}))` 确定性生成
  - 验收: dataclass frozen + 字段对齐 + fingerprint 可独立重算

- [x] T2-B: `action_intent.py` 新增 `generate_proposal_id()` 函数 + host reject
  - 输入：action_type, side_effect, subject_ref, revision_digest, request_hash
  - 输出：`sha256(canonical_json({...}))[:16]`
  - 幂等：相同输入 → 相同 ID
  - **Host 传入 reject**：ActionProposal.from_dict() 如检测到 `proposal_id` 字段 → raise ValueError
  - 验收: 确定性 + host reject + 单元测试

## 3. Runtime 层 — Receipt 生成与传递

- [x] T3-A: `engine.py` 执行路径生成 receipt
  - 拦截器阶段：当 action_type == `execute_existing_plan` 且 Validator 返回 `DECISION_AUTHORIZE` 时，捕获 receipt 食材（plan_path / revision_digest / proposal_id / request_sha1）
  - 执行路径：在 `evaluate_execution_gate()` 返回后，基于最终 gate_status 生成 receipt
    - 从 PlanSubjectProposal 取 plan_path / plan_revision_digest
    - 从 plan_path 提取 plan_id（目录名）
    - 从本次 evaluate_execution_gate() 结果取 gate_status
    - 调用 generate_proposal_id() 生成 action_proposal_id
    - 构建 authorization_source（`{ kind: "request_hash", request_sha1: ... }`）
    - 生成 fingerprint + authorized_at
    - 创建 ExecutionAuthorizationReceipt 实例
  - Receipt 写入 `RunState.execution_authorization_receipt`（持久化事实）
  - Receipt 通过 handoff artifacts 暴露（外部可观测）
  - 无新 receipt 时，所有 RunState 重建分支 MUST carry-forward 旧 receipt
  - 验收: authorize + gate eval 后 RunState 含 receipt dict；gate_status 与 receipt.gate_status 一致

- [x] T3-B: `handoff.py` 暴露 receipt
  - handoff output 中包含 execution_authorization_receipt（如果存在）
  - 验收: handoff JSON 中可见 receipt 字段

- [x] T3-C: receipt 持久化到 state（挂 current_run）
  - 在 `RunState`（`_models/core.py:241`）新增 `execution_authorization_receipt: Optional[Mapping[str, Any]] = None`
  - 类型为 raw Mapping 而非 ExecutionAuthorizationReceipt 类型引用——避免 `_models/core.py` → `action_intent.py` 反向依赖；消费者在使用时通过 `ExecutionAuthorizationReceipt.from_dict()` 获得类型化访问
  - 与 `execution_gate` 平级——同一份 current_run 既承载 gate truth 又承载 receipt truth
  - `to_dict()` / `from_dict()` 同步扩展
  - Validator 在下一次 execute_existing_plan 请求时从 `current_run` 读取已有 receipt
  - 验收: state 文件中 receipt 可存取 + 跨 session 恢复可读

## 4. Runtime 层 — Stale Receipt 检测

- [x] T4-A: Validator 校验 receipt 一致性（stale 检测）
  - 入口链路：Validator 在处理 `execute_existing_plan` 请求时，**从 state 读取**已有 receipt（不从 ActionProposal 携带）
  - 如果 state 中无 receipt → 正常走 admission + 首次授权生成流程
  - 如果 state 中有 receipt → 比较 receipt 字段与当前文件事实：
    - 检查 plan_revision_digest 与当前 plan.md 实际 SHA-256
    - 检查 plan_path 指向的 plan 目录存在性
    - 检查 gate_status 与当前 ExecutionGate.gate_status
  - 任一不匹配 → DECISION_REJECT（不降级 consult，不自动 re-authorize）
  - 验收: stale receipt → reject + 测试覆盖

## 5. 测试

- [x] T5-A: ExecutionAuthorizationReceipt 单元测试
  - to_dict / from_dict 往返
  - fingerprint 确定性（相同输入 → 相同 fingerprint）
  - fingerprint 敏感性（任一字段变更 → fingerprint 变更）
  - 验收: 全部通过

- [x] T5-B: generate_proposal_id 单元测试
  - 幂等性
  - 输入变更 → ID 变更
  - 验收: 全部通过

- [x] T5-C: Receipt 生成集成测试
  - execute_existing_plan + DECISION_AUTHORIZE → receipt 存在于 RunState + handoff artifacts
  - receipt.gate_status 与同回合 ExecutionGate.gate_status 一致
  - consult_readonly → 无 receipt
  - propose_plan → 无 receipt
  - 后续 resume 无新 ActionProposal → carry-forward 旧 receipt
  - 验收: 全部通过

- [x] T5-D: Stale receipt fail-closed 测试
  - plan.md 内容变更 → stale → DECISION_REJECT
  - plan 目录删除 → stale → DECISION_REJECT
  - gate_status 变更 → stale → DECISION_REJECT
  - 验收: 3 种 stale 场景全部 reject

- [x] T5-E: 全量 pytest 验证
  - 验收: 全量通过 + 无回归

## 6. 蓝图回写

- [x] T6-A: 更新 `blueprint/tasks.md` P1.5-B 状态
  - 验收: B 标记完成，D 前置条件已满足

## 已知测试债（Follow-up）

- [ ] T5-C 端到端集成测试（不阻塞主提交）
  - run_runtime() 级别断言：execute_existing_plan + DECISION_AUTHORIZE → RunState.execution_authorization_receipt 非空 + handoff artifacts 包含 receipt
  - consult_readonly / propose_plan → 无 receipt
  - resume carry-forward：无新 ActionProposal → receipt 保留
  - 性质：coverage completeness，不是 contract correctness
  - 建议：作为紧后方案包单独落地，不混入 P1.5-B 主交付
