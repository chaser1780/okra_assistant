from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
APP_DIR = ROOT_DIR / "app"
for path in (SCRIPTS_DIR, APP_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from common import timestamp_now
from api_contracts import ApiEnvelope, ApiError, ApiMeta, FundDetailDto, coerce_model, model_dump_compat
from copilot_service import call_copilot_llm, local_copilot_answer
from decision_support import build_agent_stage_snapshot, summarize_fund_agent_signals, summarize_fund_stage_signals
from today_orchestrator import AlreadyRunningError
from web_api_services import ExecutionController, PageService, TaskController
from web_api_format import to_jsonable as _to_jsonable
from workbench_state import WorkbenchStateService


DEFAULT_HOME = Path(r"F:\okra_assistant")


class OkraWebApi:
    def __init__(self, home: Path):
        self.home = home
        self.state_service = WorkbenchStateService(home)
        self.task_controller = TaskController(home)
        self.execution_controller = ExecutionController(home)
        self.page_service = PageService(home, self.state_service)

    def dates(self) -> dict:
        return self.page_service.dates()

    def snapshot(self, selected: str | None = None) -> dict:
        return self.page_service.snapshot(selected)

    def shell_page(self, selected: str | None = None) -> dict:
        snapshot = self.state_service.load_snapshot(selected)
        payload = self.state_service.build_shell_page_dto(snapshot)
        payload["system"] = self.page_service.system_payload(snapshot.state)
        return payload

    def today_page(self, selected: str | None = None) -> dict:
        snapshot = self.state_service.load_snapshot(selected)
        dashboard = _to_jsonable(self.state_service.build_dashboard_view_model(snapshot))
        today_analysis = self.page_service.today_analysis_payload(snapshot.state)
        payload = self.state_service.build_today_page_dto(
            snapshot,
            dashboard=dashboard,
            today_analysis=today_analysis,
            daily_first_open=_to_jsonable(today_analysis),
        )
        payload["portfolio"] = self.page_service.portfolio_payload(snapshot.state)
        payload["longMemory"] = self.page_service.long_memory_payload()
        payload["system"] = self.page_service.system_payload(snapshot.state)
        return payload

    def portfolio_page(self, selected: str | None = None) -> dict:
        snapshot = self.state_service.load_snapshot(selected)
        return self.state_service.build_portfolio_page_dto(snapshot, portfolio=self.page_service.portfolio_payload(snapshot.state))

    def execution_page(self, selected: str | None = None) -> dict:
        snapshot = self.state_service.load_snapshot(selected)
        return self.state_service.build_execution_page_dto(
            snapshot,
            execution_sync=self.execution_sync_payload(),
            portfolio=self.page_service.portfolio_payload(snapshot.state),
            system=self.page_service.system_payload(snapshot.state),
        )

    def research_page(self, selected: str | None = None) -> dict:
        snapshot = self.state_service.load_snapshot(selected)
        return self.state_service.build_research_page_dto(
            snapshot,
            research=_to_jsonable(self.state_service.build_research_view_model(snapshot)),
        )

    def realtime_page(self, selected: str | None = None) -> dict:
        snapshot = self.state_service.load_snapshot(selected)
        return self.state_service.build_realtime_page_dto(
            snapshot,
            realtime=_to_jsonable(self.state_service.build_realtime_view_model(snapshot)),
        )

    def review_page(self, selected: str | None = None) -> dict:
        snapshot = self.state_service.load_snapshot(selected)
        return self.state_service.build_review_page_dto(
            snapshot,
            review=_to_jsonable(self.state_service.build_review_view_model(snapshot)),
            long_memory=self.page_service.long_memory_payload(),
        )

    def system_page(self, selected: str | None = None) -> dict:
        snapshot = self.state_service.load_snapshot(selected)
        return self.state_service.build_system_page_dto(
            snapshot,
            system=self.page_service.system_payload(snapshot.state),
            shell=self.state_service.build_shell_page_dto(snapshot),
        )

    def fund_detail(self, fund_code: str, selected: str | None = None, range_label: str = "成立以来") -> dict:
        payload = self.page_service.fund_detail(
            fund_code,
            selected,
            range_label,
            _normalize_range_label,
            self._fund_analysis_detail,
            self.page_service.portfolio_payload,
            self.page_service.system_payload,
        )
        return coerce_model(FundDetailDto, payload)

    def run_task(self, kind: str, *, force: bool = False) -> dict:
        return self.task_controller.run_task(kind, force=force)

    def long_memory_action(self, payload: dict) -> dict:
        return self.page_service.long_memory_action(payload)

    def execution_sync_payload(self) -> dict:
        return self.execution_controller.execution_sync_payload()

    def execution_trade(self, payload: dict) -> dict:
        return self.execution_controller.execution_trade(payload)

    def execution_conversion(self, payload: dict) -> dict:
        return self.execution_controller.execution_conversion(payload)

    def execution_screenshot_parse(self, payload: dict) -> dict:
        return self.execution_controller.execution_screenshot_parse(payload)

    def execution_reconcile_preview(self, payload: dict) -> dict:
        return self.execution_controller.execution_reconcile_preview(payload)

    def execution_reconcile_apply(self, payload: dict) -> dict:
        return self.execution_controller.execution_reconcile_apply(payload)

    def execution_confirmation_update(self, payload: dict) -> dict:
        return self.execution_controller.execution_confirmation_update(payload)

    def explain(self, payload: dict) -> dict:
        context = str(payload.get("context", "当前页面") or "当前页面")
        question = str(payload.get("question", "") or "").strip()
        page = str(payload.get("page", "") or "").strip()
        selected = str(payload.get("selectedDate", "") or "").strip() or None
        fund_code = str(payload.get("fundCode", "") or "").strip()
        evidence = self._copilot_evidence(page, selected, fund_code)
        prompt_question = question or "请解释当前页面最重要的结论、风险和证据链。"
        try:
            answer = self._call_copilot_llm(context, prompt_question, evidence)
            return {"answer": answer, "mode": "llm", "sourceDate": evidence.get("selectedDate", "")}
        except Exception as exc:
            answer = self._local_copilot_answer(context, prompt_question, evidence, str(exc))
            return {"answer": answer, "mode": "local_fallback", "sourceDate": evidence.get("selectedDate", "")}

    def _fund_analysis_detail(self, aggregate: dict, fund_code: str) -> dict:
        if not fund_code:
            return {"agentSummary": {}, "stageSummary": {}, "agentCards": []}

        stage_order = {"analyst": 0, "researcher": 1, "manager": 2}
        agent_cards: list[dict] = []
        for agent_name, record in (aggregate.get("agents", {}) or {}).items():
            output = (record or {}).get("output", {}) or {}
            fund_views = [item for item in (output.get("fund_views", []) or []) if item.get("fund_code") == fund_code]
            signal_cards = [item for item in (output.get("signal_cards", []) or []) if item.get("fund_code") == fund_code]
            decision_cards = [item for item in (output.get("decision_cards", []) or []) if item.get("fund_code") == fund_code]
            if not fund_views and not signal_cards and not decision_cards:
                continue
            stage_snapshot = build_agent_stage_snapshot(agent_name, aggregate)
            agent_cards.append(
                {
                    "agent_name": agent_name,
                    "stage": stage_snapshot.get("stage", ""),
                    "stageLabel": stage_snapshot.get("label", ""),
                    "stageDescription": stage_snapshot.get("description", ""),
                    "status": record.get("status", "unknown"),
                    "summary": output.get("summary", ""),
                    "confidence": output.get("confidence", 0.0),
                    "dependsOn": stage_snapshot.get("depends_on", []),
                    "consumers": stage_snapshot.get("consumers", []),
                    "isCommitteeCore": stage_snapshot.get("is_committee_core", False),
                    "portfolioView": output.get("portfolio_view", {}) or {},
                    "fundViews": fund_views,
                    "signalCards": signal_cards,
                    "decisionCards": decision_cards,
                }
            )
        agent_cards.sort(key=lambda item: (stage_order.get(str(item.get("stage", "")), 99), str(item.get("agent_name", ""))))
        return {
            "agentSummary": summarize_fund_agent_signals(aggregate, fund_code),
            "stageSummary": summarize_fund_stage_signals(aggregate, fund_code),
            "agentCards": agent_cards,
        }

    def _copilot_evidence(self, page: str, selected: str | None, fund_code: str = "") -> dict:
        snapshot = self.snapshot(selected)
        evidence: dict = {"page": page or "today", "selectedDate": snapshot.get("selectedDate", ""), "summary": snapshot.get("summary", {})}
        page_payloads = {
            "today": snapshot.get("dashboard", {}),
            "portfolio": snapshot.get("portfolio", {}),
            "research": snapshot.get("research", {}),
            "realtime": snapshot.get("realtime", {}),
            "review": snapshot.get("review", {}),
            "longMemory": snapshot.get("longMemory", {}),
            "system": snapshot.get("system", {}),
        }
        page_key = evidence["page"]
        evidence["pageData"] = self._compact_for_copilot(page_payloads.get(page_key, snapshot.get("dashboard", {})))
        if page_key == "fundDetail" and fund_code:
            evidence["fundDetail"] = self._compact_for_copilot(self.fund_detail(fund_code, snapshot.get("selectedDate") or selected, "近1月"))
        return evidence

    def _compact_for_copilot(self, value, max_chars: int = 12000):
        compact = _to_jsonable(value)
        text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        if len(text) <= max_chars:
            return compact
        return {"truncated": True, "preview": text[:max_chars], "originalChars": len(text)}

    def _call_copilot_llm(self, context: str, question: str, evidence: dict) -> str:
        return call_copilot_llm(self.home, context, question, evidence)

    def _local_copilot_answer(self, context: str, question: str, evidence: dict, error: str) -> str:
        return local_copilot_answer(context, question, evidence, error)


def _normalize_range_label(range_label: str) -> str:
    label = str(range_label or "").strip()
    aliases = {
        "1m": "近1月",
        "3m": "近3月",
        "6m": "近6月",
        "1y": "近1年",
        "since_inception": "成立以来",
        "all": "成立以来",
        "成立以来": "成立以来",
        "近1月": "近1月",
        "近3月": "近3月",
        "近6月": "近6月",
        "近1年": "近1年",
    }
    return aliases.get(label, label or "成立以来")

class RequestHandler(BaseHTTPRequestHandler):
    api: OkraWebApi

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, error_code: str, error_message: str, *, retryable: bool = False, details: dict | None = None) -> None:
        self._send_json(
            {
                "error_code": error_code,
                "error_message": error_message,
                "retryable": retryable,
                "details": details or {},
            },
            status,
        )

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            selected = (query.get("date") or [""])[0] or None
            if parsed.path == "/api/dates":
                self._send_json(self.api.dates())
            elif parsed.path == "/api/snapshot":
                self._send_json(self.api.snapshot(selected))
            elif parsed.path == "/api/workbench/shell":
                self._send_json(self.api.shell_page(selected))
            elif parsed.path == "/api/workbench/today":
                self._send_json(self.api.today_page(selected))
            elif parsed.path == "/api/workbench/portfolio":
                self._send_json(self.api.portfolio_page(selected))
            elif parsed.path == "/api/workbench/execution":
                self._send_json(self.api.execution_page(selected))
            elif parsed.path == "/api/workbench/research":
                self._send_json(self.api.research_page(selected))
            elif parsed.path == "/api/workbench/realtime":
                self._send_json(self.api.realtime_page(selected))
            elif parsed.path == "/api/workbench/review":
                self._send_json(self.api.review_page(selected))
            elif parsed.path == "/api/workbench/system":
                self._send_json(self.api.system_page(selected))
            elif parsed.path.startswith("/api/fund/"):
                fund_code = parsed.path.rsplit("/", 1)[-1].strip()
                range_label = (query.get("range") or ["成立以来"])[0] or "成立以来"
                self._send_json(self.api.fund_detail(fund_code, selected, range_label))
            elif parsed.path == "/api/execution-sync":
                self._send_json(self.api.execution_sync_payload())
            else:
                self._send_error(404, "not_found", f"Unsupported GET path: {parsed.path}")
        except Exception as exc:
            self._send_error(500, "internal_error", str(exc), details={"path": parsed.path})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or "0")
        payload = {}
        if length:
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            except json.JSONDecodeError as exc:
                self._send_error(400, "invalid_json", str(exc))
                return
        try:
            if parsed.path == "/api/run/daily":
                self._send_json(self.api.run_task("daily", force=bool(payload.get("force"))))
            elif parsed.path == "/api/run/realtime":
                self._send_json(self.api.run_task("realtime"))
            elif parsed.path == "/api/copilot/explain":
                self._send_json(self.api.explain(payload))
            elif parsed.path == "/api/long-memory/action":
                self._send_json(self.api.long_memory_action(payload))
            elif parsed.path == "/api/execution-sync/trade":
                self._send_json(self.api.execution_trade(payload))
            elif parsed.path == "/api/execution-sync/conversion":
                self._send_json(self.api.execution_conversion(payload))
            elif parsed.path == "/api/execution-sync/alipay-screenshot/parse":
                self._send_json(self.api.execution_screenshot_parse(payload))
            elif parsed.path == "/api/execution-sync/reconcile/preview":
                self._send_json(self.api.execution_reconcile_preview(payload))
            elif parsed.path == "/api/execution-sync/reconcile/apply":
                self._send_json(self.api.execution_reconcile_apply(payload))
            elif parsed.path == "/api/execution-sync/confirmation/update":
                self._send_json(self.api.execution_confirmation_update(payload))
            else:
                self._send_error(404, "not_found", f"Unsupported POST path: {parsed.path}")
        except AlreadyRunningError as exc:
            runtime = exc.runtime
            self._send_error(
                409,
                "already_running",
                "today_analysis task is already running",
                retryable=False,
                details={
                    "runId": str(runtime.get("runId", "") or ""),
                    "reportDate": str(runtime.get("reportDate", "") or ""),
                    "startedAt": str(runtime.get("startedAt", "") or ""),
                    "currentStep": str(runtime.get("currentStep", "") or ""),
                    "currentAgent": str(runtime.get("currentAgent", "") or ""),
                },
            )
        except Exception as exc:
            self._send_error(500, "internal_error", str(exc), retryable=isinstance(exc, RuntimeError), details={"path": parsed.path})

    def log_message(self, format: str, *args) -> None:
        return


