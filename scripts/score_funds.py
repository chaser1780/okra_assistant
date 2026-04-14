from __future__ import annotations

import argparse
from collections import defaultdict

from common import (
    dump_json,
    ensure_layout,
    load_json,
    load_settings,
    load_watchlist,
    news_path,
    quote_path,
    resolve_agent_home,
    resolve_date,
    score_path,
    timestamp_now,
)


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def choose_action(score: float) -> str:
    if score >= 70:
        return "add"
    if score >= 55:
        return "observe"
    if score >= 40:
        return "reduce"
    return "avoid"


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine quotes and news into daily fund scores.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    settings = load_settings(agent_home)
    watchlist = load_watchlist(agent_home)
    report_date = resolve_date(args.date)

    quotes_payload = load_json(quote_path(agent_home, report_date))
    news_payload = load_json(news_path(agent_home, report_date))
    quotes_by_code = {item["code"]: item for item in quotes_payload["funds"]}
    news_by_code: dict[str, list[dict]] = defaultdict(list)
    for item in news_payload["items"]:
        news_by_code[item["code"]].append(item)

    scoring = settings["scoring"]
    impact_weights = scoring["impact_weights"]
    top_news = settings["report"]["top_news_per_fund"]
    conservative_mode = settings["advice"]["risk_profile"] == "conservative"

    funds: list[dict] = []
    for fund in watchlist["funds"]:
        code = fund["code"]
        quote = quotes_by_code.get(code)
        if not quote:
            continue

        related_news = news_by_code.get(code, [])[:top_news]
        performance_score = 50.0
        performance_score += quote["day_change_pct"] * scoring["day_change_weight"]
        performance_score += quote["month_change_pct"] * scoring["month_change_weight"]

        news_score = sum(impact_weights[item["impact"]] for item in related_news)
        volatility_penalty = 0.0
        if conservative_mode and fund.get("risk_level") == "high":
            volatility_penalty = scoring["high_volatility_penalty"]

        total_score = round(clamp(performance_score + news_score - volatility_penalty), 1)
        action = choose_action(total_score)

        reasons = [
            f"日涨跌 {quote['day_change_pct']}%",
            f"近一月 {quote['month_change_pct']}%",
            f"相关新闻 {len(related_news)} 条",
        ]
        risk_flags: list[str] = []
        if quote["day_change_pct"] <= scoring["drawdown_alert_pct"]:
            risk_flags.append("当日跌幅触发预警阈值")
        if any(item["impact"] == "negative" for item in related_news):
            risk_flags.append("出现负面新闻")
        if fund.get("risk_level") == "high":
            risk_flags.append("基金自身波动级别较高")
        if not related_news:
            risk_flags.append("缺少相关新闻样本")

        confidence = 0.55
        if related_news:
            confidence += 0.2
        if fund.get("benchmark"):
            confidence += 0.1

        funds.append(
            {
                "code": code,
                "name": fund["name"],
                "category": fund.get("category", "unknown"),
                "score": total_score,
                "action": action,
                "confidence": round(min(confidence, 0.95), 2),
                "reasons": reasons,
                "risk_flags": risk_flags,
                "news_count": len(related_news),
                "quote": quote,
            }
        )

    payload = {
        "report_date": report_date,
        "generated_at": timestamp_now(),
        "risk_profile": settings["advice"]["risk_profile"],
        "funds": funds,
    }
    output_path = dump_json(score_path(agent_home, report_date), payload)
    print(output_path)


if __name__ == "__main__":
    main()
