# 2026-05-20 RAG Development Handoff

本记录用于下次继续统一 RAG 升级时快速接上。当前实现仍然默认关闭，不接入现有 Copilot、daily pipeline 或 multi-agent 主链路。

## 已完成范围

- Batch A / Task 1：RAG 配置、模型、SQLite metadata store。
- Batch B / Task 2-4：source adapters。
  - `long_memory`
  - `portfolio_state`
  - `llm_context`
  - `evidence_item`
  - `validated_advice`
  - `committee_bundle`
- Batch C / Task 5：`rag_ingest.py --dry-run` 与 `--write`。
- Batch D / Task 6：QueryPlan、hard filters、SQLite/mock retriever、rerank、trace 落盘。

## 新增/修改文件

- `config/rag.toml`
- `scripts/rag_config.py`
- `scripts/rag_models.py`
- `scripts/rag_index_store.py`
- `scripts/rag_sources.py`
- `scripts/rag_ingest.py`
- `scripts/rag_query_planner.py`
- `scripts/rag_retriever.py`
- `scripts/rag_rerank.py`
- `scripts/rag_trace.py`
- `tests/test_rag_config.py`
- `tests/test_rag_models.py`
- `tests/test_rag_index_store.py`
- `tests/test_rag_sources.py`
- `tests/test_rag_memory_visibility.py`
- `tests/test_rag_ingest.py`
- `tests/test_rag_retriever_filters.py`
- `tests/test_rag_no_future.py`
- `tests/test_rag_fund_match.py`
- `tests/test_rag_execution_boundary.py`

## 真实数据验证

已执行：

```powershell
python scripts\rag_ingest.py --date 2026-05-20 --dry-run --all
python scripts\rag_ingest.py --date 2026-05-20 --write --all
python scripts\rag_ingest.py --date 2026-05-20 --write --all
```

结果：

- `documents`: 356
- `chunks`: 356
- `active_manifests`: 5
- `ingest_runs`: 2
- source 分布：
  - `long_memory`: 85
  - `portfolio_state`: 16
  - `llm_context`: 29
  - `evidence_item`: 188
  - `validated_advice`: 22
  - `committee_bundle`: 16

已做一次真实检索 smoke：

- 查询：`人工智能基金今天风险来自哪里`
- 日期：`2026-05-20`
- fund code：`011840`
- 结果：命中 `committee_bundle`、`validated_advice`、`evidence_item`、`portfolio_state`、`llm_context`
- trace：`db/rag/traces/2026-05-20/ragq_55f1cf5999984935.json`

## 已通过测试

```powershell
python -m unittest discover -s tests -p "test_rag_*.py"
python -m py_compile scripts\rag_config.py scripts\rag_models.py scripts\rag_index_store.py scripts\rag_sources.py scripts\rag_ingest.py scripts\rag_query_planner.py scripts\rag_retriever.py scripts\rag_rerank.py scripts\rag_trace.py
python -m unittest discover -s tests -p test_config_wiring.py
python -m unittest discover -s tests -p test_pipeline_logic.py
```

`test_rag_*.py` 当前 30 个测试通过。

## 重要实现约束

- `rag.enabled=false`，当前不影响主链路。
- `rag_ingest.py --dry-run` 不写 `db/rag/rag.sqlite`。
- `--write` 写 `db/rag`，可删除回滚，不影响原始业务数据。
- source adapter 只读原始 artifact，不修改 `long_memory_store.py`、`build_llm_context.py`、`validated_advice` 等主链路。
- 普通 profile 默认过滤：
  - future data
  - fund mismatch
  - `archived/rejected/superseded` memory
  - `learning_scope=execution_only`
  - `source_kind=execution_sync`

## 下次建议入口

继续按文档进入 Batch E / Task 7：

1. 新增 `scripts/rag_embedding_client.py`，先实现 embedding config/probe/dry-run/mock fallback。
2. 新增 embedding cache 行为，按 `model + text_sha256` 避免重复请求。
3. 新增 `scripts/rag_vector_store.py` 接口，第一版仍以 mock/sqlite 为默认，真实 Chroma/embedding 单独开关。

如果想先更稳，也可以在进入 embedding 前补一组 retriever 真实索引测试：从 `db/rag/rag.sqlite` 查询 `011840`、`017641`、历史日期、review profile 的 archived memory 行为。
## 2026-05-20 Continued Update: Task 7-8

This section records the continuation after the first foundation/retriever handoff.

Completed:

- Batch E / Task 7: embedding client, vector-store shim, embedding cache, and ingest embedding flags.
- Batch F / Task 8: Copilot RAG evidence pack, Web API integration, Copilot prompt/fallback support, and frontend response-field handling.

New files:

- `scripts/rag_embedding_client.py`
- `scripts/rag_vector_store.py`
- `app/rag_answering.py`
- `app/rag_service.py`
- `tests/test_rag_embedding_client.py`
- `tests/test_web_api_rag_copilot.py`

