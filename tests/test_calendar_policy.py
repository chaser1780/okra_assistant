from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import TradingCalendarUnavailableError, is_trading_day, previous_trading_day, trading_days_between
from helpers import TempAgentHome


class TradingCalendarPolicyTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_trading_day_lookup_raises_when_calendar_is_unconfigured(self):
        self.agent.write_json("config/trading_calendar.json", {"holidays": [], "makeup_trading_days": []})

        for lookup in (
            lambda: is_trading_day(self.agent.root, "2026-06-01"),
            lambda: previous_trading_day(self.agent.root, "2026-06-01"),
            lambda: trading_days_between(self.agent.root, "2026-05-31", "2026-06-01"),
        ):
            with self.assertRaises(TradingCalendarUnavailableError) as raised:
                lookup()
            self.assertEqual("trading_calendar_unconfigured", raised.exception.status["reason"])

    def test_trading_day_lookup_raises_when_target_is_outside_calendar_coverage(self):
        self.agent.write_json(
            "config/trading_calendar.json",
            {
                "source": "test-fixture",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "coverage_start": "2026-01-01",
                "coverage_end": "2026-05-31",
                "holidays": [],
                "makeup_trading_days": [],
            },
        )

        for lookup in (
            lambda: is_trading_day(self.agent.root, "2026-06-01"),
            lambda: previous_trading_day(self.agent.root, "2026-06-01"),
            lambda: trading_days_between(self.agent.root, "2026-05-31", "2026-06-01"),
        ):
            with self.assertRaises(TradingCalendarUnavailableError) as raised:
                lookup()
            self.assertEqual("trading_calendar_date_out_of_coverage", raised.exception.status["reason"])


if __name__ == "__main__":
    unittest.main()
