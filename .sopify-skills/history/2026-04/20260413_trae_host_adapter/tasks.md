---
plan_id: 20260413_trae_host_adapter
feature_key: trae_host_adapter
level: standard
lifecycle_state: archived
knowledge_sync:
  project: skip
  background: skip
  design: skip
  tasks: skip
archive_ready: true
---

# 任务清单: Sopify 适配 Trae CN 宿主

## 当前切片边界

- 第一切片与 README / CONTRIBUTING 口径调整原子绑定
- 第一切片执行范围：`1.1-1.6 + 2.8-2.11` ✅ 已完成
- 第二切片执行范围：`1.7-1.9 + 2.4-2.7 + 2.12-2.13` ✅ 已完成
- 下一步：Phase 3（真实 IDE smoke + tier 升级）

## Phase 0 — 范围澄清与可行性记录

- [x] 0.1 在 Trae CN IDE 中手动创建 `<project>/.trae/rules/sopify.md`（alwaysApply: true），验证项目级规则被读取
  - 验证记录：rules 文件在新建对话中自动注入，`sopify-rule-check` 触发返回 `[RULE_LOADED]`
- [x] 0.2 在 Trae CN IDE 中手动创建 `<project>/.trae/skills/sopify/analyze/SKILL.md`，验证项目级技能被发现和加载
  - 验证记录：向 Builder 请求代码复杂度分析，返回 `[SKILL_LOADED:sopify-test-skill]`
- [x] 0.3 在 Trae CN Builder 模式中验证 terminal 工具可执行 `python3 scripts/runtime_gate.py enter`
  - 验证记录：`python3 scripts/runtime_gate.py enter --request "测试"` 返回 `status: ready`
- [x] 0.4 确认 `<project>/.trae/rules/sopify.md` 的 `alwaysApply` 生效方式
  - 验证记录：项目级 rules 在新对话无触发词时直接生效
- [x] 0.5 记录 Phase 0 结论：当前手工验证证明的是 **项目级 `.trae/*` 注入可行**
  - 验证记录：该结论不能外推出全局用户规则目录就是 `~/.trae/rules/`
- [x] 0.6 记录 Trae CN 全局宿主路径证据
  - 用户规则目录：`~/.trae-cn/user_rules/`
  - 全局技能目录：`~/.trae-cn/skills/`
  - v1 目标宿主明确为 `trae-cn`

**Phase 0 说明**：本阶段只提供 feasibility evidence 和宿主范围澄清，不替代工程验收；最终是否可升 tier 以后续自动化测试 + 真实 Trae CN IDE smoke 为准。

## Phase 1 — 最小适配

### 1A. 宿主注册

- [x] 1.1 新建 `installer/hosts/trae_cn.py`
  - 定义 `TRAE_CN_ADAPTER`：`host_name="trae-cn"`, `source_dirname="TraeCn"`, `destination_dirname=".trae-cn"`, `header_filename="user_rules/sopify.md"`
  - 定义 `TRAE_CN_CAPABILITY`：`support_tier=EXPERIMENTAL`, `install_enabled=True`
  - declared_features：`PROMPT_INSTALL, PAYLOAD_INSTALL, WORKSPACE_BOOTSTRAP, RUNTIME_GATE, PREFERENCES_PRELOAD, HANDOFF_FIRST`
  - doctor_checks 直接包含：`workspace_ingress_proof`
  - verified_features 初始只放 `PROMPT_INSTALL + PAYLOAD_INSTALL`
  - 定义 `TRAE_CN_HOST = HostRegistration(adapter=TRAE_CN_ADAPTER, capability=TRAE_CN_CAPABILITY)`

- [x] 1.2 在 `installer/hosts/__init__.py` 注册 `TRAE_CN_HOST`
  - import `TRAE_CN_ADAPTER, TRAE_CN_HOST` from `.trae_cn`
  - 添加 `TRAE_CN_HOST.capability.host_id: TRAE_CN_HOST`

### 1B. 安装流程适配

- [x] 1.3 在 `installer/hosts/base.py` 的 `install_host_assets` 中添加子目录创建
  - `header_destination.parent.mkdir(parents=True, exist_ok=True)`
  - 验证对 Claude/Codex 无影响

### 1C. 提示层源码

