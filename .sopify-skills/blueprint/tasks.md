# 蓝图路线图与待办

本文定位: 路线图全景 + 未完成长期项与明确延后项。已完成里程碑仅保留一行摘要与归档指引。不替代当前 plan 的执行任务清单。

## 执行优先级（已确认）

以下顺序是硬约束。前一项未稳定前，不进入后一项实现。

> **对齐原则**：Sopify 总方向是 Protocol-first / Validator-centered / Runtime-optional。主航道的每一步都是"先 formalize protocol/validator 层契约，再让 runtime 作为参考实现消费"。不以 runtime 内部治理为驱动。蓝图变更优先做能强化证据与授权层的事，优先做能让外部宿主看懂、接入、被验证的事；AI + 单人维护应串行收敛，不同时开多条线。

> **先行切片例外**：以下两类改动不受上述顺序约束：① 已在后续里程碑描述中显式标注"可先行"的 presentation-only 切片；② 已证明不影响 protocol / validator / runtime machine contract 的纯展示层改动。除此之外，任何涉及契约面的工作必须等前置里程碑稳定。

> **结构重构锚点**：跨 contract 的模块拆分与 legacy control surface 收口应与里程碑同步——P1 后优先 subject resolution / plan lookup 统一入口（✅），P1.5 后优先 authorization policy / gate-receipt 收敛（✅），P2 后优先 action contract adapter 统一（✅），P3a sunset 表最终清理（✅）。engine.py / decision_tables.py 系统拆分属于 Px（runtime_surface_consolidation），需 P4 宿主消费面固化后执行。不阻止与上述 contract 无关且不改变 machine truth 的低风险整理。

| 优先级 | 任务 | 前置条件 | 说明 |
|--------|------|---------|------|
| P0 | Blueprint rebaseline | 无 | 已完成。重写 blueprint，实体化 ADR，定义削减目标 |
| P1 | subject_identity_binding | P0 | 已完成。protocol / validator / runtime 三联动定义"操作的是谁" |
| P1.5 | execution_authorization_spine | P1 | 已完成。操作化 ADR-017 ExecutionAuthorizationReceipt，规划授权链路 |
| P2 | local_action_contracts | P1.5 | 已完成。在主体已绑定前提下收敛局部动作 contract |
| P3a | contract_aligned_cleanup | P2 | 已完成。以 protocol/validator 已稳定为前提，清理 runtime 旧 contract 面 |
| P3b | presentation_projection_cleanup | P3a | 清理 prompt/projection/test 旧表面 |
| P4 | host_consumption_governance | P3b | 宿主只消费 contract，不定义 truth |
| Px | runtime_surface_consolidation | P4 | Runtime 结构性减重（26K→<20K），需 P4 宿主消费面固化后再动 |

### P0: Blueprint Rebaseline（已完成）

✅ 已完成。重写 blueprint 三件套、实体化 ADR、定义削减预算表、落地 protocol.md v0。细节见 git history。

### P1: Subject Identity & Existing Plan Binding（已完成）

✅ 已完成（归档：`history/2026-05/20260504_subject_identity_binding/`）。protocol §7 subject identity 升格 normative、Validator admission fail-closed、execute_existing_plan subject binding。P1 语义债（DECISION_REJECT consult 伪装）在 P1.5-A 收口。

### P1.5: Execution Authorization Spine（已完成）

✅ 已完成（4 方案包 + 3 先行切片 + 1 桥接切片）。归档：`history/2026-05/20260505_p15_*` ~ `20260506_p15_*`

### P2: Local Action Contracts on Bound Subjects（已完成）

✅ 已完成。admission contract 闭合（subject binding + delta schema + action-effect pairing）。归档：`history/2026-05/20260506_p2_local_action_contracts/`

### P3a: Contract-Aligned Surface Cleanup（已完成）

✅ 已完成。runtime 旧 contract 面清理 + execution routing 收敛 + knowledge_sync audit trail + dead path cleanup。Runtime 结构性减重（26K→<20K）剥离为 Px。归档：`history/2026-05/20260507_p3a_contract_aligned_surface_cleanup/`

### P3b: Presentation & Projection Cleanup

以 P3a 完成为前提。清理表面层。

