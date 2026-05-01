# Design: Action/Effect Boundary before Materialization

> **定位**：`blueprint/design.md` 基线的 P0 子方案包（原属 `20260424_lightweight_pluggable_architecture`，已删除）。
> **背景与战略**：引用总纲 ADR-016（Protocol-first）、ADR-017（Action/Effect Boundary）。不复制背景。
> **痛点**：局部语境请求被 router keyword/complexity classifier 误读为全局推进。用户可能只是想分析、批判、确认、取消、修订或查看当前 checkpoint/plan，但 runtime 可能直接进入 `light_iterate` / `workflow` / `confirm_plan_package` 等副作用路径。当前最高频症状是分析/批判类请求被误建方案包；方案包误建是首个症状，不是唯一目标。
>
> **P0 目标**：建立 Action/Effect Boundary，先用 `consult_readonly` thin slice 解决 no-write 局部语境；后续 reserved actions 逐步覆盖 checkpoint response / cancel / revise / execute 等局部动作。

---

## 核心设计

### Pipeline 位置

```
user input
  → Ingress / Preflight (existing gate)
  → State Resolution (existing context_snapshot)
  → ActionProposal resolution ← 新增
  → Effect Validator ← 新增
  → Route Decision (existing router, 或被 interceptor 覆盖)
  → Checkpoint / Execution / Handoff (existing)
```

普通命令前缀请求（`~go`、`~go plan`、`~go exec`、`~compare`）仍可作为确定性路由，不默认经过 ActionProposal。例外：需要结构化主体且会写文件的 command alias 不得直达写入；`~go finalize` 必须先映射为 `ActionProposal(action_type="archive_plan")`，再由 Validator 授权并产出 `archive_lifecycle` artifacts。

### ActionProposal 数据流

```
Host LLM (proposal source)
  读取 gate contract 中的 action_proposal_schema
  → 生成 ActionProposal JSON
  → 调用 runtime_gate.py enter --action-proposal-json '{...}' --request '用户原文'

Gate (ingestion)
  首次无 proposal 且非 legacy host：
    → 返回 gate retry contract（含 action_proposal_schema），不进入 runtime
    → host 填充 proposal 后重试 gate
  首次无 proposal 且 legacy host（不支持 ActionProposal capability）：
    → fallback：跳过 proposal，直接进入现有 router
  有 proposal → 传给 run_runtime(action_proposal=...)

Validator (authorizer, action_intent.py)
  输入: ActionProposal + ValidationContext
  ValidationContext 从 context_snapshot / current_handoff / current_run 投影:
    checkpoint_kind / checkpoint_id / stage / required_host_action
  → ValidationDecision
  P0: consult_readonly + none → authorize, route_override=consult
  P0: side-effecting + evidence 通过 → authorize, route_override=null（Router 继续路由）
  P0: side-effecting + evidence 不足/low confidence → downgrade consult_readonly
  P0: 未知 action → fallback_router（Validator 不处理，回落现有 Router）

Engine (pre-route interceptor)
  authorize + route_override=consult → 直接构造 consult RouteDecision
  authorize + route_override=null → 回落现有 Router.classify()（Validator 已授权，Router 决定具体路由）
  downgrade → 按 resolved_action 处理（P0: consult_readonly → consult RouteDecision）
  fallback_router → 回落现有 Router.classify()
```

**关键约束**：
- Host LLM 是 proposal source，不是 authorizer。Validator 是唯一授权者。
- `fallback_router` 是 Validator 的"不处理/不授权"态，不是 Router 对副作用的授权。它是 reserved actions 尚未协议化接管完成前的临时兼容出口，只表示“当前 proposal 不在 Validator 已接管范围内”，不表示 Router 获得了新的授权。
- `fallback_router` 的职责应单调收缩，不承接新增正式 side-effecting 能力；新增此类能力时，默认先 proposal 化并进入 Validator，而不是先塞进 fallback。

### ActionProposal Schema

```yaml
action_type:                    # 6 个可识别枚举；P0 只对 consult_readonly 做 route override，side-effecting action 做最小 evidence proof 授权但不接管路由
  - consult_readonly            # 分析/批判/讨论，不产生写入 ← P0 唯一 route override action
  - propose_plan                # 请求生成方案包
  - execute_existing_plan       # 执行已有 plan
  - modify_files                # 直接修改文件
  - checkpoint_response         # 对当前 checkpoint 的确认/修订/取消
  - cancel_flow                 # 取消当前流程

side_effect:
  - none                    # 只读
  - write_runtime_state     # 写 state/*.json
  - write_plan_package      # 创建/修改 plan 方案包
  - write_files             # 修改项目代码文件
  - execute_command         # 执行命令行

confidence: high | medium | low

evidence:
  - "用户原文中的依据片段"
```

