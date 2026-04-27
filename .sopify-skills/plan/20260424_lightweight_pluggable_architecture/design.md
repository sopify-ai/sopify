# Design: Sopify 总纲

## §1 战略方向

### 1.1 产品定位 (ADR-013)

Sopify 是 AI 编程工作流的 **control plane**，不是通用 LLM orchestration product。

| 层级 | 表述 |
|------|------|
| 用户层 | 按任务复杂度自适应推进，关键决策可追踪，产出质量可验证 |
| 产品层 | 自适应工作流、状态交接、质量治理和项目资产沉淀 |
| 架构层 | Workflow control plane. Core owns state truth via Protocol + Validator |

**核心机制链：** route → plan → checkpoint → handoff → gate → review → history

**Sopify 有价值的不是"会调 skill"，而是：** 自适应推进、长任务可恢复、用户决策不丢、关键执行可管控、产出质量可验证、审查结果可复用、项目知识可沉淀、AI workflow 可测试、宿主无关。

**竞品边界：**

| 产品 | 定位 | Sopify 不抢的 |
|------|------|-------------|
| Spec-Kit | Specification-first development | spec 方法论 |
| Superpowers | Skill distribution & behavioral training | 技能市场 |
| Claude Code / Codex / Cursor | Agent execution host | 模型执行器 |
| **Sopify** | **Workflow state/control plane** | 协议、状态、交接、审计 |

**生存性测试：** 2027 年宿主原生支持 plan/checkpoint/multi-agent 后，Sopify 仍必须保留：项目级资产沉淀、跨宿主连续工作、可审计决策链、权限化扩展、独立质量闭环、计划漂移治理。

### 1.2 Protocol-first / Runtime-optional (ADR-016, 2026-04-26)

> **Sopify 从 Runtime-centric 演进为 Protocol-first：以 `.sopify-skills/` 文件协议和 schema 为稳定内核；Validator 为最小可执行内核；现有 runtime 为可选增强层与参考实现。**

**战略论据：**

1. **核心价值不在 Python runtime** — plan 约定、状态交接、checkpoint、history、blueprint 天然是文件协议，不必须由 28K 行 runtime 承载
2. **Protocol 更抗平台替代** — Runtime 编排易被宿主替代；`.sopify-skills/plan + state + history` 可审计资产格式可被各宿主复用
3. **Convention 模式是多宿主最短路径** — Protocol + SKILL.md + Validator 让新宿主先"会读会写"，再决定是否接 runtime
4. **复杂 runtime 不解决 LLM 出错** — 把"LLM 随机出错"变成"系统性卡在某状态"，后者更不可控

**三层定位：**

| 层 | 内容 | 体量 | 可替代性 |
|----|------|------|---------|
| **Protocol** | `.sopify-skills/` 目录约定、plan/state/history/checkpoint schema、SKILL.md 表单式编排 | 纯文档 | 不可替代 |
| **Validator** | check / doctor / archive、schema 校验、状态迁移校验、原子写、diagnostics | ~2K 行 | 独立交付 |
| **Runtime** | 完整 gate / router / engine / handoff / checkpoint 状态机 | ~28K 行 | 可选增强 / 参考实现 |

**Convention 模式 (下界)**: LLM 读 SKILL.md → 自行推进 → Validator 事后校验。适用：无严格过程要求的任务 + 新宿主快速接入。模型下界：能读懂 SKILL.md 表单并填写。
**Runtime 模式 (上界)**: 完整 runtime 控制状态迁移。适用：需要确定性状态门控、审计、恢复、权限边界的任务。模型下界：能解析 handoff/checkpoint JSON 格式。

> ⚠️ 模式选择维度是**过程要求**，不是模型强弱。Runtime 自身有更高的模型能力下界；太弱的模型连 Runtime 协议也跟不上，此时应先降级到 Convention + Validator。

**四步演进路线：**

| 步骤 | 内容 | 前置 | 代码变更 |
|------|------|------|---------|
| Step 1 | 提取 Protocol 文档：plan/state/lifecycle/SKILL.md 编排规范 | 无 | 纯文档 |
| Step 2 | Protocol validator CLI (check / doctor / archive)，只读优先 | Step 1 + 真实校验需求信号 + 不抢 P0 | ~2K 行新代码 |
| Step 3 | SKILL.md 表单式增强 + Action Schema Boundary (`[ACTION: ...]`、枚举分支、side_effect 标注) | Step 1 + ADR-017 | SKILL.md / schema 升级 |
| Step 4 | Runtime 可选化：Convention 下界 + Runtime 上界 | Step 2+3 验证 | runtime 解耦 |

