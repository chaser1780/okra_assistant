from __future__ import annotations

import argparse
from copy import deepcopy

from common import ensure_layout, fund_profile_path, load_json, load_portfolio, load_strategy, portfolio_report_path, resolve_agent_home, resolve_date, validated_advice_path
from portfolio_exposure import STRATEGY_BUCKET_LABELS, analyze_portfolio_exposure


def money_line(amount: float) -> str:
    return f"{amount:.2f} 元"


def join_or_none(items: list[str]) -> str:
    return "；".join(item for item in items if item) if items else "无"


def render_action_item(item: dict) -> list[str]:
    lines = [f"### {item['fund_name']}"]
    lines.append(f"- 动作：`{item['validated_action']}` {money_line(float(item.get('validated_amount', 0.0)))}")
    lines.append(f"- 模型原建议：`{item.get('model_action', 'hold')}`")
    lines.append(f"- 置信度：{item.get('confidence', 0.0):.2f}")
    lines.append(f"- 策略桶：{STRATEGY_BUCKET_LABELS.get(item.get('strategy_bucket', ''), item.get('strategy_bucket', '未分类'))}")
    if item.get("agent_support"):
        lines.append(f"- 参考智能体：{', '.join(item['agent_support'])}")
    lines.append(f"- 核心判断：{item.get('thesis', '无')}")
    lines.append(f"- 依据：{join_or_none(item.get('evidence', []))}")
    lines.append(f"- 风险：{join_or_none(item.get('risks', []))}")
    lines.append(f"- 规则校验：{join_or_none(item.get('validation_notes', []))}")
    return lines


def render_bucket_summary(exposure: dict) -> list[str]:
    plan = exposure.get("allocation_plan", {})
    checklist = plan.get("bucket_checklist", []) or []
    lines = ["## 目标配置与偏离"]
    for item in checklist:
        lines.append(f"- {item.get('label', item.get('bucket', '未知'))}：{item.get('detail', '暂无')}")
        guidance = item.get("guidance")
        if guidance:
            lines.append(f"- 配置说明：{guidance}")
    lines.append(f"- 再平衡带宽：{plan.get('rebalance_band_pct', 5.0)}%")
    lines.append(f"- 是否需要再平衡：{'是' if plan.get('rebalance_needed') else '否'}")
    return lines


def render_bucket_actions(exposure: dict) -> list[str]:
    plan = exposure.get("allocation_plan", {})
    lines = ["## 再平衡建议"]
    for item in plan.get("rebalance_suggestions", []) or ["当前没有额外再平衡动作。"]:
        lines.append(f"- {item}")
    return lines


def render_bucket_holdings(exposure: dict) -> list[str]:
    members = exposure.get("strategy_bucket_members", {}) or {}
    lines = ["## 按资金层持仓"]
    for bucket in ("core_long_term", "satellite_mid_term", "tactical_short_term", "cash_defense"):
        label = STRATEGY_BUCKET_LABELS.get(bucket, bucket)
        items = members.get(bucket, [])[:6]
        if not items:
            lines.append(f"- {label}：暂无")
            continue
        joined = "；".join(f"{item.get('fund_name', item.get('fund_code', '未知'))} {item.get('weight_pct', 0)}%" for item in items)
        lines.append(f"- {label}：{joined}")
    return lines


