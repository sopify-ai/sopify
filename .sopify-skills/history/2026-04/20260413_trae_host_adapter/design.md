# 技术设计: Sopify 适配 Trae CN 宿主

## 技术方案

- 核心目标：将 `trae-cn` 作为第三个宿主接入 Sopify 多宿主架构，初始阶段达到 `EXPERIMENTAL` tier
- 本方案定位：可分阶段交付的 implementation plan；v1 只接入 Trae CN 全局宿主路径，不覆盖项目级 `.trae/*`

## 设计原则

1. **复用现有架构，不引入新抽象**
   通过现有 `HostAdapter + HostCapability + HostRegistration` 三层注册即可，不需要新的 interface。

2. **只做一个真实宿主**
   当前只接入 Trae CN；国际版 `trae` 后续作为独立 host 再评估，不在 v1 里混做路径分支。

3. **全局宿主安装优先**
   Trae CN v1 与 Codex/Claude 保持同一产品模型：全局宿主安装 + workspace `.sopify-runtime/` 按需 bootstrap。

4. **单一 config 策略，避免口径漂移**
   v1 不改 `runtime/config.py` 默认 fallback；Trae CN 一律通过桥接显式传入 `global_config_path`。

5. **多宿主资源必须可同步、可校验**
   Trae CN 接入不能形成第三套长期手维护 prompt 树，必须纳入统一 sync / check / release 流程。

## 当前交付切片说明

- 第一切片只落 `host registration + install_host_assets + TraeCn prompt-layer source tree + README/CONTRIBUTING + 核心测试`
- `sync-skills.sh / check-skills-sync.sh / release hook fixture` 调整后移到第二切片，避免首轮 review 同时覆盖生成链与 release 受管文件集

## 架构总览

### 多宿主注册架构

```
installer/hosts/
├── __init__.py          # _REGISTRATIONS dict — 注册中心
├── base.py              # HostAdapter + HostRegistration — 通用抽象
├── claude.py            # CLAUDE_HOST — Claude Code 宿主
├── codex.py             # CODEX_HOST — Codex 宿主
└── trae_cn.py           # TRAE_CN_HOST — Trae CN 宿主 (新增)
```

注册后自动被以下消费方覆盖，无需逐一改造：

```
inspect_all_hosts()      → status / doctor 诊断
iter_installable_hosts() → install CLI
iter_declared_hosts()    → capability registry
iter_host_registrations() → full registration enumeration
```

### 安装路径映射

```
仓库源码                                  安装目标                                 Trae CN 消费方式
──────────────────────────────            ───────────────────────────────          ───────────────────────
TraeCn/Skills/CN/user_rules/sopify.md →   ~/.trae-cn/user_rules/sopify.md         全局用户规则，全量注入
TraeCn/Skills/CN/skills/sopify/       →   ~/.trae-cn/skills/sopify/               全局技能，按需加载
(installer/payload.py)                →   ~/.trae-cn/sopify/                      payload + bootstrap
(installer/runtime_bundle.py)         →   <project>/.sopify-runtime/              workspace bundle (不变)
```

### 作用域边界

```
┌─────────────────────────────────────────────────────────────────┐
│  Trae CN                                                        │
│                                                                 │
│  全局宿主层（v1 受管）                                          │
│  ├── ~/.trae-cn/user_rules/sopify.md                            │
│  ├── ~/.trae-cn/skills/sopify/                                  │
│  └── ~/.trae-cn/sopify/                                         │
│                                                                 │
│  项目 overlay 层（v1 不受管）                                   │
│  ├── <project>/.trae/rules/                                     │
│  └── <project>/.trae/skills/                                    │
│                                                                 │
│  Sopify workspace 层（保持不变）                                │
│  ├── <project>/.sopify-runtime/                                 │
│  └── <project>/.sopify-skills/                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 详细设计

### 1. 宿主注册 — `installer/hosts/trae_cn.py`

```python
TRAE_CN_ADAPTER = HostAdapter(
    host_name="trae-cn",
    source_dirname="TraeCn",
    destination_dirname=".trae-cn",
    header_filename="user_rules/sopify.md",
)

