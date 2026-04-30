---
plan_id: 20260416_blueprint_graphify_integration
feature_key: blueprint_enhancer_graphify
level: standard
lifecycle_state: active
knowledge_sync:
  project: review
  background: review
  design: review
  tasks: review
archive_ready: false
---

# 任务清单: Blueprint 可插拔增强架构 + Graphify 实现

## 当前切片边界

- 第一切片：Phase 0（增强器架构 + 配置）+ Phase 1（Graphify 增强器实现）
- 第二切片：Phase 2（blueprint 文件集成）+ Phase 3（plan 同步 + finalize 提示）

## Phase 0 — 增强器架构 + 配置

- [ ] 0.1 落地 graphify 依赖策略（已确认）
  - **定位**：graphify 是 optional enhancer dependency，不改 sopify stdlib_only 基线
  - **已确认的分层策略**：
    - 开发联调：`pip install -e /path/to/graphify && pip install graspologic`（editable + Leiden）
    - 团队/CI/正式环境：`pip install graphifyy[leiden]==0.4.16`（PyPI + Leiden，仅当不依赖本地未发布修复时）
  - sys.path 注入不作为正式接入路径
  - leiden extras 注意：实际依赖是 `graspologic`（不是 leidenalg），
    且限 `python_version < 3.13`。`pip install graphifyy[leiden]` 或 `pip install graspologic`
  - **两级可用性**：base 可用（无 leiden，fallback Louvain）vs 最佳效果（有 leiden）
    - `is_available()` 只检查 base 可用性，leiden 缺失不阻塞 enhancer 启用
  - **兼容性契约（两层分离）**：
    - runtime contract: sopify runtime 不依赖 graphify/leiden，不受 Python <3.13 限制
    - artifact generation contract: 生成 tracked report.md 的环境须 Python 3.11/3.12 + `graphifyy[leiden]==0.4.16`
    - CI 硬约束（不满足则 fail），本地软约束（允许 fallback，须标出 `cluster_backend=louvain`）
  - 确认后记录到 project.md 技术约定
  - `is_available()` 使用策略链检测，不硬绑分发名

- [ ] 0.2 新增 `installer/blueprint_enhancer.py` — 可插拔增强器基类
  - `BlueprintEnhancer` ABC：
    - `name: ClassVar[str]`（类级元数据，注册时零实例化）
    - `is_available()` classmethod（类级依赖检测）
    - `validate_enhancer_config(cfg)` classmethod（增强器私有键校验，默认 no-op）
    - `__init__(config)` 接收已验证的 enhancer config
    - `generate / update / render_auto_sections` 实例方法
  - `ensure_output_excluded(repo_root, output_dir)` — 自产物排除通用约定（默认 no-op，子类 override）
  - `render_auto_sections()` 返回 `dict[str, dict[str, str]]`（filename → section_id → content）
    - 同一增强器可在同一文件中写入多个 auto-section
  - `ENHANCER_REGISTRY` 注册表 + `register_enhancer` 装饰器（纯类注册，零实例化）
  - `EnhancerConfigError(ValueError)` — 独立于 `runtime.config.ConfigError`，避免反向依赖
  - `get_enabled_enhancers(config)` — 三级过滤：enabled → validate → is_available
    - 未知 enhancer + `enabled: true` → **raise EnhancerConfigError**（统一 contract）
    - 实例化延迟到所有类级检查通过之后
  - `inject_auto_sections(blueprint_dir, enhancer, sections)` 注入引擎
    - 按 `(filename, section_id)` 精确匹配
    - section_id 做 `re.escape()` 确保安全
    - 支持含连字符的 section-id
    - 正则兼容 `\r\n` 换行
    - 使用 replacement function 避免 content 中反斜杠被 re.sub 解释
    - 保留原始换行风格（`\r\n` 或 `\n`），避免行尾漂移
    - 内容边界用 `content.strip("\n")`（仅裁换行，保留有意缩进）
  - 验收：空注册表不崩溃 + 同文件多 section 正确注入 + 未知 enhancer raise

- [ ] 0.3 修改 `runtime/config.py` + `runtime/_models/core.py` — 配置链路闭环
  - `DEFAULT_CONFIG` 新增 `"blueprint_enhancers": {}`（稳定默认键）
  - `_ALLOWED_TOP_LEVEL` 加 `"blueprint_enhancers"`
  - `_validate_blueprint_enhancers()` — 公共层只校验 `enabled` 是 bool，不限制增强器名和其他子键
  - `_validate_config()` 中**无条件调用**（因 DEFAULT_CONFIG 保证此键必然存在）
  - `RuntimeConfig` 新增 `blueprint_enhancers: Mapping[str, Mapping[str, Any]]` 字段（末尾，default_factory=dict）
  - `load_runtime_config()` 构造时传入 `merged.get("blueprint_enhancers", {})`
  - 验收：`config.blueprint_enhancers["graphify"]["enabled"]` 可读取；空配不崩溃；非法值报错

  > **为什么改 RuntimeConfig**：编排脚本和 finalize 提示都需要读取此配置。
  > 如果绕过 RuntimeConfig 直接读 raw YAML，会和主配置链路分叉。

