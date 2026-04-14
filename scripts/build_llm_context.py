from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from common import (
    dump_json,
    ensure_layout,
    estimated_nav_path,
    fund_profile_path,
    intraday_proxy_path,
    llm_context_path,
    load_json,
    load_market_overrides,
    load_portfolio,
    load_review_memory,
    load_strategy,
    news_path,
    parse_date_text,
    quote_path,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
)
from models import EstimateSnapshot, FundContextItem, FundProfile, LlmContext, NewsItem, PortfolioFund, ProxySnapshot, QuoteSnapshot
from portfolio_exposure import analyze_portfolio_exposure, infer_strategy_bucket


def summarize_news(items: list[NewsItem], limit: int = 5) -> list[NewsItem]:
    ranked = sorted(items, key=lambda item: item.get("published_at", ""), reverse=True)
    return [
        {
            "published_at": item.get("published_at", ""),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "impact": item.get("impact", "neutral"),
            "source_name": item.get("source_name", ""),
            "url": item.get("url", ""),
        }
        for item in ranked[:limit]
    ]


def build_constraints(portfolio: dict, strategy: dict) -> dict:
    exposure = analyze_portfolio_exposure(portfolio, strategy)
    allocation_plan = exposure.get("allocation_plan", {})
    fixed_dca_total = sum(float(fund.get("fixed_daily_buy_amount", 0.0)) for fund in portfolio["funds"] if fund["role"] == "core_dca")
    tactical_budget = max(0.0, float(strategy["portfolio"]["daily_max_trade_amount"]) - fixed_dca_total)
    return {
        "daily_max_trade_amount": float(strategy["portfolio"]["daily_max_trade_amount"]),
        "fixed_dca_total": fixed_dca_total,
        "tactical_budget_after_dca": tactical_budget,
        "cash_hub_floor": float(strategy["portfolio"]["cash_hub_floor"]),
        "single_tactical_cap_value": float(strategy["tactical"]["default_cap_value"]),
        "dca_rule": "标普500和纳指100仅允许固定定投，不允许额外加仓。",
        "fixed_hold_rule": "华泰保兴尊睿6个月持有期债券A保持不动。",
        "cash_hub_rule": "兴业中证同业存单AAA指数7天持有期是资金存储仓，需要保留底仓。",
        "execution_rule": "允许清仓，允许换基，最低持仓为0。",
        "allocation_targets_pct": allocation_plan.get("targets_pct", {}),
        "allocation_current_pct": allocation_plan.get("current_pct", {}),
        "allocation_drift_pct": allocation_plan.get("drift_pct", {}),
        "rebalance_band_pct": allocation_plan.get("rebalance_band_pct", 5.0),
        "rebalance_needed": bool(allocation_plan.get("rebalance_needed", False)),
        "rebalance_suggestions": allocation_plan.get("rebalance_suggestions", []),
    }


def build_fund_snapshot(
    fund: PortfolioFund,
    quote: QuoteSnapshot,
    proxy: ProxySnapshot,
    estimate: EstimateSnapshot,
    profile: FundProfile,
    news_items: list[NewsItem],
) -> FundContextItem:
    return {
        "fund_code": fund["fund_code"],
        "fund_name": fund["fund_name"],
        "role": fund["role"],
        "style_group": fund.get("style_group", "unknown"),
        "current_value": float(fund["current_value"]),
        "holding_pnl": float(fund.get("holding_pnl", 0.0)),
        "holding_return_pct": float(fund.get("holding_return_pct", 0.0)),
        "cap_value": float(fund.get("cap_value", 0.0)),
        "strategy_bucket": infer_strategy_bucket(fund),
        "allow_trade": bool(fund.get("allow_trade", False)),
        "locked_amount": float(fund.get("locked_amount", 0.0)),
        "fixed_daily_buy_amount": float(fund.get("fixed_daily_buy_amount", 0.0)),
        "quote": quote,
        "intraday_proxy": proxy,
        "estimated_nav": estimate,
        "fund_profile": profile,
        "recent_news": summarize_news(news_items),
    }


