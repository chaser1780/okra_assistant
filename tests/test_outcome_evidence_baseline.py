from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
REPORT_DATE = "2026-05-22"
GENERATED_AT = "2026-05-31T00:50:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from audit_phase8_readiness import build_phase8_audit  # noqa: E402
from build_action_ticket_shadow import run_builder as run_action_ticket_builder  # noqa: E402
from build_outcome_evidence_baseline import baseline_path, markdown_path, run_builder  # noqa: E402
from helpers import TempAgentHome  # noqa: E402


def _load_repo_json(relative: str) -> dict:
    return json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))


class OutcomeEvidenceBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def copy_real_inputs(self) -> None:
        for relative in (
            f"db/validated_advice/{REPORT_DATE}.json",
            f"db/portfolio_state/snapshots/{REPORT_DATE}.json",
            "raw/quotes/2026-05-22.json",
            "raw/quotes/2026-05-23.json",
            "raw/quotes/2026-05-29.json",
            "db/long_memory/exports/all_memory.json",
        ):
            self.agent.write_json(relative, _load_repo_json(relative))

    def test_builds_named_outcome_evidence_baseline_but_audit_requires_promotion_scale_evidence(self) -> None:
        self.copy_real_inputs()
        run_action_ticket_builder(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)

        json_path, md_path, payload = run_builder(
            self.agent.root,
            [REPORT_DATE],
            ["T+1", "T+5"],
            "phase8_outcome_baseline_test",
            generated_at=GENERATED_AT,
            min_dates=1,
            min_horizons=2,
            min_scored_events=20,
            min_action_types=2,
            required_action_types=["scheduled_dca", "hold"],
        )

        self.assertEqual(baseline_path(self.agent.root, "phase8_outcome_baseline_test"), json_path)
        self.assertEqual(markdown_path(self.agent.root, "phase8_outcome_baseline_test"), md_path)
        self.assertTrue(payload["summary"]["multi_date_outcome_evidence_passed"])
        self.assertEqual(2, payload["summary"]["outcome_artifact_count"])
        self.assertGreaterEqual(payload["summary"]["total_scored_count"], 20)
        self.assertIn("scheduled_dca", payload["summary"]["distinct_action_types"])
        self.assertEqual([], payload["summary"]["missing_required_action_types"])
        self.assertTrue(json_path.exists())
        self.assertTrue(md_path.exists())

        audit = build_phase8_audit(self.agent.root, REPORT_DATE, promotion_approved=False, generated_at=GENERATED_AT)
        gates = {item["gate_id"]: item for item in audit["required_evidence"]}

        self.assertNotIn("outcome_examples", gates)
        self.assertEqual("partial", gates["promoted_official_run"]["status"])
        promoted = gates["promoted_official_run"]["evidence"]["promoted_run"]
        self.assertFalse(promoted["valid"])
        self.assertFalse(audit["promotion_ready"])
        self.assertIn("promoted_official_run", audit["blocking_gates"])

    def test_cli_outputs_json_summary(self) -> None:
        self.copy_real_inputs()
        run_action_ticket_builder(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)

        completed = self.agent.run_script(
            "build_outcome_evidence_baseline.py",
            "--date",
            REPORT_DATE,
            "--horizon",
            "T+1",
            "--horizon",
            "T+5",
            "--baseline-name",
            "phase8_outcome_cli_test",
            "--generated-at",
            GENERATED_AT,
            "--format",
            "json",
        )

        payload = json.loads(completed.stdout)
        self.assertEqual("db/refactor_shadow_runs/outcome_evidence_baselines/phase8_outcome_cli_test/baseline.json", payload["path"])
        self.assertTrue(payload["summary"]["multi_date_outcome_evidence_passed"] is False)
        self.assertEqual(1, payload["summary"]["date_count"])

    def test_required_action_type_must_be_present(self) -> None:
        self.copy_real_inputs()
        run_action_ticket_builder(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)

        _json_path, _md_path, payload = run_builder(
            self.agent.root,
            [REPORT_DATE],
            ["T+1", "T+5"],
            "phase8_outcome_missing_reduce_test",
            generated_at=GENERATED_AT,
            min_dates=1,
            min_horizons=2,
            min_scored_events=20,
            min_action_types=2,
            required_action_types=["reduce"],
        )

        self.assertFalse(payload["summary"]["multi_date_outcome_evidence_passed"])
        self.assertEqual(["reduce"], payload["summary"]["missing_required_action_types"])


if __name__ == "__main__":
    unittest.main()
