# 变更提案: Sopify 适配 Trae CN 宿主

## 需求背景

Sopify 当前支持两个深度验证宿主：Claude Code (`~/.claude/`) 和 Codex (`~/.codex/`)。两者共享同一套安装、诊断、运行时架构，通过 `HostAdapter + HostCapability + HostRegistration` 三层抽象实现宿主解耦。

这次方案的目标不是泛化支持“所有 Trae 发行形态”，而是优先接入 **Trae CN（国内版）**。原因有两个：

1. 当前可验证的全局用户规则目录证据来自 Trae CN 社区，路径是 `~/.trae-cn/user_rules/`
2. 现有 Phase 0 手工验证跑通的是 Trae CN 中项目级 `.trae/rules/` 与 `.trae/skills/` 注入，可证明项目级能力存在，但不能外推出国际版全局目录就是 `~/.trae/rules/`

因此，v1 必须把“Trae CN 全局宿主接入”和“项目级 `.trae/*` overlay”分开看待。

### Trae CN 平台特征

Trae CN 是一个基于 VS Code 架构的 AI IDE，当前与 Sopify 适配直接相关的能力如下：

| 维度 | 能力 |
|------|------|
| **全局配置根** | `~/.trae-cn/` |
| **全局用户规则目录** | `~/.trae-cn/user_rules/` |
| **全局技能目录** | `~/.trae-cn/skills/` |
| **项目规则目录** | `<project>/.trae/rules/` |
| **项目技能目录** | `<project>/.trae/skills/` |
| **规则系统** | Markdown 文件，支持 `alwaysApply` 等 frontmatter；全局与项目是两套作用域 |
| **技能系统** | `SKILL.md` 目录树，可被 Trae CN 发现和加载 |
| **终端工具** | Builder 模式可分配 terminal 工具 |
| **SOLO 模式** | `/Plan` + `/Spec`，产出 `.trae/specs/` |

### 与现有宿主的关键差异

```
                    Claude Code              Codex                 Trae CN
                    ──────────────────────    ─────────────────     ─────────────────────────────
全局根              ~/.claude/               ~/.codex/             ~/.trae-cn/
全局入口提示文件    CLAUDE.md                AGENTS.md             user_rules/*.md
全局技能目录        ~/.claude/skills/        ~/.codex/skills/      ~/.trae-cn/skills/
项目级规则/技能     .claude/skills/          .codex/skills/        .trae/rules/ + .trae/skills/
payload 安装目标    ~/.claude/sopify/        ~/.codex/sopify/      ~/.trae-cn/sopify/
默认工作模型        全局宿主安装             全局宿主安装          全局宿主安装（v1）+
                                                                   项目级 overlay（后续）
```

**关键结论**：Sopify v1 接入的应是 Trae CN 的 **全局宿主路径**，不是项目级 `.trae/*` overlay。项目级 `.trae/*` 目前只作为已验证的可行性证据和后续增强方向保留。

## 变更内容

本方案将 Trae CN 作为第三个宿主接入 Sopify 的多宿主架构，范围包括：

1. **宿主注册层**：新增 `installer/hosts/trae_cn.py`，注册 `host_id="trae-cn"`
2. **提示层源码**：新建 `TraeCn/Skills/{CN,EN}/` 目录树，生成 Trae CN 原生格式的全局用户规则和技能文件
3. **提示层同步策略**：明确 `Codex/Skills/{CN,EN}` 为 canonical source，`Claude/Skills/*` 与 `TraeCn/Skills/*` 均通过脚本同步/校验生成
4. **安装流程适配**：`install_host_assets()` 支持 `user_rules/sopify.md` 这类子目录 header 写入
5. **诊断面（status/doctor）**：自动覆盖，并与当前 `feature/ingress-proof-doctor` 基线保持一致
6. **运行时配置接入**：Trae CN 宿主通过显式 `--global-config ~/.trae-cn/sopify.config.yaml` 接入；v1 不改 `runtime/config.py` 默认 fallback
7. **release/doc/version 自动化**：将 Trae CN 纳入 sync、version consistency、README link check、release hook 管理范围

本方案**不包含**：

- 国际版 `trae` 宿主（`~/.trae/rules/`）接入
- 项目级 `<project>/.trae/` 自动初始化或覆盖
- Trae CN 自定义智能体（UI 层，不在 installer 范围）
- Trae SOLO Spec 与 Sopify plan 的互通
- 宿主感知的 `runtime/config.py` fallback 探测
- 修改现有 Claude/Codex 的任何行为 contract

