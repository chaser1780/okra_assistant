from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from portfolio_state import save_portfolio_state


class PortfolioStateTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_save_portfolio_state_defaults_to_runtime_state_without_legacy_write(self):
        portfolio = {
            "portfolio_name": "Test Portfolio",
            "as_of_date": "2026-05-08",
            "total_value": 1000.0,
            "holding_pnl": 0.0,
            "funds": [],
        }
        legacy_path = self.agent.root / "config" / "portfolio.json"
        before_legacy = json.loads(legacy_path.read_text(encoding="utf-8"))

        current_path, snapshot_path = save_portfolio_state(
            self.agent.root,
            portfolio,
            source="official_nav_revaluation",
            event_date="2026-05-08",
            event_type="official_nav_revaluation",
            event_id="nav",
        )

        current = json.loads(current_path.read_text(encoding="utf-8"))
        after_legacy = json.loads(legacy_path.read_text(encoding="utf-8"))

        self.assertEqual(current["total_value"], 1000.0)
        self.assertEqual(snapshot_path.name, "2026-05-08.json")
        self.assertEqual(after_legacy, before_legacy)

    def test_save_portfolio_state_keeps_event_journal_for_same_day_updates(self):
        portfolio = {
            "portfolio_name": "Test Portfolio",
            "as_of_date": "2026-05-08",
            "total_value": 1000.0,
            "holding_pnl": 0.0,
            "funds": [],
        }

        save_portfolio_state(
            self.agent.root,
            portfolio,
            source="official_nav_revaluation",
            event_date="2026-05-08",
            event_type="official_nav_revaluation",
            event_id="nav",
        )
        portfolio["total_value"] = 1100.0
        current_path, snapshot_path = save_portfolio_state(
            self.agent.root,
            portfolio,
            source="portfolio_screenshot_sync",
            event_date="2026-05-08",
            event_type="portfolio_screenshot_sync",
            event_id="screenshot",
        )

        event_dir = self.agent.root / "db" / "portfolio_state" / "events" / "2026-05-08"
        event_files = sorted(path.name for path in event_dir.glob("*.json"))

        self.assertEqual(event_files, ["official_nav_revaluation_nav.json", "portfolio_screenshot_sync_screenshot.json"])
        self.assertEqual(snapshot_path.name, "2026-05-08.json")
        current = json.loads(current_path.read_text(encoding="utf-8"))
        self.assertIn("event_journal_path", current["state_metadata"])


if __name__ == "__main__":
    unittest.main()
