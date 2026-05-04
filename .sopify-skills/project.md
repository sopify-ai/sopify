# 项目技术约定

## Runtime 快照
- 项目名：sopify-skills
- 工作目录：`/Users/weixin.li/Desktop/Sopify/sopify-skills`
- 运行时目录：`.sopify-skills`
- 根配置：`sopify.config.yaml`
- 已识别清单：暂未识别
- 已识别顶层目录：tests、docs、scripts

## 使用约定
- 这里只沉淀可复用的长期技术约定。
- 一次性实现细节不默认写入本文件。
- 当约定发生变化时，应以代码现状为准并同步更新。

## 文档边界
- `project.md`：只放跨任务可复用的技术约定。
- `blueprint/background.md`：放长期目标、范围与非目标。
- `blueprint/design.md`：放模块、宿主、目录与知识消费契约。
- `blueprint/tasks.md`：只保留未完成长期项与明确延后项。

## Runtime 实现与测试约定

- `runtime/models.py` 是稳定公开 facade；`from runtime.models import X` 继续作为对外兼容入口。
- 具体实现收敛到 `runtime/_models/`，当前按 `core / decision / artifacts / summary / handoff` 分组，避免在公开路径下继续堆积单文件复杂度。
- facade 必须维护显式 `__all__`，保证 `from runtime.models import *` 的 surface 仍然可控。
- repo-local runtime 回归统一使用 `python3 -m unittest discover tests -v`，避免拆分后因手写文件列表漏测。
- repo-local 共享测试 helper 固定收敛到 `tests/runtime_test_support.py`；`tests/test_runtime_*.py` 负责按主题拆分具体 `TestCase`。
- bundle 对外继续保留 `.sopify-runtime/tests/test_runtime.py` 路径，但该文件只承担最小 smoke contract，不再复制 repo-local 全量 runtime 测试。
- 需要对绝对路径下的 bundle smoke 做便携校验时，统一使用 `python3 -m unittest discover -s <bundle-tests-dir> -p 'test_runtime.py' -v`，避免 `unittest` 把绝对路径误当成模块名。

## Develop 质量约定

- `continue_host_develop` 仍是宿主负责真实代码修改的正式模式；runtime 只负责 machine-readable quality contract、checkpoint callback 与 replay/handoff 落盘。
- develop 质量循环的正式发现顺序固定为：`.sopify-skills/project.md verify` > 项目原生脚本/配置 > `not_configured` 可见降级。
- develop 质量结果的正式字段固定为：`verification_source / command / scope / result / reason_code / retry_count / root_cause / review_result`。
- `result` 的稳定值域固定为：`passed / retried / failed / skipped / replan_required`；`root_cause` 的稳定值域固定为：`logic_regression / environment_or_dependency / missing_test_infra / scope_or_design_mismatch`。
- 当 `result == replan_required` 或 `root_cause == scope_or_design_mismatch` 时，宿主不得继续盲修；必须改走 `scripts/develop_callback_runtime.py` 的 checkpoint callback。
- 当前仓库暂不在 `project.md` 固定单一默认 verify 命令；在解释器基线统一到 Python 3.11+ 之前，未识别到稳定命令时应走 `not_configured` 可见降级，而不是假定默认测试入口存在。
