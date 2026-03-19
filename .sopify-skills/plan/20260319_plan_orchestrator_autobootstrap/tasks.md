# 任务清单: stage checkpoint orchestrator + trigger-time runtime bootstrap

目录: `.sopify-skills/plan/20260319_plan_orchestrator_autobootstrap/`

## 1. 契约收口

- [x] 1.1 明确“安装一次 + 项目触发自动 bootstrap/update”是正式产品契约
- [x] 1.2 明确 planning mode = 第一批重点场景，不等于 checkpoint contract 的全部边界
- [x] 1.3 定义统一 `checkpoint_request` schema 与 reason code
- [x] 1.4 明确当前切片的 dependency model 为 `stdlib_only`
- [x] 1.5 为未来非 stdlib 依赖预留 `dependency_mode / runtime_dependencies / host_env_dir / python_min`
- [x] 1.6 明确“全技能通用决策系统是目标，planning-mode 自动闭环是第一期”的正式产品口径

验收标准:

- README、宿主提示层、payload manifest 口径一致
- “所有所需依赖”有正式工程定义，而不只是口头约定
- “任何需要 checkpoint 的技能阶段必须先走 runtime”成为正式契约，而不是建议
- 目标边界与一期范围不再混淆

## 2. `checkpoint_request` 产出契约

- [x] 2.1 定义 route-native producer：clarification / decision policy / execution gate
- [x] 2.2 定义 host-triggered develop callback producer：`develop_callback_payload -> checkpoint_request`
- [x] 2.3 定义 runtime skill producer：`skill_result.checkpoint_request`
- [x] 2.4 定义 request normalizer / validator
- [x] 2.5 定义 malformed request 的 fail-closed 策略
- [x] 2.6 定义遗漏监控 reason code，如 `checkpoint_request_missing_but_tradeoff_detected`

验收标准:

- skill 或 route 若产出标准 request，runtime 一定能统一物化
- skill 或 route 若 request 非法，不会被静默吞掉

## 3. 宿主与 runtime 入口纪律

- [x] 3.1 定义 planning intent 识别口径，覆盖“分析需求 / 出方案 / 给蓝图 / task 拆分 / 技术路线选择”
- [x] 3.2 更新 Codex/Claude 宿主提示层，禁止在命中 checkpoint 可能性高的技能阶段时直接人工分析
- [x] 3.3 保持 freeform 请求优先走默认 runtime 入口，让 router 自己判定 route
- [x] 3.4 明确只有 plan-only 模式才直达 `go_plan_runtime.py`
- [x] 3.5 明确宿主处于 `continue_host_develop` 时，一旦命中用户拍板分叉，必须走 develop callback entry
- [x] 3.6 为“人工分析绕过 runtime”增加契约测试
- [x] 3.7 定义 CLI 宿主 readiness checklist：preflight / handoff / bridge / resume / resume_context
- [x] 3.8 为“看得到 checkpoint 但不能 prompt/submit/resume”的假闭环增加契约测试

验收标准:

- 用户不用显式输入 `~go plan`，planning mode 也不会绕开 runtime
- checkpoint 的产生依赖 runtime contract，而不是宿主自由发挥
- develop 中途的用户确认不会再由宿主自由文本兜底，而是先回调 runtime
- CLI 宿主是否“能进入决策环节”可被机器判定，而不是靠人工解释

## 4. checkpoint materializer 骨架

- [x] 4.1 新增 `runtime/checkpoint_request.py`
- [x] 4.2 新增 `runtime/checkpoint_materializer.py`
- [x] 4.3 实现 `checkpoint_request -> DecisionState/ClarificationState/RuntimeHandoff`
- [x] 4.4 支持 route-native producer、develop callback producer 与 skill-native producer
- [x] 4.5 增加 schema 校验、重复请求检测与最大循环次数保护

验收标准:

- checkpoint 不再只绑定 planning route
- checkpoint 不再只依赖 runtime skill，develop callback 也能走同一 materializer
- materializer 可持续消费 request 并收口到统一 handoff

## 5. Planning Mode Orchestrator 骨架

- [x] 5.1 新增或升级 `runtime/plan_orchestrator.py`
- [x] 5.2 在其中实现 `run_plan_loop(...)`
- [x] 5.3 在其中实现 `preflight_workspace_runtime(...)`
- [x] 5.4 在其中实现 `handle_plan_handoff(...)`
- [x] 5.5 明确它只负责 planning mode 自动闭环，不替代通用 materializer

验收标准:

- plan-only CLI 不再是单次 helper
- orchestrator 可持续消费 planning mode handoff 直到达到稳定停点

## 6. `go_plan_runtime.py` 升级

- [x] 6.1 将 `scripts/go_plan_runtime.py` 改为调用 plan orchestrator
- [x] 6.2 将 vendored `.sopify-runtime/scripts/go_plan_runtime.py` 同步为同一语义
- [x] 6.3 保留裸文本自动改写为 `~go plan ...`
- [x] 6.4 新增 `--no-bridge-loop` 调试旁路
- [x] 6.5 引入 fail-closed 退出码

验收标准:

- `go_plan_runtime.py` 默认会自动处理 analyze/design checkpoint
- 未达到正式停点时，CLI 不能伪装成“计划已完成”

## 7. Clarification / Decision bridge 串接

- [x] 7.1 orchestrator 串接 `clarification_bridge_runtime.py prompt/submit`
- [x] 7.2 orchestrator 串接 `decision_bridge_runtime.py prompt/submit`
- [x] 7.3 TTY 场景默认使用 `renderer=auto`
- [x] 7.4 非 TTY 场景自动回退文本模式
- [x] 7.5 用户取消、超时、无效输入时给出稳定退出码与提示

验收标准:

- planning mode orchestrator 在 CLI 环境可自动消化 clarification / decision 阶段
- 非交互环境不会卡死

## 8. develop-first callback 接入 checkpoint request

- [x] 8.1 新增 `scripts/develop_checkpoint_runtime.py`
- [x] 8.2 将 vendored `.sopify-runtime/scripts/develop_checkpoint_runtime.py` 同步为同一语义
- [x] 8.3 定义 `develop_callback_payload` schema，覆盖 `decision / clarification`
- [x] 8.4 为 develop callback 增加必填 `resume_context`
- [x] 8.5 约定 develop callback 不允许宿主直接手写最终 `checkpoint_request` 状态文件
- [x] 8.6 确认后优先恢复到 `continue_host_develop`，范围变化时回退到 `review_or_execute_plan`
- [x] 8.7 补 develop callback contract 测试

验收标准:

- develop 中一旦出现分叉，宿主有唯一 callback 入口，不再直接自由追问
- 用户确认后链路能带着 `resume_context` 稳定回到 develop 或 plan review

## 9. Workspace bootstrap 与依赖准备

- [x] 9.1 保持 trigger-time workspace bootstrap/update 默认开启
- [x] 9.2 在 orchestrator 进入前强制做 workspace preflight
- [x] 9.3 若 bundle 缺失、过期或不兼容，自动 refresh 后再进入 plan loop
- [x] 9.4 在 payload manifest 中写入 dependency model 字段
- [ ] 9.5 若未来切到 `host_venv`，由 `install_sopify.py` 负责一次性安装 host-root env

验收标准:

- 用户一次安装后，进入任何项目触发 Sopify 即可自动准备最新兼容 runtime
- 当前切片下不需要每个项目单独安装依赖

## 10. 宿主提示层与 installer

- [x] 10.1 更新 Codex CN/EN 提示层，把 checkpoint contract 定义为跨技能阶段通用规则
- [x] 10.2 更新 Claude CN/EN 提示层，把命中 checkpoint 可能性时先走 runtime 设为硬约束
- [x] 10.3 更新 plan-only 入口描述，把 `go_plan_runtime.py` 定义为 planning-mode orchestrator
- [x] 10.4 更新 develop 阶段宿主规则：命中用户拍板时必须调用 develop callback entry
- [x] 10.5 更新 installer 输出文案，明确“安装一次 + 项目触发自动 bootstrap/update + stage checkpoint orchestrator”
- [x] 10.6 更新 README / README_EN 说明 dependency model、checkpoint_request、fail-closed 语义
- [x] 10.7 更新宿主文档，加入“CLI readiness for develop decision loop”判定标准
- [x] 10.8 重写 README / README_EN 的“核心特性 / Key Features”，作为实现完成后的最后文档收口步骤

验收标准:

- 安装产物与文档口径一致
- 宿主不会再把 `go_plan_runtime.py` 理解成薄包装脚本
- 宿主不会再把“需求分析/方案设计”理解成可直接人工处理的自由区
- 宿主能明确区分“可进入决策环节”和“只具备部分能力”的状态
- README 的主叙事与最终实现一致，而不是提前锁死中间态

## 11. 测试

