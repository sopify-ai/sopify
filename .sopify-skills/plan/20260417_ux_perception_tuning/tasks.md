---
plan_id: 20260417_ux_perception_tuning
feature_key: ux_perception_tuning
level: standard
lifecycle_state: active
knowledge_sync:
  project: review
  background: review
  design: review
  tasks: review
archive_ready: false
---

# 任务清单: UX 感知层调优

## 当前切片边界

- 单切片交付：A（blueprint 可见化） + B（router 精度修正） + C（输出瘦身）
- 三项改动涉及文件不重叠，可并行开发

---

## A. Blueprint 贡献可见化

- [ ] A.1 在 `runtime/handoff.py` 新增 `_extract_blueprint_summary(config: RuntimeConfig)` 函数
  - 通过 `config.runtime_root` 定位 blueprint 目录
  - 检查 blueprint 目录下 project.md / design.md / background.md 存在性
  - 直接调用 `_detect_manifests(config.workspace_root)` 获取 manifest 文件名列表（7 次 `exists()`，无 I/O 成本）
  - 统计当前活跃 plan 数量
  - 返回 dict：`{has_blueprint, detected_manifests, has_design_decisions, active_plan_count}`

- [ ] A.2 在 `runtime/handoff.py:build_runtime_handoff()` (L86) 中调用 `_extract_blueprint_summary(config)`
  - 注入点在 `_collect_handoff_artifacts()` 返回之后、构建 `RuntimeHandoff` 之前
  - 注意：不在 `_collect_handoff_artifacts()` 内部调用，因为该函数签名不含 config.runtime_root 的 blueprint 路径信息
  - 非空时写入 `artifacts["blueprint_summary"]`
  - 空 blueprint → 不写入（不增加 handoff 体积）

- [ ] A.3 在 `runtime/output.py` 增加 blueprint 摘要渲染
  - 当 handoff artifacts 包含 `blueprint_summary` 且 `has_blueprint=True` 时
  - 渲染 1-3 行 emoji 标注的摘要（双语，跟随 config.language）
  - 空 blueprint 不输出

- [ ] A.4 在 `runtime/output.py` 增加首次 bootstrap 文件创建展示
  - 当 `KbArtifact.files` 非空时（表示首次创建了文件）
  - 注意：KbArtifact 只有 files（路径列表）/ mode / created_at，不携带 manifest 列表
  - 推荐只展示"已初始化 project.md / blueprint index"，不重复调用 manifest 检测
  - 仅首次创建时触发，后续 idempotent 的 bootstrap 不重复展示

- [ ] A.5 补充测试
  - 有 blueprint 时 handoff artifacts 包含 `blueprint_summary`
  - 空 blueprint 时不包含
  - output 层正确渲染中英文摘要
  - 首次 bootstrap 展示已初始化的文件列表（不含 manifest 细节）

## B. Router 精度修正

- [x] B.1 修正 `runtime/router.py:_is_consultation()` 的问句+动作词判断
  - 当前：有动作词就返回 False（不是咨询）
  - 修正：问句形式优先——问句前缀 + 动作词 = 仍是咨询
  - 需要精确定义"问句前缀"范围，避免"帮我改一下？"被误分到 consult
  - 可能需要窄化条件为：只有 `_QUESTION_PREFIXES` 开头（而非问号结尾）+ 动作词才算咨询

- [x] B.2 修正 `runtime/router.py:_estimate_complexity()` 的 complex 默认降级
  - 当前：`has_action && file_refs == 0` → complex
  - 修正：短文本（< _SHORT_REQUEST_THRESHOLD 字符）→ medium/light；长文本 → 保持 complex
  - `_SHORT_REQUEST_THRESHOLD` 初始值待测试确定（建议 80-120 字符区间）

- [x] B.3 通过现有测试回归验证修正不破坏已有路由行为
  - 运行 `tests/test_router*.py` 全量测试
  - 记录任何因修正导致的路由变化，逐条确认是否符合预期

- [x] B.4 补充边界测试
  - "删除操作会影响哪些表？" → consult（问关于动作的问题）
  - "帮我删除这个文件" → quick_fix/workflow（真正的修改请求）
  - "帮我加个日志" (短请求) → light_iterate 而非 workflow
  - "重构整个认证模块，把 session 改成 JWT" (长请求) → workflow

## C. Host-facing 输出瘦身

- [x] C.1 精简 `runtime/output.py` 中 consult/quick_fix 的 `_LABELS` 文案
  - 替换 `quick_fix_handoff`：从 "已识别 quick_fix 路由…" → 简洁的用户导向提示
  - 替换 `consult_handoff`：从 "已识别咨询问答路由…" → 简洁的用户导向提示
  - 对应修改 en-US 版本
  - 保持 `_LABELS` dict 结构不变

- [x] C.2 补充测试：验证修改后的输出内容正确渲染
  - 验证 consult/quick_fix 输出不再出现 `repo-local runtime`、`未执行代码修改`、`不生成正文回答`

### B/C 验证记录

- `python3 -m unittest tests.test_runtime_router`：通过，52 tests
- `python3 -m unittest discover`：通过，579 tests
