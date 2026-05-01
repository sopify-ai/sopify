# Design: Host Prompt Governance

> **定位**：`blueprint/design.md` 基线的独立治理包（原属 `20260424_lightweight_pluggable_architecture`，已删除）。
> **前置**：`20260428_action_proposal_boundary` P0 完成后暴露 4×510 行 prompt 的三层重复维护成本。
> **目标**：建立 prompt 作为 runtime contract 适配层的治理体系，实现渐进式披露，瘦身至核心层 ≤120 行 / 全量 ≤280 行，沉淀工程原则。

---

## 痛点分析

### P1 — 三重重复 (核心问题)

Gate/handoff 协议在 CLAUDE.md 中展开 3 次：

| 位置 | 行数 | 内容 |
|------|------|------|
| C3 说明块 (lines 142-158) | ~17 行 | gate 条件 + handoff dispatch 逐条展开 |
| 宿主接入约定 (lines 316-348) | ~32 行 | 同一协议换个角度重述 |
| 快速参考 mega-paragraph (line 503) | ~1 行(≈50 行压缩) | 第三次全量重述 |

**~100 行说同一件事：** gate → check 4 conditions → dispatch by required_host_action。

### P2 — 全量 dump (无渐进式披露)

对比参照：andrej-karpathy-skills CLAUDE.md 66 行 4 原则。核心哲学：
- **"If you write 200 lines and it could be 50, rewrite it"**
- 每条规则通过 "删掉后行为是否真的变化" 测试
- 不为假设场景写规则，不为不可能的错误写防御

当前 511 行里 A2 工具映射、A3 平台适配、runtime helper 路径表等，90% 请求根本用不到但每次占满 context window。

### P3 — CN/EN 同步靠人工

4 个 variant (Claude CN/EN, Codex CN/EN) 各 ~510 行，人工 diff 同步。pre-commit sync check 只验证对齐，不从单一源生成。

### P4 — 与 ADR-016 不对齐

ADR-016 确立 Protocol-first / Runtime-optional 三层架构。prompt 应体现这个分层，不应把 runtime 实现细节（helper 路径、gate 内部行为）和 protocol 层（目录约定、方案包结构）平铺在一起。

---

## 底层哲学

