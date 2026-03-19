# Skill 标准对齐蓝图

状态: 待评审
创建日期: 2026-03-19
定位: 面向 `Anthropic Agent Skills + Gemini CLI Agent Skills` 的专项重构蓝图

## 背景

过去这个仓库主要沿着 `runtime control plane + host prompt layer + installer` 的方向演进，工程化程度已经不低，但它对“skill 本身应该如何被发现、加载、约束、评测”这件事并没有形成与最新官方规范一致的分层。[A1][A2][A3][A4][G1][G2][G3]

这带来一个根本问题：

- 仓库现在更像“runtime 平台”，而不是“可移植 skill 标准实现”
- `SKILL.md` 更多是宿主提示层文档，不是机器契约的单一事实源
- skill 包结构、发现层级、权限边界、激活方式、评测方式，都和官方最新方向存在偏差

## 当前结论

### 1. 发现层不够通用

Anthropic 与 Gemini 都把“轻 metadata 预加载 + 需要时再激活/读取正文”当成默认模型。[A1][A2][G1][G3]

Gemini 进一步明确了三层发现模型：

- workspace skills
- user skills
- extension skills

并且把 `.agents/skills` 作为跨 agent 工具兼容的通用 alias。[G1]

相对地，当前仓库的 skill 发现还偏 `Codex` 私有实现，跨宿主抽象不够完整。这会直接限制后续接入 Gemini 或更通用的 agent runtime。

### 2. Skill 本体过重，渐进披露没有真正落到目录结构

Anthropic 明确强调 progressive disclosure：启动时只加载 `name` / `description`，触发后再读 `SKILL.md`，更细节的材料继续放到额外文件中按需读取。[A1][A2]

Anthropic 官方还给了比较明确的约束：

- `SKILL.md` body 最好控制在 500 行以内
- 接近上限时应拆到额外文件
- 引用层级不要太深
- 长内容应放到 reference / examples / scripts 这类结构里。[A3]

Gemini 也已经把推荐目录结构写得很明确：

- `SKILL.md`
- `scripts/`
- `references/`
- `assets/` [G2]

当前仓库虽然已经使用 `SKILL.md`，但大多数 skill 仍是“大而全单文件”，没有把长模板、参考资料、确定性执行逻辑拆出去。这会让 skill 激活后的上下文密度过高，也会让维护越来越困难。

### 3. Source of truth 倒置

官方语义里，skill package 本身应当是可移植能力单元：目录、frontmatter、正文、附属资源共同构成可复用 skill。[A1][A2][G2]

当前仓库则更接近：

- Python `builtin_catalog` 才是机器真相
- `SKILL.md` 主要是人类说明和宿主提示材料
- router / runtime / catalog 三处共同决定 skill 语义

这种设计短期便于收口 runtime，但长期会伤害：

- skill 的可移植性
- skill 的可组合性
- skill 的可审查性
- skill 的“所见即所得”维护体验

### 4. 权限模型缺失

Anthropic 在 sub-agents 里已经把“独立上下文、独立 system prompt、独立 tool access、独立 permission mode”做成了正式能力。[A4]

Gemini 的 `activate_skill` 也强调：激活时会向用户展示 skill 名称、用途、将获得访问权限的目录，并在确认后再注入资源。[G1][G3]

而当前仓库的 runtime skill 执行虽然有 entry contract，但缺：

- 工具白名单/黑名单语义
- 目录访问边界
- 网络能力声明
- 宿主能力要求
- 权限升级策略

这意味着它更像“能跑”，而不是“边界清晰地可跑”。

### 5. 缺少 skill authoring eval

Anthropic 明确把“build evaluations first / test with all models you plan to use / observe how Claude navigates Skills”列为 best practice。[A3]

当前仓库测试主要覆盖：

- runtime route
- state/handoff
- installer/payload
- bundle compatibility

但还缺少 skill authoring 层面的核心评测：

- skill 是否容易被正确触发
- description 是否过宽/过窄
- 拆分后是否提高了命中率与成功率
- 不同模型是否都能正确导航 skill 资源

## 蓝图目标

