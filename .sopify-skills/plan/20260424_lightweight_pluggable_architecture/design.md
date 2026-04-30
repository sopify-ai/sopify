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
| **Validator** | schema 校验、授权、deterministic check/archive 入口、状态迁移校验、原子写、diagnostics | ~2K 行 | 独立交付 |
| **Runtime** | 完整 gate / router / engine / handoff / checkpoint 状态机 | ~28K 行 | 可选增强 / 参考实现 |

**Convention 模式 (下界)**: LLM 读 SKILL.md → 自行推进 → Validator 事后校验。适用：无严格过程要求的任务 + 新宿主快速接入。模型下界：能读懂 SKILL.md 表单并填写。
**Runtime 模式 (上界)**: 完整 runtime 控制状态迁移。适用：需要确定性状态门控、审计、恢复、权限边界的任务。模型下界：能解析 handoff/checkpoint JSON 格式。

> ⚠️ 模式选择维度是**过程要求**，不是模型强弱。Runtime 自身有更高的模型能力下界；太弱的模型连 Runtime 协议也跟不上，此时应先降级到 Convention + Validator。

**四步演进路线：**

| 步骤 | 内容 | 前置 | 代码变更 |
|------|------|------|---------|
| Step 1 | 提取 Protocol 文档：plan/state/lifecycle/SKILL.md 编排规范 | 无 | 纯文档 |
| Step 2 | Protocol validator CLI（check / repair / archive），只读优先 | Step 1 + 真实校验需求信号 + 不抢 P0 | ~2K 行新代码 |
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

**Operating Principle: Produce → Verify → Knowledge → Better Produce**

Sopify 的最小闭合单元是 Produce → Verify → Knowledge → Better Produce。Sopify 负责 Verify-A（pre-write authorization gate）和编排 Verify-B（post-write project toolchain）；Verify-C（post-produce quality review）由 CrossReview 等独立质量管线承担。Knowledge 只吸收验证后的信号，并优先用于删旧规则、精简提示和更新高信号 blueprint。

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

> **澄清：** 架构层（Host / Plugin / Protocol / Validator / Runtime）是分层描述词，不计入 Core 概念预算。概念预算仅约束 Core 协议资产和状态模型中的命名概念；架构层名词可自由引用，不受"替换旧概念"规则约束。

**执行门禁：** 新 Phase、子任务包、schema 字段、checkpoint 子类型、state 文件、runtime helper、plugin 能力进入总纲前，必须先标注三层归类。未标注时默认按 Inspiration Only 处理；能作为 Curated Plugin 独立成立时默认不进 Core；进入 Core 时必须说明替换哪个旧概念或为什么不增加概念预算。

**子包开立约束（无线上用户期）：**

1. 新子包默认走激进收敛，不默认保守兼容；若保留 shim / alias / 双轨路径，必须写明删除时点，并要求在同一子包内收口。
2. 每个子包必须同时回答两件事：新增什么协议 / validator 资产；删除什么旧 route / helper / state path / output / test 断言。只增不删的子包，默认不通过。
3. 若问题可先通过删除旧语义、收敛单一路由解决，不得先扩 schema、guard、测试矩阵或 prompt 规则。
4. 文档包不是默认入口。只要已有实现方向明确，先做最小实现 cutover，再做 blueprint / plan 文档单独收口；不得连续开纯解释型子包替代实现推进。
5. 测试只保留 contract tests、关键回归和必要 smoke；不得把每个 guard、每个 reason code、每条兼容投影都展开成长期测试矩阵。
6. 子包验收优先看净减量：旧概念引用数、旧 route 分支、双重 truth 路径、兼容投影数量是否下降；新增文件数或规则数不是正向指标。
7. 若新增概念无法明确替换旧概念，或新增 runtime 结构不能沉淀为 protocol / validator 资产，则默认不立项。

**CrossReview 边界：** CrossReview 是质量验证管线，不是 Sopify 子模块。Sopify 只吸收调用时机、review-result 资产约定、verdict→checkpoint 映射和归档方式；模型、prompt、eval、发布、Action、MCP 留在 CrossReview 边界内。

**内置 skill 产品化边界：** `runtime/builtin_skill_packages/` 暂不整体拆分为独立产品。短期内它仍是 Sopify 官方 builtin workflow pack，用于提供开箱即用的 analyze / design / develop / kb / templates / model-compare / workflow-learning 能力。未来形态允许部分 builtin skill "毕业"为独立产品或独立协议包，但必须走 §1.3 Plugin 准入与 D16 外部化判定：至少 2 个非 Sopify 消费方、稳定通用 JSON contract、可独立 eval。默认分层如下：

| 类别 | 当前处理 | 未来形态 |
|------|----------|----------|
| analyze / design / develop | 保持 Sopify-owned builtin workflow pack | 可提取为官方 Protocol workflow pack，但 canonical ownership 留在 Sopify |
| kb / templates | 保持 Sopify Protocol 支撑资产 | 可随 Protocol / Validator 分发，不单独产品化 |
| model-compare | 保持 builtin runtime skill | 有外部需求后可毕业为模型对比 / eval harness plugin |
| workflow-learning | 保持 builtin workflow skill | 有稳定事件 schema 后可毕业为 trace / replay / decision explanation plugin |

**不影响当前优先级：** 该边界只记录未来产品形态，不新增 Phase、不新增 P0/P1 任务、不改变当前链路。近期仍按既有顺序推进：CrossReview release/Phase 4a、Protocol Step 1、数据驱动决定 Validator/Runtime。

**Inspiration 记录：** 记录于 background.md "外部参考与吸收登记"章节（产品、可借鉴 insight、归类、吸收方式、为什么不进 core / 边界）。

### 1.4 设计全景图

