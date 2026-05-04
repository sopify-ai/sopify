# 蓝图路线图与待办

本文定位: 只记录未完成长期项与明确延后项。已完成项不保留。不替代当前 plan 的执行任务清单。

## 执行优先级（已确认）

以下顺序是硬约束。前一项未稳定前，不进入后一项实现。

> **对齐原则**：Sopify 总方向是 Protocol-first / Validator-centered / Runtime-optional。主航道的每一步都是"先 formalize protocol/validator 层契约，再让 runtime 作为参考实现消费"。不以 runtime 内部治理为驱动。

> **先行切片例外**：以下两类改动不受上述顺序约束：① 已在后续里程碑描述中显式标注"可先行"的 presentation-only 切片；② 已证明不影响 protocol / validator / runtime machine contract 的纯展示层改动。除此之外，任何涉及契约面的工作必须等前置里程碑稳定。

> **结构重构锚点**：跨 contract 的模块拆分与 legacy control surface 收口应与里程碑同步——P1 后优先 subject resolution / plan lookup 统一入口，P1.5 后优先 authorization policy / gate-receipt 收敛，P2 后优先 action contract adapter 统一，P3a 再做 engine.py / decision_tables.py / CLI entry 系统拆分与 sunset 表最终清理。不阻止与上述 contract 无关且不改变 machine truth 的低风险整理。

| 优先级 | 任务 | 前置条件 | 说明 |
|--------|------|---------|------|
| P0 | Blueprint rebaseline | 无 | 已完成。重写 blueprint，实体化 ADR，定义削减目标 |
| P1 | subject_identity_binding | P0 | protocol / validator / runtime 三联动定义"操作的是谁" |
| P1.5 | execution_authorization_spine | P1 | 操作化 ADR-017 ExecutionAuthorizationReceipt，规划授权链路 |
| P2 | local_action_contracts | P1.5 | 在主体已绑定前提下收敛局部动作 contract |
| P3a | contract_aligned_cleanup | P2 | 以 protocol/validator 已稳定为前提，清理 runtime 旧 contract 面 |
| P3b | presentation_projection_cleanup | P3a | 清理 prompt/projection/test 旧表面 |
| P4 | host_consumption_governance | P3b | 宿主只消费 contract，不定义 truth |

### P0: Blueprint Rebaseline（已完成）

- ✅ 重写 blueprint/{background,design,tasks}.md
- ✅ 实体化 ADR-013/016/017 到 blueprint/architecture-decision-records/
- ✅ 定义削减预算表和目标词汇表
- ✅ 降级并删除 20260424_lightweight_pluggable_architecture（证据留 git history）
- ✅ 迁移 ADR 到 blueprint/architecture-decision-records/
- ✅ 竞品边界表已更新；最小协议文档已落地（`blueprint/protocol.md` v0）

### P1: Subject Identity & Existing Plan Binding

protocol / validator / runtime 三联动。不只是 runtime 内部统一主体解析，而是跨层定义"操作的是谁"的可携带 truth。

**范围界定**：P1 的核心交付是 execute_existing_plan 场景的 subject identity 规范化。protocol.md §7 已有 subject identity 草案覆盖所有 side-effecting action，P1 推进其升格路线但以 existing plan binding 为主战场，不把所有 action 的主体规范一次做完。

- 推进 `protocol.md` §7 中已有的 subject identity 草案（subject_type / subject_ref / revision_digest）的升格路线，目标从 informative/draft → canonical/normative
- 在 protocol 层定义 execute_existing_plan 场景下"我到底在操作哪个 existing plan"的可携带规则
- 定义主体取证优先级：explicit reference → self-reference → new-plan intent → stable handoff evidence → current-plan anchor
- 明确 validator 的消费边界：validator 基于 subject identity 做 admission / authorization 判定
- 明确 runtime 的消费边界：runtime 作为参考实现消费 protocol 定义的 subject identity contract
- 不定义局部动作 contract，不治理 prompt

### P1.5: Execution Authorization Spine

ADR-017 的直系后续。不要求落地完整 ExecutionAuthorizationReceipt 实现，但要把授权链路操作化为可实现 contract。

- 将 ADR-017 中 ExecutionAuthorizationReceipt 字段规范（plan_id / plan_revision_digest / gate_status / action_proposal_id / authorization_source / fingerprint）从"后续扩展方向"提升为独立里程碑
- 规划 execute_existing_plan 的 authorization context：谁提交、基于哪个 plan revision、经过什么 gate、产生什么 receipt
- 定义 plan revision binding 的失效规则：plan 变更后 receipt 自动失效的判定机制
- 定义 action identity 在 ActionProposal 管线中的唯一性保证
- **Plan materialization authorization boundary**：plan 创建是 side-effecting action，必须走 ActionProposal → Validator 管线。当前 `plan_only → immediate` 硬默认绕过了 Validator 授权，违反核心不变量。P1.5 定义授权缺口、策略选项（`deferred` / `authorized_only` 物化策略）与验收边界。本里程碑不规定具体 runtime 实现位点；凡是使 P2 可落地所必需的最小实现，应在进入 P2 前完成。（此项是 P2 的硬前置——P2 只消费已完成的授权边界，不再背授权缺口）
- 产出：可实现的 authorization contract spec（不一定是完整实现，但足够让后续 P2 的动作层基于此收敛）
- **字段命名对齐**：protocol.md 使用 `revision_digest`（通用 subject identity），ADR-017 使用 `plan_revision_digest`（plan 特化）。P1.5 需明确两者关系：`plan_revision_digest` 是 `revision_digest` 在 plan subject 场景的特化命名，实现时不得混用