- [x] 1.4 创建 `TraeCn/Skills/CN/user_rules/sopify.md`
  - YAML frontmatter：`alwaysApply: true`
  - SOPIFY_VERSION header
  - 内容基于 `Codex/Skills/CN/AGENTS.md`
  - 路径替换：`~/.codex/` → `~/.trae-cn/`

- [x] 1.5 创建 `TraeCn/Skills/CN/skills/sopify/`
  - 从 `Codex/Skills/CN/skills/sopify/` 复制所有 `SKILL.md`
  - 子目录：`analyze / design / develop / kb / templates / model-compare / workflow-learning`

- [x] 1.6 创建 `TraeCn/Skills/EN/`
  - 同 CN 结构，基于 `Codex/Skills/EN/` 对应文件
  - 同样进行 `~/.codex/` → `~/.trae-cn/` 路径替换

### 1D. prompt-layer source of truth / sync

- [x] 1.7 明确并落地 canonical source
  - `Codex/Skills/{CN,EN}` 作为 canonical source
  - `Claude/Skills/*` 与 `TraeCn/Skills/*` 视为 generated mirrors

- [x] 1.8 改造 `scripts/sync-skills.sh`
  - 在现有 `Codex -> Claude` 同步基础上，增加 `Codex -> TraeCn`
  - header 路径替换覆盖 `~/.codex/` → `~/.trae-cn/`
  - 输出 `user_rules/sopify.md` 与 `skills/sopify/*`
  - 新增 `render_trae_cn_header()` + `sync_trae_cn_lang()`

- [x] 1.9 改造 `scripts/check-skills-sync.sh`
  - 校验 Trae CN 镜像是否与 canonical source 一致
  - 校验 header 路径替换结果与目标文件布局
  - 新增 `render_expected_trae_cn_header()` + `check_trae_cn_lang()`

- [ ] 1.10 明确 runtime config v1 策略
  - 不修改 `runtime/config.py`
  - Trae CN 宿主桥接统一显式传入 `--global-config-path ~/.trae-cn/sopify.config.yaml`
  - 方案文档和实现口径保持一致

- [ ] 1.11 固化作用域边界
  - v1 只管理 `~/.trae-cn/*`
  - 不自动创建、不覆盖 `<project>/.trae/*`

## Phase 2 — Install + Diagnostics + Automation 验证

### 2A. 安装验证

- [ ] 2.1 执行 `python3 scripts/install_sopify.py --target trae-cn:zh-CN` 验证安装流程
  - 确认 `~/.trae-cn/user_rules/sopify.md` 被正确写入
  - 确认 `~/.trae-cn/skills/sopify/` 目录结构完整
  - 确认 `~/.trae-cn/sopify/payload-manifest.json` 被正确写入
  - 确认 `~/.trae-cn/sopify/bundles/` 被正确创建
  - 确认 `~/.trae-cn/sopify/helpers/bootstrap_workspace.py` 被正确写入
  - 确认 installer 不会创建 `<project>/.trae/*`

### 2B. 诊断面验证

- [ ] 2.2 `sopify status` 展示 `trae-cn` host entry
  - host_id = `trae-cn`
  - support_tier = `experimental`
  - `state.installed / state.configured / state.workspace_bundle_healthy` 正确

- [ ] 2.3 `sopify doctor` 展示 `trae-cn` 的 checks
  - `host_prompt_present`
  - `payload_present`
  - `payload_bundle_resolution`
  - `workspace_bundle_manifest`
  - `workspace_ingress_proof`

### 2C. release / doc / version 自动化接入

- [x] 2.4 改造 `scripts/release-sync.sh`
  - 确认 release-sync.sh 更新 Codex version → sync-skills.sh 已自动传播到 TraeCn
  - 无需额外改动，版本通过 sync 管线传播

- [x] 2.5 改造 `scripts/check-version-consistency.sh`
  - 将 Trae CN header 纳入版本一致性检查
  - 版本 mismatch 时对 `trae-cn` 给出明确报错
  - 添加 TRAE_CN_CN / TRAE_CN_EN 到 required_files 和 header_versions

- [x] 2.6 改造 `scripts/check-readme-links.py`
  - 将 Trae CN 文档入口/版本头纳入公共文档校验
  - 保证 README/贡献文档中新增的 Trae CN 链接可校验
  - 补充 EXPECTED_LEVEL2_SECTIONS: "What You Get After Install" / "安装后你会得到什么"

