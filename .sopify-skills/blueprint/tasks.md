# 蓝图路线图与待办

本文定位: 路线图全景 + 未完成长期项与明确延后项。已完成里程碑仅保留一行摘要与归档指引。不替代当前 plan 的执行任务清单。

## 执行优先级（已确认）

以下顺序是硬约束。前一项未稳定前，不进入后一项实现。

> **对齐原则**：Sopify 总方向是 Protocol-first / Validator-centered / Runtime-optional。主航道的每一步都是"先 formalize protocol/validator 层契约，再让 runtime 作为参考实现消费"。不以 runtime 内部治理为驱动。蓝图变更优先做能强化证据与授权层的事，优先做能让外部宿主看懂、接入、被验证的事；AI + 单人维护应串行收敛，不同时开多条线。

> **先行切片例外**：以下两类改动不受上述顺序约束：① 已在后续里程碑描述中显式标注"可先行"的 presentation-only 切片；② 已证明不影响 protocol / validator / runtime machine contract 的纯展示层改动。除此之外，任何涉及契约面的工作必须等前置里程碑稳定。

> **结构重构锚点**：跨 contract 的模块拆分与 legacy control surface 收口应与里程碑同步——P1 后优先 subject resolution / plan lookup 统一入口（✅），P1.5 后优先 authorization policy / gate-receipt 收敛（✅），P2 后优先 action contract adapter 统一（✅），P3a sunset 表最终清理（✅）。engine.py / decision_tables.py 系统拆分属于 P4b（runtime_surface_consolidation），需 P4a 外部消费面冻结后执行。不阻止与上述 contract 无关且不改变 machine truth 的低风险整理。

| 优先级 | 任务 | 前置条件 | 说明 |
|--------|------|---------|------|
| P0 | Blueprint rebaseline | 无 | 已完成。重写 blueprint，实体化 ADR，定义削减目标 |
| P1 | subject_identity_binding | P0 | 已完成。protocol / validator / runtime 三联动定义"操作的是谁" |
| P1.5 | execution_authorization_spine | P1 | 已完成。操作化 ADR-017 ExecutionAuthorizationReceipt，规划授权链路 |
| P2 | local_action_contracts | P1.5 | 已完成。在主体已绑定前提下收敛局部动作 contract |
| P3a | contract_aligned_cleanup | P2 | 已完成。以 protocol/validator 已稳定为前提，清理 runtime 旧 contract 面 |
| P3b | perimeter_cleanup | P3a | 外围面清理：release gate 修复、CHANGELOG 去文件列表化、tests 分类、旧概念清理 |
| P4a | external_surface_freeze | P3b | 薄切片：冻结不可删外部消费面 keep-list |
| P4b | runtime_surface_consolidation | P4a | Runtime 结构性减重（26K→<20K），先删后并 |
| P4c | host_consumption_governance | P4a | 宿主只消费 contract，不定义 truth |

### P0: Blueprint Rebaseline（已完成）

✅ 已完成。重写 blueprint 三件套、实体化 ADR、定义削减预算表、落地 protocol.md v0。细节见 git history。

### P1: Subject Identity & Existing Plan Binding（已完成）

✅ 已完成（归档：`history/2026-05/20260504_subject_identity_binding/`）。protocol §7 subject identity 升格 normative、Validator admission fail-closed、execute_existing_plan subject binding。P1 语义债（DECISION_REJECT consult 伪装）在 P1.5-A 收口。

### P1.5: Execution Authorization Spine（已完成）

✅ 已完成（4 方案包 + 3 先行切片 + 1 桥接切片）。归档：`history/2026-05/20260505_p15_*` ~ `20260506_p15_*`

### P2: Local Action Contracts on Bound Subjects（已完成）

✅ 已完成。admission contract 闭合（subject binding + delta schema + action-effect pairing）。归档：`history/2026-05/20260506_p2_local_action_contracts/`

### P3a: Contract-Aligned Surface Cleanup（已完成）

✅ 已完成。runtime 旧 contract 面清理 + execution routing 收敛 + knowledge_sync audit trail + dead path cleanup。Runtime 结构性减重（26K→<20K）剥离为 P4b。归档：`history/2026-05/20260507_p3a_contract_aligned_surface_cleanup/`

### P3b: Perimeter Cleanup

以 P3a 完成为前提。清理外围面，为 P4 系列减重扫清障碍。

