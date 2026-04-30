# 技术设计: Blueprint 可插拔增强架构 + Graphify 首个实现

## 技术方案

- 核心目标：为 blueprint 层引入**可插拔增强器（Enhancer）架构**，graphify 作为首个具体实现
- 本方案定位：本期交付 graphify enhancer；架构层面预留其他 enhancer 的扩展能力

## 设计原则

1. **插拔式增强**
   blueprint 增强器是可选模块，开关关闭时零影响。架构支持后续接入其他增强器，不需改核心流程。

2. **极简用户面**
   用户只需设置 `blueprint_enhancers.graphify.enabled: true` 即可启用。公共层保底 `enabled` 开关，增强器可按需暴露少量私有配置键（由各增强器白名单校验）。全部收敛在 `blueprint_enhancers` 父键下。

3. **auto-section 命名空间隔离**
   每个增强器拥有自己的 auto-section 前缀（`{name}:auto:*`），互不干扰。同一增强器可在同一文件中写入多个 auto-section。

4. **graphify 本体不改**
   所有适配逻辑在 sopify 侧。通过 graphify 的公开 API 做契约面。

5. **降级优于崩溃（运行时），快速失败（配置错误）**
   增强器依赖未安装时 warning + 跳过，字段缺失时 fallback（fail-open）。
   但配置错误（未注册的 enhancer 名、私有键类型不合法）直接 raise（fail-closed），
   不让拼写错误静默通过。

6. **信号暴露，不自动执行**
   runtime 不自动执行 enhancer 编排脚本。finalize 等生命周期事件只通过
   handoff artifact 暴露 stale/recommended-refresh 信号，由宿主/CI 决定是否触发。
   这保持 runtime 不依赖 enhancer 第三方库的边界。

## 配置形态

### 用户面

```yaml
# sopify.config.yaml
blueprint_enhancers:
  graphify:
    enabled: false
```

> **设计选择**：使用 `blueprint_enhancers` 稳定父键。
>
> 原因：当前 `runtime/config.py:53` 的 `_ALLOWED_TOP_LEVEL` 是白名单机制，
> 每加一个增强器就要改白名单，和"可插拔"矛盾。统一到 `blueprint_enhancers`
> 子键后，只需加一次 `"blueprint_enhancers"` 到白名单，后续增强器零改动扩展。

### config.py 改动

```python
# runtime/config.py

# DEFAULT_CONFIG 新增稳定父键（与 workflow/plan/multi_model/advanced 同级）
DEFAULT_CONFIG: dict[str, Any] = {
    ...
    "blueprint_enhancers": {},  # 空 dict 作为合法 baseline
}

_ALLOWED_TOP_LEVEL = {
    "brand", "language", "output_style", "title_color",
    "workflow", "plan", "multi_model", "advanced",
    "blueprint_enhancers",  # 新增
}

def _validate_blueprint_enhancers(enhancers: Any) -> None:
    """验证 blueprint_enhancers 子配置。

    公共层职责：
    - 确保整体是 mapping
    - 确保每个增强器配置是 mapping
    - 确保 `enabled` 若存在则是 bool
    - 不限制增强器名（可插拔）
    - 不限制除 `enabled` 外的子键（由各增强器通过 `validate_enhancer_config()` 自行白名单校验；
      新增私有键须同步扩展增强器校验方法）

    未注册的增强器名在此不报错；但若 enabled: true 且不在 ENHANCER_REGISTRY，
    由 get_enabled_enhancers() raise EnhancerConfigError。
    """
    if not isinstance(enhancers, dict):
        raise ConfigError("blueprint_enhancers must be a mapping")
    for name, cfg in enhancers.items():
        if not isinstance(cfg, dict):
            raise ConfigError(f"blueprint_enhancers.{name} must be a mapping")
        if "enabled" in cfg and not isinstance(cfg["enabled"], bool):
            raise ConfigError(f"blueprint_enhancers.{name}.enabled must be boolean")
```

> **设计变更记录**（vs 初版）：
>
> 1. `blueprint_enhancers: {}` 加入 `DEFAULT_CONFIG`，`_deep_merge` 后此键必然存在，
>    `_validate_config()` 中**无条件调用** `_validate_blueprint_enhancers()`，
>    与 `workflow`/`plan` 等现有父键处理模式一致。不再需要 `if "blueprint_enhancers" in config` 分支。
> 2. 去掉 `_ALLOWED_ENHANCER_KEYS` 白名单。公共层只校验 `enabled` 类型，
>    其余子键由增强器通过 `validate_enhancer_config()` 自行校验（见增强器架构节）。
>    避免"过严阻碍扩展"与"过松放过拼写错误"的两极。

### RuntimeConfig 取值链路

当前 `load_runtime_config()` (config.py:104) 返回 frozen `RuntimeConfig` dataclass，
所有字段在构造时展开。`blueprint_enhancers` 是新增的嵌套配置，有两种落地方式：

**方案 A（推荐）**：给 RuntimeConfig 加 `blueprint_enhancers` 字段

```python
# runtime/_models/core.py — RuntimeConfig 新增字段
# 追加在 cache_project 之后（最末尾），使用 default_factory 避免
# 已有测试/手工实例化因位置参数错位而报错
@dataclass(frozen=True)
class RuntimeConfig:
    ...
    cache_project: bool
    blueprint_enhancers: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

# runtime/config.py — load_runtime_config() 构造时传入
return RuntimeConfig(
    ...
    blueprint_enhancers=merged.get("blueprint_enhancers", {}),
)
```

