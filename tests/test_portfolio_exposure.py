from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from portfolio_exposure import analyze_portfolio_exposure, infer_market_bucket, infer_strategy_bucket


class PortfolioExposureTests(unittest.TestCase):
    def test_infer_market_bucket(self):
        self.assertEqual(infer_market_bucket({"role": "cash_hub", "style_group": "cash_buffer"}), "cash_like")
        self.assertEqual(infer_market_bucket({"role": "fixed_hold", "style_group": "bond_anchor"}), "bond")
        self.assertEqual(infer_market_bucket({"role": "core_dca", "style_group": "sp500_core"}), "overseas_equity")
        self.assertEqual(infer_market_bucket({"role": "tactical", "style_group": "ai"}), "domestic_equity")

    def test_infer_strategy_bucket(self):
        self.assertEqual(infer_strategy_bucket({"role": "core_dca", "style_group": "sp500_core"}), "core_long_term")
        self.assertEqual(infer_strategy_bucket({"role": "cash_hub", "style_group": "cash_buffer"}), "cash_defense")
        self.assertEqual(infer_strategy_bucket({"role": "tactical", "style_group": "industrial_metal"}), "tactical_short_term")
        self.assertEqual(infer_strategy_bucket({"role": "tactical", "style_group": "ai"}), "satellite_mid_term")

    def test_analyze_portfolio_exposure_outputs_concentration(self):
        portfolio = {
            "funds": [
                {"fund_code": "A", "role": "tactical", "style_group": "ai", "current_value": 500.0},
                {"fund_code": "B", "role": "tactical", "style_group": "ai", "current_value": 300.0},
                {"fund_code": "C", "role": "core_dca", "style_group": "sp500_core", "current_value": 200.0},
                {"fund_code": "D", "role": "cash_hub", "style_group": "cash_buffer", "current_value": 200.0},
            ]
        }
        strategy = {
            "allocation": {
                "rebalance_band_pct": 5.0,
                "targets": {
                    "core_long_term": 50.0,
                    "satellite_mid_term": 20.0,
                    "tactical_short_term": 10.0,
                    "cash_defense": 20.0,
                },
            }
        }
        exposure = analyze_portfolio_exposure(portfolio, strategy)
        self.assertEqual(exposure["total_value"], 1200.0)
        self.assertEqual(exposure["largest_style_group"]["name"], "ai")
        self.assertGreaterEqual(exposure["largest_style_group"]["weight_pct"], 60.0)
        self.assertGreaterEqual(exposure["concentration_metrics"]["overseas_weight_pct"], 10.0)
        self.assertTrue(exposure["alerts"])
        self.assertIn("allocation_plan", exposure)
        self.assertIn("by_strategy_bucket", exposure)
        self.assertTrue(exposure["allocation_plan"]["rebalance_needed"])
        self.assertIn("satellite_mid_term", exposure["allocation_plan"]["current_pct"])


if __name__ == "__main__":
    unittest.main()
