from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from long_memory_store import upsert_memory_record
from rag_sources import (
    collect_committee_bundle_documents,
    collect_llm_context_documents,
    collect_long_memory_documents,
    collect_portfolio_documents,
    collect_validated_advice_documents,
)


class RagSourcesTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_long_memory_documents_read_sqlite_and_map_visibility(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "mem-permanent",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "core_rule",
                "title": "核心规则",
                "text": "核心仓只做固定定投。",
                "status": "permanent",
                "approved_by": "user",
                "approved_at": "2026-05-20T10:00:00+08:00",
                "valid_from": "2026-05-20",
                "metadata": {"fund_codes": ["017641"]},
            },
        )
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "mem-rejected",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "old_rule",
                "title": "旧规则",
                "text": "这是一条被拒绝的旧规则。",
                "status": "rejected",
                "valid_from": "2026-05-19",
            },
        )

        bundle = collect_long_memory_documents(self.agent.root)
        docs = {doc.source_record_id: doc for doc in bundle.documents}
        self.assertEqual("ok", bundle.status)
        self.assertEqual("memory_approved", docs["mem-permanent"].source_tier)
        self.assertEqual("default", docs["mem-permanent"].visibility)
        self.assertEqual(["017641"], docs["mem-permanent"].fund_codes)
        self.assertEqual("negative_memory", docs["mem-rejected"].source_tier)
        self.assertEqual("review_only", docs["mem-rejected"].visibility)
        self.assertTrue(docs["mem-rejected"].is_negative_example)

    def test_portfolio_documents_keep_numeric_payload(self):
        self.agent.write_json(
            "db/portfolio_state/current.json",
            {
                "portfolio_name": "测试组合",
                "as_of_date": "2026-05-20",
                "total_value": 1000.0,
                "holding_pnl": 12.5,
                "funds": [
                    {
                        "fund_code": "F1",
                        "fund_name": "Fund One",
                        "current_value": 600.0,
                        "holding_units": 12.0,
                        "holding_return_pct": 3.2,
                        "role": "tactical",
                    }
                ],
            },
        )
        bundle = collect_portfolio_documents(self.agent.root)
        self.assertEqual(2, len(bundle.documents))
        fund_doc = next(doc for doc in bundle.documents if doc.entity_id == "F1")
        self.assertEqual("portfolio_state", fund_doc.source_kind)
        self.assertEqual("fund", fund_doc.domain)
        self.assertEqual(600.0, fund_doc.payload["current_value"])
        self.assertEqual(12.0, fund_doc.payload["holding_units"])

    def test_llm_context_documents_include_evidence_items_with_fund_codes(self):
        self.agent.write_json(
            "db/llm_context/2026-05-20.json",
            {
                "analysis_date": "2026-05-20",
                "generated_at": "2026-05-20T15:00:00+08:00",
                "portfolio_summary": {"total_value": 1000.0},
                "funds": [{"fund_code": "F1", "fund_name": "Fund One", "current_value": 600.0}],
                "evidence_items": [
                    {
                        "evidence_id": "ev-1",
                        "entity_id": "F1",
                        "entity_type": "fund",
                        "evidence_type": "quote_snapshot",
                        "source_tier": "official_market_data",
                        "mapping_mode": "direct_fund",
                        "summary": "Fund One quote",
                        "retrieved_at": "2026-05-20T14:59:00+08:00",
                        "numeric_payload": {"nav": 1.23},
                    }
                ],
            },
        )
        bundle = collect_llm_context_documents(self.agent.root, "2026-05-20")
        evidence_doc = next(doc for doc in bundle.documents if doc.source_kind == "evidence_item")
        self.assertEqual(["F1"], evidence_doc.fund_codes)
        self.assertEqual(1.23, evidence_doc.payload["numeric_payload"]["nav"])
        self.assertTrue(any(doc.source_record_id == "portfolio_summary" for doc in bundle.documents))

    def test_validated_advice_documents_split_actions_and_observations(self):
        self.agent.write_json(
            "db/validated_advice/2026-05-20.json",
            {
                "report_date": "2026-05-20",
                "generated_at": "2026-05-20T15:10:00+08:00",
                "market_view": {"summary": "balanced"},
                "cross_fund_observations": ["集中执行"],
                "tactical_actions": [{"fund_code": "F1", "fund_name": "Fund One", "validated_action": "add", "validated_amount": 100.0}],
                "dca_actions": [],
                "hold_actions": [],
            },
        )
        bundle = collect_validated_advice_documents(self.agent.root, "2026-05-20")
        action_doc = next(doc for doc in bundle.documents if doc.source_record_id.startswith("tactical_actions"))
        self.assertEqual("validated_advice", action_doc.source_kind)
        self.assertEqual(["F1"], action_doc.fund_codes)
        self.assertEqual(100.0, action_doc.payload["validated_amount"])
        self.assertTrue(any(doc.source_record_id.startswith("cross_fund_observation") for doc in bundle.documents))

    def test_committee_bundle_missing_is_non_blocking(self):
        bundle = collect_committee_bundle_documents(self.agent.root, "2026-05-20")
        self.assertEqual("missing", bundle.status)
        self.assertEqual(1, len(bundle.missing_data))
        self.assertEqual([], bundle.documents)
        self.assertEqual("2026-05-20:decision:committee_bundle", bundle.scope_key)

    def test_missing_bundles_use_success_scope_keys(self):
        llm_bundle = collect_llm_context_documents(self.agent.root, "2026-05-20")
        advice_bundle = collect_validated_advice_documents(self.agent.root, "2026-05-20")
        portfolio_bundle = collect_portfolio_documents(self.agent.root, "2026-05-20")

        self.assertEqual("2026-05-20:context:llm_context", llm_bundle.scope_key)
        self.assertEqual("2026-05-20:decision:validated_advice", advice_bundle.scope_key)
        self.assertEqual("current:portfolio:portfolio_state", portfolio_bundle.scope_key)

    def test_committee_bundle_documents_split_fund_decisions(self):
        self.agent.write_json(
            "db/committee_decision_bundle/2026-05-20.json",
            {
                "report_date": "2026-05-20",
                "generated_at": "2026-05-20T15:08:00+08:00",
                "decision_mode": "hold_only",
                "fund_decisions": [{"fund_code": "F1", "fund_name": "Fund One", "proposed_action": "hold", "thesis": "wait"}],
            },
        )
        bundle = collect_committee_bundle_documents(self.agent.root, "2026-05-20")
        self.assertEqual("ok", bundle.status)
        decision_doc = next(doc for doc in bundle.documents if doc.source_record_id.startswith("fund_decision"))
        self.assertEqual(["F1"], decision_doc.fund_codes)
        self.assertEqual("decision_trace", decision_doc.source_tier)


if __name__ == "__main__":
    unittest.main()