**弱模型设计约束：** SKILL.md 必须是表单式，不是方法论散文：

```markdown
# ✅ 表单式 (弱模型可机械填写)
[STEP 1] 填写评分表
  goal_score:     ?/3  # 目标是否可执行
  result_score:   ?/3  # 预期结果是否可验证
  boundary_score: ?/2  # 边界是否明确
  constraint_score: ?/2 # 约束是否已知
  total: ?/10

[IF total < 7]
  [ACTION: ASK_USER] 请补充以下缺失项: {列出 score=0 的维度}
[ELSE]
  [ACTION: PROCEED phase=design]
```

### 1.3 外部思想吸收原则

> Sopify 学习外部产品的 workflow insight，但只把可协议化、可验证、可归档、跨宿主可携带的部分吸收进内核；其余能力默认作为 plugin、外部工具或 inspiration only。

**三层吸收模型：**

| 层 | 条件 | 例子 | 默认处理 |
|----|------|------|---------|
| **Core Protocol** | 改变 `.sopify-skills/` 协议，服务所有宿主/项目/模型强度 | plan schema, checkpoint schema, history convention, review-result 归档约定 | 极少进入，必须通过 Core 准入 |
| **Curated Plugin** | 独立产品价值 + 独立生命周期，Sopify 定义接入点和产物归档方式 | CrossReview, Graphify | 可集成，不并入内核 |
| **Inspiration Only** | 只学原则，不接功能 | Linear 的状态极简, GitHub Actions 的可组合 pipeline | 记录 insight，不建模块 |

**Core 准入（4 条全问）：**

1. 是否强化核心五件事：自适应推进、状态交接、质量验证、资产沉淀、跨宿主可携带？
2. 是否能表达为文件协议或 schema，而非 runtime feature？
3. 如果能独立为 plugin，为什么仍必须进入 Core？
4. 6 个月后宿主内建此能力，留下的价值还在吗？

**Plugin 准入（前 3 条 + 替代第 4 条）：** 1-3 同上 + 是否有独立生命周期和独立 exit 标准？

**概念预算：** Core 只保留 plan / state / checkpoint / handoff / blueprint / history / review / validator / plugin manifest。新概念必须替换旧概念。**已有概念的 schema 字段扩展也需过准入问题。** 当前 plugin manifest 实现文件为 `skill.yaml`，演进不改文件名。

**执行门禁：** 新 Phase、子任务包、schema 字段、checkpoint 子类型、state 文件、runtime helper、plugin 能力进入总纲前，必须先标注三层归类。未标注时默认按 Inspiration Only 处理；能作为 Curated Plugin 独立成立时默认不进 Core；进入 Core 时必须说明替换哪个旧概念或为什么不增加概念预算。

**CrossReview 边界：** CrossReview 是质量验证管线，不是 Sopify 子模块。Sopify 只吸收调用时机、review-result 资产约定、verdict→checkpoint 映射和归档方式；模型、prompt、eval、发布、Action、MCP 留在 CrossReview 边界内。

**Inspiration 记录：** 记录于 background.md "外部参考与吸收登记"章节（产品、可借鉴 insight、归类、吸收方式、为什么不进 core / 边界）。

---

## §2 设计原则

1. **Protocol 即内核** — `.sopify-skills/` 文件协议和 schema 是不可替代的核心价值
2. **Core 只裁决状态** — 影响状态真相和路由确定性的留 Core；workflow 能力外移到 Distribution
3. **Contract 不动** — handoff / checkpoint / plan schema 是核心价值
4. **LLM 编排，保障分层** — Convention 模式: LLM + Validator；Runtime 模式: LLM + Engine
5. **向后兼容** — skill.yaml v1 继续工作，新字段可选
6. **Cross-review 分阶段验证** — 先 advisory，验证价值后升级 runtime
7. **子任务包方向一致** — 所有子任务包必须服务于或不阻碍总纲目标
8. **多宿主原生支持** — Claude Code / Codex (✅ 深度验证)；QCoder / Copilot (📋 待调研)；retired legacy host surface 已按 ADR-018 退出活跃目标
9. **策展集成** — Plugin 面向维护者集成，用户配置开关控制
10. **pipeline_hooks 默认关闭** — 心流优先
11. **Action schema boundary** — LLM 可理解自然语言并提出结构化 action；Core/Validator 只依据 action schema、机器事实、side_effect 与风险策略授权，不维护用户话术白名单

