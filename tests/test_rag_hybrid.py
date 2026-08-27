from __future__ import annotations

import sys
import unittest
import json
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome  # noqa: E402
from rag_models import RagQueryPlan  # noqa: E402
from rag_rerank import rerank_hits  # noqa: E402
from rag_retriever import _semantic_scores, retrieve_rag_evidence  # noqa: E402


class RagHybridTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _enable_hybrid(self):
        self.agent.write_text(
            "config/rag.toml",
            """[rag]
enabled = true

[rag.embedding]
enabled = true
dry_run = false

[rag.hybrid]
enabled = true
minimum_vector_coverage = 0.75
""",
        )

    def test_default_configuration_keeps_lexical_retrieval(self):
        plan = RagQueryPlan(query="基金风险", retrieval_profile="test", as_of_date="2026-05-20")
        scores, status = _semantic_scores(self.agent.root, [], plan)
        self.assertEqual({}, scores)
        self.assertEqual("lexical_rerank", status["mode"])
        self.assertEqual("hybrid_disabled", status["reason"])

    def test_insufficient_vector_coverage_falls_back_before_embedding_query(self):
        self._enable_hybrid()
        plan = RagQueryPlan(query="基金风险", retrieval_profile="test", as_of_date="2026-05-20")
        candidates = [{"chunk_id": "one"}, {"chunk_id": "two"}]

        scores, status = _semantic_scores(self.agent.root, candidates, plan)

        self.assertEqual({}, scores)
        self.assertEqual("lexical_rerank", status["mode"])
        self.assertEqual("insufficient_vector_coverage", status["reason"])
        self.assertEqual(0.0, status["coverage"])

    def test_trace_records_explicit_retrieval_mode(self):
        plan = RagQueryPlan(query="基金风险", retrieval_profile="test", as_of_date="2026-05-20")
        result = retrieve_rag_evidence(self.agent.root, plan)

        trace = json.loads(Path(result["trace_path"]).read_text(encoding="utf-8"))
        self.assertEqual("lexical_rerank", trace["retrieval"]["mode"])
        self.assertEqual("hybrid_disabled", trace["retrieval"]["semantic"]["reason"])

    def test_semantic_score_can_adjust_rank_only_when_explicit(self):
        plan = RagQueryPlan(query="基金风险", retrieval_profile="test", as_of_date="2026-05-20")
        base = {
            "source_tier": "daily_evidence",
            "text_score": 0.5,
            "as_of_date": "2026-05-20",
            "fund_codes": [],
            "entity_id": "",
            "metadata": {},
            "source_kind": "evidence_item",
            "source_record_id": "one",
            "visibility": "default",
        }
        lexical = rerank_hits([{**base, "chunk_id": "one"}, {**base, "chunk_id": "two", "source_record_id": "two"}], plan)
        hybrid = rerank_hits([
            {**base, "chunk_id": "one", "semantic_score": 0.1},
            {**base, "chunk_id": "two", "source_record_id": "two", "semantic_score": 0.9},
        ], plan, semantic_weight=0.35)
        self.assertEqual("one", lexical[0]["chunk_id"])
        self.assertEqual("two", hybrid[0]["chunk_id"])
        self.assertGreater(hybrid[0]["score_breakdown"]["semantic"], 0.0)


if __name__ == "__main__":
    unittest.main()
