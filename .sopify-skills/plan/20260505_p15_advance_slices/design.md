# 技术设计: P1.5 先行切片

> **定位**：P1.5 可先行切片方案包。三个窄切片串行执行，均不改 machine contract。
> **前置**：P1 已完成；protocol.md §4/§5 已有 Convention 样例和合规清单。
> **目标**：兑现 Convention 入口、建立 Protocol 合规断言、完成 daily_summary 预清理。

---

## 切片 1: Convention 入口兑现

### 现状

| 文件 | 当前 | 目标 |
|------|------|------|
| README.md | 只有 runtime 安装路径（Quick Start → install.sh） | 增加 Convention Mode 入口段落 |
| README.zh-CN.md | 同上 | 中文同步 |
| protocol.md §4 | 4 个生命周期样例（样例 A 是 Convention 正常流） | 不改 |
| protocol.md §5 | 6 条合规检查清单 | 不改 |

### 设计决策

**D1: Convention 入口放在 Quick Start 内部，不单独建章节**

在现有 Quick Start 章节的 Installation 之前或之后，增加 "Convention Mode (No Runtime)" 子段落。引用 protocol.md §4 样例 A 的 3 步路径。不新建顶层章节——Convention 是 Quick Start 的一种模式，不是独立产品。

**D2: 不新增模板文件、不新增 CLI 面**

蓝图明确不做 `sopify init --minimal`。Convention 入口通过 README 文字 + protocol.md 引用兑现。如需示例目录结构，引用 protocol.md §4 而非新建 examples/ 目录。

**D3: 3 步路径的表述对齐 protocol.md §4 样例 A**

1. 读 `blueprint/` 理解项目上下文
2. 在 `plan/` 下创建 plan.md（含 title/scope/approach + 内联 tasks）
3. 归档到 `history/YYYY-MM/` 并生成 receipt.md

合规自检引用 protocol.md §5。

---

## 切片 2: Protocol Compliance Suite Phase 1

### 现状

- `tests/protocol/` 不存在
- `evals/` 只有 3 个 JSON 评估文件（skill_eval_slo/baseline/report），不是协议合规断言
- protocol.md §5 定义了 6 条最小合规项

### 设计决策

**D4: 断言套件放在 `tests/protocol/`，不放 `evals/`**

理由：evals/ 当前承载的是 skill 评估数据（JSON），和协议合规是不同层面。tests/ 下新建 protocol/ 子目录，用 pytest 驱动，与现有 runtime 测试隔离。

**D5: 用 pytest + tmp_path fixture 模拟 `.sopify-skills/` 结构**

不依赖真实项目目录、不依赖 runtime 模块。每个 test case 在 tmp_path 下构建最小 `.sopify-skills/` 目录结构，验证文件存在性 + 必需字段。

这保证了 Compliance Suite 的独立性——任何宿主只要能构建正确目录结构就能通过，不需要跑 Sopify runtime。

**D6: 6 条合规项的断言策略**

| 合规项 | 断言方式 | 级别 |
|--------|---------|------|
| 1. 读取 project.md 并识别项目名 | 文件存在 + 正则匹配 `# ` 标题行 | 必选 |
| 2. 读取 blueprint/ 三件套 | 三文件存在性断言 | 必选 |
| 3. 在 plan/ 下创建方案包 | tmp_path 创建 + 目录结构验证 | 必选 |
| 4. plan.md 必需字段 | 正则/文本搜索 title + scope + approach + tasks 区块 | 必选 |
| 5. 归档 + receipt.md | history/YYYY-MM/ 结构 + receipt.md 存在 | 必选 |
| 6. blueprint 回写 | Phase 1 不断言（Convention 下界中是推荐不是必选） | 推荐 |

**D7: 不做字段 schema 深度解析**

Phase 1 只做文件存在性 + 区块存在性（正则级）。不做 YAML/JSON schema 校验、不做内容语义验证。深度验证是 Phase 2（长期方向）的范围。

---

## 切片 3: 低风险辅助层预清理（daily_summary）

### 依赖图分析（基于真实代码）

```
runtime/daily_summary.py (1,133 行)
  ├── 被 runtime/engine.py:18 import (build_daily_summary)
  │   └── engine.py:1009 调用
  ├── 被 runtime/output.py:212,689 渲染 (_render_daily_summary_output)
  └── 被 tests/ 消费:
      ├── tests/runtime_test_support.py:47 import (render_daily_summary_markdown)
      ├── tests/test_runtime_summary.py (175 行, 2 个 test case)
      └── tests/test_runtime_engine.py:2338 mock (daily_summary.subprocess.run)

runtime/_models/summary.py (473 行, 16 classes)
  ├── 被 runtime/models.py:21 re-export
  ├── 被 runtime/daily_summary.py 消费
  └── 可能被其他模块通过 runtime.models 间接消费 → 需清理前验证
```

### 设计决策

**D8: daily_summary.py 整文件删除**