class ContractRequestHandler(RequestHandler):
    def _selected_date_from_query(self, query: dict[str, list[str]]) -> str | None:
        return (query.get("date") or query.get("selectedDate") or [""])[0] or None

    def _send_envelope(self, data, *, page: str | None = None, selected_date: str | None = None, status: int = 200) -> None:
        payload = model_dump_compat(
            ApiEnvelope(
                ok=True,
                data=_to_jsonable(data),
                meta=ApiMeta(page=page, selected_date=selected_date, generated_at=timestamp_now()),
            )
        )
        self._send_json(payload, status)

    def _send_error(self, status: int, code: str, message: str, *, details: dict | None = None, page: str | None = None) -> None:
        payload = model_dump_compat(
            ApiEnvelope(
                ok=False,
                data=None,
                error=ApiError(error_code=code, error_message=message, details=details or {}),
                meta=ApiMeta(page=page, generated_at=timestamp_now()),
            )
        )
        self._send_json(payload, status)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/dates":
                self._send_envelope(self.api.dates())
            elif parsed.path == "/api/shell":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.shell_page(selected), page="shell", selected_date=selected)
            elif parsed.path == "/api/today":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.today_page(selected), page="today", selected_date=selected)
            elif parsed.path == "/api/portfolio":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.portfolio_page(selected), page="portfolio", selected_date=selected)
            elif parsed.path == "/api/execution":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.execution_page(selected), page="execution", selected_date=selected)
            elif parsed.path == "/api/research":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.research_page(selected), page="research", selected_date=selected)
            elif parsed.path == "/api/realtime":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.realtime_page(selected), page="realtime", selected_date=selected)
            elif parsed.path == "/api/review":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.review_page(selected), page="review", selected_date=selected)
            elif parsed.path == "/api/system":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.system_page(selected), page="system", selected_date=selected)
            elif parsed.path == "/api/snapshot":
                selected = self._selected_date_from_query(query)
                self._send_json(self.api.snapshot(selected))
            elif parsed.path.startswith("/api/fund/"):
                fund_code = parsed.path.rsplit("/", 1)[-1].strip()
                selected = self._selected_date_from_query(query)
                range_label = (query.get("range") or ["成立以来"])[0] or "成立以来"
                self._send_envelope(self.api.fund_detail(fund_code, selected, range_label), page="fund", selected_date=selected)
            elif parsed.path == "/api/execution-sync":
                self._send_envelope(self.api.execution_sync_payload(), page="execution-sync")
            else:
                self._send_error(404, "not_found", f"Unknown GET endpoint: {parsed.path}", details={"path": parsed.path})
        except ValueError as exc:
            self._send_error(400, "bad_request", str(exc), details={"path": parsed.path})
        except Exception as exc:
            self._send_error(500, "internal_error", str(exc), details={"path": parsed.path})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or "0")
        payload = {}
        try:
            if length:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if parsed.path == "/api/run/daily":
                self._send_envelope(self.api.run_task("daily", force=bool(payload.get("force"))))
            elif parsed.path == "/api/run/realtime":
                self._send_envelope(self.api.run_task("realtime"))
            elif parsed.path == "/api/copilot/explain":
                self._send_envelope(self.api.explain(payload))
            elif parsed.path == "/api/long-memory/action":
                self._send_envelope(self.api.long_memory_action(payload))
            elif parsed.path == "/api/execution-sync/trade":
                self._send_envelope(self.api.execution_trade(payload))
            elif parsed.path == "/api/execution-sync/conversion":
                self._send_envelope(self.api.execution_conversion(payload))
            elif parsed.path == "/api/execution-sync/alipay-screenshot/parse":
                self._send_envelope(self.api.execution_screenshot_parse(payload))
            elif parsed.path == "/api/execution-sync/reconcile/preview":
                self._send_envelope(self.api.execution_reconcile_preview(payload))
            elif parsed.path == "/api/execution-sync/reconcile/apply":
                self._send_envelope(self.api.execution_reconcile_apply(payload))
            elif parsed.path == "/api/execution-sync/confirmation/update":
                self._send_envelope(self.api.execution_confirmation_update(payload))
            else:
                self._send_error(404, "not_found", f"Unknown POST endpoint: {parsed.path}", details={"path": parsed.path})
        except AlreadyRunningError as exc:
            runtime = exc.runtime
            self._send_error(
                409,
                "already_running",
                "today_analysis task is already running",
                details={
                    "runId": str(runtime.get("runId", "") or ""),
                    "reportDate": str(runtime.get("reportDate", "") or ""),
                    "startedAt": str(runtime.get("startedAt", "") or ""),
                    "currentStep": str(runtime.get("currentStep", "") or ""),
                    "currentAgent": str(runtime.get("currentAgent", "") or ""),
                },
            )
        except json.JSONDecodeError as exc:
            self._send_error(400, "invalid_json", str(exc), details={"path": parsed.path})
        except ValueError as exc:
            self._send_error(400, "bad_request", str(exc), details={"path": parsed.path})
        except Exception as exc:
            self._send_error(500, "internal_error", str(exc), details={"path": parsed.path})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run OKRA local web API.")
    parser.add_argument("--home", default=str(DEFAULT_HOME))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    handler = ContractRequestHandler
    handler.api = OkraWebApi(Path(args.home))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"OKRA web API listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
