# 技术设计: Cross-Review 独立内核方案

## 技术方案

本方案采用两层结构：

1. **独立内核层**：`sopify-cross-review` / `cross-review engine`
   - 负责 artifact 抽取、review orchestration、finding 归一化、verdict 裁决、policy 输出。
   - 不依赖 Sopify 特定路由语义才能成立。

2. **Sopify 集成层**：`cross-review adapter`
   - 负责把内核能力接入 Sopify 的 analyze / design / develop / compare / checkpoint。
   - 复用现有 handoff、decision facade、develop_quality、state/replay。

这保证了两个目标同时成立：

- 独立使用：可作为单独 skill / runtime capability / CLI 运行。
- 内部集成：可被 Sopify 各阶段按 policy 嵌入，而不改变其核心定位。

在这个两层结构之上，再补一层**产品垂直面**：

1. **通用产品 / 通用内核**：`sopify-cross-review`
2. **垂直能力**：
   - `design-review`
   - `sopify-code-review`
   - `final-audit`
3. **工作流宿主**：`Sopify`

也就是：

- `sopify-cross-review` 解决“如何独立验证”
- `sopify-code-review` 解决“如何验证代码工件”
- `Sopify` 解决“验证发生在工作流的哪个阶段，并如何进入 plan/history 生命周期”

## 设计状态说明

本文件中的架构描述分为两类：

1. **可继续深化的推荐设计**
   - 用于支撑后续讨论、拆分 contract、完善 plan 资产结构
   - 当前可以继续展开细节

2. **必须等待用户拍板的设计决策**
   - 一旦涉及产品名、正式配置键、资产层是否入 plan、MVP 边界与首批集成阶段
   - 在用户明确确认前，不应转成实现前提

也就是说，本文件当前的任务是“把设计空间说清楚”，不是“替用户把最终产品策略定死”。

## 仓库形态与演进建议

### 建议的长期形态

当前更合理的长期目标是：

- `sopify-cross-review` 作为独立产品内核
- `Sopify` 作为工作流宿主 / adapter 消费方

从架构边界看，二者最终分属不同仓库是合理方向，因为它们解决的问题不同：

- `sopify-cross-review` 负责通用 review/verification 协议、profile、adjudication、policy
- `Sopify` 负责 plan / checkpoint / handoff / history / blueprint 生命周期

### 但当前不建议立刻钉死分仓

本方案不把“现在立刻拆新仓库”设为硬前提，原因有三点：

1. review 资产层、artifact taxonomy、正式配置键仍待用户拍板
2. 如果过早分仓，后续 contract 收敛时会反复调整 repo 边界
3. 当前更需要的是把 core / adapter 的责任边界说清楚，而不是先完成物理迁移

### 推荐的演进路径

当前建议按三阶段理解：

1. **阶段 A：独立产品方案阶段**
   - 在当前方案中把 `sopify-cross-review` 的能力边界、资产层、profile、adapter 讲清楚
   - 这一步不要求实际分仓

2. **阶段 B：独立内核实现阶段**
   - 当命名、配置键、review asset、MVP 范围稳定后
   - 再创建 `sopify-cross-review` 新仓库或等价独立包
   - 先实现 standalone core / CLI / profile

3. **阶段 C：宿主渐进接入阶段**
   - `Sopify` 进一步朝可插拔运行时框架收敛
   - 再按 `design -> develop -> finalize` 或试点顺序逐步接入

### core / adapter 边界建议

如果未来分仓，当前建议按下面边界理解：

#### `sopify-cross-review` core 更适合承载

- artifact model
- review pack
- reviewer transport abstraction
- finding / verdict schema
- adjudicator
- policy
- vertical profiles
  - `design-review`
  - `code-review`
  - `final-audit`
- standalone CLI / runtime entry

#### `Sopify adapter` 更适合承载

- `.sopify-skills/plan` 生命周期写入
- `review.md + reviews/` 的 plan/history 挂载
- checkpoint / handoff / execution gate 联动
- `develop_quality` 映射
- `current_handoff.json` / state 读写
- blueprint / history 归档联动

### 状态说明

上述“独立仓库”表述目前是**推荐演进方向**，不是冻结决策。  
是否真的创建新仓库、何时分仓、是先包级独立还是 repo 级独立，仍需用户后续拍板。

## 为什么它必须比 Sopify 更小、更聚焦

`sopify-cross-review` 如果想成为成立的独立产品，就不能只是“把 Sopify 的一部分复制出去”，也不能继续长成另一个 workflow host。

