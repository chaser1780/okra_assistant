from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.web_api import ContractRequestHandler, OkraWebApi
from helpers import TempAgentHome


REPORT_DATE = "2026-05-22"


class WebApiActionTicketShadowReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def test_missing_artifacts_return_display_only_empty_state(self) -> None:
        payload = self._request_json(f"/api/shadow-review?date={REPORT_DATE}")

        self.assertTrue(payload["ok"])
        data = payload["data"]
        self.assertEqual("missing", data["status"])
        self.assertEqual(REPORT_DATE, data["selectedDate"])
        self.assertTrue(data["nonExecutable"])
        self.assertTrue(data["displayOnly"])
        self.assertEqual([], data["items"])
        self.assertTrue(data["guardrails"]["executionDisabled"])
        self.assertFalse(data["guardrails"]["affectsPortfolio"])
        self.assertFalse(data["guardrails"]["affectsLongMemoryPromotion"])
        self.assertIn("legacyAdvice", {item["kind"] for item in data["artifacts"]["missing"]})

    def test_invalid_date_returns_bad_request_envelope(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            self._request_json("/api/shadow-review?date=bad")
        self.assertEqual(400, ctx.exception.code)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertFalse(body["ok"])
        self.assertEqual("bad_request", body["error"]["error_code"])
        self.assertIn("YYYY-MM-DD", body["error"]["error_message"])

    def test_legacy_exists_shadow_missing_returns_not_run(self) -> None:
        self.write_legacy_advice()

        payload = self._request_json(f"/api/shadow-review?date={REPORT_DATE}")

        data = payload["data"]
        self.assertEqual("not_run", data["status"])
        self.assertEqual(1, data["summary"]["legacyCount"])
        self.assertEqual(0, data["summary"]["shadowCount"])
        self.assertEqual([], data["items"])
        missing = {item["kind"]: item for item in data["artifacts"]["missing"]}
        self.assertEqual("not_generated", missing["actionTickets"]["reason"])

    def test_shadow_ticket_without_trace_returns_partial_items(self) -> None:
        self.write_legacy_advice()
        self.write_action_tickets(action="hold")

        payload = self._request_json(f"/api/shadow-review?date={REPORT_DATE}")

        data = payload["data"]
        self.assertEqual("partial", data["status"])
        self.assertEqual(1, len(data["items"]))
        item = data["items"][0]
        self.assertTrue(item["nonExecutable"])
        self.assertTrue(item["displayOnly"])
        self.assertEqual("same", item["category"])
        self.assertIn("retrievalPacks", {row["kind"] for row in data["artifacts"]["missing"]})
        self.assertIn("actionDebates", {row["kind"] for row in data["artifacts"]["missing"]})

    def test_invalid_shadow_json_returns_failed_without_stack_trace(self) -> None:
        self.write_legacy_advice()
        self.agent.write_text(f"db/action_tickets/{REPORT_DATE}.json", "{bad json")

        payload = self._request_json(f"/api/shadow-review?date={REPORT_DATE}")

        data = payload["data"]
        self.assertEqual("failed", data["status"])
        invalid_rows = [row for row in data["artifacts"]["missing"] if row["reason"] == "invalid_json"]
        self.assertTrue(invalid_rows)
        self.assertNotIn("Traceback", invalid_rows[0]["message"])

    def test_ready_payload_contains_non_execution_markers(self) -> None:
        self.write_legacy_advice()
        self.write_action_tickets(action="add")
        self.write_retrieval_packs()
        self.write_action_debates()

        payload = self._request_json(f"/api/shadow-review?date={REPORT_DATE}")

        data = payload["data"]
        self.assertEqual("ready", data["status"])
        self.assertTrue(data["nonExecutable"])
        self.assertTrue(data["displayOnly"])
        self.assertEqual(1, data["summary"]["changedCount"])
        self.assertEqual(1, data["summary"]["highRiskDiffCount"])
        self.assertFalse(data["guardrails"]["affectsAdviceAccuracy"])
        self.assertFalse(data["guardrails"]["allowExecutionEvidence"])
        item = data["items"][0]
        self.assertEqual("changed", item["category"])
        self.assertEqual("high", item["severity"])
        self.assertTrue(item["shadow"]["missingData"])
        self.assertFalse(item["debate"]["writesTicketFile"])

    def test_contract_alias_and_meta_are_stable(self) -> None:
        self.write_legacy_advice()
        payload = self._request_json(f"/api/workbench/shadow-review?date={REPORT_DATE}")

        self.assertTrue(payload["ok"])
        self.assertEqual("shadow-review", payload["meta"]["page"])
        self.assertEqual(REPORT_DATE, payload["meta"]["selected_date"])
        self.assertEqual(REPORT_DATE, payload["data"]["selectedDate"])

    def test_shadow_review_does_not_call_mutation_paths(self) -> None:
        self.write_legacy_advice()
        with patch.object(OkraWebApi, "execution_trade", side_effect=AssertionError("execution_trade called")), patch.object(
            OkraWebApi, "execution_conversion", side_effect=AssertionError("execution_conversion called")
        ), patch.object(OkraWebApi, "execution_reconcile_apply", side_effect=AssertionError("reconcile_apply called")), patch.object(
            OkraWebApi, "long_memory_action", side_effect=AssertionError("long_memory_action called")
        ):
            payload = self._request_json(f"/api/shadow-review?date={REPORT_DATE}")

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["guardrails"]["executionDisabled"])

    def write_legacy_advice(self) -> None:
        self.agent.write_json(
            f"db/validated_advice/{REPORT_DATE}.json",
            {
                "report_date": REPORT_DATE,
                "generated_at": "2026-05-22T09:00:00+08:00",
                "tactical_actions": [
                    {
                        "fund_code": "F001",
                        "fund_name": "Alpha Fund",
                        "validated_action": "hold",
                        "confidence": 0.2,
                        "thesis": "Official hold.",
                        "constraint_hits": [],
                    }
                ],
                "dca_actions": [],
                "hold_actions": [],
            },
        )

    def write_action_tickets(self, *, action: str) -> None:
        self.agent.write_json(
            f"db/action_tickets/{REPORT_DATE}.json",
            {
                "schema_version": "action_ticket.v1",
                "artifact_id": f"action_tickets:{REPORT_DATE}",
                "artifact_kind": "action_ticket_shadow",
                "report_date": REPORT_DATE,
                "generated_at": "2026-05-22T09:10:00+08:00",
                "write_scope": "shadow_only",
                "non_executable": True,
                "summary": {"ticket_count": 1, "status": "ok"},
                "tickets": [
                    {
                        "ticket_id": f"ticket:{REPORT_DATE}:F001:{action}:001",
                        "fund_code": "F001",
                        "fund_name": "Alpha Fund",
                        "action_verb": action,
                        "ticket_status": "blocked" if action == "add" else "shadow_only",
                        "execution_mode": "watch",
                        "validated_amount": 100 if action == "add" else 0,
                        "size_bucket": "small" if action == "add" else "zero",
                        "confidence": 0.7,
                        "thesis": "Shadow candidate label only.",
                        "non_executable": True,
                        "write_scope": "shadow_only",
                        "supporting_evidence_refs": [{"summary": "structured evidence"}],
                        "opposing_evidence_refs": [],
                        "hard_guardrail_results": [
                            {"rule_id": "committee_global_gate", "result": "block" if action == "add" else "pass", "status_reason": "test"}
                        ],
                        "soft_policy_adjustments": [{"policy_id": "policy:test", "effect_type": "note", "effect_value": "review"}],
                        "missing_data": [],
                        "skill_refs": [],
                        "skill_outputs": [],
                    }
                ],
            },
        )

    def write_retrieval_packs(self) -> None:
        self.agent.write_json(
            f"db/retrieval_packs/{REPORT_DATE}.json",
            {
                "schema_version": "retrieval_pack.v1",
                "artifact_id": f"retrieval_packs:{REPORT_DATE}",
                "report_date": REPORT_DATE,
                "generated_at": "2026-05-22T09:20:00+08:00",
                "write_scope": "shadow_only",
                "non_executable": True,
                "summary": {"pack_count": 1},
                "packs": [
                    {
                        "pack_id": f"pack:{REPORT_DATE}:F001:add:001",
                        "target": {"ticket_id": f"ticket:{REPORT_DATE}:F001:add:001", "fund_code": "F001"},
                        "audit": {"trace_completeness_rate": 1.0},
                        "missing_data": [{"field": "official_nav", "state": "pending"}],
                        "rag_trace_refs": [{"trace_id": "rag-disabled"}],
                    }
                ],
            },
        )

    def write_action_debates(self) -> None:
        self.agent.write_json(
            f"db/action_debates/{REPORT_DATE}.json",
            {
                "schema_version": "action_debate.v1",
                "artifact_id": f"action_debates:{REPORT_DATE}",
                "report_date": REPORT_DATE,
                "generated_at": "2026-05-22T09:30:00+08:00",
                "write_scope": "shadow_only",
                "non_executable": True,
                "summary": {"status": "ok", "node_failure_count": 0, "writes_ticket_file": False},
                "runtime": {"run_id": f"action_debate:{REPORT_DATE}", "node_status": {"ticket_writer": "ok"}},
                "debates": [
                    {
                        "debate_id": f"debate:{REPORT_DATE}:F001:001",
                        "ticket_id": f"ticket:{REPORT_DATE}:F001:add:001",
                        "node_outputs": {
                            "debate_referee": {"verdict": "soft_hold"},
                            "ticket_writer": {
                                "writes_ticket_file": False,
                                "proposed_ticket_patch": {"mutation_mode": "proposed_patch_only", "non_executable": True},
                            },
                        },
                    }
                ],
            },
        )

    def _request_json(self, path: str) -> dict:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ContractRequestHandler)
        ContractRequestHandler.api = OkraWebApi(self.agent.root)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            request = Request(f"http://127.0.0.1:{port}{path}", method="GET", headers={"Origin": "http://tauri.localhost"})
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        finally:
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
