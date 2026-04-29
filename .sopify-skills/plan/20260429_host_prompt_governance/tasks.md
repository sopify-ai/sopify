# Tasks: Host Prompt Governance

> **定位更新**：后续收口包，不再作为当前排头兵。
> **前置依赖**：`20260429_standard-archive-finalize-archive-checkpoint` 完成，并且 archive/finalize 新 contract 已稳定。
> **建议顺序**：在 `existing plan` 显式主体绑定与 `checkpoint local actions` 方向评估完成后，再进入本包实现。

## 任务列表

### T1: 审计与原则沉淀

- [ ] T1-A: 逐行标注 CLAUDE.md CN 每个区块（重复 / 唯一事实源 / 可迁移 / 可删除）
- [ ] T1-B: 量化三重重复：gate protocol 3 处 ~100 行 → 1 处 ~20 行
- [ ] T1-C: 撰写 `.sopify-skills/blueprint/prompt-governance.md`（3 条底层哲学 + 7 条工程原则 + Karpathy 删除测试引用）
- [ ] T1-D: 用户确认原则

### T2: 渐进式披露重构

- [ ] T2-A: 设计 Layer 0/1/2/3 分界（行数预算 + 触发条件）
- [ ] T2-B: 重构 Claude CN prompt Layer 0（目标 ≤120 行）
- [ ] T2-C: Layer 1 gate contract 抽取（~40 行独立块）
- [ ] T2-D: Layer 2 phase execution 抽取（~30 行/阶段）
- [ ] T2-E: Layer 3 reference 迁移至 project.md / README
- [ ] T2-F: 跑全量测试确认 runtime 行为不变
- [ ] T2-G: 1 轮 dogfood 验证

### T3: 单源生成

- [ ] T3-A: 设计模板结构 (base.template.md + partials + vars)
- [ ] T3-B: 实现 `build-prompts.py`（模板 + 变量 → 4 variant）
- [ ] T3-C: 验证生成结果与手工版功能等价
- [ ] T3-D: 集成到 pre-commit hook（替代当前 sync check）
- [ ] T3-E: 跑全量测试确认

### T4: 准入脚本

- [ ] T4-A: 实现 `check-prompt-governance.py`（行数上限 + 重复检测 + 必需区块）
- [ ] T4-B: 集成到 pre-commit hook
- [ ] T4-C: 跑全量测试确认

### T5: 收口

- [ ] T5-A: 更新 blueprint README 焦点
- [ ] T5-B: 更新总纲 tasks.md 状态
- [ ] T5-C: 归档至 history

## 依赖关系

```
T1 → T2 → T3 → T4 → T5
T1-D (用户确认) gates T2
legacy_feature_cleanup.~compare 删除 gates T2-B (去掉 multi_model.* 配置行)
20260429_standard-archive-finalize-archive-checkpoint 完成 gates T1/T2 的正式启动
existing plan 显式主体绑定方向评估完成 gates T1/T2 的优先级确认
checkpoint local actions 方向评估完成 gates T1/T2 的优先级确认
```
