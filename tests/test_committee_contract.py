from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_multiagent_research import build_committee_decision_bundle, build_committee_summary
from generate_llm_advice import build_final_advice_from_committee_bundle


class CommitteeContractTests(unittest.TestCase):
    def test_build_committee_summary_contains_cases_and_risk_veto(self):
        aggregate = {
            "committee_ready": True,
            "failed_agent_names": [],
            "failed_agents": [],
            "degraded_ok": False,
            "agents": {
                "bull_researcher": {"output": {"summary": "bull", "fund_views": [{"fund_code": "F1", "action_bias": "add", "thesis": "upside", "evidence_refs": ["q1"]}]}},
                "bear_researcher": {"output": {"summary": "bear", "fund_views": [{"fund_code": "F1", "action_bias": "hold", "thesis": "crowded"}]}},
                "research_manager": {"output": {"summary": "manager", "key_points": ["accept small add"], "decision_cards": [{"fund_code": "F1", "action_bias": "add"}]}},
                "risk_manager": {"output": {"summary": "risk", "decision_cards": [{"fund_code": "F1", "action_bias": "reduce", "risk_decision": "reject", "downgrade_reason": "crowding"}]}},
            },
        }
        committee = build_committee_summary(aggregate)
        self.assertEqual(committee["decision_source"], "risk_constrained")
        self.assertEqual(committee["committee_confidence"], "high")
        self.assertEqual(len(committee["bull_case"]), 1)
        self.assertEqual(committee["risk_vetoes"][0]["fund_code"], "F1")

    def test_failed_core_marks_fallback_low_confidence(self):
        committee = build_committee_summary({"committee_ready": False, "failed_agent_names": ["risk_manager"], "agents": {}})
        self.assertEqual(committee["decision_source"], "fallback")
        self.assertEqual(committee["committee_confidence"], "low")

    def test_committee_bundle_marks_hold_only_when_core_degraded(self):
        aggregate = {
            "report_date": "2026-05-08",
            "degradation_mode": "decision_degraded",
            "execution_eligible": False,
            "failed_agent_names": [],
            "degraded_agent_names": ["risk_manager"],
            "committee": {"decision_source": "risk_constrained", "committee_confidence": "medium", "risk_vetoes": []},
            "ordered_agents": ["research_manager", "risk_manager", "portfolio_trader"],
            "agents": {
                "research_manager": {"output": {"decision_cards": [{"decision_id": "m1", "fund_code": "F1", "proposed_action": "add", "size_bucket": "200", "confidence": 0.7, "why_now": "thesis", "manager_notes": "", "supporting_signal_ids": [], "opposing_signal_ids": []}]}},
                "risk_manager": {"output": {"decision_cards": [{"decision_id": "r1", "fund_code": "F1", "risk_decision": "modify", "proposed_action": "hold", "size_bucket": "0", "confidence": 0.8, "manager_notes": "degraded", "supporting_signal_ids": [], "opposing_signal_ids": []}]}},
                "portfolio_trader": {"output": {"decision_cards": [{"decision_id": "t1", "fund_code": "F1", "proposed_action": "add", "size_bucket": "200", "confidence": 0.9, "why_now": "thesis", "manager_notes": "", "supporting_signal_ids": [], "opposing_signal_ids": []}]}},
            },
        }
        context = {"funds": [{"fund_code": "F1", "fund_name": "基金一", "role": "tactical"}]}
        bundle = build_committee_decision_bundle(aggregate, context)
        self.assertEqual(bundle["decision_mode"], "hold_only")
        self.assertFalse(bundle["execution_eligible"])
        self.assertEqual(bundle["fund_decisions"][0]["proposed_action"], "hold")

    def test_committee_bundle_forces_hold_when_risk_vetoes_action(self):
        aggregate = {
            "report_date": "2026-05-08",
            "degradation_mode": "none",
            "execution_eligible": True,
            "failed_agent_names": [],
            "degraded_agent_names": [],
            "committee": {"decision_source": "risk_constrained", "committee_confidence": "high", "risk_vetoes": []},
            "ordered_agents": ["research_manager", "risk_manager", "portfolio_trader"],
            "agents": {
                "research_manager": {"output": {"decision_cards": [{"decision_id": "m1", "fund_code": "F1", "proposed_action": "add", "size_bucket": "200", "confidence": 0.7, "why_now": "thesis"}]}},
                "risk_manager": {"output": {"decision_cards": [{"decision_id": "r1", "fund_code": "F1", "risk_decision": "reject", "proposed_action": "hold", "size_bucket": "0", "confidence": 0.9, "manager_notes": "too crowded"}]}},
                "portfolio_trader": {"output": {"decision_cards": [{"decision_id": "t1", "fund_code": "F1", "proposed_action": "add", "size_bucket": "200", "confidence": 0.8, "why_now": "momentum"}]}},
            },
        }
        context = {"funds": [{"fund_code": "F1", "fund_name": "Fund One", "role": "tactical"}]}

        bundle = build_committee_decision_bundle(aggregate, context)
        decision = bundle["fund_decisions"][0]

        self.assertTrue(decision["risk_veto"])
        self.assertFalse(decision["execution_eligible"])
        self.assertEqual(decision["proposed_action"], "hold")
        self.assertEqual(decision["suggest_amount"], 0.0)

    def test_final_advice_keeps_vetoed_bundle_decision_non_executable(self):
        advice = build_final_advice_from_committee_bundle(
            {"funds": [{"fund_code": "F1", "fund_name": "Fund One", "role": "tactical"}]},
            {
                "decision_mode": "canonical",
                "execution_eligible": True,
                "manager_order": ["portfolio_trader", "risk_manager"],
                "fund_decisions": [
                    {
                        "fund_code": "F1",
                        "role": "tactical",
                        "proposed_action": "add",
                        "suggest_amount": 200.0,
                        "risk_veto": True,
                        "risk_decision": "reject",
                        "execution_eligible": False,
                    }
                ],
            },
        )

        decision = advice["fund_decisions"][0]
        self.assertEqual(decision["action"], "hold")
        self.assertEqual(decision["suggest_amount"], 0.0)


if __name__ == "__main__":
    unittest.main()
