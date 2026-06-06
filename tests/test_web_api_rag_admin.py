from __future__ import annotations

import sys
import json
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.web_api import ContractRequestHandler, OkraWebApi
from helpers import TempAgentHome
from rag_index_store import upsert_chunks, upsert_documents
from rag_models import RagChunk, RagDocument


class WebApiRagAdminTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _insert_rag_doc(self) -> None:
        doc = RagDocument(
            doc_id="rag-admin-f1",
            source_kind="evidence_item",
            source_path="db/llm_context/2026-05-20.json",
            source_record_id="ev-f1",
            title="F1 valuation risk",
            summary="F1 risk comes from valuation pressure.",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="fund",
            source_tier="daily_evidence",
            visibility="default",
            entity_type="fund",
            entity_id="F1",
            fund_codes=["F1"],
            payload={"evidence_id": "ev-f1", "risk": "valuation"},
        )
        chunk = RagChunk(
            chunk_id="rag-admin-f1:chunk:0",
            doc_id=doc.doc_id,
            chunk_index=0,
            text_for_embedding="F1 valuation pressure risk",
            text_for_llm="F1 risk comes from valuation pressure.",
        )
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [chunk])

    def _insert_execution_doc(self) -> None:
        doc = RagDocument(
            doc_id="rag-admin-execution",
            source_kind="execution_sync",
            source_path="db/execution_sync/actual_trades/2026-05-20.json",
            source_record_id="actual_trade:trade-1",
            title="Execution actual trade",
            summary="F1 execution actual trade pending confirmation.",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="execution",
            source_tier="execution_structured_summary",
            visibility="execution_only",
            entity_type="fund",
            entity_id="F1",
            fund_codes=["F1"],
            learning_scope="execution_only",
            payload={"trade_id": "trade-1", "fund_code": "F1", "status": "submitted"},
            metadata={"source_kind": "execution_sync"},
        )
        chunk = RagChunk(
            chunk_id="rag-admin-execution:chunk:0",
            doc_id=doc.doc_id,
            chunk_index=0,
            text_for_embedding="F1 execution actual trade pending confirmation",
            text_for_llm="F1 execution actual trade pending confirmation.",
        )
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [chunk])

    def test_rag_status_reports_counts_and_disabled_default(self):
        self._insert_rag_doc()
        api = OkraWebApi(self.agent.root)
        status = api.rag_status()
        self.assertFalse(status["enabled"])
        self.assertFalse(status["agentDefault"]["enabled"])
        self.assertTrue(status["dbExists"])
        self.assertEqual(1, status["counts"]["documents"])
        self.assertEqual(1, status["sourceCounts"]["evidence_item"])

    def test_system_page_includes_rag_runtime_status(self):
        self._insert_rag_doc()
        api = OkraWebApi(self.agent.root)
        payload = api.system_page("2026-05-20")
        rag_runtime = payload["system"]["ragRuntime"]
        self.assertFalse(rag_runtime["enabled"])
        self.assertEqual("full", rag_runtime["statusMode"])
        self.assertEqual(1, rag_runtime["counts"]["documents"])

    def test_shell_page_uses_lightweight_rag_runtime_status(self):
        self._insert_rag_doc()
        api = OkraWebApi(self.agent.root)
        payload = api.shell_page("2026-05-20")
        rag_runtime = payload["system"]["ragRuntime"]
        self.assertFalse(rag_runtime["enabled"])
        self.assertEqual("lightweight", rag_runtime["statusMode"])
        self.assertTrue(rag_runtime["dbExists"])
        self.assertEqual({}, rag_runtime["counts"])
        self.assertEqual({}, rag_runtime["sourceCounts"])

    def test_rag_search_returns_trace_and_hits(self):
        self._insert_rag_doc()
        api = OkraWebApi(self.agent.root)
        result = api.rag_search(
            {
                "query": "F1 valuation risk",
                "date": "2026-05-20",
                "fundCode": "F1",
                "topK": 3,
                "writeTrace": True,
            }
        )
        self.assertTrue(result["traceId"].startswith("ragq_"))
        self.assertEqual(1, result["hitCount"])
        self.assertEqual("rag-admin-f1", result["hits"][0]["doc_id"])

        trace = api.rag_trace(result["traceId"])
        self.assertTrue(trace["found"])
        self.assertEqual(result["traceId"], trace["traceId"])

    def test_rag_search_requires_explicit_include_execution(self):
        self._insert_execution_doc()
        api = OkraWebApi(self.agent.root)

        blocked = api.rag_search(
            {
                "query": "F1 execution actual trade pending",
                "date": "2026-05-20",
                "profile": "execution",
                "sourceKinds": ["execution_sync"],
                "domains": ["execution"],
                "writeTrace": False,
            }
        )
        self.assertFalse(blocked["queryPlan"]["include_execution"])
        self.assertEqual(0, blocked["hitCount"])
        self.assertGreaterEqual(blocked["candidateCountBeforeFilter"], 1)
        self.assertEqual(0, blocked["candidateCountAfterFilter"])

        allowed = api.rag_search(
            {
                "query": "F1 execution actual trade pending",
                "date": "2026-05-20",
                "profile": "execution",
                "intent": "execution_explain",
                "sourceKinds": ["execution_sync"],
                "domains": ["execution"],
                "includeExecution": True,
                "writeTrace": False,
            }
        )
        self.assertTrue(allowed["queryPlan"]["include_execution"])
        self.assertEqual(1, allowed["hitCount"])
        self.assertEqual("execution_sync", allowed["hits"][0]["source_kind"])

        with self.assertRaisesRegex(ValueError, "execution profile"):
            api.rag_search(
                {
                    "query": "F1 execution actual trade pending",
                    "date": "2026-05-20",
                    "includeExecution": True,
                    "intent": "execution_explain",
                    "writeTrace": False,
                }
            )
        with self.assertRaisesRegex(ValueError, "execution intent"):
            api.rag_search(
                {
                    "query": "F1 execution actual trade pending",
                    "date": "2026-05-20",
                    "profile": "execution",
                    "includeExecution": True,
                    "writeTrace": False,
                }
            )

    def test_rag_eval_runs_without_trace_when_requested(self):
        self._insert_rag_doc()
        self.agent.write_json(
            "db/llm_context/2026-05-20.json",
            {"analysis_date": "2026-05-20", "funds": [{"fund_code": "F1"}], "evidence_items": []},
        )
        api = OkraWebApi(self.agent.root)
        result = api.rag_eval({"date": "2026-05-20", "compareLegacy": False, "writeTrace": False})
        self.assertEqual("2026-05-20", result["report_date"])
        self.assertEqual("rag_only", result["mode"])
        self.assertTrue(Path(result["output_path"]).exists())

    def test_rag_reindex_dry_run_does_not_write_sqlite(self):
        api = OkraWebApi(self.agent.root)
        result = api.rag_reindex({"date": "2026-05-20", "domains": ["long_memory"], "dryRun": True})
        self.assertEqual("dry_run", result["mode"])
        self.assertFalse(result["wrote"])
        self.assertFalse((self.agent.root / "db" / "rag" / "rag.sqlite").exists())

    def test_contract_rag_admin_routes_use_envelope(self):
        self._insert_rag_doc()
        status = self._request_json("/api/rag/status")
        self.assertTrue(status["ok"])
        self.assertEqual(1, status["data"]["counts"]["documents"])

        search = self._request_json(
            "/api/rag/search",
            method="POST",
            body={"query": "F1 valuation risk", "date": "2026-05-20", "fundCode": "F1"},
            headers={"Origin": "http://tauri.localhost"},
        )
        self.assertTrue(search["ok"])
        self.assertTrue(search["data"]["traceId"].startswith("ragq_"))

        trace = self._request_json(f"/api/rag/trace?id={search['data']['traceId']}")
        self.assertTrue(trace["ok"])
        self.assertTrue(trace["data"]["found"])

        self.agent.write_json("db/llm_context/2026-05-20.json", {"analysis_date": "2026-05-20", "funds": [{"fund_code": "F1"}]})
        eval_payload = self._request_json(
            "/api/rag/eval",
            method="POST",
            body={"date": "2026-05-20", "compareLegacy": False, "writeTrace": False},
            headers={"Origin": "http://tauri.localhost"},
        )
        self.assertTrue(eval_payload["ok"])
        self.assertEqual("2026-05-20", eval_payload["data"]["report_date"])

        reindex = self._request_json(
            "/api/rag/reindex",
            method="POST",
            body={"date": "2026-05-20", "domains": ["long_memory"], "dryRun": True},
            headers={"Origin": "http://tauri.localhost"},
        )
        self.assertTrue(reindex["ok"])
        self.assertEqual("dry_run", reindex["data"]["mode"])

        maintenance = self._request_json(
            "/api/rag/maintenance",
            method="POST",
            body={"action": "check_integrity"},
            headers={"Origin": "http://tauri.localhost"},
        )
        self.assertTrue(maintenance["ok"])
        self.assertTrue(maintenance["data"]["ok"])

    def test_contract_rag_search_rejects_empty_query(self):
        with self.assertRaises(HTTPError) as ctx:
            self._request_json(
                "/api/rag/search",
                method="POST",
                body={"date": "2026-05-20"},
                headers={"Origin": "http://tauri.localhost"},
            )
        self.assertEqual(400, ctx.exception.code)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertFalse(body["ok"])
        self.assertEqual("bad_request", body["error"]["error_code"])

    def test_contract_rag_post_rejects_untrusted_origin(self):
        with self.assertRaises(HTTPError) as ctx:
            self._request_json(
                "/api/rag/search",
                method="POST",
                body={"query": "risk", "date": "2026-05-20"},
                headers={"Origin": "https://evil.example"},
            )
        self.assertEqual(403, ctx.exception.code)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual("forbidden_origin", body["error"]["error_code"])

    def _request_json(self, path: str, *, method: str = "GET", body: dict | None = None, headers: dict[str, str] | None = None) -> dict:
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
                return json.loads(response.read().decode("utf-8"))
        finally:
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
