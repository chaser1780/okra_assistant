# Subagent Notes

本次复杂拆分使用了 1 个只读子 agent 做并行审阅。

## 子 agent 会话

- 会话 id：`019e447a-07f4-7922-96cd-dec5be4a7086`
- 角色：只读 explorer
- 任务：阅读 `docs/okra_unified_rag_architecture.md`，聚焦第 15、18、16、17 节，把统一 RAG 蓝图拆成按阶段推进的 PR 依赖建议。

## 子 agent 关键建议

子 agent 建议把第一批 10 个 Task 拆成 8 批、约 24 个小 PR。主会话吸收后扩展为：

- PR-01 到 PR-25：第一批正式开发。
- PR-26 到 PR-27：Phase 7/8 延后开发。

核心依赖判断：

- T1 阻塞全部 RAG 模块。
- T2/T3/T4 阻塞 T5 的完整 ingest。
- T5 阻塞 T6 的真实检索测试。
- T6 阻塞 T8/T9，因为 no-future、fund-match、memory visibility 必须先落地。
- T7 不应阻塞 T6 的 SQLite/FTS/mock 检索，但阻塞真实向量召回上线。
- T8 不阻塞 T9，但建议先让 Copilot 消费 RAG，风险更小。
- T9 shadow 稳定后才允许 T10 默认接入。

需要单独评审的高风险 PR：

- `PR-12 hard filters`
- `PR-19 Copilot 接入`
- `PR-24 agent 默认接入`
- `PR-27 execution profile`

这些 PR 分别对应事实错配、日期穿越、旧链路稳定性、execution 数据污染风险，不能和 adapter 或 UI 大改混在一起。
