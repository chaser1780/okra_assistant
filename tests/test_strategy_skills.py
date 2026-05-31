from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
GENERATED_AT = "2026-03-12T23:30:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed  # noqa: E402
from helpers import TempAgentHome  # noqa: E402
from run_skill_curator import run_curator  # noqa: E402
from strategy_skill_models import (  # noqa: E402
    StrategySkillDocument,
    StrategySkillRegistry,
    StrategySkillValidationError,
    validate_skill_output,
)
from strategy_skill_store import (  # noqa: E402
    build_default_skill_pack,
    load_registry,
    record_skill_output_on_ticket,
    registry_path,
    skill_event_log_path,
    skill_markdown_path,
    validate_registry_matches_files,
)


class StrategySkillTests(unittest.TestCase):
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

    def write_policy_store(self, policies: list[dict]) -> None:
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

    def test_skill_markdown_frontmatter_validates(self) -> None:
        self.write_policy_store([self.policy("policy:portfolio:growth_cluster:repeat_add:v1", "candidate", 2, 0)])
        _registry, skill_paths, _event_paths, _appended = run_curator(self.agent.root, generated_at=GENERATED_AT)

        skill = StrategySkillDocument.from_markdown(skill_paths[0].read_text(encoding="utf-8"))

        self.assertEqual("strategy_skill.v1", skill.schema_version)
        self.assertEqual("candidate", skill.status)
        self.assertFalse(skill.auto_activation_allowed)
        self.assertFalse(skill.hard_constraints_editable)
        self.assertIn("Purpose", skill.sections)
        self.assertIn("Output Contract", skill.sections)

    def test_registry_entry_matches_skill_file(self) -> None:
        self.write_policy_store([self.policy("policy:portfolio:growth_cluster:repeat_add:v1", "candidate", 2, 0)])
        run_curator(self.agent.root, generated_at=GENERATED_AT)

        registry = load_registry(self.agent.root)
        errors = validate_registry_matches_files(self.agent.root)
        entry = registry.entries[0]
        skill = StrategySkillDocument.from_markdown(skill_markdown_path(self.agent.root, entry.skill_id).read_text(encoding="utf-8"))

        self.assertEqual([], errors)
        self.assertEqual(entry.skill_id, skill.skill_id)
        self.assertEqual(entry.status, skill.status)
        self.assertEqual(entry.source_policy_ids, skill.source_policy_ids)

    def test_draft_and_candidate_skills_created_from_policy_cluster_fixture(self) -> None:
        self.write_policy_store(
            [
                self.policy("policy:portfolio:growth_cluster:repeat_add:v1", "draft", 1, 0),
                self.policy("policy:portfolio:growth_cluster:repeat_hold:v1", "candidate", 2, 0, action="hold"),
                self.policy("policy:portfolio:growth_cluster:repeat_reduce:v1", "archived", 2, 4, action="reduce"),
            ]
        )

        _registry_path, skill_paths, event_paths, appended = run_curator(self.agent.root, generated_at=GENERATED_AT)
        registry = load_registry(self.agent.root)
        statuses = {entry.status for entry in registry.entries}

        self.assertEqual(3, len(skill_paths))
        self.assertEqual(3, len(event_paths))
        self.assertEqual(3, appended)
        self.assertEqual({"candidate", "draft", "archived"}, statuses)
        self.assertEqual({"archived": 1, "draft": 1, "candidate": 1}, registry.summary["status_counts"])

    def test_active_promotion_requires_support_or_approval_and_auto_active_is_zero(self) -> None:
        self.write_policy_store([self.policy("policy:portfolio:growth_cluster:repeat_add:v1", "active", 6, 0)])

        run_curator(self.agent.root, generated_at=GENERATED_AT)
        registry = load_registry(self.agent.root)

        self.assertEqual("candidate", registry.entries[0].status)
        self.assertEqual(0, registry.summary["active_skill_count"])
        self.assertEqual(0, registry.summary["auto_active_promotion_count"])
        self.assertFalse(registry.auto_activation_allowed)

    def test_archived_skill_is_kept_in_registry_but_excluded_from_default_skill_pack(self) -> None:
        self.write_policy_store(
            [
                self.policy("policy:portfolio:growth_cluster:repeat_add:v1", "candidate", 2, 0),
                self.policy("policy:portfolio:growth_cluster:repeat_reduce:v1", "archived", 2, 4, action="reduce"),
            ]
        )
        run_curator(self.agent.root, generated_at=GENERATED_AT)

        registry = load_registry(self.agent.root)
        pack = build_default_skill_pack(self.agent.root)

        self.assertEqual({"candidate", "archived"}, {entry.status for entry in registry.entries})
        self.assertEqual(0, pack["summary"]["active_skill_count"])
        self.assertEqual(1, pack["summary"]["candidate_skill_count"])
        self.assertEqual(1, pack["summary"]["archived_skill_count"])
        self.assertEqual(["skill:portfolio_growth_cluster:repeat_reduce_review:v1"], pack["archived_skill_ids"])
        self.assertEqual("candidate", pack["candidate_skills"][0]["status"])

    def test_skill_output_cannot_hard_block_or_force_trade(self) -> None:
        with self.assertRaises(StrategySkillValidationError):
            validate_skill_output({"skill_id": "skill:test:v1", "output_type": "hard_block", "value": "no"})
        with self.assertRaises(StrategySkillValidationError):
            validate_skill_output({"skill_id": "skill:test:v1", "output_type": "force_trade", "value": "buy"})

        output = validate_skill_output({"skill_id": "skill:test:v1", "output_type": "sizing_note", "value": "starter only"})
        self.assertTrue(output["non_executable"])

    def test_action_ticket_records_skill_refs_and_outputs_without_file_write(self) -> None:
        ticket = {"ticket_id": "ticket:test", "skill_refs": [], "skill_outputs": []}

        updated = record_skill_output_on_ticket(
            ticket,
            {"skill_id": "skill:test:v1", "status": "candidate"},
            {"skill_id": "skill:test:v1", "output_type": "confidence_delta", "value": "-0.05"},
        )

        self.assertEqual([], ticket["skill_refs"])
        self.assertEqual("skill:test:v1", updated["skill_refs"][0]["skill_id"])
        self.assertEqual("confidence_delta", updated["skill_outputs"][0]["output_type"])
        self.assertTrue(updated["skill_outputs"][0]["non_executable"])

    def test_event_log_append_only_and_idempotent(self) -> None:
        self.write_policy_store([self.policy("policy:portfolio:growth_cluster:repeat_add:v1", "candidate", 2, 0)])

        run_curator(self.agent.root, generated_at=GENERATED_AT)
        registry = load_registry(self.agent.root)
        event_path = skill_event_log_path(self.agent.root, registry.entries[0].skill_id)
        first = event_path.read_text(encoding="utf-8")
        _registry_path, _skill_paths, _event_paths, appended = run_curator(self.agent.root, generated_at=GENERATED_AT)
        second = event_path.read_text(encoding="utf-8")

        self.assertEqual(0, appended)
        self.assertEqual(first, second)
        self.assertEqual(1, len(first.splitlines()))

    def test_registry_round_trip_and_boundary(self) -> None:
        self.write_policy_store([self.policy("policy:portfolio:growth_cluster:repeat_add:v1", "candidate", 2, 0)])
        run_curator(self.agent.root, generated_at=GENERATED_AT)
        payload = self.agent.read_json("db/strategy_skills/registry.json") if hasattr(self.agent, "read_json") else None
        if payload is None:
            import json

            payload = json.loads(registry_path(self.agent.root).read_text(encoding="utf-8"))

        self.assertEqual(payload, StrategySkillRegistry.from_dict(payload).to_dict())
        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(self.agent.root / "db" / "validated_advice" / "registry.json", payload, self.agent.root)

    def test_cli_curator_works_with_temp_agent_home(self) -> None:
        self.write_policy_store([self.policy("policy:portfolio:growth_cluster:repeat_add:v1", "candidate", 2, 0)])

        completed = self.agent.run_script("run_skill_curator.py", "--generated-at", GENERATED_AT)

        self.assertIn("wrote strategy skill registry with 1 skills", completed.stdout)
        self.assertTrue(registry_path(self.agent.root).exists())


if __name__ == "__main__":
    unittest.main()
