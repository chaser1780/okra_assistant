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


class RagFundMatchTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_explicit_fund_query_rejects_other_fund_main_evidence(self):
        docs = [
            RagDocument(
                doc_id="f1-doc",
                source_kind="portfolio_state",
                source_path="db/portfolio_state/current.json",
                source_record_id="fund:F1",
                title="F1 position",
                summary="F1 position risk",
                as_of_date="2026-05-20",
                available_from="2026-05-20T15:00:00+08:00",
                domain="fund",
                source_tier="structured_current",
                entity_id="F1",
                fund_codes=["F1"],
            ),
            RagDocument(
                doc_id="f2-doc",
                source_kind="portfolio_state",
                source_path="db/portfolio_state/current.json",
                source_record_id="fund:F2",
                title="F2 position",
                summary="F2 position risk",
                as_of_date="2026-05-20",
                available_from="2026-05-20T15:00:00+08:00",
                domain="fund",
                source_tier="structured_current",
                entity_id="F2",
                fund_codes=["F2"],
            ),
        ]
        upsert_documents(self.agent.root, docs)
        upsert_chunks(self.agent.root, [RagChunk(chunk_id=f"{doc.doc_id}:chunk:0", doc_id=doc.doc_id, chunk_index=0, text_for_embedding=doc.summary, text_for_llm=doc.summary) for doc in docs])
        plan = build_rag_query_plan("position risk", query_date="2026-05-20", fund_codes=["F1"])
        result = retrieve_rag_evidence(self.agent.root, plan, write_trace_file=False)
        self.assertEqual(["f1-doc"], [hit["doc_id"] for hit in result["hits"]])
        self.assertTrue(any(item["reason"] == "fund_mismatch" and item["doc_id"] == "f2-doc" for item in result["rejected_samples"]))

    def test_decision_doc_for_other_fund_is_hard_filtered(self):
        docs = [
            RagDocument(
                doc_id="decision-f1",
                source_kind="committee_bundle",
                source_path="db/committee_decision_bundle/2026-05-20.json",
                source_record_id="fund_decision:F1",
                title="F1 decision",
                summary="F1 decision risk",
                as_of_date="2026-05-20",
                available_from="2026-05-20T15:00:00+08:00",
                domain="decision",
                source_tier="decision_trace",
                entity_type="fund",
                entity_id="F1",
                fund_codes=["F1"],
            ),
            RagDocument(
                doc_id="decision-f2",
                source_kind="committee_bundle",
                source_path="db/committee_decision_bundle/2026-05-20.json",
                source_record_id="fund_decision:F2",
                title="F2 decision",
                summary="F2 decision risk",
                as_of_date="2026-05-20",
                available_from="2026-05-20T15:00:00+08:00",
                domain="decision",
                source_tier="decision_trace",
                entity_type="fund",
                entity_id="F2",
                fund_codes=["F2"],
            ),
        ]
        upsert_documents(self.agent.root, docs)
        upsert_chunks(self.agent.root, [RagChunk(chunk_id=f"{doc.doc_id}:chunk:0", doc_id=doc.doc_id, chunk_index=0, text_for_embedding=doc.summary, text_for_llm=doc.summary) for doc in docs])

        plan = build_rag_query_plan("decision risk", query_date="2026-05-20", fund_codes=["F1"], domains=["decision"], source_kinds=["committee_bundle"])
        result = retrieve_rag_evidence(self.agent.root, plan, write_trace_file=False)

        self.assertEqual(["decision-f1"], [hit["doc_id"] for hit in result["hits"]])
        self.assertTrue(any(item["reason"] == "fund_mismatch" and item["doc_id"] == "decision-f2" for item in result["rejected_samples"]))

    def test_market_entity_id_is_not_treated_as_fund_binding(self):
        docs = [
            RagDocument(
                doc_id="market-cpi",
                source_kind="llm_context",
                source_path="db/llm_context/2026-05-20.json",
                source_record_id="macro:CPI",
                title="CPI macro signal",
                summary="CPI pressure may affect fund risk",
                as_of_date="2026-05-20",
                available_from="2026-05-20T15:00:00+08:00",
                domain="market",
                source_tier="daily_context",
                entity_type="macro",
                entity_id="CPI",
                fund_codes=[],
            ),
            RagDocument(
                doc_id="market-nasdaq",
                source_kind="llm_context",
                source_path="db/llm_context/2026-05-20.json",
                source_record_id="index:NASDAQ",
                title="NASDAQ market signal",
                summary="NASDAQ volatility may affect fund risk",
                as_of_date="2026-05-20",
                available_from="2026-05-20T15:00:00+08:00",
                domain="market",
                source_tier="daily_context",
                entity_type="index",
                entity_id="NASDAQ",
                fund_codes=[],
            ),
        ]
        upsert_documents(self.agent.root, docs)
        upsert_chunks(self.agent.root, [RagChunk(chunk_id=f"{doc.doc_id}:chunk:0", doc_id=doc.doc_id, chunk_index=0, text_for_embedding=doc.summary, text_for_llm=doc.summary) for doc in docs])

        plan = build_rag_query_plan("CPI NASDAQ risk", query_date="2026-05-20", fund_codes=["F1"], domains=["market"])
        result = retrieve_rag_evidence(self.agent.root, plan, write_trace_file=False)

        self.assertEqual({"market-cpi", "market-nasdaq"}, {hit["doc_id"] for hit in result["hits"]})
        self.assertFalse(any(item["reason"] == "fund_mismatch" for item in result["rejected_samples"]))


if __name__ == "__main__":
    unittest.main()
