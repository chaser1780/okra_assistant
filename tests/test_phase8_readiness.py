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

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from audit_phase8_readiness import REQUIRED_CONSUMER_AREAS, build_phase8_audit, render_markdown
from helpers import TempAgentHome


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Phase8ReadinessAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def write_ready_shadow_chain(self) -> None:
        for relative in (
            f"db/validated_advice/{REPORT_DATE}.json",
            f"db/action_tickets/{REPORT_DATE}.json",
            f"db/retrieval_packs/{REPORT_DATE}.json",
            f"db/action_debates/{REPORT_DATE}.json",
        ):
            self.agent.write_json(relative, {"report_date": REPORT_DATE})
        self.agent.write_text(f"db/refactor_reviews/{REPORT_DATE}.md", "# ready\n")

    def write_preview(self, payload: object) -> None:
        self.agent.write_json(
            f"db/refactor_shadow_runs/{REPORT_DATE}__official_advice_compat_preview/official_advice_compat_preview.json",
            payload,
        )

    def valid_preview_payload(self) -> dict:
        sources = []
        for relative in (
            f"db/validated_advice/{REPORT_DATE}.json",
            f"db/action_tickets/{REPORT_DATE}.json",
            f"db/retrieval_packs/{REPORT_DATE}.json",
            f"db/action_debates/{REPORT_DATE}.json",
        ):
            path = self.agent.root / relative
            sources.append({"kind": path.parent.name, "path": relative, "content_sha256": _sha256(path)})
        sources.append({"kind": "builder", "path": "scripts/build_official_advice_compat_preview.py", "content_sha256": ""})
        return {
            "schema_version": "official_advice_compat_preview.v1",
            "report_date": REPORT_DATE,
            "write_scope": "shadow_only",
            "non_executable": True,
            "display_only": True,
            "source_artifacts": sources,
            "summary": {
                "official_shape_compatible": True,
                "official_behavior_comparable": True,
                "official_adapter_dry_run_passed": True,
                "source_hash_verified": True,
                "official_compatible_advice": True,
                "committee_bundle_compatible": True,
                "llm_advice_compatible": True,
                "official_output_unchanged": True,
                "fallback_switch_active": True,
                "official_paths_written": [],
                "missing_required_fields": [],
            },
            "comparison_to_official": {"mismatched_count": 0},
            "committee_decision_bundle_preview": {"fund_decisions": []},
            "final_advice_preview": {"fund_decisions": []},
            "validated_action_sections_preview": {"tactical_actions": [], "dca_actions": [], "hold_actions": []},
        }

    def test_consumer_map_covers_required_phase8_areas(self) -> None:
        audit = build_phase8_audit(self.agent.root, REPORT_DATE, generated_at="2026-05-28T10:00:00+08:00")

        areas = {item["area"] for item in audit["consumer_map"]}
        self.assertTrue(REQUIRED_CONSUMER_AREAS.issubset(areas))
        self.assertEqual([], audit["missing_consumer_areas"])
        self.assertFalse(audit["official_path_mutation_allowed"])
        self.assertFalse(audit["promotion_ready"])
        self.assertIn("fallback_switch", audit["blocking_gates"])
        self.assertIn("explicit_promotion_decision", audit["blocking_gates"])

    def test_execution_mutation_boundaries_reject_shadow_inputs(self) -> None:
        audit = build_phase8_audit(self.agent.root, REPORT_DATE)

        mutation_paths = {item["path"]: item for item in audit["mutation_boundaries"]}
        self.assertIn("/api/execution-sync/trade", mutation_paths)
        self.assertIn("scripts/decision_ledger.py::build_and_write_decisions", mutation_paths)
        self.assertTrue(mutation_paths)
        self.assertTrue(all(item["shadow_allowed"] is False for item in mutation_paths.values()))

    def test_ready_shadow_artifacts_are_not_enough_for_promotion(self) -> None:
        self.write_ready_shadow_chain()

        audit = build_phase8_audit(
            self.agent.root,
            REPORT_DATE,
            generated_at="2026-05-28T10:00:00+08:00",
            promotion_approved=True,
        )

        self.assertFalse(audit["promotion_ready"])
        self.assertIn("fallback_switch", audit["blocking_gates"])
        self.assertIn("new_chain_official_compatible_advice", audit["blocking_gates"])
        self.assertNotIn("explicit_promotion_decision", audit["blocking_gates"])

    def test_contract_valid_preview_without_fallback_is_not_promotion_ready(self) -> None:
        self.write_ready_shadow_chain()
        payload = self.valid_preview_payload()
        payload["summary"]["fallback_switch_active"] = False
        payload["summary"]["official_compatible_advice"] = False
        self.write_preview(payload)

        audit = build_phase8_audit(
            self.agent.root,
            REPORT_DATE,
            generated_at="2026-05-28T10:00:00+08:00",
            promotion_approved=True,
        )

        self.assertFalse(audit["promotion_ready"])
        self.assertIn("new_chain_official_compatible_advice", audit["blocking_gates"])
        self.assertIn("fallback_switch", audit["blocking_gates"])
        compat_gate = next(item for item in audit["required_evidence"] if item["gate_id"] == "new_chain_official_compatible_advice")
        self.assertEqual("partial", compat_gate["status"])
        self.assertTrue(compat_gate["evidence"]["compat_preview"]["official_shape_compatible"])
        self.assertTrue(compat_gate["evidence"]["compat_preview"]["preview_contract_valid"])
        self.assertFalse(compat_gate["evidence"]["compat_preview"]["official_compatible_advice"])
        self.assertFalse(compat_gate["evidence"]["compat_preview"]["adapter_gate_ready"])

    def test_damaged_preview_summary_cannot_pass_adapter_gate(self) -> None:
        self.write_ready_shadow_chain()
        self.write_preview(
            {
                "schema_version": "wrong",
                "report_date": "2026-05-21",
                "write_scope": "official",
                "non_executable": False,
                "display_only": False,
                "source_artifacts": [],
                "summary": {
                    "official_shape_compatible": True,
                    "official_behavior_comparable": True,
                    "official_adapter_dry_run_passed": True,
                    "source_hash_verified": True,
                    "official_compatible_advice": True,
                    "official_output_unchanged": True,
                    "fallback_switch_active": True,
                    "official_paths_written": [],
                    "missing_required_fields": [],
                },
                "comparison_to_official": {"mismatched_count": 0},
            },
        )

        audit = build_phase8_audit(self.agent.root, REPORT_DATE, promotion_approved=True)
        compat_gate = next(item for item in audit["required_evidence"] if item["gate_id"] == "new_chain_official_compatible_advice")
        compat_preview = compat_gate["evidence"]["compat_preview"]

        self.assertEqual("partial", compat_gate["status"])
        self.assertFalse(compat_preview["official_compatible_advice"])
        self.assertFalse(compat_preview["adapter_gate_ready"])
        self.assertFalse(compat_preview["preview_contract_valid"])
        self.assertFalse(compat_preview["source_hash_verified"])

    def test_non_object_preview_json_does_not_crash_audit(self) -> None:
        self.write_ready_shadow_chain()
        self.write_preview([])

        audit = build_phase8_audit(self.agent.root, REPORT_DATE, promotion_approved=True)
        compat_gate = next(item for item in audit["required_evidence"] if item["gate_id"] == "new_chain_official_compatible_advice")
        compat_preview = compat_gate["evidence"]["compat_preview"]

        self.assertEqual("partial", compat_gate["status"])
        self.assertFalse(compat_preview["adapter_gate_ready"])
        self.assertFalse(compat_preview["preview_contract_valid"])
        self.assertIn("preview_root_object", compat_preview["preview_contract_failures"])

    def test_hash_valid_but_incomplete_preview_sources_cannot_pass_adapter_gate(self) -> None:
        self.write_ready_shadow_chain()
        action_path = self.agent.root / "db" / "action_tickets" / f"{REPORT_DATE}.json"
        payload = self.valid_preview_payload()
        payload["source_artifacts"] = [
            {"kind": "action_tickets", "path": f"db/action_tickets/{REPORT_DATE}.json", "content_sha256": _sha256(action_path)}
        ]
        self.write_preview(payload)

        audit = build_phase8_audit(self.agent.root, REPORT_DATE, promotion_approved=True)
        compat_gate = next(item for item in audit["required_evidence"] if item["gate_id"] == "new_chain_official_compatible_advice")
        compat_preview = compat_gate["evidence"]["compat_preview"]

        self.assertEqual("partial", compat_gate["status"])
        self.assertFalse(compat_preview["adapter_gate_ready"])
        self.assertFalse(compat_preview["preview_contract_valid"])
        self.assertIn("source_artifacts", compat_preview["preview_contract_failures"])
        self.assertIn(f"db/validated_advice/{REPORT_DATE}.json", compat_preview["source_hash_failures"])
        self.assertIn(f"db/retrieval_packs/{REPORT_DATE}.json", compat_preview["source_hash_failures"])
        self.assertIn(f"db/action_debates/{REPORT_DATE}.json", compat_preview["source_hash_failures"])

    def test_preview_missing_required_body_sections_cannot_pass_adapter_gate(self) -> None:
        self.write_ready_shadow_chain()
        payload = self.valid_preview_payload()
        payload.pop("committee_decision_bundle_preview")
        payload.pop("final_advice_preview")
        payload.pop("validated_action_sections_preview")
        self.write_preview(payload)

        audit = build_phase8_audit(self.agent.root, REPORT_DATE, promotion_approved=True)
        compat_gate = next(item for item in audit["required_evidence"] if item["gate_id"] == "new_chain_official_compatible_advice")
        compat_preview = compat_gate["evidence"]["compat_preview"]

        self.assertEqual("partial", compat_gate["status"])
        self.assertFalse(compat_preview["adapter_gate_ready"])
        self.assertFalse(compat_preview["preview_contract_valid"])
        self.assertIn("committee_decision_bundle_preview", compat_preview["preview_contract_failures"])
        self.assertIn("final_advice_preview", compat_preview["preview_contract_failures"])
        self.assertIn("validated_action_sections_preview", compat_preview["preview_contract_failures"])

    def test_markdown_renders_candidate_and_boundaries(self) -> None:
        audit = build_phase8_audit(self.agent.root, REPORT_DATE, generated_at="2026-05-28T10:00:00+08:00")

        markdown = render_markdown(audit)

        self.assertIn("# Phase 8 Readiness Audit - 2026-05-22", markdown)
        self.assertIn("- promotion_ready: false", markdown)
        self.assertIn("committee_bundle_to_final_advice_adapter", markdown)
        self.assertIn("/api/execution-sync/trade", markdown)
        self.assertIn("shadow allowed", markdown.lower())

    def test_cli_outputs_json(self) -> None:
        completed = self.agent.run_script(
            "audit_phase8_readiness.py",
            "--date",
            REPORT_DATE,
            "--generated-at",
            "2026-05-28T10:00:00+08:00",
        )

        payload = json.loads(completed.stdout)
        self.assertEqual("phase8_readiness_audit.v1", payload["schema_version"])
        self.assertEqual(REPORT_DATE, payload["report_date"])
        self.assertFalse(payload["promotion_ready"])


if __name__ == "__main__":
    unittest.main()
