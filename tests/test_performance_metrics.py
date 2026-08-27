from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from performance_metrics import calculate_portfolio_performance  # noqa: E402


class PortfolioPerformanceTests(unittest.TestCase):
    def test_does_not_estimate_return_without_explicit_cashflows(self):
        result = calculate_portfolio_performance([
            {"date": "2026-01-01", "total_value": 1000},
            {"date": "2026-01-02", "total_value": 1200},
        ])
        self.assertEqual("insufficient_cashflow_data", result["status"])
        self.assertFalse(result["twr"]["available"])

    def test_calculates_cashflow_adjusted_twr_and_mwr(self):
        result = calculate_portfolio_performance([
            {"date": "2026-01-01", "total_value": 1000},
            {"date": "2026-01-02", "total_value": 1210, "external_cashflow": 100, "external_cashflow_timing": "end"},
            {"date": "2026-01-03", "total_value": 1221},
        ])
        self.assertEqual("available", result["status"])
        self.assertAlmostEqual(12.0091, result["twr"]["returnPct"], places=4)
        self.assertTrue(result["mwr"]["available"])

    def test_requires_cashflow_timing(self):
        result = calculate_portfolio_performance([
            {"date": "2026-01-01", "total_value": 1000},
            {"date": "2026-01-02", "total_value": 1200, "external_cashflow": 100},
        ])
        self.assertEqual("insufficient_cashflow_data", result["status"])
        self.assertIn("发生时点", result["reason"])


if __name__ == "__main__":
    unittest.main()
