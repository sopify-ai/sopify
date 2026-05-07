# 变更历史索引

记录已归档的方案，便于后续查询。

## 索引

- `2026-05-08` [`20260507_p3a_contract_aligned_surface_cleanup`](2026-05/20260507_p3a_contract_aligned_surface_cleanup/) - standard - P3a Contract-Aligned Surface Cleanup: execution routing 收敛 + knowledge_sync audit trail + dead path cleanup (-88 LOC) + Runtime 减重剥离为 Px
- `2026-05-07` [`20260506_p2_local_action_contracts`](2026-05/20260506_p2_local_action_contracts/) - standard - P2 Local Action Contracts: subject binding 泛化 + side_effect_delta schema + action-effect canonical pairing（admission contract 闭合）
- `2026-05-06` [`20260506_p15_verifier_normative_slice`](2026-05/20260506_p15_verifier_normative_slice/) - standard - P1.5-D Verifier Minimum Normative Slice: protocol §6 升格 normative（verdict/evidence/source MUST）+ 消费路径 contract + design.md 引用修正
- `2026-05-06` [`20260506_p15_authorization_contract_spec`](2026-05/20260506_p15_authorization_contract_spec/) - standard - P1.5-B Authorization Contract Spec: ExecutionAuthorizationReceipt 8-field normative + generate_proposal_id + stale detection fail-closed
- `2026-05-06` [`20260506_p15_reject_surface`](2026-05/20260506_p15_reject_surface/) - standard - P1.5-A DECISION_REJECT Surface 收口: reject 从 consult 伪装剥离为独立 non-family surface proposal_rejected
- `2026-05-06` [`20260505_p15_plan_materialization_auth`](2026-05/20260505_p15_plan_materialization_auth/) - standard - P1.5-C Plan Materialization Authorization Boundary: plan_package_policy authorized_only + consult 误判止血 + confirm 删除
- `2026-05-06` [`20260505_p15_advance_slices`](2026-05/20260505_p15_advance_slices/) - standard - P1.5 先行切片: Convention 入口兑现 + Protocol Compliance Suite Phase 1 + ~summary surface 全链路删除
- `2026-05-04` [`20260504_subject_identity_binding`](2026-05/20260504_subject_identity_binding/) - standard - P1 Subject Identity & Existing Plan Binding: protocol §7 升格 + validator admission + engine reject + workspace root normalization
- `2026-05-04` ~~`20260416_blueprint_graphify_integration`~~ - deleted - Blueprint 可插拔增强架构 + Graphify（未实现，方向与主线相反，直接删除，git history 留底）
- `2026-05-04` [`20260326_phase1-2-3-plan`](2026-03/20260326_phase1-2-3-plan/) - archived - Phase 1-2-3 旧总纲（B1/B2/B3 语义，已被 P0→P4 蓝图取代）
- `2026-05-04` [`20260417_ux_perception_tuning`](2026-04/20260417_ux_perception_tuning/) - archived - UX 感知层调优（B/C 已完成，A 放弃；不独立拆包）
- `2026-05-04` [`20260429_host_prompt_governance`](2026-04/20260429_host_prompt_governance/) - archived(upstreamed) - Host Prompt Governance（核心观点已进蓝图 P3b/P4，设计推演保留供回看）

