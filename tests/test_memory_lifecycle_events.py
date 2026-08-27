from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.web_api import OkraWebApi  # noqa: E402
from helpers import TempAgentHome  # noqa: E402
from long_memory_store import approve_memory, list_memory_events, upsert_memory_record  # noqa: E402


class MemoryLifecycleEventTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_experiment_lifecycle_is_recorded_without_formal_influence(self):
        record = upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "experiment-memory",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "mean_revert",
                "title": "Mean revert experiment",
                "text": "Experiment-only rule.",
                "status": "experimental_active",
                "source": "replay_experiment",
                "metadata": {"experimentId": "exp-1", "sourceSnapshotHash": "snapshot-1"},
            },
        )

        events = list_memory_events(self.agent.root, memory_id="experiment-memory")

        self.assertEqual("experimental_active", record["status"])
        self.assertEqual("strategy_simulation", record["metadata"]["sourceTrack"])
        self.assertFalse(record["metadata"]["formalInfluence"])
        self.assertEqual("experimental_active", record["metadata"]["promotionLevel"])
        self.assertEqual("created", events[0]["eventType"])
        self.assertEqual("strategy_simulation", events[0]["sourceTrack"])
        self.assertEqual("exp-1", events[0]["experimentId"])

    def test_approval_and_supersession_emit_auditable_events(self):
        old = upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "old-rule",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "cash_floor",
                "title": "Old cash floor",
                "text": "Keep cash.",
                "status": "strategic",
            },
        )
        approve_memory(self.agent.root, old["memory_id"], action="approve", note="initial confirmation")
        newer = upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "new-rule",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "cash_floor",
                "title": "New cash floor",
                "text": "Keep a larger cash floor.",
                "status": "strategic",
            },
        )
        approved = approve_memory(self.agent.root, newer["memory_id"], action="approve", note="replace prior rule")

        old_events = list_memory_events(self.agent.root, memory_id="old-rule")
        new_events = list_memory_events(self.agent.root, memory_id="new-rule")

        self.assertEqual("permanent", approved["status"])
        self.assertEqual("permanent", approved["metadata"]["promotionLevel"])
        self.assertTrue(any(event["eventType"] == "superseded" and event["toStatus"] == "archived" for event in old_events))
        self.assertTrue(any(event["eventType"] == "approval" and event["toStatus"] == "permanent" for event in new_events))

    def test_unapproved_permanent_input_is_downgraded_in_both_status_and_metadata(self):
        record = upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "unapproved-permanent",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "cash_floor",
                "title": "Unapproved cash floor",
                "text": "Needs a user approval.",
                "status": "permanent",
            },
        )

        self.assertEqual("strategic", record["status"])
        self.assertEqual("strategic", record["metadata"]["promotionLevel"])

    def test_review_payload_exposes_lifecycle_as_additive_read_only_data(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "review-memory",
                "memory_type": "execution_memory",
                "domain": "execution",
                "entity_key": "lag",
                "title": "Execution lag",
                "text": "Wait for confirmation.",
                "status": "candidate",
            },
        )

        page = OkraWebApi(self.agent.root).review_page("2026-05-20")
        lifecycle = page["longMemory"]["lifecycle"]

        self.assertEqual(1, lifecycle["statusCounts"]["candidate"])
        self.assertTrue(page["longMemory"]["recentEvents"])
        self.assertIn("review", page)

    def test_review_payload_marks_expired_memory_without_mutating_its_status(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "expired-memory",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "window",
                "title": "Expired window",
                "text": "Expired rule.",
                "status": "strategic",
                "valid_until": "2026-05-10",
            },
        )

        page = OkraWebApi(self.agent.root).review_page("2026-05-20")
        record = next(item for item in page["longMemory"]["records"] if item["memory_id"] == "expired-memory")

        self.assertEqual("strategic", record["status"])
        self.assertTrue(record["isExpired"])
        self.assertEqual("expired", record["effectiveStatus"])


if __name__ == "__main__":
    unittest.main()
