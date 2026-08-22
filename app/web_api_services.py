from __future__ import annotations

import os
import json
import hashlib
import math
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from common import is_trading_day, timestamp_now
from execution_sync import (
    apply_saved_reconciliation,
    build_execution_sync_payload,
    parse_alipay_screenshot_upload,
    preview_reconciliation,
    register_reconciliation_fund,
    record_actual_trade,
    record_conversion,
    update_pending_confirmations,
)
from long_memory_store import approve_memory, can_promote_to_permanent, list_memory_records
from today_orchestrator import AlreadyRunningError, ensure_runtime_not_stale, get_active_runtime
from ui_support import build_daily_first_open_command, build_realtime_command, build_runtime_env, collect_dates, today_str
from ui_tasks import build_portfolio_alignment_command, desktop_log_path, portfolio_alignment_target_date, should_align_portfolio_on_boot
from web_api_format import money as _money
from web_api_format import percent as _percent
from web_api_format import markers as _markers
from web_api_format import series as _series
from web_api_format import to_jsonable as _to_jsonable
from workbench_history import (
    SeriesPoint,
    allocation_history,
    cap_points,
    collect_benchmark_history,
    collect_estimate_history,
    collect_holding_history,
    collect_portfolio_history,
    collect_proxy_history,
    collect_quote_history,
    collect_trade_markers,
    daily_return_series,
    drawdown_series,
    load_benchmark_mapping,
    normalized_series,
    stage_return,
)
from workbench_state import WorkbenchStateService


def _coerce_task_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return today_str()
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc


def _news_key(item: dict[str, Any]) -> str:
    return str(item.get("canonical_url") or item.get("source_url") or item.get("url") or item.get("title") or "")


def _news_id(item: dict[str, Any], index: int = 0) -> str:
    existing = str(item.get("news_id") or item.get("id") or "").strip()
    if existing:
        return existing
    parts = [
        str(item.get("canonical_url") or item.get("source_url") or item.get("url") or "").strip(),
        str(item.get("provider") or item.get("source_key") or item.get("source_name") or "").strip(),
        str(item.get("published_at") or item.get("date") or item.get("time") or "").strip(),
        str(item.get("title") or "").strip(),
        str(item.get("summary") or "").strip()[:160],
    ]
    seed = "\n".join(part for part in parts if part) or f"news-{index}"
    return f"news_{hashlib.sha1(seed.encode('utf-8', errors='ignore')).hexdigest()[:16]}"


def _with_news_ids(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        copied = dict(item)
        copied["news_id"] = _news_id(copied, index)
        enriched.append(copied)
    return enriched


def _unique_news_count(items: list[dict[str, Any]]) -> int:
    keys = {_news_key(item) for item in items if _news_key(item)}
    return len(keys) if keys else len(items)


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key, "") or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _cap_history_payload(payload: dict[str, Any], end_date: str) -> dict[str, Any]:
    capped: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, list) and value and isinstance(value[0], SeriesPoint):
            capped[key] = cap_points(value, end_date)
        else:
            capped[key] = value
    return capped


def _excess_series(fund_points: list[SeriesPoint], benchmark_points: list[SeriesPoint]) -> list[SeriesPoint]:
    benchmark_by_date = {point.date: point.value for point in benchmark_points}
    return [
        SeriesPoint(point.date, round(point.value - benchmark_by_date[point.date], 4))
        for point in fund_points
        if point.date in benchmark_by_date
    ]


def _decision_markers(research_item: dict[str, Any] | None, trade_markers: list[dict[str, Any]], selected_date: str) -> list[dict[str, Any]]:
    markers = list(trade_markers)
    if research_item:
        action = str(research_item.get("validated_action") or research_item.get("action") or "hold")
        if action:
            markers.append(
                {
                    "date": selected_date,
                    "type": "dca" if action in {"planned_dca", "scheduled_dca"} else "hold" if action in {"hold", "locked", "not_applicable"} else "sell" if action in {"sell", "reduce", "switch_out"} else "buy",
                    "label": str(research_item.get("_action_label") or action),
                    "amount": research_item.get("validated_amount") or research_item.get("amount"),
                    "source": "validated_advice",
                }
            )
    return sorted(markers, key=lambda item: str(item.get("date", "")))


