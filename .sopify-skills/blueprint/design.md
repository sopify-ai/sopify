# 蓝图架构与契约

本文定位: Sopify 的架构分层、核心契约、削减目标与硬约束。这是宿主与 runtime 的共同设计基线。

## 产品定位 (ADR-013)

Sopify 的 durable core 是跨宿主 AI 工作流的 **证据与授权层**。它不负责生成代码或编排 agent，而是把外部生产、验证、知识工具的结果收敛成可恢复、可审计、可授权的机器事实。Sopify 官方在 core 之上提供一个轻量、可插拔、收敛式的 workflow，并以 blueprint 作为默认的长期知识基线。

| 层级 | 表述 |
|------|------|
| 用户层 | 任务可恢复、决策可追踪、产出质量可验证，跨宿主无缝接力 |
| 产品层 | Core: 证据规范 + 授权判定 + 收据 + 接力 + archive truth；Default Workflow: 以 blueprint 为基线的收敛式工作流 |
| 架构层 | Evidence & authorization layer + official workflow anchored on blueprint as long-term knowledge baseline |

## 产品分层

| 产品层 | 职责 | 映射到实现 |
|-------|------|-----------|
| **Core** | 证据规范、授权判定、收据生成、handoff 接力、archive truth | Protocol + Validator |
| **Default Workflow** | 以 blueprint 为基线的分析、标准方案包生成、checkpoint 讨论（含跨宿主审查）、归档回写 | Protocol conventions + Validator policies + 可选 Runtime 编排 |
| **Plugins / Skills** | 生产增强、验证增强、知识增强（cross-review, graphify 等） | Integration Contract (protocol.md §6) + Validator admission |

**层间规则：**

- **Core promotion rule**：只有影响跨宿主互操作、receipt validity、archive admissibility 的契约才能进 Core
- **Default Workflow 边界**：消费 Core 契约，不自行定义授权语义；是 Core 之上的 opinionated happy path
- **Plugin trust rule**：插件输出进入 receipt/handoff/blueprint 前，必须经过 Validator 或 knowledge_sync admission gate

**竞品边界：**

| 类别 | 代表产品 | Sopify 的边界 |
|------|---------|-------------|
| 宿主 / IDE（内建工作流状态） | Kiro (AWS)、Claude Code、Codex、Cursor | Sopify 不做模型推理、不做代码执行；宿主原生 spec/checkpoint 是最大吸收风险 |
| Spec / artifact 系统 | OpenSpec (Fission-AI)、Spec Kit (GitHub) | Sopify 不做 spec 方法论、不做 artifact 模板管理；与 spec 系统可互补 |
| Agent runtime / platform | OpenClaw、Hermes Agent | Sopify 不做 agent orchestration、不做 skill routing/gateway；runtime 层有重叠需关注 |
| Skills / methodology 生态 | Superpowers | Sopify 不做技能市场、不做方法论教学；Superpowers 是 agentic skills + methodology |

**Sopify 的不可替代面**：不在于某一项功能，而在于 **可验证的便携式证据与授权语义**——fail-closed 授权回执、跨宿主可恢复状态、可审计项目记忆、独立 validator/compliance 套件。这些能力的组合是单一宿主难以完整替代的。

**竞品吸收应对策略：**

- 宿主吸收执行编排 → Sopify 退守 protocol + validator + compliance
- Spec 工具吸收 checkpoint → Sopify 强调跨宿主连续性 + receipt authority
- Agent 框架吸收 state → Sopify 做 interop 标准层 / 可携带协议

**生存性测试：** 2027 年宿主原生支持 plan/checkpoint/multi-agent 后，Sopify 仍必须保留：项目级资产沉淀、跨宿主连续工作、可审计决策链、独立质量闭环。如果以上任一能力被宿主完全替代且无跨宿主可携带性需求，该能力应 sunset。

## 底层哲学

> 以下 3 条哲学是 ADR-013/016/017 的共同根基。所有设计决策可从中推导。

### 哲学 1: Convergence-first (收敛优先)

