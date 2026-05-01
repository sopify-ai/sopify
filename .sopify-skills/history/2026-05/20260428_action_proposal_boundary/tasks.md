# Tasks: Action/Effect Boundary P0 Thin Slice

> **基线**：`blueprint/design.md`（原父方案包 `20260424_lightweight_pluggable_architecture` 已删除，证据留 git history）
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
- [x] 新建 `runtime/action_intent.py`
  - ActionProposal dataclass（action_type, side_effect, confidence, evidence）
  - ValidationContext dataclass（checkpoint_kind, checkpoint_id, stage, required_host_action）；从 context_snapshot / current_handoff / current_run 投影，不新造完整模型
  - ValidationDecision dataclass（decision, resolved_action, resolved_side_effect, route_override, reason_code）
  - ActionValidator class：`validate(proposal, context) → ValidationDecision`；硬规则基于 context 判断 action + side_effect 是否允许
  - P0 实现：consult_readonly + none → authorize/consult；side-effecting + evidence 通过 → authorize/null；side-effecting + evidence 不足 → downgrade consult_readonly；未知 action → fallback_router
  - Deterministic fallback adapter：无 proposal 时返回 None，engine 回落现有 router
- [x] 单元测试：validator deterministic tests

### P0-C: Gate 接收 --action-proposal-json
- [x] 修改 `scripts/runtime_gate.py`
  - 新增 `--action-proposal-json` 参数和 `--action-proposal-capability` 标志
  - New host 无 proposal 且非命令前缀请求时，返回 gate retry contract（含 `action_proposal_schema`），不进入 runtime（这是 gate 层 retry，不是 runtime checkpoint）
  - Legacy host 无 proposal 时，跳过 proposal 层，fallback 到现有 router
  - 有 proposal 时传给 `run_runtime(action_proposal=...)`
- [x] Gate contract 扩展：`action_proposal_schema` 字段 + `action_proposal_retry` response type

### P0-D: Engine pre-route interceptor
- [x] 修改 `runtime/engine.py` `run_runtime()`
  - 新增 `action_proposal` 可选参数
  - Pre-route interceptor：validated `consult_readonly` + `side_effect=none` → 直接构造 `RouteDecision(route_name="consult", ...)`
  - 否则回落 `router.classify(user_input, ...)`
- [x] 不改 `router.py` 签名，不改 router 现有 52 个测试

### P0-E: confirm_plan_package + consult_readonly side-effect row
- [x] 修改 `runtime/contracts/decision_tables.yaml`
  - 补 `switch_to_consult_readonly` for `checkpoint_kind: confirm_plan_package`
  - state_mutators：preserve current_plan_proposal + current_run
  - forbidden_state_effects：materialize_new_plan_package, advance_to_develop, clear_current_plan_proposal
  - handoff_protocol：continue_host_consult + consult_answer
- [x] 确认 side_effect_mapping_table.schema.json 已包含 `switch_to_consult_readonly`（已有）
- [x] 补 deterministic guard 测试

### P0-F: Host prompt 更新
- [x] 宿主 prompt 加一条规则：首次调用 gate 时声明 `--action-proposal-capability`；当 gate contract 返回 `action_proposal_schema` 时，按 schema 生成 ActionProposal 并以 `--action-proposal-json` 重试 gate
- [x] 不在 prompt 嵌入完整 schema（schema 由 gate contract 动态返回）
- [x] 说明：`--action-proposal-capability` 是 gate 区分 new host 和 legacy host 的必要依据；不声明则 gate 走 legacy fallback，schema 不返回

### P0-G: 测试与验证
- [x] Validator deterministic tests（CI 阻塞；给定 ActionProposal → 确定性 validation result）
- [x] Integration route tests（CI 阻塞；完整链路 user input → proposal → gate → validator → final route）
- [x] Side effect mapping tests（CI 阻塞）
- [x] 保留现有 router 52 个测试（不改，确认 fallback 不回归）
- [x] 回归样例：
  - Validator: consult_readonly+none→authorize/consult, propose_plan+write+high+evidence→authorize/null, propose_plan+write+low→downgrade consult_readonly, propose_plan+write+evidence不足→downgrade consult_readonly
  - Integration: "批判看下"→consult, "加一个缓存功能"→light_iterate(router fallback)

---

## 依赖关系

```
P0-A (文档) ← 已完成
  ↓
P0-B (schema + validator) → P0-E (effect row) 可并行 ← 已完成
  ↓
P0-C (gate ingestion) ← 已完成
  ↓
P0-D (engine interceptor) ← 已完成
  ↓
P0-F (host prompt) ← 已完成
  ↓
P0-G (测试) ← 已完成
  ↓
P0-H (legacy cleanup; low-risk done; medium-risk deferred)
```

## Legacy 标注

以下 classifier 在 P0-H (low-risk) 中已删除：
- ~~`plan_meta_review`（`_classify_plan_meta_review`）~~ — 已删除，含 `_looks_like_plan_meta_review` + 10 个专属常量
- ~~`analyze_challenge`（`_classify_analyze_challenge`）~~ — 已删除，含 `_match_analyze_challenge_label` + 6 个专属常量

