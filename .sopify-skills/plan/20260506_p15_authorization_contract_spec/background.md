# 变更提案: P1.5-B Authorization Contract Spec

## 需求背景

P1.5-C（Plan Materialization Auth Boundary）已完成（PR #23），建立了 `authorized_only` 授权模式。
但当前 runtime 只完成了"可否物化 plan"的授权边界——execute_existing_plan 的完整授权链路仍缺失。

ADR-017 定义了 ExecutionAuthorizationReceipt 的 8 个字段（plan_id / plan_path / plan_revision_digest / gate_status / action_proposal_id / authorization_source / fingerprint / authorized_at），标注为"方向"而非 normative。Blueprint tasks.md 将其提升为 P1.5 核心交付（方案包 B）。

### 现状精确表述

- **ExecutionAuthorizationReceipt 零实现**：runtime 中无此 class、无 receipt 生成、无 stale 检查（`grep` 确认）
- **现有 ExecutionGate 是相邻但不同的 gate truth**：`ExecutionGate`（`_models/core.py:178`）只判定"plan 可否继续"（gate_status / blocking_reason / plan_completion），不回答"谁授权了这次执行、基于哪个 revision"
- **PlanSubjectProposal 已有基础**（P1 交付）：`subject_ref` + `revision_digest` 已 normative，Validator admission 已实现
- **ActionProposal 无 ID 字段**：frozen dataclass 只有 action_type/side_effect/confidence/evidence + 可选 subjects，无 `action_proposal_id`

## 蓝图依据

- `blueprint/tasks.md:80-97` — P1.5-B 定义（5 个蓝图条目 #2/#3/#4/#5/#7）
- `blueprint/architecture-decision-records/ADR-017.md:32-55` — ExecutionAuthorizationReceipt 字段定义（标注"方向"）
- `blueprint/protocol.md:196-201` — Sopify 统一出口（receipt = plan identity + action identity + validator decision + fingerprint）
- `blueprint/protocol.md:231-245` — execute_existing_plan Subject Binding（normative，P1 升格）

## 触发事件

P1.5-C 完成后，按 tasks.md 串行依赖，B 的前置条件已满足。B 是 P1.5 的核心交付——不是附属切片。
