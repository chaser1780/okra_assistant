from __future__ import annotations

from contextlib import closing
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from rag_config import rag_db_path
from rag_index_store import count_rows, deactivate_missing_scope, init_store, upsert_chunks, upsert_documents, write_manifest, write_trace
from rag_models import RagChunk, RagDocument, RagTrace


class RagIndexStoreTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _document(self, summary: str = "Memory summary") -> RagDocument:
        return RagDocument(
            doc_id="doc-1",
            source_kind="long_memory",
            source_path="db/long_memory/memory.sqlite",
            source_record_id="memory-1",
            title="Memory title",
            summary=summary,
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:30:00+08:00",
            domain="fund",
            source_tier="derived_memory",
            visibility="default",
            fund_codes=["001234"],
            payload={"summary": summary},
        )

    def _chunk(self, text: str = "Memory summary") -> RagChunk:
        return RagChunk(
            chunk_id="chunk-1",
            doc_id="doc-1",
            chunk_index=0,
            text_for_embedding=f"标题：Memory title 内容：{text}",
            text_for_llm=text,
        )

    def test_init_store_creates_sqlite_schema_without_network(self):
        path = init_store(self.agent.root)
        self.assertEqual(self.agent.root / "db" / "rag" / "rag.sqlite", path)
        self.assertTrue(path.exists())
        with closing(sqlite3.connect(path)) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("documents", tables)
        self.assertIn("chunks", tables)
        self.assertIn("source_manifests", tables)
        self.assertIn("query_traces", tables)
        self.assertIn("embedding_vectors", tables)

    def test_upsert_documents_and_chunks_are_idempotent(self):
        self.assertEqual(1, upsert_documents(self.agent.root, [self._document()]))
        self.assertEqual(1, upsert_chunks(self.agent.root, [self._chunk()]))
        self.assertEqual(1, upsert_documents(self.agent.root, [self._document("Updated summary")]))
        self.assertEqual(1, upsert_chunks(self.agent.root, [self._chunk("Updated summary")]))
        self.assertEqual(1, count_rows(self.agent.root, "documents"))
        self.assertEqual(1, count_rows(self.agent.root, "chunks"))
        with closing(sqlite3.connect(rag_db_path(self.agent.root))) as conn:
            row = conn.execute("SELECT summary FROM documents WHERE doc_id = 'doc-1'").fetchone()
        self.assertEqual("Updated summary", row[0])

    def test_manifest_can_be_activated(self):
        self.assertEqual(1, upsert_documents(self.agent.root, [self._document()]))
        self.assertEqual(1, upsert_chunks(self.agent.root, [self._chunk()]))
        manifest_id = write_manifest(
            self.agent.root,
            {
                "manifest_id": "manifest-1",
                "scope_key": "2026-05-20:memory:long_memory",
                "source_kind": "long_memory",
                "source_path": "db/long_memory/memory.sqlite",
                "as_of_date": "2026-05-20",
                "status": "ok",
                "doc_count": 1,
                "chunk_count": 1,
            },
            document_ids=["doc-1"],
            chunk_ids=["chunk-1"],
        )
        self.assertEqual("manifest-1", manifest_id)
        self.assertEqual(1, count_rows(self.agent.root, "source_manifests"))
        self.assertEqual(1, count_rows(self.agent.root, "active_manifests"))
        self.assertEqual(1, count_rows(self.agent.root, "manifest_documents"))
        self.assertEqual(1, count_rows(self.agent.root, "manifest_chunks"))

    def test_deactivate_missing_scope_tombstones_stale_docs_and_chunks(self):
        doc = self._document()
        doc.metadata["scope_key"] = "2026-05-20:memory:long_memory"
        chunk = self._chunk()
        chunk.metadata["scope_key"] = "2026-05-20:memory:long_memory"
        stale_doc = self._document("stale")
        stale_doc.doc_id = "doc-stale"
        stale_doc.source_record_id = "memory-stale"
        stale_doc.metadata["scope_key"] = "2026-05-20:memory:long_memory"
        stale_chunk = RagChunk(chunk_id="chunk-stale", doc_id="doc-stale", chunk_index=0, text_for_embedding="stale", text_for_llm="stale", metadata={"scope_key": "2026-05-20:memory:long_memory"})
        upsert_documents(self.agent.root, [doc, stale_doc])
        upsert_chunks(self.agent.root, [chunk, stale_chunk])

        result = deactivate_missing_scope(self.agent.root, "2026-05-20:memory:long_memory", document_ids=["doc-1"], chunk_ids=["chunk-1"])

        self.assertEqual({"documents": 1, "chunks": 1}, result)
        with closing(sqlite3.connect(rag_db_path(self.agent.root))) as conn:
            doc_active = conn.execute("SELECT active FROM documents WHERE doc_id = 'doc-stale'").fetchone()[0]
            chunk_active = conn.execute("SELECT active FROM chunks WHERE chunk_id = 'chunk-stale'").fetchone()[0]
        self.assertEqual(0, doc_active)
        self.assertEqual(0, chunk_active)

    def test_trace_write_persists_rejected_samples(self):
        trace_id = write_trace(
            self.agent.root,
            RagTrace(
                trace_id="trace-1",
                query_plan={"query": "risk", "as_of_date": "2026-05-20"},
                hits=[],
                rejected_samples=[{"reason": "future_data", "doc_id": "doc-future"}],
                missing_data=[{"source_kind": "llm_context"}],
            ),
        )
        self.assertEqual("trace-1", trace_id)
        self.assertEqual(1, count_rows(self.agent.root, "query_traces"))


if __name__ == "__main__":
    unittest.main()