> 本节从终态视角呈现 Sopify 的完整架构。读者看完后应能回答：**Sopify 最终长什么样、各部分如何协作、为什么这么分层。**
> 细节在后续章节展开；本节只画全局地图。

#### 1.4.1 终态架构分层

```
┌─────────────────────────────────────────────────────────────────┐
│  Host Layer -- host execution env                               │
│  Claude Code [ok] | Codex [ok] | QCoder [-] | Copilot [-]       │
│  LLM exec + tool-call only                                      │
│  Convention mode: r/w .sopify-skills/ only                      │
├─────────────────────────────────────────────────────────────────┤
│  Plugin Layer -- curated external capabilities                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ CrossReview  │  │ Graphify     │  │ future       │           │
│  │ quality-pipe │  │ proj-graph   │  │ plugins      │           │
│  │ advisory /   │  │ advisory     │  │              │           │
│  │ runtime(frzn)│  │              │  │              │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  contract: skill.yaml + SKILL.md manifest + artifact archive    │
│  admission: §1.3 3-layer filter + 4 core/plugin questions       │
├─────────────────────────────────────────────────────────────────┤
│  Runtime Layer -- optional enhance / ref impl   ~28K replaceable│
│  gate -> router -> engine -> handoff -> checkpoint state machine│
│  provides: state gate, audit chain, interrupt resume, perms     │
│  Convention mode: this layer can be fully absent                │
├═════════════════════════════════════════════════════════════════╡
                                      ↑ below: irreplaceable stable core
│  Validator Layer -- min executable kernel         ~2K standalone│
│  validate/authorize . check/repair . archive (migrate)          │
│  read-first . atomic write . diagnostics                        │
│  scripts/*.py -- 22 deterministic helpers, invoke via SKILL.md  │
├─────────────────────────────────────────────────────────────────┤
│  Protocol Layer -- irreplaceable core             pure docs     │
│  .sopify-skills/ directory convention                           │
│  plan / state / history / checkpoint schema                     │
│  SKILL.md form-based orchestration standard                     │
│  lifecycle convention (plan -> history -> blueprint)            │
└─────────────────────────────────────────────────────────────────┘
```

**分层原则：** 越靠下越稳定、越不可替代。即使所有上层都被宿主原生替代，Protocol 层的可审计资产格式和跨宿主可携带性仍然保留全部价值——这是 §1.1 生存性测试的架构基础。

**各层关键 ADR：**

| 层 | 关键 ADR | 约束 |
|----|---------|------|
| Protocol | ADR-016 (顶层战略), ADR-015 (写入收口) | 不可替代内核，概念预算 ≤9 |
| Validator | ADR-002 (LLM 判断 + Python 持久化), ADR-017 (Action Schema) | 只读优先，fail-close |
| Runtime | ADR-001 (不 pipeline 化), ADR-010 (4 种 checkpoint) | 可选增强，不是唯一路径 |
| Plugin | ADR-008 (策展集成), ADR-004 (CR 分阶段), ADR-009 (hooks 默认关闭) | 独立产品 + Sopify 接入点 |
| Host | ADR-007 (多宿主原生), ADR-003 (v2 向后兼容), ADR-018 (退出路径), ADR-019 (分发接入) | Convention = 最短接入路径；thin-stub 零配置 |

#### 1.4.2 核心资产链

Sopify 的不可替代产品不是 runtime 代码，而是**资产链**——从用户请求到项目知识的完整流转：

```
用户请求
  │
  ▼
route ─── 复杂度判定 → 路由分类 (简单/中等/复杂 → 快速修复/轻量迭代/完整流程)
  │
  ▼
plan ──── background + design + tasks 方案包，版本化、可追溯
  │
  ▼                          ┌─────────────────────┐
checkpoint ◄── 用户拍板 ◄───│ clarification (补事实)│
  │             (4 种内置)    │ decision (选路径)    │
  │                          │ plan_proposal (建包)  │
  ▼                          │ execution_confirm    │
handoff ── 结构化交接契约     └─────────────────────┘
  │
  ▼
develop ── LLM 执行代码变更
  │
  ▼
gate ───── 质量门禁 (risk boundary, execution_gate)
  │
  ▼ (可选触发 Plugin)
review ─── [Plugin: CR] advisory → findings → verdict
  │
  ▼
history ── 归档，含方案包 + review-result，可追溯
  │
  ▼
blueprint ─ 项目级长期知识 (人工策展 + 机器派生)
  │
  ▼                          ┌─────────────────────┐
knowledge/ (P2/P3) ─────────│ graph.json (项目图谱)│
  │                          │ rules/ (缺陷规则)   │
  └───── 回注下一次 route ───│ modules.md (结构)   │
                             └─────────────────────┘
```

**资产链在两种模式下的驱动差异：**

| 维度 | Convention 模式 | Runtime 模式 |
|------|----------------|-------------|
| 驱动者 | LLM 读 SKILL.md 自驱 | engine.py 控制每步迁移 |
| 校验者 | Validator 事后校验 | state machine 实时门控 |
| 资产格式 | **完全相同** | **完全相同** |
| 断裂风险 | LLM 偏离 → Validator 捕获 | 低（确定性） |

**共享不变量：** 无论哪种模式，Protocol 层的 schema 和归档格式完全相同。这是跨模式互操作的基础，也是"先 Convention 验证、再决定是否需要 Runtime"策略的前提。

#### 1.4.3 双模运行模型