---

## §3 当前活跃设计

### 3.1 Phase 0.2 — 感知层精度 (`20260417_ux_perception_tuning`)

三个子项：

- **B. Router 精度修正**：修正 `_is_consultation()` 的问句+动作词判断、`_estimate_complexity()` 的短请求降级。改动 `router.py` (~15行)
- **C. 输出瘦身**：精简 consult/quick_fix 调试信息为面向用户的提示。改动 `output.py`
- 约束：不改 engine.py 执行路径，不改机器契约

> A (Blueprint 可见化) 延后至 Phase 2 启动时。详细设计见子任务包 `20260417_ux_perception_tuning/design.md`。

### 3.2 Phase 4a — CrossReview Advisory Plugin

**草拟前置：** CrossReview v0 CLI 可用 (`pip install crossreview`)
**E2E/dogfood 前置：** CR v0 release gate 通过 + PyPI 可安装 + `verify --diff` + `--format human` 可用
**不依赖：** Phase 3 (runtime hook/bridge 接口)，可与 Phase 0-3 并行

**目录结构与配置：**
```
.agents/skills/cross-review/
├── SKILL.md        # prompt + CLI 调用指令
└── skill.yaml      # advisory mode
```

```yaml
# 当前实现仍使用 skill.yaml 文件名；Phase 4a 只依赖 advisory metadata，
# 不依赖 Phase 3 的 runtime hook / bridge / pipeline_hooks 标准。
id: cross-review
mode: advisory
triggers: ["review", "cross-review"]
host_support: ["*"]
```

**SKILL.md 编排指令（草案）：**

默认路径 (verify --diff，一步到位)：
1. 生成 diff: `git diff HEAD~{task_count}..HEAD > /tmp/cr-diff.patch`
2. 审查: `crossreview verify --diff /tmp/cr-diff.patch --format human`
3. 按 verdict 处理：
   - `pass_candidate` → 继续 finalize
   - `concerns` → 展示 findings，询问用户：修改 / 接受 / 忽略
   - `needs_human_triage` → 请用户判断
   - `inconclusive` → 记录，不阻断

回退路径 (pack → verify，verify --diff 不可用时)：
1. `crossreview pack --diff /tmp/cr-diff.patch --intent "{task_summary}"`
2. `crossreview verify --pack pack.json`
3. 读取 review-result.json，同上 verdict 处理

**无需 bridge.py** — LLM 读 SKILL.md 后自行调用 CLI，与 Graphify 一致。

> Phase 4b (Runtime 模式) 当前冻结。升级条件：(1) Phase 4a 验证了价值 (2) Phase 3 就绪 (3) CR v0 release gate 通过。详见延后设计索引。

---

## §4 延后设计索引

> 以下 Phase 当前延后/冻结。激活时展开为独立子任务包。

| Phase | 内容摘要 | 状态 | 激活条件 | Protocol-first 关系 |
|-------|---------|------|---------|-------------------|
| 0.1 | Action/Risk Boundary v1 (`execution_gate.py` hard-risk detector + action/side_effect policy) | 🔶 事件触发 P0 | 高风险误放行事件 | 受 ADR-017 约束；RiskRule 只做 hard-risk detector，不扩用户话术名单 |
| 0.2-A | Blueprint 可见化 (handoff 注入 blueprint 摘要) | ⏸️ 延后 | Phase 2 启动时 | 信息基础 |
| 0.3 | State Write Classification (ADR-015 前置) | ⏸️ 延后 | Phase 1 启动前 | Validator writer 收口 |
| 1 | Engine 拆分 (engine.py → checkpoint_engine + plan_engine + state_ops) | ⏸️ 延后 | advisory 数据不足时 | Runtime 优化 |
| 2 | Skill 自包含 (SKILL.md 编排指令增强) | ⏸️ 与 Step 3 合并 | Phase 1 后 | 直接服务 Protocol |
| 3 | Runtime hook/bridge 接口 (skill.yaml v2 + bridge.py + pipeline_hooks 标准) | ⏸️ 延后 | Phase 1-2 后 | Runtime 模式专用；advisory manifest 不依赖此项 |
| 4b | CR Runtime 模式 (bridge.py + pipeline_hooks) | 🧊 冻结 | 3 个 dogfood 后裁决 | 依赖 Phase 3 |
| 5 | Graphify Advisory Skill（Sopify 侧用户可调用插件封装） | ⏸️ 延后 | Phase 3 后 | 可先行 advisory |
| 6 | 文档与示例 (plugin 开发指南) | ⏸️ 跟随各 Phase | — | — |