def build_memory_digest(memory: dict) -> dict:
    analysis_date = memory.get("_analysis_date", "")
    analysis_day = parse_date_text(analysis_date)
    active_bias_adjustments = []
    expired_bias_count = 0
    for item in memory.get("bias_adjustments", []):
        expires_on = parse_date_text(item.get("expires_on"))
        if analysis_day is not None and expires_on is not None and expires_on < analysis_day:
            expired_bias_count += 1
            continue
        active_bias_adjustments.append(item)
    return {
        "updated_at": memory.get("updated_at", ""),
        "recent_lessons": memory.get("lessons", [])[-8:],
        "recent_review_history": memory.get("review_history", [])[-5:],
        "recent_bias_adjustments": active_bias_adjustments[-8:],
        "expired_bias_adjustment_count": expired_bias_count,
        "recent_agent_feedback": memory.get("agent_feedback", [])[-8:],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the structured LLM context for portfolio advice.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--mode", default="intraday", choices=["intraday", "nightly"])
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    portfolio = load_portfolio(agent_home)
    strategy = load_strategy(agent_home)
    overrides = load_market_overrides(agent_home)
    memory = load_review_memory(agent_home)
    memory["_analysis_date"] = report_date
    quotes_payload = load_json(quote_path(agent_home, report_date))
    news_payload = load_json(news_path(agent_home, report_date))
    proxies_payload = load_json(intraday_proxy_path(agent_home, report_date))
    estimate_payload = load_json(estimated_nav_path(agent_home, report_date)) if estimated_nav_path(agent_home, report_date).exists() else {"items": []}
    profile_payload = load_json(fund_profile_path(agent_home, report_date)) if fund_profile_path(agent_home, report_date).exists() else {"items": []}

    quotes_by_code = {item["code"]: item for item in quotes_payload.get("funds", [])}
    proxies_by_code = {
        item.get("proxy_fund_code") or item.get("fund_code"): item
        for item in proxies_payload.get("proxies", [])
        if item.get("proxy_fund_code") or item.get("fund_code")
    }
    estimates_by_code = {item["fund_code"]: item for item in estimate_payload.get("items", [])}
    profiles_by_code = {item["fund_code"]: item for item in profile_payload.get("items", [])}
    news_by_code: dict[str, list[dict]] = defaultdict(list)
    for item in news_payload.get("items", []):
        news_by_code[item["code"]].append(item)

    role_counts = Counter(fund["role"] for fund in portfolio["funds"])
    all_proxies_stale = all(bool(item.get("stale", False)) for item in proxies_payload.get("proxies", [])) if proxies_payload.get("proxies") else True
    all_estimates_stale = all(bool(item.get("stale", False)) for item in estimate_payload.get("items", [])) if estimate_payload.get("items") else True
    delayed_official_nav_count = sum(1 for item in quotes_payload.get("funds", []) if bool(item.get("freshness_is_delayed", False)))
    stale_proxy_count = sum(1 for item in proxies_payload.get("proxies", []) if bool(item.get("stale", False)))
    stale_estimate_count = sum(1 for item in estimate_payload.get("items", []) if bool(item.get("stale", False)))
    exposure_summary = analyze_portfolio_exposure(portfolio, strategy)
    context: LlmContext = {
        "analysis_date": report_date,
        "mode": args.mode,
        "generated_at": timestamp_now(),
        "portfolio_summary": {
            "portfolio_name": portfolio["portfolio_name"],
            "total_value": float(portfolio.get("total_value", 0.0)),
            "holding_pnl": float(portfolio.get("holding_pnl", 0.0)),
            "risk_profile": strategy["portfolio"]["risk_profile"],
            "role_counts": dict(role_counts),
            "all_intraday_proxies_stale": all_proxies_stale,
            "all_estimates_stale": all_estimates_stale,
            "stale_proxy_count": stale_proxy_count,
            "stale_estimate_count": stale_estimate_count,
            "delayed_official_nav_count": delayed_official_nav_count,
        },
        "exposure_summary": exposure_summary,
        "constraints": build_constraints(portfolio, strategy),
        "external_reference": {
            "manual_theme_reference_enabled": bool(strategy["manual_references"]["use_yangjibao_board_heat"]),
            "manual_biases": overrides.get("biases", []),
        },
        "memory_digest": build_memory_digest(memory),
        "funds": [
            build_fund_snapshot(
                fund,
                quotes_by_code.get(fund["fund_code"], {}),
                proxies_by_code.get(fund["fund_code"], {}),
                estimates_by_code.get(fund["fund_code"], {}),
                profiles_by_code.get(fund["fund_code"], {}),
                news_by_code.get(fund["fund_code"], []),
            )
            for fund in portfolio["funds"]
        ],
    }

    output_path = dump_json(llm_context_path(agent_home, report_date), context)
    print(output_path)


if __name__ == "__main__":
    main()
