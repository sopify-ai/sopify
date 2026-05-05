# 任务清单: P1.5 Plan Materialization Authorization Boundary

目录: `.sopify-skills/plan/20260505_p15_plan_materialization_auth/`

## 1. L2 — Plan Materialization Authorization Boundary

- [x] T1-A: `_models/core.py` — `PLAN_PACKAGE_POLICIES` 替换为 `("none", "immediate", "authorized_only")`
  - 删除 `"confirm"`（当前线上无用户，不做兼容）
  - 新增 `"authorized_only"`
  - 验收: `RouteDecision(plan_package_policy="authorized_only")` 归一化后仍为 `"authorized_only"`；`confirm` 输入归一化为 `"none"`
- [x] T1-B: `router.py` — `_plan_package_policy_for_route` 默认值改为 `authorized_only`
  - plan_only/workflow/light_iterate 从 `"immediate"` 改为 `"authorized_only"`
  - `~go plan` 命令路径不受影响（`_classify_command` 仍返回 `"immediate"`，D6 本轮显式兼容例外）
  - 验收: 非命令路径返回 `"authorized_only"`
- [x] T1-C: `engine.py` — `_normalized_plan_package_policy` 清理
  - 删除 plan_only/workflow/light_iterate 兜底 `"immediate"` 逻辑（line 1913-1916）
  - 删除 `confirm` → `immediate` 退化逻辑（D7: confirm 已从白名单移除，无需迁移）
  - 缺省/空 policy 返回 `"none"`
  - 验收: 无任何隐式 immediate 路径（除 `~go plan` 显式命令）
- [x] T1-D: `engine.py` — `_advance_planning_route` 增加 authorization check
  - 新增 `plan_materialization_authorized` 参数传递 Validator 授权状态
  - 当 `plan_package_policy == "authorized_only"` 且无授权时，降级到 consult surface，不触发 `create_plan_scaffold` 等写盘操作
  - 降级后保留原始 guard artifacts（`entry_guard_reason_code`、`direct_edit_guard_kind` 等）
  - 验收: 无授权时不创建 plan 目录，handoff 正确返回 `continue_host_consult`
- [x] T1-E: `engine.py` — Validator 授权结果传递到 planning 流程
  - `run_runtime` pre-route interceptor 从 Validator 结果提取 `plan_materialization_authorized`
  - 通过 `_advance_planning_route` 参数传递（不走 RouteDecision artifacts）
  - 验收: `_advance_planning_route` 能区分"经过授权"和"未经过授权"

## 2. L1 — Router consult 误判止血

- [x] T2-A: `router.py` — 收紧 `_ACTION_KEYWORDS`
  - 移除单字"修"和"补"
  - "修" 替换为 "修复" / "修改"（"修复"已存在，只需删"修"）
  - "补" 替换为更精确的短语（或直接删除，依赖"修复"/"添加"/"新增"覆盖）
  - 验收: "批判看下哪些必须修，等我确认" 不再命中 action keyword

## 3. 测试

- [x] T3-A: plan materialization authorization 测试覆盖
  - 无 ActionProposal 时 planning route 降级到 consult，不创建 plan 目录
  - 有 `propose_plan` + `write_plan_package` + authorized 时正常创建
  - `~go plan` 显式命令不受影响
  - feature request regression tests 更新匹配 consult 降级行为
  - 验收: 全量测试通过
- [x] T3-B: `confirm` 存量测试更新
  - 3 处 `plan_package_policy="confirm"` 测试改为 `"authorized_only"`
  - `confirm` 已从白名单删除，无需兼容测试
  - 验收: 无 `plan_package_policy="confirm"` 残留
- [x] T3-C: 增加 consult 误判回归测试
  - "批判看下哪些必须修，等我确认" → router.classify 返回 consult
  - "修复这个 bug" → router.classify 不返回 consult（不回归）
  - 验收: 新测试全部通过
- [x] T3-D: 全量 pytest 验证
  - 验收: 597 tests passed, 46 subtests passed
