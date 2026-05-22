from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from long_memory_store import approve_memory, build_execution_memory, build_fund_memory, list_memory_records, search_long_memory, stable_memory_id, upsert_memory_record
from learning_memory import run_learning_sync
import run_today_analysis as run_today_module
from run_today_analysis import _pending_backfill_dates, run_pending_backfills, run_today_analysis, should_run_pending_backfills
from today_orchestrator import AlreadyRunningError, get_active_runtime
from run_long_memory_analysis import run_memory_cycle


class LongMemoryTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_fund_memory_uses_system_advice_reviews_not_trade_execution(self):
        self.agent.write_json(
            "db/review_results/2026-03-10_T1.json",
            {
                "source": "advice",
                "base_date": "2026-03-10",
                "review_date": "2026-03-11",
                "horizon": 1,
                "items": [
                    {
                        "fund_code": "F1",
                        "fund_name": "Advice Fund",
                        "source_action": "add",
                        "source_amount": 200.0,
                        "outcome": "adverse",
                        "diagnostic_label": "signal_failure",
                    }
                ],
            },
        )
        self.agent.write_json(
            "db/execution_reviews/2026-03-10_execution_T1.json",
            {
                "source": "execution",
                "base_date": "2026-03-10",
                "review_date": "2026-03-11",
                "horizon": 1,
                "items": [
                    {
                        "fund_code": "F1",
                        "fund_name": "Advice Fund",
                        "source_action": "reduce",
                        "outcome": "supportive",
                        "diagnostic_label": "good_risk_reduction",
                    }
                ],
            },
        )
        payload = build_fund_memory(self.agent.root)
        record = payload["items"][0]
        self.assertEqual(record["entity_key"], "F1")
        self.assertEqual(record["support_count"], 0)
        self.assertEqual(record["contradiction_count"], 1)
        self.assertEqual(record["metadata"]["by_action"]["add"]["failure"], 1)
        self.assertNotIn("reduce", [key for key, value in record["metadata"]["by_action"].items() if value["count"]])

    def test_permanent_memory_requires_explicit_approval(self):
        memory_id = stable_memory_id("portfolio", "rule_a", "Rule A", "portfolio_policy_memory")
        record = upsert_memory_record(
            self.agent.root,
            {
                "memory_id": memory_id,
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "rule_a",
                "title": "Rule A",
                "text": "A candidate rule.",
                "status": "permanent",
                "confidence": 0.9,
            },
        )
        self.assertEqual(record["status"], "strategic")
        approved = approve_memory(self.agent.root, memory_id, action="approve", note="looks right")
        self.assertEqual(approved["status"], "permanent")
        records = list_memory_records(self.agent.root, status="permanent")
        self.assertEqual(records[0]["memory_id"], memory_id)

    def test_fund_profile_cannot_be_approved_as_permanent_rule(self):
        memory_id = stable_memory_id("fund", "F1", "F1 profile", "fund_profile_memory")
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": memory_id,
                "memory_type": "fund_profile_memory",
                "domain": "fund",
                "entity_key": "F1",
                "title": "F1 profile",
                "text": "F1 advice profile should remain fund learning.",
                "status": "strategic",
                "confidence": 0.8,
            },
        )
        with self.assertRaises(ValueError):
            approve_memory(self.agent.root, memory_id, action="approve", note="not a reusable policy")
        records = list_memory_records(self.agent.root, domain="fund")
        self.assertEqual(records[0]["status"], "strategic")
        self.assertFalse(records[0]["can_promote_permanent"])

    def test_execution_memory_is_separate_from_fund_accuracy(self):
        self.agent.write_json(
            "db/execution_reviews/2026-03-10_execution_T1.json",
            {
                "source": "execution",
                "base_date": "2026-03-10",
                "review_date": "2026-03-11",
                "horizon": 1,
                "items": [
                    {
                        "fund_code": "QDII1",
                        "fund_name": "QDII Fund",
                        "source_action": "add",
                        "outcome": "adverse",
                        "diagnostic_label": "timing_drag",
                        "purchase_confirm_days": 2,
                    }
                ],
            },
        )
        payload = build_execution_memory(self.agent.root)
        self.assertEqual(payload["items"][0]["domain"], "execution")
        self.assertIn("confirmation", payload["items"][0]["entity_key"])
        fund_payload = build_fund_memory(self.agent.root)
        self.assertEqual(fund_payload["items"], [])

    def test_execution_review_does_not_promote_advice_learning_ledger(self):
        review_batches = [
            {
                "source": "execution",
                "base_date": "2026-03-10",
                "review_date": "2026-03-11",
                "horizon": 1,
                "summary": {"supportive": 0, "adverse": 1, "missed_upside": 0, "unknown": 0},
                "diagnostic_summary": {"timing_drag": 2},
            }
        ]

        _summary, ledger, _memory = run_learning_sync(self.agent.root, "2026-03-11", review_batches)

        self.assertEqual(ledger["summary"]["strategic"], 0)
        self.assertEqual(ledger["summary"]["permanent"], 0)
        self.assertEqual(ledger["summary"]["core_permanent"], 0)

    def test_search_long_memory_uses_local_fts(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_type": "execution_memory",
                "domain": "execution",
                "entity_key": "qdii_confirmation_lag_check",
                "title": "QDII confirmation lag",
                "text": "Check QDII confirmation lag before scheduled buys.",
                "status": "strategic",
                "confidence": 0.8,
            },
        )
        hits = search_long_memory(self.agent.root, "QDII confirmation", limit=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["domain"], "execution")

    def test_daily_first_open_demo_writes_workspace(self):
        self.agent.write_json(
            "raw/quotes/2026-05-04.json",
            {"provider": "demo", "funds": []},
        )
        result = self.agent.run_script("run_daily_first_open.py", "--date", "2026-05-04", "--demo", "--force")
        output_path = Path(result.stdout.strip().splitlines()[-1])
        self.assertTrue(output_path.exists())
        workspace = self.agent.root / "db" / "daily_workspace" / "2026-05-04"
        self.assertTrue((workspace / "memory_updates.json").exists())
        self.assertTrue((workspace / "daily_brief.md").exists())

    def test_today_analysis_marks_pre_close_as_not_memory_eligible(self):
        self.agent.write_json("raw/quotes/2026-05-06.json", {"provider": "demo", "funds": []})
        run_today_analysis(
            self.agent.root,
            "2026-05-06",
            trigger="manual",
            demo=True,
            force=True,
            llm_mock=True,
            started_at=datetime(2026, 5, 6, 14, 59),
        )
        meta = json.loads((self.agent.root / "db" / "daily_workspace" / "2026-05-06" / "today_analysis_meta.json").read_text(encoding="utf-8"))
        cycle = json.loads((self.agent.root / "db" / "daily_workspace" / "2026-05-06" / "memory_cycle.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["analysis_quality"], "pre_close")
        self.assertFalse(meta["memory_eligible"])
        self.assertEqual(cycle["status"], "skipped")

    def test_today_analysis_after_close_runs_memory_cycle(self):
        report_date = "2026-05-06"
        self.agent.write_json(
            f"db/llm_context/{report_date}.json",
            {
                "analysis_date": report_date,
                "portfolio_summary": {"portfolio_name": "Test"},
                "constraints": {},
                "memory_digest": {},
                "funds": [],
            },
        )
        self.agent.write_json(
            f"db/validated_advice/{report_date}.json",
            {
                "report_date": report_date,
                "market_view": {"summary": "after close"},
                "cross_fund_observations": ["obs"],
                "tactical_actions": [],
                "dca_actions": [],
                "hold_actions": [],
            },
        )
        self.agent.write_json(f"db/committee_advice/{report_date}.json", {"market_view": {"summary": "committee"}, "fund_decisions": []})
        self.agent.write_json(f"db/llm_raw/{report_date}.json", {"mode": "mock"})
        self.agent.write_json(f"db/agent_outputs/{report_date}/aggregate.json", {"committee": {}, "failed_agents": [], "degraded_ok": False})
        self.agent.write_json(f"db/decisions/{report_date}.json", {"decisions": []})
        (self.agent.root / "reports" / "daily" / f"{report_date}.md").write_text("report", encoding="utf-8")
        run_today_analysis(
            self.agent.root,
            report_date,
            trigger="manual",
            demo=True,
            force=True,
            llm_mock=True,
            started_at=datetime(2026, 5, 6, 15, 1),
        )
        meta = json.loads((self.agent.root / "db" / "daily_workspace" / report_date / "today_analysis_meta.json").read_text(encoding="utf-8"))
        cycle = json.loads((self.agent.root / "db" / "daily_workspace" / report_date / "memory_cycle.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["analysis_quality"], "after_close")
        self.assertTrue(meta["memory_eligible"])
        self.assertEqual(cycle["status"], "ok")
        records = list_memory_records(self.agent.root, limit=20)
        self.assertTrue(records)
        self.assertTrue(any(item.get("horizon_bucket") for item in records))

    def test_today_analysis_runtime_marks_result_fields(self):
        self.agent.write_json("raw/quotes/2026-05-06.json", {"provider": "demo", "funds": []})
        run_today_analysis(
            self.agent.root,
            "2026-05-06",
            trigger="manual",
            demo=True,
            force=True,
            llm_mock=True,
            started_at=datetime(2026, 5, 6, 14, 59),
        )
        runtime = json.loads((self.agent.root / "db" / "daily_workspace" / "2026-05-06" / "today_analysis_runtime.json").read_text(encoding="utf-8"))
        self.assertIn(runtime["status"], {"ok", "degraded"})
        self.assertTrue(runtime["resultReady"])
        self.assertEqual(runtime["resultRunId"], runtime["runId"])
        self.assertTrue(runtime["heartbeatAt"])
        self.assertTrue(runtime["endedAt"])
        self.assertGreater(int(runtime["pid"]), 0)
        if runtime["status"] == "degraded":
            self.assertIn("executionEligible", runtime)
            self.assertIn("committeeReady", runtime)

    def test_active_runtime_blocks_duplicate_today_analysis(self):
        runtime_path = self.agent.root / "db" / "daily_workspace" / "2026-05-06" / "today_analysis_runtime.json"
        self.agent.write_json(
            runtime_path.relative_to(self.agent.root).as_posix(),
            {
                "status": "running",
                "runId": "run-1",
                "pid": os.getpid(),
                "reportDate": "2026-05-06",
                "startedAt": "2026-05-06T15:00:00+08:00",
                "heartbeatAt": "2026-05-06T15:00:00+08:00",
                "currentStep": "run_daily_pipeline",
                "currentAgent": "portfolio_trader",
            },
        )
        active = get_active_runtime(self.agent.root, "2026-05-06")
        self.assertEqual(active["runId"], "run-1")
        with self.assertRaises(AlreadyRunningError):
            run_today_analysis(
                self.agent.root,
                "2026-05-06",
                trigger="manual",
                demo=True,
                force=True,
                llm_mock=True,
                started_at=datetime(2026, 5, 6, 15, 1),
            )

    def test_today_analysis_backfill_only_looks_back_three_calendar_days(self):
        self.agent.write_json(
            "db/daily_workspace/2026-05-02/today_analysis_meta.json",
            {
                "analysis_run_id": "old-run",
                "analysis_quality": "pre_close",
                "memory_eligible": False,
            },
        )
        self.agent.write_json(
            "db/daily_workspace/2026-05-02/memory_cycle.json",
            {"status": "failed_retryable"},
        )
        self.agent.write_json(
            "db/daily_workspace/2026-05-06/today_analysis_meta.json",
            {
                "analysis_run_id": "recent-ok",
                "analysis_quality": "after_close",
                "memory_eligible": True,
            },
        )
        self.agent.write_json(
            "db/daily_workspace/2026-05-06/memory_cycle.json",
            {"status": "ok"},
        )
        self.agent.write_json(
            "db/daily_workspace/2026-05-07/today_analysis_meta.json",
            {
                "analysis_run_id": "recent-rerun",
                "analysis_quality": "pre_close",
                "memory_eligible": False,
            },
        )
        self.agent.write_json(
            "db/daily_workspace/2026-05-07/memory_cycle.json",
            {"status": "skipped"},
        )
        pending = _pending_backfill_dates(
            self.agent.root,
            "2026-05-08",
            datetime(2026, 5, 8, 15, 1),
        )
        self.assertEqual(pending, ["2026-05-05", "2026-05-07"])
        self.assertNotIn("2026-05-02", pending)

    def test_active_backfill_does_not_block_remaining_backfills(self):
        started = datetime(2026, 5, 11, 10, 8)
        active_error = AlreadyRunningError(
            {
                "runId": "run-0508",
                "reportDate": "2026-05-08",
                "pid": os.getpid(),
            }
        )
        with patch.object(run_today_module, "pending_backfill_dates", return_value=["2026-05-08", "2026-05-09"]), patch.object(
            run_today_module,
            "run_today_analysis",
            side_effect=[active_error, self.agent.root / "db" / "daily_workspace" / "2026-05-09" / "today_summary.json"],
        ) as runner:
            skipped = run_pending_backfills(
                self.agent.root,
                "2026-05-11",
                started,
                demo=True,
                llm_mock=True,
                resume_existing=False,
            )
        self.assertEqual(skipped[0]["date"], "2026-05-08")
        self.assertIn("already running", skipped[0]["reason"])
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(runner.call_args_list[1].args[1], "2026-05-09")

    def test_manual_today_analysis_does_not_start_pending_backfills(self):
        started = datetime(2026, 5, 11, 10, 8)
        self.assertFalse(should_run_pending_backfills("manual", "2026-05-11", started))
        self.assertTrue(should_run_pending_backfills("auto", "2026-05-11", started))
        self.assertTrue(should_run_pending_backfills("compat_first_open", "2026-05-11", started))

    def test_run_long_memory_analysis_requires_memory_eligible(self):
        report_date = "2026-05-06"
        workspace = self.agent.root / "db" / "daily_workspace" / report_date
        workspace.mkdir(parents=True, exist_ok=True)
        self.agent.write_json(
            f"db/daily_workspace/{report_date}/today_analysis_meta.json",
            {
                "analysis_run_id": "run-1",
                "analysis_quality": "pre_close",
                "memory_eligible": False,
            },
        )
        with self.assertRaises(RuntimeError):
            run_memory_cycle(self.agent.root, report_date, mock=True)


if __name__ == "__main__":
    unittest.main()
