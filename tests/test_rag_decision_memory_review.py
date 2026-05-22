from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from long_memory_store import upsert_memory_record
from rag_index_store import upsert_chunks, upsert_documents
from rag_models import RagChunk, RagDocument
from rag_profile_evidence import (
    build_backtest_evidence_pack,
    build_decision_evidence_pack,
    build_memory_evidence_pack,
    build_review_evidence_pack,
)


PROFILE_RAG_TOML = """[rag]
enabled = false

[rag.profile_evidence]
enabled = true
write_trace = false

[rag.profile_evidence.decision]
enabled = true
top_k = 4
min_hits = 1
source_kinds = ["committee_bundle", "validated_advice"]
domains = ["decision"]

[rag.profile_evidence.memory]
enabled = true
top_k = 4
skip_duplicate_permanent = true
source_kinds = ["long_memory"]

[rag.profile_evidence.review]
enabled = true
top_k = 4
source_kinds = ["long_memory"]
domains = ["long_memory", "portfolio", "market", "fund"]
include_negative_memory = true

[rag.profile_evidence.backtest]
enabled = true
top_k = 4
source_kinds = ["long_memory", "validated_advice", "committee_bundle", "portfolio_state"]
strict_no_future = true
"""


class RagDecisionMemoryReviewTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()
        self.agent.write_text("config/rag.toml", PROFILE_RAG_TOML)

    def tearDown(self):
        self.agent.cleanup()

    def _chunk(self, doc: RagDocument) -> RagChunk:
        return RagChunk(
            chunk_id=f"{doc.doc_id}:chunk:0",
            doc_id=doc.doc_id,
            chunk_index=0,
            text_for_embedding=f"{doc.title} {doc.summary}",
            text_for_llm=doc.summary,
        )

    def _insert_doc(self, doc: RagDocument) -> None:
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [self._chunk(doc)])

    def test_decision_profile_missing_committee_bundle_is_missing_not_advice(self):
        pack = build_decision_evidence_pack(self.agent.root, "2026-05-20", committee_bundle={}, validated_advice={})
        self.assertTrue(pack["enabled"])
        self.assertEqual("missing", pack["status"])
        self.assertEqual("missing_committee_bundle", pack["missingData"][0]["reason"])
        self.assertEqual([], pack["hits"])

    def test_decision_profile_only_retrieves_decision_sources(self):
        decision_doc = RagDocument(
            doc_id="decision-doc",
            source_kind="committee_bundle",
            source_path="db/committee_decision_bundle/2026-05-20.json",
            source_record_id="fund:F1",
            title="committee F1 decision",
            summary="existing committee decision says hold F1",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="decision",
            source_tier="decision_trace",
            entity_type="fund",
            entity_id="F1",
            fund_codes=["F1"],
        )
        news_doc = RagDocument(
            doc_id="news-doc",
            source_kind="evidence_item",
            source_path="db/llm_context/2026-05-20.json",
            source_record_id="news:F1",
            title="news says buy",
            summary="news should not create a new decision",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="market",
            source_tier="daily_evidence",
            entity_type="fund",
            entity_id="F1",
            fund_codes=["F1"],
        )
        self._insert_doc(decision_doc)
        self._insert_doc(news_doc)
        pack = build_decision_evidence_pack(
            self.agent.root,
            "2026-05-20",
            committee_bundle={"fund_decisions": [{"fund_code": "F1", "proposed_action": "hold"}]},
            validated_advice={},
        )
        self.assertEqual("ok", pack["status"])
        self.assertEqual(["committee_bundle"], sorted({hit["sourceKind"] for hit in pack["hits"]}))
        self.assertFalse(pack["guardrails"]["mayGenerateNewAdvice"])

    def test_memory_profile_marks_same_entity_permanent_duplicate(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "mem-f1-permanent",
                "memory_type": "fund_profile_memory",
                "domain": "fund",
                "entity_key": "F1",
                "title": "F1 permanent profile",
                "text": "F1 behaves defensively in drawdowns.",
                "status": "permanent",
                "approved_by": "user",
                "approved_at": "2026-05-19T10:00:00+08:00",
                "valid_from": "2026-05-19",
            },
        )
        self.agent.run_script("rag_ingest.py", "--date", "2026-05-21", "--write", "--domain", "long_memory")
        pack = build_memory_evidence_pack(
            self.agent.root,
            "2026-05-21",
            domain="fund",
            entity_key="F1",
            title="F1 profile candidate",
            text="F1 behaves defensively in drawdowns.",
        )
        self.assertTrue(pack["memoryCheck"]["duplicatePermanent"])
        self.assertTrue(pack["memoryCheck"]["skipWriteRecommended"])

    def test_run_long_memory_analysis_attaches_memory_check_metadata(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "mem-short-term-regime",
                "memory_type": "market_regime_memory",
                "domain": "market",
                "entity_key": "short_term_regime",
                "title": "Recent short-term market regime",
                "text": "Recent 5-10 day signals favor cautious, confirmation-based positioning.",
                "status": "permanent",
                "approved_by": "user",
                "approved_at": "2026-03-10T10:00:00+08:00",
                "valid_from": "2026-03-10",
            },
        )
        self.agent.run_script("rag_ingest.py", "--date", "2026-03-10", "--write", "--domain", "long_memory")
        self.agent.write_json("db/daily_workspace/2026-03-10/today_analysis_meta.json", {"memory_eligible": True, "analysis_run_id": "run-1", "analysis_quality": "ok"})
        self.agent.write_json("db/llm_context/2026-03-10.json", {"analysis_date": "2026-03-10", "funds": []})
        self.agent.write_json("db/committee_advice/2026-03-10.json", {})
        result = self.agent.run_script("run_long_memory_analysis.py", "--date", "2026-03-10", "--mock")
        payload = json.loads((self.agent.root / "db" / "daily_workspace" / "2026-03-10" / "memory_cycle.json").read_text(encoding="utf-8"))
        self.assertIn("rag_memory_checks", payload)
        self.assertTrue(payload["rag_memory_checks"])
        self.assertIn("rag_memory_check", payload["written_records"][0]["metadata"])
        self.assertIn('"written_count"', result.stdout)

    def test_review_profile_labels_archived_memory_as_negative_example(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "mem-archived",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "old_rule",
                "title": "archived timing rule",
                "text": "Old add timing rule failed.",
                "status": "archived",
                "valid_from": "2026-05-01",
            },
        )
        self.agent.run_script("rag_ingest.py", "--date", "2026-05-21", "--write", "--domain", "long_memory")
        pack = build_review_evidence_pack(
            self.agent.root,
            "2026-05-20",
            review_date="2026-05-21",
            diagnostic_labels=["timing rule failed"],
        )
        self.assertTrue(pack["hits"])
        self.assertTrue(any(hit["negativeExample"] for hit in pack["hits"]))
        self.assertTrue(any(citation["negativeExample"] for citation in pack["citations"]))

    def test_backtest_profile_audits_no_future_and_excludes_future_hits(self):
        future_doc = RagDocument(
            doc_id="future-doc",
            source_kind="validated_advice",
            source_path="db/validated_advice/2026-05-21.json",
            source_record_id="future",
            title="future validated advice",
            summary="future advice must not be visible",
            as_of_date="2026-05-21",
            available_from="2026-05-21T09:00:00+08:00",
            domain="decision",
            source_tier="structured_current",
            entity_type="fund",
            entity_id="F1",
            fund_codes=["F1"],
        )
        past_doc = RagDocument(
            doc_id="past-doc",
            source_kind="validated_advice",
            source_path="db/validated_advice/2026-05-20.json",
            source_record_id="past",
            title="past validated advice",
            summary="past advice is visible",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="decision",
            source_tier="structured_current",
            entity_type="fund",
            entity_id="F1",
            fund_codes=["F1"],
        )
        self._insert_doc(future_doc)
        self._insert_doc(past_doc)
        pack = build_backtest_evidence_pack(self.agent.root, "2026-05-20", fund_codes=["F1"], mode="baseline")
        self.assertEqual("ok", pack["status"])
        self.assertTrue(pack["noFutureAudit"]["passed"])
        self.assertGreaterEqual(pack["noFutureAudit"]["futureRejectedCount"], 1)
        self.assertEqual(["past-doc"], [hit["docId"] for hit in pack["hits"]])


if __name__ == "__main__":
    unittest.main()
