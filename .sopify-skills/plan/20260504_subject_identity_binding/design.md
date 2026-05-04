# Design: Subject Identity & Existing Plan Binding（最小核）

> **定位**：P1 里程碑方案包。只固化 protocol contract + validator 最小消费。
> **前置**：P0 已完成；protocol.md §7 Subject Identity 草案已存在。
> **目标**：升格 execute_existing_plan 的 subject binding + validator fail-closed admission。

---

## 现状分析

### Protocol 层

| 区块 | 当前状态 | P1 目标状态 |
|------|---------|-----------|
| Subject Identity 通用字段 | normative target | normative（仅 subject_type="plan"） |
| 取证优先级链路 | normative target | 不动（文档层规则已足够，操作化等 runtime 层需要时再做） |
| execute_existing_plan binding | UNSTABLE/draft | **normative** |
| Review Subject Identity | informative/draft | 不动 |

### 现役 machine truth vs canonical

| 现役路径 | 代码位置 | 与 canonical subject 的关系 |
|---------|---------|--------------------------|
| `current_plan` | `state.py:47` | 隐含 subject_type=plan, subject_ref=current_plan path |
| `~go exec` | action_projection | 隐含 execute_existing_plan，但无显式 subject binding |
| `review_or_execute_plan` | action_projection | legacy composite，P3a 收口 |
| `archive_plan` + ArchiveSubjectProposal | action_intent.py | 已有显式 subject，但不使用通用字段名 |

**P1 的最小切入点**：不改动现役路径，只在 execute_existing_plan 这条 canonical 路径上加 subject admission。

### Validator 层

当前 `ActionIntentValidator` 对 `execute_existing_plan` 的校验是**最小 evidence proof**（和其他 side-effecting action 一样），没有 subject 层面的校验。

---

## 设计决策

### D1: 只做 protocol 升格 + validator 最小消费

不新增 runtime 抽象层。Protocol 升格是文档变更（protocol.md §7 标注）。Validator 变更限于 `action_intent.py` 中 `execute_existing_plan` 分支增加 subject_ref 存在性 + revision_digest 一致性校验。

### D2: 不做通用 SubjectIdentity dataclass

现役代码中 ArchiveSubjectProposal 已经特化工作良好。在没有第二个真实消费者前，提前提取通用抽象是过度设计。等 P1 contract 稳住 + execute_existing_plan 成为真正主链路后再评估。

### D3: Legacy mapping 只做文档规则

明确"现役 current_plan / ~go exec 如何映射到 canonical subject"的规则，但只写在方案包设计文档或 protocol.md 的 informative 注释里。不在 runtime 里实现自动映射——那是 P3a contract-aligned cleanup 的范围。

### D4: revision_digest 计算规则（最小版）

- 对 execute_existing_plan：SHA-256(plan.md 文件内容) 的 hex digest
- 文件不存在 → validator 拒绝 admission
- 不做缓存、不做增量 hash

### D5: new_plan_intent 不进 P1

蓝图把 plan materialization authorization 明确放在 P1.5（tasks.md:55）。代码里没有 `create_plan` action type，只有 `propose_plan`。P1 不碰这个语义。

### D6: execute_existing_plan 的 subject 载荷入口

**决策：方案 A — 新增 execute_existing_plan 专用最小字段块。**

给 ActionProposal 增加一个仅供 execute_existing_plan 使用的字段块 `plan_subject`，只含 `subject_ref`（plan 路径）和 `revision_digest`（SHA-256 hex）。

**subject_ref 的 canonical 形状**：workspace-relative 方案目录路径（如 `.sopify-skills/plan/20260504_subject_identity_binding`），不是文件路径。revision_digest = 该目录下 `plan.md` 的 SHA-256 hex digest。这贴合现役 `current_plan.path` 的形状（`state.py:47`），也最可审计。

理由：
- 对齐现有 `archive_subject`（ArchiveSubjectProposal）的模式——场景特化字段块
- 不提前引入通用 `subject_identity` 字段，避免"先造 runtime 抽象层"
- gate 暴露给宿主的 schema 只需新增 `plan_subject` 一个字段块

不选方案 B（通用 subject_identity 整块）：会把这次拉回"提前造通用层"。

### D7: 缺少/不匹配 subject 时的 validator 语义

**决策：方案 A — execute_existing_plan 用 reject。**

当 execute_existing_plan 的 `plan_subject` 缺失、`subject_ref` 指向不存在的 plan、或 `revision_digest` 与文件实际内容不匹配时，validator 返回 **DECISION_REJECT** + 具体 reason_code。

**reject 发生在 validator 层，不前移到 parse 层。** 当前 `ArchiveSubjectProposal` 是 parse-time 强校验（`action_intent.py:162`），但 `plan_subject` 不应照搬这个模式——如果 parse 层就因缺失而使 proposal 无效/消失，就变成"proposal 不存在"而非"proposal 被明确拒绝"。正确做法：gate schema 提示宿主必填，但 ActionProposal parse 层允许 plan_subject 缺失（解析为 None），缺失/不匹配由 validator 在 admission 阶段返回 DECISION_REJECT + reason_code（如 `validator.execute_existing_plan_missing_subject` / `validator.execute_existing_plan_digest_mismatch`）。

理由：
- P1 的核心命题是"主体不明确就不能执行"，降级 consult 会稀释这个不变量
- execute_existing_plan 是显式 side-effecting canonical action，subject 缺失 = contract invalid
- 与蓝图 protocol.md §7 的 fail-closed 原则一致

不选方案 B（降级 consult）：会让"主体不明确时仍可继续"变成默认行为。

---

## 文件变更预估

| 层 | 文件 | 变更类型 | 范围 |
|----|------|---------|------|
| Protocol | `blueprint/protocol.md` §7 | 编辑 | 移除 UNSTABLE 标注，RFC 2119 化 |
| Protocol | `blueprint/protocol.md` §7 | 编辑 | legacy mapping 注释（informative） |
| Validator | `runtime/action_intent.py` | 编辑 | execute_existing_plan 分支增加 plan_subject admission + reject 语义 |
| Validator | `runtime/gate.py` | 编辑 | gate schema 增加 plan_subject 字段块 |
| Test | `tests/test_action_intent.py` 或现有测试 | 编辑/新增 | subject admission 单元测试 |
| Blueprint | `blueprint/README.md` | 编辑 | 焦点更新 |
| Blueprint | `blueprint/tasks.md` | 编辑 | P1 状态 |

**不新增文件**：无 subject_identity.py, 无 schema.json, 无 e2e test file。

---

## 验收标准

1. protocol.md §7 execute_existing_plan binding 无 UNSTABLE 标注，使用 RFC 2119 规范表述
2. protocol.md §7 有 informative 注释说明现役 legacy 路径与 canonical subject 的映射关系
3. Validator 对缺少 plan_subject 的 execute_existing_plan proposal 返回 **rejected**（不是 downgrade）
4. Validator 对 revision_digest 不匹配的 execute_existing_plan proposal 返回 **rejected**
5. 以上两条有单元测试覆盖
6. gate schema 正确暴露 plan_subject 字段块
7. 不引入新的 runtime 抽象文件

