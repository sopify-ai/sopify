# 任务清单: P1.5-A DECISION_REJECT Surface 收口

目录: `.sopify-skills/plan/20260506_p15_reject_surface/`

## 1. Engine 层 — Reject 路由独立化

- [x] T1-A: engine.py reject 分支 route_name 改为 "proposal_rejected"
  - `engine.py:664` RouteDecision route_name 从 "consult" 改为 "proposal_rejected"
  - 注入 artifacts: `{"reject_reason_code": validation_decision.reason_code}`
  - 验收: reject 路径 route_name == "proposal_rejected" + artifacts 含 reject_reason_code

- [x] T1-B: engine.py _NON_FAMILY_SURFACES 扩口
  - 添加 "proposal_rejected" 到 frozenset
  - 验收: `"proposal_rejected" in _NON_FAMILY_SURFACES`

## 2. Handoff 层 — Reject Kind 注册

- [x] T2-A: handoff.py _ROUTE_HANDOFF_KIND 新增映射
  - 添加 `"proposal_rejected": "reject"` 到映射表
  - 验收: proposal_rejected 路由能生成 handoff（不返回 None）

- [x] T2-B: handoff.py _required_host_action 新增分支
  - 添加 `if route_name == "proposal_rejected": return "continue_host_consult"`
  - 验收: reject handoff 的 required_host_action == "continue_host_consult"

## 3. Output 层 — Reject 投影修正

- [x] T3-A: output.py _PHASE_LABELS 新增 reject 阶段标签
  - 新增 `"proposal_rejected"` 条目到 zh-CN 和 en-US
  - 中文: "操作被拒绝" / 英文: "Action Rejected"
  - 验收: 阶段标题显示拒绝语义

- [x] T3-B: output.py _status_message 新增 reject 拦截
  - 在 L454 handoff required_host_action 查表之前，拦截 `route_name == "proposal_rejected"`
  - 返回 reject 专用文案（不让它落入 `handoff_continue_host_consult`）
  - 中文: "操作被拒绝，请查看原因" / 英文: "Action rejected; review the reason"
  - 验收: reject 场景 _status_message 不显示"已进入咨询问答"

- [x] T3-C: output.py _handoff_next_hint 新增 reject 分支
  - 在 `_handoff_next_hint` 中按 `handoff_kind == "reject"` 区分
  - 中文: "操作被拒绝，请查看原因后重新提交" / 英文: "Action rejected; review the reason and resubmit"
  - 验收: reject 场景不显示 consult next hint 文案

- [x] T3-D: output.py _status_symbol 新增 reject 分支
  - `_status_symbol()` 对 `route_name == "proposal_rejected"` 返回 `"!"`
  - 验收: reject 标题状态符为 `!`，不是 `✓`

## 4. Blueprint 层 — 表面注册

- [x] T4-A: design.md Non-family Surfaces 表新增 proposal_rejected
  - 分类: 跨路由错误面
  - 说明: Validator DECISION_REJECT 独立 surface
  - 验收: 表中有 proposal_rejected 行

## 5. 测试

- [x] T5-A: reject 路由断言更新
  - 现有 test_action_intent.py 中 reject 测试：断言 route_name == "proposal_rejected"（不再仅断言 ∉ EXEC_ROUTES）
  - 验收: 断言更精确

- [x] T5-B: reject handoff 断言
  - handoff_kind == "reject"
  - reject_reason_code in artifacts
  - required_host_action == "continue_host_consult"
  - 验收: handoff 结构正确

- [x] T5-C: 真 consult 不回归
  - 正常 consult 路由（非 reject 触发）→ route_name == "consult", handoff_kind == "consult"
  - 验收: consult 路径不受影响

- [x] T5-D: digest mismatch admission reject 走新 surface
  - plan 内容变更 + 旧 digest → admission DECISION_REJECT → route_name == "proposal_rejected"
  - 验收: admission reject 命中新 surface

- [x] T5-E: missing plan_subject reject 走新 surface
  - 无 plan_subject → DECISION_REJECT → route_name == "proposal_rejected"
  - 验收: admission reject 也命中新 surface

- [x] T5-F: 全量 pytest 验证
  - 验收: 全量通过 + 无回归

## 6. 蓝图回写

- [x] T6-A: 更新 blueprint/tasks.md P1.5-A 状态
  - 验收: A 标记完成

## 已知测试债（Follow-up）

- [ ] stale receipt run-level integration test（不阻塞 P1.5-A 主提交）
  - 真正的 stale-receipt reject 需要跨 run 的 state 持久化：第一次 run 生成 receipt → 修改 plan → 第二次 run 传新 digest 通过 admission → `_check_stale_receipt()` 发现旧 receipt digest 不匹配 → reject
  - 当前 unit 层 stale receipt 检测已有测试覆盖（`_check_stale_receipt` 单元测试）
  - run-level integration proof 归 T5-C follow-up，不混入 P1.5-A
