from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def parse_date(value: str) -> datetime.date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def calendar_day_gap(start: str, end: str) -> int:
    return (parse_date(end) - parse_date(start)).days


def infer_default_min_hold_days(fund: dict) -> int:
    if "min_hold_days" in fund:
        return int(fund.get("min_hold_days", 0) or 0)
    if fund.get("role") == "cash_hub":
        return 7
    return 0


def infer_default_redeem_settlement_days(fund: dict) -> int:
    if "redeem_settlement_days" in fund:
        return int(fund.get("redeem_settlement_days", 0) or 0)
    style = (fund.get("style_group") or "").lower()
    if any(marker in style for marker in ("sp500", "nasdaq", "internet")):
        return 3
    if fund.get("role") == "cash_hub":
        return 1
    return 1


def infer_default_purchase_confirm_days(fund: dict) -> int:
    if "purchase_confirm_days" in fund:
        return int(fund.get("purchase_confirm_days", 1) or 1)
    style = (fund.get("style_group") or "").lower()
    if any(marker in style for marker in ("sp500", "nasdaq", "internet", "qdii")):
        return 2
    return 1


def infer_default_nav_confirm_days(fund: dict) -> int:
    if "nav_confirm_days" in fund:
        return int(fund.get("nav_confirm_days", 1) or 1)
    if fund.get("role") == "cash_hub":
        return 1
    style = (fund.get("style_group") or "").lower()
    if any(marker in style for marker in ("sp500", "nasdaq", "internet", "qdii")):
        return 2
    return 1


def infer_default_conversion_supported(fund: dict) -> bool:
    if "conversion_supported" in fund:
        return bool(fund.get("conversion_supported"))
    return bool(fund.get("allow_trade", False) and fund.get("role") not in {"fixed_hold"})


def infer_default_redeem_fee_rate(fund: dict) -> float:
    if "estimated_redeem_fee_rate" in fund:
        return float(fund.get("estimated_redeem_fee_rate", 0.0) or 0.0)
    if fund.get("role") == "cash_hub":
        return 0.0
    style = (fund.get("style_group") or "").lower()
    if any(marker in style for marker in ("sp500", "nasdaq", "internet", "qdii")):
        return 0.5
    if fund.get("role") == "fixed_hold":
        return 0.1
    return 0.5


def iter_trade_items(agent_home: Path) -> list[dict]:
    trade_dir = agent_home / "db" / "trade_journal"
    items: list[dict] = []
    if not trade_dir.exists():
        return items
    for path in sorted(trade_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        trade_date = payload.get("trade_date") or path.stem
        for item in payload.get("items", []):
            items.append({"trade_date": trade_date, **item})
    items.sort(key=lambda item: item["trade_date"])
    return items


def locked_amount_from_recent_trades(agent_home: Path, fund_code: str, report_date: str, min_hold_days: int) -> float:
    if min_hold_days <= 0:
        return 0.0
    recent_buys = 0.0
    recent_sells = 0.0
    for item in iter_trade_items(agent_home):
        if item.get("fund_code") != fund_code:
            continue
        if calendar_day_gap(item["trade_date"], report_date) < 0:
            continue
        if calendar_day_gap(item["trade_date"], report_date) >= min_hold_days:
            continue
        action = item.get("action")
        amount = float(item.get("amount", 0.0) or 0.0)
        if action in {"buy", "switch_in"}:
            recent_buys += amount
        elif action in {"sell", "switch_out"}:
            recent_sells += amount
    return round(max(0.0, recent_buys - recent_sells), 2)


def build_trade_constraints(agent_home: Path, portfolio: dict, report_date: str) -> dict[str, dict]:
    constraints: dict[str, dict] = {}
    for fund in portfolio.get("funds", []):
        min_hold_days = infer_default_min_hold_days(fund)
        settlement_days = infer_default_redeem_settlement_days(fund)
        purchase_confirm_days = infer_default_purchase_confirm_days(fund)
        nav_confirm_days = infer_default_nav_confirm_days(fund)
        conversion_supported = infer_default_conversion_supported(fund)
        redeem_fee_rate = infer_default_redeem_fee_rate(fund)
        current_value = float(fund.get("current_value", 0.0))
        locked_amount = min(current_value, locked_amount_from_recent_trades(agent_home, fund["fund_code"], report_date, min_hold_days))
        available_to_sell = round(max(0.0, current_value - locked_amount), 2)
        notes = []
        if locked_amount > 0:
            notes.append(f"最近 {min_hold_days} 天内新买入部分约 {locked_amount:.2f} 元仍处锁定期。")
        if settlement_days > 0:
            notes.append(f"若卖出，预计回款到账时效约 T+{settlement_days}。")
        notes.append(f"预计申购确认时效约 T+{purchase_confirm_days}。")
        notes.append(f"预计净值确认时效约 T+{nav_confirm_days}。")
        notes.append(f"{'支持' if conversion_supported else '不支持'}直接转换。")
        if redeem_fee_rate > 0:
            notes.append(f"估算赎回费率约 {redeem_fee_rate:.2f}%。")
        constraints[fund["fund_code"]] = {
            "min_hold_days": min_hold_days,
            "redeem_settlement_days": settlement_days,
            "purchase_confirm_days": purchase_confirm_days,
            "nav_confirm_days": nav_confirm_days,
            "conversion_supported": conversion_supported,
            "estimated_redeem_fee_rate": round(redeem_fee_rate, 4),
            "locked_amount": round(locked_amount, 2),
            "available_to_sell": available_to_sell,
            "notes": notes,
        }
    return constraints
