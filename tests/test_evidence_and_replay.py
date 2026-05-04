from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_index import build_evidence_index_payload, retrieve_agent_evidence
from helpers import TempAgentHome


class EvidenceAndReplayTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_retrieve_agent_evidence_prefers_role_relevant_items(self):
        context = {
            "analysis_date": "2026-03-10",
            "generated_at": "2026-03-10T14:00:00+08:00",
            "funds": [
                {
                    "fund_code": "F1",
                    "fund_name": "Quality Fund",
                    "role": "tactical",
                    "strategy_bucket": "satellite_mid_term",
                    "style_group": "growth",
                    "recent_news": [{"title": "Manager update", "summary": "manager tenure and fee"}],
                }
            ],
            "fund_evidence_map": {
                "F1": [
                    {"evidence_id": "profile:F1"},
                    {"evidence_id": "news:F1"},
                ]
            },
            "evidence_items": [
                {
                    "evidence_id": "profile:F1",
                    "entity_id": "F1",
                    "entity_type": "fund",
                    "evidence_type": "fund_profile",
                    "source_role": "fund_news",
                    "source_tier": "official_market_data",
                    "mapping_mode": "direct_fund",
                    "summary": "Fund profile with manager tenure, fee level and scale.",
                    "source_title": "Profile",
                    "freshness_status": "fresh",
                    "stale": False,
                    "confidence": 0.9,
                    "tags": ["manager", "fee", "quality"],
                },
                {
                    "evidence_id": "news:F1",
                    "entity_id": "F1",
                    "entity_type": "fund",
                    "evidence_type": "theme_news",
                    "source_role": "theme_news",
                    "source_tier": "self_media",
                    "mapping_mode": "direct_fund",
                    "summary": "Theme momentum headline.",
                    "source_title": "Theme",
                    "freshness_status": "fresh",
                    "stale": False,
                    "confidence": 0.7,
                    "tags": ["momentum"],
                },
            ],
        }
        index_payload = build_evidence_index_payload(context)
        retrieval = retrieve_agent_evidence(
            "fund_quality_analyst",
            context,
            index_payload=index_payload,
            relevant_funds=context["funds"],
        )
        self.assertEqual(retrieval["funds"]["F1"][0]["evidence_id"], "profile:F1")

    def test_run_replay_experiment_writes_summary(self):
        portfolio = {
            "portfolio_name": "Replay Test",
            "as_of_date": "2026-03-10",
            "total_value": 1000.0,
            "holding_pnl": 0.0,
            "funds": [
                {
                    "fund_code": "CASH",
                    "fund_name": "Cash",
                    "role": "cash_hub",
                    "style_group": "cash",
                    "current_value": 400.0,
                    "allow_trade": True,
                    "holding_units": 400.0,
                    "last_valuation_nav": 1.0,
                    "units_source": "stored",
                },
                {
                    "fund_code": "F1",
                    "fund_name": "Replay Fund",
                    "role": "tactical",
                    "style_group": "growth",
                    "current_value": 200.0,
                    "cap_value": 500.0,
                    "allow_trade": True,
                    "holding_units": 100.0,
                    "last_valuation_nav": 2.0,
                    "units_source": "stored",
                },
            ],
        }
        self.agent.write_json("db/portfolio_state/snapshots/2026-03-10.json", portfolio)
        self.agent.write_json(
            "db/llm_advice/2026-03-10.json",
            {
                "market_view": {"regime": "mixed", "summary": "replay", "key_drivers": []},
                "cross_fund_observations": [],
                "fund_decisions": [
                    {
                        "fund_code": "F1",
                        "action": "add",
                        "suggest_amount": 200.0,
                        "priority": 1,
                        "confidence": 0.8,
                        "thesis": "replay add",
                        "evidence": ["signal"],
                        "risks": [],
                        "agent_support": ["portfolio_trader"],
                    }
                ],
            },
        )
        result = self.agent.run_script(
            "run_replay_experiment.py",
            "--start-date",
            "2026-03-10",
            "--end-date",
            "2026-03-10",
            "--mode",
            "revalidate",
            "--experiment-name",
            "unit_test_replay",
        )
        summary_path = Path(result.stdout.strip().splitlines()[-1])
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["mode"], "revalidate")
        self.assertEqual(len(summary["daily_results"]), 1)
        self.assertEqual(summary["daily_results"][0]["metrics"]["tactical_action_count"], 1)
        self.assertIn("optimizer", summary["aggregate"])
        self.assertEqual(summary["aggregate"]["optimizer"]["days_with_optimizer"], 1)
        self.assertEqual(summary["daily_results"][0]["optimizer"]["selected_candidate_count"], 1)

    def test_run_replay_experiment_can_update_learning_ledger(self):
        portfolio = {
            "portfolio_name": "Replay Test",
            "as_of_date": "2026-03-10",
            "total_value": 1000.0,
            "holding_pnl": 0.0,
            "funds": [
                {
                    "fund_code": "CASH",
                    "fund_name": "Cash",
                    "role": "cash_hub",
                    "style_group": "cash",
                    "current_value": 400.0,
                    "allow_trade": True,
                    "holding_units": 400.0,
                    "last_valuation_nav": 1.0,
                    "units_source": "stored",
                },
                {
                    "fund_code": "F1",
                    "fund_name": "Replay Fund",
                    "role": "tactical",
                    "style_group": "growth",
                    "current_value": 200.0,
                    "cap_value": 500.0,
                    "allow_trade": True,
                    "holding_units": 100.0,
                    "last_valuation_nav": 2.0,
                    "units_source": "stored",
                },
            ],
        }
        self.agent.write_json("db/portfolio_state/snapshots/2026-03-10.json", portfolio)
        self.agent.write_json(
            "db/llm_advice/2026-03-10.json",
            {
                "market_view": {"regime": "mixed", "summary": "replay", "key_drivers": []},
                "cross_fund_observations": [],
                "fund_decisions": [
                    {
                        "fund_code": "F1",
                        "action": "hold",
                        "suggest_amount": 0.0,
                        "priority": 1,
                        "confidence": 0.8,
                        "thesis": "stay flat",
                        "evidence": ["signal"],
                        "risks": [],
                        "agent_support": ["portfolio_trader"],
                    }
                ],
            },
        )
        self.agent.write_json(
            "db/validated_advice/2026-03-10.json",
            {
                "report_date": "2026-03-10",
                "generated_at": "2026-03-10T14:00:00+08:00",
                "portfolio_name": "Replay Test",
                "risk_profile": "balanced",
                "daily_max_trade_amount": 1000.0,
                "daily_max_gross_trade_amount": 1000.0,
                "daily_max_net_buy_amount": 1000.0,
                "fixed_dca_total": 0.0,
                "remaining_budget_after_validation": 800.0,
                "remaining_gross_trade_budget_after_validation": 800.0,
                "remaining_net_buy_budget_after_validation": 800.0,
                "cash_hub_available": 300.0,
                "market_view": {"regime": "mixed", "summary": "baseline", "key_drivers": []},
                "cross_fund_observations": [],
                "optimization_summary": {"mode": "portfolio_search", "candidate_count": 1, "selected_candidate_count": 1},
                "recommendation_deltas": [],
                "dca_actions": [],
                "tactical_actions": [
                    {
                        "fund_code": "F1",
                        "fund_name": "Replay Fund",
                        "validated_action": "add",
                        "validated_amount": 200.0,
                    }
                ],
                "hold_actions": [],
            },
        )
        self.agent.write_json(
            "db/review_results/2026-03-10_T1.json",
            {
                "source": "advice",
                "base_date": "2026-03-10",
                "review_date": "2026-03-11",
                "horizon": 1,
                "summary": {"supportive": 0, "adverse": 1, "missed_upside": 0, "neutral": 0, "unknown": 0},
                "diagnostic_summary": {"signal_failure": 1},
                "primary_diagnostic": "signal_failure",
                "items": [
                    {
                        "fund_code": "F1",
                        "fund_name": "Replay Fund",
                        "source_action": "add",
                        "source_amount": 200.0,
                        "outcome": "adverse",
                        "diagnostic_label": "signal_failure",
                        "evaluation_return_pct": -5.0,
                        "estimated_redeem_fee_rate": 0.5,
                    }
                ],
            },
        )
        result = self.agent.run_script(
            "run_replay_experiment.py",
            "--start-date",
            "2026-03-10",
            "--end-date",
            "2026-03-10",
            "--mode",
            "revalidate",
            "--experiment-name",
            "unit_test_learning_replay",
            "--write-learning",
        )
        summary_path = Path(result.stdout.strip().splitlines()[-1])
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertTrue(summary["learning_update"]["applied"])
        ledger = json.loads((self.agent.root / "db" / "review_memory" / "ledger.json").read_text(encoding="utf-8"))
        signal_rule = next(item for item in ledger["rules"] if item["rule_key"] == "require_signal_confirmation_before_add")
        self.assertGreaterEqual(signal_rule["replay_support_count"], 1)
        self.assertIn("unit_test_learning_replay", ledger["applied_replay_experiments"])


if __name__ == "__main__":
    unittest.main()
