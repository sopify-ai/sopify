# 蓝图背景与目标

本文定位: Sopify 为什么存在、核心价值主张、当前现实状态、以及本蓝图的边界。

## Sopify 是什么

Sopify 是 AI 编程工作流的 **control plane**。它不做模型推理、不做代码执行、不做技能市场——它做的是：让 AI 编程任务在跨轮、跨会话、跨宿主的场景下可恢复、可审计、可持续推进。

核心价值不在于"能调 skill"，而在于：

- **自适应推进**：按任务复杂度选择快速修复 / 轻量迭代 / 完整方案
- **状态交接**：handoff 机器契约让任务中断后能精确恢复
- **质量验证**：独立验证闭环（cross-review 是参考实现）
- **资产沉淀**：blueprint / history 构建跨任务的项目记忆
- **宿主无关**：`.sopify-skills/` 是纯文件协议，不绑定特定 IDE 或 runtime

## 核心架构模式

Sopify 的一切交互遵循一条管线：

```
用户自然语言
  → Host LLM 映射为 ActionProposal（结构化工单）
  → Validator 校验 schema + 事实 + side effect
  → Deterministic action 按结构化字段执行
  → Handoff / Receipt 暴露机器事实
```

Host LLM 只是 proposal source，不是 authorizer。Validator 是唯一授权者。执行层不理解人话，只按结构化字段和文件事实做事。

## 当前现实

截至 2026-05-01：

- **Runtime 规模**：~29K 行 Python / 66 个模块，`engine.py` 单文件 3086 行
- **已完成**：ActionProposal P0 thin slice（ADR-017）、archive lifecycle cutover、legacy feature cleanup
- **核心矛盾**：方向是"轻量可插拔"，但 checkpoint 5 种、host action 13 种、route 18 种、state 文件 8 个——协议层膨胀与轻量化目标直接冲突

知识资产分五层：

| 层 | 路径 | 职责 |
|----|------|------|
| L0 index | `blueprint/README.md` | 入口索引 |
| L1 stable | `project.md` + `blueprint/{background,design,tasks}` | 长期知识 |
| L2 active | `plan/YYYYMMDD_feature/` | 活动方案 |
| L3 archive | `history/YYYY-MM/` | 收口归档 |
| runtime | `state/*.json` + `replay/` | 运行态 |

## 本蓝图的定位

本蓝图（`blueprint/`）是 Sopify 的**长期设计基线**，不是方案包也不是执行计划。

- `background.md`（本文）：为什么存在、核心价值、当前现实
- `design.md`：架构分层、核心契约、削减目标、硬约束
- `tasks.md`：未完成长期项与明确延后项

方案包（`plan/`）消费 blueprint 作为输入，执行完毕后将稳定结论回写 blueprint。Blueprint 不膨胀、不重复方案包细节、不承载执行任务清单。

## 非目标

- 不新增知识层
- 不在 blueprint 里规定实现细节（hash 格式、字段命名等归 ADR 或 implementation plan）
- 不把 history 正文纳入默认长期上下文
