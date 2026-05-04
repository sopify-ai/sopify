# Subject Identity & Existing Plan Binding

title: P1 — Subject Identity & Existing Plan Binding（最小核）
scope: protocol §7 execute_existing_plan binding 升格 + validator 最小 fail-closed admission
approach: 只固化 protocol 层 contract + validator 最小消费；暂缓 runtime 通用 resolver / 新抽象层

## Plan Intake Checklist

1. **命中蓝图里程碑**：P1（主）
2. **改动性质**：contract acceptance boundary（进 blueprint）
3. **新增 machine truth**：是 — execute_existing_plan 的 subject binding 从 UNSTABLE/draft 升格为 normative
4. **Legacy surface 影响**：不动现役 legacy surface（review_or_execute_plan 等 P3a 再收口）
5. **Core/validator authority 影响**：validator 对 execute_existing_plan 增加 subject 存在性 + digest 一致性校验

## 背景

P0 (Blueprint Rebaseline) 已完成。protocol.md §7 已有 Subject Identity 草案：
- 通用字段（subject_type / subject_ref / revision_digest）已升格为 **normative target**
- execute_existing_plan 场景绑定仍标记 **UNSTABLE/draft**
- 取证优先级链路（5 级 fallback）已定义

但 execute_existing_plan 目前只出现在 ActionProposal 枚举里（`action_intent.py:21`），不是现役主链路。现役 machine truth 仍是 current_plan / `~go exec` / review_or_execute_plan。

## 目标（收窄后）

P1 只做"协议层定规矩 + validator 最小执行"：
1. protocol.md §7 execute_existing_plan binding 升格为 normative
2. Validator 对 execute_existing_plan 做最小 fail-closed subject admission
3. 明确"现役 legacy 输入如何映射到 canonical subject"的规则（文档层，不急着改 runtime）

## 不做（显式延后）

- 通用 `SubjectIdentity` runtime dataclass → 等 P1 contract 稳住后再决定是否需要
- 通用 5 级 resolver 实现 → 等 P1.5 授权脊柱定清楚
- `new_plan_intent` / `create_plan` 语义 → 明确属于 P1.5 plan materialization authorization
- 现役 legacy surface 收口（review_or_execute_plan 等）→ P3a
- e2e 集成测试铺设 → 等 contract 稳住
- ArchiveSubjectProposal 对齐到通用 contract → 等通用 contract 存在后再说

## 实现决策（已拍板）

1. **Subject 载荷入口**：给 ActionProposal 增加 `plan_subject` 专用字段块（仅含 subject_ref + revision_digest），对齐 `archive_subject` 模式。不引入通用 `subject_identity` 字段。
2. **subject_ref 形状**：workspace-relative 方案目录路径（如 `.sopify-skills/plan/20260504_xxx`）。revision_digest = 该目录下 plan.md 的 SHA-256。
3. **Validator 失败语义**：execute_existing_plan 缺少/不匹配 plan_subject 时 validator 返回 **DECISION_REJECT** + reason_code。
4. **Reject 在 validator 层**：parse 层允许 plan_subject 缺失（解析为 None），不前移到 parse 层强校验。gate schema 提示宿主必填。

## Tasks

- [ ] t1-protocol-upgrade: protocol.md §7 execute_existing_plan binding 升格 draft→normative（RFC 2119 表述）
- [ ] t2-legacy-mapping-doc: 文档层明确"现役 legacy 路径如何映射到 canonical subject"规则
- [ ] t3-validator-admission: ActionProposal 增加 plan_subject 字段块 + Validator execute_existing_plan subject admission（reject 语义）
- [ ] t4-validator-test: t3 的单元测试
- [ ] t5-blueprint-writeback: 蓝图回写（README 焦点 + tasks.md P1 状态）

