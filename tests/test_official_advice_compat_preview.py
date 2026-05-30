from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
REPORT_DATE = "2026-05-22"
TICKET_GENERATED_AT = "2026-05-22T21:30:00+08:00"
PACK_GENERATED_AT = "2026-05-22T21:35:00+08:00"
DEBATE_GENERATED_AT = "2026-05-22T21:40:00+08:00"
PREVIEW_GENERATED_AT = "2026-05-28T11:00:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed
from build_action_ticket_shadow import run_builder as run_action_ticket_builder
from build_layered_retrieval_pack import run_builder as run_retrieval_pack_builder
from build_official_advice_compat_preview import (
    CompatPreviewError,
    preview_path,
    run_builder as run_compat_preview_builder,
)
from action_debate_graph import run_debate_graph
from helpers import TempAgentHome


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_repo_json(relative: str) -> dict:
    return json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))


class OfficialAdviceCompatPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def copy_real_inputs(self) -> None:
        for relative in (
            f"db/validated_advice/{REPORT_DATE}.json",
            "db/portfolio_state/current.json",
            f"db/llm_context/{REPORT_DATE}.json",
            f"db/evidence_index/{REPORT_DATE}.json",
            "db/long_memory/exports/all_memory.json",
        ):
            self.agent.write_json(relative, _load_repo_json(relative))

    def build_shadow_chain(self) -> None:
        self.copy_real_inputs()
        run_action_ticket_builder(self.agent.root, REPORT_DATE, generated_at=TICKET_GENERATED_AT)
        run_retrieval_pack_builder(self.agent.root, REPORT_DATE, generated_at=PACK_GENERATED_AT)
        run_debate_graph(self.agent.root, REPORT_DATE, generated_at=DEBATE_GENERATED_AT)

    def test_preview_builds_official_compatible_shapes_without_official_mutation(self) -> None:
        self.build_shadow_chain()
        validated_path = self.agent.root / "db" / "validated_advice" / f"{REPORT_DATE}.json"
        portfolio_path = self.agent.root / "db" / "portfolio_state" / "current.json"
        before_validated = _sha256(validated_path)
        before_portfolio = _sha256(portfolio_path)

        path, payload = run_compat_preview_builder(self.agent.root, REPORT_DATE, generated_at=PREVIEW_GENERATED_AT)

        self.assertEqual(preview_path(self.agent.root, REPORT_DATE), path)
        self.assertEqual("official_advice_compat_preview.v1", payload["schema_version"])
        self.assertEqual("shadow_only", payload["write_scope"])
        self.assertTrue(payload["non_executable"])
        self.assertTrue(payload["summary"]["official_shape_compatible"])
        self.assertFalse(payload["summary"]["official_compatible_advice"])
        self.assertFalse(payload["summary"]["fallback_switch_active"])
        self.assertFalse(payload["summary"]["promotion_ready"])
        self.assertEqual([], payload["summary"]["official_paths_written"])
        self.assertEqual(15, payload["summary"]["committee_decision_count"])
        self.assertEqual(15, len(payload["committee_decision_bundle_preview"]["fund_decisions"]))
        self.assertEqual(15, len(payload["final_advice_preview"]["fund_decisions"]))
        self.assertEqual(15, payload["summary"]["validated_section_preview_count"])
        self.assertEqual(
            "hold_only",
            payload["committee_decision_bundle_preview"]["decision_mode"],
        )
        self.assertFalse(payload["committee_decision_bundle_preview"]["execution_eligible"])
        section_items = (
            payload["validated_action_sections_preview"]["tactical_actions"]
            + payload["validated_action_sections_preview"]["dca_actions"]
            + payload["validated_action_sections_preview"]["hold_actions"]
        )
        self.assertTrue(section_items)
        for item in section_items:
            self.assertIn("cash_impact", item)
            self.assertIn("allocation_impact", item)
            self.assertIn("source_signal_ids", item)
            self.assertIn("opposing_signal_ids", item)
        self.assertEqual(before_validated, _sha256(validated_path))
        self.assertEqual(before_portfolio, _sha256(portfolio_path))
        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(validated_path, payload, self.agent.root)

    def test_golden_slice_fund_maps_to_final_advice_decision(self) -> None:
        self.build_shadow_chain()

        _path, payload = run_compat_preview_builder(self.agent.root, REPORT_DATE, generated_at=PREVIEW_GENERATED_AT)

        decisions = {
            item["fund_code"]: item
            for item in payload["final_advice_preview"]["fund_decisions"]
        }
        golden = decisions["017641"]
        self.assertEqual("scheduled_dca", golden["action"])
        self.assertEqual(25.0, golden["suggest_amount"])
        self.assertIn("decision_trace", golden)
        self.assertIn("ticket:2026-05-22:017641:scheduled_dca:001", golden["decision_trace"]["decision_card_ids"])

    def test_source_hash_mismatch_rejects_preview(self) -> None:
        self.build_shadow_chain()
        ticket_path = self.agent.root / "db" / "action_tickets" / f"{REPORT_DATE}.json"
        ticket_payload = json.loads(ticket_path.read_text(encoding="utf-8"))
        ticket_payload["tickets"][0]["confidence"] = 0.99
        ticket_path.write_text(json.dumps(ticket_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with self.assertRaises(CompatPreviewError) as ctx:
            run_compat_preview_builder(self.agent.root, REPORT_DATE, generated_at=PREVIEW_GENERATED_AT)

        self.assertIn("hash mismatch", str(ctx.exception))

    def test_cli_outputs_summary_json(self) -> None:
        self.build_shadow_chain()

        completed = self.agent.run_script(
            "build_official_advice_compat_preview.py",
            "--date",
            REPORT_DATE,
            "--generated-at",
            PREVIEW_GENERATED_AT,
            "--format",
            "json",
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(
            f"db/refactor_shadow_runs/{REPORT_DATE}__official_advice_compat_preview/official_advice_compat_preview.json",
            payload["path"],
        )
        self.assertTrue(payload["summary"]["official_shape_compatible"])
        self.assertFalse(payload["summary"]["official_compatible_advice"])


if __name__ == "__main__":
    unittest.main()