- [x] 2.7 改造 `.githooks/pre-commit`
  - 将 Trae CN prompt-layer 产物加入 release snapshot 与 `git add` 管理范围
  - 保持 release hook 对受管文件集的原子回滚语义
  - 三处更新: managed_paths / is_release_relevant_file / git add

### 2D. 测试补充

- [x] 2.8 在 `tests/test_installer_status_doctor.py` 中补充 Trae CN host 断言
  - `test_registry_returns_complete_capabilities_for_declared_hosts` 验证 `trae-cn` capability
  - `test_installable_hosts_only_return_install_enabled_entries` 断言集合扩展为 `{"codex", "claude", "trae-cn"}`
  - 新增 `test_trae_cn_status_and_doctor_with_workspace`
  - 补充 `workspace_ingress_proof` 断言

- [x] 2.9 在 `tests/test_installer.py` 中新增 Trae CN 安装回归
  - 验证安装流程可写入 `user_rules/sopify.md`
  - 验证 `--target trae-cn:zh-CN` 的 prompt/payload 安装路径正确

- [x] 2.10 新增 `test_trae_cn_header_subdirectory_created`
  - `install_host_assets` 后 `~/.trae-cn/user_rules/sopify.md` 存在
  - 文件以 `---\nalwaysApply: true\n---` 开头

- [x] 2.11 新增 `test_trae_cn_install_does_not_affect_claude_codex`
  - 安装 `trae-cn` 前后，claude/codex 的 expected_paths 不变

- [x] 2.12 在 `tests/test_release_hooks.py` 中补充 Trae CN 受管文件集断言
  - fixture 初始化 `TraeCn` 目录
  - release hook snapshot / restore / add 覆盖 Trae CN 产物
  - 新增 `_minimal_trae_cn_rules()` helper + version propagation assertion

- [x] 2.13 在 `tests/test_check_readme_links.py` 中补充 Trae CN 文档/版本头断言
  - README 新增的 Trae CN 链接可被校验
  - Trae CN 版本头缺失或不一致时会失败
  - 新增 `_minimal_trae_cn_rules()` helper + TraeCn fixture in `_configure_module` / `_init_fixture`

## Phase 3 — 真实 Trae CN IDE Smoke + Tier 升级

### 3A. 安装到真实环境

- [ ] 3.1 安装到 `~/.trae-cn/`
  ```bash
  python3 scripts/install_sopify.py --target trae-cn:zh-CN
  ```
  验收：
  - [ ] `~/.trae-cn/user_rules/sopify.md` 存在，以 `---\nalwaysApply: true\n---` 开头
  - [ ] `~/.trae-cn/skills/sopify/` 完整（analyze / design / develop / kb / templates / model-compare / workflow-learning）
  - [ ] `~/.trae-cn/sopify/payload-manifest.json` 存在
  - [ ] `~/.trae-cn/sopify/bundles/<version>/manifest.json` 存在
  - [ ] `~/.trae-cn/sopify/helpers/bootstrap_workspace.py` 存在

### 3B. IDE Smoke 验证（人工操作）

- [ ] 3.2 全局 user_rules 注入验证
  - 打开空项目（无 `.trae/rules/sopify.md`），新建 Builder 对话
  - 发送任意消息，观察 Sopify 系统提示是否自动注入
  验收（可复查证据，非经验性 probe）：
  - [ ] `alwaysApply: true` 使全局 user_rules 在无触发词时自动生效
  - [ ] Sopify 版本头、A1-A4 提示段均出现在对话上下文中
  - [ ] 确认使用的是 `~/.trae-cn/user_rules/sopify.md` 而非项目级 `.trae/rules/*`
  - [ ] 证据留存：IDE 对话截图（含版本头 + 提示段），或导出的 IDE 日志片段
  > 注意：此前 tasks.md 中使用的 `sopify-rule-check -> [RULE_LOADED]` 不是仓库代码定义的稳定观测点，
  > 而是手工验证时的经验性回显标记，不适合用作正式验收 contract。验收以上述可复查证据为准。