当前更合理的尺度定位是：

- `Sopify`：完整 AI 编程工作流宿主
- `sopify-cross-review`：独立验证内核
- `sopify-code-review`：代码工件 vertical

### 为什么必须更小

如果 `sopify-cross-review` 同时承担下面这些能力：

- runtime gate
- clarification / decision checkpoint
- plan package 生命周期
- handoff / history / blueprint 主流程

那它就不再是验证产品，而是在重复构建一个更小的 Sopify。  
这样会带来两个问题：

1. 与 `Sopify` 的边界重叠，宿主 / 内核职责重新混乱
2. 独立产品无法保持清晰心智，用户不知道它究竟是“review 产品”还是“workflow 框架”

### 为什么必须更集中

`sopify-cross-review` 的产品焦点应该稳定落在四件事上：

1. `independent`
   - 生产与评审上下文分离

2. `structured`
   - review 输入和输出可结构化表达

3. `decidable`
   - review 结果可以形成 verdict 与后续动作

4. `auditable`
   - review 结果可进入长期资产与审计链

只要一直围绕这四点，它就是独立验证产品；  
一旦开始扩张到“完整开发流程管理”，焦点就会跑掉。

### 因此建议的边界

#### 应保留在 `sopify-cross-review core` 的能力

- artifact model
- review pack
- reviewer orchestration
- finding / verdict schema
- adjudicator
- policy engine
- report payload / report content generation

#### 应保留在 `Sopify adapter` 的能力

- 何时触发 review
- 如何写入 `.sopify-skills/plan/...`
- 如何更新 `review.md + reviews/`
- 如何映射到 `develop_quality`
- 如何进入 `handoff / checkpoint / history`

#### 应留在 vertical profile 的能力

- `code-review` 的代码 rubric
- `design-review` 的方案挑战 rubric
- `final-audit` 的收口审计 rubric

### 对后续设计的约束

这条“更小、更聚焦”的原则，后续会约束三类设计：

1. **仓库边界**
   - core 与 adapter 必须分离

2. **文档边界**
   - `sopify-cross-review` 文档聚焦验证协议，不扩张成完整 workflow 文档

3. **实现边界**
   - 不把 plan lifecycle、history 归档、checkpoint 主逻辑写进 core

这一点目前不要求用户立即拍板，但应作为后续演进中的持续校验标准。

## 为什么不直接复用 `~compare`

`~compare` 和 `cross-review` 在产品语义上不同：

| 能力 | 目标 | 输入重心 | 输出重心 |
|---|---|---|---|
| `~compare` | 选优 | 同一问题的多个候选答案 | 候选结果 + 人工选择 |
| `cross-review` | 验错 | 已产生的 artifact 与证据 | findings + verdict + 后续动作 |

结论：

1. `cross-review` 可以复用 compare runtime 的 fan-out、context pack、normalize 基座。
2. 但不能继续使用 compare 的产品语义，否则会把“验证”错误地表达成“候选结果选择”。

因此，本方案把 compare runtime 视为**执行子模块**，而不是产品壳。

## 为什么不把 `cross-review` 直接并入 `code-review`

如果只看 develop 阶段，确实容易产生一种错觉：review = code review。  
但一旦把“设计评审报告”正式纳入 plan 生命周期，这个边界就变了。

更稳定的分层应该是：

| 层级 | 作用 | 示例 |
|---|---|---|
| 通用协议层 | 定义 review pack / finding / verdict / adjudication / policy | `cross-review` |
| 工件垂直层 | 针对某一类 artifact 提供专门 rubric 和输出 | `code-review`, `design-review` |
| 工作流层 | 决定何时触发、如何沉淀到 plan/history | `Sopify` |

因此建议：

1. `sopify-code-review` 不作为总产品名；
2. `sopify-code-review` 作为 `sopify-cross-review` 的一个垂直产品 / 模式；
3. Sopify 集成的是 `cross-review` 内核和若干 review 模式，而不是只集成 `sopify-code-review`。

这能同时解释：

- 你原先独立做的 `code-review` 产品仍然成立；
- 现在新增的设计评审报告需求也能自然纳入；
- 不会让 review 体系被“代码”这个单一工件绑死。

## 核心抽象

### 1. Artifact

Cross-Review 的输入必须先被收口为显式 artifact，而不是随意问题文本。

建议首批支持：

