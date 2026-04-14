from __future__ import annotations

from collections import defaultdict


STRATEGY_BUCKET_LABELS = {
    "core_long_term": "长期核心仓",
    "satellite_mid_term": "中期卫星仓",
    "tactical_short_term": "短期战术仓",
    "cash_defense": "防守/现金仓",
}

DEFAULT_STRATEGY_TARGETS = {
    "core_long_term": 50.0,
    "satellite_mid_term": 20.0,
    "tactical_short_term": 10.0,
    "cash_defense": 20.0,
}

DEFAULT_ALLOCATION_SETTINGS = {
    "rebalance_band_pct": 5.0,
    "max_single_theme_family_pct": 30.0,
    "max_high_volatility_theme_pct": 45.0,
}

SHORT_TERM_STYLE_GROUPS = {
    "industrial_metal",
    "chemical",
    "precious_metals",
    "growth_rotation",
}


def safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def infer_market_bucket(fund: dict) -> str:
    role = (fund.get("role") or "").lower()
    style = (fund.get("style_group") or "").lower()
    if role == "cash_hub" or "cash" in style:
        return "cash_like"
    if role == "fixed_hold" or "bond" in style:
        return "bond"
    overseas_markers = ("sp500", "nasdaq", "internet", "qdii", "us_", "global")
    if any(marker in style for marker in overseas_markers):
        return "overseas_equity"
    return "domestic_equity"


def infer_theme_family(fund: dict) -> str:
    style = (fund.get("style_group") or "").lower()
    mapping = {
        "industrial_metal": "cyclical_resources",
        "chemical": "cyclical_resources",
        "grain_agriculture": "domestic_defensive_theme",
        "carbon_neutral": "energy_transition",
        "grid_equipment": "energy_transition",
        "high_end_equipment": "advanced_manufacturing",
        "growth_rotation": "growth_cluster",
        "tech_growth": "growth_cluster",
        "ai": "growth_cluster",
        "china_us_internet": "global_growth",
        "sp500_core": "global_growth",
        "nasdaq_core": "global_growth",
        "precious_metals": "commodity_hedge",
        "cash_buffer": "defensive_buffer",
        "bond_anchor": "defensive_buffer",
    }
    return mapping.get(style, style or "unknown")


def infer_strategy_bucket(fund: dict) -> str:
    explicit = (fund.get("strategy_bucket") or "").strip()
    if explicit in STRATEGY_BUCKET_LABELS:
        return explicit

    role = (fund.get("role") or "").lower()
    style = (fund.get("style_group") or "").lower()
    if role == "core_dca":
        return "core_long_term"
    if role in {"cash_hub", "fixed_hold"}:
        return "cash_defense"
    if style in SHORT_TERM_STYLE_GROUPS:
        return "tactical_short_term"
    return "satellite_mid_term"


def normalize_strategy_targets(strategy: dict | None = None) -> dict[str, float]:
    allocation = (strategy or {}).get("allocation", {}) or {}
    targets = allocation.get("targets", {}) or {}
    resolved = dict(DEFAULT_STRATEGY_TARGETS)
    for key in resolved:
        if key in targets:
            resolved[key] = round(max(0.0, safe_float(targets[key])), 2)
        legacy_key = f"target_{key}_pct"
        if legacy_key in allocation:
            resolved[key] = round(max(0.0, safe_float(allocation[legacy_key])), 2)
    return resolved


def normalize_allocation_settings(strategy: dict | None = None) -> dict[str, float]:
    allocation = (strategy or {}).get("allocation", {}) or {}
    resolved = dict(DEFAULT_ALLOCATION_SETTINGS)
    for key in resolved:
        if key in allocation:
            resolved[key] = round(max(0.0, safe_float(allocation[key])), 2)
    return resolved


