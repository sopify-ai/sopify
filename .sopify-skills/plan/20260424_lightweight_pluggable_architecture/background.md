# Background: Sopify 轻量化可插拔架构

> **战略方向 (2026-04-26)**：Sopify 已确认 Protocol-first / Runtime-optional 方向。核心价值层定位为 `.sopify-skills/` 文件协议和 schema，runtime 降级为可选增强层与参考实现。详见 design.md §1.2 及 ADR-016。

## 产品定位

### 战略定位 (ADR-013)

**Sopify 是 AI 编码助手里的自适应工作流与状态交接系统。**

它按任务复杂度推进 AI 编程流程，让关键决策可追踪、产出质量可验证，并把计划、审查和历史沉淀为项目资产。

架构上，Sopify 是 AI 编程工作流的 control plane —— 不与宿主（Claude Code / Codex / Cursor）竞争执行层，不与 Superpowers 竞争技能分发，不与 Spec-Kit 竞争方法论。

Sopify 的核心价值是让 AI 编程工作流 **自适应推进、状态可交接、质量可验证、资产可沉淀、流程可策略管控**。

| 不做 | 做 |
|------|------|
| 执行代码（宿主负责） | 裁决工作流状态转移（gate → checkpoint → handoff） |
| 分发技能（Superpowers 等） | 策展集成优质工具，定义 plugin contract |
| 定义方法论（Spec-Kit 等） | 提供结构化框架，承载 spec-driven workflow |
| 与竞品做功能对比 | 提供开放协议，被竞品集成或集成竞品 |

**在 Sopify 生态矩阵中的定位：**
- **sopify-skills**: AI 编程自适应工作流、状态交接与质量治理层 ← 本产品
- **cross-review**: 独立验证 / 质量 gate（高价值默认 plugin，不是核心大模块）
- **graphify**: 项目理解 / 蓝图知识图谱（高价值默认 plugin）
- **helloagents / hermes-agent**: 执行层实验 / agent runtime
- **superpowers / spec-kit**: 外部生态参照物

### 用户感知定位

**Sopify 是运行在 AI 编码助手内部的自适应工作流系统。**

默认 analyze / design / develop 流程是开箱即用体验入口，不是核心护城河。核心护城河是自适应推进、状态交接、质量治理、项目资产沉淀和权限边界。

| 特性 | 说明 |
|------|------|
| **开箱即用** | 安装即可用，默认配置即提供完整工作流；这是体验策略，不是核心定位 |
| **自适应推进** | 按任务复杂度选择快速修复、轻量迭代或完整方案流程 |
| **结构化工作流** | 需求分析 → 方案设计 → 开发实施 → 归档，可沉淀可复用 |
| **机器契约** | handoff / checkpoint / gate / plan schema，确定性保障 |
| **质量验证** | gate / pipeline_hooks / CrossReview 等机制让关键执行和产出审查可验证 |
| **项目资产沉淀** | plan / review / history / blueprint 让计划、审查和历史可追踪、可复用 |
| **集成优质工具** | graphify（蓝图初始化）、cross-review（代码评审）等，默认按需启用/可配置关闭 |
| **多宿主** | 同一内核优先跑在 Claude Code / Codex，QCoder / Copilot 走调研接入，retired legacy host surface 已按 ADR-018 退出活跃目标 |
| **轻量可插拔** | 内核精简，工具以 plugin 形式接入，维护者可低成本集成新工具 |

**用户感知层：**
- 入门感知：任务步骤更清楚，AI 不乱跳，当前进度可见。
- 进阶感知：可以暂停恢复、复用计划、追踪决策、沉淀历史。
- 团队感知：可以审计、治理、接入质量门禁、跨工具协作。

这三层不是不同产品线，而是同一套机制的不同感知层。普通用户不需要理解框架内部；高级用户可通过 `sopify.config.yaml` 深度定制；Sopify 维护者通过 plugin contract 集成新工具。

**"策展集成"模式：** 用户不需要自己写 plugin——好用的工具由 Sopify 团队筛选集成好，用户只管开关。这是运营模式的选择，不影响框架级别的技术架构（ADR-008）。

## 起因

