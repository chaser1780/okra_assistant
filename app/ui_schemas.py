from __future__ import annotations

from pathlib import Path

from decision_support import build_agent_stage_snapshot
from ui_support import (
    build_agent_detail_text,
    build_dashboard_text,
    build_fund_detail_text,
    build_realtime_detail_text,
    build_review_detail_fallback,
    build_review_summary_text,
    build_settings_text,
    build_trade_output_text,
    build_trade_preview_text,
    money,
    num,
    pct,
)


def _action_tone(action: str) -> str:
    return {
        "buy": "accent",
        "add": "accent",
        "scheduled_dca": "accent",
        "sell": "danger",
        "reduce": "danger",
        "switch_in": "success",
        "switch_out": "warning",
        "hold": "neutral",
    }.get(action, "info")


def _status_tone(status: str) -> str:
    return {
        "executed": "success",
        "done": "success",
        "ok": "success",
        "pending": "warning",
        "running": "info",
        "partial": "warning",
        "warning": "warning",
        "failed": "danger",
        "error": "danger",
        "stale": "warning",
        "unknown": "muted",
    }.get((status or "").lower(), "neutral")


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


def build_dashboard_detail_schema(summary: dict, validated: dict, portfolio: dict, exposure: dict | None, alerts: list[str], change_lines: list[str], plain_lines: list[str], portfolio_report: str) -> dict:
    tactical = validated.get("tactical_actions", []) or []
    dca = validated.get("dca_actions", []) or []
    holds = validated.get("hold_actions", []) or []
    actionable = tactical + dca
    top_action = actionable[0] if actionable else {}
    market = validated.get("market_view", {}) or {}
    summary_pairs = [
        ("当前查看日期", summary.get("selected_date", "暂无")),
        ("组合", summary.get("portfolio_name", "暂无") or "暂无"),
        ("市场状态", market.get("regime", "暂无")),
        ("建议模式", summary.get("advice_mode", "unknown")),
        ("最终通道", summary.get("transport_name", "暂无") or "暂无"),
        ("运行前自检", summary.get("preflight_status", "暂无") or "暂无"),
        ("主动建议数", str(len(actionable))),
        ("观察建议数", str(len(holds))),
        ("组合估值日期", portfolio.get("as_of_date", "暂无")),
        ("组合重估时间", portfolio.get("last_valuation_generated_at", "暂无")),
    ]
    lead = plain_lines[0] if plain_lines else top_action.get("thesis", "今天先看风险和执行状态，再决定要不要动。")
    badges = [
        {"text": f"fallback {_yes_no(summary.get('advice_is_fallback', False))}", "tone": "warning" if summary.get("advice_is_fallback") else "success"},
        {"text": f"失败智能体 {len(summary.get('failed_agent_names', []))}", "tone": "danger" if summary.get("failed_agent_names") else "success"},
        {"text": f"建议 {len(actionable)} 条", "tone": "info"},
        {"text": f"观察 {len(holds)} 条", "tone": "neutral"},
    ]
    sections = [
        {"title": "今天最重要的三件事", "kind": "bullets", "tone": "accent", "items": plain_lines or ["今天没有额外高优先动作。"]},
        {"title": "今日执行清单", "kind": "bullets", "tone": "surface", "items": [f"{item.get('fund_name')}：{item.get('validated_action')} {money(item.get('validated_amount', 0))}" for item in actionable] or ["今天没有需要立刻执行的动作。"]},
        {"title": "今日观察清单", "kind": "bullets", "tone": "success", "items": [f"{item.get('fund_name')}：{item.get('thesis', '继续观察')}" for item in holds if item.get("agent_support")] or ["今天没有特别需要跟踪的观察项。"]},
        {"title": "当前提醒", "kind": "bullets", "tone": "warning" if alerts else "soft", "items": alerts or ["当前没有额外高优先风险提醒。"]},
        {"title": "与上一期相比", "kind": "bullets", "tone": "soft", "items": change_lines or ["相比上一期，动作结构没有明显变化。"]},
    ]
    if portfolio_report:
        sections.append({"title": "组合报告节选", "kind": "text", "tone": "panel", "text": portfolio_report})
    return {
        "title": "今日决策面板",
        "subtitle": "先回答今天该不该动，再看理由、风险和时间语义。",
        "lead": lead,
        "badges": badges,
        "summary_pairs": summary_pairs,
        "sections": sections,
        "raw_text": build_dashboard_text(summary, validated, portfolio, portfolio_report, exposure, change_lines, alerts, plain_lines),
    }


