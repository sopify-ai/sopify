# 任务清单: 文档治理、索引与决策确认

状态: 第二阶段主链路已收口，进入 decision 通用化排期

状态说明：

- `[ ]` 未开始
- `[x]` 已完成
- `[-]` 明确延后

说明：

- 本清单中的 `[x]` 表示文档、模板、runtime machine contract 或仓库默认策略已收口，不等于所有宿主桥接都已经落地
- decision 相关能力需要明确区分：runtime contract 已完成，不等于 CLI 型宿主的交互式 bridge 已完成

## 0. 蓝图文档

- [x] 0.1 建立 `.sopify-skills/blueprint/` 正式目录
- [x] 0.2 写入 `README.md / background.md / design.md / tasks.md`
- [x] 0.3 明确零配置开箱即用、首次触发索引 bootstrap、plan 收口归档、decision checkpoint 前后关系
- [x] 0.4 吸收旧 `20260313_sopify_runtime_blueprint` 的有效内容，并迁移到新的 `blueprint/` 口径

验收标准：

- 仓库内已有一套正式、可实施的文档治理蓝图
- 后续实现不需要再从聊天记录里反推规则
- 旧 runtime 蓝图不再需要继续双维护

## 1. Blueprint Index Bootstrap

- [x] 1.1 在 runtime 固定入口增加 `ensure_blueprint_index(...)`
- [x] 1.2 固化“真实项目仓库”判定规则
- [x] 1.3 首次 Sopify 触发时，仅在缺失时创建 `blueprint/README.md`
- [x] 1.4 保持咨询场景也可创建索引文件，但不创建完整深层 blueprint
- [x] 1.5 为首次触发创建索引的行为补测试

验收标准：

- 不要求用户额外配置
- 首次触发 Sopify 即可为真实项目建立全局入口索引

## 2. Blueprint 强约束模板

- [x] 2.1 固化 `blueprint/README.md` 的 6 个固定区块
- [x] 2.2 设计托管区块标记 `<!-- sopify:auto:* -->`
- [x] 2.3 限定自动刷新只覆盖托管区块
- [x] 2.4 保留非托管区块用于人工补充
- [x] 2.5 为 README 模板与托管区块补测试

验收标准：

- 人和 LLM 都能稳定把 `blueprint/README.md` 当项目入口索引
- 自动刷新不会覆盖人工维护说明

## 3. 首次进入 Plan 生命周期时补齐完整 Blueprint

- [x] 3.1 在 `plan_only / workflow / light_iterate` 路由下补齐 `background.md / design.md / tasks.md`
- [x] 3.2 保持 blueprint 深层文件只在首次 plan 生命周期创建
- [x] 3.3 确保首次 plan 生命周期与首次索引 bootstrap 不冲突
- [x] 3.4 为首次 plan 生命周期补齐完整 blueprint 的行为补测试

验收标准：

- 咨询场景不写重文档
- 一旦真正进入方案流，项目就拥有完整 blueprint 骨架

## 4. Plan 元数据契约

- [x] 4.1 在 `plan.md` 或 `tasks.md` 头部增加机器字段
- [x] 4.2 固化 `lifecycle_state` 状态集合
- [x] 4.3 固化 `blueprint_obligation` 状态集合
- [x] 4.4 建立 `light / standard / full` 到 obligation 的默认映射
- [x] 4.5 为元数据读写与兼容补测试

验收标准：

- blueprint 是否必须更新不再只靠语义判断
- 收口逻辑可直接读取 plan 元数据

## 5. 收口事务

- [x] 5.1 引入统一 `finalize_plan(...)` 收口事务
- [x] 5.2 在收口事务中刷新 `blueprint/README.md` 的索引区块
- [x] 5.3 在收口事务中检查 `blueprint_obligation`
- [x] 5.4 在收口事务中完成 `plan -> history` 归档
- [x] 5.5 在收口事务中更新 `history/index.md`
- [x] 5.6 在收口事务中清理活动状态

验收标准：

- 不依赖 commit hook
- 文档更新、归档、状态收口通过固定事务完成

## 6. Blueprint 更新规则