用户明确提出：将 Sopify 做成可插拔的 AI 编程框架，支持 graphify、cross-review 等外部 skill 以插件形式接入，同时保留 Sopify 的核心机制（plan 方案包、机器契约、gate 入口、归档体系）。

关键约束：不是重构，而是**轻量化** —— 只保留核心链路和机制，释放冗余编排逻辑。

## 调研范围

### 1. Sopify 当前架构深度分析

#### 1.1 Runtime 层全景

| 模块 | 文件 | 行数 | 核心职责 |
|------|------|------|---------|
| 入口守卫 | `gate.py` | 736 | 严格入口校验、偏好注入、workspace preflight |
| 路由器 | `router.py` | 1,251 | 确定性路由分类，18 种路由，正则命令匹配 |
| 引擎 | `engine.py` | **2,982** | 全流程编排（**单体，问题核心**） |
| 技能发现 | `skill_registry.py` | 251 | SKILL.md + skill.yaml 多级搜索发现 |
| 技能解析 | `skill_resolver.py` | 112 | 声明式 route-to-skill 解析 |
| 技能执行 | `skill_runner.py` | 86 | Python 模块调用约定 |
| 技能 schema | `skill_schema.py` | 141 | skill.yaml 标准化与校验 |
| 状态管理 | `state.py` | 502 | 文件系统状态读写 |
| 交接契约 | `handoff.py` | 630 | current_handoff.json 构建 |
| 检查点 | `checkpoint_request.py` | 478 | 统一 checkpoint contract |
| 检查点物化 | `checkpoint_materializer.py` | ~200 | checkpoint → state 写入 |
| 决策系统 | `decision.py` + `decision_tables.py` + `decision_bridge.py` + `decision_policy.py` + `decision_templates.py` | 2,800+ | 完整决策分叉管理 |
| 澄清系统 | `clarification.py` + `clarification_bridge.py` | ~600 | 事实补充管理 |
| 执行门控 | `execution_gate.py` + `execution_confirm.py` | ~400 | 开发前确认 |
| Plan 管理 | `plan_scaffold.py` + `plan_registry.py` + `plan_proposal.py` + `plan_orchestrator.py` | 1,500+ | 方案包生命周期 |
| 配置 | `config.py` | 269 | sopify.config.yaml 加载 + 校验 |
| 数据模型 | `_models/` (6 文件) | 1,715 | 核心数据结构定义 |
| Replay | `replay.py` | 469 | 回放记录 |
| 知识库 | `kb.py` + `knowledge_layout.py` + `knowledge_sync.py` | ~500 | KB 初始化与同步 |
| Context | `context_builder.py` + `context_snapshot.py` + `context_recovery.py` + `context_v1_scope.py` | ~500 | 上下文压缩与恢复 |
| 输出 | `output.py` | 802 | 格式化输出生成 |
| 安装器 | `installer/` (8 文件) | — | bootstrap + bundle 分发 |
| Manifest | `manifest.py` | 484 | bundle manifest 生成 |
| 总计 | runtime/ 全部 | **~26,658** | — |

#### 1.2 Engine.py 函数分析 (72 个函数)

```
类别                     函数数   估算行数   是否应留在 engine
──────────────────────────────────────────────────────────────
入口 run_runtime           1      ~553      ✅ 瘦身保留
Checkpoint handler:
  _handle_clarification    1       94       ⚠️ 移出
  _handle_decision         1      126       ⚠️ 移出
  _handle_proposal         1      155       ⚠️ 移出
  _handle_execution_confirm 1     202       ⚠️ 移出
  _resume_from_develop_*   2      ~140      ⚠️ 移出
Plan 操作:
  _advance_planning_route  1      242       ⚠️ 移出
  _resolve_plan_for_request 1      89       ⚠️ 移出
  plan helper 函数         ~8     ~170       ⚠️ 移出
State/conflict/cancel:
  _handle_cancel_active    1       16       ⚠️ 移出
  _handle_state_conflict   1       37       ⚠️ 移出
  _resolve_execution_state 1       41       ⚠️ 移出
  _promote_review_state    1       48       ⚠️ 移出
  state helper 函数        ~8     ~250       ⚠️ 移出
Run state 管理:
  _make_run_state          1       27       ✅ 保留
  _make_*_run_state        3       ~90      ✅ 保留
  _set_execution_run_state 1       12       ✅ 保留
Route dispatch helper:
  _*_route                 6      ~200      ✅ 保留
Activation/handoff:
  _build_skill_activation  1       25       ✅ 保留
  _activation_target       1       27       ✅ 保留
  _find_skill              1        7       ✅ 保留
Replay/KB/output:
  replay 写入              ~3     ~100      ✅ 保留
Snapshot helper:
  _snapshot_*              4       ~30       ✅ 保留
```