### ValidationContext（从现有状态投影的只读 view）

```yaml
# 不新造完整模型；从 context_snapshot / current_handoff / current_run 投影
checkpoint_kind: str | null       # confirm_plan_package, confirm_decision, ...
checkpoint_id: str | null
stage: str | null                 # from current_run.stage
required_host_action: str | null  # from current_handoff
```

局部语境不限于 checkpoint；ValidationContext 也覆盖无 checkpoint 的分析/讨论场景（此时所有字段为 null）。

### ValidationDecision（Validator 统一输出）

```yaml
decision: authorize | downgrade | reject | fallback_router
resolved_action: consult_readonly | checkpoint_response | cancel_flow | ...
resolved_side_effect: none | write_runtime_state | write_plan_package | ...
route_override: consult | null
reason_code: ...
```

P0 只走三条路径：
- `consult_readonly + none` → `decision=authorize, route_override=consult`
- side-effecting action + evidence 通过最小 proof → `decision=authorize, route_override=null`（Validator 授权但不接管路由，现有 Router 继续决定路由）
- side-effecting action + evidence 不足或 confidence=low → `decision=downgrade, resolved_action=consult_readonly, route_override=consult`
- 未知/不支持的 action → `decision=fallback_router, route_override=null`

> P0 的 side-effect proof 只证明用户存在明确副作用意图，不替代 response mode、risk policy、execution gate 或项目工具链验证。

### Validator 硬规则

**Verify-A 定位**：Validator 是 pre-write authorization gate（副作用发生前同步校验），区别于 post-write execution gate（Verify-B: tests/lint/build）和 post-produce quality review（Verify-C: CrossReview isolated review）。

**Proposal quality 边界**：P0 不解决 ActionProposal 的 source 质量问题（host LLM 投影可能偏保守或偏激进）。P0 的安全取舍是 fail-close：允许误降级为 consult，不允许误升级为写入。proposal 误降级通过 dogfood 观察，不用关键词补丁修。

1. Validator 基于 ValidationContext 判断：当前 context 下，requested action + side_effect 是否允许。不硬编码单个 side_effect 名称为唯一关注对象。
2. `consult_readonly` + `side_effect=none` 时，不得写 `current_plan_proposal`、不得推进 checkpoint、不得物化 plan。
3. `confidence=low` 或 evidence 不足 → 默认 `consult_readonly`，不创建方案包。
4. **Side-effect proof 原则**：Validator 校验 evidence 是否能正向证明 requested side_effect。不列举具体话术词表；判定标准是"evidence 能否证明写入意图"，而非"evidence 是否包含某些分析类关键词"。
5. `write_plan_package` side effect 需要 evidence 能正向证明写入意图；evidence 不能证明写入意图就拒绝或降级为 `consult_readonly`。`write_plan_package` 是首个受控 side effect，不是 Validator 的唯一关心对象。
6. Checkpoint pending 时收到 `consult_readonly` + `side_effect=none` → 允许 `continue_host_consult`，保留原 checkpoint identity。P0 验证 `confirm_plan_package` 场景；架构不限于此 checkpoint kind。

### Deterministic Fallback

Gate 区分两种无 proposal 场景：

1. **New host（支持 ActionProposal capability）**：无 proposal → gate 返回 retry contract + schema，host 填充后重试。不进入 runtime。
2. **Legacy host（不支持 ActionProposal）**：无 proposal → 跳过 proposal 层，直接进入现有 Router。保证 gate 正常返回、runtime 正常路由，但不承诺 read-only 意图精确保护。

Legacy fallback 保证旧宿主不崩溃，但不保证不误建包。只有理解 ActionProposal schema 的新宿主才获得 read-only 意图保护。当前 host 可控且已升级，该风险接受。

Gate 判定 host 是否支持 ActionProposal 的方式：gate 入口参数是否携带 `--action-proposal-json` 或 `--action-proposal-capability` 标志。首次调用不带标志 → legacy path。

### Legacy Compatibility Paths

以下现有 classifier 在 P0-H (low-risk) 中已删除：
- ~~`plan_meta_review`（`_classify_plan_meta_review`）~~ — 已删除
- ~~`analyze_challenge`（`_classify_analyze_challenge`）~~ — 已删除

以下保留（非 router classifier 或有独立调用者）：
- `analysis_only_no_write_brake` — 是 decision_tables.yaml 信号，非 router classifier
- `explain_only_override`（`_classify_explain_only_override`） — 有 engine.py 交互，后续单独处理