```
                    ┌────────────────────────────────┐
                    │       Protocol Layer           │
                    │  .sopify-skills/ schema        │
                    │  SKILL.md 表单式编排标准       │
                    │  plan/state/checkpoint 约定    │
                    └───────────┬────────────────────┘
                                │
                   ┌────────────┴────────────┐
                   │                         │
         ┌─────────▼──────────┐   ┌──────────▼──────────┐
         │  Convention 模式    │   │  Runtime 模式        │
         │  (下界)             │   │  (上界)              │
         ├────────────────────┤   ├─────────────────────┤
         │ 编排者: LLM         │   │ 编排者: engine.py    │
         │ 指令源: SKILL.md    │   │ 指令源: engine dispatch│
         │ 确定性工具:          │   │ 校验: state machine   │
         │   scripts/*.py     │   │ 状态: StateStore      │
         │ 校验: Validator     │   │ 适用: 审计/权限/恢复  │
         │ 状态: 文件即状态    │   │       高可靠任务      │
         │ 适用: 无严格过程    │   │ 接入成本: 完整 runtime│
         │       要求的任务    │   │ 模型下界: 能解析      │
         │ 接入成本: 极低      │   │   handoff JSON       │
         │ 模型下界: 能读      │   └─────────────────────┘
         │   SKILL.md 表单     │
         └────────────────────┘
```

**模式选择维度是过程要求，不是模型强弱。**

- 需要确定性门控 + 审计链 + 中断恢复 → Runtime 模式
- 能接受 LLM 偶尔偏离 + 事后校验兜底 → Convention 模式
- 太弱的模型连 Runtime 协议也跟不上 → 先降级 Convention + Validator

**Phase 4a 的战略双重角色：**
1. **产品目标**：develop 后可选触发 CR advisory 审查
2. **战略验证**：Convention 模式**首次实战检验** — LLM 仅靠 SKILL.md 表单式指令自主调用外部 CLI，不经 runtime 编排

验证结果直接决定 Protocol Step 2/3 激活时机（详见 §3.2 Convention 验证指标）。

#### 1.4.4 飞轮架构映射

生态总纲定义了**生产 → 验证 → 知识**三环飞轮。以下是 Sopify 内部架构如何承载这三环：

```
                    ┌────────────────────────┐
                    │    知识环 (P2/P3)       │
                    │ blueprint/knowledge/   │
                    │ graph.json · rules/    │
                    │ + review-result 沉淀   │
                    └───────┬────────────────┘
                            │
                  注入 plan/develop 上下文
                            │
        ┌───────────────────▼───────────────────────┐
        │                                           │
        │           Sopify Core (生产环)            │
        │      route → plan → develop → finalize    │
        │      checkpoint · handoff · gate          │
        │                                           │
        └──────────────────┬────────────────────────┘
                           │
                  develop 完成后触发
                           │
        ┌──────────────────▼────────────────────────┐
        │                                           │
        │        CR Plugin (验证环)                 │
        │  advisory: SKILL.md → CLI → findings      │
        │  runtime: bridge → verdict (🧊 Phase 4b 冻结)    │
        │                                           │
        └──────────────────┬────────────────────────┘
                           │
                 findings + review-result
                           │
                    ┌──────▼───────┐
                    │   history/   │──→ blueprint/ ──→ knowledge/ ──→ 回注生产环
                    │  归档 + 索引 │
                    └──────────────┘
```

**Sopify 承载飞轮的关键机制：**

| 飞轮环节 | Sopify 架构映射 | 关键 ADR / Phase | 当前状态 |
|---------|----------------|-----------------|---------|
| 生产 → 验证 | develop 完成 → SKILL.md 触发 CR CLI | Phase 4a, ADR-004 | 🔶 草拟已完成，待 E2E + 3 项目 dogfood |
| 验证 → 沉淀 | review-result.json → history/ 归档 | ADR-011 (verdict 映射) | ADR 已定义 |
| 沉淀 → 知识 | history/ + review-result → knowledge/rules/ | 知识工程 P2 | ⏸️ 延后 |
| 知识 → 回注 | knowledge/ → design/develop Skill 上下文注入 | 知识工程 P3 | ⏸️ 延后 |

**当前飞轮成熟度：** 生产环 ✅ 运行中 → 验证环 🔶 Phase 4a 草拟完成、待 dogfood 闭合 → 知识环 ⏸️ P2/P3 延后（不阻塞前两环）。飞轮的启动策略是**先闭合生产→验证环**，用真实 review-result 数据驱动知识环的优先级决策。

#### 1.4.5 ADR 战略拓扑

19 个 ADR 不是平级的技术决策列表。以下是它们的逻辑层级：

```
                            ADR-016
                    Protocol-first / Runtime-optional
                          ┌─ 顶层战略 ─┐
                          │            │
                   ADR-012 (已演进 ↗)  ADR-013 (已演进 ↗)
                   4层架构演进          自适应定位演进
                   （演进方向: 012→016; 括号标注为演进来源，非依赖关系）

    ┌─────────────────────┬─────────────────────┬────────────────────┐
    │                     │                     │                    │
    ▼                     ▼                     ▼                    ▼
  状态与权限           执行边界             插件与集成          宿主与分发
 ┌──────────┐        ┌──────────┐        ┌──────────┐        ┌──────────┐
 │ ADR-002  │        │ ADR-017  │        │ ADR-008  │        │ ADR-007  │
 │ LLM判断+ │        │ Action   │        │ 策展集成  │        │ 多宿主   │
 │ Python   │        │ Schema   │        │          │        │ 原生支持  │
 │ 持久化   │        │ Boundary │        │ ADR-009  │        │          │
 │          │        │          │        │ hooks    │        │ ADR-003  │
 │ ADR-010  │        │ ADR-001  │        │ 默认关闭  │        │ v2向后   │
 │ 4种      │        │ 不pipe-  │        │          │        │ 兼容     │
 │ checkpoint│       │ line化   │        │ ADR-004  │        │          │
 │          │        │ engine   │        │ CR分阶段  │        │ ADR-019  │
 │ ADR-014  │        └──────────┘        │          │        │ Thin-Stub│
 │ 权限分层  │                            │ ADR-011  │        │ 分发接入  │
 │          │                            │ verdict  │        └──────────┘
 │ ADR-015  │                            │ 映射     │
 │ State写  │                            └──────────┘
 │ 入收口   │
 └──────────┘

                   治理与清理                方向一致性
                  ┌──────────┐              ┌──────────┐
                  │ ADR-018  │              │ ADR-006  │
                  │ Legacy   │              │ 子包方向  │
                  │ Retirement│             │ 一致性   │
                  │          │              │          │
                  │ §9 复杂度 │              │ ADR-005  │
                  │ 预算守卫  │              │ 旧纲吸收  │
                  │          │              │ (归档)   │
                  └──────────┘              └──────────┘
```

