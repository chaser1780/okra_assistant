from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from common import (
    actual_trade_dir,
    dump_json,
    ensure_layout,
    actual_trade_path,
    file_lock,
    load_json,
    load_portfolio,
    lock_path,
    project_relative_path,
    resolve_date,
    settlement_event_path,
    timestamp_now,
    validated_advice_path,
)
from portfolio_state import _save_portfolio_state_unlocked, portfolio_state_event_path, portfolio_state_hash, upsert_execution_status
from trade_lifecycle import lifecycle_status, resolve_trade_lifecycle
from update_portfolio_from_trade import apply_trade


def execution_sync_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "execution_sync"


def position_snapshot_path(agent_home: Path, snapshot_date: str) -> Path:
    return execution_sync_dir(agent_home) / "position_snapshots" / f"{snapshot_date}.json"


def pending_confirmations_path(agent_home: Path) -> Path:
    return execution_sync_dir(agent_home) / "pending_confirmations.json"


def reconciliation_report_path(agent_home: Path, report_date: str) -> Path:
    return execution_sync_dir(agent_home) / "reconciliation_reports" / f"{report_date}.json"


def parsed_import_path(agent_home: Path, import_id: str) -> Path:
    return execution_sync_dir(agent_home) / "imports" / "parsed" / f"{import_id}.json"


def reconciliation_applied_path(agent_home: Path, reconcile_id: str) -> Path:
    return execution_sync_dir(agent_home) / "reconciliation_applied" / f"{reconcile_id}.json"


def alipay_screenshot_dir(agent_home: Path) -> Path:
    return execution_sync_dir(agent_home) / "imports" / "alipay_screenshots"


SETTLEMENT_JOURNAL_SCHEMA_VERSION = "settlement_journal.v2"
MAX_SCREENSHOT_FILES = 4
MAX_SCREENSHOT_FILE_BYTES = 10 * 1024 * 1024
MAX_SCREENSHOT_TOTAL_BYTES = 24 * 1024 * 1024
IMPORT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def settlement_journal_path(agent_home: Path, idempotency_key: str) -> Path:
    return execution_sync_dir(agent_home) / "settlement_journal" / settlement_event_path(agent_home, idempotency_key).name


