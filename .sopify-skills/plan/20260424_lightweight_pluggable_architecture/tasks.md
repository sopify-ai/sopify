# Tasks: Sopify 总纲（已降级为历史证据源）

> **⚠️ 本文件已于 2026-05-01 降级。** Canonical 任务优先级见 `../../blueprint/tasks.md`。

## 子任务包索引

| 子任务包 | Phase 归属 | 状态 | 方案包路径 |
|---------|-----------|------|----------|
| `20260417_risk_engine_upgrade` | Phase 0.1 | 事件触发 P0；启动前按 ADR-017 重审 | `plan/20260417_risk_engine_upgrade/` |
| `20260417_ux_perception_tuning` | Phase 0.2 | 活跃 (B/C) | `plan/20260417_ux_perception_tuning/` |
| `20260418_cross_review_engine` | Phase 4 前置 | 已确认 | `plan/20260418_cross_review_engine/` |
| `20260416_blueprint_graphify_integration` | Phase 5 基础 | 基础集成活跃；Plugin 封装延后 | `plan/20260416_blueprint_graphify_integration/` |
| `20260428_action_proposal_boundary` | ADR-017 P0 thin slice | ✅ P0 完成（dogfood 通过） | `plan/20260428_action_proposal_boundary/` |
| `20260429_standard-archive-finalize-archive-checkpoint` | 显式主体与生命周期收敛 | **当前最高优先级 / 新建** | `plan/20260429_standard-archive-finalize-archive-checkpoint/` |
| `runtime_surface_cleanup` | Runtime 表层治理与删减 | 待触发；在 archive/existing-plan/checkpoint-local-actions 之后 | 暂不拆子包（先在总纲定义） |
| `20260429_legacy_feature_cleanup` | Legacy 清理 | 新建 | `plan/20260429_legacy_feature_cleanup/` |
| `20260429_host_prompt_governance` | Prompt 治理 | 新建 | `plan/20260429_host_prompt_governance/` |
| archived legacy host adapter | 多宿主扩展 | Sunset (ADR-018) | `history/2026-04/` |

## 旧总纲吸收记录

| 旧子 plan | 状态 | 吸收到 | 说明 |
|----------|------|-------|------|
| Plan H / B1 / A | ✅ 已归档 | — | contract 稳定性继续有效 |
| Plan D (文档) | 未启动 | Phase 6 | |
| Plan B2 (Ghost State) | ✅ 终结 | ADR-005 | Phase 1+2 自然解决 |
| Plan C (Side task) | ✅ 终结 | ADR-005 | Phase 2 自然解决 |
| Plan B3 (Ghost Knowledge) | 延后 | Phase 2 扩展 | |

---

## 执行路线

> **核心原则**：先验证价值，再决定建多少基础设施。
> **战略方向 (2026-04-26)**：Protocol-first / Runtime-optional。Protocol 提取不与任何 Phase 冲突，Protocol Step 1 为 P1（不抢 P0）。Phase 4a 兼做 Convention 模式首次验证。详见 design.md §1.2。
> **产品架构方向 (2026-04-27, ADR-020)**：Sopify = 轻量内核 + 可外部化组件生态。Core 只保留协议/状态/权限层；具有独立用户价值的分析/推理能力设计为可外部化组件，CrossReview 是已实现的参考范本。详见 D16。

### 三阶段总览

| 阶段 | 内容 | 时间窗口 |
|------|------|---------|
| **阶段 1 — 验证就绪** | Sopify 0.2-B/C + CR v0 → release gate → PyPI | CR `0.1.0a1` 已发布并 smoke 通过；Sopify 0.2-B/C 未完成 |
| **阶段 2 — 价值验证** | Phase 4a advisory + 3 项目 dogfood | 当前下一步 |
| **阶段 3 — 数据驱动** | advisory 够用 → 继续；不够用 → Phase 1-3 | dogfood 数据后 |

### 轻量化执行链（已确认）

> 目标：先删除不服务主线的维护面，再做小体验修正和协议澄清，最后用 CrossReview 真实 dogfood 决定是否需要新基础设施。
> 性质：排序护栏，不新增功能范围；不得被解释为提前启动 Validator / Runtime / bridge.py。