Key modified files:

- `scripts/rag_config.py`
- `scripts/rag_index_store.py`
- `scripts/rag_ingest.py`
- `app/web_api.py`
- `app/copilot_service.py`
- `frontend/src/lib/types.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/components/okra/CopilotPanel.tsx`

Current behavior:

- `config/rag.toml` still has `enabled=false`, so current Copilot/daily pipeline behavior remains legacy by default.
- When `rag.enabled=true`, `OkraWebApi.explain()` builds a Copilot RAG pack first, calls the same Copilot LLM path, and returns compatible fields plus `traceId`, `citations`, `retrieval`, and `traceSummary`.
- If RAG pack construction fails, Web API falls back to `_copilot_evidence()`.
- If LLM fails after RAG retrieval, local fallback now summarizes the trace and citations.
- Frontend `askCopilot()` now accepts the expanded response; `CopilotPanel` stores and lightly displays mode, source date, trace id, hit count, and up to four citations.

Latest validation:

```powershell
python -m unittest discover -s tests -p "test_rag_*.py"
python -m unittest discover -s tests -p test_web_api_rag_copilot.py
python -m unittest discover -s tests -p test_web_api_long_memory.py
python -m unittest discover -s tests -p test_config_wiring.py
python -m unittest discover -s tests -p test_pipeline_logic.py
python -m py_compile scripts\rag_config.py scripts\rag_models.py scripts\rag_index_store.py scripts\rag_sources.py scripts\rag_ingest.py scripts\rag_query_planner.py scripts\rag_retriever.py scripts\rag_rerank.py scripts\rag_trace.py scripts\rag_embedding_client.py scripts\rag_vector_store.py app\rag_answering.py app\rag_service.py app\web_api.py app\copilot_service.py
cd frontend
npm run build
```

Real-index Copilot smoke:

- The repository config remained default-disabled; the smoke patched `load_rag_config` in-process only.
- Query: `人工智能基金今天风险来自哪里`
- Date: `2026-05-20`
- Fund code: `011840`
- Result: `mode=rag_llm`, `traceId=ragq_d9aea057686e4132`, `citations=8`
- Retrieval: `candidateCountBeforeFilter=356`, `candidateCountAfterFilter=91`, `missingData=[]`
- Hit source kinds: `committee_bundle`, `evidence_item`, `llm_context`, `portfolio_state`, `validated_advice`

Next suggested entrypoint:

- Continue with Batch G / Task 9 Daily Shadow.
- Add optional RAG ingest/eval hooks to `scripts/run_daily_pipeline.py` without changing final advice.
- Add shadow RAG fields to `scripts/agent_inputs.py` beside legacy evidence.
- Add `scripts/rag_eval.py` for legacy-vs-RAG comparison output.

## 2026-05-20 Continued Update: Task 9

Completed:

- Batch G / Task 9 Daily Shadow is now implemented.
- `config/rag.toml` and `scripts/rag_config.py` include `[rag.agent_shadow]` with:
  - `enabled=false`
  - `write_trace=true`
  - `inject_into_prompt=false`
  - `compare_legacy=true`
- `scripts/rag_eval.py` writes `db/rag/eval/YYYY-MM-DD.json` and compares legacy evidence-index retrieval with RAG shadow retrieval.
- `scripts/run_daily_pipeline.py` supports optional shadow hooks:
  - `--rag-shadow`
  - `--rag-strict`
  - config-driven `rag.agent_shadow.enabled`
- Shadow failures are degraded/non-blocking unless `--rag-strict` is passed.
- `scripts/agent_inputs.py` preserves legacy `retrieved_evidence`; with shadow enabled it adds:
  - `rag_retrieval_trace_id`
  - `rag_legacy_diff`
  - `rag_retrieved_evidence` only if `inject_into_prompt=true`
- `scripts/run_multiagent_research.py` records RAG trace/hit/fallback summary in workflow trace without changing default prompts.

New files:

- `scripts/rag_eval.py`
- `tests/test_rag_eval.py`

Additional modified files:

- `config/rag.toml`
- `scripts/run_daily_pipeline.py`
- `scripts/agent_inputs.py`
- `scripts/run_multiagent_research.py`
- `tests/test_pipeline_logic.py`
- `tests/test_multiagent_and_review.py`

Task 9 validation:

```powershell
python -m unittest discover -s tests -p test_rag_eval.py
python -m unittest discover -s tests -p test_pipeline_logic.py
python -m unittest discover -s tests -p test_multiagent_and_review.py
python -m unittest discover -s tests -p "test_rag_*.py"
python -m py_compile scripts\rag_config.py scripts\rag_models.py scripts\rag_index_store.py scripts\rag_sources.py scripts\rag_ingest.py scripts\rag_query_planner.py scripts\rag_retriever.py scripts\rag_rerank.py scripts\rag_trace.py scripts\rag_embedding_client.py scripts\rag_vector_store.py scripts\rag_eval.py scripts\agent_inputs.py scripts\run_daily_pipeline.py scripts\run_multiagent_research.py app\rag_answering.py app\rag_service.py app\web_api.py app\copilot_service.py
cd frontend
npm run build
```