### 目标 1: 建立标准化 skill package

把 skill 目录本身提升为第一事实源，至少统一到以下结构：

- `SKILL.md`
- `skill.yaml` 或等价 manifest
- `scripts/`
- `references/`
- `assets/`

其中：

- `SKILL.md` 只保留入口说明、触发语义、流程骨架
- 长模板进入 `assets/`
- 静态规范进入 `references/`
- 确定性执行逻辑进入 `scripts/`

### 目标 2: 重做 discovery tier

发现优先级至少对齐到：

1. workspace
2. user
3. bundled / extension

并支持以下 alias：

- `.agents/skills`
- `.gemini/skills`
- `~/.agents/skills`
- `~/.gemini/skills`
- 现有 `~/.codex/skills`
- 现有 `~/.claude/skills`

目标不是复制 Gemini 的 UI，而是吸收它的分层与兼容路径设计。[G1]

### 目标 3: 让 skill package 生成 runtime catalog，而不是反过来

保留 `runtime/builtin_catalog.py` 作为运行时加速产物可以接受，但它应该从 skill package 生成，而不是手工维护。

理想顺序：

1. skill package 定义元数据与资源
2. build/generate 步骤产出 builtin catalog / manifest
3. runtime 消费 catalog

### 目标 4: 建立权限与宿主能力声明

skill 元数据应显式声明最小边界，例如：

- `allowed_paths`
- `requires_network`
- `tools`
- `disallowed_tools`
- `host_support`
- `permission_mode`

这里不必完全照搬 Anthropic sub-agents frontmatter，但必须把“运行边界”从隐式约定升级为显式契约。[A4][G3]

### 目标 5: 把评测纳入标准流程

至少形成一组面向 skill 的回归评测：

- discovery/precedence eval
- activation/selection eval
- skill navigation eval
- long-context split regression eval
- cross-model smoke eval

## P0 / P1 方向

### P0

- discovery tier 改造，先补 `.agents/skills` 兼容层
- skill 包结构改造，先把 builtin skills 从大单文件拆出 `references/` / `assets/`
- 建立 skill package -> catalog 的单向生成链路
- 为 runtime skill 增加最小权限元数据
- 建立首批 skill authoring 评测基线

### P1

- 把 host adapter 从 `Codex/Claude` 扩展为更通用的 agent host abstraction
- 补 extension tier / bundled tier 的统一发现与覆盖规则
- 为 skill 激活增加更强的宿主能力声明与 fail-closed 行为
- 补多模型评测与 skill 导航可观测性

## 非目标

- 本轮不重写既有 runtime control plane 主链路
- 本轮不把 Gemini CLI 直接作为正式宿主接入对象
- 本轮不承诺一次性消除所有旧 prompt-layer 文档

## 后续评审问题

后续再次分析时，建议优先确认这几个问题：

1. skill package 的最小 manifest 字段是否采用 `skill.yaml`，还是直接扩展 frontmatter
2. `.agents/skills` 是否上升为仓库默认标准路径
3. builtin catalog 是实时扫描生成，还是发布时静态生成
4. runtime skill 的权限边界由宿主执行还是 runtime 自验
5. skill eval 放在 `tests/` 还是独立 `evals/`

## 参考文献

- [A1] Anthropic, “Equipping agents for the real world with Agent Skills”, 2025-10-16, https://claude.com/blog/equipping-agents-for-the-real-world-with-agent-skills
- [A2] Anthropic, “Agent Skills - Overview”, https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- [A3] Anthropic, “Skill authoring best practices”, https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- [A4] Anthropic, “Create custom subagents”, https://docs.anthropic.com/en/docs/claude-code/sub-agents
- [G1] Gemini CLI, “Agent Skills”, https://geminicli.com/docs/cli/skills/
- [G2] Gemini CLI, “Creating Agent Skills”, https://geminicli.com/docs/cli/creating-skills/
- [G3] Gemini CLI, “Activate skill tool (`activate_skill`)", https://geminicli.com/docs/tools/activate-skill/
- [G4] Gemini CLI, “Release notes”, https://geminicli.com/docs/changelogs/
