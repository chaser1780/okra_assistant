from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome  # noqa: E402
from strategy_simulation import create_experiment, list_experiments, record_action  # noqa: E402


class StrategySimulationTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()
        portfolio = {
            "as_of_date": "2026-08-27",
            "total_value": 1000.0,
            "holding_pnl": 0.0,
            "funds": [
                {"fund_code": "CASH", "fund_name": "Cash", "role": "cash_hub", "current_value": 500.0, "cost_basis_value": 500.0, "holding_units": 500.0, "last_valuation_nav": 1.0},
                {"fund_code": "F1", "fund_name": "Fund 1", "role": "tactical", "current_value": 500.0, "cost_basis_value": 500.0, "holding_units": 500.0, "last_valuation_nav": 1.0},
            ],
        }
        self.agent.write_json("db/portfolio_state/current.json", portfolio)

    def tearDown(self):
        self.agent.cleanup()

    def test_strategy_action_never_mutates_user_portfolio(self):
        created = create_experiment(self.agent.root, {"experimentId": "mean-revert", "label": "均值回归"})
        action = record_action(
            self.agent.root,
            {"experimentId": "mean-revert", "actionId": "a1", "action": "buy", "fundCode": "F1", "amount": 100},
        )
        user_portfolio = json.loads((self.agent.root / "db" / "portfolio_state" / "current.json").read_text(encoding="utf-8"))
        replay = record_action(
            self.agent.root,
            {"experimentId": "mean-revert", "actionId": "a1", "action": "buy", "fundCode": "F1", "amount": 100},
        )

        self.assertTrue(created["experiment"]["experimental"])
        self.assertFalse(created["experiment"]["affectsFormalPortfolio"])
        self.assertEqual(600.0, action["experiment"]["portfolio"]["funds"][1]["current_value"])
        self.assertEqual(500.0, user_portfolio["funds"][1]["current_value"])
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(1, list_experiments(self.agent.root)[0]["actionCount"])

    def test_strategy_simulation_rejects_unknown_fund_and_inactive_experiment(self):
        create_experiment(self.agent.root, {"experimentId": "safe", "label": "Safe"})
        with self.assertRaisesRegex(RuntimeError, "Fund code not found"):
            record_action(self.agent.root, {"experimentId": "safe", "action": "buy", "fundCode": "UNKNOWN", "amount": 10})


if __name__ == "__main__":
    unittest.main()
