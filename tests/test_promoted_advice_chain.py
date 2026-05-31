from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from helpers import TempAgentHome  # noqa: E402
from run_promoted_advice_chain import PROMOTED_MODE, run_chain  # noqa: E402


class PromotedAdviceChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def write_inputs(self) -> None:
        portfolio = {
            "portfolio_name": "test",
            "as_of_date": "2026-06-01",
            "total_value": 1250.0,
            "funds": [
                {
                    "fund_code": "DCA1",
                    "fund_name": "Core DCA",
                    "role": "core_dca",
                    "style_group": "core",
                    "current_value": 100.0,
                    "allow_trade": True,
                    "fixed_daily_buy_amount": 25.0,
                    "holding_units": 100.0,
                    "last_valuation_nav": 1.0,
                    "units_source": "stored",
                },
                {
                    "fund_code": "CASH",
                    "fund_name": "Cash",
                    "role": "cash_hub",
                    "style_group": "cash",
                    "current_value": 500.0,
                    "allow_trade": True,
                    "holding_units": 500.0,
                    "last_valuation_nav": 1.0,
                    "units_source": "stored",
                },
                {
                    "fund_code": "TADD",
                    "fund_name": "Add Target",
                    "role": "tactical",
                    "style_group": "growth_rotation",
                    "current_value": 200.0,
                    "cap_value": 800.0,
                    "allow_trade": True,
                    "holding_units": 100.0,
                    "last_valuation_nav": 2.0,
                    "units_source": "stored",
                },
                {
                    "fund_code": "TRED",
                    "fund_name": "Reduce Target",
                    "role": "tactical",
                    "style_group": "industrial_metal",
                    "current_value": 250.0,
                    "cap_value": 800.0,
                    "allow_trade": True,
                    "holding_units": 125.0,
                    "last_valuation_nav": 2.0,
                    "units_source": "stored",
                },
            ],
        }
        self.agent.write_json("db/portfolio_state/current.json", portfolio)
        self.agent.write_json("db/portfolio_state/snapshots/2026-06-01.json", portfolio)
        self.agent.write_json(
            "db/daily_scores/2026-06-01.json",
            {
                "report_date": "2026-06-01",
                "generated_at": "2026-06-01T14:00:00+08:00",
                "funds": [
                    {"code": "TADD", "name": "Add Target", "score": 88.0, "action": "add", "confidence": 0.84, "reasons": ["strong score"], "risk_flags": []},
                    {"code": "TRED", "name": "Reduce Target", "score": 24.0, "action": "avoid", "confidence": 0.8, "reasons": ["weak score"], "risk_flags": ["drawdown"]},
                ],
            },
        )
        self.agent.write_json(
            "db/llm_context/2026-06-01.json",
            {
                "analysis_date": "2026-06-01",
                "generated_at": "2026-06-01T14:00:00+08:00",
                "funds": [
                    {"fund_code": "DCA1", "fund_name": "Core DCA", "role": "core_dca"},
                    {"fund_code": "CASH", "fund_name": "Cash", "role": "cash_hub"},
                    {
                        "fund_code": "TADD",
                        "fund_name": "Add Target",
                        "role": "tactical",
                        "quote": {"day_change_pct": 1.2, "as_of_date": "2026-05-29", "retrieved_at": "2026-06-01T14:00:00+08:00"},
                        "intraday_proxy": {"change_pct": 2.1, "trade_date": "2026-06-01", "retrieved_at": "2026-06-01T14:00:00+08:00"},
                        "recent_news": [{"title": "positive catalyst", "summary": "positive", "impact": "positive", "published_at": "2026-06-01T10:00:00+08:00"}],
                    },
                    {
                        "fund_code": "TRED",
                        "fund_name": "Reduce Target",
                        "role": "tactical",
                        "quote": {"day_change_pct": -2.5, "as_of_date": "2026-05-29", "retrieved_at": "2026-06-01T14:00:00+08:00"},
                        "intraday_proxy": {"change_pct": -1.7, "trade_date": "2026-06-01", "retrieved_at": "2026-06-01T14:00:00+08:00"},
                        "recent_news": [{"title": "risk", "summary": "risk", "impact": "negative", "published_at": "2026-06-01T10:00:00+08:00"}],
                    },
                ],
                "evidence_items": [],
            },
        )
        self.agent.write_json("db/evidence_index/2026-06-01.json", {"items": []})

    def test_promoted_chain_does_not_require_existing_validated_advice_seed(self) -> None:
        self.write_inputs()

        status_path, status = run_chain(self.agent.root, "2026-06-01", generated_at="2026-06-01T14:30:00+08:00")

        self.assertTrue(status_path.exists())
        self.assertFalse((self.agent.root / "db" / "validated_advice" / "legacy_seed.json").exists())
        self.assertEqual(PROMOTED_MODE, status["summary"]["advice_mode"])
        self.assertGreater(status["summary"]["validated_action_count"], 0)
        self.assertTrue((self.agent.root / "db" / "action_seed" / "2026-06-01.json").exists())
        raw = json.loads((self.agent.root / "db" / "llm_raw" / "2026-06-01.json").read_text(encoding="utf-8"))
        self.assertEqual(PROMOTED_MODE, raw["mode"])
        self.assertTrue(raw["promoted_chain"]["native_independent_of_legacy_validated_seed"])
        validated = json.loads((self.agent.root / "db" / "validated_advice" / "2026-06-01.json").read_text(encoding="utf-8"))
        self.assertEqual(PROMOTED_MODE, validated["advice_mode"])
        self.assertEqual("action_debate_promoted", validated["decision_source"])
        self.assertTrue(validated["dca_actions"])
        self.assertTrue((self.agent.root / "db" / "decisions" / "2026-06-01.json").exists())


if __name__ == "__main__":
    unittest.main()
