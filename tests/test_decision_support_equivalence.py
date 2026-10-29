from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.decision_support import (  # noqa: E402
    summarize_fund_agent_signals,
    summarize_fund_stage_signals,
)


def _agents(records):
    return {"agents": records}


class DecisionSupportEquivalenceTests(unittest.TestCase):
    def test_mixed_three_card_kinds_for_one_fund(self):
        aggregate = _agents(
            {
                "theme_analyst": {
                    "output": {
                        "signal_cards": [
                            {"fund_code": "F1", "action_bias": "add", "comment": "growth driver", "risks": ["risk a"]},
                        ],
                        "decision_cards": [
                            {"fund_code": "F1", "proposed_action": "reduce", "why_now": "valuation top", "manager_notes": ""},
                        ],
                        "fund_views": [
                            {"fund_code": "F1", "action_bias": "hold", "thesis": "sideways"},
                        ],
                    }
                }
            }
        )
        stage = summarize_fund_stage_signals(aggregate, "F1")
        self.assertEqual(stage["analyst"]["support"], ["theme_analyst"])
        self.assertEqual(stage["analyst"]["caution"], ["theme_analyst"])
        self.assertEqual(stage["analyst"]["neutral"], ["theme_analyst"])
        self.assertEqual(
            stage["analyst"]["highlights"],
            ["theme_analyst: growth driver", "theme_analyst: valuation top", "theme_analyst: sideways"],
        )
        self.assertTrue(stage["analyst"]["has_conflict"])
        agent = summarize_fund_agent_signals(aggregate, "F1")
        self.assertEqual(agent["supporting_agents"], ["theme_analyst"])
        self.assertEqual(agent["caution_agents"], ["theme_analyst"])
        self.assertEqual(agent["neutral_agents"], ["theme_analyst"])
        self.assertEqual(agent["support_points"], ["theme_analyst: growth driver"])
        self.assertEqual(agent["caution_points"], ["theme_analyst: valuation top"])

    def test_multiple_agents_dedup_and_sorted(self):
        records = {}
        for i, bias in enumerate(["add", "BUY", "trim", "hold", "avoid"]):
            records[f"agent_{i}"] = {"output": {"signal_cards": [{"fund_code": "F1", "action_bias": bias, "comment": "c"}]}}
        agent = summarize_fund_agent_signals(_agents(records), "F1")
        self.assertEqual(agent["supporting_agents"], ["agent_0", "agent_1"])
        self.assertEqual(agent["caution_agents"], ["agent_2", "agent_4"])
        self.assertEqual(agent["neutral_agents"], ["agent_3"])
        stage = summarize_fund_stage_signals(_agents(records), "F1")
        self.assertEqual(stage["manager"]["support"], ["agent_0", "agent_1"])
        self.assertEqual(stage["manager"]["caution"], ["agent_2", "agent_4"])
        self.assertEqual(stage["manager"]["neutral"], ["agent_3"])

    def test_non_matching_fund_ignored(self):
        aggregate = _agents(
            {"a1": {"output": {"signal_cards": [{"fund_code": "OTHER", "action_bias": "add", "comment": "x"}]}}}
        )
        stage = summarize_fund_stage_signals(aggregate, "F1")
        self.assertEqual(stage["analyst"]["support"], [])
        self.assertEqual(stage["analyst"]["highlights"], [])
        agent = summarize_fund_agent_signals(aggregate, "F1")
        self.assertEqual(agent["supporting_agents"], [])
        self.assertEqual(agent["support_points"], [])

    def test_missing_or_none_lists(self):
        self.assertEqual(summarize_fund_stage_signals({}, "F1")["analyst"]["support"], [])
        self.assertEqual(summarize_fund_stage_signals(_agents({"a": {"output": None}}), "F1")["analyst"]["support"], [])
        self.assertEqual(summarize_fund_stage_signals(_agents({"a": {"output": {"signal_cards": None}}}), "F1")["analyst"]["support"], [])
        self.assertEqual(summarize_fund_agent_signals({}, "F1")["supporting_agents"], [])
        self.assertEqual(summarize_fund_agent_signals(_agents({"a": {"output": None}}), "F1")["supporting_agents"], [])

    def test_unknown_stage_bucket_created(self):
        aggregate = {
            "agents": {"weird": {"output": {"signal_cards": [{"fund_code": "F1", "action_bias": "buy", "comment": "x"}]}}},
            "agent_roles": {"weird": "custom_stage"},
        }
        stage = summarize_fund_stage_signals(aggregate, "F1")
        self.assertIn("custom_stage", stage)
        self.assertEqual(stage["custom_stage"]["support"], ["weird"])
        # default stages still exist with defaults
        self.assertEqual(stage["analyst"]["highlights"], [])

    def test_duplicates_dedup_and_truncation(self):
        cards = [{"fund_code": "F1", "action_bias": "add", "comment": "same"} for _ in range(10)]
        records = {f"a{i}": {"output": {"signal_cards": cards}} for i in range(3)}
        stage = summarize_fund_stage_signals(_agents(records), "F1")
        self.assertEqual(len(stage["manager"]["highlights"]), 3)  # [:3]
        self.assertEqual(stage["manager"]["highlights"], ["a0: same", "a1: same", "a2: same"])
        agent = summarize_fund_agent_signals(_agents(records), "F1")
        self.assertEqual(len(agent["support_points"]), 3)  # [:5] but only 3 distinct strings
        agent2 = summarize_fund_agent_signals(
            _agents({f"a{i}": {"output": {"signal_cards": [{"fund_code": "F1", "action_bias": "add", "comment": f"point{i}"}]}} for i in range(8)}),
            "F1",
        )
        self.assertEqual(len(agent2["support_points"]), 5)  # [:5] truncation

    def test_committee_views_details(self):
        records = {
            "research_manager": {
                "output": {
                    # signal cards from committee members must NOT appear in committee_views
                    "signal_cards": [{"fund_code": "F1", "action_bias": "add", "comment": "sig"}],
                    "decision_cards": [{"fund_code": "F1", "proposed_action": "trim", "why_now": "overvalued"}],
                    "fund_views": [{"fund_code": "F1", "action_bias": "hold", "comment": "", "risks": ["risk only"]}],
                }
            }
        }
        agent = summarize_fund_agent_signals(_agents(records), "F1")
        self.assertEqual(len(agent["committee_views"]), 2)
        self.assertEqual(agent["committee_views"][0]["agent_name"], "research_manager")
        self.assertEqual(agent["committee_views"][0]["action_bias"], "trim")
        self.assertEqual(agent["committee_views"][0]["comment"], "overvalued")
        # fund_views committee entry uses view action_bias and falls back to risks
        self.assertEqual(agent["committee_views"][1]["action_bias"], "hold")
        self.assertEqual(agent["committee_views"][1]["comment"], "risk only")

    def test_signal_card_caution_risk_fallback_but_stage_signal_no_risk(self):
        records = {
            "a1": {"output": {"signal_cards": [{"fund_code": "F1", "action_bias": "reduce", "comment": "", "risks": ["r1"]}]}}
        }
        agent = summarize_fund_agent_signals(_agents(records), "F1")
        self.assertEqual(agent["caution_points"], ["a1: r1"])  # agent view falls back to risks
        stage = summarize_fund_stage_signals(_agents(records), "F1")
        # stage signal cards do NOT fall back to risks -> manager highlight empty; a1 lands in manager caution
        self.assertEqual(stage["manager"]["caution"], ["a1"])
        self.assertEqual(stage["manager"]["highlights"], [])

    def test_failure_input_raises_same_exceptions(self):
        with self.assertRaises(AttributeError):
            summarize_fund_stage_signals(_agents({"broken": None}), "F1")
        with self.assertRaises(AttributeError):
            summarize_fund_agent_signals(_agents({"broken": None}), "F1")
        with self.assertRaises(AttributeError):
            summarize_fund_stage_signals(_agents({"a": {"output": {"signal_cards": [None]}}}), "F1")

    def test_input_not_mutated(self):
        records = {
            "a1": {"output": {"signal_cards": [{"fund_code": "F1", "action_bias": "add", "comment": "x", "risks": ["r"]}]}}
        }
        snapshot = str(records)
        summarize_fund_stage_signals(_agents(records), "F1")
        summarize_fund_agent_signals(_agents(records), "F1")
        self.assertEqual(str(records), snapshot)


if __name__ == "__main__":
    unittest.main()