1. **显式主体与生命周期收敛（第一子切片）**：优先收敛 `archive/finalize` 语义、archive 所需显式主体解析、以及旧 finalize 绕行链路删除。该主题下的后续子方案包顺序固定为 `existing_plan_subject_binding` → `checkpoint_local_actions` → `runtime_surface_cleanup` → `host_prompt_governance`；在前两者稳定前，不进入 prompt 治理实现。
2. **Phase 0.2-B/C**：完成 router 精度修正与输出瘦身，只改 `router.py` / `output.py`，不改 `engine.py` 或机器契约；不得吸收 existing plan subject truth、checkpoint local action truth 或局部语境副作用授权问题。
3. **CrossReview Phase 4a**：以 advisory skill 接入 develop 后审查；`SKILL.md` 调用 CLI，不使用 `bridge.py` / `pipeline_hooks`。
4. **Protocol Step 1**：提取最小协议文档与 8-12 个行为契约 case；只写文档，不实现 validator / test runner。应以 archive/finalize 新现实与已稳定 contract 为输入，不提前固化旧 finalize 语义。
5. **ADR-018 Trae sunset 收口**：已实现的 retired host 清理改为文档与状态收口，不再占当前实现主序列。
6. **数据驱动后续**：Phase 4a dogfood 后再决定是否启动更广的 Protocol Validator、Action Schema 实现、Phase 1-3 或 Phase 4b。

---

### 当前活跃

**当前最高优先级：显式主体与生命周期收敛（第一子切片）**
- 子方案包：`20260429_standard-archive-finalize-archive-checkpoint/`
- 目标：把 `archive/finalize` 从活动 runtime 流中回收，收敛为面向显式主体的协议级归档操作。
- 范围：archive/finalize 新语义、archive subject contract、deterministic core check/apply、旧 finalize 绕行删除；validator 仅负责校验/授权与产出 artifacts，不负责解析业务对象；migration/repair 不在本包执行路径内。
- 前置关系：完成前，`20260429_host_prompt_governance` 不进入实现阶段；prompt 层不得继续围绕旧 finalize surface 做治理。
- 后续顺序：本子切片完成后，先开 `existing_plan_subject_binding`，再开 `checkpoint_local_actions`，然后进入 `runtime_surface_cleanup`，最后才允许进入 `host_prompt_governance`。
- 开包边界：`existing_plan_subject_binding` 负责先稳定“操作的是谁”；`checkpoint_local_actions` 负责在主体 truth 稳定后收敛 `continue / revise / cancel / inspect`；`runtime_surface_cleanup` 负责删除上述稳定 contract 已覆盖的旧 route / handoff / output / recovery / tests 表层结构；`host_prompt_governance` 只消费稳定 contract，不得反向充当 runtime truth 或 keyword patch。

**待触发：existing_plan_subject_binding（不先拆子包）**
- 优先级：高；紧随 `archive/finalize` 之后，先于 `checkpoint_local_actions`
- 启动条件：
  1. `archive/finalize` 已完成单一路由 cutover
  2. archive 所需显式主体 contract 已稳定，不再借旧 finalize active-flow
- 目标：统一 existing plan 的显式主体解析，先解决“操作的是谁”，再允许后续子切片处理动作层
- 范围：
  - 收敛 review / revise / execute / `~go plan` 对 existing plan 的主体绑定口径
  - 定义主体取证优先级：explicit plan reference → explicit self-reference → explicit new-plan intent → stable handoff/current plan evidence → explicit current-plan anchor
  - 对非锚定请求 + active/current plan 存在的场景，收敛到 `active_plan_binding_choice` 或等价 decision checkpoint
  - 对齐 `current_plan.path`、`current_run.plan_path`、`handoff.plan_path` 的主体含义，不再允许多份 truth 并存
- 非目标：
  - 不定义 `continue / revise / cancel / inspect` 的局部动作 contract
  - 不治理 prompt / output 展示层
  - 不扩 ActionProposal 通用 schema
  - 不处理 archive lifecycle 或 gate/preflight 架构
- 验收口径：
  - existing plan 请求的主体绑定有唯一 deterministic 结论，或显式停在 decision
  - 不再依赖 strict single-active-plan 的静默自动复用作为主路径
  - plan review / reuse 相关 tests 收敛为主体绑定 contract，而不是分散在 router phrasing 和 engine fallback 中

