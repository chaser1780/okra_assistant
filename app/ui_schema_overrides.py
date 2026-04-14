from __future__ import annotations

from decision_support import stage_label, stage_tone, summarize_fund_agent_signals, summarize_fund_stage_signals
from ui_support import (
    build_dashboard_text,
    build_fund_detail_text,
    build_realtime_detail_text,
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


def _bucket_label(bucket: str) -> str:
    return {
        "core_long_term": "长期核心仓",
        "satellite_mid_term": "中期卫星仓",
        "tactical_short_term": "短期战术仓",
        "cash_defense": "防守/现金仓",
    }.get(bucket, bucket or "未分类")


def build_dashboard_detail_schema(
    summary: dict,
    validated: dict,
    portfolio: dict,
    realtime: dict | None,
    exposure: dict | None,
    alerts: list[str],
    change_lines: list[str],
    plain_lines: list[str],
    portfolio_report: str,
    view_mode: str = "analyst",
) -> dict:
    tactical = validated.get("tactical_actions", []) or []
    dca = validated.get("dca_actions", []) or []
    holds = validated.get("hold_actions", []) or []
    actionable = tactical + dca
    top_action = actionable[0] if actionable else {}
    market = validated.get("market_view", {}) or {}
    allocation_plan = (exposure or {}).get("allocation_plan", {}) or {}
    concentration = (exposure or {}).get("concentration_metrics", {}) or {}
    realtime_totals = (realtime or {}).get("totals", {}) or {}

    summary_pairs = [
        ("查看日期", summary.get("selected_date", "暂无")),
        ("组合", summary.get("portfolio_name", "暂无") or "暂无"),
        ("市场状态", market.get("regime", "暂无")),
        ("建议模式", summary.get("advice_mode", "unknown")),
        ("最终通道", summary.get("transport_name", "暂无") or "暂无"),
        ("预检状态", summary.get("preflight_status", "暂无") or "暂无"),
        ("主动建议数", str(len(actionable))),
        ("观察建议数", str(len(holds))),
        ("官方净值日期", portfolio.get("as_of_date", "暂无")),
        ("组合重估时间", portfolio.get("last_valuation_generated_at", "暂无")),
        ("实时收益", money(realtime_totals.get("estimated_intraday_pnl_amount", 0)) if realtime else "暂无"),
        ("实时快照", (realtime or {}).get("market_timestamp", "暂无") if realtime else "暂无"),
    ]

    badges = [
        {"text": f"fallback {_yes_no(summary.get('advice_is_fallback', False))}", "tone": "warning" if summary.get("advice_is_fallback") else "success"},
        {"text": f"失败智能体 {len(summary.get('failed_agent_names', []))}", "tone": "danger" if summary.get("failed_agent_names") else "success"},
        {"text": f"建议 {len(actionable)} 条", "tone": "info"},
        {"text": f"观察 {len(holds)} 条", "tone": "neutral"},
    ]

    sections = [
        {
            "title": "今天最重要",
            "kind": "kv",
            "tone": "accent",
            "pairs": [
                ("主动作", f"{top_action.get('fund_name', '暂无')} {top_action.get('validated_action', 'hold')} {money(top_action.get('validated_amount', 0))}" if top_action else "今天暂无主动动作"),
                ("市场判断", market.get("regime", "暂无")),
                ("实时收益", money(realtime_totals.get("estimated_intraday_pnl_amount", 0)) if realtime else "暂无"),
                ("建议模式", summary.get("advice_mode", "unknown")),
                ("数据可信度", f"fallback {_yes_no(summary.get('advice_is_fallback', False))} | 失败智能体 {len(summary.get('failed_agent_names', []))}"),
            ],
        },
        {
            "title": "今天最重要的三件事",
            "kind": "bullets",
            "tone": "accent",
            "items": plain_lines or ["今天没有额外高优先级动作。"],
        },
        {
            "title": "当前风险与提醒",
            "kind": "bullets",
            "tone": "warning" if alerts else "soft",
            "items": alerts or ["当前没有额外高优先级风险提醒。"],
        },
        {
            "title": "相对上一期的变化",
            "kind": "bullets",
            "tone": "soft",
            "items": change_lines or ["相较上一期，没有明显动作变化。"],
        },
        {
            "title": "今天怎么做 / 先观察 / 今天别急",
            "kind": "checklist",
            "tone": "panel",
            "items": (
                [{"label": item, "detail": "优先执行", "status": "success", "status_text": "DO", "tone": "success"} for item in ([f"{entry.get('fund_name')}：{entry.get('validated_action')} {money(entry.get('validated_amount', 0))}" for entry in actionable[:3]] or ["今天没有需要立刻执行的动作。"])]
                + [{"label": item, "detail": "继续观察", "status": "info", "status_text": "WAIT", "tone": "info"} for item in ([f"{entry.get('fund_name')}：{entry.get('thesis', '继续观察')}" for entry in holds[:3]] or ["今天没有特别需要继续跟踪的观察项。"])]
                + [{"label": item, "detail": "避免误操作", "status": "warning", "status_text": "SLOW", "tone": "warning"} for item in ((alerts or ["当前没有额外高优先级风险提醒。"])[:3])]
            ),
        },
        {
            "title": "组合层风险与配置偏离",
            "kind": "bars",
            "tone": "surface",
            "items": [
                {"label": "前三主题集中度", "value": concentration.get("top3_family_weight_pct", 0), "value_text": pct(concentration.get("top3_family_weight_pct", 0), 2), "tone": "warning"},
                {"label": "高波动主题", "value": concentration.get("high_volatility_theme_weight_pct", 0), "value_text": pct(concentration.get("high_volatility_theme_weight_pct", 0), 2), "tone": "danger"},
                {"label": "防守缓冲", "value": concentration.get("defensive_buffer_weight_pct", 0), "value_text": pct(concentration.get("defensive_buffer_weight_pct", 0), 2), "tone": "success"},
                {"label": "长期核心仓", "value": allocation_plan.get("current_pct", {}).get("core_long_term", 0), "value_text": f"{pct(allocation_plan.get('current_pct', {}).get('core_long_term', 0), 2)} / 目标 {pct(allocation_plan.get('targets_pct', {}).get('core_long_term', 0), 2)}", "tone": "info"},
            ],
        },
        {
            "title": "时间语义",
            "kind": "kv",
            "tone": "panel",
            "pairs": [
                ("查看日期", summary.get("selected_date", "暂无")),
                ("组合净值日期", portfolio.get("as_of_date", "暂无")),
                ("组合重估时间", portfolio.get("last_valuation_generated_at", "暂无")),
                ("建议生成模式", summary.get("advice_mode", "unknown")),
            ],
        },
    ]

    if view_mode == "analyst":
        sections.extend(
            [
                {
                    "title": "今日待执行清单",
                    "kind": "bullets",
                    "tone": "surface",
                    "items": [f"{item.get('fund_name')}：{item.get('validated_action')} {money(item.get('validated_amount', 0))}" for item in actionable] or ["今天没有需要立刻执行的动作。"],
                },
                {
                    "title": "今日观察清单",
                    "kind": "bullets",
                    "tone": "success",
                    "items": [f"{item.get('fund_name')}：{item.get('thesis', '继续观察')}" for item in holds if item.get("agent_support")] or ["今天没有特别需要继续跟踪的观察项。"],
                },
            ]
        )
        if portfolio_report:
            sections.append({"title": "组合报告节选", "kind": "text", "tone": "panel", "text": portfolio_report})
    else:
        sections.extend(
            [
                {
                    "title": "今天怎么做",
                    "kind": "bullets",
                    "tone": "surface",
                    "items": [f"{item.get('fund_name')}：{item.get('validated_action')} {money(item.get('validated_amount', 0))}" for item in actionable[:5]] or ["今天以观察为主，不急于动作。"],
                },
                {
                    "title": "为什么和昨天不同",
                    "kind": "bullets",
                    "tone": "panel",
                    "items": change_lines[:5] or ["今天和上一期相比没有关键变化。"],
                },
            ]
        )

    return {
        "title": "今天先看什么" if view_mode == "investor" else "今日决策面板",
        "subtitle": "先回答今天要不要动，再看理由、风险和时间语义。",
        "lead": plain_lines[0] if plain_lines else top_action.get("thesis", "先看风险和执行状态，再决定是否动作。"),
        "badges": badges,
        "summary_pairs": summary_pairs,
        "sections": sections,
        "raw_text": build_dashboard_text(summary, validated, portfolio, portfolio_report, exposure, change_lines, alerts, plain_lines),
        "show_raw_text": view_mode == "analyst",
    }


def build_portfolio_cockpit_schema(state: dict, exposure: dict | None, alerts: list[str], view_mode: str = "analyst") -> dict:
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

    concentration = (exposure or {}).get("concentration_metrics", {}) or {}
    stale_count = sum(1 for item in realtime.get("items", []) if item.get("stale"))

    allocation_plan = (exposure or {}).get("allocation_plan", {}) or {}
    sections = [
        {
            "title": "关键暴露",
            "kind": "bars",
            "tone": "surface",
            "items": [
                {"label": "前三基金集中度", "value": concentration.get("top3_fund_weight_pct", 0), "value_text": pct(concentration.get("top3_fund_weight_pct", 0), 2), "tone": "warning"},
                {"label": "前三主题集中度", "value": concentration.get("top3_family_weight_pct", 0), "value_text": pct(concentration.get("top3_family_weight_pct", 0), 2), "tone": "danger"},
                {"label": "高波动主题", "value": concentration.get("high_volatility_theme_weight_pct", 0), "value_text": pct(concentration.get("high_volatility_theme_weight_pct", 0), 2), "tone": "danger"},
                {"label": "海外权益", "value": concentration.get("overseas_weight_pct", 0), "value_text": pct(concentration.get("overseas_weight_pct", 0), 2), "tone": "info"},
                {"label": "防守缓冲", "value": concentration.get("defensive_buffer_weight_pct", 0), "value_text": pct(concentration.get("defensive_buffer_weight_pct", 0), 2), "tone": "success"},
            ],
        },
        {
            "title": "风险与健康",
            "kind": "checklist",
            "tone": "surface",
            "items": [
                {
                    "label": f"最近预检状态：{state.get('preflight', {}).get('status', '暂无')}",
                    "status": "success" if state.get("preflight", {}).get("status") == "ok" else "warning",
                    "tone": _status_tone(state.get("preflight", {}).get("status", "warning")),
                },
                *({"label": line, "status": "warning", "tone": "warning"} for line in (alerts or ["当前没有额外风险提醒。"])),
            ],
        },
    ]

    if allocation_plan.get("bucket_checklist"):
        sections.insert(
            0,
            {
                "title": "目标配置偏离",
                "kind": "checklist",
                "tone": "panel",
                "items": [
                    {
                        "label": item.get("label", item.get("bucket", "未知")),
                        "detail": item.get("detail", ""),
                        "status": item.get("status", "info"),
                        "status_text": item.get("status_text", "INFO"),
                        "tone": item.get("tone", "info"),
                    }
                    for item in allocation_plan.get("bucket_checklist", [])[:4]
                ],
            },
        )

    if view_mode == "analyst":
        sections.append(
            {
                "title": "角色分布",
                "kind": "bars",
                "tone": "soft",
                "items": [
                    {"label": item.get("name", "暂无"), "value": item.get("weight_pct", 0), "value_text": pct(item.get("weight_pct", 0), 2), "tone": "info"}
                    for item in (exposure or {}).get("by_role", [])[:5]
                ]
                or [{"label": "暂无", "value": 0, "value_text": "--", "tone": "muted"}],
            }
        )
    else:
        sections.append(
            {
                "title": "今天该重点盯什么",
                "kind": "bullets",
                "tone": "panel",
                "items": alerts[:5] or ["当前组合没有新的高优先级异常，先关注待执行建议和实时分歧。"],
            }
        )

    return {
        "title": "组合风险总览" if view_mode == "investor" else "Portfolio / Risk Cockpit",
        "subtitle": "把仓位、风险、执行和数据可信度放在同一页联查。",
        "summary_pairs": [
            ("总资产", money(portfolio.get("total_value", 0))),
            ("现金仓", money(cash.get("current_value", 0))),
            ("今日实时收益", money(totals.get("estimated_intraday_pnl_amount", 0))),
            ("已执行金额", money(executed_amount)),
            ("待执行建议", str(pending_count)),
            ("高波动主题占比", pct(concentration.get("high_volatility_theme_weight_pct", 0), 2)),
            ("海外权益占比", pct(concentration.get("overseas_weight_pct", 0), 2)),
            ("陈旧实时项", str(stale_count)),
        ],
        "sections": sections,
    }


def build_portfolio_strategy_schema(state: dict, exposure: dict | None, view_mode: str = "analyst") -> dict:
    portfolio = state.get("portfolio", {}) or {}
    validated = state.get("validated", {}) or {}
    exposure = exposure or {}
    allocation_plan = exposure.get("allocation_plan", {}) or {}
    bucket_summary = exposure.get("by_strategy_bucket", []) or []
    members = exposure.get("strategy_bucket_members", {}) or {}
    concentration = exposure.get("concentration_metrics", {}) or {}
    actionable_count = sum(len(validated.get(section, []) or []) for section in ("tactical_actions", "dca_actions"))

    sections = [
        {
            "title": "目标配置与偏离",
            "kind": "checklist",
            "tone": "panel",
            "items": [
                {
                    "label": item.get("label", item.get("bucket", "未知")),
                    "detail": f"{item.get('detail', '')} {item.get('guidance', '')}".strip(),
                    "status": item.get("status", "info"),
                    "status_text": item.get("status_text", "INFO"),
                    "tone": item.get("tone", "info"),
                }
                for item in allocation_plan.get("bucket_checklist", [])
            ]
            or [{"label": "暂无目标配置", "detail": "尚未读取到 allocation 配置。", "status": "info", "status_text": "INFO", "tone": "info"}],
        },
        {
            "title": "当前资金层分布",
            "kind": "bars",
            "tone": "surface",
            "items": [
                {
                    "label": _bucket_label(item.get("name", "")),
                    "value": item.get("weight_pct", 0),
                    "value_text": f"{pct(item.get('weight_pct', 0), 2)} / 目标 {pct(allocation_plan.get('targets_pct', {}).get(item.get('name', ''), 0), 2)}",
                    "tone": "warning" if allocation_plan.get("status_by_bucket", {}).get(item.get("name")) == "overweight" else "info" if allocation_plan.get("status_by_bucket", {}).get(item.get("name")) == "underweight" else "success",
                }
                for item in bucket_summary
            ],
        },
        {
            "title": "再平衡建议",
            "kind": "bullets",
            "tone": "warning" if allocation_plan.get("rebalance_needed") else "success",
            "items": allocation_plan.get("rebalance_suggestions", []) or ["当前配置大体在带宽内，无需额外再平衡动作。"],
        },
        {
            "title": "集中度与风险",
            "kind": "kv",
            "tone": "soft",
            "pairs": [
                ("前三基金集中度", pct(concentration.get("top3_fund_weight_pct", 0), 2)),
                ("前三主题家族集中度", pct(concentration.get("top3_family_weight_pct", 0), 2)),
                ("高波动主题占比", pct(concentration.get("high_volatility_theme_weight_pct", 0), 2)),
                ("防守缓冲占比", pct(concentration.get("defensive_buffer_weight_pct", 0), 2)),
                ("海外权益占比", pct(concentration.get("overseas_weight_pct", 0), 2)),
                ("待执行动作数", str(actionable_count)),
            ],
        },
    ]

    if view_mode == "analyst":
        sections.append(
            {
                "title": "底层持仓归属",
                "kind": "bullets",
                "tone": "surface",
                "items": [
                    f"{_bucket_label(bucket)}："
                    + "；".join(f"{item.get('fund_name', item.get('fund_code', '未知'))} {pct(item.get('weight_pct', 0), 2)}" for item in members.get(bucket, [])[:6])
                    for bucket in ("core_long_term", "satellite_mid_term", "tactical_short_term", "cash_defense")
                ],
            }
        )

    return {
        "title": "组合配置与偏离" if view_mode == "investor" else "组合策略与配置目标",
        "subtitle": "先看目标配置与当前偏离，再决定今天的动作是在修结构，还是只做短线应对。",
        "lead": (allocation_plan.get("rebalance_suggestions") or ["当前配置大体在带宽内，可优先执行高置信动作。"])[0],
        "badges": [
            {"text": f"总资产 {money(portfolio.get('total_value', 0))}", "tone": "info"},
            {"text": f"再平衡 {'需要' if allocation_plan.get('rebalance_needed') else '暂缓'}", "tone": "warning" if allocation_plan.get("rebalance_needed") else "success"},
            {"text": f"高波动主题 {pct(concentration.get('high_volatility_theme_weight_pct', 0), 2)}", "tone": "warning"},
        ],
        "summary_pairs": [
            ("组合", portfolio.get("portfolio_name", "暂无")),
            ("估值日期", portfolio.get("as_of_date", "暂无")),
            ("重估时间", portfolio.get("last_valuation_generated_at", "暂无")),
            ("再平衡带宽", pct(allocation_plan.get("rebalance_band_pct", 5.0), 2)),
            ("核心仓目标", pct(allocation_plan.get("targets_pct", {}).get("core_long_term", 0), 2)),
            ("战术仓目标", pct(allocation_plan.get("targets_pct", {}).get("tactical_short_term", 0), 2)),
        ],
        "sections": sections,
        "raw_text": state.get("portfolio_report", ""),
        "show_raw_text": view_mode == "analyst",
    }


def build_portfolio_actions_schema(state: dict, exposure: dict | None, view_mode: str = "analyst") -> dict:
    validated = state.get("validated", {}) or {}
    allocation_plan = (exposure or {}).get("allocation_plan", {}) or {}
    actions = (validated.get("tactical_actions", []) or []) + (validated.get("dca_actions", []) or [])
    hold_items = validated.get("hold_actions", []) or []
    return {
        "title": "今天怎么做" if view_mode == "investor" else "执行与观察",
        "subtitle": "把今天真正要执行的动作和需要继续观察的方向分开。",
        "summary_pairs": [
            ("主动动作", str(len(validated.get("tactical_actions", []) or []))),
            ("定投动作", str(len(validated.get("dca_actions", []) or []))),
            ("观察项", str(len(hold_items))),
            ("需要再平衡", "是" if allocation_plan.get("rebalance_needed") else "否"),
        ],
        "sections": [
            {
                "title": "今天优先执行",
                "kind": "bullets",
                "tone": "accent",
                "items": [
                    f"{item.get('fund_name')}：{item.get('validated_action')} {money(item.get('validated_amount', 0))}"
                    f"（{_bucket_label(item.get('strategy_bucket', ''))}）"
                    for item in actions[:8]
                ]
                or ["今天没有新的可执行动作，先观察。"],
            },
            {
                "title": "继续观察",
                "kind": "bullets",
                "tone": "soft",
                "items": [
                    f"{item.get('fund_name')}：{item.get('thesis', '继续观察')}（{_bucket_label(item.get('strategy_bucket', ''))}）"
                    for item in hold_items[:10]
                ]
                or ["暂无观察项。"],
            },
        ],
        "show_raw_text": False,
    }


def build_portfolio_report_schema(state: dict, exposure: dict | None, view_mode: str = "analyst") -> dict:
    exposure = exposure or {}
    strategy_schema = build_portfolio_strategy_schema(state, exposure, view_mode)
    actions_schema = build_portfolio_actions_schema(state, exposure, view_mode)
    allocation_plan = exposure.get("allocation_plan", {}) or {}
    concentration = exposure.get("concentration_metrics", {}) or {}
    return {
        "title": "组合配置报告" if view_mode == "investor" else "组合配置与执行报告",
        "subtitle": "按一份连续报告阅读：先看配置偏离，再看再平衡，再看今天动作和组合原则。",
        "lead": strategy_schema.get("lead", "先看配置目标和当前偏离。"),
        "badges": [
            {"text": f"再平衡 {'需要' if allocation_plan.get('rebalance_needed') else '暂缓'}", "tone": "warning" if allocation_plan.get("rebalance_needed") else "success"},
            {"text": f"高波动主题 {pct(concentration.get('high_volatility_theme_weight_pct', 0), 2)}", "tone": "warning"},
            {"text": f"防守缓冲 {pct(concentration.get('defensive_buffer_weight_pct', 0), 2)}", "tone": "success"},
        ],
        "summary_pairs": strategy_schema.get("summary_pairs", []),
        "sections": strategy_schema.get("sections", [])
        + actions_schema.get("sections", [])
        + [
            {
                "title": "组合原则",
                "kind": "bullets",
                "tone": "soft",
                "items": (allocation_plan.get("rebalance_suggestions", [])[:3] or ["当前配置大体处于带宽内，优先按高置信建议小步执行。"])
                + [
                    "优先用组合层目标解释单基金动作，避免只盯单日涨跌。",
                    "卖出后的资金先看是否应该回防守层，再决定要不要补长期核心仓。",
                    "如果多个主题都只是小仓位且长期目标不清晰，优先先收敛，再考虑新增动作。",
                ],
            }
        ],
        "raw_text": state.get("portfolio_report", ""),
        "show_raw_text": view_mode == "analyst",
    }


def build_fund_detail_schema(
    item: dict,
    realtime_item: dict | None,
    review_item: dict | None,
    aggregate: dict | None = None,
    view_mode: str = "analyst",
) -> dict:
    action = item.get("validated_action", "hold")
    execution_status = item.get("execution_status", "pending")
    agent_summary = summarize_fund_agent_signals(aggregate or {}, item.get("fund_code", ""))
    stage_summary = summarize_fund_stage_signals(aggregate or {}, item.get("fund_code", ""))

    sections = [
        {"title": "核心判断", "kind": "text", "tone": "accent", "text": item.get("thesis", "暂无")},
        {"title": "依据", "kind": "bullets", "tone": "surface", "items": item.get("evidence", []) or ["暂无"]},
        {"title": "风险", "kind": "bullets", "tone": "warning", "items": item.get("risks", []) or ["暂无"]},
        {"title": "规则校验", "kind": "bullets", "tone": "soft", "items": item.get("validation_notes", []) or ["暂无"]},
        {"title": "参考智能体", "kind": "bullets", "tone": "panel", "items": item.get("agent_support", []) or ["暂无"]},
        {
            "title": "委员会共识",
            "kind": "kv",
            "tone": "info",
            "pairs": [
                ("支持智能体", str(len(agent_summary["supporting_agents"]))),
                ("谨慎/反对智能体", str(len(agent_summary["caution_agents"]))),
                ("中性智能体", str(len(agent_summary["neutral_agents"]))),
                ("存在分歧", _yes_no(agent_summary["has_conflict"])),
            ],
        },
    ]

    stage_items = []
    for stage in ("analyst", "researcher", "manager"):
        stage_bucket = stage_summary.get(stage, {})
        support_count = len(stage_bucket.get("support", []))
        caution_count = len(stage_bucket.get("caution", []))
        neutral_count = len(stage_bucket.get("neutral", []))
        if support_count == caution_count == neutral_count == 0:
            continue
        if support_count > caution_count:
            tone = stage_tone(stage) if not stage_bucket.get("has_conflict") else "warning"
            status = "success" if not stage_bucket.get("has_conflict") else "warning"
            status_text = "LEAN+"
        elif caution_count > support_count:
            tone = "warning"
            status = "warning"
            status_text = "LEAN-"
        else:
            tone = "info"
            status = "info"
            status_text = "MIXED"
        detail = f"支持 {support_count} | 谨慎 {caution_count} | 中性 {neutral_count}"
        highlights = stage_bucket.get("highlights", []) or []
        if highlights:
            detail = f"{detail} | {'；'.join(highlights[:2])}"
        stage_items.append(
            {
                "label": stage_label(stage),
                "detail": detail,
                "status": status,
                "status_text": status_text,
                "tone": tone,
            }
        )
    if stage_items:
        sections.append(
            {
                "title": "研究链路",
                "kind": "checklist",
                "tone": "panel",
                "items": stage_items,
            }
        )

    if agent_summary["committee_views"]:
        sections.append(
            {
                "title": "委员会覆盖",
                "kind": "checklist",
                "tone": "surface",
                "items": [
                    {
                        "label": f"{entry['agent_name']}：{entry.get('action_bias', 'hold')}",
                        "detail": entry.get("comment", ""),
                        "status": "success" if entry.get("bucket") == "support" else "warning" if entry.get("bucket") == "caution" else "info",
                        "tone": "success" if entry.get("bucket") == "support" else "warning" if entry.get("bucket") == "caution" else "info",
                    }
                    for entry in agent_summary["committee_views"]
                ],
            }
        )
    if agent_summary["support_points"]:
        sections.append({"title": "主要支持理由", "kind": "bullets", "tone": "success", "items": agent_summary["support_points"]})
    if agent_summary["caution_points"]:
        sections.append({"title": "主要反对理由", "kind": "bullets", "tone": "warning", "items": agent_summary["caution_points"]})
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
                    ("估值-代理分歧", pct(realtime_item.get("divergence_pct"), 2)),
                    ("异常程度", num(realtime_item.get("anomaly_score"), 2)),
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
                    ("相对基准", pct(review_item.get("excess_return_vs_benchmark_pct", 0), 2)),
                ],
            }
        )

    if view_mode == "investor":
        sections = sections[:1] + [section for section in sections[5:] if section["title"] not in {"参考智能体", "规则校验"}]

    return {
        "title": item.get("fund_name", "基金详情"),
        "subtitle": f"{item.get('fund_code', '暂无')} | {item.get('_section', 'unknown')}",
        "lead": item.get("thesis", "暂无"),
        "badges": [
            {"text": f"动作 {action}", "tone": _action_tone(action)},
            {"text": f"执行 {execution_status}", "tone": _status_tone(execution_status)},
            {"text": f"可信度 {num(item.get('confidence'), 2)}", "tone": "info"},
            {"text": f"存在分歧 {_yes_no(agent_summary['has_conflict'])}", "tone": "warning" if agent_summary["has_conflict"] else "success"},
        ],
        "summary_pairs": [
            ("建议编号", item.get("suggestion_id", "暂无")),
            ("基金代码", item.get("fund_code", "暂无")),
            ("基金名称", item.get("fund_name", "暂无")),
            ("策略桶", _bucket_label(item.get("strategy_bucket", ""))),
            ("所属分组", item.get("_section", "暂无")),
            ("模型原动作", item.get("model_action", "暂无")),
            ("校验后动作", action),
            ("建议金额", money(item.get("validated_amount", 0))),
            ("执行状态", execution_status),
            ("已执行金额", money(item.get("executed_amount", 0))),
            ("可信度", num(item.get("confidence"), 2)),
            ("最近交易日期", item.get("linked_trade_date", "暂无") or "暂无"),
            ("已绑定交易", _yes_no(bool(item.get("linked_trade_date")))),
        ],
        "sections": sections,
        "raw_text": build_fund_detail_text(item, realtime_item, review_item),
        "show_raw_text": view_mode == "analyst",
    }


