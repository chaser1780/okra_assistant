from __future__ import annotations

import argparse

from common import (
    classify_official_nav_freshness,
    dump_json,
    ensure_layout,
    estimated_nav_path,
    fund_nav_history_path,
    iter_actual_trade_items,
    load_json,
    load_portfolio,
    parse_date_text,
    portfolio_daily_pnl_path,
    project_relative_path,
    portfolio_valuation_path,
    quote_path,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
)
from portfolio_state import actual_position_is_authoritative, daily_pnl_units_are_trusted, save_portfolio_state
from update_portfolio_from_trade import ensure_cost_basis, ensure_units, recalc_fund


def safe_float(value) -> float | None:
    try:
        if value in (None, "", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def choose_official_nav(fund: dict, quote_by_code: dict, estimate_by_code: dict, report_date: str) -> dict:
    code = fund["fund_code"]
    quote = quote_by_code.get(code, {})
    estimate = estimate_by_code.get(code, {})
    quote_nav = safe_float(quote.get("nav"))
    if quote_nav and quote_nav > 0:
        return {
            "official_nav": quote_nav,
            "nav_date": quote.get("as_of_date") or report_date,
            "nav_source": "quotes",
            "match_type": quote.get("date_match_type", "unknown"),
            "previous_nav": safe_float(quote.get("previous_nav")),
            "previous_nav_date": str(quote.get("previous_nav_date") or ""),
            "stale": bool(quote.get("stale") or quote.get("fallback_reason")),
        }
    estimate_nav = safe_float(estimate.get("official_nav"))
    if estimate_nav and estimate_nav > 0:
        return {
            "official_nav": estimate_nav,
            "nav_date": estimate.get("official_nav_date") or report_date,
            "nav_source": "estimate_official",
            "match_type": "unknown",
            "previous_nav": None,
            "previous_nav_date": "",
            "stale": bool(estimate.get("stale") or estimate.get("fallback_reason")),
        }
    return {"official_nav": None, "nav_date": "", "nav_source": "missing", "match_type": "unknown", "previous_nav": None, "previous_nav_date": "", "stale": False}


def find_previous_nav(agent_home, fund_code: str, nav_date: str, default_nav: float | None, default_date: str) -> tuple[float | None, str]:
    if default_nav is not None and default_nav > 0:
        return default_nav, default_date
    target = parse_date_text(nav_date)
    if target is None:
        return None, ""
    path = fund_nav_history_path(agent_home, fund_code)
    if not path.exists():
        return None, ""
    payload = load_json(path)
    previous_nav = None
    previous_date = ""
    for item in payload.get("items", []) or []:
        item_date = parse_date_text(str(item.get("date") or ""))
        nav = safe_float(item.get("nav"))
        if item_date is None or nav is None or nav <= 0 or item_date >= target:
            continue
        if not previous_date or str(item.get("date") or "") > previous_date:
            previous_nav = nav
            previous_date = str(item.get("date") or "")
    return previous_nav, previous_date


def has_cashflow_between_nav_dates(agent_home, fund_code: str, previous_nav_date: str, nav_date: str) -> bool:
    previous_day = parse_date_text(previous_nav_date)
    current_day = parse_date_text(nav_date)
    if previous_day is None or current_day is None:
        return False
    for trade in iter_actual_trade_items(agent_home, nav_date):
        operation = str(trade.get("operation_type") or "")
        relevant = False
        if operation == "convert":
            relevant = fund_code in {str(trade.get("out_fund_code") or ""), str(trade.get("in_fund_code") or "")}
        else:
            relevant = fund_code == str(trade.get("fund_code") or "")
        if not relevant:
            continue
        effective_text = str(trade.get("effective_trade_date") or trade.get("confirm_date") or trade.get("trade_date") or "")
        effective_day = parse_date_text(effective_text)
        if effective_day is not None and previous_day < effective_day <= current_day:
            return True
    return False


def build_official_daily_pnl(agent_home, fund: dict, nav_info: dict, report_date: str) -> dict:
    official_nav = safe_float(nav_info.get("official_nav"))
    nav_date = str(nav_info.get("nav_date") or "")
    previous_nav, previous_nav_date = find_previous_nav(
        agent_home,
        fund["fund_code"],
        nav_date,
        safe_float(nav_info.get("previous_nav")),
        str(nav_info.get("previous_nav_date") or ""),
    )
    base = {
        "official_daily_pnl": None,
        "official_daily_pnl_date": nav_date,
        "official_daily_pnl_source": "official_nav_delta",
        "official_daily_pnl_status": "blocked",
        "official_daily_pnl_reason": "",
        "official_daily_pnl_units": safe_float(fund.get("holding_units")),
        "official_daily_pnl_nav": official_nav,
        "official_daily_pnl_previous_nav": previous_nav,
        "official_daily_pnl_previous_nav_date": previous_nav_date,
    }
    if official_nav is None or official_nav <= 0 or not nav_date:
        base["official_daily_pnl_reason"] = "missing_official_nav"
        return base
    if bool(nav_info.get("stale")):
        base["official_daily_pnl_reason"] = "stale_or_fallback_quote"
        return base
    if previous_nav is None or previous_nav <= 0 or not previous_nav_date:
        base["official_daily_pnl_reason"] = "missing_previous_official_nav"
        return base
    if str(fund.get("official_daily_pnl_date") or "") == nav_date and str(fund.get("official_daily_pnl_source") or "") == "official_nav_delta":
        base["official_daily_pnl"] = safe_float(fund.get("official_daily_pnl"))
        base["official_daily_pnl_status"] = "already_written"
        base["official_daily_pnl_reason"] = ""
        return base
    trusted, reason = daily_pnl_units_are_trusted(fund)
    if not trusted:
        base["official_daily_pnl_reason"] = reason
        return base
    units = safe_float(fund.get("holding_units"))
    if units is None or units <= 0:
        base["official_daily_pnl_reason"] = "missing_holding_units"
        return base
    if has_cashflow_between_nav_dates(agent_home, fund["fund_code"], previous_nav_date, nav_date):
        base["official_daily_pnl_reason"] = "cashflow_between_nav_dates_requires_position_snapshot"
        return base
    base["official_daily_pnl"] = round(units * (official_nav - previous_nav), 2)
    base["official_daily_pnl_status"] = "ok"
    base["official_daily_pnl_reason"] = ""
    base["official_daily_pnl_units"] = round(units, 6)
    return base


def official_daily_pnl_row(item: dict) -> dict:
    keys = (
        "fund_code",
        "fund_name",
        "official_nav",
        "official_nav_date",
        "nav_source",
        "date_match_type",
        "official_daily_pnl",
        "official_daily_pnl_date",
        "official_daily_pnl_source",
        "official_daily_pnl_status",
        "official_daily_pnl_reason",
        "official_daily_pnl_units",
        "official_daily_pnl_nav",
        "official_daily_pnl_previous_nav",
        "official_daily_pnl_previous_nav_date",
    )
    return {key: item.get(key) for key in keys}


def apply_official_daily_pnl(fund: dict, daily_pnl: dict) -> None:
    status = str(daily_pnl.get("official_daily_pnl_status") or "")
    if status == "ok":
        for key in (
            "official_daily_pnl",
            "official_daily_pnl_date",
            "official_daily_pnl_source",
            "official_daily_pnl_status",
            "official_daily_pnl_reason",
            "official_daily_pnl_units",
            "official_daily_pnl_nav",
            "official_daily_pnl_previous_nav",
            "official_daily_pnl_previous_nav_date",
        ):
            fund[key] = daily_pnl.get(key)
        fund["actual_daily_pnl"] = daily_pnl.get("official_daily_pnl")
        fund["actual_daily_pnl_date"] = daily_pnl.get("official_daily_pnl_date")
        fund["actual_daily_pnl_source"] = "official_nav_delta"
        return
    for key in (
        "official_daily_pnl",
        "official_daily_pnl_date",
        "official_daily_pnl_source",
        "official_daily_pnl_status",
        "official_daily_pnl_reason",
        "official_daily_pnl_units",
        "official_daily_pnl_nav",
        "official_daily_pnl_previous_nav",
        "official_daily_pnl_previous_nav_date",
    ):
        fund[key] = daily_pnl.get(key)


def build_item(agent_home, fund: dict, quote_by_code: dict, estimate_by_code: dict, report_date: str) -> dict:
    nav_info = choose_official_nav(fund, quote_by_code, estimate_by_code, report_date)
    official_nav = safe_float(nav_info.get("official_nav"))
    nav_date = str(nav_info.get("nav_date") or "")
    nav_source = str(nav_info.get("nav_source") or "missing")
    match_type = str(nav_info.get("match_type") or "unknown")
    freshness = classify_official_nav_freshness(report_date, nav_date)
    old_value = round(float(fund.get("current_value", 0.0)), 2)
    old_pnl = round(float(fund.get("holding_pnl", 0.0)), 2)
    official_daily_pnl = build_official_daily_pnl(agent_home, fund, nav_info, report_date)
    apply_official_daily_pnl(fund, official_daily_pnl)
    if actual_position_is_authoritative(fund, report_date):
        return {
            "fund_code": fund["fund_code"],
            "fund_name": fund["fund_name"],
            "status": "skipped",
            "reason": "actual_position_snapshot_authoritative",
            "official_nav": round(official_nav, 6) if official_nav else None,
            "official_nav_date": nav_date,
            "units": safe_float(fund.get("holding_units")),
            "old_current_value": old_value,
            "new_current_value": old_value,
            "old_holding_pnl": old_pnl,
            "new_holding_pnl": old_pnl,
            "nav_source": nav_source,
            "date_match_type": match_type,
            "freshness_label": freshness["label"],
            **official_daily_pnl,
        }

    ensure_cost_basis(fund)
    units = ensure_units(fund)

    if official_nav is None or official_nav <= 0:
        return {
            "fund_code": fund["fund_code"],
            "fund_name": fund["fund_name"],
            "status": "skipped",
            "reason": "missing_official_nav",
            "official_nav": None,
            "official_nav_date": "",
            "units": units,
            "old_current_value": old_value,
            "new_current_value": old_value,
            "old_holding_pnl": old_pnl,
            "new_holding_pnl": old_pnl,
            "nav_source": nav_source,
            "date_match_type": match_type,
            "freshness_label": freshness["label"],
            **official_daily_pnl,
        }
    if units is None or units <= 0:
        return {
            "fund_code": fund["fund_code"],
            "fund_name": fund["fund_name"],
            "status": "skipped",
            "reason": "missing_holding_units",
            "official_nav": round(official_nav, 6),
            "official_nav_date": nav_date,
            "units": None,
            "old_current_value": old_value,
            "new_current_value": old_value,
            "old_holding_pnl": old_pnl,
            "new_holding_pnl": old_pnl,
            "nav_source": nav_source,
            "date_match_type": match_type,
            "freshness_label": freshness["label"],
            **official_daily_pnl,
        }

    fund["current_value"] = round(units * official_nav, 2)
    fund["last_valuation_nav"] = round(official_nav, 6)
    fund["last_valuation_date"] = nav_date or report_date
    fund["last_official_nav"] = round(official_nav, 6)
    fund["last_official_nav_date"] = nav_date or report_date
    recalc_fund(fund)

    return {
        "fund_code": fund["fund_code"],
        "fund_name": fund["fund_name"],
        "status": "updated",
        "reason": "",
        "official_nav": round(official_nav, 6),
        "official_nav_date": nav_date,
        "units": round(units, 6),
        "old_current_value": old_value,
        "new_current_value": round(float(fund["current_value"]), 2),
        "value_change_amount": round(float(fund["current_value"]) - old_value, 2),
        "old_holding_pnl": old_pnl,
        "new_holding_pnl": round(float(fund.get("holding_pnl", 0.0)), 2),
        "nav_source": nav_source,
        "date_match_type": match_type,
        "freshness_label": freshness["label"],
        **official_daily_pnl,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Revalue portfolio positions using official daily NAV.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)

    portfolio = load_portfolio(agent_home)
    quotes = load_json(quote_path(agent_home, report_date)) if quote_path(agent_home, report_date).exists() else {"funds": []}
    estimates = load_json(estimated_nav_path(agent_home, report_date)) if estimated_nav_path(agent_home, report_date).exists() else {"items": []}
    quote_by_code = {item["code"]: item for item in quotes.get("funds", [])}
    estimate_by_code = {item["fund_code"]: item for item in estimates.get("items", [])}

    items = [build_item(agent_home, fund, quote_by_code, estimate_by_code, report_date) for fund in portfolio.get("funds", [])]
    updated_count = sum(1 for item in items if item["status"] == "updated")
    skipped_items = [item for item in items if item["status"] != "updated"]
    stale_funds = [item["fund_code"] for item in items if item["status"] == "updated" and item.get("date_match_type") == "delayed"]
    daily_pnl_items = [official_daily_pnl_row(item) for item in items]
    confirmed_daily_pnl_items = [item for item in daily_pnl_items if item.get("official_daily_pnl_status") in {"ok", "already_written"}]
    blocked_daily_pnl_items = [item for item in daily_pnl_items if item.get("official_daily_pnl_status") not in {"ok", "already_written"}]
    official_daily_pnl_total = round(sum(float(item.get("official_daily_pnl") or 0.0) for item in confirmed_daily_pnl_items), 2)

    portfolio["total_value"] = round(sum(float(fund.get("current_value", 0.0)) for fund in portfolio.get("funds", [])), 2)
    portfolio["holding_pnl"] = round(sum(float(fund.get("holding_pnl", 0.0)) for fund in portfolio.get("funds", [])), 2)
    portfolio["as_of_date"] = report_date
    portfolio["last_valuation_run_date"] = report_date
    portfolio["last_valuation_generated_at"] = timestamp_now()
    portfolio["official_daily_pnl"] = official_daily_pnl_total
    portfolio["official_daily_pnl_confirmed_count"] = len(confirmed_daily_pnl_items)
    portfolio["official_daily_pnl_blocked_count"] = len(blocked_daily_pnl_items)

    valuation_payload = {
        "report_date": report_date,
        "generated_at": portfolio["last_valuation_generated_at"],
        "portfolio_name": portfolio.get("portfolio_name", ""),
        "updated_fund_count": updated_count,
        "skipped_fund_count": len(skipped_items),
        "stale_fund_codes": stale_funds,
        "total_value": portfolio["total_value"],
        "holding_pnl": portfolio["holding_pnl"],
        "official_daily_pnl": official_daily_pnl_total,
        "official_daily_pnl_confirmed_count": len(confirmed_daily_pnl_items),
        "official_daily_pnl_blocked_count": len(blocked_daily_pnl_items),
        "items": items,
    }

    daily_pnl_payload = {
        "report_date": report_date,
        "generated_at": portfolio["last_valuation_generated_at"],
        "source": "official_nav_delta",
        "total_official_daily_pnl": official_daily_pnl_total,
        "confirmed_count": len(confirmed_daily_pnl_items),
        "blocked_count": len(blocked_daily_pnl_items),
        "items": daily_pnl_items,
    }

    current_state_path, snapshot_path = save_portfolio_state(
        agent_home,
        portfolio,
        source="official_nav_revaluation",
        event_date=report_date,
        event_type="official_nav_revaluation",
        extra_meta={"valuation_snapshot_path": project_relative_path(agent_home, portfolio_valuation_path(agent_home, report_date))},
    )
    valuation_payload["portfolio_state_snapshot_path"] = project_relative_path(agent_home, snapshot_path)
    valuation_path = dump_json(portfolio_valuation_path(agent_home, report_date), valuation_payload)
    daily_pnl_path = dump_json(portfolio_daily_pnl_path(agent_home, report_date), daily_pnl_payload)
    portfolio_path = current_state_path
    print(valuation_path)
    print(daily_pnl_path)
    print(portfolio_path)


if __name__ == "__main__":
    main()
