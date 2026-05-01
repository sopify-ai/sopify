# 蓝图架构与契约

本文定位: Sopify 的架构分层、核心契约、削减目标与硬约束。这是宿主与 runtime 的共同设计基线。

## 产品定位 (ADR-013)

Sopify 是 AI 编程工作流的 **control plane**，不是通用 LLM orchestration。

| 层级 | 表述 |
|------|------|
| 用户层 | 按复杂度自适应推进，关键决策可追踪，产出质量可验证 |
| 产品层 | 自适应工作流、状态交接、质量治理、项目资产沉淀 |
| 架构层 | Workflow control plane. Core owns state truth via Protocol + Validator |

**竞品边界：**

| 产品 | 定位 | Sopify 不做的 |
|------|------|-------------|
| Spec-Kit | Specification-first development | spec 方法论 |
| Superpowers | Skill distribution | 技能市场 |
| Claude Code / Codex / Cursor | Agent execution host | 模型执行器 |
| **Sopify** | **Workflow state/control plane** | 协议、状态、交接、审计 |

**生存性测试：** 2027 年宿主原生支持 plan/checkpoint 后，Sopify 仍必须保留：项目级资产沉淀、跨宿主连续工作、可审计决策链、独立质量闭环。

## 底层哲学

> 以下 3 条哲学是 ADR-013/016/017 的共同根基。所有设计决策可从中推导。

### 哲学 1: Loop-first (循环优先)

每个工作单元是独立闭环：**produce → verify (isolated) → accumulate → produce**。

- produce: 按复杂度选择快速修复 / 轻量迭代 / 完整方案
- verify: 独立上下文验证（cross-review 是参考实现）
- accumulate: 沉淀到 blueprint/history
- loop: 新任务从积累出发

### 哲学 2: Wire-composable (线可组合)

独立 loop 通过**线**（机器契约）组合。Sopify 是串联小 loop 的线——control plane 负责串联和传递状态，不做节点内部的事。

线独立于 session / model / host：handoff + run state 让不同会话精确继续。

| 显隐 | 实现 | 适用 |
|------|------|------|
| 显式 (Runtime) | gate → handoff → checkpoint JSON | 确定性门控 / 审计 |
| 隐式 (Convention) | SKILL.md + 目录约定 | 轻量任务 / 新宿主 |

### 哲学 3: Surface-shared (面共享)

所有线共享一个知识面（blueprint / history）。知识面是跨 session/model/host 的共享工作记忆。

**Sopify 的不可替代性 = 线 + 面的组合。** Protocol 定义 schema，Runtime 是可选的"加固线"。

## 三层定位 (ADR-016: Protocol-first / Runtime-optional)

| 层 | 内容 | 体量目标 | 可替代性 |
|----|------|---------|---------|
| **Protocol** | `.sopify-skills/` 目录约定、schema、SKILL.md 编排 | 纯文档 | 不可替代 |
| **Validator** | ActionProposal 校验、状态迁移校验、archive check/apply | ~2K 行 | 独立交付 |
| **Runtime** | gate / router / engine / handoff 状态机 | 目标 <20K 行 | 可选增强 |

**Convention 模式 (下界)**: LLM 读 SKILL.md → 自行推进 → Validator 事后校验。
**Runtime 模式 (上界)**: 完整 runtime 控制状态迁移。

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

### ExecutionAuthorizationReceipt

执行授权不再是 checkpoint，而是机器授权事实：

**不变量：** 绑定 plan identity + plan revision + execution gate result + action proposal identity + authorization source。使用 canonical JSON + sha256 生成 fingerprint。Plan 变更后 receipt 自动失效。Fail-closed：任一字段不匹配则拒绝执行。

具体字段定义见 ADR-017。

## Runtime 五层架构

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
| `plan_proposal` | propose_plan 的 pending artifact | 等 ActionProposal side-effect proof 稳定后降级 |
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

| Legacy action | 目标归宿 | Sunset 条件 |
|---------------|----------|------------|
| `confirm_plan_package` | propose_plan artifact flow | ActionProposal side-effect proof 覆盖 |
| `confirm_execute` | ExecutionAuthorizationReceipt | receipt 替代 checkpoint |
| `review_or_execute_plan` | ActionProposal routing | Validator 接管 |
| `continue_host_quick_fix` | `continue_host_develop(mode=quick_fix)` | 合并为 hint |
| `continue_host_workflow` | `continue_host_develop(mode=standard)` | 合并 |
| `archive_completed` | `archive_receipt.status=completed` | 结果状态，不是 host action |
| `archive_review` | `archive_receipt.status=review_required` | 结果状态 |
| `host_replay_bridge_required` | sunset | 不再需要独立 host action |

#### Route Families (target: 6)

| Canonical | 覆盖旧 route |
|-----------|-------------|
| `plan` | workflow, light_iterate, plan_only |
| `develop` | quick_fix, exec_plan, resume_active |
| `consult` | consult_readonly |
| `archive` | archive |
| `clarification` | clarification_pending, clarification_resume |
| `decision` | decision_pending, decision_resume |

#### Core State Files (target: 6, authoritative)

| File | 职责 |
|------|------|
| `current_run.json` | 当前运行态 |
| `current_plan.json` | 活动 plan 绑定 |
| `current_handoff.json` | 执行交接 |
| `current_clarification.json` | clarification checkpoint |
| `current_decision.json` | decision checkpoint |
| `current_archive_receipt.json` | archive 可审计 receipt（不是 host action） |

**Fold/remove：** `current_plan_proposal.json` → `current_handoff.artifacts.proposal` 或 `current_run` pending artifact。不得新建替代文件。

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

**Develop callback：** `continue_host_develop` 期间命中用户拍板分叉时，通过 `develop_checkpoint_runtime.py` 回调 runtime，触发 clarification 或 decision。不是独立 checkpoint type。

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
- 根级 `state/` 只承载 global execution truth（`execution_confirm_pending / resume_active / exec_plan`）
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
| ADR-013 | Product Positioning: Workflow Control Plane | 已确认 |
| ADR-016 | Protocol-first / Runtime-optional | 已确认 |
| ADR-017 | Action/Effect Boundary | P0 完成，持续扩展 |

详见 `docs/adr/`。

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
