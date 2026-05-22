from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from common import long_memory_db_path
from long_memory_store import upsert_memory_record
from rag_index_store import count_rows, upsert_chunks, upsert_documents, write_manifest
from rag_maintenance import purge_domain, rebuild_domain
from rag_models import RagChunk, RagDocument


class RagMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_rebuild_domain_writes_deletable_rag_index_only(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "mem-1",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "rule",
                "title": "Rule",
                "text": "Rule text",
                "status": "strategic",
            },
        )
        result = rebuild_domain(self.agent.root, "long_memory")
        self.assertTrue(result["ok"])
        self.assertTrue(result["wrote"])
        self.assertEqual(1, count_rows(self.agent.root, "documents"))
        self.assertTrue(long_memory_db_path(self.agent.root).exists())

    def test_purge_domain_deactivates_rag_documents_without_source_delete(self):
        doc = RagDocument(
            doc_id="doc-exec",
            source_kind="execution_sync",
            source_path="db/execution_sync/actual_trades/1.json",
            source_record_id="trade-1",
            title="Trade",
            summary="Execution-only trade",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="execution",
            source_tier="execution_memory",
            learning_scope="execution_only",
        )
        chunk = RagChunk(chunk_id="doc-exec:chunk:0", doc_id=doc.doc_id, chunk_index=0, text_for_embedding="trade", text_for_llm="trade")
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [chunk])
        write_manifest(
            self.agent.root,
            {
                "manifest_id": "manifest:execution",
                "scope_key": "2026-05-20:execution:execution_sync",
                "source_kind": "execution_sync",
                "source_path": "db/execution_sync",
                "status": "ok",
            },
        )
        source_path = self.agent.write_json("db/execution_sync/actual_trades/1.json", {"trade_id": "trade-1"})

        result = purge_domain(self.agent.root, "execution")
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["deactivatedDocuments"])
        self.assertTrue(source_path.exists())


if __name__ == "__main__":
    unittest.main()
