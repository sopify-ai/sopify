# Tasks: Subject Identity & Existing Plan Binding（最小核）

## 任务列表

### T1: Protocol — execute_existing_plan Subject Binding 升格 ✅

- [x] T1-A: 将 protocol.md §7 execute_existing_plan 小节的 UNSTABLE/draft 标注移除，升格为 normative
- [x] T1-B: 使用 RFC 2119 表述规范化可携带规则（MUST / MUST NOT / SHOULD）
- [x] T1-C: 明确 subject_type="plan" 为 normative，其余值域保留 draft

### T2: Protocol — Legacy Mapping 文档规则 ✅

- [x] T2-A: 在 protocol.md §7 添加 informative 注释，说明现役路径与 canonical subject 的映射关系
- [x] T2-B: 明确 current_plan → subject_ref 的映射规则（不实现，只定义规则）
- [x] T2-C: 明确 review_or_execute_plan 是 legacy composite，P3a 收口（引用 design.md sunset 表）

### T3: Validator — execute_existing_plan Subject Admission ✅

- [x] T3-A: ActionProposal 增加 `plan_subject` 字段块（仅含 subject_ref + revision_digest）
- [x] T3-B: gate schema 暴露 plan_subject 字段块给宿主
- [x] T3-C: Validator execute_existing_plan 分支校验 plan_subject 存在
- [x] T3-D: 校验 subject_ref 指向的 plan 文件存在
- [x] T3-E: 校验 revision_digest 一致性（SHA-256 vs plan.md 实际内容）
- [x] T3-F: 缺少 plan_subject / subject_ref 不存在 / digest 不匹配 → **reject**（不降级 consult）
- [x] T3-G: subject_ref 边界防线：拒绝绝对路径 / `..` 穿越 / 非 `.sopify-skills/plan/` 前缀
- [x] T3-H: Engine 显式消费 DECISION_REJECT，阻断执行链路

### T4: Validator 测试 ✅

- [x] T4-A: 缺少 subject_ref 的 execute_existing_plan → rejected
- [x] T4-B: revision_digest 不匹配 → rejected
- [x] T4-C: subject_ref 指向不存在的 plan → rejected
- [x] T4-D: 正确 subject_ref + revision_digest → admitted
- [x] T4-E: 绝对路径 subject_ref → rejected
- [x] T4-F: `..` 穿越 subject_ref → rejected
- [x] T4-G: 非 plan 前缀 subject_ref → rejected
- [x] T4-H: Engine 级集成测试（reject 阻断 / digest 错误阻断 / valid 放行）

### T5: 蓝图回写

- [x] T5-A: 更新 blueprint/README.md 焦点区块
- [x] T5-B: 更新 tasks.md P1 状态
- [x] T5-C: CHANGELOG.md 由 pre-commit hook 自动维护，不需手工更新

## 已知语义债

- **DECISION_REJECT surface**：validator 返回 reject 后，engine 阻断执行但对外 surface 仍表现为 consult route。需 P1.5 扩展 handoff/gate 白名单以支持独立 reject surface。

## 附带修复

- **workspace root normalization**：gate 层在 preflight 解析出 activation_root 后，将 downstream workspace 归一到 activation_root，修复 .sopify-skills 误写到子目录的 bug。

