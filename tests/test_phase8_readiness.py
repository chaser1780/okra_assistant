from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
REPORT_DATE = "2026-05-22"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from audit_phase8_readiness import REQUIRED_CONSUMER_AREAS, build_phase8_audit, render_markdown  # noqa: E402
from helpers import TempAgentHome  # noqa: E402


def _write_promoted_run(agent: TempAgentHome) -> None:
    official_paths = {
        "committee_advice": f"db/committee_advice/{REPORT_DATE}.json",
        "committee_decision_bundle": f"db/committee_decision_bundle/{REPORT_DATE}.json",
        "llm_advice": f"db/llm_advice/{REPORT_DATE}.json",
        "llm_raw": f"db/llm_raw/{REPORT_DATE}.json",
        "validated_advice": f"db/validated_advice/{REPORT_DATE}.json",
        "decisions": f"db/decisions/{REPORT_DATE}.json",
    }
    agent.write_json(
        f"db/phase8/promoted_runs/{REPORT_DATE}.json",
        {
            "schema_version": "promoted_advice_chain.v1",
            "mode": "action_debate_promoted",
            "official_path_mutation_allowed": True,
            "native_independent_of_legacy_validated_seed": True,
            "official_paths_written": official_paths,
            "preview_quality": {"missing_required_fields": []},
            "summary": {
                "promoted_run_passed": True,
                "validated_action_count": 1,
                "advice_mode": "action_debate_promoted",
                "decision_source": "action_debate_promoted",
            },
        },
    )
    agent.write_json(
        f"db/llm_raw/{REPORT_DATE}.json",
        {"mode": "action_debate_promoted", "decision_source": "action_debate_promoted"},
    )
    agent.write_json(
        f"db/validated_advice/{REPORT_DATE}.json",
        {"advice_mode": "action_debate_promoted", "decision_source": "action_debate_promoted"},
    )
    agent.write_json(
        f"db/action_seed/{REPORT_DATE}.json",
        {"summary": {"native_independent_of_validated_advice": True}},
    )
    agent.write_json(f"db/decisions/{REPORT_DATE}.json", {"decisions": [{"decision_id": "d1"}]})
    agent.write_text(f"db/refactor_reviews/{REPORT_DATE}.md", "# ready\n")


class Phase8ReadinessAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()
        (self.agent.root / "scripts").mkdir(exist_ok=True)
        (self.agent.root / "scripts" / "run_daily_pipeline.py").write_text(
            "run_promoted_advice_chain.py\npromoted_advice_guardrails.py\n",
            encoding="utf-8",
        )
        (self.agent.root / "scripts" / "promoted_advice_guardrails.py").write_text("# guardrails\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.agent.cleanup()

    def test_consumer_map_covers_required_phase8_areas(self) -> None:
        audit = build_phase8_audit(self.agent.root, REPORT_DATE, generated_at="2026-05-28T10:00:00+08:00")

        areas = {item["area"] for item in audit["consumer_map"]}
        self.assertTrue(REQUIRED_CONSUMER_AREAS.issubset(areas))
        self.assertEqual([], audit["missing_consumer_areas"])
        self.assertFalse(audit["official_path_mutation_allowed"])
        self.assertFalse(audit["promotion_ready"])
        self.assertIn("promoted_official_run", audit["blocking_gates"])

    def test_execution_mutation_boundaries_reject_shadow_inputs(self) -> None:
        audit = build_phase8_audit(self.agent.root, REPORT_DATE)

        mutation_paths = {item["path"]: item for item in audit["mutation_boundaries"]}
        self.assertIn("/api/execution-sync/trade", mutation_paths)
        self.assertIn("scripts/decision_ledger.py::build_and_write_decisions", mutation_paths)
        self.assertTrue(all(item["shadow_allowed"] is False for item in mutation_paths.values()))

    def test_promoted_run_evidence_makes_readiness_ready(self) -> None:
        _write_promoted_run(self.agent)

        audit = build_phase8_audit(
            self.agent.root,
            REPORT_DATE,
            generated_at="2026-05-28T10:00:00+08:00",
            promotion_approved=True,
        )

        self.assertTrue(audit["promotion_ready"])
        self.assertEqual([], audit["blocking_gates"])
        gates = {item["gate_id"]: item for item in audit["required_evidence"]}
        self.assertEqual("ready", gates["promoted_official_run"]["status"])
        self.assertEqual("ready", gates["legacy_chain_removed"]["status"])
        self.assertEqual("ready", gates["default_pipeline_promoted_only"]["status"])

    def test_existing_legacy_script_blocks_readiness(self) -> None:
        _write_promoted_run(self.agent)
        (self.agent.root / "scripts" / "generate_llm_advice.py").write_text("# legacy\n", encoding="utf-8")

        audit = build_phase8_audit(self.agent.root, REPORT_DATE)

        self.assertFalse(audit["promotion_ready"])
        self.assertIn("legacy_chain_removed", audit["blocking_gates"])

    def test_markdown_renderer_includes_promoted_gates(self) -> None:
        _write_promoted_run(self.agent)
        audit = build_phase8_audit(self.agent.root, REPORT_DATE)
        markdown = render_markdown(audit)

        self.assertIn("promoted_official_run", markdown)
        self.assertIn("legacy_chain_removed", markdown)

    def test_cli_outputs_json(self) -> None:
        _write_promoted_run(self.agent)
        completed = self.agent.run_script("audit_phase8_readiness.py", "--date", REPORT_DATE)

        payload = json.loads(completed.stdout)
        self.assertEqual("phase8_readiness_audit.v2", payload["schema_version"])
        self.assertTrue(payload["promotion_ready"])


if __name__ == "__main__":
    unittest.main()