#### 1.3 内置 Skill 分析

7 个内置 skill，全部在 `runtime/builtin_skill_packages/` 下：

| Skill | Mode | 实际行为 |
|-------|------|---------|
| `analyze` | workflow | SKILL.md prompt 被 LLM 读取，engine 控制阶段转移 |
| `design` | workflow | 同上 |
| `develop` | workflow | 同上 |
| `kb` | workflow | 同上 |
| `templates` | workflow | 同上 |
| `model-compare` | **runtime** | 唯一的 runtime skill，通过 `run_skill()` 执行 Python |
| `workflow-learning` | workflow | SKILL.md prompt |

**关键发现：** `workflow` 模式的 skill 实际上是 "无执行体的 prompt"。真正的编排逻辑全在 engine.py 里硬编码。这意味着外部 skill 无法通过声明式方式参与工作流 —— 它们必须修改 engine。

#### 1.4 Skill 发现机制 (已有，设计良好)

搜索路径（优先级从高到低）：
1. `.agents/skills/` (workspace)
2. `.gemini/skills/` (workspace)
3. `skills/` (project)
4. `.sopify-skills/skills/` (workspace, legacy)
5. `~/.agents/skills/` (user)
6. `~/.gemini/skills/` (user)
7. `~/.codex/skills/` (user)
8. `~/.claude/skills/` (user)

每个 skill 目录需要 `SKILL.md`（必须）+ `skill.yaml`（可选但推荐）。

已有的 skill.yaml 字段：
- `id`, `name`, `description`, `mode`
- `runtime_entry` — Python 模块路径
- `supports_routes` — 声明支持哪些路由
- `triggers` — 语义触发关键词
- `tools`, `disallowed_tools`, `allowed_paths`
- `host_support` — 宿主兼容限制
- `permission_mode`, `override_builtin`
- `metadata` (含 `priority`)

Skill resolver (`skill_resolver.py`) 使用声明式 `supports_routes` 做路由解析，有优先级排序。

### 2. Claude Code 架构对比分析

#### 2.1 核心设计哲学

| 维度 | Claude Code | Sopify |
|------|-------------|--------|
| **编排者** | LLM（无 engine.py） | Python runtime (engine.py 2982 行) |
| **Skill 定义** | SKILL.md + frontmatter | SKILL.md + skill.yaml |
| **Skill 执行** | SkillTool 分发，LLM 读 prompt 执行 | engine 硬编码阶段逻辑 |
| **状态管理** | 几乎无状态 | 完整文件系统状态 (state/) |
| **机器契约** | 无 | handoff.json, checkpoint, plan schema |
| **Plugin 体系** | `registerBundledSkill()` + marketplace | 只有 skill 发现，无安装管理 |
| **Agent 体系** | AgentTool fork 独立上下文 | 无 sub-agent |

#### 2.2 Claude Code 的 Skill 系统

**BundledSkillDefinition** (TypeScript):
```typescript
type BundledSkillDefinition = {
  name: string
  description: string
  allowedTools?: string[]
  model?: string
  context?: 'inline' | 'fork'
  getPromptForCommand: (args, context) => ContentBlockParam[]
}
```

注册方式：`registerBundledSkill(definition)` → 启动时注册到 registry → SkillTool 调用时查找并执行。

**关键发现：** Claude Code 的 skill 是 "prompt 工厂" —— 每次调用时动态生成 prompt，LLM 读后自主执行。没有 Python/TS 来控制执行流程。

**AgentTool** (Claude Code 的 sub-agent):
- `GENERAL_PURPOSE_AGENT` — 全能力 agent
- `EXPLORE_AGENT` — 只读探索 agent
- `PLAN_AGENT` — 规划 agent
- 每个 agent fork 独立上下文窗口