> 各 Phase 的详细设计保留在对应子任务包中，或在激活时新建。本总纲不展开延后 Phase 的实现细节。
>
> **Phase 0.1 口径修订 (2026-04-26)**：`20260417_risk_engine_upgrade` 是历史子任务包。启动前必须按 ADR-017 重审，禁止以扩用户话术/白名单作为主方案；RiskRule 可保留为底层 hard-risk detector，检测对象优先来自 plan task、tool action、diff、side_effect 等机器事实。
>
> **概念区分 (2026-04-26)**：GraphifyEnhancer（知识资产生成，属知识工程 P2，不在 Sopify 总纲范围）和 Graphify Advisory Skill（Phase 5，Sopify 侧用户可调用插件）是两个独立概念。前者由知识工程独立推进，后者依赖 Phase 3。

---

## §5 多宿主适配设计

### 5.1 架构分层

```
┌──────────────────────────────────────────────────────┐
│  宿主无关层 (engine / skill / contract / state)      │
│  · runtime/*.py + .sopify-skills/                    │
├──────────────────────────────────────────────────────┤
│  宿主适配层 (仅此层允许宿主特化)                    │
│  · installer/hosts/*.py                              │
│  · 三层抽象: HostAdapter + HostCapability +          │
│    HostRegistration                                  │
├──────────────────────────────────────────────────────┤
│  宿主提示层 (每个宿主的 prompt/skill 源码)           │
│  · Claude/ / Codex/ / ...                            │
└──────────────────────────────────────────────────────┘
```

> Retired legacy host prompt mirror 属于 ADR-018 sunset surface，清理后不作为新宿主提示层示例。

### 5.2 当前宿主支持

| 宿主 | 状态 | 适配层 |
|------|------|-------|
| Claude Code | ✅ 深度验证 | `~/.claude/` |
| Codex | ✅ 深度验证 | `~/.codex/` |
| Retired legacy host | 🔴 Sunset (ADR-018) | archived |
| QCoder | 📋 待调研 | 待确定 |
| GitHub Copilot | 📋 待调研 | 待确定 |

**新宿主适配**：参考 archived legacy host adapter 的三层抽象经验，在 `installer/hosts/` 下新建文件。适配清单：Phase 0 调研 (全局配置/规则注入/技能发现) → Phase 1 注册 → Phase 2 提示层 → Phase 3 验证。

**skill.yaml 宿主兼容声明**：`host_support: ["*"]` (全宿主) 或指定宿主 ID。`skill_registry.py` 按当前宿主过滤。

**与 Protocol-first 的关系**：Convention 模式下新宿主只需"会读写 `.sopify-skills/`"即可接入，无需实现完整适配层。这是多宿主最短路径。

---

## §6 关键技术决策 (ADR)

### ADR 状态总览

| ADR | 标题 | 状态 |
|-----|------|------|
| 001 | 不 pipeline 化 engine | ✅ 活跃 |
| 002 | Checkpoint: LLM 判断 + Python/Validator 持久化 | ✅ 活跃 |
| 003 | skill.yaml v2 向后兼容 | ✅ 活跃 |
| 004 | CR 分阶段验证 (advisory → runtime) | ✅ 活跃 |
| 005 | 旧总纲残余吸收策略 | 📦 归档 |
| 006 | 子任务包方向一致性约束 | ✅ 活跃 |
| 007 | 多宿主原生支持 | ✅ 活跃 |
| 008 | Plugin 策展集成模型 | ✅ 活跃 |
| 009 | pipeline_hooks 默认关闭 | ✅ 活跃 |
| 010 | 不允许新 checkpoint 类型 (只用内置 4 种) | ✅ 活跃 |
| 011 | CR verdict → checkpoint 映射 + review-fix 循环限制 | ✅ 活跃 |
| 012 | Minimal Core Boundary — 4 层架构 | 🔄 已演进 → 016 |
| 013 | Adaptive Workflow Positioning | 🔄 已演进 → 016 |
| 014 | Skill / Plugin Permission Tiers | ✅ 活跃 |
| 015 | State Write Ownership | ✅ 活跃 |
| 016 | Protocol-first / Runtime-optional | ✅ 顶层战略 |
| 017 | Action Schema Boundary | ✅ 活跃 / P1 架构约束 |