def summarize_bucket(values: dict[str, float], total_value: float) -> list[dict]:
    items = []
    for key, value in sorted(values.items(), key=lambda item: item[1], reverse=True):
        share = round((value / total_value) * 100, 2) if total_value > 0 else 0.0
        items.append({"name": key, "value": round(value, 2), "weight_pct": share})
    return items


def _strategy_members(funds: list[dict], total_value: float) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for fund in funds:
        value = safe_float(fund.get("current_value", 0.0))
        bucket = infer_strategy_bucket(fund)
        grouped[bucket].append(
            {
                "fund_code": fund.get("fund_code", ""),
                "fund_name": fund.get("fund_name", fund.get("fund_code", "")),
                "style_group": fund.get("style_group", "unknown"),
                "value": round(value, 2),
                "weight_pct": round((value / total_value) * 100, 2) if total_value > 0 else 0.0,
            }
        )
    for bucket, items in grouped.items():
        grouped[bucket] = sorted(items, key=lambda item: item["value"], reverse=True)
    return grouped


def _bucket_guidance(bucket: str) -> str:
    if bucket == "core_long_term":
        return "优先承接长期定投和中长期配置，不宜被短线噪音频繁打断。"
    if bucket == "satellite_mid_term":
        return "保留中期主题暴露，但应控制重叠和拥挤。"
    if bucket == "tactical_short_term":
        return "只保留高置信、可快速验证的战术动作，避免多点分散。"
    return "承担现金缓冲、防守与等待资金回收的角色。"


def build_allocation_plan(
    total_value: float,
    strategy_bucket_values: dict[str, float],
    largest_theme_family: dict,
    high_vol_theme_weight: float,
    strategy: dict | None = None,
) -> dict:
    targets_pct = normalize_strategy_targets(strategy)
    settings = normalize_allocation_settings(strategy)
    rebalance_band_pct = settings["rebalance_band_pct"]
    current_pct = {
        bucket: round((strategy_bucket_values.get(bucket, 0.0) / total_value) * 100, 2) if total_value > 0 else 0.0
        for bucket in STRATEGY_BUCKET_LABELS
    }
    drift_pct = {bucket: round(current_pct[bucket] - targets_pct[bucket], 2) for bucket in STRATEGY_BUCKET_LABELS}
    status_by_bucket = {}
    bucket_checklist: list[dict] = []
    for bucket, label in STRATEGY_BUCKET_LABELS.items():
        drift = drift_pct[bucket]
        if drift > rebalance_band_pct:
            status = "overweight"
            tone = "warning"
            status_text = "HIGH"
        elif drift < -rebalance_band_pct:
            status = "underweight"
            tone = "info"
            status_text = "LOW"
        else:
            status = "aligned"
            tone = "success"
            status_text = "OK"
        status_by_bucket[bucket] = status
        bucket_checklist.append(
            {
                "bucket": bucket,
                "label": label,
                "detail": f"当前 {current_pct[bucket]:.2f}% / 目标 {targets_pct[bucket]:.2f}% / 偏离 {drift:+.2f}%",
                "status": status,
                "status_text": status_text,
                "tone": tone,
                "guidance": _bucket_guidance(bucket),
            }
        )

    suggestions: list[str] = []
    if status_by_bucket["tactical_short_term"] == "overweight":
        suggestions.append("短期战术仓高于目标带宽，优先减少最弱或重叠最高的主题仓，把卖出资金先留在现金/防守层。")
    if status_by_bucket["core_long_term"] == "underweight":
        suggestions.append("长期核心仓低于目标带宽，后续新增资金优先补向长期核心而不是继续扩张主题仓。")
    if status_by_bucket["cash_defense"] == "underweight":
        suggestions.append("防守/现金仓偏低，近期减仓回笼资金应优先保留缓冲，而不是立即再投入高波动主题。")
    if status_by_bucket["satellite_mid_term"] == "overweight":
        suggestions.append("中期卫星仓偏高，建议合并重叠主题，减少‘多个相近赛道小仓并存’。")
    if largest_theme_family.get("weight_pct", 0) >= settings["max_single_theme_family_pct"]:
        suggestions.append(
            f"单一主题家族 {largest_theme_family.get('name', 'unknown')} 占比 {largest_theme_family.get('weight_pct', 0)}%，已触及集中度阈值，应优先内部收敛。"
        )
    if high_vol_theme_weight >= settings["max_high_volatility_theme_pct"]:
        suggestions.append(f"高波动主题合计占比 {high_vol_theme_weight}%，高于预设阈值，短线新增净暴露应更克制。")
    if not suggestions:
        suggestions.append("当前配置大体在目标带宽内，先按既定定投和高置信日内动作小步执行。")

    rebalance_needed = any(status != "aligned" for status in status_by_bucket.values()) or len(suggestions) > 1
    return {
        "targets_pct": targets_pct,
        "current_pct": current_pct,
        "drift_pct": drift_pct,
        "rebalance_band_pct": rebalance_band_pct,
        "max_single_theme_family_pct": settings["max_single_theme_family_pct"],
        "max_high_volatility_theme_pct": settings["max_high_volatility_theme_pct"],
        "status_by_bucket": status_by_bucket,
        "bucket_checklist": bucket_checklist,
        "rebalance_needed": rebalance_needed,
        "rebalance_suggestions": suggestions,
    }


