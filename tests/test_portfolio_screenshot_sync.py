from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from helpers import TempAgentHome
from sync_portfolio_from_screenshots import apply_sync_preview, build_sync_preview, normalize_fund_name


class PortfolioScreenshotSyncTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()
        self.agent.write_json(
            "config/portfolio.json",
            {
                "portfolio_name": "测试组合",
                "as_of_date": "2026-04-15",
                "total_value": 2500.0,
                "holding_pnl": 100.0,
                "funds": [
                    {
                        "fund_code": "017641",
                        "fund_name": "摩根标普500指数(QDII)人民币A",
                        "role": "core_dca",
                        "style_group": "sp500_core",
                        "current_value": 1600.0,
                        "holding_pnl": 10.0,
                        "holding_return_pct": 0.63,
                        "holding_units": 100.0,
                        "cost_basis_value": 1590.0,
                        "units_source": "derived_from_official_nav",
                    },
                    {
                        "fund_code": "025857",
                        "fund_name": "华夏中证电网设备主题ETF联接C",
                        "role": "tactical",
                        "style_group": "grid_equipment",
                        "current_value": 900.0,
                        "holding_pnl": -20.0,
                        "holding_return_pct": -2.17,
                        "holding_units": 300.0,
                        "cost_basis_value": 920.0,
                        "units_source": "derived_from_official_nav",
                    },
                ],
            },
        )
        self.agent.write_json(
            "db/portfolio_state/current.json",
            json.loads((self.agent.root / "config" / "portfolio.json").read_text(encoding="utf-8")),
        )
        self.agent.write_json(
            "config/watchlist.json",
            {
                "funds": [
                    {
                        "code": "NEW1",
                        "name": "广发中证机器人ETF联接C",
                        "category": "etf_linked",
                        "benchmark": "机器人主题指数",
                        "risk_level": "high",
                    }
                ]
            },
        )

    def tearDown(self):
        self.agent.cleanup()

    def test_normalize_fund_name_removes_non_essential_tokens(self):
        self.assertEqual(
            normalize_fund_name("摩根标普500指数(QDII)A"),
            normalize_fund_name("摩根标普500指数(QDII)人民币A"),
        )

    def test_build_sync_preview_matches_existing_holdings(self):
        preview = build_sync_preview(
            self.agent.root,
            [
                {
                    "display_name": "摩根标普500指数(QDII)A",
                    "current_value": 1653.34,
                    "daily_pnl": 14.64,
                    "holding_pnl": 3.34,
                    "holding_return_pct": 0.21,
                    "page_index": 1,
                    "row_index": 1,
                },
                {
                    "display_name": "华夏中证电网设备主题ETF联接C",
                    "current_value": 1092.48,
                    "daily_pnl": 4.68,
                    "holding_pnl": -18.53,
                    "holding_return_pct": -1.67,
                    "page_index": 1,
                    "row_index": 2,
                },
            ],
            [Path("page1.jpg")],
            "alipay",
            "2026-04-15",
        )
        self.assertTrue(preview["apply_ready"])
        self.assertEqual(len(preview["matched_items"]), 2)
        self.assertEqual(preview["matched_items"][0]["matched_fund_code"], "017641")
        self.assertEqual(preview["matched_items"][1]["matched_fund_code"], "025857")
        self.assertFalse(preview["unmatched_detected"])
        self.assertFalse(preview["missing_portfolio_funds"])

    def test_apply_sync_preview_updates_values_and_can_zero_missing(self):
        preview = {
            "provider": "alipay",
            "image_count": 2,
            "matched_items": [
                {
                    "matched_fund_code": "017641",
                    "match_status": "matched",
                    "current_value": 1653.34,
                    "holding_pnl": 3.34,
                    "holding_return_pct": 0.21,
                    "derived_cost_basis_value": 1650.0,
                }
            ],
            "missing_portfolio_funds": [
                {"fund_code": "025857", "fund_name": "华夏中证电网设备主题ETF联接C", "current_value": 900.0}
            ],
            "new_fund_candidates": [],
            "unmatched_detected": [],
        }
        summary = apply_sync_preview(self.agent.root, preview, sync_date="2026-04-16", drop_missing=True, auto_add_new=False)
        portfolio = json.loads((self.agent.root / "db" / "portfolio_state" / "current.json").read_text(encoding="utf-8"))
        sp500 = next(item for item in portfolio["funds"] if item["fund_code"] == "017641")
        grid = next(item for item in portfolio["funds"] if item["fund_code"] == "025857")

        self.assertEqual(summary["updated_fund_count"], 1)
        self.assertEqual(summary["dropped_missing_count"], 1)
        self.assertEqual(sp500["current_value"], 1653.34)
        self.assertEqual(sp500["holding_pnl"], 3.34)
        self.assertEqual(sp500["cost_basis_value"], 1650.0)
        self.assertEqual(grid["current_value"], 0.0)
        self.assertEqual(grid["holding_units"], 0.0)
        self.assertEqual(portfolio["as_of_date"], "2026-04-16")

    def test_build_sync_preview_identifies_new_fund_candidates(self):
        preview = build_sync_preview(
            self.agent.root,
            [
                {
                    "display_name": "广发中证机器人ETF联接C",
                    "current_value": 888.88,
                    "daily_pnl": 6.66,
                    "holding_pnl": 12.34,
                    "holding_return_pct": 1.41,
                    "page_index": 1,
                    "row_index": 1,
                }
            ],
            [Path("page_new.jpg")],
            "alipay",
            "2026-04-15",
        )
        self.assertTrue(preview["apply_ready"])
        self.assertEqual(len(preview["new_fund_candidates"]), 1)
        self.assertEqual(preview["new_fund_candidates"][0]["matched_fund_code"], "NEW1")
        self.assertEqual(preview["new_fund_candidates"][0]["match_status"], "not_in_current_portfolio")

    def test_apply_sync_preview_can_auto_add_new_funds(self):
        preview = {
            "provider": "alipay",
            "image_count": 1,
            "matched_items": [
                {
                    "display_name": "广发中证机器人ETF联接C",
                    "matched_fund_code": "NEW1",
                    "matched_fund_name": "广发中证机器人ETF联接C",
                    "match_source": "watchlist",
                    "match_status": "not_in_current_portfolio",
                    "category": "etf_linked",
                    "benchmark": "机器人主题指数",
                    "style_group": "",
                    "role": "",
                    "proxy_symbol": "",
                    "proxy_name": "",
                    "definition_item": {},
                    "current_value": 888.88,
                    "holding_pnl": 12.34,
                    "holding_return_pct": 1.41,
                    "derived_cost_basis_value": 876.54,
                }
            ],
            "new_fund_candidates": [
                {
                    "matched_fund_code": "NEW1",
                    "matched_fund_name": "广发中证机器人ETF联接C",
                }
            ],
            "missing_portfolio_funds": [],
            "unmatched_detected": [],
        }
        summary = apply_sync_preview(self.agent.root, preview, sync_date="2026-04-16", drop_missing=False, auto_add_new=True)
        portfolio = json.loads((self.agent.root / "db" / "portfolio_state" / "current.json").read_text(encoding="utf-8"))
        definition = json.loads((self.agent.root / "config" / "portfolio_definition.json").read_text(encoding="utf-8"))
        added = next(item for item in portfolio["funds"] if item["fund_code"] == "NEW1")
        definition_item = next(item for item in definition["funds"] if item["fund_code"] == "NEW1")

        self.assertEqual(summary["added_fund_count"], 1)
        self.assertIn("NEW1", summary["added_fund_codes"])
        self.assertEqual(added["current_value"], 888.88)
        self.assertEqual(added["holding_pnl"], 12.34)
        self.assertEqual(added["cost_basis_value"], 876.54)
        self.assertEqual(definition_item["opening_state"]["current_value"], 888.88)


if __name__ == "__main__":
    unittest.main()