def build_portfolio_cockpit_schema(state: dict, exposure: dict | None, alerts: list[str]) -> dict:
    portfolio = state.get("portfolio", {})
    realtime = state.get("realtime", {}) or {}
    validated = state.get("validated", {}) or {}
    totals = realtime.get("totals", {}) or {}
    funds = portfolio.get("funds", []) or []
    cash = next((item for item in funds if item.get("role") == "cash_hub"), {})
    executed_amount = 0.0
    pending_count = 0
    for section in ("tactical_actions", "dca_actions", "hold_actions"):
        for item in validated.get(section, []) or []:
            executed_amount += float(item.get("executed_amount", 0.0) or 0.0)
            if item.get("execution_status", "pending") in {"pending", "partial"} and item.get("validated_action") != "hold":
                pending_count += 1
    summary_pairs = [
        ("总资产", money(portfolio.get("total_value", 0))),
        ("现金仓", money(cash.get("current_value", 0))),
        ("今日实时盈亏", money(totals.get("estimated_intraday_pnl_amount", 0))),
        ("已执行金额", money(executed_amount)),
        ("待执行建议", str(pending_count)),
        ("组合估值日", portfolio.get("as_of_date", "暂无")),
        ("最大单基金", f"{(exposure or {}).get('largest_fund', {}).get('name', '暂无')} {(exposure or {}).get('largest_fund', {}).get('weight_pct', '—')}%"),
        ("最大主题家族", f"{(exposure or {}).get('largest_theme_family', {}).get('name', '暂无')} {(exposure or {}).get('largest_theme_family', {}).get('weight_pct', '—')}%"),
    ]
    concentration = (exposure or {}).get("concentration_metrics", {}) or {}
    bar_items = [
        {"label": "前三基金集中度", "value": concentration.get("top3_fund_weight_pct", 0), "value_text": pct(concentration.get("top3_fund_weight_pct", 0), 2), "tone": "warning"},
        {"label": "前三主题集中度", "value": concentration.get("top3_family_weight_pct", 0), "value_text": pct(concentration.get("top3_family_weight_pct", 0), 2), "tone": "danger"},
        {"label": "高波动主题", "value": concentration.get("high_volatility_theme_weight_pct", 0), "value_text": pct(concentration.get("high_volatility_theme_weight_pct", 0), 2), "tone": "danger"},
        {"label": "海外权益占比", "value": concentration.get("overseas_weight_pct", 0), "value_text": pct(concentration.get("overseas_weight_pct", 0), 2), "tone": "info"},
        {"label": "防守缓冲占比", "value": concentration.get("defensive_buffer_weight_pct", 0), "value_text": pct(concentration.get("defensive_buffer_weight_pct", 0), 2), "tone": "success"},
    ]
    checklist = []
    checklist.append({"label": f"最近预检状态：{state.get('preflight', {}).get('status', '暂无')}", "status": "success" if state.get("preflight", {}).get("status") == "ok" else "warning", "tone": _status_tone(state.get("preflight", {}).get("status", "warning"))})
    checklist.extend({"label": line, "status": "warning", "tone": "warning"} for line in (alerts or ["当前没有额外风险提醒。"]))
    return {
        "title": "Portfolio / Risk Cockpit",
        "subtitle": "把仓位、风险、执行和时效放在同一页里联查。",
        "summary_pairs": summary_pairs,
        "sections": [
            {"title": "关键暴露", "kind": "bars", "tone": "surface", "items": bar_items},
            {"title": "风险与健康", "kind": "checklist", "tone": "surface", "items": checklist},
            {"title": "角色分布", "kind": "bars", "tone": "soft", "items": [{"label": item.get("name", "暂无"), "value": item.get("weight_pct", 0), "value_text": pct(item.get("weight_pct", 0), 2), "tone": "info"} for item in (exposure or {}).get("by_role", [])[:5]] or [{"label": "暂无", "value": 0, "value_text": "—", "tone": "muted"}]},
        ],
    }


