# Blueprint Truth Cutover — 任务清单

## 验收标准

1. **Runtime 表面符合预算** — checkpoint ≤2, host action ≤5 (canonical), route family ≤6, core state ≤6。超出部分必须标为 `legacy/compat` 且带 sunset 条件，不得在新链路中使用
2. **最小新链路可跑** — `consult` route 完整走通 Protocol → Validator → Receipt（proof command: `python3 scripts/runtime_gate.py enter` + consult 请求；预期产物: `current_handoff.json` 含 canonical `continue_host_consult` action + `current_run.json` + `current_gate_receipt.json`）；proof 前置断言：consult 不经过 plan_proposal / execution_confirm 路径
3. **旧复杂面被显著移除** — runtime 行数或模块数有可观察的下降（方向可证明即可）
4. **Blueprint 是唯一 forward baseline** — 新代码修改以 design.md 预算和契约为前提，不以 runtime 现状为前提
5. **旧面冻结** — 不在 legacy route / legacy host action / legacy state file 上新增功能或扩展
6. **Prompt-layer 同步** — `Codex/Skills/{CN,EN}/AGENTS.md` 中不再规范已删除的 legacy action / state file；宿主消费的契约面与 runtime canonical 面一致
7. **Smoke/bundle 合同同步** — `scripts/check-prompt-runtime-gate-smoke.py` 和 `scripts/sync-runtime-assets.sh` 不再断言或依赖已删除的 legacy action / state file；删旧面后 smoke 仍 pass
8. **测试层同步** — 每波删旧面后，涉及的 test 文件和 fixture YAML 同步更新；现有测试套件 pass（允许删除只验证旧概念的断言，但不允许静默跳过或注释掉）

## 任务

| # | 任务 | 说明 | 同步面 | 状态 |
|---|------|------|--------|------|
| 1 | 盘点 legacy 面 | 列出 runtime 中超出 canonical 预算的所有 route / host action / checkpoint / state，标注引用范围、耦合深度、按层归类 | — | pending |
| 2 | 冻结旧面扩展 | 在 contributing/review 流程中明确：不在 legacy 面上新增功能 | — | pending |
| 3 | Wave 1（低耦合） | 删除 `continue_host_quick_fix`→`continue_host_develop`、`host_replay_bridge_required`→`continue_host_workflow`、`archive_completed`→`archive_review`（降为结果状态，Next 提示按 archive_status 区分）。233 测试全通过 | prompt-layer/smoke/contracts 无引用 | done |
| 4a | Wave 2a（低风险） | `continue_host_workflow`(17 refs) → `continue_host_develop(mode=standard)` 合并。runtime/tests 零残留，`_handoff_next_hint` 按 route_name 智能分发，233 测试全通过 | deterministic_guard 合并后 inspect 泄漏到全场景（Wave 2d 统一处理） | done |
| 4b | Wave 2b | `archive_review`(30 refs) 从 host action 退出，archive 变成 terminal receipt surface。host-facing action 复用 `continue_host_consult`，结果由 `archive_lifecycle` artifact + `archive_receipt_status`(completed\|review_required) + `current_archive_receipt.json` 表达。deterministic_guard / action_projection / output 专用分支已删除。冻结约束写入 `test_contract_consistency.py`。663→662 tests (3 旧 projection tests 合并为 2 新 tests)，全通过 | 涉及断言 + action_projection + deterministic_guard + gate normalize + 冻结约束 | done |
| 4c | Wave 2c | `develop_checkpoint` 完整重命名为 `develop_callback`。保留 helper 能力（host 仍通过回调 runtime 触发 clarification/decision），但从所有机器契约面退出 checkpoint/route 概念。26 个活跃文件，含 runtime(6)/installer(4)/scripts(3)/prompt-layer(4)/tests(4)/infra(1)/docs(3)/release(1)。不兼容、不加 legacy alias、不扩语义。checkpoint_kind 和 route names 不改。接受 hard cutover：旧 develop session 不兼容，不做 alias/migration | runtime + installer + scripts + prompt-layer + smoke/sync + tests + .githooks/pre-commit + project.md | done |
| 4d | Wave 2d（route family 真收敛） | handoff.py 5 个映射收敛到 canonical family（workflow→plan, light_iterate→plan, quick_fix→develop, archive_lifecycle→archive, replay→consult）。engine.py 添加 `_CANONICAL_ROUTE_FAMILIES` + `_NON_FAMILY_SURFACES`。output.py 消除旧 handoff_kind 分支。blueprint/design.md 回写 Route Families 覆盖表 + Non-family surfaces 段落。deterministic_guard / gate 无需改动。归宿决策：summary/cancel_active 为 non-family surface | handoff + engine + output + builtin_catalog + skill.yaml + tests(state/gate/engine/router) + blueprint(design.md/README.md) | done |
| 4e | Wave 2 consult proof | 绑定 Wave 2d 完成态。Proof: `python3 scripts/runtime_gate.py enter` + consult → handoff 含 `continue_host_consult` + `handoff_kind=consult` + receipt 完整。前置断言：consult 不经过 plan_proposal/execution_confirm | — | done |
| 5 | Wave 3a（plan_proposal） | 单拆 `plan_proposal`(162 refs/16 files)。一并折叠 `current_plan_proposal.json`、`confirm_plan_package`、`plan_proposal_pending`。涉及状态解析层 + 控制平面 + 呈现层 | prompt-layer + smoke + `test_context_v1_scope`(47) + `test_runtime_engine`(大量) + `test_runtime_sample_invariant_gate`(37) + contract YAML(30+) | pending |
| 6 | Wave 3b（execution_confirm） | 在 3a 稳定后拆 `execution_confirm`(87 refs/13 files)。一并折叠 `confirm_execute`、`execution_confirm_pending`。涉及状态解析层 + 控制平面 + 呈现层 | prompt-layer + smoke + `test_runtime_engine` + `test_runtime_decision`(52) + `test_runtime_state`(17) + contract YAML | pending |
| 7 | 验收与收口 | 确认 8 条验收标准达成，归档本方案 | — | pending |

## 与 blueprint P1–P4 的关系

本方案高于 P1–P4，但不替代它们，而是重定义它们的语境：

| 原任务 | Cutover 后的新定位 |
|--------|-------------------|
| P1 existing_plan_subject_binding | 在新骨架上做主体绑定，不在旧 route 上做 |
| P2 checkpoint_local_actions | 只收敛 2 canonical checkpoint 的动作，不维护旧 5 种 |
| P3 runtime_surface_cleanup | 从"长期清理"变成 cutover 的结果动作 |
| P4 host_prompt_governance | 前提不变，但 prompt 消费的是新骨架的 contract |
