# Convention Mode 跨宿主 Smoke Test — Host B 指引

## 你是谁

你是 **Host B**，一个独立于 Host A 的第二宿主/模型。你的任务是验证 Sopify 的 Convention 模式协议是否可被第二消费者消费。

## 前提

- 项目目录：你需要访问 `sopify-skills` 仓库
- 分支：`feat/blueprint-rebaseline`（protocol.md 在这个分支上）
- **你不能读取** `.sopify-skills/state/` 下的任何文件
- **你不能读取** `.sopify-skills/replay/` 下的任何文件
- **你不需要运行** Python runtime 或任何脚本

## 执行步骤（共 4 步）

### Step 1: 读取项目约定
读取 `.sopify-skills/project.md`，确认你能识别项目名。

### Step 2: 读取蓝图上下文
读取以下文件，理解项目定位：
- `.sopify-skills/blueprint/background.md`（核心：Sopify 是什么）
- `.sopify-skills/blueprint/protocol.md`（核心：最小协议规范）

用一句话复述 Sopify 的定位。

### Step 3: 读取活动 plan
读取 `.sopify-skills/plan/20260501_convention_smoke/plan.md`
- 确认 task-1 已完成（`[x]`）
- 确认 task-2 已被上一个 Host B 完成（`[x]`）

### Step 4: 创建新 task 并完成它
在同一个 `plan.md` 文件中：

1. 在 Tasks 区域添加一行：
```
- [x] task-3: 真实第二宿主验证 — 读取 project.md + blueprint/，确认 Convention 模式可消费
```

2. 在 `## Host B 消费证据` 区域下方新增一个 `## Host C 消费证据` 区域（或直接追加），填写：
```
- `host_identity`: [你的宿主名 + 模型名，如 "Cursor / GPT-4o" 或 "Codex / o3"]
- `project_name`: [从 project.md 读到的项目名]
- `sopify_positioning`: [从 background.md 读到的 Sopify 定位，一句话]
- `protocol_version`: [从 protocol.md 读到的版本标识]
- `state_dependency`: no
- `files_read`: [你实际读取的文件列表]
- `files_not_read`: state/*, replay/*
```

## 验收标准

完成以下全部即为 pass：

| # | 条件 |
|---|------|
| 1 | 正确识别项目名 |
| 2 | 能用一句话复述 Sopify 定位 |
| 3 | 正确识别 plan 中 task-1 和 task-2 的状态 |
| 4 | 成功添加 task-3 并填写消费证据 |
| 5 | 未读取 state/ 或 replay/ 下的任何文件 |

## 非目标

- 不需要运行 runtime 或测试
- 不需要归档或 finalize
- 不需要回写 blueprint
- 不需要理解 runtime 内部架构
- 只需要证明：**仅靠文件协议，第二个消费者能找到并继续任务**
