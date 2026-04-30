---
name: cross-review
description: "在开发完成后自动交叉评审代码变更。审查者运行在隔离的 LLM 会话中，不继承开发上下文，发现偏差和盲点。Advisory 模式：结论仅供参考，不自动阻断。"
---

## 何时触发

在 develop 阶段完成、代码已写入磁盘后触发。不要在规划阶段或未产生代码变更时触发。

前置条件：
- 工作区存在未评审的代码变更（已提交的 review range、已暂存的本轮变更，或可确认只包含本轮任务的未暂存变更）。
- `crossreview` CLI 已安装，版本为 `0.1.0a2+`（`pip install -U crossreview` 或 `pip install -e .`）。
- 默认 host-integrated 路径可用：宿主能在 fresh / isolated review context 中执行 `render-prompt` 产出的完整 prompt。

注释：Sopify Phase 4a 的默认路径不要求 CrossReview 自己配置模型、provider 或 API key；LLM 调用由当前宿主完成。只有使用 standalone fallback 的 `crossreview verify` 时，才需要 `CROSSREVIEW_MODEL` / `CROSSREVIEW_PROVIDER` / API key 或等价 `crossreview.yaml`。

## 默认流程（Host-integrated）

### Step 0 — 选择 diff source 并隔离 review range

CrossReview `0.1.0a2+` 支持三种确定性差异来源：

- `--staged`：优先用于本轮未提交变更的 pre-commit review，执行 `git diff --cached`，不要求创建 review commit。
- `--diff REF`：用于已提交或需要可复现 review range 的场景，执行 `git diff REF HEAD`。
- `--unstaged`：只在工作区未暂存变更可以确认全是本轮任务时使用，执行 `git diff`。

**0A — 选择推荐路径：**

[IF 本轮变更尚未提交，且可以安全区分本轮目标文件]
  只 stage 本轮 develop 产生的文件（基于任务清单中的目标文件），不使用 `git add -A`。
  设置 `DIFF_SOURCE="--staged"`。

[ELSE IF 本轮变更已提交，或用户要求审查提交范围]
  [IF 任务涉及多次提交]
    REF = HEAD~{提交数}
  [ELSE]
    REF = HEAD~1

  展示 REF 对应的 commit，让用户确认起点正确：

  ```bash
  git log -1 --oneline <REF>
  ```

  [ACTION: INFORM_USER] "Review 起点为：`{REF 对应的 commit 摘要}`。本轮 develop 的所有变更应在此之后。"
  若用户认为起点不对，让用户指定正确的 commit SHA 作为 REF。
  设置 `DIFF_SOURCE="--diff <REF>"`。

[ELSE IF 工作区存在未暂存变更，且可以确认全部属于本轮任务]
  设置 `DIFF_SOURCE="--unstaged"`。

[ELSE]
  跳过 advisory review，记录原因 `diff_source_not_isolated`，继续主流程。

重要：不要自动 `git add -A && git commit`。这会把工作区所有变更（包括无关草稿、未跟踪文件）一起提交，违反安全边界。

### Step 1 — 生成 ReviewPack

```bash
CR_TMP="$(mktemp -d)"
printf '%s\n' "$CR_TMP"
crossreview pack $DIFF_SOURCE \
  --intent "任务意图摘要" \
  > "$CR_TMP/pack.json"
```

若 exit code 非零，记录 `pack_failed` 并结束本次 advisory review，继续主流程。

参数说明：
- `--intent "任务意图摘要"` — 帮助审查者理解变更目标（推荐始终提供）。
- `--task ./task.md` — 任务描述文件；仅在文件真实存在时添加。
- `--context ./plan.md` — 额外上下文文件（可重复）；仅在文件真实存在时添加。
- `--focus <area>` — 聚焦区域（可重复）。

注释：`pack` 只做确定性打包，不调用 LLM，不需要 API key。
注释：如果后续命令不是在同一个 shell session 中执行，必须记录 `mktemp` 打印的实际目录，并把后续命令里的 `$CR_TMP` 显式替换为该目录；不要假设 shell 变量会跨 tool call 保留。

### Step 2 — 渲染 canonical reviewer prompt

```bash
crossreview render-prompt --pack "$CR_TMP/pack.json" > "$CR_TMP/prompt.md"
```

若 exit code 非零，记录 `render_prompt_failed` 并结束本次 advisory review，继续主流程。

注释：`render-prompt` 只把 ReviewPack 渲染成标准审查 prompt，不调用 LLM，不需要 API key。

### Step 3 — 宿主执行隔离审查

在 fresh / isolated host review context 中执行 `"$CR_TMP/prompt.md"` 的完整内容，并将原始审查输出保存为：

```bash
RAW_ANALYSIS="$CR_TMP/raw-analysis.md"
printf '%s\n' "$RAW_ANALYSIS"
```

