from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_llm_context import build_memory_digest
from learning_memory import run_learning_sync, write_learning_artifacts
from helpers import TempAgentHome
from ui_support import build_replay_command, build_replay_differences_text, build_replay_rule_impact_text, load_state


class LearningMemoryTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_learning_sync_promotes_rule_and_writes_artifacts(self):
        review_batches = [
            {
                "source": "advice",
                "base_date": "2026-03-10",
                "review_date": "2026-03-11",
                "horizon": 1,
                "summary": {"supportive": 0, "adverse": 8, "missed_upside": 0, "unknown": 0},
                "diagnostic_summary": {"signal_failure": 8},
                "primary_diagnostic": "signal_failure",
                "items": [],
            }
        ]
        cycle_summary, ledger, memory = run_learning_sync(self.agent.root, "2026-03-11", review_batches)
        written = write_learning_artifacts(self.agent.root, "2026-03-11", cycle_summary, ledger, memory, review_batches)

        self.assertEqual(ledger["summary"]["core_permanent"], 1)
        self.assertEqual(memory["core_permanent_memory"][0]["scope"], "core_permanent_memory")
        self.assertTrue(written["learning_report_path"].exists())
        self.assertTrue(written["legacy_review_report_path"].exists())
        report_text = written["learning_report_path"].read_text(encoding="utf-8")
        self.assertIn("Learning Center Report", report_text)

    def test_build_memory_digest_prioritizes_core_permanent_memory(self):
        memory = {
            "updated_at": "2026-03-11T21:00:00+08:00",
            "core_permanent_memory": [
                {
                    "memory_id": "rule:core",
                    "memory_type": "policy",
                    "scope": "core_permanent_memory",
                    "entity_keys": ["tactical_entries", "signal_validation"],
                    "text": "Require signal confirmation before adding.",
                    "base_date": "2026-03-11",
                    "promotion_level": "promoted",
                    "confidence": 0.91,
                    "status": "active",
                }
            ],
            "permanent_memory": [],
            "strategic_memory": [],
            "lessons": [],
            "review_history": [],
            "bias_adjustments": [],
            "agent_feedback": [],
            "records": [],
            "user_confirmed_memory": [],
            "memory_ledger_summary": {"core_permanent": 1},
            "_analysis_date": "2026-03-12",
        }
        portfolio = {
            "funds": [
                {
                    "fund_code": "F1",
                    "fund_name": "Test Fund",
                    "role": "tactical",
                    "style_group": "growth",
                    "current_value": 100.0,
                }
            ]
        }
        exposure_summary = {
            "by_strategy_bucket": [],
            "by_theme_family": [{"name": "growth_cluster", "weight_pct": 100.0}],
            "concentration_metrics": {"high_volatility_theme_weight_pct": 100.0},
        }
        digest = build_memory_digest(memory, portfolio, exposure_summary)
        self.assertEqual(digest["core_permanent_memory_hits"][0]["memory_id"], "rule:core")
        self.assertEqual(digest["active_memory_records"][0]["memory_id"], "rule:core")

    def test_load_state_exposes_learning_artifacts(self):
        self.agent.write_json("db/review_memory/ledger.json", {"rules": [], "events": [], "summary": {"strategic": 1, "permanent": 0, "core_permanent": 0}})
        self.agent.write_json(
            "db/review_memory/cycles/2026-03-11.json",
            {"review_date": "2026-03-11", "batch_count": 2, "headline": "learning cycle complete"},
        )
        self.agent.write_text("reports/daily/2026-03-11_learning.md", "# Learning Report\n")
        state = load_state(self.agent.root, "2026-03-11")
        self.assertEqual(state["learning_cycle"]["batch_count"], 2)
        self.assertEqual(state["memory_ledger"]["summary"]["strategic"], 1)
        self.assertIn("Learning Report", state["learning_report"])

    def test_build_replay_command_supports_learning_writeback(self):
        command = build_replay_command(self.agent.root, "2026-03-10", "2026-03-12", "revalidate", write_learning=True, experiment_name="ui_test")
        self.assertIn("--write-learning", command)
        self.assertIn("--experiment-name", command)
        self.assertIn("ui_test", command)

    def test_load_state_exposes_replay_difference_and_rule_impact_details(self):
        self.agent.write_json(
            "db/replay_experiments/demo/summary.json",
            {
                "experiment_id": "demo",
                "mode": "revalidate",
                "generated_at": "2026-03-12T10:00:00+08:00",
                "start_date": "2026-03-10",
                "end_date": "2026-03-12",
                "aggregate": {"changed_days": 2, "total_tactical_actions": 4, "total_gross_trade": 600.0, "edge_delta_total": 45.0, "improved_items": 3, "worsened_items": 1},
                "learning_update": {"applied": True},
                "learning_impacts": [
                    {
                        "rule_label": "signal_failure",
                        "support_count": 2,
                        "contradiction_count": 0,
                        "changed_item_count": 2,
                        "total_edge_delta": 40.0,
                        "fund_codes": ["F1", "F2"],
                    }
                ],
                "daily_results": [
                    {
                        "report_date": "2026-03-10",
                        "counterfactual": {
                            "item_deltas": [
                                {
                                    "fund_code": "F1",
                                    "existing_action": "add",
                                    "replay_action": "hold",
                                    "existing_edge": -10.0,
                                    "replay_edge": 0.0,
                                    "edge_delta": 10.0,
                                    "diagnostic_label": "signal_failure",
                                    "changed": True,
                                    "existing_outcome": "adverse",
                                    "replay_outcome": "neutral",
                                }
                            ]
                        },
                    }
                ],
            },
        )
        state = load_state(self.agent.root, "2026-03-12")
        replay = state["replay_experiments"][0]
        self.assertEqual(replay["difference_count"], 1)
        self.assertEqual(replay["learning_impacts"][0]["rule_label"], "signal_failure")
        diff_text = build_replay_differences_text(replay)
        impact_text = build_replay_rule_impact_text(replay)
        self.assertIn("F1", diff_text)
        self.assertIn("signal_failure", impact_text)


if __name__ == "__main__":
    unittest.main()