这给 Sopify 的启示：Sopify 不需要 agent 体系（太重），但可以借鉴 "LLM 自编排" 的理念。

#### 2.3 Claude Code 的 Plugin 体系

**BuiltinPluginDefinition**:
```typescript
type BuiltinPluginDefinition = {
  name: string
  description: string
  defaultEnabled?: boolean
  skills?: BundledSkillDefinition[]
  hooks?: HooksSettings
  mcpServers?: Record<string, McpServerConfig>
  isAvailable?: () => boolean
}
```

Plugin = skills + hooks + MCP servers 的集合。可通过 `/plugin` UI 启用/禁用。

**启示：** Sopify 不需要 hooks 和 MCP servers，但 "plugin = skill + 元数据 + 可选 runtime" 的模型值得借鉴。

#### 2.4 可借鉴的设计原则

1. **"LLM 即编排器"** — Python/TS 只做确定性保障，不替 LLM 做流程决策
2. **"Skill = prompt 工厂"** — skill 产出 prompt，不控制执行流程
3. **"注册模式"** — 启动时注册，运行时查找，不硬编码
4. **"Feature flag 渐进发布"** — `feature('COORDINATOR_MODE')` 保护新功能
5. **"最小接口"** — `getPromptForCommand(args, context)` 是唯一必需方法

### 3. 外部项目接入分析

#### 3.1 Cross-Review

当前结构：
```
crossreview/
├── __init__.py
├── adjudicator.py    # 裁决器
├── budget.py         # 预算管理
├── cli.py            # CLI 入口
├── config.py         # 配置
├── core/             # 核心逻辑 (prompt.py)
├── ingest.py         # 数据摄入
├── normalizer.py     # 标准化
├── pack.py           # 打包
├── reviewer.py       # 评审器
├── schema.py         # Schema 定义
└── verify.py         # 校验
```

作为 Sopify plugin 接入方案：
- `bridge.py` 包装 `reviewer.py` + `adjudicator.py` 调用
- 输入：plan package (design.md + tasks.md)
- 输出：review-result.json + findings report
- 触发点：`after_design` pipeline hook（design 生成后自动触发评审）
- Checkpoint：如果有 critical findings → 触发 decision checkpoint

#### 3.2 Graphify

当前结构：
```
graphify/
├── analyze.py     # 分析
├── build.py       # 构建
├── cluster.py     # 聚类
├── detect.py      # 检测
├── export.py      # 导出
├── ingest.py      # 摄入
├── serve.py       # 服务
├── skill.md       # 已有 skill prompt!
├── watch.py       # 监听
└── wiki.py        # Wiki 生成
```

作为 Sopify plugin 接入方案：
- 无需 `bridge.py` — graphify 有独立 CLI，LLM 可直接调用
- `SKILL.md` 已经存在 (`graphify/skill.md`)，只需迁移到标准 skill 目录
- 模式：advisory（纯 prompt 指导）
- 触发：`/graphify` 或语义触发

#### 3.3 Spec-Kit

```
spec-kit/
├── src/           # 核心源码
├── extensions/    # 扩展
├── integrations/  # 集成
├── templates/     # 模板
├── workflows/     # 工作流
└── presets/       # 预设
```

潜在接入方式：
- 作为 Sopify 的 "模板提供者" plugin
- 可以提供 plan package 模板
- 需要进一步分析具体接口

## 核心发现总结

1. **Engine 单体是唯一的结构性瓶颈** — 不是重构，是拆分。把 engine 从 2982 行拆到 ~500 行 + 3 个子模块，行为完全不变。

2. **Skill 有能力自包含** — 当前 `workflow` 模式 skill 只有 prompt，编排逻辑硬编码在 engine。如果 SKILL.md 里写清楚 "何时触发 checkpoint"，engine 就不需要知道具体阶段逻辑。

3. **Plugin 接口已有 80% 基础** — skill 发现机制、skill.yaml schema、skill_runner 都已就绪。只需要：(a) 扩展 skill.yaml 增加 `pipeline_hooks` / `inputs` / `outputs`，(b) 标准化 bridge.py 接口。

