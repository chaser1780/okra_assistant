from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from helpers import TempAgentHome  # noqa: E402
from run_daily_pipeline import maybe_run_step, step_output_exists  # noqa: E402
from run_promoted_advice_chain import MOCK_MODE, run_chain  # noqa: E402


class PromotedAdviceChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def write_inputs(self) -> None:
        self.agent.write_json("config/benchmark_mappings.json", {"fund_benchmarks": {}})
        for script_name in (
            "action_debate_graph.py",
            "build_action_ticket_shadow.py",
            "build_layered_retrieval_pack.py",
        ):
            self.agent.write_text(f"scripts/{script_name}", f"# {script_name} test fixture\n")
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

        status_path, status = run_chain(self.agent.root, "2026-06-01", generated_at="2026-06-01T14:30:00+08:00", debate_mode="deterministic")

        self.assertTrue(status_path.exists())
        self.assertFalse((self.agent.root / "db" / "validated_advice" / "legacy_seed.json").exists())
        self.assertEqual(MOCK_MODE, status["summary"]["advice_mode"])
        self.assertEqual("ok", status["status"])
        self.assertTrue(status["is_mock"])
        self.assertFalse(status["production_eligible"])
        self.assertEqual("deterministic", status["debate_mode"])
        self.assertEqual("gpt-5.5", status["llm_model"])
        self.assertGreater(status["summary"]["validated_action_count"], 0)
        self.assertTrue((self.agent.root / "db" / "action_seed" / "2026-06-01.json").exists())
        raw = json.loads((self.agent.root / "db" / "llm_raw" / "2026-06-01.json").read_text(encoding="utf-8"))
        self.assertEqual(MOCK_MODE, raw["mode"])
        self.assertTrue(raw["is_mock"])
        self.assertFalse(raw["promoted_chain"]["production_eligible"])
        self.assertTrue(raw["promoted_chain"]["native_independent_of_legacy_validated_seed"])
        validated = json.loads((self.agent.root / "db" / "validated_advice" / "2026-06-01.json").read_text(encoding="utf-8"))
        self.assertEqual(MOCK_MODE, validated["advice_mode"])
        self.assertEqual("action_debate_mock", validated["decision_source"])
        self.assertTrue(validated["advice_is_mock"])
        self.assertFalse(validated["execution_eligible"])
        self.assertFalse(validated["dca_actions"])
        self.assertFalse(validated["tactical_actions"])
        self.assertEqual(4, len(validated["hold_actions"]))
        self.assertIn("Mock action-ticket chain", validated["market_view"]["summary"])
        self.assertNotIn("Compatibility preview only", " ".join(validated["cross_fund_observations"]))
        self.assertTrue(step_output_exists(self.agent.root, "2026-06-01", "run_promoted_advice_chain.py", ["--llm-mock"]))
        self.assertFalse(step_output_exists(self.agent.root, "2026-06-01", "run_promoted_advice_chain.py"))
        with patch("run_daily_pipeline.run_step") as run_step_mock:
            elapsed = maybe_run_step(
                "run_promoted_advice_chain.py",
                self.agent.root,
                "2026-06-01",
                False,
                extra_args=["--llm-mock"],
                resume_existing=True,
            )
        self.assertEqual(0.0, elapsed)
        run_step_mock.assert_not_called()
        self.assertTrue((self.agent.root / "db" / "decisions" / "2026-06-01.json").exists())
        self.assertTrue((self.agent.root / "db" / "decision_traces" / "2026-06-01.json").exists())
        trace = json.loads((self.agent.root / "db" / "decision_traces" / "2026-06-01.json").read_text(encoding="utf-8"))
        self.assertEqual("user_simulation", trace["formalTrack"])
        self.assertTrue(trace["simulationOnly"])
        self.assertTrue(trace["sourceArtifacts"]["validatedAdvice"]["exists"])
        capture = status["replay_snapshot_capture"]
        self.assertEqual("captured", capture["status"])
        self.assertFalse(capture["learning_eligible"])
        self.assertTrue((self.agent.root / capture["manifest_candidate_path"]).exists())
        candidate = json.loads((self.agent.root / capture["manifest_candidate_path"]).read_text(encoding="utf-8"))
        self.assertEqual("blocked", candidate["dates"]["2026-06-01"]["mode"])

    def test_snapshot_capture_failure_is_recorded_without_blocking_official_outputs(self) -> None:
        self.write_inputs()
        (self.agent.root / "config" / "benchmark_mappings.json").unlink()

        status_path, status = run_chain(
            self.agent.root,
            "2026-06-01",
            generated_at="2026-06-01T14:30:00+08:00",
            debate_mode="deterministic",
        )

        self.assertTrue(status_path.exists())
        self.assertTrue(status["summary"]["promoted_run_passed"])
        self.assertEqual("failed", status["replay_snapshot_capture"]["status"])
        self.assertEqual("FileNotFoundError", status["replay_snapshot_capture"]["error_type"])
        self.assertTrue((self.agent.root / "db" / "validated_advice" / "2026-06-01.json").exists())
        self.assertTrue((self.agent.root / "db" / "decisions" / "2026-06-01.json").exists())

    def test_intraday_promoted_chain_accepts_previous_business_day_current_state(self) -> None:
        self.write_inputs()
        (self.agent.root / "db" / "portfolio_state" / "snapshots" / "2026-06-01.json").unlink()
        current_path = self.agent.root / "db" / "portfolio_state" / "current.json"
        current = json.loads(current_path.read_text(encoding="utf-8"))
        current["as_of_date"] = "2026-05-29"
        current_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")

        status_path, status = run_chain(
            self.agent.root,
            "2026-06-01",
            generated_at="2026-06-01T14:30:00+08:00",
            debate_mode="deterministic",
        )

        self.assertTrue(status_path.exists())
        self.assertTrue(status["summary"]["promoted_run_passed"])
        tickets = json.loads((self.agent.root / "db" / "action_tickets" / "2026-06-01.json").read_text(encoding="utf-8"))
        self.assertTrue(tickets["summary"]["portfolio_state_carried_forward"])
        self.assertEqual(tickets["summary"]["portfolio_state_as_of_date"], "2026-05-29")
        portfolio_source = next(item for item in tickets["source_artifacts"] if item["kind"] == "portfolio_state")
        self.assertEqual(portfolio_source["as_of_date"], "2026-05-29")


if __name__ == "__main__":
    unittest.main()