- `code_diff`
- `plan_package`
- `task_result`
- `design_summary`
- `consult_answer`
- `command_result`

首期 MVP 只推荐正式落地：

- `code_diff`
- `plan_package`
- `task_result`

原因：
- 它们最容易结构化；
- 最容易和 Sopify 的 design / develop / finalize 对接；
- 最容易定义验收标准和 block policy。

### 2. Review Pack

所有 reviewer 都消费同一种 review pack，而不是各自拿不同上下文。

建议结构：

```json
{
  "artifact_kind": "code_diff",
  "task": {
    "request": "...",
    "acceptance_criteria": ["..."],
    "constraints": ["..."]
  },
  "artifact": {
    "diff": "...",
    "files": ["src/a.ts", "src/b.ts"]
  },
  "evidence": {
    "tests": [
      {"command": "npm test", "status": "passed"}
    ],
    "snippets": [
      {"path": "src/a.ts", "start_line": 10, "end_line": 42, "content": "..."}
    ]
  },
  "policy_context": {
    "risk_tags": ["auth"],
    "severity_threshold": "high"
  }
}
```

设计原则：

1. reviewer 不直接读取 producer 的长推理过程；
2. 先看任务、工件、证据；
3. 作者说明若需要，应作为二阶段补充，而不是默认主输入。

### 3. Reviewer

reviewer 不等于“另一个模型”，而是一个执行角色。

建议支持三种 reviewer 类型：

1. **fresh_session_same_model**
   - 同模型，新上下文。
   - 成本最低，且能明显降低自我锚定偏差。

2. **cross_model_reviewer**
   - 不同模型进行独立审查。
   - 更适合高风险或高不确定性工件。

3. **deterministic_checker**
   - 非 LLM checker，如 lint/test/schema rule/contract validator。
   - 不属于“语言审查”，但应进入同一 verdict 汇总。

这里的关键结论是：

Cross-Review 不应被设计成“只会调多个 LLM”。  
它应该是一个统一验证编排层，LLM reviewer 只是其中一类执行者。

### 4. Finding

review 输出不能停留在自然语言点评，必须归一化。

建议 finding schema：

```json
{
  "id": "finding_001",
  "severity": "high",
  "category": "logic_regression",
  "title": "Token refresh path may bypass expiry check",
  "summary": "expiry validation moved behind early return",
  "evidence": [
    {
      "kind": "file_ref",
      "path": "src/auth/token.ts",
      "line": 88
    }
  ],
  "confidence": 0.81,
  "source_reviewer_id": "session_default_fresh"
}
```

建议首批 category：

- `logic_regression`
- `spec_mismatch`
- `missing_validation`
- `insufficient_tests`
- `risk_unmitigated`
- `architecture_mismatch`

### 5. Verdict

单个 finding 不是最终动作，最终要收口成 verdict。

建议 verdict：

- `pass`
- `concerns`
- `block`
- `inconclusive`

建议动作：

- `proceed`
- `revise_then_recheck`
- `checkpoint_required`
- `human_decision_required`

映射原则：

1. `pass`：没有高严重度问题，且 evidence 充分。
2. `concerns`：存在中低风险问题，建议修改，但不一定阻断。
3. `block`：存在高风险或多 reviewer 共识问题，需阻断。
4. `inconclusive`：证据不足、上下文不全、reviewer 冲突过大。

## Review 资产面设计

如果要让 review 真正进入 Sopify 的 plan 生命周期，建议把“控制面”和“资产面”拆开。

### 控制面

继续使用现有运行时机制：

- session review state
- `review_or_execute_plan`
- `develop_quality`
- `handoff.artifacts`
- checkpoint / resume / finalize

控制面负责本轮机器事实、阻断与恢复。

### 资产面

新增 tracked review 资产：

```text
plan/YYYYMMDD_feature/
├── background.md
├── design.md
├── tasks.md
├── review.md
└── reviews/
    ├── design-review.md
    ├── final-audit.md
    └── tasks/
        ├── T1-review.md
        └── T2-review.md
```

资产面负责：

1. 给人类看；
2. 在 history 中长期保存；
3. 作为事后审计与复盘证据；
4. 为未来 graphify / blueprint 等长期知识层提供引用入口。

### `review.md` 的职责

`review.md` 不应承载所有细节，而应作为总索引和状态面板。

建议内容：

1. 当前 plan review 总状态
2. design review 结论摘要
3. task review 覆盖率
4. 未解决高风险问题
5. final audit 结论
6. 详细报告链接

