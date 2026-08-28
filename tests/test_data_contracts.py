from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))

from data_contracts import build_data_context, normalize_evidence_refs  # noqa: E402
from simulation_tracks import build_simulation_payload, simulation_fields, user_simulation_fields  # noqa: E402


class DataContractTests(unittest.TestCase):
    def test_closed_market_proxy_snapshot_is_not_reported_as_live(self):
        context = build_data_context(
            selected_date="2026-08-27",
            portfolio={"as_of_date": "2026-08-27"},
            realtime={
                "report_date": "2026-08-27",
                "generated_at": "2026-08-27T21:30:00+08:00",
                "realtime_policy": {"provider": "fund_estimate_proxy"},
                "items": [
                    {
                        "mode": "proxy_fallback",
                        "effective_change_pct": 1.2,
                        "estimate_change_pct": 1.1,
                        "proxy_change_pct": 1.2,
                        "stale": True,
                        "freshness_age_business_days": 0,
                        "confidence": 0.38,
                    }
                ],
            },
        )
        self.assertEqual("market_closed", context["sessionStatus"])
        self.assertEqual("official_nav_pending", context["freshnessStatus"])
        self.assertIn("官方净值", context["freshnessReason"])
        self.assertEqual("fund_estimate_proxy", context["sourceKey"])
        self.assertEqual("portfolio", context["subjectId"])
        self.assertEqual("2026-08-27", context["asOfDate"])

    def test_conflicting_realtime_observations_are_explicit(self):
        context = build_data_context(
            selected_date="2026-08-27",
            portfolio={},
            realtime={
                "report_date": "2026-08-27",
                "generated_at": "2026-08-27T11:00:00+08:00",
                "items": [
                    {
                        "mode": "proxy_primary",
                        "estimate_change_pct": 2.2,
                        "proxy_change_pct": -0.4,
                        "stale": False,
                    }
                ],
            },
        )
        self.assertEqual("conflict", context["freshnessStatus"])
        self.assertEqual(1, context["conflictItemCount"])

    def test_closed_market_snapshot_never_claims_latest(self):
        context = build_data_context(
            selected_date="2026-08-27",
            portfolio={},
            realtime={
                "report_date": "2026-08-27",
                "generated_at": "2026-08-27T21:00:00+08:00",
                "items": [{"mode": "official_nav", "effective_change_pct": 0.2, "stale": False}],
            },
        )
        self.assertEqual("market_closed", context["freshnessStatus"])

    def test_evidence_references_are_stable_and_preserve_time_fields(self):
        source = {
            "news_id": "news-1",
            "source_kind": "regulatory_notice",
            "source_path": "raw/news/2026-08-27.json",
            "fund_codes": ["017641"],
            "published_at": "2026-08-27T10:00:00+08:00",
            "retrieved_at": "2026-08-27T10:02:00+08:00",
            "source_tier": "official_policy",
            "confidence": 0.9,
            "matched_keywords": ["基金"],
        }
        refs = normalize_evidence_refs([source, dict(source)])
        self.assertEqual(1, len(refs))
        reference = refs[0]
        self.assertEqual("news-1", reference["sourceRecordId"])
        self.assertEqual("official_policy", reference["authority"])
        self.assertEqual(["017641"], reference["fundCodes"])
        self.assertTrue(reference["payloadHash"])

    def test_simulation_tracks_stay_separate_from_user_holdings(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "db" / "execution_sync" / "actual_trades").mkdir(parents=True)
            (home / "db" / "strategy_simulation" / "experiments").mkdir(parents=True)
            (home / "db" / "execution_sync" / "actual_trades" / "2026-08-27.json").write_text(
                json.dumps({"items": [{"trade_id": "trade-1", "status": "submitted"}]}), encoding="utf-8"
            )
            (home / "db" / "strategy_simulation" / "experiments" / "mean-revert.json").write_text(
                json.dumps({"experiment_id": "mean-revert", "label": "均值回归", "status": "active"}), encoding="utf-8"
            )
            payload = build_simulation_payload(home, portfolio={"as_of_date": "2026-08-27", "funds": [{"fund_code": "017641"}]})
        self.assertTrue(payload["simulationOnly"])
        self.assertEqual("user_simulation", payload["formalTrack"])
        self.assertTrue(payload["userSimulation"]["affectsFormalPortfolio"])
        self.assertFalse(payload["strategySimulation"]["affectsFormalPortfolio"])
        self.assertEqual(1, payload["strategySimulation"]["experimentCount"])
        self.assertEqual(1, payload["userSimulation"]["operationCounts"]["planned"])

    def test_simulation_fields_reject_non_simulation_statuses(self):
        normalized = simulation_fields({"status": "submitted"})
        self.assertEqual("user_simulation", normalized["simulation_track"])
        self.assertEqual("planned", normalized["simulation_status"])
        self.assertFalse(normalized["is_simulation"])
        self.assertTrue(simulation_fields({"simulation_track": "user_simulation"})["is_simulation"])
        with self.assertRaisesRegex(ValueError, "Unsupported simulation status"):
            simulation_fields({"simulation_status": "filled"})

    def test_desktop_user_simulation_defaults_legacy_status_to_simulation(self):
        planned = user_simulation_fields({"status": "submitted"})
        confirmed = user_simulation_fields({"status": "settled"})
        self.assertTrue(planned["is_simulation"])
        self.assertEqual("planned", planned["simulation_status"])
        self.assertEqual("confirmed", confirmed["simulation_status"])
        with self.assertRaisesRegex(ValueError, "user_simulation"):
            user_simulation_fields({"simulation_track": "strategy_simulation"})


if __name__ == "__main__":
    unittest.main()