Real eval smoke:

```powershell
python scripts\rag_eval.py --date 2026-05-20 --compare-legacy
```

Output:

- `db/rag/eval/2026-05-20.json`
- `legacy.available=true`
- `rag.agent_count=11`
- metrics: `hit_count=616`, `stale_hit_count=0`, `no_future_violation_count=0`

Next suggested entrypoint:

- Continue with Batch H / Task 10 Default/Admin.
- Keep the default off until shadow results are reviewed.
- Add status/admin API and system-page visibility for RAG enabled/shadow/fallback, recent ingest, document counts, trace, eval, and source counts.

## 2026-05-21 Stage Closeout: Task 10 Maintenance Baseline

This section records the stopping point before the next work session. No production-default behavior was changed in this closeout.

Completed / verified in this closeout:

- Confirmed current RAG default remains off:
  - `rag.enabled=false`
  - `rag.agent_shadow.enabled=false`
  - `rag.embedding.enabled=false`
  - `rag.vector_store.backend=sqlite_mock`
- Confirmed the Task 10 maintenance baseline exists in `scripts/rag_maintenance.py`.
- Verified maintenance status and integrity against the local RAG SQLite index.
- Verified the current RAG test suite still passes.

Current RAG index snapshot from `python scripts\rag_maintenance.py --status`:

- `documents=356`
- `chunks=356`
- `active_manifests=5`
- `source_manifests=20`
- `ingest_runs=4`
- `query_traces=79`
- `embedding_cache=20`
- source counts:
  - `committee_bundle=16`
  - `evidence_item=188`
  - `llm_context=29`
  - `long_memory=85`
  - `portfolio_state=16`
  - `validated_advice=22`
- embedding status:
  - `ok=20`
  - `pending=336`
- latest eval:
  - path: `db/rag/eval/2026-05-20.json`
  - `legacy.available=true`
  - `rag.agent_count=11`
  - `hit_count=616`
  - `stale_hit_count=0`
  - `no_future_violation_count=0`

Closeout validation:

```powershell
python -m unittest discover -s tests -p "test_rag_*.py"
python -m py_compile scripts\rag_maintenance.py
python scripts\rag_maintenance.py --check-integrity
python scripts\rag_maintenance.py --status
```

Results:

- `test_rag_*.py`: 38 tests passed.
- `rag_maintenance.py` compile check passed.
- SQLite `PRAGMA integrity_check`: `ok`.
- Status command returned the snapshot above.

Important unfinished Task 10 work:

- PR-24 Agent Profiles default接入 has not been enabled. Keep using shadow/off mode until the shadow results are reviewed.
- Admin API endpoints are not yet implemented:
  - `GET /api/rag/status`
  - `POST /api/rag/search`
  - `POST /api/rag/reindex`
  - `GET /api/rag/trace?id=...`
  - `POST /api/rag/eval`
- System page / settings page visibility is not yet implemented.
- `scripts/rag_maintenance.py` currently supports status, trace lookup, integrity check, and vacuum. The planned rebuild / purge-domain commands from Task 10 still need implementation.

Recommended next entrypoint:

1. Add focused tests for RAG admin/status API, likely `tests/test_web_api_rag_admin.py`.
2. Wire read-only admin methods into `OkraWebApi` first: status, trace, search/eval smoke.
3. Add the frontend system-page visibility after API tests pass.
4. Only after that, revisit PR-24 agent default profiles. Keep `rag.enabled=false` and `rag.agent_shadow.enabled=false` unless explicitly turning on a review run.

## 2026-05-21 Continued Update: Task 10 Admin and Agent Default

Completed in this session:

- PR-25 Admin API and observability:
  - `GET /api/rag/status`
  - `GET /api/rag/trace?id=...`
  - `POST /api/rag/search`
  - `POST /api/rag/reindex`
  - `POST /api/rag/eval`
  - `POST /api/rag/maintenance`
- System page now receives `system.ragRuntime` and displays:
  - RAG enabled / shadow / fallback
  - document / chunk counts
  - embedding pending / error counts
  - source counts
  - latest eval
  - latest traces
- `scripts/rag_maintenance.py` now supports:
  - `--status`
  - `--trace`
  - `--check-integrity`
  - `--vacuum`
  - `--rebuild --domain ...`
  - `--purge-domain ...`
- `--purge-domain` only deactivates RAG index rows and active manifests. It does not delete original business artifacts.
- PR-24 Agent default profile support is implemented behind config:
  - `rag.agent_default.enabled=false` remains the checked-in default.
  - Agent profiles are present in `config/rag.toml`.
  - When explicitly enabled, `agent_inputs.py` can use RAG evidence first.
  - If RAG fails or hit count is below `min_hits`, legacy `retrieve_agent_evidence()` remains the fallback.
  - `run_multiagent_research.py` records RAG backend/default/shadow/fallback and active manifest hash in workflow metadata.

