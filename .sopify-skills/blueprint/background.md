# 知识布局 V2 蓝图背景

状态: 已与 runtime V2 目录契约对齐

## 背景

Sopify 的知识资产已经从“散落的文档集合”收敛为固定分层：

1. `L0 index`: `blueprint/README.md`
2. `L1 stable`: `project.md + blueprint/{background,design,tasks}`
3. `L2 active`: `plan/YYYYMMDD_feature/`
4. `L3 archive`: `history/index.md + history/YYYY-MM/...`
5. `runtime`: `state/*.json + replay/`

本轮的目标不是再引入新层，而是把对外文档、skills、templates 与 runtime 的世界观一次性切到同一套 V2 口径。

## 主要问题

旧口径存在以下问题：

1. 仍把 `wiki/*` 作为默认长期知识结构，对外说明与 runtime 实现不一致。
2. `blueprint/README.md` 容易膨胀成长说明书，不再像入口索引。
3. plan 输出没有把评分块固定为默认结构，方案评审口径不稳定。
4. `blueprint_obligation` 仍在部分文档中被当成主要概念，和 `knowledge_sync` 的正式语义冲突。

## 本轮目标

1. 切掉旧 `wiki/*` 主结构描述，不再对外承诺双轨。
2. 把 `blueprint/README.md` 收缩成纯索引页。
3. 用 `knowledge_sync` 固定 finalize 前的长期知识同步责任。
4. 把“方案质量 / 落地就绪 / 评分理由”固定纳入正式 plan 包输出。

## 非目标

- 不新增新的知识层。
- 不在本轮重做 runtime 的主链路实现。
- 不把 history 正文纳入默认长期上下文。
