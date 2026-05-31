from __future__ import annotations

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

from adaptive_policy_models import (  # noqa: E402
    EVENT_SCHEMA_VERSION,
    AdaptivePolicyEvent,
    AdaptivePolicyStore,
    AdaptivePolicyValidationError,
)
from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed  # noqa: E402
from helpers import TempAgentHome  # noqa: E402
from update_adaptive_policies import (  # noqa: E402
    materialize_policy_store,
    policy_event_log_path,
    policy_store_path,
    run_updater,
)


class AdaptivePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def ticket(self, code: str, action: str = "add", bucket: str = "growth_cluster") -> dict:
        return {
            "ticket_id": f"ticket:{BASE_DATE}:{code}:{action}:001",
            "schema_version": "action_ticket.v1",
            "report_date": BASE_DATE,
            "fund_code": code,
            "fund_name": f"{code} Fund",
            "role": "tactical",
            "portfolio_bucket": bucket,
            "action_verb": action,
            "execution_mode": "immediate" if action != "hold" else "watch",
            "ticket_status": "shadow_only",
            "non_executable": True,
            "write_scope": "shadow_only",
            "amount_currency": "CNY",
            "validated_amount": 100.0 if action != "hold" else 0.0,
            "confidence": 0.6,
            "thesis": f"{action} {code}",
            "hard_guardrail_results": [],
            "source_artifacts": [],
        }

    def outcome(
        self,
        code: str,
        label: str,
        *,
        action: str = "add",
        index: int = 1,
        status: str = "scored",
    ) -> dict:
        return {
            "outcome_id": f"outcome:{BASE_DATE}:T+1:{code}:{action}:{index:03d}",
            "ticket_id": f"ticket:{BASE_DATE}:{code}:{action}:001",
            "base_date": BASE_DATE,
            "evaluation_date": "2026-03-11",
            "horizon": "T+1",
            "fund_code": code,
            "fund_name": f"{code} Fund",
            "action_verb": action,
            "execution_mode": "immediate" if action != "hold" else "watch",
            "amount": 100.0 if action != "hold" else 0.0,
            "amount_currency": "CNY",
            "scoring_status": status,
            "blocked_reason": "missing_evaluation_quote_file" if status == "pending" else "",
            "official_nav_start": {"nav_date": BASE_DATE, "nav": 1.0} if status == "scored" else {},
            "official_nav_end": {"nav_date": "2026-03-11", "nav": 1.01} if status == "scored" else {},
            "benchmark": {},
            "actual_return_pct": 1.0 if status == "scored" else None,
            "benchmark_return_pct": None,
            "excess_return_pct": None,
            "no_action_baseline": {"baseline_type": "hold_cash", "return_pct": 0.0},
            "outcome_label": label,
            "diagnostic_label": f"{action}_{label}",
            "confidence": 0.6 if status == "scored" else 0.0,
            "cashflow_checks": {"cashflow_between_nav_dates": False, "units_trusted": True, "position_authoritative": True},
            "decision_context": {"exposure_context": "increase_exposure", "learning_eligible": True},
            "learning_implications": [],
            "source_refs": [],
            "audit": {"builder": "test"},
        }

    def write_inputs(self, outcomes: list[dict], tickets: list[dict] | None = None) -> None:
        tickets = tickets or [self.ticket(str(item["fund_code"]), str(item["action_verb"])) for item in outcomes]
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
                "summary": {"ticket_count": len(tickets)},
                "tickets": tickets,
            },
        )
        self.agent.write_json(
            f"db/outcome_events/{BASE_DATE}__T+1.json",
            {
                "schema_version": "outcome_event.v1",
                "artifact_id": f"outcome_events:{BASE_DATE}:T+1",
                "base_date": BASE_DATE,
                "evaluation_date": "2026-03-11",
                "horizon": "T+1",
                "generated_at": GENERATED_AT,
                "write_scope": "learning_only",
                "non_executable": True,
                "source_artifacts": [],
                "events": outcomes,
                "summary": {
                    "event_count": len(outcomes),
                    "scored_count": len([item for item in outcomes if item["scoring_status"] == "scored"]),
                    "pending_count": len([item for item in outcomes if item["scoring_status"] == "pending"]),
                    "blocked_count": 0,
                },
            },
        )

    def append_event(self, event: AdaptivePolicyEvent) -> None:
        path = policy_event_log_path(self.agent.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")

    def manual_event(self, event_id: str, policy_id: str, event_type: str, *, time: str = GENERATED_AT) -> AdaptivePolicyEvent:
        return AdaptivePolicyEvent(
            event_id=event_id,
            policy_id=policy_id,
            schema_version=EVENT_SCHEMA_VERSION,
            event_type=event_type,
            event_time=time,
            scope="portfolio:growth_cluster",
            statement="Manual policy event for test.",
            when_to_apply={"action_verb": "add"},
            effect_type="note",
            effect_value="manual_review_note",
            source_outcome_id=f"outcome:{event_id}",
            source_ticket_id=f"ticket:{event_id}",
            source_artifact="test",
            outcome_label="helped" if event_type == "support" else "hurt",
            diagnostic_label=event_type,
            delta={event_type: 1},
            notes="test",
            write_scope="learning_only",
            non_executable=True,
            audit={"created_by": "test"},
        )

    def test_supportive_outcomes_promote_draft_to_candidate_under_threshold_rules(self) -> None:
        outcomes = [
            self.outcome("F001", "helped", index=1),
            self.outcome("F002", "helped", index=2),
        ]
        tickets = [self.ticket("F001"), self.ticket("F002")]
        self.write_inputs(outcomes, tickets)

        event_path, store_path, updated, store = run_updater(self.agent.root, BASE_DATE, ["T+1"], generated_at=GENERATED_AT)
        policy = store.policies[0]

        self.assertEqual(policy_event_log_path(self.agent.root), event_path)
        self.assertEqual(policy_store_path(self.agent.root), store_path)
        self.assertEqual(2, updated)
        self.assertEqual("candidate", policy.status)
        self.assertEqual(2, policy.support_count)
        self.assertEqual(0, policy.contradiction_count)
        self.assertEqual("learning_only", store.write_scope)
        self.assertTrue(store.non_executable)
        self.assertFalse(store.hard_block_allowed)

    def test_active_promotion_requires_enough_support_or_user_approval(self) -> None:
        policy_id = "policy:portfolio:growth_cluster:repeat_add:v1"
        for index in range(4):
            self.append_event(self.manual_event(f"support:{index}", policy_id, "support"))

        store = materialize_policy_store(self.agent.root, generated_at=GENERATED_AT)
        self.assertEqual("candidate", store.policies[0].status)

        self.append_event(self.manual_event("support:4", policy_id, "support"))
        store = materialize_policy_store(self.agent.root, generated_at=GENERATED_AT)
        self.assertEqual("active", store.policies[0].status)

        approved_policy_id = "policy:portfolio:growth_cluster:repeat_hold:v1"
        self.append_event(self.manual_event("support:approved", approved_policy_id, "support"))
        self.append_event(self.manual_event("approval:approved", approved_policy_id, "user_approve"))
        store = materialize_policy_store(self.agent.root, generated_at=GENERATED_AT)
        by_id = {policy.policy_id: policy for policy in store.policies}
        self.assertEqual("active", by_id[approved_policy_id].status)

    def test_contradictions_weaken_and_archive_without_deleting_history(self) -> None:
        policy_id = "policy:portfolio:growth_cluster:repeat_add:v1"
        self.append_event(self.manual_event("support:1", policy_id, "support"))
        self.append_event(self.manual_event("contradict:1", policy_id, "contradict"))

        store = materialize_policy_store(self.agent.root, generated_at=GENERATED_AT)
        self.assertEqual("weakened", store.policies[0].status)

        self.append_event(self.manual_event("contradict:2", policy_id, "contradict"))
        store = materialize_policy_store(self.agent.root, generated_at=GENERATED_AT)
        policy = store.policies[0]

        self.assertEqual("archived", policy.status)
        self.assertEqual(1, policy.support_count)
        self.assertEqual(2, policy.contradiction_count)
        self.assertEqual(3, store.summary["valid_event_count"])

    def test_pending_and_neutral_outcomes_do_not_create_policy_events(self) -> None:
        outcomes = [
            self.outcome("F001", "not_scored", status="pending"),
            self.outcome("F002", "neutral", index=2),
        ]
        self.write_inputs(outcomes, [self.ticket("F001"), self.ticket("F002")])

        _event_path, _store_path, updated, store = run_updater(self.agent.root, BASE_DATE, ["T+1"], generated_at=GENERATED_AT)

        self.assertEqual(0, updated)
        self.assertEqual([], store.policies)
        self.assertEqual(0, store.summary["valid_event_count"])

    def test_unclear_hold_context_does_not_create_policy_event(self) -> None:
        outcome = self.outcome("F001", "avoided_loss", action="hold")
        outcome["decision_context"] = {"exposure_context": "unclear_hold_context", "learning_eligible": False}
        self.write_inputs([outcome], [self.ticket("F001", "hold")])

        _event_path, _store_path, updated, store = run_updater(self.agent.root, BASE_DATE, ["T+1"], generated_at=GENERATED_AT)

        self.assertEqual(0, updated)
        self.assertEqual([], store.policies)

    def test_policy_cap_per_scope_is_enforced(self) -> None:
        for index in range(25):
            policy_id = f"policy:portfolio:growth_cluster:repeat_add_{index:02d}:v1"
            self.append_event(self.manual_event(f"support:{index}:1", policy_id, "support"))
            self.append_event(self.manual_event(f"support:{index}:2", policy_id, "support"))

        store = materialize_policy_store(self.agent.root, generated_at=GENERATED_AT)
        active_or_candidate = [
            policy
            for policy in store.policies
            if policy.scope == "portfolio:growth_cluster" and policy.status in {"active", "candidate", "draft", "weakened", "revised"}
        ]

        self.assertLessEqual(len(active_or_candidate), store.caps["max_candidate_policies_per_scope"])
        self.assertEqual(5, store.summary["cap_adjusted_count"])

    def test_policy_event_log_replay_is_idempotent(self) -> None:
        outcomes = [self.outcome("F001", "helped")]
        self.write_inputs(outcomes, [self.ticket("F001")])

        run_updater(self.agent.root, BASE_DATE, ["T+1"], generated_at=GENERATED_AT)
        first = policy_event_log_path(self.agent.root).read_text(encoding="utf-8")
        _event_path, _store_path, updated, _store = run_updater(self.agent.root, BASE_DATE, ["T+1"], generated_at=GENERATED_AT)
        second = policy_event_log_path(self.agent.root).read_text(encoding="utf-8")

        self.assertEqual(0, updated)
        self.assertEqual(first, second)
        self.assertEqual(1, len(first.splitlines()))

    def test_policy_event_replay_replaces_stale_derived_outcome_event(self) -> None:
        outcome = self.outcome("F001", "hurt")
        self.write_inputs([outcome], [self.ticket("F001")])
        run_updater(self.agent.root, BASE_DATE, ["T+1"], generated_at=GENERATED_AT)

        outcome["outcome_label"] = "helped"
        outcome["diagnostic_label"] = "add_helped"
        outcome["actual_return_pct"] = 1.5
        self.write_inputs([outcome], [self.ticket("F001")])
        _event_path, _store_path, rewritten, store = run_updater(self.agent.root, BASE_DATE, ["T+1"], generated_at=GENERATED_AT)

        lines = [json.loads(line) for line in policy_event_log_path(self.agent.root).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(1, rewritten)
        self.assertEqual(1, len(lines))
        self.assertEqual("support", lines[0]["event_type"])
        self.assertEqual("helped", lines[0]["outcome_label"])
        self.assertEqual(1, store.policies[0].support_count)
        self.assertEqual(0, store.policies[0].contradiction_count)

    def test_soft_policy_cannot_produce_hard_block(self) -> None:
        with self.assertRaises(AdaptivePolicyValidationError):
            AdaptivePolicyEvent(
                event_id="policy_event:block",
                policy_id="policy:portfolio:growth_cluster:block:v1",
                schema_version=EVENT_SCHEMA_VERSION,
                event_type="support",
                event_time=GENERATED_AT,
                scope="portfolio:growth_cluster",
                statement="Bad hard block.",
                when_to_apply={"action_verb": "add"},
                effect_type="block",
                effect_value="block_trade",
                write_scope="learning_only",
                non_executable=True,
            )

    def test_malformed_policy_event_does_not_corrupt_materialized_view(self) -> None:
        path = policy_event_log_path(self.agent.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{bad json\n", encoding="utf-8")
        self.append_event(self.manual_event("support:good", "policy:portfolio:growth_cluster:repeat_add:v1", "support"))

        store = materialize_policy_store(self.agent.root, generated_at=GENERATED_AT)

        self.assertEqual(1, store.summary["invalid_event_count"])
        self.assertEqual(1, store.summary["valid_event_count"])
        self.assertEqual(1, len(store.policies))

    def test_round_trip_and_boundary(self) -> None:
        outcomes = [self.outcome("F001", "helped")]
        self.write_inputs(outcomes, [self.ticket("F001")])
        _event_path, _store_path, _updated, store = run_updater(self.agent.root, BASE_DATE, ["T+1"], generated_at=GENERATED_AT)
        payload = store.to_dict()

        self.assertEqual(payload, AdaptivePolicyStore.from_dict(payload).to_dict())
        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(self.agent.root / "db" / "validated_advice" / "policies.json", payload, self.agent.root)

    def test_cli_updater_works_with_temp_agent_home(self) -> None:
        outcomes = [self.outcome("F001", "helped")]
        self.write_inputs(outcomes, [self.ticket("F001")])

        completed = self.agent.run_script(
            "update_adaptive_policies.py",
            "--date",
            BASE_DATE,
            "--horizon",
            "T+1",
            "--generated-at",
            GENERATED_AT,
        )

        self.assertIn("updated 1 derived policy events", completed.stdout)
        self.assertTrue(policy_event_log_path(self.agent.root).exists())
        self.assertTrue(policy_store_path(self.agent.root).exists())


if __name__ == "__main__":
    unittest.main()