**待触发：checkpoint_local_actions（不先拆子包）**
- 优先级：高；在 `existing_plan_subject_binding` 之后，先于 `runtime_surface_cleanup`
- 启动条件：`existing_plan_subject_binding` 已稳定 existing plan subject truth
- 目标：只收敛 `continue / revise / cancel / inspect` 的局部动作 contract，不再同时猜主体
- 约束：动作层只消费已绑定主体；不得回头吸收主体歧义问题

**待触发：runtime_surface_cleanup（不先拆子包）**
- 优先级：高；仅次于 `archive/finalize`、`existing_plan_subject_binding`、`checkpoint_local_actions`
- 启动条件：
  1. `archive/finalize` 已完成单一路由 cutover，不再以旧 `finalize_active` 作为主链路事实
  2. `existing_plan_subject_binding` 已稳定 existing plan 的显式主体解析
  3. `checkpoint_local_actions` 已稳定 `continue / revise / cancel / inspect` 的局部动作 contract
- 目标：基于已稳定语义，对 runtime 表层做一轮集中治理和删减，删除旧双轨、旧兼容投影和只服务旧语义的测试矩阵，降低 machine truth 漂移面
- 范围：
  - 清理旧 route / alias / reason phrasing / phase label 特判
  - 清理 handoff / output / replay 中的旧兼容投影
  - 清理 failure recovery / deterministic guard / decision tables 中只服务旧语义的分支
  - 清理 tests 中只验证旧别名、旧 reason code、旧 surface 的断言
  - 回写总纲 / blueprint / plan 文档，确保命名与 machine contract 一致
- 非目标：
  - 不新增 checkpoint type
  - 不扩 ActionProposal schema
  - 不重做 gate / preflight / workspace bootstrap 架构
  - 不做 runtime optionalization / engine 拆分 / validator 独立交付
  - 不用 prompt workaround 替代 machine truth 收敛
- 验收口径：
  - 旧概念引用数下降
  - 旧 route 分支和兼容投影数量下降
  - tests 从 legacy surface matrix 收敛为 contract tests + 关键回归
  - 不引入新的 runtime truth source 或新的长期兼容 alias

**ADR-018 Trae cleanup（已实现，待文档收口）**
- 状态说明：retired host surface 已完成 sunset 与归档，当前剩余事项以总纲/README/验证口径收口为主，不再作为当前实现主任务。
- 收口范围：确认总纲、背景、设计、CHANGELOG 和验证标准中的 sunset 口径一致。
- 约束：不重新打开 retired host 实现面，不影响当前 archive/lifecycle 第一子切片。

**Phase 0.2-B: Router 精度修正**
- [ ] 修正 `_is_consultation()` 问句+动作词判断
- [ ] 修正 `_estimate_complexity()` 短请求降级
- 改动 `router.py` (~15行)，不改 engine.py
- 边界：不得把 existing plan subject 解析、checkpoint local actions、`archive_plan`/`checkpoint_response` 授权、或局部语境副作用保护塞回 router patch
- 验证：全量测试通过，路由行为变更逐条确认

**Phase 0.2-C: 输出瘦身**
- [ ] 精简 consult/quick_fix 调试信息为面向用户的提示
- 改动 `output.py`，不改机器契约
- 边界：只改展示，不改 handoff truth、checkpoint 语义、ActionProposal/Validator 授权边界
- 验证：全量测试通过

> 详细设计见子任务包 `20260417_ux_perception_tuning/design.md`

**ADR-017 P0: ActionProposal Boundary** `当前最高痛点之一；已完成 thin slice，后续以清理为主`
- 子方案包：`20260428_action_proposal_boundary/`
- 目标：建立 Action/Effect Boundary，P0 先用 `consult_readonly` 解决 no-write 局部语境；方案包误建是当前最高频症状。
- 体量：~200 行新增 + ~30 行修改，不改 router 签名和 52 个现有测试
- 与 Phase 0.2-B 关系：P0 结构性解决 consult 误路由，0.2-B 中 `_is_consultation()` 修复在 P0-H cleanup 时一并退出；`_estimate_complexity()` 短请求降级对非 consult 场景仍有效，优先级降低

---

### 待触发

