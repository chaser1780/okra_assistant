from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from common import load_json, parse_date_text


DEFAULT_CUTOFF_TIME = "15:00"


def is_business_day(value: date) -> bool:
    return value.weekday() < 5


def next_business_day(value: date) -> date:
    current = value + timedelta(days=1)
    while not is_business_day(current):
        current += timedelta(days=1)
    return current


def add_business_days(value: date, days: int) -> date:
    current = value
    for _ in range(max(0, int(days))):
        current = next_business_day(current)
    return current


def parse_cutoff(value: str | None) -> time:
    raw = str(value or DEFAULT_CUTOFF_TIME).strip()
    try:
        hour, minute = raw.split(":", 1)
        return time(int(hour), int(minute))
    except (TypeError, ValueError):
        return time(15, 0)


def effective_trade_date(trade_date: str, trade_time: str = "", *, cutoff_time: str = DEFAULT_CUTOFF_TIME) -> str:
    parsed = parse_date_text(trade_date) or date.today()
    if not is_business_day(parsed):
        return next_business_day(parsed).isoformat()
    if trade_time:
        try:
            submitted = datetime.strptime(trade_time[:5], "%H:%M").time()
            if submitted >= parse_cutoff(cutoff_time):
                return next_business_day(parsed).isoformat()
        except ValueError:
            pass
    return parsed.isoformat()


def fund_lifecycle_overrides(agent_home: Path, fund_code: str) -> dict[str, Any]:
    definition_path = agent_home / "config" / "portfolio_definition.json"
    current_path = agent_home / "db" / "portfolio_state" / "current.json"
    for payload in (load_json(definition_path) if definition_path.exists() else {}, load_json(current_path) if current_path.exists() else {}):
        for item in payload.get("funds", []) or []:
            if str(item.get("fund_code", "")) == str(fund_code):
                return item
    return {}


def infer_fund_kind(fund: dict[str, Any]) -> str:
    text = " ".join(str(fund.get(key, "")) for key in ("fund_name", "style_group", "proxy_name", "category")).lower()
    if "qdii" in text or "nasdaq" in text or "sp500" in text or "标普" in text or "纳斯达克" in text:
        return "qdii"
    if "货币" in text or "存单" in text or str(fund.get("role", "")) == "cash_hub":
        return "cash"
    if "债" in text:
        return "bond"
    return "normal"


def default_confirm_days(fund: dict[str, Any], operation_type: str) -> tuple[int, int]:
    kind = infer_fund_kind(fund)
    if kind == "qdii":
        return (2, int(fund.get("redeem_settlement_days", 3) or 3))
    if kind == "cash":
        return (1, int(fund.get("redeem_settlement_days", 1) or 1))
    if kind == "bond":
        return (1, int(fund.get("redeem_settlement_days", 2) or 2))
    return (1, int(fund.get("redeem_settlement_days", 1) or 1))


def resolve_trade_lifecycle(
    agent_home: Path,
    *,
    fund_code: str,
    operation_type: str,
    trade_date: str,
    trade_time: str = "",
    confirm_date: str = "",
    settlement_date: str = "",
    cutoff_time: str = "",
) -> dict[str, Any]:
    fund = fund_lifecycle_overrides(agent_home, fund_code)
    cutoff = str(cutoff_time or fund.get("cutoff_time") or DEFAULT_CUTOFF_TIME)
    effective = effective_trade_date(trade_date, trade_time, cutoff_time=cutoff)
    effective_date = parse_date_text(effective) or date.today()
    buy_days, sell_settle_days = default_confirm_days(fund, operation_type)
    confirm_days = int(
        fund.get("confirm_days_sell" if operation_type in {"sell", "convert_out"} else "confirm_days_buy", buy_days)
        or buy_days
    )
    if operation_type in {"sell", "convert_out"}:
        confirm_days = int(fund.get("confirm_days_sell", confirm_days) or confirm_days)
    resolved_confirm = confirm_date or add_business_days(effective_date, confirm_days).isoformat()
    resolved_settlement = settlement_date
    if not resolved_settlement:
        if operation_type in {"sell", "convert_out"}:
            resolved_settlement = add_business_days(parse_date_text(resolved_confirm) or effective_date, sell_settle_days).isoformat()
        else:
            resolved_settlement = resolved_confirm
    return {
        "cutoff_time": cutoff,
        "effective_trade_date": effective,
        "confirm_date": resolved_confirm,
        "settlement_date": resolved_settlement,
        "fund_kind": infer_fund_kind(fund),
        "confirm_days": confirm_days,
        "settlement_days": sell_settle_days if operation_type in {"sell", "convert_out"} else 0,
    }


def lifecycle_status(lifecycle: dict[str, Any], as_of: str | None = None, *, operation_type: str = "") -> str:
    current = parse_date_text(as_of or date.today().isoformat()) or date.today()
    confirm = parse_date_text(str(lifecycle.get("confirm_date", "")))
    settle = parse_date_text(str(lifecycle.get("settlement_date", "")))
    if confirm and current < confirm:
        return "submitted"
    if operation_type in {"sell", "convert_out"} and settle and current < settle:
        return "confirmed"
    return "settled"
