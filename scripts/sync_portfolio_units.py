from __future__ import annotations

import argparse

from common import ensure_layout, estimated_nav_path, load_json, load_portfolio, quote_path, resolve_agent_home, resolve_date
from portfolio_state import save_portfolio_state


def safe_float(value) -> float | None:
    try:
        if value in (None, "", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync holding units into portfolio using latest official NAV.")
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

    for fund in portfolio.get("funds", []):
        current_value = float(fund.get("current_value", 0.0))
        if current_value <= 0:
            continue
        estimate = estimate_by_code.get(fund["fund_code"], {})
        quote = quote_by_code.get(fund["fund_code"], {})
        official_nav = safe_float(estimate.get("official_nav")) or safe_float(quote.get("nav"))
        if not official_nav or official_nav <= 0:
            continue
        fund["holding_units"] = round(current_value / official_nav, 6)
        fund["last_valuation_nav"] = round(official_nav, 6)
        fund["last_valuation_date"] = estimate.get("official_nav_date") or quote.get("as_of_date") or report_date
        fund["units_source"] = "derived_from_official_nav"

    path, _snapshot = save_portfolio_state(
        agent_home,
        portfolio,
        source="unit_sync",
        event_date=report_date,
        event_type="unit_sync",
    )
    print(path)


if __name__ == "__main__":
    main()
