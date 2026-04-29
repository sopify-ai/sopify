# Tasks: Action/Effect Boundary P0 Thin Slice

> **父方案包**：`20260424_lightweight_pluggable_architecture`
> **ADR 依据**：ADR-017 (Action/Effect Boundary before Materialization)
> **目标**：建立 Action/Effect Boundary，先用 `consult_readonly` thin slice 解决 no-write 局部语境。局部语境请求被 router 误读为全局推进是通用问题，方案包误建是当前最高频症状。P0 只激活 `consult_readonly` pre-route 拦截；后续 reserved actions 逐步覆盖 checkpoint response / cancel / revise / execute 等局部动作。

---

## 任务列表

### P0-A: 文档修订（总纲 ADR-017 + 子方案包引用）
- [x] 总纲 design.md：ADR-017 标题升级 + host-generated ActionProposal + gate retry contract + write_plan_package 受控 side effect + active/reserved 分离
- [x] 总纲 tasks.md：Protocol Step 3 thin slice 提高优先级 + 子方案包索引
- [x] Blueprint design.md：State Resolution 和 Routing 之间补 Action/Effect Boundary 摘要
- [x] 新建本子方案包（design.md + tasks.md，不建 background.md）

### P0-B: ActionProposal schema + ValidationContext + Validator
- [ ] 新建 `runtime/action_intent.py`
  - ActionProposal dataclass（action_type, side_effect, confidence, evidence）
  - ValidationContext dataclass（checkpoint_kind, checkpoint_id, stage, required_host_action）；从 context_snapshot / current_handoff / current_run 投影，不新造完整模型
  - ValidationDecision dataclass（decision, resolved_action, resolved_side_effect, route_override, reason_code）
  - ActionValidator class：`validate(proposal, context) → ValidationDecision`；硬规则基于 context 判断 action + side_effect 是否允许
  - P0 实现：consult_readonly + none → authorize/consult；side-effecting + evidence 通过 → authorize/null；side-effecting + evidence 不足 → downgrade consult_readonly；未知 action → fallback_router
  - Deterministic fallback adapter：无 proposal 时返回 None，engine 回落现有 router
- [ ] 单元测试：validator deterministic tests

### P0-C: Gate 接收 --action-proposal-json
- [ ] 修改 `scripts/runtime_gate.py`
  - 新增 `--action-proposal-json` 参数和 `--action-proposal-capability` 标志
  - New host 无 proposal 且非命令前缀请求时，返回 gate retry contract（含 `action_proposal_schema`），不进入 runtime（这是 gate 层 retry，不是 runtime checkpoint）
  - Legacy host 无 proposal 时，跳过 proposal 层，fallback 到现有 router
  - 有 proposal 时传给 `run_runtime(action_proposal=...)`
- [ ] Gate contract 扩展：`action_proposal_schema` 字段 + `action_proposal_retry` response type

### P0-D: Engine pre-route interceptor
- [ ] 修改 `runtime/engine.py` `run_runtime()`
  - 新增 `action_proposal` 可选参数
  - Pre-route interceptor：validated `consult_readonly` + `side_effect=none` → 直接构造 `RouteDecision(route_name="consult", ...)`
  - 否则回落 `router.classify(user_input, ...)`
- [ ] 不改 `router.py` 签名，不改 router 现有 52 个测试

### P0-E: confirm_plan_package + consult_readonly side-effect row
- [ ] 修改 `runtime/contracts/decision_tables.yaml`
  - 补 `switch_to_consult_readonly` for `checkpoint_kind: confirm_plan_package`
  - state_mutators：preserve current_plan_proposal + current_run
  - forbidden_state_effects：materialize_new_plan_package, advance_to_develop, clear_current_plan_proposal
  - handoff_protocol：continue_host_consult + consult_answer
- [ ] 确认 side_effect_mapping_table.schema.json 已包含 `switch_to_consult_readonly`（已有）
- [ ] 补 deterministic guard 测试

### P0-F: Host prompt 更新
- [ ] 宿主 prompt 加一条规则：首次调用 gate 时声明 `--action-proposal-capability`；当 gate contract 返回 `action_proposal_schema` 时，按 schema 生成 ActionProposal 并以 `--action-proposal-json` 重试 gate
- [ ] 不在 prompt 嵌入完整 schema（schema 由 gate contract 动态返回）
- [ ] 说明：`--action-proposal-capability` 是 gate 区分 new host 和 legacy host 的必要依据；不声明则 gate 走 legacy fallback，schema 不返回

### P0-G: 测试与验证
- [ ] Validator deterministic tests（CI 阻塞；给定 ActionProposal → 确定性 validation result）
- [ ] Integration route tests（CI 阻塞；完整链路 user input → proposal → gate → validator → final route）
- [ ] Side effect mapping tests（CI 阻塞）
- [ ] 保留现有 router 52 个测试（不改，确认 fallback 不回归）
- [ ] 回归样例：
  - Validator: consult_readonly+none→authorize/consult, propose_plan+write+high+evidence→authorize/null, propose_plan+write+low→downgrade consult_readonly, propose_plan+write+evidence不足→downgrade consult_readonly
  - Integration: "批判看下"→consult, "加一个缓存功能"→light_iterate(router fallback)

---

## 依赖关系

```
P0-A (文档) ← 已完成
  ↓
P0-B (schema + validator) → P0-E (effect row) 可并行
  ↓
P0-C (gate ingestion)
  ↓
P0-D (engine interceptor)
  ↓
P0-F (host prompt)
  ↓
P0-G (测试)
  ↓
P0-H (legacy cleanup; 触发: P0-G pass + 1 轮 dogfood)
```

## Legacy 标注

以下 classifier 在 P0 中标为 legacy compatibility path，不删除：
- `analysis_only_no_write_brake`
- `plan_meta_review`（`_classify_plan_meta_review`）
- `analyze_challenge`（`_classify_analyze_challenge`）
- `explain_only_override`（`_classify_explain_only_override`）

Legacy fallback 是开发期安全网；P0-F 更新 host prompt 后即为死代码。

### P0-H: Legacy classifier path cleanup

- **依赖**: P0-G
- **触发条件**: P0-G 测试通过 + 1 轮 dogfood 验证
- **内容**: 先列出四条路径的全部 callsite（含 checkpoint response、cancel、数字选项等非 consult 场景），确认无复用后再删除 `analysis_only_no_write_brake`、`_classify_plan_meta_review`、`_classify_analyze_challenge`、`_classify_explain_only_override` 及其测试；更新总纲 ADR-017（移除 legacy compatibility 段落）；更新 host prompt（移除 legacy fallback 描述）；跑全量测试确认无残留依赖
- **流程**: 按 ADR-018 sunset → removed

## Follow-up（不建方案包，仅列出）

- `protocol_step3_schema_docs`：ActionProposal schema 写入 protocol 文档层
- `runtime_handoff_slimming`：精简 handoff artifacts
- `action_audit_observability`：action_audit.jsonl 事件可观测性