**微观（单任务）是收敛链**：produce → verify → authorize → settle。目标是按风险逐步降低不确定性，收敛到"可授权阈值"即停止——不以"更完整/更优雅"为默认继续条件。

- produce: 外部生产器（LLM/宿主）输出候选事实
- verify: 外部验证器（cross-review 等）提供独立证据
- authorize: Sopify Validator 判定是否可执行/可归档
- settle: 沉淀为 receipt / handoff / history

**宏观（跨任务）是知识飞轮**：每次 settle 沉淀的 machine truth 提高下一条收敛链的起点，降低验证成本并缩短授权路径。

**停点原则**：达到可授权阈值后即停止。不是每个任务都需要完整的设计 + 交叉审查 + 知识提炼全套流程；按风险选择验证深度。

**沉淀准入门槛**：只有同时满足以下条件的结论才进入长期知识层（blueprint / history）：
- 跨任务可复用
- 影响未来授权或验证基线
- 已经稳定
- 可 machine-readably 引用

**方案级收敛（Default Workflow 策略）**：收敛链不仅适用于单任务执行，也适用于方案讨论阶段。跨宿主审查遵循收敛链语义：

- 方案状态流转：`draft → under_review → [accept → approved | revise → draft | blocked → escalate]`
- 停点条件：至少一轮审查无阻塞性 finding 且返回 accept；或用户显式 override；或审查轮数达到上限（默认 3 轮）
- 多审查者冲突：有任一 `blocked` 则整体 blocked；`accept` + `revise` 混合时取 revise
- 机器契约（subject identity / verdict shape）见 `protocol.md §7`；策略性规则（轮数上限、severity 判定）归 Default Workflow，不进 Core

### 哲学 2: Wire-composable (线可组合)

独立收敛链通过**线**（机器契约）组合。Sopify 是串联收敛链的证据与授权线——负责证据规范、授权判定和收据生成，不做生产/验证/知识处理节点本身。

线独立于 session / model / host：同一逻辑 session（`session_id`）内，handoff + run state 让中断后精确继续；跨 session 接力需显式 claim/receipt，不允许静默推进旧 session 的 pending checkpoint。

| 显隐 | 实现 | 适用 |
|------|------|------|
| 显式 (Runtime) | gate → handoff → checkpoint JSON | 确定性门控 / 审计 |
| 隐式 (Convention) | SKILL.md + 目录约定 | 轻量任务 / 新宿主 |

外部能力通过 integration contract 接入（见 `protocol.md` Integration Contract 小节）。

### 哲学 3: Surface-shared (面共享)

所有线共享一个知识面（blueprint / history）。知识面是跨 session/model/host 的共享工作记忆。

在多模型、多云、多宿主逐步解耦的环境下，Surface-shared 的目标是让项目连续性绑定到共享文件协议，而不是绑定到某个模型、云或聊天上下文。任意 host/model 只要正确消费 blueprint/history 与 handoff 暴露的机器事实，就能基于同一项目记忆继续工作；但推进 pending checkpoint 或产生副作用仍必须回到 Wire-composable 的机器接力与 Validator 授权。

**Sopify 的不可替代性 = 线 + 面的组合。** Protocol 定义证据规范，Validator 定义授权判定，Runtime 是可选的"加固线"。

## 三层定位 (ADR-016: Protocol-first / Runtime-optional)

> **迁移现状（2026-05）**：Protocol-first 是已确认的架构方向。`blueprint/protocol.md` v0 已落地，定义了不依赖 runtime 也成立的最小可携带协议。当前 runtime（~29K 行 / 66 模块）仍是最完整的参考实现，protocol.md 是协议层的规范起点。
>
> **Blueprint Truth Cutover 原则**：Blueprint 是产品合法边界和预算的唯一定义源。Runtime 定义 how it currently runs，blueprint 定义 what is valid。当 runtime 与 blueprint 冲突时，以 blueprint 为准——runtime 中超出 canonical 预算的面是待迁移的遗留面，不是产品真相。Runtime 在架构上是参考实现和迁移层，不是 truth source。当前产品尚处于早期阶段，无外部消费者依赖和生产级兼容承诺，处于可激进收敛的窗口期。
>
> **协议规范**：`blueprint/protocol.md` 定义最小可携带协议（目录结构、必备文件/字段、宿主最小义务、生命周期样例）。本节定义三层架构分工，protocol.md 定义最小合规下界。

