# 变更提案: P1.5 Plan Materialization Authorization Boundary

## 需求背景

蓝图 tasks.md:65 明确指出：

> plan 创建是 side-effecting action，必须走 ActionProposal → Validator 管线。
> 当前 `plan_only → immediate` 硬默认绕过了 Validator 授权，违反核心不变量。

当前实现存在双重硬默认：
- `router.py:758` — `_plan_package_policy_for_route` 对 plan_only/workflow/light_iterate 返回 `"immediate"`
- `engine.py:1913-1916` — `_normalized_plan_package_policy` 兜底再次硬编码 `"immediate"`

同时，router 的 `_is_consultation` 使用 `_ACTION_KEYWORDS` 做 substring match，
单字如"修"会误命中分析类请求（如"批判看下哪些必须修"），
导致咨询请求被误判为 change intent，进入 planning route 后直接生成方案包。

两层叠加的结果：分析/咨询类请求直接落盘生成 plan 包。

## 蓝图依据

- `blueprint/tasks.md:65` — Plan materialization authorization boundary（P1.5 主线未完成项）
- `blueprint/protocol.md:155` — ActionProposal 是 Producer 交给 Sopify 的结构化提案，不由生产器自己决定执行
- `blueprint/protocol.md:164` — Validator 才有授权权
- `action_intent.py:33` — `write_plan_package` side_effect 已定义
- `action_intent.py:318-325` — Validator 对 side-effecting + evidence 不足的 fail-close 降级已实现

基础设施已就位，只需接线。

## 触发事件

P1.5 先行切片执行过程中，gate 在咨询类请求上误生成了方案包（`20260505_p1-p2-p3/`、`20260505_consult-plan-actionproposal-validator-determinis/`）。
