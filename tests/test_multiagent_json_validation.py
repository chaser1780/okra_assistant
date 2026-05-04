from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from multiagent_utils import GENERIC_AGENT_SCHEMA, normalize_json_against_schema, parse_json_text
from update_review_memory import REVIEW_MEMORY_SCHEMA


class MultiagentJsonValidationTests(unittest.TestCase):
    def test_parse_json_text_handles_fenced_payload(self):
        payload = "```json\n{\"ok\": true}\n```"
        parsed = parse_json_text(payload)
        self.assertEqual(parsed, {"ok": True})

    def test_normalize_agent_payload_repairs_missing_required_fields(self):
        raw = {
            "summary": "test summary",
            "confidence": "0.78",
            "evidence_strength": "strong",
            "portfolio_view": {"regime": "mixed"},
            "fund_views": [{"fund_code": "F1", "thesis": "x"}],
        }
        normalized = normalize_json_against_schema(
            raw,
            GENERIC_AGENT_SCHEMA,
            defaults={"agent_name": "market_analyst", "mode": "intraday"},
        )
        self.assertEqual(normalized["agent_name"], "market_analyst")
        self.assertEqual(normalized["mode"], "intraday")
        self.assertEqual(normalized["evidence_strength"], "high")
        self.assertEqual(normalized["data_freshness"], "mixed")
        self.assertEqual(normalized["portfolio_view"]["risk_bias"], "")
        self.assertEqual(normalized["fund_views"][0]["fund_code"], "F1")
        self.assertEqual(normalized["fund_views"][0]["comment"], "")
        self.assertEqual(normalized["watchouts"], [])

    def test_normalize_review_memory_payload_repairs_types(self):
        raw = {
            "summary": "nightly",
            "confidence": "55",
            "lessons": [{"type": "signal", "text": "x"}],
            "bias_adjustments": [{"scope": "all", "target": "ai", "adjustment": "be careful", "reason": "noise", "ttl_days": "7"}],
            "agent_feedback": [{"agent_name": "research_manager", "bias": "cautious", "confidence": "0.7", "reason": "sample"}],
        }
        normalized = normalize_json_against_schema(
            raw,
            REVIEW_MEMORY_SCHEMA,
            defaults={"agent_name": "review_memory_agent", "mode": "nightly_review"},
        )
        self.assertEqual(normalized["agent_name"], "review_memory_agent")
        self.assertEqual(normalized["mode"], "nightly_review")
        self.assertEqual(normalized["lessons"][0]["applies_to"], "")
        self.assertEqual(normalized["bias_adjustments"][0]["ttl_days"], 7)
        self.assertAlmostEqual(normalized["agent_feedback"][0]["confidence"], 0.7, places=4)
        self.assertEqual(normalized["watchouts"], [])


if __name__ == "__main__":
    unittest.main()
