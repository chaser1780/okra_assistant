from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_daily_pipeline import add_business_days, due_review_jobs, run_rag_shadow, run_step, step_output_exists
from run_realtime_monitor import should_sync_units
from run_report_window import intraday_report_target
from helpers import TempAgentHome
from ui_support import latest_nightly_target_date, load_portfolio_for_date, pending_nightly_catchup_dates, should_autorun_intraday_on_boot, should_refresh_realtime_on_boot
from ui_tasks import portfolio_alignment_target_date, should_align_portfolio_on_boot
from web_api_services import TaskController
from today_orchestrator import should_apply_configured_dca
from datetime import datetime, timezone, timedelta


class PipelineLogicTests(unittest.TestCase):
    def test_configured_dca_only_applies_on_current_shanghai_day(self):
        started = datetime(2026, 5, 4, 16, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(should_apply_configured_dca("2026-05-04", started))
        self.assertFalse(should_apply_configured_dca("2026-05-03", started))

    def test_run_step_persists_child_stderr_on_failure(self):
        agent = TempAgentHome()
        try:
            completed = __import__("subprocess").CompletedProcess(["python"], 1, stdout="partial output", stderr="root cause")
            with patch("run_daily_pipeline.subprocess.run", return_value=completed):
                with self.assertRaisesRegex(RuntimeError, "root cause"):
                    run_step("failing_step.py", agent.root, "2026-07-18", False)

            error_path = agent.root / "db" / "daily_workspace" / "2026-07-18" / "step_errors" / "failing_step.json"
            payload = json.loads(error_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["returncode"], 1)
            self.assertEqual(payload["stderr"], "root cause")
        finally:
            agent.cleanup()

    def _write_promoted_outputs(self, agent: TempAgentHome, report_date: str, *, is_mock: bool = False, model: str = "gpt-5.5") -> Path:
        for relative in (
            f"db/daily_scores/{report_date}.json",
            "db/portfolio_state/current.json",
            "config/portfolio.json",
            "db/long_memory/exports/all_memory.json",
        ):
            agent.write_json(relative, {"report_date": report_date})
        for relative in (
            f"db/committee_advice/{report_date}.json",
            f"db/llm_raw/{report_date}.json",
            f"db/llm_advice/{report_date}.json",
            f"db/committee_decision_bundle/{report_date}.json",
            f"db/validated_advice/{report_date}.json",
        ):
            agent.write_json(relative, {"report_date": report_date})
        return agent.write_json(
            f"db/phase8/promoted_runs/{report_date}.json",
            {
                "status": "ok",
                "report_date": report_date,
                "debate_mode": "deterministic" if is_mock else "llm",
                "llm_model": model,
                "is_mock": is_mock,
                "production_eligible": not is_mock,
                "summary": {"promoted_run_passed": True},
            },
        )

    def _make_promoted_outputs_newer_than_inputs(self, agent: TempAgentHome, report_date: str, future: float) -> None:
        for relative in (
            f"db/llm_context/{report_date}.json",
            f"db/daily_scores/{report_date}.json",
            "db/portfolio_state/current.json",
            "config/portfolio.json",
            "db/long_memory/exports/all_memory.json",
            "config/strategy.toml",
            "config/llm.toml",
        ):
            os.utime(agent.root / relative, (future - 10, future - 10))
        for relative in (
            f"db/committee_advice/{report_date}.json",
            f"db/llm_raw/{report_date}.json",
            f"db/llm_advice/{report_date}.json",
            f"db/committee_decision_bundle/{report_date}.json",
            f"db/validated_advice/{report_date}.json",
            f"db/phase8/promoted_runs/{report_date}.json",
        ):
            os.utime(agent.root / relative, (future, future))

    def _fresh_promoted_output_timestamp(self, agent: TempAgentHome, report_date: str) -> float:
        from run_daily_pipeline import STEP_OUTPUT_CHECKS

        step = STEP_OUTPUT_CHECKS["run_promoted_advice_chain.py"]
        newest_input = max(path.stat().st_mtime for path in step.input_paths(agent.root, report_date) if path.exists())
        return newest_input + 10

    def test_resume_existing_rebuilds_llm_context_when_raw_input_changes(self):
        agent = TempAgentHome()
        try:
            report_date = "2026-03-11"
            for relative in (
                f"raw/quotes/{report_date}.json",
                f"raw/news/{report_date}.json",
                f"raw/fund_profiles/{report_date}.json",
                f"db/intraday_proxies/{report_date}.json",
                f"db/estimated_nav/{report_date}.json",
                f"db/portfolio_state/current.json",
                "db/long_memory/exports/all_memory.json",
            ):
                agent.write_json(relative, {"ok": True})
            context_path = agent.write_json(f"db/llm_context/{report_date}.json", {"context": True})

            self.assertTrue(step_output_exists(agent.root, report_date, "build_llm_context.py"))
            os.utime(agent.root / f"raw/news/{report_date}.json", (context_path.stat().st_mtime + 10, context_path.stat().st_mtime + 10))

            self.assertFalse(step_output_exists(agent.root, report_date, "build_llm_context.py"))
        finally:
            agent.cleanup()

    def test_resume_existing_rebuilds_evidence_index_when_context_changes(self):
        agent = TempAgentHome()
        try:
            report_date = "2026-03-11"
            context_path = agent.write_json(f"db/llm_context/{report_date}.json", {"context": True})
            index_path = agent.write_json(f"db/evidence_index/{report_date}.json", {"index": True})

            self.assertTrue(step_output_exists(agent.root, report_date, "build_evidence_index.py"))
            os.utime(context_path, (index_path.stat().st_mtime + 10, index_path.stat().st_mtime + 10))

            self.assertFalse(step_output_exists(agent.root, report_date, "build_evidence_index.py"))
        finally:
            agent.cleanup()

    def test_resume_existing_rebuilds_promoted_chain_when_context_changes(self):
        agent = TempAgentHome()
        try:
            report_date = "2026-03-11"
            context_path = agent.write_json(f"db/llm_context/{report_date}.json", {"context": True})
            status_path = self._write_promoted_outputs(agent, report_date)
            future = self._fresh_promoted_output_timestamp(agent, report_date)
            self._make_promoted_outputs_newer_than_inputs(agent, report_date, future)

            self.assertTrue(step_output_exists(agent.root, report_date, "run_promoted_advice_chain.py"))
            os.utime(context_path, (status_path.stat().st_mtime + 10, status_path.stat().st_mtime + 10))

            self.assertFalse(step_output_exists(agent.root, report_date, "run_promoted_advice_chain.py"))
        finally:
            agent.cleanup()

    def test_resume_existing_rebuilds_promoted_chain_when_strategy_changes(self):
        agent = TempAgentHome()
        try:
            report_date = "2026-03-11"
            agent.write_json(f"db/llm_context/{report_date}.json", {"context": True})
            self._write_promoted_outputs(agent, report_date)
            future = self._fresh_promoted_output_timestamp(agent, report_date)
            self._make_promoted_outputs_newer_than_inputs(agent, report_date, future)

            self.assertTrue(step_output_exists(agent.root, report_date, "run_promoted_advice_chain.py"))
            os.utime(agent.root / "config" / "strategy.toml", (future + 10, future + 10))

            self.assertFalse(step_output_exists(agent.root, report_date, "run_promoted_advice_chain.py"))
        finally:
            agent.cleanup()

    def test_resume_existing_rebuilds_promoted_chain_when_guardrail_source_changes(self):
        agent = TempAgentHome()
        try:
            report_date = "2026-03-11"
            agent.write_json(f"db/llm_context/{report_date}.json", {"context": True})
            self._write_promoted_outputs(agent, report_date)
            future = self._fresh_promoted_output_timestamp(agent, report_date)
            self._make_promoted_outputs_newer_than_inputs(agent, report_date, future)

            self.assertTrue(step_output_exists(agent.root, report_date, "run_promoted_advice_chain.py"))
            guardrail_source = Path(__file__).resolve().parents[1] / "scripts" / "promoted_advice_guardrails.py"
            original_times = (guardrail_source.stat().st_atime, guardrail_source.stat().st_mtime)
            try:
                os.utime(guardrail_source, (future + 10, future + 10))
                self.assertFalse(step_output_exists(agent.root, report_date, "run_promoted_advice_chain.py"))
            finally:
                os.utime(guardrail_source, original_times)
        finally:
            agent.cleanup()

    def test_resume_existing_separates_live_and_mock_promoted_runs(self):
        agent = TempAgentHome()
        try:
            report_date = "2026-03-11"
            agent.write_json(f"db/llm_context/{report_date}.json", {"context": True})
            self._write_promoted_outputs(agent, report_date, is_mock=True)
            future = self._fresh_promoted_output_timestamp(agent, report_date)
            self._make_promoted_outputs_newer_than_inputs(agent, report_date, future)

            self.assertTrue(step_output_exists(agent.root, report_date, "run_promoted_advice_chain.py", ["--llm-mock"]))
            self.assertFalse(step_output_exists(agent.root, report_date, "run_promoted_advice_chain.py"))
        finally:
            agent.cleanup()

    def test_resume_existing_rebuilds_promoted_chain_when_model_changes(self):
        agent = TempAgentHome()
        try:
            report_date = "2026-03-11"
            agent.write_json(f"db/llm_context/{report_date}.json", {"context": True})
            self._write_promoted_outputs(agent, report_date, model="old-model")
            future = self._fresh_promoted_output_timestamp(agent, report_date)
            self._make_promoted_outputs_newer_than_inputs(agent, report_date, future)

            self.assertFalse(step_output_exists(agent.root, report_date, "run_promoted_advice_chain.py"))
        finally:
            agent.cleanup()

    def test_snapshot_run_never_resumes(self):
        agent = TempAgentHome()
        try:
            self.assertFalse(step_output_exists(agent.root, "2026-03-11", "snapshot_run.py"))
        finally:
            agent.cleanup()

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

    def test_due_review_jobs_uses_execution_sync_actual_trades(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "db" / "execution_sync" / "actual_trades").mkdir(parents=True, exist_ok=True)
            (root / "config" / "review.toml").write_text(
                "[review]\nenabled = true\nhorizons = [1]\ncompare_against = 'validated_advice'\n",
                encoding="utf-8",
            )
            (root / "db" / "execution_sync" / "actual_trades" / "2026-03-10.json").write_text(
                json.dumps({"trade_date": "2026-03-10", "items": [{"trade_id": "t1"}]}, ensure_ascii=False),
                encoding="utf-8",
            )

            jobs = due_review_jobs(root, "2026-03-11")

            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["base_date"], "2026-03-10")
            self.assertTrue(jobs[0]["has_execution"])
            self.assertFalse(jobs[0]["has_advice"])

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

    def test_should_not_sync_units_for_actual_position_snapshot(self):
        agent = TempAgentHome()
        try:
            agent.write_json(
                "config/portfolio.json",
                {
                    "portfolio_name": "娴嬭瘯缁勫悎",
                    "as_of_date": "2026-03-11",
                    "funds": [
                        {
                            "fund_code": "EQ1",
                            "fund_name": "鏉冪泭鍩洪噾",
                            "role": "tactical",
                            "current_value": 503.21,
                            "holding_units": 250.0,
                            "last_valuation_nav": 2.0,
                            "last_valuation_date": "2026-03-11",
                            "units_source": "actual_position_value_only",
                            "actual_daily_pnl": 3.21,
                            "actual_daily_pnl_date": "2026-03-11",
                            "last_real_position_date": "2026-03-11",
                            "real_position_source": "alipay_screenshot",
                        }
                    ],
                },
            )
            agent.write_json("raw/quotes/2026-03-11.json", {"funds": [{"code": "EQ1", "nav": 2.1, "as_of_date": "2026-03-11"}]})
            agent.write_json("db/estimated_nav/2026-03-11.json", {"items": [{"fund_code": "EQ1", "official_nav": 2.1, "official_nav_date": "2026-03-11"}]})

            self.assertFalse(should_sync_units(agent.root, "2026-03-11"))
        finally:
            agent.cleanup()

    def test_load_portfolio_for_date_prefers_runtime_state_over_legacy_bootstrap(self):
        agent = TempAgentHome()
        try:
            agent.write_json("config/portfolio.json", {"portfolio_name": "legacy", "as_of_date": "2026-03-09", "funds": []})
            agent.write_json("db/portfolio_state/current.json", {"portfolio_name": "runtime", "as_of_date": "2026-03-10", "funds": []})

            source_date, payload = load_portfolio_for_date(agent.root, "2026-03-10", "2026-03-10")

            self.assertEqual(source_date, "2026-03-10")
            self.assertEqual(payload["portfolio_name"], "runtime")
            self.assertEqual(payload["_source_kind"], "current")
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

    def test_startup_portfolio_alignment_decision_tracks_nightly_target(self):
        agent = TempAgentHome()
        try:
            now = __import__("datetime").datetime(2026, 4, 21, 10, 0, 0)
            agent.write_json(
                "db/portfolio_state/current.json",
                {
                    "portfolio_name": "runtime",
                    "as_of_date": "2026-04-17",
                    "funds": [{"fund_code": "EQ1", "fund_name": "fund", "current_value": 100.0}],
                },
            )

            self.assertEqual(portfolio_alignment_target_date(agent.root, now=now), "2026-04-20")
            self.assertTrue(should_align_portfolio_on_boot(agent.root, now=now))

            agent.write_json(
                "db/portfolio_state/current.json",
                {
                    "portfolio_name": "runtime",
                    "as_of_date": "2026-04-20",
                    "funds": [{"fund_code": "EQ1", "fund_name": "fund", "current_value": 100.0}],
                },
            )
            self.assertFalse(should_align_portfolio_on_boot(agent.root, now=now))
        finally:
            agent.cleanup()

    def test_daily_task_runs_portfolio_alignment_before_today_analysis(self):
        agent = TempAgentHome()
        try:
            calls = []

            class FakeProcess:
                pid = 12345

            def fake_run(command, **kwargs):
                calls.append(("run", command))
                return type("Completed", (), {"returncode": 0})()

            def fake_popen(command, **kwargs):
                calls.append(("popen", command))
                workspace = agent.root / "db" / "daily_workspace" / "2026-04-21"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "today_analysis_runtime.json").write_text(
                    json.dumps({"runId": "run-1", "status": "running", "pid": FakeProcess.pid}, ensure_ascii=False),
                    encoding="utf-8",
                )
                return FakeProcess()

            with (
                patch("web_api_services.today_str", return_value="2026-04-21"),
                patch("web_api_services.should_align_portfolio_on_boot", return_value=True),
                patch("web_api_services.portfolio_alignment_target_date", return_value="2026-04-20"),
                patch("web_api_services.subprocess.run", side_effect=fake_run),
                patch("web_api_services.subprocess.Popen", side_effect=fake_popen),
                patch("web_api_services.get_active_runtime", side_effect=[{}, {"runId": "run-1", "pid": FakeProcess.pid, "status": "running"}]),
                patch("web_api_services.time.sleep", return_value=None),
            ):
                result = TaskController(agent.root).run_task("daily")

            self.assertEqual(result["runId"], "run-1")
            self.assertEqual(calls[0][0], "run")
            self.assertTrue(any(str(part).endswith("align_portfolio_on_startup.py") for part in calls[0][1]))
            self.assertEqual(calls[1][0], "popen")
            self.assertTrue(any(str(part).endswith("run_today_analysis.py") for part in calls[1][1]))
        finally:
            agent.cleanup()

    def test_rag_shadow_runs_ingest_and_eval_without_blocking(self):
        agent = TempAgentHome()
        try:
            calls = []

            def fake_run_step(script_name, agent_home, report_date, demo, extra_args=None, step_label=None, record_step=None):
                calls.append((script_name, list(extra_args or []), step_label))
                return 0.1

            with patch("run_daily_pipeline.run_step", side_effect=fake_run_step):
                timings = run_rag_shadow(agent.root, "2026-05-20")

            self.assertIn("rag_ingest.py", timings)
            self.assertIn("rag_eval.py", timings)
            self.assertEqual("rag_ingest.py", calls[0][0])
            self.assertIn("--write", calls[0][1])
            self.assertIn("--all", calls[0][1])
            self.assertEqual("rag_eval.py", calls[1][0])
            self.assertIn("--compare-legacy", calls[1][1])
        finally:
            agent.cleanup()

    def test_rag_shadow_degrades_unless_strict(self):
        agent = TempAgentHome()
        try:
            with patch("run_daily_pipeline.run_step", side_effect=RuntimeError("rag failed")):
                timings = run_rag_shadow(agent.root, "2026-05-20", strict=False)
            self.assertIn("rag_shadow_degraded", timings)

            with patch("run_daily_pipeline.run_step", side_effect=RuntimeError("rag failed")):
                with self.assertRaises(RuntimeError):
                    run_rag_shadow(agent.root, "2026-05-20", strict=True)
        finally:
            agent.cleanup()


if __name__ == "__main__":
    unittest.main()
