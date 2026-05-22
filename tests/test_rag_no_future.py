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


class RagNoFutureTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_future_available_from_is_rejected(self):
        doc = RagDocument(
            doc_id="future-doc",
            source_kind="llm_context",
            source_path="db/llm_context/2026-05-21.json",
            source_record_id="future",
            title="future risk",
            summary="future risk should not appear",
            as_of_date="2026-05-20",
            available_from="2026-05-21T09:00:00+08:00",
            domain="fund",
            source_tier="daily_context",
            entity_id="F1",
            fund_codes=["F1"],
        )
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [RagChunk(chunk_id="future-doc:chunk:0", doc_id="future-doc", chunk_index=0, text_for_embedding="future risk", text_for_llm="future risk")])
        plan = build_rag_query_plan("future risk", query_date="2026-05-20", fund_codes=["F1"])
        result = retrieve_rag_evidence(self.agent.root, plan, write_trace_file=False)
        self.assertEqual([], result["hits"])
        self.assertEqual("future_available_from", result["rejected_samples"][0]["reason"])

    def test_naive_timestamp_is_normalized_for_no_future_filter(self):
        doc = RagDocument(
            doc_id="naive-doc",
            source_kind="llm_context",
            source_path="db/llm_context/2026-05-20.json",
            source_record_id="naive",
            title="naive timestamp risk",
            summary="naive timestamp should not crash",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00",
            domain="fund",
            source_tier="daily_context",
            entity_id="F1",
            fund_codes=["F1"],
        )
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [RagChunk(chunk_id="naive-doc:chunk:0", doc_id="naive-doc", chunk_index=0, text_for_embedding="timestamp risk", text_for_llm="timestamp risk")])
        plan = build_rag_query_plan("timestamp risk", query_date="2026-05-20", fund_codes=["F1"])

        result = retrieve_rag_evidence(self.agent.root, plan, write_trace_file=False)

        self.assertEqual(["naive-doc"], [hit["doc_id"] for hit in result["hits"]])


if __name__ == "__main__":
    unittest.main()