- [x] 11.1 新增 raw planning request 路由测试：freeform 输入会进入 `workflow / light_iterate / plan_only`
- [x] 11.2 新增 materializer 测试：合法 `checkpoint_request` -> state + handoff
- [x] 11.3 新增 materializer 测试：malformed `checkpoint_request` -> fail-closed
- [x] 11.4 新增 develop callback payload 测试：decision / clarification -> `checkpoint_request`
- [x] 11.5 新增 plan orchestrator 端到端测试：clarification -> plan closed
- [x] 11.6 新增 plan orchestrator 端到端测试：decision -> plan closed
- [x] 11.7 新增 plan orchestrator 端到端测试：decision -> confirm_execute
- [x] 11.8 新增非 TTY 文本回退测试
- [x] 11.9 新增重复 handoff / 最大循环次数保护测试
- [x] 11.10 新增 trigger-time bootstrap/update 后再进入 orchestrator 的集成测试
- [x] 11.11 新增宿主提示层契约测试，锁住 preflight + orchestrator 文案
- [x] 11.12 新增 dependency model manifest 测试
- [x] 11.13 新增 `resume_context` roundtrip 测试：确认后能恢复到 `continue_host_develop`
- [x] 11.14 新增 develop callback fallback 测试：范围变化时回退 `review_or_execute_plan`
- [x] 11.15 新增遗漏监控测试：develop 存在 tradeoff 但无 request 时给出 reason code
- [x] 11.16 新增 CLI readiness 测试：manifest capability + callback entry + handoff + bridge + resume
- [x] 11.17 新增假闭环测试：develop callback 产出 decision checkpoint 但 bridge/resume 缺失时 fail-closed

验收标准:

- “安装一次 + 自动 bootstrap/update + checkpoint 闭环”具备自动化保护
- 宿主即使不看自然语言文案，也能依赖退出码与 handoff 契约
- 宿主 readiness 不会停留在“文档说可以”，而是有 develop callback 自动化验证

## 12. 后续保留项

- [ ] 12.1 若未来引入外部依赖，落地 host-global virtualenv/runner
- [ ] 12.2 compare 从 facade 完整迁移到主链路 checkpoint
- [ ] 12.3 replay 按同一 contract 接入
- [ ] 12.4 评估是否需要 develop orchestrator 全接管，而不是仅 callback
- [ ] 12.5 评估是否提供 `~/.codex/sopify/bin/sopify` 统一 wrapper 作为更强的宿主入口

说明:

- planning mode 自动闭环作为前置已落地
- 当前批次优先做 develop-first callback，把 develop 中途分叉接入统一 checkpoint 主链
- compare / replay 不在当前批次主线，但 schema 和 materializer 继续保持通用
- README 的“核心特性 / Key Features”重写放到最后收尾，不前置占用主线实现节奏

## 13. 下一阶段：宿主强制 runtime 入口守卫（develop-first）

- [x] 13.1 增加宿主入口 guard 契约：除明确 `~go plan` helper 场景外，所有原始请求一律先进入默认 runtime 入口
- [x] 13.2 增加 pending-checkpoint guard：当 `required_host_action` 为 `answer_questions / confirm_decision / confirm_execute` 时，禁止宿主绕过到自由分析或 `~go exec`
- [x] 13.3 增加 develop guard：`continue_host_develop` 阶段命中用户拍板分叉时，宿主只能通过 `develop_checkpoint_runtime.py submit --payload-json ...` 回调
- [x] 13.4 增加 fake-closed-loop guard：若仅能读取 checkpoint 但不能完成 prompt/submit/resume，必须 fail-closed，禁止伪装“已继续”
- [x] 13.5 增加 runtime-trigger 守卫测试：验证宿主不能直接手写 `current_decision.json / current_handoff.json` 作为替代路径
- [x] 13.6 增加入口守卫可观测性：在 handoff 或 stderr 输出统一 reason code，支持宿主机器诊断
- [x] 13.7 增加 bundle/installer 联动测试：确保“一次安装 + 项目触发自动 bootstrap/update + 入口守卫”链路一致
- [x] 13.8 更新 README / AGENTS / CLAUDE 口径：从“建议先走 runtime”升级为“必须先走 runtime”

验收标准:

- 宿主在 planning/develop 等技能引用阶段不再存在“人工分析绕过 runtime”的执行路径
- checkpoint 进入、提交、恢复链路可由机器判定为完整闭环，缺任一环节时 fail-closed
- 用户侧体验保持“安装一次后项目触发自动准备”，不新增额外手工安装步骤