def build_fund_detail_schema(item: dict, realtime_item: dict | None, review_item: dict | None) -> dict:
    action = item.get("validated_action", "hold")
    execution_status = item.get("execution_status", "pending")
    summary_pairs = [
        ("建议编号", item.get("suggestion_id", "暂无")),
        ("基金代码", item.get("fund_code", "暂无")),
        ("基金名称", item.get("fund_name", "暂无")),
        ("所属分组", item.get("_section", "暂无")),
        ("模型原动作", item.get("model_action", "暂无")),
        ("校验后动作", action),
        ("建议金额", money(item.get("validated_amount", 0))),
        ("执行状态", execution_status),
        ("已执行金额", money(item.get("executed_amount", 0))),
        ("置信度", num(item.get("confidence"), 2)),
        ("最近交易日期", item.get("linked_trade_date", "暂无") or "暂无"),
        ("绑定交易", _yes_no(bool(item.get("linked_trade_date")))),
    ]
    sections = [
        {"title": "核心判断", "kind": "text", "tone": "accent", "text": item.get("thesis", "暂无")},
        {"title": "依据", "kind": "bullets", "tone": "surface", "items": item.get("evidence", []) or ["暂无"]},
        {"title": "风险", "kind": "bullets", "tone": "warning", "items": item.get("risks", []) or ["暂无"]},
        {"title": "规则校验", "kind": "bullets", "tone": "soft", "items": item.get("validation_notes", []) or ["暂无"]},
        {"title": "参考智能体", "kind": "bullets", "tone": "panel", "items": item.get("agent_support", []) or ["暂无"]},
    ]
    if realtime_item:
        sections.append(
            {
                "title": "实时参考",
                "kind": "kv",
                "tone": "info",
                "pairs": [
                    ("估算模式", realtime_item.get("mode", "暂无")),
                    ("模式说明", realtime_item.get("reason", "暂无")),
                    ("今日估算收益", money(realtime_item.get("estimated_intraday_pnl_amount", 0))),
                    ("今日估算涨跌", pct(realtime_item.get("effective_change_pct", 0), 2)),
                    ("估值跨日", _yes_no(bool(realtime_item.get("stale")))),
                    ("可信度", num(realtime_item.get("confidence"), 2)),
                ],
            }
        )
    if review_item:
        sections.append(
            {
                "title": "复盘结果",
                "kind": "kv",
                "tone": "success" if review_item.get("outcome") == "supportive" else "warning",
                "pairs": [
                    ("outcome", review_item.get("outcome", "暂无")),
                    ("真实单日涨跌", pct(review_item.get("review_day_change_pct", 0), 2)),
                    ("一周涨跌", pct(review_item.get("review_week_change_pct", 0), 2)),
                    ("与基准相对", pct(review_item.get("excess_return_vs_benchmark_pct", 0), 2)),
                ],
            }
        )
    return {
        "title": item.get("fund_name", "基金详情"),
        "subtitle": f"{item.get('fund_code', '暂无')} | {item.get('_section', 'unknown')}",
        "lead": item.get("thesis", "暂无"),
        "badges": [
            {"text": f"动作 {action}", "tone": _action_tone(action)},
            {"text": f"执行 {execution_status}", "tone": _status_tone(execution_status)},
            {"text": f"置信度 {num(item.get('confidence'), 2)}", "tone": "info"},
            {"text": f"已绑定交易 {_yes_no(bool(item.get('linked_trade_date')))}", "tone": "success" if item.get("linked_trade_date") else "warning"},
        ],
        "summary_pairs": summary_pairs,
        "sections": sections,
        "raw_text": build_fund_detail_text(item, realtime_item, review_item),
    }


