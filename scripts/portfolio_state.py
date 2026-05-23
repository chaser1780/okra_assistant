from __future__ import annotations

import json
import hashlib
import uuid
from copy import deepcopy
from pathlib import Path

from common import (
    PORTFOLIO_RUNTIME_FIELDS,
    iter_actual_trade_items,
    dump_json,
    execution_status_path,
    file_lock,
    legacy_portfolio_path,
    load_json,
    load_portfolio,
    lock_path,
    parse_date_text,
    portfolio_definition_path,
    portfolio_state_current_path,
    portfolio_state_event_dir,
    portfolio_state_snapshot_path,
    timestamp_now,
)


RUNTIME_FIELDS = PORTFOLIO_RUNTIME_FIELDS

ACTUAL_POSITION_UNIT_SOURCES = {
    "actual_position_sync",
    "actual_position_value_only",
    "actual_position_missing_zero",
    "screenshot_sync_value_only",
    "screenshot_sync_missing_zero",
}

VALUE_ONLY_POSITION_UNIT_SOURCES = {
    "actual_position_value_only",
    "actual_position_missing_zero",
    "screenshot_sync_value_only",
    "screenshot_sync_missing_zero",
}

ACTUAL_POSITION_SOURCES = {
    "actual_position_sync",
    "alipay_screenshot",
    "manual_position_snapshot",
    "portfolio_screenshot_sync",
}

TRUSTED_DAILY_PNL_UNIT_SOURCES = {
    "stored",
    "manual",
    "manual_position_snapshot",
    "actual_position_sync",
    "actual_trade_units",
}

UNTRUSTED_DAILY_PNL_UNIT_SOURCES = {
    "derived_from_official_nav",
    *VALUE_ONLY_POSITION_UNIT_SOURCES,
}


def actual_position_snapshot_date(fund: dict) -> str:
    for key in ("last_real_position_date", "actual_daily_pnl_date"):
        value = str(fund.get(key) or "").strip()
        if value:
            return value
    return ""


def is_actual_position_source(fund: dict) -> bool:
    units_source = str(fund.get("units_source") or "").strip()
    source = str(fund.get("real_position_source") or fund.get("actual_daily_pnl_source") or "").strip()
    return units_source in ACTUAL_POSITION_UNIT_SOURCES or source in ACTUAL_POSITION_SOURCES


def actual_position_is_authoritative(fund: dict, report_date: str | None = None) -> bool:
    units_source = str(fund.get("units_source") or "").strip()
    if units_source in VALUE_ONLY_POSITION_UNIT_SOURCES:
        if report_date is None:
            return True
        return actual_position_snapshot_date(fund) == str(report_date or "").strip()
    if not is_actual_position_source(fund):
        return False
    if report_date is None:
        return True
    return actual_position_snapshot_date(fund) == str(report_date or "").strip()


def daily_pnl_units_are_trusted(fund: dict) -> tuple[bool, str]:
    units_source = str(fund.get("units_source") or "").strip()
    if units_source in TRUSTED_DAILY_PNL_UNIT_SOURCES:
        return True, ""
    if units_source in UNTRUSTED_DAILY_PNL_UNIT_SOURCES:
        return False, f"untrusted_units_source:{units_source}"
    return False, f"unclassified_units_source:{units_source or 'missing'}"


def _safe_event_token(value: str) -> str:
    token = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(value or "").strip())
    return token.strip("_") or "event"


def portfolio_state_event_path(agent_home: Path, event_date: str, event_type: str, event_id: str | None = None) -> Path:
    event_dir = portfolio_state_event_dir(agent_home, event_date)
    if not event_id:
        event_id = timestamp_now().replace(":", "").replace("+", "_").replace(".", "_")
    filename = f"{_safe_event_token(event_type)}_{_safe_event_token(event_id)}.json"
    return event_dir / filename