| 层 | 内容 | 体量目标 | 可替代性 |
|----|------|---------|---------|
| **Protocol** | `.sopify-skills/` 目录约定、schema、SKILL.md 编排 | 纯文档 | 不可替代 |
| **Validator** | ActionProposal 校验、状态迁移校验、archive check/apply | ~2K 行 | 独立交付 |
| **Runtime** | gate / router / engine / handoff 状态机 | 目标 <20K 行（当前 ~29K） | 可选增强 / 参考实现 |

**Convention 模式 (下界)**: LLM 读 SKILL.md → 自行推进 → Validator 事后校验（protocol acceptance / receipt authority）。
**Runtime 模式 (上界)**: 完整 runtime 控制状态迁移，Validator 是 pre-write authorizer。

"Validator 是唯一授权者"在两种模式下含义不同：Runtime 模式是写前授权；Convention 模式是事后合规校验与 receipt 签发。两者共享同一校验逻辑，但触发时机和阻断语义不同。

模式选择维度是**过程要求**，不是模型强弱。

## 核心管线 (ADR-017: Action/Effect Boundary)

```
用户自然语言
  → Host LLM 映射为 ActionProposal
  → Validator 校验 schema + facts + side effect → ValidationDecision
  → Deterministic action 执行
  → Handoff / Receipt 暴露机器事实
```

**不变量：**

- Host LLM 只是 proposal source，**不是 authorizer**
- Validator 是**唯一授权者**：判断当前 context 下 action/side effect 是否允许
- Validator **不是 executor**：不做 plan materialization、文件迁移、状态推进
- 执行层**不理解人话**：只按结构化字段和文件事实做事
- `fallback_router` 只是临时兼容出口，应单调收缩

### Subject Identity（主体身份）

ActionProposal 管线中，每个 side-effecting action 必须携带明确的 subject identity——"操作的是谁"。Subject identity 是 protocol 层契约，validator 和 runtime 都是消费方。

- `subject_type`：被操作对象类型（`plan` / `code` / `architecture`）
- `subject_ref`：对象定位（如 `plan/20260501_dark_mode/plan.md`）
- `revision_digest`：版本标识（git SHA 或内容 hash），保证操作绑定到确定性快照

主体取证优先级：explicit reference → self-reference → new-plan intent → stable handoff evidence → current-plan anchor。

> **规范来源**：`protocol.md` §7 定义 wire contract；`tasks.md` P1 定义升格路线。

### ExecutionAuthorizationReceipt（授权脊柱）

执行授权不再是 checkpoint，而是机器授权事实。这是 subject identity 绑定后的直系产物——先确定"操作的是谁"，再回答"这次操作是否被授权"。

**不变量：** 绑定 plan identity + plan revision + execution gate result + action proposal identity + authorization source。使用 canonical JSON + sha256 生成 fingerprint。Plan 变更后 receipt 自动失效。Fail-closed：任一字段不匹配则拒绝执行。

具体字段定义见 ADR-017。操作化路线见 `tasks.md` P1.5。

## Runtime 五层架构（参考实现）

> 以下五层是当前 Python runtime 的参考实现架构。Protocol 本体（目录约定、schema、Validator 契约）不依赖此五层也成立。宿主可通过 Convention 模式直接消费 Protocol + Validator，不必实现完整 runtime。

### 1. Ingress Layer | 入口守卫层

回答：当前请求能不能进入 runtime、带什么最小上下文进入。不负责路由或意图解释。

### 2. State Resolution Layer | 状态真相层

收敛"现在该信哪份状态"。Loader + Resolver 生成唯一 `ContextResolvedSnapshot`，下游只消费 snapshot，不散读 JSON。

### 3. Routing & Checkpoint Layer | 路由与停点层

基于 snapshot 决定：直接执行还是进入 checkpoint。只有两种 checkpoint 是真正的协作分叉：