def build_agent_detail_schema(name: str, agent: dict, aggregate: dict | None = None, view_mode: str = "analyst") -> dict:
    out = agent.get("output", {}) or {}
    stage_snapshot = build_agent_stage_snapshot(name, aggregate)
    summary_pairs = [
        ("研究阶段", stage_snapshot.get("label", "暂无")),
        ("状态", agent.get("status", "unknown")),
        ("置信度", num(out.get("confidence"), 2)),
        ("证据强度", out.get("evidence_strength", "暂无")),
        ("数据新鲜度", out.get("data_freshness", "暂无")),
        ("上游输入", str(len(stage_snapshot.get("depends_on", [])))),
        ("下游去向", str(len(stage_snapshot.get("consumers", [])))),
        ("委员会核心", "是" if stage_snapshot.get("is_committee_core") else "否"),
    ]
    sections = [
        {
            "title": "研究位置",
            "kind": "kv",
            "tone": stage_snapshot.get("tone", "info"),
            "pairs": [
                ("阶段", stage_snapshot.get("label", "暂无")),
                ("职责", stage_snapshot.get("description", "暂无")),
                ("上游输入", "、".join(stage_snapshot.get("depends_on", [])) or "无"),
                ("下游去向", "、".join(stage_snapshot.get("consumers", [])) or "无"),
            ],
            "columns": 1,
        },
        {"title": "摘要", "kind": "text", "tone": "accent", "text": out.get("summary", "暂无")},
        {"title": "关键点", "kind": "bullets", "tone": "surface", "items": out.get("key_points", []) or ["暂无"]},
        {"title": "缺失信息", "kind": "bullets", "tone": "warning", "items": out.get("missing_info", []) or ["暂无"]},
        {"title": "观察项", "kind": "bullets", "tone": "soft", "items": out.get("watchouts", []) or ["暂无"]},
    ]
    if out.get("portfolio_view"):
        pv = out["portfolio_view"]
        sections.append({"title": "组合视角", "kind": "kv", "tone": "info", "pairs": [("regime", pv.get("regime", "暂无")), ("risk_bias", pv.get("risk_bias", "暂无"))]})
    if out.get("fund_views"):
        sections.append({"title": "基金视角", "kind": "bullets", "tone": "panel", "items": [f"{x.get('fund_code')} | {x.get('action_bias')} | {x.get('thesis')}" for x in out.get("fund_views", [])[:8]]})
    return {
        "title": name,
        "subtitle": "智能体详情与关键信号",
        "lead": out.get("summary", "暂无"),
        "badges": [
            {"text": stage_snapshot.get("label", "Unknown"), "tone": stage_snapshot.get("tone", "info")},
            {"text": f"状态 {agent.get('status', 'unknown')}", "tone": _status_tone(agent.get("status", "unknown"))},
            {"text": f"置信度 {num(out.get('confidence'), 2)}", "tone": "info"},
        ],
        "summary_pairs": summary_pairs,
        "sections": sections,
        "raw_text": build_agent_detail_text(name, agent),
        "show_raw_text": view_mode == "analyst",
    }


