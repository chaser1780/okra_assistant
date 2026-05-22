from __future__ import annotations

from contextlib import closing
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from common import long_memory_db_path
from long_memory_store import upsert_memory_record
from rag_sources import collect_long_memory_documents


class RagMemoryVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_active_memory_is_default_visible(self):
        for status in ("permanent", "strategic", "candidate"):
            upsert_memory_record(
                self.agent.root,
                {
                    "memory_id": f"mem-{status}",
                    "memory_type": "portfolio_policy_memory",
                    "domain": "portfolio",
                    "entity_key": status,
                    "title": status,
                    "text": f"{status} memory",
                    "status": status,
                    "approved_by": "user" if status == "permanent" else "",
                    "approved_at": "2026-05-20T10:00:00+08:00" if status == "permanent" else "",
                    "valid_from": "2026-05-20",
                },
            )
        bundle = collect_long_memory_documents(self.agent.root)
        visibility = {doc.source_record_id: doc.visibility for doc in bundle.documents}
        self.assertEqual("default", visibility["mem-permanent"])
        self.assertEqual("default", visibility["mem-strategic"])
        self.assertEqual("default", visibility["mem-candidate"])

    def test_negative_and_superseded_memory_is_review_only(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "mem-archived",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "archived",
                "title": "archived",
                "text": "archived memory",
                "status": "archived",
                "valid_from": "2026-05-19",
            },
        )
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "mem-superseded",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "superseded",
                "title": "superseded",
                "text": "superseded memory",
                "status": "strategic",
                "valid_from": "2026-05-19",
                "metadata": {"superseded_by": "mem-new"},
            },
        )
        bundle = collect_long_memory_documents(self.agent.root)
        docs = {doc.source_record_id: doc for doc in bundle.documents}
        self.assertEqual("review_only", docs["mem-archived"].visibility)
        self.assertTrue(docs["mem-archived"].is_negative_example)
        self.assertEqual("review_only", docs["mem-superseded"].visibility)
        self.assertEqual("mem-new", docs["mem-superseded"].metadata["superseded_by"])

    def test_missing_timestamps_are_marked_inferred(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "mem-old",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "old",
                "title": "old",
                "text": "old memory",
                "status": "strategic",
                "valid_from": "2026-05-18",
                "created_at": "",
                "updated_at": "",
            },
        )
        with closing(sqlite3.connect(long_memory_db_path(self.agent.root))) as conn:
            conn.execute("UPDATE memory_records SET created_at = '', updated_at = '' WHERE memory_id = 'mem-old'")
            conn.commit()
        doc = next(doc for doc in collect_long_memory_documents(self.agent.root).documents if doc.source_record_id == "mem-old")
        self.assertTrue(doc.metadata["available_from_inferred"])
        self.assertEqual("2026-05-18T23:59:59+08:00", doc.available_from)

    def test_execution_domain_long_memory_is_execution_only(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "mem-execution",
                "memory_type": "execution_memory",
                "domain": "execution",
                "entity_key": "discipline",
                "title": "execution discipline",
                "text": "execution-only lesson",
                "status": "strategic",
                "valid_from": "2026-05-18",
            },
        )
        doc = next(doc for doc in collect_long_memory_documents(self.agent.root).documents if doc.source_record_id == "mem-execution")
        self.assertEqual("execution_only", doc.learning_scope)
        self.assertEqual("execution_only", doc.visibility)
        self.assertEqual("execution_only", doc.metadata["learning_scope"])


if __name__ == "__main__":
    unittest.main()