Legacy fallback 保证旧 host 不崩溃（gate 正常返回、runtime 正常路由），但**不承诺 read-only 意图保护**。未声明 `--action-proposal-capability` 的 host 可能将分析类请求误判为 `light_iterate`。该风险接受：当前 host 可控且已升级，ActionProposal 是正式保护层。

### Post-validation Cleanup

P0-H low-risk cleanup 已完成：删除 `plan_meta_review` 和 `analyze_challenge` 两条 legacy classifier 及其专属常量和测试。`explain_only_override` deferred。完整 legacy sunset 另行处理，不在本方案包范围内。

---

## Side Effect Mapping 补齐

`decision_tables.yaml` 的 `side_effect_mapping_rows` 缺少 `confirm_plan_package` 的 `switch_to_consult_readonly` effect row。需补齐：

```yaml
- resolved_action: switch_to_consult_readonly
  checkpoint_kind: confirm_plan_package
  state_mutators:
    preserve:
      - current_plan_proposal
      - current_run
    clear: []
    update: []
    write: []
  forbidden_state_effects:
    - materialize_new_plan_package
    - advance_to_develop
    - clear_current_plan_proposal
  preserved_identity:
    - checkpoint_id
    - reserved_plan_id
    - topic_key
  handoff_protocol:
    required_host_action: continue_host_consult
    artifact_keys:
      - checkpoint_request
      - proposal
    resume_route: plan_proposal_pending
    output_mode: consult_answer
  terminality: route_terminal
  reason_code: effect.hard_constraint.analysis_only_consult_readonly
```

---

## 测试策略

| 测试类型 | CI 阻塞 | 内容 |
|---------|---------|------|
| Validator deterministic tests | ✅ 是 | 给定 ActionProposal → 确定性 route result |
| 现有 router 52 个测试 | ✅ 是 | 不改，确认 fallback path 不回归 |
| Side effect mapping tests | ✅ 是 | 新 effect row 的 deterministic guard 测试 |
| LLM proposal golden-file | ❌ 否 | 10 个典型输入的期望 proposal，手动验证，放 dogfood 记录 |

### Validator deterministic tests

给定 ActionProposal + ValidationContext → 确定性 ValidationDecision。不涉及 router。

| ActionProposal (action_type, side_effect, confidence) | ValidationContext | 期望 ValidationDecision |
|-------------------------------------------------------|-------------------|----------------------|
| consult_readonly, none, high | checkpoint_kind=null | authorize, route_override=consult |
| consult_readonly, none, low | checkpoint_kind=null | authorize, route_override=consult（consult_readonly + none 无需降级） |
| consult_readonly, none, high | checkpoint_kind=confirm_plan_package | authorize, route_override=consult（checkpoint 上方 consult 共存） |
| propose_plan, write_plan_package, high + evidence 充分 | checkpoint_kind=null | authorize, route_override=null（Validator 授权，Router 继续路由） |
| propose_plan, write_plan_package, low | checkpoint_kind=null | downgrade → consult_readonly, route_override=consult |
| propose_plan, write_plan_package, high + evidence 不足 | checkpoint_kind=null | downgrade → consult_readonly, route_override=consult |
| modify_files, write_files, high | checkpoint_kind=null | authorize, route_override=null（Validator 授权，Router 继续路由） |

### Integration route tests

完整链路：user input → host proposal → gate → validator → final route。

| 输入 | 期望 action_type | 期望 final route |
|------|-----------------|-----------------|
| "批判看下这个 ADR" | consult_readonly | consult (pre-route interceptor) |
| "分析下是否认可" | consult_readonly | consult (pre-route interceptor) |
| "等我确认" | consult_readonly | consult (pre-route interceptor) |
| "这个方案有什么风险" | consult_readonly | consult (pre-route interceptor) |
| "加一个缓存功能" | modify_files / propose_plan | light_iterate (existing router fallback) |
| "实现 ADR-017" | propose_plan | workflow (existing router fallback) |

---

## 不做的事

- 不新建 LLM API client（runtime 不调 LLM）
- 不改 Router.classify() 签名
- 不在 host prompt 嵌入完整 schema（gate contract 动态返回）
- 不做完整 action system（只激活 `consult_readonly` pre-route 拦截）
- 不做 `action_audit.jsonl`（P1）
- 不建 `protocol_step3_schema_docs` / `runtime_handoff_slimming` / `action_audit_observability` 子方案包（仅在总纲 tasks 列为 follow-up）
- 不另建 legacy classifier cleanup 子方案包；legacy cleanup 由本方案包 P0-H 执行
- 不设计 candidate → accepted 的自动 knowledge promotion gate（样本不足，自动化只会固化偶然偏差）
- 不让 Validator 承担产物质量验证（质量验证归 CrossReview Verify-C，Validator 只做授权）
