# 蓝图任务

状态: 只保留未完成长期项与明确延后项

## 未完成长期项

- [ ] 补宿主级 first-hop ingress proof / doctor，让 host-first runtime gate 有独立可见性与诊断闭环。
- [ ] 把 `~compare` 的 shortlist facade 收敛进默认主链路恢复，复用统一的 decision checkpoint machine contract。
- [ ] 补 `workflow-learning` 的独立 runtime helper 与更稳定的按任务/按日期 replay retrieval。

## 明确延后项

- [-] runtime 全接管 develop orchestrator；当前阶段保持 host-owned develop + standardized checkpoint callback。
- [-] 非 CLI 宿主的图形化 clarification / decision 表单；当前正式范围仍是 CLI bridge。
- [-] 把 history 正文纳入默认长期上下文；当前只保留索引发现，不作为默认消费源。

### 12.5 决策确认后的回流

- [x] 12.5.1 明确 decision confirmed 后不能直接进入 develop，必须先重新运行 execution gate
- [x] 12.5.2 在 plan 物化后保留足够上下文，让 gate evaluator 能读取决策结果
- [x] 12.5.3 明确 `decision_pending -> confirmed -> ready_for_execution|clarification_pending|decision_pending` 的回流路径
- [x] 12.5.4 为“决策已确认但仍缺信息”与“决策已确认但仍有阻塞风险”补状态说明
- [x] 12.5.5 明确 consumed decision 的清理时机，不影响后续执行确认

验收标准：

- 决策确认只解决“拍板”问题，不会跳过后续门禁
- 决策结果能稳定参与 plan 与 gate 判断

### 12.6 `~go exec` 高级恢复入口化

- [x] 12.6.1 明确 `~go exec` 只在已有活动 plan 或恢复态存在时可用
- [x] 12.6.2 明确 `~go exec` 不得绕过 `clarification_pending`
- [x] 12.6.3 明确 `~go exec` 不得绕过 `decision_pending`
- [x] 12.6.4 明确 `~go exec` 不得绕过 `execution_confirm_pending`
- [x] 12.6.5 为宿主文档补齐“高级恢复入口”而非“普通主链路入口”的对外口径

验收标准：

- `~go exec` 的行为边界稳定，不再被误当成普通用户必经步骤
- 恢复入口与标准主链路不互相污染

### 12.7 宿主消费与文档口径

- [x] 12.7.1 更新 README，明确普通主链路默认推进到执行前确认
- [x] 12.7.2 更新 Codex/Claude 宿主契约，明确 `confirm_execute` 与自然语言确认入口
- [x] 12.7.3 更新 design/develop skill 文档，避免继续把 `~go exec` 写成默认下一步
- [x] 12.7.4 更新输出文案中的 `Next:`，让其与第二阶段主链路一致
- [x] 12.7.5 检查中英文口径同步，避免 CN/EN 行为描述分叉

验收标准：

- 蓝图、README、AGENTS/CLAUDE、skill 文档口径一致
- 用户看到的“下一步”不再与机器门禁冲突

### 12.8 自动化测试

- [x] 12.8.1 为 `clarification_pending` 的创建、恢复、退出补测试
- [x] 12.8.2 为 execution gate 的 `blocked / decision_required / ready` 三类结果补测试
- [x] 12.8.3 为 `confirm_execute` handoff 与自然语言 `继续 / next / 开始` 补测试
- [x] 12.8.4 为 decision confirmed 后重新过 gate 的链路补测试
- [x] 12.8.5 为 `~go exec` 不能绕过澄清/决策/执行确认补测试
- [x] 12.8.6 为 synced bundle 在其他仓库内的第二阶段主链路补测试

验收标准：

- 第二阶段核心状态机具备回归测试保护
- repo-local runtime 与 vendored bundle 行为一致

### 12.9 外围能力评估

- [x] 12.9.1 评估是否让 model-compare 的人工选择协议迁移到 decision checkpoint（当前以 `compare_decision_contract` facade 方式落地，不改主链路 state）
- [ ] 12.9.2 评估是否引入 blueprint 索引摘要的更细粒度自动刷新
- [ ] 12.9.3 评估是否为 history 建立更紧凑的 feature_key 聚合视图

说明：

- 第二阶段建立在文档治理、decision checkpoint 与 finalize 收口都已稳定的基础上
- 先落清晰门禁与主链路，再考虑扩张 compare/replay 等外围交互能力

## 13. 决策通用化与宿主桥接

- [x] 13.1 新增 `runtime/decision_templates.py`
- [x] 13.2 第一版模板先实现 `strategy_pick`，并支持 `custom -> textarea` 的补充说明路径
- [x] 13.3 将当前 planning-request 语义触发收口到 `runtime/decision_policy.py`
- [x] 13.4 保留当前触发基线，并为 design-stage candidate tradeoff 复用同一套 checkpoint contract 预留扩展
- [x] 13.5 明确 CLI 型宿主当前默认使用内置 interactive renderer，但 richer terminal UI 仍只算宿主实现细节，缺少依赖时必须退化到纯文本桥接
- [x] 13.6 宿主统一把采集结果归一化为 `DecisionSubmission`，写回 `current_decision.json` 后仍通过默认 runtime 入口恢复
- [x] 13.7 为 CLI bridge 补一组契约测试
- [x] 13.8 同步 README / AGENTS，明确“接入方式不变，桥接能力增强”

