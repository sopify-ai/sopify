# 任务清单: P1.5 先行切片

目录: `.sopify-skills/plan/20260505_p15_advance_slices/`

## 1. Convention 入口兑现

- [x] T1-A: 在 README.md Quick Start 章节内增加 Convention Mode 子段落
  - 描述 3 步最小路径（读 blueprint → 写 plan → 归档 + receipt）
  - 引用 protocol.md §4 样例 A 和 §5 合规检查清单
  - 验收: 段落存在 + 内容准确引用协议文档
- [x] T1-B: 在 README.zh-CN.md 同步增加对应中文段落
  - 验收: 中文段落结构与英文一致
- [x] T1-C: 运行 `pytest tests/test_check_readme_links.py` 验证链接完整性
  - 验收: 测试通过

## 2. Protocol Compliance Suite Phase 1

- [x] T2-A: 新建 `tests/protocol/test_convention_compliance.py` 骨架
  - 验收: `pytest tests/protocol/` 可运行（即使 0 test）
- [x] T2-B: 实现断言 1-2（project.md 存在 + blueprint 三件套存在）
  - 使用 tmp_path fixture 构建最小 `.sopify-skills/` 目录
  - 验收: 正向（结构完整）和反向（缺文件）均测试
- [x] T2-C: 实现断言 3-4（plan 创建 + plan.md 必需字段）
  - 在 tmp_path 下创建 plan/YYYYMMDD_feature/plan.md
  - 验证 title / scope / approach / tasks 区块存在
  - 验收: 正向 + 反向（缺必需字段时失败）
- [x] T2-D: 实现断言 5（归档 + receipt.md）
  - 在 tmp_path 下创建 history/YYYY-MM/feature/receipt.md
  - 验证 receipt.md 存在
  - 验收: 正向 + 反向
- [x] T2-E: 验证 `pytest tests/protocol/` 不 import 任何 `runtime.*` 模块
  - 验收: `grep -rn "from runtime\|import runtime" tests/protocol/` 无匹配

## 3. 低风险辅助层预清理（daily_summary）

- [x] T3-A: 验证 `_models/summary.py` 中各 class 的消费方
  - grep 全量引用，确认哪些 class 仅被 daily_summary 消费
  - 记录结论到本任务备注（共用 class 保留，专属 class 删除）
  - 验收: 消费方分析结果记录完毕
  - 结论: 全部 16 个 class 均为 daily_summary 专属，整文件删除
- [x] T3-B: 删除 `runtime/daily_summary.py` + 清理 `runtime/engine.py` 中的 import 和调用点
  - 删除 `runtime/router.py` 中 `~summary` 命令匹配、`summary` route 支持、以及 capture/decision 相关分支
  - 删除 `runtime/__init__.py` 中 `DailySummaryArtifact` public export
  - 删除 `runtime/engine.py` 中 summary 相关 import 和 4 处分支（last_route 豁免、build_daily_summary 调用、handoff 保留分支、phase 映射）
  - 验收: router/engine/__init__ 不再暴露或消费 summary route
- [x] T3-C: 清理 `runtime/output.py` 中全部 summary 专属分支
  - 删除 phase label、`next_summary` 文案、`_render_daily_summary_output`、以及 `summary` route 相关的 `_collect_changes` / `_next_hint` / `_status_symbol` / `_status_message` 分支
  - 验收: output.py 不再包含 summary route 的专属渲染与提示逻辑
- [x] T3-D: 清理 `runtime/_models/summary.py` + `runtime/models.py` re-export
  - 按 T3-A 结论删除 daily_summary 专属 class
  - 清理 `runtime/models.py` 中对应的 re-export
  - 验收: 无 daily_summary 专属 class 残留
- [x] T3-E: 清理测试文件
  - 删除 `tests/test_runtime_summary.py`（175 行）
  - 清理 `tests/runtime_test_support.py:47` 的 import
  - 清理 `tests/test_runtime_engine.py:2338` 的 mock patch
  - 清理 `tests/test_runtime_router.py:124,131-132` 的 `~summary` 分类断言
  - 清理 `tests/test_runtime_gate.py:1947-1959` 与 `2380-2390` 的 `~summary` route 断言
  - 验收: 测试文件不再引用 `~summary` / `daily_summary`，且不误删 `render_outcome_summary`、`ClarificationState.summary`、`DecisionOption.summary` 等无关断言
- [x] T3-F: 全量 `pytest` 验证 + `grep` 残留检查
  - `pytest` 全量通过（595 passed）
  - `grep` 使用精确 pattern 组检查残留：`~summary`、`route_name.*summary`、`daily_summary`、`DailySummary`、`_render_daily_summary`、`next_summary`
  - 验收: 目标 surface 零残留（runtime/ + tests/ 范围） + 无 import 断裂，且不把 `render_outcome_summary` / 各类 `*.summary` 字段误判为失败

## 4. 蓝图回写

- [x] T4-A: 确认 `blueprint/README.md` 当前焦点
  - 焦点区块由 renderer (`runtime/kb.py`) 托管，不手工覆写
  - 验收: `tasks.md` 状态标记到位即可；焦点区块保持 renderer-managed 不变
- [x] T4-B: 更新 `blueprint/tasks.md` P1.5 先行切片状态标记