注释：这里是保存路径约定；宿主隔离审查完成后，必须把 raw analysis 写入该文件，之后 Step 4 才能 ingest。

硬性约束：
- 不要把 develop 对话、作者推理链、未公开的自我解释放入 reviewer context。
- 不要在当前 develop 上下文中直接“自己审自己”，这不满足 CrossReview 的上下文隔离目标。
- 若宿主无法提供 fresh / isolated review context，记录原因 `host_isolation_unavailable` 并结束本次 host-integrated 审查（不得执行 Step 4）；若 standalone 前置条件满足可改走备用流程，否则继续主流程。不要伪装成已完成 CrossReview。

### Step 4 — Ingest 原始审查输出并读取 verdict

```bash
crossreview ingest \
  --raw-analysis "$RAW_ANALYSIS" \
  --pack "$CR_TMP/pack.json" \
  --model host_unknown \
  --prompt-source product \
  --prompt-version v0.1 \
  --format human
```

若 exit code 非零，记录 `ingest_failed` 并结束本次 advisory review，继续主流程。

命令成功时（exit code 0），输出格式为：

```text
CrossReview 0.1-alpha | artifact: <hash> | review_status: <status>

Intent: <intent>
Intent Coverage: covered/partial/unknown
Pack Completeness: 0.XX

Findings (N):
  [HIGH]  file.py:42 — 发现摘要
  [MED]   other.py — 另一个发现

Advisory Verdict: <verdict>
  Rationale: <理由>
```

关键字段：
- `review_status` — `complete` / `rejected` / `failed`
- `Advisory Verdict` — 见 Step 5 分支

### Step 5 — 根据 verdict 分支处理

[IF review_status != "complete"]
  [ACTION: LOG_WARNING] 记录非正常状态（rejected / failed），继续主流程，不阻断。
  [SKIP] 不进入以下 verdict 分支。

[IF Advisory Verdict == "pass_candidate"]
  [ACTION: CONTINUE]
  告知用户：评审未发现问题，代码可以继续推进。

[IF Advisory Verdict == "concerns"]
  [ACTION: SHOW_FINDINGS] 向用户展示所有 findings（按严重度排列）。
  [ACTION: ASK_USER] "评审发现以下问题：\n{findings}\n(A) 修改代码后重新评审 (B) 接受并继续 (C) 忽略"
  - 用户选 A → 修改代码，回到 Step 0 重新执行
  - 用户选 B 或 C → 继续主流程

[IF Advisory Verdict == "needs_human_triage"]
  [ACTION: SHOW_FINDINGS] 展示所有 findings。
  [ACTION: REQUEST_HUMAN] "评审发现需要人工判断的复杂问题，请审阅后决定。"
  等待用户明确指令后再继续。

[IF Advisory Verdict == "inconclusive"]
  [ACTION: LOG_WARNING] "评审结果不确定，可能由于上下文不足、隔离审查失败或模型限制。"
  继续主流程，不阻断。

## 备用流程（Standalone Verify）

仅在 host-integrated 路径不可用，且 standalone reviewer 配置已经存在时使用：

```bash
crossreview verify $DIFF_SOURCE --intent "任务意图摘要" --format human
```

可选参数同 Step 1（`--task`、`--context`、`--focus`）。

Standalone 前置条件：
- 已设置 `CROSSREVIEW_MODEL` / `CROSSREVIEW_PROVIDER` / `CROSSREVIEW_API_KEY_ENV`，或等价 `crossreview.yaml`。
- 对应 API key 环境变量存在。

注释：standalone fallback 会由 CrossReview CLI 直接调用 LLM API；这不是 Phase 4a 的默认宿主集成路径。

## 重要约束

- **Exit code 0 = 结果已产出**，不代表评审通过。必须读 `Advisory Verdict` 行判断。
- **Exit code 非零 = 命令执行失败**，无评审结果。记录错误，继续主流程。
- **Advisory 模式：verdict 仅供参考，不自动阻断任何流程。**
- 不要在无代码变更时运行（浪费 token）。
- 默认 host-integrated 路径为 `pack -> render-prompt -> host isolated review -> ingest`；`verify --diff` 只是 standalone fallback。
- `--format human` 用于终端展示，`--format json` 用于程序解析。

## 交付检查

- [ ] `crossreview pack` 成功生成 ReviewPack
- [ ] `crossreview render-prompt` 成功生成 canonical reviewer prompt
- [ ] 宿主 fresh / isolated review context 已产出 raw analysis
- [ ] `crossreview ingest --format human` 成功产出 ReviewResult
- [ ] Advisory Verdict 已读取并展示给用户
- [ ] concerns / needs_human_triage 时用户已被告知并做出决定
- [ ] 结果不阻断主流程（advisory only）
