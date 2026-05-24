from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
REPORT_DATE = "2026-05-22"
GENERATED_AT = "2026-05-22T21:30:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from action_ticket_models import ActionTicket, ActionTicketArtifact, ActionTicketValidationError, GuardrailResult
from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed
from build_action_ticket_shadow import action_ticket_path, build_action_ticket_artifact, run_builder
from helpers import TempAgentHome


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_repo_json(relative: str) -> dict:
    return json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))


class ActionTicketModelTests(unittest.TestCase):
    def build_ticket(self) -> ActionTicket:
        return ActionTicket(
            ticket_id="ticket:2026-05-22:017641:scheduled_dca:001",
            schema_version="action_ticket.v1",
            report_date=REPORT_DATE,
            generated_at=GENERATED_AT,
            fund_code="017641",
            fund_name="摩根标普500指数(QDII)人民币A",
            action_verb="scheduled_dca",
            execution_mode="scheduled",
            ticket_status="shadow_only",
            non_executable=True,
            write_scope="shadow_only",
            validated_amount=25.0,
            confidence=0.0,
            thesis="Preserve the scheduled DCA as a shadow-only ticket.",
            hard_guardrail_results=[GuardrailResult("amount_normalization", "pass", "validated_amount=25.00")],
            source_artifacts=[{"kind": "validated_advice", "path": "db/validated_advice/2026-05-22.json"}],
            legacy_mapping={"suggestion_id": "2026-05-22:017641:scheduled_dca"},
        )

    def test_action_ticket_round_trip_is_stable(self) -> None:
        payload = self.build_ticket().to_dict()
        self.assertEqual(payload, ActionTicket.from_dict(payload).to_dict())

        artifact = ActionTicketArtifact(
            schema_version="action_ticket.v1",
            artifact_id="action_tickets:2026-05-22",
            artifact_kind="action_ticket_shadow",
            report_date=REPORT_DATE,
            generated_at=GENERATED_AT,
            write_scope="shadow_only",
            non_executable=True,
            source_artifacts=[{"kind": "validated_advice", "path": "db/validated_advice/2026-05-22.json"}],
            summary={"ticket_count": 1},
            tickets=[payload],
        )
        self.assertEqual(artifact.to_dict(), ActionTicketArtifact.from_dict(artifact.to_dict()).to_dict())

    def test_phase1_rejects_executable_or_official_scope_ticket(self) -> None:
        payload = self.build_ticket().to_dict()
        payload["non_executable"] = False
        with self.assertRaises(ActionTicketValidationError):
            ActionTicket.from_dict(payload)

        payload = self.build_ticket().to_dict()
        payload["non_executable"] = "true"
        with self.assertRaises(ActionTicketValidationError):
            ActionTicket.from_dict(payload)

        payload = self.build_ticket().to_dict()
        payload["write_scope"] = "official"
        with self.assertRaises(ActionTicketValidationError):
            ActionTicket.from_dict(payload)


class ActionTicketBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def copy_real_slice_inputs(self) -> None:
        self.agent.write_json(f"db/validated_advice/{REPORT_DATE}.json", _load_repo_json(f"db/validated_advice/{REPORT_DATE}.json"))
        self.agent.write_json("db/portfolio_state/current.json", _load_repo_json("db/portfolio_state/current.json"))

    def test_builds_all_fund_tickets_for_2026_05_22_shadow_only(self) -> None:
        self.copy_real_slice_inputs()
        artifact = build_action_ticket_artifact(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)
        payload = artifact.to_dict()
        tickets = payload["tickets"]
        by_code = {item["fund_code"]: item for item in tickets}
        portfolio_codes = {
            item["fund_code"]
            for item in _load_repo_json("db/portfolio_state/current.json")["funds"]
        }

        self.assertEqual(15, payload["summary"]["ticket_count"])
        self.assertEqual(portfolio_codes, set(by_code))
        self.assertEqual(2, payload["summary"]["action_count"])
        self.assertEqual(13, payload["summary"]["hold_ticket_count"])
        self.assertEqual(0.0, payload["summary"]["silent_hold_rate"])
        self.assertEqual(0, payload["summary"]["non_executable_violation_count"])
        self.assertGreater(payload["summary"]["blocked_count"], 0)

        for ticket in tickets:
            for field in (
                "ticket_id",
                "schema_version",
                "report_date",
                "generated_at",
                "fund_code",
                "fund_name",
                "action_verb",
                "execution_mode",
                "ticket_status",
                "non_executable",
                "write_scope",
                "validated_amount",
                "confidence",
                "thesis",
                "hard_guardrail_results",
                "source_artifacts",
                "legacy_mapping",
            ):
                self.assertIn(field, ticket)
            self.assertTrue(ticket["non_executable"])
            self.assertEqual("shadow_only", ticket["write_scope"])
            self.assertTrue(ticket["hard_guardrail_results"])
            self.assertTrue(ticket["source_artifacts"])

        self.assertEqual("scheduled_dca", by_code["017641"]["action_verb"])
        self.assertEqual("scheduled", by_code["017641"]["execution_mode"])
        self.assertEqual("shadow_only", by_code["017641"]["ticket_status"])
        self.assertEqual(25.0, by_code["017641"]["requested_amount"])
        self.assertEqual(25.0, by_code["017641"]["validated_amount"])
        self.assertFalse(
            any(result["rule_id"] == "legacy_constraint:core_dca_fixed_rule" for result in by_code["017641"]["hard_guardrail_results"])
        )
        self.assertTrue(
            any(adjustment["policy_id"] == "legacy_constraint:core_dca_fixed_rule" for adjustment in by_code["017641"]["soft_policy_adjustments"])
        )
        self.assertEqual("scheduled_dca", by_code["016452"]["action_verb"])
        self.assertEqual("blocked", by_code["017193"]["ticket_status"])

    def test_builder_writes_only_action_ticket_artifact_and_keeps_inputs_unchanged(self) -> None:
        self.copy_real_slice_inputs()
        validated_path = self.agent.root / "db" / "validated_advice" / f"{REPORT_DATE}.json"
        portfolio_path = self.agent.root / "db" / "portfolio_state" / "current.json"
        before_validated = _sha256(validated_path)
        before_portfolio = _sha256(portfolio_path)

        path, artifact = run_builder(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)

        self.assertEqual(action_ticket_path(self.agent.root, REPORT_DATE), path)
        self.assertTrue(path.exists())
        self.assertEqual(before_validated, _sha256(validated_path))
        self.assertEqual(before_portfolio, _sha256(portfolio_path))
        self.assertTrue(artifact.to_dict()["summary"]["official_advice_unchanged"])

    def test_boundary_rejects_action_ticket_payload_on_official_path(self) -> None:
        self.copy_real_slice_inputs()
        artifact = build_action_ticket_artifact(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)
        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(
                self.agent.root / "db" / "validated_advice" / f"{REPORT_DATE}.json",
                artifact.to_dict(),
                self.agent.root,
            )

    def test_cli_builder_works_with_temp_agent_home(self) -> None:
        self.copy_real_slice_inputs()
        completed = self.agent.run_script(
            "build_action_ticket_shadow.py",
            "--date",
            REPORT_DATE,
            "--generated-at",
            GENERATED_AT,
        )
        self.assertIn("wrote 15 action tickets", completed.stdout)
        payload = json.loads(action_ticket_path(self.agent.root, REPORT_DATE).read_text(encoding="utf-8"))
        self.assertEqual(15, payload["summary"]["ticket_count"])

    def test_builder_normalizes_actions_statuses_and_missing_data(self) -> None:
        self.agent.write_json(
            "db/portfolio_state/current.json",
            {
                "as_of_date": REPORT_DATE,
                "total_value": 1000.0,
                "funds": [
                    {"fund_code": "ADD", "fund_name": "Add Fund", "role": "tactical", "current_value": 200.0},
                    {"fund_code": "RED", "fund_name": "Reduce Fund", "role": "tactical", "current_value": 300.0},
                    {"fund_code": "DCA", "fund_name": "DCA Fund", "role": "core_dca", "current_value": 100.0},
                    {"fund_code": "HOLD", "fund_name": "Blocked Hold Fund", "role": "tactical", "current_value": 250.0},
                    {"fund_code": "EXTRA", "fund_name": "Extra Fund", "role": "tactical", "current_value": 150.0},
                ],
            },
        )
        self.agent.write_json(
            f"db/validated_advice/{REPORT_DATE}.json",
            {
                "generated_at": GENERATED_AT,
                "decision_mode": "canonical",
                "execution_eligible": True,
                "committee_decision_bundle": {
                    "fund_decisions": [
                        {"fund_code": "HOLD", "risk_veto": True, "execution_eligible": False},
                    ]
                },
                "tactical_actions": [
                    {
                        "suggestion_id": "add-1",
                        "fund_code": "ADD",
                        "fund_name": "Add Fund",
                        "validated_action": "buy",
                        "model_action": "add",
                        "requested_amount": 200.0,
                        "validated_amount": 150.0,
                        "confidence": 0.7,
                        "priority": 1,
                        "thesis": "Add after validator size adjustment.",
                    },
                    {
                        "suggestion_id": "reduce-1",
                        "fund_code": "RED",
                        "fund_name": "Reduce Fund",
                        "validated_action": "sell",
                        "model_action": "reduce",
                        "validated_amount": 100.0,
                        "confidence": 0.8,
                        "priority": 2,
                        "thesis": "Reduce an overweight position.",
                    },
                    {
                        "suggestion_id": "missing-position-1",
                        "fund_code": "MISS",
                        "fund_name": "Missing Position Fund",
                        "validated_action": "add",
                        "model_action": "add",
                        "validated_amount": 100.0,
                        "confidence": 0.5,
                        "priority": 3,
                        "thesis": "Action has no matching portfolio position.",
                    },
                ],
                "dca_actions": [
                    {
                        "suggestion_id": "dca-1",
                        "fund_code": "DCA",
                        "fund_name": "DCA Fund",
                        "validated_action": "dca",
                        "model_action": "hold",
                        "validated_amount": 25.0,
                        "confidence": 0.0,
                        "priority": 4,
                        "thesis": "Scheduled DCA.",
                    }
                ],
                "hold_actions": [
                    {
                        "suggestion_id": "hold-1",
                        "fund_code": "HOLD",
                        "fund_name": "Blocked Hold Fund",
                        "validated_action": "hold",
                        "model_action": "add",
                        "validated_amount": 0.0,
                        "confidence": 0.4,
                        "priority": 5,
                        "thesis": "Risk manager blocked the add.",
                        "policy_rule_hits": ["committee_bundle_fund_gate"],
                        "constraint_hits": ["risk_veto"],
                    }
                ],
            },
        )

        artifact = build_action_ticket_artifact(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)
        by_code = {item.fund_code: item for item in artifact.tickets}

        self.assertEqual("add", by_code["ADD"].action_verb)
        self.assertEqual("adjusted", by_code["ADD"].ticket_status)
        self.assertTrue(any(item.rule_id == "requested_vs_validated_amount" and item.result == "adjust" for item in by_code["ADD"].hard_guardrail_results))
        self.assertEqual("reduce", by_code["RED"].action_verb)
        self.assertEqual("scheduled_dca", by_code["DCA"].action_verb)
        self.assertEqual("shadow_only", by_code["DCA"].ticket_status)
        self.assertEqual("blocked", by_code["HOLD"].ticket_status)
        self.assertIn("portfolio_position", by_code["MISS"].missing_data)
        self.assertIn("legacy_validated_action", by_code["EXTRA"].missing_data)


if __name__ == "__main__":
    unittest.main()
