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

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from action_debate_graph import (
    NODE_SEQUENCE,
    STATE_SIZE_LIMIT_BYTES,
    action_debate_path,
    action_debate_runtime_path,
    run_debate_graph,
)
from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed
from build_action_ticket_shadow import run_builder as run_action_ticket_builder
from build_layered_retrieval_pack import run_builder as run_retrieval_pack_builder
from helpers import TempAgentHome


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_repo_json(relative: str) -> dict:
    return json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))


class ActionDebateGraphTests(unittest.TestCase):
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

    def build_phase2_inputs(self) -> None:
        self.copy_real_inputs()
        run_action_ticket_builder(self.agent.root, REPORT_DATE, generated_at=TICKET_GENERATED_AT)
        run_retrieval_pack_builder(self.agent.root, REPORT_DATE, generated_at=PACK_GENERATED_AT)

    def run_graph(self, *, fail_node: str = "") -> dict:
        self.build_phase2_inputs()
        path, artifact = run_debate_graph(
            self.agent.root,
            REPORT_DATE,
            generated_at=DEBATE_GENERATED_AT,
            fail_node=fail_node,
        )
        self.assertEqual(action_debate_path(self.agent.root, REPORT_DATE), path)
        self.assertTrue(path.exists())
        return artifact

    def test_graph_runs_from_retrieval_pack_and_captures_node_outputs(self) -> None:
        artifact = self.run_graph()
        debates = artifact["debates"]
        first = debates[0]
        node_outputs = first["node_outputs"]

        self.assertEqual("ok", artifact["summary"]["status"])
        self.assertEqual(15, artifact["summary"]["debate_count"])
        self.assertEqual(0, artifact["summary"]["node_failure_count"])
        self.assertTrue(artifact["non_executable"])
        self.assertEqual("shadow_only", artifact["write_scope"])
        self.assertEqual(set(NODE_SEQUENCE), set(artifact["runtime"]["node_status"]))
        self.assertEqual("ok", artifact["runtime"]["node_status"]["ticket_writer"])
        for key in ("analyst_evidence_view", "bull_case", "bear_case", "debate_referee", "action_former"):
            self.assertIn(key, node_outputs)
            self.assertTrue(node_outputs[key])
        self.assertFalse(node_outputs["ticket_writer"]["writes_ticket_file"])
        self.assertEqual("proposed_patch_only", node_outputs["ticket_writer"]["proposed_ticket_patch"]["mutation_mode"])

    def test_node_failure_writes_degraded_artifact_without_official_mutation(self) -> None:
        self.build_phase2_inputs()
        validated_path = self.agent.root / "db" / "validated_advice" / f"{REPORT_DATE}.json"
        portfolio_path = self.agent.root / "db" / "portfolio_state" / "current.json"
        before_validated = _sha256(validated_path)
        before_portfolio = _sha256(portfolio_path)

        _, artifact = run_debate_graph(
            self.agent.root,
            REPORT_DATE,
            generated_at=DEBATE_GENERATED_AT,
            fail_node="bear_case",
        )

        self.assertEqual("degraded", artifact["summary"]["status"])
        self.assertEqual(15, artifact["summary"]["debate_count"])
        self.assertGreater(artifact["summary"]["node_failure_count"], 0)
        self.assertEqual(15, artifact["summary"]["degraded_count"])
        self.assertEqual("degraded", artifact["runtime"]["node_status"]["bear_case"])
        self.assertEqual(before_validated, _sha256(validated_path))
        self.assertEqual(before_portfolio, _sha256(portfolio_path))

    def test_rerun_is_idempotent_for_same_inputs_and_fixed_clock(self) -> None:
        self.build_phase2_inputs()
        _, first = run_debate_graph(self.agent.root, REPORT_DATE, generated_at=DEBATE_GENERATED_AT)
        first_text = json.dumps(first, ensure_ascii=False, sort_keys=True)
        _, second = run_debate_graph(self.agent.root, REPORT_DATE, generated_at=DEBATE_GENERATED_AT)
        second_text = json.dumps(second, ensure_ascii=False, sort_keys=True)
        self.assertEqual(first_text, second_text)

    def test_runtime_state_contains_refs_not_large_pack_sections(self) -> None:
        artifact = self.run_graph()
        runtime_path = action_debate_runtime_path(self.agent.root, REPORT_DATE)
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        serialized = json.dumps(runtime, ensure_ascii=False, sort_keys=True)
        forbidden_keys = (
            "canonical_facts",
            "raw_observation_refs",
            "long_text_evidence",
            "execution_sync",
            "portfolio_state",
        )

        self.assertLess(artifact["summary"]["state_size_bytes"], STATE_SIZE_LIMIT_BYTES)
        self.assertLess(len(serialized.encode("utf-8")), STATE_SIZE_LIMIT_BYTES + 5000)
        self.assertEqual("local_shadow_runtime_json", artifact["runtime"]["checkpoint_backend"])
        for key in forbidden_keys:
            self.assertNotIn(f'"{key}"', serialized)

    def test_shadow_run_does_not_write_official_artifacts(self) -> None:
        self.build_phase2_inputs()
        validated_path = self.agent.root / "db" / "validated_advice" / f"{REPORT_DATE}.json"
        portfolio_path = self.agent.root / "db" / "portfolio_state" / "current.json"
        before_validated = _sha256(validated_path)
        before_portfolio = _sha256(portfolio_path)

        _, artifact = run_debate_graph(self.agent.root, REPORT_DATE, generated_at=DEBATE_GENERATED_AT)

        self.assertTrue(artifact["summary"]["official_output_unchanged"])
        self.assertEqual(before_validated, _sha256(validated_path))
        self.assertEqual(before_portfolio, _sha256(portfolio_path))
        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(validated_path, artifact, self.agent.root)

    def test_missing_retrieval_pack_produces_clear_missing_state(self) -> None:
        self.copy_real_inputs()
        run_action_ticket_builder(self.agent.root, REPORT_DATE, generated_at=TICKET_GENERATED_AT)

        _, artifact = run_debate_graph(self.agent.root, REPORT_DATE, generated_at=DEBATE_GENERATED_AT)

        self.assertEqual("missing_inputs", artifact["summary"]["status"])
        self.assertEqual(0, artifact["summary"]["debate_count"])
        self.assertEqual(1, artifact["summary"]["node_failure_count"])
        self.assertEqual("degraded", artifact["runtime"]["node_status"]["load_retrieval_pack"])
        self.assertTrue(action_debate_runtime_path(self.agent.root, REPORT_DATE).exists())

    def test_cli_runner_works_with_temp_agent_home(self) -> None:
        self.build_phase2_inputs()
        completed = self.agent.run_script(
            "run_action_debate_shadow.py",
            "--date",
            REPORT_DATE,
            "--generated-at",
            DEBATE_GENERATED_AT,
        )
        self.assertIn("wrote 15 action debates", completed.stdout)
        payload = json.loads(action_debate_path(self.agent.root, REPORT_DATE).read_text(encoding="utf-8"))
        self.assertEqual(15, payload["summary"]["debate_count"])


if __name__ == "__main__":
    unittest.main()