- **Release gate 修复**：`release-preflight.sh` 从 `unittest discover`（当前环境挂死）改为 `pytest`
- **CHANGELOG 去文件列表化**：旧 102 条自动生成条目直接压成阶段摘要（不逐条迁移）；新条目只写 Summary + Changed，不列文件；修 `release-draft-changelog.py` 只产摘要，不产文件清单；同步更新 CONTRIBUTING.md changelog 说明
- **Tests 分类**：`tests/test_*.py` 按 contract（必保）/ smoke（必保）/ distribution（必保）/ implementation-mirror（可砍）标注，为 P4b 减重做分类基础
- **旧概念清理**：tests 中验证 P3a 已 sunset surface 的断言、prompt 中引用已 sunset contract 的段落、handoff/output/replay 旧兼容投影、reason phrasing / phase label 特判
- **evals 生成物治理**：`evals/skill_eval_report.json` 是脚本生成物，从 repo 真值中移除（`.gitignore`），baseline 和 SLO 保留
- **README 首屏降噪与默认入口翻转**：首屏只保留"中断可恢复 + 需要拍板时会停 + 安装入口"三件事；默认叙事以 Convention（纯协议、无 runtime）为入口，Runtime（完整编排、gate、checkpoint）定位为增强路径；plan lifecycle / blueprint / runtime gate / checkpoint taxonomy / task size routing / .sopify-runtime 等内部术语降级到二级文档（how-sopify-works / protocol.md），不在首接触面前置暴露。`.sopify-runtime` 只作为后台实现细节出现，不作为用户首接触概念。目的：为 P4c 运行时首接触验收创造前提
- **replay 能力下线**：删除 replay/ 目录数据；移除 runtime 中 replay 写入逻辑（replay.py、engine.py replay 事件、develop_callback.py replay 记录、handoff.py replay_session_dir 附件、output.py replay 展示）；清 README / skill 列表 / docs 中对 replay 和 workflow-learning 的引用。replay 不进机器事实链（纯 append-only，无回读），下线不影响 gate/router/handoff 决策链路。workflow-learning 能力同步下线，未来如需重设计另行评估
- **Runtime 减重外围清理**：清 tests / prompt / projection / docs 中对 P3a 已删 surface 的引用残留

### P4a: External Surface Freeze

薄切片。列出不可删除的外部消费面 keep-list，作为 P4b 减重的红线边界。

- 枚举 keep-list：protocol.md、gate contract（gate_receipt schema）、handoff/receipt machine truth fields、archive truth（ArchiveCheckResult / ArchiveApplyResult）、install.sh/install.ps1 contract（SOURCE_CHANNEL, SOURCE_REF）、builtin_catalog.py 导出接口（freeze 指接口契约形态——schema / entry_kind / metadata contract，不指具体 skill 枚举或文件字节；能力上下线属内容变更，不违反 freeze）、skill_eval baseline/SLO
- **冻结 persistence surface 分类**：keep-list 覆盖到目录级别（参照 design.md "Persistence Surface 分层"表），明确哪些目录属于长期知识/主链真相/凭证/可删派生，作为 P4b 减重和 P4c 宿主消费治理的红线
- 输出：design.md 加 "Frozen External Surface" 表（与 Persistence Surface 分层互补——后者分类所有持久化面，Frozen 表只冻结外部消费面的 keep-list；不重复造表）
- 不写代码，纯边界确认

### P4b: Runtime Surface Consolidation

P4a keep-list 确认后执行。先删后并，不先设计新结构。

