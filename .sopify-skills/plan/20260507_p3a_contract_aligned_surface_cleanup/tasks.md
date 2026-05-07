# Tasks: P3a Contract-Aligned Surface Cleanup

## 执行切片顺序

```
A0: 文档矛盾收口（本次已完成）
 ↓
A: review_or_execute_plan 最终删除 + plan review 语义迁移（14 runtime targets + guard/projection/resume 迁移）
 ↓
B: Execution routing 收敛（validator AUTHORIZE → deterministic route）
 ↓
C: Runtime 减重（dead path pruning, 目标 26K→<20K）

D: knowledge_sync audit trail（独立尾项，不与 A/B/C 绑死）
```

## Phase A: `review_or_execute_plan` 最终删除 + plan review 语义迁移

- [x] A1: `handoff.py` — plan_only 分支改为返回 `"continue_host_develop"`
- [x] A2: `develop_callback.py` — **仅 `_submit_quality_checkpoint` 路径（L484）**：`resume_after` 改为 `"continue_host_develop"` + 设置 `resume_route = "plan_only"`；通用 checkpoint 创建路径（L372）`resume_route="resume_active"` 保持不变
- [x] A3: `checkpoint_request.py` — `DEVELOP_RESUME_AFTER_ACTIONS` 移除 `"review_or_execute_plan"`（仅保留 `"continue_host_develop"`）
- [x] A4: `engine.py:1740/1803` — resume 判定改为检查 `resume_route == "plan_only"` 回退到 plan review
- [x] A5: `engine.py:2401` — `next_required_action` 改为 `"continue_host_develop"`
- [x] A6: `deterministic_guard.py` — 移除独立 entry，plan review guard 逻辑合入 `continue_host_develop` 分支（以 `current_run.stage == "plan_generated"` 判定）
- [x] A7: `action_projection.py` — 移除独立 builder，plan review 字段合入 `continue_host_develop` projection（以 plan_generated 状态条件触发）
- [x] A8: `plan_orchestrator.py` — stable action 判定改为三条件：`required_host_action == "continue_host_develop"` + `route_name == "plan_only"` + `guard.resume_target_kind == "plan_review"`
- [x] A9: `vnext_phase_boundary.py` — 从 supported set 移除
- [x] A10: `output.py` — 删除 `review_or_execute_plan` 独立 case；在 `continue_host_develop` 分支内新增 `route_name == "plan_only"` → `labels["next_plan"]`
- [x] A11: contracts 清理 — `failure_recovery_table.yaml`、`decision_tables.yaml` 删除 entry；3 个 schema.json 从 enum 移除（resolution_planner / sidecar_classifier_boundary 直接不产出 artifact）
- [x] A12: `test_context_v1_scope.py` 等集成测试 — plan_only 场景的 planner/boundary artifacts 已删除（旧 rows 为 no-op），更新断言
- [x] A13: 添加 fail-closed 测试：state 中残留 `review_or_execute_plan` → state_conflict / inspect-required
- [x] A14: 删除或改写 tests 中仅验证 `review_or_execute_plan` 旧行为的 test cases（allowlist 外的引用全部清除）
- [x] A15: 验证 grep 门：`runtime/` 零引用；活跃 `.sopify-skills/blueprint/` 仅 informative/已收口注释；`tests/` 仅 allowlist 内保留
- [x] A16: 全量测试通过（670 passed, 0 failures）

## Phase B: Execution routing 收敛

- [x] B1: 实现 `_derive_route_from_authorized_proposal()` in engine.py
- [x] B2: 提取 `estimate_complexity()` 为 router.py 公开函数（供 B1 消费）；提取 `decide_capture_mode()` 为共享 helper（derive + classify 共用）
- [x] B3: engine.py L712-715 三路分支改写（proposal_override / derive / router.classify fallback）
- [x] B4: 添加路由收敛测试（每个 action_type → 预期 route_name；验证不依赖 Router.classify 做主判定）
- [x] B5: 添加 modify_files complexity 回归测试（simple → quick_fix / complex → workflow；capture_mode parity 验证）
- [x] B6: 添加 checkpoint_response 分流测试（无 active checkpoint → REJECT）
- [x] B7: 添加 propose_plan 端到端回归测试（plan_artifact + handoff 验证）
- [x] B8: 裸文本请求回归测试（Router.classify 仍正常工作）
- [x] B9: 全量测试通过（681 passed, 46 subtests passed）

## Phase C: Runtime 减重

- [ ] C1: 基于 A/B 后的 dead code analysis，列出模块级删除清单
- [ ] C2: 执行删除（每模块单独确认测试通过）
- [ ] C3: decision_tables.py 裁剪旧 route/action entries
- [ ] C4: deterministic_guard.py 裁剪已删 surface 的 guard entries
- [ ] C5: context_snapshot.py 裁剪只服务已删 route 的逻辑
- [ ] C6: 验证 LOC < 20K
- [ ] C7: 全量测试通过

## Phase D: knowledge_sync audit trail（尾项）

- [ ] D1: 评估 archive finalize 路径是否允许零成本挂接
- [ ] D2: 如可行：追加 knowledge_sync_result 写入逻辑 + receipt 模板更新 + 测试
- [ ] D3: 如需重构 finalize 路径：defer 到 P3b，标记为 out-of-scope

## Blueprint 同步

- [ ] E1: design.md sunset 表标记 `review_or_execute_plan` 为 ✅ 已完成
- [ ] E2: tasks.md P3a 更新完成状态
- [ ] E3: protocol.md §7 如有 `review_or_execute_plan` 引用则清理

## 完成标准

- 全量测试通过（670+ tests, 0 regression）
- grep `review_or_execute_plan` 在 `runtime/` 和活跃 `.sopify-skills/blueprint/` = 0 hits（排除 history/ 和 CHANGELOG.md）
- grep `review_or_execute_plan` 在 `tests/` 仅限 fail-closed / compatibility coverage allowlist 内保留
- Authorized ActionProposal 不再依赖 Router.classify() 做主路由判定（modify_files 仅经提取后的 complexity helper）
- propose_plan 最终 runtime result 可观察行为与旧路径一致（plan_artifact.level + handoff），不只验证 derive 中间值
- checkpoint_response 正确分流到 clarification_resume / decision_resume（仅 active 状态 {"pending","collecting"} 可 resume；terminal 状态 → REJECT）
- runtime/*.py LOC < 20,000
- D（knowledge_sync）按实际成本决定是否进入本里程碑
