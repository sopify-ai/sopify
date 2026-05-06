# Sopify 最小协议规范 (Protocol v0)

本文定位: 定义不依赖 runtime 也成立的最小可携带协议。这是宿主接入 Sopify 的最低门槛。

**权限边界：**

- 本文是 **宿主接入的最小规范入口文档**
- 最小合规看本文；runtime/扩展契约以 `design.md` / ADR 为准
- `design.md` 负责架构分层、削减目标、runtime 参考实现、核心契约细节（含 state 文件、checkpoint、knowledge_sync）
- `ADR-016` 负责 Protocol-first 决策理据与演进路线
- `ADR-017` 负责 ActionProposal / Receipt 字段定义（含 ExecutionAuthorizationReceipt 字段规范）
- 本文不重复上述内容，只定义"宿主能不能只看这一页就接入"

## 1. 最小必备目录结构

```
.sopify-skills/
├── project.md              # 项目技术约定（长期可复用）
├── blueprint/
│   ├── background.md       # 为什么存在、核心价值
│   ├── design.md           # 架构基线、核心契约
│   └── tasks.md            # 未完成长期项
├── plan/
│   └── YYYYMMDD_feature/   # 活动方案包
├── history/
│   └── YYYY-MM/            # 收口归档
├── state/                  # 运行态（runtime 管理，Convention 模式可省略）
└── user/                   # 用户偏好（可选）
```

**最小下界（Convention 模式）**：只需 `project.md` + `blueprint/` + `plan/` + `history/`。`state/` 和 `user/` 是 runtime 增强，Convention 模式下宿主自行管理等价状态。

## 2. 最小必备文件与字段

### plan 方案包（Convention 模式最小示例 / light 下界）

> 以下是 Convention 模式的最小方案包结构，等同于现有 plan scaffold 的 **light** 级别。Standard 和 full 级别需额外包含 background.md / design.md 等，见 runtime plan scaffold 约定。本文不覆盖 standard/full 正式分级。

每个方案包是一个目录 `plan/YYYYMMDD_slug/`，light 下界至少包含：

| 文件 | 必需字段 | 说明 |
|------|---------|------|
| `plan.md` | title, scope, approach | 方案正文（light 级将 tasks/status 内联在 plan.md 末尾） |

`status` 值域：`pending` / `in_progress` / `done` / `blocked`。Light 模式下 task 和 status 内联在 `plan.md`，不要求单独 `tasks.md`。

### blueprint 知识层

| 文件 | 最小内容 | 更新时机 |
|------|---------|---------|
| `project.md` | 项目名、工作目录、运行时目录 | 项目初始化时 |
| `blueprint/background.md` | 项目定位（≤3 段） | 目标变更时 |
| `blueprint/design.md` | 架构基线 | 方案归档后回写 |
| `blueprint/tasks.md` | 未完成长期项 | 方案归档后回写 |

### history 归档

归档目录 `history/YYYY-MM/YYYYMMDD_slug/`，在显式 finalize 时按需创建（archive on demand），至少包含：

| 文件 | 必需字段 | 说明 |
|------|---------|------|
| `receipt.md` | outcome, summary, key_decisions | 可审计收据 |

## 3. 宿主最小义务

宿主（Host）接入 Sopify 协议需满足以下最小义务：

| 义务 | Convention 模式 | Runtime 模式 |
|------|----------------|-------------|
| **读取 blueprint** | 必须。每轮开始前消费 `project.md` + `blueprint/` | 同左 |
| **结构化提案** | 推荐。将用户意图映射为 ActionProposal | 必须。走 Validator 写前授权 |
| **方案包管理** | 必须。创建/更新 `plan/` 下的方案包 | 必须。runtime 辅助 |
| **归档** | 必须。完成后归档到 `history/` 并写 receipt | 必须。runtime 辅助 |
| **knowledge_sync** | 推荐。归档时将稳定结论回写 blueprint | 必须 |
| **checkpoint 响应** | 推荐。遇到 clarification/decision 时暂停等用户 | 必须。runtime 强制 |
| **handoff 消费** | 推荐。读取上轮 handoff 恢复上下文 | 必须 |
| **Validator 校验** | 事后校验。最小交互流可不依赖 Validator 实时阻断，但正式合规与 receipt authority 仍由 Validator 事后校验提供 | 写前授权。Validator 是 pre-write authorizer |

**Convention 模式最小合规**：读 blueprint → 写方案包 → 归档。最小交互流不要求 Validator 实时阻断或 runtime state 文件；但要获得正式 receipt authority 和合规校验，仍需调用 Validator（可事后批量）。

## 4. 典型生命周期样例

### 样例 A: 正常方案流（Convention 模式）

