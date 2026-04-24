from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_multiagent_research import build_committee_summary


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


if __name__ == "__main__":
    unittest.main()