- 目标：runtime/*.py LOC 26K → <20K
- 红线：ActionProposal → Validator → Handoff/Receipt/Archive 主链完整；keep-list 内保留，keep-list 外默认删除
- 执行顺序（硬约束，不可并行跳跃）：
  1. release gate 范围收口 — 发布门禁从全量测试缩为 contract + smoke + distribution + eval gate（runner 切换在 P3b 完成）
  2. runtime 旧面删除 — 砍 compat / bridge / fallback / 旧分支；此时 implementation-mirror tests 仍在，作为管道完整性验证
  3. implementation-mirror tests 收口 — runtime 瘦身稳定后，删除保护对象已不存在的镜像测试
- 不允许在 release gate 未降载前同步大规模删除 runtime 与 mirror tests
- 约束：不改 machine contract、不改 protocol 语义、不扩 canonical budget
- 不先承诺合并方案 — 删完再评估是否需要并文件

### P4c: Host Consumption Governance

宿主只消费稳定 contract，不再定义 machine truth。独立于减重，P4a 之后可与 P4b 并行或顺序执行。

- prompt 不定义机器契约、不维护路由表
- doctor/status 输出只渲染 machine truth，不作为 truth source
- handoff rendering 只消费结构化字段，不做语义推断
- 接入文档以 protocol.md 为唯一合规入口
- **宿主消费边界**：宿主只允许消费"主链机器真相"层（current_run/current_plan/current_handoff/current_clarification/current_decision）和"可审计凭证"层（gate_receipt/archive_receipt）；不得消费 state/sessions/* 内部细节、last_route 等 runtime-only/derived 面（参照 design.md "Persistence Surface 分层"表）
- **验收 (a) 文档递进顺序**：渐进式披露 Layer 0 Protocol ≤120 行 → Layer 1 Gate → Layer 2 Phase → Layer 3 Reference（不进 prompt）
- **验收 (b) 运行时首接触感知**：新用户首次使用时，只感知到"中断可恢复"和"需要拍板时会停"两个语义；blueprint / checkpoint taxonomy / runtime state 等内部概念不在默认运行时路径中主动暴露。doctor/status 不主动呈现 checkpoint 分类体系，~go 入口不前置 blueprint 概念
- **Builtin skill capability disclosure**：宿主文案稳定表达 builtin skill 的当前能力边界与可消费方式；AGENTS.md 只做消费投影，builtin_catalog 为唯一 truth source。当前 analyze/design/develop 是 phase-bound workflow skill（entry_kind=null, triggers=[]），不宣称 standalone invocation。若后续要支持 builtin skill 显式单独调用，必须先 formalize 独立的 invocation metadata contract / invocation syntax；在该 contract 明确前，本项只做披露，不预设其进入 P2 或单列里程碑。边界：只覆盖 builtin skill，不扩展到外部 skill discovery/routing/distribution（background.md 明确排除）

## 未完成长期项

- [ ] 补宿主级 first-hop ingress proof / diagnostics
- [ ] `~compare` shortlist facade 收敛进默认主链路
- [-] `workflow-learning` 独立 helper 与更稳定 replay retrieval → P3b replay 能力下线后，未来如需重设计另行评估
- [ ] blueprint 索引摘要更细粒度自动刷新
- [ ] history feature_key 聚合视图

- [ ] CrossReview Phase 4a：advisory skill 接入 develop 后审查
- [ ] Plan intake checklist（在 intake 模板/脚本落地前，后续新 plan 开包时手工回答以下问题）：
  1. 主命中哪个蓝图里程碑（P3b / P4a / P4b / P4c）？若不命中主线，须显式标记为"长期项"或"延后项"，不强行归类
  2. 这次改动定义的是 contract acceptance boundary，还是 execution strategy / implementation wave？（前者进 blueprint，后者留方案包）
  3. 是否新增、删除、替代 action / route / state / checkpoint / receipt 中的任一 machine truth？若是，对照 `design.md` 削减预算表
  4. 若涉及 legacy surface，替代 contract 是否已在 `design.md` sunset 表中对应里程碑稳定？
  5. 若影响 Core promotion rule / hard max / ownership / validator authority，须补充 ADR impact
- [ ] Multi-host review contract 正式化（protocol.md §7 从 informative/draft 升级为 normative）— 部分由 P1 subject identity 升格推进
- [ ] 方案级收敛语义操作化（risk ladder + 验证深度规则 + 多审查者冲突解决）
- [ ] 轻量化产品指标与 acceptance gate（首次上手步骤数、必需文件数、默认 workflow 必需 contract 数）
- [-] Convention 入口兑现差距 → 已转入 P1.5 可先行切片，非落地完成
- [ ] 产品层 ↔ 实现层 contract matrix 正式化（ownership / admission / lifecycle responsibilities）
- [ ] Protocol Compliance Phase 2：在 Phase 1 文件断言之上，参考 Superpowers headless behavioral test 做端到端行为验证；扩展 Convention smoke 到完整最小生命周期（含 knowledge_sync / blueprint writeback）。外部启发：Superpowers headless Claude 测试，准入 T1 Adoption。_触发条件：P4c 验收通过后评估是否提升为里程碑_
- [ ] 第三方宿主自助接入 Convention 证明：不指定下一个官方深适配目标，先把 Convention quickstart + compliance check 做出来，再由外部宿主自行验证接入。_触发条件：P4c 验收通过后评估是否提升为里程碑_
- [ ] First-Use Adoption Proof：验证非作者用户/宿主能安装、触发、理解、走通 Sopify 首次使用链路。覆盖 install/bootstrap 文案压缩、status/doctor 用户语言化验收、scripts 用户面与维护面分离、至少一个非作者首次采用 walkthrough。前提：P4c 已确保默认路径不暴露内部 taxonomy。边界：只做首次采用证明与用户面收口，不重开 protocol/runtime 产品定位，不回头扩 machine contract，不把维护者脚本整理泛化成大规模重构。语义方向待收窄（External Adoption Proof 或 User-Facing Onboarding Convergence），编号待定。_触发条件：P4c 验收通过后评估是否提升为里程碑_

## 明确延后项

- [-] runtime 全接管 develop orchestrator
- [-] 非 CLI 宿主图形化表单
- [-] history 正文纳入默认长期上下文
- [-] daily index
- [-] ~replay 更多入口 → P3b replay 能力已下线
- [-] runtime 独立 preferences_artifact
- [-] 偏好自动归纳/提炼
- [-] `sopify init --minimal` 等新增 CLI 面（Convention 入口优先通过文档/模板兑现）
- [-] 知识自动提炼（Hermes Agent persistent memory + curator 方向，T0 Reference；与 runtime 全接管、偏好自动归纳有直接张力）
- [-] 声明式工作流引擎（Spec-Kit YAML workflow engine 方向，T0 Reference；与 Runtime-optional 有张力）
