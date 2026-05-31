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

from app.web_api import ContractRequestHandler, OkraWebApi, cors_origin_value, is_allowed_origin
from app.web_api_services import ExecutionController
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

    def test_health_endpoint_identifies_okra_api(self):
        payload = self._request_json("/api/health")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["app"], "okra-assistant")
        self.assertEqual(payload["meta"]["page"], "health")

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
            api.open_url({"url": "file:///C:/Windows/win.ini"})

    def test_contract_handler_uses_api_error_contract(self):
        with self.assertRaises(HTTPError) as ctx:
            self._request_json("/api/unknown")
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["error_code"], "not_found")
        self.assertIn("Unknown GET endpoint", body["error"]["error_message"])
        self.assertTrue(str(body["meta"]["generated_at"]).startswith("20"))

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