- [ ] 3.3 全局 skills 发现与加载验证
  - 在 Builder 对话中请求 "分析当前代码复杂度"（触发 analyze skill）
  验收（可复查证据，非经验性 probe）：
  - [ ] 至少一个 skill 被 IDE 发现并加载
  - [ ] skill 内容来自 `~/.trae-cn/skills/sopify/` 而非项目级 `.trae/skills/`
  - [ ] 证据留存：IDE 对话截图（显示 skill 被调用），或 Builder 对话中实际注入的 prompt 片段
  > 注意：此前使用的 `[SKILL_LOADED:sopify-test-skill]` 同样不是仓库内定义的观测点。

- [ ] 3.4 Runtime gate 端到端验证
  ```bash
  python3 ~/.trae-cn/sopify/bundles/<version>/scripts/runtime_gate.py enter \
    --workspace-root . \
    --request "测试 runtime gate" \
    --global-config-path ~/.trae-cn/sopify.config.yaml \
    --host-id trae-cn \
    --format json
  ```
  > 参数契约已对齐 `scripts/runtime_gate.py` build_parser()（L24-85）：
  > `--global-config-path`(L35), `--host-id`(L62), `--format json|text`(L82) 均为稳定 CLI 参数。
  验收：
  - [ ] 返回 `"status": "ready"` 且 `"gate_passed": true`
  - [ ] `.sopify-skills/state/current_gate_receipt.json` 被正确写入
  - [ ] handoff contract 包含 `entry_guard` 字段

- [ ] 3.5 显式 global config 接入策略验证
  - 确认宿主桥接显式传入 `--global-config-path ~/.trae-cn/sopify.config.yaml`
  - 明确本轮不修改 `runtime/config.py`

- [ ] 3.6 项目 `.trae/*` 隔离验证
  - 在已有 `.trae/rules/sopify.md` 的项目中执行安装
  验收：
  - [ ] 安装前后项目 `.trae/` 目录内容不变
  - [ ] `sopify doctor` 不报告项目级 `.trae/` 的问题

### 3C. Bundle Smoke + Doctor 独立验证

- [ ] 3.7a Bundle 安装（含 workspace）
  ```bash
  python3 scripts/install_sopify.py --target trae-cn:zh-CN --workspace /path/to/workspace
  ```
  验收：
  - [ ] 安装命令成功完成，摘要中无 FAIL 状态
  - [ ] 复用 `run_bundle_smoke_check` 现有逻辑

- [ ] 3.7b Doctor 独立核对（安装后单独运行）
  ```bash
  python3 scripts/sopify_doctor.py --workspace-root /path/to/workspace --format json
  ```
  > 入口为 `scripts/sopify_doctor.py`（L18-23），底层调用 `build_doctor_payload(home_root=..., workspace_root=...)`。
  > `--home-root` 缺省时取 `Path.home()`，对本机环境通常无需显式传入。
  验收（以 doctor JSON 结构化输出为准，逐项核对）：
  - [ ] `host_prompt_present`: status = `pass`
  - [ ] `payload_present`: status = `pass`
  - [ ] `workspace_bundle_manifest`: status = `pass`
  - [ ] `workspace_ingress_proof`: status = `pass`
  - [ ] `workspace_handoff_first`: status = `pass`
  - [ ] `workspace_preferences_preload`: status = `pass`
  - [ ] `bundle_smoke`: status = `pass`
  > 注意：`install_sopify.py` 的安装摘要（`distribution.py:142 render_distribution_result`）是人类可读文本，
  > 不是 machine contract。doctor 核对必须以独立调用的结构化输出为准，不能以"安装时顺带看摘要"替代。

### 3D. 工具映射确认

- [ ] 3.8 确认 Builder 工具映射
  - 在 Trae CN Builder 对话中确认实际可用的工具名（文件读取 / 搜索 / 编辑 / Terminal）
  - 评估 `user_rules/sopify.md` 的 `A2 | 工具映射` 段是否需要 TraeCn 专属映射
  - 若需要，补充 `Codex -> TraeCn` 的 host-specific transform 规则，避免后续 sync 覆盖

### 3E. Capability 元数据收口（代码变更，依赖 3A-3D 全部通过）

