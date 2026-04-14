from __future__ import annotations

import argparse

from common import (
    classify_official_nav_freshness,
    dump_json,
    ensure_layout,
    estimated_nav_path,
    load_json,
    load_portfolio,
    portfolio_valuation_path,
    quote_path,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
)
from portfolio_state import save_portfolio_state
from update_portfolio_from_trade import ensure_cost_basis, ensure_units, recalc_fund, save_portfolio


def safe_float(value) -> float | None:
    try:
        if value in (None, "", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def choose_official_nav(fund: dict, quote_by_code: dict, estimate_by_code: dict, report_date: str) -> tuple[float | None, str, str, str]:
    code = fund["fund_code"]
    quote = quote_by_code.get(code, {})
    estimate = estimate_by_code.get(code, {})
    quote_nav = safe_float(quote.get("nav"))
    if quote_nav and quote_nav > 0:
        return quote_nav, quote.get("as_of_date") or report_date, "quotes", quote.get("date_match_type", "unknown")
    estimate_nav = safe_float(estimate.get("official_nav"))
    if estimate_nav and estimate_nav > 0:
        return estimate_nav, estimate.get("official_nav_date") or report_date, "estimate_official", "unknown"
    return None, "", "missing", "unknown"


def build_item(fund: dict, quote_by_code: dict, estimate_by_code: dict, report_date: str) -> dict:
    ensure_cost_basis(fund)
    units = ensure_units(fund)
    official_nav, nav_date, nav_source, match_type = choose_official_nav(fund, quote_by_code, estimate_by_code, report_date)
    freshness = classify_official_nav_freshness(report_date, nav_date)
    old_value = round(float(fund.get("current_value", 0.0)), 2)
    old_pnl = round(float(fund.get("holding_pnl", 0.0)), 2)

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

    items = [build_item(fund, quote_by_code, estimate_by_code, report_date) for fund in portfolio.get("funds", [])]
    updated_count = sum(1 for item in items if item["status"] == "updated")
    skipped_items = [item for item in items if item["status"] != "updated"]
    stale_funds = [item["fund_code"] for item in items if item["status"] == "updated" and item.get("date_match_type") == "delayed"]

    portfolio["total_value"] = round(sum(float(fund.get("current_value", 0.0)) for fund in portfolio.get("funds", [])), 2)
    portfolio["holding_pnl"] = round(sum(float(fund.get("holding_pnl", 0.0)) for fund in portfolio.get("funds", [])), 2)
    portfolio["as_of_date"] = report_date
    portfolio["last_valuation_run_date"] = report_date
    portfolio["last_valuation_generated_at"] = timestamp_now()

    valuation_payload = {
        "report_date": report_date,
        "generated_at": portfolio["last_valuation_generated_at"],
        "portfolio_name": portfolio.get("portfolio_name", ""),
        "updated_fund_count": updated_count,
        "skipped_fund_count": len(skipped_items),
        "stale_fund_codes": stale_funds,
        "total_value": portfolio["total_value"],
        "holding_pnl": portfolio["holding_pnl"],
        "items": items,
    }

    current_state_path, snapshot_path = save_portfolio_state(
        agent_home,
        portfolio,
        source="official_nav_revaluation",
        event_date=report_date,
        event_type="official_nav_revaluation",
        extra_meta={"valuation_snapshot_path": str(portfolio_valuation_path(agent_home, report_date))},
    )
    valuation_payload["portfolio_state_snapshot_path"] = str(snapshot_path)
    valuation_path = dump_json(portfolio_valuation_path(agent_home, report_date), valuation_payload)
    portfolio_path = current_state_path
    print(valuation_path)
    print(portfolio_path)


if __name__ == "__main__":
    main()
