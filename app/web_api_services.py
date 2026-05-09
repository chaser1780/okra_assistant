from __future__ import annotations

import os
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from common import timestamp_now
from execution_sync import (
    apply_reconciliation,
    build_execution_sync_payload,
    parse_alipay_screenshot_upload,
    preview_reconciliation,
    record_actual_trade,
    record_conversion,
    update_pending_confirmations,
)
from long_memory_store import approve_memory, can_promote_to_permanent, list_memory_records
from today_orchestrator import AlreadyRunningError, get_active_runtime
from ui_support import build_daily_first_open_command, build_realtime_command, build_runtime_env, collect_dates, today_str
from ui_tasks import desktop_log_path
from web_api_format import money as _money
from web_api_format import percent as _percent
from web_api_format import markers as _markers
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


class TaskController:
    def __init__(self, home: Path):
        self.home = home

    def run_task(self, kind: str, *, force: bool = False) -> dict[str, Any]:
        run_date = today_str()
        if kind == "daily":
            active_runtime = get_active_runtime(self.home, run_date)
            if active_runtime:
                raise AlreadyRunningError(active_runtime)
            command = build_daily_first_open_command(self.home, run_date, force=force)
            task_name = "today_analysis"
        elif kind == "realtime":
            command = build_realtime_command(self.home, run_date)
            task_name = "realtime"
        else:
            raise ValueError(f"Unsupported task: {kind}")
        env = {**os.environ, **build_runtime_env(self.home)}
        started_at = datetime.now()
        log_path = desktop_log_path(self.home, f"{task_name}_{run_date.replace('-', '')}", started_at)
        handle = log_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=str(self.home), env=env, stdout=handle, stderr=subprocess.STDOUT)
        finally:
            handle.close()
        runtime: dict[str, Any] = {}
        for _ in range(20):
            runtime = get_active_runtime(self.home, run_date)
            if runtime.get("runId"):
                break
            time.sleep(0.1)
        return {
            "ok": True,
            "task": task_name,
            "pid": process.pid,
            "runId": str(runtime.get("runId", "") or ""),
            "runDate": run_date,
            "force": force,
            "logPath": str(log_path),
        }