- **clarification**：补事实
- **decision**：拍板选路

### 4. Execution & Handoff Layer | 执行交接层

执行当前动作，结果写入 `current_handoff.json`。宿主后续该做什么以 handoff 为准。

### 5. Knowledge Lifecycle Layer | 知识生命周期层

渐进式物化：bootstrap 建最小骨架 → 方案流补齐 blueprint → archive 后归档到 history。

## 削减目标

### 目标词汇表

以下是 canonical 目标。当前存在的非 canonical 词汇标为 legacy/compat，需带 sunset 条件，不得被 blueprint 重新合法化。

#### Checkpoint Types (target: 2)

| Canonical | 语义 |
|-----------|------|
| `clarification` | 补事实（真协作分叉） |
| `decision` | 拍板选路（真协作分叉） |

**已重分类（不再是 checkpoint type）：**

| 旧类型 | 新定位 | 说明 |
|--------|--------|------|
| `plan_proposal` | ~~propose_plan 的 pending artifact~~ | **Wave 3a 已 hard-cut 删除** |
| `execution_confirm` | ExecutionAuthorizationReceipt | 机器授权事实，不是协作分叉 |
| `develop_checkpoint` | develop callback source | 可触发 clarification 或 decision，不是独立 checkpoint type |

#### required_host_action (target: 5)

| Canonical | 语义 |
|-----------|------|
| `answer_questions` | 宿主展示缺失事实，等待用户补充 |
| `confirm_decision` | 宿主展示设计分叉，等待用户选择 |
| `continue_host_consult` | 宿主继续问答 |
| `continue_host_develop` | 宿主继续代码修改（develop_mode 为 hint：quick_fix/standard） |
| `resolve_state_conflict` | 状态冲突，需宿主介入 |

**Sunset（不计入 canonical budget）：**

| Legacy action | 目标归宿 | Sunset 条件 | 替代 contract | 清理里程碑 |
|---------------|----------|------------|-------------|-----------|
| `confirm_plan_package` | — | — | — | ✅ 已完成（Wave 3a） |
| `confirm_execute` | ExecutionAuthorizationReceipt | receipt 替代 checkpoint | P1.5 authorization contract spec | P3a 复核（runtime 已清，tests/contracts 残留待确认） |
| `review_or_execute_plan` | ActionProposal routing | Validator 接管 plan review/execute 语义 | P2 local action contracts | P3a impl |
| `continue_host_quick_fix` | `continue_host_develop(mode=quick_fix)` | 合并为 hint | P2 local action contracts | P3a 复核（runtime 已清） |
| `continue_host_workflow` | `continue_host_develop(mode=standard)` | 合并 | P2 local action contracts | P3a 复核（runtime 已清） |
| `archive_completed` | — | — | — | ✅ 已完成（archive lifecycle cutover） |
| `archive_review` | — | — | — | ✅ 已完成（archive lifecycle cutover） |
| `host_replay_bridge_required` | — | — | — | ✅ 已完成（runtime 无活跃引用） |

#### Route Families (target: 6)

| Canonical | 覆盖 route_name（runtime 实际值） |
|-----------|-------------------------------|
| `plan` | `plan_only`, `workflow`, `light_iterate` |
| `develop` | `exec_plan`, `resume_active`, `quick_fix` |
| `consult` | `consult`, `replay` |
| `archive` | `archive_lifecycle` |
| `clarification` | `clarification_pending`, `clarification_resume` |
| `decision` | `decision_pending`, `decision_resume` |

#### Non-family Surfaces

以下 route 不计入 6 family 预算。总条件：它不是 resumable 的 host-facing workflow continuation。然后必须属于以下之一：

1. **跨路由错误面** — 任何 route 内均可触发的横切 error handling
2. **显式 control/teardown 命令** — 不产出 handoff、不参与工作流推进
3. **显式 read-only utility 命令** — 不影响工作流状态的只读渲染

| route_name | 分类 | 说明 |
|------------|------|------|
| `state_conflict` | 跨路由错误面 | state-resolution error surface |
| `cancel_active` | control/teardown | 清空 active flow，不产出 handoff |
| `summary` | read-only utility | `~summary` 显式命令，不写 last_route、不覆盖 handoff |

