from __future__ import annotations

import argparse
import json
from collections import Counter

from common import (
    ensure_layout,
    estimated_nav_path,
    execution_review_result_path,
    intraday_proxy_path,
    load_json,
    load_portfolio,
    load_watchlist,
    quote_path,
    resolve_agent_home,
    resolve_date,
    review_result_path,
    trade_journal_path,
    validated_advice_path,
)
from trade_constraints import build_trade_constraints


def normalize_action(action: str) -> str:
    lowered = (action or "").lower()
    mapping = {
        "buy": "add",
        "switch_in": "add",
        "sell": "reduce",
        "switch_out": "switch_out",
        "scheduled_dca": "scheduled_dca",
        "add": "add",
        "reduce": "reduce",
        "hold": "hold",
    }
    return mapping.get(lowered, lowered or "hold")


def classify_outcome(action: str, actual_day_change_pct: float | None) -> str:
    normalized = normalize_action(action)
    if actual_day_change_pct is None:
        return "unknown"
    if normalized in {"add", "scheduled_dca"}:
        return "supportive" if actual_day_change_pct > 0 else "adverse"
    if normalized in {"reduce", "switch_out"}:
        return "supportive" if actual_day_change_pct < 0 else "missed_upside"
    if normalized == "hold":
        return "neutral"
    return "neutral"


def compare_against_no_trade(action: str, actual_day_change_pct: float | None) -> str:
    normalized = normalize_action(action)
    if actual_day_change_pct is None:
        return "unknown"
    if normalized == "hold":
        return "same_as_no_trade"
    if normalized in {"add", "scheduled_dca"}:
        return "better_than_no_trade" if actual_day_change_pct > 0 else "worse_than_no_trade"
    if normalized in {"reduce", "switch_out"}:
        return "better_than_no_trade" if actual_day_change_pct < 0 else "worse_than_no_trade"
    return "unknown"


def estimated_edge_vs_no_trade(action: str, amount: float, actual_day_change_pct: float | None) -> float | None:
    normalized = normalize_action(action)
    if actual_day_change_pct is None:
        return None
    edge = round(float(amount) * float(actual_day_change_pct) / 100.0, 2)
    if normalized in {"add", "scheduled_dca"}:
        return edge
    if normalized in {"reduce", "switch_out"}:
        return round(-edge, 2)
    return 0.0


def estimated_transaction_cost_amount(action: str, amount: float, constraint: dict) -> float:
    normalized = normalize_action(action)
    fee_rate = float(constraint.get("estimated_redeem_fee_rate", 0.0) or 0.0)
    if normalized in {"reduce", "switch_out"} and fee_rate > 0:
        return round(float(amount) * fee_rate / 100.0, 2)
    return 0.0


def execution_lag_days(action: str, constraint: dict) -> int:
    normalized = normalize_action(action)
    if normalized in {"add", "scheduled_dca"}:
        return int(constraint.get("purchase_confirm_days", 1) or 1)
    if normalized in {"reduce", "switch_out"}:
        return int(constraint.get("redeem_settlement_days", 1) or 1)
    return 0


def advice_source_items(advice: dict) -> list[dict]:
    items = []
    for section in ("tactical_actions", "dca_actions"):
        for item in advice.get(section, []) or []:
            items.append(
                {
                    "fund_code": item.get("fund_code", ""),
                    "fund_name": item.get("fund_name", ""),
                    "action": item.get("validated_action", "hold"),
                    "amount": float(item.get("validated_amount", 0.0) or 0.0),
                    "suggestion_id": item.get("suggestion_id", ""),
                    "agent_support": item.get("agent_support", []),
                    "thesis": item.get("thesis", ""),
                    "source_section": section,
                    "execution_status": item.get("execution_status", "pending"),
                }
            )
    return items


def execution_source_items(agent_home, base_date: str) -> list[dict]:
    path = trade_journal_path(agent_home, base_date)
    if not path.exists():
        return []
    payload = load_json(path)
    items = []
    for index, item in enumerate(payload.get("items", []) or [], start=1):
        items.append(
            {
                "fund_code": item.get("fund_code", ""),
                "fund_name": item.get("fund_name", ""),
                "action": item.get("action", "hold"),
                "amount": float(item.get("amount", 0.0) or 0.0),
                "suggestion_id": item.get("suggestion_id", ""),
                "agent_support": [],
                "thesis": item.get("note", ""),
                "source_section": "executed_trade",
                "trade_nav": item.get("trade_nav"),
                "trade_units": item.get("units"),
                "trade_index": index,
            }
        )
    return items