### P2: Local Action Contracts on Bound Subjects

在主体已绑定（P1）、授权脊柱已规划（P1.5）的前提下，收敛局部动作 contract。

- 收敛 continue / revise / cancel / inspect 的局部动作 contract
- 动作层只消费已绑定主体，不再承接主体歧义
- 每个动作的 ActionProposal 必须携带 subject identity，validator 基于此做 admission
- 不回头吸收主体歧义问题——如果主体不清，回到 P1 的 subject resolution 链路

### P3a: Contract-Aligned Surface Cleanup

以 protocol/validator 已稳定为前提。清理 runtime 中与已稳定 contract 不一致的旧面。

- 执行 `design.md` sunset 表中标注为 P3a 的 legacy surface 最终清理与复核
- 清理旧 route/alias 到 canonical route family 的迁移残留
- 清理 failure recovery / deterministic guard / decision tables 中基于旧 contract 的分支
- 清理 state 文件中超出 canonical budget 的遗留面
- 不新增 checkpoint type、不扩 ActionProposal schema、不重做 gate 架构

### P3b: Presentation & Projection Cleanup

以 P3a 完成为前提。清理表面层。

- **Changelog 治理（首个切片，可先行）**：脚本从"按文件分组"改为"摘要 + 方案包归因 + 文件附录折叠"；白名单 `.sopify-skills/plan/` 和 `history/` 做方案包归因，`state/` 和临时文件继续排除；过滤 CHANGELOG.md 自引用；旧条目不一口气重写，用 Legacy format 分界线过渡
- 清理 reason phrasing / phase label 特判
- 清理 handoff/output/replay 旧兼容投影
- 清理 tests 中只验证旧概念的断言
- 清理 prompt 中直接引用已 sunset 的旧 contract 的段落

### P4: Host Consumption Governance

宿主只消费稳定 contract，不再定义 machine truth。范围覆盖 prompt、doctor/status、handoff 呈现、接入文档——不只是 prompt 治理。

- prompt 不定义机器契约、不维护路由表
- doctor/status 输出只渲染 machine truth，不作为 truth source
- handoff rendering 只消费结构化字段，不做语义推断
- 接入文档以 protocol.md 为唯一合规入口
- 每条规则通过删除测试
- 渐进式披露：Layer 0 Protocol ≤120 行 → Layer 1 Gate → Layer 2 Phase → Layer 3 Reference（不进 prompt）
- **Builtin skill capability disclosure**：宿主文案稳定表达 builtin skill 的当前能力边界与可消费方式；AGENTS.md 只做消费投影，builtin_catalog 为唯一 truth source。当前 analyze/design/develop 是 phase-bound workflow skill（entry_kind=null, triggers=[]），不宣称 standalone invocation。若后续要支持 builtin skill 显式单独调用，必须先 formalize 独立的 invocation metadata contract / invocation syntax；在该 contract 明确前，本项只做披露，不预设其进入 P2 或单列里程碑。边界：只覆盖 builtin skill，不扩展到外部 skill discovery/routing/distribution（background.md 明确排除）

## 未完成长期项

- [ ] 补宿主级 first-hop ingress proof / diagnostics
- [ ] `~compare` shortlist facade 收敛进默认主链路
- [ ] `workflow-learning` 独立 helper 与更稳定 replay retrieval
- [ ] blueprint 索引摘要更细粒度自动刷新
- [ ] history feature_key 聚合视图
- [x] Protocol Step 1：提取最小协议文档与行为契约 case → `blueprint/protocol.md` v0
- [ ] CrossReview Phase 4a：advisory skill 接入 develop 后审查
- [ ] Plan intake checklist（在 intake 模板/脚本落地前，后续新 plan 开包时手工回答以下问题）：
  1. 主命中哪个蓝图里程碑（P1 / P1.5 / P2 / P3a / P3b / P4）？可附次级影响里程碑
  2. 这次改动定义的是 contract acceptance boundary，还是 execution strategy / implementation wave？（前者进 blueprint，后者留方案包）
  3. 是否新增、删除、替代 action / route / state / checkpoint / receipt 中的任一 machine truth？若是，对照 `design.md` 削减预算表
  4. 若涉及 legacy surface，替代 contract 是否已在 `design.md` sunset 表中对应里程碑稳定？
  5. 若影响 Core promotion rule / hard max / ownership / validator authority，须补充 ADR impact
- [ ] Multi-host review contract 正式化（protocol.md §7 从 informative/draft 升级为 normative）— 部分由 P1 subject identity 升格推进
- [ ] 方案级收敛语义操作化（risk ladder + 验证深度规则 + 多审查者冲突解决）
- [ ] 轻量化产品指标与 acceptance gate（首次上手步骤数、必需文件数、默认 workflow 必需 contract 数）
- [ ] 产品层 ↔ 实现层 contract matrix 正式化（ownership / admission / lifecycle responsibilities）

## 明确延后项

- [-] runtime 全接管 develop orchestrator
- [-] 非 CLI 宿主图形化表单
- [-] history 正文纳入默认长期上下文
- [-] daily index
- [-] ~replay 更多入口
- [-] runtime 独立 preferences_artifact
- [-] 偏好自动归纳/提炼
