from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rag_models import RagChunk, RagDocument, RagHit, RagQueryPlan, RagTrace


class RagModelsTests(unittest.TestCase):
    def _document(self) -> RagDocument:
        return RagDocument(
            doc_id="doc-1",
            source_kind="long_memory",
            source_path="db/long_memory/memory.sqlite",
            source_record_id="memory-1",
            title="Memory title",
            summary="Memory summary",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:30:00+08:00",
            domain="fund",
            source_tier="derived_memory",
            visibility="default",
            fund_codes=["001234", "", " 005678 "],
            payload={"text": "payload"},
        )

    def test_document_normalizes_fund_codes_and_generates_checksum(self):
        doc = self._document()
        self.assertEqual(["001234", "005678"], doc.fund_codes)
        self.assertTrue(doc.content_sha256)
        self.assertEqual("2026-05-20", doc.as_of_date)

    def test_document_requires_auditable_fields(self):
        with self.assertRaisesRegex(ValueError, "source_path"):
            RagDocument(
                doc_id="doc-1",
                source_kind="llm_context",
                source_path="",
                source_record_id="row-1",
                title="Title",
                summary="Summary",
                as_of_date="2026-05-20",
                available_from="2026-05-20T15:30:00+08:00",
                domain="market",
                source_tier="daily_context",
            )

    def test_document_rejects_non_list_fund_codes(self):
        with self.assertRaisesRegex(ValueError, "fund_codes"):
            doc = self._document()
            doc.fund_codes = "001234"  # type: ignore[assignment]
            doc.__post_init__()

    def test_chunk_requires_text_and_generates_embedding_hash(self):
        chunk = RagChunk(
            chunk_id="chunk-1",
            doc_id="doc-1",
            chunk_index=0,
            text_for_embedding="标题：Memory title 内容：Memory summary",
            text_for_llm="Memory summary",
        )
        self.assertTrue(chunk.embedding_sha256)
        self.assertEqual("pending", chunk.embedding_status)

    def test_query_plan_keeps_hard_filter_inputs_structured(self):
        plan = RagQueryPlan(
            query="风险来自哪里",
            retrieval_profile="copilot_qa",
            as_of_date="2026-05-20",
            fund_codes=["001234"],
            source_kinds=["long_memory", "llm_context"],
            domains=["fund"],
        )
        self.assertEqual(["001234"], plan.fund_codes)
        self.assertFalse(plan.include_execution)

    def test_hit_and_trace_are_serializable(self):
        hit = RagHit(
            chunk_id="chunk-1",
            doc_id="doc-1",
            score=0.8,
            source_kind="long_memory",
            title="Memory title",
            text_for_llm="Memory summary",
        )
        trace = RagTrace(trace_id="trace-1", query_plan={"query": "risk"}, hits=[hit.to_dict()])
        self.assertEqual("trace-1", trace.to_dict()["trace_id"])
        self.assertEqual("chunk-1", trace.hits[0]["chunk_id"])


if __name__ == "__main__":
    unittest.main()
