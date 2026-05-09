from __future__ import annotations

import sys
import unittest
import os
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from http.server import ThreadingHTTPServer

from app.web_api import ContractRequestHandler, OkraWebApi
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

    def test_contract_handler_uses_api_error_contract(self):
        with self.assertRaises(HTTPError) as ctx:
            self._request_json("/api/unknown")
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["error_code"], "not_found")
        self.assertIn("Unknown GET endpoint", body["error"]["error_message"])
        self.assertTrue(str(body["meta"]["generated_at"]).startswith("20"))

    def _request_json(self, path: str) -> dict:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ContractRequestHandler)
        ContractRequestHandler.api = OkraWebApi(self.agent.root)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            request = Request(f"http://127.0.0.1:{port}{path}")
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        finally:
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
