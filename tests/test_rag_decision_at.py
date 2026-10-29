from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from rag_index_store import upsert_chunks, upsert_documents
from rag_models import RagChunk, RagDocument
from rag_query_planner import build_rag_query_plan
from rag_retriever import retrieve_rag_evidence


class RagDecisionAtTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _seed(self, doc_id: str, available_from: str) -> None:
        doc = RagDocument(
            doc_id=doc_id,
            source_kind="llm_context",
            source_path=f"db/llm_context/2026-05-20.json",
            source_record_id=doc_id,
            title=doc_id,
            summary=doc_id,
            as_of_date="2026-05-20",
            available_from=available_from,
            domain="fund",
            source_tier="daily_context",
            entity_id="F1",
            fund_codes=["F1"],
        )
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(
            self.agent.root,
            [RagChunk(chunk_id=f"{doc_id}:chunk:0", doc_id=doc_id, chunk_index=0, text_for_embedding=doc_id, text_for_llm=doc_id)],
        )

    def test_decision_at_rejects_later_intraday(self):
        # available_from 15:00 晚于 decision_at 10:00 -> 拒绝
        self._seed("late-intraday", "2026-05-20T15:00:00+08:00")
        plan = build_rag_query_plan(
            "intraday risk",
            query_date="2026-05-20",
            decision_at="2026-05-20T10:00:00+08:00",
            fund_codes=["F1"],
        )
        self.assertEqual(plan.metadata["cutoff_precision"], "decision_at_instant")
        result = retrieve_rag_evidence(self.agent.root, plan, write_trace_file=False)
        self.assertEqual([], result["hits"])
        self.assertEqual("future_available_from", result["rejected_samples"][0]["reason"])

    def test_decision_at_allows_earlier_intraday(self):
        # available_from 09:00 早于 decision_at 10:00 -> 放行
        self._seed("early-intraday", "2026-05-20T09:00:00+08:00")
        plan = build_rag_query_plan(
            "intraday risk",
            query_date="2026-05-20",
            decision_at="2026-05-20T10:00:00+08:00",
            fund_codes=["F1"],
        )
        result = retrieve_rag_evidence(self.agent.root, plan, write_trace_file=False)
        self.assertEqual(["early-intraday"], [hit["doc_id"] for hit in result["hits"]])

    def test_naive_decision_at_rejected(self):
        with self.assertRaises(ValueError):
            build_rag_query_plan(
                "naive",
                query_date="2026-05-20",
                decision_at="2026-05-20T10:00:00",
                fund_codes=["F1"],
            )

    def test_mismatched_date_rejected(self):
        # decision_at 落在 05-21，query_date 05-20 -> 冲突拒绝
        with self.assertRaises(ValueError):
            build_rag_query_plan(
                "mismatch",
                query_date="2026-05-20",
                decision_at="2026-05-21T10:00:00+08:00",
                fund_codes=["F1"],
            )

    def test_end_of_day_legacy_metadata_when_no_decision_at(self):
        plan = build_rag_query_plan("legacy", query_date="2026-05-20", fund_codes=["F1"])
        self.assertIsNone(plan.decision_at)
        self.assertEqual(plan.metadata["cutoff_precision"], "end_of_day_legacy")
        self.assertIn("does NOT guarantee no future intraday", plan.metadata["time_basis_note"])


if __name__ == "__main__":
    unittest.main()
