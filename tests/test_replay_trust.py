from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from replay_trust import audit_replay_entry


class ReplayTrustTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _write_source(self, payload: dict, name: str = "decision.json") -> Path:
        return self.agent.write_json(f"db/trust_test/{name}", payload)

    def _write_manifest(
        self,
        source_path: Path,
        *,
        mode: str = "trusted",
        learning_eligible: bool = True,
        role: str = "decision",
        sha256: str | None = None,
    ) -> None:
        relative = source_path.relative_to(self.agent.root).as_posix()
        digest = sha256 or hashlib.sha256(source_path.read_bytes()).hexdigest()
        self.agent.write_json(
            "config/historical_replay_trust.json",
            {
                "schema_version": "historical_replay_trust.v1",
                "default_mode": "blocked",
                "dates": {
                    "2026-03-10": {
                        "report_date": "2026-03-10",
                        "mode": mode,
                        "learning_eligible": learning_eligible,
                        "decision_cutoff": "2026-03-10T15:00:00+08:00",
                        "sources": [
                            {
                                "kind": "test_source",
                                "role": role,
                                "path": relative,
                                "sha256": digest,
                            }
                        ],
                    }
                },
                "slices": {},
            },
        )

    def test_trusted_entry_with_exact_hash_allows_learning(self):
        source = self._write_source({"generated_at": "2026-03-10T14:00:00+08:00"})
        self._write_manifest(source)

        audit = audit_replay_entry(self.agent.root, "2026-03-10")

        self.assertTrue(audit["integrity_passed"])
        self.assertTrue(audit["allowed_for_replay"])
        self.assertTrue(audit["allowed_for_learning"])

    def test_missing_manifest_fails_closed(self):
        audit = audit_replay_entry(self.agent.root, "2026-03-10")

        self.assertFalse(audit["allowed_for_replay"])
        self.assertIn("missing_trust_manifest", audit["reason_codes"])

    def test_hash_mismatch_fails_integrity(self):
        source = self._write_source({"generated_at": "2026-03-10T14:00:00+08:00"})
        self._write_manifest(source, sha256="0" * 64)

        audit = audit_replay_entry(self.agent.root, "2026-03-10")

        self.assertFalse(audit["integrity_passed"])
        self.assertIn("source_hash_mismatch", audit["reason_codes"])

    def test_future_decision_evidence_blocks_trusted_entry(self):
        source = self._write_source({"items": [{"available_from": "2026-03-11T09:00:00+08:00"}]})
        self._write_manifest(source)

        audit = audit_replay_entry(self.agent.root, "2026-03-10")

        self.assertTrue(audit["integrity_passed"])
        self.assertFalse(audit["allowed_for_replay"])
        self.assertEqual(audit["contamination_findings"][0]["code"], "future_decision_evidence")

    def test_future_evaluation_evidence_is_not_a_decision_leak(self):
        source = self._write_source({"available_from": "2026-03-11T09:00:00+08:00"}, "evaluation.json")
        self._write_manifest(source, role="evaluation")

        audit = audit_replay_entry(self.agent.root, "2026-03-10")

        self.assertTrue(audit["allowed_for_learning"])

    def test_execution_memory_blocks_trusted_entry(self):
        source = self._write_source(
            {
                "visibility": {"include_execution": False},
                "similar_cases": [{"source_record_id": "execution:historical_trade"}],
            }
        )
        self._write_manifest(source)

        audit = audit_replay_entry(self.agent.root, "2026-03-10")

        self.assertFalse(audit["allowed_for_learning"])
        self.assertIn("execution_record_visible", {item["code"] for item in audit["contamination_findings"]})

    def test_structural_entry_requires_opt_in_and_never_allows_learning(self):
        source = self._write_source({"generated_at": "2026-03-10T14:00:00+08:00"})
        self._write_manifest(source, mode="structural_only", learning_eligible=False)

        default_audit = audit_replay_entry(self.agent.root, "2026-03-10")
        structural_audit = audit_replay_entry(self.agent.root, "2026-03-10", include_structural=True)

        self.assertFalse(default_audit["allowed_for_replay"])
        self.assertTrue(structural_audit["allowed_for_replay"])
        self.assertFalse(structural_audit["allowed_for_learning"])

    def test_source_path_must_remain_inside_agent_home(self):
        outside = self.agent.root.parent / "outside-replay-trust.json"
        outside.write_text("{}", encoding="utf-8")
        try:
            source = self._write_source({})
            self._write_manifest(source)
            manifest_path = self.agent.root / "config/historical_replay_trust.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["dates"]["2026-03-10"]["sources"][0]["path"] = "../outside-replay-trust.json"
            manifest["dates"]["2026-03-10"]["sources"][0]["sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
            self.agent.write_json("config/historical_replay_trust.json", manifest)
            audit = audit_replay_entry(self.agent.root, "2026-03-10")
        finally:
            outside.unlink(missing_ok=True)

        self.assertFalse(audit["integrity_passed"])
        self.assertIn("source_path_outside_agent_home", audit["reason_codes"])


class RepositoryReplayTrustTests(unittest.TestCase):
    def test_golden_slice_is_structural_only_and_contaminated(self):
        agent_home = Path(__file__).resolve().parents[1]

        audit = audit_replay_entry(
            agent_home,
            "2026-05-22__017641__scheduled_dca",
            entry_type="slices",
            include_structural=True,
        )

        self.assertTrue(audit["integrity_passed"])
        self.assertEqual(audit["mode"], "structural_only")
        self.assertTrue(audit["allowed_for_replay"])
        self.assertFalse(audit["allowed_for_learning"])
        codes = {item["code"] for item in audit["contamination_findings"]}
        self.assertIn("future_decision_evidence", codes)
        self.assertIn("execution_record_visible", codes)


if __name__ == "__main__":
    unittest.main()
