from __future__ import annotations

import argparse
import json
import sys
import webbrowser
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
from api_contracts import (
    ApiEnvelope,
    ApiError,
    ApiMeta,
    ExecutionConversionRequestDto,
    ExecutionTradeRequestDto,
    FundDetailDto,
    IntelligencePageDto,
    coerce_model,
    model_dump_compat,
)
from copilot_service import call_copilot_llm, local_copilot_answer
from decision_support import build_agent_stage_snapshot, summarize_fund_agent_signals, summarize_fund_stage_signals
from rag_service import RagUnavailable, build_copilot_rag_pack
from rag_eval import run_eval as run_rag_eval
from rag_ingest import build_parser as build_rag_ingest_parser, run_ingest as run_rag_ingest
from rag_maintenance import (
    check_integrity as rag_check_integrity,
    purge_domain as rag_purge_domain,
    rag_status as build_rag_status,
    rag_trace as load_rag_trace,
    rebuild_domain as rag_rebuild_domain,
    vacuum as rag_vacuum,
)
from rag_query_planner import build_rag_query_plan
from rag_retriever import retrieve_rag_evidence
from today_orchestrator import AlreadyRunningError
from web_api_services import ExecutionController, PageService, TaskController
from web_api_format import to_jsonable as _to_jsonable
from workbench_state import WorkbenchStateService


DEFAULT_HOME = Path(r"F:\okra_assistant")
ALLOWED_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
}
LOCAL_CORS_HOSTS = {"127.0.0.1", "localhost", "tauri.localhost"}
DEFAULT_COPILOT_QUESTION = "\u8bf7\u89e3\u91ca\u5f53\u524d\u9875\u9762\u6700\u91cd\u8981\u7684\u7ed3\u8bba\u3001\u98ce\u9669\u548c\u8bc1\u636e\u94fe\u3002"


def is_allowed_origin(origin: str | None) -> bool:
    value = str(origin or "").strip()
    if not value:
        return True
    if value in ALLOWED_ORIGINS:
        return True
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme in {"http", "https"} and host in LOCAL_CORS_HOSTS:
        return True
    if parsed.scheme == "tauri" and host == "localhost":
        return True
    return False


def cors_origin_value(origin: str | None) -> str:
    value = str(origin or "").strip()
    if not value:
        return "*"
    return value if is_allowed_origin(value) else ""