## 影响范围

- 模块:
  - `installer/hosts/trae_cn.py`（新增）
  - `installer/hosts/__init__.py`（注册）
  - `installer/hosts/base.py`（小幅适配：header 子目录创建）
  - `installer/inspection.py`（不改主逻辑，注册即自动覆盖）
  - `TraeCn/Skills/`（新增目录树和源码）
  - `scripts/sync-skills.sh` / `scripts/check-skills-sync.sh`
  - `scripts/release-sync.sh` / `scripts/check-version-consistency.sh` / `scripts/check-readme-links.py`
  - `.githooks/pre-commit`
  - `tests/test_installer_status_doctor.py`
  - `tests/test_installer.py`
  - `tests/test_release_hooks.py`
  - `tests/test_check_readme_links.py`
- 文档:
  - `README.md` / `README.zh-CN.md` 补充 Trae CN 宿主支持说明与文档入口
  - `CONTRIBUTING.md` / `CONTRIBUTING_CN.md` 如有必要补充多宿主同步约定

## 约束条件

1. **不改现有 Claude/Codex 行为**：所有改动对现有两个宿主零影响
2. **初始 support_tier = EXPERIMENTAL**：在完成 smoke 验证前不升级
3. **Trae CN 终端可用性为硬前提**：若 Builder 模式不分配 terminal 工具，runtime 层不可用，整个方案降级为 prompt-only
4. **v1 只管理全局 `~/.trae-cn/*`**：不接管、不覆盖、不诊断 repo 内 `<project>/.trae/*`
5. **不改 `.sopify-runtime/` 语义**：workspace bundle 目录不变，项目侧仍只放 `.sopify-runtime/` 与 `.sopify-skills/`
6. **YAML frontmatter 必须带 `alwaysApply: true`**：全局用户规则入口文件必须自动生效
7. **单一 source of truth**：`Codex/Skills/{CN,EN}` 继续作为 prompt-layer canonical source，Trae CN 不能手工长期维护独立第三套
8. **单一 config 策略**：v1 统一通过 Trae CN 宿主桥接显式传 `--global-config ~/.trae-cn/sopify.config.yaml`
9. **工程验收以可观测 smoke 为准**：Phase 0 手工探索记录只作为 feasibility evidence，不替代 Phase 3 的工程验收
10. **基线按 `feature/ingress-proof-doctor` 对齐**：Trae CN 的 doctor / status / tests 直接包含 `workspace_ingress_proof`

## 风险评估

| 风险 | 等级 | 影响 | 缓解 |
|------|------|------|------|
| Trae CN Builder 不分配 terminal | 高 | runtime gate/engine 完全不可用 | Phase 0 先手动验证；降级为 prompt-only |
| 把项目级 `.trae/*` 误当成全局宿主路径 | 高 | 安装目标错误，status/doctor 误判 | v1 只管理 `~/.trae-cn/*`；项目 `.trae/*` 明确排除 |
| Trae CN prompt 资源树手维护漂移 | 高 | Codex / Claude / TraeCn 三套内容版本不一致 | 固定 `Codex` 为 source of truth；TraeCn/Claude 一律走同步脚本与校验 |
| release/doc 自动化遗漏 Trae CN | 高 | release hook 与版本校验对 Trae CN 失明，产物可漂移 | 接入时同步改造 release-sync / version check / README link check / hook |
| user_rules 全量注入 token 预算 | 中 | 入口规则长期占用上下文 | 核心约束放 `user_rules/sopify.md`，实操指令放 `skills` 按需加载 |
| Trae CN skills 按需加载准确率 | 中 | 某些场景下 skill 不被加载 | 在入口规则里保证关键 skill 可被发现，并补真实 IDE smoke |
| `header_filename` 含路径分隔符 | 低 | 安装时目标目录可能不存在 | `install_host_assets` 增加 `parent.mkdir()` |

## 先决条件

- [ ] 目标宿主拍板为 **Trae CN**，不是国际版 `trae`
- [ ] v1 范围拍板：只管理 `~/.trae-cn/*`，不自动写 `<project>/.trae/*`
- [ ] `runtime/config.py` 不进入 v1；Trae CN 改走显式 `global_config_path`
- [ ] prompt-layer source of truth 拍板：`Codex` canonical，`Claude/TraeCn` 走同步脚本与校验
- [ ] release/doc/version 自动化接入 Trae CN 的范围拍板，不后置
- [ ] 实施基线改为 `feature/ingress-proof-doctor`，不再从 `feature/context-v1-scope-finalize` 起分支