- [x] 6.1 固化 `light` 只刷新索引、不强制改深层 blueprint
- [x] 6.2 固化 `standard` 在边界或契约变化时更新深层 blueprint
- [x] 6.3 固化 `full` 必须更新深层 blueprint
- [x] 6.4 为 `standard` 的命中条件建立可测试判定规则
- [x] 6.5 为 `full` 缺失深层更新的场景补失败提示

验收标准：

- `light / standard / full` 的文档责任边界清晰稳定
- 不会让简单任务被重文档拖慢，也不会让架构级变更无痕通过

## 7. History 策略

- [x] 7.1 明确 `history/` 只在收口时写入
- [x] 7.2 明确 `history/` 不做实时镜像
- [x] 7.3 明确 `history/` 不做多个 plan 自动归并
- [x] 7.4 在 `history/index.md` 中保留摘要索引格式
- [x] 7.5 为归档与索引更新补测试

验收标准：

- 当前 plan 与归档 history 的职责明确
- 历史信息可追溯但不会干扰当前工作区

## 8. 默认 Git 策略

- [x] 8.1 将 `blueprint/` 设为默认入库目录
- [x] 8.2 将 `plan/` 设为默认忽略目录
- [x] 8.3 将 `history/` 设为默认忽略目录
- [x] 8.4 将 `state/` 与 `replay/` 继续设为默认忽略目录
- [x] 8.5 在文档中保留“用户可自行调整 `.gitignore`”的说明

验收标准：

- 默认策略开箱即用
- 用户如有特殊需要，仍可自行调整入库范围

## 9. 决策确认能力蓝图

- [x] 9.1 固化 design 自动触发的前提条件与不触发条件
- [x] 9.2 固化 `current_decision.json` 的最小字段与单文件协议
- [x] 9.3 固化 `pending / collecting / confirmed / consumed / cancelled / timed_out / stale` 状态机
- [x] 9.4 固化“先决策确认，再生成唯一正式 plan”的主路径
- [x] 9.5 固化 plan / history / blueprint 的决策写入边界
- [x] 9.6 固化 `~decide` 只作为 debug/override 入口
- [x] 9.7 固化 `auto_decide` 不绕过 design 决策确认
- [x] 9.8 在 runtime/router 中接入 design 自动触发
- [x] 9.9 实现 `current_decision.json` 的读写、恢复与清理
- [x] 9.10 实现 runtime 侧 decision handoff / state / 纯文本 fallback 契约
- [x] 9.11 为 pending / submission-resume / stale / cancel / confirmed 路径补测试

验收标准：

- 后续实现决策确认能力时，不需要再推翻当前文档治理模型
- “用户拍板后继续生成唯一正式 plan”成为固定主路径
- 不引入多份 draft plan，也不把关键决策只留在聊天上下文中

## 10. 文档与测试收口

- [x] 10.1 更新 README，解释 blueprint / plan / history / replay 的边界
- [x] 10.2 更新 AGENTS/CLAUDE 文档，解释 blueprint 的默认行为
- [ ] 10.3 更新 templates skill，补 blueprint 模板
- [ ] 10.4 更新 kb/develop/design skill，接入 blueprint 生命周期
- [x] 10.5 增加 blueprint bootstrap、托管区块、收口事务、history 归档的自动化测试

验收标准：

- README、宿主文档、skill 文档、runtime 行为口径一致
- 下游项目接入 Sopify 后可以完整复用这套文档治理模型

## 11. 第二阶段蓝图收敛

- [x] 11.1 固化“普通输入 / ~go / ~go plan / ~go exec / ~go finalize”的主链路语义边界
- [x] 11.2 固化 `clarification_pending / decision_pending / ready_for_execution / execution_confirm_pending` 的状态边界
- [x] 11.3 固化“先机器执行门禁，再用户执行确认”的执行门禁模型
- [x] 11.4 固化“未消解风险先进入澄清或决策，不直接执行”的分流规则
- [x] 11.5 固化 `~go exec` 仅作为恢复/调试/高级入口，且不能绕过任何门禁

验收标准：

- 普通用户不需要记忆 `~go exec` 才能走标准开发流
- 第二阶段实现时不需要再从聊天记录回溯主链路语义
- 决策确认、执行确认、收口归档之间的顺序关系清晰稳定

## 12. 第二阶段实现排期

实施顺序建议：

- 先补状态与路由骨架，再补执行门禁与确认协议
- 再补 `~go exec` 的限制语义与宿主消费逻辑
- 最后补自动化测试与外围能力评估