**Phase 0.1: Action/Risk Boundary v1** `🔶 事件触发型 P0`
- 触发条件：出现高风险误放行 (force_push / credential_exposure / production_deploy 等)
- 内容：Action/Risk Boundary v1；RiskRule dataclass + scan_scope + cacheable 只保留为 hard-risk detector，不扩用户话术白名单
- 约束：启动前必须按 ADR-017 重审 `20260417_risk_engine_upgrade/`，风险判断对象优先为 action / side_effect / tool input / diff / plan task
- 若事件早于 Protocol Step 3，最小审核标准为：① 不以扩用户话术白名单为主方案；② 必须评估 action/side_effect/tool input/diff/plan task 至少一类机器事实；③ 缺机器事实、缺 side_effect 或状态不匹配时 fail-close
- 详见子任务包 `20260417_risk_engine_upgrade/`

**Phase 4a: CrossReview Advisory Plugin + Convention 模式验证** `草拟已完成；E2E + 3 项目 dogfood 待执行`
- [x] T4a.1 创建 `.agents/skills/cross-review/` 目录 (SKILL.md + skill.yaml)
- [x] T4a.2 编写 SKILL.md：触发时机 (develop 完成后) + CLI 调用步骤 (默认 `pack -> render-prompt -> 宿主隔离审查 -> ingest --format human`，`verify --diff --format human` 仅为 standalone fallback) + 4 种 verdict 处理
- [x] T4a.3 编写 skill.yaml：advisory mode, triggers=["review","cross-review","verify","post_develop"], host_support=["*"]
- [ ] T4a.4 端到端验证 + 3 项目 dogfood
- 草拟门槛：已满足，CR v0 CLI 可用，Sopify 宿主消费副本已落地。
- E2E/dogfood 门槛：已满足，CR v0 release gate 通过，PyPI `crossreview==0.1.0a1` 可安装，host-integrated CLI (`pack` / `render-prompt` / `ingest --format human`) smoke 通过；`verify --diff --format human` 仅作为 standalone fallback 校验
- 验证：LLM 读 SKILL.md 后自主调用 CLI；至少 3 个真实项目、至少 2 个 valid issue；误报不阻塞主流程

**Protocol Step 2: Protocol validator CLI** `待需求信号确认`
- check / repair / archive，只读优先
- 触发条件（满足其一）：
  1. Protocol Step 1 完成 + 至少 2 次实际 plan/state 校验需求出现（手动修正 / 状态损坏 / 迁移校验）
  2. Phase 4a Convention 模式验证暴露系统性 SKILL.md 偏离（LLM 不按表单操作需事后校验）
  3. 新宿主（QCoder / Copilot）接入时需要 Convention 模式支持
- 约束：不影响 Phase 0.2-B/C 和 CrossReview v0 的 P0 工作
- 体量 ~2K 行新代码。分发形态待 Step 1 稳定后定。

**Protocol Step 3: Action Schema Boundary / SKILL.md 表单式增强** `P0 thin slice 已提升；完整 schema 仍为 P1`

**P0 thin slice（子方案包 `20260428_action_proposal_boundary/`）：**
- [ ] 定义 ActionProposal schema（6 个 action_type enum + 5 个 side_effect types；P0 只对 consult_readonly 做 route override，side-effecting action 做最小 evidence proof 授权但不接管路由）
- [ ] 实现 `action_intent.py`：ActionProposal + ValidationContext + ValidationDecision + Validator + deterministic fallback（不带 LLM API）；P0 4 路分支：consult_readonly → authorize/consult；side-effecting + evidence 通过 → authorize/null；evidence 不足 → downgrade consult_readonly；unknown → fallback_router
- [ ] Gate 接收 `--action-proposal-json`；new host 无 proposal 时返回 gate retry contract
- [ ] Engine pre-route interceptor：authorize + route_override=consult → consult route；authorize + route_override=null → Router 继续；downgrade → consult route；fallback_router → Router 继续
- [ ] `decision_tables.yaml` 补 `confirm_plan_package` 的 `switch_to_consult_readonly` effect row
- [ ] Host prompt 加一条规则（schema 由 gate 动态返回，不嵌 prompt）
- [ ] Validator deterministic tests + 保留现有 router 52 个测试
- [ ] P0-H：P0-G 测试通过 + 1 轮 dogfood 后，按 ADR-018 清理被 ActionProposal 覆盖的 legacy classifier paths
- 约束：P0 只激活 `consult_readonly` pre-route 拦截；Router 签名不改；普通命令前缀请求不默认经过 ActionProposal，但 `~go finalize` 等 side-effecting alias 可由后续子切片映射成 action-specific proposal
- 标注：现有 `analysis_only_no_write_brake`、`plan_meta_review`、`analyze_challenge`、`explain_only_override` 为 legacy compatibility path，P0-G 测试通过 + 1 轮 dogfood 后由 P0-H 清理

