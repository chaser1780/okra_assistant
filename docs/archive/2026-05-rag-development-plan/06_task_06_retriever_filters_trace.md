# Task 6：Hard Filter Retriever

目标：把 OKRA 投资场景的强约束放进检索层：日期不能穿越、基金不能混配、记忆不能复活、execution 不能污染。该任务是 Copilot 和 daily shadow 接入前的强制门槛。

## PR-12：QueryPlan 与 Hard Filters

范围：

- 新增 `scripts/rag_query_planner.py` 或 `app/rag_query_planner.py` 的共享核心。
- 定义 `RagQueryPlan`。
- 实现 hard filter 构造：
  - no-future
  - fund-match
  - memory visibility/lifecycle
  - execution boundary
  - stale/freshness 标记

QueryPlan 字段：

```json
{
  "query": "...",
  "query_date": "2026-05-20",
  "time_mode": "current|selected_date|historical|backtest",
  "intent": "fund_explain",
  "fund_codes": ["011840"],
  "domains": ["portfolio", "fund", "news", "decision", "memory"],
  "retrieval_profile": "copilot_qa",
  "allow_future_data": false,
  "include_negative_memory": false,
  "include_execution": false,
  "require_structured_facts": true,
  "top_k": 24,
  "token_budget": 6000
}
```

必须实现的过滤：

- `available_from <= query_date end_of_day`
- `as_of_date <= query_date`
- `published_at <= query_date end_of_day`
- 明确 `fund_code` 时主证据必须 `fund_codes contains fund_code` 或 `entity_id == fund_code`
- archived/rejected 只在 review/lesson profile 可见
- `learning_scope=execution_only` 不进入 fund/market/decision profile

验收：

```powershell
python -m unittest discover -s tests -p test_rag_no_future.py
python -m unittest discover -s tests -p test_rag_fund_match.py
python -m unittest discover -s tests -p test_rag_memory_visibility.py
python -m unittest discover -s tests -p test_rag_execution_boundary.py
```

这里的 `test_rag_execution_boundary.py` 只覆盖负向边界：普通 fund/market/decision profile 不召回 `learning_scope=execution_only` 的证据。真实 execution intent 能召回 execution 数据的正向能力放到 Later `PR-27`。

## PR-13：SQLite/FTS/Mock Retriever 与 MissingData

范围：

- 新增 `scripts/rag_retriever.py`。
- 新增 `scripts/rag_rerank.py`。
- 第一版支持 SQLite/FTS/mock 检索，不强依赖真实向量。
- 召回流程：
  1. query plan 生成 hard filters。
  2. SQLite 根据 metadata 先筛候选。
  3. FTS/mock/vector search 在候选集合内排序。
  4. rerank 合并 source tier、date fit、entity match、freshness、confidence、diversity。
  5. 无命中时返回 `missingData`，不放宽到未来数据或错配基金。

rerank 初始权重：

```text
final_score =
  vector_similarity * 0.45
  + source_tier_score * 0.18
  + date_fit_score * 0.14
  + entity_match_score * 0.12
  + freshness_score * 0.05
  + confidence_score * 0.04
  + diversity_score * 0.02
  - penalties
```

验收：

```powershell
python -m unittest discover -s tests -p test_rag_retriever_filters.py
```

## PR-14：Trace 落盘与 Rejected Samples

范围：

- 新增 `scripts/rag_trace.py`。
- `db/rag/traces/YYYY-MM-DD/{trace_id}.json` 落盘。
- trace 必填：
  - `trace_id`
  - `created_at`
  - `caller`
  - `query_plan`
  - `hard_filters`
  - `source_manifest_ids`
  - `candidate_count_before_filter`
  - `candidate_count_after_filter`
  - `rejected_samples`
  - `final_hits`
  - `missing_data`
  - `token_budget`
  - `evidence_pack_sha256`
  - `answer_citation_ids`
  - `fallback_reason`

验收：

```powershell
python -m unittest discover -s tests -p test_rag_retriever_filters.py
python scripts\rag_ingest.py --date 2026-05-20 --write --all
```

人工检查：

- 随机打开一个 trace，能看到哪些候选因未来数据、基金错配、memory visibility、execution boundary 被过滤。

## Task 6 完成定义

- no-future 违规数为 0。
- 明确 fund_code 主证据错配数为 0。
- 普通 profile 不召回 execution actual trades。
- 普通 profile 不召回 archived/rejected。
- 无命中返回 missingData，不静默放宽安全条件。