#### 1.4.6 分发与接入模型

Sopify 采用 **thin-stub + 集中管理** 分发架构（ADR-019）。项目本地零拷贝，全局 payload 单点管理版本与更新。

```
全局 payload (一次安装)                      项目 workspace (自动 bootstrap)
~/.claude/sopify/                            project-root/
  ├─ payload-manifest.json ─ 版本索引          └─ .sopify-runtime/
  ├─ bundles/                                       └─ manifest.json (thin-stub)
  │    └─ {version}/                                     8 字段：schema_version,
  │         ├─ manifest.json (完整契约)                    stub_version, bundle_version,
  │         ├─ runtime/      (~28K 行)                     required_capabilities,
  │         └─ scripts/      (22 helpers)                  locator_mode, legacy_fallback,
  └─ helpers/                                              ignore_mode, written_by_host
       └─ bootstrap_workspace.py                     ↑
            (自包含, 不依赖源仓库)             locator_mode: global_first
                                              ─── 指向全局 bundle ───
```

**首次接入流 (用户视角)：**

> 详细的 bootstrap 流程、后续使用流、版本兼容不变量（`NEWER_THAN_GLOBAL / STALE / INCOMPATIBLE` 三态）、ADR-019 接入约束 5 问，见 §10（ADR-019 完整展开）。

**阅读指引：**

| 目的 | 阅读路径 |
|------|---------|
| 理解 Sopify 战略 | ADR-016 → ADR-017 → §1.1 生存性测试 |
| 理解状态模型 | ADR-002 → ADR-010 → ADR-014 → ADR-015 |
| 理解插件模型 | ADR-008 → ADR-004 → ADR-011 → ADR-009 |
| 理解治理约束 | ADR-018 → §9 复杂度预算 → ADR-006 |
| 理解多宿主 | ADR-007 → ADR-003 → §5 多宿主设计 → Convention 模式 (§1.4.3) |
| 理解分发接入 | ADR-019 → §5 多宿主 → ADR-007 → Convention 模式 (§1.4.3) |

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
12. **轻量化顺序** — 删除 / 冻结 / 文档化优先于新增基础设施。当前确认链路为 Trae sunset → Phase 0.2-B/C → Protocol Step 1 → CrossReview Phase 4a → 数据驱动决定 Validator/Runtime

### 2.1 后续子方案包开包边界

当同一主题同时暴露“主体真相”“checkpoint 局部动作”“宿主提示治理”三类问题时，后续子方案包的开包顺序固定为：

1. explicit subject binding
2. checkpoint local actions
3. host prompt governance

具体到当前 archive/lifecycle 延伸主题：

- `existing_plan_subject_binding` 先做：先统一 review / revise / execute 对 existing plan 的显式主体解析，先解决“操作的是谁”，再进入动作层。
- `checkpoint_local_actions` 次之：在主体 truth 稳定后，再收敛 `continue / revise / cancel / inspect` 等局部动作；不得把主体歧义和动作歧义混在同一切片。
- `host_prompt_governance` 最后做：只在前两者稳定后进入，职责是消费稳定 contract 做宿主展示与投影，不得反向定义 runtime truth。

#### `existing_plan_subject_binding` 边界定义（预备）

这个子切片只回答一个问题：**当前请求操作的是哪个 existing plan**。它不回答“用户下一步想继续 / 修改 / 取消 / 执行什么动作”。

适用范围：

- `~go plan` / review / revise / execute 等请求显式指向某个 existing plan
- 当前已有 active/current plan，用户希望继续评审、挂接、重绑或切换到另一 existing plan
- clarification / decision 恢复后，需要把 planning / review 上下文重新绑定到唯一 plan 主体

主体取证优先级：

1. request 中显式给出的 `plan_id` / `plan_path` / 可判定 existing plan 引用
2. 与当前 `current_plan` 完全一致的显式 self-reference
3. 明确“新建 plan”意图，此时结论不是绑定 existing plan，而是显式走 create-new
4. 当前 checkpoint / handoff 已稳定携带的 `plan_path`，且与 `current_plan` / resolved snapshot 一致
5. 显式 current-plan anchor（例如“当前 plan / 这个 plan / 继续这个方案”这类能和唯一 current plan 对齐的取证）

当以上取证都不足以唯一确定主体时：

- 若当前存在 active/current plan，且请求涉及 existing plan 继续推进，但未明确锚定主体，必须停在 `active_plan_binding_choice` 或等价 decision checkpoint。
- 不允许继续沿用“strict single-active-plan policy”做静默自动绑定。

这个子切片要统一的不是自然语言动作，而是 existing plan subject truth：

- 当前是复用 `current_plan`
- 还是重绑到另一个 explicit existing plan
- 还是明确新建 plan
- 还是必须先让用户拍板“挂当前 plan / 新开 plan”

不在本切片范围内：

- `continue / revise / cancel / inspect` 的局部动作语义
- archive/finalize lifecycle
- prompt 治理、展示文案和宿主投影优化
- gate / preflight / bootstrap 架构
- 通用 ActionProposal action 扩展