```
1. 宿主读取 blueprint/{background,design}.md 理解项目上下文
2. 用户："添加暗色模式"
3. 宿主创建 plan/20260501_dark_mode/plan.md（含 title/scope/approach + 内联 tasks）
4. 宿主逐项完成 tasks，更新 plan.md 中 status → done
   - 可插拔点：用户可在此阶段引入外部工具（如 graphify 生成架构图、
     cross-review 做独立审查）强化 blueprint 或方案质量，不改变核心方案流
5. 宿主归档到 history/2026-05/20260501_dark_mode/receipt.md
6. 宿主将稳定设计决策回写 blueprint/design.md（knowledge_sync）
```

### 样例 B: 中断与恢复（跨 session / 跨模型 / 跨宿主接力）

```
1. 用户在会话 A（Claude Code）中开始方案，完成 2/5 任务
2. 会话 A 中断（用户关闭/网络断开/切换宿主）
3. 新会话 B（可以是不同宿主如 Cursor，或不同模型）启动，宿主读取：
   - blueprint/ 获取项目上下文
   - plan/20260501_dark_mode/plan.md 获取进度（内联 tasks: 2 done, 3 pending）
   - state/current_handoff.json（如有）获取上轮交接事实
   - history/ 获取已归档方案的决策记忆
4. 宿主从第 3 个 pending task 继续，无需用户重述上下文
   - 协议保证：任意 host/model 只要正确消费 blueprint + plan + handoff，
     就能基于同一项目记忆继续工作
   - 正式 receipt authority 和 compliance 仍由 Validator 事后校验提供
```

### 样例 C: Checkpoint — 需要用户决策

```
1. 宿主在实现过程中发现两种可行方案（CSS variables vs. class toggle）
2. 宿主暂停执行，向用户展示选项
   - Convention 模式：宿主直接在对话中展示选项
   - Runtime 模式：写入 state/current_decision.json，handoff 暴露 checkpoint_request
3. 用户选择方案 A
4. 宿主记录决策到 plan.md（内联在方案正文或 tasks 备注中），继续执行
   - receipt.md 仅在最终归档时生成，不在进行中承载决策状态
```

### 样例 D: 归档失败与回退

```
1. 宿主尝试归档，但方案包缺少必需字段（如 plan.md 无 scope 或 approach）
2. Validator 返回 validation_failed（或 Convention 模式下宿主自检失败）
3. 宿主不执行归档，向用户报告缺失项
4. 用户补全后重新归档
5. 归档成功，receipt.md 记录 outcome + 关键决策
```

## 5. 协议合规检查清单

宿主实现者可用此清单自检最小合规：

- [ ] 能读取 `.sopify-skills/project.md` 并识别项目名
- [ ] 能读取 `blueprint/` 三件套并作为上下文消费
- [ ] 能在 `plan/` 下创建结构化方案包
- [ ] 方案包至少包含 `plan.md`（title/scope/approach + 内联 tasks/status）；standard/full 另需单独 tasks.md 等
- [ ] 能将完成的方案归档到 `history/YYYY-MM/` 并生成 `receipt.md`
- [ ] 归档后能将稳定结论回写 blueprint

以上全部通过即为 **Convention 模式最小合规**。如需 Runtime 模式，另需满足 Validator 接入（见 design.md 核心管线）。

## 6. Integration Contract（外部能力接入契约）— *informative / draft*

> 本节是方向性参考，尚未稳定为规范。具体字段定义待 Validator/Receipt 接口稳定后正式化。当前用于说明外部能力如何接入 Sopify 的收敛链。

Sopify 不做生产/验证/知识处理节点本身，但拥有证据规范、授权判定、收据生成这几个控制节点。外部能力通过以下契约接入 Sopify 的收敛链。

### Producer（外部生产器）

外部生产器（LLM、宿主、代码执行器）交给 Sopify 的是 **ActionProposal**：

| 字段 | 说明 |
|------|------|
| `action_type` | 要做什么（plan / develop / archive / consult …） |
| `side_effect` | 会产生什么副作用 |
| `confidence` | 生产器自评置信度 |
| `evidence` | 支撑提案的事实引用 |

Sopify 接收后由 Validator 授权，不由生产器自行决定执行。

### Verifier（外部验证器）

外部验证器（cross-review、测试框架、lint 等）回传给 Sopify 的是 **verdict + evidence**：

| 字段 | 说明 |
|------|------|
| `verdict` | passed / failed / warning / info |
| `evidence` | 支撑判定的具体事实（文件路径、行号、代码片段等） |
| `source` | 验证器标识（如 `cross-review:v1`、`unittest`） |
| `scope` | 验证范围（全量 / 增量 / 特定文件） |

