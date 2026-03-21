---
name: templates
description: 文档模板集合；创建文档时读取；包含所有知识库模板和方案文件模板
---

# 文档模板集合

**模板使用说明：**
1. 将 `{...}` 内容替换为实际内容。
2. 正式 plan 包默认带评分区块。
3. `blueprint/README.md` 只保留轻量入口索引。

## A1 | 知识库文档模板

### project.md

```markdown
# 项目技术约定

## 技术栈
- 核心: {语言版本} / {框架版本}
- 构建: {构建工具}
- 测试: {测试框架}

## 使用约定
- 这里只沉淀可复用的长期技术约定。
- 一次性实现细节不默认写入本文件。

## 文档边界
- `project.md`: 可复用技术约定
- `blueprint/background.md`: 长期目标、范围、非目标
- `blueprint/design.md`: 模块/宿主/目录/消费契约
- `blueprint/tasks.md`: 未完成长期项与明确延后项
```

### blueprint/README.md

```markdown
# 项目蓝图索引

状态: {当前状态}
维护方式: 仅保留入口索引；长说明进入其他 blueprint 文件

| Entry | Meaning | Status |
|-----|------|------|
| `../project.md` | 项目级技术约定 | active |
| `./background.md` | 长期目标、范围、非目标 | active |
| `./design.md` | 模块/宿主/目录/消费契约 | active |
| `./tasks.md` | 未完成长期项与明确延后项 | active |
| `../plan/` | 当前活动方案 | on-demand |
| `../history/index.md` | 归档索引 | on-demand |
```

### blueprint/background.md

```markdown
# 蓝图背景

## 长期目标
- {目标1}
- {目标2}

## 范围
- 范围内: {内容}
- 范围外: {内容}

## 非目标
- {内容}
```

### blueprint/design.md

```markdown
# 蓝图设计

## 正式契约
- `knowledge_sync` 是唯一正式同步契约。
- `active_plan = current_plan.path + current_plan.files`。

## 消费契约

| Context Profile | Reads | Fail-open Rule | Notes |
|-----|------|------|------|
| `consult` | `project.md`, `preferences.md`, `blueprint/README.md` | 缺 deep blueprint 不报错 | 不强制物化 plan |
| `plan` | `L1` + `active_plan` | 缺 deep blueprint 时按生命周期补齐 | history 不是默认上下文 |
| `finalize` | `active_plan`, `knowledge_sync`, `blueprint/*`, `history/index.md` | 缺 `history/index.md` 时现场创建 | `required` 未满足则阻断 |
```

### blueprint/tasks.md

```markdown
# 蓝图任务

## 未完成长期项
- [ ] {长期项}

## 明确延后项
- [-] {延后项}
```

### history/index.md

```markdown
# 变更历史索引

| 时间戳 | 功能名称 | 状态 | 方案包 |
|--------|----------|------|--------|
| {YYYYMMDD} | {功能} | ✓ | [链接](YYYY-MM/...) |
```

### user/preferences.md

```markdown
# 用户长期偏好

> 仅记录用户明确声明的长期偏好；一次性指令不入库。

当前暂无已确认的长期偏好。
```

### user/feedback.jsonl

```json
{"timestamp":"2026-01-15T10:30:00Z","source":"chat","message":"以后默认先给最小改动清单","scope":"planning","promote_to_preference":true,"preference_id":"pref-002"}
{"timestamp":"2026-01-15T11:10:00Z","source":"chat","message":"这次把输出写详细点","scope":"current_task","promote_to_preference":false}
```

## A2 | 方案文件模板

### Light 级别 - plan.md

```markdown
# {功能名称}

## 背景
{1-2 句话描述需求背景}

评分:
- 方案质量: {X}/10
- 落地就绪: {Y}/10

评分理由:
- 优点: {1 行}
- 扣分: {1 行}

## 方案
- {技术方案要点1}
- {技术方案要点2}

## 任务
- [ ] {任务1}
- [ ] {任务2}

## 变更文件
- {file1}
- {file2}
```

### Standard 级别 - background.md

```markdown
# 变更提案: {功能名称}

## 需求背景
{描述现状、痛点及变更驱动因素}

评分:
- 方案质量: {X}/10
- 落地就绪: {Y}/10

评分理由:
- 优点: {1 行}
- 扣分: {1 行}

## 变更内容
1. {变更点1}
2. {变更点2}

## 影响范围
- 模块: {列表}
- 文件: {列表}

## 风险评估
- 风险: {描述}
- 缓解: {措施}
```

### Standard 级别 - design.md

```markdown
# 技术设计: {功能名称}

## 技术方案
- 核心技术: {语言/框架/库}
- 实现要点:
  - {要点1}
  - {要点2}

## 架构设计
{如有架构变更}

## 安全与性能
- 安全: {措施}
- 性能: {优化}
```

### Standard 级别 - tasks.md

```markdown
# 任务清单: {功能名称}

目录: `.sopify-skills/plan/{YYYYMMDD}_{feature}/`

## 1. {模块名称}
- [ ] 1.1 在 `{文件路径}` 中实现 {功能}
- [ ] 1.2 在 `{文件路径}` 中实现 {功能}

## 2. 测试
- [ ] 2.1 {测试任务}

## 3. 文档更新
- [ ] 3.1 更新 `project.md / blueprint/background.md / blueprint/design.md / blueprint/tasks.md`
```

### Full 级别 - adr/{NNN}-{title}.md

```markdown
# ADR-{NNN}: {决策标题}

## 状态
已采纳 | 待定 | 已废弃

## 日期
{YYYY-MM-DD}

## 上下文
{背景和问题描述}

## 决策
{核心决策内容}
```

## A3 | 任务状态符号

| 符号 | 含义 |
|-----|------|
| `[ ]` | 待执行 |
| `[x]` | 已完成 |
| `[-]` | 已跳过 |
| `[!]` | 阻塞中 |
