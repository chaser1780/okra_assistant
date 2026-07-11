from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture_replay_snapshot import capture_decision_snapshot
from helpers import TempAgentHome
from replay_trust import audit_replay_entry


class CaptureReplaySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()
        self.decision_path = self.agent.write_json(
            "db/llm_advice/2026-03-10.json",
            {
                "report_date": "2026-03-10",
                "generated_at": "2026-03-10T14:00:00+08:00",
                "visibility": {"include_execution": False},
            },
        )

    def tearDown(self):
        self.agent.cleanup()

    def sources(self) -> list[dict[str, str]]:
        return [
            {
                "kind": "llm_advice",
                "role": "decision",
                "path": self.decision_path.relative_to(self.agent.root).as_posix(),
            }
        ]

    def test_capture_copies_exact_bytes_and_emits_blocked_candidate(self):
        official_manifest = self.agent.root / "config/historical_replay_trust.json"

        result = capture_decision_snapshot(
            self.agent.root,
            "2026-03-10",
            "2026-03-10T15:00:00+08:00",
            sources=self.sources(),
        )

        candidate_path = self.agent.root / result["manifest_candidate_path"]
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        entry = candidate["dates"]["2026-03-10"]
        copied_path = self.agent.root / entry["sources"][0]["path"]
        self.assertTrue(result["created"])
        self.assertFalse(official_manifest.exists())
        self.assertEqual("blocked", entry["mode"])
        self.assertFalse(entry["learning_eligible"])
        self.assertEqual("decision", entry["sources"][0]["role"])
        self.assertEqual(self.decision_path.read_bytes(), copied_path.read_bytes())
        self.assertEqual(hashlib.sha256(copied_path.read_bytes()).hexdigest(), entry["sources"][0]["sha256"])
        audit = audit_replay_entry(self.agent.root, "2026-03-10", manifest_path=candidate_path)
        self.assertTrue(audit["integrity_passed"])
        self.assertFalse(audit["allowed_for_replay"])
        self.assertFalse(audit["allowed_for_learning"])

    def test_capture_records_future_and_execution_contamination(self):
        self.agent.write_json(
            "db/llm_advice/2026-03-10.json",
            {
                "items": [
                    {"available_from": "2026-03-10T16:00:00+08:00"},
                    {"source_record_id": "execution:trade-1"},
                ]
            },
        )

        result = capture_decision_snapshot(
            self.agent.root,
            "2026-03-10",
            "2026-03-10T15:00:00+08:00",
            sources=self.sources(),
        )

        candidate = json.loads((self.agent.root / result["manifest_candidate_path"]).read_text(encoding="utf-8"))
        codes = {item["code"] for item in candidate["candidate_metadata"]["contamination_findings"]}
        self.assertIn("future_decision_evidence", codes)
        self.assertIn("execution_record_visible", codes)
        self.assertIn("future_decision_evidence", candidate["dates"]["2026-03-10"]["reason_codes"])
        self.assertFalse(result["audit"]["allowed_for_replay"])

    def test_identical_capture_is_idempotent_and_hash_stable(self):
        first = capture_decision_snapshot(
            self.agent.root,
            "2026-03-10",
            "2026-03-10T15:00:00+08:00",
            sources=self.sources(),
        )
        candidate_path = self.agent.root / first["manifest_candidate_path"]
        before = hashlib.sha256(candidate_path.read_bytes()).hexdigest()

        second = capture_decision_snapshot(
            self.agent.root,
            "2026-03-10",
            "2026-03-10T15:00:00+08:00",
            sources=self.sources(),
        )

        after = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        self.assertFalse(second["created"])
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(before, after)

    def test_standard_discovery_freezes_declared_decision_dependencies(self):
        self.agent.write_json("config/benchmark_mappings.json", {"fund_benchmarks": {}})
        self.agent.write_json("db/validated_advice/2026-03-10.json", {"report_date": "2026-03-10"})
        self.agent.write_json("db/portfolio_state/snapshots/2026-03-10.json", {"as_of_date": "2026-03-10"})
        dependency = self.agent.write_json("db/long_memory/exports/replay-input.json", {"items": []})
        self.agent.write_json(
            "db/llm_advice/2026-03-10.json",
            {
                "report_date": "2026-03-10",
                "generated_at": "2026-03-10T14:00:00+08:00",
                "source_artifacts": [
                    {"kind": "long_memory", "path": dependency.relative_to(self.agent.root).as_posix()}
                ],
            },
        )

        result = capture_decision_snapshot(
            self.agent.root,
            "2026-03-10",
            "2026-03-10T15:00:00+08:00",
        )

        candidate = json.loads((self.agent.root / result["manifest_candidate_path"]).read_text(encoding="utf-8"))
        origins = {
            item["original_path"]
            for item in candidate["candidate_metadata"]["source_origins"]
        }
        self.assertIn("db/long_memory/exports/replay-input.json", origins)

    def test_changed_source_cannot_overwrite_immutable_snapshot(self):
        result = capture_decision_snapshot(
            self.agent.root,
            "2026-03-10",
            "2026-03-10T15:00:00+08:00",
            sources=self.sources(),
        )
        candidate_path = self.agent.root / result["manifest_candidate_path"]
        candidate_hash = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        self.agent.write_json("db/llm_advice/2026-03-10.json", {"generated_at": "2026-03-10T14:30:00+08:00"})

        with self.assertRaisesRegex(RuntimeError, "immutable replay snapshot conflict"):
            capture_decision_snapshot(
                self.agent.root,
                "2026-03-10",
                "2026-03-10T15:00:00+08:00",
                sources=self.sources(),
            )

        self.assertEqual(candidate_hash, hashlib.sha256(candidate_path.read_bytes()).hexdigest())

    def test_source_path_cannot_escape_agent_home(self):
        outside = self.agent.root.parent / "outside-capture.json"
        outside.write_text("{}", encoding="utf-8")
        try:
            with self.assertRaisesRegex(ValueError, "escapes agent_home"):
                capture_decision_snapshot(
                    self.agent.root,
                    "2026-03-10",
                    "2026-03-10T15:00:00+08:00",
                    sources=[{"kind": "outside", "role": "decision", "path": "../outside-capture.json"}],
                )
        finally:
            outside.unlink(missing_ok=True)

    def test_cutoff_requires_offset_and_matching_report_date(self):
        with self.assertRaisesRegex(ValueError, "UTC offset"):
            capture_decision_snapshot(
                self.agent.root,
                "2026-03-10",
                "2026-03-10T15:00:00",
                sources=self.sources(),
            )
        with self.assertRaisesRegex(ValueError, "match report_date"):
            capture_decision_snapshot(
                self.agent.root,
                "2026-03-10",
                "2026-03-11T15:00:00+08:00",
                sources=self.sources(),
            )


if __name__ == "__main__":
    unittest.main()
