# OKRA Unified RAG Development Plan

本目录把 `docs/okra_unified_rag_architecture.md` 从“整体蓝图”拆成后续可以直接进入开发的任务包。

核心落地原则：

- 先底座，后消费方：先配置、schema、source adapter、ingest、retriever、trace，再接 Copilot，最后 shadow 每日分析。
- 先可回滚，后默认启用：所有 PR 都保留 `rag.enabled=false`、`fallback_to_legacy=true` 或单独 profile 开关。
- 硬约束前置：日期无穿越、基金不混配、记忆生命周期、execution 隔离必须在 prompt 之前由检索层保证。
- 先 mock/FTS，再真实向量：SQLite/mock retriever 不被 embedding API 阻塞；真实 embedding 独立 PR 接入。
- 每个 PR 可单独验收、单独回退，避免一次性重写当前稳定 daily pipeline。

## 文件索引

| 文件 | 用途 |
|---|---|
| `00_pr_dependency_map.md` | 全局批次、PR 依赖、开发顺序、风险卡点 |
| `01_task_01_foundation.md` | Task 1：RAG 配置、数据模型、SQLite store |
| `02_task_02_long_memory_adapter.md` | Task 2：长期记忆 adapter |
| `03_task_03_portfolio_llm_context_adapter.md` | Task 3：portfolio 与 llm_context adapter |
| `04_task_04_validated_committee_adapter.md` | Task 4：validated advice 与 committee adapter |
| `05_task_05_ingest_cli.md` | Task 5：rag_ingest CLI 与 manifest |
| `06_task_06_retriever_filters_trace.md` | Task 6：hard filter、retriever、rerank、trace |
| `07_task_07_embedding_vector.md` | Task 7：embedding client、cache、vector store |
| `08_task_08_copilot_rag.md` | Task 8：Copilot RAG 接入 |
| `09_task_09_daily_shadow.md` | Task 9：daily shadow 接入 |
| `10_task_10_agent_default_admin.md` | Task 10：agent 默认接入与管理维护 |
| `11_later_phase_backlog.md` | Phase 7/8 延后项：decision/memory/review/replay、execution profile |
| `acceptance_matrix.md` | 分批验收命令、质量门禁、人工问题集 |
| `subagent_notes.md` | 本轮子 agent 会话 id 与只读拆分建议摘要 |

## 推荐执行路线

```text
Batch A: PR-01..PR-03   RAG disabled foundation
Batch B: PR-04..PR-09   Source adapters
Batch C: PR-10..PR-11   Ingest and manifest
Batch D: PR-12..PR-14   Query plan, filters, retriever, trace
Batch E: PR-15..PR-17   Embedding and vector backend
Batch F: PR-18..PR-20   Copilot RAG
Batch G: PR-21..PR-23   Daily shadow
Batch H: PR-24..PR-25   Agent default and admin observability
Later:  PR-26..PR-27   Decision/memory/review/replay and execution profile
```

最重要的安全门：

- `PR-12`：hard filters 必须先通过 no-future、fund-match、memory visibility、execution boundary 测试。
- `PR-19`：Copilot 接入必须保留旧 `_copilot_evidence()` fallback。
- `PR-24`：agent 默认接入必须先有 shadow 评估结果，且 legacy fallback 始终可用。
- `PR-27`：execution profile 必须单独安全评审，默认关闭，不能污染 fund/market/decision profile。
