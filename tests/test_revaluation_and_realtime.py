from __future__ import annotations

import json
import unittest

from helpers import TempAgentHome


class RevaluationAndRealtimeTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def build_portfolio(self):
        portfolio = {
            "portfolio_name": "测试组合",
            "as_of_date": "2026-03-10",
            "total_value": 1500.0,
            "holding_pnl": 0.0,
            "funds": [
                {
                    "fund_code": "EQ1",
                    "fund_name": "权益基金",
                    "role": "tactical",
                    "style_group": "growth",
                    "current_value": 500.0,
                    "holding_pnl": -20.0,
                    "holding_return_pct": -3.85,
                    "holding_units": 250.0,
                    "last_valuation_nav": 2.0,
                    "units_source": "stored",
                    "cap_value": 1000.0,
                    "allow_trade": True,
                    "cost_basis_value": 520.0,
                    "proxy_symbol": "sh515000",
                    "proxy_name": "科技ETF",
                    "proxy_type": "etf",
                    "category": "active_equity",
                },
                {
                    "fund_code": "QDII1",
                    "fund_name": "QDII基金",
                    "role": "tactical",
                    "style_group": "overseas",
                    "current_value": 600.0,
                    "holding_pnl": 10.0,
                    "holding_return_pct": 1.69,
                    "holding_units": 300.0,
                    "last_valuation_nav": 2.0,
                    "units_source": "stored",
                    "cap_value": 1000.0,
                    "allow_trade": True,
                    "cost_basis_value": 590.0,
                    "proxy_symbol": "sz159941",
                    "proxy_name": "纳指ETF",
                    "proxy_type": "etf",
                    "category": "qdii_index",
                },
                {
                    "fund_code": "CASH",
                    "fund_name": "现金仓",
                    "role": "cash_hub",
                    "style_group": "cash",
                    "current_value": 400.0,
                    "holding_pnl": 0.0,
                    "holding_return_pct": 0.0,
                    "holding_units": 400.0,
                    "last_valuation_nav": 1.0,
                    "units_source": "stored",
                    "locked_amount": 0.0,
                    "allow_trade": True,
                    "cost_basis_value": 400.0,
                    "category": "cash_management",
                },
            ],
        }
        self.agent.write_json("config/portfolio.json", portfolio)
        self.agent.write_json(
            "config/watchlist.json",
            {
                "funds": [
                    {"code": "EQ1", "name": "权益基金", "category": "active_equity"},
                    {"code": "QDII1", "name": "QDII基金", "category": "qdii_index"},
                    {"code": "CASH", "name": "现金仓", "category": "cash_management"},
                ]
            },
        )

    def test_revalue_portfolio_updates_values_and_freshness(self):
        self.build_portfolio()
        self.agent.write_json(
            "raw/quotes/2026-03-11.json",
            {
                "report_date": "2026-03-11",
                "funds": [
                    {
                        "code": "EQ1",
                        "nav": 2.12,
                        "as_of_date": "2026-03-10",
                        "date_match_type": "previous_trading_day",
                        "freshness_label": "官方净值为上一交易日",
                    },
                    {
                        "code": "QDII1",
                        "nav": 1.95,
                        "as_of_date": "2026-03-05",
                        "date_match_type": "delayed",
                        "freshness_label": "官方净值滞后 4 个交易日",
                    },
                    {
                        "code": "CASH",
                        "nav": 1.0,
                        "as_of_date": "2026-03-10",
                        "date_match_type": "previous_trading_day",
                        "freshness_label": "官方净值为上一交易日",
                    },
                ],
            },
        )
        self.agent.write_json("db/estimated_nav/2026-03-11.json", {"items": []})
        self.agent.run_script("revalue_portfolio_official_nav.py", "--date", "2026-03-11")

        valuation = json.loads((self.agent.root / "db" / "portfolio_valuation" / "2026-03-11.json").read_text(encoding="utf-8"))
        portfolio = json.loads((self.agent.root / "config" / "portfolio.json").read_text(encoding="utf-8"))

        self.assertEqual(portfolio["as_of_date"], "2026-03-11")
        eq1 = next(item for item in valuation["items"] if item["fund_code"] == "EQ1")
        qdii = next(item for item in valuation["items"] if item["fund_code"] == "QDII1")
        self.assertEqual(eq1["new_current_value"], 530.0)
        self.assertEqual(eq1["freshness_label"], "官方净值为上一交易日")
        self.assertEqual(qdii["freshness_label"], "官方净值滞后 4 个交易日")
        self.assertEqual(valuation["stale_fund_codes"], ["QDII1"])

    def test_build_realtime_profit_respects_policy_and_outputs_freshness(self):
        self.build_portfolio()
        self.agent.write_json(
            "raw/quotes/2026-03-11.json",
            {
                "report_date": "2026-03-11",
                "funds": [
                    {
                        "code": "EQ1",
                        "nav": 2.12,
                        "day_change_pct": 0.5,
                        "as_of_date": "2026-03-10",
                        "date_match_type": "previous_trading_day",
                        "freshness_label": "官方净值为上一交易日",
                    },
                    {
                        "code": "QDII1",
                        "nav": 1.95,
                        "day_change_pct": -0.2,
                        "as_of_date": "2026-03-05",
                        "date_match_type": "delayed",
                        "freshness_label": "官方净值滞后 4 个交易日",
                    },
                    {
                        "code": "CASH",
                        "nav": 1.0,
                        "day_change_pct": 0.0,
                        "as_of_date": "2026-03-10",
                        "date_match_type": "previous_trading_day",
                        "freshness_label": "官方净值为上一交易日",
                    },
                ],
            },
        )
        self.agent.write_json(
            "db/intraday_proxies/2026-03-11.json",
            {
                "report_date": "2026-03-11",
                "proxies": [
                    {
                        "proxy_fund_code": "EQ1",
                        "change_pct": 1.5,
                        "trade_time": "15:00:00",
                        "freshness_status": "same_day",
                        "freshness_label": "代理行情为当日",
                        "freshness_business_day_gap": 0,
                        "stale": False,
                    },
                    {
                        "proxy_fund_code": "QDII1",
                        "change_pct": -0.8,
                        "trade_time": "15:00:00",
                        "freshness_status": "same_day",
                        "freshness_label": "代理行情为当日",
                        "freshness_business_day_gap": 0,
                        "stale": False,
                    },
                ],
            },
        )
        self.agent.write_json(
            "db/estimated_nav/2026-03-11.json",
            {
                "report_date": "2026-03-11",
                "items": [
                    {
                        "fund_code": "EQ1",
                        "fund_name": "权益基金",
                        "category": "active_equity",
                        "estimate_nav": 2.14,
                        "estimate_change_pct": 0.94,
                        "estimate_time": "15:00",
                        "estimate_date": "2026-03-11",
                        "estimate_freshness_status": "same_day",
                        "estimate_freshness_label": "基金估值为当日",
                        "estimate_freshness_business_day_gap": 0,
                        "official_nav": 2.12,
                        "official_nav_date": "2026-03-10",
                        "official_nav_freshness_status": "previous_trading_day",
                        "official_nav_freshness_label": "官方净值为上一交易日",
                        "official_nav_freshness_business_day_gap": 1,
                        "stale": False,
                        "confidence": 0.72,
                        "status": "ok",
                    },
                    {
                        "fund_code": "QDII1",
                        "fund_name": "QDII基金",
                        "category": "qdii_index",
                        "estimate_nav": 1.92,
                        "estimate_change_pct": -1.5,
                        "estimate_time": "05:00",
                        "estimate_date": "2026-03-07",
                        "estimate_freshness_status": "cross_day",
                        "estimate_freshness_label": "基金估值跨日，滞后 3 个交易日",
                        "estimate_freshness_business_day_gap": 3,
                        "official_nav": 1.95,
                        "official_nav_date": "2026-03-05",
                        "official_nav_freshness_status": "delayed",
                        "official_nav_freshness_label": "官方净值滞后 4 个交易日",
                        "official_nav_freshness_business_day_gap": 4,
                        "stale": True,
                        "confidence": 0.38,
                        "status": "ok",
                    },
                ],
            },
        )

        self.agent.run_script("build_realtime_profit.py", "--date", "2026-03-11")
        payload = json.loads((self.agent.root / "db" / "realtime_monitor" / "2026-03-11.json").read_text(encoding="utf-8"))

        eq1 = next(item for item in payload["items"] if item["fund_code"] == "EQ1")
        qdii = next(item for item in payload["items"] if item["fund_code"] == "QDII1")

        self.assertAlmostEqual(eq1["divergence_pct"], 0.56, places=2)
        self.assertGreater(eq1["position_weight_pct"], 0)
        self.assertGreater(eq1["anomaly_score"], 0)
        self.assertEqual(qdii["freshness_age_business_days"], 4)
        self.assertGreater(qdii["anomaly_score"], eq1["anomaly_score"])

        self.assertEqual(eq1["mode"], "estimate_proxy_aligned")
        self.assertTrue(eq1["estimate_policy_allowed"])
        self.assertEqual(eq1["official_nav_freshness_label"], "官方净值为上一交易日")
        self.assertEqual(qdii["mode"], "proxy_primary")
        self.assertFalse(qdii["estimate_policy_allowed"])
        self.assertTrue(qdii["proxy_policy_allowed"])
        self.assertIn("代理行情", qdii["reason"])
        self.assertEqual(payload["realtime_policy"]["enabled"], True)


if __name__ == "__main__":
    unittest.main()