4. **Sopify 的差异化价值在 contract 层** — gate、handoff、checkpoint、plan schema 是 Claude Code 没有的。轻量化不能动这些。

5. **Claude Code 的 "LLM 即编排器" 是正确的方向** — 但 Sopify 不应完全照搬（因为 Sopify 需要确定性保障）。正确的平衡是："LLM 做编排判断，Python 做持久化保障"。

---

## 总纲定位与子任务包体系

### 本方案包的定位

本方案包（`20260424_lightweight_pluggable_architecture`）是 Sopify 项目当前的**总纲方案包**，统一管辖以下相关子任务包。所有活跃子任务包的方向必须服务于或不阻碍总纲目标；sunset 子任务包按 ADR-018 进入清理链路。

总纲目标：Sopify 从 "runtime 编排一切" → "runtime 只做 gate + state + contract，LLM 读 skill 自编排"，同时保证多宿主原生支持（Claude Code / Codex ✅ 深度验证；QCoder / Copilot 📋 待调研；retired legacy host surface 已归档）。

### 子任务包映射

| 子任务包 | 方案包 ID | Phase 归属 | 关系 |
|---------|----------|-----------|------|
| 检测层结构化 | `20260417_risk_engine_upgrade` | Phase 0.1 | 前置基础改善 |
| 感知层精度 | `20260417_ux_perception_tuning` | Phase 0.2 | 前置基础改善 |
| CrossReview v0 核心 | `20260418_cross_review_engine` | Phase 4 前置依赖 | 独立产品线，并行推进 |
| Blueprint Graphify 增强 | `20260416_blueprint_graphify_integration` | Phase 5 基础设施 | 增强器架构，并行推进 |
| Legacy host adapter | archived legacy host adapter plan | 多宿主扩展 | ADR-018 sunset；归档经验，不再作为 Phase 3 验证环境 |

### 旧总纲残余吸收

旧总纲（`20260326_phase1-2-3-plan`）的已完成和未完成子 plan 按以下方式处理：

| 旧总纲子 plan | 状态 | 处理 |
|-------------|------|------|
| Plan H (状态机 Hotfix, `20260327_hotfix`) | ✅ 已完成归档 | 不变 |
| Plan B1 (全局 bundle, `20260326_5-plan...`) | ✅ 已完成归档 | 不变 |
| Plan A (风险自适应打断, `20260403_plan-a...`) | ✅ 已完成归档 | `20260417_risk_engine_upgrade` 是其检测层的自然延续 |
| Plan D (文档) | ❌ 未启动 | → 吸收入本总纲 Phase 6 (文档与示例) |
| Plan B2 (Ghost State) | ❌ 未启动 | → 吸收入本总纲 Phase 1 (engine 拆分) + Phase 2 (skill 自包含)。核心目标"减少 runtime 状态控制"被 engine 瘦身自然解决 |
| Plan C (Side task) | ❌ 未启动 | → 吸收入本总纲 Phase 2。Skill 自包含后 LLM 天然支持 bounded side task，无需 suspend/resume 状态机 |
| Plan B3 (Ghost Knowledge) | ❌ 显式延后 | → 继续延后；若需启动，纳入 Phase 2 skill 自包含的扩展范围 |

### 子任务包方向一致性对齐

#### Phase 0.1: `20260417_risk_engine_upgrade` — 检测层结构化

与总纲方向：✅ 强一致
- RiskRule dataclass 替代 tuple-of-tuples → 是"结构化保障"层面的改善
- scan_scope 引入上下文感知 → 降低误报率 → 减少不必要的 checkpoint 打断 → 服务于"LLM 更顺畅地自主编排"
- 改动范围仅 `execution_gate.py` ~180 行 → 不影响 engine 拆分
- 约束：`gate_status` 值集不变，`ExecutionGate` 对外接口不变

#### Phase 0.2: `20260417_ux_perception_tuning` — 感知层精度