- 优点：编排脚本直接 `config.blueprint_enhancers`，类型安全
- 改动：RuntimeConfig + load_runtime_config 各加一行

**方案 B**：编排脚本独立读 raw config

```python
# scripts/blueprint_enhance.py — 不走 RuntimeConfig
from runtime.config import _load_config_file
raw = _load_config_file(workspace / "sopify.config.yaml")
enhancers_cfg = raw.get("blueprint_enhancers", {})
```

- 优点：零改动 RuntimeConfig
- 缺点：绕过验证链路，未来维护时 config 路径可能分叉

> **本方案选择 A**。`blueprint_enhancers` 是稳定父键，进入 RuntimeConfig 后
> 所有消费者（编排脚本、finalize 提示等）都走同一条链路。

## graphify 依赖策略

### 定位

graphify 是 **optional enhancer dependency**，不是 sopify runtime hard dependency。
当前 sopify-skills runtime 明确宣称 `stdlib_only=True, runtime_dependencies=[]`
（runtime/manifest.py:139），这个基线不变。

### 分层策略

| 场景 | 安装方式 | 说明 |
|---|---|---|
| 本地开发联调 | `pip install -e /path/to/graphify && pip install graspologic` | editable + Leiden，联调效率最高 |
| 团队/CI/正式环境 | `pip install graphifyy[leiden]==0.4.16` | PyPI pinned + Leiden，可复现。**仅当不依赖本地未发布修复时 CI 跟 PyPI 走** |
| 临时调试 | import path hack | **不作为正式接入路径** |

### 兼容性契约（两层分离）

| 契约 | 适用范围 | 约束 |
|---|---|---|
| **runtime contract** | sopify runtime（IDE 宿主侧） | 不依赖 graphify/leiden，**不受 Python <3.13 限制** |
| **artifact generation contract** | 生成 tracked `report.md` 的执行环境（本地 / CI） | Python 3.11/3.12 + `graphifyy[leiden]==0.4.16` |

> 两层分离原则：optional enhancer 的第三方依赖不反向约束 sopify runtime 基线。

**CI 硬约束**：不满足 Python 3.11/3.12 + Leiden → 编排脚本直接报错退出。
**本地软约束**：允许 fallback Louvain，但输出必须标出 `cluster_backend=louvain`，
防止误提交与 CI 不一致的 report.md。

### leiden extras 注意

graphify 的 `cluster()` 使用 Leiden 算法（`graspologic.partition.leiden`，
定义在 `graphify/cluster.py:31`）。这是 optional extra：

```toml
# graphify pyproject.toml
leiden = ["graspologic; python_version < '3.13'"]
```

**两级可用性**：

| 级别 | 条件 | 聚类行为 | 报告质量 |
|---|---|---|---|
| **base 可用** | graphify 已安装（无 leiden extra） | fallback 到 networkx Louvain | 可用但聚类质量较低 |
| **最佳效果可用** | graphify + `graspologic` 已安装 | Leiden 算法 | 最佳聚类质量 |

> `is_available()` 只检查 base 可用性。leiden extra 缺失不阻塞 enhancer 启用，
> 但编排脚本应在输出中提示聚类质量差异。

> **⚠️ 安装档位一致性**：如果 `report.md` 进入版本管理，所有环境（本地 / CI / 团队成员）
> **必须统一到同一安装档位**（同时有 Leiden 或同时没有）。否则本地走 Leiden、CI 走
> Louvain，图谱和报告的聚类结果会不可复现。编排脚本输出应包含当前聚类后端标识
> （`leiden` / `louvain`），便于 review 时发现环境漂移。

推荐安装：
```bash
pip install graphifyy[leiden]==0.4.16   # PyPI + Leiden
pip install -e /path/to/graphify && pip install graspologic  # editable + Leiden
```

> **注意**：`graspologic` 要求 `python_version < 3.13`。Python 3.13+ 环境
> 会自动 fallback 到 Louvain。

### is_available() 策略链

```python
_DETECT_STRATEGIES = [
    ("pkg", "graphifyy"),    # PyPI 安装
    ("pkg", "graphify"),     # editable install 可能用不同包名
    ("import", "graphify"),  # fallback
]
```

无论哪种安装方式，策略链都能检测到。

## 可插拔增强器架构

### 核心抽象

