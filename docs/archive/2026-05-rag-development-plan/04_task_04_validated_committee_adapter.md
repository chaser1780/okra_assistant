# Task 4：Validated Advice 和 Committee Adapter

目标：把已验证建议与委员会决策作为高优先级、可引用的决策事实源接入 RAG。它们解释“系统为什么这么建议”，不能被新闻或普通文本替代。

## PR-08：Validated Advice Adapter

范围：

- `scripts/rag_sources.py` 实现 `iter_validated_advice_documents(date)`。
- 输入：`db/validated_advice/YYYY-MM-DD.json`。
- 输出粒度：
  - `market_view` 一条或多条 doc。
  - `tactical_actions` 每条 action 一条 doc。
  - `dca_actions` 每条 action 一条 doc。
  - `hold_actions` 每条 action 一条 doc。
  - `cross_fund_observations` 每条 observation 一条 doc。
  - `optimization_summary` 一条 doc。

metadata 要求：

- `source_kind="validated_advice"`
- `source_tier="structured_current"` 或 `decision_trace`
- action 级 doc 必须尽量填 `fund_codes`
- `domain="decision"` 或 `domain="fund"`
- `payload_json` 保留 action type、amount、reason、constraints、eligibility、validation status 等结构化字段

验收：

```powershell
python -m unittest discover -s tests -p test_rag_sources.py
python scripts\rag_ingest.py --date 2026-05-20 --domain validated_advice --dry-run
```

## PR-09：Committee Bundle Adapter

范围：

- `scripts/rag_sources.py` 实现 `iter_committee_bundle_documents(date)`。
- 输入：`db/committee_decision_bundle/YYYY-MM-DD.json`。
- 输出粒度：
  - bundle summary doc。
  - 每只基金 decision doc。
  - execution eligibility / degradation / notes 视结构拆分。

metadata 要求：

- `source_kind="committee_bundle"`
- `source_tier="decision_trace"`
- `domain="decision"`
- 明确基金决策必须有 `fund_codes`
- 缺文件时返回 missing source 记录，不抛出阻断错误

验收：

```powershell
python -m unittest discover -s tests -p test_rag_sources.py
python scripts\rag_ingest.py --date 2026-05-20 --domain committee_bundle --dry-run
```

## Task 4 完成定义

- 每条 action 可引用。
- market view 和 cross-fund observations 可引用。
- committee 缺文件时进入 missingData，不阻断 ingest。
- 决策事实 source tier 高于普通新闻。