验收标准：

- runtime 侧不再直接硬编码单选 checkpoint 构造逻辑，而是通过模板与 policy 产出通用 contract
- CLI 型宿主能稳定消费同一份 `decision_checkpoint`，并在缺少 richer renderer 时回退到纯文本桥接
- 用户仍按原有一键接入与默认 runtime 入口使用 Sopify，不需要新的安装步骤或新的主入口脚本

## 14. 宿主入口强约束（develop-first）

- [x] 14.1 把“宿主应先走 runtime”升级为“宿主只能先走 runtime”的入口守卫契约
- [x] 14.2 固化 pending checkpoint 三态（`answer_questions / confirm_decision / confirm_execute`）的不可绕过规则
- [x] 14.3 固化 `continue_host_develop` 阶段拍板分叉的唯一回调路径：`develop_checkpoint_runtime.py submit --payload-json ...`
- [x] 14.4 固化 fake-closed-loop 的 fail-closed 规则：不能 prompt/submit/resume 时禁止继续主链路
- [x] 14.5 增加宿主入口守卫自动化测试：禁止手写 `current_decision.json / current_handoff.json` 作为替代
- [x] 14.6 增加入口守卫可观测性 reason code，支持宿主 readiness 机器判定
- [x] 14.7 更新 installer 与 bundle smoke，保证“一次安装 + 项目触发 + 自动 bootstrap/update + 入口守卫”链路一致
- [x] 14.8 同步 README / AGENTS / CLAUDE 对外口径，明确这是硬约束而非建议

验收标准：

- planning 与 develop 等技能引用阶段不存在“人工分析绕过 runtime”的执行通道
- 宿主是否“可进入决策环节”能由机器检查判定，不再依赖人工解释
- 用户体验保持零新增步骤；触发 Sopify 后自动完成 runtime 准备并进入统一 checkpoint 主链

## 15. 当前时间显示与今日摘要

- [x] 15.1 在技能进入执行时输出当前本地时间，作为用户侧最小可见时间反馈
- [x] 15.2 保持内部结构化时间字段可复用给 replay 与摘要生成，但不把工程字段直接暴露给用户
- [x] 15.3 新增 `~summary`，默认总结“今天、当前工作区”的思考链路与代码变更细节
- [x] 15.4 固化 `~summary` 的详细摘要模板，保证结果可用于复盘、学习与知识沉淀
- [x] 15.5 固化 `~summary` 的 source pack 数据契约，明确 `plan/state/git` 为主、`replay` 为可选增强
- [x] 15.6 明确 `~summary` 首版采用“确定性收集 -> 模板渲染”两段式生成，不依赖 `daily index`
- [x] 15.7 把“`~summary` 一天通常只运行 1-2 次”写入设计约束，作为本期不先做 `daily index` 的依据
- [-] 15.8 `daily index` 降级为后续可选能力，仅在需要提速或更稳定按天检索时再评估引入
- [-] 15.9 `~replay` 与更多按日期 retrieval 入口保留后续能力，不进入当前主线
- [x] 15.10 为 `~summary` 补 4 条硬化测试：同日 `revision` 递增、`git` 缺失 fallback、`current_run / last_route` 不污染、终端渲染与落盘一致
- [-] 15.11 摘要质量优化与验证结果摄取降为后续长期优化，不阻塞本期主线收口
- [-] 15.12 基于 replay activation 的时间线增强保留后续能力，不进入首版交付面

验收标准：

- 用户每次进入技能阶段都能看到“当前时间”
- 用户只需要一个命令就能拿到“今天、当前工作区”的详细复盘摘要
- 摘要结果不仅说明改了什么，还能说明为什么这么改、遇到了什么问题、有哪些可复用经验
- 首版在重复运行、缺少 `git`、存在 active flow 的情况下仍能稳定生成并保持状态不被污染

## 16. 宿主偏好预载入（`preferences-preload-v1`）

- [x] 16.1 固化宿主 preflight 读取 `preferences.md` 的最小契约
- [x] 16.2 固化 `workspace_root + plan.directory + user/preferences.md` 的路径解析规则，禁止宿主硬编码默认路径
- [x] 16.3 固化 `fail-open with visibility`：`loaded / missing / invalid / read_error`
- [x] 16.4 固化注入格式与优先级：当前任务 > preferences > 默认规则
- [x] 16.5 在 README / README_EN 中补齐宿主接入口径，明确这是 preflight 能力，不是 runtime 新阶段
- [-] 16.6 runtime 独立 `preferences_artifact` 保留后续评估，不进入首版范围
- [-] 16.7 偏好分类、自动归纳、自动提炼保留后续评估，不进入首版范围

验收标准：

- 宿主每次 Sopify 调用前都能按当前工作区正确定位 `preferences.md`
- 自定义 `plan.directory` 时，宿主仍能稳定命中正确路径
- `preferences.md` 缺失或读取失败不阻断主链路，但宿主可观测
- 长期偏好能稳定进入 LLM，而不是依赖人工记忆
- 首版不修改 `RecoveredContext` 语义，也不把偏好系统升级为新的 checkpoint
- 中文与英文宿主文档口径保持一致，不再让偏好预载入只存在单语文档中