```python
# installer/blueprint_enhancer.py（新增）

from pathlib import Path
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Mapping

class BlueprintEnhancer(ABC):
    """可插拔的 blueprint 增强器基类。

    设计约束：
    - name 是类级元数据（ClassVar），注册时零实例化
    - is_available() 和 validate_enhancer_config() 是类方法，
      只有在 enabled + config 合法 + available 全部通过后才实例化
    - 实例化时接收已验证的 enhancer config
    """

    name: ClassVar[str]
    """增强器标识符。
    用于：config key (`blueprint_enhancers.{name}.enabled`)
          auto-section 前缀 (`<!-- {name}:auto:{section_id}:start/end -->`)
          产物子目录 (`blueprint/{name}/`)
    """

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """检查依赖是否已安装且版本兼容。类级检查，不实例化。"""
        ...

    @classmethod
    def validate_enhancer_config(cls, cfg: Mapping[str, Any]) -> None:
        """校验增强器私有配置键。

        公共层已保证 `enabled` 是 bool，此方法只需校验增强器自定义的键。
        默认实现为 no-op；增强器有自定义配置时 override。
        """
        pass

    def __init__(self, config: Mapping[str, Any] | None = None):
        """实例化时接收已验证的 enhancer config。"""
        self._config = config or {}

    @abstractmethod
    def generate(self, repo_root: Path, output_dir: Path) -> dict:
        """全量生成。返回结构化结果供 render_auto_sections 使用。"""
        ...

    @abstractmethod
    def update(self, repo_root: Path, output_dir: Path) -> dict:
        """增量更新。无法增量时内部自动 fallback 到 generate。"""
        ...

    @abstractmethod
    def render_auto_sections(self, result: dict) -> dict[str, dict[str, str]]:
        """返回 {filename: {section_id: markdown_content}}。

        同一增强器可在同一文件中写入多个 auto-section。
        例如：
        {
            "background.md": {
                "codebase-overview": "...",
            },
            "design.md": {
                "architecture": "...",
                "module-stats": "...",
            },
        }
        """
        ...

    def ensure_output_excluded(self, repo_root: Path, output_dir: Path):
        """确保增强器自产物不被自身的增量检测扫描到。

        增强器通用约定——每个增强器在 generate()/update() 前应调用此方法
        （或自行实现等效逻辑），避免"自产物触发自身再次更新"的反馈循环。

        默认实现为 no-op；具体增强器按自身检测工具的约定 override。
        例如 GraphifyEnhancer 通过 .graphifyignore 实现。
        """
        pass
```

> **设计变更记录**（vs 初版）：
>
> - `name` 从 `@property @abstractmethod` 改为 `ClassVar[str]`，注册时零实例化
> - `is_available()` 从实例方法改为 `@classmethod`，依赖检测不需要实例
> - 新增 `validate_enhancer_config()` 类方法，承接从公共层下放的私有键校验
> - `__init__` 接收已验证的 `config`，实例化延迟到一切检查通过之后

### 增强器注册表

```python
class EnhancerConfigError(ValueError):
    """增强器配置校验失败。

    独立于 runtime.config.ConfigError，避免 installer → runtime 反向依赖。
    """

ENHANCER_REGISTRY: dict[str, type[BlueprintEnhancer]] = {}

def register_enhancer(cls: type[BlueprintEnhancer]):
    """纯类注册，零实例化。name 是 ClassVar，直接从类上读取。"""
    ENHANCER_REGISTRY[cls.name] = cls
    return cls

def get_enabled_enhancers(config: RuntimeConfig) -> list[BlueprintEnhancer]:
    """返回已启用、配置合法、依赖可用的增强器实例列表。

    三级过滤：enabled → validate_enhancer_config → is_available。
    只有全部通过后才实例化。

    Raises:
        EnhancerConfigError: 未知 enhancer enabled: true / 私有键校验失败
    """
    enhancers_cfg = config.blueprint_enhancers
    result = []

    # 未知 enhancer + enabled: true → 配置错误，直接 raise
    for cfg_name, cfg in enhancers_cfg.items():
        if cfg.get("enabled", False) and cfg_name not in ENHANCER_REGISTRY:
            raise EnhancerConfigError(
                f"Enhancer '{cfg_name}' is enabled in config but not registered. "
                f"Check for typos in blueprint_enhancers.{cfg_name}"
            )

    for name, cls in ENHANCER_REGISTRY.items():
        cfg = enhancers_cfg.get(name, {})
        if not cfg.get("enabled", False):
            continue
        # 类级校验：增强器私有配置键（校验失败 raise EnhancerConfigError）
        cls.validate_enhancer_config(cfg)
        # 类级检测：依赖可用性
        if cls.is_available():
            result.append(cls(config=cfg))  # 此时才实例化
        else:
            import warnings
            warnings.warn(f"Enhancer '{name}' enabled but dependencies not available")
    return result
```

> **设计变更记录**（vs 初版）：
>
> 1. 新增 `EnhancerConfigError(ValueError)`，独立于 `runtime.config.ConfigError`，
>    避免 `installer` → `runtime` 反向依赖
> 2. `register_enhancer` 不再实例化（`cls.name` 直接从 ClassVar 读取）
> 3. `get_enabled_enhancers` 改为三级过滤：enabled → validate → is_available
> 4. 未知 enhancer + `enabled: true` → **raise EnhancerConfigError**（统一为单一 contract，
>    不再同时说 warning 和报错两种行为）
> 5. 实例化延迟到所有类级检查通过之后，传入已验证的 config

### auto-section 注入引擎

