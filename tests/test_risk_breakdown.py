from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome  # noqa: E402
from app.web_api import OkraWebApi  # noqa: E402
from risk_breakdown import build_risk_breakdowns  # noqa: E402


class RiskBreakdownTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _portfolio_item(self):
        return {"fundCode": "F1", "fundName": "Fund 1", "weight": 0.5, "allowTrade": True}

    def _realtime_item(self):
        return {
            "fund_code": "F1",
            "anomaly_score": 10.0,
            "freshness_age_business_days": 1,
            "stale": True,
            "confidence": 0.5,
            "mode": "proxy_fallback",
            "estimate_change_pct": 1.5,
            "proxy_change_pct": -1.5,
            "effective_change_pct": 2.0,
        }

    def test_breakdown_uses_only_observation_fields_and_keeps_historical_percentile_explicit(self):
        for index, score in enumerate((2, 4, 6, 8, 10), start=1):
            self.agent.write_json(f"db/realtime_monitor/2026-05-{index:02d}.json", {"items": [{"fund_code": "F1", "anomaly_score": score}]})

        rows, summary = build_risk_breakdowns(
            self.agent.root,
            selected_date="2026-05-20",
            portfolio_items=[self._portfolio_item()],
            realtime_items=[self._realtime_item()],
            context_funds=[{"fund_code": "F1", "recent_news": [{"risk_level": "high", "crowding_signal": "crowded", "virality_score": 0.8}]}],
            pending_simulation_actions=[{"fund_code": "F1", "simulation_status": "planned"}],
        )

        row = rows[0]
        self.assertGreater(row["freshnessRisk"], 0)
        self.assertEqual(100.0, row["dataConflictRisk"])
        self.assertEqual(100.0, row["newsRisk"])
        self.assertGreater(row["executionFrictionRisk"], 0)
        self.assertEqual(100.0, row["historicalPercentile"])
        self.assertEqual(5, row["historicalSampleCount"])
        self.assertGreater(row["totalAnomalyScore"], 0)
        self.assertEqual("display_only_risk_breakdown.v1", summary["methodology"])

    def test_missing_realtime_keeps_unavailable_components_explicit(self):
        rows, summary = build_risk_breakdowns(
            self.agent.root,
            selected_date="2026-05-20",
            portfolio_items=[self._portfolio_item()],
            realtime_items=[],
            context_funds=[],
            pending_simulation_actions=[],
        )

        row = rows[0]
        self.assertIsNone(row["freshnessRisk"])
        self.assertIsNone(row["dataConflictRisk"])
        self.assertIsNone(row["volatilityRisk"])
        self.assertTrue(row["dataCoverage"]["isPartial"])
        self.assertIsNone(row["historicalPercentile"])
        self.assertEqual(1, summary["partialCoverageFundCount"])

    def test_portfolio_page_exposes_additive_risk_breakdown_fields(self):
        self.agent.write_json(
            "db/portfolio_state/current.json",
            {
                "as_of_date": "2026-05-20",
                "total_value": 1000.0,
                "holding_pnl": 0.0,
                "funds": [
                    {
                        "fund_code": "F1",
                        "fund_name": "Fund 1",
                        "role": "tactical",
                        "style_group": "growth",
                        "current_value": 1000.0,
                        "cost_basis_value": 1000.0,
                        "holding_units": 500.0,
                        "last_valuation_nav": 2.0,
                    }
                ],
            },
        )
        self.agent.write_json(
            "db/realtime_monitor/2026-05-20.json",
            {"report_date": "2026-05-20", "items": [self._realtime_item()]},
        )
        self.agent.write_json(
            "db/llm_context/2026-05-20.json",
            {"analysis_date": "2026-05-20", "funds": [{"fund_code": "F1", "recent_news": []}]},
        )

        page = OkraWebApi(self.agent.root).portfolio_page("2026-05-20")
        portfolio = page["portfolio"]

        self.assertIn("riskBreakdown", portfolio)
        self.assertIn("riskSummary", portfolio)
        self.assertEqual("F1", portfolio["riskBreakdown"][0]["fundCode"])
        self.assertIn("riskScatter", portfolio)
        self.assertIn("history", portfolio)


if __name__ == "__main__":
    unittest.main()
