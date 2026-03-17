# 文档治理蓝图设计

状态: 文档已收口，部分已实现
创建日期: 2026-03-17

## 设计原则

1. 默认行为优先于用户配置
2. 工程化生命周期优先于语义化记忆
3. 索引与深层文档分层，避免首次触发写得过重
4. 单活动 plan 优先，历史归档延后到收口时
5. Blueprint 是长期真相；plan/history 是执行资产

## 目录契约

```text
.sopify-skills/
├── blueprint/              # 项目级长期蓝图，默认进入版本管理
│   ├── README.md           # 项目入口索引，首次触发即可创建
│   ├── background.md       # 长期目标、边界、约束、非目标
│   ├── design.md           # 模块边界、宿主契约、目录契约、关键数据流
│   └── tasks.md            # 长期演进项与待办
├── plan/                   # 当前活动方案，默认忽略
│   └── YYYYMMDD_feature/
├── history/                # 收口归档，默认忽略
│   ├── index.md
│   └── YYYY-MM/
│       └── YYYYMMDD_feature/
├── state/                  # 运行态状态，始终忽略
└── replay/                 # 可选回放能力，始终忽略
```

## 首次触发生命周期

### A. 首次 Sopify 触发

在 runtime 固定入口中执行 `ensure_blueprint_index(...)`：

- 不依赖用户命令是否进入 plan
- 不依赖咨询/设计/开发语义
- 只依赖“当前目录是否为真实项目仓库”的机器判定

真实项目仓库判定建议：

- 命中以下任一条件即视为真实项目：
  - 存在 `.git/`
  - 存在 `package.json / pyproject.toml / go.mod / Cargo.toml / pom.xml / build.gradle`
  - 存在 `src / app / lib / tests / scripts` 等目录

若命中且 `blueprint/README.md` 缺失：

- 只创建 `blueprint/README.md`
- 不在咨询场景强行创建 `background.md / design.md / tasks.md`

### B. 首次进入 plan 生命周期

进入 `plan_only / workflow / light_iterate` 时：

- 若 `blueprint/background.md / design.md / tasks.md` 缺失，则补齐
- 创建当前活动 `plan/`
- 写入本次方案的机器元数据

## Blueprint README 强约束模板

`blueprint/README.md` 是项目级全局索引，必须固定包含以下区块：

1. 当前目标
2. 项目概览
3. 架构地图
4. 关键契约
5. 当前焦点
6. 深入阅读入口

其中索引性区块采用托管标记，便于后续自动刷新：

```md
<!-- sopify:auto:goal:start -->
...
<!-- sopify:auto:goal:end -->
```

设计要求：

- 托管区块只写高密度摘要，不写长篇论证
- 非托管区块允许人工补充背景说明
- 自动刷新只更新托管区块，不覆盖人工说明

## Plan 元数据契约

不新增独立元数据文件，优先使用现有 plan 文件头部承载机器字段：

- `light`: 写入 `plan.md`
- `standard / full`: 写入 `tasks.md`

最小字段建议：

```yaml
plan_id:
feature_key:
level: light|standard|full
lifecycle_state: active|ready_for_verify|archived
blueprint_obligation: index_only|review_required|design_required
archive_ready: false
```

默认映射：

- `light` -> `index_only`
- `standard` -> `review_required`
- `full` -> `design_required`

说明：

- `standard` 是否真的需要更新深层 blueprint，不再完全依赖语义猜测，而是在收口阶段结合改动类型与 obligation 共同判断
- `full` 视为必须同步深层 blueprint

## 收口事务

不依赖 commit hook；使用固定的“收口事务”统一完成文档生命周期。

建议事务顺序：

1. 校验当前 plan 是否达到 `ready_for_verify`
2. 刷新 `blueprint/README.md` 托管区块
3. 根据 `blueprint_obligation` 判断是否要求更新 `background.md / design.md / tasks.md`
4. 归档当前 plan 到 `history/YYYY-MM/...`
5. 更新 `history/index.md`
6. 清理或更新 `current_plan / current_run / current_handoff`

## Blueprint 更新规则

### Light

- 不要求更新深层 blueprint
- 允许只刷新 `blueprint/README.md` 的索引摘要

### Standard

仅在以下任一条件命中时，要求更新深层 blueprint：

- 模块边界变化
- 宿主接入契约变化
- manifest / handoff 契约变化
- 目录契约变化
- 长期技术约定变化