- [ ] 0.4 sopify.config.yaml 加配置
  ```yaml
  blueprint_enhancers:
    graphify:
      enabled: false
  ```

- [ ] 0.5 .gitignore 追加产物排除
  ```
  .sopify-skills/blueprint/graphify/graph.json
  .sopify-skills/blueprint/graphify/graph.html
  .sopify-skills/blueprint/graphify/.meta.json
  .sopify-skills/blueprint/graphify/.cache/
  ```

## Phase 1 — Graphify 增强器实现

- [ ] 1.1 新增 `installer/enhancers/graphify_enhancer.py`
  - `GraphifyEnhancer(BlueprintEnhancer)`
  - `name = "graphify"`（ClassVar，类级元数据）
  - `validate_enhancer_config()` classmethod：
    - 校验 `history_scan_depth`（正整数）
    - 校验未知私有键（当前仅定义 `history_scan_depth`，新增键须同步更新）
    - 校验失败 raise `EnhancerConfigError`
  - `is_available()` classmethod：策略链检测（pkg:graphifyy → pkg:graphify → import:graphify）
    - 不硬绑 PyPI 分发名，兼容 editable install / sys.path / PyPI
  - `generate()`:
    - `collect_files(repo_root)` → `list[Path]`
    - `extract(code_files)` → `dict{nodes, edges}`（批量 `list[Path]`）
    - `build_from_json(extraction)` → `nx.Graph`
    - 补充 plan/history .md 文档节点 → `_collect_plan_docs()` 返回 `(nodes, scan_meta)`
    - `cluster()` → `god_nodes()` → `surprising_connections()` → `suggest_questions()`
    - `_label_communities()` 生成社区可读标签
    - 持久化到 `blueprint/graphify/`，`scan_meta` 写入 `.meta.json`
  - `update()`:
    - `detect_incremental()` → `new_files` + `deleted_files`
    - .meta.json 缺失/损坏/版本变化 / graph.json 异常 → fallback generate()
  - `render_auto_sections()` → `{filename: {section_id: content}}`

- [ ] 1.2 实现 `_collect_plan_docs()` — Markdown 文档节点
  - 扫描 `plan/**/*.md` → `source_location: "L2"`（active plan）— 全量扫描
  - 扫描 `history/YYYY-MM/<plan_id>/` → `source_location: "L3"`（archived plan）— **策略性收敛**：
    - 收敛粒度为**具体归档 plan 目录**（非月份目录），按 plan 目录名倒序取最近 N 个
    - 排序依据：plan 目录名遵循 `YYYYMMDD_<slug>` 命名规范，字符串倒序 ≈ 时间倒序
    - 默认 `history_scan_depth=5`，可通过 enhancer config 覆盖
    - 截断信息写入 `scan_meta`（`history_truncated`, `history_total_plans`），落入 `.meta.json`
  - 返回 `tuple[list[dict], dict]`（节点列表 + 扫描元数据）
  - 不写死 "L1"，避免与 blueprint stable 层混淆
  - 本期只保证"入图可见"，不承诺文档间依赖推断

- [ ] 1.3 实现 `_label_communities()` — 社区可读标签
  - 基于社区内 degree 最高节点生成标签
  - 弱标签（degree ≤ 2）时回退到前两个代表节点名
  - 空社区防御

- [ ] 1.4 新增 `scripts/blueprint_enhance.py` — 编排脚本
  - `--only <name>` / `--list` / 默认全部
  - `--strict`：CI 模式，Leiden 不满足 → exit 1（自动检测 `CI` 环境变量作为 fallback）
  - 检查 scaffold 存在性
  - 捕获 `EnhancerConfigError` → 格式化用户可见错误 + exit 1（UX 闭环）
  - 协调 update → render_auto_sections → inject_auto_sections
  - **输出必须包含 `cluster_backend=leiden|louvain` 标识**
  - normal 模式下 Louvain fallback 输出警告，提示勿提交
  - strict 模式下 Louvain fallback 直接报错退出

- [ ] 1.5 .meta.json 自动管理 + graceful 降级
  - fail-open：任何异常回退全量重建
  - `.get()` 防御所有 graph.json 字段

