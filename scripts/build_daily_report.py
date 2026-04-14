from __future__ import annotations

import argparse
from collections import Counter

from common import ensure_layout, load_json, load_portfolio, load_strategy, news_path, report_path, resolve_agent_home, resolve_date, score_path, timestamp_now, validated_advice_path
from portfolio_exposure import STRATEGY_BUCKET_LABELS, analyze_portfolio_exposure


def money_line(amount: float) -> str:
    return f"{amount:.2f} 元"


def related_news(news_lookup: dict[str, list[dict]], fund_code: str, limit: int = 2) -> list[str]:
    items = news_lookup.get(fund_code, [])[:limit]
    if not items:
        return ["- 今日未抓到直接相关的新增新闻"]
    return [f"- [{item['title']}]({item['url']})（{item['source_name']}，{item['published_at']}，{item['impact']}）" for item in items]


def render_action_summary(advice: dict) -> str:
    action_counter = Counter(item.get("validated_action", "hold") for item in advice.get("tactical_actions", []))
    dca_count = len(advice.get("dca_actions", []) or [])
    hold_count = len(advice.get("hold_actions", []) or [])
    total_trade_amount = sum(float(item.get("validated_amount", 0.0) or 0.0) for section in ("tactical_actions", "dca_actions") for item in advice.get(section, []) or [])
    lines = [
        f"- 主动战术动作：{sum(action_counter.values())} 条",
        f"- 固定定投动作：{dca_count} 条",
        f"- 暂不动作基金：{hold_count} 条",
        f"- 计划总交易额：{money_line(total_trade_amount)}",
    ]
    if action_counter:
        lines.append("- 战术动作结构：" + "；".join(f"{action} {count} 条" for action, count in sorted(action_counter.items())))
    return "\n".join(lines)


def render_priority_actions(advice: dict, news_lookup: dict[str, list[dict]]) -> str:
    sections: list[str] = []
    for item in (advice.get("tactical_actions", []) or []) + (advice.get("dca_actions", []) or []):
        sections.append(
            "\n".join(
                [
                    f"### {item['fund_name']}（{item['fund_code']}）",
                    f"- 动作：`{item['validated_action']}` {money_line(float(item.get('validated_amount', 0.0)))}",
                    f"- 策略桶：{STRATEGY_BUCKET_LABELS.get(item.get('strategy_bucket', ''), item.get('strategy_bucket', '未分类'))}",
                    f"- 置信度：{item.get('confidence', 0.0):.2f}",
                    f"- 核心判断：{item.get('thesis', '无')}",
                    f"- 依据：{'；'.join(item.get('evidence', [])) or '无'}",
                    f"- 风险：{'；'.join(item.get('risks', [])) or '无'}",
                    f"- 执行状态：{item.get('execution_status', 'pending')}",
                    "- 相关新闻：",
                    *related_news(news_lookup, item["fund_code"]),
                ]
            )
        )
    if not sections:
        return "### 今日无新增动作\n- 当前没有通过约束校验的主动战术动作，先观察。"
    return "\n\n".join(sections)


def render_hold_section(advice: dict) -> str:
    items = advice.get("hold_actions", []) or []
    if not items:
        return "- 今日没有额外观望项。"
    lines = []
    for item in items:
        bucket = STRATEGY_BUCKET_LABELS.get(item.get("strategy_bucket", ""), item.get("strategy_bucket", "未分类"))
        lines.append(f"- {item['fund_name']}：{item.get('thesis', '继续观察')}（{bucket}）")
    return "\n".join(lines)


def render_bucket_drift(exposure: dict) -> str:
    plan = exposure.get("allocation_plan", {})
    items = plan.get("bucket_checklist", []) or []
    lines = []
    for item in items:
        lines.append(f"- {item.get('label', item.get('bucket', '未知'))}：{item.get('detail', '暂无')}")
    for suggestion in plan.get("rebalance_suggestions", []) or []:
        lines.append(f"- 再平衡提示：{suggestion}")
    return "\n".join(lines)