def build_realtime_detail_schema(item: dict) -> dict:
    summary_pairs = [
        ("基金代码", item.get("fund_code", "暂无")),
        ("角色", item.get("role", "暂无")),
        ("风格分组", item.get("style_group", "暂无")),
        ("估算模式", item.get("mode", "暂无")),
        ("可信度", num(item.get("confidence"), 2)),
        ("估值跨日", _yes_no(bool(item.get("stale")))),
        ("今日估算收益", money(item.get("estimated_intraday_pnl_amount", 0))),
        ("今日估算收益率", pct(item.get("estimated_intraday_pnl_pct", 0), 4)),
        ("估算持仓市值", money(item.get("estimated_position_value", 0))),
        ("估算总盈亏", money(item.get("estimated_total_pnl_amount", 0))),
    ]
    sections = [
        {"title": "时点与模式", "kind": "kv", "tone": "accent", "pairs": [("模式说明", item.get("reason", "暂无")), ("估值时间", item.get("estimate_time", "暂无")), ("代理时间", item.get("proxy_time", "暂无")), ("官方净值日期", item.get("official_nav_date", "暂无"))]},
        {"title": "份额与净值", "kind": "kv", "tone": "surface", "pairs": [("持有份额", num(item.get("holding_units"), 6)), ("份额来源", item.get("unit_source", "暂无")), ("份额置信度", num(item.get("unit_confidence"), 2)), ("官方净值", num(item.get("official_nav"), 6)), ("有效净值", num(item.get("effective_nav"), 6)), ("官方净值时效", item.get("official_nav_freshness_label", "暂无"))]},
        {"title": "涨跌与收益", "kind": "kv", "tone": "info", "pairs": [("估值涨跌", pct(item.get("estimate_change_pct"), 2)), ("估值时效", item.get("estimate_freshness_label", "暂无")), ("代理涨跌", pct(item.get("proxy_change_pct"), 2)), ("代理时效", item.get("proxy_freshness_label", "暂无")), ("采用涨跌", pct(item.get("effective_change_pct"), 2)), ("估值策略允许", _yes_no(bool(item.get("estimate_policy_allowed")))), ("代理策略允许", _yes_no(bool(item.get("proxy_policy_allowed"))))]},
    ]
    return {
        "title": item.get("fund_name", "实时详情"),
        "subtitle": f"{item.get('fund_code', '暂无')} | {item.get('mode', 'unknown')}",
        "lead": item.get("reason", "暂无"),
        "badges": [
            {"text": f"模式 {item.get('mode', '暂无')}", "tone": "info"},
            {"text": f"可信度 {num(item.get('confidence'), 2)}", "tone": "info"},
            {"text": "数据陈旧" if item.get("stale") else "同日内", "tone": "warning" if item.get("stale") else "success"},
        ],
        "summary_pairs": summary_pairs,
        "sections": sections,
        "raw_text": build_realtime_detail_text(item),
    }