这使 `review.md` 和 `background/design/tasks` 平级成立，但不会成为巨型流水账。

### 详细报告职责

- `reviews/design-review.md`
  - 面向 plan package 的设计评审
  - 聚焦范围、风险、验证路径、长期契约

- `reviews/tasks/Tn-review.md`
  - task 完成后触发的复核报告
  - 聚焦该 task 的代码改动、测试、finding、结论

- `reviews/final-audit.md`
  - plan 完成前的收口审计
  - 聚焦任务闭环率、风险残留、是否允许归档

这三类报告共同组成 plan 的 review 资产。

## 裁决层设计

Cross-Review 不能只把多个 reviewer 原样输出给用户，必须有 adjudication 层。

建议 adjudicator 负责：

1. finding 去重
2. severity 归一化
3. reviewer 冲突整理
4. 依据 policy 形成最终 verdict

### 推荐裁决规则

MVP 建议使用确定性规则，不引入额外 LLM adjudicator：

1. 任一 reviewer 发现 `high` 且 evidence 充分的 finding → 至少 `concerns`
2. 两个 reviewer 对同一问题独立命中 → 升级到 `block`
3. 只有一个 reviewer 提出、且 confidence 低、evidence 弱 → 保留为 `concerns`
4. reviewer 全部失败或证据包过空 → `inconclusive`

这一步非常重要，因为它决定这件事更像工程系统，而不是多人聊天。

## 配置设计

当前不建议把能力继续挂在 `multi_model` 下。  
建议引入新的稳定父键：

```yaml
cross_review:
  enabled: false
  mode: advisory
  default_strategy: fresh_session_same_model

  reviewers:
    - id: session_default_fresh
      type: fresh_session_same_model
      enabled: true
    - id: qwen_reviewer
      type: cross_model_reviewer
      provider: openai_compatible
      model: qwen-plus
      enabled: false

  policy:
    develop:
      advisory_when:
        - changed_files_gt_2
      required_when:
        - auth
        - schema
        - payment
        - no_tests
    design:
      advisory_when:
        - architecture_change
        - long_term_contract_change
```

设计原则：

1. `multi_model` 仍保留给 compare；
2. `cross_review` 独立描述验证能力；
3. 未来如果底层调用器统一，也只复用执行层，不混淆产品配置语义。

如果未来需要把 `sopify-code-review` 暴露成独立产品，也建议采用“共享内核，不共享顶层配置名”的策略：

```yaml
cross_review:
  ...

code_review:
  enabled: false
  profile: strict
```

其中：

- `cross_review` 负责通用协议与 reviewer 编排；
- `code_review` 作为面向代码工件的产品型 profile 或 wrapper；
- Sopify 内部优先依赖 `cross_review`，而不是反向依赖 `code_review`。

> 状态说明：
> 上述配置设计目前是**推荐草案**，不是最终契约。
> 是否真的引入 `cross_review` 顶层配置键，仍需用户后续明确拍板。

## 与 Sopify 的集成边界

### 集成优先级

建议集成顺序：

1. **design**
2. **develop**
3. **finalize**
4. **analyze**

原因：

1. 既然要把设计评审报告放入 plan 资产，design 就不应再是后补；
2. develop 的 task review 是第二层闭环；
3. finalize 是把 review 资产正式收口进 history 的最佳切点；
4. analyze 的“需求反方审题”收益真实，但噪音风险也最高。

### design 集成方式

建议在 plan package 物化完成后、进入 `confirm_execute` 前，先生成：

- `review.md`
- `reviews/design-review.md`

作用：

1. 让设计评审成为 plan 的正式组成；
2. 如果 design review 发现高风险问题，可直接阻断进入 develop；
3. 让后续 task review 有明确的“设计基线”可追溯。

### develop 集成方式

建议方式：

1. 每个 task 完成后，生成 `task_result` 或 `code_diff` review pack；
2. 执行 cross-review；
3. detailed report 写入：
   - `handoff.artifacts.cross_review_report`
   - `reviews/tasks/Tn-review.md`
4. 汇总状态同步到 `review.md`
5. verdict 映射进 `develop_quality.review_result`
6. 若 verdict 命中 block policy，则转为 `checkpoint_required` 或 `review_or_execute_plan`

设计重点：

- 先不破坏 `develop_quality` 主 schema；
- 先以 artifact 扩展方式承载详细报告；
- 等能力稳定后再决定是否升级 schema version。

