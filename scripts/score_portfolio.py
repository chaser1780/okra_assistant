from __future__ import annotations

import argparse
from collections import defaultdict

from common import (
    dump_json,
    ensure_layout,
    intraday_proxy_path,
    load_json,
    load_market_overrides,
    load_portfolio,
    load_strategy,
    news_path,
    portfolio_advice_path,
    quote_path,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
)


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def floor_to_100(value: float) -> float:
    if value <= 0:
        return 0.0
    return float(int(value // 100) * 100)


def summarize_news(items: list[dict]) -> dict:
    positive = sum(1 for item in items if item.get("impact") == "positive")
    negative = sum(1 for item in items if item.get("impact") == "negative")
    neutral = sum(1 for item in items if item.get("impact") == "neutral")
    return {"count": len(items), "positive": positive, "negative": negative, "neutral": neutral}


def collect_manual_bias(overrides: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in overrides.get("biases", []):
        grouped[item.get("style_group", "unknown")].append(item)
    return grouped


def choose_tactical_action(fund: dict, score: float, proxy_change_pct: float, news_summary: dict, strategy: dict) -> tuple[str, float, str]:
    tactical = strategy["tactical"]
    current_value = float(fund["current_value"])
    cap_value = float(fund.get("cap_value", tactical["default_cap_value"]))
    return_pct = float(fund.get("holding_return_pct", 0.0))
    remaining_room = max(0.0, cap_value - current_value)

    if score >= tactical["strong_add_score"] and proxy_change_pct > 0 and remaining_room >= tactical["min_add_amount"]:
        amount = tactical["max_add_amount"] if score >= tactical["very_strong_add_score"] else tactical["mid_add_amount"]
        amount = min(amount, floor_to_100(remaining_room))
        if amount >= tactical["min_add_amount"]:
            return "add", amount, "盘中代理偏强且仓位仍低于上限，允许小到中等幅度加仓。"

    if score <= tactical["trim_score"] and return_pct > tactical["winner_trim_return_pct"] and current_value >= tactical["min_reduce_amount"]:
        amount = tactical["max_reduce_amount"] if return_pct >= tactical["winner_large_trim_return_pct"] else tactical["mid_reduce_amount"]
        amount = min(amount, floor_to_100(current_value))
        if amount >= tactical["min_reduce_amount"]:
            return "reduce", amount, "持仓已有盈利且盘中代理转弱，优先做盈利减仓。"

    if score <= tactical["switch_out_score"] and news_summary["negative"] > 0 and current_value >= tactical["min_reduce_amount"]:
        amount = min(tactical["max_reduce_amount"], floor_to_100(current_value))
        if amount >= tactical["min_reduce_amount"]:
            return "switch_out", amount, "新闻和盘中信号同时偏弱，建议分批切回资金仓。"

    return "hold", 0.0, "暂无足够强的盘中信号，不建议今天主动调整。"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate portfolio-level daily advice.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    strategy = load_strategy(agent_home)
    portfolio = load_portfolio(agent_home)
    overrides = load_market_overrides(agent_home)

    quotes_payload = load_json(quote_path(agent_home, report_date))
    news_payload = load_json(news_path(agent_home, report_date))
    proxies_payload = load_json(intraday_proxy_path(agent_home, report_date))

    quotes_by_code = {item["code"]: item for item in quotes_payload.get("funds", [])}
    news_by_code: dict[str, list[dict]] = defaultdict(list)
    for item in news_payload.get("items", []):
        news_by_code[item["code"]].append(item)
    proxies_by_code = {item["proxy_fund_code"]: item for item in proxies_payload.get("proxies", [])}
    manual_bias_by_group = collect_manual_bias(overrides)

    daily_max_trade = float(strategy["portfolio"]["daily_max_trade_amount"])
    fixed_dca_total = 0.0
    available_cash_hub = 0.0

    recommendations: list[dict] = []
    dca_actions: list[dict] = []
    tactical_candidates: list[dict] = []
    reduce_candidates: list[dict] = []
    hold_actions: list[dict] = []

    for fund in portfolio["funds"]:
        code = fund["fund_code"]
        role = fund["role"]
        quote = quotes_by_code.get(code, {})
        proxy = proxies_by_code.get(code, {})
        news_summary = summarize_news(news_by_code.get(code, []))
        manual_bias_items = manual_bias_by_group.get(fund.get("style_group", "unknown"), [])
        manual_bias = sum(float(item.get("score_adjustment", 0.0)) for item in manual_bias_items)

        if role == "core_dca":
            amount = float(fund.get("fixed_daily_buy_amount", strategy["core_dca"]["amount_per_fund"]))
            fixed_dca_total += amount
            dca_actions.append({
                "fund_code": code,
                "fund_name": fund["fund_name"],
                "action": "scheduled_dca",
                "amount": amount,
                "reason": "按你的规则执行固定定投，不参与额外加仓判断。",
            })
            continue

        if role == "cash_hub":
            cash_floor = float(strategy["portfolio"]["cash_hub_floor"])
            locked_amount = float(fund.get("locked_amount", 0.0))
            available_cash_hub = max(0.0, float(fund["current_value"]) - cash_floor - locked_amount)
            hold_actions.append({
                "fund_code": code,
                "fund_name": fund["fund_name"],
                "action": "buffer_hold",
                "amount": 0.0,
                "reason": f"作为资金存储仓，当前可调拨参考金额约 {available_cash_hub:.2f} 元。",
            })
            continue

        if role == "fixed_hold":
            hold_actions.append({
                "fund_code": code,
                "fund_name": fund["fund_name"],
                "action": "locked_hold",
                "amount": 0.0,
                "reason": "按你的规则保持不动，不纳入日常调仓。",
            })
            continue

        proxy_change_pct = float(proxy.get("change_pct", 0.0) or 0.0)
        nav_change_pct = float(quote.get("day_change_pct", 0.0) or 0.0)
        return_pct = float(fund.get("holding_return_pct", 0.0))
        tactical = strategy["tactical"]
        score = 50.0
        score += proxy_change_pct * float(tactical["proxy_weight"])
        score += nav_change_pct * float(tactical["nav_weight"])
        score += news_summary["positive"] * float(tactical["news_positive_weight"])
        score += news_summary["negative"] * float(tactical["news_negative_weight"])
        score += manual_bias

        if return_pct <= float(tactical["loss_rebound_return_threshold"]) and proxy_change_pct >= float(tactical["loss_rebound_proxy_threshold"]):
            score += float(tactical["loss_rebound_bonus"])
        if return_pct >= float(tactical["winner_trim_return_pct"]) and proxy_change_pct <= float(tactical["winner_trim_proxy_threshold"]):
            score -= float(tactical["winner_trim_penalty"])
        if proxy.get("stale"):
            score -= float(tactical["stale_proxy_penalty"])
        if float(fund["current_value"]) >= float(fund.get("cap_value", tactical["default_cap_value"])) * 0.95:
            score -= float(tactical["near_cap_penalty"])

        score = round(clamp(score), 1)
        action, amount, reason = choose_tactical_action(fund, score, proxy_change_pct, news_summary, strategy)
        recommendation = {
            "fund_code": code,
            "fund_name": fund["fund_name"],
            "role": role,
            "style_group": fund.get("style_group", "unknown"),
            "score": score,
            "action": action,
            "amount": amount,
            "holding_return_pct": return_pct,
            "current_value": float(fund["current_value"]),
            "cap_value": float(fund.get("cap_value", tactical["default_cap_value"])),
            "proxy_symbol": fund.get("proxy_symbol", ""),
            "proxy_name": fund.get("proxy_name", ""),
            "proxy_change_pct": proxy_change_pct,
            "nav_change_pct": nav_change_pct,
            "news_summary": news_summary,
            "manual_bias_items": manual_bias_items,
            "reason": reason,
            "quote_as_of": quote.get("as_of_date", ""),
            "proxy_trade_date": proxy.get("trade_date", ""),
            "proxy_trade_time": proxy.get("trade_time", ""),
            "proxy_stale": bool(proxy.get("stale", False)),
        }
        recommendations.append(recommendation)
        if action == "add":
            tactical_candidates.append(recommendation)
        elif action in {"reduce", "switch_out"}:
            reduce_candidates.append(recommendation)
        else:
            hold_actions.append(recommendation)

    tactical_budget = max(0.0, daily_max_trade - fixed_dca_total)
    tactical_actions: list[dict] = []
    gross_trade_used = 0.0

    for candidate in sorted(reduce_candidates, key=lambda item: item["score"]):
        amount = candidate["amount"]
        if not amount or gross_trade_used + amount > tactical_budget:
            continue
        tactical_actions.append(candidate)
        gross_trade_used += amount

    funding_capacity = available_cash_hub + sum(item["amount"] for item in tactical_actions if item["action"] in {"reduce", "switch_out"})
    for candidate in sorted(tactical_candidates, key=lambda item: item["score"], reverse=True):
        amount = candidate["amount"]
        if not amount or gross_trade_used + amount > tactical_budget or amount > funding_capacity:
            continue
        tactical_actions.append(candidate)
        gross_trade_used += amount
        funding_capacity -= amount
        if len([item for item in tactical_actions if item["action"] in {"add", "reduce", "switch_out"}]) >= int(strategy["tactical"]["max_actions_per_day"]):
            break

    selected_codes = {item["fund_code"] for item in tactical_actions}
    hold_actions.extend([item for item in recommendations if item["fund_code"] not in selected_codes and item["action"] in {"add", "reduce", "switch_out"}])

    payload = {
        "report_date": report_date,
        "generated_at": timestamp_now(),
        "portfolio_name": portfolio["portfolio_name"],
        "risk_profile": strategy["portfolio"]["risk_profile"],
        "daily_max_trade_amount": daily_max_trade,
        "fixed_dca_total": round(fixed_dca_total, 2),
        "tactical_budget": round(tactical_budget, 2),
        "cash_hub_available": round(available_cash_hub, 2),
        "dca_actions": dca_actions,
        "tactical_actions": tactical_actions,
        "hold_actions": hold_actions,
        "all_recommendations": recommendations,
        "external_reference": {
            "use_yangjibao_board_heat": bool(strategy["manual_references"]["use_yangjibao_board_heat"]),
            "manual_bias_count": sum(len(items) for items in manual_bias_by_group.values()),
        },
    }
    output_path = dump_json(portfolio_advice_path(agent_home, report_date), payload)
    print(output_path)


if __name__ == "__main__":
    main()