def build_review_summary_schema(selected_date: str, review_batches: list[dict], memory: dict, operating_metrics: dict, review_report: str) -> dict:
    summary = {
        "supportive": sum(item.get("summary", {}).get("supportive", 0) for item in review_batches),
        "adverse": sum(item.get("summary", {}).get("adverse", 0) for item in review_batches),
        "missed_upside": sum(item.get("summary", {}).get("missed_upside", 0) for item in review_batches),
        "unknown": sum(item.get("summary", {}).get("unknown", 0) for item in review_batches),
    }
    history = memory.get("review_history", []) or []
    advice_history = [item for item in history if item.get("source", "advice") == "advice"]
    recent_30 = advice_history[-30:]
    recent_90 = advice_history[-90:]
    def _agg(items, key):
        return sum(item.get("summary", {}).get(key, 0) for item in items)
    summary_pairs = [
        ("复盘日期", selected_date),
        ("批次数", str(len(review_batches))),
        ("supportive", str(summary.get("supportive", 0))),
        ("adverse", str(summary.get("adverse", 0))),
        ("missed_upside", str(summary.get("missed_upside", 0))),
        ("unknown", str(summary.get("unknown", 0))),
        ("最近样本天数", str(operating_metrics.get("sample_days", 0))),
        ("fallback 天数", str(operating_metrics.get("fallback_days", 0))),
        ("stale 天数", str(operating_metrics.get("stale_days", 0))),
    ]
    sections = [
        {"title": "当日结果分布", "kind": "bars", "tone": "surface", "items": [{"label": key, "value": value, "value_text": str(value), "tone": "success" if key == "supportive" else ("danger" if key == "adverse" else "warning")} for key, value in summary.items()]},
        {"title": "近 30 / 90 条建议层表现", "kind": "bars", "tone": "panel", "items": [{"label": "30 supportive", "value": _agg(recent_30, 'supportive'), "value_text": str(_agg(recent_30, 'supportive')), "tone": "success"}, {"label": "30 adverse", "value": _agg(recent_30, 'adverse'), "value_text": str(_agg(recent_30, 'adverse')), "tone": "danger"}, {"label": "90 supportive", "value": _agg(recent_90, 'supportive'), "value_text": str(_agg(recent_90, 'supportive')), "tone": "success"}, {"label": "90 adverse", "value": _agg(recent_90, 'adverse'), "value_text": str(_agg(recent_90, 'adverse')), "tone": "danger"}]},
        {"title": "当日批次", "kind": "bullets", "tone": "soft", "items": [f"{('建议层' if item.get('source', 'advice') == 'advice' else '执行层')} {'T0' if int(item.get('horizon', 0)) == 0 else 'T+' + str(int(item.get('horizon', 0)))} | base={item.get('base_date')}" for item in review_batches] or ["暂无"]},
        {"title": "最新 lessons", "kind": "bullets", "tone": "accent", "items": [x.get("text", "暂无") for x in (memory.get("lessons", [])[-5:] or [{"text": "暂无"}])]},
        {"title": "最新 bias adjustments", "kind": "bullets", "tone": "warning", "items": [f"[{x.get('scope')}] {x.get('target')}：{x.get('adjustment')}" for x in (memory.get("bias_adjustments", [])[-5:] or [{"scope": "", "target": "", "adjustment": "暂无"}])]},
        {"title": "最新 agent feedback", "kind": "bullets", "tone": "panel", "items": [f"{x.get('agent_name')}：{x.get('bias')}" for x in (memory.get("agent_feedback", [])[-5:] or [{"agent_name": "", "bias": "暂无"}])]},
    ]
    raw = review_report or build_review_detail_fallback(selected_date, review_batches)
    return {
        "title": "复盘与记忆",
        "subtitle": "不只看报告，还要看批次、历史趋势与最新 learnings。",
        "lead": "先看 supportive / adverse 的结构，再看 lessons 和 bias adjustments。",
        "summary_pairs": summary_pairs,
        "sections": sections,
        "raw_text": raw if raw else build_review_summary_text(selected_date, review_batches, memory, operating_metrics),
    }


