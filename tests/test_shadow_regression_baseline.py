from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
REPORT_DATE = "2026-05-22"
GENERATED_AT = "2026-05-30T23:30:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from audit_phase8_readiness import build_phase8_audit  # noqa: E402
from build_shadow_regression_baseline import baseline_path, markdown_path, run_builder  # noqa: E402
from helpers import TempAgentHome  # noqa: E402
from layered_fixture_helpers import write_synthetic_inputs  # noqa: E402


class ShadowRegressionBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def seed(self, report_date: str = REPORT_DATE) -> None:
        write_synthetic_inputs(self.agent, report_date)

    def test_builds_named_shadow_regression_baseline_and_phase8_audit_uses_it(self) -> None:
        self.seed()

        json_path, md_path, payload = run_builder(
            self.agent.root,
            [REPORT_DATE],
            "phase8_shadow_baseline_test",
            generated_at=GENERATED_AT,
        )

        self.assertEqual(baseline_path(self.agent.root, "phase8_shadow_baseline_test"), json_path)
        self.assertEqual(markdown_path(self.agent.root, "phase8_shadow_baseline_test"), md_path)
        self.assertTrue(payload["summary"]["named_regression_baseline_passed"])
        self.assertTrue(json_path.exists())
        self.assertTrue(md_path.exists())

        audit = build_phase8_audit(self.agent.root, REPORT_DATE, promotion_approved=False, generated_at=GENERATED_AT)
        gates = {item["gate_id"]: item for item in audit["required_evidence"]}

        self.assertNotIn("regression_baselines", gates)
        self.assertEqual("partial", gates["promoted_official_run"]["status"])
        promoted = gates["promoted_official_run"]["evidence"]["promoted_run"]
        self.assertFalse(promoted["valid"])
        self.assertIn("promoted_official_run", audit["blocking_gates"])

    def test_regression_baseline_fails_when_preview_is_not_validator_compatible(self) -> None:
        self.seed("2026-04-20")
        preview_file = self.agent.root / "db/refactor_shadow_runs/2026-04-20__official_advice_compat_preview/official_advice_compat_preview.json"

        def write_failed_preview(*args, **kwargs):
            preview_file.parent.mkdir(parents=True, exist_ok=True)
            preview = {
                "summary": {
                    "official_shape_compatible": True,
                    "official_behavior_comparable": True,
                    "official_adapter_dry_run_passed": False,
                    "source_hash_verified": True,
                    "official_compatible_advice": False,
                    "official_output_unchanged": True,
                    "official_paths_written": [],
                    "missing_required_fields": [],
                },
                "comparison_to_official": {"mismatched_count": 0},
                "validated_action_sections_preview": {
                    "tactical_actions": [{"validated_action": "reduce"}],
                    "dca_actions": [],
                    "hold_actions": [],
                },
            }
            preview_file.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
            return preview_file, preview

        with patch("build_shadow_regression_baseline.run_compat_preview_builder", side_effect=write_failed_preview):
            _json_path, _md_path, payload = run_builder(
                self.agent.root,
                ["2026-04-20"],
                "phase8_shadow_reduce_not_compatible_test",
                generated_at=GENERATED_AT,
                required_action_types=["reduce"],
            )

        self.assertFalse(payload["summary"]["named_regression_baseline_passed"])
        self.assertEqual(0, payload["summary"]["ready_date_count"])
        self.assertIn("reduce", payload["summary"]["distinct_action_types"])
        self.assertEqual([], payload["summary"]["missing_required_action_types"])
        self.assertIn("official_adapter_dry_run_passed", payload["dates"][0]["failures"])


if __name__ == "__main__":
    unittest.main()
