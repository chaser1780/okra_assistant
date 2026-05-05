from __future__ import annotations

import argparse
import json
import os
import subprocess
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
from copilot_service import call_copilot_llm, local_copilot_answer
from long_memory_store import approve_memory, can_promote_to_permanent, list_memory_records
from ui_support import build_daily_first_open_command, build_realtime_command, build_runtime_env, collect_dates, today_str
from web_api_format import action_text as _action_text
from web_api_format import markers as _markers
from web_api_format import money as _money
from web_api_format import percent as _percent
from web_api_format import series as _series
from web_api_format import to_jsonable as _to_jsonable
from workbench_history import (
    collect_estimate_history,
    collect_holding_history,
    collect_portfolio_history,
    collect_proxy_history,
    collect_quote_history,
    collect_trade_markers,
    stage_return,
)
from workbench_state import WorkbenchStateService


DEFAULT_HOME = Path(r"F:\okra_assistant")


class OkraWebApi:
    def __init__(self, home: Path):
        self.home = home
        self.state_service = WorkbenchStateService(home)

    def dates(self) -> dict:
        return {"dates": collect_dates(self.home), "today": today_str()}

    def snapshot(self, selected: str | None = None) -> dict:
        snapshot = self.state_service.load_snapshot(selected)
        dashboard = self.state_service.build_dashboard_view_model(snapshot)
        research = self.state_service.build_research_view_model(snapshot)
        realtime = self.state_service.build_realtime_view_model(snapshot)
        review = self.state_service.build_review_view_model(snapshot)
        state = snapshot.state
        return {
            "selectedDate": snapshot.selected_date,
            "dates": snapshot.dates,
            "summary": _to_jsonable(snapshot.summary),
            "dashboard": _to_jsonable(dashboard),
            "portfolio": self._portfolio_payload(state),
            "research": _to_jsonable(research),
            "realtime": _to_jsonable(realtime),
            "review": _to_jsonable(review),
            "longMemory": self._long_memory_payload(),
            "dailyFirstOpen": {
                "decision": state.get("daily_first_open", {}) or {},
                "analysis": state.get("daily_first_open_analysis", {}) or {},
                "updates": state.get("daily_first_open_updates", {}) or {},
                "brief": state.get("daily_first_open_brief", "") or "",
            },
            "system": self._system_payload(state),
        }

    def fund_detail(self, fund_code: str, selected: str | None = None, range_label: str = "成立以来") -> dict:
        range_label = _normalize_range_label(range_label)
        snapshot = self.state_service.load_snapshot(selected)
        state = snapshot.state
        portfolio = self._portfolio_payload(state)
        portfolio_item = next((item for item in portfolio.get("items", []) if item.get("fundCode") == fund_code), None)

        realtime_vm = self.state_service.build_realtime_view_model(snapshot)
        realtime_items = list(_to_jsonable(realtime_vm).get("items", []) or [])
        realtime_item = next((item for item in realtime_items if item.get("fund_code") == fund_code), None)

        research_vm = self.state_service.build_research_view_model(snapshot)
        research_rows = list(_to_jsonable(research_vm).get("rows", []) or [])
        research_item = next((item for item in research_rows if item.get("fund_code") == fund_code), None)

        quote_history = collect_quote_history(self.home, fund_code, range_label)
        proxy_history = collect_proxy_history(self.home, fund_code, range_label)
        holding_history = collect_holding_history(self.home, fund_code, range_label)
        estimate_history = collect_estimate_history(self.home, fund_code, range_label)
        trade_markers = collect_trade_markers(self.home, fund_code, range_label)
        nav_points = quote_history.get("nav", []) or []
        planned_dca_markers = self._planned_dca_markers(fund_code, portfolio_item or {}, snapshot.dates, range_label)

        fund_name = (
            (portfolio_item or {}).get("fundName")
            or (realtime_item or {}).get("fund_name")
            or (research_item or {}).get("fund_name")
            or fund_code
        )
        return {
            "fundCode": fund_code,
            "fundName": fund_name,
            "selectedDate": snapshot.selected_date,
            "range": range_label,
            "portfolio": portfolio_item or {},
            "realtime": realtime_item or {},
            "research": research_item or {},
            "history": {
                "nav": _series(nav_points),
                "navNormalized": _series(quote_history.get("nav_normalized", [])),
                "dayChangePct": _series(quote_history.get("day_change_pct", [])),
                "weekChangePct": _series(quote_history.get("week_change_pct", [])),
                "monthChangePct": _series(quote_history.get("month_change_pct", [])),
                "proxyNormalized": _series(proxy_history.get("normalized", [])),
                "proxyDayChangePct": _series(proxy_history.get("day_change_pct", [])),
                "estimateChangePct": _series(estimate_history),
                "holdingValue": _series(holding_history.get("current_value", [])),
                "holdingPnl": _series(holding_history.get("holding_pnl", [])),
                "holdingReturnPct": _series(holding_history.get("holding_return_pct", [])),
                "holdingUnits": _series(holding_history.get("holding_units", [])),
            },
            "performance": {
                "stageReturn": stage_return(nav_points),
                "navSource": quote_history.get("source", ""),
                "proxySource": proxy_history.get("source", ""),
                "proxyName": proxy_history.get("name", ""),
            },
            "tradeMarkers": sorted(_markers(trade_markers) + planned_dca_markers, key=lambda item: item.get("date", "")),
            "longMemory": self._fund_long_memory_payload(fund_code),
        }

    def run_task(self, kind: str, *, force: bool = False) -> dict:
        run_date = today_str()
        if kind == "daily":
            command = build_daily_first_open_command(self.home, run_date, force=force)
        elif kind == "realtime":
            command = build_realtime_command(self.home, run_date)
        else:
            raise ValueError(f"Unsupported task: {kind}")
        env = {**os.environ, **build_runtime_env(self.home)}
        process = subprocess.Popen(command, cwd=str(self.home), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "task": kind, "pid": process.pid, "runDate": run_date, "force": force}

    def long_memory_action(self, payload: dict) -> dict:
        memory_id = str(payload.get("memoryId", "") or payload.get("memory_id", "") or "").strip()
        action = str(payload.get("action", "") or "").strip().lower()
        note = str(payload.get("note", "") or "").strip()
        if not memory_id:
            raise ValueError("memoryId is required")
        result = approve_memory(self.home, memory_id, action=action, note=note)
        return {"ok": True, "record": _to_jsonable(result)}

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

    def _long_memory_payload(self) -> dict:
        records = list_memory_records(self.home, limit=1000)
        grouped = {
            "fund": [item for item in records if item.get("domain") == "fund"],
            "market": [item for item in records if item.get("domain") == "market"],
            "execution": [item for item in records if item.get("domain") == "execution"],
            "portfolio": [item for item in records if item.get("domain") == "portfolio"],
        }
        pending = [item for item in records if item.get("status") == "strategic" and can_promote_to_permanent(item)]
        counts = {key: len(value) for key, value in grouped.items()}
        counts.update({"pending": len(pending), "total": len(records)})
        return {
            "updatedAt": timestamp_now(),
            "records": _to_jsonable(records),
            "pending": _to_jsonable(pending),
            "fund": _to_jsonable(grouped["fund"]),
            "market": _to_jsonable(grouped["market"]),
            "execution": _to_jsonable(grouped["execution"]),
            "portfolio": _to_jsonable(grouped["portfolio"]),
            "counts": counts,
        }

    def _fund_long_memory_payload(self, fund_code: str) -> dict:
        fund_records = list_memory_records(self.home, domain="fund", entity_key=fund_code, limit=80)
        execution_records = list_memory_records(self.home, domain="execution", limit=80)
        portfolio_rules = [
            item
            for item in list_memory_records(self.home, domain="portfolio", limit=120)
            if item.get("status") in {"strategic", "permanent"}
        ]
        return {"fund": _to_jsonable(fund_records), "execution": _to_jsonable(execution_records[:12]), "rules": _to_jsonable(portfolio_rules[:12])}

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

    def _portfolio_payload(self, state: dict) -> dict:
        portfolio = state.get("portfolio", {}) or {}
        holdings = list(portfolio.get("funds", []) or portfolio.get("holdings", []) or portfolio.get("positions", []) or [])
        total_value = portfolio.get("total_value") or portfolio.get("market_value") or portfolio.get("total_asset") or 0
        cash = portfolio.get("cash") or portfolio.get("cash_balance") or 0
        items = []
        for item in holdings:
            amount = item.get("current_value") or item.get("amount") or item.get("market_value") or item.get("value") or 0
            weight = item.get("weight") or item.get("position_pct") or item.get("allocation") or 0
            if not weight and total_value:
                try:
                    weight = float(amount or 0) / float(total_value or 1) * 100
                except (TypeError, ValueError, ZeroDivisionError):
                    weight = 0
            action = item.get("suggested_action") or item.get("action") or ("locked" if item.get("allow_trade") is False else "hold")
            items.append(
                {
                    "fundCode": item.get("fund_code") or item.get("code") or "",
                    "fundName": item.get("fund_name") or item.get("name") or "",
                    "amount": amount,
                    "amountText": _money(amount),
                    "weight": weight,
                    "weightText": _percent(float(weight) * 100 if isinstance(weight, (int, float)) and abs(weight) <= 1 else weight),
                    "risk": item.get("risk_level") or item.get("risk") or item.get("role") or "normal",
                    "action": action,
                    "role": item.get("role") or "",
                    "styleGroup": item.get("style_group") or "",
                    "holdingPnl": item.get("holding_pnl") or 0,
                    "holdingPnlText": _money(item.get("holding_pnl") or 0),
                    "holdingReturnPct": item.get("holding_return_pct") or 0,
                    "holdingReturnPctText": _percent(item.get("holding_return_pct") or 0),
                    "costBasis": item.get("cost_basis_value") or 0,
                    "costBasisText": _money(item.get("cost_basis_value") or 0),
                    "holdingUnits": item.get("holding_units") or 0,
                    "lastNav": item.get("last_official_nav") or item.get("last_valuation_nav") or 0,
                    "lastNavDate": item.get("last_official_nav_date") or item.get("last_valuation_date") or "",
                    "allowTrade": item.get("allow_trade", True),
                    "fixedDailyBuyAmount": item.get("fixed_daily_buy_amount") or 0,
                    "allowExtraBuys": item.get("allow_extra_buys", True),
                }
            )
        items.sort(key=lambda item: float(item.get("amount") or 0), reverse=True)
        history = collect_portfolio_history(self.home, "成立以来")
        return {
            "asOfDate": portfolio.get("as_of_date") or state.get("portfolio_date") or "",
            "totalValue": total_value,
            "totalValueText": _money(total_value),
            "cash": cash,
            "cashText": _money(cash),
            "holdingPnl": portfolio.get("holding_pnl") or sum(float(item.get("holdingPnl") or 0) for item in items),
            "holdingPnlText": _money(portfolio.get("holding_pnl") or sum(float(item.get("holdingPnl") or 0) for item in items)),
            "styleAllocation": self._group_items(items, "styleGroup", total_value),
            "roleAllocation": self._group_items(items, "role", total_value),
            "profitLeaders": sorted(items, key=lambda item: float(item.get("holdingPnl") or 0), reverse=True)[:5],
            "lossLeaders": sorted(items, key=lambda item: float(item.get("holdingPnl") or 0))[:5],
            "history": {
                "totalValue": _series(history.get("total_value", [])),
                "holdingPnl": _series(history.get("holding_pnl", [])),
                "holdingReturnPct": _series(history.get("holding_return_pct", [])),
            },
            "items": items,
        }

    def _group_items(self, items: list[dict], key: str, total_value: float) -> list[dict]:
        grouped: dict[str, float] = {}
        for item in items:
            label = str(item.get(key) or "未分组")
            grouped[label] = grouped.get(label, 0.0) + float(item.get("amount") or 0)
        rows = []
        for label, value in sorted(grouped.items(), key=lambda pair: pair[1], reverse=True):
            weight = value / float(total_value or 1) * 100 if total_value else 0
            rows.append({"name": label, "value": round(value, 2), "valueText": _money(value), "weight": round(weight, 2), "weightText": _percent(weight)})
        return rows

    def _planned_dca_markers(self, fund_code: str, portfolio_item: dict, dates: list[str], range_label: str) -> list[dict]:
        try:
            amount = float(portfolio_item.get("fixedDailyBuyAmount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            return []
        if not dates:
            dates = collect_dates(self.home)
        selected_dates = self._filter_dates_for_range(sorted(set(str(item)[:10] for item in dates if item)), range_label)
        fund_name = portfolio_item.get("fundName") or fund_code
        return [
            {"date": item, "action": "计划定投", "amount": amount, "amountText": _money(amount), "fundCode": fund_code, "fundName": fund_name, "source": "planned_dca"}
            for item in selected_dates
        ]

    def _filter_dates_for_range(self, dates: list[str], range_label: str) -> list[str]:
        from datetime import date, timedelta

        if not dates:
            return []
        days_by_label = {"近1月": 31, "近3月": 93, "近6月": 186, "近1年": 366}
        days = days_by_label.get(_normalize_range_label(range_label))
        if days is None:
            return dates
        try:
            end = date.fromisoformat(dates[-1][:10])
        except ValueError:
            return dates[-60:]
        start = end - timedelta(days=days)
        return [item for item in dates if date.fromisoformat(item[:10]) >= start]

    def _system_payload(self, state: dict) -> dict:
        selected = str(state.get("selected_date", "") or today_str())
        today = today_str()
        workspace = self.home / "db" / "daily_workspace" / today
        today_decision = workspace / "today_decision.json"
        return {
            "sourceHealth": state.get("source_health", {}) or {},
            "todayManifest": state.get("today_intraday_manifest", {}) or {},
            "preflightStatus": (state.get("summary", {}) or {}).get("preflight_status", ""),
            "settings": state.get("settings", {}) or {},
            "dailyFirstOpen": {
                "selectedDate": selected,
                "today": today,
                "autoRunNeeded": selected == today and not today_decision.exists(),
                "todayWorkspace": str(workspace),
                "todayDecisionPath": str(today_decision),
                "todayDecisionExists": today_decision.exists(),
            },
        }


def _normalize_range_label(range_label: str) -> str:
    label = str(range_label or "").strip()
    aliases = {
        "1m": "近1月",
        "3m": "近3月",
        "6m": "近6月",
        "1y": "近1年",
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

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/dates":
                self._send_json(self.api.dates())
            elif parsed.path == "/api/snapshot":
                selected = (query.get("date") or [""])[0] or None
                self._send_json(self.api.snapshot(selected))
            elif parsed.path.startswith("/api/fund/"):
                fund_code = parsed.path.rsplit("/", 1)[-1].strip()
                selected = (query.get("date") or [""])[0] or None
                range_label = (query.get("range") or ["成立以来"])[0] or "成立以来"
                self._send_json(self.api.fund_detail(fund_code, selected, range_label))
            else:
                self._send_json({"error": "未找到"}, 404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or "0")
        payload = {}
        if length:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        try:
            if parsed.path == "/api/run/daily":
                self._send_json(self.api.run_task("daily", force=bool(payload.get("force"))))
            elif parsed.path == "/api/run/realtime":
                self._send_json(self.api.run_task("realtime"))
            elif parsed.path == "/api/copilot/explain":
                self._send_json(self.api.explain(payload))
            elif parsed.path == "/api/long-memory/action":
                self._send_json(self.api.long_memory_action(payload))
            else:
                self._send_json({"error": "未找到"}, 404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def log_message(self, format: str, *args) -> None:
        return


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run OKRA local web API.")
    parser.add_argument("--home", default=str(DEFAULT_HOME))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    RequestHandler.api = OkraWebApi(Path(args.home))
    server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
    print(f"OKRA web API listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