### Full

- 必须更新 `background.md / design.md / tasks.md`
- `README.md` 同步刷新当前焦点、关键契约与阅读入口

## History 契约

`history/` 只在“本轮任务收口、准备交付验证”时写入：

- 平时不与当前 `plan/` 双写
- 不做实时镜像
- 不做多个 plan 自动归并

单次 plan 的归档规则：

- 一个活动 plan 对应一个归档目录
- `history/index.md` 只记录摘要索引
- 归档后 `plan/` 中不再保留该活动方案的工作态职责

## Replay 契约

- `replay/` 保持为可选能力
- 不作为“接入 Sopify 后必须完整支持”的基础文档治理要求
- 若启用 `workflow-learning`，仍可按独立能力写入本地 replay 资产

## 与决策确认能力的衔接

决策确认能力（decision checkpoint）应建立在本蓝图之上：

1. 仅在 design 阶段自动触发
2. 触发时先暂停正式 plan 生成
3. 将待确认状态写入 `state/current_decision.json`
4. 用户确认后再生成唯一正式 plan
5. 选择结果先写入当前 plan
6. 若形成长期稳定结论，再在收口时同步到 blueprint

这样可以同时满足：

- 不引入多份 draft plan
- 不要求用户额外配置
- 不把关键决策只留在聊天上下文里

## 决策确认触发契约

### 自动触发条件

第一版 runtime 已按确定性规则落地自动触发：

- 仅在 `plan_only / workflow / light_iterate` 中生效
- 仅对显式多方案输入触发，当前识别符包括 `还是 / vs / or`
- 同时要求命中长期契约关键词（如 `runtime / payload / manifest / blueprint / 目录 / 宿主 / workspace`）

也就是说，第一版先优先保证“严谨可测”，而不是对所有隐式分叉都做激进猜测。

只有同时满足以下条件，才进入 decision checkpoint：

1. 当前已进入 `design` 阶段，而不是咨询、快速修复或 develop 收口
2. 至少存在 2 个都可实施的候选方案
3. 候选方案差异涉及长期契约，而不是局部实现细节
4. 不同选择会改变后续 plan 内容、任务拆分或 blueprint 写入结果
5. 现有 `project.md / blueprint / 当前活动上下文` 不能直接推导唯一答案

长期契约分叉典型包括：

- 宿主接入契约
- payload / manifest / handoff 结构
- 目录落点与生命周期
- 模块边界或职责切分
- 持久化格式与状态文件协议
- 依赖引入策略或验证链路

### 不触发条件

以下情况不应触发 decision checkpoint：

- 只是命名、注释、文案、排版等轻量差异
- 只有一个方案符合现有契约，其他候选明显无效
- 已被 `project.md` 或 blueprint 明确写死
- `light` 级任务内的局部实现细节
- 单纯为了给用户“看起来有选择”而构造伪分叉

## 决策状态机

决策确认采用单 pending 模型，每个仓库同一时刻只允许一个未完成决策：

```text
none
  -> pending      # design 识别到需拍板的分叉，写入 current_decision.json
  -> confirmed    # 用户选定方案，但正式 plan 尚未完全物化
  -> consumed     # 已基于确认结果生成唯一正式 plan
  -> cancelled    # 用户取消，本轮 design 不继续产出正式 plan
  -> stale        # 上下文已变化，原决策不再可信，需要重建
```

状态要求：

- `pending` 时，plan 不得提前生成
- `confirmed` 时，必须保留足够信息让 runtime 能幂等恢复 plan 物化
- `consumed` 后，应清理当前决策状态，避免后续误恢复
- `cancelled` 后，不生成正式 plan，由用户重新发起设计或修改需求
- `stale` 只表示状态失效，不等于用户已经完成选择

## `state/current_decision.json` 契约

第一版不新增多文件协议，统一落到：

```text
.sopify-skills/state/current_decision.json
```

建议最小字段：

```yaml
decision_id:
feature_key:
phase: design
status: pending|confirmed|consumed|cancelled|stale
decision_type:
question:
summary:
options:
  - id:
    title:
    summary:
    tradeoffs:
    impacts:
    recommended: true|false
recommended_option_id:
default_option_id:
context_files:
  - project.md
  - .sopify-skills/blueprint/README.md
resume_route:
selection:
  option_id:
  source: interactive|text|debug_override
  raw_input:
created_at:
updated_at:
confirmed_at:
consumed_at:
```