> **参见 [`blueprint/design.md` § 底层哲学](../../blueprint/design.md#底层哲学)**
>
> 3 条核心哲学（Loop-first / Wire-composable / Surface-shared）已沉淀至总纲。
> 本包的每条 prompt 工程原则都服务于这 3 条哲学中的至少一条——哲学是根基，prompt 是适配层。

---

## 外部项目启示

> 以下遵循总纲 [Design Influence Intake Gate](../../blueprint/design.md#design-influence-intake-gate) 三级准入。
> 每条标注 tier / 来源 / 哲学映射 / 验证路径。

### 应该学的

| 来源 | 启示 | Tier | 哲学映射 | 验证路径 |
|------|------|------|---------|---------|
| OpenSpec | **Schema-driven 模板外置**: `schema.yaml` + `templates/*.md`，改模板不改代码 | **T0 Reference** | Wire-composable | Layer 2 迁到 SKILL.md 可行性待 Phase 2 验证；当前无方案包承接模板外置本身 |
| OpenSpec | **Delta-based 增量语义**: ADDED/MODIFIED/REMOVED 描述变更 | **T0 Reference** | Surface-shared | `~go finalize` delta merge 未排期，需独立方案包设计后验证 |
| OpenSpec | **Progressive Rigor**: Lite spec / Full spec 按需分级 | **T1 Adoption** | Loop-first | 已有 Layer 0-3 设计（本包 Phase 2）；复杂度分级决定验证深度的映射可在实现时验证 |
| OpenSpec | **config.yaml rules 分域**: 按 artifact 类型设置规则 | **T0 Reference** | Loop-first | 纯设计灵感，无方案包承接 |
| andrej-karpathy-skills | **66 行 4 原则，每条通过删除测试** | **T1 Adoption** | 全部 | 已写入工程原则 #3；Phase 1 审计即为验证——每行 prompt 通过删除测试 |

### 明确不学的

| OpenSpec 特性 | 不学的原因 |
|--------------|----------|
| "fluid not rigid" 无门控 | Sopify 的 gate/checkpoint 是有意的确定性边界，是核心差异化 |
| Actions 完全放开不 lock phases | Sopify 需要在高风险操作上 lock phases (执行确认、decision 拍板) |
| 无跨 session 接力 | OpenSpec 不考虑这个；Sopify 的 Wire-composable 已解决 |
| 无隔离验证 | OpenSpec 的 verify 是自验；Sopify 的 cross-review 是独立上下文 |
| 纯 NPM 分发 | Sopify 是 Python runtime + 文件协议，Protocol-first 不绑定包管理器 |

---

## Prompt 工程原则

> **Prompt 是 runtime contract 的适配层，不是事实源。**
> 每条原则都服务于底层哲学（Loop-first / Wire-composable / Surface-shared）。

7 条工程原则（沉淀至 `.sopify-skills/blueprint/prompt-governance.md`）：

0. **Loop-aligned** — prompt 的每一节都服务于 produce→verify→accumulate→produce 循环中的至少一环。不服务于任何一环的内容删除。
1. **Prompt 不定义机器契约** — 引用 runtime 输出，不在 prompt 里展开算法
2. **Prompt 不维护两份路由表** — 一处定义，其他处引用
3. **每条规则通过删除测试** — 删掉这行，宿主行为是否真的变化？不变则删
4. **渐进式披露** — 按触发路径分层加载，不全量 dump
5. **单源生成** — 从模板生成 4 个 variant，不手工同步
6. **行数硬上限** — 核心层 ≤ 120 行，含扩展层 ≤ 280 行

---

## 渐进式披露架构

对齐 ADR-016 三层模型 + 知名项目渐进式写法：

```
Layer 0 — Protocol (始终加载, ≤120 行)
├── 底层公理 (Loop-first / Wire-composable / Surface-shared) (~20 行)
├── 角色定义 + 路由入口表 (~20 行)  ← 一处定义，不重复
├── 输出格式约束 (~25 行)
├── 工作流模式 + 复杂度判定 (~20 行)
├── 目录结构 + 生命周期 (含"读"环节) (~20 行)
└── 配置默认值 (~15 行)  ← 去掉 multi_model.* 后

Layer 1 — Gate Contract (gate 触发时注入, ~40 行)
├── gate 4 条件校验 (~10 行)  ← 一次性定义
├── required_host_action dispatch 表 (~20 行)
└── ActionProposal capability 声明 (~10 行)

Layer 2 — Phase Execution (进入具体阶段时注入, ~30 行/阶段)
├── P1 需求分析流程 + 输出模板
├── P2 方案设计流程 + 输出模板
└── P3 开发实施流程 + 输出模板

Layer 3 — Reference (按需查阅, 不注入 prompt)
├── runtime helper 路径表 → 迁入 project.md 或 README
├── 平台适配 (A3) → 迁入 project.md
├── 工具映射 (A2) → 宿主自带，不需要 prompt 重复
└── 配置项说明 → 迁入 sopify.config.yaml 注释
```

**预期效果：**
- Layer 0 alone: ~120 行 (覆盖 80% 场景)
- Layer 0 + Layer 1: ~160 行 (覆盖 95% 场景)
- 全量 (L0+L1+L2): ~280 行 (对比当前 511 行, -45%)
- Layer 3 不进 prompt，迁到文档

---

## CN/EN 同步方案

**单源模板 + 构建生成：**

```
prompts/
├── base.template.md          # 共享骨架 (Layer 0 + 占位符)
├── gate-contract.partial.md  # Layer 1
├── phase-*.partial.md        # Layer 2
├── vars/
│   ├── claude-cn.yaml        # 变量: lang, encoding, tool_mapping
│   ├── claude-en.yaml
│   ├── codex-cn.yaml
│   └── codex-en.yaml
└── build-prompts.py          # 模板 + 变量 → 4 个 CLAUDE.md/AGENTS.md
```

差异维度只有 3 项：
- 语言 (zh-CN / en)
- 宿主工具名 (Read/Grep/Edit vs cat/grep/apply_patch)
- 入口文件名 (CLAUDE.md vs AGENTS.md)

---

## 与总纲对齐

- **ADR-016 Protocol-first**: prompt 分层 = Protocol 层始终加载 + Runtime 细节按需注入
- **ADR-013 产品定位**: prompt 只声明 control plane 能力，不展开执行细节
- **轻量化可插拔**: prompt 本身也是可插拔的——Layer 1/2 可独立更新不影响 Layer 0

---

## 执行范围

### Phase 1: 审计与原则沉淀
- 逐行标注 CLAUDE.md 每个区块：重复 / 唯一事实源 / 可迁移 / 可删除
- 撰写 `.sopify-skills/blueprint/prompt-governance.md` (6 条原则)
- 用户确认

### Phase 2: 渐进式披露重构
- 实现分层结构 (Layer 0 ≤ 120 行)
- 重构 Claude CN prompt 为 Layer 0
- 验证 runtime 行为不变（全量测试通过）
- 1 轮 dogfood

### Phase 3: 单源生成
- 实现 `build-prompts.py` 模板引擎
- 从模板重新生成 4 个 variant
- 集成到 pre-commit hook（替代当前 sync check）
- 验证生成结果与手工版功能一致

### Phase 4: 准入脚本
- `check-prompt-governance.py`：
  - 行数上限检查 (Layer 0 ≤ 120, 全量 ≤ 280)
  - 必需区块存在性检查
  - 重复模式检测（同一 key 出现 >1 次则报警）
  - 与 runtime gate contract 版本一致性检查

## 不做

- 不改 runtime gate / engine / router 逻辑
- 不改机器契约定义（只改 prompt 中的引用方式）
- 不合并到 legacy_feature_cleanup 包
- 不在本包实施前删除 ~compare（那是 cleanup 包的事）

---

## 附录: blueprint/design.md 结构审计观察

> 以下为本包设计阶段对 `blueprint/design.md`（当前 353 行）的结构审计发现。
> 这些是观察与建议，不是本包范围内的实现项。后续是否纳入实现取决于 blueprint 实际膨胀趋势。

### 观察 1 — Checkpoint 类型重复列举

**现状**: Routing & Checkpoint Layer (lines 166-169) 概述列出 4 种 checkpoint（clarification / decision / plan proposal / execution confirm），Checkpoint 契约补充 (lines 308-334) 展开了相同 4 种的实现细节。

**问题**: 修改一种 checkpoint 定义需要同步两处，且概述与展开的措辞可能漂移。

**建议改动**: 将 lines 166-169 的 4-bullet 列表替换为 `详见下文 Checkpoint 契约补充`，保留一句话概括 checkpoint 的设计意图（"把协作中的关键分叉点从聊天语气提升为机器可恢复的交接结构"），删除逐项枚举。省 ~4 行，消除一处维护双份。

### 观察 2 — "第一性原理分层结论" 标题名不副实

**现状**: §第一性原理分层结论 (lines 13-42) 下混合了两类内容：
- Lines 15-19: analyze skill pilot 决策记录（45 样本 / promotion gate）
- Lines 21-42: Design Influence Intake Gate（外部项目准入机制）

**问题**: "第一性原理分层结论"这个标题已经不能准确描述内容。pilot 决策和外部准入是两个独立关注点，共用一个标题增加了后续维护者的认知负担。

**建议改动**: 两个选项——
- 选项 A: 重命名为 `§ 准入与分层决策`，保持内容不变，只改标题
- 选项 B: 拆分为 `§ 历史 pilot 结论` (lines 15-19) + `§ Design Influence Intake Gate` (lines 21-42，升为独立 `##` 节)

### 观察 3 — 目录分层 vs KB 职责矩阵 轻度重叠

**现状**: 目录分层 (lines 115-125) 用文字描述 5 层（L0-L3 + runtime），KB 职责矩阵 (lines 336-346) 用表格列出同样 5 层的路径/职责/创建时机/Git 策略。

**判断**: 不构成真正冗余——一个是概念定义，一个是操作参考。如果要极致精简，可以只保留表格并在表头加一行概念说明，删除目录分层的文字段（省 ~10 行）。但当前不建议改动——两种视角对不同读者（架构理解 vs 操作查阅）都有价值。

### 观察 4 — Runtime state scope / gate ingress contract 实现细节偏重

**现状**: Lines 251-266 定义 session_id 语义、persisted_handoff 判定、handoff_source_kind 值域、previous_receipt 字段等 JSON 字段级契约。

**判断**: 当前 353 行尚可接受。但这些内容更接近 `project.md` 或独立 `runtime-contracts.md` 的职责定位。如果 design.md 继续膨胀到 400+ 行，这些是优先外迁候选——迁到 project.md 后 design.md 只保留 "runtime state 按 session 隔离，gate 以 persisted_handoff 为唯一正向证据" 一句摘要。

### 观察 5 — 评分输出 contract 是展示格式而非架构

**现状**: Lines 294-306 定义评分格式模板（方案质量 X/10 + 落地就绪 Y/10）。

**判断**: 这是 presentation format 而非架构决策。长期可迁到 SKILL.md 模板或 prompt governance 的 Layer 2 Phase Execution 模板中。优先级低，不阻塞当前。

### 无冗余确认

以下区块经审计确认不构成冗余：
- **拓扑全景 vs Runtime Flow mermaid**: 概念模型（loop+wire+surface）vs 实现流程（5 层执行链路），视角不同
- **底层哲学 ADR 映射 vs prompt governance "与总纲对齐"**: prompt governance 侧应改为引用 blueprint，属于 prompt governance 自身的问题
- **正式结论 vs 正文**: 正常 executive summary 模式

---

## 附录: blueprint 整体结构审计

> 以下为对 blueprint 目录整体（5 文件 ~708 行）的结构审计。与上一节 design.md 审计互补。

### 文件级审计

| 文件 | 行数 | 状态 | 发现 |
|------|------|------|------|
| README.md | 33 | ✅ 健康 | 纯索引，auto-managed blocks |
| background.md | 38 | ⚠️ 可能过时 | "本轮目标" 4 项全部已完成 |
| design.md | 353 | ⚠️ 职责过载 | 详见上节 |
| tasks.md | 26 | ⚠️ 陈旧条目 | ~compare 条目事实错误 |
| skill-standards-refactor.md | 258 | ⚠️ 已收口，待迁移 | 详见下方迁移方案 |

### 待办 A — background.md 过时标注

**现状**: "本轮目标" 4 项（切 wiki、收缩 README、knowledge_sync 固化、评分输出标准化）均已完成。整份文件描述已结束的轮次上下文。

**建议**: 顶部加一行 "以下目标已在 2026-03 轮次完成；当前上下文见 design.md §底层哲学 与 README.md §当前焦点"。

### 待办 B — tasks.md ~compare 条目修正

**现状**: Line 9 `把 ~compare 的 shortlist facade 收敛进默认主链路恢复` — 实际计划是 `20260429_legacy_feature_cleanup` 中直接删除 ~compare，不是合并进主链路。

**建议**: 改为 `[x] ~compare 功能移除（见 20260429_legacy_feature_cleanup T2）` 或直接删除该条目。

### 待办 C — skill-standards-refactor.md 迁移归档

**现状**: 258 行，标注 "已收口（2026-03-19 决议已落地）"。高价值内容约 76 行（6 项决策 + 4 项契约 A-D），低价值内容约 117 行（旧背景 + 已实现目标 + 已完成执行策略）。

**迁移方案:**

```
迁移目标:
  blueprint/design.md += ~15 行
    → 新增 `### Skill System 决策` (6 项已拍板决策, 压缩为精简段落)

  project.md += ~40 行
    → 新增 Skill System 约束节 (4 契约 A-D + 决策模式触发规则 + 权限最小字段集)

  history/2026-03/skill-standards-refactor.md
    → 原文件完整归档

  blueprint/skill-standards-refactor.md → 删除
  blueprint/README.md line 29 → 删除阅读入口或改为 history 链接
```

**预期效果:**
- blueprint: 5 文件 708 行 → 4 文件 ~465 行
- design.md: 353 → ~368 行 (+15)
- 高价值内容在正确位置（架构决策→design.md，实现约束→project.md）
- 低价值内容归档不丢失

**前置条件**: 检查 project.md 是否已有 skill 相关段落，避免重复。

### 跨文件一致性问题

| 检查项 | 结果 |
|--------|------|
| 5 层模型一致性 | ✅ background / design 目录分层 / KB 矩阵 三处一致 |
| ~compare 口径 | ❌ tasks.md 说"收敛进主链路" vs README/cleanup 说"移除" |
| 正式结论 5 条 vs 现状 | ✅ 全部仍成立 |

### design.md 拆分压力点

当前 353 行尚可接受。若膨胀到 ~500 行，建议拆分为：
- `blueprint/philosophy.md` — 3 公理 + 拓扑 + ADR 映射
- `blueprint/architecture.md` — runtime 5 层 + flow + guarantees
- `blueprint/contracts.md` — 消费契约 + checkpoint 契约
- `blueprint/design.md` — 结论 + 准入 + 目录分层 + KB 矩阵 + 治理

当前不执行此拆分。

---

## 附录: andrej-karpathy-skills 学习分析

> 遵循总纲 [Design Influence Intake Gate](../../blueprint/design.md#design-influence-intake-gate)。
> 来源：[andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) — 66 行 4 原则的 LLM 行为指导。

### 与 Sopify 3 哲学的映射

| karpathy 原则 | Sopify 哲学映射 | 现状 | 差距 |
|--------------|----------------|------|------|
| Think Before Coding | Loop-first (verify) + Wire-composable (clarification) | 架构已编码（clarification / decision checkpoint） | prompt 未显式要求 LLM "进入实施前列假设" |
| Simplicity First | Loop-first (minimal produce) | 复杂度评分管工作流级别 | 不管代码复杂度——Sopify 是 orchestrator 不是 linter |
| Surgical Changes | Loop-first (scoped produce → verify scope) | task 拆分隐含作用域 | 不验证 diff 是否越出 task 作用域 |
| Goal-Driven Execution | Loop-first (直接同构) | tasks.md 有描述无验证标准 | 模板未强制 verify 字段 |

### Sopify 可学习项

| 启示 | Tier | 实现路径 | 验证方式 |
|------|------|---------|---------|
| **tasks.md 模板强制 verify 字段** | **T1 Adoption** | Phase 2 重构模板，每个 task 必须有 `verify: [check]` | dogfood 1 轮——生成的 tasks.md 是否都带 verify |
| **Layer 0 加 "明确假设再行动" 指令** | **T0 Reference** | Layer 0 骨架中加 1 句 | 需评估是否与 clarification checkpoint 职责重叠 |
| **EXAMPLES.md anti-pattern 对照表** | **T0 Reference** | 可作为 SKILL.md references/ 补充 | 需评估 context window 成本 |

### 明确不学的

| 特性 | 理由 |
|------|------|
| 66 行硬上限 | Sopify 复杂度远超个人 coding guidelines；Layer 0 ≤120 行已合理 |
| 无分层、无渐进式披露 | karpathy 是单文件全量；Sopify 需要 Layer 0-3 |
| 无 runtime / 无 gate | karpathy 是纯行为指导；Sopify 需要确定性门控 |
| "For trivial tasks, use judgment" | Sopify adaptive 模式已实现 |

---

## 附录: evident-loop 独立仓库计划（后续待办）

> **触发条件**：prompt governance 包落地后，3 条哲学经过 1 轮实现验证（prompt 瘦身成功 = Loop-first 有效）。
> **前置**：本包 Phase 2 完成 + 1 轮 dogfood 通过。

### 定位

`evidentloop/evident-loop` — 将 Loop/Wire/Surface 哲学蒸馏为 ~60 行行为指导，以 Agent Skill 形式分发。

**两层内容：**
- **行为层**（CLAUDE.md / SKILL.md, ~60 行）：不依赖 Sopify runtime，任何 LLM 用户可直接使用
- **哲学层**（README.md / EXAMPLES.md）：完整理论、拓扑模型、场景对照

**与 Sopify 的关系**：evident-loop 是"轻量版"（纯行为指导），Sopify 是"完整版"（runtime + gate + checkpoint + knowledge lifecycle）。形成推广漏斗：`evident-loop skill → 了解哲学 → 了解 Sopify`。

### 预期结构

```
evidentloop/evident-loop/
├── CLAUDE.md           # ~60 行行为指导
├── SKILL.md            # plugin 格式
├── README.md           # 完整哲学 + 为什么 + 与 Sopify 关系
├── EXAMPLES.md         # 有 loop / 没 loop 的场景对照
└── skills/evident-loop/SKILL.md
```

### 行为指导草案

```markdown
## 1. Loop-first: 每个任务是闭环
- 开始前定义成功标准（可验证条件，不是"让它工作"）
- 每步有 verify：step → verify: [check]
- 完成后总结学到了什么，不只是做了什么

## 2. Wire-composable: 步骤之间用结构化交接
- 传递上下文用结构化格式，不用自由文本
- 写"下一步需要什么"而不是"我做了什么"
- 状态交接独立于当前 session（另一个 session 能继续吗？）

## 3. Surface-shared: 读和写同等重要
- 开始任务前先读项目的设计文档和历史决策
- 完成任务后把关键决策写回项目文档
- 文档是跨 session 的工作记忆，不只是归档
```

### 验证标准

working if:
- fewer context losses across sessions（跨 session 上下文丢失减少）
- verification steps present in task plans（任务计划中有验证步骤）
- project docs updated after task completion（任务完成后项目文档有更新）

### 与 Design Influence Intake Gate 的关系

evident-loop 仓库本身作为 evidentloop org 的哲学实践入口，不需要通过 Sopify 的 Intake Gate（它不是外部项目的设计影响，而是自有哲学的外化）。但仓库内容的演进应与 blueprint 哲学保持一致。
