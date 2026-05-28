from __future__ import annotations

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
REVIEW_GENERATED_AT = "2026-05-22T21:45:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from action_debate_graph import run_debate_graph
from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed
from build_action_ticket_shadow import run_builder as run_action_ticket_builder
from build_layered_retrieval_pack import run_builder as run_retrieval_pack_builder
from helpers import TempAgentHome
from render_refactor_review import refactor_review_path, review_payload, run_renderer


def _load_repo_json(relative: str) -> dict:
    return json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))


class RefactorReviewMarkdownTests(unittest.TestCase):
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

    def build_ready_artifacts(self) -> None:
        self.copy_real_inputs()
        run_action_ticket_builder(self.agent.root, REPORT_DATE, generated_at=TICKET_GENERATED_AT)
        run_retrieval_pack_builder(self.agent.root, REPORT_DATE, generated_at=PACK_GENERATED_AT)
        run_debate_graph(self.agent.root, REPORT_DATE, generated_at=DEBATE_GENERATED_AT)

    def test_ready_review_markdown_chains_shadow_artifacts(self) -> None:
        self.build_ready_artifacts()

        path, markdown = run_renderer(self.agent.root, REPORT_DATE, generated_at=REVIEW_GENERATED_AT)

        self.assertEqual(refactor_review_path(self.agent.root, REPORT_DATE), path)
        self.assertTrue(path.exists())
        self.assertIn("- status: ready", markdown)
        self.assertIn("- display_only: true", markdown)
        self.assertIn("- non_executable: true", markdown)
        self.assertIn("validated_advice -> action_ticket -> retrieval_pack -> action_debate", markdown)
        self.assertIn("017641", markdown)
        self.assertIn("scheduled_dca", markdown)
        self.assertIn("writes_ticket_file=false", markdown)
        self.assertIn("## Guardrail Map", markdown)
        self.assertIn("trace=1", markdown)
        self.assertIn("- compared_fund_count: 15", markdown)
        self.assertIn("- mismatched_action_count:", markdown)

    def test_partial_review_renders_missing_shadow_artifacts_without_exception(self) -> None:
        self.agent.write_json(f"db/validated_advice/{REPORT_DATE}.json", _load_repo_json(f"db/validated_advice/{REPORT_DATE}.json"))

        path, markdown = run_renderer(self.agent.root, REPORT_DATE, generated_at=REVIEW_GENERATED_AT)

        self.assertTrue(path.exists())
        self.assertIn("- status: partial", markdown)
        self.assertIn("| action_tickets | db/action_tickets/2026-05-22.json | not_run | missing artifact |", markdown)
        self.assertIn("| retrieval_packs | db/retrieval_packs/2026-05-22.json | not_run | missing artifact |", markdown)
        self.assertIn("| action_debates | db/action_debates/2026-05-22.json | not_run | missing artifact |", markdown)
        self.assertIn("- action_tickets: not_run (missing artifact)", markdown)

    def test_invalid_json_artifact_renders_failed_state_without_exception(self) -> None:
        self.agent.write_json(f"db/validated_advice/{REPORT_DATE}.json", _load_repo_json(f"db/validated_advice/{REPORT_DATE}.json"))
        self.agent.write_text(f"db/action_tickets/{REPORT_DATE}.json", "{bad json")

        path, markdown = run_renderer(self.agent.root, REPORT_DATE, generated_at=REVIEW_GENERATED_AT)

        self.assertTrue(path.exists())
        self.assertIn("- status: failed", markdown)
        self.assertIn("| action_tickets | db/action_tickets/2026-05-22.json | failed | invalid artifact:", markdown)

    def test_boundary_rejects_review_payload_on_official_path(self) -> None:
        payload = review_payload(REPORT_DATE, REVIEW_GENERATED_AT)

        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(
                self.agent.root / "db" / "validated_advice" / f"{REPORT_DATE}.md",
                payload,
                self.agent.root,
            )

    def test_cli_renderer_works_with_temp_agent_home(self) -> None:
        self.build_ready_artifacts()

        completed = self.agent.run_script(
            "render_refactor_review.py",
            "--date",
            REPORT_DATE,
            "--generated-at",
            REVIEW_GENERATED_AT,
        )

        self.assertIn("wrote refactor review (ready)", completed.stdout)
        self.assertTrue(refactor_review_path(self.agent.root, REPORT_DATE).exists())


if __name__ == "__main__":
    unittest.main()