TRAE_CN_CAPABILITY = HostCapability(
    host_id="trae-cn",
    support_tier=SupportTier.EXPERIMENTAL,
    install_enabled=True,
    declared_features=(
        FeatureId.PROMPT_INSTALL,
        FeatureId.PAYLOAD_INSTALL,
        FeatureId.WORKSPACE_BOOTSTRAP,
        FeatureId.RUNTIME_GATE,
        FeatureId.PREFERENCES_PRELOAD,
        FeatureId.HANDOFF_FIRST,
    ),
    verified_features=(
        FeatureId.PROMPT_INSTALL,
        FeatureId.PAYLOAD_INSTALL,
    ),
    entry_modes=(EntryMode.PROMPT_ONLY,),
    doctor_checks=(
        "host_prompt_present",
        "payload_present",
        "workspace_bundle_manifest",
        "workspace_ingress_proof",
        "workspace_handoff_first",
        "workspace_preferences_preload",
        "bundle_smoke",
    ),
    smoke_targets=("bundle_runtime_smoke",),
)

TRAE_CN_HOST = HostRegistration(adapter=TRAE_CN_ADAPTER, capability=TRAE_CN_CAPABILITY)
```

说明：

- `host_id` 与安装 target 统一使用 `trae-cn`
- `destination_dirname=".trae-cn"` 对齐 Trae CN 全局宿主根目录
- `header_filename="user_rules/sopify.md"` 对齐当前已确认的全局用户规则目录
- 当前基线已经包含 ingress proof，因此 `doctor_checks` 直接带上 `workspace_ingress_proof`

### 2. 安装流程适配 — `installer/hosts/base.py`

当前 `install_host_assets` 在写入 header 时只创建 `destination_root`，但不创建 header 文件的 parent 子目录。当 `header_filename` 含路径分隔符时（如 `user_rules/sopify.md`），需要确保 `~/.trae-cn/user_rules/` 存在。

改动范围：1 行

```python
header_destination = destination_root / adapter.header_filename
header_destination.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(header_source, header_destination)
```

对 Claude/Codex 无影响，因为 `CLAUDE.md` / `AGENTS.md` 的 parent 就是 `destination_root`。

### 3. 提示层源码 — `TraeCn/Skills/` 目录树

```
TraeCn/
└── Skills/
    ├── CN/
    │   ├── user_rules/
    │   │   └── sopify.md
    │   └── skills/
    │       └── sopify/
    │           ├── analyze/SKILL.md
    │           ├── design/SKILL.md
    │           ├── develop/SKILL.md
    │           ├── kb/SKILL.md
    │           ├── templates/SKILL.md
    │           ├── model-compare/SKILL.md
    │           └── workflow-learning/SKILL.md
    └── EN/
        └── (同上)
```

#### `user_rules/sopify.md` 格式

```markdown
---
alwaysApply: true
---
<!-- bootstrap: lang=zh-CN; encoding=UTF-8 -->
<!-- SOPIFY_VERSION: {version} -->
<!-- ARCHITECTURE: Adaptive Workflow + Layered Rules -->

