from __future__ import annotations

from contextlib import closing
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from long_memory_store import upsert_memory_record
from rag_index_store import count_rows
from rag_ingest import build_parser, run_ingest


class RagIngestTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _args(self, *args: str):
        return build_parser().parse_args(list(args))

    def test_dry_run_summarizes_without_writing_sqlite(self):
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
        result = run_ingest(self.agent.root, self._args("--domain", "long_memory", "--dry-run"))
        self.assertEqual("dry_run", result["mode"])
        self.assertEqual(1, result["summary"]["doc_count"])
        self.assertFalse((self.agent.root / "db" / "rag" / "rag.sqlite").exists())

    def test_write_is_idempotent_for_documents_and_chunks(self):
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
        run_ingest(self.agent.root, self._args("--domain", "long_memory", "--write"))
        run_ingest(self.agent.root, self._args("--domain", "long_memory", "--write"))
        self.assertEqual(1, count_rows(self.agent.root, "documents"))
        self.assertEqual(1, count_rows(self.agent.root, "chunks"))
        self.assertEqual(2, count_rows(self.agent.root, "source_manifests"))
        self.assertEqual(1, count_rows(self.agent.root, "active_manifests"))
        self.assertEqual(2, count_rows(self.agent.root, "manifest_documents"))
        self.assertEqual(2, count_rows(self.agent.root, "manifest_chunks"))

    def test_write_deactivates_disappeared_docs_in_same_scope(self):
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
        run_ingest(self.agent.root, self._args("--domain", "long_memory", "--write"))
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "mem-1",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "rule",
                "title": "Rule",
                "text": "Rule text",
                "status": "archived",
            },
        )
        with closing(__import__("sqlite3").connect(self.agent.root / "db" / "long_memory" / "memory.sqlite")) as conn:
            conn.execute("DELETE FROM memory_records WHERE memory_id = 'mem-1'")
            conn.commit()

        result = run_ingest(self.agent.root, self._args("--domain", "long_memory", "--write"))

        self.assertEqual(0, result["summary"]["doc_count"])
        self.assertEqual(1, result["deactivated"][0]["documents"])
        self.assertEqual(1, result["deactivated"][0]["chunks"])

    def test_all_without_date_skips_date_required_sources(self):
        result = run_ingest(self.agent.root, self._args("--all", "--dry-run"))
        skipped = {source["domain"]: source["skipped_reason"] for source in result["sources"] if source["skipped_reason"]}
        self.assertEqual("date_required", skipped["llm_context"])
        self.assertEqual("date_required", skipped["validated_advice"])
        self.assertEqual("date_required", skipped["committee_bundle"])

    def test_all_dates_only_expands_date_required_sources(self):
        result = run_ingest(
            self.agent.root,
            self._args("--all", "--all-dates", "--date-from", "2026-05-20", "--date-to", "2026-05-21", "--dry-run"),
        )

        self.assertEqual(8, result["summary"]["source_count"])
        scopes = [source["scope_key"] for source in result["sources"]]
        self.assertEqual(1, scopes.count("global:long_memory:long_memory"))
        self.assertEqual(1, scopes.count("current:portfolio:portfolio_state"))
        self.assertIn("2026-05-20:context:llm_context", scopes)
        self.assertIn("2026-05-21:context:llm_context", scopes)
        self.assertIn("2026-05-20:decision:validated_advice", scopes)
        self.assertIn("2026-05-21:decision:committee_bundle", scopes)

    def test_missing_llm_context_write_deactivates_previous_same_scope_docs(self):
        self.agent.write_json(
            "db/llm_context/2026-05-20.json",
            {
                "analysis_date": "2026-05-20",
                "generated_at": "2026-05-20T15:00:00+08:00",
                "portfolio_summary": {"total_value": 1000.0},
            },
        )
        first = run_ingest(self.agent.root, self._args("--domain", "llm_context", "--date", "2026-05-20", "--write"))
        self.assertEqual("2026-05-20:context:llm_context", first["sources"][0]["scope_key"])
        (self.agent.root / "db" / "llm_context" / "2026-05-20.json").unlink()

        second = run_ingest(self.agent.root, self._args("--domain", "llm_context", "--date", "2026-05-20", "--write"))

        self.assertEqual("2026-05-20:context:llm_context", second["sources"][0]["scope_key"])
        self.assertEqual(1, second["deactivated"][0]["documents"])
        self.assertEqual(1, second["deactivated"][0]["chunks"])

    def test_write_embed_uses_cache_on_second_run(self):
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
        first = run_ingest(self.agent.root, self._args("--domain", "long_memory", "--write", "--embed", "--embedding-dry-run"))
        second = run_ingest(self.agent.root, self._args("--domain", "long_memory", "--write", "--embed", "--embedding-dry-run"))
        self.assertEqual(1, first["embedding"]["embedded"])
        self.assertEqual(0, second["embedding"]["embedded"])
        self.assertEqual(1, count_rows(self.agent.root, "embedding_cache"))


if __name__ == "__main__":
    unittest.main()