### ADR 详细记录

**ADR-001: 不 pipeline 化 engine**
Engine 做 dispatch，不做 pipeline。Sopify 的 skill 类型多样 (advisory / workflow / runtime)，强制统一 stage 接口会增加复杂度。

**ADR-002: Checkpoint 触发由 LLM 判断，持久化由保障层负责**
SKILL.md 写明"何时需要 checkpoint"，Runtime 模式下 engine 写 state，Convention 模式下 Validator 校验结果。这是"LLM 即编排器"和"确定性保障"的平衡点。

**ADR-003: skill.yaml v2 向后兼容**
新字段全部可选，v1 schema 继续工作。已有 7 个内置 skill，不能 breaking change。

**ADR-004: 第一个外部 plugin 用 cross-review 分阶段验证**
Phase 4a advisory 不依赖 Phase 3，可提前验证价值。Phase 4b runtime 验证 `pipeline_hooks` + `bridge.py` 接口。

**ADR-005: 旧总纲残余吸收策略** `📦 归档`
Plan B2 (Ghost State) → Phase 1+2 自然解决，正式终结。Plan C (Side task) → Phase 2 自然解决。Plan D (文档) → Phase 6。Plan B3 (Ghost Knowledge) → 继续延后。旧总纲已完成成果 (Plan H/B1/A) 的 contract 稳定性继续有效。

**ADR-006: 子任务包方向一致性约束**
所有活跃子任务包必须：方向服务总纲、不引入冲突 contract、文件重叠时先完成局部改善。

**ADR-007: 多宿主原生支持**
engine 子模块不假设特定宿主。`host_support` 字段声明兼容性。handoff/checkpoint/plan 机器契约层宿主无关。宿主差异只落在 `installer/` 和 `hosts/`。

**ADR-008: Plugin 策展集成模型**
Plugin 面向 Sopify 维护者集成经验证的高质量工具。用户通过 `sopify.config.yaml` 配置开关控制。非开放市场。

**ADR-009: pipeline_hooks 默认关闭**
心流优先。用户在 `sopify.config.yaml` 中显式启用才生效。Phase 4a advisory 不通过 hooks 触发——LLM 自主决定。

**ADR-010: 不允许外部 plugin 引入新 checkpoint 类型**
只用内置 4 种 (clarification / decision / execution_confirm / plan_proposal)。Plugin 通过内置类型 + 自定义内容表达交互需求。如需新类型，在 runtime 层新增，非 plugin 自定义。

**ADR-011: CR verdict → checkpoint 映射 + review-fix 循环限制**

| verdict | checkpoint | 行为 |
|---------|-----------|------|
| pass_candidate | 无 | 继续 finalize |
| concerns | decision | 修改代码 / 接受风险 / 忽略 |
| needs_human_triage | clarification | 请用户判断 |
| inconclusive | 无 | 静默记录 |

Review-fix 最多 2 轮，第 3 次强制 decision（只提供"接受/忽略"）。适用 Phase 4b。

**ADR-012: Minimal Core Boundary — 4 层架构** `🔄 已演进 → 016`
原始决策：代码库分 Core Protocol / Core Runtime / Plugin Runtime / Default Distribution 4 层。
演进说明：ADR-016 将 Core 的真正最小边界重定义为 Protocol + Validator，而非瘦身后的 runtime。4 层划分在 Runtime 模式下继续有效，但不再是唯一架构视图。

**ADR-013: Adaptive Workflow Positioning** `🔄 已演进 → 016`
原始决策：Sopify 是 AI 编码助手里的自适应工作流与状态交接系统。
演进说明：产品定位升级为 §1.1。自适应推进可由 SKILL.md 表单式分支实现（Convention 模式），不必须由 router 硬编码（Runtime 模式）。核心价值表述提升至 Protocol-first 战略层。