**P1 完整 schema（原 Protocol Step 3 范围）：**
- [ ] 为 reserved actions 逐步激活完整 schema（`inspect_checkpoint` / `confirm_plan_package` / `revise_plan_proposal` 等）
- [ ] 为每个 action 标注 `side_effect`、必填 id、允许 stage、允许 `required_host_action`
- [ ] 更新 SKILL.md 表单式编排，使用 `[ACTION: ...]` 输出结构化 action proposal
- [ ] 明确 fail-close 策略：缺字段、低置信度、歧义或机器事实不匹配时降级 inspect/ask 或拒绝写入
- [ ] 定义 `action_schema_version` / `supported_actions` capability（区分 active / reserved），供未来 bridge.py 或宿主查询 Core 支持面
- [ ] 定义最小 `action_audit` 事件字段；暂不展开完整 `action_audit.jsonl` schema
- [ ] 复核 Phase 0.1 风险检测、checkpoint 恢复、plugin verdict 映射是否只评估 action/payload/side_effect，不评估用户话术白名单
- 优先级：P1 / Protocol Step 3。完整 action system 不阻塞 P0 thin slice。

**P1 follow-up（P0 thin slice 验证后）：**
- `protocol_step3_schema_docs`：将 ActionProposal schema 写入 protocol 文档层（ADR-016 Layer 1）
- `runtime_handoff_slimming`：精简 handoff artifacts
- `action_audit_observability`：`action_audit.jsonl` 事件可观测性
- `runtime_surface_cleanup`：在 `archive/finalize`、`existing_plan_subject_binding`、`checkpoint_local_actions` 稳定后启动；负责删 runtime 表层旧语义，不扩协议面。
- `host_prompt_governance`：后续收口包。前置依赖：archive/finalize 新 contract 稳定，且 `existing_plan_subject_binding`、`checkpoint_local_actions`、`runtime_surface_cleanup` 已完成；在此之前不对旧 finalize/runtime surface 做 prompt 治理实现，也不允许用 prompt workaround 代替 machine truth 收敛。

---

### P1 (不抢 P0，与 Phase 0.2-B/C 并行)