收口目标：

- existing plan 的主体解析从 router keyword / scattered engine fallback 中抽离成单一 deterministic binding contract
- `current_plan.path`、`handoff.plan_path`、`current_run.plan_path` 不再各自隐式代表不同“主体真相”
- 为后续 `checkpoint_local_actions` 提供稳定前提：动作层只消费已绑定主体，不再一边猜动作一边猜主体

后续开包 guard：

- 不新增用户话术白名单或 keyword patch 去理解“局部语境”。
- 不用 prompt 层 workaround 修补未收敛的 machine truth / subject truth / checkpoint truth。
- 不把窄切片问题顺手扩成通用 action framework；新增 action 必须是 contract-backed 最小切片，并绑定 side_effect、machine ids 与 fail-close。
- 不把 Phase 0.2-B/C 当成 subject/action contract 的临时承载层；它们只能做 non-contract perception cleanup。
- 不在 protocol / validator 足够时引入更重 runtime 基础设施；新增 runtime 复杂度必须说明替换了什么旧耦合。
- 每个后续子方案包都要证明自己在降低 route semantics 与 conversational/local context 的耦合，而不是重新编码它。

---

## §3 当前活跃设计

### 3.1 Phase 0.2 — 感知层精度 (`20260417_ux_perception_tuning`)

三个子项：

- **B. Router 精度修正**：修正 `_is_consultation()` 的问句+动作词判断、`_estimate_complexity()` 的短请求降级。改动 `router.py` (~15行)
- **C. 输出瘦身**：精简 consult/quick_fix 调试信息为面向用户的提示。改动 `output.py`
- 约束：不改 engine.py 执行路径，不改机器契约

> A (Blueprint 可见化) 延后至 Phase 2 启动时。详细设计见子任务包 `20260417_ux_perception_tuning/design.md`。

### 3.2 Phase 4a — CrossReview Advisory Plugin + Convention 模式验证

**草拟前置：** CrossReview v0 CLI 可用 (`pip install crossreview`)
**E2E/dogfood 前置：** CR v0 release gate 通过 + PyPI 可安装 + host-integrated CLI 可用（`pack` / `render-prompt` / `ingest --format human`）；`verify --diff --format human` 仅作为 standalone fallback 校验
**当前状态 (2026-04-28)：** 草拟前置与 E2E/dogfood 前置均已满足；`.agents/skills/cross-review/` 宿主消费副本与 develop-rules `post_develop` advisory 步骤已落地。剩余工作是端到端验证与 3 项目 dogfood 数据采集。
**不依赖：** Phase 3 (runtime hook/bridge 接口)，可与 Phase 0-3 并行

**战略双重定位：**
1. **产品目标**：Sopify develop 后可选触发 CR advisory 审查
2. **战略验证**：Convention 模式（ADR-016）首次实战检验 — LLM 不经 runtime 编排，仅靠 SKILL.md 表单式指令自主调用外部 CLI

**Convention 验证指标**（Phase 4a + 3 项目 dogfood 完成后评估）：
- LLM 是否按 SKILL.md 指令可靠调用 CLI？
- 失败时的 failure mode 分类：忘记调用 / 参数错误 / verdict 处理偏离 / 回退路径不触发
- 3 项目 dogfood 中 Convention 模式成功率
- 是否暴露 Validator (Protocol Step 2) 的真实需求？

**验证结果反馈至 Protocol-first 路线：**
- 成功率高 → Protocol-first 可行，Step 2 维持信号驱动
- 出现系统性偏离 → Step 2 (Validator) 升级为 P1
- 特定 failure mode 暴露 → 定向调整 SKILL.md 格式或 Step 3 优先级

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

默认路径（host-integrated，宿主负责隔离 LLM 调用）：
1. 生成 ReviewPack: `crossreview pack --diff <REF> --intent "{task_summary}" > pack.json`
2. 渲染 prompt: `crossreview render-prompt --pack pack.json > prompt.md`
3. 宿主在 fresh / isolated review context 中执行 `prompt.md`，保存 raw analysis
4. 归一化结果: `crossreview ingest --raw-analysis raw-analysis.md --pack pack.json --model host_unknown --format human`
5. 按 verdict 处理：
   - `pass_candidate` → 继续 finalize
   - `concerns` → 展示 findings，询问用户：修改 / 接受 / 忽略
   - `needs_human_triage` → 请用户判断
   - `inconclusive` → 记录，不阻断

回退路径（standalone verify，仅 reviewer config / API key 已配置时）：
1. `crossreview verify --diff <REF> --intent "{task_summary}" --format human`
2. 读取输出，同上 verdict 处理

