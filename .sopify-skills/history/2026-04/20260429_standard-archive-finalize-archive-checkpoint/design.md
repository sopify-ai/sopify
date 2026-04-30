# 技术设计: 显式主体与生命周期收敛（第一子切片）

## 设计结论

本包只做一件事：把 archive 生命周期从 runtime active-flow 中减重出来，收敛为 `ActionProposal(archive_plan)` 驱动的 deterministic protocol。Runtime 仍存在，但只负责校验结构化 action、调用薄 core、生成 handoff/output。

核心判断：

- archive 是协议资产治理，不是 develop 交互流程。
- archive 主体必须来自结构化 `ActionProposal.archive_subject` 或 validator 认可的唯一 current plan fallback；不得靠 raw request 正则或自然语言词表猜测。
- `~go finalize` 只是 host/CLI alias，必须先映射成同一个 `archive_plan` proposal；runtime 内部 route 统一为 `archive_lifecycle`。
- 本仓库没有线上用户，旧 `finalize_active` 链路、`finalize_status` 投影、`runtime/finalize.py` helper 层直接删除，不保留双轨兼容。

## ADR Guard

- 不新增 checkpoint type。
- 不新增第二套 archive route。
- 不新增自然语言归档白名单或 raw-text subject 正则。
- 不扩展通用 ActionProposal 框架；只给 `archive_plan` 增加最小 subject contract。
- 不把 diagnostics 演化成 migration/repair 平台；legacy/migration 默认返回 `archive_review`，除非后续显式 action 单独授权。
- 不新增通用 document framework；archive core 只接收已验证的结构化 subject。

## Deletion Policy

本包执行“一刀切切换”，不做线上兼容双轨：

- 遇到旧 `finalize_*` runtime 路径、raw-text archive subject 解析、pending archive 绕行、自动 migration/repair 补写等冗余代码，直接删除，不保留 wrapper/adapter。
- `~go finalize` 只能作为 host/CLI thin alias 映射到 `ActionProposal(archive_plan)`；runtime 内不得保留命令直达 archive 的第二入口。
- 测试按新协议重写；旧行为断言不迁就，不新增 legacy fallback 来让旧测试继续通过。
- 文档可以保留历史描述，但 active plan / blueprint 当前口径必须使用 `archive_plan` / `archive_lifecycle` / `archive_subject`。

## Archive Contract

Archive 固定拆成两层：

- `validator`: 负责 `validate + authorize + emit artifacts`，校验 `archive_plan` schema、side effect、subject 与 pending/state conflict；它不是 executor，不负责 plan materialization、知识写入、文件迁移、自动修复或 runtime 状态推进。
- `deterministic core`: 负责 `check + apply`，只读判断主体状态，并仅对 ready managed subject 写入 history、更新必要索引；当主体等于当前 global `current_plan` 时，额外清理对应 runtime state。

### ActionProposal Schema

`archive_plan` 的 proposal 必须把主体升格为硬 schema，runtime 不再从 `request_text` 补猜：

该字段是 `archive_plan` 的 action-specific payload，不代表扩展通用 ActionProposal 大 schema；通用层仍只定义 action/effect 边界，archive 主体字段只服务本 action。

```json
{
  "action_type": "archive_plan",
  "side_effect": "write_files",
  "confidence": "high",
  "evidence": ["user explicitly requested archive/finalize"],
  "archive_subject": {
    "ref_kind": "plan_id | path | current_plan",
    "ref_value": "20260429_example | .sopify-skills/plan/20260429_example | ",
    "source": "host_explicit | current_plan",
    "allow_current_plan_fallback": false
  }
}
```

字段约束：

- `archive_subject` 必填；裸 proposal 不允许进入 archive。
- `ref_kind=plan_id|path` 时，`ref_value` 必须非空，`source` 必须是 `host_explicit`。
- `ref_kind=current_plan` 时，`ref_value` 为空，`source` 必须是 `current_plan`，且 `allow_current_plan_fallback=true`。
- `allow_current_plan_fallback` 只允许 validator 在存在唯一 current plan 时使用；不得作为 engine 的二次推断开关。
- host 不提供 `managed/legacy/archived` 等事实分类；这些由 archive core 基于文件事实解析，validator 只传递结构化 subject，不负责把 subject 解析成 filesystem/business target。

主体解析只覆盖本包需要的最小集合：

1. host 将用户自然语言或命令 alias 映射为 `ActionProposal(action_type="archive_plan")`。
2. proposal 必须携带结构化 `archive_subject`：`plan_id`、`path`，或显式声明 `current_plan` fallback。
3. 未显式给出 `plan_id/path` 时，proposal 仍必须显式携带 `archive_subject.ref_kind=current_plan`；validator 只验证该 fallback 是否唯一成立，不负责发明 subject。
4. 主体已归档，返回 `already_archived`。
5. 主体缺失、歧义或目标冲突，fail-close，不写文件。

