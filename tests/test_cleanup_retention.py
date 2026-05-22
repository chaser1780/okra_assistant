from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cleanup_retention import apply_retention_plan, build_retention_plan, load_plan_snapshot, render_markdown_report, write_plan_snapshot
from helpers import TempAgentHome


class CleanupRetentionTests(unittest.TestCase):
    def test_raw_news_archives_only_when_context_exists(self):
        agent = TempAgentHome()
        try:
            agent.write_json("raw/news/2026-01-01.json", {"items": [{"title": "old with context"}]})
            agent.write_json("raw/news/2026-01-02.json", {"items": [{"title": "old without context"}]})
            agent.write_json("db/llm_context/2026-01-01.json", {"news_digest": {}})
            config = {
                "archive_root": "backups/retention",
                "protected_paths": [],
                "rules": [
                    {
                        "name": "raw_news",
                        "enabled": True,
                        "path": "raw/news",
                        "selector": "dated_files",
                        "pattern": "*.json",
                        "retention_days": 60,
                        "action": "archive",
                        "require_existing": "db/llm_context/{date}.json",
                    }
                ],
            }

            plan = build_retention_plan(agent.root, config, as_of=date(2026, 5, 15), dry_run=True)

            paths = {item.path for item in plan.items}
            self.assertIn("raw/news/2026-01-01.json", paths)
            self.assertNotIn("raw/news/2026-01-02.json", paths)
            self.assertEqual([], plan.protected_violations)
        finally:
            agent.cleanup()

    def test_protected_paths_are_reported_and_not_planned(self):
        agent = TempAgentHome()
        try:
            protected = agent.write_json("db/long_memory/exports/2026-01-01.json", {"items": []})
            old_time = datetime(2026, 1, 1).timestamp()
            os.utime(protected, (old_time, old_time))
            config = {
                "archive_root": "backups/retention",
                "protected_paths": ["db/long_memory"],
                "rules": [
                    {
                        "name": "bad_rule",
                        "enabled": True,
                        "path": "db/long_memory",
                        "selector": "mtime_files",
                        "pattern": "*",
                        "retention_days": 0,
                        "action": "delete",
                    }
                ],
            }

            plan = build_retention_plan(agent.root, config, as_of=date(2026, 5, 15), dry_run=True)

            self.assertEqual([], plan.items)
            self.assertEqual(1, len(plan.protected_violations))
            self.assertEqual("protected_path", plan.protected_violations[0]["reason"])
        finally:
            agent.cleanup()

    def test_temp_rule_preserves_latest_ui_screenshots(self):
        agent = TempAgentHome()
        try:
            newest = agent.write_text("temp/ui-check-new.png", "new")
            oldest = agent.write_text("temp/ui-check-old.png", "old")
            stale = agent.write_text("temp/runtime.tmp", "tmp")
            os.utime(newest, (datetime(2026, 5, 10).timestamp(), datetime(2026, 5, 10).timestamp()))
            os.utime(oldest, (datetime(2026, 1, 1).timestamp(), datetime(2026, 1, 1).timestamp()))
            os.utime(stale, (datetime(2026, 1, 1).timestamp(), datetime(2026, 1, 1).timestamp()))
            config = {
                "archive_root": "backups/retention",
                "protected_paths": [],
                "rules": [
                    {
                        "name": "temp",
                        "enabled": True,
                        "path": "temp",
                        "selector": "mtime_files",
                        "pattern": "*",
                        "retention_days": 7,
                        "action": "delete",
                        "preserve_latest_count": 1,
                        "preserve_latest_patterns": ["*.png"],
                    }
                ],
            }

            plan = build_retention_plan(agent.root, config, as_of=date(2026, 5, 15), dry_run=True)

            paths = {item.path for item in plan.items}
            self.assertNotIn("temp/ui-check-new.png", paths)
            self.assertIn("temp/ui-check-old.png", paths)
            self.assertIn("temp/runtime.tmp", paths)
        finally:
            agent.cleanup()

    def test_markdown_report_is_reviewable_by_humans(self):
        agent = TempAgentHome()
        try:
            agent.write_json("raw/news/2026-01-01.json", {"items": [{"title": "old with context"}]})
            agent.write_json("db/llm_context/2026-01-01.json", {"news_digest": {}})
            config = {
                "archive_root": "backups/retention",
                "protected_paths": ["db/long_memory", "db/execution_sync"],
                "rules": [
                    {
                        "name": "raw_news",
                        "enabled": True,
                        "path": "raw/news",
                        "selector": "dated_files",
                        "pattern": "*.json",
                        "retention_days": 60,
                        "action": "archive",
                        "require_existing": "db/llm_context/{date}.json",
                    }
                ],
            }
            plan = build_retention_plan(agent.root, config, as_of=date(2026, 5, 15), dry_run=True)

            report = render_markdown_report(plan, config, limit=5, plan_path="reports/maintenance/retention_latest.plan.json")

            self.assertIn("# OKRA Retention Review", report)
            self.assertIn("| `raw_news` | 1 |", report)
            self.assertIn("`db/long_memory`", report)
            self.assertIn("Human Checklist", report)
            self.assertIn("--apply-plan", report)
            self.assertIn("raw/news/2026-01-01.json", report)
        finally:
            agent.cleanup()

    def test_reviewed_plan_snapshot_can_be_loaded_and_applied(self):
        agent = TempAgentHome()
        try:
            stale = agent.write_text("temp/stale.tmp", "old")
            os.utime(stale, (datetime(2026, 1, 1).timestamp(), datetime(2026, 1, 1).timestamp()))
            config = {
                "archive_root": "backups/retention",
                "protected_paths": [],
                "rules": [
                    {
                        "name": "temp",
                        "enabled": True,
                        "path": "temp",
                        "selector": "mtime_files",
                        "pattern": "*.tmp",
                        "retention_days": 7,
                        "action": "delete",
                    }
                ],
            }
            plan = build_retention_plan(agent.root, config, as_of=date(2026, 5, 15), dry_run=True)
            snapshot = write_plan_snapshot(agent.root, plan, "reports/maintenance/test.plan.json")

            reviewed = load_plan_snapshot(agent.root, snapshot)
            apply_retention_plan(agent.root, reviewed)

            self.assertFalse(stale.exists())
        finally:
            agent.cleanup()

    def test_apply_refuses_stale_plan_when_file_size_changes(self):
        agent = TempAgentHome()
        try:
            stale = agent.write_text("temp/stale.tmp", "old")
            os.utime(stale, (datetime(2026, 1, 1).timestamp(), datetime(2026, 1, 1).timestamp()))
            config = {
                "archive_root": "backups/retention",
                "protected_paths": [],
                "rules": [
                    {
                        "name": "temp",
                        "enabled": True,
                        "path": "temp",
                        "selector": "mtime_files",
                        "pattern": "*.tmp",
                        "retention_days": 7,
                        "action": "delete",
                    }
                ],
            }
            plan = build_retention_plan(agent.root, config, as_of=date(2026, 5, 15), dry_run=True)
            stale.write_text("changed", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "stale retention item"):
                apply_retention_plan(agent.root, plan)
            self.assertTrue(stale.exists())
        finally:
            agent.cleanup()


if __name__ == "__main__":
    unittest.main()