New files:

- `tests/test_web_api_rag_admin.py`
- `tests/test_rag_maintenance.py`

Key modified files:

- `config/rag.toml`
- `scripts/rag_config.py`
- `scripts/agent_inputs.py`
- `scripts/run_multiagent_research.py`
- `scripts/rag_maintenance.py`
- `app/web_api.py`
- `app/web_api_services.py`
- `frontend/src/lib/types.ts`
- `frontend/src/app/pages/SystemPage.tsx`
- `tests/test_multiagent_and_review.py`

Default behavior after this session:

- RAG remains off by default:
  - `rag.enabled=false`
  - `rag.agent_shadow.enabled=false`
  - `rag.agent_default.enabled=false`
  - `rag.embedding.enabled=false`
- Current Copilot and daily multi-agent behavior remains legacy unless RAG is explicitly enabled in config or by admin/search/eval calls.

Validation run:

```powershell
python -m unittest discover -s tests -p "test_rag_*.py"
python -m unittest discover -s tests -p test_web_api_rag_admin.py
python -m unittest discover -s tests -p test_multiagent_and_review.py
python -m unittest discover -s tests -p test_pipeline_logic.py
python -m py_compile scripts\rag_config.py scripts\rag_models.py scripts\rag_index_store.py scripts\rag_sources.py scripts\rag_ingest.py scripts\rag_query_planner.py scripts\rag_retriever.py scripts\rag_rerank.py scripts\rag_trace.py scripts\rag_embedding_client.py scripts\rag_vector_store.py scripts\rag_eval.py scripts\rag_maintenance.py scripts\agent_inputs.py scripts\run_multiagent_research.py app\rag_answering.py app\rag_service.py app\web_api.py app\web_api_services.py
python scripts\rag_maintenance.py --check-integrity
python scripts\rag_maintenance.py --status
cd frontend
npm run build
```

Results:

- `test_rag_*.py`: 40 tests passed.
- `test_web_api_rag_admin.py`: 8 tests passed.
- `test_multiagent_and_review.py`: 24 tests passed.
- `test_pipeline_logic.py`: 17 tests passed.
- Python compile checks passed.
- SQLite integrity check returned `ok`.
- Frontend build passed.

Current local RAG status after validation:

- `enabled=false`
- `documents=356`
- `chunks=356`
- `active_manifests=5`
- `source_manifests=20`
- `embedding_cache=20`
- `query_traces=79`
- `ingest_runs=4`
- `embeddingStatus.ok=20`
- `embeddingStatus.pending=336`

Recommended next entrypoint:

1. Run one explicit shadow/default review using real current-day data before changing any default config:
   - `python scripts\rag_ingest.py --date <YYYY-MM-DD> --write --all`
   - `python scripts\rag_eval.py --date <YYYY-MM-DD> --compare-legacy`
   - optional temporary config-only run with `rag.agent_default.enabled=true` and `--mock`.
2. Review `db/rag/eval/<date>.json`, `workflow_trace.json`, and system-page RAG card.
3. Only if the reviewed traces are acceptable, consider turning on `rag.agent_default.enabled` for selected agents rather than globally.

## 2026-05-21 Continued Update: PR-26 Decision / Memory / Review / Replay Profiles

Completed in this session:

- Added optional PR-26 profile evidence support behind config:
  - `rag.profile_evidence.enabled=false` remains the checked-in default.
  - `rag.profile_evidence.decision.enabled=false`
  - `rag.profile_evidence.memory.enabled=false`
  - `rag.profile_evidence.review.enabled=false`
  - `rag.profile_evidence.backtest.enabled=false`
- Added `scripts/rag_profile_evidence.py` as the shared helper for:
  - decision evidence packs: only `committee_bundle` / `validated_advice`, and only after an existing committee bundle is present.
  - memory checks: same-domain / same-entity retrieval before memory write, with duplicate permanent detection.
  - review packs: archived/rejected memory can be retrieved only as labeled negative examples.
  - backtest packs: query date is the replay date, `allow_future_data=false`, and each pack includes a no-future audit.
- Wired optional packs into:
  - `scripts/generate_llm_advice.py`
  - `scripts/run_long_memory_analysis.py`
  - `scripts/review_advice.py`
  - `scripts/run_replay_experiment.py`
- Default-disabled behavior stays clean: disabled PR-26 packs are not injected into prompts or written into review/replay/memory artifacts.
- PR-27 execution recall remains deferred. PR-26 profiles do not enable execution retrieval.

New files:

- `scripts/rag_profile_evidence.py`
- `tests/test_rag_decision_memory_review.py`

Key modified files:

