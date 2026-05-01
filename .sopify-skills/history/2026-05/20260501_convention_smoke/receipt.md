# Receipt: Convention Mode Smoke Test

outcome: passed
date: 2026-05-01

## Summary

Convention 模式跨宿主最小 roundtrip 验证通过。两个独立消费者（Host B: Claude Sonnet, Host C: Codex/GPT-5）仅通过文件协议（project.md + blueprint/ + plan/）成功识别项目、理解定位、找到活动任务并继续执行，未依赖 state/ 或 runtime。

## Key Decisions

1. protocol.md v0 正式纳入版本控制（commit 58ed5c0），作为 Convention 模式最小协议基线
2. Smoke scope 收窄为 "Host A write → Host B read + continue"，不含 finalize/archive/blueprint 回写
3. host_b_instructions.md 保留为可复用 smoke fixture，不作一次性文档删除

## Verification Evidence

| 消费者 | 宿主/模型 | 验收条件 | 结果 | Commit |
|--------|----------|---------|------|--------|
| Host B | Copilot CLI / Claude Sonnet | 5/5 pass | 同环境角色切换 (preliminary) | df7b4ab |
| Host C | Codex / GPT-5 | 5/5 pass | 真实第二宿主 (definitive) | e58d458 |

## Limitations

- Smoke 只验证了 Convention 模式最小消费性（read + continue），未验证 finalize / archive / blueprint 回写
- 未验证 Runtime 模式兼容性
- 未验证 multi-host review wire contract（protocol.md §7）
- 未建立 acceptance gate 自动化

## Impact on Blueprint

- tasks.md: Convention 模式跨宿主消费性已有初步证据，Protocol-first 战略方向获得实证支撑
- design.md: 无需更新（Convention 模式定义未变）
- protocol.md: v0 已 commit，内容未修改
