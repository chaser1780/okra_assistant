from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
BASE_DATE = "2026-03-10"
GENERATED_AT = "2026-03-11T23:30:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed
from evaluate_action_ticket_outcomes import build_outcome_artifact, outcome_event_path, run_builder
from helpers import TempAgentHome
from outcome_event_models import OutcomeEventArtifact, OutcomeEventValidationError


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ActionOutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()
        self.write_base_inputs()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def write_base_inputs(self) -> None:
        portfolio = {
            "as_of_date": BASE_DATE,
            "total_value": 2000.0,
            "funds": [
                {
                    "fund_code": "ADD",
                    "fund_name": "Add Fund",
                    "current_value": 500.0,
                    "holding_units": 250.0,
                    "units_source": "stored",
                },
                {
                    "fund_code": "HOLD",
                    "fund_name": "Hold Fund",
                    "current_value": 500.0,
                    "holding_units": 250.0,
                    "units_source": "stored",
                },
                {
                    "fund_code": "RED",
                    "fund_name": "Reduce Fund",
                    "current_value": 500.0,
                    "holding_units": 250.0,
                    "units_source": "stored",
                },
                {
                    "fund_code": "UNTRUST",
                    "fund_name": "Untrusted Reduce Fund",
                    "current_value": 500.0,
                    "holding_units": 250.0,
                    "units_source": "derived_from_official_nav",
                },
            ],
        }
        self.agent.write_json(f"db/portfolio_state/snapshots/{BASE_DATE}.json", portfolio)
        self.agent.write_json("db/portfolio_state/current.json", portfolio)
        self.agent.write_json(
            f"db/action_tickets/{BASE_DATE}.json",
            {
                "schema_version": "action_ticket.v1",
                "artifact_id": f"action_tickets:{BASE_DATE}",
                "artifact_kind": "action_ticket_shadow",
                "report_date": BASE_DATE,
                "generated_at": GENERATED_AT,
                "write_scope": "shadow_only",
                "non_executable": True,
                "source_artifacts": [],
                "summary": {"ticket_count": 4},
                "tickets": [
                    self.ticket("ADD", "add", 100.0),
                    self.ticket("HOLD", "hold", 0.0),
                    self.ticket("RED", "reduce", 100.0),
                    self.ticket("UNTRUST", "reduce", 100.0),
                ],
            },
        )
        self.agent.write_json(
            f"raw/quotes/{BASE_DATE}.json",
            {
                "report_date": BASE_DATE,
                "generated_at": "2026-03-10T16:00:00+08:00",
                "funds": [
                    self.quote("ADD", 2.0, "2026-03-10"),
                    self.quote("HOLD", 2.0, "2026-03-10"),
                    self.quote("RED", 2.0, "2026-03-10"),
                    self.quote("UNTRUST", 2.0, "2026-03-10"),
                ],
            },
        )
        self.agent.write_json(
            "raw/quotes/2026-03-11.json",
            {
                "report_date": "2026-03-11",
                "generated_at": "2026-03-11T16:00:00+08:00",
                "funds": [
                    self.quote("ADD", 2.1, "2026-03-11"),
                    self.quote("HOLD", 1.9, "2026-03-11"),
                    self.quote("RED", 1.9, "2026-03-11"),
                    self.quote("UNTRUST", 1.9, "2026-03-11"),
                ],
            },
        )
        self.agent.write_json(
            "config/benchmark_mappings.json",
            {
                "fund_benchmarks": {
                    "ADD": {"benchmark_key": "bm_add", "benchmark_name": "Add Benchmark"},
                    "HOLD": {"benchmark_key": "bm_hold", "benchmark_name": "Hold Benchmark"},
                }
            },
        )
        self.agent.write_json(
            "db/benchmark_history/bm_add.json",
            {
                "generated_at": "2026-03-11T16:30:00+08:00",
                "items": [
                    {"date": "2026-03-10", "nav": 1.0},
                    {"date": "2026-03-11", "nav": 1.02},
                ],
            },
        )
        self.agent.write_json(
            "db/benchmark_history/bm_hold.json",
            {
                "generated_at": "2026-03-11T16:30:00+08:00",
                "items": [
                    {"date": "2026-03-10", "nav": 1.0},
                    {"date": "2026-03-11", "nav": 0.99},
                ],
            },
        )

    def ticket(self, code: str, action: str, amount: float) -> dict:
        return {
            "ticket_id": f"ticket:{BASE_DATE}:{code}:{action}:001",
            "schema_version": "action_ticket.v1",
            "report_date": BASE_DATE,
            "generated_at": GENERATED_AT,
            "fund_code": code,
            "fund_name": f"{code} Fund",
            "action_verb": action,
            "execution_mode": "immediate" if action != "hold" else "watch",
            "ticket_status": "shadow_only",
            "non_executable": True,
            "write_scope": "shadow_only",
            "amount_currency": "CNY",
            "validated_amount": amount,
            "confidence": 0.6,
            "thesis": f"{action} {code}",
            "hard_guardrail_results": [{"rule_id": "test", "result": "pass", "status_reason": "test"}],
            "source_artifacts": [],
            "legacy_mapping": {"suggestion_id": code},
        }

    def quote(self, code: str, nav: float, nav_date: str) -> dict:
        return {
            "code": code,
            "name": f"{code} Fund",
            "nav": nav,
            "as_of_date": nav_date,
            "date_match_type": "same_day",
            "retrieved_at": f"{nav_date}T16:00:00+08:00",
        }

    def test_scores_add_reduce_and_hold_outcomes(self) -> None:
        artifact = build_outcome_artifact(self.agent.root, BASE_DATE, "T+1", generated_at=GENERATED_AT)
        payload = artifact.to_dict()
        by_code = {event["fund_code"]: event for event in payload["events"]}

        self.assertEqual(4, payload["summary"]["event_count"])
        self.assertEqual(3, payload["summary"]["scored_count"])
        self.assertEqual(1, payload["summary"]["blocked_count"])
        self.assertEqual("scored", by_code["ADD"]["scoring_status"])
        self.assertEqual("helped", by_code["ADD"]["outcome_label"])
        self.assertEqual(5.0, by_code["ADD"]["actual_return_pct"])
        self.assertEqual(2.0, by_code["ADD"]["benchmark_return_pct"])
        self.assertEqual(3.0, by_code["ADD"]["excess_return_pct"])
        self.assertEqual("scored", by_code["HOLD"]["scoring_status"])
        self.assertEqual("hurt", by_code["HOLD"]["outcome_label"])
        self.assertEqual("hold_existing_position", by_code["HOLD"]["decision_context"]["exposure_context"])
        self.assertTrue(by_code["HOLD"]["decision_context"]["learning_eligible"])
        self.assertEqual("scored", by_code["RED"]["scoring_status"])
        self.assertEqual("avoided_loss", by_code["RED"]["outcome_label"])
        self.assertEqual("reduce_exposure", by_code["RED"]["decision_context"]["exposure_context"])
        self.assertEqual("blocked", by_code["UNTRUST"]["scoring_status"])
        self.assertEqual("untrusted_units_source:derived_from_official_nav", by_code["UNTRUST"]["blocked_reason"])
        self.assertEqual("ticket:2026-03-10:ADD:add:001", by_code["ADD"]["ticket_id"])

    def test_cash_hold_context_keeps_avoided_loss_semantics(self) -> None:
        ticket_path = self.agent.root / "db" / "action_tickets" / f"{BASE_DATE}.json"
        payload = json.loads(ticket_path.read_text(encoding="utf-8"))
        payload["tickets"] = [self.ticket("CASH", "hold", 0.0)]
        payload["tickets"][0]["legacy_mapping"]["model_action"] = "add"
        ticket_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        quote = self.quote("CASH", 2.0, BASE_DATE)
        self.agent.write_json(f"raw/quotes/{BASE_DATE}.json", {"report_date": BASE_DATE, "funds": [quote]})
        self.agent.write_json("raw/quotes/2026-03-11.json", {"report_date": "2026-03-11", "funds": [self.quote("CASH", 1.9, "2026-03-11")]})

        artifact = build_outcome_artifact(self.agent.root, BASE_DATE, "T+1", generated_at=GENERATED_AT)
        event = artifact.to_dict()["events"][0]

        self.assertEqual("avoided_loss", event["outcome_label"])
        self.assertEqual("blocked_add_or_cash_hold", event["decision_context"]["exposure_context"])

    def test_existing_position_blocked_add_hold_is_not_learning_eligible(self) -> None:
        ticket_path = self.agent.root / "db" / "action_tickets" / f"{BASE_DATE}.json"
        payload = json.loads(ticket_path.read_text(encoding="utf-8"))
        payload["tickets"] = [self.ticket("HOLD", "hold", 0.0)]
        payload["tickets"][0]["legacy_mapping"]["model_action"] = "add"
        ticket_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.agent.write_json(
            "raw/quotes/2026-03-11.json",
            {
                "report_date": "2026-03-11",
                "generated_at": "2026-03-11T16:00:00+08:00",
                "funds": [self.quote("HOLD", 2.1, "2026-03-11")],
            },
        )

        artifact = build_outcome_artifact(self.agent.root, BASE_DATE, "T+1", generated_at=GENERATED_AT)
        event = artifact.to_dict()["events"][0]

        self.assertEqual("neutral", event["outcome_label"])
        self.assertEqual("blocked_add_with_existing_position", event["decision_context"]["exposure_context"])
        self.assertFalse(event["decision_context"]["learning_eligible"])
        self.assertEqual("blocked_add_with_existing_position_mixed_follow_through_not_scored_for_learning", event["diagnostic_label"])

    def test_uses_next_available_quote_after_calendar_target(self) -> None:
        (self.agent.root / "raw" / "quotes" / "2026-03-11.json").unlink()
        self.agent.write_json("raw/quotes/2026-03-12.json", {
            "report_date": "2026-03-12",
            "generated_at": "2026-03-12T16:00:00+08:00",
            "funds": [
                self.quote("ADD", 2.2, "2026-03-12"),
                self.quote("HOLD", 2.1, "2026-03-12"),
                self.quote("RED", 1.8, "2026-03-12"),
                self.quote("UNTRUST", 1.8, "2026-03-12"),
            ],
        })
        self.agent.write_json("config/trading_calendar.json", {"holidays": ["2026-03-11"], "makeup_trading_days": []})

        artifact = build_outcome_artifact(self.agent.root, BASE_DATE, "T+1", generated_at=GENERATED_AT)
        payload = artifact.to_dict()

        self.assertEqual("2026-03-11", payload["target_date"])
        self.assertEqual("2026-03-12", payload["evaluation_date"])
        self.assertEqual("2026-03-12", payload["evaluation_date_used"])
        self.assertEqual("next_available_official_nav", payload["date_match_type"])
        self.assertEqual(["2026-03-12"], payload["summary"]["actual_evaluation_dates"])
        self.assertEqual(3, payload["summary"]["scored_count"])

    def test_uses_next_available_quote_when_fund_missing_on_target_quote_file(self) -> None:
        target_payload = json.loads((self.agent.root / "raw" / "quotes" / "2026-03-11.json").read_text(encoding="utf-8"))
        target_payload["funds"] = [item for item in target_payload["funds"] if item["code"] != "HOLD"]
        self.agent.write_json("raw/quotes/2026-03-11.json", target_payload)
        self.agent.write_json("raw/quotes/2026-03-12.json", {
            "report_date": "2026-03-12",
            "generated_at": "2026-03-12T16:00:00+08:00",
            "funds": [self.quote("HOLD", 2.1, "2026-03-12")],
        })

        artifact = build_outcome_artifact(self.agent.root, BASE_DATE, "T+1", generated_at=GENERATED_AT)
        payload = artifact.to_dict()
        hold_event = next(item for item in payload["events"] if item["fund_code"] == "HOLD")
        quote_sources = {
            item["path"]
            for item in payload["source_artifacts"]
            if item.get("kind") == "official_nav"
        }

        self.assertEqual("scored", hold_event["scoring_status"])
        self.assertEqual("2026-03-12", hold_event["evaluation_date"])
        self.assertEqual("2026-03-12", hold_event["official_nav_end"]["evaluation_date_used"])
        self.assertEqual("next_available_official_nav", hold_event["official_nav_end"]["evaluation_file_match_type"])
        self.assertEqual(["2026-03-11", "2026-03-12"], payload["summary"]["actual_evaluation_dates"])
        self.assertIn("raw/quotes/2026-03-12.json", quote_sources)

    def test_pending_when_evaluation_quote_file_missing(self) -> None:
        (self.agent.root / "raw" / "quotes" / "2026-03-11.json").unlink()

        artifact = build_outcome_artifact(self.agent.root, BASE_DATE, "T+1", generated_at=GENERATED_AT)
        statuses = {event.scoring_status for event in artifact.events}
        reasons = {event.blocked_reason for event in artifact.events}

        self.assertEqual({"pending"}, statuses)
        self.assertEqual({"missing_evaluation_quote_file"}, reasons)
        self.assertEqual(4, artifact.summary["pending_count"])

    def test_blocks_when_cashflow_crosses_nav_window(self) -> None:
        self.agent.write_json(
            "db/execution_sync/actual_trades/2026-03-11.json",
            {
                "trade_date": "2026-03-11",
                "items": [
                    {
                        "trade_id": "trade:add:cashflow",
                        "operation_type": "buy",
                        "fund_code": "ADD",
                        "effective_trade_date": "2026-03-11",
                    }
                ],
            },
        )

        artifact = build_outcome_artifact(self.agent.root, BASE_DATE, "T+1", generated_at=GENERATED_AT)
        add_event = next(event for event in artifact.events if event.fund_code == "ADD")

        self.assertEqual("blocked", add_event.scoring_status)
        self.assertEqual("cashflow_between_nav_dates_requires_position_snapshot", add_event.blocked_reason)
        self.assertTrue(add_event.cashflow_checks["cashflow_between_nav_dates"])

    def test_rerun_is_idempotent_for_same_inputs_and_fixed_clock(self) -> None:
        _, first = run_builder(self.agent.root, BASE_DATE, "T+1", generated_at=GENERATED_AT)
        _, second = run_builder(self.agent.root, BASE_DATE, "T+1", generated_at=GENERATED_AT)

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(outcome_event_path(self.agent.root, BASE_DATE, "T+1"), self.agent.root / "db" / "outcome_events" / "2026-03-10__T+1.json")

    def test_round_trip_and_boundary(self) -> None:
        artifact = build_outcome_artifact(self.agent.root, BASE_DATE, "T+1", generated_at=GENERATED_AT)
        payload = artifact.to_dict()

        self.assertEqual(payload, OutcomeEventArtifact.from_dict(payload).to_dict())
        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(
                self.agent.root / "db" / "validated_advice" / f"{BASE_DATE}.json",
                payload,
                self.agent.root,
            )
        payload["non_executable"] = False
        with self.assertRaises(OutcomeEventValidationError):
            OutcomeEventArtifact.from_dict(payload)

    def test_builder_does_not_mutate_official_inputs(self) -> None:
        portfolio_path = self.agent.root / "db" / "portfolio_state" / "current.json"
        quote_path = self.agent.root / "raw" / "quotes" / "2026-03-11.json"
        before_portfolio = _sha256(portfolio_path)
        before_quote = _sha256(quote_path)

        path, artifact = run_builder(self.agent.root, BASE_DATE, "T+1", generated_at=GENERATED_AT)

        self.assertTrue(path.exists())
        self.assertEqual(4, artifact.summary["event_count"])
        self.assertEqual(before_portfolio, _sha256(portfolio_path))
        self.assertEqual(before_quote, _sha256(quote_path))
        completed = self.agent.run_script(
            "evaluate_action_ticket_outcomes.py",
            "--date",
            BASE_DATE,
            "--horizon",
            "T+1",
            "--generated-at",
            GENERATED_AT,
        )
        self.assertIn("wrote 4 outcome events", completed.stdout)


if __name__ == "__main__":
    unittest.main()