def _positive_number(payload: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            if float(value) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _reject_shadow_mutation_payload(payload: dict[str, Any], *, endpoint: str) -> None:
    write_scope = str(payload.get("write_scope", "") or payload.get("writeScope", "") or "")
    artifact_kind = str(payload.get("artifact_kind", "") or payload.get("artifactKind", "") or "")
    markers = {
        "write_scope": write_scope,
        "artifact_kind": artifact_kind,
    }
    has_shadow_marker = (
        payload.get("non_executable") is True
        or payload.get("nonExecutable") is True
        or payload.get("display_only") is True
        or payload.get("displayOnly") is True
        or markers["write_scope"] in {"shadow_only", "learning_only", "review_only"}
        or any(token in markers["artifact_kind"] for token in ("shadow", "learning", "retrieval_pack", "action_debate", "official_advice_compat_preview"))
    )
    if has_shadow_marker:
        raise ValueError(f"{endpoint} does not accept shadow, display-only, or non-executable artifacts.")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def _source_health_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "source_count": len(items),
        "warning_count": sum(1 for item in items if str(item.get("status", "") or "") not in {"", "ok"}),
        "error_count": sum(int(item.get("error_count", 0) or 0) for item in items),
    }


def _rank_news_items(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    def sort_key(item: dict[str, Any]) -> tuple[float, int, str]:
        risk_rank = {"high": 3, "medium": 2, "low": 1}.get(str(item.get("risk_level", "") or ""), 0)
        return (_safe_float(item.get("heat_score"), 0.0), risk_rank, str(item.get("published_at", "") or ""))

    return [dict(item) for item in sorted(items, key=sort_key, reverse=True)[:limit]]


def _related_news_by_fund(items: list[dict[str, Any]], *, limit_per_fund: int) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in _rank_news_items(items, limit=len(items)):
        fund_code = str(item.get("code") or item.get("fund_code") or "")
        if not fund_code or fund_code == "GLOBAL":
            continue
        grouped.setdefault(fund_code, [])
        if len(grouped[fund_code]) < limit_per_fund:
            grouped[fund_code].append(item)
    return grouped


class TaskController:
    def __init__(self, home: Path):
        self.home = home
        self._run_lock = threading.Lock()
        self._alignment_lock = threading.Lock()
        self._realtime_process = None
        self._realtime_log_path = ""

    def run_portfolio_alignment_if_needed(self, *, force: bool = False) -> dict[str, Any]:
        with self._alignment_lock:
            if not force and not should_align_portfolio_on_boot(self.home):
                return {"ok": True, "task": "portfolio_alignment", "skipped": True, "reason": "portfolio_already_current"}
            run_date = portfolio_alignment_target_date(self.home)
            command = build_portfolio_alignment_command(self.home, run_date, force=force)
            env = {**os.environ, **build_runtime_env(self.home)}
            started_at = datetime.now()
            log_path = desktop_log_path(self.home, f"portfolio_alignment_{run_date.replace('-', '')}", started_at)
            with log_path.open("w", encoding="utf-8") as handle:
                completed = subprocess.run(command, cwd=str(self.home), env=env, stdout=handle, stderr=subprocess.STDOUT)
            if completed.returncode != 0:
                raise RuntimeError(f"portfolio alignment failed. See {log_path}")
            return {
                "ok": True,
                "task": "portfolio_alignment",
                "skipped": False,
                "runDate": run_date,
                "logPath": str(log_path),
            }

    def run_task(self, kind: str, *, force: bool = False, run_date: str | None = None, automatic: bool = False) -> dict[str, Any]:
        with self._run_lock:
            run_date = _coerce_task_date(run_date)
            if kind == "daily":
                active_runtime = get_active_runtime(self.home, run_date)
                if active_runtime:
                    raise AlreadyRunningError(active_runtime)
                if run_date == today_str():
                    alignment = self.run_portfolio_alignment_if_needed(force=False)
                else:
                    alignment = {"ok": True, "task": "portfolio_alignment", "skipped": True, "reason": "historical_daily_run"}
                command = build_daily_first_open_command(self.home, run_date, force=force, trigger="manual" if force else "auto")
                task_name = "today_analysis"
            elif kind == "realtime":
                run_date = today_str()
                if automatic and not is_trading_day(self.home, run_date):
                    return {
                        "ok": True,
                        "task": "realtime",
                        "pid": 0,
                        "runId": "",
                        "runDate": run_date,
                        "force": False,
                        "logPath": "",
                        "portfolioAlignment": {},
                        "alreadyRunning": False,
                        "skipped": True,
                        "reason": "non_trading_day",
                    }
                if self._realtime_process is not None and self._realtime_process.poll() is None:
                    return {
                        "ok": True,
                        "task": "realtime",
                        "pid": self._realtime_process.pid,
                        "runId": "",
                        "runDate": run_date,
                        "force": False,
                        "logPath": self._realtime_log_path,
                        "portfolioAlignment": {},
                        "alreadyRunning": True,
                    }
                command = build_realtime_command(self.home, run_date)
                task_name = "realtime"
                alignment = {}
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
            if kind == "realtime":
                self._realtime_process = process
                self._realtime_log_path = str(log_path)
            runtime: dict[str, Any] = {}
            if kind == "daily":
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
            "portfolioAlignment": alignment,
            "alreadyRunning": False,
        }


