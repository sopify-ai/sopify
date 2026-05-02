# Blueprint Truth Cutover — 方案设计

## 方案目标

让 blueprint 成为产品合法边界和预算的唯一定义源。Runtime 降为：

- **迁移层** — 临时桥接旧状态，目标是尽快删除
- **参考实现** — 证明 protocol / validator / receipt 跑通的一种做法，不是产品定义

原则已写入 `blueprint/design.md` §三层定位。

## 立即生效的稳定约束

| 约束 | 来源 |
|------|------|
| 产品分层：Core / Default Workflow / Plugins | design.md §产品分层 |
| 架构分层：Protocol / Validator / Runtime | ADR-016 |
| Checkpoint canonical = 2（clarification, decision） | design.md §削减目标 |
| Host action canonical = 5 | design.md §削减目标 |
| Route family canonical = 6 | design.md §削减目标 |
| Core state files canonical = 6 | design.md §削减目标 |
| Validator 不执行，只授权 | ADR-017 |
| Prompt 不定义 machine truth | design.md §硬约束 |
| Runtime 是参考实现，不是 truth source | ADR-016 |

## 允许留白的未定细节

以下不阻塞 cutover，后续通过 smoke / validator 逐步收敛：

- protocol §6 Integration Contract 具体字段（当前 informative/draft）
- protocol §7 Multi-host review wire contract（当前 informative/draft）
- knowledge_sync receipt 级证据格式
- session GC 具体策略
- Default Workflow review 停点细则

## 允许的破坏

| 允许 | 说明 |
|------|------|
| 删 legacy route / alias | 旧 18 种 route 压向 6 family |
| 删 legacy host action | 旧 13 种压向 5 canonical |
| 删 legacy checkpoint type | 旧 5 种压向 2 canonical |
| 删旧 state 投影 / compat 文件 | core state 压向 6 authoritative |
| 打断旧 session/state 兼容 | 尚未进入生产消费周期，兼容约束最小 |
| 废弃部分 runtime 表面 API | runtime 不再是公共契约面 |
| 高级能力临时退化或不可用 | 先证骨架，再补功能 |

## 伪切换红线（不该做的事）

- ❌ 只改文档不删代码 — 那是"愿景更新"不是 cutover
- ❌ 旧逻辑全部保留、仅加 `if new_mode` 分支 — 那是膨胀不是迁移
- ❌ 等 protocol §6/§7 draft 完全定型再动手 — 骨架已够，不用等细节
- ❌ 把 runtime 当产品主体继续精修 — cutover 的前提是 runtime 失去中心地位
- ❌ 在旧 route/action/state 上新增功能 — 冻结旧面扩展
- ❌ 名义上删面但继承旧面控制语义 — 复用 transport label 时不借原面的 guard/projection/allowed_actions；删旧面意味着旧面的消费面也一并清除，不是换皮

## 非目标

本轮不做：

- 完整 Validator 实现
- 完整 multi-host review 正式化
- 所有 draft contract 细节定稿
- Runtime 行数达到 <20K 最终目标（方向对即可，不设一次性硬目标）

## 执行节奏

1. **先删低耦合错面** — 用 Wave 1 建立“删旧 → 同步 prompt/smoke/bundle → 验收”的固定节奏，但不把它当作 cutover 主体
2. **再收中度控制面** — Wave 2 先压 route alias 与 host-facing truth，使 consult proof 能在 canonical 面上跑通
3. **最后拆重子系统** — Wave 3 不并做；先单拆 `plan_proposal`，再拆 `execution_confirm`

## 实施分层

本轮 cutover 不是单纯的五个核心模块瘦身，而是一次跨三层的控制平面改造。评审与任务拆分都应按层看，而不是按“删几个 legacy 名词”看。

| 层 | 职责 | 当前典型落点 |
|----|------|-------------|
| 状态解析层 | 解析当前该信哪份 state / checkpoint / handoff truth | `context_snapshot.py`, `context_recovery.py`, `checkpoint_request.py` |
| 控制平面 | 路由、状态推进、fail-close、恢复策略、planning stop point | `engine.py`, `router.py`, `deterministic_guard.py`, `gate.py`, `entry_guard.py`, `plan_orchestrator.py`；声明式合同：`contracts/decision_tables.yaml`(49 legacy refs), `contracts/failure_recovery_table.yaml`(18 legacy refs) |
| 呈现层 | host-facing truth、用户输出、action projection | `handoff.py`, `output.py`, `action_projection.py`, `_models/handoff.py` |
| 测试层 | 旧面断言、fixture、case matrix | 18 test files (~481 legacy refs) + 3 fixture YAML (~80 refs) |