新增 non-family surface 必须显式修改本段落，默认不允许扩口。non-family surface 如果不再被 runtime 主链路引用，应直接删除而非保留为 legacy。

#### Core State Files (target: 6, authoritative)

| File | 职责 |
|------|------|
| `current_run.json` | 当前运行态 |
| `current_plan.json` | 活动 plan 绑定 |
| `current_handoff.json` | 执行交接 |
| `current_clarification.json` | clarification checkpoint |
| `current_decision.json` | decision checkpoint |
| `current_archive_receipt.json` | archive 可审计 receipt（不是 host action） |

**Fold/remove：** ~~`current_plan_proposal.json`~~ — **Wave 3a 已删除，未新建替代文件。`context_snapshot.current_plan_proposal` 字段保留为 `None`（反序列化兼容）。**

**Derived/compat（不计入 core budget）：** `last_route.json` — 后续证明可从 handoff/run 派生后移除。

**Ingress scope（不算 review state）：** `current_gate_receipt.json`

### 削减预算表

| 维度 | 当前 | Target | Hard Max | 计算口径 |
|------|-----:|-------:|---------:|---------|
| Checkpoint types | 5 | 2 | 2 | canonical only |
| required_host_action | 13 | 5 | 6 | canonical; compat/derived 不计 |
| Route families | 18 | 6 | 8 | canonical; migration alias 不计 |
| Core state files | 8 | 6 | 7 | authoritative only; derived/compat 不计 |

**Hard max 例外路径：** 只能通过 ADR 更新。必须说明替代了什么旧概念、为什么不能放到 artifacts/status/hint 里。

> **削减前提**：削减执行以 protocol/validator 层契约已稳定为前提（见 `tasks.md` P3a/P3b）。先 formalize contract，再清 runtime 旧面。不以 runtime 内部治理为驱动独立清理。

## 轻量化产品指标

Sopify 的设计目标不仅是工程轻量（削减 runtime），更是产品轻量（少概念、少前置、默认能用、可逐步增强）。

| 指标 | 目标 |
|------|------|
| Convention 首次上手步骤数 | ≤3（读 blueprint → 写 light plan → finalize） |
| 首次上手必需持久化文件 | ≤4（project.md + blueprint/ 三件套） |
| 默认 workflow 必需 contract 数 | ≤5（plan package + archive + receipt + knowledge_sync + blueprint read） |
| 增强路径额外概念 | 逐步引入：review loop → checkpoint → runtime state → plugin |

## 硬约束

1. **能删则删**：新概念必须替换旧概念或证明不增加概念预算
2. **Validator 只授权不执行**：不做 plan materialization、文件迁移、自动修复、状态推进
3. **Deterministic core 只按结构化事实执行**：不理解人话、不做语义推断
4. **Host prompt 不定义机器真相**：prompt 只渲染 machine truth，不作为 runtime truth source
5. **develop_mode 是 hint**：不参与权限裁决；权限裁决看 ActionProposal side_effect + state + risk policy
6. **archive 终态不是 host action**：`archive_receipt.status` 是结果状态，不进 `required_host_action`
7. **不用 router phrasing patch 或 prompt workaround 充当长期解法**：machine truth 未收敛时，回到 protocol/validator/deterministic guard 修复

## 核心契约

### Archive lifecycle

- `ActionProposal(action_type="archive_plan")` 是协议入口；`~go finalize` 只是 alias
- 主体是结构化 `archive_subject`，不通过正则或词表猜
- 两层分离：Validator 负责 validate + authorize + emit artifacts；deterministic core 负责 check + apply
- Legacy/metadata 不完整主体返回 `migration_required`，不自动修复
- 归档只在主体等于当前 global `current_plan` 时清理执行状态

### Checkpoint 契约

只有两种 canonical checkpoint：

**Clarification：** 补齐最小事实。Runtime 写入 `current_clarification.json`，handoff 暴露 `checkpoint_request`。宿主展示问题列表，等待用户补充后恢复 runtime。Pending 期间不生成正式 plan。