- [ ] 3.9 升级 `installer/hosts/trae_cn.py`
  Tier 判定逻辑（收紧版）：
  - 3.2-3.4 全通过 + 3.7b doctor 7 项全 pass → `BASELINE_SUPPORTED`
  - 部分通过 → 保持 `EXPERIMENTAL`（记录未通过项）
  - 3.2 未通过（全局注入失败）→ 保持 `EXPERIMENTAL`
  代码变更（BASELINE_SUPPORTED 场景）：
  - `support_tier=SupportTier.BASELINE_SUPPORTED`
  - `verified_features` 补齐: `WORKSPACE_BOOTSTRAP, RUNTIME_GATE, PREFERENCES_PRELOAD, HANDOFF_FIRST, SMOKE_VERIFIED`
  - 注意：`HOST_BRIDGE` 仍不加入（v1 scope 排除）
  > DEEP_VERIFIED 升级条件（留给后续轮次）：
  > Codex/Claude 的 DEEP_VERIFIED 包含 `HOST_BRIDGE` verified（8 项 verified_features），
  > 代表长期稳定的宿主桥接验证经验。TraeCn v1 不含 HOST_BRIDGE，首轮 IDE smoke 不足以
  > 等价声称"与 Codex/Claude 齐平"。DEEP_VERIFIED 需要第二轮更完整的宿主使用验证，
  > 或团队内部明确定义"不含 HOST_BRIDGE 的 DEEP_VERIFIED"为可接受语义。

- [ ] 3.10 更新测试断言
  - `tests/test_installer_status_doctor.py:120`: `"experimental"` → `"baseline_supported"`
  - `tests/test_installer_status_doctor.py:159`: `"experimental"` → `"baseline_supported"`

- [ ] 3.11 更新 README host matrix
  - `README.md` L91: Experimental → Baseline supported, Notes → "Install + smoke verified; HOST_BRIDGE pending"
  - `README.zh-CN.md` L91: Experimental → Baseline supported, 说明 → "安装与 smoke 已验证；HOST_BRIDGE 待验证"

- [ ] 3.12 工具映射代码更新（如 3.8 发现需要）
  - 更新 `TraeCn/Skills/{CN,EN}/user_rules/sopify.md` 的 `A2 | 工具映射` 段
  - 如需 TraeCn 专属映射，在 `sync-skills.sh` 中添加 host-specific transform

- [ ] 3.13 提交 + 验证
  ```bash
  git checkout -b feature/trae-cn-phase3-tier-upgrade feature/trae-cn-host-adapter-slice2
  # 修改 3.9-3.12 的文件
  python3 -m unittest tests.test_installer_status_doctor -v
  bash scripts/check-version-consistency.sh
  python3 scripts/check-readme-links.py
  ```

- [ ] 3.14 更新 tasks.md 标记 Phase 3 完成

## Phase 后续 — 可选增强

- [ ] 4.0 确认 `trae-cn:en-US` 的长期产品语义
  - 触发条件：国际版 `trae` 宿主的 Phase 0 路径证据确认，且 `trae` 的 install target / 语言策略已拍板后
  - 评估 `trae-cn:en-US` 是否保持现状，或进入 deprecate 路径
  - 若进入 deprecate 路径，需单独规划 remove 时机，并同步改造 installer 语言矩阵、README 与测试
- [ ] 4.1 评估国际版 `trae` 宿主（`~/.trae/rules/`）是否作为独立 `HostRegistration` 立项
- [ ] 4.2 评估项目级 `<project>/.trae/*` overlay 初始化能力
- [ ] 4.3 评估 Trae SOLO Spec (`.trae/specs/`) 与 Sopify plan 的互通价值
- [ ] 4.4 评估 Trae CN 自定义智能体 `@Sopify` 的用户体验价值
- [ ] 4.5 评估宿主感知的 `runtime/config.py` fallback 探测是否值得独立立项

## 跨切片依赖

```
Phase 0  ──(gate)──→  Phase 1  ──(gate)──→  Phase 2  ──(gate)──→  Phase 3
  │                      │                      │
  │ 宿主范围澄清         │ 注册 + 源码          │ install + automation + test
  │ → Trae CN only       │ → 可独立 PR          │ → 可独立 PR
  └──────────────────────┘                      └──────────────────→ tier 评审
```

- Phase 0 与 Phase 1 无代码依赖，Phase 0 负责澄清宿主范围
- Phase 1A/1B/1C/1D 可并行
- Phase 2A 依赖 Phase 1 全部完成
- Phase 2C/2D 的自动化与测试代码可与 Phase 1 并行编写
- Phase 3 依赖 Phase 2 验收通过
- 建议从 `feature/ingress-proof-doctor` 切 `feature/trae-cn-host-adapter`