注释：`verify --diff` 会由 CrossReview CLI 直接调用 LLM API，不是 Phase 4a 默认宿主集成路径。Phase 4a 默认通过 `render-prompt + ingest` 借用宿主自身 LLM 能力，避免额外 API key / SDK 前置。

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
│  host-agnostic (engine / skill / contract / state)   │
│  · runtime/*.py + .sopify-skills/                    │
├──────────────────────────────────────────────────────┤
│  host-adapter (only this layer may specialize)       │
│  · installer/hosts/*.py                              │
│  · abstraction: HostAdapter + HostCapability +       │
│    HostRegistration                                  │
├──────────────────────────────────────────────────────┤
│  host-prompt (per-host prompt/skill source)          │
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
| 018 | Legacy Surface Retirement | ✅ 活跃 / P1 治理约束 |
| 019 | Payload Bundle Distribution — Thin-Stub + Centralized Runtime | ✅ 活跃 / 已实现 |

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

**ADR-017: Action/Effect Boundary before Materialization** `P0 架构约束（thin slice 已提升）`

Sopify 不维护用户自然语言白名单。自然语言由 host LLM 投影为结构化 ActionProposal；状态推进、写入、checkpoint 消费和风险放行只能由 Core/Validator 基于机器事实授权。**局部语境请求（分析、批判、确认、取消、修订、查看）被 router keyword/complexity classifier 误读为全局推进是通用问题。** 方案包误建是当前最高频症状，不是 Validator 的设计边界。**计划包生成（write_plan_package）是首个受控 side effect，不是唯一关心对象。**

**Pipeline 位置：** ActionProposal 解析和 Effect 授权发生在 State Resolution 之后、Router 产生副作用之前。普通命令前缀请求（`~go`、`~go plan`、`~compare` 等）仍可作为确定性路由，不默认经过 ActionProposal；但需要结构化主体且会写文件的 command alias 不得直达写入，例如 `~go finalize` 必须先映射为 `ActionProposal(action_type="archive_plan")`，再由 Validator 授权。

| 层 | 职责 |
|----|------|
| Host LLM (proposal source) | 将用户输入映射为结构化 ActionProposal，附带 side_effect / confidence / evidence |
| Gate (ingestion) | 接收 `--action-proposal-json`；new host 首次无 proposal 时返回 gate retry contract + schema（不进入 runtime）；legacy host 无 proposal 时 fallback 到现有 router |
| Validator (authorizer) | 基于 ActionProposal + ValidationContext（从 context_snapshot / current_handoff / current_run 投影的 checkpoint_kind / checkpoint_id / stage / required_host_action）授权或降级；输出统一 ValidationDecision（decision / resolved_action / resolved_side_effect / route_override / reason_code）；host LLM 不是授权者 |
| Risk policy | 判断 action/payload/diff/tool input 的风险，不判断用户话术本身 |
| Materializer | 仅在 Validator allow 后写 state / plan / checkpoint |

**ActionProposal schema：**

```yaml
action_type:            # 6 个可识别枚举；P0 只对 consult_readonly 做 route override，side-effecting action 做最小 evidence proof 授权但不接管路由
  - consult_readonly        # 分析/批判/确认/讨论，不产生写入 ← P0 唯一 route override action
  - propose_plan            # 请求生成方案包
  - execute_existing_plan   # 执行已有 plan
  - modify_files            # 直接修改文件（quick_fix / develop）
  - checkpoint_response     # 对当前 checkpoint 的确认/修订/取消
  - cancel_flow             # 取消当前流程
side_effect:            # 5 个 effect 类型
  - none                    # 只读
  - write_runtime_state     # 写 state/*.json
  - write_plan_package      # 创建/修改 plan 方案包
  - write_files             # 修改项目代码文件
  - execute_command         # 执行命令行
confidence: high | medium | low
evidence: ["用户原文中的依据片段"]
```

**Reserved actions（Protocol Step 3 完整化时激活）：**

原 ADR-017 的 9 个 canonical actions 重新分类如下。P0 只对 `consult_readonly` 做 route override；side-effecting action 做最小 evidence proof 授权但不接管路由；其余 action 的显式 schema 化为 reserved，现有 runtime 隐式实现继续运行。

| 分类 | Actions |
|------|---------|
| **Active (P0)** | `consult_readonly`（pre-route interceptor） |
| **Reserved** | `inspect_checkpoint`、`confirm_plan_package`、`revise_plan_proposal`、`submit_decision`、`answer_clarification`、`confirm_execute`、`cancel_checkpoint`、`ask_question` |

字段至少包含 `action_id`、`checkpoint_id/run_id/plan_id`（如适用）、`payload`、`side_effect`、`confidence_band`、`ambiguity_reason`。`confidence_band` 只分 `high / medium / low`；具体数值阈值由 Protocol Step 3 评测后定义，不在 ADR 中写死。

`continue` / `retopic` / `block` 不进入 canonical action 集：`continue` 是确认类 action 的用户表达或 resolved intent；`retopic` 是 `revise_plan_proposal` 的 payload 变体；`block` 是 Validator/Risk policy outcome，不是用户动作。

**Validator 硬规则：**

**Verify 分层定位**：Validator 是 Verify-A（pre-write authorization gate，副作用发生前同步校验）。区别于 Verify-B（post-write execution gate: tests/lint/build，由项目工具链 + Sopify 编排）和 Verify-C（post-produce quality review: CrossReview isolated review，异步可行）。

**Proposal quality 边界**：P0 不解决 ActionProposal 的 source 质量。host LLM 投影可能偏保守或偏激进。P0 安全取舍：fail-close，允许误降级为 consult，不允许误升级为写入。proposal 误降级通过 dogfood 观察，不用关键词补丁修。

1. Validator 基于 ValidationContext 判断当前 context 下 requested action + side_effect 是否允许。不硬编码单个 side_effect 名称为唯一关注对象。
2. `checkpoint_id` / `run_id` / `plan_id` 是否与当前机器事实一致。
3. `side_effect` 是否被当前 response mode 和 checkpoint 类型允许。**`write_plan_package` 是首个受控 side effect，需要 evidence 能正向证明写入意图；evidence 不能证明写入意图就拒绝或降级为 `consult_readonly`。**
4. 风险策略只评估结构化 action、payload、diff、tool input、plan task，不扩展用户话术白名单。
5. 缺字段、低置信度、歧义或状态不匹配时 fail-close：降级为 `consult_readonly` / `inspect_checkpoint` / `ask_question`，或拒绝写入。
6. **Side-effect proof 原则**：Validator 校验 evidence 是否能正向证明 requested side_effect。不列举具体话术词表；判定标准是"evidence 能否证明写入意图"，而非"evidence 是否包含某些特定关键词"。
7. **`fallback_router`** 是 Validator 的"不处理/不授权"态，不是 Router 对副作用的授权。随着 reserved actions 激活，`fallback_router` 覆盖范围预期递减。

**Checkpoint 上方的 consult 行为：**
Checkpoint pending 时，如果新 ActionProposal 为 `consult_readonly` + `side_effect=none`，Validator 输出 `decision=authorize, route_override=consult`，允许返回 `continue_host_consult`，保留原 checkpoint identity（不清状态、不推进、不物化 plan）。P0 验证 `confirm_plan_package` 场景；架构不限于此 checkpoint kind。对应 side_effect_mapping_table 需补齐 `confirm_plan_package` 的 `switch_to_consult_readonly` effect row。

**P0 实现边界（thin slice）：**
- `action_intent.py`：ActionProposal schema + ValidationContext（从现有状态投影的只读 view）+ ValidationDecision + Validator + deterministic fallback adapter（不带 LLM API client）。P0 实现：consult_readonly + none → authorize/consult；side-effecting action + evidence 通过 → authorize, route_override=null（Router 继续路由）；evidence 不足/low confidence → downgrade consult_readonly；未知 action → fallback_router。P0 的 side-effect proof 只证明用户存在明确副作用意图，不替代 response mode、risk policy、execution gate 或项目工具链验证。
- Gate 接收 `--action-proposal-json`；new host 无 proposal 时返回 gate retry contract + schema（不是 runtime checkpoint），host 填充后重试；legacy host 无 proposal 时 fallback 到现有 router。
- `engine.py` `run_runtime()` 加 pre-route interceptor：authorize + route_override=consult → 直接构造 consult route；authorize + route_override=null → 回落现有 Router（Validator 已授权，Router 决定具体路由）；downgrade consult_readonly → consult route；fallback_router → 回落现有 Router。
- Router 签名和 52 个测试不改。
- Host prompt 只加一条规则：当 gate contract 包含 `action_proposal_schema` 时，按 schema 生成 ActionProposal 并重试 gate。完整 schema 由 gate contract 动态返回，不嵌入 prompt。
- 现有 `analysis_only_no_write_brake`、`plan_meta_review`、`analyze_challenge`、`explain_only_override` 标为 legacy compatibility path，P0 不提前删；P0-G 测试通过 + 1 轮 dogfood 后由子方案包 P0-H 按 ADR-018 清理。

少量确定性信号保留为硬刹车：显式 no-write / 只分析、cancel / stop、数字选项。它们不是完整意图识别面，不能演化为维护用户习惯白名单。

Protocol Step 3 需要补齐最小协议面：`action_schema_version`、`supported_actions` capability（区分 active / reserved）、以及最小 `action_audit` 事件（记录 proposed_action / validator_decision / reason_code / side_effect）。不提前定义完整 `action_audit.jsonl` schema。

**Knowledge accumulation 原则**：dogfood / action audit 是 P1 观测能力的基础；P0 期间如有手工记录，仅记录 raw，不做 promotion。分层：raw record → candidate insight → accepted fixture/rule/blueprint。candidate → accepted 先由人工确认。对 Produce 的优先反哺方式不是追加 prompt 规则，而是删旧规则、精简提示、更新 blueprint 中的高信号事实。

**优先级变更：** 原 P1 → **P0 thin slice**。只激活 `consult_readonly` pre-route 拦截，解决局部语境请求被误读为全局推进的最高频症状（分析/批判类请求被误建方案包）。Validator 接口从设计上是 checkpoint-aware 的（输入 ActionProposal + ValidationContext，输出统一 ValidationDecision）。P0 实现：`consult_readonly + none → authorize/consult`；side-effecting action 做最小 evidence proof（通过 → `authorize, route_override=null`，Router 继续路由；不通过 → `downgrade consult_readonly`）；未知 action → `fallback_router`。完整 action system（Protocol Step 3 全部 action 激活）仍为 P1。实现方案包：`20260428_action_proposal_boundary/`。

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
| Action schema 过早变成 runtime feature | 中 | 中 | P0 thin slice 只激活 `consult_readonly` pre-route 拦截，不做完整 action system；完整 schema 化仍为 Protocol Step 3 |
| ActionProposal "守卫检查自己" | 中 | 低 | host LLM 是 proposal source 不是 authorizer；Validator evidence-action 一致性检查 + confidence=low 默认 consult_readonly |
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

不能说明的默认不进入 P0/P1 主线。Knowledge 反哺 Produce 的默认方式不是追加 prompt 规则，而是删除被验证替代的旧规则、精简宿主提示、更新高信号 blueprint；不能说明替代关系的知识沉淀不得进入 P0/P1 主线。

**预算覆盖 4 类：**

| 类别 | 当前值 | 说明 |
|------|--------|------|
| state files | 7 | `current_{clarification,decision,gate_receipt,handoff,plan,plan_proposal,run}.json` |
| helper entrypoints | 22 | `scripts/*.py` |
| host actions | 8 × 28 sub-actions | `_HOST_ACTION_ALLOWED_ACTIONS` |
| prompt/runtime rules | 24+ | 系统提示 C3 节"说明"条数 |

当前值仅作基线参考，不作为硬上限。ADR-017 Step 3 完成后由 T-P3-5b (Protocol Slim Audit) 重新评估。

---

## §10 ADR-019: Payload Bundle Distribution — Thin-Stub + Centralized Runtime `已实现`

### 决策

项目本地只保留 thin-stub（`manifest.json`，8 个字段），完整 runtime 集中管理在宿主全局 payload 中。用户首次接入时 bootstrap 全自动，后续使用透明刷新。

### 理由

| 问题 | 替代方案 | 决策 |
|------|---------|------|
| N 个项目各复制一份 ~28K 行 runtime | 每项目全拷贝 | 零拷贝 thin-stub，N 项目共享 1 份 runtime |
| runtime 更新需逐项目手动同步 | 每项目独立版本 | 全局 payload 单点更新，下次触发自动传播 |
| `.sopify-runtime/` 污染项目 git | 不管 gitignore | bootstrap 自动管理 `.git/info/exclude` 或 `.gitignore` |
| 首次使用需手动配置 | 要求用户先安装 | `~go plan` 触发即自动 bootstrap，零配置 |

### 架构

**三层分发：**

```
installer/payload.py ────── 全局 payload 安装 (一次)
  └─ bundles/{version}/ ─── 版本化 runtime 存储

installer/bootstrap_workspace.py ─── 项目 bootstrap (首次自动)
  └─ .sopify-runtime/manifest.json ── thin-stub (8 字段)

runtime/manifest.py ────── bundle manifest 生成 (capabilities, limits, entries)
```

**Stub 契约 (`.sopify-runtime/manifest.json`)：**

| 字段 | 值 | 用途 |
|------|-----|------|
| `schema_version` | `"1"` | 兼容性门控（不匹配 → fail closed） |
| `stub_version` | `"1"` | stub 格式版本 |
| `bundle_version` | `"2026-04-24.154241"` | 指向全局 bundle 版本 |
| `required_capabilities` | `["runtime_gate", "preferences_preload"]` | stub 最低能力要求 |
| `locator_mode` | `"global_first"` | runtime 发现策略 |
| `legacy_fallback` | `false` | 是否允许 legacy 回退 |
| `ignore_mode` | `"exclude"` | gitignore 管理方式 |
| `written_by_host` | `true` | 标记由 host installer 写入 |

### 版本兼容不变量

1. **向前兼容**：workspace stub 版本 > 全局 → `NEWER_THAN_GLOBAL` 状态 → 不降级，保持 workspace 版本
2. **向后兼容**：schema_version 门控 + 能力协商 → 匹配则继续，不匹配 fail closed
3. **Stub 扩展性**：新字段只加在全局 bundle manifest 侧，stub 格式不变，旧 stub 不受影响
4. **Legacy 回退**：`locator_mode=global_first + legacy_fallback=true` 允许降级到本地遗留 artifacts；`global_only` 禁止（代码强制互斥校验）
5. **原子写入**：所有 manifest 更新经 `NamedTemporaryFile` + `Path.replace()`，中断不损坏
6. **版本比较**：semver-like 算法，支持 `dev < alpha < beta < rc < release` prerelease rank

### 首次写入安全策略

| 层 | 机制 | 行为 |
|----|------|------|
| Brake layer | 用户输入含"先分析/不要改/explain-only" | 拒绝 bootstrap 写入 |
| Blocked commands | `~compare/~go exec/~go finalize` 在未激活 workspace | 拒绝 |
| Confirm commands | `~go init` | 授权 bootstrap + 根目录确认 |
| Allowed commands | `~go/~go plan` | 直接授权 bootstrap |
| Non-interactive | 非交互式 session | 拒绝，要求交互式 |
| Root disambiguation | workspace ≠ git root 时 | 提示用户选择激活目录 |

### 后续 ADR 接入约束

**所有后续 ADR 实现前必须通过以下检查：**

1. **零配置保证**：新特性不得要求用户在首次使用前做任何手动配置。需要配置的必须有合理默认值，或由 bootstrap 自动完成。
2. **Stub 向后兼容**：如需在 stub manifest 新增字段，旧 stub 必须在缺少该字段时仍能正常工作（字段可选 + 默认值降级）。
3. **能力协商约束**：如需新增 `required_capability`，这是 breaking change，必须同时升 `schema_version` 并考虑迁移路径。
4. **Ignore policy 覆盖**：如在 `.sopify-runtime/` 内写入新类型文件，须确认已被 ignore policy 覆盖。
5. **首次写入安全**：新命令必须分类到 allowed/blocked/confirm 之一，不得绕过 `_authorize_first_workspace_write()`。

### 与其他 ADR 的协同

- **ADR-007 (多宿主)**：payload 路径由 `HostAdapter.payload_root()` 决定，不同宿主不同根。bootstrap 逻辑宿主无关。
- **ADR-016 (Protocol-first)**：Convention 模式下 stub 只需 `runtime_gate` + `preferences_preload` 两个 capability，不需要完整 runtime。
- **ADR-018 (Legacy Retirement)**：旧版本 workspace bundle 的 `legacy_fallback` 机制即是 sunset → removed 流程在分发层的投影。
- **§9 Complexity Budget**：stub 8 个字段计入 protocol 预算；新增字段必须经 §9 审查。

### 代码实现索引

| 文件 | 关键函数/常量 |
|------|-------------|
| `installer/payload.py` | `install_global_payload()`, `_REQUIRED_BUNDLE_CAPABILITIES` (13 项) |
| `installer/bootstrap_workspace.py` | `bootstrap_workspace()`, `_authorize_first_workspace_write()`, `_classify_workspace_bundle()`, `_write_workspace_stub_overlay()`, `_compare_versions()` |
| `installer/runtime_bundle.py` | `sync_runtime_bundle()`, `DEFAULT_BUNDLE_DIRNAME = ".sopify-runtime"` |
| `installer/validate.py` | `validate_payload_install()`, `validate_workspace_stub_manifest()`, `_STUB_REQUIRED_CAPABILITIES` |
| `runtime/manifest.py` | `BundleManifest`, `build_bundle_manifest()`, `MANIFEST_SCHEMA_VERSION = "1"` |
| `installer/models.py` | `FeatureId.WORKSPACE_BOOTSTRAP`, `FeatureId.PAYLOAD_INSTALL` |

优先级：已实现。作为不变量约束所有后续 ADR。
