from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
REPORT_DATE = "2026-03-12"
GENERATED_AT = "2026-03-12T23:30:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed  # noqa: E402
from build_strategy_skill_pack import build_usage_artifact, run_builder  # noqa: E402
from helpers import TempAgentHome  # noqa: E402
from run_skill_curator import run_curator  # noqa: E402
from strategy_skill_store import skill_pack_path, skill_usage_path  # noqa: E402


class StrategySkillPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def policy(self, policy_id: str, status: str, support: int, contradiction: int, action: str = "add") -> dict:
        return {
            "policy_id": policy_id,
            "schema_version": "adaptive_policy.v1",
            "scope": "portfolio:growth_cluster",
            "status": status,
            "statement": f"Review repeat {action}.",
            "when_to_apply": {"action_verb": action, "portfolio_bucket": "growth_cluster"},
            "effect_type": "note",
            "effect_value": "review_outcome_history_before_repeating_action",
            "effect_bounds": {},
            "allowed_effects": ["confidence_delta", "note", "size_multiplier", "wait_trigger"],
            "forbidden_effects": ["block", "change_hard_constraint", "force_trade"],
            "support_count": support,
            "contradiction_count": contradiction,
            "confidence": max(0.0, min(0.95, 0.2 + support * 0.08 - contradiction * 0.12)),
            "source_outcome_ids": [f"outcome:2026-03-10:T+1:F{idx}:add:{idx:03d}" for idx in range(1, max(1, support) + 1)],
            "source_ticket_ids": [f"ticket:2026-03-10:F{idx}:add:001" for idx in range(1, max(1, support) + 1)],
            "last_supported_at": GENERATED_AT if support else "",
            "last_contradicted_at": GENERATED_AT if contradiction else "",
            "last_reviewed_at": GENERATED_AT,
            "valid_from": "2026-03-12",
            "valid_until": "",
            "version": 1,
            "promotion_rule": {"min_support_count_for_active": 5, "user_approval_can_activate": True},
            "audit": {"created_by": "test"},
        }

    def write_policy_store(self) -> None:
        policies = [
            self.policy("policy:portfolio:growth_cluster:repeat_add:v1", "candidate", 2, 0),
            self.policy("policy:portfolio:growth_cluster:repeat_reduce:v1", "archived", 2, 4, action="reduce"),
        ]
        self.agent.write_json(
            "db/strategy_memory/policies.json",
            {
                "schema_version": "adaptive_policy_store.v1",
                "generated_at": GENERATED_AT,
                "materialized_from": "db/strategy_memory/policy_events.jsonl",
                "write_scope": "learning_only",
                "non_executable": True,
                "hard_block_allowed": False,
                "policies": policies,
                "recent_events": [],
                "caps": {
                    "min_support_count_for_candidate": 2,
                    "min_support_count_for_active": 5,
                    "max_contradiction_ratio_for_active": 0.25,
                    "max_active_policies_per_scope": 5,
                    "max_candidate_policies_per_scope": 20,
                    "archive_if_contradiction_ratio_above": 0.6,
                    "min_total_count_for_contradiction_archive": 3,
                },
                "summary": {"policy_count": len(policies)},
            },
        )

    def write_action_tickets(self) -> None:
        self.agent.write_json(
            f"db/action_tickets/{REPORT_DATE}.json",
            {
                "schema_version": "action_ticket.v1",
                "artifact_id": f"action_tickets:{REPORT_DATE}",
                "artifact_kind": "action_ticket_shadow",
                "report_date": REPORT_DATE,
                "generated_at": GENERATED_AT,
                "write_scope": "shadow_only",
                "non_executable": True,
                "source_artifacts": [],
                "summary": {"ticket_count": 1},
                "tickets": [
                    {
                        "ticket_id": f"ticket:{REPORT_DATE}:ADD:add:001",
                        "fund_code": "ADD",
                        "fund_name": "Add Fund",
                        "action_verb": "add",
                        "portfolio_bucket": "growth_cluster",
                        "ticket_status": "shadow_only",
                        "write_scope": "shadow_only",
                        "non_executable": True,
                    }
                ],
            },
        )

    def write_trusted_skill_audit(self) -> None:
        registry = json.loads((self.agent.root / "db/strategy_skills/registry.json").read_text(encoding="utf-8"))
        self.agent.write_json(
            "db/learning_trust_audits/latest.json",
            {
                "schema_version": "learning_trust_audit.v1",
                "skills": [
                    {"skill_id": item["skill_id"], "trust_status": "trusted", "reason_codes": []}
                    for item in registry.get("entries", [])
                ],
                "summary": {},
            },
        )

    def test_builder_writes_pack_and_non_mutating_usage_candidates(self) -> None:
        self.write_policy_store()
        self.write_action_tickets()
        run_curator(self.agent.root, generated_at=GENERATED_AT)
        self.write_trusted_skill_audit()

        pack_path, usage_path, pack, usage = run_builder(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)

        self.assertEqual(skill_pack_path(self.agent.root), pack_path)
        self.assertEqual(skill_usage_path(self.agent.root, REPORT_DATE), usage_path)
        self.assertEqual("strategy_skill_pack.v1", pack["schema_version"])
        self.assertEqual("learning_only", pack["write_scope"])
        self.assertTrue(pack["non_executable"])
        self.assertFalse(pack["selection_policy"]["writes_action_tickets"])
        self.assertEqual(1, pack["summary"]["candidate_skill_count"])
        self.assertEqual(1, usage["summary"]["usage_candidate_count"])
        self.assertEqual(0, usage["summary"]["applied_to_ticket_file_count"])
        self.assertFalse(usage["usage"][0]["applied_to_ticket_file"])

    def test_untrusted_skill_remains_visible_but_is_not_used(self) -> None:
        self.write_policy_store()
        self.write_action_tickets()
        run_curator(self.agent.root, generated_at=GENERATED_AT)

        _pack_path, _usage_path, pack, usage = run_builder(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)

        self.assertEqual("blocked", pack["candidate_skills"][0]["learning_trust_status"])
        self.assertEqual(0, usage["summary"]["usage_candidate_count"])

    def test_usage_artifact_without_ticket_file_stays_empty(self) -> None:
        self.write_policy_store()
        run_curator(self.agent.root, generated_at=GENERATED_AT)
        pack_path, _usage_path, pack, _usage = run_builder(self.agent.root, generated_at=GENERATED_AT)

        usage = build_usage_artifact(self.agent.root, REPORT_DATE, pack, generated_at=GENERATED_AT)

        self.assertEqual(0, usage["summary"]["ticket_count"])
        self.assertEqual(0, usage["summary"]["usage_candidate_count"])
        self.assertEqual(pack_path, skill_pack_path(self.agent.root))

    def test_pack_boundary_rejects_official_path(self) -> None:
        self.write_policy_store()
        run_curator(self.agent.root, generated_at=GENERATED_AT)
        _pack_path, _usage_path, pack, _usage = run_builder(self.agent.root, generated_at=GENERATED_AT)

        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(self.agent.root / "db" / "validated_advice" / "skill_pack.json", pack, self.agent.root)

    def test_cli_skill_pack_builder_works_with_temp_agent_home(self) -> None:
        self.write_policy_store()
        self.write_action_tickets()
        run_curator(self.agent.root, generated_at=GENERATED_AT)
        self.write_trusted_skill_audit()

        completed = self.agent.run_script("build_strategy_skill_pack.py", "--date", REPORT_DATE, "--generated-at", GENERATED_AT)

        self.assertIn("wrote strategy skill pack", completed.stdout)
        self.assertTrue(skill_pack_path(self.agent.root).exists())
        self.assertTrue(skill_usage_path(self.agent.root, REPORT_DATE).exists())
        usage = json.loads(skill_usage_path(self.agent.root, REPORT_DATE).read_text(encoding="utf-8"))
        self.assertEqual(1, usage["summary"]["usage_candidate_count"])


if __name__ == "__main__":
    unittest.main()
