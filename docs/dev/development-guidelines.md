# Sopify 开发规范

面向维护者与协作者。本文只约束日常开发协作边界；发布步骤、版本更新与 release smoke 仍以 `docs/dev/release-process.md` 为准。

---

## 1. 目的与范围

- 统一日常开发、合并与发布前的最小协作约束。
- 保持 `main` 可继续集成，并让 stable release 的来源清晰可追踪。
- 本文不重复 release 细节，不定义独立的 release branch 流程。

---

## 2. 主分支与发布线

- `main` 是唯一长期主分支。
- 对外发布版本使用 `tag + GitHub Release` 表达，不使用长期维护的 `release branch`。
- 当前默认模式是：`main + topic branches + release tags`。
- 只有在出现并行维护多个已发布版本、需要长期 backport 修复时，才重新评估是否引入 `release branch`。

---

## 3. 主题分支

- 日常开发使用短生命周期主题分支，通过 MR/PR 合入 `main`。
- 分支命名采用 `<type>/<topic>`。
- 若改动明确归属某个计划窗口，采用 `<type>/<plan>-<topic>`，其中 `plan` 只使用短标识，不带完整目录名。

推荐类型：

- `hotfix`
- `feature`
- `refactor`
- `docs`

推荐示例：

- `hotfix/plan-h-checkpoint-cancel`
- `feature/plan-a-cancel-semantics`
- `refactor/runtime-gate-cleanup`
- `docs/dev-guidelines`

不建议：

- 直接把完整 plan 目录名塞进分支名
- 一个分支同时承载 hotfix、语义增强、文档扩写等多个主题

---

## 4. 合并原则

- `main` 默认通过 MR/PR 合入，不把直推 `main` 作为常规流程。
- 一个分支只承载一个可验证的闭环主题。
- 合入前应完成与改动直接相关的最小验证与回归。
- `main` 上的提交应保持“可继续集成、可进入下一次 release”的基本质量。

---

## 5. 开发取舍

- Hotfix 以最小闭环为原则，只修当前错误链路，不顺手扩词表、扩状态模型或新增流程守卫。
- 本轮不解决但已识别的问题，应记录到对应的 plan 或 backlog，避免混入当前修复窗口。

---

## 6. 提交与验证

- 提交粒度以单一闭环为单位，避免把不同性质的改动揉进同一个提交。
- 新增共享源码文件后，必须显式纳入版本控制，不要依赖 `git commit -am` 覆盖新增文件。
- 若改动影响 runtime 契约、checkpoint、bridge、status/doctor 或 installer 行为，必须补对应回归测试。
- 对于文档-only 变更，不要求额外运行代码测试，但应避免与功能改动混提。

---

## 7. 与发布流程的关系

- stable release 从 `main` 上的已合入提交生成。
- README 首屏安装入口面向 latest stable release，不面向 `raw/main`。
- `raw/main` 入口仅用于开发者文档、调试或 inspect-first 场景，不进入对普通用户的主安装链路。
- 版本号、asset 渲染、GitHub Release 创建与 post-release smoke，统一遵循 `docs/dev/release-process.md`。
