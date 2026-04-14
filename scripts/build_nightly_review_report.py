from __future__ import annotations

import argparse
from pathlib import Path

from common import ensure_layout, load_json, load_review_memory, nightly_review_report_path, portfolio_valuation_path, resolve_agent_home, resolve_date


def horizon_label(horizon: int) -> str:
    return "T0" if horizon == 0 else f"T+{horizon}"


def collect_reviews(agent_home: Path, review_date: str) -> list[dict]:
    items: list[dict] = []
    for review_dir in (agent_home / "db" / "review_results", agent_home / "db" / "execution_reviews"):
        if not review_dir.exists():
            continue
        for path in sorted(review_dir.glob("*.json")):
            payload = load_json(path)
            if payload.get("review_date") == review_date:
                items.append(payload)
    items.sort(key=lambda item: (item.get("source", "advice"), int(item.get("horizon", 0)), item.get("base_date", "")))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the nightly review markdown report.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--review-date", help="Review date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    review_date = resolve_date(args.review_date)
    reviews = collect_reviews(agent_home, review_date)
    memory = load_review_memory(agent_home)
    valuation_path = portfolio_valuation_path(agent_home, review_date)
    valuation = load_json(valuation_path) if valuation_path.exists() else {}

    advice_reviews = [item for item in reviews if item.get("source", "advice") == "advice"]
    execution_reviews = [item for item in reviews if item.get("source") == "execution"]
    total_supportive = sum(item.get("summary", {}).get("supportive", 0) for item in advice_reviews)
    total_adverse = sum(item.get("summary", {}).get("adverse", 0) for item in advice_reviews)
    total_missed = sum(item.get("summary", {}).get("missed_upside", 0) for item in advice_reviews)
    total_baseline_better = sum(item.get("no_trade_summary", {}).get("better_than_no_trade", 0) for item in advice_reviews)
    total_baseline_worse = sum(item.get("no_trade_summary", {}).get("worse_than_no_trade", 0) for item in advice_reviews)
    total_execution_reviews = sum(item.get("aggregate_metrics", {}).get("reviewed_item_count", 0) for item in execution_reviews)

    lines = [
        f"# 夜间复盘报告 - {review_date}",
        "",
        f"- 复盘日期：{review_date}",
        f"- 已纳入复盘批次数：{len(reviews)}",
        f"- 支持性结果总数：{total_supportive}",
        f"- 逆向结果总数：{total_adverse}",
        f"- 错失上涨总数：{total_missed}",
        f"- 优于不操作次数：{total_baseline_better}",
        f"- 劣于不操作次数：{total_baseline_worse}",
        f"- 执行复盘动作数：{total_execution_reviews}",
        "",
        "## 本次复盘批次",
    ]

    if reviews:
        for review in reviews:
            label = horizon_label(int(review.get("horizon", 0)))
            source = "建议层" if review.get("source", "advice") == "advice" else "执行层"
            lines.append(
                f"- {source} {label}｜建议日期 {review.get('base_date')}｜supportive={review.get('summary', {}).get('supportive', 0)}｜"
                f"adverse={review.get('summary', {}).get('adverse', 0)}｜missed_upside={review.get('summary', {}).get('missed_upside', 0)}"
            )
    else:
        lines.append("- 当晚没有到期的复盘批次。")

    for review in reviews:
        label = horizon_label(int(review.get("horizon", 0)))
        source = "建议层" if review.get("source", "advice") == "advice" else "执行层"
        lines.extend(
            [
                "",
                f"## {source} {label} 复盘明细（对应建议日期：{review.get('base_date')}）",
            ]
        )
        for item in review.get("items", []):
            lines.append(
                f"- {item['fund_name']}：动作 `{item.get('source_action', item.get('validated_action', 'hold'))}`，结果 `{item['outcome']}`，"
                f"复盘日真实涨跌 {item.get('review_day_change_pct')}%，"
                f"复盘周涨跌 {item.get('review_week_change_pct')}%，"
                f"参考估值信号 {item.get('signal_estimate_change_pct')}%，"
                f"参考代理信号 {item.get('signal_proxy_change_pct')}%，"
                f"相对参考基准 {item.get('excess_return_vs_benchmark_pct')}%，"
                f"相对不操作：{item.get('no_trade_baseline')}，"
                f"估算边际收益 {item.get('estimated_edge_vs_no_trade_amount')} 元，"
                f"估算交易成本 {item.get('estimated_transaction_cost_amount')} 元，"
                f"成本后边际收益 {item.get('net_edge_after_cost_amount')} 元。"
            )
        if not review.get("items"):
            lines.append("- 本批次没有可复盘动作。")

    lines.extend(["", "## 记忆更新"])
    recent_lessons = memory.get("lessons", [])[-8:]
    if recent_lessons:
        for lesson in recent_lessons:
            lines.append(f"- [{horizon_label(int(lesson.get('horizon', 0)))}] {lesson['text']}")
    else:
        lines.append("- 暂无历史记忆。")

    recent_bias = memory.get("bias_adjustments", [])[-8:]
    if recent_bias:
        lines.extend(["", "## 偏置调整"])
        for item in recent_bias:
            lines.append(
                f"- [{item['scope']}] {item['target']}：{item['adjustment']}（{item['reason']}）"
            )

    recent_feedback = memory.get("agent_feedback", [])[-8:]
    if recent_feedback:
        lines.extend(["", "## Agent Feedback"])
        for item in recent_feedback:
            lines.append(
                f"- [{horizon_label(int(item.get('horizon', 0)))}] {item['agent_name']}：{item['bias']}（{item['reason']}）"
            )

    if valuation:
        lines.extend(
            [
                "",
                "## 官方净值重估摘要",
                f"- 重估日期：{valuation.get('report_date', review_date)}",
                f"- 重估生成时间：{valuation.get('generated_at', '—')}",
                f"- 更新基金数量：{valuation.get('updated_fund_count', 0)}",
                f"- 跳过基金数量：{valuation.get('skipped_fund_count', 0)}",
                f"- 存在滞后净值基金：{', '.join(valuation.get('stale_fund_codes', []) or []) or '无'}",
            ]
        )

    path = nightly_review_report_path(agent_home, review_date)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
