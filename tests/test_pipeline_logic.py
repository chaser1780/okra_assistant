from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_daily_pipeline import add_business_days, due_review_jobs
from run_realtime_monitor import should_sync_units
from run_report_window import intraday_report_target
from helpers import TempAgentHome
from ui_support import latest_nightly_target_date, pending_nightly_catchup_dates, should_autorun_intraday_on_boot, should_refresh_realtime_on_boot


class PipelineLogicTests(unittest.TestCase):
    def test_add_business_days_skips_weekend(self):
        self.assertEqual(add_business_days("2026-03-06", 1), "2026-03-09")
        self.assertEqual(add_business_days("2026-03-06", 5), "2026-03-13")

    def test_due_review_jobs_finds_matching_horizon(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "db" / "validated_advice").mkdir(parents=True, exist_ok=True)
            (root / "config" / "review.toml").write_text(
                "[review]\nenabled = true\nhorizons = [1, 5, 20]\ncompare_against = 'validated_advice'\n",
                encoding="utf-8",
            )
            for date_text in ("2026-03-10", "2026-03-06"):
                (root / "db" / "validated_advice" / f"{date_text}.json").write_text(
                    json.dumps({"report_date": date_text}, ensure_ascii=False),
                    encoding="utf-8",
                )

            jobs = due_review_jobs(root, "2026-03-11")
            labels = {(item["base_date"], item["horizon"]) for item in jobs}
            self.assertIn(("2026-03-10", 1), labels)
            self.assertNotIn(("2026-03-06", 5), labels)

    def test_intraday_report_target_follows_report_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "reports" / "daily").mkdir(parents=True, exist_ok=True)
            strategy = {"schedule": {"report_mode": "daily_report"}}
            target = intraday_report_target(root, strategy, "2026-03-10")
            self.assertEqual(target.name, "2026-03-10.md")

            strategy = {"schedule": {"report_mode": "intraday_proxy"}}
            target = intraday_report_target(root, strategy, "2026-03-10")
            self.assertEqual(target.name, "2026-03-10_portfolio.md")

    def test_should_sync_units_only_when_official_nav_state_changes(self):
        agent = TempAgentHome()
        try:
            agent.write_json(
                "config/portfolio.json",
                {
                    "portfolio_name": "测试组合",
                    "as_of_date": "2026-03-10",
                    "funds": [
                        {
                            "fund_code": "EQ1",
                            "fund_name": "权益基金",
                            "role": "tactical",
                            "current_value": 500.0,
                            "holding_units": 250.0,
                            "last_valuation_nav": 2.0,
                            "last_valuation_date": "2026-03-10",
                            "units_source": "derived_from_official_nav",
                        }
                    ],
                },
            )
            agent.write_json("raw/quotes/2026-03-11.json", {"funds": [{"code": "EQ1", "nav": 2.0, "as_of_date": "2026-03-10"}]})
            agent.write_json("db/estimated_nav/2026-03-11.json", {"items": [{"fund_code": "EQ1", "official_nav": 2.0, "official_nav_date": "2026-03-10"}]})
            self.assertFalse(should_sync_units(agent.root, "2026-03-11"))

            agent.write_json("db/estimated_nav/2026-03-11.json", {"items": [{"fund_code": "EQ1", "official_nav": 2.1, "official_nav_date": "2026-03-11"}]})
            self.assertTrue(should_sync_units(agent.root, "2026-03-11"))
        finally:
            agent.cleanup()

    def test_pending_nightly_catchup_dates_respects_schedule_and_business_days(self):
        agent = TempAgentHome()
        try:
            now = __import__("datetime").datetime(2026, 4, 21, 10, 0, 0)
            target = latest_nightly_target_date(agent.root, now=now)
            self.assertEqual(target, "2026-04-20")
            dates = pending_nightly_catchup_dates(agent.root, "2026-04-16", now=now)
            self.assertEqual(dates, ["2026-04-17", "2026-04-20"])
        finally:
            agent.cleanup()

    def test_startup_autorun_intraday_and_realtime_decisions(self):
        agent = TempAgentHome()
        try:
            now = __import__("datetime").datetime(2026, 4, 21, 15, 0, 0)
            self.assertTrue(should_autorun_intraday_on_boot(agent.root, "2026-04-21", now=now))
            self.assertTrue(should_refresh_realtime_on_boot(agent.root, "2026-04-21", now=now))

            agent.write_json("db/validated_advice/2026-04-21.json", {"report_date": "2026-04-21"})
            self.assertFalse(should_autorun_intraday_on_boot(agent.root, "2026-04-21", now=now))

            agent.write_json("db/realtime_monitor/2026-04-21.json", {"report_date": "2026-04-21"})
            snapshot = agent.root / "db" / "realtime_monitor" / "2026-04-21.json"
            import os, time
            fresh_ts = now.timestamp()
            os.utime(snapshot, (fresh_ts, fresh_ts))
            self.assertFalse(should_refresh_realtime_on_boot(agent.root, "2026-04-21", now=now))
        finally:
            agent.cleanup()


if __name__ == "__main__":
    unittest.main()
