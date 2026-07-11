from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "app"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from helpers import TempAgentHome
from workbench_state import DesktopSnapshot, WorkbenchStateService


class WorkbenchLearningTrustTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def test_review_surface_exposes_fail_closed_learning_trust(self) -> None:
        self.agent.write_json(
            "config/historical_replay_trust.json",
            {
                "schema_version": "historical_replay_trust.v1",
                "default_mode": "blocked",
                "dates": {
                    "2026-03-10": {
                        "mode": "trusted",
                        "learning_eligible": True,
                        "reason_codes": [],
                    }
                },
                "slices": {},
            },
        )
        self.agent.write_json(
            "db/replay_audits/test.json",
            {
                "date_audits": [
                    {
                        "replay_key": "2026-03-10",
                        "allowed_for_replay": True,
                        "allowed_for_learning": True,
                    }
                ]
            },
        )
        snapshot = DesktopSnapshot(
            home=self.agent.root,
            state={"review_results_for_date": [], "selected_date": "2026-03-10"},
            summary={},
            selected_date="2026-03-10",
            dates=["2026-03-10"],
        )

        review = WorkbenchStateService(self.agent.root).build_review_view_model(snapshot)

        self.assertEqual("trusted", review.trust["mode"])
        self.assertTrue(review.trust["learningEligible"])
        self.assertTrue(review.trust["trustedForLearning"])
        self.assertEqual("db/replay_audits/test.json", review.trust["latestReplayAuditPath"])

    def test_review_surface_defaults_to_blocked_without_manifest(self) -> None:
        snapshot = DesktopSnapshot(
            home=self.agent.root,
            state={"review_results_for_date": [], "selected_date": "2026-03-10"},
            summary={},
            selected_date="2026-03-10",
            dates=["2026-03-10"],
        )

        review = WorkbenchStateService(self.agent.root).build_review_view_model(snapshot)

        self.assertEqual("blocked", review.trust["mode"])
        self.assertFalse(review.trust["learningEligible"])
        self.assertFalse(review.trust["trustedForLearning"])


if __name__ == "__main__":
    unittest.main()