def build_trade_precheck_schema(selected: dict | None, cash: dict | None, constraint: dict | None, action: str, amount: float, nav_text: str, units_text: str) -> dict:
    if not selected:
        return {"title": "交易前检查", "subtitle": "请选择基金后再查看检查结果。"}
    constraint = constraint or {}
    current_value = float(selected.get("current_value", 0) or 0)
    cash_value = float(cash.get("current_value", 0) or 0) if cash else 0.0
    cap_value = float(selected.get("cap_value", 0) or 0)
    available_to_sell = float(constraint.get("available_to_sell", current_value) or 0)
    locked_amount = float(constraint.get("locked_amount", 0) or 0)
    post_fund_value = current_value
    post_cash_value = cash_value
    checks = []
    if action in {"buy", "switch_in"}:
        post_fund_value += amount
        post_cash_value -= amount
        checks.append({"label": "现金仓是否足够", "detail": f"当前现金仓 {money(cash_value)}，本次需要 {money(amount)}。", "status": "success" if cash_value >= amount else "danger", "status_text": "OK" if cash_value >= amount else "RISK", "tone": "success" if cash_value >= amount else "danger"})
    elif action in {"sell", "switch_out"}:
        post_fund_value -= amount
        post_cash_value += amount
        checks.append({"label": "当前可卖金额是否足够", "detail": f"当前可卖 {money(available_to_sell)}，本次计划卖出 {money(amount)}。", "status": "success" if available_to_sell >= amount else "danger", "status_text": "OK" if available_to_sell >= amount else "RISK", "tone": "success" if available_to_sell >= amount else "danger"})
    if cap_value > 0:
        checks.append({"label": "是否触碰单只上限", "detail": f"上限 {money(cap_value)}，交易后估算 {money(post_fund_value)}。", "status": "success" if post_fund_value <= cap_value else "warning", "status_text": "SAFE" if post_fund_value <= cap_value else "CAP", "tone": "success" if post_fund_value <= cap_value else "warning"})
    checks.append({"label": "锁定金额提示", "detail": f"当前锁定金额 {money(locked_amount)}。", "status": "warning" if locked_amount > 0 else "success", "status_text": "LOCK" if locked_amount > 0 else "OPEN", "tone": "warning" if locked_amount > 0 else "success"})
    checks.append({"label": "最短持有与到账节奏", "detail": f"最短持有 {constraint.get('min_hold_days', 0)} 天，赎回到账 T+{constraint.get('redeem_settlement_days', 0)}。", "status": "info", "status_text": "INFO", "tone": "info"})
    checks.append({"label": "转换能力", "detail": "支持直接转换。" if constraint.get("conversion_supported") else "不支持直接转换。", "status": "success" if constraint.get("conversion_supported") else "warning", "status_text": "YES" if constraint.get("conversion_supported") else "NO", "tone": "success" if constraint.get("conversion_supported") else "warning"})
    checks.append({"label": "成交明细补充", "detail": "已录入成交净值/份额，可提升持仓精度。" if (nav_text or units_text) else "建议补充成交净值或成交份额，以提升持仓精度。", "status": "success" if (nav_text or units_text) else "warning", "status_text": "DONE" if (nav_text or units_text) else "TODO", "tone": "success" if (nav_text or units_text) else "warning"})
    summary_pairs = [
        ("基金", selected.get("fund_name", "暂无")),
        ("基金代码", selected.get("fund_code", "暂无")),
        ("交易动作", action or "暂无"),
        ("交易金额", money(amount)),
        ("当前市值", money(current_value)),
        ("交易后市值", money(post_fund_value)),
        ("现金仓当前市值", money(cash_value)),
        ("现金仓交易后市值", money(post_cash_value)),
        ("可卖金额", money(available_to_sell)),
        ("赎回费率", pct(constraint.get("estimated_redeem_fee_rate", 0), 2)),
    ]
    lead = f"你即将{('买入' if action in {'buy', 'switch_in'} else '卖出')} {selected.get('fund_name', '该基金')} {money(amount)}。先确认现金、上限、持有约束和到账节奏。"
    raw_text = build_trade_preview_text(selected, cash, constraint)
    return {
        "title": "交易前检查台",
        "subtitle": "先确认风险，再提交交易记录。",
        "lead": lead,
        "badges": [
            {"text": f"动作 {action}", "tone": _action_tone(action)},
            {"text": f"金额 {money(amount)}", "tone": "info"},
            {"text": f"费率 {pct(constraint.get('estimated_redeem_fee_rate', 0), 2)}", "tone": "warning"},
        ],
        "summary_pairs": summary_pairs,
        "sections": [
            {"title": "交易前检查", "kind": "checklist", "tone": "surface", "items": checks},
            {"title": "约束提示", "kind": "bullets", "tone": "soft", "items": constraint.get("notes", []) or ["暂无额外约束提示。"]},
        ],
        "raw_text": raw_text,
    }