**ADR-014: Skill / Plugin Permission Tiers**

| 层级 | 状态写权限 | 例子 |
|------|-----------|------|
| Advisory | ❌ 不可写 | templates, kb, workflow-learning |
| Workflow | ⚠️ 提交给 Core 裁决后物化 | analyze, design, develop |
| Runtime Plugin | ⚠️ 通过 bridge contract | CrossReview, Graphify |
| Core | ✅ 直接写 | state store, checkpoint materializer |

防止 Sopify 退化为 prompt pack——checkpoint 触发不能从 Python 确定性退化为 LLM prompt 遵从度。

**ADR-015: State Write Ownership**
Runtime state 只能通过 StateStore 或专用 materializer 写入。目标：收口到 ≤3 个 Core writer (state.py / checkpoint_materializer / handoff builder)。Convention 模式下进一步收口为 1 个 (validator)。先立法后迁移。

**ADR-016: Protocol-first / Runtime-optional** `顶层战略`
详见 §1.2。核心论据和失败模式分析（Context Window 衰减、State 分裂、路由-引擎-LLM 三方不一致）已在战略方向章节展开。反对论据（Validator 体量 ~2K 行、弱模型不能靠自编排、Runtime 是参考实现不是废件）已纳入决策。

**ADR-017: Action Schema Boundary** `P1 架构约束`
Sopify 不维护用户自然语言白名单。自然语言可由 LLM 投影为结构化 action proposal；状态推进、写入、checkpoint 消费和风险放行只能由 Core/Validator 基于机器事实授权。

| 层 | 职责 |
|----|------|
| LLM proposal | 将用户输入映射为有限 action，并附带 payload / confidence_band / ambiguity_reason |
| Protocol / Validator | 校验 action 是否被当前 stage、required_host_action、checkpoint_id、side_effect policy 允许 |
| Risk policy | 判断 action/payload/diff/tool input 的风险，不判断用户话术本身 |
| Materializer | 仅在 validator allow 后写 state / plan / checkpoint |

最小 action 集合：`inspect_checkpoint`、`confirm_plan_package`、`revise_plan_proposal`、`submit_decision`、`answer_clarification`、`confirm_execute`、`cancel_checkpoint`、`ask_question`、`no_write_consult`。字段至少包含 `action_id`、`checkpoint_id/run_id/plan_id`（如适用）、`payload`、`side_effect`、`confidence_band`、`ambiguity_reason`。`confidence_band` 只分 `high / medium / low`；具体数值阈值由 Protocol Step 3 评测后定义，不在 ADR 中写死。

`continue` / `retopic` / `block` 不进入 canonical action 集：`continue` 是确认类 action 的用户表达或 resolved intent；`retopic` 是 `revise_plan_proposal` 的 payload 变体；`block` 是 Validator/Risk policy outcome，不是用户动作。

Validator 必须检查：
1. 当前 `stage` / `required_host_action` / `allowed_actions` 是否允许该 action。
2. `checkpoint_id` / `run_id` / `plan_id` 是否与当前机器事实一致。
3. `side_effect` 是否被当前 response mode 和 checkpoint 类型允许。
4. 风险策略只评估结构化 action、payload、diff、tool input、plan task，不扩展用户话术白名单。
5. 缺字段、低置信度、歧义或状态不匹配时 fail-close：降级为 `inspect_checkpoint` / `ask_question`，或拒绝写入。

少量确定性信号只作为硬刹车：显式 no-write / 只分析、cancel / stop、数字选项。它们不是完整意图识别面，不能演化为维护用户习惯白名单。

Protocol Step 3 需要补齐最小协议面：`action_schema_version`、`supported_actions` capability、以及最小 `action_audit` 事件（记录 proposed_action / validator_decision / reason_code / side_effect）。不提前定义完整 `action_audit.jsonl` schema。

优先级：P1 / Protocol Step 3 架构约束。它不抢 CR release gate 或当前 Phase 0.2-B/C，但所有 checkpoint action、plugin verdict 映射、Phase 0.1 风险检测升级和未来 Runtime 模式都必须遵守。

---

