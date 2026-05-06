from __future__ import annotations

import base64
import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from common import (
    dump_json,
    ensure_layout,
    load_json,
    load_portfolio,
    resolve_date,
    timestamp_now,
    trade_journal_path,
    validated_advice_path,
)
from portfolio_state import save_portfolio_state, upsert_execution_status
from trade_lifecycle import lifecycle_status, resolve_trade_lifecycle
from update_portfolio_from_trade import apply_trade


def execution_sync_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "execution_sync"


def actual_trade_path(agent_home: Path, trade_date: str) -> Path:
    return execution_sync_dir(agent_home) / "actual_trades" / f"{trade_date}.json"


def position_snapshot_path(agent_home: Path, snapshot_date: str) -> Path:
    return execution_sync_dir(agent_home) / "position_snapshots" / f"{snapshot_date}.json"


def pending_confirmations_path(agent_home: Path) -> Path:
    return execution_sync_dir(agent_home) / "pending_confirmations.json"


def reconciliation_report_path(agent_home: Path, report_date: str) -> Path:
    return execution_sync_dir(agent_home) / "reconciliation_reports" / f"{report_date}.json"


def parsed_import_path(agent_home: Path, import_id: str) -> Path:
    return execution_sync_dir(agent_home) / "imports" / "parsed" / f"{import_id}.json"


def alipay_screenshot_dir(agent_home: Path) -> Path:
    return execution_sync_dir(agent_home) / "imports" / "alipay_screenshots"


