from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from rag_index_store import upsert_chunks, upsert_documents, write_manifest
from rag_models import RagChunk, RagDocument
from rag_query_planner import build_rag_query_plan
from rag_retriever import retrieve_rag_evidence


class RagRetrieverFilterTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _doc(self, doc_id: str, **overrides) -> RagDocument:
        payload = {
            "doc_id": doc_id,
            "source_kind": "llm_context",
            "source_path": "db/llm_context/2026-05-20.json",
            "source_record_id": doc_id,
            "title": f"{doc_id} title",
            "summary": f"{doc_id} summary",
            "as_of_date": "2026-05-20",
            "available_from": "2026-05-20T15:00:00+08:00",
            "domain": "fund",
            "source_tier": "daily_context",
            "visibility": "default",
            "entity_type": "fund",
            "entity_id": "F1",
            "fund_codes": ["F1"],
        }
        payload.update(overrides)
        return RagDocument(**payload)

    def _chunk(self, doc: RagDocument) -> RagChunk:
        return RagChunk(
            chunk_id=f"{doc.doc_id}:chunk:0",
            doc_id=doc.doc_id,
            chunk_index=0,
            text_for_embedding=f"{doc.title} {doc.summary}",
            text_for_llm=doc.summary,
        )

    def _insert(self, *docs: RagDocument):
        upsert_documents(self.agent.root, docs)
        upsert_chunks(self.agent.root, [self._chunk(doc) for doc in docs])

    def test_retriever_returns_ranked_hits_and_trace(self):
        self._insert(self._doc("doc-current", summary="F1 risk is valuation pressure"))
        plan = build_rag_query_plan("risk valuation", query_date="2026-05-20", fund_codes=["F1"], top_k=3)
        result = retrieve_rag_evidence(self.agent.root, plan)
        self.assertEqual("doc-current", result["hits"][0]["doc_id"])
        self.assertTrue(Path(result["trace_path"]).exists())
        self.assertEqual([], result["missing_data"])

    def test_no_hits_returns_missing_data(self):
        self._insert(self._doc("doc-f2", entity_id="F2", fund_codes=["F2"]))
        plan = build_rag_query_plan("risk", query_date="2026-05-20", fund_codes=["F1"])
        result = retrieve_rag_evidence(self.agent.root, plan)
        self.assertEqual([], result["hits"])
        self.assertEqual("no_hits_after_hard_filters", result["missing_data"][0]["reason"])
        self.assertEqual("fund_mismatch", result["rejected_samples"][0]["reason"])

    def test_active_manifest_membership_limits_candidates(self):
        old_doc = self._doc("old-doc", summary="old stale risk")
        new_doc = self._doc("new-doc", summary="new active risk")
        for doc in (old_doc, new_doc):
            doc.metadata["scope_key"] = "2026-05-20:context:llm_context"
        old_chunk = self._chunk(old_doc)
        old_chunk.metadata["scope_key"] = "2026-05-20:context:llm_context"
        new_chunk = self._chunk(new_doc)
        new_chunk.metadata["scope_key"] = "2026-05-20:context:llm_context"
        upsert_documents(self.agent.root, [old_doc, new_doc])
        upsert_chunks(self.agent.root, [old_chunk, new_chunk])
        write_manifest(
            self.agent.root,
            {
                "manifest_id": "manifest-current",
                "scope_key": "2026-05-20:context:llm_context",
                "source_kind": "llm_context",
                "source_path": "db/llm_context/2026-05-20.json",
                "as_of_date": "2026-05-20",
                "status": "ok",
                "doc_count": 1,
                "chunk_count": 1,
            },
            document_ids=["new-doc"],
            chunk_ids=["new-doc:chunk:0"],
        )

        plan = build_rag_query_plan("risk", query_date="2026-05-20", fund_codes=["F1"], top_k=5)
        result = retrieve_rag_evidence(self.agent.root, plan, write_trace_file=False)

        self.assertEqual(["new-doc"], [hit["doc_id"] for hit in result["hits"]])
        self.assertEqual(1, result["candidate_count_before_filter"])


if __name__ == "__main__":
    unittest.main()