def portfolio_state_hash(portfolio: dict) -> str:
    payload = deepcopy(portfolio)
    payload.pop("state_metadata", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ensure_portfolio_definition(agent_home: Path) -> dict:
    path = portfolio_definition_path(agent_home)
    if path.exists():
        return load_json(path)
    # `load_portfolio` will bootstrap the definition/current files on first access.
    load_portfolio(agent_home)
    return load_json(path)


def restore_portfolio_from_definition(definition: dict) -> dict:
    funds = []
    for item in definition.get("funds", []):
        fund = {key: deepcopy(value) for key, value in item.items() if key != "opening_state"}
        opening = deepcopy(item.get("opening_state", {}))
        fund.update(opening)
        funds.append(fund)
    total_value = round(sum(float(fund.get("current_value", 0.0)) for fund in funds), 2)
    holding_pnl = round(sum(float(fund.get("holding_pnl", 0.0)) for fund in funds), 2)
    return {
        "portfolio_name": definition.get("portfolio_name", ""),
        "as_of_date": definition.get("base_as_of_date", ""),
        "total_value": total_value,
        "holding_pnl": holding_pnl,
        "definition_bootstrapped_at": definition.get("bootstrapped_at", ""),
        "funds": funds,
    }


def save_portfolio_state(
    agent_home: Path,
    portfolio: dict,
    *,
    source: str,
    event_date: str,
    event_type: str,
    event_id: str | None = None,
    extra_meta: dict | None = None,
    source_path: str = "",
    persist_legacy: bool = False,
) -> tuple[Path, Path]:
    with file_lock(lock_path(agent_home, "portfolio_state")):
        return _save_portfolio_state_unlocked(
            agent_home,
            portfolio,
            source=source,
            event_date=event_date,
            event_type=event_type,
            event_id=event_id,
            extra_meta=extra_meta,
            source_path=source_path,
            persist_legacy=persist_legacy,
        )


def _save_portfolio_state_unlocked(
    agent_home: Path,
    portfolio: dict,
    *,
    source: str,
    event_date: str,
    event_type: str,
    event_id: str | None = None,
    extra_meta: dict | None = None,
    source_path: str = "",
    persist_legacy: bool = False,
) -> tuple[Path, Path]:
    previous_state = load_json(portfolio_state_current_path(agent_home)) if portfolio_state_current_path(agent_home).exists() else {}
    parent_state_id = str((previous_state.get("state_metadata", {}) or {}).get("state_id", ""))
    resolved_event_id = event_id or timestamp_now().replace(":", "").replace("+", "_").replace(".", "_")
    state_id = uuid.uuid4().hex
    current_payload = deepcopy(portfolio)
    current_payload.setdefault("state_metadata", {})
    updated_at = timestamp_now()
    current_payload["state_metadata"].update(
        {
            "state_id": state_id,
            "parent_state_id": parent_state_id,
            "event_id": resolved_event_id,
            "source": source,
            "source_path": source_path,
            "event_type": event_type,
            "event_date": event_date,
            "updated_at": updated_at,
        }
    )
    if extra_meta:
        current_payload["state_metadata"].update(extra_meta)

    current_path = dump_json(portfolio_state_current_path(agent_home), current_payload)
    snapshot_payload = deepcopy(current_payload)
    snapshot_path = dump_json(portfolio_state_snapshot_path(agent_home, event_date), snapshot_payload)
    event_path = portfolio_state_event_path(agent_home, event_date, event_type, resolved_event_id)
    event_payload = deepcopy(current_payload)
    event_payload["state_metadata"].update({"event_journal_path": str(event_path), "latest_snapshot_path": str(snapshot_path)})
    dump_json(event_path, event_payload)
    current_payload["state_metadata"]["event_journal_path"] = str(event_path)
    current_path = dump_json(portfolio_state_current_path(agent_home), current_payload)
    if persist_legacy:
        dump_json(legacy_portfolio_path(agent_home), current_payload)
    return current_path, snapshot_path


def _trade_items_until(agent_home: Path, target_date: str) -> list[dict]:
    target = parse_date_text(target_date)
    if target is None:
        return []
    items: list[dict] = []
    for item in iter_actual_trade_items(agent_home, target_date):
        operation = str(item.get("operation_type", "") or "")
        if operation == "convert":
            items.append(
                {
                    "trade_date": item.get("trade_date", ""),
                    "fund_code": item.get("out_fund_code", ""),
                    "action": "switch_out",
                    "amount": float(item.get("out_amount", 0.0) or 0.0),
                    "trade_nav": item.get("out_nav"),
                    "units": item.get("out_units"),
                }
            )
            items.append(
                {
                    "trade_date": item.get("trade_date", ""),
                    "fund_code": item.get("in_fund_code", ""),
                    "action": "switch_in",
                    "amount": float(item.get("in_amount", 0.0) or 0.0),
                    "trade_nav": item.get("in_nav"),
                    "units": item.get("in_units"),
                }
            )
            continue
        mapped_action = {
            "buy": "buy",
            "dca": "buy",
            "sell": "sell",
            "convert_in": "switch_in",
            "convert_out": "switch_out",
        }.get(operation, operation)
        items.append(
            {
                "trade_date": item.get("trade_date", ""),
                "fund_code": item.get("fund_code", ""),
                "action": mapped_action,
                "amount": float(item.get("amount", 0.0) or 0.0),
                "trade_nav": item.get("nav"),
                "units": item.get("units"),
            }
        )
    items.sort(key=lambda item: (item.get("trade_date", ""), item.get("fund_code", "")))
    return items


def _latest_snapshot_on_or_before(agent_home: Path, target_date: str) -> tuple[dict | None, str]:
    snapshot_dir = agent_home / "db" / "portfolio_state" / "snapshots"
    if not snapshot_dir.exists():
        return None, ""
    target = parse_date_text(target_date)
    if target is None:
        return None, ""
    candidates: list[tuple[str, dict]] = []
    for path in snapshot_dir.glob("*.json"):
        snap_date = parse_date_text(path.stem)
        if snap_date is None or snap_date > target:
            continue
        candidates.append((path.stem, load_json(path)))
    if not candidates:
        return None, ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], candidates[0][0]


