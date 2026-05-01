# ADR 索引

Architecture Decision Records for Sopify.

本文是 ADR 编号的唯一 canonical registry。旧 `20260424_lightweight_pluggable_architecture` 总纲已删除，证据留在 git history；本表保留 ADR-001..020 的编号连续性和当前归宿，避免后续 plan 复用旧编号或回退到旧总纲。

## Numbering Policy

- ADR-001..020 是旧总纲时代的保留编号，不得复用为新含义。
- 只有 `文件` 列指向实体文件的 ADR 才是当前 canonical entity。
- `absorbed` 表示结论已并入 `blueprint/design.md` 或现有实体 ADR，不再单独维护正文。
- `historical` 表示只保留历史证据，不作为新方案默认依据。
- 后续新增 ADR 使用 ADR-021 起，除非是在实现分支中正式实体化本表已有的 deferred / absorbed 主题。

## Complete Registry

| ADR | 标题 | 当前状态 | 当前归宿 | 文件 |
|-----|------|----------|----------|------|
| ADR-001 | 不 pipeline 化 engine | historical / runtime-mode constraint | 被 ADR-016 的 Runtime-optional 视角吸收；engine 不再作为 core 边界来源 | - |
| ADR-002 | Checkpoint: LLM 判断 + Python/Validator 持久化 | absorbed | 被 ADR-017 与 `blueprint/design.md` Checkpoint 契约吸收；checkpoint 收敛为 `clarification` / `decision` | - |
| ADR-003 | `skill.yaml` v2 向后兼容 | scoped / skill package | 保留在 skill package 标准化语境；不作为当前 core baseline 实体 | - |
| ADR-004 | CrossReview 分阶段验证 (advisory → runtime) | scoped / plugin | CrossReview 作为质量验证参考实现；不并入 Sopify core ADR 实体 | - |
| ADR-005 | 旧总纲残余吸收策略 | historical | 旧纲吸收已完成；证据留 git history | - |
| ADR-006 | 子任务包方向一致性约束 | absorbed | 被 `blueprint/tasks.md` 执行优先级、Plan intake checklist 与 `blueprint/design.md` 硬约束吸收 | - |
| ADR-007 | 多宿主原生支持 | absorbed | 被 ADR-016 Protocol-first 与 `blueprint/design.md` Surface-shared / Wire-composable 吸收 | - |
| ADR-008 | Plugin 策展集成模型 | deferred / scoped | 后续插件体系或 skill package 分支再实体化；当前不进入 core baseline | - |
| ADR-009 | `pipeline_hooks` 默认关闭 | historical / frozen | hooks 不作为当前主线；如恢复需新 ADR 或实现分支重审 | - |
| ADR-010 | 不允许外部 plugin 引入新 checkpoint 类型 | superseded | 被 `blueprint/design.md` Checkpoint target: 2 取代，旧 4 类型口径不再合法化 | - |
| ADR-011 | CR verdict → checkpoint 映射 + review-fix 循环限制 | scoped / plugin | CrossReview runtime 模式冻结；后续若恢复 runtime 集成再实体化 | - |
| ADR-012 | Minimal Core Boundary — 4 层架构 | superseded | 被 ADR-016 的 Protocol / Validator / Runtime 三层定位取代 | - |
| ADR-013 | Product Positioning: Evidence & Authorization Layer | canonical | Sopify 产品定位与生存性测试 | [ADR-013.md](ADR-013.md) |
| ADR-014 | Skill / Plugin Permission Tiers | absorbed | 权限语义收敛到 ADR-017 side-effect authorization 与 `blueprint/design.md` hard constraints；skill 权限细节保留在专项 skill 文档 | - |
| ADR-015 | State Write Ownership | absorbed | 被 ADR-016 Validator 边界与 `blueprint/design.md` Core State Files / Runtime state scope 吸收 | - |
| ADR-016 | Protocol-first / Runtime-optional | canonical | 顶层架构战略 | [ADR-016.md](ADR-016.md) |
| ADR-017 | Action/Effect Boundary | canonical | ActionProposal → Validator → deterministic action → receipt/handoff | [ADR-017.md](ADR-017.md) |
| ADR-018 | Legacy Surface Retirement | absorbed / governance | 被 `blueprint/design.md` 硬约束、削减预算表和后续 cleanup 分支约束吸收；不得复用为 P1 subject-binding 编号 | - |
| ADR-019 | Payload Bundle Distribution — Thin-Stub + Centralized Runtime | implemented / historical invariant | 已实现的分发不变量；后续改动必须显式重审，但当前不新增实体 | - |
| ADR-020 | Sopify Core = 轻量内核 + 可外部化组件生态 | absorbed | 被 ADR-013 产品定位与 ADR-016 Protocol-first / Runtime-optional 吸收；保留外部化三条件：至少 2 个非 Sopify 消费方、稳定 JSON contract、可独立 eval | - |

## Canonical Entity Files

| ADR | 标题 | 状态 | 文件 |
|-----|------|------|------|
| ADR-013 | Product Positioning: Evidence & Authorization Layer | 已确认 | [ADR-013.md](ADR-013.md) |
| ADR-016 | Protocol-first / Runtime-optional | 已确认 | [ADR-016.md](ADR-016.md) |
| ADR-017 | Action/Effect Boundary | P0 完成，持续扩展 | [ADR-017.md](ADR-017.md) |

---

> Blueprint `design.md` 底部的 ADR 索引表只列 canonical entities；本文件保留完整编号 registry。