def build_trade_history_schema(trade_date: str, items: list[dict]) -> dict:
    summary_pairs = [
        ("交易日期", trade_date),
        ("记录数", str(len(items))),
        ("总买入", money(sum(float(item.get("amount", 0) or 0) for item in items if item.get("action") in {"buy", "switch_in"}))),
        ("总卖出", money(sum(float(item.get("amount", 0) or 0) for item in items if item.get("action") in {"sell", "switch_out"}))),
    ]
    sections = [
        {"title": "当日交易记录", "kind": "bullets", "tone": "surface", "items": [f"{item.get('fund_name')} | {item.get('action')} | {money(item.get('amount', 0))} | 建议={item.get('suggestion_id', '—')}" for item in items] or ["当日暂无交易记录。"]}
    ]
    return {
        "title": "交易结果与流水",
        "subtitle": "录入完成后在这里核对写回结果。",
        "summary_pairs": summary_pairs,
        "sections": sections,
        "raw_text": build_trade_output_text(trade_date, items),
    }


def build_system_schema(home: Path, selected_date: str, portfolio: dict, project: dict, strategy: dict, watchlist: dict, llm_config: dict, llm_raw: dict, realtime: dict, preflight: dict, manifests: dict[str, dict]) -> dict:
    summary_pairs = [
        ("查看日期", selected_date),
        ("agent_home", str(home)),
        ("组合估值日", portfolio.get("as_of_date", "暂无")),
        ("最近重估时间", portfolio.get("last_valuation_generated_at", "暂无")),
        ("风险偏好", strategy.get("portfolio", {}).get("risk_profile", "暂无")),
        ("日内报告模式", strategy.get("schedule", {}).get("report_mode", "暂无")),
        ("watchlist 数量", str(len(watchlist.get("funds", []) or []))),
        ("模型 provider", llm_config.get("model_provider", "暂无")),
        ("模型", llm_config.get("model", "暂无")),
        ("建议模式", llm_raw.get("mode", "暂无")),
        ("transport", llm_raw.get("transport_name", "暂无")),
        ("preflight", preflight.get("status", "暂无")),
    ]
    manifest_items = []
    for label, payload in manifests.items():
        if not payload:
            manifest_items.append({"label": f"{label}: 暂无 manifest", "status": "warning", "status_text": "MISS", "tone": "warning"})
            continue
        errors = payload.get("errors") or []
        status = payload.get("status", "unknown")
        detail = f"step={payload.get('current_step', '—')} | total_seconds={payload.get('total_seconds', '—')}"
        if errors:
            detail += f" | error={errors[-1].get('error', '')}"
        manifest_items.append({"label": f"{label}: {status}", "detail": detail, "status": "success" if status == "done" else ("warning" if status == "running" else "danger" if status == "failed" else "info"), "status_text": status.upper()[:5] or "INFO", "tone": _status_tone(status)})
    latest_checks = preflight.get("checks", [])[-8:]
    sections = [
        {"title": "最近 manifest", "kind": "checklist", "tone": "surface", "items": manifest_items},
        {"title": "最近 preflight 检查", "kind": "bullets", "tone": "soft", "items": [f"{item.get('name')} | {item.get('status')} | {item.get('detail')}" for item in latest_checks] or ["暂无"]},
        {"title": "常用路径", "kind": "bullets", "tone": "panel", "items": [str(home / "config"), str(home / "db"), str(home / "reports" / "daily"), str(home / "logs")]},
    ]
    return {
        "title": "系统健康与数据路径",
        "subtitle": "先看健康检查和运行产物，再看底层路径。",
        "summary_pairs": summary_pairs,
        "sections": sections,
        "raw_text": build_settings_text(home, selected_date, portfolio, project, strategy, watchlist, llm_config, llm_raw, realtime, preflight, manifests),
    }
