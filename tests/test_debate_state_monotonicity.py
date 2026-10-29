from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import action_debate_graph as adg  # noqa: E402


def _view(ticket_status: str = "shadow_only") -> dict:
    return {
        "target": {"ticket_id": "t1", "fund_code": "F1", "fund_name": "F1",
                   "action_verb": "hold", "role": "tactical"},
        "ticket_status": ticket_status,
        "execution_mode": "",
        "validated_amount": 0.0,
        "counts": {"missing_data_count": 1, "anti_pattern_count": 0},
        "missing_data": [{"field": "quote", "state": "missing", "blocks_debate": True}],
        "primary_risk": "missing quote (blocking)",
    }


def _ctx(view: dict) -> dict:
    return {
        "evidence_views": [view],
        "ticket_artifact": {"tickets": [
            {"ticket_id": "t1", "fund_code": "F1", "fund_name": "F1", "role": "tactical",
             "action_verb": "hold", "ticket_status": "shadow_only", "validated_amount": 0.0,
             "execution_mode": ""},
        ]},
        "agent_home": Path(tempfile.mkdtemp()),
    }


class DebateStateMonotonicityTests(unittest.TestCase):
    def test_bear_llm_low_cannot_relax_blocking_missing_to_low(self):
        view = _view()
        ctx = _ctx(view)
        with patch.object(adg, "call_debate_llm_node", return_value={"t1": {"strength": "low", "summary": "weak"}}):
            adg.node_bear_case(SimpleNamespace(report_date="2026-06-01"), ctx)
        # deterministic floor=high(blocking_missing_field)；LLM low 不得放松。
        self.assertEqual("high", ctx["bear_cases"]["t1"]["risk_strength"])

    def test_referee_llm_support_cannot_relax_deterministic_degrade(self):
        view = _view()
        ctx = _ctx(view)
        adg.node_bear_case(SimpleNamespace(report_date="2026-06-01"), ctx)  # bear -> high -> degrade
        ctx["bull_cases"] = {"t1": {"summary": "bull"}}
        with patch.object(adg, "call_debate_llm_node",
                          return_value={"t1": {"verdict": "support_shadow_ticket", "summary": "x", "uncertainty": "low"}}):
            adg.node_debate_referee(SimpleNamespace(report_date="2026-06-01"), ctx)
        # deterministic=degrade_to_watch；LLM support 不得放松。
        self.assertEqual("degrade_to_watch", ctx["referee_verdicts"]["t1"]["verdict"])

    def test_former_llm_shadow_cannot_relax_referee_degrade(self):
        view = _view()
        ctx = _ctx(view)
        adg.node_bear_case(SimpleNamespace(report_date="2026-06-01"), ctx)
        ctx["bull_cases"] = {"t1": {"summary": "bull"}}
        adg.node_debate_referee(SimpleNamespace(report_date="2026-06-01"), ctx)  # -> degraded
        with patch.object(adg, "call_debate_llm_node",
                          return_value={"t1": {"action": "add", "size_tier": "medium",
                                               "horizon": "unspecified", "evidence_quality": "medium",
                                               "target_status": "shadow_only", "reason": "buy it"}}):
            adg.node_action_former(SimpleNamespace(report_date="2026-06-01"), ctx)
        # referee=degraded，former LLM shadow_only 不得抬权。
        self.assertEqual("degraded", ctx["action_drafts"]["t1"]["target_status"])

    def test_former_bogus_status_fails_closed_to_blocked(self):
        view = _view()
        ctx = _ctx(view)
        adg.node_bear_case(SimpleNamespace(report_date="2026-06-01"), ctx)
        ctx["bull_cases"] = {"t1": {"summary": "bull"}}
        adg.node_debate_referee(SimpleNamespace(report_date="2026-06-01"), ctx)
        with patch.object(adg, "call_debate_llm_node",
                          return_value={"t1": {"action": "add", "size_tier": "medium",
                                               "target_status": "totally_bogus", "reason": "x"}}):
            adg.node_action_former(SimpleNamespace(report_date="2026-06-01"), ctx)
        self.assertEqual("blocked", ctx["action_drafts"]["t1"]["target_status"])

    def test_former_empty_status_keeps_deterministic_degrade(self):
        view = _view()
        ctx = _ctx(view)
        adg.node_bear_case(SimpleNamespace(report_date="2026-06-01"), ctx)
        ctx["bull_cases"] = {"t1": {"summary": "bull"}}
        adg.node_debate_referee(SimpleNamespace(report_date="2026-06-01"), ctx)
        with patch.object(adg, "call_debate_llm_node",
                          return_value={"t1": {"action": "add", "size_tier": "medium", "target_status": "", "reason": "x"}}):
            adg.node_action_former(SimpleNamespace(report_date="2026-06-01"), ctx)
        self.assertEqual("degraded", ctx["action_drafts"]["t1"]["target_status"])


if __name__ == "__main__":
    unittest.main()