def rebuild_portfolio_state(agent_home: Path, target_date: str | None = None) -> dict:
    from update_portfolio_from_trade import apply_trade

    definition = ensure_portfolio_definition(agent_home)
    target = target_date or definition.get("base_as_of_date") or ""
    snapshot_payload, snapshot_date = _latest_snapshot_on_or_before(agent_home, target) if target else (None, "")
    if snapshot_payload:
        portfolio = deepcopy(snapshot_payload)
    else:
        portfolio = restore_portfolio_from_definition(definition)
        snapshot_date = definition.get("base_as_of_date", "")

    start_date = parse_date_text(snapshot_date)
    for item in _trade_items_until(agent_home, target):
        trade_date = parse_date_text(item.get("trade_date"))
        if start_date is not None and trade_date is not None and trade_date <= start_date:
            continue
        portfolio = apply_trade(
            portfolio,
            item["fund_code"],
            item["action"],
            item["amount"],
            trade_nav=item.get("trade_nav"),
            trade_units=item.get("units"),
        )
    return portfolio


def load_execution_status(agent_home: Path, report_date: str) -> dict:
    path = execution_status_path(agent_home, report_date)
    if not path.exists():
        return {"report_date": report_date, "items": []}
    return load_json(path)


def upsert_execution_status(agent_home: Path, report_date: str, item: dict) -> Path:
    with file_lock(lock_path(agent_home, f"execution_status_{report_date}")):
        return _upsert_execution_status_unlocked(agent_home, report_date, item)


def _upsert_execution_status_unlocked(agent_home: Path, report_date: str, item: dict) -> Path:
    payload = load_execution_status(agent_home, report_date)
    existing = next((entry for entry in payload.get("items", []) if entry.get("suggestion_id") == item.get("suggestion_id")), None)
    items = [entry for entry in payload.get("items", []) if entry.get("suggestion_id") != item.get("suggestion_id")]
    merged = dict(existing or {})
    merged.update(item)
    previous_amount = float((existing or {}).get("trade_amount", 0.0) or 0.0)
    current_amount = float(item.get("trade_amount", 0.0) or 0.0)
    if existing:
        merged["trade_amount"] = round(previous_amount + current_amount, 2)
        linked_dates = list(existing.get("linked_trade_dates", []) or [])
        if item.get("linked_trade_date") and item.get("linked_trade_date") not in linked_dates:
            linked_dates.append(item.get("linked_trade_date"))
        merged["linked_trade_dates"] = linked_dates
    else:
        merged["linked_trade_dates"] = [item.get("linked_trade_date")] if item.get("linked_trade_date") else []
    items.append(merged)
    payload["report_date"] = report_date
    payload["updated_at"] = timestamp_now()
    payload["items"] = sorted(items, key=lambda entry: (entry.get("fund_code", ""), entry.get("suggestion_id", "")))
    return dump_json(execution_status_path(agent_home, report_date), payload)