### Validator To Engine Contract

Validator 需要产出 engine 可直接传递给 archive core 的最小 artifacts：

```json
{
  "decision": "authorize",
  "resolved_action": "archive_plan",
  "resolved_side_effect": "write_files",
  "route_override": "archive_lifecycle",
  "artifacts": {
    "archive_subject": {
      "ref_kind": "plan_id | path | current_plan",
      "ref_value": "...",
      "source": "host_explicit | current_plan"
    }
  }
}
```

边界：

- Engine 只消费 `ValidationDecision.artifacts.archive_subject`，禁止读取 raw `request_text` 重新解析 subject。
- `ValidationDecision.artifacts.archive_subject` 表示已授权的结构化 subject，不表示已完成 plan/path 的 filesystem 或业务解析；真实 archive target 的确定性解析属于 `archive_lifecycle.resolve_archive_subject(...)`。
- Validator 校验失败时只产出 `blocking_reason` / `block_code`，或降级 consult；`archive_status` 由 archive core / handoff receipt 生成，不得让 engine 自行补猜。
- `archive_review` 是 handoff outcome，不是 ActionProposal 类型，也不是第二条 route。
- `~go finalize` 只允许存在于 host alias / CLI thin adapter；它的产物仍必须是同一个 `archive_plan` proposal。

## Implementation Boundary

`runtime/archive_lifecycle.py` 是 archive lifecycle 薄 core，暴露：

- `resolve_archive_subject(archive_subject, config, state_store?, current_plan?)`
- `check_archive_subject(subject, config)`
- `apply_archive_subject(subject, config, state_store?)`
- `archive_status_payload(...)`

`apply_archive_subject` 的 state 契约：

- `state_store is None`: 只写 history / index，不读写 runtime state。
- `state_store` 存在且主体等于当前 `state_store.current_plan`: 归档成功后清理 `current_run/current_plan`。
- `state_store` 存在但主体不是当前 plan: 不清理 runtime state。

Runtime cutover：

- Router 不再从 raw user input 正则解析 archive subject；`~go finalize` 仅可作为 alias 映射为 `archive_plan` proposal。
- Validator 接受最小 `archive_plan` proposal 后进入 `archive_lifecycle`；未通过校验则降级 consult 或返回 `archive_review`。
- Engine 只调用 archive core，不再把 archive 转成 `execution_confirm_pending / resume_active / review_or_execute_plan / state_conflict`。
- 归档非当前 active plan 时，Engine 保留现有 active handoff，并只写本次 archive 的持久 receipt；gate 仅在本次 route 为 `archive_lifecycle` 时读取该 receipt，不把它作为普通 active-flow truth。
- Handoff/output/replay 只暴露 `archive_lifecycle.archive_status`，不再暴露 `finalize_status`。
- `runtime/finalize.py` 删除；metadata 解析、history/index 写入只保留 archive apply 必需路径，不新增 migration/repair 平台。

## Legacy / Migration Boundary

Legacy / migration 在本包中默认不写入：

- legacy 或 metadata 不完整主体返回 `archive_review` + `archive_status=migration_required`
- host 可展示缺失事实，但不得由本包自动补写 plan metadata/front matter/background
- 如需自动 migration/repair，必须另开显式 action 与独立方案包

Legacy / migration 禁止：

- 语义润色
- 大规模内容重写
- 跨 plan 迁移
- 批量归档
- 隐式 apply

## Acceptance

必须成立：

- `archive_plan` proposal 经 validator 授权后进入 `archive_lifecycle`。
- `~go finalize` 不作为 runtime 内第二条归档入口，只能映射为同一个 `archive_plan` proposal。
- 旧内部 route 名 `finalize_active` 不存在。
- 旧 artifact 投影 `finalize_status` 不存在。
- 代码不再 import `runtime.finalize` 或调用 `finalize_plan`。
- managed active / inactive plan 可单轮 apply。
- legacy plan 不自动 migration/repair；返回 `migration_required/archive_review`。
- archive 其他 plan 不清理当前 unrelated runtime state。
- 自然语言只有经 host 映射为结构化 `archive_plan` 且 validator 通过后才触发 archive。

不在本包内解决：

- existing plan review/revise/execute 的通用显式主体解析。
- checkpoint pending 下 continue/revise/cancel 的统一 action schema。
- host prompt governance。

## Verification

原相关测试脚本必须通过：

```bash
python3 -m pytest tests/test_action_intent.py tests/test_runtime_router.py tests/test_runtime_engine.py tests/test_runtime_gate.py tests/test_runtime_plan_registry.py
```

额外覆盖：

```bash
python3 -m pytest tests/test_runtime_knowledge_layout.py
```