# Sopify - 自适应 AI 编程助手
```

#### 路径替换映射

header 文本以 `Codex/Skills/*/AGENTS.md` 为 canonical source，做 Trae CN 宿主路径替换：

| Codex 源 | Trae CN 目标 |
|---|---|
| `~/.codex/sopify.config.yaml` | `~/.trae-cn/sopify.config.yaml` |
| `~/.codex/sopify/payload-manifest.json` | `~/.trae-cn/sopify/payload-manifest.json` |
| `~/.codex/sopify/helpers/bootstrap_workspace.py` | `~/.trae-cn/sopify/helpers/bootstrap_workspace.py` |

#### SKILL.md 文件

`skills/sopify/*` 目录内容与 Codex 版本保持一致。Trae CN 的全局技能目录目标为 `~/.trae-cn/skills/sopify/`。

### 4. prompt-layer source of truth / sync 策略

#### 决策

- `Codex/Skills/{CN,EN}` 继续作为 canonical source
- `Claude/Skills/{CN,EN}` 与 `TraeCn/Skills/{CN,EN}` 视为 host-specific generated mirrors
- v1 必须补齐 repo 内的同步与校验链路，避免三套目录长期手工维护

#### 原因

当前仓库已有明确的 `Codex -> Claude` 镜像关系与校验脚本。如果 Trae CN 直接按“从 Claude 复制”落地，会形成 `Codex / Claude / TraeCn` 三套 prompt-layer 目录并行演化，版本号、路径替换和技能内容都容易漂移，且 release hook 不会自动发现偏差。

#### v1 设计约束

- header 文本统一从 `Codex/Skills/*/AGENTS.md` 生成
- Trae CN header 文件名映射为 `user_rules/sopify.md`
- `skills/sopify/*` 目录与 canonical source 保持一致，不允许 Trae CN 独立漂移

### 5. 运行时配置 — `runtime/config.py`

当前 `load_runtime_config` 默认读取 `~/.codex/sopify.config.yaml`。v1 决策是不修改默认值，而由 Trae CN 宿主桥接在触发 gate 时显式传：

```bash
--global-config ~/.trae-cn/sopify.config.yaml
```

这样可以避免在 v1 引入新的宿主识别分支，也不会改变 Codex / Claude 的现有默认行为。

### 6. 注册到 `installer/hosts/__init__.py`

```python
from .trae_cn import TRAE_CN_ADAPTER, TRAE_CN_HOST

_REGISTRATIONS = {
    CODEX_HOST.capability.host_id: CODEX_HOST,
    CLAUDE_HOST.capability.host_id: CLAUDE_HOST,
    TRAE_CN_HOST.capability.host_id: TRAE_CN_HOST,
}
```

注册后 `install_sopify.py --target trae-cn:zh-CN` 自动可用。

### 7. 诊断面覆盖

无需修改 `inspection.py` 主逻辑。`inspect_all_hosts()` 遍历 `iter_host_registrations()`，注册即覆盖：

- `sopify status` 会展示 `trae-cn` host 行
- `sopify doctor` 会检查 `trae-cn` 的 prompt/payload/workspace bundle/ingress proof/smoke

### 8. expected_paths 适配

当前 `HostAdapter.expected_paths()` 返回：

```python
(
    root / self.header_filename,                          # ~/.trae-cn/user_rules/sopify.md
    root / "skills" / "sopify" / "analyze" / "SKILL.md", # ~/.trae-cn/skills/sopify/analyze/SKILL.md
    root / "skills" / "sopify" / "design" / "SKILL.md",  # ~/.trae-cn/skills/sopify/design/SKILL.md
)
```

`header_filename="user_rules/sopify.md"` 会自然拼接为正确路径，无需改 `expected_paths()`。

### 9. release / doc / version 自动化接入

Trae CN 不能只完成 installer 注册，而必须同步纳入以下仓库级契约：

- `scripts/sync-skills.sh`：从 canonical source 生成 Trae CN prompt-layer 产物
- `scripts/check-skills-sync.sh`：校验 Trae CN 镜像是否与 canonical source 对齐
- `scripts/release-sync.sh`：release 时同步更新 Trae CN header 的 `SOPIFY_VERSION`
- `scripts/check-version-consistency.sh`：把 Trae CN header 纳入版本一致性检查
- `scripts/check-readme-links.py`：把 Trae CN 文档入口和版本头一起纳入公共文档校验
- `.githooks/pre-commit`：把 Trae CN 产物加入 release snapshot / staged add 的受管范围

这部分是 v1 落地的必要部分，否则 `trae-cn` 会成为 release gate 的盲区。

### 10. 全局宿主 vs 项目 overlay 决策

| 维度 | 策略 A: 全局 `~/.trae-cn/user_rules` + `~/.trae-cn/skills` | 策略 B: 项目 `.trae/rules` + `.trae/skills` 作为主安装目标 |
|------|---|---|
| 与现有 installer 架构一致性 | 高 | 低 |
| 与 Codex/Claude 宿主模型一致性 | 高 | 低 |
| 对用户 repo 的侵入性 | 低 | 高 |
| 对团队自定义 `.trae/*` 的干扰 | 低 | 高 |
| Phase 0 已验证程度 | 全局路径靠社区证据 + 真实 smoke | 只验证了手工项目级注入可行 |
| **结论** | **推荐，v1 采用** | 后续增强 |

### 11. smoke 证据契约

Phase 0 的手工记录只证明“Trae CN 项目级注入可行”，不能替代工程验收。v1 的工程验收至少需要以下真实 Trae CN IDE 证据：

1. 安装后的 `~/.trae-cn/user_rules/sopify.md` 自动注入，而不是依赖项目 `.trae/rules/*`
2. 安装后的 `~/.trae-cn/skills/sopify/*` 可被 Trae CN 发现，并能按需加载至少一个 Sopify skill
3. Trae CN Builder 可执行 `python3 scripts/runtime_gate.py enter ...`
4. 安装后的 `~/.trae-cn/` 产物与 repo 内版本号、同步规则保持一致
5. installer 不会创建或覆盖 `<project>/.trae/*`

## 分阶段交付

```
Phase 0: 可行性记录与宿主范围确认
│  ├── 已验证 Trae CN 中项目级 .trae/rules + .trae/skills 注入可行
│  └── 已确认 v1 真实目标是全局 ~/.trae-cn/user_rules + ~/.trae-cn/skills
│
Phase 1: 最小适配
│  ├── 新增 installer/hosts/trae_cn.py
│  ├── 注册到 __init__.py
│  ├── install_host_assets 适配 user_rules 子目录 header
│  ├── 新建 TraeCn/Skills/ 目录树
│  └── 接入 sync/check 脚本，明确 prompt-layer source of truth
│
Phase 2: install + diagnostics + automation
│  ├── install_sopify.py --target trae-cn:zh-CN 验证通过
│  ├── sopify status / doctor 展示 trae-cn 宿主
│  ├── release/doc/version 自动化纳入 Trae CN
│  └── 测试: installer / status-doctor / release hooks / readme checks 补充 trae-cn 断言
│
Phase 3: 真实 Trae CN IDE smoke + tier 评审
│  ├── 全局 user_rules 自动注入
│  ├── 全局 skills 可发现与加载
│  ├── runtime gate 可执行
│  └── 依据 smoke 证据决定是否升级 tier
```

## 测试策略

### 新增测试点

1. **注册完整性**：`get_host_capability("trae-cn")` 返回预期 capability
2. **安装流程**：`install_sopify.py --target trae-cn:zh-CN` 成功，expected_paths 全部存在
3. **status contract**：`build_status_payload` 返回 `trae-cn` host entry，state 字段完整
4. **doctor contract**：`build_doctor_payload` 返回 `trae-cn` 的 checks，且包含 `workspace_ingress_proof`
5. **子目录 header**：确认 `~/.trae-cn/user_rules/` 被正确创建，`sopify.md` 被写入
6. **YAML frontmatter**：确认 `user_rules/sopify.md` 以 `---\nalwaysApply: true\n---` 开头
7. **sync/release contract**：Trae CN header 与 skill 目录被 sync/check/version/release hook 一并管理
8. **非侵入性保护**：installer 不会创建或覆盖 `<project>/.trae/*`
9. **真实 IDE smoke**：Trae CN 中确认全局 user_rules 自动注入、全局 skills 可发现、runtime gate 可执行

### 回归保护

- 现有 Claude/Codex contract 不回退
- 宿主集合断言改成三宿主：`codex / claude / trae-cn`
- `workspace_ingress_proof` 在 `trae-cn` capability / doctor / 测试中直接对齐当前基线

## 非目标 (Non-goals)

1. 不修改现有 Claude/Codex 宿主的任何行为或 contract
2. 不创建 Trae CN 自定义智能体（UI 层操作）
3. 不桥接 Trae SOLO Spec 与 Sopify plan
4. 不改 `.sopify-runtime/` workspace bundle 路径
5. 不实现国际版 `trae` 宿主
6. 不自动初始化或覆盖项目 `<project>/.trae/*`
7. 不在本轮实现宿主感知的 `runtime/config.py` fallback 探测
8. 不在证据不足时提前升级 Trae CN 的 `support_tier` 到 `DEEP_VERIFIED`