```python
import re

def inject_auto_sections(
    blueprint_dir: Path,
    enhancer: BlueprintEnhancer,
    sections: dict[str, dict[str, str]],
) -> list[str]:
    """将渲染结果注入 blueprint 文件的 auto-section。

    sections 结构：{filename: {section_id: content}}
    匹配标记：<!-- {enhancer.name}:auto:{section_id}:start/end -->
    手写区域永远不碰。
    """
    modified = []
    prefix = re.escape(enhancer.name)
    for filename, section_map in sections.items():
        filepath = blueprint_dir / filename
        if not filepath.exists():
            continue
        text = filepath.read_text(encoding="utf-8")
        changed = False
        for section_id, content in section_map.items():
            escaped_id = re.escape(section_id)
            # 兼容 \n 和 \r\n 换行
            pattern = re.compile(
                rf"(<!-- {prefix}:auto:{escaped_id}:start -->)\r?\n.*?\r?\n(<!-- {prefix}:auto:{escaped_id}:end -->)",
                re.DOTALL,
            )
            # 使用 replacement function 避免 content 中的反斜杠被 re.sub 解释
            trimmed = content.strip("\n")

            def _make_replacer(c: str):
                def _replacer(match: re.Match) -> str:
                    # 保留原始换行风格，避免行尾漂移
                    nl = "\r\n" if "\r\n" in match.group(0) else "\n"
                    return f"{match.group(1)}{nl}{c}{nl}{match.group(2)}"
                return _replacer

            new_text = pattern.sub(_make_replacer(trimmed), text)
            if new_text != text:
                text = new_text
                changed = True
        if changed:
            filepath.write_text(text, encoding="utf-8")
            modified.append(str(filepath))
    return modified
```

> **设计变更记录**（vs 初版）：
>
> 1. 正则兼容 `\r\n` 换行（`\r?\n`），避免 Windows 文件失配
> 2. 改用 replacement function（`_make_replacer`），避免 `content` 中的
>    `\1`、`\g<0>` 等序列被 `re.sub` 按替换语义解释
> 3. replacement function 保留原始换行风格（`\r\n` 或 `\n`），
>    匹配时兼容、替换时也保持一致，避免行尾漂移
> 4. 内容边界处理用 `content.strip("\n")`（仅裁换行），
>    不用 `content.strip()`（会吃掉 markdown 有意缩进）
> - `sections` 从 `dict[str, str]` 改为 `dict[str, dict[str, str]]`
> - 按 `(filename, section_id)` 精确匹配，同一文件可有多个 auto-section
> - section_id 也做 `re.escape()` 确保特殊字符安全

## Graphify 增强器具体实现

### 引用 graphify 公开 API（对齐真实签名）

基于 graphify 仓库当前 v0.4.16 的实际实现：

| graphify API | 真实签名 | 适配层用途 |
|---|---|---|
| `collect_files(target)` | `(Path, *, follow_symlinks=False, root=None) -> list[Path]` | 目录扫描，返回代码文件路径列表 |
| `extract(paths)` | `(list[Path], cache_root=None) -> dict{nodes, edges, input_tokens, output_tokens}` | 批量 AST 提取 |
| `build_from_json(data)` | `(dict, *, directed=False) -> nx.Graph` | 提取结果 → NetworkX 图 |
| `cluster(G)` | `(nx.Graph) -> dict[int, list[str]]` | Leiden 社区检测 |
| `score_all(G, communities)` | `(G, dict) -> dict[int, float]` | 社区内聚度评分 |
| `god_nodes(G, top_n=10)` | `(G, int) -> list[dict]` | 核心节点 |
| `surprising_connections(G, communities)` | `(G, dict) -> list[dict]` | 跨社区异常连接 |
| `suggest_questions(G, communities, labels)` | `(G, dict, dict) -> list[dict]` | 建议问题 |
| `generate(G, ...)` | `(G, communities, cohesion, labels, gods, surprises, detection, token_cost, root, *, suggested_questions) -> str` | 生成 report.md |
| `to_json(G, communities, path)` | `(G, dict, str) -> None` | 持久化 graph.json |
| `to_html(G, communities, path)` | `(G, dict, str) -> None` | 交互可视化 |
| `detect_incremental(root)` | `(Path, manifest_path=...) -> dict` | 增量检测，返回 `new_files` + `deleted_files` + `new_total` |

### collect_files 局限：不收 .md

```python
# graphify/extract.py:3183
_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".go", ".rs", ...}  # 无 .md
```

plan/ 和 history/ 的 Markdown 方案文件不会被收集。适配层额外扫描补充。

> **本期能力边界**：只保证"文档节点入图可见"，不承诺自动推断文档间依赖。

### _collect_plan_docs — 文档节点补充扫描