**Protocol Step 1: 提取 Protocol 文档** `P1 — ADR-016 顶层战略基础`
- [ ] plan schema（目录约定、文件命名、background/design/tasks 结构）
- [ ] state schema（current_handoff.json / current_run.json / gate_receipt 契约字段）
- [ ] lifecycle 约定（plan → history 生命周期、归档规则、blueprint 更新触发）
- [ ] SKILL.md 编排规范（表单式格式、`[ACTION:]` 模式、分支结构、弱模型下界要求）
- [ ] checkpoint schema（4 种内置 checkpoint 的字段约定与 side_effect 标注）
- [ ] 最小行为契约示例（8-12 个 protocol examples，非执行性）：checkpoint resume、handoff action、plan proposal、execution confirm、no-write consult、history archive 等协议语义
- [ ] scripts/*.py 一等公民约定：每个确定性脚本须满足 stdin/stdout/JSON + exit code 接口，可在无 runtime 下直接 shell 调用（参考 `score_requirement.py`、`extract_pending_tasks.py`）
- 产出：docs/protocol/ 或 .sopify-skills/protocol/
- 纯文档，0 行代码变更。不与任何 Phase 冲突；只列契约，不实现 validator / test runner。
- **三层架构约束**：Protocol 文档仅约束 Layer 1（协议语义）；Layer 2 Validator 是 Step 2 的事；Layer 3 Runtime 是参考实现，不是接入前提条件。文档不得把"调用 engine.py"写成必须步骤。
- 验证：外部读者（新 host）只读协议文档，应能回答"如何在无 runtime 下操作 `.sopify-skills/` 目录"。至少 1 个非 Sopify 维护者验证可理解性。
- 不抢 P0：Phase 0.2-B/C 和 CR gate 优先

---

### 延后 (数据驱动后决策)

> 以下 Phase 当前延后。激活时展开为独立子任务包或在已有子任务包中扩展。不在本文档展开实现步骤。

| Phase | 内容摘要 | 激活条件 |
|-------|---------|---------|
| 0.2-A | Blueprint 可见化 (handoff 注入 blueprint 摘要) | Phase 2 启动时 |
| 0.3 | State Write Classification (标注 engine.py 59 次 StateStore 调用) | Phase 1 启动前 |
| 1 | Engine 拆分 (engine.py → checkpoint_engine + plan_engine + state_ops) | 阶段 2 数据证明 advisory 不够用 |
| 2 | Skill 自包含 (SKILL.md 编排指令增强) — 与 Protocol Step 3 / ADR-017 合并 | Phase 1 完成后 |
| 3 | Runtime hook/bridge 接口 (skill.yaml v2 + bridge.py 标准 + pipeline hooks) | Phase 1 完成后，可与 Phase 2 并行 |
| 5 | Graphify Advisory Skill（Sopify 侧插件封装；区别于 GraphifyEnhancer 知识资产生成，后者属知识工程 P2） | Phase 3 完成后；当前仅基础集成活跃 |
| 6 | 文档与示例 (plugin 开发指南) — 吸收旧 Plan D | 跟随各 Phase |

### 冻结

**Phase 4b: CR Runtime 模式** `🧊 冻结，不进入 0-6 个月承诺`
- 升级 advisory → runtime (bridge.py + pipeline_hooks.after_develop)
- 启动条件：Phase 3 就绪 + Phase 4a 价值验证 + 3 个 dogfood 数据证明 advisory 不够用

---

## 依赖关系

```
当前活跃                    P0 thin slice
  Phase 0.2-B/C ──┐        ADR-017 Action/Effect Boundary
                   │          └─ 20260428_action_proposal_boundary
待触发              │
  Phase 0.1 (事件) │        P1 (不抢 P0)
                   │        Protocol Step 1 (纯文档, ADR-016 基础)
  CR v0 release ───┼──→ Phase 4a (advisory + Convention 验证) ──→ 3 项目 dogfood
   gate 通过        │                                               │
                   │                                      数据驱动决策 ↓
  Protocol Step 2 ─┤ (Step 1 完成 + 信号触发，含 Phase 4a 验证数据)
  Protocol Step 3 ─┤ (ADR-017 完整 schema；P0 thin slice 验证后)
                   │
延后                │              ┌── advisory 够用 → 继续
  Phase 0.3 ───→ Phase 1 ──→ Phase 2+3 ──→ Phase 4b (冻结中)
                                    │            └── Phase 5
                                    │
                              Phase 6 (跟随)
```

**CrossReview 交叉依赖：**
CR v0 release gate 通过 → Sopify Phase 4a → dogfood 数据 → 决定 Phase 1-3 / Phase 4b

---

## 多宿主扩展

不阻塞 Phase 0-6 主线。Phase 3 完成后需在 ≥2 宿主上验证 `host_support`。

| 宿主 | 状态 | 子任务包 |
|------|------|---------|
| Claude Code | ✅ 深度验证 | — |
| Codex | ✅ 深度验证 | — |
| Retired legacy host | 🔴 Sunset (ADR-018) | history/ 归档 |
| QCoder | 📋 待调研 | 调研后独立立项 |
| GitHub Copilot | 📋 待调研 | 调研后独立立项 |

新宿主适配参考三层抽象 (HostAdapter + HostCapability + HostRegistration)，见 design.md §5。retired legacy host 适配经验保留在 history/ 归档中供参考。

---

## P1/P2 Host Research（不阻塞主线）

### T-host-research-1：QCoder CLI Host Capability Research

- **行动：** 调研 QCoder CLI 的全局配置目录、规则注入方式、技能发现路径、命令触发方式和文件协议读写能力
- **产出：** host capability matrix；是否值得独立立项的建议
- **依赖：** 无
- **验证：** 不进入 release gate；只要求调研结论可复核

### T-host-research-2：GitHub Copilot CLI Host Capability Research

- **行动：** 调研 Copilot CLI 的配置入口、规则注入能力、命令触发方式、隔离上下文能力和 `.sopify-skills/` 文件协议适配成本
- **产出：** host capability matrix；是否值得独立立项的建议
- **依赖：** 无
- **验证：** 不进入 release gate；只要求调研结论可复核

---

## P1 Legacy Cleanup (ADR-018)

> 不阻塞 Phase 0.2-B/C 或 CR P0。随 runtime/host 改造同步推进。

### T-cleanup-1：Runtime Entrypoint Inventory

- **行动：** 输出 entrypoint ownership table（canonical / debug / old-host / no-callsite）
- **产出：** 本文件"多宿主扩展"章节更新，或独立 entrypoint-inventory.md
- **依赖：** 无
- **估计：** 0.5 天

### T-cleanup-2：Legacy Host Surface Retirement

- **行动（顺序遵循 ADR-018 §8 删除顺序）：**
  1. 从 `installer/hosts/__init__.py` 注册表中移除 retired host（CI dry-run）
  2. 移除 installer / status / release hook 中 retired host 测试用例
  3. 更新 README link、skills sync、version consistency、sync 和 pre-commit 脚本，停止扫描 retired host prompt mirror
  4. 移除 retired host adapter 实现
  5. 移除 retired host prompt mirror
  6. 归档 retired host adapter plan → `.sopify-skills/history/2026-04/`
  7. 编辑 README.md / README.zh-CN.md / CONTRIBUTING.md / CONTRIBUTING_CN.md 移除 retired host 引用
  8. CHANGELOG.md 保留历史记录，只在最新版本添加 sunset 说明
- **依赖：** T-cleanup-1
- **验证：** CI 全量通过；retired host literal 仅返回 CHANGELOG 和 history/ 中的归档记录
- **估计：** 1 天

### T-cleanup-3：总纲与文档同步

- **行动：**
  1. 更新总纲 design.md / tasks.md / background.md 中的宿主列表（确认 sunset 口径一致）
  2. 确认 CI 全量通过，retired host literal 仅返回 CHANGELOG 和 history/
- **依赖：** T-cleanup-2
- **验证：** CI 全量通过，retired host literal 仅返回 CHANGELOG 和 history/ 中的归档记录
- **估计：** 0.5 天

### T-cleanup-4：install-sopify.sh 评估

- **行动：** 评估 `scripts/install-sopify.sh` 是否被 `scripts/install_sopify.py` 完全替代；如果是则 sunset → removed
- **依赖：** T-cleanup-1
- **估计：** 0.5 天

---

## 优先级约束

P0 任务必须增强至少一项核心能力：adaptive route/workflow、state protocol、handoff/checkpoint contract、quality gate、plugin permission、plan-blueprint-history-review 资产链，或解除关键 UX 阻塞。纯 prompt/output 优化最高 P1。

**Complexity Budget Guard**（见 design.md §9）：新增 protocol 字段、状态文件、runtime helper、host action、系统提示规则或 ADR，必须同时说明替代了什么、能否删旧、是否增加 complexity debt。不能说明的默认不进入 P0/P1 主线。

**外部思想吸收门禁**（见 design.md §1.3）：
- 新 Phase / 子任务包 / schema 字段 / checkpoint 子类型 / state 文件 / runtime helper / plugin 能力，必须先标注 `Core Protocol` / `Curated Plugin` / `Inspiration Only`
- 进入 Core 时必须说明强化哪项核心能力，并说明替换哪个旧概念；不能只新增概念
- 能独立为 plugin 的能力默认留在 plugin；Sopify 只定义接入点、产物归档和 checkpoint 映射
- 未完成归类和准入说明的新增项，默认不进入执行队列

---

## 验证标准

| 范围 | 标准 |
|------|------|
| Phase 0.2-B/C | 全量测试通过，路由行为变更逐条确认 |
| Phase 0.1 | 按 ADR-017 重审后 execution_gate / action-risk policy 全量通过，现有 hard-risk 行为不变 |
| Phase 4a | E2E 跑通 + 3 项目 dogfood + ≥2 valid issue + 误报不阻塞 |
| Phase 1 | pytest 全量通过，engine.py ≤600 行，行为等价 |
| Phase 2 | 3 种复杂度工作流手动验证 |
| Phase 3 | v2 解析无报错，v1 兼容，host_support 多宿主验证（Claude + Codex baseline） |
| Phase 4b | 冻结，仅在启动条件满足后评审 |
| ADR-018 cleanup | legacy host sunset 完成（retired host literal 仅返回 CHANGELOG + history/）|
| 多宿主 | QCoder/Copilot 完成调研 |

---

## 待确认与讨论

### Open

| # | 讨论项 | 何时 | 依赖 |
|---|--------|------|------|
| 2 | CR fixture provenance 复核 | CR release gate 前 | 以 CR 总纲事实为准 |
| 3 | Phase 4b 启动时机 | Phase 3 临近 + 4a 有价值 | Phase 3 + 4a + CR gate 三条件 |
| 4 | Plan B3 是否被 Phase 2 覆盖 | Phase 2 完成后 | Phase 2 实际效果 |
| 5 | QCoder / Copilot 调研 | 按需 | 无硬性阻塞 |

### 已收口

| 决策 | 内容 | 记录 |
|------|------|------|
| D1 | 策展集成模型 | ADR-008 |
| D2 | pipeline_hooks 默认关闭 | ADR-009 |
| D3 | Ghost 路线终结 | ADR-005 |
| D4 | 只用内置 4 种 checkpoint | ADR-010 |
| D5 | verdict→checkpoint 映射 + 2 轮限制 | ADR-011 |
| D6 | Phase 4 分阶段 (advisory → runtime) | design.md §3.2 |
| D7 | Protocol-first 战略 | ADR-016 |
| D8 | 三份总纲 Source of Truth 划分 | Sopify→Sopify 总纲, CR→CR 总纲, 生态→跨项目排序+依赖图 |
| D9 | 知识工程优先级 | 降为 P2/P3，不作为 CR/Sopify 任何阶段前置；blueprint/knowledge/ 随 P2 启动再定 |
| D10 | Phase 4a scope | 确认既有共识并于 2026-04-28 修订执行路径：advisory only，无 bridge.py/pipeline_hooks；默认 host-integrated (`pack -> render-prompt -> 宿主隔离审查 -> ingest --format human`)，`verify --diff` 仅为 standalone fallback |
| D11 | GraphifyEnhancer vs Graphify Advisory Skill | 两个独立概念：前者知识资产生成（知识工程 P2），后者 Sopify Phase 5 用户插件 |
| D12 | Action Schema Boundary | ADR-017：不维护用户话术白名单；LLM 只提议结构化 action，Core/Validator 基于机器事实、side_effect 和风险策略授权。Phase 0.2-B/C 的 router/output 修正不属于 ADR-017 实现；任何 action schema / checkpoint / plugin verdict 映射改动必须独立立项或修订 ADR |
| D13 | 遗留 surface 退出路径 | ADR-018：改造时必须声明退出路径；frozen surface 不计入 release gate；Trae CN 归档后不作为新宿主示例 |
| D14 | 分发架构：thin-stub + 集中管理 | ADR-019：项目本地零拷贝，全局 payload 单点管理版本与更新；后续 ADR 接入不得引入本地冷拷贝 |
| D15 | Phase 0.2-B/C 不触及 V2 classifier | 修正范围锁定 `_is_consultation()` 和 `_estimate_complexity()`；新增 `_STRONG_INTERROGATIVE_PREFIXES` 子集替代宽泛前缀覆盖动作词逻辑；`_SHORT_REQUEST_THRESHOLD = 80`；不改 engine.py、V2 classifier、handoff 契约 |
| D16 | Sopify 轻量内核 + 可外部化组件生态 | ADR-020：Sopify Core 锁定为协议/状态/权限层（checkpoint 生命周期、handoff 契约、plan/state/history 协议、plugin manifest 接入规则、blueprint 资产链）；分析/推理能力按"可外部化组件"模式设计，不塞进 Core。参考范本：CrossReview（独立 CLI + PyPI + eval，Sopify 只定义调用时机和 verdict→checkpoint 映射）。**外部化判定条件（三者同时满足）**：① ≥2 个非 Sopify 独立消费方；② 稳定 JSON contract（顶层字段只用通用业务概念，Sopify 内部状态只作 `context` 附加字段）；③ 可独立 eval（无需 Sopify 运行时）。**当前组件候选状态**：CrossReview ✅ 已外部化；Action Proposal Engine / Graphify / evaluator / trace-observability 为"设计时预留外部化接口，未外部化"——不提前建项目，等第一个非 Sopify 消费方出现后再立项。|
| D17 | builtin skill 产品化边界 | `runtime/builtin_skill_packages/` 暂不整体拆分；短期保持 Sopify 官方 builtin workflow pack，保障开箱即用。未来仅当满足 D16 外部化三条件时，允许单个能力毕业为独立产品或协议包：analyze/design/develop 可成为官方 Protocol workflow pack，kb/templates 随 Protocol/Validator 分发，model-compare 可毕业为模型对比/eval harness，workflow-learning 可毕业为 trace/replay/decision explanation plugin。该记录只作未来形态说明，不新增 P0/P1，不改变当前优先级。|