def _money(value: Any) -> float:
    try:
        return round(float(value or 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def _optional_money(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


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
    base = actual_trade_dir(agent_home)
    items: list[dict[str, Any]] = []
    if base.exists():
        for path in sorted(base.glob("*.json"), reverse=True):
            payload = load_json(path)
            for item in payload.get("items", []) or []:
                items.append({**item, "source_path": project_relative_path(agent_home, path)})
                if len(items) >= limit:
                    return items
    return items


def load_pending_confirmations(agent_home: Path) -> dict[str, Any]:
    path = pending_confirmations_path(agent_home)
    if not path.exists():
        return {"updated_at": "", "items": []}
    return load_json(path)


def _write_pending_confirmations(agent_home: Path, items: list[dict[str, Any]]) -> Path:
    active = [
        item
        for item in items
        if item.get("status") not in {"canceled", "failed"}
        and (item.get("status") != "settled" or not item.get("portfolio_applied_at"))
    ]
    active.sort(key=lambda item: (item.get("confirm_date", ""), item.get("settlement_date", ""), item.get("trade_id", item.get("conversion_id", ""))))
    return dump_json(pending_confirmations_path(agent_home), {"updated_at": timestamp_now(), "items": active})


def _with_source_path(agent_home: Path, item: dict[str, Any], path: Path) -> dict[str, Any]:
    return {**item, "source_path": project_relative_path(agent_home, path)}


def _append_actual_trade(agent_home: Path, trade_date: str, item: dict[str, Any]) -> Path:
    path = actual_trade_path(agent_home, trade_date)
    payload = load_json(path) if path.exists() else {"trade_date": trade_date, "items": []}
    items = [entry for entry in payload.get("items", []) or [] if entry.get("trade_id") != item.get("trade_id")]
    items.append(_with_source_path(agent_home, item, path))
    payload["trade_date"] = trade_date
    payload["updated_at"] = timestamp_now()
    payload["items"] = items
    return dump_json(path, payload)


def _record_identity_digest(item: dict[str, Any]) -> str:
    stable = {
        key: item.get(key)
        for key in (
            "trade_id", "conversion_id", "trade_date", "trade_time", "operation_type",
            "fund_code", "fund_name", "amount", "units", "nav", "fee",
            "out_fund_code", "out_fund_name", "out_amount", "out_units", "out_nav",
            "in_fund_code", "in_fund_name", "in_amount", "in_units", "in_nav",
            "status", "linked_suggestion_id", "linked_advice_date", "source", "platform", "user_note",
        )
    }
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _find_record_by_trade_id(agent_home: Path, trade_id: str) -> tuple[dict[str, Any], Path] | None:
    if not trade_id:
        return None
    for path in sorted(actual_trade_dir(agent_home).glob("*.json")):
        payload = load_json(path)
        for item in payload.get("items", []) or []:
            if str(item.get("trade_id", "") or "") == trade_id:
                return dict(item), path
    return None


def _existing_record_result(agent_home: Path, item: dict[str, Any], *, result_key: str) -> dict[str, Any] | None:
    existing = _find_record_by_trade_id(agent_home, str(item.get("trade_id", "") or ""))
    if existing is None:
        return None
    existing_item, path = existing
    if _record_identity_digest(existing_item) != _record_identity_digest(item):
        raise ValueError("trade_id already exists with a different execution payload")
    return {
        "ok": True,
        result_key: existing_item,
        "path": project_relative_path(agent_home, path),
        "idempotent_replay": True,
    }


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


def settlement_idempotency_key(trade: dict[str, Any]) -> str:
    trade_id = str(trade.get("trade_id") or trade.get("conversion_id") or "")
    if trade_id:
        return trade_id
    parts = [
        str(trade.get("trade_date", "")),
        str(trade.get("settlement_date", "")),
        str(trade.get("operation_type", "")),
        str(trade.get("fund_code") or trade.get("out_fund_code", "")),
        str(trade.get("amount") or trade.get("out_amount", "")),
    ]
    return "_".join(part for part in parts if part) or _new_id("settlement")


def settlement_event_exists(agent_home: Path, trade: dict[str, Any]) -> bool:
    return settlement_event_path(agent_home, settlement_idempotency_key(trade)).exists()


def _settlement_trade_digest(trade: dict[str, Any]) -> str:
    stable_fields = {
        key: trade.get(key)
        for key in (
            "trade_id",
            "conversion_id",
            "trade_date",
            "confirm_date",
            "settlement_date",
            "operation_type",
            "fund_code",
            "amount",
            "units",
            "nav",
            "out_fund_code",
            "out_amount",
            "out_units",
            "out_nav",
            "in_fund_code",
            "in_amount",
            "in_units",
            "in_nav",
        )
    }
    encoded = json.dumps(stable_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_settlement_journal(agent_home: Path, idempotency_key: str) -> dict[str, Any]:
    path = settlement_journal_path(agent_home, idempotency_key)
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def _write_settlement_journal(agent_home: Path, idempotency_key: str, payload: dict[str, Any]) -> Path:
    journal = dict(payload)
    journal["schema_version"] = SETTLEMENT_JOURNAL_SCHEMA_VERSION
    journal["idempotency_key"] = idempotency_key
    journal["updated_at"] = timestamp_now()
    return dump_json(settlement_journal_path(agent_home, idempotency_key), journal)


def _applied_settlement_ids(portfolio: dict[str, Any]) -> set[str]:
    metadata = portfolio.get("state_metadata", {}) or {}
    return {str(item) for item in (metadata.get("applied_settlement_ids", []) or []) if str(item)}


def _portfolio_settlement_event_path(agent_home: Path, trade: dict[str, Any], idempotency_key: str) -> Path:
    event_date = str(trade.get("settlement_date") or trade.get("confirm_date") or trade.get("trade_date") or resolve_date())
    return portfolio_state_event_path(agent_home, event_date, "actual_trade_settlement", idempotency_key)


def _portfolio_has_settlement(agent_home: Path, portfolio: dict[str, Any], trade: dict[str, Any], idempotency_key: str) -> bool:
    metadata = portfolio.get("state_metadata", {}) or {}
    if idempotency_key in _applied_settlement_ids(portfolio):
        return True
    if metadata.get("event_type") == "actual_trade_settlement" and str(metadata.get("event_id", "")) == idempotency_key:
        return True
    return _portfolio_settlement_event_path(agent_home, trade, idempotency_key).exists()


def _recovered_settlement_payload(
    agent_home: Path,
    trade: dict[str, Any],
    portfolio: dict[str, Any],
    idempotency_key: str,
    journal: dict[str, Any],
) -> dict[str, Any]:
    metadata = portfolio.get("state_metadata", {}) or {}
    return {
        "event_type": "actual_trade_settlement",
        "trade_id": trade.get("trade_id", ""),
        "conversion_id": trade.get("conversion_id", ""),
        "idempotency_key": idempotency_key,
        "before_state_hash": journal.get("before_state_hash", metadata.get("before_state_hash", "")),
        "after_state_hash": journal.get("after_state_hash", metadata.get("after_state_hash", portfolio_state_hash(portfolio))),
        "current_path": project_relative_path(agent_home, agent_home / "db" / "portfolio_state" / "current.json"),
        "snapshot_path": str(metadata.get("latest_snapshot_path", "") or ""),
        "source_path": str(trade.get("source_path", "")),
        "created_at": str(journal.get("created_at", "") or timestamp_now()),
        "recovered_at": timestamp_now(),
    }


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
    with file_lock(lock_path(agent_home, "execution_sync")):
        return _record_actual_trade_unlocked(agent_home, payload)


def _record_actual_trade_unlocked(agent_home: Path, payload: dict[str, Any]) -> dict[str, Any]:
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
    existing = _existing_record_result(agent_home, item, result_key="trade")
    if existing is not None:
        return existing
    path = _append_actual_trade(agent_home, trade_date, item)
    persisted_item = _with_source_path(agent_home, item, path)
    pending = load_pending_confirmations(agent_home).get("items", []) or []
    pending = [entry for entry in pending if entry.get("trade_id") != item["trade_id"]]
    if item["status"] not in {"settled", "canceled", "failed"}:
        pending.append(persisted_item)
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
    return {"ok": True, "trade": persisted_item, "path": project_relative_path(agent_home, path)}


def record_conversion(agent_home: Path, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_layout(agent_home)
    with file_lock(lock_path(agent_home, "execution_sync")):
        return _record_conversion_unlocked(agent_home, payload)


def _record_conversion_unlocked(agent_home: Path, payload: dict[str, Any]) -> dict[str, Any]:
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
    existing = _existing_record_result(agent_home, item, result_key="conversion")
    if existing is not None:
        return existing
    path = _append_actual_trade(agent_home, trade_date, item)
    persisted_item = _with_source_path(agent_home, item, path)
    pending = load_pending_confirmations(agent_home).get("items", []) or []
    pending = [entry for entry in pending if entry.get("conversion_id") != conversion_id]
    if item["status"] not in {"settled", "canceled", "failed"}:
        pending.append(persisted_item)
    _write_pending_confirmations(agent_home, pending)
    return {"ok": True, "conversion": persisted_item, "path": project_relative_path(agent_home, path)}


def update_pending_confirmations(agent_home: Path, as_of: str | None = None) -> dict[str, Any]:
    with file_lock(lock_path(agent_home, "execution_sync")):
        return _update_pending_confirmations_unlocked(agent_home, as_of)


def _update_pending_confirmations_unlocked(agent_home: Path, as_of: str | None = None) -> dict[str, Any]:
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
            if not entry.get("portfolio_applied_at") and not settlement_event_exists(agent_home, entry):
                try:
                    result = apply_settled_trade_to_portfolio(agent_home, entry)
                    if not result.get("ok", False):
                        raise RuntimeError(str(result.get("reason", "settlement did not update portfolio")))
                    entry["portfolio_applied_at"] = timestamp_now()
                    entry["portfolio_applied_as_of"] = as_of_date
                    entry["portfolio_settlement_event_path"] = result.get("settlement_event_path", "")
                    entry.pop("portfolio_apply_error", None)
                    if not result.get("skipped", False):
                        applied += 1
                except Exception as exc:
                    entry["portfolio_apply_error"] = str(exc)
                    apply_errors.append({"trade_id": entry.get("trade_id", ""), "error": str(exc)})
            elif settlement_event_exists(agent_home, entry):
                entry["portfolio_applied_at"] = entry.get("portfolio_applied_at") or timestamp_now()
                entry["portfolio_applied_as_of"] = entry.get("portfolio_applied_as_of") or as_of_date
                entry["portfolio_settlement_event_path"] = project_relative_path(agent_home, settlement_event_path(agent_home, settlement_idempotency_key(entry)))
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
        "path": project_relative_path(agent_home, path),
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
            "daily_pnl": _optional_money(item.get("daily_pnl", item.get("actual_daily_pnl"))),
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
        "portfolio_state_sha256": portfolio_state_hash(portfolio),
        "matched_items": matched,
        "new_items": new_items,
        "missing_items": missing,
        "apply_ready": bool(matched or new_items),
        "warnings": ["应用前请确认本次来源就是你的真实仓位。", "截图或手动快照只会在确认应用后覆盖组合状态。"],
    }
    preview["preview_sha256"] = reconciliation_preview_digest(preview)
    dump_json(parsed_import_path(agent_home, preview["reconcile_id"]), preview)
    return preview


def reconciliation_preview_digest(preview: dict[str, Any]) -> str:
    stable = {key: value for key, value in preview.items() if key != "preview_sha256"}
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_saved_reconciliation(
    agent_home: Path,
    reconcile_id: str,
    *,
    preview_sha256: str,
    expected_portfolio_state_sha256: str,
    drop_missing: bool = False,
) -> dict[str, Any]:
    if not IMPORT_ID_PATTERN.fullmatch(str(reconcile_id or "")):
        raise ValueError("reconcile_id must contain only letters, numbers, underscores, or hyphens")
    path = parsed_import_path(agent_home, reconcile_id)
    if not path.exists():
        raise FileNotFoundError(f"Reconciliation preview not found: {reconcile_id}")
    preview = load_json(path)
    if not isinstance(preview, dict) or str(preview.get("reconcile_id", "") or "") != reconcile_id:
        raise ValueError("Stored reconciliation preview is invalid")
    stored_digest = str(preview.get("preview_sha256", "") or "")
    actual_digest = reconciliation_preview_digest(preview)
    if not preview_sha256 or preview_sha256 != stored_digest or stored_digest != actual_digest:
        raise ValueError("Reconciliation preview hash mismatch")
    expected_state = str(preview.get("portfolio_state_sha256", "") or "")
    if not expected_portfolio_state_sha256 or expected_portfolio_state_sha256 != expected_state:
        raise ValueError("Expected portfolio state hash does not match reconciliation preview")
    request_digest = hashlib.sha256(
        json.dumps(
            {
                "reconcile_id": reconcile_id,
                "preview_sha256": preview_sha256,
                "portfolio_state_sha256": expected_portfolio_state_sha256,
                "drop_missing": bool(drop_missing),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    applied_path = reconciliation_applied_path(agent_home, reconcile_id)
    if applied_path.exists():
        applied = load_json(applied_path)
        if str(applied.get("request_sha256", "") or "") != request_digest:
            raise ValueError("Reconciliation id was already applied with a different request")
        result = dict(applied.get("result", {}) or {})
        result["idempotent_replay"] = True
        return result
    current_state = portfolio_state_hash(load_portfolio(agent_home))
    if current_state != expected_state:
        raise ValueError("Portfolio state changed after reconciliation preview; generate a new preview")
    result = apply_reconciliation(agent_home, preview, drop_missing=drop_missing)
    result["reconcile_id"] = reconcile_id
    result["preview_sha256"] = preview_sha256
    result["idempotent_replay"] = False
    dump_json(
        applied_path,
        {
            "schema_version": "reconciliation_apply.v1",
            "reconcile_id": reconcile_id,
            "request_sha256": request_digest,
            "applied_at": timestamp_now(),
            "result": result,
        },
    )
    return result


def _position_row_from_preview(row: dict[str, Any]) -> dict[str, Any]:
    code = str(row.get("fund_code") or row.get("matched_fund_code") or "").strip()
    name = str(row.get("fund_name") or row.get("matched_fund_name") or row.get("display_name") or code)
    current_value = _money(row.get("current_value"))
    holding_pnl = row.get("holding_pnl")
    cost_basis = row.get("cost_basis_value", row.get("derived_cost_basis_value"))
    daily_pnl = _optional_money(row.get("daily_pnl", row.get("actual_daily_pnl")))
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
        "actual_daily_pnl": daily_pnl,
    }


def apply_reconciliation(agent_home: Path, preview: dict[str, Any], *, drop_missing: bool = False) -> dict[str, Any]:
    with file_lock(lock_path(agent_home, "portfolio_state")):
        return _apply_reconciliation_unlocked(agent_home, preview, drop_missing=drop_missing)


def _apply_reconciliation_unlocked(agent_home: Path, preview: dict[str, Any], *, drop_missing: bool = False) -> dict[str, Any]:
    unmatched = list(preview.get("unmatched_detected", []) or [])
    if unmatched and preview.get("apply_ready") is False:
        raise ValueError("Position preview contains unmatched holdings; add or classify them before applying.")
    portfolio = deepcopy(load_portfolio(agent_home))
    current_by_code = {str(item.get("fund_code", "")): item for item in portfolio.get("funds", []) or []}
    snapshot_date = str(preview.get("snapshot_date") or preview.get("sync_date") or resolve_date())
    source = str(preview.get("source") or preview.get("provider") or "actual_position_sync")
    platform = str(preview.get("platform") or preview.get("provider") or "alipay")
    synced_at = timestamp_now()
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
        else:
            fund["units_source"] = "actual_position_value_only"
        if row.get("cost_basis_value") not in (None, ""):
            fund["cost_basis_value"] = _money(row.get("cost_basis_value"))
        if row.get("holding_pnl") not in (None, ""):
            fund["holding_pnl"] = _money(row.get("holding_pnl"))
        else:
            fund["holding_pnl"] = round(_money(fund.get("current_value")) - _money(fund.get("cost_basis_value")), 2)
        fund["holding_return_pct"] = float(row.get("holding_return_pct", fund.get("holding_return_pct", 0.0)) or 0.0)
        fund["last_valuation_date"] = snapshot_date
        if row.get("actual_daily_pnl") is not None:
            fund["actual_daily_pnl"] = row["actual_daily_pnl"]
            fund["actual_daily_pnl_date"] = snapshot_date
            fund["actual_daily_pnl_source"] = source
        fund["last_real_position_date"] = snapshot_date
        fund["real_position_source"] = source
        fund["actual_position_synced_at"] = synced_at
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
                fund["actual_daily_pnl"] = 0.0
                fund["actual_daily_pnl_date"] = snapshot_date
                fund["actual_daily_pnl_source"] = source
                fund["last_real_position_date"] = snapshot_date
                fund["real_position_source"] = source
                fund["actual_position_synced_at"] = synced_at
                dropped_codes.append(str(row.get("fund_code", "")))
    portfolio["as_of_date"] = snapshot_date
    portfolio["total_value"] = round(sum(_money(item.get("current_value")) for item in portfolio.get("funds", []) or []), 2)
    portfolio["holding_pnl"] = round(sum(_money(item.get("holding_pnl")) for item in portfolio.get("funds", []) or []), 2)
    current_path, snapshot_path = _save_portfolio_state_unlocked(
        agent_home,
        portfolio,
        source=source,
        event_date=snapshot_date,
        event_type="actual_position_reconcile",
        extra_meta={
            "platform": platform,
            "reconcile_id": preview.get("reconcile_id", ""),
            "updated_fund_codes": updated_codes,
            "added_fund_codes": added_codes,
            "dropped_missing_fund_codes": dropped_codes,
        },
    )
    position_payload = {
        "snapshot_date": snapshot_date,
        "source": source,
        "platform": platform,
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
        "current_path": project_relative_path(agent_home, current_path),
        "snapshot_path": project_relative_path(agent_home, snapshot_path),
    }
    dump_json(reconciliation_report_path(agent_home, snapshot_date), report)
    return report


def parse_alipay_screenshot_upload(agent_home: Path, payload: dict[str, Any]) -> dict[str, Any]:
    import_id = str(payload.get("import_id") or _new_id("alipay"))
    if not IMPORT_ID_PATTERN.fullmatch(import_id):
        raise ValueError("import_id must contain only letters, numbers, underscores, or hyphens")
    files = payload.get("files", []) or []
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_SCREENSHOT_FILES:
        raise ValueError(f"files must contain between 1 and {MAX_SCREENSHOT_FILES} screenshots")
    decoded_files: list[tuple[str, bytes]] = []
    total_bytes = 0
    max_encoded_chars = ((MAX_SCREENSHOT_FILE_BYTES + 2) // 3) * 4
    for index, item in enumerate(files, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"files[{index - 1}] must be an object")
        name = str(item.get("name") or f"screenshot_{index}.png")
        safe_name = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in Path(name).name)
        if not safe_name or safe_name in {".", ".."}:
            safe_name = f"screenshot_{index}.png"
        raw = item.get("data")
        if not isinstance(raw, str) or not raw:
            raise ValueError(f"files[{index - 1}].data must be non-empty base64")
        if raw.startswith("data:"):
            marker = ";base64,"
            if marker not in raw:
                raise ValueError(f"files[{index - 1}].data must be a base64 data URL")
            raw = raw.split(marker, 1)[1]
        elif "," in raw:
            raise ValueError(f"files[{index - 1}].data has an invalid data URL")
        if len(raw) > max_encoded_chars:
            raise ValueError(f"files[{index - 1}] exceeds {MAX_SCREENSHOT_FILE_BYTES} decoded bytes")
        try:
            decoded = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"files[{index - 1}].data is not valid base64") from exc
        if len(decoded) > MAX_SCREENSHOT_FILE_BYTES:
            raise ValueError(f"files[{index - 1}] exceeds {MAX_SCREENSHOT_FILE_BYTES} decoded bytes")
        total_bytes += len(decoded)
        if total_bytes > MAX_SCREENSHOT_TOTAL_BYTES:
            raise ValueError(f"screenshot payload exceeds {MAX_SCREENSHOT_TOTAL_BYTES} decoded bytes")
        decoded_files.append((safe_name, decoded))

    target_dir = (alipay_screenshot_dir(agent_home) / import_id).resolve()
    screenshot_root = alipay_screenshot_dir(agent_home).resolve()
    try:
        target_dir.relative_to(screenshot_root)
    except ValueError as exc:
        raise ValueError("screenshot import path must stay under the import directory") from exc
    saved: list[str] = []
    absolute_paths: list[Path] = []
    for safe_name, decoded in decoded_files:
        target = target_dir / safe_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(decoded)
        absolute_paths.append(target)
        saved.append(project_relative_path(agent_home, target))
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
        "auto_parse_attempted": bool(payload.get("auto_parse", True) and saved),
        "auto_parse_ok": False,
        "auto_parse_error": "",
        "warnings": [
            "截图已保存到本地。自动识别成功前不会覆盖仓位。",
        ],
        "generated_at": timestamp_now(),
    }
    if payload.get("auto_parse", True) and saved:
        try:
            from sync_portfolio_from_screenshots import build_sync_preview, call_screenshot_vision

            image_paths = absolute_paths
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
            recognized["auto_parse_attempted"] = True
            recognized["auto_parse_ok"] = True
            recognized["auto_parse_error"] = ""
            dump_json(parsed_import_path(agent_home, import_id), recognized)
            return recognized
        except Exception as exc:
            preview["auto_parse_error"] = str(exc)
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
    with file_lock(lock_path(agent_home, "portfolio_state")):
        return _apply_settled_trade_to_portfolio_unlocked(agent_home, trade)


def _apply_settled_trade_to_portfolio_unlocked(agent_home: Path, trade: dict[str, Any]) -> dict[str, Any]:
    idempotency_key = settlement_idempotency_key(trade)
    event_path = settlement_event_path(agent_home, idempotency_key)
    journal = _load_settlement_journal(agent_home, idempotency_key)
    trade_digest = _settlement_trade_digest(trade)
    if journal and str(journal.get("trade_digest", "")) not in {"", trade_digest}:
        _write_settlement_journal(agent_home, idempotency_key, {**journal, "status": "conflict", "last_error": "settlement idempotency key reused with different trade payload"})
        raise RuntimeError("settlement idempotency key was reused with a different trade payload")
    portfolio = load_portfolio(agent_home)
    if trade.get("portfolio_applied_at") or event_path.exists() or _portfolio_has_settlement(agent_home, portfolio, trade, idempotency_key):
        if not event_path.exists():
            dump_json(event_path, _recovered_settlement_payload(agent_home, trade, portfolio, idempotency_key, journal))
        _write_settlement_journal(
            agent_home,
            idempotency_key,
            {
                **journal,
                "status": "completed",
                "trade_digest": trade_digest,
                "after_state_hash": journal.get("after_state_hash", portfolio_state_hash(portfolio)),
                "completed_at": timestamp_now(),
                "recovered": True,
            },
        )
        return {"ok": True, "skipped": True, "reason": "settlement_already_applied", "settlement_event_path": project_relative_path(agent_home, event_path)}
    before_hash = portfolio_state_hash(portfolio)
    journal = {
        **journal,
        "status": "prepared",
        "trade_digest": trade_digest,
        "trade_id": trade.get("trade_id", ""),
        "conversion_id": trade.get("conversion_id", ""),
        "before_state_hash": before_hash,
        "created_at": str(journal.get("created_at", "") or timestamp_now()),
    }
    _write_settlement_journal(agent_home, idempotency_key, journal)
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
    portfolio.setdefault("state_metadata", {})["applied_settlement_ids"] = sorted(_applied_settlement_ids(portfolio) | {idempotency_key})
    after_hash = portfolio_state_hash(portfolio)
    settlement_payload = {
        "event_type": "actual_trade_settlement",
        "trade_id": trade.get("trade_id", ""),
        "conversion_id": trade.get("conversion_id", ""),
        "idempotency_key": idempotency_key,
        "before_state_hash": before_hash,
        "after_state_hash": after_hash,
        "created_at": timestamp_now(),
    }
    _write_settlement_journal(agent_home, idempotency_key, {**journal, "after_state_hash": after_hash})
    current_path, snapshot_path = _save_portfolio_state_unlocked(
        agent_home,
        portfolio,
        source="actual_trade_settlement",
        event_date=str(trade.get("settlement_date") or trade.get("confirm_date") or trade.get("trade_date") or resolve_date()),
        event_type="actual_trade_settlement",
        event_id=idempotency_key,
        source_path=str(trade.get("source_path", "")),
        extra_meta={**settlement_payload, "settlement_event_path": project_relative_path(agent_home, event_path)},
    )
    settlement_payload.update(
        {
            "current_path": project_relative_path(agent_home, current_path),
            "snapshot_path": project_relative_path(agent_home, snapshot_path),
            "source_path": str(trade.get("source_path", "")),
        }
    )
    _write_settlement_journal(
        agent_home,
        idempotency_key,
        {
            **journal,
            "status": "portfolio_applied",
            "after_state_hash": after_hash,
            "current_path": project_relative_path(agent_home, current_path),
            "snapshot_path": project_relative_path(agent_home, snapshot_path),
            "portfolio_applied_at": timestamp_now(),
        },
    )
    dump_json(event_path, settlement_payload)
    _write_settlement_journal(
        agent_home,
        idempotency_key,
        {
            **journal,
            "status": "completed",
            "after_state_hash": after_hash,
            "current_path": project_relative_path(agent_home, current_path),
            "snapshot_path": project_relative_path(agent_home, snapshot_path),
            "portfolio_applied_at": timestamp_now(),
            "completed_at": timestamp_now(),
        },
    )
    return {
        "ok": True,
        "current_path": project_relative_path(agent_home, current_path),
        "snapshot_path": project_relative_path(agent_home, snapshot_path),
        "settlement_event_path": project_relative_path(agent_home, event_path),
    }