字段要求：

- `options` 应限制为 2-3 个高价值候选；超过 3 个时，design 先自行压缩 shortlist
- `recommended_option_id` 必须存在，且推荐理由要能落到输出摘要
- `raw_input` 允许保留用户自由输入，但后续只进 plan，不直接写 blueprint
- `context_files` 用于恢复时提示模型优先读取哪些文件，而不是重新扫全仓

## 交互契约

### 主路径

第一版主路径只支持 design 自动触发：

1. design 识别到长期契约分叉
2. 写入 `current_decision.json`
3. 输出简洁决策摘要与候选项
4. 等待用户选择
5. 用户确认后继续生成唯一正式 plan

### 交互形态

宿主若支持交互式 UI，应优先渲染成 Inquirer 风格选择器；若不支持，则退化为文本选择：

- 推荐项排第一
- 每个候选只展示一行摘要和一行关键 tradeoff
- 允许用户选择现有选项、要求重做比较、或明确取消
- 不要求用户学习额外配置或预先启用某个模式

### `~decide` 边界

`~decide` 只作为调试或覆盖入口，不是第一版主路径：

- `~decide status`：查看当前 pending decision
- `~decide choose <option_id>`：直接选定某个候选
- `~decide cancel`：放弃本轮 decision checkpoint

它不负责：

- 主动发现是否需要决策
- 取代 design 阶段的自动触发
- 让用户绕过当前 blueprint / project 契约随意落 plan

## 与现有 `auto_decide` 的边界

`README/AGENTS` 中已有 `auto_decide`，但该能力属于需求分析阶段的缺口补全，不应越权替代 design 阶段的决策确认。

边界应固定为：

- `auto_decide`：当需求评分不足时，是否允许 AI 代为补齐分析缺口
- `decision checkpoint`：当 design 出现长期契约分叉时，是否需要用户拍板

第一版中：

- `auto_decide` 不绕过 decision checkpoint
- 出现 decision checkpoint 时，默认必须等待用户确认
- 不新增新的配置项去关闭这条主路径

## Plan 物化契约

decision checkpoint 通过前，不生成正式 `plan/` 目录。

用户确认后，runtime 才基于所选方案物化唯一正式 plan，并在 plan 元数据中补充决策字段：

```yaml
decision_checkpoint:
  required: true
  decision_id:
  selected_option_id:
  status: confirmed
```

同时在 plan 正文中保留完整决策块，至少包括：

- 问题定义
- 候选方案摘要
- 最终选择
- 推荐理由与用户确认结果
- 被放弃方案的关键取舍

这样可以保证：

- plan 是唯一正式执行入口
- 后续 develop / history 不必回头解析聊天记录
- 决策解释在 plan 中完整可追溯

## Blueprint / History 写入边界

写入分层固定如下：

- `plan`：写完整决策上下文、用户选择、被放弃方案的关键取舍
- `history`：写摘要级结论，便于之后追溯为什么走了该方案
- `blueprint`：只在形成稳定长期结论时写入，不写原始自由输入

blueprint 的典型落点：

- `blueprint/README.md` 的关键契约与当前焦点摘要
- `blueprint/design.md` 中的宿主契约、目录契约、状态协议
- `blueprint/background.md` 中新增的长期边界或非目标

## 恢复与幂等

决策确认必须支持中断恢复：

1. 若仓库存在 `current_decision.json` 且状态为 `pending / confirmed`，优先恢复，而不是重新生成新决策
2. 若用户修改了核心上下文，导致原候选不再可信，则标记为 `stale`
3. `stale` 后必须重新走 design 产出新的 decision packet，不能直接沿用旧选择
4. `confirmed` 到 plan 物化之间若中断，恢复后应能幂等继续，不重复创建多个 plan

单仓库单 pending 的限制，可以避免：

- 多个决策文件互相竞争
- 多份草稿 plan 并存
- 宿主在恢复时无法判断该优先处理哪一个 checkpoint

## 读取优先级建议

给宿主与 LLM 的默认读取顺序：

1. `project.md`
2. `blueprint/README.md`
3. `wiki/overview.md`
4. 当前活动 `plan/`
5. 按需进入 `blueprint/design.md / background.md`
6. 只有在需要追溯旧方案时才查看 `history/`

这样可以形成稳定的渐进式披露：

- 先读索引
- 再读当前任务
- 最后按需追溯历史
