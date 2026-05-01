# Convention Mode Smoke Test

title: Convention 模式跨宿主最小 roundtrip 验证
scope: 验证 Host B 仅通过文件协议（不依赖 state/ 或 runtime）能读取 Host A 产出并继续工作
approach: Host A 产出 light plan + 完成 1 个 task → Host B 读取 blueprint + plan → Host B 继续 pending task

## Tasks

- [x] task-1: 在 blueprint/ 下建立最小上下文（project.md + background.md + design.md + protocol.md）— Host A 已完成，文件已存在且已 commit
- [x] task-2: Host B 读取 project.md 和 blueprint/，正确识别项目名和定位，然后继续本 task — 将本 task 标为 done 并在下方记录消费证据
- [x] task-3: 真实第二宿主验证 — 读取 project.md + blueprint/，确认 Convention 模式可消费

## Host B 消费指引

Host B（任意宿主/模型/脚本），请按以下步骤操作：

1. 读取 `.sopify-skills/project.md`，确认项目名
2. 读取 `.sopify-skills/blueprint/background.md`，用一句话复述 Sopify 的核心定位
3. 读取本文件，确认 task-1 已完成、task-2 待执行
4. 将 task-2 标为 `[x]`，并在下方 `## Host B 消费证据` 区域填写：
   - `host_identity`: 你是谁（宿主名 + 模型名）
   - `project_name`: 从 project.md 读到的项目名
   - `sopify_positioning`: 从 background.md 读到的 Sopify 定位（一句话）
   - `state_dependency`: 是否读取了 state/ 目录下的任何文件（应为 no）

## Host B 消费证据

- `host_identity`: Copilot CLI agent / Claude Sonnet
- `project_name`: sopify-skills
- `sopify_positioning`: Sopify 是跨宿主 AI 工作流的证据与授权层，将外部生产、验证、知识工具的结果收敛成可恢复、可审计、可授权的机器事实。
- `state_dependency`: no

## Host C 消费证据

- `host_identity`: Codex / GPT-5
- `project_name`: sopify-skills
- `sopify_positioning`: Sopify 是跨宿主 AI 工作流的证据与授权层，将外部生产、验证、知识工具的结果收敛成可恢复、可审计、可授权的机器事实。
- `protocol_version`: Protocol v0
- `state_dependency`: no
- `files_read`: .sopify-skills/project.md, .sopify-skills/blueprint/background.md, .sopify-skills/blueprint/protocol.md, .sopify-skills/plan/20260501_convention_smoke/plan.md
- `files_not_read`: state/*, replay/*