### 分层约束

- **Wave 1** 只允许删低耦合 legacy action，并同步 prompt-layer / smoke / bundle；目的是建立工作节奏，不是宣称完成 cutover
  - 测试同步范围：涉及 `continue_host_quick_fix` / `host_replay_bridge_required` / `archive_completed` 的断言
- **Wave 2 拆为 4 个子波 + proof**，不一次性做。原因：route alias 收敛 735+ refs 和 host action 删减是不同维度的工作，一次性做等于控制平面重写
  - **2a**（`continue_host_workflow` → `continue_host_develop`）：类似 Wave 1 手法，17 refs，低风险先做
  - **2b**（`archive_review` receipt 化）：从 host action 退出，30 refs。Wave 1 已把 archive_completed 吸入 archive_review，本波让 archive_review 自身退出 host action 空间
  - **2c**（`develop_checkpoint` → `develop_callback` 完整重命名）：26 个活跃文件。**关键决策：保留 helper 能力，完整退出 checkpoint/route 概念**——从文件名、脚本名、manifest key（含 `host_bridge_status`/`entry_guard` section）、entry guard、policy/source/truth id、prompt-layer、smoke/sync/test/infra 全部重命名为 `develop_callback`。不兼容、不加 legacy alias、不扩语义。`checkpoint_kind` (decision|clarification)、`checkpoint_request.py`、`DEVELOP_RESUME_*`、route names、`phase == "develop"` 不改
  - **2d**（route family 真收敛）：精确审计 route_name literal 后，对 router + engine + handoff + output + guard 做真收敛——内部主链路开始使用 6 canonical family，旧 alias 只允许在入口解析边界短期存在。**2d 独占 engine.py**，完成后才开 3a/3b。不删 plan_proposal/execution_confirm 语义，只挂到 canonical family 下
  - 测试同步范围：每个子波各自同步涉及的断言；`test_runtime_router.py`(52) 主要受 2d 影响
  - Contract YAML：当前 `decision_tables.yaml` 和 `failure_recovery_table.yaml` 对 Wave 2 三个目标引用为 0（已审计）
  - 精确审计原则：2d 启动前区分 route_name literal/comparison/dispatch/persisted contract vs 变量名/注释/概念词，不把后者算进工作量
- **Wave 2 proof 绑定 2d 完成态**：`consult` route 的 Protocol → Validator → Receipt proof 作为 Wave 2 的验收项；要求输出包含 `route_family=consult`
  - Proof 前置断言：`consult` 不经过 `plan_proposal` / `execution_confirm` 路径（已验证：router 中 consult 走 `_is_consultation` → `route_name="consult"`，不触发 plan_proposal / execution_confirm 分支）
- **Wave 2 验收标准**：新链路和 prompt 只消费 family/canonical action，不是"源码里看不到旧 route 字符串"
- **Wave 3a** 先单拆 `plan_proposal`：目标是一并折叠 `current_plan_proposal.json`、`confirm_plan_package`、`plan_proposal_pending`
  - 测试同步范围：`test_context_v1_scope.py`(47)、`test_runtime_engine.py`(大量 plan_proposal 断言)、`test_runtime_sample_invariant_gate.py`(37)、`fixtures/context_fail_close_contract.yaml`(45)、`fixtures/sample_invariant_gate_matrix.yaml`(26)
  - Contract YAML：`decision_tables.yaml` 中 `confirm_plan_package` / `current_plan_proposal` 全部条目（~30+）
- **Wave 3b** 再拆 `execution_confirm`：目标是一并折叠 `confirm_execute`、`execution_confirm_pending` 与相关 execution confirmation proof surface
  - 测试同步范围：`test_runtime_engine.py`(剩余 execution_confirm 断言)、`test_runtime_decision.py`(部分)、`test_runtime_state.py`(17)、`fixtures/fail_close_case_matrix.yaml`(9)
  - Contract YAML：`decision_tables.yaml` / `failure_recovery_table.yaml` 中 `confirm_execute` 全部条目
- 每一波都必须同步更新 `Codex/Skills/{CN,EN}/AGENTS.md`、`scripts/check-prompt-runtime-gate-smoke.py`、`scripts/sync-runtime-assets.sh` 等消费面；它们不是收尾附属品，而是 cutover 完成态的一部分

### Wave 2c 命名映射表

