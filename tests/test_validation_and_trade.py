from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from config_mutations import update_fund_cap_value, update_strategy_controls, upsert_watchlist_item
from portfolio_state import load_execution_status, rebuild_portfolio_state
from update_portfolio_from_trade import apply_trade

from helpers import TempAgentHome
from trade_constraints import build_trade_constraints


class ValidationAndTradeTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def build_portfolio(self):
        portfolio = {
            "portfolio_name": "测试组合",
            "as_of_date": "2026-03-10",
            "total_value": 1250.0,
            "holding_pnl": 0.0,
            "funds": [
                {
                    "fund_code": "DCA1",
                    "fund_name": "核心定投基金",
                    "role": "core_dca",
                    "style_group": "core",
                    "current_value": 100.0,
                    "holding_pnl": 0.0,
                    "holding_return_pct": 0.0,
                    "allow_trade": True,
                    "fixed_daily_buy_amount": 25.0,
                    "allow_extra_buys": False,
                    "holding_units": 100.0,
                    "last_valuation_nav": 1.0,
                    "units_source": "stored",
                },
                {
                    "fund_code": "CASH",
                    "fund_name": "现金仓",
                    "role": "cash_hub",
                    "style_group": "cash",
                    "current_value": 500.0,
                    "holding_pnl": 0.0,
                    "holding_return_pct": 0.0,
                    "allow_trade": True,
                    "holding_units": 500.0,
                    "last_valuation_nav": 1.0,
                    "units_source": "stored",
                    "locked_amount": 0.0,
                },
                {
                    "fund_code": "TADD",
                    "fund_name": "战术加仓基金",
                    "role": "tactical",
                    "style_group": "growth",
                    "current_value": 200.0,
                    "holding_pnl": 0.0,
                    "holding_return_pct": 0.0,
                    "allow_trade": True,
                    "cap_value": 500.0,
                    "holding_units": 100.0,
                    "last_valuation_nav": 2.0,
                    "units_source": "stored",
                },
                {
                    "fund_code": "TRED",
                    "fund_name": "战术减仓基金",
                    "role": "tactical",
                    "style_group": "value",
                    "current_value": 250.0,
                    "holding_pnl": -50.0,
                    "holding_return_pct": -16.67,
                    "allow_trade": True,
                    "cap_value": 500.0,
                    "holding_units": 125.0,
                    "last_valuation_nav": 2.0,
                    "units_source": "stored",
                },
                {
                    "fund_code": "BOND",
                    "fund_name": "固定持有债基",
                    "role": "fixed_hold",
                    "style_group": "bond",
                    "current_value": 200.0,
                    "holding_pnl": 0.0,
                    "holding_return_pct": 0.0,
                    "allow_trade": False,
                    "holding_units": 200.0,
                    "last_valuation_nav": 1.0,
                    "units_source": "stored",
                },
            ],
        }
        self.agent.write_json("config/portfolio.json", portfolio)
        self.agent.write_json(
            "config/watchlist.json",
            {
                "funds": [
                    {"code": "DCA1", "name": "核心定投基金", "category": "qdii_index"},
                    {"code": "CASH", "name": "现金仓", "category": "cash_management"},
                    {"code": "TADD", "name": "战术加仓基金", "category": "active_equity"},
                    {"code": "TRED", "name": "战术减仓基金", "category": "active_equity"},
                    {"code": "BOND", "name": "固定持有债基", "category": "bond"},
                ]
            },
        )

    def test_validate_llm_advice_clamps_add_and_preserves_dca(self):
        self.build_portfolio()
        self.agent.write_json(
            "db/llm_advice/2026-03-10.json",
            {
                "market_view": {"regime": "mixed", "summary": "测试", "key_drivers": []},
                "cross_fund_observations": [],
                "fund_decisions": [
                    {
                        "fund_code": "TADD",
                        "action": "add",
                        "suggest_amount": 280.0,
                        "priority": 1,
                        "confidence": 0.8,
                        "thesis": "测试加仓",
                        "evidence": [],
                        "risks": [],
                        "agent_support": ["portfolio_trader", "risk_manager"],
                    }
                ],
            },
        )
        self.agent.run_script("validate_llm_advice.py", "--date", "2026-03-10")
        payload = json.loads((self.agent.root / "db" / "validated_advice" / "2026-03-10.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["fixed_dca_total"], 25.0)
        self.assertEqual(payload["dca_actions"][0]["validated_action"], "scheduled_dca")
        tactical = next(item for item in payload["tactical_actions"] if item["fund_code"] == "TADD")
        self.assertEqual(tactical["validated_action"], "add")
        self.assertEqual(tactical["validated_amount"], 200.0)
        self.assertEqual(payload["cash_hub_available"], 400.0)

    def test_validate_llm_advice_allows_full_exit_reduce(self):
        self.build_portfolio()
        strategy_path = self.agent.root / "config" / "strategy.toml"
        text = strategy_path.read_text(encoding="utf-8").replace("daily_max_trade_amount = 1000.0", "daily_max_trade_amount = 600.0")
        strategy_path.write_text(text, encoding="utf-8")
        self.agent.write_json(
            "db/llm_advice/2026-03-10.json",
            {
                "market_view": {"regime": "mixed", "summary": "测试", "key_drivers": []},
                "cross_fund_observations": [],
                "fund_decisions": [
                    {
                        "fund_code": "TRED",
                        "action": "reduce",
                        "suggest_amount": 240.0,
                        "priority": 1,
                        "confidence": 0.9,
                        "thesis": "测试减仓",
                        "evidence": [],
                        "risks": [],
                        "agent_support": ["portfolio_trader", "risk_manager"],
                    }
                ],
            },
        )
        self.agent.run_script("validate_llm_advice.py", "--date", "2026-03-10")
        payload = json.loads((self.agent.root / "db" / "validated_advice" / "2026-03-10.json").read_text(encoding="utf-8"))
        tactical = next(item for item in payload["tactical_actions"] if item["fund_code"] == "TRED")
        self.assertEqual(tactical["validated_action"], "reduce")
        self.assertEqual(tactical["validated_amount"], 250.0)

    def test_apply_trade_buy_uses_cash_hub_and_precise_units(self):
        portfolio = {
            "funds": [
                {
                    "fund_code": "CASH",
                    "fund_name": "现金仓",
                    "role": "cash_hub",
                    "current_value": 500.0,
                    "holding_pnl": 0.0,
                    "holding_units": 500.0,
                    "last_valuation_nav": 1.0,
                },
                {
                    "fund_code": "T1",
                    "fund_name": "测试基金",
                    "role": "tactical",
                    "current_value": 200.0,
                    "holding_pnl": 0.0,
                    "holding_units": 100.0,
                    "last_valuation_nav": 2.0,
                },
            ]
        }
        updated = apply_trade(portfolio, "T1", "buy", 100.0, trade_nav=2.5)
        cash = next(item for item in updated["funds"] if item["fund_code"] == "CASH")
        target = next(item for item in updated["funds"] if item["fund_code"] == "T1")
        self.assertEqual(cash["current_value"], 400.0)
        self.assertEqual(target["current_value"], 300.0)
        self.assertAlmostEqual(target["holding_units"], 140.0, places=6)
        self.assertEqual(target["last_valuation_nav"], 2.5)

    def test_apply_trade_sell_returns_cash_and_reduces_units(self):
        portfolio = {
            "funds": [
                {
                    "fund_code": "CASH",
                    "fund_name": "现金仓",
                    "role": "cash_hub",
                    "current_value": 300.0,
                    "holding_pnl": 0.0,
                    "holding_units": 300.0,
                    "last_valuation_nav": 1.0,
                },
                {
                    "fund_code": "T1",
                    "fund_name": "测试基金",
                    "role": "tactical",
                    "current_value": 400.0,
                    "holding_pnl": 40.0,
                    "holding_units": 200.0,
                    "last_valuation_nav": 2.0,
                },
            ]
        }
        updated = apply_trade(portfolio, "T1", "sell", 100.0, trade_nav=2.0)
        cash = next(item for item in updated["funds"] if item["fund_code"] == "CASH")
        target = next(item for item in updated["funds"] if item["fund_code"] == "T1")
        self.assertEqual(cash["current_value"], 400.0)
        self.assertEqual(target["current_value"], 300.0)
        self.assertAlmostEqual(target["holding_units"], 150.0, places=6)
        self.assertAlmostEqual(target["cost_basis_value"], 270.0, places=2)

    def test_trade_constraints_lock_recent_buys_and_limit_reduce(self):
        self.build_portfolio()
        portfolio = json.loads((self.agent.root / "config" / "portfolio.json").read_text(encoding="utf-8"))
        for fund in portfolio["funds"]:
            if fund["fund_code"] == "TRED":
                fund["min_hold_days"] = 7
        self.agent.write_json("config/portfolio.json", portfolio)
        self.agent.write_json(
            "db/trade_journal/2026-03-10.json",
            {
                "trade_date": "2026-03-10",
                "items": [
                    {
                        "fund_code": "TRED",
                        "fund_name": "战术减仓基金",
                        "action": "buy",
                        "amount": 150.0,
                        "trade_nav": 2.0,
                        "units": 75.0,
                        "note": "recent buy",
                    }
                ],
            },
        )
        constraints = build_trade_constraints(self.agent.root, portfolio, "2026-03-11")
        self.assertEqual(constraints["TRED"]["locked_amount"], 150.0)
        self.assertEqual(constraints["TRED"]["available_to_sell"], 100.0)

        self.agent.write_json(
            "db/llm_advice/2026-03-11.json",
            {
                "market_view": {"regime": "mixed", "summary": "测试", "key_drivers": []},
                "cross_fund_observations": [],
                "fund_decisions": [
                    {
                        "fund_code": "TRED",
                        "action": "reduce",
                        "suggest_amount": 200.0,
                        "priority": 1,
                        "confidence": 0.9,
                        "thesis": "测试减仓",
                        "evidence": [],
                        "risks": [],
                        "agent_support": ["risk_manager"],
                    }
                ],
            },
        )
        self.agent.run_script("validate_llm_advice.py", "--date", "2026-03-11")
        payload = json.loads((self.agent.root / "db" / "validated_advice" / "2026-03-11.json").read_text(encoding="utf-8"))
        tactical = next(item for item in payload["tactical_actions"] if item["fund_code"] == "TRED")
        self.assertEqual(tactical["validated_amount"], 100.0)
        self.assertTrue(any("锁定期" in note for note in tactical["validation_notes"]))

    def test_record_trade_links_suggestion_and_updates_execution_status(self):
        self.build_portfolio()
        self.agent.write_json(
            "db/llm_advice/2026-03-10.json",
            {
                "market_view": {"regime": "mixed", "summary": "测试", "key_drivers": []},
                "cross_fund_observations": [],
                "fund_decisions": [
                    {
                        "fund_code": "TADD",
                        "action": "add",
                        "suggest_amount": 200.0,
                        "priority": 1,
                        "confidence": 0.8,
                        "thesis": "测试加仓",
                        "evidence": [],
                        "risks": [],
                        "agent_support": ["portfolio_trader"],
                    }
                ],
            },
        )
        self.agent.run_script("validate_llm_advice.py", "--date", "2026-03-10")
        validated = json.loads((self.agent.root / "db" / "validated_advice" / "2026-03-10.json").read_text(encoding="utf-8"))
        suggestion = validated["tactical_actions"][0]
        self.agent.run_script(
            "record_trade.py",
            "--date",
            "2026-03-10",
            "--fund-code",
            "TADD",
            "--fund-name",
            "战术加仓基金",
            "--action",
            "buy",
            "--amount",
            "100",
            "--suggestion-id",
            suggestion["suggestion_id"],
        )
        journal = json.loads((self.agent.root / "db" / "trade_journal" / "2026-03-10.json").read_text(encoding="utf-8"))
        self.assertEqual(journal["items"][0]["suggestion_id"], suggestion["suggestion_id"])
        execution = load_execution_status(self.agent.root, "2026-03-10")
        self.assertEqual(execution["items"][0]["suggestion_id"], suggestion["suggestion_id"])
        self.assertEqual(execution["items"][0]["trade_amount"], 100.0)

    def test_rebuild_portfolio_state_replays_trades(self):
        self.build_portfolio()
        self.agent.write_json(
            "db/trade_journal/2026-03-11.json",
            {
                "trade_date": "2026-03-11",
                "items": [
                    {
                        "fund_code": "TADD",
                        "fund_name": "战术加仓基金",
                        "action": "buy",
                        "amount": 100.0,
                        "trade_nav": 2.0,
                        "units": 50.0,
                    }
                ],
            },
        )
        rebuilt = rebuild_portfolio_state(self.agent.root, "2026-03-11")
        target = next(item for item in rebuilt["funds"] if item["fund_code"] == "TADD")
        self.assertEqual(target["current_value"], 300.0)
        self.assertAlmostEqual(target["holding_units"], 150.0, places=6)

    def test_config_mutations_update_strategy_cap_and_watchlist(self):
        self.build_portfolio()
        strategy_path = update_strategy_controls(
            self.agent.root,
            risk_profile="conservative",
            cash_hub_floor=666.0,
            gross_trade_limit=888.0,
            net_buy_limit=555.0,
            dca_amount=33.0,
            report_mode="daily_report",
            core_target_pct=40.0,
            satellite_target_pct=25.0,
            tactical_target_pct=15.0,
            defense_target_pct=20.0,
            rebalance_band_pct=6.0,
        )
        text = strategy_path.read_text(encoding="utf-8")
        self.assertIn('risk_profile = "conservative"', text)
        self.assertIn("daily_max_net_buy_amount = 555.0", text)
        self.assertIn('report_mode = "daily_report"', text)
        self.assertIn("core_long_term = 40.0", text)
        self.assertIn("rebalance_band_pct = 6.0", text)

        definition_path, current_path = update_fund_cap_value(self.agent.root, "TADD", 777.0)
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        current = json.loads(current_path.read_text(encoding="utf-8"))
        self.assertEqual(next(item for item in definition["funds"] if item["fund_code"] == "TADD")["cap_value"], 777.0)
        self.assertEqual(next(item for item in current["funds"] if item["fund_code"] == "TADD")["cap_value"], 777.0)

        watchlist_path = upsert_watchlist_item(
            self.agent.root,
            code="NEW1",
            name="新增观察基金",
            category="index_equity",
            benchmark="测试基准",
            risk_level="medium",
        )
        watchlist = json.loads(watchlist_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["code"] == "NEW1" for item in watchlist["funds"]))


if __name__ == "__main__":
    unittest.main()
