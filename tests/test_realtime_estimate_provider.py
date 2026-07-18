from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch_realtime_estimate
from helpers import TempAgentHome


class RealtimeEstimateProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()
        portfolio = {
            "portfolio_name": "test",
            "as_of_date": "2026-03-10",
            "funds": [{"fund_code": "F1", "fund_name": "Fund 1", "role": "tactical", "current_value": 100.0}],
        }
        self.agent.write_json("db/portfolio_state/current.json", portfolio)
        self.agent.write_json("config/watchlist.json", {"funds": [{"code": "F1", "name": "Fund 1", "category": "active_equity"}]})

    def tearDown(self) -> None:
        self.agent.cleanup()

    def test_complete_live_payload_is_not_overwritten_by_stale_fallback(self) -> None:
        live_items = [
            {
                "fund_code": "F1",
                "fund_name": "Fund 1",
                "estimate_nav": 1.02,
                "estimate_change_pct": 2.0,
                "estimate_date": "2026-03-11",
                "stale": False,
                "status": "ok",
                "provider": "fundgz_1234567",
            }
        ]
        self.agent.write_json(
            "db/estimated_nav/2026-03-10.json",
            {
                "report_date": "2026-03-10",
                "provider": "fundgz_1234567",
                "items": [{"fund_code": "F1", "estimate_date": "2026-01-01", "stale": False, "status": "ok"}],
            },
        )

        with (
            patch.object(fetch_realtime_estimate, "build_live_items", return_value=live_items),
            patch.object(fetch_realtime_estimate, "build_quote_derived_items") as quote_fallback,
            patch.object(
                sys,
                "argv",
                [
                    "fetch_realtime_estimate.py",
                    "--agent-home",
                    str(self.agent.root),
                    "--date",
                    "2026-03-11",
                ],
            ),
        ):
            fetch_realtime_estimate.main()

        payload = json.loads((self.agent.root / "db" / "estimated_nav" / "2026-03-11.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["selected_provider"], "fundgz_1234567")
        self.assertEqual(payload["provider"], "fundgz_1234567")
        self.assertEqual(payload["items"], live_items)
        self.assertEqual(len(payload["provider_attempts"]), 1)
        quote_fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