class ExecutionController:
    def __init__(self, home: Path):
        self.home = home

    def execution_sync_payload(self) -> dict[str, Any]:
        return _to_jsonable(build_execution_sync_payload(self.home))

    def execution_trade(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _to_jsonable(record_actual_trade(self.home, payload))

    def execution_conversion(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _to_jsonable(record_conversion(self.home, payload))

    def execution_screenshot_parse(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _to_jsonable(parse_alipay_screenshot_upload(self.home, payload))

    def execution_reconcile_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("items", []) or payload.get("positions", []) or []
        snapshot_date = str(payload.get("snapshotDate") or payload.get("snapshot_date") or today_str())
        source = str(payload.get("source") or "manual_position_snapshot")
        return _to_jsonable(preview_reconciliation(self.home, items, snapshot_date=snapshot_date, source=source))

    def execution_reconcile_apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        preview = payload.get("preview") or payload
        drop_missing = bool(payload.get("dropMissing") or payload.get("drop_missing"))
        return _to_jsonable(apply_reconciliation(self.home, preview, drop_missing=drop_missing))

    def execution_confirmation_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        as_of = str(payload.get("date") or payload.get("asOf") or "") or None
        return _to_jsonable(update_pending_confirmations(self.home, as_of))


class PageService:
    def __init__(self, home: Path, state_service: WorkbenchStateService):
        self.home = home
        self.state_service = state_service
        self.execution_controller = ExecutionController(home)

    def dates(self) -> dict[str, Any]:
        return {"dates": collect_dates(self.home), "today": today_str()}

    def long_memory_payload(self) -> dict[str, Any]:
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

    def fund_long_memory_payload(self, fund_code: str) -> dict[str, Any]:
        fund_records = list_memory_records(self.home, domain="fund", entity_key=fund_code, limit=80)
        execution_records = list_memory_records(self.home, domain="execution", limit=80)
        portfolio_rules = [
            item
            for item in list_memory_records(self.home, domain="portfolio", limit=120)
            if item.get("status") in {"strategic", "permanent"}
        ]
        return {"fund": _to_jsonable(fund_records), "execution": _to_jsonable(execution_records[:12]), "rules": _to_jsonable(portfolio_rules[:12])}

    def snapshot(self, selected: str | None = None) -> dict[str, Any]:
        snapshot = self.state_service.load_snapshot(selected)
        dashboard = self.state_service.build_dashboard_view_model(snapshot)
        research = self.state_service.build_research_view_model(snapshot)
        realtime = self.state_service.build_realtime_view_model(snapshot)
        review = self.state_service.build_review_view_model(snapshot)
        state = snapshot.state
        today_analysis = self.today_analysis_payload(state)
        return {
            "selectedDate": snapshot.selected_date,
            "dates": snapshot.dates,
            "summary": _to_jsonable(snapshot.summary),
            "dashboard": _to_jsonable(dashboard),
            "portfolio": self.portfolio_payload(state),
            "research": _to_jsonable(research),
            "realtime": _to_jsonable(realtime),
            "review": _to_jsonable(review),
            "longMemory": self.long_memory_payload(),
            "executionSync": self.execution_controller.execution_sync_payload(),
            "todayAnalysis": today_analysis,
            "dailyFirstOpen": _to_jsonable(today_analysis),
            "system": self.system_payload(state),
        }

    def fund_detail(
        self,
        fund_code: str,
        selected: str | None,
        range_label: str,
        normalize_range_label,
        fund_analysis_detail,
        portfolio_payload,
        system_payload,
    ) -> dict[str, Any]:
        range_label = normalize_range_label(range_label)
        snapshot = self.state_service.load_snapshot(selected)
        state = snapshot.state
        portfolio = portfolio_payload(state)
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
            "analysisDetail": fund_analysis_detail(state.get("aggregate", {}) or {}, fund_code),
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
            "longMemory": self.fund_long_memory_payload(fund_code),
            "system": system_payload(state),
        }

    def long_memory_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        memory_id = str(payload.get("memoryId", "") or payload.get("memory_id", "") or "").strip()
        action = str(payload.get("action", "") or "").strip().lower()
        note = str(payload.get("note", "") or "").strip()
        if not memory_id:
            raise ValueError("memoryId is required")
        result = approve_memory(self.home, memory_id, action=action, note=note)
        return {"ok": True, "record": _to_jsonable(result)}

    def _planned_dca_markers(self, fund_code: str, portfolio_item: dict[str, Any], dates: list[str], range_label: str) -> list[dict[str, Any]]:
        marker_dates = [item for item in dates if item]
        if range_label == "近1月":
            marker_dates = marker_dates[-31:]
        if range_label == "近3月":
            marker_dates = marker_dates[-93:]
        if range_label == "近6月":
            marker_dates = marker_dates[-186:]
        if range_label == "近1年":
            marker_dates = marker_dates[-366:]
        amount = float(portfolio_item.get("fixedDailyBuyAmount", 0.0) or 0.0)
        if amount <= 0:
            return []
        return [
            {
                "date": date_text,
                "label": "计划定投",
                "kind": "scheduled_dca",
                "amount": amount,
                "fundCode": fund_code,
            }
            for date_text in marker_dates[-20:]
        ]

    def group_items(self, items: list[dict[str, Any]], key: str, total_value: float) -> list[dict[str, Any]]:
        grouped: dict[str, float] = {}
        for item in items:
            label = str(item.get(key) or "未分组")
            grouped[label] = grouped.get(label, 0.0) + float(item.get("amount") or 0)
        rows = []
        for label, value in sorted(grouped.items(), key=lambda pair: pair[1], reverse=True):
            weight = value / float(total_value or 1) * 100 if total_value else 0
            rows.append({"name": label, "value": round(value, 2), "valueText": _money(value), "weight": round(weight, 2), "weightText": _percent(weight)})
        return rows

    def portfolio_payload(self, state: dict[str, Any]) -> dict[str, Any]:
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
            "styleAllocation": self.group_items(items, "styleGroup", total_value),
            "roleAllocation": self.group_items(items, "role", total_value),
            "profitLeaders": sorted(items, key=lambda item: float(item.get("holdingPnl") or 0), reverse=True)[:5],
            "lossLeaders": sorted(items, key=lambda item: float(item.get("holdingPnl") or 0))[:5],
            "history": {
                "totalValue": _series(history.get("total_value", [])),
                "holdingPnl": _series(history.get("holding_pnl", [])),
                "holdingReturnPct": _series(history.get("holding_return_pct", [])),
            },
            "items": items,
        }

    def read_json_file(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def time_label(self, value: str) -> str:
        if not value:
            return ""
        try:
            return datetime.fromisoformat(value).strftime("%H:%M")
        except ValueError:
            return value

    def normalize_today_runtime_payload(self, payload: dict | None) -> dict[str, Any]:
        runtime = dict(payload or {})
        return {
            "runId": runtime.get("runId", ""),
            "pid": runtime.get("pid"),
            "status": runtime.get("status", ""),
            "startedAt": runtime.get("startedAt", ""),
            "endedAt": runtime.get("endedAt", ""),
            "heartbeatAt": runtime.get("heartbeatAt", runtime.get("startedAt", "")),
            "elapsedSeconds": runtime.get("elapsedSeconds", 0),
            "currentStep": runtime.get("currentStep", ""),
            "currentAgent": runtime.get("currentAgent", ""),
            "currentAgentStage": runtime.get("currentAgentStage", ""),
            "runningAgents": runtime.get("runningAgents", []),
            "failedAgents": runtime.get("failedAgents", []),
            "degradedAgents": runtime.get("degradedAgents", []),
            "lastError": runtime.get("lastError", ""),
            "analysisQuality": runtime.get("analysisQuality"),
            "memoryEligible": runtime.get("memoryEligible"),
            "resultReady": runtime.get("resultReady", False),
            "resultRunId": runtime.get("resultRunId", ""),
        }

    def today_analysis_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "decision": state.get("today_analysis_decision", {}) or state.get("daily_first_open", {}) or {},
            "analysis": state.get("today_analysis", {}) or state.get("daily_first_open_analysis", {}) or {},
            "meta": state.get("today_analysis_meta", {}) or state.get("daily_first_open_updates", {}) or {},
            "memoryCycle": state.get("today_analysis_memory_cycle", {}) or state.get("learning_cycle", {}) or {},
            "brief": state.get("daily_first_open_brief", "") or "",
        }

    def system_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        selected = str(state.get("selected_date", "") or today_str())
        today = today_str()
        llm_config = state.get("llm_config", {}) or {}
        aggregate = state.get("aggregate", {}) or {}
        workspace = self.home / "db" / "daily_workspace" / selected
        today_decision = workspace / "today_decision.json"
        today_analysis = workspace / "today_analysis.json"
        today_analysis_meta = workspace / "today_analysis_meta.json"
        memory_cycle = workspace / "memory_cycle.json"
        today_analysis_runtime = workspace / "today_analysis_runtime.json"
        long_memory_runtime = workspace / "long_memory_runtime.json"
        today_decision_payload = state.get("today_analysis_decision", {}) or self.read_json_file(today_decision)
        today_analysis_payload = state.get("today_analysis", {}) or self.read_json_file(today_analysis)
        today_analysis_meta_payload = state.get("today_analysis_meta", {}) or self.read_json_file(today_analysis_meta)
        memory_cycle_payload = state.get("today_analysis_memory_cycle", {}) or self.read_json_file(memory_cycle)
        today_analysis_runtime_payload = self.normalize_today_runtime_payload(self.read_json_file(today_analysis_runtime))
        long_memory_runtime_payload = self.read_json_file(long_memory_runtime)
        generated_at = str(
            today_analysis_meta_payload.get("runAt")
            or today_analysis_meta_payload.get("run_at")
            or today_decision_payload.get("generated_at")
            or today_analysis_payload.get("generated_at")
            or ""
        )
        if not generated_at and today_decision.exists():
            generated_at = datetime.fromtimestamp(today_decision.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        analysis_quality = today_analysis_meta_payload.get("analysis_quality")
        memory_eligible = today_analysis_meta_payload.get("memory_eligible")
        task_name = (
            today_analysis_meta_payload.get("task")
            or today_decision_payload.get("task")
            or ("today_analysis" if today_decision.exists() or today_analysis.exists() else "")
        )
        today_analysis_system = {
            "selectedDate": selected,
            "today": today,
            "autoRunNeeded": selected == today and not today_decision.exists(),
            "todayWorkspace": str(workspace),
            "todayDecisionPath": str(today_decision),
            "todayAnalysisPath": str(today_analysis),
            "todayAnalysisMetaPath": str(today_analysis_meta),
            "memoryCyclePath": str(memory_cycle),
            "todayDecisionExists": today_decision.exists(),
            "todayAnalysisExists": today_analysis.exists(),
            "todayAnalysisMetaExists": today_analysis_meta.exists(),
            "memoryCycleExists": memory_cycle.exists(),
            "hasRunToday": today_decision.exists() or today_analysis.exists(),
            "task": task_name,
            "analysis_quality": analysis_quality,
            "memory_eligible": memory_eligible,
            "runAt": generated_at,
            "runTime": self.time_label(generated_at),
            "memoryCycleSummary": memory_cycle_payload.get("summary", {}) if isinstance(memory_cycle_payload, dict) else {},
        }
        return {
            "sourceHealth": state.get("source_health", {}) or {},
            "preflightStatus": (state.get("summary", {}) or {}).get("preflight_status", ""),
            "settings": state.get("settings", {}) or {},
            "llmRuntime": {
                "modelProvider": llm_config.get("model_provider", ""),
                "model": llm_config.get("model", ""),
                "reviewModel": llm_config.get("review_model", ""),
                "reasoningEffort": llm_config.get("model_reasoning_effort", ""),
                "wireApi": ((llm_config.get("model_providers", {}) or {}).get(str(llm_config.get("model_provider", "") or ""), {}) or {}).get("wire_api", ""),
                "baseUrl": ((llm_config.get("model_providers", {}) or {}).get(str(llm_config.get("model_provider", "") or ""), {}) or {}).get("base_url", ""),
            },
            "todayAnalysisRuntime": today_analysis_runtime_payload,
            "longMemoryRuntime": long_memory_runtime_payload,
            "agentRuntime": {
                "failedAgents": aggregate.get("failed_agents", []),
                "degradedAgents": aggregate.get("degraded_agent_names", []),
                "orderedAgents": aggregate.get("ordered_agents", []),
                "stageStatus": aggregate.get("stage_status", {}),
                "committeeReady": aggregate.get("committee_ready", False),
                "workflowTrace": aggregate.get("workflow_trace", {}),
            },
            "todayAnalysis": today_analysis_system,
            "dailyFirstOpen": dict(today_analysis_system),
        }