- `2026-04-30` [`20260429_standard-archive-finalize-archive-checkpoint`](2026-04/20260429_standard-archive-finalize-archive-checkpoint/) - standard - 任务清单: 为“显式主体与生命周期收敛”主题写第一子切片方案文档：新建 standard 方案包，只覆...
- `2026-05-01` [`20260501_convention_smoke`](2026-05/20260501_convention_smoke/) - smoke - Convention 模式跨宿主最小 roundtrip 验证（Host B: Claude Sonnet + Host C: Codex/GPT-5，5/5 pass）
- `2026-05-01` [`20260429_legacy_feature_cleanup`](2026-05/20260429_legacy_feature_cleanup/) - standard - Legacy Feature Cleanup: consult override 删除 + model compare 功能面移除
- `2026-05-01` [`20260428_action_proposal_boundary`](2026-05/20260428_action_proposal_boundary/) - standard - Action/Effect Boundary P0: ActionProposal validator + consult_readonly thin slice + legacy classifier cleanup
- `2026-03-24` ~~`20260323_unified_plan_history_index`~~ - abandoned - 统一 plan history 索引投影（on_hold，无法验收，2026-04 主动弃置）
- `2026-03-21` ~~`20260320_default_host_bridge_install`~~ - abandoned - 默认宿主桥接一键安装（on_hold，无法验收，2026-04 主动弃置）
- `2026-03-21` ~~`20260320_cursor_plugin_install`~~ - abandoned - Cursor 插件安装（on_hold，路线未定，2026-04 主动弃置）
- `2026-03-24` [`20260324_task`](2026-03/20260324_task/) - standard - Steering: 从 HelloAGENTS/Superpowers 对比收口 Sopify 学习路径（E.1-E.3 全完成）
- `2026-03-26` [`20260326_5-plan-20260326-phase1-2-3-plan-plan-20260326-ph`](2026-03/20260326_5-plan-20260326-phase1-2-3-plan-plan-20260326-ph/) - standard - B1 文档收口后的实施与验证（全部 79 任务完成）
- `2026-04-27` ~~[`20260413_trae_host_adapter`](2026-04/20260413_trae_host_adapter/)~~ - retired - Trae CN 宿主适配（Phase 1-2 已完成，宿主面已退役）
- `2026-04-12` [`20260403_plan-a-risk-adaptive-interruption`](2026-04/20260403_plan-a-risk-adaptive-interruption/) - standard - Plan A 子计划：风险自适应打断与局部语义收敛
- `2026-03-28` [`20260327_hotfix`](2026-03/20260327_hotfix/) - standard - 状态机 Hotfix（B1 前置门禁）
- `2026-03-26` [`20260326_planning-materialization-decoupling`](2026-03/20260326_planning-materialization-decoupling/) - standard - 规划流程与方案包物化解耦
- `2026-03-26` [`20260325_one-liner-distribution`](2026-03/20260325_one-liner-distribution/) - standard - 任务清单: one-liner-distribution
- `2026-03-24` [`20260324_develop-quality-loop`](2026-03/20260324_develop-quality-loop/) - standard - 任务清单: develop-quality-loop
- `2026-03-24` [`20260317_design_decision_confirmation`](2026-03/20260317_design_decision_confirmation/) - standard - 决策确认能力通用化（兼容现有接入链路）
- `2026-03-24` [`20260320_helloagents_integration_enhancements`](2026-03/20260320_helloagents_integration_enhancements/) - standard - 借鉴 HelloAGENTS 的产品接入增强（`helloagents-integration-enhancements`）
- `2026-03-24` [`20260323_models-tests-refactor`](2026-03/20260323_models-tests-refactor/) - standard - runtime models / tests 结构拆分与 bundle smoke 收敛
- `2026-03-23` [`20260323_readme-about-changelog`](2026-03/20260323_readme-about-changelog/) - standard - README / About / CHANGELOG 对外表达收口
- `2026-03-23` [`20260323_runtime-gate-diagnostics`](2026-03/20260323_runtime-gate-diagnostics/) - standard - runtime gate 证据对齐与诊断硬化
- `2026-03-23` [`20260323_runtime-session-lease-session-scoped-review-stat`](2026-03/20260323_runtime-session-lease-session-scoped-review-stat/) - standard - runtime 并发会话隔离修复：引入 session lease + session-s...
- `2026-03-23` [`20260323_plan_registry_governance`](2026-03/20260323_plan_registry_governance/) - standard - 任务清单: plan registry 治理层（`plan-registry-governance`）
- `2026-03-22` [`20260321_go-plan`](2026-03/20260321_go-plan/) - standard - 任务清单: ~go plan
- `2026-03-21` [`20260320_preferences-preload-v1`](2026-03/20260320_preferences-preload-v1/) - standard - 宿主偏好预载入
- `2026-03-21` [`20260320_kb_layout_v2`](2026-03/20260320_kb_layout_v2/) - standard - Sopify KB Layout V2
- `2026-03-20` [`20260320_prompt_runtime_gate`](2026-03/20260320_prompt_runtime_gate/) - standard - Prompt-Level Runtime Gate