| 旧 | 新 | 说明 |
|----|-----|------|
| `runtime/develop_checkpoint.py` | `runtime/develop_callback.py` | 模块文件 |
| `scripts/develop_checkpoint_runtime.py` | `scripts/develop_callback_runtime.py` | CLI entry |
| `DevelopCheckpointError` | `DevelopCallbackError` | 异常类 |
| `submit_develop_checkpoint()` | `submit_develop_callback()` | 核心提交函数 |
| `is_develop_checkpoint_state()` | `is_develop_callback_state()` | 状态检测 |
| `inspect_develop_checkpoint_context()` | `inspect_develop_callback_context()` | 上下文检查 |
| `build_develop_checkpoint_request()` | `build_develop_callback_request()` | 请求构造 |
| `DEVELOP_CHECKPOINT_*` constants | `DEVELOP_CALLBACK_*` | 模块常量 |
| manifest `develop_checkpoint_callback` | `develop_callback` | capability key |
| manifest `develop_checkpoint_entry` | `develop_callback_entry` | limits key |
| manifest `develop_checkpoint_hosts` | `develop_callback_hosts` | limits key |
| entry_guard `develop_checkpoint_callback_required` | `develop_callback_required` | reason code |
| `policy_id: "develop_checkpoint_callback"` | `policy_id: "develop_callback"` | 策略标识 |
| `required_helper: "develop_checkpoint"` | `required_helper: "develop_callback"` | quality helper key |
| `requires_develop_checkpoint()` | `requires_develop_callback()` | checkpoint trigger predicate |
| manifest `host_bridge_status.develop_checkpoint` | `host_bridge_status.develop_callback` | bridge 状态 key |
| manifest `entry_guard.develop_checkpoint_callback_reason_code` | `entry_guard.develop_callback_reason_code` | entry_guard JSON key |

不改：`checkpoint_kind` (decision\|clarification)、`checkpoint_request.py`、`DEVELOP_RESUME_*`、route names (decision_pending/clarification_pending)、`phase == "develop"`

### Wave 2c 影响面（26 个活跃文件）

| 层 | 文件 | 改动性质 |
|----|------|---------|
| runtime | develop_checkpoint.py → develop_callback.py | 文件重命名 + 内部名全改 |
| runtime | develop_quality.py | `required_helper` key + `requires_develop_checkpoint` → `requires_develop_callback` |
| runtime | engine.py | import path + 2 个函数调用重命名（机械改，不碰 route family） |
| runtime | entry_guard.py | `DEVELOP_CHECKPOINT_ENTRY` + `develop_checkpoint_callback` reason code |
| runtime | manifest.py | `DEVELOP_CHECKPOINT_ENTRY` + 5 个 manifest contract keys（含 `host_bridge_status`、`entry_guard` section） |
| runtime | state_invariants.py | `develop_checkpoint_callback` → `develop_callback` |
| installer | bootstrap_workspace.py, payload.py, runtime_bundle.py, validate.py | 文件路径 + capability key |
| scripts | develop_checkpoint_runtime.py → develop_callback_runtime.py | 文件重命名 + import |
| scripts | check-runtime-smoke.sh | `DEVELOP_CHECKPOINT_ENTRY` 变量 |
| scripts | sync-runtime-assets.sh | 文件名引用 |
| prompt | CLAUDE.md ×2, AGENTS.md ×2 | 脚本名 + 契约名 |
| tests | test_installer.py, test_runtime_decision.py, test_runtime_engine.py | 函数名 + 脚本路径 + manifest key |
| tests | runtime_test_support.py | import path（2 处，不改 ImportError） |
| infra | .githooks/pre-commit | 脚本路径正则匹配（不改 release sync 触发失效） |
| docs | .sopify-skills/project.md | 运行时指引文档脚本路径 |
| docs | blueprint design.md, ADR-017.md | 迁移说明（保留旧名作历史记录可以接受） |
| release | CHANGELOG.md | release-sync 自动处理 |

### Wave 2c 执行原则

1. **不兼容、不加 legacy alias** — 旧脚本名/manifest key 直接消失，不保留 fallback
2. **engine.py 改动限于 import rename** — 不碰 route family 收敛（2d 范围）
3. **`develop_quality.py:79` 的 `required_helper` 是机器 key** — 需审计消费链（engine.py `_should_attempt_develop_checkpoint` 附近）一并改名
4. **冻结测试** — `develop_checkpoint` 不得出现在 CHECKPOINT_KINDS / route names；manifest 不再暴露 `develop_checkpoint_*` key
5. **blueprint docs 中 "旧类型 develop_checkpoint → develop callback source" 的历史迁移说明保留** — 那是迁移记录，不是运行面残留
