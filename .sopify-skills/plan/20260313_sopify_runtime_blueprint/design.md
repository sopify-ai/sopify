# 设计

## 架构总览

推荐形态：

`契约层 + 薄 runtime + 文件系统状态机 + 可扩展 skills`

### 契约层

这一层延续 Sopify 当前已经很强的部分：

- `AGENTS.md`
- `SKILL.md`
- 模板

它负责定义行为、阶段和约束，但不直接负责确定性的状态推进。

### 薄 runtime

这是新增的执行壳，要求小、清晰、可控。

它负责：

- 配置加载
- 路由分类
- 运行状态持久化
- 方案骨架生成
- replay 写入
- skill 发现

### 文件系统状态机

文件系统是运行状态的单一事实源。

这样做的收益是：

- 运行状态可观察
- 多轮任务可恢复
- 不依赖 prompt 记忆

### 可扩展 skills

skills 仍然作为上层契约保留，并对未来扩展开放。

Sopify 不维护外部 skill 的业务细节，只负责：

- 发现它
- 判断它是否可参与当前流程
- 在合适阶段把它纳入编排
- 当它是 runtime 型 skill 时调用它

## 职责划分

### Sopify Runtime 负责

- 命令路由
- 工作流阶段推进
- 产物目录结构
- 状态文件
- replay 落盘
- skill 发现规则

### 模型负责

- 流程内的语义理解
- 候选 skill 中的偏好判断
- 内容生成
- 解释、总结、方案正文

### 外部 Skill 负责

- 领域指令
- 可选运行脚本
- 该 skill 自己定义的领域产物

## 工程模式收口

### P0 优先吸收的模式

- 稳定入口只负责引导，不承载业务流程细节
- 路由判断与总编排明确拆开
- 状态与上下文恢复由 runtime 主动完成
- 高频控制点优先代码化，而不是继续堆叠 prompt 规则

### P1 优先吸收的模式

- 知识库初始化先做最小可用版本
- 历史回收优先索引和摘要，不直接展开全量内容
- 任务状态作为一等运行对象显式维护
- 高价值规则优先转成脚本入口

### 当前不进入核心的模式

- 安装器、升级器、通知、hooks 等外围产品层
- 多 CLI 兼容层
- 子代理编排平台
- 重型宿主配置写入器

## R0 发布切片

### 发布目标

R0 只发布一条最小闭环：

- `runtime-backed ~go plan`

这意味着本阶段的目标不是“把所有 Sopify 命令都 runtime 化”，而是先把最容易闭环的一条路径变成真实可安装能力。

### R0 最小闭环

建议闭环顺序：

1. 安装产物包含 runtime 所需代码
2. 安装后的入口可以把 `~go plan` 交给 runtime
3. runtime 生成 plan / state / replay 产物
4. 输出层把 `RuntimeResult` 渲染成 Sopify 统一展示格式
5. 测试与 CI 对这条路径给出稳定校验

### R0 新增接线层

在现有 runtime 核心之外，R0 还需要补齐 4 类接线能力：

- 分发接线: 确保安装包里真的带上 runtime 所需代码
- 入口接线: 确保 `~go plan` 有稳定入口进入 `run_runtime(...)`
- 输出接线: 确保 `RuntimeResult` 可以转换成用户可见摘要
- 发布校验: 确保安装后端到端行为可验证

### R0 不纳入范围

以下能力保留到后续阶段，不进入当前发布切片：

- `~go` 的完整分析到开发闭环
- `~go exec` 的任务执行桥接
- `workflow-learning` 的 runtime 解释链路
- history archive / task state / KB bootstrap
- 完整 develop 自动执行引擎

## P0 模块边界

### `runtime/models.py`

负责：

- 定义共享数据结构和跨模块契约

建议导出：

- `RuntimeConfig`
- `SkillMeta`
- `RouteDecision`
- `RunState`
- `RecoveredContext`
- `PlanArtifact`
- `ReplayEvent`
- `RuntimeResult`

不负责：

- 文件 IO
- 路由逻辑
- 业务规则

### `runtime/config.py`

负责：

- 加载默认配置
- 合并项目级 / 全局配置
- 归一化运行期配置

输入：

- workspace root
- 可选全局配置路径

输出：

- `RuntimeConfig`

不负责：

- skill 发现
- 路由判断
- 状态写入
- 宿主 CLI 配置修补

### `runtime/state.py`

负责：

