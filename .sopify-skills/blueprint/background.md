# 蓝图背景与目标

本文定位: Sopify 为什么存在、核心价值主张、当前现实状态、以及本蓝图的边界。

## Sopify 是什么

Sopify 的 durable core 是跨宿主 AI 工作流的 **证据与授权层**。它不负责生成代码或编排 agent，而是把外部生产、验证、知识工具的结果收敛成可恢复、可审计、可授权的机器事实。这里的"授权"指判定行动是否可执行、方案是否可归档、交接是否可信——不是安全/权限授权。

Sopify 官方在 core 之上提供一个轻量、可插拔、收敛式的 blueprint-driven workflow 作为默认产品体验。

### 产品栈

| 层 | 职责 | 生存性 |
|----|------|--------|
| **Core**（证据与授权层） | 协议规范 + Validator 授权 + 收据/接力/归档 truth | Durable：不随宿主生态变化而 sunset |
| **Default Workflow** | blueprint 驱动的分析 → 计划讨论 → 标准方案包 → 开发验证 → 归档回写 | 用户买到的主体验，建构在 core 之上，不硬绑 runtime 状态机 |
| **Plugins / Skills** | cross-review、graphify、宿主自带分析/开发/验证增强 | Sopify 定义接入点（Producer/Verifier/Knowledge Provider），不做 skill 分发 |

核心价值不在于"能调 skill"或"能编排 workflow"，而在于：

- **证据规范**：定义任务事实、方案事实、交接事实、归档事实的标准格式
- **授权判定**：Validator 是唯一授权者——判断当前上下文下行动是否可执行
- **收据生成**：fail-closed 授权回执让每次决策可追溯、可审计
- **跨宿主接力**：`.sopify-skills/` 纯文件协议让任务中断后在不同宿主/模型间精确恢复
- **知识沉淀**：只有跨任务可复用、能改变后续授权或验证基线的稳定结论，才进入长期知识层（blueprint / history）

**外插原则**：谁负责"把事做好"（生产、验证、知识处理），谁外插；谁负责"把结果变成可验证事实"（证据规范、授权判定、收据生成），谁进 Sopify core。

**产品形态锚点**：Protocol 是新宿主的唯一硬依赖（Convention 模式下无需 runtime 即可合规工作）；Validator 是宿主吸收执行编排后 Sopify 最后保留的面（durable core 的生存底线）；Runtime 是确定性加固线，不是接入前提（新接入方不应被要求先跑完整 runtime）；一切外部验证与生产能力通过 integration contract 外插，不进 core（边界判定原则）。

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