- **Changelog 治理（首个切片，可先行）**：脚本从"按文件分组"改为"摘要 + 方案包归因 + 文件附录折叠"；白名单 `.sopify-skills/plan/` 和 `history/` 做方案包归因，`state/` 和临时文件继续排除；过滤 CHANGELOG.md 自引用；旧条目不一口气重写，用 Legacy format 分界线过渡
- 清理 reason phrasing / phase label 特判
- 清理 handoff/output/replay 旧兼容投影
- 清理 tests 中只验证旧概念的断言
- 清理 prompt 中直接引用已 sunset 的旧 contract 的段落
- **Runtime 减重外围清理**：清 tests / prompt / projection / installer / docs 中对 P3a 已删 surface 的引用残留，防止 runtime 瘦了但外围契约残留继续拖累维护

### P4: Host Consumption Governance

宿主只消费稳定 contract，不再定义 machine truth。范围覆盖 prompt、doctor/status、handoff 呈现、接入文档——不只是 prompt 治理。

- prompt 不定义机器契约、不维护路由表
- doctor/status 输出只渲染 machine truth，不作为 truth source
- handoff rendering 只消费结构化字段，不做语义推断
- 接入文档以 protocol.md 为唯一合规入口
- 每条规则通过删除测试
- 渐进式披露：Layer 0 Protocol ≤120 行 → Layer 1 Gate → Layer 2 Phase → Layer 3 Reference（不进 prompt）
- **Builtin skill capability disclosure**：宿主文案稳定表达 builtin skill 的当前能力边界与可消费方式；AGENTS.md 只做消费投影，builtin_catalog 为唯一 truth source。当前 analyze/design/develop 是 phase-bound workflow skill（entry_kind=null, triggers=[]），不宣称 standalone invocation。若后续要支持 builtin skill 显式单独调用，必须先 formalize 独立的 invocation metadata contract / invocation syntax；在该 contract 明确前，本项只做披露，不预设其进入 P2 或单列里程碑。边界：只覆盖 builtin skill，不扩展到外部 skill discovery/routing/distribution（background.md 明确排除）

### Px: Runtime Surface Consolidation

独立里程碑。前置条件：P4 宿主消费面固化。P3a 实证：dead path 层面代码库已很紧（26,179 LOC），进一步减重需模块合并和架构简化，不能用"删死路"范式。

- 目标：runtime/*.py LOC 26K → <20K
- 前提：P4 固化宿主实际消费面后，才知道哪些内部 surface 可安全合并
- 手段：模块合并（resolution_planner + sidecar + vnext 三合一等）、engine.py 拆分、上下文层薄化、compat shim 清退（workspace_preflight vendored fallback ~230 LOC, failure_recovery standalone ~100 LOC）
- 约束：不改 machine contract、不改 protocol 语义、不扩 canonical budget
- 不与 P3a/P3b/P4 绑死——单独立项、单独评估成本

## 未完成长期项

- [ ] 补宿主级 first-hop ingress proof / diagnostics
- [ ] `~compare` shortlist facade 收敛进默认主链路
- [ ] `workflow-learning` 独立 helper 与更稳定 replay retrieval
- [ ] blueprint 索引摘要更细粒度自动刷新
- [ ] history feature_key 聚合视图

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
- [-] Convention 入口兑现差距 → 已转入 P1.5 可先行切片，非落地完成
- [ ] 产品层 ↔ 实现层 contract matrix 正式化（ownership / admission / lifecycle responsibilities）
- [ ] Protocol Compliance Phase 2：在 Phase 1 文件断言之上，参考 Superpowers headless behavioral test 做端到端行为验证；扩展 Convention smoke 到完整最小生命周期（含 knowledge_sync / blueprint writeback）。外部启发：Superpowers headless Claude 测试，准入 T1 Adoption
- [ ] 第三方宿主自助接入 Convention 证明：不指定下一个官方深适配目标，先把 Convention quickstart + compliance check 做出来，再由外部宿主自行验证接入

## 明确延后项

- [-] runtime 全接管 develop orchestrator
- [-] 非 CLI 宿主图形化表单
- [-] history 正文纳入默认长期上下文
- [-] daily index
- [-] ~replay 更多入口
- [-] runtime 独立 preferences_artifact
- [-] 偏好自动归纳/提炼
- [-] `sopify init --minimal` 等新增 CLI 面（Convention 入口优先通过文档/模板兑现）
- [-] 知识自动提炼（Hermes Agent persistent memory + curator 方向，T0 Reference；与 runtime 全接管、偏好自动归纳有直接张力）
- [-] 声明式工作流引擎（Spec-Kit YAML workflow engine 方向，T0 Reference；与 Runtime-optional 有张力）
