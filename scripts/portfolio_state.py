from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from common import (
    dump_json,
    execution_status_path,
    load_json,
    load_portfolio,
    parse_date_text,
    portfolio_definition_path,
    portfolio_state_current_path,
    portfolio_state_snapshot_path,
    timestamp_now,
)


RUNTIME_FIELDS = {
    "current_value",
    "holding_pnl",
    "holding_return_pct",
    "holding_units",
    "cost_basis_value",
    "last_valuation_nav",
    "last_valuation_date",
    "last_official_nav",
    "last_official_nav_date",
    "units_source",
}


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
    extra_meta: dict | None = None,
    persist_legacy: bool = True,
) -> tuple[Path, Path]:
    current_payload = deepcopy(portfolio)
    current_payload.setdefault("state_metadata", {})
    current_payload["state_metadata"].update(
        {
            "source": source,
            "event_type": event_type,
            "event_date": event_date,
            "updated_at": timestamp_now(),
        }
    )
    if extra_meta:
        current_payload["state_metadata"].update(extra_meta)

    current_path = dump_json(portfolio_state_current_path(agent_home), current_payload)
    snapshot_payload = deepcopy(current_payload)
    snapshot_path = dump_json(portfolio_state_snapshot_path(agent_home, event_date), snapshot_payload)
    if persist_legacy:
        dump_json(agent_home / "config" / "portfolio.json", current_payload)
    return current_path, snapshot_path


def _trade_items_until(agent_home: Path, target_date: str) -> list[dict]:
    trade_dir = agent_home / "db" / "trade_journal"
    if not trade_dir.exists():
        return []
    target = parse_date_text(target_date)
    if target is None:
        return []
    items: list[dict] = []
    for path in sorted(trade_dir.glob("*.json")):
        trade_date = parse_date_text(path.stem)
        if trade_date is None or trade_date > target:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("items", []):
            items.append({"trade_date": path.stem, **item})
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
