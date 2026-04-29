# Design: Legacy Feature Cleanup

> **定位**：`20260424_lightweight_pluggable_architecture` 总纲下的独立清理包。
> **前置**：`20260428_action_proposal_boundary` P0 thin slice 已完成，ActionProposal validator 已成为正式保护层。
> **结果**：清除被 ActionProposal 替代的 legacy consult override 路径，并移除已废弃的 model compare 功能面。

---

## 执行结果

### 1. Legacy consult override 清理

已删除内容：

- `runtime/router.py` 中的 explain-only override classifier 与 classify chain callsite
- `runtime/engine.py` 中只服务该 legacy route 的 plan materialization bypass
- 关联的 router / sample invariant / engine 测试断言

保留内容：

- `analysis_only_no_write_brake` 继续作为信号层保留
- `_is_consultation()` 与其他共享 helper 不在本包调整
- legacy host 迁移风险不再额外补安全网；当前线上使用方已升级 ActionProposal path

### 2. Model compare 功能面移除

已删除内容：

- `scripts/model_compare_runtime.py`
- `runtime/compare_decision.py`
- `runtime/builtin_skill_packages/model-compare/skill.yaml`
- Codex / Claude 双语 `model-compare` 子 Skill 文档

已清理引用：

- router / engine / gate / handoff / output / replay / manifest / builtin catalog
- runtime config 中的 `multi_model` 字段、默认值与校验
- README、Codex / Claude host prompt、design-rules 中的命令与配置说明
- eval gate、SLO、baseline 与同步脚本中的 compare 专项入口
- 对应测试改为验证功能已移除或删除旧行为断言

---

## 当前行为

- `~go`、`~go plan`、`~go exec`、`~go finalize` 仍是命令前缀入口。
- `~compare` 不再是命令前缀；输入会按普通文本进入现有路由。
- `multi_model.*` 不再是 runtime config 字段。
- 内置 Skill manifest 不再包含 `model-compare`。
- 本方案包已归档到 `history/2026-04/20260429_legacy_feature_cleanup/`。

## 不做

- 不引入 CrossReview 替代口径。
- 不做 prompt governance；该议题已放入独立 follow-up。
- 不在本包中继续展开归档后的跨 session 阻塞复盘；该分析单独处理。