class ExecutionController:
    def __init__(self, home: Path):
        self.home = home

    def execution_sync_payload(self) -> dict[str, Any]:
        return _to_jsonable(build_execution_sync_payload(self.home))

    def execution_trade(self, payload: dict[str, Any]) -> dict[str, Any]:
        _reject_shadow_mutation_payload(payload, endpoint="execution trade")
        if not str(payload.get("fund_code", "") or "").strip():
            raise ValueError("fund_code is required")
        operation_type = str(payload.get("operation_type", "") or "").strip().lower()
        if operation_type not in {"buy", "sell", "add", "reduce", "fee", "dividend", "cancel"}:
            raise ValueError("operation_type must be buy, sell, add, reduce, fee, dividend, or cancel")
        if operation_type in {"buy", "sell", "add", "reduce"} and not _positive_number(payload, "amount", "units"):
            raise ValueError("amount or units must be greater than 0")
        return _to_jsonable(record_actual_trade(self.home, payload))

    def execution_conversion(self, payload: dict[str, Any]) -> dict[str, Any]:
        _reject_shadow_mutation_payload(payload, endpoint="execution conversion")
        out_code = str(payload.get("out_fund_code", "") or "").strip()
        in_code = str(payload.get("in_fund_code", "") or "").strip()
        if not out_code or not in_code:
            raise ValueError("out_fund_code and in_fund_code are required")
        if out_code == in_code:
            raise ValueError("conversion source and target funds must be different")
        if not _positive_number(payload, "out_amount", "out_units"):
            raise ValueError("out_amount or out_units must be greater than 0")
        return _to_jsonable(record_conversion(self.home, payload))

    def execution_screenshot_parse(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _to_jsonable(parse_alipay_screenshot_upload(self.home, payload))

    def execution_fund_lookup(self, payload: dict[str, Any]) -> dict[str, Any]:
        from fund_registry import search_fund_candidates

        return _to_jsonable(search_fund_candidates(str(payload.get("name") or "")))

    def execution_fund_register(self, payload: dict[str, Any]) -> dict[str, Any]:
        _reject_shadow_mutation_payload(payload, endpoint="execution fund register")
        if payload.get("userConfirmed") is not True:
            raise ValueError("userConfirmed=true is required")
        return _to_jsonable(
            register_reconciliation_fund(
                self.home,
                str(payload.get("reconcileId") or ""),
                expected_preview_sha256=str(payload.get("expectedPreviewSha256") or ""),
                display_name=str(payload.get("displayName") or ""),
                fund_code=str(payload.get("fundCode") or ""),
            )
        )

    def execution_reconcile_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("items", []) or payload.get("positions", []) or []
        snapshot_date = str(payload.get("snapshotDate") or payload.get("snapshot_date") or today_str())
        source = str(payload.get("source") or "manual_position_snapshot")
        return _to_jsonable(preview_reconciliation(self.home, items, snapshot_date=snapshot_date, source=source))

    def execution_reconcile_apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        _reject_shadow_mutation_payload(payload, endpoint="execution reconcile apply")
        reconcile_id = str(payload.get("reconcileId") or payload.get("reconcile_id") or "").strip()
        preview_sha256 = str(payload.get("previewSha256") or payload.get("preview_sha256") or "").strip()
        portfolio_sha256 = str(payload.get("expectedPortfolioStateSha256") or payload.get("expected_portfolio_state_sha256") or "").strip()
        if not reconcile_id or not preview_sha256 or not portfolio_sha256:
            raise ValueError("reconcileId, previewSha256, and expectedPortfolioStateSha256 are required")
        drop_missing = bool(payload.get("dropMissing") or payload.get("drop_missing"))
        if drop_missing and str(payload.get("confirmReplace") or payload.get("confirm_replace") or "").strip().upper() != "REPLACE":
            raise ValueError("confirmReplace=REPLACE is required when replacing all positions.")
        return _to_jsonable(
            apply_saved_reconciliation(
                self.home,
                reconcile_id,
                preview_sha256=preview_sha256,
                expected_portfolio_state_sha256=portfolio_sha256,
                drop_missing=drop_missing,
            )
        )

    def execution_confirmation_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        _reject_shadow_mutation_payload(payload, endpoint="execution confirmation update")
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

    def intelligence_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        llm_context = state.get("llm_context", {}) or {}
        selected = str(state.get("selected_date", "") or today_str())
        news_payload = self.read_json_file(self.home / "raw" / "news" / f"{selected}.json")
        news_items = _with_news_ids(list(news_payload.get("items", []) or []))
        source_health = state.get("source_health", {}) or {}
        source_health_items = list(source_health.get("items", []) or llm_context.get("source_health_summary", []) or news_payload.get("source_health", []) or [])
        news_digest = llm_context.get("news_digest", {}) or {}
        sentiment_digest = llm_context.get("sentiment_digest", {}) or {}
        event_risks = _with_news_ids(list(llm_context.get("event_risks", []) or []))
        unique_count = int(news_digest.get("unique_item_count") or (news_payload.get("dedup_summary", {}) or {}).get("unique_item_count") or _unique_news_count(news_items))
        mapped_count = int(news_digest.get("mapped_item_count") or (news_payload.get("dedup_summary", {}) or {}).get("mapped_item_count") or len(news_items))
        all_regulatory_items = [
            item
            for item in news_items
            if str(item.get("source_role", "") or "") == "regulatory_news"
            or str(item.get("evidence_type", "") or "") == "regulatory_notice"
        ]
        all_szse_items = [item for item in all_regulatory_items if "szse" in str(item.get("provider", "") or "").lower()]
        regulatory_items = _rank_news_items(all_regulatory_items, limit=12)
        szse_items = _rank_news_items(all_szse_items, limit=12)
        important_news = _rank_news_items(
            [
                item
                for item in news_items
                if _safe_float(item.get("heat_score"), 0.0) >= 0.65
                or str(item.get("risk_level", "") or "") in {"high", "medium"}
                or bool(item.get("is_policy_signal", False))
            ],
            limit=12,
        )
        if not important_news:
            important_news = _with_news_ids(list(news_digest.get("top_heat_items", []) or news_digest.get("latest", []) or [])[:12])
        return {
            "metrics": {
                "unique_news_count": unique_count,
                "mapped_news_count": mapped_count,
                "important_news_count": len(important_news),
                "regulatory_count": len(all_regulatory_items),
                "szse_count": len(all_szse_items),
                "source_count": len(source_health_items),
                "warning_source_count": sum(1 for item in source_health_items if str(item.get("status", "") or "") != "ok"),
                "text_sentiment_score": sentiment_digest.get("text_sentiment_score", sentiment_digest.get("sentiment_score", 0.0)),
                "heat_score": sentiment_digest.get("heat_score", 0.0),
                "derived_sentiment_score": sentiment_digest.get("derived_sentiment_score", 0.0),
            },
            "source_health": {"items": source_health_items, "summary": source_health.get("summary", {}) or _source_health_summary(source_health_items)},
            "news_digest": news_digest,
            "sentiment_digest": sentiment_digest,
            "important_news": important_news,
            "regulatory_items": regulatory_items,
            "szse_items": szse_items,
            "related_news_by_fund": _related_news_by_fund(news_items, limit_per_fund=6),
            "source_breakdown": news_digest.get("source_breakdown") or _count_by(news_items, "provider"),
            "event_risks": event_risks,
            "generated_at": news_payload.get("generated_at") or llm_context.get("generated_at") or "",
        }

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
            "intelligence": self.intelligence_payload(state),
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
        end_date = snapshot.selected_date
        quote_history = _cap_history_payload(quote_history, end_date)
        proxy_history = _cap_history_payload(proxy_history, end_date)
        holding_history = _cap_history_payload(holding_history, end_date)
        estimate_history = cap_points(estimate_history, end_date)
        trade_markers = [marker for marker in trade_markers if str(marker.date or "")[:10] <= end_date]
        nav_points = quote_history.get("nav", []) or []
        benchmark_mapping = load_benchmark_mapping(self.home, fund_code)
        benchmark_key = str(benchmark_mapping.get("benchmark_key") or "").strip()
        benchmark_history = collect_benchmark_history(self.home, benchmark_key, range_label) if benchmark_key else {"normalized": [], "day_change_pct": [], "name": ""}
        benchmark_points = cap_points(benchmark_history.get("normalized", []) or [], end_date)
        benchmark_day_points = cap_points(benchmark_history.get("change_pct", []) or [], end_date)
        excess_points = _excess_series(quote_history.get("nav_normalized", []) or [], benchmark_points)
        benchmark_status = "available" if benchmark_points else "missing_data" if benchmark_key else "not_configured"
        planned_dca_markers = self._planned_dca_markers(fund_code, portfolio_item or {}, snapshot.dates, range_label)
        planned_dca_markers = [item for item in planned_dca_markers if str(item.get("date", ""))[:10] <= end_date]
        decision_markers = _decision_markers(research_item, _markers(trade_markers) + planned_dca_markers, end_date)
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
                "benchmarkNormalized": _series(benchmark_points),
                "benchmarkDayChangePct": _series(benchmark_day_points),
                "drawdownPct": _series(drawdown_series(nav_points)),
                "excessReturnPct": _series(excess_points),
                "decisionMarkers": decision_markers,
            },
            "performance": {
                "stageReturn": stage_return(nav_points),
                "navSource": quote_history.get("source", ""),
                "proxySource": proxy_history.get("source", ""),
                "proxyName": proxy_history.get("name", ""),
                "benchmarkName": benchmark_history.get("name", "") or benchmark_mapping.get("benchmark_name", ""),
                "benchmarkKey": benchmark_key,
                "benchmarkStatus": benchmark_status,
            },
            "tradeMarkers": sorted(_markers(trade_markers) + planned_dca_markers, key=lambda item: item.get("date", "")),
            "longMemory": self.fund_long_memory_payload(fund_code),
            "system": system_payload(state),
        }

    def long_memory_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        _reject_shadow_mutation_payload(payload, endpoint="long memory action")
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
                    "officialDailyPnl": item.get("official_daily_pnl"),
                    "officialDailyPnlText": _money(item.get("official_daily_pnl") or 0) if item.get("official_daily_pnl") is not None else "暂无",
                    "officialDailyPnlDate": item.get("official_daily_pnl_date") or "",
                    "officialDailyPnlStatus": item.get("official_daily_pnl_status") or "",
                    "officialDailyPnlReason": item.get("official_daily_pnl_reason") or "",
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
        history_end_date = str(portfolio.get("as_of_date") or state.get("portfolio_date") or "")
        history = collect_portfolio_history(self.home, "成立以来", end_date=history_end_date)
        total_points = history.get("total_value", []) or []
        normalized_points = normalized_series(total_points)
        daily_points = daily_return_series(total_points)
        drawdown_points = drawdown_series(total_points)
        style_history = allocation_history(self.home, "style_group", "成立以来", end_date=history_end_date)
        role_history = allocation_history(self.home, "role", "成立以来", end_date=history_end_date)
        realtime = state.get("live_realtime", {}) or state.get("realtime", {}) or {}
        realtime_map = {str(item.get("fund_code") or ""): item for item in realtime.get("items", []) or []}
        risk_scatter = []
        for item in items:
            realtime_item = realtime_map.get(str(item.get("fundCode") or ""), {})
            weight = float(item.get("weight") or 0)
            if abs(weight) <= 1:
                weight *= 100.0
            risk_scatter.append(
                {
                    "fundCode": item.get("fundCode", ""),
                    "fundName": item.get("fundName", ""),
                    "weightPct": round(weight, 4),
                    "anomalyScore": round(float(realtime_item.get("anomaly_score", 0) or 0), 4),
                    "holdingPnl": round(float(item.get("holdingPnl") or 0), 4),
                    "styleGroup": item.get("styleGroup") or "未归类",
                }
            )
        top_style_weight = max((float(row.get("weight") or 0) for row in self.group_items(items, "styleGroup", total_value)), default=0.0)
        top_holding_weight = max(
            ((float(item.get("weight") or 0) * 100.0 if abs(float(item.get("weight") or 0)) <= 1 else float(item.get("weight") or 0)) for item in items),
            default=None,
        )
        current_drawdown = drawdown_points[-1].value if drawdown_points else None
        max_drawdown = min((point.value for point in drawdown_points), default=None)
        cash_weight = float(cash or 0) / float(total_value or 1) * 100.0 if total_value else None
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
                "totalValueNormalized": _series(normalized_points),
                "dailyReturnPct": _series(daily_points),
                "drawdownPct": _series(drawdown_points),
                "styleAllocationHistory": style_history,
                "roleAllocationHistory": role_history,
            },
            "riskSnapshot": {
                "currentDrawdownPct": current_drawdown,
                "maxDrawdownPct": max_drawdown,
                "cashWeightPct": round(cash_weight, 4) if cash_weight is not None else None,
                "topHoldingWeightPct": round(top_holding_weight, 4) if top_holding_weight is not None else None,
                "topStyleWeightPct": round(top_style_weight, 4),
                "asOfDate": portfolio.get("as_of_date") or state.get("portfolio_date") or "",
            },
            "riskScatter": risk_scatter,
            "benchmark": {"status": "not_configured", "normalized": [], "excessReturnPct": []},
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
            "phase": runtime.get("phase", ""),
            "reportDate": runtime.get("reportDate", ""),
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
            "failureType": runtime.get("failureType", ""),
            "retryable": runtime.get("retryable"),
            "degradationMode": runtime.get("degradationMode", ""),
            "decisionMode": runtime.get("decisionMode", ""),
            "executionEligible": runtime.get("executionEligible"),
            "committeeReady": runtime.get("committeeReady"),
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

    def system_payload(self, state: dict[str, Any], *, include_full_rag: bool = False) -> dict[str, Any]:
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
        today_analysis_runtime_payload = self.normalize_today_runtime_payload(ensure_runtime_not_stale(self.home, selected))
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
                "baseUrl": "[hidden]",
                "baseUrlConfigured": bool(((llm_config.get("model_providers", {}) or {}).get(str(llm_config.get("model_provider", "") or ""), {}) or {}).get("base_url", "")),
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
            "ragRuntime": self.rag_runtime_payload(full=include_full_rag),
        }

    def rag_runtime_payload(self, *, full: bool = True) -> dict[str, Any]:
        if not full:
            return self.lightweight_rag_runtime_payload()
        try:
            from rag_maintenance import rag_status

            payload = rag_status(self.home)
            payload["statusMode"] = "full"
            return payload
        except Exception as exc:
            return self.empty_rag_runtime_payload(status_error=str(exc), status_mode="full")

    def lightweight_rag_runtime_payload(self) -> dict[str, Any]:
        try:
            from rag_config import load_rag_config, rag_db_path

            config = load_rag_config(self.home)
            settings = config.get("rag", {}) or {}
            db_path = rag_db_path(self.home, config)
            return {
                "generatedAt": timestamp_now(),
                "enabled": bool(settings.get("enabled", False)),
                "defaultProfile": str(settings.get("default_profile", "") or ""),
                "fallbackToLegacy": bool(settings.get("fallback_to_legacy", True)),
                "traceEnabled": bool(settings.get("trace_enabled", True)),
                "agentShadow": settings.get("agent_shadow", {}) or {},
                "agentDefault": settings.get("agent_default", {}) or {},
                "profileEvidence": settings.get("profile_evidence", {}) or {},
                "embedding": settings.get("embedding", {}) or {},
                "vectorStore": settings.get("vector_store", {}) or {},
                "dbPath": str(db_path),
                "dbExists": db_path.exists(),
                "counts": {},
                "sourceCounts": {},
                "embeddingStatus": {},
                "latestIngestRuns": [],
                "latestTraces": [],
                "activeManifests": [],
                "latestEval": {},
                "statusMode": "lightweight",
            }
        except Exception as exc:
            return self.empty_rag_runtime_payload(status_error=str(exc), status_mode="lightweight")

    def empty_rag_runtime_payload(self, *, status_error: str, status_mode: str) -> dict[str, Any]:
        return {
            "generatedAt": timestamp_now(),
            "enabled": False,
            "defaultProfile": "",
            "fallbackToLegacy": True,
            "traceEnabled": False,
            "dbPath": "",
            "dbExists": False,
            "statusError": status_error,
            "counts": {},
            "sourceCounts": {},
            "embeddingStatus": {},
            "agentShadow": {},
            "agentDefault": {},
            "profileEvidence": {},
            "embedding": {},
            "vectorStore": {},
            "latestEval": {},
            "latestTraces": [],
            "latestIngestRuns": [],
            "activeManifests": [],
            "statusMode": status_mode,
        }
