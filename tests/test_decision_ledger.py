from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from decision_ledger import append_decision_ledger, build_and_write_decisions, build_decisions_from_validated, load_decision_latest, make_decision_id
from update_decision_outcomes import update_outcomes
from helpers import TempAgentHome


class DecisionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()
        self.agent.write_json(
            "config/portfolio.json",
            {
                "portfolio_name": "test",
                "as_of_date": "2026-04-01",
                "funds": [
                    {"fund_code": "F1", "fund_name": "Fund One", "role": "tactical", "current_value": 1000.0, "holding_pnl": 10.0, "holding_return_pct": 1.0},
                    {"fund_code": "F2", "fund_name": "Fund Two", "role": "tactical", "current_value": 500.0},
                ],
            },
        )

    def tearDown(self):
        self.agent.cleanup()

    def test_stable_decision_id_includes_amount_hash(self):
        self.assertEqual(make_decision_id("2026-04-01", "F1", "add", 200), make_decision_id("2026-04-01", "F1", "add", 200.0))
        self.assertNotEqual(make_decision_id("2026-04-01", "F1", "add", 100), make_decision_id("2026-04-01", "F1", "add", 200))
        self.assertNotEqual(
            make_decision_id("2026-04-01", "F1", "add", 200, "s1", "tactical_actions"),
            make_decision_id("2026-04-01", "F1", "add", 200, "s2", "tactical_actions"),
        )

    def test_build_decisions_from_validated_captures_actions_and_fallback(self):
        self.agent.write_json(
            "db/validated_advice/2026-04-01.json",
            {
                "report_date": "2026-04-01",
                "decision_source": "risk_constrained",
                "advice_is_fallback": True,
                "tactical_actions": [{"fund_code": "F1", "fund_name": "Fund One", "validated_action": "add", "validated_amount": 200.0, "risks": ["crowded"], "constraint_hits": ["cap"]}],
                "hold_actions": [{"fund_code": "F2", "fund_name": "Fund Two", "validated_action": "hold", "validated_amount": 0.0}],
            },
        )
        payload = build_decisions_from_validated(self.agent.root, "2026-04-01")
        self.assertEqual(len(payload["decisions"]), 2)
        first = payload["decisions"][0]
        self.assertEqual(first["decision_source"], "risk_constrained")
        self.assertTrue(first["advice_is_fallback"])
        self.assertEqual(first["position_before"]["current_value"], 1000.0)
        self.assertIn("cap", first["constraints"])

    def test_append_decision_ledger_is_idempotent(self):
        self.agent.write_json(
            "db/validated_advice/2026-04-01.json",
            {"report_date": "2026-04-01", "tactical_actions": [{"fund_code": "F1", "fund_name": "Fund One", "validated_action": "add", "validated_amount": 200.0}]},
        )
        payload = build_decisions_from_validated(self.agent.root, "2026-04-01")
        append_decision_ledger(self.agent.root, payload)
        append_decision_ledger(self.agent.root, payload)
        lines = (self.agent.root / "db/decision_ledger/F1.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)

    def test_update_outcomes_marks_ready_from_nav_history(self):
        self.agent.write_json(
            "db/decisions/2026-04-01.json",
            {"schema_version": 1, "report_date": "2026-04-01", "decisions": [{"decision_id": "d1", "report_date": "2026-04-01", "fund_code": "F1", "validated_action": "add", "outcomes": {}}]},
        )
        self.agent.write_json(
            "db/fund_nav_history/F1.json",
            {"items": [{"date": "2026-04-01", "nav": 1.0}, {"date": "2026-04-02", "nav": 1.1}, {"date": "2026-04-06", "nav": 1.2}]},
        )
        updated = update_outcomes(self.agent.root, "2026-04-01", "2026-04-06")
        self.assertEqual(updated["decisions"][0]["outcomes"]["t1"]["status"], "ready")
        self.assertAlmostEqual(updated["decisions"][0]["outcomes"]["t1"]["nav_return"], 10.0)

    def test_update_outcomes_refreshes_latest_view(self):
        self.agent.write_json(
            "db/validated_advice/2026-04-01.json",
            {
                "report_date": "2026-04-01",
                "tactical_actions": [{"suggestion_id": "s1", "fund_code": "F1", "fund_name": "Fund One", "validated_action": "add", "validated_amount": 200.0}],
            },
        )
        build_and_write_decisions(self.agent.root, "2026-04-01")
        self.agent.write_json(
            "db/fund_nav_history/F1.json",
            {"items": [{"date": "2026-04-01", "nav": 1.0}, {"date": "2026-04-02", "nav": 1.1}]},
        )

        update_outcomes(self.agent.root, "2026-04-01", "2026-04-02")
        latest = load_decision_latest(self.agent.root, "F1")

        self.assertEqual(latest["decision"]["outcomes"]["t1"]["status"], "ready")
        self.assertAlmostEqual(latest["decision"]["outcomes"]["t1"]["nav_return"], 10.0)

    def test_update_outcomes_appends_outcome_event_to_ledger(self):
        self.agent.write_json(
            "db/validated_advice/2026-04-01.json",
            {
                "report_date": "2026-04-01",
                "tactical_actions": [{"suggestion_id": "s1", "fund_code": "F1", "fund_name": "Fund One", "validated_action": "add", "validated_amount": 200.0}],
            },
        )
        build_and_write_decisions(self.agent.root, "2026-04-01")
        self.agent.write_json(
            "db/fund_nav_history/F1.json",
            {"items": [{"date": "2026-04-01", "nav": 1.0}, {"date": "2026-04-02", "nav": 1.1}]},
        )

        update_outcomes(self.agent.root, "2026-04-01", "2026-04-02")
        rows = [
            json.loads(line)
            for line in (self.agent.root / "db/decision_ledger/F1.jsonl").read_text(encoding="utf-8").splitlines()
        ]

        self.assertEqual(rows[0].get("validated_action"), "add")
        self.assertEqual(rows[1]["event_type"], "outcome_update")
        self.assertEqual(rows[1]["outcomes"]["t1"]["status"], "ready")

    def test_same_day_same_fund_multiple_suggestions_do_not_collide(self):
        self.agent.write_json(
            "db/validated_advice/2026-04-01.json",
            {
                "report_date": "2026-04-01",
                "tactical_actions": [
                    {"suggestion_id": "s1", "fund_code": "F1", "fund_name": "Fund One", "validated_action": "add", "validated_amount": 200.0},
                    {"suggestion_id": "s2", "fund_code": "F1", "fund_name": "Fund One", "validated_action": "add", "validated_amount": 200.0},
                ],
            },
        )

        payload = build_and_write_decisions(self.agent.root, "2026-04-01")
        ids = [item["decision_id"] for item in payload["decisions"]]
        latest = load_decision_latest(self.agent.root, "F1")

        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(len(latest["decisions"]), 2)


if __name__ == "__main__":
    unittest.main()
