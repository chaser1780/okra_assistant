from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_learning_trust import build_learning_trust_audit, run_audit, write_learning_trust_audit
from helpers import TempAgentHome


GENERATED_AT = "2026-07-11T10:00:00+08:00"
BASE_DATE = "2026-03-10"
OUTCOME_ID = "outcome:2026-03-10:T+1:000001:add:001"
POLICY_ID = "policy:fund:000001:repeat_add:v1"
SKILL_ID = "skill:fund_000001:repeat_add_review:v1"


class LearningTrustAuditTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _write_trust_manifest(self) -> None:
        source = self.agent.write_json(
            "db/trust_source/decision.json",
            {"generated_at": "2026-03-10T14:00:00+08:00"},
        )
        self.agent.write_json(
            "config/historical_replay_trust.json",
            {
                "schema_version": "historical_replay_trust.v1",
                "default_mode": "blocked",
                "dates": {
                    BASE_DATE: {
                        "report_date": BASE_DATE,
                        "mode": "trusted",
                        "learning_eligible": True,
                        "decision_cutoff": "2026-03-10T15:00:00+08:00",
                        "sources": [
                            {
                                "kind": "decision",
                                "role": "decision",
                                "path": source.relative_to(self.agent.root).as_posix(),
                                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                            }
                        ],
                    }
                },
                "slices": {},
            },
        )

    def _write_learning_lineage(
        self,
        *,
        learning_eligible: bool = True,
        excess_return_pct: float | None = 1.25,
        relative_semantics: bool = True,
    ) -> dict[str, Path]:
        outcome_path = self.agent.write_json(
            f"db/outcome_events/{BASE_DATE}__T+1.json",
            {
                "schema_version": "outcome_event.v1",
                "base_date": BASE_DATE,
                "horizon": "T+1",
                "events": [
                    {
                        "outcome_id": OUTCOME_ID,
                        "base_date": BASE_DATE,
                        "horizon": "T+1",
                        "scoring_status": "scored",
                        "excess_return_pct": excess_return_pct,
                        "decision_context": {
                            "learning_eligible": learning_eligible,
                            "learning_basis": "benchmark_excess_return",
                        },
                    }
                ],
            },
        )
        event_audit = {"source_artifact_sha256": hashlib.sha256(outcome_path.read_bytes()).hexdigest()}
        if relative_semantics:
            event_audit["learning_signal_basis"] = "benchmark_excess_return"
        event_path = self.agent.write_text(
            "db/strategy_memory/policy_events.jsonl",
            json.dumps(
                {
                    "event_id": f"policy_event:{OUTCOME_ID}",
                    "policy_id": POLICY_ID,
                    "source_outcome_id": OUTCOME_ID,
                    "source_artifact": outcome_path.relative_to(self.agent.root).as_posix(),
                    "write_scope": "learning_only",
                    "non_executable": True,
                    "audit": event_audit,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
        )
        policy_path = self.agent.write_json(
            "db/strategy_memory/policies.json",
            {
                "schema_version": "adaptive_policy_store.v1",
                "non_executable": True,
                "policies": [
                    {"policy_id": POLICY_ID, "status": "candidate", "source_outcome_ids": [OUTCOME_ID]}
                ],
            },
        )
        skill_path = self.agent.write_text("db/strategy_skills/fund_000001/skill.md", "# Test skill\n")
        skill_events = self.agent.write_text(
            "db/strategy_skills/fund_000001/events.jsonl",
            json.dumps(
                {
                    "event_id": "skill_event:test",
                    "skill_id": SKILL_ID,
                    "source_policy_ids": [POLICY_ID],
                    "source_outcome_ids": [OUTCOME_ID],
                    "status_after": "candidate",
                    "non_executable": True,
                },
                sort_keys=True,
            )
            + "\n",
        )
        registry_path = self.agent.write_json(
            "db/strategy_skills/registry.json",
            {
                "schema_version": "strategy_skill_registry.v1",
                "non_executable": True,
                "auto_activation_allowed": False,
                "entries": [
                    {
                        "skill_id": SKILL_ID,
                        "status": "candidate",
                        "source_policy_ids": [POLICY_ID],
                        "source_outcome_ids": [OUTCOME_ID],
                        "skill_path": skill_path.relative_to(self.agent.root).as_posix(),
                        "event_log_path": skill_events.relative_to(self.agent.root).as_posix(),
                        "auto_activation_allowed": False,
                        "non_executable": True,
                    }
                ],
            },
        )
        return {
            "outcome": outcome_path,
            "event": event_path,
            "policy": policy_path,
            "registry": registry_path,
            "skill": skill_path,
            "skill_events": skill_events,
        }

    def test_trusted_relative_lineage_is_trusted_end_to_end(self):
        self._write_trust_manifest()
        self._write_learning_lineage()

        audit = build_learning_trust_audit(self.agent.root, generated_at=GENERATED_AT)

        self.assertEqual(audit["outcomes"][0]["trust_status"], "trusted")
        self.assertEqual(audit["policy_events"][0]["trust_status"], "trusted")
        self.assertEqual(audit["policies"][0]["trust_status"], "trusted")
        self.assertEqual(audit["skills"][0]["trust_status"], "trusted")
        self.assertEqual(audit["summary"]["trusted_learning_artifact_count"], 4)

    def test_missing_replay_trust_keeps_valid_lineage_legacy_untrusted(self):
        self._write_learning_lineage()

        audit = build_learning_trust_audit(self.agent.root, generated_at=GENERATED_AT)

        self.assertEqual(audit["outcomes"][0]["trust_status"], "legacy_untrusted")
        self.assertEqual(audit["policy_events"][0]["trust_status"], "legacy_untrusted")
        self.assertEqual(audit["policies"][0]["trust_status"], "legacy_untrusted")
        self.assertEqual(audit["skills"][0]["trust_status"], "legacy_untrusted")

    def test_old_absolute_return_event_is_legacy_without_source_mutation(self):
        self._write_trust_manifest()
        paths = self._write_learning_lineage(
            learning_eligible=False,
            excess_return_pct=None,
            relative_semantics=False,
        )
        before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}

        _path, audit = run_audit(self.agent.root, generated_at=GENERATED_AT)

        after = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
        self.assertEqual(before, after)
        self.assertEqual(audit["outcomes"][0]["trust_status"], "blocked")
        self.assertEqual(audit["policy_events"][0]["trust_status"], "legacy_untrusted")
        self.assertEqual(audit["policies"][0]["trust_status"], "legacy_untrusted")
        self.assertEqual(audit["skills"][0]["trust_status"], "legacy_untrusted")
        self.assertIn("legacy_absolute_return_semantics", audit["policy_events"][0]["reason_codes"])
        self.assertEqual(audit["summary"]["source_mutation_count"], 0)
        self.assertEqual(audit["summary"]["activation_change_count"], 0)

    def test_ineligible_outcome_blocks_relative_lineage(self):
        self._write_trust_manifest()
        self._write_learning_lineage(learning_eligible=False, excess_return_pct=None)

        audit = build_learning_trust_audit(self.agent.root, generated_at=GENERATED_AT)

        self.assertEqual(audit["outcomes"][0]["trust_status"], "blocked")
        self.assertEqual(audit["policy_events"][0]["trust_status"], "blocked")
        self.assertEqual(audit["policies"][0]["trust_status"], "blocked")
        self.assertEqual(audit["skills"][0]["trust_status"], "blocked")

    def test_fixed_timestamp_produces_deterministic_output(self):
        self._write_trust_manifest()
        self._write_learning_lineage()
        path, _audit = run_audit(self.agent.root, generated_at=GENERATED_AT)
        first = path.read_bytes()

        path, _audit = run_audit(self.agent.root, generated_at=GENERATED_AT)

        self.assertEqual(first, path.read_bytes())

    def test_output_path_cannot_escape_audit_directory(self):
        with self.assertRaises(ValueError):
            write_learning_trust_audit(self.agent.root, {"schema_version": "test"}, output="db/outside.json")

    def test_cli_writes_only_sidecar_audit(self):
        self._write_trust_manifest()
        paths = self._write_learning_lineage()
        before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}

        completed = self.agent.run_script(
            "audit_learning_trust.py",
            "--generated-at",
            GENERATED_AT,
            "--format",
            "json",
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema_version"], "learning_trust_audit.v1")
        self.assertTrue((self.agent.root / "db/learning_trust_audits/latest.json").is_file())
        after = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
