from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import business_day_gap, classify_intraday_freshness, classify_official_nav_freshness


class CommonFreshnessTests(unittest.TestCase):
    def test_business_day_gap_same_day(self):
        self.assertEqual(business_day_gap("2026-03-11", "2026-03-11"), 0)

    def test_business_day_gap_across_weekend_counts_previous_trading_day(self):
        self.assertEqual(business_day_gap("2026-03-06", "2026-03-09"), 1)

    def test_official_nav_previous_trading_day_is_acceptable(self):
        result = classify_official_nav_freshness("2026-03-11", "2026-03-10")
        self.assertEqual(result["status"], "previous_trading_day")
        self.assertTrue(result["is_acceptable"])
        self.assertFalse(result["is_delayed"])

    def test_official_nav_old_data_is_delayed(self):
        result = classify_official_nav_freshness("2026-03-11", "2026-03-05")
        self.assertEqual(result["status"], "delayed")
        self.assertTrue(result["is_delayed"])

    def test_intraday_same_day_is_fresh(self):
        result = classify_intraday_freshness("2026-03-11", "2026-03-11", "基金估值")
        self.assertEqual(result["status"], "same_day")
        self.assertTrue(result["is_fresh"])
        self.assertEqual(result["label"], "基金估值为当日")

    def test_intraday_cross_day_is_stale(self):
        result = classify_intraday_freshness("2026-03-11", "2026-03-07", "基金估值")
        self.assertEqual(result["status"], "cross_day")
        self.assertTrue(result["is_stale"])


if __name__ == "__main__":
    unittest.main()