- `config/rag.toml`
- `scripts/rag_config.py`
- `scripts/generate_llm_advice.py`
- `scripts/run_long_memory_analysis.py`
- `scripts/review_advice.py`
- `scripts/run_replay_experiment.py`
- `tests/test_rag_config.py`

Validation run:

```powershell
python -m unittest discover -s tests -p test_rag_decision_memory_review.py
python -m unittest discover -s tests -p "test_rag_*.py"
python -m unittest discover -s tests -p test_multiagent_and_review.py
python -m unittest discover -s tests -p test_evidence_and_replay.py
python -m unittest discover -s tests -p test_long_memory.py
python -m unittest discover -s tests -p test_pipeline_logic.py
python -m unittest discover -s tests -p test_web_api_rag_admin.py
python -m unittest discover -s tests -p test_rag_maintenance.py
python -m py_compile scripts\rag_config.py scripts\rag_models.py scripts\rag_index_store.py scripts\rag_sources.py scripts\rag_ingest.py scripts\rag_query_planner.py scripts\rag_retriever.py scripts\rag_rerank.py scripts\rag_trace.py scripts\rag_embedding_client.py scripts\rag_vector_store.py scripts\rag_eval.py scripts\rag_maintenance.py scripts\rag_profile_evidence.py scripts\agent_inputs.py scripts\run_multiagent_research.py scripts\generate_llm_advice.py scripts\run_long_memory_analysis.py scripts\review_advice.py scripts\run_replay_experiment.py app\rag_answering.py app\rag_service.py app\web_api.py app\web_api_services.py app\copilot_service.py
python scripts\rag_maintenance.py --check-integrity
cd frontend
npm run build
```

Results:

- `test_rag_decision_memory_review.py`: 6 tests passed.
- `test_rag_*.py`: 47 tests passed.
- `test_multiagent_and_review.py`: 24 tests passed.
- `test_evidence_and_replay.py`: 3 tests passed.
- `test_long_memory.py`: 15 tests passed.
- `test_pipeline_logic.py`: 17 tests passed.
- `test_web_api_rag_admin.py`: 8 tests passed.
- `test_rag_maintenance.py`: 2 tests passed.
- Python compile checks passed.
- SQLite integrity check returned `ok`.
- Frontend build passed.

Recommended next entrypoint:

1. Keep PR-26 profile evidence disabled until a real trace review is run.
2. Run a controlled profile-evidence smoke on indexed data by temporarily enabling only one profile at a time.
3. Then decide whether PR-27 execution profile should start; do not merge execution data into fund/market/decision learning.

## 2026-05-21 Continued Update: PR-27 Execution Profile And Privacy Boundary

Completed in this session:

- Added `execution_sync` as an explicit RAG source adapter in `scripts/rag_sources.py`, but kept it out of `DEFAULT_SOURCES`.
- The adapter only reads structured summaries from:
  - `db/execution_sync/actual_trades/*.json`
  - `db/execution_sync/pending_confirmations.json`
  - `db/execution_sync/position_snapshots/*.json`
  - `db/execution_sync/reconciliation_reports/*.json`
- The adapter intentionally does not index screenshot files, parsed import OCR blobs, raw OCR text, user notes, base64 image content, or detailed account screenshot artifacts.
- Every execution document is created with the PR-27 hard markers:
  - `domain=execution`
  - `learning_scope=execution_only`
  - `visibility=execution_only`
  - `source_kind=execution_sync`
- Copilot execution retrieval is now limited to trusted execution-page intents:
  - `execution_explain`
  - `position_reconcile`
  - `pending_confirmation`
- Fund/detail/market Copilot queries keep `include_execution=false`, even when execution wording appears in the question text.
- Admin RAG search can query execution docs only when `includeExecution=true` is paired with:
  - `profile=execution` or `profile=execution_review`
  - one of the approved execution intents above.
- `rag_maintenance.py --purge-domain execution` remains RAG-index-only; tests confirm original `db/execution_sync` source files are preserved.

Default behavior after this session:

- RAG is still disabled by default:
  - `rag.enabled=false`
  - `rag.agent_shadow.enabled=false`
  - `rag.agent_default.enabled=false`
  - `rag.profile_evidence.enabled=false`
  - `rag.embedding.enabled=false`
- Execution source ingestion is still disabled by default:
  - `rag.sources.execution_sync=false`
  - `python scripts\rag_ingest.py --date 2026-05-20 --dry-run --all` still selects only long memory, portfolio state, LLM context, validated advice, and committee bundle.
- The current live `execution_sync` dry run found no indexable structured records, and did not ingest parsed OCR/screenshot import files.

New or expanded tests:

- `tests/test_rag_execution_boundary.py`
  - normal profile rejects execution-only evidence.
  - execution adapter creates only redacted execution-only docs.
  - execution profile can retrieve execution docs.
  - default `--all` ingest excludes `execution_sync`.
