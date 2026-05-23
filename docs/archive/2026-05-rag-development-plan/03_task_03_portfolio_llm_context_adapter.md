# Task 3：Portfolio 和 LLM Context Adapter

目标：把当前/历史持仓、每日上下文、清洗后的 evidence_items 抽成统一 RAG 文档。数值事实必须保留结构化 payload，不能只变成自然语言。

## PR-06：Portfolio Current/Snapshot Adapter

范围：

- `scripts/rag_sources.py` 实现 `iter_portfolio_documents(date=None)`。
- 输入：
  - `db/portfolio_state/current.json`
  - `db/portfolio_state/snapshots/*.json`
- 输出粒度：
  - 组合整体一条 doc。
  - 每只基金一条 doc。

metadata 要求：

- `source_kind="portfolio_state"`
- `domain="portfolio"` 或 `domain="fund"`
- 明确基金 doc 必须有 `fund_codes=[fund_code]`、`entity_id=fund_code`
- `source_tier="structured_current"` 或历史 snapshot 对应 tier
- `payload_json` 保留金额、份额、成本、收益、目标仓位、偏离等结构化数值

注意：

- 回答持仓金额、收益率、仓位偏离时，未来 answer layer 必须优先读 payload。
- 不要把完整大 JSON 原样 embedding，只构造短摘要文本。

验收：

```powershell
python -m unittest discover -s tests -p test_rag_sources.py
python scripts\rag_ingest.py --domain portfolio_state --dry-run
```

## PR-07：LLM Context 与 Evidence Items Adapter

范围：

- `scripts/rag_sources.py` 实现：
  - `iter_llm_context_documents(date)`
  - `iter_evidence_item_documents(date)`
- 输入：
  - `db/llm_context/YYYY-MM-DD.json`
  - 可选兼容 `db/evidence_index/*.json`
- 输出：
  - `portfolio_summary`
  - `exposure_summary`
  - `constraints`
  - `memory_digest`
  - `news_digest`
  - `sentiment_digest`
  - `event_risks`
  - `funds`
  - `evidence_items`

metadata 要求：

- `source_kind="llm_context"` 或 `source_kind="evidence_item"`
- `available_from` 优先使用文件内 generated/retrieved timestamp；缺失时使用业务日期当天 `23:59:59+08:00` 并标 inferred
- 明确基金 evidence 必须有 `fund_codes`
- 新闻类 evidence 保留 `published_at`、`url`、`canonical_url`、`source_health`
- stale/estimated_nav/source_health warning 进入 metadata

风险：

- llm_context 中可能有组合级摘要和基金级摘要混合，不能让组合级摘要替代基金主证据。
- 主题新闻只能作为辅助，必须有 `mapping_mode=theme_match` 或等价标识。

验收：

```powershell
python -m unittest discover -s tests -p test_rag_sources.py
python scripts\rag_ingest.py --date 2026-05-20 --domain llm_context --dry-run
```

## Task 3 完成定义

- `db/portfolio_state/current.json` 可生成组合和基金 docs。
- `db/llm_context/YYYY-MM-DD.json` 可生成 summary、fund、evidence docs。
- 明确基金代码的 evidence docs 带 `fund_codes`。
- numeric payload 不丢失。