### finalize 集成方式

在 finalize 前补一轮 `final-audit`：

1. 检查 tasks 是否完成
2. 检查 task review 是否闭环
3. 检查 design review 遗留问题是否已处理
4. 生成 `reviews/final-audit.md`
5. 更新 `review.md` 最终状态
6. 随 plan 一起进入 history

这使 history 不再只有“做了什么”，也能回答“做完之后是否被审过、审出了什么、怎么收口的”。

### analyze 集成方式

只建议作为后续增强：

1. 用于 challenge requirement completeness；
2. 只做 advisory，不默认 block；
3. 避免把 analyze 变成噪音追问器。

## 独立使用形态

Cross-Review 内核至少应支持三种入口：

1. **独立 skill**
   - 例：`交叉验证这次改动`
   - 适合人工触发。

2. **runtime skill**
   - 可被 Sopify 路由调用。
   - 适合阶段内自动化集成。

3. **CLI / script**
   - 例：`python3 scripts/cross_review_runtime.py --artifact code_diff`
   - 适合 CI、维护者、宿主外调试。

建议第一版优先实现 runtime skill + script，两者共享同一内核入口。

如果保留你之前的独立产品 `sopify-code-review`，当前更合理的定位是：

1. `sopify-code-review` 作为 standalone vertical product 存在；
2. 它内部复用 `cross-review` 内核；
3. Sopify 不直接依赖 `sopify-code-review` 产品壳，而是集成 `cross-review` 与 `code-review profile`。

## 命名建议

当前建议：

1. 对外产品名优先使用 `sopify-cross-review`
2. 对外能力名、方案包、命令名优先使用 `cross-review`
3. 对内模块名可使用：
   - `cross_review`
   - `verification_loop`
   - `review_pack`
   - `review_policy`
   - `review_adjudicator`

推荐组合：

- 产品名：`sopify-cross-review`
- 能力名：`cross-review`
- 核心模块语义：`verification loop`

如果未来保留第二品牌线，建议关系为：

- `sopify-cross-review`: 通用 review/verification 产品
- `sopify-code-review`: 基于 `cross-review` 的代码工件垂直产品

而不是反过来。

这样可读性和系统性都比较平衡。

命名备选清单已单独整理到：

- [naming-options.md](./naming-options.md)

该文档只用于命名评审，不代表最终定名。

## 后续需用户拍板的关键决策

以下决策会直接影响后续目录命名、配置键、模块边界与实现切片，因此必须由用户后续确认：

1. **品牌与命名**
   - 是否正式采用 `sopify-cross-review`
   - 是否固定 `cross-review` 为能力名
   - 是否固定 `verification loop` 为内核语义名

2. **产品层关系**
   - 是否采用 `sopify-cross-review > sopify-code-review` 的层次
   - 还是保留并列产品，或反向层级

3. **plan 资产层**
   - 是否正式引入 `review.md + reviews/`
   - 是否把 design review / task review / final audit 都视为 tracked asset

4. **正式配置**
   - 是否采用 `cross_review` 顶层配置键
   - 是否需要 `code_review` 作为 profile / wrapper 配置面

5. **MVP 范围**
   - 第一版是否只做 `plan_package + task_result/code_diff`
   - 第一版是否先接 `design + develop`

6. **仓库形态**
   - 是否最终采用独立仓库
   - 何时分仓
   - 是先 package 级独立还是直接 repo 级独立

在这些点没有明确决策前，本文件中的实现形态都只视为**推荐设计草案**。

## MVP 范围建议

第一版只做：

1. `plan_package` artifact
2. `task_result` / `code_diff` artifact
3. `fresh_session_same_model` reviewer
4. `cross_model_reviewer` reviewer
5. 确定性 adjudicator
6. advisory / block 两档 policy
7. plan 内 `review.md + reviews/` 资产结构
8. Sopify 先接 design + develop

先不做：

- analyze 自动 cross-review
- 多轮 reviewer 辩论
- LLM adjudicator
- PR 平台集成
- graphify / blueprint 联动自动触发

## 方案评级

- 方案质量: 8/10
- 落地就绪: 7/10

评分理由:
- 优点: 与 Sopify 现有 runtime skill、compare、quality gate、handoff 结构高度兼容，且产品边界比“继续强化 compare”更清晰。
- 扣分: 命名、schema 边界、policy 升级路径仍需进一步收敛，否则容易出现“compare / review / quality gate”职责重叠。
