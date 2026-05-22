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
from rag_ingest import build_parser as build_ingest_parser, run_ingest
from rag_sources import DEFAULT_SOURCES, collect_execution_sync_documents


class RagExecutionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_normal_profile_rejects_execution_only_evidence(self):
        doc = RagDocument(
            doc_id="execution-doc",
            source_kind="long_memory",
            source_path="db/long_memory/memory.sqlite",
            source_record_id="execution-memory",
            title="Execution lag",
            summary="QDII confirmation lag execution rule",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="execution",
            source_tier="memory_approved",
            learning_scope="execution_only",
        )
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [RagChunk(chunk_id="execution-doc:chunk:0", doc_id="execution-doc", chunk_index=0, text_for_embedding=doc.summary, text_for_llm=doc.summary)])
        plan = build_rag_query_plan("confirmation lag", query_date="2026-05-20", retrieval_profile="copilot_qa")
        result = retrieve_rag_evidence(self.agent.root, plan, write_trace_file=False)
        self.assertEqual([], result["hits"])
        self.assertEqual("execution_boundary", result["rejected_samples"][0]["reason"])

    def test_normal_profile_rejects_execution_domain_even_without_learning_scope(self):
        doc = RagDocument(
            doc_id="execution-domain-doc",
            source_kind="long_memory",
            source_path="db/long_memory/memory.sqlite",
            source_record_id="execution-memory-domain",
            title="Execution domain",
            summary="Execution domain should be isolated",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="execution",
            source_tier="memory_approved",
        )
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [RagChunk(chunk_id="execution-domain-doc:chunk:0", doc_id=doc.doc_id, chunk_index=0, text_for_embedding=doc.summary, text_for_llm=doc.summary)])
        plan = build_rag_query_plan("execution domain", query_date="2026-05-20", retrieval_profile="copilot_qa")
        result = retrieve_rag_evidence(self.agent.root, plan, write_trace_file=False)
        self.assertEqual([], result["hits"])
        self.assertEqual("execution_boundary", result["rejected_samples"][0]["reason"])

    def test_execution_source_adapter_builds_redacted_execution_only_docs(self):
        self.agent.write_json(
            "db/execution_sync/actual_trades/2026-05-20.json",
            {
                "trade_date": "2026-05-20",
                "updated_at": "2026-05-20T15:00:00+08:00",
                "items": [
                    {
                        "trade_id": "trade-1",
                        "operation_type": "buy",
                        "trade_date": "2026-05-20",
                        "fund_code": "F1",
                        "fund_name": "Fund One",
                        "amount": 100.0,
                        "status": "submitted",
                        "confirm_date": "2026-05-21",
                        "raw_ocr_text": "OCR_SECRET_SHOULD_NOT_APPEAR",
                        "screenshot_base64": "BASE64_SECRET_SHOULD_NOT_APPEAR",
                        "user_note": "PRIVATE_USER_NOTE_SHOULD_NOT_APPEAR",
                    }
                ],
            },
        )
        self.agent.write_json(
            "db/execution_sync/imports/parsed/alipay_1.json",
            {
                "detected_holdings": [{"raw_ocr_text": "PARSED_OCR_SECRET_SHOULD_NOT_APPEAR"}],
                "saved_files": ["db/execution_sync/imports/alipay_screenshots/private.jpg"],
            },
        )

        bundle = collect_execution_sync_documents(self.agent.root)

        self.assertEqual("ok", bundle.status)
        self.assertTrue(bundle.documents)
        self.assertTrue(bundle.chunks)
        for doc in bundle.documents:
            self.assertEqual("execution", doc.domain)
            self.assertEqual("execution_sync", doc.source_kind)
            self.assertEqual("execution_only", doc.learning_scope)
            self.assertEqual("execution_only", doc.visibility)
            self.assertEqual("execution_sync", doc.metadata["source_kind"])
        serialized = "\n".join([str(doc.to_dict()) for doc in bundle.documents] + [chunk.text_for_embedding + chunk.text_for_llm for chunk in bundle.chunks])
        self.assertNotIn("OCR_SECRET_SHOULD_NOT_APPEAR", serialized)
        self.assertNotIn("BASE64_SECRET_SHOULD_NOT_APPEAR", serialized)
        self.assertNotIn("PRIVATE_USER_NOTE_SHOULD_NOT_APPEAR", serialized)
        self.assertNotIn("PARSED_OCR_SECRET_SHOULD_NOT_APPEAR", serialized)
        self.assertNotIn("alipay_screenshots", serialized)

    def test_execution_profile_can_retrieve_execution_sync_docs(self):
        self.agent.write_json(
            "db/execution_sync/actual_trades/2026-05-20.json",
            {
                "trade_date": "2026-05-20",
                "updated_at": "2026-05-20T15:00:00+08:00",
                "items": [
                    {
                        "trade_id": "trade-1",
                        "operation_type": "buy",
                        "trade_date": "2026-05-20",
                        "fund_code": "F1",
                        "fund_name": "Fund One",
                        "amount": 100.0,
                        "status": "submitted",
                        "confirm_date": "2026-05-21",
                    }
                ],
            },
        )
        bundle = collect_execution_sync_documents(self.agent.root)
        upsert_documents(self.agent.root, bundle.documents)
        upsert_chunks(self.agent.root, bundle.chunks)

        normal_plan = build_rag_query_plan("Fund One actual trade confirmation", query_date="2026-05-20", retrieval_profile="copilot_qa")
        normal = retrieve_rag_evidence(self.agent.root, normal_plan, write_trace_file=False)
        self.assertEqual([], normal["hits"])
        self.assertEqual("execution_boundary", normal["rejected_samples"][0]["reason"])

        execution_plan = build_rag_query_plan(
            "Fund One actual trade confirmation",
            query_date="2026-05-20",
            retrieval_profile="execution",
            intent="execution_explain",
            include_execution=True,
        )
        result = retrieve_rag_evidence(self.agent.root, execution_plan, write_trace_file=False)
        self.assertGreaterEqual(len(result["hits"]), 1)
        hit = result["hits"][0]
        self.assertEqual("execution_sync", hit["source_kind"])
        self.assertEqual("execution", hit["domain"])
        self.assertEqual("execution_only", hit["learning_scope"])
        self.assertEqual("execution_only", hit["visibility"])

    def test_default_all_ingest_excludes_execution_sync_source(self):
        self.assertNotIn("execution_sync", DEFAULT_SOURCES)
        self.agent.write_json(
            "db/execution_sync/actual_trades/2026-05-20.json",
            {
                "trade_date": "2026-05-20",
                "items": [{"trade_id": "trade-1", "operation_type": "buy", "trade_date": "2026-05-20", "fund_code": "F1"}],
            },
        )

        args = build_ingest_parser().parse_args(["--date", "2026-05-20", "--all", "--dry-run"])
        result = run_ingest(self.agent.root, args)

        self.assertNotIn("execution_sync", result["domains"])
        self.assertTrue(all(source["source_kind"] != "execution_sync" for source in result["sources"]))


if __name__ == "__main__":
    unittest.main()