def build_realtime_detail_schema(item: dict, view_mode: str = "analyst") -> dict:
    sections = [
        {
            "title": "时点与模式",
            "kind": "kv",
            "tone": "accent",
            "pairs": [
                ("模式说明", item.get("reason", "暂无")),
                ("估值时间", item.get("estimate_time", "暂无")),
                ("代理时间", item.get("proxy_time", "暂无")),
                ("官方净值日期", item.get("official_nav_date", "暂无")),
                ("数据陈旧天数", str(item.get("freshness_age_business_days", 0))),
            ],
        },
        {
            "title": "份额与净值",
            "kind": "kv",
            "tone": "surface",
            "pairs": [
                ("持有份额", num(item.get("holding_units"), 6)),
                ("份额来源", item.get("unit_source", "暂无")),
                ("份额可信度", num(item.get("unit_confidence"), 2)),
                ("官方净值", num(item.get("official_nav"), 6)),
                ("有效净值", num(item.get("effective_nav"), 6)),
                ("官方净值时效", item.get("official_nav_freshness_label", "暂无")),
            ],
        },
        {
            "title": "涨跌与异常",
            "kind": "kv",
            "tone": "info",
            "pairs": [
                ("估值涨跌", pct(item.get("estimate_change_pct"), 2)),
                ("估值时效", item.get("estimate_freshness_label", "暂无")),
                ("代理涨跌", pct(item.get("proxy_change_pct"), 2)),
                ("代理时效", item.get("proxy_freshness_label", "暂无")),
                ("采用涨跌", pct(item.get("effective_change_pct"), 2)),
                ("估值-代理分歧", pct(item.get("divergence_pct"), 2)),
                ("估值策略允许", _yes_no(bool(item.get("estimate_policy_allowed")))),
                ("代理策略允许", _yes_no(bool(item.get("proxy_policy_allowed")))),
            ],
        },
    ]

    if view_mode == "investor":
        sections = sections[:1] + [sections[2]]

    return {
        "title": item.get("fund_name", "实时详情"),
        "subtitle": f"{item.get('fund_code', '暂无')} | {item.get('mode', 'unknown')}",
        "lead": item.get("reason", "暂无"),
        "badges": [
            {"text": f"模式 {item.get('mode', '暂无')}", "tone": "info"},
            {"text": f"可信度 {num(item.get('confidence'), 2)}", "tone": "info"},
            {"text": "数据陈旧" if item.get("stale") else "同日快照", "tone": "warning" if item.get("stale") else "success"},
            {"text": f"异常 {num(item.get('anomaly_score'), 2)}", "tone": "warning" if float(item.get("anomaly_score", 0) or 0) >= 8 else "neutral"},
        ],
        "summary_pairs": [
            ("基金代码", item.get("fund_code", "暂无")),
            ("角色", item.get("role", "暂无")),
            ("风格分组", item.get("style_group", "暂无")),
            ("估算模式", item.get("mode", "暂无")),
            ("可信度", num(item.get("confidence"), 2)),
            ("异常程度", num(item.get("anomaly_score"), 2)),
            ("估值-代理分歧", pct(item.get("divergence_pct"), 2)),
            ("仓位占比", pct(item.get("position_weight_pct"), 2)),
            ("今日估算收益", money(item.get("estimated_intraday_pnl_amount", 0))),
            ("今日估算收益率", pct(item.get("estimated_intraday_pnl_pct", 0), 4)),
        ],
        "sections": sections,
        "raw_text": build_realtime_detail_text(item),
        "show_raw_text": view_mode == "analyst",
    }