def build_review_items(
    source: str,
    source_items: list[dict],
    quotes: dict[str, dict],
    estimates: dict[str, dict],
    proxies: dict[str, dict],
    watchlist: dict[str, dict],
    constraint_map: dict[str, dict],
) -> tuple[list[dict], Counter, Counter]:
    items = []
    outcome_counter = Counter()
    baseline_counter = Counter()
    for item in source_items:
        code = item["fund_code"]
        actual_day_change = quotes.get(code, {}).get("day_change_pct")
        actual_week_change = quotes.get(code, {}).get("week_change_pct")
        signal_estimate = estimates.get(code, {}).get("estimate_change_pct")
        signal_proxy = proxies.get(code, {}).get("change_pct")
        constraint = constraint_map.get(code, {})
        outcome = classify_outcome(item["action"], actual_day_change)
        baseline = compare_against_no_trade(item["action"], actual_day_change)
        edge = estimated_edge_vs_no_trade(item["action"], item["amount"], actual_day_change)
        cost = estimated_transaction_cost_amount(item["action"], item["amount"], constraint)
        benchmark_reference = signal_proxy if signal_proxy is not None else signal_estimate
        outcome_counter[outcome] += 1
        baseline_counter[baseline] += 1
        items.append(
            {
                "review_source": source,
                "fund_code": code,
                "fund_name": item["fund_name"],
                "benchmark_name": watchlist.get(code, {}).get("benchmark", ""),
                "source_action": item["action"],
                "source_amount": item["amount"],
                "source_section": item.get("source_section", ""),
                "suggestion_id": item.get("suggestion_id", ""),
                "agent_support": item.get("agent_support", []),
                "review_day_change_pct": actual_day_change,
                "review_week_change_pct": actual_week_change,
                "signal_estimate_change_pct": signal_estimate,
                "signal_proxy_change_pct": signal_proxy,
                "benchmark_reference_change_pct": benchmark_reference,
                "excess_return_vs_benchmark_pct": round(actual_day_change - benchmark_reference, 2)
                if actual_day_change is not None and benchmark_reference is not None
                else None,
                "outcome": outcome,
                "no_trade_baseline": baseline,
                "estimated_edge_vs_no_trade_amount": edge,
                "estimated_transaction_cost_amount": cost,
                "net_edge_after_cost_amount": round((edge or 0.0) - cost, 2) if edge is not None else None,
                "execution_lag_days": execution_lag_days(item["action"], constraint),
                "redeem_settlement_days": constraint.get("redeem_settlement_days"),
                "purchase_confirm_days": constraint.get("purchase_confirm_days"),
                "conversion_supported": constraint.get("conversion_supported"),
                "estimated_redeem_fee_rate": constraint.get("estimated_redeem_fee_rate"),
            }
        )
    return items, outcome_counter, baseline_counter


def main() -> None:
    parser = argparse.ArgumentParser(description="Create richer review records for advice or executed trades.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--base-date", required=True)
    parser.add_argument("--review-date", help="Review date in YYYY-MM-DD format.")
    parser.add_argument("--horizon", type=int, default=0)
    parser.add_argument("--source", default="advice", choices=["advice", "execution"])
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    base_date = resolve_date(args.base_date)
    review_date = resolve_date(args.review_date)
    portfolio = load_portfolio(agent_home)
    watchlist = {item["code"]: item for item in load_watchlist(agent_home).get("funds", [])}
    constraint_map = build_trade_constraints(agent_home, portfolio, base_date)
    review_quote = load_json(quote_path(agent_home, review_date)) if quote_path(agent_home, review_date).exists() else {"funds": []}
    review_estimate = load_json(estimated_nav_path(agent_home, base_date)) if estimated_nav_path(agent_home, base_date).exists() else {"items": []}
    review_proxy = load_json(intraday_proxy_path(agent_home, base_date)) if intraday_proxy_path(agent_home, base_date).exists() else {"proxies": []}

    quotes = {item["code"]: item for item in review_quote.get("funds", [])}
    estimates = {item["fund_code"]: item for item in review_estimate.get("items", [])}
    proxies = {item["proxy_fund_code"]: item for item in review_proxy.get("proxies", [])}

    if args.source == "advice":
        advice = load_json(validated_advice_path(agent_home, base_date))
        source_items = advice_source_items(advice)
    else:
        source_items = execution_source_items(agent_home, base_date)

    items, outcome_counter, baseline_counter = build_review_items(
        args.source,
        source_items,
        quotes,
        estimates,
        proxies,
        watchlist,
        constraint_map,
    )

    result = {
        "source": args.source,
        "base_date": base_date,
        "review_date": review_date,
        "horizon": args.horizon,
        "summary": {
            "supportive": outcome_counter.get("supportive", 0),
            "adverse": outcome_counter.get("adverse", 0),
            "missed_upside": outcome_counter.get("missed_upside", 0),
            "neutral": outcome_counter.get("neutral", 0),
            "unknown": outcome_counter.get("unknown", 0),
        },
        "no_trade_summary": {
            "better_than_no_trade": baseline_counter.get("better_than_no_trade", 0),
            "worse_than_no_trade": baseline_counter.get("worse_than_no_trade", 0),
            "same_as_no_trade": baseline_counter.get("same_as_no_trade", 0),
            "unknown": baseline_counter.get("unknown", 0),
        },
        "aggregate_metrics": {
            "reviewed_item_count": len(items),
            "total_estimated_edge_vs_no_trade_amount": round(sum(item.get("estimated_edge_vs_no_trade_amount", 0.0) or 0.0 for item in items), 2),
            "total_estimated_transaction_cost_amount": round(sum(item.get("estimated_transaction_cost_amount", 0.0) or 0.0 for item in items), 2),
            "total_net_edge_after_cost_amount": round(sum(item.get("net_edge_after_cost_amount", 0.0) or 0.0 for item in items), 2),
        },
        "items": items,
    }

    path = review_result_path(agent_home, base_date, args.horizon) if args.source == "advice" else execution_review_result_path(agent_home, base_date, args.horizon)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