- `tests/test_web_api_rag_copilot.py`
  - normal Copilot queries exclude execution even when the source is enabled.
  - execution-page Copilot questions use the execution profile and approved intent.
- `tests/test_web_api_rag_admin.py`
  - admin search requires explicit `includeExecution=true`.
  - explicit execution search also requires execution profile and execution intent.

Validation run:

```powershell
python -m unittest discover -s tests -p test_rag_execution_boundary.py
python -m unittest discover -s tests -p test_web_api_rag_copilot.py
python -m unittest discover -s tests -p test_web_api_rag_admin.py
python -m unittest discover -s tests -p test_execution_sync.py
python -m unittest discover -s tests -p "test_rag_*.py"
python -m unittest discover -s tests -p test_rag_sources.py
python -m unittest discover -s tests -p test_rag_maintenance.py
python -m unittest discover -s tests -p test_long_memory.py
python -m unittest discover -s tests -p test_pipeline_logic.py
python -m py_compile scripts\rag_config.py scripts\rag_models.py scripts\rag_index_store.py scripts\rag_sources.py scripts\rag_ingest.py scripts\rag_query_planner.py scripts\rag_retriever.py scripts\rag_rerank.py scripts\rag_trace.py scripts\rag_maintenance.py app\rag_service.py app\rag_answering.py app\web_api.py
python scripts\rag_maintenance.py --check-integrity
python scripts\rag_ingest.py --domain execution_sync --dry-run
python scripts\rag_ingest.py --date 2026-05-20 --dry-run --all
python scripts\rag_maintenance.py --status
```

Results:

- `test_rag_execution_boundary.py`: 4 tests passed.
- `test_web_api_rag_copilot.py`: 6 tests passed.
- `test_web_api_rag_admin.py`: 9 tests passed.
- `test_execution_sync.py`: 9 tests passed.
- `test_rag_*.py`: 50 tests passed.
- `test_rag_sources.py`: 6 tests passed.
- `test_rag_maintenance.py`: 2 tests passed.
- `test_long_memory.py`: 15 tests passed.
- `test_pipeline_logic.py`: 17 tests passed.
- Python compile checks passed.
- SQLite integrity check returned `ok`.
- `execution_sync` dry run returned `doc_count=0`, `chunk_count=0`, because current repo data has no structured actual-trade / pending / position / reconciliation records to index.
- Default `--all` dry run returned `doc_count=356`, `chunk_count=356`, and did not include `execution_sync`.

Current local RAG status after validation:

- `enabled=false`
- `documents=356`
- `chunks=356`
- `active_manifests=5`
- `source_manifests=21`
- `ingest_runs=5`
- `query_traces=79`
- `embedding_cache=20`
- active source counts:
  - `committee_bundle=16`
  - `evidence_item=188`
  - `llm_context=29`
  - `long_memory=85`
  - `portfolio_state=16`
  - `validated_advice=22`
- latest eval: `db/rag/eval/2026-05-20.json`
  - `hit_count=616`
  - `no_future_violation_count=0`

Recommended next entrypoint:

1. Keep `rag.sources.execution_sync=false` until there is a deliberate, reviewed execution-profile smoke run.
2. If testing PR-27 with real records, first create or capture structured actual-trade / pending / position records, then run:
   - `python scripts\rag_ingest.py --domain execution_sync --dry-run`
   - review the dry-run doc/chunk counts and metadata.
   - only then run `--write`, if the redaction looks correct.
3. Do not enable execution retrieval for fund/market/decision profiles. Execution data remains execution-only.

## 2026-05-21 Continued Update: Enable Default RAG

Completed in this session:

- Enabled the main Copilot RAG switch in `config/rag.toml`:
  - `rag.enabled=true`
- Enabled default multi-agent RAG retrieval in `config/rag.toml`:
  - `rag.agent_default.enabled=true`
  - `rag.agent_default.fallback_to_legacy=true`
  - `rag.agent_default.min_hits=1`
- Kept high-risk or optional scopes disabled:
  - `rag.agent_shadow.enabled=false`
  - `rag.profile_evidence.enabled=false`
  - all `rag.profile_evidence.*.enabled=false`
  - `rag.embedding.enabled=false`
  - `rag.sources.execution_sync=false`
- Added `agentDefault` and `profileEvidence` to `rag_maintenance.py --status` / RAG status API output.
- Added an Agent Default status tile to the System page RAG card.

Smoke result:

- Ran:

```powershell
python scripts\run_daily_pipeline.py --date 2026-05-20 --mode intraday --demo --llm-mock --resume-existing
```

- The pipeline completed successfully.
- `db/agent_outputs/2026-05-20/aggregate.json` now records:
  - `workflow_meta.rag.retrieval_backend=rag`
  - `workflow_meta.rag.rag_enabled=true`
  - `workflow_meta.rag.shadow_enabled=false`
  - `workflow_meta.rag.fallback_to_legacy=true`
  - active RAG manifest ids and `manifest_set_sha256`
