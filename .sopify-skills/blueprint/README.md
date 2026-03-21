# 项目蓝图索引

状态: L3 history-ready
工作目录: `/Users/weixin.li/Desktop/vs-code-extension/sopify-skills`
运行时目录: `.sopify-skills`
维护方式: Sopify 托管自动区块，说明区块允许人工补充。

## 当前目标

<!-- sopify:auto:goal:start -->
- 项目：`sopify-skills`。
- 长期目标与范围收敛到 `./background.md`；本索引只保留入口与状态，不展开正文。
<!-- sopify:auto:goal:end -->

## 项目概览

<!-- sopify:auto:overview:start -->
- blueprint: 长期项目真相，默认入库
- plan: 按需创建的活动方案
- history: 收口后生成的历史归档
- replay: 可选回放能力
<!-- sopify:auto:overview:end -->

## 架构地图

<!-- sopify:auto:architecture:start -->
```text
.sopify-skills/
├── blueprint/
├── plan/
├── history/
├── state/
└── replay/
```
<!-- sopify:auto:architecture:end -->

## 关键契约

<!-- sopify:auto:contracts:start -->
- bootstrap 只创建最小长期知识骨架
- 深层 blueprint 文件在首次进入 plan 生命周期时补齐，或在 `kb_init: full` 下提前物化
- 仅在显式 `~go finalize` 收口时生成 history
<!-- sopify:auto:contracts:end -->

## 当前焦点

<!-- sopify:auto:focus:start -->
- 当前活动 plan：暂无。
- history 归档：已可用；最近归档为 `../history/2026-03/20260320_preferences-preload-v1`。
<!-- sopify:auto:focus:end -->

## 深入阅读入口

<!-- sopify:auto:read-next:start -->
- [项目技术约定](../project.md)
- [蓝图背景](./background.md)
- [蓝图设计](./design.md)
- [蓝图任务](./tasks.md)
- [变更历史](../history/index.md)
- 最近归档：`../history/2026-03/20260320_preferences-preload-v1`
<!-- sopify:auto:read-next:end -->