```python
# 默认 history 扫描深度（最近 N 个归档目录）
_DEFAULT_HISTORY_SCAN_DEPTH = 5

def _collect_plan_docs(self, repo_root: Path) -> tuple[list[dict], dict]:
    """扫描 plan/ 和 history/ 中的 .md 文件，生成文件级文档节点。

    source_location 按 sopify 知识层级映射：
    - plan/  → L2 (active plan)，全量扫描
    - history/ → L3 (archived plan)，策略性收敛：只扫最近 N 个归档目录

    不写死为 L1，避免与 blueprint stable 层混淆。

    Returns:
        (md_nodes, scan_meta) — 节点列表 + 扫描元数据（含截断信息）
    """
    LAYER_MAP = {
        "plan": "L2",       # active plan — 全扫
        "history": "L3",    # archived plan — 策略性收敛
    }
    history_scan_depth = self._config.get(
        "history_scan_depth", _DEFAULT_HISTORY_SCAN_DEPTH
    )
    md_nodes = []
    scan_meta = {"history_truncated": False, "history_scan_depth": history_scan_depth}

    for subdir, layer in LAYER_MAP.items():
        md_dir = repo_root / ".sopify-skills" / subdir
        if not md_dir.exists():
            continue

        if subdir == "history":
            # 策略性收敛：遍历 history/YYYY-MM/<plan_id>/，
            # 按 plan 目录名倒序取最近 N 个具体归档 plan。
            #
            # 排序依据：plan 目录名遵循 sopify 命名规范 `YYYYMMDD_<slug>`，
            # 字符串倒序等价于时间倒序。若目录名不符合此规范（无日期前缀），
            # 仍按字符串排序，行为退化为字母序但不报错。
            all_plan_dirs = sorted(
                [d for month_dir in md_dir.iterdir() if month_dir.is_dir()
                 for d in month_dir.iterdir() if d.is_dir()],
                key=lambda d: d.name,
                reverse=True,
            )
            if len(all_plan_dirs) > history_scan_depth:
                scan_meta["history_truncated"] = True
                scan_meta["history_total_plans"] = len(all_plan_dirs)
                all_plan_dirs = all_plan_dirs[:history_scan_depth]
            for plan_dir in all_plan_dirs:
                for md_file in plan_dir.rglob("*.md"):
                    md_nodes.append({
                        "id": str(md_file.relative_to(repo_root)),
                        "label": md_file.stem,
                        "file_type": "markdown",
                        "source_file": str(md_file),
                        "source_location": layer,
                    })
        else:
            # plan/ 全量扫描
            for md_file in md_dir.rglob("*.md"):
                md_nodes.append({
                    "id": str(md_file.relative_to(repo_root)),
                    "label": md_file.stem,
                    "file_type": "markdown",
                    "source_file": str(md_file),
                    "source_location": layer,
                })
    return md_nodes, scan_meta
```

> **设计变更记录**（vs 初版）：
>
> 1. history 改为策略性收敛：按目录名排序取最近 N 个归档，
>    防止历史文档节点淹没代码图谱、影响聚类和报告可读性
> 2. `history_scan_depth` 可通过增强器 config 覆盖（默认 5）
> 3. 截断信息写入 `scan_meta`，最终落入 `.meta.json`，便于追溯
> 4. 返回值从 `list[dict]` 改为 `tuple[list[dict], dict]`，携带扫描元数据

### 依赖可用性检测

`is_available()` 使用策略链检测（见上方"graphify 依赖策略"节），不硬绑分发名：

```python
class GraphifyEnhancer(BlueprintEnhancer):
    name = "graphify"
    MIN_VERSION = "0.4.16"

    _DETECT_STRATEGIES = [
        ("pkg", "graphifyy"),
        ("pkg", "graphify"),
        ("import", "graphify"),
    ]

    @classmethod
    def validate_enhancer_config(cls, cfg):
        """校验 graphify 增强器私有配置键。

        当前 graphify 增强器仅定义以下私有键：
        - history_scan_depth: int (>= 1) — history 归档扫描深度

        新增私有键时必须同步更新此方法。未在此校验的键不应出现在配置中。
        """
        known_private_keys = {"history_scan_depth"}
        private_keys = {k for k in cfg if k != "enabled"}
        unknown = private_keys - known_private_keys
        if unknown:
            raise EnhancerConfigError(
                f"Unknown key(s) in blueprint_enhancers.graphify: {unknown}"
            )
        depth = cfg.get("history_scan_depth")
        if depth is not None:
            if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
                raise EnhancerConfigError(
                    f"blueprint_enhancers.graphify.history_scan_depth "
                    f"must be a positive integer, got {depth!r}"
                )

    @classmethod
    def is_available(cls) -> bool:
        for strategy, target in cls._DETECT_STRATEGIES:
            if strategy == "pkg":
                try:
                    from importlib.metadata import version
                    ver = version(target)
                    if cls._version_compat(ver):
                        return True
                except Exception:
                    continue
            elif strategy == "import":
                try:
                    import importlib
                    mod = importlib.import_module(target)
                    ver = getattr(mod, "__version__", None)
                    if ver and cls._version_compat(ver):
                        return True
                except Exception:
                    continue
        return False
```

### 社区标签策略

```python
def _label_communities(self, G: nx.Graph, communities: dict) -> dict[int, str]:
    """基于社区内核心节点生成可读标签。"""
    labels = {}
    for cid, members in communities.items():
        if not members:
            labels[cid] = f"Community {cid}"
            continue
        # 取社区内 degree 最高的节点
        real_members = [n for n in members if n in G]
        if not real_members:
            labels[cid] = f"Community {cid}"
            continue
        sorted_by_degree = sorted(real_members, key=lambda n: G.degree(n), reverse=True)
        top = sorted_by_degree[0]
        top_label = G.nodes[top].get("label", top)
        # 空社区或弱标签时，用前两个代表节点
        if len(sorted_by_degree) >= 2 and G.degree(sorted_by_degree[0]) <= 2:
            second_label = G.nodes[sorted_by_degree[1]].get("label", sorted_by_degree[1])
            labels[cid] = f"{top_label} & {second_label}"
        else:
            labels[cid] = f"{top_label} cluster"
    return labels
```

> **与上版差异**：
> - 空社区或弱标签（degree ≤ 2）时回退到前两个代表节点名
> - 防御 real_members 为空的边界情况

