from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SLICE_ID = "2026-05-22__017641__scheduled_dca"

sys.path.insert(0, str(SCRIPTS_DIR))

from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed, assert_shadow_write_allowed
from diff_refactor_slice import build_diff_report, run_diff
from replay_refactor_slice import build_artifacts, load_slice_inputs, run_slice


class RefactorGoldenSliceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.output_dir = PROJECT_ROOT / "db" / "refactor_shadow_runs" / SLICE_ID
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def test_replay_from_fixture_is_deterministic(self) -> None:
        inputs = load_slice_inputs(SLICE_ID)
        first = build_artifacts(inputs)
        second = build_artifacts(inputs)
        self.assertEqual(first, second)
        ticket = first["action_ticket"]["tickets"][0]
        self.assertEqual("017641", ticket["fund_code"])
        self.assertEqual("scheduled_dca", ticket["action_verb"])
        self.assertTrue(ticket["non_executable"])
        self.assertEqual("shadow_only", ticket["write_scope"])
        self.assertEqual("not_checked", ticket["hard_guardrail_results"][2]["result"])

    def test_replay_writes_shadow_artifacts_and_diff_passes(self) -> None:
        result = run_slice(SLICE_ID, output_dir=self.output_dir)
        self.assertTrue((self.output_dir / "action_ticket.json").exists())
        self.assertTrue((self.output_dir / "retrieval_pack.json").exists())
        self.assertTrue((self.output_dir / "outcome_event.json").exists())
        self.assertEqual([], result["metadata"]["forbidden_writes"])

        diff_result = run_diff(SLICE_ID, output_dir=self.output_dir)
        self.assertEqual("PASS", diff_result["verdict"])
        report = (self.output_dir / "diff_report.md").read_text(encoding="utf-8")
        self.assertIn("trace_completeness_rate: 1.00", report)
        self.assertIn("forbidden_write_count: 0", report)
        self.assertIn("replay_diff_unapproved_count: 0", report)

    def test_artifacts_round_trip_json(self) -> None:
        run_slice(SLICE_ID, output_dir=self.output_dir)
        for name in ("action_ticket", "retrieval_pack", "outcome_event", "run_metadata"):
            path = self.output_dir / f"{name}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            self.assertEqual(payload, json.loads(serialized))

    def test_forbidden_official_write_is_detected(self) -> None:
        artifact = {
            "schema_version": "action_ticket.v1",
            "write_scope": "shadow_only",
            "non_executable": True,
            "tickets": [{"ticket_id": "ticket:test", "non_executable": True}],
        }
        with self.assertRaises(BoundaryViolation):
            assert_shadow_write_allowed(PROJECT_ROOT / "db" / "validated_advice" / "2026-05-22.json", artifact)

    def test_non_executable_check_scans_nested_debates(self) -> None:
        artifact = {
            "schema_version": "action_debate.v1",
            "artifact_id": "action_debates:test",
            "write_scope": "shadow_only",
            "non_executable": True,
            "debates": [
                {
                    "debate_id": "debate:test",
                    "non_executable": True,
                    "node_outputs": {
                        "ticket_writer": {
                            "proposed_ticket_patch": {
                                "ticket_id": "ticket:test",
                                "non_executable": False,
                            }
                        }
                    },
                }
            ],
        }
        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(PROJECT_ROOT / "db" / "action_debates" / "test.json", artifact)

    def test_diff_report_builder_flags_changed_artifact(self) -> None:
        run_slice(SLICE_ID, output_dir=self.output_dir)
        path = self.output_dir / "action_ticket.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["tickets"][0]["validated_amount"] = 30.0
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        report, details = build_diff_report(SLICE_ID, output_dir=self.output_dir)
        self.assertEqual("FAIL", details["verdict"])
        self.assertIn("replay_diff_unapproved_count: 1", report)
        self.assertIn("/tickets/0/validated_amount", report)

    def test_cli_replay_and_diff(self) -> None:
        subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(SCRIPTS_DIR / "replay_refactor_slice.py"),
                "--slice-id",
                SLICE_ID,
                "--output-dir",
                str(self.output_dir),
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(SCRIPTS_DIR / "diff_refactor_slice.py"),
                "--slice-id",
                SLICE_ID,
                "--output-dir",
                str(self.output_dir),
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertIn("PASS", completed.stdout)


if __name__ == "__main__":
    unittest.main()
