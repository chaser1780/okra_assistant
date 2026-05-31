from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
GENERATED_AT = "2026-05-31T18:30:00+08:00"
DATES = ["2026-05-21", "2026-05-22"]

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from audit_phase8_completion import run_builder  # noqa: E402
from helpers import TempAgentHome  # noqa: E402


def _write_promoted_date(agent: TempAgentHome, report_date: str) -> None:
    official_paths = {
        "committee_advice": f"db/committee_advice/{report_date}.json",
        "committee_decision_bundle": f"db/committee_decision_bundle/{report_date}.json",
        "llm_advice": f"db/llm_advice/{report_date}.json",
        "llm_raw": f"db/llm_raw/{report_date}.json",
        "validated_advice": f"db/validated_advice/{report_date}.json",
        "decisions": f"db/decisions/{report_date}.json",
    }
    agent.write_json(
        f"db/phase8/promoted_runs/{report_date}.json",
        {
            "schema_version": "promoted_advice_chain.v1",
            "mode": "action_debate_promoted",
            "official_path_mutation_allowed": True,
            "native_independent_of_legacy_validated_seed": True,
            "official_paths_written": official_paths,
            "preview_quality": {
                "official_shape_compatible": True,
                "official_behavior_comparable": True,
                "official_adapter_dry_run_passed": True,
                "source_hash_verified": True,
                "missing_required_fields": [],
            },
            "summary": {
                "promoted_run_passed": True,
                "validated_action_count": 2,
                "tactical_action_count": 1,
                "dca_action_count": 1,
                "hold_action_count": 0,
                "advice_mode": "action_debate_promoted",
                "decision_source": "action_debate_promoted",
            },
        },
    )
    agent.write_json(
        f"db/llm_raw/{report_date}.json",
        {"mode": "action_debate_promoted", "decision_source": "action_debate_promoted"},
    )
    agent.write_json(
        f"db/validated_advice/{report_date}.json",
        {"advice_mode": "action_debate_promoted", "decision_source": "action_debate_promoted"},
    )
    agent.write_json(
        f"db/action_seed/{report_date}.json",
        {"summary": {"native_independent_of_validated_advice": True}},
    )
    agent.write_json(
        f"db/decisions/{report_date}.json",
        {"decisions": [{"decision_id": f"{report_date}:F1"}]},
    )


def _write_production_config(agent: TempAgentHome) -> None:
    agent.write_text(
        "config/production.toml",
        """[advice]
default_chain = "action_debate_promoted"
default_entrypoint = "scripts/run_promoted_advice_chain.py"
official_path_mutation_allowed = true
requires_legacy_validated_seed = false
legacy_multiagent_chain_enabled = false
legacy_committee_chain_enabled = false
legacy_validator_chain_enabled = false

[phase8]
promoted_rollout_approved = true
promoted_guardrails = "scripts/promoted_advice_guardrails.py"
stable_observation_dates = ["2026-05-21", "2026-05-22"]

[compatibility]
okra_env_required = false
""",
    )


class Phase8CompletionAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def copy_deleted_legacy_state(self) -> None:
        (self.agent.root / "scripts").mkdir(exist_ok=True)
        (self.agent.root / "scripts" / "run_daily_pipeline.py").write_text(
            "run_promoted_advice_chain.py\npromoted_advice_guardrails.py\n",
            encoding="utf-8",
        )
        _write_production_config(self.agent)
        for report_date in DATES:
            _write_promoted_date(self.agent, report_date)

    def test_completion_audit_ready_when_promoted_rollout_evidence_is_complete(self) -> None:
        self.copy_deleted_legacy_state()

        json_path, md_path, payload = run_builder(
            self.agent.root,
            DATES[-1],
            dates=DATES,
            generated_at=GENERATED_AT,
        )

        self.assertEqual("phase8_completion_audit.v2", payload["schema_version"])
        self.assertTrue(payload["summary"]["completion_ready"])
        self.assertTrue(payload["summary"]["all_promoted_dates_valid"])
        self.assertTrue(payload["summary"]["legacy_scripts_deleted"])
        self.assertTrue(payload["summary"]["default_pipeline_promoted_only"])
        self.assertTrue(payload["summary"]["project_production_config_ready"])
        self.assertEqual([], payload["remaining_required"])
        self.assertTrue(json_path.exists())
        self.assertTrue(md_path.exists())
        self.assertIn("Phase 8 Completion Audit", md_path.read_text(encoding="utf-8"))

    def test_cli_completion_audit_outputs_json_summary(self) -> None:
        self.copy_deleted_legacy_state()
        (self.agent.root / "config" / "production.toml").unlink()
        completed = self.agent.run_script(
            "audit_phase8_completion.py",
            "--date",
            DATES[-1],
            "--observation-date",
            DATES[0],
            "--observation-date",
            DATES[1],
            "--generated-at",
            GENERATED_AT,
            "--format",
            "json",
        )

        payload = json.loads(completed.stdout)
        self.assertEqual("db/phase8/completion_audit.json", payload["path"])
        self.assertFalse(payload["summary"]["completion_ready"])
        self.assertIn("project production config", " ".join(payload["remaining_required"]))


if __name__ == "__main__":
    unittest.main()
