from __future__ import annotations

import argparse
import math
from pathlib import Path

from common import ensure_layout, load_portfolio, resolve_agent_home, timestamp_now
from portfolio_state import save_portfolio_state


V2_FUNDING_MODE = "virtual_external_flows"
V2_TIMING = "end"


def _require_finite_positive(value, what: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"{what} must be a finite positive number")
    return value


def _require_finite_nonnegative(value, what: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise RuntimeError(f"{what} must be a finite non-negative number")
    return value


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
    units = fund.get("holding_units")
    if units is not None:
        try:
            value = float(units)
            if value > 0:
                fund["holding_units"] = round(value, 6)
                return value
        except (TypeError, ValueError):
            pass
    return None


def recalc_fund(fund: dict) -> None:
    current_value = round(float(fund.get("current_value", 0.0)), 2)
    cost_basis = round(float(fund.get("cost_basis_value", 0.0)), 2)
    holding_pnl = round(current_value - cost_basis, 2)
    fund["current_value"] = current_value
    fund["cost_basis_value"] = cost_basis
    fund["holding_pnl"] = holding_pnl
    fund["holding_return_pct"] = round((holding_pnl / cost_basis) * 100, 2) if cost_basis > 0 else 0.0


def _mark_v2(portfolio: dict) -> None:
    """Lazily activate the virtual-external-flows ledger on first v2 operation.

    Old snapshots simply lack these keys and stay readable; historical cash_hub
    holdings are never deleted and never used as an automatic funding source.
    """
    if "simulation_v2" not in portfolio:
        portfolio["simulation_v2"] = {
            "version": 2,
            "funding_mode": V2_FUNDING_MODE,
            "activated_at": timestamp_now(),
        }
    portfolio["external_cashflow_timing"] = V2_TIMING
    portfolio.setdefault("income_adjustment_value", 0.0)


def _resolve_units_delta(amount: float, trade_nav: float | None, trade_units: float | None) -> tuple[float | None, str]:
    """Return (units_delta, valuation_status). Never fabricate units from stale value."""
    if trade_units is not None:
        return round(trade_units, 6), "exact"
    if trade_nav is not None and trade_nav > 0:
        return round(amount / trade_nav, 6), "exact"
    return None, "pending"


def apply_trade(
    portfolio: dict,
    fund_code: str,
    action: str,
    amount: float,
    trade_nav: float | None = None,
    trade_units: float | None = None,
    *,
    fee: float = 0.0,
    trade_date: str | None = None,
) -> dict:
    target = None
    for fund in portfolio["funds"]:
        if str(fund["fund_code"]) == str(fund_code):
            target = fund
            break
    if target is None:
        raise RuntimeError(f"Fund code not found in portfolio: {fund_code}")

    ensure_cost_basis(target)
    target_units = ensure_units(target)

    # Validate before any mutation / v2 marking: finite, sign, and cross-field consistency.
    amount = round(_require_finite_positive(amount, "Trade amount"), 2)
    fee = round(_require_finite_nonnegative(fee or 0.0, "Trade fee"), 2)
    if action in {"sell", "switch_out"} and fee > amount:
        raise RuntimeError("Sell fee exceeds gross amount (would create a fake external inflow).")
    nav = round(_require_finite_positive(trade_nav, "Trade nav"), 6) if trade_nav is not None else None
    units = round(_require_finite_positive(trade_units, "Trade units"), 6) if trade_units is not None else None
    if nav is not None and units is not None:
        # explicit nav+units must agree with the principal amount within tolerance
        if abs(nav * units - amount) > max(0.01, amount * 0.01):
            raise RuntimeError("trade_nav * trade_units disagrees with trade amount; refusing to drift shares")

    _mark_v2(portfolio)

    if action in {"buy", "switch_in"}:
        units_delta, vstatus = _resolve_units_delta(amount, nav, units)
        target["current_value"] = round(float(target["current_value"]) + amount, 2)
        target["cost_basis_value"] = round(float(target["cost_basis_value"]) + amount, 2)
        if units_delta is not None:
            target["holding_units"] = round((target_units or 0.0) + units_delta, 6)
            if units is not None and nav is None:
                target["last_valuation_nav"] = round(amount / units, 6)
                target["last_valuation_nav_source"] = "derived_from_explicit_trade"
            if target_units is None:
                # we know only this delta, not the prior total; never claim the whole holding
                target["units_source"] = "partial_explicit_trade_units"
                vstatus = "pending"
            else:
                target["units_source"] = (
                    "derived_from_explicit_trade" if (units is not None and nav is None) else "actual_trade_units"
                )
        else:
            # do not fabricate units; value bookkeeping stays explicit
            target["units_source"] = "unconfirmed_trade_units"
        if nav is not None:
            target["last_valuation_nav"] = nav
        target["valuation_status"] = vstatus
        recalc_fund(target)
        # user pays net principal + fee out of pocket
        portfolio["external_cashflow"] = round(amount + fee, 2)

    elif action in {"sell", "switch_out"}:
        current_before = float(target["current_value"])
        if current_before < amount:
            raise RuntimeError("Trade amount exceeds current position value.")
        if units is not None and target_units is not None and units > target_units:
            raise RuntimeError("Trade units exceed held units.")
        cost_basis_before = float(target["cost_basis_value"])
        sold_cost = (cost_basis_before * amount / current_before) if current_before > 0 else 0.0
        units_delta, vstatus = _resolve_units_delta(amount, nav, units)
        target["current_value"] = round(current_before - amount, 2)
        target["cost_basis_value"] = round(max(0.0, cost_basis_before - sold_cost), 2)
        fully_closed = current_before - amount <= 0.005
        if fully_closed:
            target["holding_units"] = 0.0
            target["units_source"] = "closed_position"
            target["valuation_status"] = "exact"
        elif units_delta is not None:
            target["holding_units"] = round(max(0.0, (target_units or 0.0) - units_delta), 6)
            target["units_source"] = "actual_trade_units"
            target["valuation_status"] = vstatus
        else:
            target["units_source"] = "unconfirmed_trade_units"
            target["valuation_status"] = "pending"
        recalc_fund(target)
        # net proceeds (gross - fee) leave the wallet back to the user
        portfolio["external_cashflow"] = round(-(amount - fee), 2)
        if nav is not None:
            target["last_valuation_nav"] = nav
    else:
        raise RuntimeError(f"Unsupported trade action: {action}")

    portfolio["total_value"] = round(
        sum(float(fund.get("current_value", 0.0)) for fund in portfolio["funds"])
        + float(portfolio.get("income_adjustment_value", 0.0)),
        2,
    )
    portfolio["holding_pnl"] = round(sum(float(fund.get("holding_pnl", 0.0)) for fund in portfolio["funds"]), 2)
    return portfolio


def record_cash_dividend(portfolio: dict, fund_code: str, amount: float, *, reinvest: bool, trade_nav: float | None = None) -> dict:
    """Internal dividend bookkeeping with no external cash flow and no double count.

    Cash dividend -> income_adjustment_value (part of net assets, not a cash balance).
    Reinvest -> increase units only (next revaluation turns units into value); never
    also book the income here.
    """
    target = None
    for fund in portfolio["funds"]:
        if str(fund["fund_code"]) == str(fund_code):
            target = fund
            break
    if target is None:
        raise RuntimeError(f"Fund code not found in portfolio: {fund_code}")
    amount = round(_require_finite_positive(amount, "Dividend amount"), 2)
    _mark_v2(portfolio)
    # A dividend is a pending NETTING event, not "unknown units". Trusted units stay trusted;
    # revalue nets the ex-dividend NAV drop against the income and clears this marker.
    pending = portfolio.setdefault("pending_dividend_events", [])
    pending.append({"fund_code": str(fund_code), "amount": amount, "reinvest": bool(reinvest)})
    if reinvest:
        nav = round(_require_finite_positive(trade_nav, "Dividend reinvest nav"), 6) if trade_nav is not None else None
        if nav is None:
            target["valuation_status"] = "pending"
            target["units_source"] = "unconfirmed_dividend_reinvest"
        else:
            target["holding_units"] = round(float(target.get("holding_units") or 0.0) + amount / nav, 6)
            target["units_source"] = "dividend_reinvest_pending"
            target["dividend_netting_pending"] = True
    else:
        portfolio["income_adjustment_value"] = round(float(portfolio.get("income_adjustment_value", 0.0)) + amount, 2)
        target["dividend_netting_pending"] = True
    recalc_fund(target)
    portfolio["external_cashflow"] = 0.0  # internal income, never external
    portfolio["total_value"] = round(
        sum(float(fund.get("current_value", 0.0)) for fund in portfolio["funds"])
        + float(portfolio.get("income_adjustment_value", 0.0)),
        2,
    )
    return portfolio


def record_internal_fee(portfolio: dict, amount: float) -> dict:
    """A fee that is not already captured in an external flow reduces internal adjustment."""
    amount = round(float(amount), 2)
    if amount < 0:
        raise RuntimeError("Fee amount cannot be negative.")
    _mark_v2(portfolio)
    portfolio["income_adjustment_value"] = round(float(portfolio.get("income_adjustment_value", 0.0)) - amount, 2)
    portfolio["external_cashflow"] = 0.0
    portfolio["total_value"] = round(
        sum(float(fund.get("current_value", 0.0)) for fund in portfolio["funds"])
        + float(portfolio.get("income_adjustment_value", 0.0)),
        2,
    )
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
    parser.add_argument("--fee", type=float, default=0.0)
    parser.add_argument("--trade-nav", type=float, help="Optional trade NAV used to update holding units precisely.")
    parser.add_argument("--units", type=float, help="Optional exact holding units for this trade.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    portfolio = load_portfolio(agent_home)
    updated = apply_trade(portfolio, args.fund_code, args.action, args.amount, trade_nav=args.trade_nav, trade_units=args.units, fee=args.fee)
    print(save_portfolio(agent_home, updated))


if __name__ == "__main__":
    main()