def build_markdown(portfolio: dict, advice: dict, strategy: dict, report_date: str) -> str:
    exposure = analyze_portfolio_exposure(portfolio, strategy)
    advice_mode = advice.get("advice_mode") or advice.get("source_mode") or "validated"
    allocation_plan = exposure.get("allocation_plan", {})
    lines = [
        f"# 组合调仓建议 - {report_date}",
        "",
        f"- 组合名称：{portfolio['portfolio_name']}",
        f"- 生成时间：{advice['generated_at']}",
        f"- 组合估值日期：{portfolio.get('as_of_date', '未知')}",
        f"- 组合重估生成时间：{portfolio.get('last_valuation_generated_at', '未知')}",
        f"- 风险偏好：{advice['risk_profile']}",
        f"- 总交易额度：{money_line(float(advice.get('daily_max_gross_trade_amount', advice['daily_max_trade_amount'])))}",
        f"- 净买入额度：{money_line(float(advice.get('daily_max_net_buy_amount', advice['daily_max_trade_amount'])))}",
        f"- 今日固定定投合计：{money_line(float(advice['fixed_dca_total']))}",
        f"- 资金存储仓可调拨参考：{money_line(float(advice['cash_hub_available']))}",
        f"- 建议模式：{advice_mode}",
        "",
        "## 可信度横幅",
        f"- 建议是否 fallback：{'是' if advice.get('advice_is_fallback') else '否'}",
        f"- 建议是否 mock：{'是' if advice.get('advice_is_mock') else '否'}",
        f"- 失败智能体数：{len(advice.get('failed_agents', []) or [])}",
        "",
        "## 市场判断",
        f"- 市场状态：{advice.get('market_view', {}).get('regime', 'unknown')}",
        f"- 综合结论：{advice.get('market_view', {}).get('summary', '无')}",
    ]
    if portfolio.get("as_of_date") and portfolio.get("as_of_date") != report_date:
        lines.append("- 说明：当前组合市值仍基于最近官方净值口径，日内分析主要参考盘中估值与代理行情。")
    for driver in advice.get("market_view", {}).get("key_drivers", []):
        lines.append(f"- 关键驱动：{driver}")

    lines.extend(
        [
            "",
            "## 组合暴露",
            f"- 最大风格暴露：{exposure['largest_style_group']['name']} {exposure['largest_style_group']['weight_pct']}%",
            f"- 最大主题家族暴露：{exposure['largest_theme_family']['name']} {exposure['largest_theme_family']['weight_pct']}%",
            f"- 最大单基金暴露：{exposure['largest_fund']['name']} {exposure['largest_fund']['weight_pct']}%",
            f"- 前三风格集中度：{exposure['concentration_metrics']['top3_style_weight_pct']}%",
            f"- 前三主题家族集中度：{exposure['concentration_metrics']['top3_family_weight_pct']}%",
            f"- 前三基金集中度：{exposure['concentration_metrics']['top3_fund_weight_pct']}%",
            f"- 海外权益占比：{exposure['concentration_metrics']['overseas_weight_pct']}%",
            f"- QDII 占比：{exposure['concentration_metrics']['qdii_weight_pct']}%",
            f"- 主动权益占比：{exposure['concentration_metrics']['active_equity_weight_pct']}%",
            f"- 指数/ETF 联接占比：{exposure['concentration_metrics']['index_like_weight_pct']}%",
            f"- 高波动主题占比：{exposure['concentration_metrics']['high_volatility_theme_weight_pct']}%",
            f"- 防守缓冲占比：{exposure['concentration_metrics']['defensive_buffer_weight_pct']}%",
            f"- 目标带宽：{allocation_plan.get('rebalance_band_pct', 5.0)}%",
        ]
    )
    for alert in exposure.get("alerts", []):
        lines.append(f"- 暴露提醒：{alert}")

    lines.append("")
    lines.extend(render_bucket_summary(exposure))
    lines.append("")
    lines.extend(render_bucket_actions(exposure))
    lines.append("")
    lines.extend(render_bucket_holdings(exposure))

    lines.append("")
    lines.append("## 固定定投")
    for item in advice.get("dca_actions", []):
        lines.append(
            f"- {item['fund_name']}：固定定投 {money_line(float(item['validated_amount']))}。"
            f"{item['thesis']}（{STRATEGY_BUCKET_LABELS.get(item.get('strategy_bucket', ''), item.get('strategy_bucket', '未分类'))}）"
        )

    lines.append("")
    lines.append("## 今日优先执行")
    if not advice.get("tactical_actions"):
        lines.append("- 今日没有通过约束校验的战术动作。")
    for item in advice.get("tactical_actions", []):
        lines.extend(render_action_item(item))
        lines.append(f"- 建议编号：{item.get('suggestion_id', '暂无')}")
        lines.append(f"- 执行状态：{item.get('execution_status', 'pending')}，已执行金额 {money_line(float(item.get('executed_amount', 0.0)))}")
        lines.append("")

    lines.append("## 暂不动作")
    for item in advice.get("hold_actions", []):
        bucket_text = STRATEGY_BUCKET_LABELS.get(item.get("strategy_bucket", ""), item.get("strategy_bucket", "未分类"))
        if item.get("agent_support"):
            lines.append(f"- {item['fund_name']}：{item.get('thesis') or '暂不动作'}（{bucket_text}；参考智能体：{', '.join(item['agent_support'])}）")
        else:
            lines.append(f"- {item['fund_name']}：{item.get('thesis') or '暂不动作'}（{bucket_text}）")

    if advice.get("cross_fund_observations"):
        lines.append("")
        lines.append("## 组合观察")
        for item in advice["cross_fund_observations"]:
            lines.append(f"- {item}")

    lines.append("")
    lines.append("## 说明")
    lines.append("- 本报告先由多智能体进行研究，再由规则层完成金额与角色约束校验。")
    lines.append("- 若盘中代理并非当日完整交易数据，模型会基于最近交易日与实时估值给出谨慎判断。")
    lines.append("- 组合层新增了长期核心 / 中期卫星 / 短期战术 / 防守现金四层结构，用于帮助控制交易频率和主题拥挤。")
    lines.append("- 本报告仅供研究与执行辅助，不构成个性化投资建议。")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the validated LLM portfolio report.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    portfolio = deepcopy(load_portfolio(agent_home))
    strategy = load_strategy(agent_home)
    profile_payload = load_json(fund_profile_path(agent_home, report_date)) if fund_profile_path(agent_home, report_date).exists() else {"items": []}
    profiles = {item["fund_code"]: item for item in profile_payload.get("items", [])}
    for fund in portfolio.get("funds", []):
        if fund.get("fund_code") in profiles:
            fund["fund_profile"] = profiles[fund["fund_code"]]
            fund["management_company"] = profiles[fund["fund_code"]].get("management_company")
            fund["category"] = fund.get("category") or profiles[fund["fund_code"]].get("category")
    advice = load_json(validated_advice_path(agent_home, report_date))

    output_path = portfolio_report_path(agent_home, report_date)
    output_path.write_text(build_markdown(portfolio, advice, strategy, report_date), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
