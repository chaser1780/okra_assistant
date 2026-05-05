from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from long_memory_store import approve_memory, build_execution_memory, build_fund_memory, list_memory_records, search_long_memory, stable_memory_id, upsert_memory_record


class LongMemoryTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_fund_memory_uses_system_advice_reviews_not_trade_execution(self):
        self.agent.write_json(
            "db/review_results/2026-03-10_T1.json",
            {
                "source": "advice",
                "base_date": "2026-03-10",
                "review_date": "2026-03-11",
                "horizon": 1,
                "items": [
                    {
                        "fund_code": "F1",
                        "fund_name": "Advice Fund",
                        "source_action": "add",
                        "source_amount": 200.0,
                        "outcome": "adverse",
                        "diagnostic_label": "signal_failure",
                    }
                ],
            },
        )
        self.agent.write_json(
            "db/execution_reviews/2026-03-10_execution_T1.json",
            {
                "source": "execution",
                "base_date": "2026-03-10",
                "review_date": "2026-03-11",
                "horizon": 1,
                "items": [
                    {
                        "fund_code": "F1",
                        "fund_name": "Advice Fund",
                        "source_action": "reduce",
                        "outcome": "supportive",
                        "diagnostic_label": "good_risk_reduction",
                    }
                ],
            },
        )
        payload = build_fund_memory(self.agent.root)
        record = payload["items"][0]
        self.assertEqual(record["entity_key"], "F1")
        self.assertEqual(record["support_count"], 0)
        self.assertEqual(record["contradiction_count"], 1)
        self.assertEqual(record["metadata"]["by_action"]["add"]["failure"], 1)
        self.assertNotIn("reduce", [key for key, value in record["metadata"]["by_action"].items() if value["count"]])

    def test_permanent_memory_requires_explicit_approval(self):
        memory_id = stable_memory_id("portfolio", "rule_a", "Rule A", "portfolio_policy_memory")
        record = upsert_memory_record(
            self.agent.root,
            {
                "memory_id": memory_id,
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "rule_a",
                "title": "Rule A",
                "text": "A candidate rule.",
                "status": "permanent",
                "confidence": 0.9,
            },
        )
        self.assertEqual(record["status"], "strategic")
        approved = approve_memory(self.agent.root, memory_id, action="approve", note="looks right")
        self.assertEqual(approved["status"], "permanent")
        records = list_memory_records(self.agent.root, status="permanent")
        self.assertEqual(records[0]["memory_id"], memory_id)

    def test_fund_profile_cannot_be_approved_as_permanent_rule(self):
        memory_id = stable_memory_id("fund", "F1", "F1 profile", "fund_profile_memory")
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": memory_id,
                "memory_type": "fund_profile_memory",
                "domain": "fund",
                "entity_key": "F1",
                "title": "F1 profile",
                "text": "F1 advice profile should remain fund learning.",
                "status": "strategic",
                "confidence": 0.8,
            },
        )
        with self.assertRaises(ValueError):
            approve_memory(self.agent.root, memory_id, action="approve", note="not a reusable policy")
        records = list_memory_records(self.agent.root, domain="fund")
        self.assertEqual(records[0]["status"], "strategic")
        self.assertFalse(records[0]["can_promote_permanent"])

    def test_execution_memory_is_separate_from_fund_accuracy(self):
        self.agent.write_json(
            "db/execution_reviews/2026-03-10_execution_T1.json",
            {
                "source": "execution",
                "base_date": "2026-03-10",
                "review_date": "2026-03-11",
                "horizon": 1,
                "items": [
                    {
                        "fund_code": "QDII1",
                        "fund_name": "QDII Fund",
                        "source_action": "add",
                        "outcome": "adverse",
                        "diagnostic_label": "timing_drag",
                        "purchase_confirm_days": 2,
                    }
                ],
            },
        )
        payload = build_execution_memory(self.agent.root)
        self.assertEqual(payload["items"][0]["domain"], "execution")
        self.assertIn("confirmation", payload["items"][0]["entity_key"])
        fund_payload = build_fund_memory(self.agent.root)
        self.assertEqual(fund_payload["items"], [])

    def test_search_long_memory_uses_local_fts(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_type": "execution_memory",
                "domain": "execution",
                "entity_key": "qdii_confirmation_lag_check",
                "title": "QDII confirmation lag",
                "text": "Check QDII confirmation lag before scheduled buys.",
                "status": "strategic",
                "confidence": 0.8,
            },
        )
        hits = search_long_memory(self.agent.root, "QDII confirmation", limit=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["domain"], "execution")

    def test_daily_first_open_demo_writes_workspace(self):
        self.agent.write_json(
            "raw/quotes/2026-05-04.json",
            {"provider": "demo", "funds": []},
        )
        result = self.agent.run_script("run_daily_first_open.py", "--date", "2026-05-04", "--demo", "--force")
        output_path = Path(result.stdout.strip().splitlines()[-1])
        self.assertTrue(output_path.exists())
        workspace = self.agent.root / "db" / "daily_workspace" / "2026-05-04"
        self.assertTrue((workspace / "memory_updates.json").exists())
        self.assertTrue((workspace / "daily_brief.md").exists())


if __name__ == "__main__":
    unittest.main()