### GraphifyEnhancer 实现

```python
@register_enhancer
class GraphifyEnhancer(BlueprintEnhancer):
    name = "graphify"
    MIN_VERSION = "0.4.16"

    def generate(self, repo_root, output_dir):
        import graphify

        # 0. 通过基类 hook 排除自产物
        self.ensure_output_excluded(repo_root, output_dir)

        # 1. 扫描代码文件 → list[Path]
        code_files = graphify.collect_files(repo_root)

        # 2. 批量 AST 提取 → dict{nodes, edges}
        extraction = graphify.extract(code_files)

        # 3. 构图
        G = graphify.build_from_json(extraction)

        # 4. 补充 plan/history .md 文档节点（L2/L3 层级标记，含 history 截断）
        md_nodes, scan_meta = self._collect_plan_docs(repo_root)
        for node in md_nodes:
            G.add_node(node["id"], **node)

        # 5. 聚类 + 分析
        communities = graphify.cluster(G)
        cohesion = graphify.score_all(G, communities)
        gods = graphify.god_nodes(G, top_n=5)
        surprises = graphify.surprising_connections(G, communities)
        labels = self._label_communities(G, communities)
        questions = graphify.suggest_questions(G, communities, labels)

        # 6. 持久化到 blueprint/graphify/ 目录
        output_dir.mkdir(parents=True, exist_ok=True)
        detection_stub = {"files": {}, "total_files": len(code_files)}
        report_md = graphify.generate(
            G, communities, cohesion, labels, gods, surprises,
            detection_stub, {"input": 0, "output": 0}, str(repo_root),
            suggested_questions=questions,
        )
        (output_dir / "report.md").write_text(report_md, encoding="utf-8")
        graphify.to_json(G, communities, str(output_dir / "graph.json"))
        graphify.to_html(G, communities, str(output_dir / "graph.html"))
        self._write_meta(output_dir, G, communities, scan_meta=scan_meta)

        return {
            "gods": gods, "communities": communities,
            "surprises": surprises, "questions": questions,
            "labels": labels,
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
            "community_count": len(communities),
            "scan_meta": scan_meta,
        }

    def update(self, repo_root, output_dir):
        # 通过基类 hook 排除自产物（增量检测前必须生效）
        self.ensure_output_excluded(repo_root, output_dir)

        graph_json = output_dir / "graph.json"
        if not graph_json.exists():
            return self.generate(repo_root, output_dir)

        meta = self._read_meta(output_dir)
        if self._needs_full_rebuild(meta):
            return self.generate(repo_root, output_dir)

        from graphify.detect import detect_incremental
        detection = detect_incremental(repo_root)

        if detection.get("new_total", 0) == 0 and not detection.get("deleted_files"):
            return self._load_existing_result(output_dir)

        return self._incremental_rebuild(detection, output_dir, repo_root)

    def render_auto_sections(self, result):
        """返回 {filename: {section_id: content}}。"""
        return {
            "background.md": {
                "codebase-overview": self._render_codebase_overview(result),
            },
            "design.md": {
                "architecture": self._render_architecture(result),
            },
        }
```

## 增量检测自产物排除

### 通用约定

`BlueprintEnhancer` 基类定义了 `ensure_output_excluded(repo_root, output_dir)` 方法。
每个增强器在 `generate()`/`update()` 开始前应调用此方法（或等效实现），
确保自产物不被自身的增量检测扫描到。后续接入第二个 enhancer 时复用同一约定。

### GraphifyEnhancer 实现

`detect_incremental(repo_root)` 扫描整个仓库（detect.py:337-360），
包括 `blueprint/graphify/report.md` 等增强器自产物。如果不排除，
上次生成的 report.md 会在下次检测中被识别为"新变化文件"，
导致"自己生成的报告触发自己再次更新"的噪音循环。

### 方案

GraphifyEnhancer override `ensure_output_excluded()` 为 `_ensure_graphifyignore()`，
利用 graphify 自带的 `.graphifyignore` 文件过滤（detect.py:337-348）：

```python
def ensure_output_excluded(self, repo_root: Path, output_dir: Path):
    """Override 基类通用 hook，委托到 .graphifyignore 机制。"""
    self._ensure_graphifyignore(repo_root, output_dir)

def _ensure_graphifyignore(self, repo_root: Path, output_dir: Path):
    """确保 .graphifyignore 排除增强器自产物目录。"""
    ignore_file = repo_root / ".graphifyignore"
    rel_output = output_dir.relative_to(repo_root)
    exclude_pattern = f"{rel_output}/"

    if ignore_file.exists():
        content = ignore_file.read_text(encoding="utf-8")
        if exclude_pattern not in content:
            with ignore_file.open("a", encoding="utf-8") as f:
                f.write(f"\n# sopify blueprint enhancer output\n{exclude_pattern}\n")
    else:
        ignore_file.write_text(
            f"# sopify blueprint enhancer output\n{exclude_pattern}\n",
            encoding="utf-8",
        )
```

- generate()/update() 调用 `self.ensure_output_excluded()` → 走基类 hook
- GraphifyEnhancer override → `_ensure_graphifyignore()` → `.graphifyignore` 机制
- 排除的是整个 `blueprint/graphify/` 目录
- `.graphifyignore` 应 git tracked（和 `.gitignore` 同级），这样团队共享
- 如果仓库已有 `.graphifyignore`，只追加不覆盖

