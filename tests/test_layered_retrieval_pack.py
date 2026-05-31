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
GENERATED_AT = "2026-05-22T21:35:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed
from build_action_ticket_shadow import MissingPortfolioStateError
from build_layered_retrieval_pack import build_retrieval_pack_artifact, retrieval_pack_path, run_builder
from layered_context_models import LayeredContextItem, LayeredContextValidationError, RetrievalPackArtifact
from helpers import TempAgentHome


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_repo_json(relative: str) -> dict:
    return json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))


class LayeredRetrievalPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def copy_real_inputs(self) -> None:
        for relative in (
            f"db/validated_advice/{REPORT_DATE}.json",
            "db/portfolio_state/current.json",
            f"db/portfolio_state/snapshots/{REPORT_DATE}.json",
            f"db/llm_context/{REPORT_DATE}.json",
            f"db/evidence_index/{REPORT_DATE}.json",
            "db/long_memory/exports/all_memory.json",
        ):
            self.agent.write_json(relative, _load_repo_json(relative))

    def build_artifact(self):
        self.copy_real_inputs()
        return build_retrieval_pack_artifact(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)

    def test_retrieval_pack_round_trip_is_stable(self) -> None:
        artifact = self.build_artifact()
        payload = artifact.to_dict()
        self.assertEqual(payload, RetrievalPackArtifact.from_dict(payload).to_dict())
        self.assertEqual(15, payload["summary"]["pack_count"])
        self.assertEqual(0, payload["summary"]["no_future_violation_count"])
        self.assertEqual(0, payload["summary"]["canonical_from_rag_count"])
        self.assertEqual(0, payload["summary"]["execution_included_count"])
        self.assertGreaterEqual(payload["summary"]["trace_completeness_rate"], 0.95)

    def test_pack_for_017641_uses_structured_canonical_facts(self) -> None:
        artifact = self.build_artifact()
        pack = next(item for item in artifact.packs if item.target["fund_code"] == "017641")
        canonical_sources = {item.source_kind for item in pack.canonical_facts}
        canonical_ids = {item.item_id for item in pack.canonical_facts}

        self.assertIn("portfolio_state", canonical_sources)
        self.assertIn("action_ticket", canonical_sources)
        self.assertIn("validated_advice", canonical_sources)
        self.assertIn("quote_snapshot", canonical_sources)
        self.assertFalse(any(source.startswith("rag") for source in canonical_sources))
        self.assertIn("fact:portfolio:017641:position", canonical_ids)
        self.assertEqual("scheduled_dca", pack.target["action_verb"])
        self.assertFalse(pack.visibility.include_execution)
        self.assertTrue(any(item.field == f"official_nav_for_{REPORT_DATE}" and item.state == "pending" for item in pack.missing_data))

    def test_no_future_available_from_is_rejected_by_model(self) -> None:
        artifact = self.build_artifact()
        payload = artifact.to_dict()
        payload["packs"][0]["canonical_facts"][0]["available_from"] = "2026-05-23T00:00:00+08:00"
        with self.assertRaises(LayeredContextValidationError):
            RetrievalPackArtifact.from_dict(payload)

    def test_fund_specific_pack_does_not_use_wrong_fund_primary_canonical_fact(self) -> None:
        artifact = self.build_artifact()
        pack = next(item for item in artifact.packs if item.target["fund_code"] == "017641")
        primary_fund_items = [item for item in pack.canonical_facts if item.fund_code]
        self.assertTrue(primary_fund_items)
        self.assertTrue(all(item.fund_code == "017641" for item in primary_fund_items))

    def test_archived_rejected_and_execution_memory_excluded(self) -> None:
        self.copy_real_inputs()
        memory = _load_repo_json("db/long_memory/exports/all_memory.json")
        memory["items"].extend(
            [
                {
                    "memory_id": "mem-archived-test",
                    "memory_type": "portfolio_policy_memory",
                    "domain": "portfolio",
                    "entity_key": "017641_archived",
                    "title": "archived 017641",
                    "text": "archived 017641 should not appear",
                    "status": "archived",
                    "confidence": 0.99,
                    "updated_at": "2026-05-21T10:00:00+08:00",
                    "valid_from": "2026-05-20",
                    "metadata": {"tags": ["017641"]},
                },
                {
                    "memory_id": "mem-rejected-test",
                    "memory_type": "portfolio_policy_memory",
                    "domain": "portfolio",
                    "entity_key": "017641_rejected",
                    "title": "rejected 017641",
                    "text": "rejected 017641 should not appear",
                    "status": "rejected",
                    "confidence": 0.99,
                    "updated_at": "2026-05-21T10:00:00+08:00",
                    "valid_from": "2026-05-20",
                    "metadata": {"tags": ["017641"]},
                },
                {
                    "memory_id": "mem-execution-test",
                    "memory_type": "execution_memory",
                    "domain": "execution",
                    "entity_key": "017641_execution",
                    "title": "execution 017641",
                    "text": "execution-only 017641 should not appear",
                    "status": "permanent",
                    "confidence": 0.99,
                    "updated_at": "2026-05-21T10:00:00+08:00",
                    "valid_from": "2026-05-20",
                    "learning_scope": "execution_only",
                    "metadata": {"tags": ["017641"], "learning_scope": "execution_only"},
                },
            ]
        )
        self.agent.write_json("db/long_memory/exports/all_memory.json", memory)

        artifact = build_retrieval_pack_artifact(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)
        serialized = json.dumps(artifact.to_dict(), ensure_ascii=False)
        self.assertNotIn("mem-archived-test", serialized)
        self.assertNotIn("mem-rejected-test", serialized)
        self.assertNotIn("mem-execution-test", serialized)

    def test_rag_failure_falls_back_to_missing_data_not_exception(self) -> None:
        self.copy_real_inputs()
        artifact = build_retrieval_pack_artifact(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT, use_rag=True)
        self.assertEqual(15, len(artifact.packs))
        self.assertTrue(any(ref.fallback_used for pack in artifact.packs for ref in pack.rag_trace_refs) or artifact.summary["rag_trace_count"] >= 0)

    def test_builder_writes_only_retrieval_pack_artifact_and_keeps_inputs_unchanged(self) -> None:
        self.copy_real_inputs()
        validated_path = self.agent.root / "db" / "validated_advice" / f"{REPORT_DATE}.json"
        portfolio_path = self.agent.root / "db" / "portfolio_state" / "current.json"
        before_validated = _sha256(validated_path)
        before_portfolio = _sha256(portfolio_path)

        path, artifact = run_builder(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)

        self.assertEqual(retrieval_pack_path(self.agent.root, REPORT_DATE), path)
        self.assertTrue(path.exists())
        self.assertEqual(15, artifact.summary["pack_count"])
        self.assertEqual(before_validated, _sha256(validated_path))
        self.assertEqual(before_portfolio, _sha256(portfolio_path))

    def test_historical_build_uses_snapshot_portfolio_source(self) -> None:
        self.copy_real_inputs()
        future_current = _load_repo_json("db/portfolio_state/current.json")
        future_current["as_of_date"] = "2026-05-27"
        future_current["funds"] = []
        self.agent.write_json("db/portfolio_state/current.json", future_current)

        artifact = build_retrieval_pack_artifact(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)
        payload = artifact.to_dict()
        portfolio_source = next(item for item in payload["source_artifacts"] if item["kind"] == "portfolio_state")
        pack = next(item for item in artifact.packs if item.target["fund_code"] == "017641")
        portfolio_facts = [item for item in pack.canonical_facts if item.source_kind == "portfolio_state"]

        self.assertEqual(f"db/portfolio_state/snapshots/{REPORT_DATE}.json", portfolio_source["path"])
        self.assertTrue(portfolio_facts)
        self.assertTrue(all(item.source_path == f"db/portfolio_state/snapshots/{REPORT_DATE}.json" for item in portfolio_facts))

    def test_historical_build_fails_when_snapshot_missing_and_current_is_future(self) -> None:
        self.copy_real_inputs()
        build_retrieval_pack_artifact(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)
        (self.agent.root / "db" / "portfolio_state" / "snapshots" / f"{REPORT_DATE}.json").unlink()
        future_current = _load_repo_json("db/portfolio_state/current.json")
        future_current["as_of_date"] = "2026-05-27"
        self.agent.write_json("db/portfolio_state/current.json", future_current)

        with self.assertRaises(MissingPortfolioStateError) as caught:
            build_retrieval_pack_artifact(self.agent.root, REPORT_DATE, generated_at=GENERATED_AT)

        message = str(caught.exception)
        self.assertIn("portfolio_state snapshot missing", message)
        self.assertIn("current.as_of_date=2026-05-27", message)

    def test_boundary_rejects_retrieval_pack_payload_on_official_path(self) -> None:
        artifact = self.build_artifact()
        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(
                self.agent.root / "db" / "validated_advice" / f"{REPORT_DATE}.json",
                artifact.to_dict(),
                self.agent.root,
            )

    def test_layered_item_requires_trace_fields(self) -> None:
        with self.assertRaises(LayeredContextValidationError):
            LayeredContextItem(
                item_id="bad",
                layer="canonical_fact",
                source_kind="portfolio_state",
                source_path="",
                source_record_id="fund:bad",
                as_of_date=REPORT_DATE,
                available_from=GENERATED_AT,
                status="present",
                summary="missing source path",
            )


if __name__ == "__main__":
    unittest.main()
