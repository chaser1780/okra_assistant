from __future__ import annotations

import sys
import unittest
import os
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from http.server import ThreadingHTTPServer

import app.web_api as web_api_module
from app.web_api import ContractRequestHandler, OkraWebApi, cors_origin_value, is_allowed_origin, is_loopback_host
from app.web_api_services import ExecutionController, TaskController
from helpers import TempAgentHome
from long_memory_store import stable_memory_id, upsert_memory_record
from today_orchestrator import AlreadyRunningError
from ui_support import today_str


class WebApiLongMemoryTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_snapshot_exposes_long_memory_for_react_app(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_type": "fund_profile_memory",
                "domain": "fund",
                "entity_key": "F1",
                "title": "F1 profile",
                "text": "F1 add advice has been weak in choppy markets.",
                "status": "strategic",
                "confidence": 0.8,
            },
        )
        upsert_memory_record(
            self.agent.root,
            {
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "cash_floor",
                "title": "Cash floor",
                "text": "Keep a minimum cash floor.",
                "status": "strategic",
                "confidence": 0.9,
            },
        )
        api = OkraWebApi(self.agent.root)
        snapshot = api.snapshot()
        self.assertIn("longMemory", snapshot)
        self.assertIn("dailyFirstOpen", snapshot)
        self.assertIn("todayAnalysis", snapshot)
        self.assertEqual(snapshot["longMemory"]["counts"]["fund"], 1)
        self.assertEqual(snapshot["longMemory"]["counts"]["pending"], 1)
        self.assertEqual(snapshot["longMemory"]["pending"][0]["entity_key"], "cash_floor")

    def test_snapshot_exposes_today_analysis_system_fields(self):
        report_date = "2026-05-06"
        self.agent.write_json(
            f"db/daily_workspace/{report_date}/today_decision.json",
            {"generated_at": "2026-05-06T15:05:00+08:00", "task": "today_analysis"},
        )
        self.agent.write_json(
            f"db/daily_workspace/{report_date}/today_analysis.json",
            {"analysis_date": report_date},
        )
        self.agent.write_json(
            f"db/daily_workspace/{report_date}/today_analysis_meta.json",
            {
                "runAt": "2026-05-06T15:05:00+08:00",
                "analysis_quality": "after_close",
                "memory_eligible": True,
                "task": "today_analysis",
            },
        )
        self.agent.write_json(
            f"db/daily_workspace/{report_date}/memory_cycle.json",
            {"status": "ok", "summary": {"written_count": 4}},
        )
        api = OkraWebApi(self.agent.root)
        snapshot = api.snapshot(report_date)
        self.assertEqual(snapshot["todayAnalysis"]["meta"]["analysis_quality"], "after_close")
        self.assertTrue(snapshot["system"]["todayAnalysis"]["memory_eligible"])
        self.assertEqual(snapshot["system"]["todayAnalysis"]["task"], "today_analysis")

    def test_page_payloads_expose_simulation_and_data_context(self):
        report_date = "2026-05-06"
        self.agent.write_json(
            f"db/realtime_monitor/{report_date}.json",
            {
                "report_date": report_date,
                "generated_at": "2026-05-06T21:00:00+08:00",
                "realtime_policy": {"provider": "fund_estimate_proxy"},
                "items": [
                    {
                        "fund_code": "F1",
                        "mode": "proxy_fallback",
                        "effective_change_pct": 1.2,
                        "estimate_change_pct": 1.0,
                        "proxy_change_pct": 1.2,
                        "stale": True,
                        "freshness_age_business_days": 0,
                    }
                ],
            },
        )
        api = OkraWebApi(self.agent.root)
        portfolio = api.portfolio_page(report_date)["portfolio"]
        realtime = api.realtime_page(report_date)["realtime"]
        execution = api.execution_page(report_date)["executionSync"]

        self.assertEqual(report_date, portfolio["dataContext"]["selectedDate"])
        self.assertTrue(portfolio["simulation"]["simulationOnly"])
        self.assertEqual("user_simulation", execution["simulation"]["formalTrack"])
        self.assertTrue(realtime["observationOnly"])
        self.assertIn(realtime["dataContext"]["freshnessStatus"], {"official_nav_pending", "delayed_1d", "proxy_observation"})

    def test_snapshot_exposes_today_analysis_runtime_fields(self):
        report_date = "2026-05-06"
        self.agent.write_json(
            f"db/daily_workspace/{report_date}/today_analysis_runtime.json",
            {
                "status": "running",
                "runId": "run-123",
                "pid": os.getpid(),
                "reportDate": report_date,
                "startedAt": "2026-05-06T15:00:00+08:00",
                "heartbeatAt": "2026-05-06T15:01:00+08:00",
                "endedAt": "",
                "currentStep": "multiagent_research",
                "currentAgent": "portfolio_trader",
                "resultReady": False,
                "resultRunId": "",
            },
        )
        api = OkraWebApi(self.agent.root)
        snapshot = api.snapshot(report_date)
        runtime = snapshot["system"]["todayAnalysisRuntime"]
        self.assertEqual(runtime["runId"], "run-123")
        self.assertEqual(runtime["currentStep"], "multiagent_research")
        self.assertIn("heartbeatAt", runtime)
        self.assertIn("resultReady", runtime)

    def test_run_task_rejects_duplicate_daily_run(self):
        report_date = today_str()
        self.agent.write_json(
            f"db/daily_workspace/{report_date}/today_analysis_runtime.json",
            {
                "status": "running",
                "runId": "run-dup",
                "pid": os.getpid(),
                "reportDate": report_date,
                "startedAt": "2026-05-09T16:40:00+08:00",
                "heartbeatAt": "2026-05-09T16:42:00+08:00",
                "currentStep": "multiagent_research",
                "currentAgent": "portfolio_trader",
            },
        )
        api = OkraWebApi(self.agent.root)
        with self.assertRaises(AlreadyRunningError):
            api.run_task("daily", force=True)

    def test_manual_daily_run_uses_manual_trigger(self):
        api = OkraWebApi(self.agent.root)
        with patch("app.web_api_services.subprocess.Popen") as popen, patch("app.web_api_services.get_active_runtime", return_value={}):
            popen.return_value.pid = 12345
            result = api.run_task("daily", force=True)
        command = popen.call_args.args[0]
        self.assertIn("--trigger", command)
        self.assertIn("manual", command)
        self.assertIn("--force", command)
        self.assertEqual(result["pid"], 12345)

    def test_historical_daily_run_uses_selected_date_without_startup_alignment(self):
        api = OkraWebApi(self.agent.root)
        with patch("app.web_api_services.subprocess.Popen") as popen, patch("app.web_api_services.get_active_runtime", return_value={}), patch.object(
            TaskController, "run_portfolio_alignment_if_needed", side_effect=AssertionError("historical daily run should not align current portfolio")
        ):
            popen.return_value.pid = 12345
            result = api.run_task("daily", force=True, run_date="2026-05-20")
        command = popen.call_args.args[0]
        self.assertIn("--date", command)
        self.assertIn("2026-05-20", command)
        self.assertEqual(result["runDate"], "2026-05-20")
        self.assertTrue(result["portfolioAlignment"]["skipped"])
        self.assertEqual(result["portfolioAlignment"]["reason"], "historical_daily_run")

    def test_realtime_run_ignores_historical_selected_date(self):
        api = OkraWebApi(self.agent.root)
        expected_date = today_str()
        with patch("app.web_api_services.subprocess.Popen") as popen, patch("app.web_api_services.get_active_runtime", return_value={}):
            popen.return_value.pid = 12345
            result = api.run_task("realtime", run_date="2026-05-20")
        command = popen.call_args.args[0]
        self.assertIn("--date", command)
        self.assertIn(expected_date, command)
        self.assertNotIn("2026-05-20", command)
        self.assertEqual(result["runDate"], expected_date)

    def test_realtime_run_reuses_active_process(self):
        controller = TaskController(self.agent.root)
        process = unittest.mock.MagicMock()
        process.pid = 12345
        process.poll.return_value = None
        with patch("app.web_api_services.subprocess.Popen", return_value=process) as popen:
            first = controller.run_task("realtime")
            second = controller.run_task("realtime")

        self.assertFalse(first["alreadyRunning"])
        self.assertTrue(second["alreadyRunning"])
        self.assertEqual(first["pid"], second["pid"])
        popen.assert_called_once()

    def test_fund_detail_exposes_fund_memory(self):
        upsert_memory_record(
            self.agent.root,
            {
                "memory_type": "fund_profile_memory",
                "domain": "fund",
                "entity_key": "F1",
                "title": "F1 profile",
                "text": "F1 follows the proxy with one day lag.",
                "status": "strategic",
                "confidence": 0.7,
            },
        )
        api = OkraWebApi(self.agent.root)
        detail = api.fund_detail("F1")
        self.assertEqual(detail["longMemory"]["fund"][0]["title"], "F1 profile")

    def test_long_memory_action_promotes_to_permanent(self):
        memory_id = stable_memory_id("portfolio", "cash_floor", "Cash floor", "portfolio_policy_memory")
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": memory_id,
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "cash_floor",
                "title": "Cash floor",
                "text": "Keep a minimum cash floor.",
                "status": "strategic",
                "confidence": 0.9,
            },
        )
        api = OkraWebApi(self.agent.root)
        result = api.long_memory_action({"memoryId": memory_id, "action": "approve", "note": "confirmed in UI"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["record"]["status"], "permanent")
        self.assertEqual(result["record"]["approved_by"], "user")

    def test_learning_derived_memory_requires_trusted_lineage_for_approval(self):
        memory_id = stable_memory_id("portfolio", "replay_rule", "Replay rule", "portfolio_policy_memory")
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": memory_id,
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "replay_rule",
                "title": "Replay rule",
                "text": "Derived from replay evidence.",
                "status": "strategic",
                "source": "replay_experiment",
                "metadata": {"experiment_id": "legacy-replay"},
            },
        )
        api = OkraWebApi(self.agent.root)

        with self.assertRaises(ValueError):
            api.long_memory_action({"memoryId": memory_id, "action": "approve"})

        trusted_id = stable_memory_id("portfolio", "trusted_replay_rule", "Trusted replay rule", "portfolio_policy_memory")
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": trusted_id,
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "trusted_replay_rule",
                "title": "Trusted replay rule",
                "text": "Derived from a trusted replay.",
                "status": "strategic",
                "source": "replay_experiment",
                "metadata": {"experiment_id": "trusted-replay", "learning_trust_status": "trusted"},
            },
        )
        result = api.long_memory_action({"memoryId": trusted_id, "action": "approve"})
        self.assertEqual("permanent", result["record"]["status"])

    def test_strategy_experiment_memory_is_marked_as_non_formal(self):
        record = upsert_memory_record(
            self.agent.root,
            {
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "experiment_rule",
                "title": "实验规则",
                "text": "Only validated in a strategy experiment.",
                "status": "candidate",
                "source": "replay_experiment",
                "metadata": {"experiment_id": "exp-1"},
            },
        )
        self.assertEqual("strategy_simulation", record["metadata"]["sourceTrack"])
        self.assertEqual("exp-1", record["metadata"]["experimentId"])
        self.assertFalse(record["metadata"]["formalInfluence"])

    def test_strategy_experiment_memory_is_marked_as_non_formal(self):
        record = upsert_memory_record(
            self.agent.root,
            {
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "experiment_rule",
                "title": "实验规则",
                "text": "Only validated in a strategy experiment.",
                "status": "candidate",
                "source": "replay_experiment",
                "metadata": {"experiment_id": "exp-1"},
            },
        )
        self.assertEqual("strategy_simulation", record["metadata"]["sourceTrack"])
        self.assertEqual("exp-1", record["metadata"]["experimentId"])
        self.assertFalse(record["metadata"]["formalInfluence"])

    def test_contract_handler_wraps_page_payload_in_envelope(self):
        payload = self._request_json("/api/today")
        self.assertTrue(payload["ok"])
        self.assertIn("data", payload)
        self.assertEqual(payload["meta"]["page"], "today")
        self.assertIn("selectedDate", payload["data"])
        self.assertIn("dashboard", payload["data"])

    def test_snapshot_endpoint_keeps_legacy_raw_payload(self):
        payload = self._request_json("/api/snapshot")
        self.assertIn("selectedDate", payload)
        self.assertIn("dashboard", payload)
        self.assertNotIn("ok", payload)
        self.assertNotIn("data", payload)

    def test_local_api_rejects_non_loopback_bind_targets(self):
        self.assertTrue(is_loopback_host("127.0.0.1"))
        self.assertTrue(is_loopback_host("::1"))
        self.assertTrue(is_loopback_host("localhost"))
        self.assertFalse(is_loopback_host("0.0.0.0"))
        self.assertFalse(is_loopback_host("192.168.1.10"))

    def test_health_endpoint_identifies_okra_api(self):
        payload = self._request_json("/api/health")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["app"], "okra-assistant")
        self.assertNotIn("home", payload["data"])
        self.assertEqual(payload["meta"]["page"], "health")

    def test_remote_page_reads_require_cloudflare_access_identity(self):
        remote_env = {
            "OKRA_PUBLIC_BASE_URL": "https://okra.example.test",
            "OKRA_ALLOWED_ORIGINS": "https://okra.example.test",
            "OKRA_TRUST_CLOUDFLARE_ACCESS": "1",
            "OKRA_API_TOKEN": "test-remote-token",
        }
        with patch.dict(os.environ, remote_env, clear=False):
            with self.assertRaises(HTTPError) as ctx:
                self._request_json("/api/today", headers={"Origin": "https://okra.example.test"})
            self.assertEqual(401, ctx.exception.code)
            denied = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual("cloudflare_access_required", denied["error"]["error_code"])

            payload, headers = self._request_json_with_headers(
                "/api/today",
                headers={
                    "Origin": "https://okra.example.test",
                    "Cf-Access-Authenticated-User-Email": "user@example.test",
                },
            )
            token_payload = self._request_json(
                "/api/today",
                headers={
                    "Origin": "https://okra.example.test",
                    "Authorization": "Bearer test-remote-token",
                },
            )
        self.assertTrue(payload["ok"])
        self.assertTrue(token_payload["ok"])
        self.assertEqual("https://okra.example.test", headers.get("Access-Control-Allow-Origin"))

    def test_remote_mutation_requires_access_and_bearer_token(self):
        remote_env = {
            "OKRA_PUBLIC_BASE_URL": "https://okra.example.test",
            "OKRA_ALLOWED_ORIGINS": "https://okra.example.test",
            "OKRA_TRUST_CLOUDFLARE_ACCESS": "1",
            "OKRA_API_TOKEN": "test-remote-token",
            "OKRA_DISABLE_REMOTE_MUTATIONS": "0",
        }
        access_headers = {
            "Origin": "https://okra.example.test",
            "Cf-Access-Jwt-Assertion": "test-access-assertion",
        }
        with patch.dict(os.environ, remote_env, clear=False):
            with self.assertRaises(HTTPError) as ctx:
                self._request_json("/api/run/realtime", method="POST", body={}, headers=access_headers)
            self.assertEqual(401, ctx.exception.code)
            denied = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual("bearer_token_required", denied["error"]["error_code"])

            with patch.object(OkraWebApi, "run_task", return_value={"ok": True}):
                payload = self._request_json(
                    "/api/run/realtime",
                    method="POST",
                    body={},
                    headers={**access_headers, "Authorization": "Bearer test-remote-token"},
                )
        self.assertTrue(payload["ok"])
        audit_path = self.agent.root / "logs" / "cloud" / "mutation_audit.jsonl"
        audit_lines = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["denied", "allowed"], [item["decision"] for item in audit_lines])
        self.assertNotIn("test-remote-token", audit_path.read_text(encoding="utf-8"))

    def test_remote_mutations_can_be_disabled_even_with_valid_auth(self):
        remote_env = {
            "OKRA_PUBLIC_BASE_URL": "https://okra.example.test",
            "OKRA_ALLOWED_ORIGINS": "https://okra.example.test",
            "OKRA_TRUST_CLOUDFLARE_ACCESS": "1",
            "OKRA_API_TOKEN": "test-remote-token",
            "OKRA_DISABLE_REMOTE_MUTATIONS": "1",
        }
        with patch.dict(os.environ, remote_env, clear=False), self.assertRaises(HTTPError) as ctx:
            self._request_json(
                "/api/run/realtime",
                method="POST",
                body={},
                headers={
                    "Origin": "https://okra.example.test",
                    "Cf-Access-Jwt-Assertion": "test-access-assertion",
                    "Authorization": "Bearer test-remote-token",
                },
            )
        self.assertEqual(403, ctx.exception.code)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual("remote_mutations_disabled", body["error"]["error_code"])

    def test_remote_rag_admin_get_requires_bearer_token(self):
        remote_env = {
            "OKRA_PUBLIC_BASE_URL": "https://okra.example.test",
            "OKRA_ALLOWED_ORIGINS": "https://okra.example.test",
            "OKRA_TRUST_CLOUDFLARE_ACCESS": "1",
            "OKRA_API_TOKEN": "test-remote-token",
        }
        access_headers = {
            "Origin": "https://okra.example.test",
            "Cf-Access-Jwt-Assertion": "test-access-assertion",
        }
        with patch.dict(os.environ, remote_env, clear=False):
            with self.assertRaises(HTTPError) as ctx:
                self._request_json("/api/rag/status", headers=access_headers)
            self.assertEqual(401, ctx.exception.code)
            denied = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual("bearer_token_required", denied["error"]["error_code"])

            payload = self._request_json(
                "/api/rag/status",
                headers={**access_headers, "Authorization": "Bearer test-remote-token"},
            )
        self.assertTrue(payload["ok"])

    def test_remote_internal_errors_do_not_leak_paths_or_tokens(self):
        remote_env = {
            "OKRA_PUBLIC_BASE_URL": "https://okra.example.test",
            "OKRA_ALLOWED_ORIGINS": "https://okra.example.test",
            "OKRA_API_TOKEN": "test-remote-token",
        }
        with patch.dict(os.environ, remote_env, clear=False), patch.object(
            OkraWebApi,
            "today_page",
            side_effect=RuntimeError("C:/private/state.json test-remote-token"),
        ), self.assertRaises(HTTPError) as ctx:
            self._request_json(
                "/api/today",
                headers={
                    "Origin": "https://okra.example.test",
                    "Authorization": "Bearer test-remote-token",
                },
            )
        self.assertEqual(500, ctx.exception.code)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual("Internal server error", body["error"]["error_message"])
        self.assertNotIn("private", json.dumps(body))
        self.assertNotIn("test-remote-token", json.dumps(body))

    def test_contract_handler_rejects_untrusted_post_origin(self):
        with self.assertRaises(HTTPError) as ctx:
            self._request_json(
                "/api/run/realtime",
                method="POST",
                body={},
                headers={"Origin": "https://evil.example"},
            )
        self.assertEqual(ctx.exception.code, 403)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(body["error"]["error_code"], "forbidden_origin")

    def test_contract_handler_allows_tauri_localhost_origin_for_page_data(self):
        payload = self._request_json("/api/today", headers={"Origin": "http://tauri.localhost"})
        self.assertTrue(payload["ok"])
        self.assertIn("dashboard", payload["data"])

    def test_contract_handler_serves_all_workbench_pages_for_tauri_origin(self):
        expected_keys = {
            "/api/shell": "summary",
            "/api/today": "dashboard",
            "/api/portfolio": "portfolio",
            "/api/execution": "executionSync",
            "/api/research": "research",
            "/api/intelligence": "intelligence",
            "/api/realtime": "realtime",
            "/api/review": "review",
            "/api/system": "system",
        }
        for path, data_key in expected_keys.items():
            with self.subTest(path=path):
                payload, headers = self._request_json_with_headers(path, headers={"Origin": "http://tauri.localhost"})
                self.assertTrue(payload["ok"])
                self.assertIn(data_key, payload["data"])
                self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://tauri.localhost")

    def test_contract_handler_keeps_legacy_workbench_routes_compatible(self):
        expected_keys = {
            "/api/workbench/today": ("today", "dashboard"),
            "/api/workbench/system": ("system", "system"),
        }
        for path, (page, data_key) in expected_keys.items():
            with self.subTest(path=path):
                payload = self._request_json(path, headers={"Origin": "http://tauri.localhost"})
                self.assertTrue(payload["ok"])
                self.assertEqual(page, payload["meta"]["page"])
                self.assertIn(data_key, payload["data"])

    def test_contract_handler_keeps_legacy_workbench_post_routes_compatible(self):
        with patch.object(OkraWebApi, "explain", return_value={"answer": "ok", "mode": "llm"}):
            payload = self._request_json(
                "/api/workbench/copilot/explain",
                method="POST",
                body={"context": "today", "question": "组合风险是什么？", "page": "today"},
                headers={"Origin": "http://tauri.localhost"},
            )
        self.assertTrue(payload["ok"])
        self.assertEqual("ok", payload["data"]["answer"])

    def test_cors_origin_accepts_tauri_and_local_dev_hosts(self):
        self.assertTrue(is_allowed_origin("http://tauri.localhost"))
        self.assertTrue(is_allowed_origin("https://tauri.localhost"))
        self.assertTrue(is_allowed_origin("http://127.0.0.1:5173"))
        self.assertTrue(is_allowed_origin("http://localhost:4173"))
        self.assertEqual(cors_origin_value("http://tauri.localhost"), "http://tauri.localhost")
        self.assertFalse(is_allowed_origin("https://evil.example"))

    def test_execution_trade_rejects_empty_trade_payload(self):
        api = OkraWebApi(self.agent.root)
        with self.assertRaises(ValueError):
            api.execution_trade({"operation_type": "buy", "amount": 0})

    def test_execution_conversion_requires_distinct_funds(self):
        api = OkraWebApi(self.agent.root)
        with self.assertRaises(ValueError):
            api.execution_conversion({"out_fund_code": "F1", "in_fund_code": "F1", "out_amount": 100})

    def test_mutation_endpoints_reject_shadow_artifacts(self):
        api = OkraWebApi(self.agent.root)
        shadow_payload = {
            "fund_code": "F1",
            "operation_type": "buy",
            "amount": 100,
            "ticket_id": "ticket:2026-05-22:F1:add:001",
            "write_scope": "shadow_only",
            "non_executable": True,
            "displayOnly": True,
        }
        with self.assertRaises(ValueError):
            api.execution_trade(shadow_payload)
        with self.assertRaises(ValueError):
            api.execution_conversion(
                {
                    "out_fund_code": "F1",
                    "in_fund_code": "F2",
                    "out_amount": 100,
                    "artifact_kind": "action_ticket_shadow",
                    "nonExecutable": True,
                }
            )
        with self.assertRaises(ValueError):
            api.long_memory_action({"memoryId": "m1", "action": "approve", "write_scope": "learning_only"})

    def test_reconcile_and_confirmation_reject_shadow_artifacts(self):
        api = OkraWebApi(self.agent.root)
        with self.assertRaises(ValueError):
            api.execution_reconcile_apply(
                {
                    "preview": {
                        "apply_ready": True,
                        "write_scope": "shadow_only",
                        "nonExecutable": True,
                    }
                }
            )
        with self.assertRaises(ValueError):
            api.execution_confirmation_update(
                {
                    "date": "2026-05-22",
                    "artifact_kind": "outcome_evidence_learning",
                    "displayOnly": True,
                }
            )

    def test_reconcile_replace_requires_explicit_confirmation(self):
        controller = ExecutionController(self.agent.root)
        request = {
            "reconcileId": "reconcile-1",
            "previewSha256": "1" * 64,
            "expectedPortfolioStateSha256": "2" * 64,
            "dropMissing": True,
        }
        with patch("app.web_api_services.apply_saved_reconciliation", return_value={"ok": True}) as apply:
            with self.assertRaises(ValueError):
                controller.execution_reconcile_apply(request)
            result = controller.execution_reconcile_apply({**request, "confirmReplace": "REPLACE"})

        self.assertTrue(result["ok"])
        apply.assert_called_once_with(
            self.agent.root,
            "reconcile-1",
            preview_sha256="1" * 64,
            expected_portfolio_state_sha256="2" * 64,
            drop_missing=True,
        )

    def test_source_path_alone_does_not_make_manual_payload_shadow(self):
        controller = ExecutionController(self.agent.root)
        with patch("app.web_api_services.record_actual_trade", return_value={"ok": True, "trade_id": "manual-1"}) as record:
            result = controller.execution_trade(
                {
                    "fund_code": "F1",
                    "operation_type": "buy",
                    "amount": 100,
                    "source_path": "manual-import.csv",
                }
            )

        self.assertTrue(result["ok"])
        record.assert_called_once()

    def test_contract_trade_request_rejects_shadow_extra_fields(self):
        with self.assertRaises(HTTPError) as ctx:
            self._request_json(
                "/api/execution-sync/trade",
                method="POST",
                body={
                    "fund_code": "F1",
                    "operation_type": "buy",
                    "amount": 100,
                    "ticket_id": "ticket:2026-05-22:F1:add:001",
                    "write_scope": "shadow_only",
                    "non_executable": True,
                },
                headers={"Origin": "http://tauri.localhost"},
            )
        self.assertEqual(ctx.exception.code, 400)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(body["error"]["error_code"], "bad_request")

    def test_intelligence_tolerates_non_numeric_heat_score(self):
        report_date = "2026-05-15"
        self.agent.write_json(
            f"raw/news/{report_date}.json",
            {
                "items": [
                    {
                        "code": "F1",
                        "title": "测试新闻",
                        "summary": "测试摘要",
                        "provider": "rss:test",
                        "source_role": "theme_news",
                        "published_at": "2026-05-15T10:00:00+08:00",
                        "heat_score": "N/A",
                        "risk_level": "low",
                    }
                ],
                "dedup_summary": {"unique_item_count": 1, "mapped_item_count": 1},
                "source_health": [],
            },
        )
        api = OkraWebApi(self.agent.root)
        payload = api.intelligence_page(report_date)
        self.assertEqual(payload["intelligence"]["metrics"]["unique_news_count"], 1)
        self.assertEqual(payload["intelligence"]["related_news_by_fund"]["F1"][0]["title"], "测试新闻")
        self.assertTrue(payload["intelligence"]["related_news_by_fund"]["F1"][0]["news_id"].startswith("news_"))

    def test_intelligence_news_id_is_stable_for_same_news(self):
        report_date = "2026-05-15"
        item = {
            "code": "F1",
            "title": "稳定资讯",
            "summary": "相同内容应生成相同 news_id",
            "provider": "rss:test",
            "source_url": "https://example.test/news/1",
            "published_at": "2026-05-15T10:00:00+08:00",
            "heat_score": 0.8,
        }
        self.agent.write_json(f"raw/news/{report_date}.json", {"items": [item], "source_health": []})
        api = OkraWebApi(self.agent.root)
        first = api.intelligence_page(report_date)["intelligence"]["important_news"][0]["news_id"]
        second = api.intelligence_page(report_date)["intelligence"]["important_news"][0]["news_id"]
        self.assertEqual(first, second)

    def test_open_url_uses_system_browser_for_http_urls(self):
        api = OkraWebApi(self.agent.root)
        with patch("app.web_api.webbrowser.open", return_value=True) as open_browser:
            payload = api.open_url({"url": "https://example.test/news/1"})
        self.assertTrue(payload["ok"])
        open_browser.assert_called_once_with("https://example.test/news/1", new=2, autoraise=True)

    def test_open_url_rejects_non_http_urls(self):
        api = OkraWebApi(self.agent.root)
        with self.assertRaises(ValueError):
            api.open_url({"url": "file:///not-http-url"})

    def test_contract_handler_uses_api_error_contract(self):
        with self.assertRaises(HTTPError) as ctx:
            self._request_json("/api/unknown")
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["error_code"], "not_found")
        self.assertIn("Unknown GET endpoint", body["error"]["error_message"])
        self.assertTrue(str(body["meta"]["generated_at"]).startswith("20"))

    def test_contract_handler_rejects_oversized_json_body(self):
        with patch.object(web_api_module, "MAX_JSON_BODY_BYTES", 32):
            with self.assertRaises(HTTPError) as ctx:
                self._request_json(
                    "/api/execution-sync/alipay-screenshot/parse",
                    method="POST",
                    body={"files": [{"name": "page.jpg", "data": "x" * 64}]},
                )
        self.assertEqual(ctx.exception.code, 413)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["error_code"], "payload_too_large")

    def test_screenshot_contract_rejects_empty_files_and_extra_fields(self):
        invalid_payloads = [
            {"files": []},
            {"files": [{"name": "page.jpg", "data": "aW1hZ2U="}], "unexpected": True},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(HTTPError) as ctx:
                self._request_json(
                    "/api/execution-sync/alipay-screenshot/parse",
                    method="POST",
                    body=payload,
                )
            self.assertEqual(ctx.exception.code, 400)
            body = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual(body["error"]["error_code"], "bad_request")

    def test_mutation_contracts_reject_unknown_fields(self):
        requests = [
            ("/api/run/daily", {"unexpected": True}),
            ("/api/long-memory/action", {"memoryId": "memory-1", "action": "reject", "unexpected": True}),
            ("/api/execution-sync/reconcile/preview", {"unexpected": True}),
            (
                "/api/execution-sync/reconcile/apply",
                {
                    "reconcileId": "reconcile-1",
                    "previewSha256": "a" * 64,
                    "expectedPortfolioStateSha256": "b" * 64,
                    "unexpected": True,
                },
            ),
            ("/api/execution-sync/confirmation/update", {"unexpected": True}),
            ("/api/open-url", {"url": "https://example.test", "unexpected": True}),
            ("/api/rag/search", {"query": "test", "unexpected": True}),
            ("/api/rag/reindex", {"unexpected": True}),
            ("/api/rag/eval", {"unexpected": True}),
            ("/api/rag/maintenance", {"action": "check_integrity", "unexpected": True}),
        ]
        for path, payload in requests:
            with self.subTest(path=path), self.assertRaises(HTTPError) as ctx:
                self._request_json(path, method="POST", body=payload)
            self.assertEqual(ctx.exception.code, 400)
            body = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual(body["error"]["error_code"], "bad_request")

    def _request_json(self, path: str, *, method: str = "GET", body: dict | None = None, headers: dict[str, str] | None = None) -> dict:
        payload, _ = self._request_json_with_headers(path, method=method, body=body, headers=headers)
        return payload

    def _request_json_with_headers(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[dict, dict]:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ContractRequestHandler)
        ContractRequestHandler.api = OkraWebApi(self.agent.root)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            data = json.dumps(body or {}).encode("utf-8") if method != "GET" else None
            request = Request(f"http://127.0.0.1:{port}{path}", data=data, method=method, headers=headers or {})
            if data is not None:
                request.add_header("Content-Type", "application/json")
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8")), dict(response.headers.items())
        finally:
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
