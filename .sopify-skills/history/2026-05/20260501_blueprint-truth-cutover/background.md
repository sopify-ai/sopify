# Blueprint Truth Cutover — 背景

## 需求背景

Sopify 的架构方向已确认为 Protocol-first / Runtime-optional（ADR-016），蓝图骨架已稳定：

- 产品分层：Core / Default Workflow / Plugins
- 架构分层：Protocol / Validator / Runtime
- 削减预算：checkpoint 2、host action 5、route family 6、core state 6

但当前 runtime（~29K 行 / 66 模块）仍远超蓝图预算：checkpoint 5 种、host action 13 种、route 18 种、state 文件 8 个。协议层膨胀与轻量化方向正面冲突。

## 核心矛盾

方向已经定了，但 runtime 仍然在代表过去。

旧 P1–P4 路线图默认 runtime 仍是产品主体，在旧面上做收缩治理。这是最贵的路径：蓝图越写越好，runtime 却继续按旧惯性生长，两边渐行渐远。

## 为什么现在做

1. **产品尚处于早期阶段** — 无外部消费者依赖和生产级兼容承诺，兼容约束最小
2. **蓝图骨架已够稳定** — Core / Default Workflow / Plugins 分层、Protocol / Validator / Runtime 分层、削减预算均已硬写在 design.md，不需要等 draft 细节全部定型
3. **窗口成本极低** — 破坏旧兼容、删旧入口、废弃旧 API 在当前阶段代价趋近于零；越晚做越贵
4. **runtime 每多存在一天，就多固化一天错误形状** — 新功能、新修补继续在旧面上累积，增加未来迁移成本

## 已知局限

- protocol §6 Integration Contract 和 §7 Multi-host review wire contract 仍为 informative/draft，不阻塞 cutover 但限制新链路可证明的深度
- 完整 Validator 实现不在本轮范围
- Runtime 不会一次性降到 <20K 行最终目标

## 方案定位

本方案是 Sopify 当前最高优先级（P0+），高于 blueprint tasks.md 现有 P1–P4。目标是让 blueprint 成为唯一 forward baseline，runtime 降为迁移层/参考实现。不替代 P1–P4，而是重新定义它们的执行语境。