### 12.0 里程碑视图

| Milestone | 目标 | 覆盖任务 | 退出条件 |
|-----|------|---------|---------|
| `M1` | 建立主链路状态骨架 | `12.1` + `12.2` | runtime 能稳定表达澄清、决策、执行确认三类待处理状态 |
| `M2` | 引入机器执行门禁 | `12.3` + `12.5` | plan 是否可执行不再靠文案猜测，决策后重新过 gate |
| `M3` | 落地执行前用户确认 | `12.4` | gate 通过后统一进入 `confirm_execute`，用户用自然语言确认执行 |
| `M4` | `~go exec` 高级恢复入口化 | `12.6` + `12.7` | `~go exec` 退出主链路默认入口，文档与宿主口径统一 |
| `M5` | 回归验证与外围评估 | `12.8` + `12.9` | 第二阶段主链路具备测试保护，外围能力评估不阻塞主链路 |

依赖顺序：

- `M2` 依赖 `M1`
- `M3` 依赖 `M2`
- `M4` 依赖 `M3`
- `M5` 依赖 `M4`

切片建议：

- 每个 milestone 单独收口、单独验证、单独更新蓝图与宿主文档
- 不建议把 `M1-M4` 合并成一次大改动

### 12.1 状态与路由骨架

- [x] 12.1.1 在 runtime 层新增 `clarification_pending` 与 `execution_confirm_pending` 的状态定义
- [x] 12.1.2 在 router 中明确普通开发请求、`~go`、`~go plan`、`~go exec` 对应的主链路分支
- [x] 12.1.3 在 engine 中为第二阶段增加统一的状态迁移入口，避免把澄清、决策、执行确认散落在多个 if 分支
- [x] 12.1.4 在 output 中为 `clarification_pending` 与 `execution_confirm_pending` 增加统一输出模板
- [x] 12.1.5 在 manifest / handoff 契约中补齐第二阶段新增状态的可发现性

验收标准：

- runtime 内部可以稳定表示“缺信息待澄清”和“待执行确认”
- 路由、状态、输出、manifest 的名称保持一致

### 12.2 `clarification_pending` 接入

- [x] 12.2.1 固化“缺事实信息”的最小判定规则，不与 decision checkpoint 混用
- [x] 12.2.2 在 planning 主链路中把缺信息场景收敛到 `clarification_pending`
- [x] 12.2.3 明确 `clarification_pending` 的状态落盘格式与恢复规则
- [x] 12.2.4 为自然语言补充信息后的恢复路径补文档与状态转换说明
- [x] 12.2.5 明确 `clarification_pending` 不生成可执行 plan，也不允许进入 `~go exec`

验收标准：

- “缺信息”与“需拍板”不再混淆
- 宿主能恢复澄清状态，而不是误进 develop

### 12.3 机器执行门禁

- [x] 12.3.1 在 engine 中实现统一的 execution gate evaluator，而不是靠 `Next:` 文案暗示
- [x] 12.3.2 固化 `gate_status / blocking_reason / plan_completion / next_required_action` 的 machine contract
- [x] 12.3.3 明确哪些风险属于 `decision_required`，哪些风险可被 plan 吸收后继续前进
- [x] 12.3.4 明确 plan 结构完整性的最小要求，例如 metadata、tasks、风险说明、执行范围
- [x] 12.3.5 为 decision 确认完成后重新过门禁预留幂等入口

验收标准：

- plan 是否可执行不再靠宿主猜测
- 同一 plan 多次评估时门禁结果可重复、可解释

### 12.4 执行前用户确认

- [x] 12.4.1 在 handoff contract 中新增或收敛统一的 `confirm_execute` machine action
- [x] 12.4.2 明确执行前确认必须展示的最小摘要：plan 路径、方案摘要、任务数、关键风险
- [x] 12.4.3 固化自然语言确认入口 `继续 / next / 开始` 的解析规则
- [x] 12.4.4 明确执行前确认通过后的状态迁移：`ready_for_execution -> execution_confirm_pending -> executing`
- [x] 12.4.5 明确执行前确认取消或修改意见的回退路径

验收标准：

- 普通用户不需要记住 `~go exec`
- 代码执行前始终存在一次清晰、轻量、统一的确认动作

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