def analyze_portfolio_exposure(portfolio: dict, strategy: dict | None = None) -> dict:
    funds = portfolio.get("funds", [])
    total_value = round(sum(safe_float(fund.get("current_value", 0.0)) for fund in funds), 2)

    role_values: dict[str, float] = defaultdict(float)
    style_values: dict[str, float] = defaultdict(float)
    market_values: dict[str, float] = defaultdict(float)
    family_values: dict[str, float] = defaultdict(float)
    category_values: dict[str, float] = defaultdict(float)
    company_values: dict[str, float] = defaultdict(float)
    strategy_bucket_values: dict[str, float] = defaultdict(float)
    fund_weights: list[tuple[str, float]] = []
    alerts: list[str] = []

    for fund in funds:
        value = safe_float(fund.get("current_value", 0.0))
        role_values[fund.get("role", "unknown")] += value
        style_values[fund.get("style_group", "unknown")] += value
        market_values[infer_market_bucket(fund)] += value
        family_values[infer_theme_family(fund)] += value
        category_values[fund.get("category", "unknown")] += value
        strategy_bucket_values[infer_strategy_bucket(fund)] += value
        company = (fund.get("fund_profile", {}) or {}).get("management_company") or fund.get("management_company") or "unknown"
        company_values[company] += value
        fund_weights.append((fund.get("fund_code", "unknown"), value))

    style_summary = summarize_bucket(style_values, total_value)
    role_summary = summarize_bucket(role_values, total_value)
    market_summary = summarize_bucket(market_values, total_value)
    family_summary = summarize_bucket(family_values, total_value)
    category_summary = summarize_bucket(category_values, total_value)
    company_summary = summarize_bucket(company_values, total_value)
    fund_summary = summarize_bucket(dict(fund_weights), total_value)
    strategy_bucket_summary = summarize_bucket(strategy_bucket_values, total_value)

    largest_style = style_summary[0] if style_summary else {"weight_pct": 0.0, "name": "unknown"}
    largest_fund = fund_summary[0] if fund_summary else {"weight_pct": 0.0, "name": "unknown"}
    largest_family = family_summary[0] if family_summary else {"weight_pct": 0.0, "name": "unknown"}
    largest_company = company_summary[0] if company_summary else {"weight_pct": 0.0, "name": "unknown"}
    top3_style_weight = round(sum(item["weight_pct"] for item in style_summary[:3]), 2)
    top3_fund_weight = round(sum(item["weight_pct"] for item in fund_summary[:3]), 2)
    top3_family_weight = round(sum(item["weight_pct"] for item in family_summary[:3]), 2)
    tactical_weight = round(sum(item["weight_pct"] for item in role_summary if item["name"] == "tactical"), 2)
    overseas_weight = round(sum(item["weight_pct"] for item in market_summary if item["name"] == "overseas_equity"), 2)
    defensive_weight = round(sum(item["weight_pct"] for item in market_summary if item["name"] in {"cash_like", "bond"}), 2)
    qdii_weight = round(sum(item["weight_pct"] for item in category_summary if item["name"] == "qdii_index"), 2)
    active_weight = round(sum(item["weight_pct"] for item in category_summary if item["name"] == "active_equity"), 2)
    index_weight = round(sum(item["weight_pct"] for item in category_summary if item["name"] in {"index_equity", "etf_linked"}), 2)
    high_vol_theme_weight = round(
        sum(
            item["weight_pct"]
            for item in family_summary
            if item["name"] in {"growth_cluster", "energy_transition", "cyclical_resources", "global_growth"}
        ),
        2,
    )

    if largest_style["weight_pct"] >= 20:
        alerts.append(f"单一风格暴露较高：{largest_style['name']} 占比 {largest_style['weight_pct']}%。")
    if largest_family["weight_pct"] >= 28:
        alerts.append(f"单一主题家族暴露较高：{largest_family['name']} 占比 {largest_family['weight_pct']}%。")
    if top3_style_weight >= 65:
        alerts.append(f"前三风格集中度偏高：合计 {top3_style_weight}%。")
    if top3_family_weight >= 70:
        alerts.append(f"前三主题家族集中度偏高：合计 {top3_family_weight}%。")
    if top3_fund_weight >= 45:
        alerts.append(f"前三基金持仓集中度偏高：合计 {top3_fund_weight}%。")
    if overseas_weight >= 25:
        alerts.append(f"海外权益暴露较高：{overseas_weight}%。")
    if qdii_weight >= 20:
        alerts.append(f"QDII 暴露较高：{qdii_weight}%。")
    if largest_company["name"] != "unknown" and largest_company["weight_pct"] >= 25:
        alerts.append(f"单一管理人暴露偏高：{largest_company['name']} 占比 {largest_company['weight_pct']}%。")
    if high_vol_theme_weight >= 45:
        alerts.append(f"高波动主题合计占比较高：{high_vol_theme_weight}%。")
    if defensive_weight < 15:
        alerts.append(f"防守缓冲偏低：现金+债券仅 {defensive_weight}%。")

    allocation_plan = build_allocation_plan(total_value, strategy_bucket_values, largest_family, high_vol_theme_weight, strategy=strategy)

    return {
        "total_value": total_value,
        "by_role": role_summary,
        "by_style_group": style_summary,
        "by_theme_family": family_summary,
        "by_market_bucket": market_summary,
        "by_category": category_summary,
        "by_management_company": company_summary,
        "by_strategy_bucket": strategy_bucket_summary,
        "strategy_bucket_labels": STRATEGY_BUCKET_LABELS,
        "strategy_bucket_members": _strategy_members(funds, total_value),
        "allocation_plan": allocation_plan,
        "largest_style_group": largest_style,
        "largest_fund": largest_fund,
        "largest_theme_family": largest_family,
        "largest_management_company": largest_company,
        "concentration_metrics": {
            "top3_style_weight_pct": top3_style_weight,
            "top3_family_weight_pct": top3_family_weight,
            "top3_fund_weight_pct": top3_fund_weight,
            "tactical_weight_pct": tactical_weight,
            "overseas_weight_pct": overseas_weight,
            "qdii_weight_pct": qdii_weight,
            "active_equity_weight_pct": active_weight,
            "index_like_weight_pct": index_weight,
            "high_volatility_theme_weight_pct": high_vol_theme_weight,
            "defensive_buffer_weight_pct": defensive_weight,
        },
        "alerts": alerts,
    }