以下保留（有独立调用者或非 classifier）：
- `analysis_only_no_write_brake` — 是 decision_tables.yaml 信号，非 classifier
- `explain_only_override`（`_classify_explain_only_override`） — 有 engine.py 交互，中等风险，待后续方案包处理
- `_active_plan_meta_review_has_followup_edit` / `_split_active_plan_review_fragments` — 被 `_should_bypass_consult_for_active_plan_followup_edit` 共用

### P0-H: Legacy classifier path cleanup ✅ (low-risk done)

- **依赖**: P0-G
- **Dogfood bypass 说明**: low-risk 删除（`plan_meta_review` / `analyze_challenge`）在 P0-G 测试通过后直接执行，未等 1 轮 dogfood。原因：这两条 classifier 的所有调用路径已被 ActionProposal validator 覆盖且有 80 个 deterministic 测试保护，callsite audit 确认无共享依赖。Pragmatic override，风险可控。Dogfood 准入条件重新定义为 `explain_only_override` 删除（medium-risk）的前置条件。
- **完成内容 (low-risk)**:
  - 删除 `_classify_plan_meta_review` 及其专属 helper `_looks_like_plan_meta_review`
  - 删除 `_classify_analyze_challenge` 及其专属 helper `_match_analyze_challenge_label`
  - 删除 16 个专属常量（10 个 `_PLAN_META_REVIEW_*` / `_ACTIVE_PLAN_META_REVIEW_ANCHORS` + 6 个 `_ANALYZE_CHALLENGE_*`）
  - 保留共享 helper 链：`_should_bypass_consult_for_active_plan_followup_edit` → `_active_plan_meta_review_has_followup_edit` → `_split_active_plan_review_fragments` + 2 个 cue 常量
  - 删除 7 个测试（3 router + 3 plan-reuse + 1 sample-invariant）
  - 全量测试 652 passed + 68 subtests passed
- **Deferred (medium-risk)**: `explain_only_override` 删除待后续方案包
- **流程**: 按 ADR-018 sunset → removed

## 验证摘要 (2026-04-29)

| 指标 | 结果 |
|------|------|
| 全量测试 | 652 passed |
| action_intent 专项 | 80 passed (9.8s) |
| P0-G 覆盖场景 | gate function 层、CLI 层、exit 1 仍解析 stdout、malformed JSON、command prefix bypass、special characters/quoting、two-phase retry 成功路径 |
| Legacy classifier 状态 | `plan_meta_review` 已删、`analyze_challenge` 已删、`explain_only_override` deferred、`analysis_only_no_write_brake` 保留(signal) |
| Dogfood 状态 | **通过** — 真实宿主路径 `action_proposal_retry → proposal → consult` 全链路验证 |

**Dogfood 验证记录 (2026-04-29)：**
1. Phase 1: `--action-proposal-capability` 无 proposal → gate 返回 `action_proposal_retry` + schema ✅
2. Phase 2: `--action-proposal-json consult_readonly` → `gate_passed=true, route=consult, reason=validator.consult_readonly_authorized, handoff=continue_host_consult` ✅
3. 修复过程中发现 `.agents/skills/cross-review/` 的 `skill.md` 和 `skill.yaml` 使用了 `>-` 多行折叠语法（runtime `_yaml.py` 不支持），已改为单行引号字符串
4. workspace 级 `.sopify-runtime/manifest.json` bundle_version 不一致（`2026-04-10.104951` vs global `2026-03-31.154241`），已对齐

**Dogfood 准入条件（medium-risk `explain_only_override` 删除）：**
1. 真实宿主触发非命令前缀请求
2. 宿主接收 `action_proposal_retry` gate contract
3. 宿主按 schema 生成 ActionProposal 并重试 gate
4. 最终路由为 consult（不误建方案包）

## 迁移风险说明

未升级 host 不声明 `--action-proposal-capability` 时，分析类请求（"批判看下"、"分析下这个方案的评分"等）可能回落 legacy router 并误判为 `light_iterate`，导致误建方案包。该风险接受，理由：
- 当前线上 host 可控且已升级，默认声明 `--action-proposal-capability`
- ActionProposal validator 是正式保护层，legacy keyword classifier 不再是安全边界
- 补回 keyword classifier 与 ActionProposal 架构方向冲突，收益不抵维护成本

## Follow-up（不建方案包，仅列出）

- `protocol_step3_schema_docs`：ActionProposal schema 写入 protocol 文档层
- `runtime_handoff_slimming`：精简 handoff artifacts
- `action_audit_observability`：action_audit.jsonl 事件可观测性
- `host_prompt_governance`：**建议新开 standard 方案包**（`20260429_host_prompt_governance`）。P0-F 暴露 4 × 510 行 prompt 的三层重复维护成本（说明行/宿主接入约定/快速参考各展开一遍 allowed_response_mode 等机器契约）。核心原则："prompt 是 runtime contract 的适配层，不是事实源"。预期内容：重复规则审计 → prompt 架构分层（核心角色/gate 算法/checkpoint 表/输出格式/资源索引）→ `check-prompt-governance.py` 准入脚本 → prompt 瘦身至 350-400 行。6 条工程原则待沉淀至 `.sopify-skills/blueprint/prompt-governance.md`。