## §7 风险评估

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| Engine 拆分引入回归 | 高 | 中 | 全量测试通过是 gate |
| SKILL.md 表单式格式弱模型仍然偏离 | 中 | 中 | 渐进验证：先强模型确认格式，再弱模型测试 |
| Plugin 接口设计不够通用 | 中 | 中 | cross-review + graphify 两个 case 验证 |
| Protocol 文档化后无人遵守 | 中 | 低 | Runtime 作为参考实现证明协议可行 |
| `.sopify-skills/` 协议无外部采纳者 | 高 | 中 | CrossReview 作为第一个外部协议使用者验证；Protocol Step 1 降低接入门槛；寻找第二个独立项目使用 |
| 新宿主适配成本失控 | 中 | 低 | Convention 模式降低门槛 + 三层抽象模板化 |
| Action schema 过早变成 runtime feature | 中 | 中 | ADR-017 先作为 Protocol Step 3 / SKILL.md / schema 约束；代码实现事件触发，不抢 P0 |
| 遗留 surface 长期保留导致维护负担 | 中 | 中 | ADR-018 强制在改造时声明退出路径，frozen surface 不计入 release gate |

---

## §8 ADR-018: Legacy Surface Retirement `P1 治理约束`

改造 runtime / engine / host 时，必须同时声明：

| 声明项 | 说明 |
|--------|------|
| 新的唯一机器事实来源 | 替代后的 canonical entrypoint / contract |
| 被替代的旧入口 / 旧 helper / 旧测试 | 逐项列出 |
| 删除顺序 | 先声明 → CI dry-run → 迁移测试 → 删旧测试 → 删旧代码 → 清文档 |
| 暂时保留原因 | 如有，需标注截止日期或激活条件 |

**三态定义：**

| 状态 | 含义 | CI 行为 | 代码维护 |
|------|------|---------|---------|
| **frozen** | 不再新增功能，只修安全/阻断 | 不计入 release gate，可保留 smoke | 只接受 security fix |
| **sunset** | 有明确清理任务 | 从 CI release gate 中移除 | 不接受任何修改 |
| **removed** | 已删除 | 彻底删除 | 同步清文档、测试、脚本、fixture、README |

**Entrypoint ownership 分类（每次改造需更新）：**

| 类别 | 处理 |
|------|------|
| canonical entrypoint | 保留并加强测试 |
| debug/helper-only | 保留，文档降级为 "internal/debug" |
| old host-facing entrypoint | 从文档和 release gate 测试中移除 |
| no contract / no callsite | 删除 |
| frozen future work | 不进 release gate；标注截止或激活条件 |

**与 ADR-017 的协同：** 当 Protocol Step 3 完成 action schema 实施后，router.py / execution_confirm.py / decision.py / plan_proposal.py / clarification.py 中的 risk/action intent alias sets（如 `_CONTINUE_KEYWORDS`、`_CANCEL_KEYWORDS`、`_CONFIRM_ALIASES` 等用于动作意图匹配的关键词集）应按本 ADR 的 sunset → removed 流程清理。正常 UX 命令别名（如 `~go`、`~compare`）不在此范围。

优先级：P1 治理约束。不抢 CR P0 或当前 Phase 0.2-B/C。所有 runtime/engine/host 改造（包括 Phase 0.1、Phase 1、Phase 3）都必须遵守。

---

## §9 Complexity Budget Guard `P1 治理约束`

任何新增 protocol 字段、状态文件、runtime helper、host action、系统提示规则或 ADR，必须同时说明：

1. **替代了什么** — 新增项是否替代现有概念
2. **能否删旧** — 被替代的旧概念是否可以进入 ADR-018 sunset → removed
3. **是否增加 complexity debt** — 如果确实只增不减，显式声明为 debt 并标注清理条件

不能说明的默认不进入 P0/P1 主线。

**预算覆盖 4 类：**

| 类别 | 当前值 | 说明 |
|------|--------|------|
| state files | 7 | `current_{clarification,decision,gate_receipt,handoff,plan,plan_proposal,run}.json` |
| helper entrypoints | 22 | `scripts/*.py` |
| host actions | 8 × 28 sub-actions | `_HOST_ACTION_ALLOWED_ACTIONS` |
| prompt/runtime rules | 24+ | 系统提示 C3 节"说明"条数 |

当前值仅作基线参考，不作为硬上限。ADR-017 Step 3 完成后由 T-P3-5b (Protocol Slim Audit) 重新评估。
