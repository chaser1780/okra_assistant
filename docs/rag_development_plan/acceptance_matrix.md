# Acceptance Matrix

## Batch A：Task 1 底座

```powershell
python -m unittest discover -s tests -p test_rag_config.py
python -m unittest discover -s tests -p test_rag_models.py
python -m unittest discover -s tests -p test_rag_index_store.py
```

通过标准：

- `db/rag/rag.sqlite` 可初始化。
- `config/rag.toml` 缺失或 `rag.enabled=false` 时，现有 Copilot/daily pipeline 不变。
- 不需要网络、不需要 API key。

## Batch B：Task 2-4 Source Adapters

```powershell
python -m unittest discover -s tests -p test_rag_sources.py
python scripts\rag_ingest.py --date 2026-05-20 --dry-run --all
```

通过标准：

- `long_memory` permanent/strategic/candidate 默认可见。
- archived/rejected 默认 review_only。
- portfolio numeric payload 保留。
- validated/committee 缺文件返回 missing，不阻断。
- execution 默认不 ingest。

## Batch C：Task 5 Ingest

```powershell
python -m unittest discover -s tests -p test_rag_index_store.py
python -m unittest discover -s tests -p test_rag_sources.py
python scripts\rag_ingest.py --date 2026-05-20 --write --all
python scripts\rag_ingest.py --date 2026-05-20 --write --all
```

通过标准：

- 第二次运行 doc/chunk 不重复写入。
- source manifest 能反映 source 状态。
- 任一 source 失败不影响其他 source。

## Batch D：Task 6 Filters / Retriever / Trace

```powershell
python -m unittest discover -s tests -p test_rag_retriever_filters.py
python -m unittest discover -s tests -p test_rag_no_future.py
python -m unittest discover -s tests -p test_rag_fund_match.py
python -m unittest discover -s tests -p test_rag_memory_visibility.py
```

通过标准：

- no-future 违规为 0。
- 明确 fund_code 主证据错配为 0。
- 普通 profile 不召回 archived/rejected。
- 普通 profile 不召回 execution actual trades。
- trace 有 rejected_samples。

## Batch E：Task 7 Embedding / Vector

```powershell
python -m unittest discover -s tests -p test_rag_embedding_client.py
python -m unittest discover -s tests -p test_rag_retriever_filters.py
python scripts\rag_embedding_client.py --probe
```

通过标准：

- 无 API key 时 dry-run/mock 通过。
- API 不支持 embeddings endpoint 时有清晰 fallback。
- unchanged chunk 不重复请求。

## Batch F：Task 8 Copilot

```powershell
python -m unittest discover -s tests -p test_web_api_rag_copilot.py
cd frontend
npm run build
```

通过标准：

- 旧 `askCopilot()` 调用不报错。
- RAG 开启时返回 `mode=rag_llm`、`traceId`、`citations`。
- RAG 失败 fallback 到旧页面上下文或 local fallback。

## Batch G：Task 9 Daily Shadow

```powershell
python -m unittest discover -s tests -p test_pipeline_logic.py
python -m unittest discover -s tests -p test_multiagent_and_review.py
python scripts\run_daily_pipeline.py --date 2026-05-20 --mode intraday --demo --llm-mock --resume-existing
python scripts\rag_eval.py --date 2026-05-20 --compare-legacy
```

通过标准：

- Shadow 不改变最终 `validated_advice`。
- 每个 agent 有 trace。
- eval 输出 legacy/RAG diff。

## Batch H：Task 10 Default / Admin

```powershell
python -m unittest discover -s tests -p test_multiagent_and_review.py
python -m unittest discover -s tests -p test_web_api_rag_admin.py
python -m unittest discover -s tests -p test_rag_retriever_filters.py
python -m unittest discover -s tests -p test_rag_execution_boundary.py
cd frontend
npm run build
```

通过标准：

- RAG 默认接入后 agent output schema 不变。
- `fallback_to_legacy=true` 时旧链路可自动补位。
- 系统页/API 可查看 RAG 状态、trace、eval 和 source count。
- 这里只验收普通 fund/market/decision profile 不召回 execution-only 证据；`test_rag_execution_boundary.py` 在 Batch H 只放负向边界用例，真实 execution 召回能力和 `test_execution_sync.py` 放到 Later `PR-27` 单独验收。

## 人工验收问题集

建议维护在：

```text
tests/fixtures/rag_questions/copilot_current.json
tests/fixtures/rag_questions/copilot_historical.json
tests/fixtures/rag_questions/agent_profiles.json
tests/fixtures/rag_questions/execution_boundary.json
```

每条问题包含：

- `question`
- `selected_date`
- `fund_code`
- `expected_intent`
- `must_include_source_kinds`
- `must_exclude_domains`
- `must_not_use_future_after`
- `expected_missing_data`

必测类别：

- 当前组合仓位。
- 今天某基金建议原因。
- 数据是否过期。
- 回答用了哪些证据。
- 历史日期不能召回未来 memory/validated/review。
- 明确基金代码不能用其他基金当主证据。
- 普通问题不能出现 rejected memory。
- Batch H 之前只要求普通投研问题不能召回 execution。
- 执行问题可以召回 execution 的能力放到 Later `PR-27` 的人工验收问题集。
- stale estimated_nav 必须标注陈旧。

## 指标门槛

| 指标 | Phase 4 阈值 | Phase 6 阈值 |
|---|---:|---:|
| no-future 违规 | 0 | 0 |
| 明确 fund_code 主证据错配 | 0 | 0 |
| Copilot P95 首答延迟 | < 12s | < 8s |
| embedding 缓存命中率 | > 60% | > 85% |
| Agent token 增量 | 仅 shadow | < 15% |
| RAG fallback 率 | 可高 | < 10% |