与总纲方向：✅ 一致
- A (Blueprint 可见化) → Phase 2 前奏：让 LLM 通过 handoff artifacts 感知 blueprint 状态，是 skill 自包含的信息基础
- B (Router 精度) → Phase 1 配套：engine 瘦身后 router 承担更多分流职责，精度必须先到位
- C (输出瘦身) → Phase 2 配套：减少 runtime 对输出的控制，为 skill 自主管理输出铺路
- 约束：不改 engine.py 执行路径，不改机器契约
- ⚠️ B 部分 router 修正属于旧总纲 Plan A 的 V1.x 精度微调范围（parser-first 路线），不是 V2 classifier 方向。如果后续需要更深的 router 改造，需要单独评估是否符合旧总纲 4.16 冻结的切片边界

#### Phase 4 前置: `20260418_cross_review_engine` — v0 产品核心

与总纲方向：✅ 强一致
- CrossReview 被设计为独立产品（独立仓库、独立 Python 包） → 天然符合 "plugin = 独立产品 + Sopify 封装" 模式
- v0 scope 已确认 context isolation 为核心价值 → 不依赖 Sopify engine 内部状态
- 可以与 Phase 0-3 完全并行推进
- ⚠️ Phase 4 (plugin 封装) 需要等 Phase 3 (plugin 接口) 和 CrossReview v0 的 pack + reviewer 模块都就绪

#### Phase 5 基础: `20260416_blueprint_graphify_integration` — 增强器架构

与总纲方向：✅ 一致但维度不同
- 20260416 是 graphify 作为 blueprint "自动增强器"（build 时扫描代码生成结构图）
- Phase 5 是 graphify 作为 Sopify "可调用 skill"（用户按需调用）
- 两者互补：20260416 提供自动化基础设施，Phase 5 提供用户面能力
- 可以独立推进，不依赖 engine 拆分

#### 独立线: archived legacy host adapter — Retired Surface

与总纲方向：✅ 已按 ADR-018 降级
- 宿主适配层（installer, hosts adapter）独立于 engine/skill 层
- retired legacy host 从活跃多宿主目标降为 sunset surface，不再作为 Phase 3 验证环境
- 既有适配经验归档到 history/，作为后续 HostAdapter / HostCapability / HostRegistration 的历史参考
- 后续目标宿主优先 QCoder、GitHub Copilot，调研后各自独立立项
- 每个新宿主适配参考三层抽象 (HostAdapter + HostCapability + HostRegistration)
- 不阻塞任何 Phase；Phase 3 的 `host_support` baseline 为 Claude + Codex
- ⚠️ QCoder / Copilot 的全局配置目录、规则注入方式、技能发现路径需要在适配前做调研

---

## 外部参考与吸收登记

> 按 design.md §1.3 外部思想吸收原则，此处记录外部产品 insight、三层归类和不进 core 的理由，避免同一想法反复被重新发现。

| 产品 | 可借鉴 insight | 归类 | 吸收方式 | 为什么不进 core / 边界 |
|------|--------------|------|---------|------------------------|
| Git | plumbing vs porcelain 分层；小内核 + 约定 + 长期稳定 | Core Protocol inspiration | 影响 Protocol-first 三层定位 | Sopify 不做 VCS，只学小内核和长期稳定约定 |
| Terraform | State 文件是核心价值；provider 可插拔 | Core Protocol inspiration | 影响 state / plugin manifest 设计 | Sopify 不做 IaC，provider 模型只转化为 plugin 边界 |
| Rails | Convention over Configuration | Core Protocol inspiration | 影响 `.sopify-skills/` 目录约定 | Sopify 不做 Web 框架，只保留约定优先原则 |
| Linear | 状态极简；不做全功能项目管理 | Inspiration Only | 影响概念预算约束 | Sopify 不做 issue tracker |
| GitHub Actions | 可组合 pipeline；YAML 声明式 | Curated Plugin inspiration | 部分影响 `skill.yaml` 和 hooks 默认关闭 | Sopify 不做 CI/CD，pipeline 只能作为 plugin/runtime 增强 |
| Claude Code | prompt as orchestrator；skill 发现 | Curated Plugin inspiration | 影响 ADR-002 和 advisory skill 形态 | Sopify 不做 agent runtime，只消费宿主能力 |
| Spec-Kit | spec-driven development constraint | Inspiration Only | 作为 plan/schema 约束参考 | Sopify 不做方法论产品 |
