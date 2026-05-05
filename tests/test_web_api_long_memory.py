from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.web_api import OkraWebApi
from helpers import TempAgentHome
from long_memory_store import stable_memory_id, upsert_memory_record


class WebApiLongMemoryTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_snapshot_exposes_long_memory_for_react_app(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_type": "fund_profile_memory",
                "domain": "fund",
                "entity_key": "F1",
                "title": "F1 profile",
                "text": "F1 add advice has been weak in choppy markets.",
                "status": "strategic",
                "confidence": 0.8,
            },
        )
        upsert_memory_record(
            self.agent.root,
            {
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "cash_floor",
                "title": "Cash floor",
                "text": "Keep a minimum cash floor.",
                "status": "strategic",
                "confidence": 0.9,
            },
        )
        api = OkraWebApi(self.agent.root)
        snapshot = api.snapshot()
        self.assertIn("longMemory", snapshot)
        self.assertIn("dailyFirstOpen", snapshot)
        self.assertEqual(snapshot["longMemory"]["counts"]["fund"], 1)
        self.assertEqual(snapshot["longMemory"]["counts"]["pending"], 1)
        self.assertEqual(snapshot["longMemory"]["pending"][0]["entity_key"], "cash_floor")

    def test_fund_detail_exposes_fund_memory(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_type": "fund_profile_memory",
                "domain": "fund",
                "entity_key": "F1",
                "title": "F1 profile",
                "text": "F1 follows the proxy with one day lag.",
                "status": "strategic",
                "confidence": 0.7,
            },
        )
        api = OkraWebApi(self.agent.root)
        detail = api.fund_detail("F1")
        self.assertEqual(detail["longMemory"]["fund"][0]["title"], "F1 profile")

    def test_long_memory_action_promotes_to_permanent(self):
        memory_id = stable_memory_id("portfolio", "cash_floor", "Cash floor", "portfolio_policy_memory")
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": memory_id,
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "cash_floor",
                "title": "Cash floor",
                "text": "Keep a minimum cash floor.",
                "status": "strategic",
                "confidence": 0.9,
            },
        )
        api = OkraWebApi(self.agent.root)
        result = api.long_memory_action({"memoryId": memory_id, "action": "approve", "note": "confirmed in UI"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["record"]["status"], "permanent")
        self.assertEqual(result["record"]["approved_by"], "user")


if __name__ == "__main__":
    unittest.main()