## README.md 入口链接

### 问题

`runtime/kb.py` 的 read-next 区块是 runtime 完全重渲染的（L298-301, L351-354），
手工注入会被覆盖。`_additional_blueprint_entries()` (L359-364) 只扫顶层文件。

### 方案

扩展 `_additional_blueprint_entries()` 自动发现子目录产物：

```python
def _additional_blueprint_entries(config: RuntimeConfig) -> list[str]:
    blueprint_root = config.runtime_root / "blueprint"
    if not blueprint_root.exists():
        return []
    entries: list[str] = []
    for path in sorted(blueprint_root.glob("*.md")):
        if path.name in _STANDARD_BLUEPRINT_FILENAMES:
            continue
        entries.append(f"- [{path.stem}](./{path.name})")
    # 新增：扫描增强器产物目录中的 report.md
    for subdir in sorted(blueprint_root.iterdir()):
        if subdir.is_dir() and (subdir / "report.md").exists():
            entries.append(f"- [{subdir.name} 增强报告](./{subdir.name}/report.md)")
    return entries
```

不绑定 graphify 名字——任何增强器在 `blueprint/{name}/report.md` 放产物都被发现。

## 首次运行时机

增强器**不挂入 bootstrap 默认流程**。首次运行为显式脚本调用：

```bash
python3 scripts/blueprint_enhance.py
```

脚本内部检查 blueprint scaffold 是否存在，不存在则报提示退出。

## 目录结构

```
.sopify-skills/
├── blueprint/
│   ├── README.md                    # 索引（runtime 自动渲染 read-next）
│   ├── background.md                # 手写 + <!-- graphify:auto:codebase-overview:start/end -->
│   ├── design.md                    # 手写 + <!-- graphify:auto:architecture:start/end -->
│   ├── tasks.md                     # 不变
│   └── graphify/                    # = blueprint/{enhancer.name}/
│       ├── report.md                # git tracked
│       ├── graph.json               # git ignored
│       ├── graph.html               # git ignored
│       └── .meta.json               # git ignored
```

.gitignore 追加：
```
.sopify-skills/blueprint/graphify/graph.json
.sopify-skills/blueprint/graphify/graph.html
.sopify-skills/blueprint/graphify/.meta.json
.sopify-skills/blueprint/graphify/.cache/
```

## 迭代机制

```
代码/文档变更
  → python3 scripts/blueprint_enhance.py
  → get_enabled_enhancers(config)
      - EnhancerConfigError → 格式化用户可见错误，exit 1
  → 每个增强器 update()
      - graph.json 不存在 → fallback generate()
      - .meta.json 缺失/损坏/版本变化 → fallback generate()
      - graph.json 格式异常 → fallback generate()
      - 正常 → detect_incremental() → new_files + deleted_files
  → render_auto_sections() → {filename: {section_id: content}}
  → inject_auto_sections() 精确匹配 (filename, section_id) 注入
  → 人工 review
```

编排脚本**错误处理**：

```python
# scripts/blueprint_enhance.py — 异常捕获闭环
try:
    enhancers = get_enabled_enhancers(config)
except EnhancerConfigError as exc:
    print(f"[ERROR] {exc}", file=sys.stderr)
    sys.exit(1)
```

> `EnhancerConfigError` 是内部类型契约；编排脚本负责统一渲染为用户可见的终端输出。
> 不在 `get_enabled_enhancers()` 内部做 print/exit，保持 library-style 行为。

编排脚本接口：
```bash
python3 scripts/blueprint_enhance.py                    # 全部已启用增强器
python3 scripts/blueprint_enhance.py --only graphify     # 仅 graphify
python3 scripts/blueprint_enhance.py --list              # 列出注册表
python3 scripts/blueprint_enhance.py --strict            # CI 模式：不满足 Leiden → exit 1
```

**CI / 本地模式切换**：

| 模式 | 触发条件 | Louvain fallback 行为 |
|---|---|---|
| strict（CI） | `--strict` flag 或 `CI=true` 环境变量 | **报错退出**（exit 1），不生成 report.md |
| normal（本地） | 默认 | warning + 标出 `cluster_backend=louvain`，允许生成但提示勿提交 |

脚本伪逻辑：
```python
strict_mode = args.strict or os.environ.get("CI", "").lower() in ("true", "1")
if cluster_backend == "louvain" and strict_mode:
    sys.exit("[FAIL] Leiden required in strict mode. Install: pip install graspologic")
```

编排脚本输出必须包含**聚类后端标识**，便于 review 和排障：

```
[graphify] cluster_backend=leiden    node_count=142  edge_count=287  community_count=5
[graphify] report.md updated: blueprint/graphify/report.md
```

或 fallback 时：

```
[graphify] ⚠ cluster_backend=louvain (graspologic not installed)
[graphify] ⚠ Report generated with Louvain fallback. Do NOT commit if CI requires Leiden.
```

## Plan 同步机制

### 能力边界

> 本期：plan/history 文档"入图可见"（文件节点，L2/L3 层级标记）。
> 不承诺：自动推断文档间依赖（Phase 4.1）。

### Plan 生命周期映射