def build_report(report_date: str, portfolio: dict, strategy: dict, advice: dict, news_lookup: dict[str, list[dict]]) -> str:
    exposure = analyze_portfolio_exposure(portfolio, strategy)
    market_view = advice.get("market_view", {}) or {}
    lines = [
        f"# 基金日报 - {report_date}",
        "",
        f"- 生成时间：{timestamp_now()}",
        f"- 风险画像：{advice.get('risk_profile', strategy.get('portfolio', {}).get('risk_profile', 'balanced'))}",
        f"- 组合名称：{portfolio.get('portfolio_name', '我的基金组合')}",
        f"- 组合估值日期：{portfolio.get('as_of_date', '未知')}",
        f"- 建议模式：{advice.get('advice_mode', 'validated') or 'validated'}",
        "",
        "## 今日结论",
        render_action_summary(advice),
        "",
        "## 今日策略",
        f"- 市场状态：{market_view.get('regime', 'unknown')}",
        f"- 综合结论：{market_view.get('summary', '无')}",
    ]
    for driver in market_view.get("key_drivers", []) or []:
        lines.append(f"- 关键驱动：{driver}")

    lines.extend(
        [
            "",
            "## 今日优先执行",
            render_priority_actions(advice, news_lookup),
            "",
            "## 暂不动作",
            render_hold_section(advice),
            "",
            "## 组合结构与再平衡",
            render_bucket_drift(exposure),
            "",
            "## 组合风险提醒",
        ]
    )
    for alert in exposure.get("alerts", []) or ["当前没有额外高优先风险提醒。"]:
        lines.append(f"- {alert}")

    lines.extend(
        [
            "",
            "## 组合观察",
        ]
    )
    for item in advice.get("cross_fund_observations", []) or ["今天以少量、集中、可解释的动作优先。"]:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## 风险提示",
            "本报告仅供研究与跟踪，不构成个人化投资建议，请结合资产配置、流动性需求和真实持仓再做决策。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_fallback_score_report(report_date: str, portfolio: dict, strategy: dict, score_payload: dict, news_lookup: dict[str, list[dict]]) -> str:
    funds = score_payload.get("funds", []) or []
    lines = [
        f"# 基金日报 - {report_date}",
        "",
        f"- 生成时间：{timestamp_now()}",
        f"- 风险画像：{strategy.get('portfolio', {}).get('risk_profile', 'balanced')}",
        f"- 组合名称：{portfolio.get('portfolio_name', '我的基金组合')}",
        "- 当前状态：最终建议尚未生成，以下仅展示评分层临时视图。",
        "",
        "## 评分层概览",
        f"- 覆盖基金数：{len(funds)}",
    ]
    for item in funds[:10]:
        lines.extend(
            [
                "",
                f"### {item.get('name', item.get('code', '未知'))}（{item.get('code', '')}）",
                f"- 评分层动作：`{item.get('action', 'observe')}`",
                f"- 综合评分：{item.get('score', 0)}",
                f"- 风险提示：{'；'.join(item.get('risk_flags', [])) or '无'}",
                "- 相关新闻：",
                *(related_news(news_lookup, item.get("code", ""))),
            ]
        )
    lines.extend(
        [
            "",
            "## 风险提示",
            "当前仍缺少 validated_advice，请先完成日内研究链路后再查看最终执行口径。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the validated daily Markdown report.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    portfolio = load_portfolio(agent_home)
    strategy = load_strategy(agent_home)
    news_payload = load_json(news_path(agent_home, report_date)) if news_path(agent_home, report_date).exists() else {"items": []}
    news_lookup: dict[str, list[dict]] = {}
    for item in news_payload.get("items", []):
        news_lookup.setdefault(item["code"], []).append(item)

    validated_path = validated_advice_path(agent_home, report_date)
    if validated_path.exists():
        advice = load_json(validated_path)
        report_text = build_report(report_date, portfolio, strategy, advice, news_lookup)
    else:
        score_payload = load_json(score_path(agent_home, report_date)) if score_path(agent_home, report_date).exists() else {"funds": []}
        report_text = build_fallback_score_report(report_date, portfolio, strategy, score_payload, news_lookup)
    output_path = report_path(agent_home, report_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