验证结果进入 handoff / receipt，作为后续授权和归档的证据。**注意**：Verifier 输出的是 **evidence 输入**，不是授权输出；只有 Validator 有权授权。Verifier 的 verdict 作为 Validator 授权判定的风险因子之一。

### Knowledge Provider（外部知识工具）

外部知识工具（graphify、摘要生成器等）沉淀给 Sopify 的是 **artifact + reference**：

| 字段 | 说明 |
|------|------|
| `artifact_type` | 产出类型（graph / summary / diagram / analysis） |
| `artifact_ref` | 产出定位（repo-relative 路径或 URI + digest） |
| `reference_target` | 该产出关联的 plan / blueprint 节点 |
| `stability` | draft / stable（只有 stable 才可进入长期知识层） |

只有满足沉淀准入门槛（跨任务可复用 + 影响后续授权/验证 + 已稳定 + 可 machine-readably 引用）的产出才由 knowledge_sync 回写 blueprint。

### Sopify 的统一出口

Sopify 把上述三类输入统一收敛为：

| 出口 | 承载内容 |
|------|---------|
| `receipt` | 授权回执（见下方 ExecutionAuthorizationReceipt） |
| `handoff` | 交接事实：当前状态 + 验证结果 + 下一步建议 + checkpoint（如有） |
| `history` | 归档事实：outcome + key_decisions + verification_evidence |
| `blueprint` | 长期知识：只有稳定结论（via knowledge_sync） |

#### ExecutionAuthorizationReceipt — *normative*

> **升格状态**：本节从 informative/方向 升格为 **normative**（P1.5-B 升格）。字段语义使用 RFC 2119 表述。

ExecutionAuthorizationReceipt 是 execute_existing_plan 授权通过后生成的机器事实，回答"这次执行被谁、基于哪个 revision、通过什么授权"。

**Receipt MUST 包含以下字段：**

| 字段 | 类型 | 语义 |
|------|------|------|
| `plan_id` | string | 目标 plan 的唯一标识（plan 目录名） |
| `plan_path` | string | 目标 plan 的 workspace-relative 目录路径 |
| `plan_revision_digest` | string | plan.md 内容的 SHA-256 hex digest |
| `gate_status` | string | 生成时 ExecutionGate.gate_status 的值 |
| `action_proposal_id` | string | 触发授权的 ActionProposal 唯一标识（engine 确定性生成，MUST NOT 由 host 指定） |
| `authorization_source` | object | `{ kind: "request_hash", request_sha1: string }` |
| `fingerprint` | string | `sha256(canonical_json({plan_id, plan_path, plan_revision_digest, gate_status, action_proposal_id}))` |
| `authorized_at` | string | ISO 8601 UTC 时间戳 |

**Fail-closed 不变量：**

- Validator 在处理 execute_existing_plan 请求时 MUST 从持久化的 authoritative runtime state 读取已有 receipt
- 如 `plan_revision_digest` 与当前 plan.md 实际 SHA-256 不匹配，Validator MUST 返回 DECISION_REJECT
- 如 `plan_path` 指向的 plan 目录不存在，Validator MUST 返回 DECISION_REJECT
- 如 `gate_status` 与当前 ExecutionGate.gate_status 不匹配，Validator MUST 返回 DECISION_REJECT
- Stale receipt MUST NOT 降级为 consult，MUST NOT 自动 re-authorize

**命名对齐注释**：`plan_revision_digest`（receipt 字段）是通用 Subject Identity 中 `revision_digest` 在 plan subject 场景的特化命名，不是独立概念。两者 MUST NOT 长期并存为不同语义。

## 7. Subject Identity & Review Wire Contract

> **升格状态**：本节中 Subject Identity 的通用字段与核心语义（subject_type / subject_ref / revision_digest / 取证优先级）为 **normative**（其中 `subject_type` 仅 `"plan"` 为 normative，其余值域保留 draft）。execute_existing_plan 场景的 Subject Binding 为 **normative**（P1 升格）。Review Wire Contract 部分仍为 informative/draft，待后续里程碑联动升格。
>
> 本节定义跨宿主协作中"操作的是谁"的最小 machine contract（wire level）。适用于 review、execute_existing_plan、revise、archive 等所有需要绑定主体的场景。收敛策略性规则（轮数上限、severity 判定、冲突解决）归 `design.md` Default Workflow 策略。

### Subject Identity（跨场景通用）

每个 side-effecting action 必须携带明确的主体身份，以保证跨宿主可追溯、可验证。Subject identity 是 protocol 层契约，validator 和 runtime 都是消费方。