- Sample agent traces showed RAG retrieval in use with nonzero hit counts and empty fallback reasons.
- RAG traces still show `include_execution=false`.

Validation run:

```powershell
python -m unittest discover -s tests -p test_rag_config.py
python -m unittest discover -s tests -p test_web_api_rag_admin.py
python -m unittest discover -s tests -p test_web_api_rag_copilot.py
python -m unittest discover -s tests -p "test_rag_*.py"
python -m unittest discover -s tests -p test_multiagent_and_review.py
python -m unittest discover -s tests -p test_pipeline_logic.py
python -m unittest discover -s tests -p test_execution_sync.py
python -m py_compile scripts\rag_config.py scripts\rag_models.py scripts\rag_index_store.py scripts\rag_sources.py scripts\rag_ingest.py scripts\rag_query_planner.py scripts\rag_retriever.py scripts\rag_rerank.py scripts\rag_trace.py scripts\rag_maintenance.py scripts\agent_inputs.py scripts\run_multiagent_research.py app\rag_answering.py app\rag_service.py app\web_api.py app\web_api_services.py
python scripts\rag_maintenance.py --status
```

Results:

- `test_rag_config.py`: 4 tests passed.
- `test_web_api_rag_admin.py`: 9 tests passed.
- `test_web_api_rag_copilot.py`: 6 tests passed.
- `test_rag_*.py`: 50 tests passed.
- `test_multiagent_and_review.py`: 24 tests passed.
- `test_pipeline_logic.py`: 17 tests passed.
- `test_execution_sync.py`: 9 tests passed.
- Python compile checks passed.
- Current RAG status after the smoke:
  - `enabled=true`
  - `agentDefault.enabled=true`
  - `agentShadow.enabled=false`
  - `profileEvidence.enabled=false`
  - `embedding.enabled=false`
  - `documents=356`
  - `chunks=356`
  - `query_traces=101`
  - active source counts unchanged and still no `execution_sync` source count.

Rollback:

- To return to the prior default-off behavior, set:
  - `rag.enabled=false`
  - `rag.agent_default.enabled=false`
- No original source artifacts need to be deleted. RAG traces and index files are under `db/rag`.

## 2026-05-21 Enablement Closeout Verification

Completed after the default-RAG enablement smoke:

- Kept the enablement scope unchanged:
  - `rag.enabled=true`
  - `rag.agent_default.enabled=true`
  - `rag.agent_shadow.enabled=false`
  - `rag.profile_evidence.enabled=false`
  - `rag.embedding.enabled=false`
  - `rag.sources.execution_sync=false`
- Tightened the System page RAG status layout so the six RAG status tiles render as a responsive `2 / 3 / 6` column grid.
- Re-ran the frontend build after the layout correction:

```powershell
cd frontend
npm run build
```

- Re-ran RAG maintenance checks:

```powershell
python scripts\rag_maintenance.py --status
python scripts\rag_maintenance.py --check-integrity
python scripts\rag_eval.py --date 2026-05-20 --compare-legacy
```

Results:

- Frontend build passed.
- Integrity check returned `ok=true`.
- RAG status confirmed:
  - `enabled=true`
  - `agentDefault.enabled=true`
  - `agentShadow.enabled=false`
  - `profileEvidence.enabled=false`
  - `embedding.enabled=false`
  - `documents=356`
  - `chunks=356`
  - `active_manifests=5`
  - no `execution_sync` source count.
- `rag_eval.py --compare-legacy` refreshed `db/rag/eval/2026-05-20.json`.
- The eval command can write retrieval-only `agent_shadow:*` traces for comparison, but production shadow injection remains disabled by config and all observed traces still had `include_execution=false`.

Recommended next checkpoint:

1. Monitor the first non-demo daily run with default RAG enabled.
2. Confirm `workflow_meta.rag.retrieval_backend=rag` and `include_execution=false` in the new day's traces.
3. Keep profile evidence, embeddings, and execution-sync retrieval off until each has its own reviewed enablement step.

## 2026-05-21 Desktop Startup Review And Fix

Issue observed:

- Double-clicking the desktop shortcut `C:\Users\qmq\Desktop\okra的小助手.lnk` can appear to do nothing.
- The shortcut points to `app\okra_helper.vbs`, which launches `run_desktop_app.ps1` hidden.
- Before this fix, the launcher defaulted to source freshness scanning and Tauri rebuilds. After the RAG/frontend edits, a hidden first launch could spend minutes in `npm run build` / `tauri build --no-bundle`, with no visible feedback.
- Repeated double-clicks could stack build waits and background startup work, making the app look broken even though the eventual release binary was valid.

Fix applied:

- Changed `run_desktop_app.ps1` to default to fast startup:
  - use the existing `frontend\src-tauri\target\release\okra-workbench.exe` when present.
  - only rebuild when `-Rebuild`, `--rebuild`, or `OKRA_DESKTOP_REBUILD=1` is set.
  - source freshness rebuild can still be requested with `-AutoRebuildWhenChanged`, `--auto-rebuild-when-changed`, or `OKRA_DESKTOP_AUTO_REBUILD=1`.