- [ ] 1.6 实现 `_ensure_graphifyignore()` — 自产物排除（override `ensure_output_excluded`）
  - generate()/update() 开始前自动写入 `.graphifyignore` 排除规则
  - 排除 `blueprint/graphify/` 整个目录，防止自产物触发下轮增量检测
  - `.graphifyignore` 应 git tracked，团队共享
  - 后续 enhancer 复用基类约定，按自身工具链实现排除
  - 已有 `.graphifyignore` 时追加，不覆盖

  > **为什么需要这步**：`detect_incremental()` 扫描整个 repo（detect.py:337-360），
  > 如果不排除，上次生成的 `report.md` 会被识别为新变化，导致噪音循环。
  > graphify 已支持 `.graphifyignore` 过滤（detect.py:348）。

## Phase 2 — Blueprint 文件集成

- [ ] 2.1 background.md 加 auto-section
  ```markdown
  ## 项目结构概览
  <!-- graphify:auto:codebase-overview:start -->
  （graphify 自动生成）
  <!-- graphify:auto:codebase-overview:end -->
  ```

- [ ] 2.2 design.md 加 auto-section
  ```markdown
  ## 模块依赖图谱
  <!-- graphify:auto:architecture:start -->
  （graphify 自动生成）
  <!-- graphify:auto:architecture:end -->
  ```

- [ ] 2.3 扩展 `runtime/kb.py` — README 自动发现增强器产物
  - `_additional_blueprint_entries()` 增加 `blueprint/*/report.md` 子目录扫描
  - 不绑定增强器名

- [ ] 2.4 验证关闭时零影响 + 增删不互相影响

## Phase 3 — Plan 同步 + Archive 提示

- [ ] 3.1 验证 plan/history .md 入图（L2/L3 层级正确）

- [ ] 3.2 archive 触发机制（A + C-lite）
  - engine.py：archive_lifecycle 分支末尾，条件化 `notes.append("...")`
    - 判断口径：`config.blueprint_enhancers` 中有 `enabled: true` 的 enhancer
    - 不 import enhancer registry，不碰 graphify availability
  - handoff.py：`_collect_handoff_artifacts()` 在 `archive_lifecycle.archive_status == "completed"` 后补 artifact
    ```json
    {"blueprint_enhancer_refresh": {"recommended": true, "reason": "plan_finalized", "trigger": "enabled_enhancer_config_present", "command": "..."}}
    ```
  - notes 给人看，artifacts 给机器读（宿主按 `trigger` 字段分支处理）
  - runtime 不自动执行 enhancer（设计原则 6）

- [ ] 3.3 端到端验证
  - 创建 plan → run → L2 节点入图
  - 修改 plan → run → 增量更新
  - finalize → run → L2 节点消失、L3 节点出现
  - **验收 checklist**：
    - [ ] `report.md` 中出现 plan/ 下新增文件对应的节点名
    - [ ] `graph.json` 的 `nodes` 数组包含 L2 标记节点（`source_location: "L2"`）
    - [ ] 修改 plan 后 re-run，`.meta.json` 的 `generated_at` 时间戳更新且 `report.md` 内容变化
    - [ ] finalize 后 re-run，原 L2 节点消失、对应 history/ 路径出现为 L3
    - [ ] `cluster_backend` 输出与 CI 环境一致（均为 `leiden`）
    - [ ] `.graphifyignore` 包含 `blueprint/graphify/` 排除规则
    - [ ] 关闭 `graphify.enabled` 后 re-run，无报错且 report.md 不变

## Phase 后续

- [ ] 4.1 .md 文件间引用关系提取（Markdown 链接 → 图谱边）
- [ ] 4.2 deep mode（LLM 语义提取）评估
- [ ] 4.3 graph.html 嵌入 IDE 评估
- [ ] 4.4 enhancer freshness gate 评估
- [ ] 4.5 其他增强器候选评估

## 跨切片依赖

```
Phase 0  ──(gate)──→  Phase 1  ──(gate)──→  Phase 2  ──(gate)──→  Phase 3
  │                      │                      │
  │ 增强器架构 + 配置     │ Graphify 增强器       │ blueprint 集成
  │ → BlueprintEnhancer  │ → GraphifyEnhancer    │ → auto-section
  │ → config 父键         │ → _collect_plan_docs  │ → kb.py 发现
  │ → graphify 可检测    │ → _label_communities  │
  └──────────────────────┘                      └──────────────→ plan 同步
```

- Phase 0.1+0.2+0.3 阻塞 Phase 1
- Phase 0.4-0.5 可并行
- Phase 1.1-1.6 可并行
- Phase 2 依赖 Phase 1
- Phase 3 依赖 Phase 2（3.1 依赖 1.2）