| 字段 | 说明 |
|------|------|
| `subject_type` | 被操作对象类型（`plan` 为 normative；`code` / `architecture` 保留 draft） |
| `subject_ref` | 对象定位：workspace-relative 路径（如 `.sopify-skills/plan/20260501_dark_mode`） |
| `revision_digest` | 版本标识：目标对象的确定性快照标识（SHA-256 hex digest），保证操作绑定到确定性快照 |

> **命名对齐注释**：通用 Subject Identity 使用 `revision_digest`；ExecutionAuthorizationReceipt 使用 `plan_revision_digest`。后者是前者在 plan subject 场景的特化命名，不是独立概念。实现时 MUST NOT 混用或创建不同语义。

**主体取证优先级**（当 subject 未显式给出时的解析链路）：

1. `explicit_reference` — 用户或 ActionProposal 显式指定
2. `self_reference` — 当前上下文中可唯一推定的活跃主体
3. `new_plan_intent` — 检测到新建意图，不绑定已有主体
4. `stable_handoff_evidence` — 上轮 handoff 中稳定的主体引用
5. `current_plan_anchor` — 全局 current_plan 作为兜底

**Validator 消费边界**：validator 基于 subject identity 做 admission / authorization 判定。subject 不明确时 validator MUST 拒绝而非猜测。

**Runtime 消费边界**：runtime 作为参考实现消费 protocol 定义的 subject identity contract，MUST NOT 自行定义主体解析语义。

### execute_existing_plan 场景的 Subject Binding — *normative*

execute_existing_plan 是 subject identity 最关键的消费场景。宿主 MUST 在 ActionProposal 中通过 `plan_subject` 字段块携带以下信息：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `subject_ref` | string | MUST | 目标 plan 的 workspace-relative 方案目录路径（如 `.sopify-skills/plan/20260501_dark_mode`） |
| `revision_digest` | string | MUST | 该目录下 `plan.md` 文件内容的 SHA-256 hex digest |

**可携带规则**：

- 跨 session 接力时，新 session MUST 通过 handoff 或 plan 文件重新建立 subject binding，MUST NOT 隐式继承前 session 的绑定
- plan 内容变更（revision_digest 不匹配）后，已有 ExecutionAuthorizationReceipt 自动失效
- Validator 在 admission 阶段 MUST 校验 `subject_ref` 存在性 + `revision_digest` 一致性
- 缺少 `plan_subject`、`subject_ref` 指向不存在的 plan、或 `revision_digest` 与文件实际内容不匹配时，Validator MUST 返回 DECISION_REJECT（不降级 consult）

> **Legacy mapping 注释**（informative）：
>
> 现役 machine truth 中，plan 主体的表达形式与上述 canonical subject binding 存在映射关系：
>
> | 现役路径 | canonical 映射 |
> |---------|--------------|
> | `current_plan.path`（state.py） | → `plan_subject.subject_ref`（workspace-relative 目录路径） |
> | `~go exec` 隐含的 plan 指向 | → 应显式携带 `plan_subject`，当前未携带 |
> | `review_or_execute_plan`（action_projection） | legacy composite，计划 P3a 收口（见 `design.md` sunset 表） |
>
> 以上映射为 informative 注释，不构成规范性要求。现役路径的 canonical 化属于 P3a contract-aligned cleanup 范围。

### Review Subject Identity — *informative/draft*

审查是 subject identity 的一个消费场景。每次审查必须绑定被审查对象，字段复用上述 Subject Identity 定义。本小节仍为 informative/draft，待后续里程碑联动升格。

### Review Record Shape

审查记录遵循 Verifier contract（§6），附加跨宿主审查所需字段：

| 字段 | 说明 |
|------|------|
| `review_id` | 唯一审查标识 |
| `reviewer_source` | 审查来源标识（`host:cursor` / `host:claude-code` / `skill:cross-review`） |
| `convergence_action` | `accept` / `revise` / `blocked` / `escalate` |
| `revision_suggestions` | 具体修改建议（可选） |

### 存储位置

审查记录作为 evidence 进入 handoff 或 plan metadata，归档时纳入 receipt 的 verification_evidence。具体字段与路径待 Validator/Receipt 接口稳定后正式化。

## 非目标

- 不定义 Validator 实现细节（见 ADR-017）
- 不定义 Runtime 内部架构（见 design.md "Runtime 五层架构"）
- 不定义 state 文件 schema（归 runtime 管理）
- 不定义 SKILL.md 编排规范（待 ADR-016 Step 3 稳定后补充）
- 不替代 design.md 的契约定义，只提取"不依赖 runtime 也成立"的最小子集
- 不定义收敛策略性规则（轮数上限、severity 判定等归 design.md Default Workflow 策略）