- The launcher no longer requires Node/npm or Cargo when a release executable already exists and no rebuild was requested.
- Existing running Workbench windows are detected by executable path; the launcher preserves the current window and only starts/restarts the API if needed.
- API startup now waits for `/api/health` before proceeding and logs health failures to `logs\desktop\desktop_*.log`.

Validation:

```powershell
[System.Management.Automation.Language.Parser]::ParseFile("F:\okra_assistant\run_desktop_app.ps1", ...)
npm run build
npm run tauri -- build --no-bundle
python -m py_compile app\web_api.py app\web_api_services.py app\rag_service.py app\rag_answering.py scripts\rag_config.py scripts\rag_models.py scripts\rag_index_store.py scripts\rag_sources.py scripts\rag_ingest.py scripts\rag_query_planner.py scripts\rag_retriever.py scripts\rag_rerank.py scripts\rag_trace.py scripts\rag_maintenance.py scripts\agent_inputs.py scripts\run_multiagent_research.py
python scripts\rag_maintenance.py --check-integrity
python -m unittest discover -s tests -p "test_rag_*.py"
python -m unittest discover -s tests -p test_web_api_rag_admin.py
python -m unittest discover -s tests -p test_web_api_rag_copilot.py
python -m unittest discover -s tests -p test_pipeline_logic.py
python -m unittest discover -s tests -p test_multiagent_and_review.py
python -m unittest discover -s tests -p test_execution_sync.py
```

Results:

- PowerShell syntax check passed.
- Frontend build passed.
- Tauri release build passed and refreshed `frontend\src-tauri\target\release\okra-workbench.exe`.
- Desktop launcher smoke passed: within about 8 seconds, `okra-workbench.exe` was running and responding with title `OKRA 长期记忆投资工作台`, the Python API process was running, and `/api/health` returned HTTP 200.
- RAG and nearby regression tests passed.

Remaining notes:

- If frontend/Tauri source changes should be rebuilt into the desktop exe, run:
  - `.\run_desktop_app.ps1 -Rebuild`
- The first launch after a manual rebuild can still take longer because Tauri compiles Rust code; normal desktop double-clicks should now use the existing release exe directly.

## 2026-05-21 RAG Release Boundary Hardening

Reason:

- A review found RAG had crossed the original shadow/offline boundary: `config/rag.toml` enabled both global RAG and `agent_default`, and agent input replacement could change production advice prompts.
- The same review identified release blockers around active manifest membership, stale document lifecycle, Copilot 0-hit fallback, evidence id compatibility, execution isolation, fund hard filters, freshness signatures, timestamp normalization, and frontend response resilience.

Work in this checkpoint:

- Restored default production boundary:
  - `rag.enabled=false`
  - `rag.agent_default.enabled=false`
  - RAG admin/search/eval/ingest remains available for explicit testing.
- Added manifest membership and stale lifecycle:
  - `manifest_documents`
  - `manifest_chunks`
  - `scope_key` on documents/chunks
  - ingest writes membership per active manifest and deactivates same-scope records missing from the current bundle.
- Tightened retriever behavior:
  - active manifests constrain candidates when an active set exists.
  - ordinary queries block `domain="execution"` in addition to `learning_scope=execution_only` and `source_kind=execution_sync`.
  - fund-bound records are hard-filtered by `fund_codes` / fund entity id even when their domain is `decision`.
  - naive timestamps are normalized to Asia/Shanghai before no-future comparison.
- Tightened Copilot and agent contracts:
  - Copilot falls back to legacy evidence when RAG hit count is below `min_hits`.
  - RAG evidence injected into agents is normalized to `evidence_id = rag:{doc_id}#{chunk_id}` and mapped to funds only when the hit explicitly carries that fund code.
- Added freshness and UI resilience:
  - daily multi-agent reuse now observes `config/rag.toml`, RAG code paths, and active manifest digest.
  - System/Copilot frontend parsing uses zod schemas and array guards for RAG runtime/Copilot response shapes.

Validation target for this checkpoint:

```powershell
python -m unittest discover -s tests -p "test_rag_*.py"
python -m unittest tests.test_web_api_rag_admin tests.test_web_api_rag_copilot tests.test_execution_sync tests.test_pipeline_logic
python scripts\rag_maintenance.py --check-integrity
python -m py_compile scripts\rag_index_store.py scripts\rag_ingest.py scripts\rag_retriever.py scripts\agent_inputs.py app\rag_service.py app\web_api.py
npm --prefix frontend run build
```

Next enablement rule:

- Do not enable default production RAG again until this hardening checkpoint passes and a separate shadow/admin verification confirms active manifest filtering, fallback behavior, and execution exclusion on current data.