**Decision：** 多方案拍板。Runtime 写入 `current_decision.json`，handoff 暴露推荐项与提交状态。宿主展示选项，等待确认后恢复 runtime。Pending 期间不物化 plan。

**Develop callback：** `continue_host_develop` 期间命中用户拍板分叉时，通过 `develop_callback_runtime.py` 回调 runtime，触发 clarification 或 decision。不是独立 checkpoint type。

### knowledge_sync

`knowledge_sync` 是唯一正式同步契约。旧 `blueprint_obligation` 概念只保留 legacy reject 语义，不重新合法化。

```yaml
knowledge_sync:
  project: skip|review|required
  background: skip|review|required
  design: skip|review|required
  tasks: skip|review|required
```

- `skip`: 本轮无需同步
- `review`: 可能受影响，finalize 时复核
- `required`: 必须更新，否则 finalize 阻断

### Runtime gate ingress

- `persisted_handoff` 是 gate 唯一正向机器证据
- gate 判定优先级：`strict_runtime_entry_missing` > `handoff_missing/normalize_failed` > `handoff_source_kind`
- `reused_prior_state` 保持允许态（只读恢复路径）

### Runtime state scope

- Review state 默认落在 `state/sessions/<session_id>/`，覆盖 `current_plan/current_run/current_handoff/current_clarification/current_decision/last_route`
- 根级 `state/` 只承载 global execution truth（当前仍包含 `resume_active / exec_plan` 等 transitional 语义，将随 route 收敛逐步清理；`execution_confirm_pending` 已在 Wave 3b 删除）
- Archive lifecycle 只在归档主体等于当前 global `current_plan` 时清理对应执行状态
- `session_id` 由宿主透传或 gate 自动生成；同一条 review 续轮必须复用同一个 `session_id`
- 并发 review 使用不同 `session_id`；global truth 只补 soft ownership 观测字段
- Clarification / decision bridge 先读 session review state，再回退到 global execution truth

### 消费契约

| Context | 读取集 | Fail-open |
|---------|--------|-----------|
| `bootstrap` | project.md, preferences.md, blueprint/README.md | 缺深层 blueprint 不报错 |
| `consult` | project.md, preferences.md, blueprint/README.md | 不要求 background/design/tasks |
| `plan` | 上述 + blueprint 全集 + active_plan | 深层 blueprint 缺失先补齐 |
| `develop` | plan 读取集 + state/*.json | history 缺失不阻断 |
| `archive` | archive_subject, knowledge_sync, blueprint 全集, history/index.md | history/index.md 缺失现场创建 |

## Design Influence Intake Gate

外部设计影响分三级准入：

| 级别 | 含义 | 准入条件 |
|------|------|---------|
| T0 Reference | 启发方向 | plan 包内标注 |
| T1 Adoption | 采纳待验证 | 映射到哲学 + 有实现路径 + 有验证方案 + 不与 ADR 冲突 |
| T2 Principle | 沉淀原则 | 已实现 + dogfood 未回退 + 通过删除测试 |

## ADR 索引

| ADR | 标题 | 状态 |
|-----|------|------|
| ADR-013 | Product Positioning: Evidence & Authorization Layer | 已确认 |
| ADR-016 | Protocol-first / Runtime-optional | 已确认 |
| ADR-017 | Action/Effect Boundary | P0 完成，持续扩展 |

详见 `architecture-decision-records/`。

## KB 职责矩阵

| Path | Layer | Created When | Git Default |
|------|-------|-------------|-------------|
| `blueprint/README.md` | L0 index | 首次项目触发 | tracked |
| `project.md` | L1 stable | 首次 bootstrap | tracked |
| `blueprint/{background,design,tasks}.md` | L1 stable | 首次进入 plan 流 | tracked |
| `plan/YYYYMMDD_feature/` | L2 active | 每次正式方案流 | tracked |
| `history/YYYY-MM/...` | L3 archive | archive_plan apply 成功 | tracked |
| `state/*.json` | runtime | runtime 执行期间 | ignored |
| `replay/` | optional | 命中主动记录策略 | ignored |