| Plan 事件 | 图谱反应 | 触发方式 |
|---|---|---|
| Plan Created | plan/ .md → L2 节点 | 下次手动 run |
| Plan Modified | mtime 变化 → 重提取 | 下次手动 run |
| Plan Finalized | plan/ → history/ → L2 节点消失、L3 节点出现 | finalize 后提示 |

### Archive 触发机制（A + C-lite）

**方案选择**：runtime 不自动执行 enhancer（见设计原则 6），采用双通道信号：

- **notes（人看）**：engine.py archive_lifecycle 分支末尾，条件化追加提示
- **artifacts（机器读）**：handoff.py `_collect_handoff_artifacts()` 补结构化标记

#### engine.py 条件化 note

```python
# engine.py — archive_lifecycle 分支末尾
if archived_plan is not None:
    has_enabled = any(
        isinstance(cfg, Mapping) and cfg.get("enabled", False)
        for cfg in config.blueprint_enhancers.values()
    )
    if has_enabled:
        notes.append(
            "Plan finalized. Run 'python3 scripts/blueprint_enhance.py' "
            "to update the blueprint."
        )
```

> 只读 `config.blueprint_enhancers`（已在 RuntimeConfig），不 import enhancer registry，
> 不碰 graphify availability。判断口径：有已启用 enhancer 配置 = 推荐刷新。

#### handoff.py 结构化 artifact

```python
# handoff.py — _collect_handoff_artifacts()
# 在 archive_lifecycle.archive_status == "completed" 分支之后
archive_lifecycle = artifacts.get("archive_lifecycle")
if isinstance(archive_lifecycle, Mapping) and archive_lifecycle.get("archive_status") == "completed":
    has_enabled = any(
        isinstance(cfg, Mapping) and cfg.get("enabled", False)
        for cfg in config.blueprint_enhancers.values()
    )
    if has_enabled:
        artifacts["blueprint_enhancer_refresh"] = {
            "recommended": True,
            "reason": "plan_finalized",
            "trigger": "enabled_enhancer_config_present",
            "command": "python3 scripts/blueprint_enhance.py",
        }
```

宿主收到的 handoff：

```json
{
  "required_host_action": "archive_completed",
  "artifacts": {
    "archive_lifecycle": {
      "archive_status": "completed"
    },
    "archived_plan_path": "history/2026-04/plan_id",
    "blueprint_enhancer_refresh": {
      "recommended": true,
      "reason": "plan_finalized",
      "trigger": "enabled_enhancer_config_present",
      "command": "python3 scripts/blueprint_enhance.py"
    }
  }
}
```

> **职责分层**：
> - `archive_lifecycle` 纯 archive，不知道 enhancer
> - engine.py 传递结果 + 条件化人类提示
> - handoff.py 暴露机器可读的 stale signal
> - 宿主/CI 自行决定是否触发（本期不自动执行）

> **`trigger` 字段约定**：`reason` 是生命周期事件（plan_finalized / staleness_check），
> `trigger` 是判定原因（enabled_enhancer_config_present / enhancer_output_stale）。
> 宿主按 `trigger` 分支处理，不依赖 artifact 键的有无推断语义。

#### 演进路径

| 阶段 | 能力 | 位置 |
|---|---|---|
| 当前（Phase 3.2） | finalize 后 notes + artifact 标记 | engine.py + handoff.py |
| Phase 4.4 | freshness gate：enhancer 产物 stale 时 state/ 记录 | runtime/gate.py |
| Phase 4+ | 宿主/CI 根据 stale signal 自动排队执行 | 宿主侧 |

> 不在 runtime 内核实现"自动执行外部可选工具"。

## 版本兼容策略

### .meta.json（自动管理，git ignored）

```json
{
  "generated_with": "0.4.16",
  "generated_at": "2026-04-16T06:45:00Z",
  "node_count": 142,
  "edge_count": 287,
  "community_count": 5
}
```

### 兼容矩阵

| 场景 | 适配层行为 |
|---|---|
| graphify 未安装 | 策略链检测失败 → warn + skip |
| graphify < MIN_VERSION | 同上 |
| patch 升级 | 默认增量；.meta.json/graph.json 异常 → 回退全量 |
| minor/major 升级 | `_needs_full_rebuild()` → 全量重建 |
| .meta.json 缺失/损坏 | 回退全量重建（fail-open） |
| graph.json 字段缺失 | `.get()` 防御 → placeholder |

> 原则：fail-open + 可回退。任何异常状态统一回退全量重建。

## 实现分层

| 层 | 文件 | 职责 | 状态 |
|---|---|---|---|
| 配置验证 | `runtime/config.py` | `blueprint_enhancers` 父键 | 改动 |
| 增强器抽象 | `installer/blueprint_enhancer.py` | 基类 + 注册表 + 注入引擎 | **新增** |
| Graphify 实现 | `installer/enhancers/graphify_enhancer.py` | 增强器 + plan 补充 + 标签 + 检测策略链 | **新增** |
| 编排脚本 | `scripts/blueprint_enhance.py` | 协调流程 | **新增** |
| README 发现 | `runtime/kb.py` | 子目录产物发现 | 改动 |
| .gitignore | `.gitignore` | 排除 graphify 重文件 | 追加 |
| blueprint 文件 | `blueprint/{background,design}.md` | auto-section 占位 | 追加 |
| graphify 核心 | （外部仓库） | 不改 | — |
