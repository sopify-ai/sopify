# ADR 索引

Architecture Decision Records for Sopify.

## Canonical Entities

| ADR | 标题 | 状态 | 文件 |
|-----|------|------|------|
| ADR-013 | Product Positioning: Workflow Control Plane | 已确认 | [ADR-013.md](ADR-013.md) |
| ADR-016 | Protocol-first / Runtime-optional | 已确认 | [ADR-016.md](ADR-016.md) |
| ADR-017 | Action/Effect Boundary | P0 完成，持续扩展 | [ADR-017.md](ADR-017.md) |

## Absorbed (无独立实体)

以下 ADR 编号曾在旧总纲中引用（旧总纲已删除，证据留 git history），其核心内容已并入 blueprint 削减目标和约束。当前不设独立实体文件。

| ADR | 原始含义 | 归并去向 |
|-----|---------|---------|
| ADR-014 | Checkpoint / host-action governance | `blueprint/design.md` 削减预算表 + 硬约束 |
| ADR-015 | Route convergence | `blueprint/design.md` 目标 Route Families |

## Deferred (待实体化)

以下 ADR 编号对应后续实现分支，实体文件随各自分支创建。旧总纲中的相关讨论可通过 git history 追溯。

| ADR | 对应实现分支 | 预期时机 |
|-----|-------------|---------|
| ADR-018 | existing_plan_subject_binding (P1) | P1 分支 |
| ADR-019 | host_prompt_governance (P4) | 远期 |
| ADR-020 | runtime_surface_cleanup (P3) | 远期 |

---

> 本索引维护在 `.sopify-skills/blueprint/architecture-decision-records/README.md`，是 ADR 编号的唯一 canonical 索引。
> Blueprint `design.md` 底部的 ADR 索引表只列 canonical entities。
