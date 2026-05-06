# 变更提案: P1.5-A DECISION_REJECT Surface 收口

## 需求背景

P1 引入 DECISION_REJECT 语义（validator 显式拒绝 ActionProposal），但当时以 consult route 作为临时阻断机制，
未建立独立的 reject host-facing surface。结果是宿主无法区分"被拒绝"与"正常问答"——4 层语义全部泄漏为 consult。

### 现状精确表述

- **route_name**：`engine.py:664` — DECISION_REJECT 时 `route_name="consult"`
- **handoff_kind**：通过 `_ROUTE_HANDOFF_KIND["consult"]` 映射为 `"consult"`
- **required_host_action**：通过 `_required_host_action` consult 分支返回 `"continue_host_consult"`
- **output 投影**：`output.py` 的 `_route_label` / `_handoff_next_hint` 将 reject 渲染为 consult 文案
- **reason**：`action_proposal_rejected: {reason_code}` 仅作为自由文本 reason 字符串，无结构化 artifact

**State 层**：reject 不做 state mutation（正确行为，engine.py:662 注释已明确）。

### P1 语义债清单

`blueprint/tasks.md` P1.5 蓝图条目 #1：
> DECISION_REJECT surface 收口 — P1 的 validator reject 当前通过 consult route 阻断执行，
> 但对宿主暴露的 surface 仍表现为 consult。P1.5 需扩展 handoff 白名单和 gate 输出，
> 使 reject 有独立的结构化 surface。

## 蓝图依据

- `blueprint/tasks.md:83` — P1.5-A 定义（蓝图条目 #1）
- `blueprint/tasks.md:89` — 蓝图条目 #1 详述
- `blueprint/design.md:240-254` — Non-family Surfaces 定义与扩口规则
- `blueprint/design.md:206-214` — required_host_action canonical 5 预算

## 触发事件

P1.5-B 完成后，stale receipt 检测链路也产生 DECISION_REJECT。
如果 reject surface 仍是脏的（穿 consult 皮），D（Verifier normative slice）在定义 Verifier 输出消费路径时
会把错误表面继续制度化。A 是 D 的事实前置。
