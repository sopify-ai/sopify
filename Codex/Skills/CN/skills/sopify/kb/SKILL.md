---
name: kb
description: 知识库管理技能；知识库操作时读取；包含初始化、更新、同步策略
---

# 知识库管理 - V2 规则

**目标：** 管理 `.sopify-skills/` 的 V2 分层知识，保持长期知识、活动方案与归档层职责清晰。

## 知识库结构

```text
.sopify-skills/
├── blueprint/
│   ├── README.md           # 纯索引页，只保留入口与状态
│   ├── background.md       # 长期目标、范围、非目标
│   ├── design.md           # 模块/宿主/目录/消费契约
│   └── tasks.md            # 未完成长期项与明确延后项
├── project.md              # 项目技术约定
├── user/
│   ├── preferences.md      # 用户长期偏好
│   └── feedback.jsonl      # 原始反馈事件
├── plan/
│   └── YYYYMMDD_feature/   # 当前活动方案
├── history/
│   ├── index.md            # 归档索引
│   └── YYYY-MM/
└── state/                  # runtime machine truth
```

## 初始化策略

### Full 模式 (`kb_init: full`)

首次 bootstrap 直接创建：

```yaml
创建文件:
  - .sopify-skills/project.md
  - .sopify-skills/user/preferences.md
  - .sopify-skills/user/feedback.jsonl
  - .sopify-skills/blueprint/README.md
  - .sopify-skills/blueprint/background.md
  - .sopify-skills/blueprint/design.md
  - .sopify-skills/blueprint/tasks.md
```

注意：

- 不预建 `plan/` 正文。
- 不预建 `history/index.md` 或任何 archive。

### Progressive 模式 (`kb_init: progressive`) [默认]

按生命周期创建：

```yaml
首次真实项目触发:
  - .sopify-skills/project.md
  - .sopify-skills/user/preferences.md
  - .sopify-skills/blueprint/README.md

首次进入 plan 生命周期:
  - .sopify-skills/blueprint/background.md
  - .sopify-skills/blueprint/design.md
  - .sopify-skills/blueprint/tasks.md
  - .sopify-skills/plan/YYYYMMDD_feature/

首次显式 ~go finalize:
  - .sopify-skills/history/index.md
  - .sopify-skills/history/YYYY-MM/YYYYMMDD_feature/

首次出现明确长期偏好:
  - .sopify-skills/user/feedback.jsonl
```

## 上下文读取顺序

1. `project.md`
2. `user/preferences.md`
3. `blueprint/README.md`
4. `blueprint/background.md`
5. `blueprint/design.md`
6. `blueprint/tasks.md`
7. `active_plan = current_plan.path + current_plan.files`

读取规则：

- 咨询/澄清优先消费 `L0/L1`，不强制要求 deep blueprint。
- planning / develop 才进入 `L2 active plan`。
- `history/` 不是默认长期上下文，只在 finalize 后查询或人工追溯时读取。

## 更新规则

### 必须更新

- `project.md`：跨任务可复用的技术约定变化。
- `blueprint/background.md`：长期目标、范围、非目标变化。
- `blueprint/design.md`：模块/宿主/目录/消费契约变化。
- `blueprint/tasks.md`：长期未完成项或明确延后项变化。
- `user/preferences.md`：用户明确声明长期偏好。

### 不应写入长期知识

- 一次性实现细节。
- 当前 plan 的短期拆解。
- 仅属于本轮任务的临时取舍。
- history 正文回灌到 blueprint。

## `knowledge_sync` 同步契约

```yaml
knowledge_sync:
  project: skip|review|required
  background: skip|review|required
  design: skip|review|required
  tasks: skip|review|required
```

执行要求：

- `skip`：本轮不要求同步。
- `review`：finalize 前至少复核。
- `required`：未更新则 finalize 阻断。

## 冲突处理

- 代码与文档冲突：以代码现状为准，文档随后修正。
- 当前任务与长期偏好冲突：当前任务明确要求 > `user/preferences.md` > 默认规则。

## 输出格式

**初始化完成：**

```text
[{BRAND_NAME}] 知识库初始化 ✓

创建: {N} 文件
策略: {full/progressive}

---
Changes: {N} files
  - .sopify-skills/project.md
  - .sopify-skills/blueprint/README.md
  - ...

Next: 知识库已就绪
```

**同步完成：**

```text
[{BRAND_NAME}] 知识库同步 ✓

更新: {N} 文件

---
Changes: {N} files
  - .sopify-skills/project.md
  - .sopify-skills/blueprint/design.md
  - ...

Next: 文档已更新
```