def _money(value: Any) -> float:
    try:
        return round(float(value or 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def _units(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def load_actual_trades(agent_home: Path, limit: int = 200) -> list[dict[str, Any]]:
    base = execution_sync_dir(agent_home) / "actual_trades"
    items: list[dict[str, Any]] = []
    if base.exists():
        for path in sorted(base.glob("*.json"), reverse=True):
            payload = load_json(path)
            for item in payload.get("items", []) or []:
                items.append({**item, "source_path": str(path)})
                if len(items) >= limit:
                    return items
    return items


def load_pending_confirmations(agent_home: Path) -> dict[str, Any]:
    path = pending_confirmations_path(agent_home)
    if not path.exists():
        return {"updated_at": "", "items": []}
    return load_json(path)


def _write_pending_confirmations(agent_home: Path, items: list[dict[str, Any]]) -> Path:
    active = [item for item in items if item.get("status") not in {"settled", "canceled", "failed"}]
    active.sort(key=lambda item: (item.get("confirm_date", ""), item.get("settlement_date", ""), item.get("trade_id", item.get("conversion_id", ""))))
    return dump_json(pending_confirmations_path(agent_home), {"updated_at": timestamp_now(), "items": active})


def _append_actual_trade(agent_home: Path, trade_date: str, item: dict[str, Any]) -> Path:
    path = actual_trade_path(agent_home, trade_date)
    payload = load_json(path) if path.exists() else {"trade_date": trade_date, "items": []}
    items = [entry for entry in payload.get("items", []) or [] if entry.get("trade_id") != item.get("trade_id")]
    items.append(item)
    payload["trade_date"] = trade_date
    payload["updated_at"] = timestamp_now()
    payload["items"] = items
    return dump_json(path, payload)


def _update_actual_trade_record(agent_home: Path, item: dict[str, Any]) -> Path | None:
    trade_date = str(item.get("trade_date") or "")
    trade_id = str(item.get("trade_id") or "")
    if not trade_date or not trade_id:
        return None
    path = actual_trade_path(agent_home, trade_date)
    if not path.exists():
        return None
    payload = load_json(path)
    changed = False
    updated_items = []
    for entry in payload.get("items", []) or []:
        if str(entry.get("trade_id", "")) == trade_id:
            merged = dict(entry)
            merged.update(item)
            updated_items.append(merged)
            changed = True
        else:
            updated_items.append(entry)
    if not changed:
        return None
    payload["items"] = updated_items
    payload["updated_at"] = timestamp_now()
    return dump_json(path, payload)


def _append_legacy_trade_journal(agent_home: Path, trade_date: str, item: dict[str, Any]) -> Path:
    path = trade_journal_path(agent_home, trade_date)
    payload = load_json(path) if path.exists() else {"trade_date": trade_date, "items": []}
    legacy_action = {
        "buy": "buy",
        "dca": "buy",
        "sell": "sell",
        "convert_out": "switch_out",
        "convert_in": "switch_in",
    }.get(str(item.get("operation_type", "")), str(item.get("operation_type", "")))
    legacy = {
        "fund_code": item.get("fund_code", ""),
        "fund_name": item.get("fund_name", ""),
        "action": legacy_action,
        "amount": item.get("amount", 0.0),
        "trade_nav": item.get("nav"),
        "units": item.get("units"),
        "note": item.get("user_note", ""),
        "trade_id": item.get("trade_id", ""),
        "source": item.get("source", "manual"),
        "execution_deviation": item.get("execution_deviation", {}),
    }
    if item.get("linked_suggestion_id"):
        legacy["suggestion_id"] = item.get("linked_suggestion_id")
        legacy["suggestion_date"] = item.get("linked_advice_date", trade_date)
    payload["items"] = [entry for entry in payload.get("items", []) or [] if entry.get("trade_id") != item.get("trade_id")]
    payload["items"].append(legacy)
    return dump_json(path, payload)


def match_suggestion(agent_home: Path, advice_date: str, fund_code: str, operation_type: str, suggestion_id: str = "") -> dict[str, Any] | None:
    path = validated_advice_path(agent_home, advice_date)
    if not path.exists():
        return None
    payload = load_json(path)
    wanted = {
        "buy": {"add", "scheduled_dca", "planned_dca"},
        "dca": {"add", "scheduled_dca", "planned_dca"},
        "sell": {"reduce"},
        "convert_out": {"reduce", "switch_out"},
        "convert_in": {"add", "switch_in"},
    }.get(operation_type, set())
    for section in ("tactical_actions", "dca_actions", "hold_actions"):
        for item in payload.get(section, []) or []:
            if suggestion_id and item.get("suggestion_id") == suggestion_id:
                return item
            if item.get("fund_code") == fund_code and item.get("validated_action") in wanted:
                return item
    return None


def build_execution_deviation(agent_home: Path, item: dict[str, Any]) -> dict[str, Any]:
    advice_date = str(item.get("linked_advice_date") or item.get("trade_date") or "")
    suggestion = match_suggestion(agent_home, advice_date, str(item.get("fund_code", "")), str(item.get("operation_type", "")), str(item.get("linked_suggestion_id", "")))
    if not suggestion:
        return {"type": "unlinked", "label": "未关联系统建议", "affects_advice_accuracy": False}
    suggested_amount = _money(suggestion.get("validated_amount"))
    actual_amount = _money(item.get("amount"))
    suggested_action = str(suggestion.get("validated_action", ""))
    operation = str(item.get("operation_type", ""))
    direction_match = (
        operation in {"buy", "dca", "convert_in"} and suggested_action in {"add", "scheduled_dca", "planned_dca"}
    ) or (operation in {"sell", "convert_out"} and suggested_action in {"reduce", "switch_out"})
    amount_delta = round(actual_amount - suggested_amount, 2)
    if not direction_match:
        deviation_type = "opposite_direction"
        label = "方向相反"
    elif suggested_amount > 0 and 0 < actual_amount < suggested_amount:
        deviation_type = "partial_execution"
        label = "部分执行"
    elif amount_delta != 0:
        deviation_type = "amount_delta"
        label = "金额偏差"
    else:
        deviation_type = "matched"
        label = "按建议执行"
    return {
        "type": deviation_type,
        "label": label,
        "affects_advice_accuracy": False,
        "suggestion_id": suggestion.get("suggestion_id", ""),
        "suggested_action": suggested_action,
        "suggested_amount": suggested_amount,
        "actual_amount": actual_amount,
        "amount_delta": amount_delta,
    }


def record_actual_trade(agent_home: Path, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_layout(agent_home)
    operation = str(payload.get("operation_type") or payload.get("action") or "buy").strip()
    if operation == "planned_dca":
        operation = "dca"
    if operation not in {"buy", "sell", "dca", "dividend", "fee", "cancel"}:
        raise ValueError(f"Unsupported operation_type: {operation}")
    trade_date = resolve_date(str(payload.get("trade_date") or payload.get("date") or "") or None)
    trade_time = str(payload.get("trade_time", "") or "")
    lifecycle = resolve_trade_lifecycle(
        agent_home,
        fund_code=str(payload.get("fund_code", "")),
        operation_type=operation,
        trade_date=trade_date,
        trade_time=trade_time,
        confirm_date=str(payload.get("confirm_date", "") or ""),
        settlement_date=str(payload.get("settlement_date", "") or ""),
    )
    item = {
        "trade_id": str(payload.get("trade_id") or _new_id("trade")),
        "source": str(payload.get("source") or "manual"),
        "platform": str(payload.get("platform") or "alipay"),
        "operation_type": operation,
        "trade_time": trade_time,
        "trade_date": trade_date,
        "effective_trade_date": lifecycle["effective_trade_date"],
        "fund_code": str(payload.get("fund_code", "")).strip(),
        "fund_name": str(payload.get("fund_name", "")).strip(),
        "amount": _money(payload.get("amount")),
        "units": _units(payload.get("units")),
        "nav": _units(payload.get("nav")),
        "fee": _money(payload.get("fee")),
        "status": str(payload.get("status") or "submitted"),
        "confirm_date": lifecycle["confirm_date"],
        "settlement_date": lifecycle["settlement_date"],
        "linked_suggestion_id": str(payload.get("linked_suggestion_id", "") or ""),
        "linked_advice_date": str(payload.get("linked_advice_date", "") or trade_date),
        "user_note": str(payload.get("user_note", "") or payload.get("note", "") or ""),
        "created_at": timestamp_now(),
        "updated_at": timestamp_now(),
        "lifecycle": lifecycle,
    }
    item["execution_deviation"] = build_execution_deviation(agent_home, item)
    path = _append_actual_trade(agent_home, trade_date, item)
    legacy_path = _append_legacy_trade_journal(agent_home, trade_date, item)
    pending = load_pending_confirmations(agent_home).get("items", []) or []
    pending = [entry for entry in pending if entry.get("trade_id") != item["trade_id"]]
    if item["status"] not in {"settled", "canceled", "failed"}:
        pending.append(item)
    _write_pending_confirmations(agent_home, pending)
    if item.get("linked_suggestion_id"):
        upsert_execution_status(
            agent_home,
            item["linked_advice_date"] or trade_date,
            {
                "suggestion_id": item.get("linked_suggestion_id"),
                "fund_code": item.get("fund_code"),
                "fund_name": item.get("fund_name"),
                "trade_action": operation,
                "trade_amount": item.get("amount"),
                "status": "executed" if item["status"] in {"confirmed", "settled"} else item["status"],
                "linked_trade_date": trade_date,
                "linked_note": item.get("user_note", ""),
                "execution_deviation": item.get("execution_deviation", {}),
            },
        )
    return {"ok": True, "trade": item, "path": str(path), "legacyTradeJournalPath": str(legacy_path)}


def record_conversion(agent_home: Path, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_layout(agent_home)
    trade_date = resolve_date(str(payload.get("trade_date") or payload.get("date") or "") or None)
    conversion_id = str(payload.get("conversion_id") or _new_id("conversion"))
    out_lifecycle = resolve_trade_lifecycle(
        agent_home,
        fund_code=str(payload.get("out_fund_code", "")),
        operation_type="convert_out",
        trade_date=trade_date,
        trade_time=str(payload.get("trade_time", "") or ""),
        confirm_date=str(payload.get("out_confirm_date", "") or ""),
    )
    in_lifecycle = resolve_trade_lifecycle(
        agent_home,
        fund_code=str(payload.get("in_fund_code", "")),
        operation_type="convert_in",
        trade_date=trade_date,
        trade_time=str(payload.get("trade_time", "") or ""),
        confirm_date=str(payload.get("in_confirm_date", "") or ""),
    )
    item = {
        "trade_id": conversion_id,
        "conversion_id": conversion_id,
        "source": str(payload.get("source") or "manual"),
        "platform": str(payload.get("platform") or "alipay"),
        "operation_type": "convert",
        "trade_time": str(payload.get("trade_time", "") or ""),
        "trade_date": trade_date,
        "out_fund_code": str(payload.get("out_fund_code", "")).strip(),
        "out_fund_name": str(payload.get("out_fund_name", "")).strip(),
        "out_amount": _money(payload.get("out_amount")),
        "out_units": _units(payload.get("out_units")),
        "out_nav": _units(payload.get("out_nav")),
        "in_fund_code": str(payload.get("in_fund_code", "")).strip(),
        "in_fund_name": str(payload.get("in_fund_name", "")).strip(),
        "in_amount": _money(payload.get("in_amount") or payload.get("out_amount")),
        "in_units": _units(payload.get("in_units")),
        "in_nav": _units(payload.get("in_nav")),
        "fee": _money(payload.get("fee")),
        "out_confirm_date": out_lifecycle["confirm_date"],
        "in_confirm_date": in_lifecycle["confirm_date"],
        "settlement_date": in_lifecycle["settlement_date"],
        "status": str(payload.get("status") or lifecycle_status(in_lifecycle, operation_type="convert_in")),
        "linked_suggestion_id": str(payload.get("linked_suggestion_id", "") or ""),
        "linked_advice_date": str(payload.get("linked_advice_date", "") or trade_date),
        "user_note": str(payload.get("user_note", "") or payload.get("note", "") or ""),
        "created_at": timestamp_now(),
        "updated_at": timestamp_now(),
        "lifecycle": {"out": out_lifecycle, "in": in_lifecycle},
        "execution_deviation": {"type": "conversion_substitute", "label": "转换替代执行", "affects_advice_accuracy": False},
    }
    path = _append_actual_trade(agent_home, trade_date, item)
    _append_legacy_trade_journal(
        agent_home,
        trade_date,
        {
            "trade_id": conversion_id + "_out",
            "operation_type": "convert_out",
            "fund_code": item["out_fund_code"],
            "fund_name": item["out_fund_name"],
            "amount": item["out_amount"],
            "units": item["out_units"],
            "nav": item["out_nav"],
            "source": item["source"],
            "user_note": item["user_note"],
            "execution_deviation": item["execution_deviation"],
        },
    )
    _append_legacy_trade_journal(
        agent_home,
        trade_date,
        {
            "trade_id": conversion_id + "_in",
            "operation_type": "convert_in",
            "fund_code": item["in_fund_code"],
            "fund_name": item["in_fund_name"],
            "amount": item["in_amount"],
            "units": item["in_units"],
            "nav": item["in_nav"],
            "source": item["source"],
            "user_note": item["user_note"],
            "execution_deviation": item["execution_deviation"],
        },
    )
    pending = load_pending_confirmations(agent_home).get("items", []) or []
    pending = [entry for entry in pending if entry.get("conversion_id") != conversion_id]
    if item["status"] not in {"settled", "canceled", "failed"}:
        pending.append(item)
    _write_pending_confirmations(agent_home, pending)
    return {"ok": True, "conversion": item, "path": str(path)}


def update_pending_confirmations(agent_home: Path, as_of: str | None = None) -> dict[str, Any]:
    as_of_date = resolve_date(as_of)
    pending = load_pending_confirmations(agent_home).get("items", []) or []
    updated: list[dict[str, Any]] = []
    settled = 0
    applied = 0
    apply_errors: list[dict[str, Any]] = []
    for item in pending:
        entry = dict(item)
        if entry.get("operation_type") == "convert":
            status = lifecycle_status((entry.get("lifecycle", {}) or {}).get("in", {}), as_of_date, operation_type="convert_in")
        else:
            status = lifecycle_status(entry.get("lifecycle", {}), as_of_date, operation_type=str(entry.get("operation_type", "")))
        entry["status"] = status
        entry["updated_at"] = timestamp_now()
        if status == "settled":
            settled += 1
            if not entry.get("portfolio_applied_at"):
                try:
                    apply_settled_trade_to_portfolio(agent_home, entry)
                    entry["portfolio_applied_at"] = timestamp_now()
                    entry["portfolio_applied_as_of"] = as_of_date
                    applied += 1
                except Exception as exc:
                    entry["portfolio_apply_error"] = str(exc)
                    apply_errors.append({"trade_id": entry.get("trade_id", ""), "error": str(exc)})
            _update_actual_trade_record(agent_home, entry)
        updated.append(entry)
    path = _write_pending_confirmations(agent_home, updated)
    return {
        "updated_at": timestamp_now(),
        "as_of": as_of_date,
        "settled_count": settled,
        "portfolio_applied_count": applied,
        "apply_errors": apply_errors,
        "pending_count": len(load_json(path).get("items", []) or []),
        "path": str(path),
    }


def preview_reconciliation(agent_home: Path, actual_positions: list[dict[str, Any]], *, snapshot_date: str, source: str = "manual") -> dict[str, Any]:
    portfolio = load_portfolio(agent_home)
    current_by_code = {str(item.get("fund_code", "")): item for item in portfolio.get("funds", []) or []}
    matched = []
    new_items = []
    seen: set[str] = set()
    for item in actual_positions:
        code = str(item.get("fund_code", "")).strip()
        if not code:
            continue
        seen.add(code)
        current = current_by_code.get(code, {})
        row = {
            "fund_code": code,
            "fund_name": str(item.get("fund_name") or current.get("fund_name") or ""),
            "current_value": _money(item.get("current_value")),
            "holding_units": _units(item.get("holding_units")),
            "cost_basis_value": _money(item.get("cost_basis_value")),
            "holding_pnl": _money(item.get("holding_pnl")),
            "holding_return_pct": float(item.get("holding_return_pct", 0.0) or 0.0),
            "before_current_value": _money(current.get("current_value")),
            "before_holding_units": _units(current.get("holding_units")),
            "delta_current_value": round(_money(item.get("current_value")) - _money(current.get("current_value")), 2),
            "status": "matched" if current else "new",
        }
        (matched if current else new_items).append(row)
    missing = [
        {"fund_code": code, "fund_name": item.get("fund_name", ""), "current_value": _money(item.get("current_value"))}
        for code, item in current_by_code.items()
        if code and code not in seen and _money(item.get("current_value")) > 0
    ]
    preview = {
        "reconcile_id": _new_id("reconcile"),
        "source": source,
        "platform": "alipay",
        "snapshot_date": snapshot_date,
        "generated_at": timestamp_now(),
        "matched_items": matched,
        "new_items": new_items,
        "missing_items": missing,
        "apply_ready": bool(matched or new_items),
        "warnings": ["应用前请确认本次来源就是你的真实仓位。", "截图或手动快照只会在确认应用后覆盖组合状态。"],
    }
    dump_json(parsed_import_path(agent_home, preview["reconcile_id"]), preview)
    return preview


def _position_row_from_preview(row: dict[str, Any]) -> dict[str, Any]:
    code = str(row.get("fund_code") or row.get("matched_fund_code") or "").strip()
    name = str(row.get("fund_name") or row.get("matched_fund_name") or row.get("display_name") or code)
    current_value = _money(row.get("current_value"))
    holding_pnl = row.get("holding_pnl")
    cost_basis = row.get("cost_basis_value", row.get("derived_cost_basis_value"))
    if cost_basis in (None, "") and holding_pnl not in (None, ""):
        cost_basis = round(max(0.0, current_value - _money(holding_pnl)), 2)
    return {
        "fund_code": code,
        "fund_name": name,
        "current_value": current_value,
        "holding_units": _units(row.get("holding_units")),
        "cost_basis_value": _money(cost_basis),
        "holding_pnl": _money(holding_pnl),
        "holding_return_pct": float(row.get("holding_return_pct", 0.0) or 0.0),
    }


def apply_reconciliation(agent_home: Path, preview: dict[str, Any], *, drop_missing: bool = False) -> dict[str, Any]:
    portfolio = deepcopy(load_portfolio(agent_home))
    current_by_code = {str(item.get("fund_code", "")): item for item in portfolio.get("funds", []) or []}
    snapshot_date = str(preview.get("snapshot_date") or preview.get("sync_date") or resolve_date())
    updated_codes: list[str] = []
    added_codes: list[str] = []
    rows = list(preview.get("matched_items", []) or []) + list(preview.get("new_items", []) or [])
    if not rows and preview.get("detected_holdings"):
        rows = [row for row in preview.get("detected_holdings", []) or [] if row.get("matched_fund_code") or row.get("fund_code")]
    for raw_row in rows:
        row = _position_row_from_preview(raw_row)
        code = str(row.get("fund_code", ""))
        if not code:
            continue
        fund = current_by_code.get(code)
        if not fund:
            fund = {
                "fund_code": code,
                "fund_name": row.get("fund_name", code),
                "role": "tactical",
                "style_group": "unknown",
                "allow_trade": True,
            }
            portfolio.setdefault("funds", []).append(fund)
            current_by_code[code] = fund
            added_codes.append(code)
        fund["current_value"] = _money(row.get("current_value"))
        if row.get("holding_units") not in (None, ""):
            fund["holding_units"] = _units(row.get("holding_units")) or 0.0
            fund["units_source"] = "actual_position_sync"
        if row.get("cost_basis_value") not in (None, ""):
            fund["cost_basis_value"] = _money(row.get("cost_basis_value"))
        if row.get("holding_pnl") not in (None, ""):
            fund["holding_pnl"] = _money(row.get("holding_pnl"))
        else:
            fund["holding_pnl"] = round(_money(fund.get("current_value")) - _money(fund.get("cost_basis_value")), 2)
        fund["holding_return_pct"] = float(row.get("holding_return_pct", fund.get("holding_return_pct", 0.0)) or 0.0)
        fund["last_valuation_date"] = snapshot_date
        updated_codes.append(code)
    dropped_codes: list[str] = []
    if drop_missing:
        missing_rows = list(preview.get("missing_items", []) or []) + list(preview.get("missing_portfolio_funds", []) or [])
        for row in missing_rows:
            fund = current_by_code.get(str(row.get("fund_code", "")))
            if fund:
                fund["current_value"] = 0.0
                fund["holding_units"] = 0.0
                fund["cost_basis_value"] = 0.0
                fund["holding_pnl"] = 0.0
                fund["holding_return_pct"] = 0.0
                fund["units_source"] = "actual_position_missing_zero"
                dropped_codes.append(str(row.get("fund_code", "")))
    portfolio["as_of_date"] = snapshot_date
    portfolio["total_value"] = round(sum(_money(item.get("current_value")) for item in portfolio.get("funds", []) or []), 2)
    portfolio["holding_pnl"] = round(sum(_money(item.get("holding_pnl")) for item in portfolio.get("funds", []) or []), 2)
    current_path, snapshot_path = save_portfolio_state(
        agent_home,
        portfolio,
        source=str(preview.get("source") or "actual_position_sync"),
        event_date=snapshot_date,
        event_type="actual_position_reconcile",
        extra_meta={
            "platform": preview.get("platform", "alipay"),
            "reconcile_id": preview.get("reconcile_id", ""),
            "updated_fund_codes": updated_codes,
            "added_fund_codes": added_codes,
            "dropped_missing_fund_codes": dropped_codes,
        },
    )
    position_payload = {
        "snapshot_date": snapshot_date,
        "source": preview.get("source", "manual"),
        "platform": preview.get("platform", "alipay"),
        "reconcile_id": preview.get("reconcile_id", "") or preview.get("import_id", ""),
        "portfolio": portfolio,
        "updated_at": timestamp_now(),
    }
    dump_json(position_snapshot_path(agent_home, snapshot_date), position_payload)
    report = {
        "ok": True,
        "snapshot_date": snapshot_date,
        "updated_fund_count": len(updated_codes),
        "updated_fund_codes": updated_codes,
        "added_fund_count": len(added_codes),
        "added_fund_codes": added_codes,
        "dropped_missing_count": len(dropped_codes),
        "dropped_missing_fund_codes": dropped_codes,
        "mode": "replace" if drop_missing else "update",
        "current_path": str(current_path),
        "snapshot_path": str(snapshot_path),
    }
    dump_json(reconciliation_report_path(agent_home, snapshot_date), report)
    return report


def parse_alipay_screenshot_upload(agent_home: Path, payload: dict[str, Any]) -> dict[str, Any]:
    import_id = str(payload.get("import_id") or _new_id("alipay"))
    files = payload.get("files", []) or []
    saved: list[str] = []
    for index, item in enumerate(files, start=1):
        name = str(item.get("name") or f"screenshot_{index}.png")
        safe_name = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in name)
        raw = str(item.get("data") or "")
        if "," in raw:
            raw = raw.split(",", 1)[1]
        target = alipay_screenshot_dir(agent_home) / import_id / safe_name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(base64.b64decode(raw))
        except Exception:
            target.write_text(str(item.get("data") or ""), encoding="utf-8")
        saved.append(str(target))
    preview = {
        "import_id": import_id,
        "source": "alipay_screenshot",
        "platform": "alipay",
        "snapshot_date": str(payload.get("snapshot_date") or resolve_date()),
        "saved_files": saved,
        "matched_items": [],
        "new_items": [],
        "missing_items": [],
        "apply_ready": False,
        "warnings": [
            "截图已保存到本地。第一版不会自动覆盖仓位，请在预览区手动校正识别结果后再应用。",
            "如需自动视觉识别，可继续接入已有 sync_portfolio_from_screenshots.py 的 LLM 解析流程。",
        ],
        "generated_at": timestamp_now(),
    }
    if payload.get("auto_parse", True) and saved:
        try:
            from sync_portfolio_from_screenshots import build_sync_preview, call_screenshot_vision

            image_paths = [Path(path) for path in saved]
            extracted = call_screenshot_vision(agent_home, image_paths, "alipay")
            recognized = build_sync_preview(
                agent_home,
                extracted.get("items", []) or [],
                image_paths,
                "alipay",
                str(preview["snapshot_date"]),
            )
            recognized["import_id"] = import_id
            recognized["reconcile_id"] = import_id
            recognized["source"] = "alipay_screenshot"
            recognized["platform"] = "alipay"
            recognized["snapshot_date"] = str(preview["snapshot_date"])
            recognized["saved_files"] = saved
            recognized["vision_warnings"] = extracted.get("warnings", []) or []
            recognized["transport_name"] = extracted.get("_transport_name", "")
            dump_json(parsed_import_path(agent_home, import_id), recognized)
            return recognized
        except Exception as exc:
            preview["warnings"].append(f"自动识别未完成：{exc}")
    dump_json(parsed_import_path(agent_home, import_id), preview)
    return preview


def build_execution_sync_payload(agent_home: Path) -> dict[str, Any]:
    pending = load_pending_confirmations(agent_home)
    trades = load_actual_trades(agent_home, limit=120)
    reports = []
    report_dir = execution_sync_dir(agent_home) / "reconciliation_reports"
    if report_dir.exists():
        for path in sorted(report_dir.glob("*.json"), reverse=True)[:20]:
            reports.append(load_json(path))
    deviations = [item for item in trades if (item.get("execution_deviation") or {}).get("type") not in {"", "matched", None}]
    return {
        "updatedAt": timestamp_now(),
        "pending": pending.get("items", []),
        "trades": trades,
        "deviations": deviations[:80],
        "reconciliationReports": reports,
        "counts": {
            "pending": len(pending.get("items", []) or []),
            "trades": len(trades),
            "deviations": len(deviations),
            "reports": len(reports),
        },
    }


def apply_settled_trade_to_portfolio(agent_home: Path, trade: dict[str, Any]) -> dict[str, Any]:
    portfolio = load_portfolio(agent_home)
    operation = str(trade.get("operation_type", ""))
    if operation == "convert":
        portfolio = apply_trade(portfolio, str(trade.get("out_fund_code", "")), "switch_out", _money(trade.get("out_amount")), trade_nav=trade.get("out_nav"), trade_units=trade.get("out_units"))
        portfolio = apply_trade(portfolio, str(trade.get("in_fund_code", "")), "switch_in", _money(trade.get("in_amount")), trade_nav=trade.get("in_nav"), trade_units=trade.get("in_units"))
    elif operation in {"buy", "dca"}:
        portfolio = apply_trade(portfolio, str(trade.get("fund_code", "")), "buy", _money(trade.get("amount")), trade_nav=trade.get("nav"), trade_units=trade.get("units"))
    elif operation == "sell":
        portfolio = apply_trade(portfolio, str(trade.get("fund_code", "")), "sell", _money(trade.get("amount")), trade_nav=trade.get("nav"), trade_units=trade.get("units"))
    else:
        return {"ok": False, "reason": f"operation {operation} does not update portfolio automatically"}
    current_path, snapshot_path = save_portfolio_state(
        agent_home,
        portfolio,
        source="actual_trade_settlement",
        event_date=str(trade.get("settlement_date") or trade.get("confirm_date") or trade.get("trade_date") or resolve_date()),
        event_type="actual_trade_settlement",
        extra_meta={"trade_id": trade.get("trade_id", ""), "conversion_id": trade.get("conversion_id", "")},
    )
    return {"ok": True, "current_path": str(current_path), "snapshot_path": str(snapshot_path)}