class OkraWebApi:
    def __init__(self, home: Path):
        self.home = home
        self.state_service = WorkbenchStateService(home)
        self.task_controller = TaskController(home)
        self.execution_controller = ExecutionController(home)
        self.page_service = PageService(home, self.state_service)

    def start_bootstrap_alignment(self) -> None:
        try:
            self.task_controller.run_portfolio_alignment_if_needed(force=False)
        except Exception as exc:
            print(f"startup portfolio alignment failed: {exc}", file=sys.stderr, flush=True)

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

    def intelligence_page(self, selected: str | None = None) -> dict:
        snapshot = self.state_service.load_snapshot(selected)
        return coerce_model(
            IntelligencePageDto,
            self.state_service.build_intelligence_page_dto(
                snapshot,
                intelligence=self.page_service.intelligence_payload(snapshot.state),
            ),
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

    def fund_detail(self, fund_code: str, selected: str | None = None, range_label: str = "\u6210\u7acb\u4ee5\u6765") -> dict:
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

    def open_url(self, payload: dict) -> dict:
        url = str(payload.get("url", "") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Only absolute http/https URLs can be opened.")
        opened = webbrowser.open(url, new=2, autoraise=True)
        if not opened:
            raise RuntimeError("System browser refused to open the URL.")
        return {"ok": True, "url": url, "opened": opened}

    def rag_status(self) -> dict:
        return build_rag_status(self.home)

    def rag_trace(self, trace_id: str) -> dict:
        return load_rag_trace(self.home, trace_id)

    def rag_search(self, payload: dict) -> dict:
        query = str(payload.get("query", "") or "").strip()
        if not query:
            raise ValueError("query is required")
        selected = str(payload.get("date") or payload.get("selectedDate") or "").strip() or None
        query_date = selected or self.dates().get("selectedDate", "") or ""
        if not query_date:
            raise ValueError("date is required")
        fund_codes = _coerce_string_list(payload.get("fundCodes"))
        fund_code = str(payload.get("fundCode", "") or "").strip()
        if fund_code and fund_code not in fund_codes:
            fund_codes.append(fund_code)
        top_k = _positive_int(payload.get("topK"), 8)
        include_execution = _optional_bool(payload.get("includeExecution"))
        profile = str(payload.get("profile", "") or "rag_admin")
        intent = str(payload.get("intent", "") or "rag_admin_search")
        if include_execution:
            if profile not in {"execution", "execution_review"}:
                raise ValueError("includeExecution requires execution profile")
            if intent not in {"execution_explain", "position_reconcile", "pending_confirmation"}:
                raise ValueError("includeExecution requires execution intent")
        plan = build_rag_query_plan(
            query,
            query_date=query_date,
            retrieval_profile=profile,
            intent=intent,
            fund_codes=fund_codes,
            domains=_coerce_string_list(payload.get("domains")),
            source_kinds=_coerce_string_list(payload.get("sourceKinds")),
            top_k=top_k,
            token_budget=_positive_int(payload.get("tokenBudget"), 6000),
            include_negative_memory=_optional_bool(payload.get("includeNegativeMemory")),
            include_execution=bool(include_execution),
            metadata={"consumer": "rag_admin"},
        )
        result = retrieve_rag_evidence(self.home, plan, caller="rag_admin", write_trace_file=bool(payload.get("writeTrace", True)))
        return {
            "traceId": result.get("trace_id", ""),
            "tracePath": result.get("trace_path", ""),
            "queryPlan": plan.to_dict(),
            "hitCount": len(result.get("hits", []) or []),
            "hits": result.get("hits", []),
            "missingData": result.get("missing_data", []),
            "candidateCountBeforeFilter": result.get("candidate_count_before_filter", 0),
            "candidateCountAfterFilter": result.get("candidate_count_after_filter", 0),
        }

    def rag_eval(self, payload: dict) -> dict:
        selected = str(payload.get("date") or payload.get("selectedDate") or "").strip() or None
        report_date = selected or self.dates().get("selectedDate", "") or ""
        if not report_date:
            raise ValueError("date is required")
        return run_rag_eval(
            self.home,
            report_date,
            compare_legacy=bool(payload.get("compareLegacy", True)),
            write_trace=bool(payload.get("writeTrace", True)),
        )

    def rag_reindex(self, payload: dict) -> dict:
        args_list: list[str] = []
        selected = str(payload.get("date") or payload.get("selectedDate") or "").strip()
        if selected:
            args_list.extend(["--date", selected])
        for domain in _coerce_string_list(payload.get("domains") or payload.get("domain")):
            args_list.extend(["--domain", domain])
        if not any(item == "--domain" for item in args_list):
            args_list.append("--all")
        if bool(payload.get("write", False)) and not bool(payload.get("dryRun", False)):
            args_list.append("--write")
        else:
            args_list.append("--dry-run")
        if bool(payload.get("embed", False)):
            args_list.append("--embed")
        if bool(payload.get("embeddingDryRun", False)):
            args_list.append("--embedding-dry-run")
        if payload.get("embedLimit") not in (None, ""):
            args_list.extend(["--embed-limit", str(_positive_int(payload.get("embedLimit"), 200))])
        args = build_rag_ingest_parser().parse_args(args_list)
        return run_rag_ingest(self.home, args)

    def rag_maintenance(self, payload: dict) -> dict:
        action = str(payload.get("action", "") or "").strip()
        if action == "check_integrity":
            return rag_check_integrity(self.home)
        if action == "vacuum":
            return rag_vacuum(self.home)
        if action == "rebuild":
            return rag_rebuild_domain(
                self.home,
                str(payload.get("domain", "") or ""),
                report_date=str(payload.get("date") or payload.get("selectedDate") or ""),
                embed=bool(payload.get("embed", False)),
                embedding_dry_run=bool(payload.get("embeddingDryRun", True)),
            )
        if action == "purge_domain":
            return rag_purge_domain(self.home, str(payload.get("domain", "") or ""))
        raise ValueError("Unsupported RAG maintenance action")

    def explain(self, payload: dict) -> dict:
        context = str(payload.get("context", "\u5f53\u524d\u9875\u9762") or "\u5f53\u524d\u9875\u9762")
        question = str(payload.get("question", "") or "").strip()
        page = str(payload.get("page", "") or "").strip()
        selected = str(payload.get("selectedDate", "") or "").strip() or None
        fund_code = str(payload.get("fundCode", "") or "").strip()
        prompt_question = question or DEFAULT_COPILOT_QUESTION
        rag_error = ""
        try:
            rag_payload = dict(payload)
            rag_payload["question"] = prompt_question
            rag_pack = self._build_copilot_rag_pack(rag_payload)
        except RagUnavailable:
            rag_pack = None
        except Exception as exc:
            rag_pack = None
            rag_error = str(exc)
        if rag_pack is not None:
            rag_fallback_reason = str(rag_pack.get("fallbackReason", "") or "")
            if rag_fallback_reason and bool(rag_pack.get("fallbackToLegacy", True)):
                rag_error = rag_fallback_reason
                rag_pack = None

        if rag_pack is not None:
            try:
                answer = self._call_copilot_llm(context, prompt_question, rag_pack)
                return {
                    "answer": answer,
                    "mode": "rag_llm",
                    "sourceDate": rag_pack.get("sourceDate", ""),
                    "traceId": rag_pack.get("traceId", ""),
                    "citations": rag_pack.get("citations", []),
                    "retrieval": rag_pack.get("retrieval", {}),
                    "traceSummary": rag_pack.get("traceSummary", {}),
                }
            except Exception as exc:
                answer = self._local_copilot_answer(context, prompt_question, rag_pack, str(exc))
                return {
                    "answer": answer,
                    "mode": "local_fallback",
                    "sourceDate": rag_pack.get("sourceDate", ""),
                    "traceId": rag_pack.get("traceId", ""),
                    "citations": rag_pack.get("citations", []),
                    "retrieval": rag_pack.get("retrieval", {}),
                    "traceSummary": rag_pack.get("traceSummary", {}),
                    "fallbackReason": str(exc),
                }
        evidence = self._copilot_evidence(page, selected, fund_code)
        prompt_question = question or DEFAULT_COPILOT_QUESTION
        try:
            answer = self._call_copilot_llm(context, prompt_question, evidence)
            result = {"answer": answer, "mode": "llm", "sourceDate": evidence.get("selectedDate", "")}
            if rag_error:
                result["ragFallbackReason"] = rag_error
            return result
        except Exception as exc:
            answer = self._local_copilot_answer(context, prompt_question, evidence, str(exc))
            result = {"answer": answer, "mode": "local_fallback", "sourceDate": evidence.get("selectedDate", "")}
            if rag_error:
                result["ragFallbackReason"] = rag_error
            return result

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
            evidence["fundDetail"] = self._compact_for_copilot(self.fund_detail(fund_code, snapshot.get("selectedDate") or selected, "\u6210\u7acb\u4ee5\u6765"))
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

    def _build_copilot_rag_pack(self, payload: dict) -> dict:
        return build_copilot_rag_pack(self.home, payload)


def _normalize_range_label(range_label: str) -> str:
    label = str(range_label or "").strip()
    aliases = {
        "1m": "\u8fd11\u6708",
        "3m": "\u8fd13\u6708",
        "6m": "\u8fd16\u6708",
        "1y": "\u8fd11\u5e74",
        "since_inception": "\u6210\u7acb\u4ee5\u6765",
        "all": "\u6210\u7acb\u4ee5\u6765",
        "\u6210\u7acb\u4ee5\u6765": "\u6210\u7acb\u4ee5\u6765",
        "\u8fd11\u6708": "\u8fd11\u6708",
        "\u8fd13\u6708": "\u8fd13\u6708",
        "\u8fd16\u6708": "\u8fd16\u6708",
        "\u8fd11\u5e74": "\u8fd11\u5e74",
    }
    return aliases.get(label, label or "\u6210\u7acb\u4ee5\u6765")


def _coerce_string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
        return result
    text = str(value or "").strip()
    return [text] if text else []


def _positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _optional_bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None

class RequestHandler(BaseHTTPRequestHandler):
    api: OkraWebApi

    def _cors_origin(self) -> str:
        return cors_origin_value(self.headers.get("Origin"))

    def _origin_allowed(self) -> bool:
        return is_allowed_origin(self.headers.get("Origin"))

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        cors_origin = self._cors_origin()
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
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
        if not self._origin_allowed():
            self._send_error(403, "forbidden_origin", "Origin is not allowed for OKRA local API")
            return
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
            elif parsed.path == "/api/workbench/intelligence":
                self._send_json(self.api.intelligence_page(selected))
            elif parsed.path == "/api/workbench/realtime":
                self._send_json(self.api.realtime_page(selected))
            elif parsed.path == "/api/workbench/review":
                self._send_json(self.api.review_page(selected))
            elif parsed.path == "/api/workbench/system":
                self._send_json(self.api.system_page(selected))
            elif parsed.path.startswith("/api/fund/"):
                fund_code = parsed.path.rsplit("/", 1)[-1].strip()
                range_label = (query.get("range") or ["\u6210\u7acb\u4ee5\u6765"])[0] or "\u6210\u7acb\u4ee5\u6765"
                self._send_json(self.api.fund_detail(fund_code, selected, range_label))
            elif parsed.path == "/api/execution-sync":
                self._send_json(self.api.execution_sync_payload())
            elif parsed.path == "/api/rag/status":
                self._send_json(self.api.rag_status())
            elif parsed.path == "/api/rag/trace":
                self._send_json(self.api.rag_trace((query.get("id") or query.get("traceId") or [""])[0]))
            else:
                self._send_error(404, "not_found", f"Unsupported GET path: {parsed.path}")
        except Exception as exc:
            self._send_error(500, "internal_error", str(exc), details={"path": parsed.path})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._origin_allowed():
            self._send_error(403, "forbidden_origin", "Origin is not allowed for OKRA local API")
            return
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
            elif parsed.path == "/api/open-url":
                self._send_json(self.api.open_url(payload))
            elif parsed.path == "/api/rag/search":
                self._send_json(self.api.rag_search(payload))
            elif parsed.path == "/api/rag/reindex":
                self._send_json(self.api.rag_reindex(payload))
            elif parsed.path == "/api/rag/eval":
                self._send_json(self.api.rag_eval(payload))
            elif parsed.path == "/api/rag/maintenance":
                self._send_json(self.api.rag_maintenance(payload))
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
        endpoint_path = parsed.path
        if endpoint_path.startswith("/api/workbench/"):
            endpoint_path = "/api/" + endpoint_path[len("/api/workbench/") :]
        try:
            if endpoint_path == "/api/dates":
                self._send_envelope(self.api.dates())
            elif endpoint_path == "/api/shell":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.shell_page(selected), page="shell", selected_date=selected)
            elif endpoint_path == "/api/today":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.today_page(selected), page="today", selected_date=selected)
            elif endpoint_path == "/api/portfolio":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.portfolio_page(selected), page="portfolio", selected_date=selected)
            elif endpoint_path == "/api/execution":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.execution_page(selected), page="execution", selected_date=selected)
            elif endpoint_path == "/api/research":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.research_page(selected), page="research", selected_date=selected)
            elif endpoint_path == "/api/intelligence":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.intelligence_page(selected), page="intelligence", selected_date=selected)
            elif endpoint_path == "/api/realtime":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.realtime_page(selected), page="realtime", selected_date=selected)
            elif endpoint_path == "/api/review":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.review_page(selected), page="review", selected_date=selected)
            elif endpoint_path == "/api/system":
                selected = self._selected_date_from_query(query)
                self._send_envelope(self.api.system_page(selected), page="system", selected_date=selected)
            elif endpoint_path == "/api/snapshot":
                selected = self._selected_date_from_query(query)
                self._send_json(self.api.snapshot(selected))
            elif endpoint_path.startswith("/api/fund/"):
                fund_code = endpoint_path.rsplit("/", 1)[-1].strip()
                selected = self._selected_date_from_query(query)
                range_label = (query.get("range") or ["\u6210\u7acb\u4ee5\u6765"])[0] or "\u6210\u7acb\u4ee5\u6765"
                self._send_envelope(self.api.fund_detail(fund_code, selected, range_label), page="fund", selected_date=selected)
            elif endpoint_path == "/api/execution-sync":
                self._send_envelope(self.api.execution_sync_payload(), page="execution-sync")
            elif endpoint_path == "/api/rag/status":
                self._send_envelope(self.api.rag_status(), page="rag")
            elif endpoint_path == "/api/rag/trace":
                self._send_envelope(self.api.rag_trace((query.get("id") or query.get("traceId") or [""])[0]), page="rag")
            elif endpoint_path == "/api/health":
                self._send_envelope({"app": "okra-assistant", "version": "v1", "home": str(self.api.home)}, page="health")
            else:
                self._send_error(404, "not_found", f"Unknown GET endpoint: {parsed.path}", details={"path": parsed.path})
        except ValueError as exc:
            self._send_error(400, "bad_request", str(exc), details={"path": parsed.path})
        except Exception as exc:
            self._send_error(500, "internal_error", str(exc), details={"path": parsed.path})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._origin_allowed():
            self._send_error(403, "forbidden_origin", "Origin is not allowed for OKRA local API", details={"path": parsed.path})
            return
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
                self._send_envelope(self.api.execution_trade(coerce_model(ExecutionTradeRequestDto, payload)))
            elif parsed.path == "/api/execution-sync/conversion":
                self._send_envelope(self.api.execution_conversion(coerce_model(ExecutionConversionRequestDto, payload)))
            elif parsed.path == "/api/execution-sync/alipay-screenshot/parse":
                self._send_envelope(self.api.execution_screenshot_parse(payload))
            elif parsed.path == "/api/execution-sync/reconcile/preview":
                self._send_envelope(self.api.execution_reconcile_preview(payload))
            elif parsed.path == "/api/execution-sync/reconcile/apply":
                self._send_envelope(self.api.execution_reconcile_apply(payload))
            elif parsed.path == "/api/execution-sync/confirmation/update":
                self._send_envelope(self.api.execution_confirmation_update(payload))
            elif parsed.path == "/api/open-url":
                self._send_envelope(self.api.open_url(payload), page="open-url")
            elif parsed.path == "/api/rag/search":
                self._send_envelope(self.api.rag_search(payload), page="rag")
            elif parsed.path == "/api/rag/reindex":
                self._send_envelope(self.api.rag_reindex(payload), page="rag")
            elif parsed.path == "/api/rag/eval":
                self._send_envelope(self.api.rag_eval(payload), page="rag")
            elif parsed.path == "/api/rag/maintenance":
                self._send_envelope(self.api.rag_maintenance(payload), page="rag")
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
    handler.api.start_bootstrap_alignment()
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"OKRA web API listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