1,133 行全部删除。不保留骨架——没有用户在用，不需要 stub。

**D9: _models/summary.py 需逐 class 验证消费方后再决定**

16 个 class 中，`DailySummaryArtifact` + `SummaryScope` + `SummarySourceWindow` + `SummarySourceRefs` 等 class 大概率是 daily_summary 专属。但 `runtime/models.py` 的 re-export 可能导致其他模块间接引用。

策略：**先 grep 全量消费方，只删仅被 daily_summary 消费的 class**。如果 _models/summary.py 全部 class 都只被 daily_summary 消费，则整文件删除；否则保留共用 class。

**D10: output.py 中 `_render_daily_summary_output` 函数删除**

不只删除 `_render_daily_summary_output`。`output.py` 中与 `summary` route 绑定的 phase label、`next_summary`、`_collect_changes`、`_next_hint`、`_status_symbol`、`_status_message` 等分支都需要同步清理，避免 route 删除后留下只读渲染残面。

**D11: 测试清理范围**

| 文件 | 处理 |
|------|------|
| `tests/test_runtime_summary.py` (175 行) | 整文件删除 |
| `tests/runtime_test_support.py:47` | 删除 `render_daily_summary_markdown` import |
| `tests/test_runtime_engine.py:2338` | 删除 mock patch 行及关联上下文 |
| `tests/test_runtime_router.py:124,131-132` | 删除 `~summary` 分类断言 |
| `tests/test_runtime_gate.py:1947-1959,2380-2390` | 删除 `~summary` route 集成断言 |

说明：`installer.outcome_contract.render_outcome_summary`、`ClarificationState.summary`、`DecisionOption.summary` 等与 `daily_summary` route 无关的引用不在本次删除范围内。

**D12: engine.py 调用点处理**

`engine.py` 不只是一处调用点。需要同步删除：

- `summary` route 的 `last_route` 豁免分支
- `build_daily_summary` 调用分支
- `summary` route 的 handoff 保留分支
- `summary` route 的 phase / skill 映射分支

`router.py` 也需同步删除 `~summary` 命令匹配、`summary` route 支持、以及 capture/decision 相关分支。`runtime/__init__.py` 和 `runtime/models.py` 的 public export / re-export 需一起收口，保证删除后不存在公开 facade 残留。

---

## 文件变更预估

| 切片 | 文件 | 变更类型 | 范围 |
|------|------|---------|------|
| 1 | README.md | 编辑 | Convention Mode 段落 |
| 1 | README.zh-CN.md | 编辑 | 中文同步 |
| 2 | tests/protocol/test_convention_compliance.py | 新建 | 6 条合规断言 |
| 3 | runtime/daily_summary.py | 删除 | 1,133 行 |
| 3 | runtime/router.py | 编辑 | 删除 `~summary` route 入口与相关分支 |
| 3 | runtime/engine.py | 编辑 | 删除 summary route 分支 |
| 3 | runtime/output.py | 编辑 | 删除 summary route 全部专属分支 |
| 3 | runtime/__init__.py | 编辑 | 删除 `DailySummaryArtifact` public export |
| 3 | runtime/_models/summary.py | 编辑/删除 | 视消费方验证结果 |
| 3 | runtime/models.py | 编辑 | 清理 re-export |
| 3 | tests/test_runtime_summary.py | 删除 | 175 行 |
| 3 | tests/runtime_test_support.py | 编辑 | 删除 import |
| 3 | tests/test_runtime_engine.py | 编辑 | 删除 mock 行 |
| 3 | tests/test_runtime_router.py | 编辑 | 删除 `~summary` 断言 |
| 3 | tests/test_runtime_gate.py | 编辑 | 删除 `~summary` route 集成断言 |
| 4 | .sopify-skills/blueprint/README.md | 确认 | 焦点区块由 renderer 托管，不手工覆写 |
| 4 | .sopify-skills/blueprint/tasks.md | 编辑 | 状态更新 |

不新增 runtime 模块、不新增 CLI 面、不改 protocol.md。

---

## 验收标准

### 切片 1
1. README.md 含 Convention Mode 段落，描述 ≤3 步最小路径
2. 段落引用 protocol.md §4 样例 A 和 §5 合规清单
3. README.zh-CN.md 有对应中文段落
4. `test_check_readme_links.py` 通过（已有测试）

### 切片 2
5. `pytest tests/protocol/` 可独立运行并全部通过
6. 断言覆盖 protocol.md §5 前 5 条（第 6 条不纳入 Phase 1）
7. 不 import 任何 `runtime.*` 模块

### 切片 3
8. `summary` surface 相关精确 pattern 组无残留：`~summary`、`route_name.*summary`、`daily_summary`、`DailySummary`、`_render_daily_summary`、`next_summary`
9. 全量 `pytest` 通过
10. runtime 行数减少 ≥1,100 行

### 蓝图回写
11. blueprint/README.md 焦点已更新
12. blueprint/tasks.md 先行切片状态已标记