- `.sopify-skills/state/` 路径约定
- 当前 run 状态读写
- 上一次路由结果读写
- 当前 plan 引用读写

管理文件：

- `current_run.json`
- `last_route.json`
- `current_plan.json`

不负责：

- 路由选择
- replay 内容
- 方案文件生成
- 安装或升级行为

### `runtime/context_recovery.py`

负责：

- 基于 route 回收最小必要上下文
- 在新会话中恢复 active run 的最小工作集
- 将文件系统状态整理成标准化上下文对象

P0 只允许读取：

- `state/current_run.json`
- `state/current_plan.json`
- `state/last_route.json`
- 当前 plan 包的摘要文件

输出：

- `RecoveredContext`

不负责：

- 全量扫描 `wiki/`
- 全量扫描 `history/`
- 全量加载 `replay/`
- 推断长期偏好
- 依赖 prompt 约定做隐式恢复

### `runtime/skill_registry.py`

负责：

- 扫描约定目录
- 解析最小 skill 元信息
- 对外暴露候选 skill 列表

搜索顺序：

1. 内建 Sopify skills
2. `./skills/*`
3. `./.sopify-skills/skills/*`
4. `~/.codex/skills/*`

不负责：

- 最终 skill 选择
- 执行完整 `SKILL.md`
- 调用 runtime 脚本

### `runtime/router.py`

负责：

- 对命令做硬路由
- 对已有状态延续做硬路由
- 对普通输入生成 soft candidate set
- 推荐 plan level

输出：

- `RouteDecision`

硬路由示例：

- `~go`
- `~go plan`
- `~go exec`
- `~compare`
- 回放 / 复盘类意图
- 当前 active run 下的“继续 / 下一步”意图

不负责：

- 写状态文件
- 生成产物
- 执行 skills
- 交互式安装或运维命令

### `runtime/plan_scaffold.py`

负责：

- 生成 `light / standard / full` 方案包骨架
- 方案目录命名
- 调用模板渲染入口

输出：

- plan 目录
- 生成的文件清单
- `PlanArtifact`

不负责：

- 路由判断
- 任务执行
- history 归档

### `runtime/replay.py`

负责：

- 创建 run session 目录
- 追加事件
- 生成 `session.md`
- 生成 `breakdown.md`

管理文件：

- `.sopify-skills/replay/sessions/{run_id}/events.jsonl`
- `.sopify-skills/replay/sessions/{run_id}/session.md`
- `.sopify-skills/replay/sessions/{run_id}/breakdown.md`

不负责：

- 决定是否开启 capture
- 路由判断
- plan 生成
- 任务状态推进

### `runtime/skill_runner.py`

负责：

- 调用 runtime 型 skill
- 标准化 runtime skill 的返回结果
- 将 skill 执行与 router 解耦

不负责：

- skill 发现
- 路由选择
- 直接维护全局状态
- 把普通 advisory skill 强行转成 runtime skill

### `runtime/engine.py`

负责：

- 唯一的总编排入口
- 规定模块调用顺序
- 返回标准化 `RuntimeResult`

标准调用顺序：

1. 加载 config
2. 加载 state
3. 初始化最小 KB 骨架
4. 发现 skills
5. 分类 route
6. 回收最小上下文
7. 持久化 route 状态
8. 分支进入 scaffold / replay / runtime skill / plain Q&A
9. 按需写 replay 事件

不负责：

- 深层路由规则细节
- 任意业务 skill 逻辑
- 越权写入其他模块负责的路径
- 安装器、升级器、通知等外围产品能力

### `发布接线层`

负责：

- 把仓库内 runtime 资产纳入安装路径
- 保证 Codex / Claude 两侧拿到同一份运行时能力
- 明确发布切片需要同步的额外文件

不负责：

- 改写 runtime 核心逻辑
- 承担路由或状态判断

### `入口适配层`

负责：

- 接收宿主环境中的 `~go plan` 输入
- 调用 `run_runtime(...)`
- 传递 workspace、配置路径和宿主必要上下文

不负责：

- 自己重复实现路由逻辑
- 绕开 runtime 直接写 plan 产物

### `输出渲染层`

负责：

- 把 `RuntimeResult` 映射成 Sopify 输出模板
- 稳定展示 plan 路径、产物文件、下一步提示
- 失败时输出可诊断信息

不负责：

- 决定路由
- 写状态文件
- 生成业务内容

