from __future__ import annotations

import argparse
from pathlib import Path

from common import ensure_layout, load_portfolio, resolve_agent_home
from portfolio_state import save_portfolio_state


def find_cash_hub(portfolio: dict) -> dict | None:
    for fund in portfolio["funds"]:
        if fund.get("role") == "cash_hub":
            return fund
    return None


def ensure_cost_basis(fund: dict) -> float:
    if "cost_basis_value" in fund:
        return float(fund["cost_basis_value"])
    current_value = float(fund.get("current_value", 0.0))
    holding_pnl = float(fund.get("holding_pnl", 0.0))
    basis = current_value - holding_pnl
    fund["cost_basis_value"] = round(max(0.0, basis), 2)
    return float(fund["cost_basis_value"])


def ensure_units(fund: dict) -> float | None:
    if "holding_units" in fund:
        try:
            units = float(fund["holding_units"])
            if units > 0:
                fund["holding_units"] = round(units, 6)
                return float(fund["holding_units"])
        except (TypeError, ValueError):
            pass
    nav = None
    for key in ("last_valuation_nav", "last_official_nav"):
        try:
            if fund.get(key) not in (None, "", "--"):
                nav = float(fund[key])
                break
        except (TypeError, ValueError):
            continue
    current_value = float(fund.get("current_value", 0.0))
    if nav and nav > 0 and current_value > 0:
        fund["holding_units"] = round(current_value / nav, 6)
        return float(fund["holding_units"])
    return None


def recalc_fund(fund: dict) -> None:
    current_value = round(float(fund.get("current_value", 0.0)), 2)
    cost_basis = round(float(fund.get("cost_basis_value", 0.0)), 2)
    holding_pnl = round(current_value - cost_basis, 2)
    fund["current_value"] = current_value
    fund["cost_basis_value"] = cost_basis
    fund["holding_pnl"] = holding_pnl
    fund["holding_return_pct"] = round((holding_pnl / cost_basis) * 100, 2) if cost_basis > 0 else 0.0


def apply_trade(portfolio: dict, fund_code: str, action: str, amount: float, trade_nav: float | None = None, trade_units: float | None = None) -> dict:
    target = None
    for fund in portfolio["funds"]:
        if fund["fund_code"] == fund_code:
            target = fund
            break
    if target is None:
        raise RuntimeError(f"Fund code not found in portfolio: {fund_code}")

    cash_hub = find_cash_hub(portfolio)
    if cash_hub:
        ensure_cost_basis(cash_hub)
        ensure_units(cash_hub)
    ensure_cost_basis(target)
    ensure_units(target)

    amount = round(float(amount), 2)
    if amount <= 0:
        raise RuntimeError("Trade amount must be positive.")

    if trade_units is not None:
        trade_units = round(float(trade_units), 6)
        if trade_units <= 0:
            raise RuntimeError("Trade units must be positive.")
    elif trade_nav is not None:
        trade_nav = round(float(trade_nav), 6)
        if trade_nav <= 0:
            raise RuntimeError("Trade nav must be positive.")

    def infer_trade_units(fund: dict, amount_value: float) -> float | None:
        if trade_units is not None:
            return trade_units
        if trade_nav is not None:
            return round(amount_value / trade_nav, 6)
        existing_units = ensure_units(fund)
        current_value = float(fund.get("current_value", 0.0))
        if existing_units and current_value > 0:
            implied_nav = current_value / existing_units
            if implied_nav > 0:
                return round(amount_value / implied_nav, 6)
        return None

    if action in {"buy", "switch_in"}:
        if cash_hub and cash_hub["fund_code"] != fund_code:
            if float(cash_hub["current_value"]) < amount:
                raise RuntimeError("Cash hub balance is insufficient for this trade.")
            cash_hub["current_value"] = round(float(cash_hub["current_value"]) - amount, 2)
            cash_hub["cost_basis_value"] = round(max(0.0, float(cash_hub["cost_basis_value"]) - amount), 2)
            cash_hub_units = ensure_units(cash_hub)
            if cash_hub_units:
                units_delta = infer_trade_units(cash_hub, amount)
                if units_delta:
                    cash_hub["holding_units"] = round(max(0.0, cash_hub_units - units_delta), 6)
            recalc_fund(cash_hub)
        target["current_value"] = round(float(target["current_value"]) + amount, 2)
        target["cost_basis_value"] = round(float(target["cost_basis_value"]) + amount, 2)
        target_units = ensure_units(target)
        units_delta = infer_trade_units(target, amount)
        if units_delta:
            target["holding_units"] = round((target_units or 0.0) + units_delta, 6)
        if trade_nav is not None:
            target["last_valuation_nav"] = round(trade_nav, 6)
        recalc_fund(target)
    elif action in {"sell", "switch_out"}:
        current_before = float(target["current_value"])
        if current_before < amount:
            raise RuntimeError("Trade amount exceeds current position value.")
        cost_basis_before = float(target["cost_basis_value"])
        sold_cost = (cost_basis_before * amount / current_before) if current_before > 0 else 0.0
        target["current_value"] = round(current_before - amount, 2)
        target["cost_basis_value"] = round(max(0.0, cost_basis_before - sold_cost), 2)
        target_units = ensure_units(target)
        units_delta = infer_trade_units(target, amount)
        if target_units and units_delta:
            target["holding_units"] = round(max(0.0, target_units - units_delta), 6)
        if trade_nav is not None:
            target["last_valuation_nav"] = round(trade_nav, 6)
        recalc_fund(target)
        if cash_hub and cash_hub["fund_code"] != fund_code:
            cash_hub["current_value"] = round(float(cash_hub["current_value"]) + amount, 2)
            cash_hub["cost_basis_value"] = round(float(cash_hub["cost_basis_value"]) + amount, 2)
            cash_hub_units = ensure_units(cash_hub)
            units_delta = infer_trade_units(cash_hub, amount)
            if units_delta:
                cash_hub["holding_units"] = round((cash_hub_units or 0.0) + units_delta, 6)
            recalc_fund(cash_hub)
    else:
        raise RuntimeError(f"Unsupported trade action: {action}")

    portfolio["total_value"] = round(sum(float(fund.get("current_value", 0.0)) for fund in portfolio["funds"]), 2)
    portfolio["holding_pnl"] = round(sum(float(fund.get("holding_pnl", 0.0)) for fund in portfolio["funds"]), 2)
    return portfolio


def save_portfolio(agent_home, portfolio: dict, *, event_date: str | None = None, source: str = "trade_update") -> Path:
    current_path, _snapshot_path = save_portfolio_state(
        agent_home,
        portfolio,
        source=source,
        event_date=event_date or portfolio.get("as_of_date", "") or "unknown",
        event_type=source,
    )
    return current_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a single trade to the portfolio state.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--fund-code", required=True)
    parser.add_argument("--action", required=True, choices=["buy", "sell", "switch_in", "switch_out"])
    parser.add_argument("--amount", required=True, type=float)
    parser.add_argument("--trade-nav", type=float, help="Optional trade NAV used to update holding units precisely.")
    parser.add_argument("--units", type=float, help="Optional exact holding units for this trade.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    portfolio = load_portfolio(agent_home)
    updated = apply_trade(portfolio, args.fund_code, args.action, args.amount, trade_nav=args.trade_nav, trade_units=args.units)
    print(save_portfolio(agent_home, updated))


if __name__ == "__main__":
    main()