def build_trade_precheck_schema(
    selected: dict | None,
    cash: dict | None,
    constraint: dict | None,
    action: str,
    amount: float,
    nav_text: str,
    units_text: str,
    view_mode: str = "analyst",
) -> dict:
    if not selected:
        return {"title": "交易前检查", "subtitle": "请选择基金后再查看检查结果。"}

    constraint = constraint or {}
    current_value = float(selected.get("current_value", 0) or 0)
    cash_value = float(cash.get("current_value", 0) or 0) if cash else 0.0
    cap_value = float(selected.get("cap_value", 0) or 0)
    available_to_sell = float(constraint.get("available_to_sell", current_value) or 0)
    locked_amount = float(constraint.get("locked_amount", 0) or 0)
    post_fund_value = current_value + amount if action in {"buy", "switch_in"} else current_value - amount if action in {"sell", "switch_out"} else current_value
    post_cash_value = cash_value - amount if action in {"buy", "switch_in"} else cash_value + amount if action in {"sell", "switch_out"} else cash_value
    remaining_cap_room = max(0.0, cap_value - post_fund_value) if cap_value > 0 else 0.0

    checks = []
    if action in {"buy", "switch_in"}:
        checks.append({"label": "现金仓是否足够", "detail": f"当前现金仓 {money(cash_value)}，本次需要 {money(amount)}。", "status": "success" if cash_value >= amount else "danger", "status_text": "OK" if cash_value >= amount else "RISK", "tone": "success" if cash_value >= amount else "danger"})
    elif action in {"sell", "switch_out"}:
        checks.append({"label": "当前可卖金额是否足够", "detail": f"当前可卖 {money(available_to_sell)}，本次计划卖出 {money(amount)}。", "status": "success" if available_to_sell >= amount else "danger", "status_text": "OK" if available_to_sell >= amount else "RISK", "tone": "success" if available_to_sell >= amount else "danger"})
    if cap_value > 0:
        checks.append({"label": "是否触碰单只上限", "detail": f"上限 {money(cap_value)}，交易后估算 {money(post_fund_value)}。", "status": "success" if post_fund_value <= cap_value else "warning", "status_text": "SAFE" if post_fund_value <= cap_value else "CAP", "tone": "success" if post_fund_value <= cap_value else "warning"})
    checks.append({"label": "锁定金额提示", "detail": f"当前锁定金额 {money(locked_amount)}。", "status": "warning" if locked_amount > 0 else "success", "status_text": "LOCK" if locked_amount > 0 else "OPEN", "tone": "warning" if locked_amount > 0 else "success"})
    checks.append({"label": "持有与到账节奏", "detail": f"最短持有 {constraint.get('min_hold_days', 0)} 天，赎回到账 T+{constraint.get('redeem_settlement_days', 0)}。", "status": "info", "status_text": "INFO", "tone": "info"})
    checks.append({"label": "转换能力", "detail": "支持直接转换。" if constraint.get("conversion_supported") else "不支持直接转换。", "status": "success" if constraint.get("conversion_supported") else "warning", "status_text": "YES" if constraint.get("conversion_supported") else "NO", "tone": "success" if constraint.get("conversion_supported") else "warning"})
    checks.append({"label": "成交细节补充", "detail": "已录入成交净值/份额，可提升持仓精度。" if (nav_text or units_text) else "建议补充成交净值或成交份额，以提升持仓精度。", "status": "success" if (nav_text or units_text) else "warning", "status_text": "DONE" if (nav_text or units_text) else "TODO", "tone": "success" if (nav_text or units_text) else "warning"})

    sections = [
        {"title": "交易前检查", "kind": "checklist", "tone": "surface", "items": checks},
        {
            "title": "交易后模拟",
            "kind": "kv",
            "tone": "panel",
            "pairs": [
                ("交易后基金市值", money(post_fund_value)),
                ("交易后现金仓", money(post_cash_value)),
                ("距离上限余量", money(remaining_cap_room)),
                ("锁定金额", money(locked_amount)),
                ("申购确认节奏", f"T+{constraint.get('purchase_confirm_days', 0)}"),
                ("赎回到账节奏", f"T+{constraint.get('redeem_settlement_days', 0)}"),
            ],
        },
        {"title": "约束提示", "kind": "bullets", "tone": "soft", "items": constraint.get("notes", []) or ["暂无额外约束提示。"]},
    ]

    if view_mode == "investor":
        sections = sections[:2]

    lead_action = "买入" if action in {"buy", "switch_in"} else "卖出" if action in {"sell", "switch_out"} else action or "操作"

    return {
        "title": "交易前检查台",
        "subtitle": "先确认风险，再提交交易记录。",
        "lead": f"你即将{lead_action} {selected.get('fund_name', '该基金')} {money(amount)}。先确认现金、上限、持有约束和到账节奏。",
        "badges": [
            {"text": f"动作 {action}", "tone": _action_tone(action)},
            {"text": f"金额 {money(amount)}", "tone": "info"},
            {"text": f"费率 {pct(constraint.get('estimated_redeem_fee_rate', 0), 2)}", "tone": "warning"},
        ],
        "summary_pairs": [
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
        ],
        "sections": sections,
        "raw_text": build_trade_preview_text(selected, cash, constraint),
    }