## P1 模块边界

### `runtime/kb.py`

负责：

- 最小知识库初始化
- 最小偏好持久化
- 轻量项目上下文文件
- 当前先读取根配置、manifest、顶层目录；后续再按需扩展到源码扫描
- 当前最小落地范围是首次运行时创建 `project.md`、`wiki/overview.md`、`user/preferences.md`、`history/index.md`

不负责：

- 智能全量文档同步
- 全量自动加载知识库
- history archive
- 选择性历史回收策略

### `runtime/history.py`

负责：

- 方案归档
- `history/index.md` 更新
- 为 P1 的选择性历史回收提供稳定索引入口

不负责：

- 任务执行
- 方案生成
- 决定是否加载全部历史

### `runtime/task_state.py`

负责：

- 读取和更新任务状态标记
- 维护 `plan.md` / `tasks.md` 中的 `[ ] [x] [!] [-]`

不负责：

- 真实开发动作执行
- replay 事件写入

### `skills/.../scripts/*`

P1 优先脚本化的高价值 skills：

- `workflow-learning`
- `templates`

之后再评估：

- `kb`
- `develop`

### 外围产品层（当前后置）

这类能力不进入当前 runtime 核心：

- installer / updater
- notify / hooks
- 宿主配置 doctor / patch
- 多 CLI 兼容适配

## 文件系统状态模型

建议目录：

```text
.sopify-skills/
├── state/
│   ├── current_run.json
│   ├── last_route.json
│   └── current_plan.json
├── plan/
├── replay/
│   └── sessions/{run_id}/
├── history/
├── wiki/
└── user/
```

推荐状态推进：

1. 收到输入
2. 决定路由
3. 回收该路由所需的最小上下文
4. 路由落盘
5. 生成 plan 或 replay 产物
6. 到 P1 才逐步补齐 KB 与 history

## 上下文回收边界

### 基本原则

- 上下文不是模型天然记忆，而是 runtime 主动回收的本地状态
- 回收必须按路由选择，不能做目录级全量加载
- P0 只解决“续跑当前流程”，P1 才解决“有边界地利用历史积累”

### P0 最小上下文回收

目标：

- 支持新会话续接当前活跃流程
- 让 `~go exec`、`继续`、`下一步` 具备确定性恢复能力

推荐读取集：

- `state/current_run.json`
- `state/current_plan.json`
- `state/last_route.json`
- 当前 plan 的 `README.md`、`plan.md` 或 `tasks.md`

禁止项：

- 不自动全量读取 `wiki/`
- 不自动全量读取 `history/`
- 不自动遍历全部 replay session

### P1 选择性历史回收

目标：

- 让 Sopify 在长期使用后能有限利用历史积累
- 避免历史文档反向污染当前任务

推荐候选源：

- `history/index.md`
- 最近一次相关 replay 的 `session.md`
- `user/preferences.md`
- `wiki/overview.md`

触发原则：

- 只在路由明确需要历史时读取
- 优先读取索引和摘要，不直接展开原始全量文档
- 单次回收必须有数量上限和文件类型上限

## Skill 扩展约定

### 推荐结构

```text
skills/<skill-id>/
├── SKILL.md
├── skill.yaml
├── scripts/
└── references/
```

### `skill.yaml` 最小字段

建议字段：

- `id`
- `description`
- `mode`
- `triggers`
- `runtime_entry`
- `artifacts`
- `requires`

### Skill 模式

- `advisory`: 纯指导型，给模型读
- `workflow`: 参与流程阶段
- `runtime`: 有脚本入口，可由 Sopify 调用

## 明确延后

以下内容当前明确延后：

- 深 `core / adapter / provider / plugin` 架构
- marketplace 式扩展系统
- 复杂 skill 继承语义
- 重型 KB 智能同步
- 全量自动加载 KB
- 完整 develop 自动执行引擎
- 安装器、升级器、通知、hooks、多 CLI 兼容层

## 设计原则收束

- 先把 P0 工程骨架和 R0 发布切片分开管理
- R0 只发布最小闭环，不为了口径完整而提前承诺后续能力
- P0 优先保证 runtime 清晰可控
- R0 优先保证安装、接线、输出、验证闭环
- P1 优先保证积累、归档、回放能力
- 任何会破坏“默认无配置主流程”的改动，都应谨慎引入
- 任何会扩大用户可见配置面的设计，都应优先考虑是否能改成约定优于配置
