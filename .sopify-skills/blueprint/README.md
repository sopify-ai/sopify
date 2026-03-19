# 项目蓝图索引

状态: 文档已收口，进入宿主入口守卫排期
创建日期: 2026-03-17
维护方式: 首次识别到真实项目仓库并触发 Sopify 时，至少创建本文件；索引区块由 Sopify 托管刷新，说明区块允许人工补充

## 当前目标

<!-- sopify:auto:goal:start -->
- 建立零配置开箱即用的 Sopify 标准开发流与文档治理闭环
- 让 `blueprint/README.md` 成为项目级长期入口索引，而不是依赖当前 plan 或历史归档
- 在不要求用户额外配置的前提下，稳定支持 blueprint / plan / history 的生命周期与执行门禁
<!-- sopify:auto:goal:end -->

## 项目概览

<!-- sopify:auto:overview:start -->
- blueprint: 项目级长期蓝图，默认进入版本管理
- plan: 当前活动方案，默认本地使用、默认忽略
- history: 收口后的方案归档，默认本地使用、默认忽略
- replay: 可选回放能力，不属于基础文档治理契约
<!-- sopify:auto:overview:end -->

## 架构地图

<!-- sopify:auto:architecture:start -->
```text
.sopify-skills/
├── blueprint/
│   ├── README.md
│   ├── background.md
│   ├── design.md
│   └── tasks.md
├── plan/
├── history/
├── state/
└── replay/
```
<!-- sopify:auto:architecture:end -->

## 关键契约

<!-- sopify:auto:contracts:start -->
- 不要求用户新增配置；默认行为即完成 bootstrap、索引刷新与方案收口
- 首次 Sopify 触发只要求创建轻量 `blueprint/README.md`
- 首次进入 plan 生命周期时，再补齐 `blueprint/background.md / design.md / tasks.md`
- 普通开发请求与 `~go` 应默认推进到“执行前确认”这一关；`~go plan` 明确只生成 plan
- `plan` 只保留当前活动方案；第一版通过显式 `~go finalize` 在“本轮任务收口、准备交付验证”时归档到 `history/`
- `full` 任务必须更新深层 blueprint；`standard` 仅在边界或契约变化时更新；`light` 不强制
- 缺事实信息时进入 `clarification_pending`；长期契约分叉或未消解关键风险时进入 `decision_pending`
- design 阶段若出现长期契约分叉，先进入 decision checkpoint；用户确认后才生成唯一正式 plan
- 当 `required_host_action == confirm_decision` 时，宿主优先消费 `current_handoff.json.artifacts.decision_checkpoint` 与 `decision_submission_state`；`current_decision.json` 作为状态兜底与 legacy projection 来源
- 代码执行前必须同时通过机器执行门禁与用户执行确认；`~go exec` 仅作为恢复/调试入口，不能绕过门禁
- 命中技能引用阶段且存在 checkpoint 可能性时，宿主必须先走默认 runtime 入口，不得直接人工分析绕过 router
- 若 `current_handoff.required_host_action` 为 `answer_questions / confirm_decision / confirm_execute`，宿主不得把 `~go exec` 当作绕过入口
- 若 `required_host_action == continue_host_develop` 且开发中再次出现用户拍板分叉，宿主必须调用 `develop_checkpoint_runtime.py submit --payload-json ...`，不得自由追问或手写状态文件
- 若出现结构化 tradeoff 信号但缺失可用 `checkpoint_request`，必须输出 reason code `checkpoint_request_missing_but_tradeoff_detected` 并 fail-closed
- 旧遗留 plan 不自动迁移；finalize 只支持 metadata-managed plan
<!-- sopify:auto:contracts:end -->

## 当前焦点

<!-- sopify:auto:focus:start -->
- blueprint bootstrap、execution gate 与 decision runtime contract 已接入 runtime 主链路
- `DecisionCheckpoint / DecisionSubmission / structured submission resume` 已作为 runtime 机器契约落地
- `decision_templates / decision_policy / decision bridge helper` 已落地；`decision_policy` 已支持 structured tradeoff candidates，`~compare` handoff 已可输出 `compare_decision_contract` facade，clarification 已可输出 `clarification_form` 并结构化恢复，replay 已记录推荐项/最终选择并默认省略自由输入原文
- `planning-mode orchestrator + develop-first callback + missing-request reason code` 已收口并有自动化测试保护
- 下一阶段优先级收敛为“宿主强制 runtime 入口守卫（develop-first）”：把“文档约束”提升为“入口级机器约束”
- compare / replay 继续作为后续切片，不抢占当前强约束主线
- 保持单活动 plan 模型与既有接入链路，不引入新的主入口、drafts 目录或额外安装步骤
<!-- sopify:auto:focus:end -->

## 深入阅读入口

<!-- sopify:auto:read-next:start -->
- [背景与目标](./background.md)
- [治理设计](./design.md)
- [实施任务](./tasks.md)
- [项目技术约定](../project.md)
- [项目概览](../wiki/overview.md)
- 当前活动方案: 见 `../plan/`
<!-- sopify:auto:read-next:end -->

## 专项蓝图

- [Skill 标准对齐蓝图](./skill-standards-refactor.md)

## 维护说明

- 本文件是项目级入口索引，不承载单次任务的完整实现细节。
- 当前仓库已完成蓝图文档收口；blueprint bootstrap、metadata-managed plan 的 finalize 收口、execution gate、`decision_templates / decision_policy / decision bridge helper` 与 decision runtime contract 已落地；CLI interactive bridge、structured tradeoff policy、compare facade、scope clarify bridge 与 replay 摘要增强也已进入代码主线。下一阶段重点是把“宿主应当先走 runtime”升级为“宿主只能先走 runtime”的入口级约束，优先收口 develop-first 决策回调链路，再扩展 compare/replay 主链接入。
- 自动区块优先保持“短、稳、可扫描”；深入说明进入 `background.md / design.md / tasks.md`。
- 若人工补充内容与代码、宿主契约、目录契约冲突，以实现与正式蓝图为准，并在后续收口时修正。
