---
plan_id: 20260429_legacy_feature_cleanup
feature_key: legacy_feature_cleanup
level: standard
lifecycle_state: archived
knowledge_sync:
  project: skip
  background: skip
  design: skip
  tasks: skip
archive_ready: true
plan_status: completed
---

# Tasks: Legacy Feature Cleanup

## 任务列表

### T1: legacy consult override 删除

- [x] T1-A: 审计 router 中的 legacy consult override 调用链
- [x] T1-B: 审计 engine 中 plan materialization bypass 分支的独立性
- [x] T1-C: 删除 router callsite 与 classifier
- [x] T1-D: 删除 engine callsite
- [x] T1-E: 删除或改写关联测试
- [x] T1-F: 保留 `analysis_only_no_write_brake` 与共享 helper

### T2: model compare 功能面移除

- [x] T2-A: 列出所有 compare runtime / decision / prompt / config 引用
- [x] T2-B: 删除 model compare runtime helper
- [x] T2-C: 删除 compare decision helper
- [x] T2-D: 清理 router / engine / gate / handoff / output / replay / manifest 引用
- [x] T2-E: 删除内置 model-compare skill package 与双语子 Skill 文档
- [x] T2-F: 清理 host prompt、README、design-rules 中的命令与配置说明
- [x] T2-G: 清理 `multi_model` runtime config 字段、默认值与校验
- [x] T2-H: 更新 eval gate、SLO、baseline 与同步脚本
- [x] T2-I: 删除旧行为断言，保留已移除行为的 guard 测试

### T3: 验证与收口

- [x] T3-A: 运行残留引用扫描
- [x] T3-B: 运行 compileall
- [x] T3-C: 运行聚焦测试
- [x] T3-D: 运行 git diff --check
- [x] T3-E: 运行全量测试
- [x] T3-F: 最终确认后已完成本方案包归档

## 收口说明

- 本包不补 CrossReview 替代口径。
- 本包不展开 prompt governance。
- `.sopify-skills/blueprint/design.md` 与 `20260429_host_prompt_governance` 中的并行编辑由用户保留，本包不覆盖。
