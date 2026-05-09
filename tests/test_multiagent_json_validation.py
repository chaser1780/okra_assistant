from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from multiagent_utils import GENERIC_AGENT_SCHEMA, normalize_json_against_schema, parse_json_text, validate_required_paths


class MultiagentJsonValidationTests(unittest.TestCase):
    def test_parse_json_text_handles_fenced_payload(self):
        payload = "```json\n{\"ok\": true}\n```"
        parsed = parse_json_text(payload)
        self.assertEqual(parsed, {"ok": True})

    def test_validate_required_paths_reports_missing_required_fields(self):
        raw = {
            "summary": "test summary",
            "confidence": "0.78",
            "evidence_strength": "strong",
            "portfolio_view": {"regime": "mixed"},
            "fund_views": [{"fund_code": "F1", "thesis": "x"}],
        }
        missing = validate_required_paths(raw, GENERIC_AGENT_SCHEMA)
        self.assertIn("agent_name", missing)
        self.assertIn("mode", missing)
        self.assertIn("portfolio_view.risk_bias", missing)
        self.assertIn("fund_views.0.comment", missing)

    def test_normalize_agent_payload_only_coerces_existing_fields(self):
        raw = {
            "agent_name": "market_analyst",
            "mode": "intraday",
            "summary": "test summary",
            "confidence": "0.78",
            "evidence_strength": "strong",
            "data_freshness": "degraded",
            "abstain": "false",
            "missing_info": [],
            "key_points": [],
            "portfolio_view": {
                "regime": "mixed",
                "risk_bias": "balanced",
                "key_drivers": [],
                "portfolio_implications": [],
            },
            "fund_views": [
                {
                    "fund_code": "F1",
                    "direction": "up",
                    "horizon": "1-5d",
                    "thesis": "x",
                    "catalysts": [],
                    "risks": [],
                    "invalidation": "",
                    "portfolio_impact": "",
                    "action_bias": "hold",
                    "comment": "",
                }
            ],
            "watchouts": [],
        }
        normalized = normalize_json_against_schema(raw, GENERIC_AGENT_SCHEMA)
        self.assertEqual(normalized["evidence_strength"], "high")
        self.assertEqual(normalized["data_freshness"], "mixed")
        self.assertFalse(normalized["abstain"])

if __name__ == "__main__":
    unittest.main()
