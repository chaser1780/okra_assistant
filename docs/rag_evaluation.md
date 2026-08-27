# RAG Offline Evaluation

OKRA keeps retrieval evaluation separate from the decision path. A local, manually labeled set may be placed at:

```text
db/rag/eval_sets/YYYY-MM-DD.json
```

It is read only by `scripts/rag_eval.py`; it never changes retrieval settings, prompts, agent outputs, simulated portfolios, or advice.

```json
{
  "schemaVersion": "rag_eval_set.v1",
  "reportDate": "2026-05-20",
  "queries": [
    {
      "queryId": "risk-manager-fund-F1",
      "agentName": "risk_manager",
      "scope": "fund",
      "fundCode": "F1",
      "expectedEvidenceIds": ["evidence:official-nav:F1"],
      "forbiddenEvidenceIds": ["evidence:future:F1"],
      "shouldAbstain": false
    }
  ]
}
```

`agentName`, `scope`, and `fundCode` identify the existing shadow-evaluation query. Evidence ids use the same `source_record_id` values emitted by RAG hits. With valid labels, the evaluation reports Recall@K, nDCG@K, evidence coverage, forbidden-hit rate, citation correctness, abstention quality, and future-data rejection rate. Without labels, those quality metrics remain unavailable rather than being inferred from legacy retrieval.
