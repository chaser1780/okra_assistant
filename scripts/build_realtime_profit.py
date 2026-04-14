from __future__ import annotations

import argparse
from datetime import datetime

from common import (
    dump_json,
    ensure_layout,
    estimated_nav_path,
    intraday_proxy_path,
    load_json,
    load_portfolio,
    load_realtime_valuation_config,
    quote_path,
    realtime_monitor_path,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
)
from models import EstimateSnapshot, PortfolioFund, ProxySnapshot, QuoteSnapshot, RealtimeItem, RealtimeSnapshot


def safe_float(value) -> float | None:
    try:
        if value in (None, "", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def infer_cost_basis_value(fund: dict) -> float:
    if "cost_basis_value" in fund:
        return round(float(fund.get("cost_basis_value", 0.0)), 2)
    current_value = float(fund.get("current_value", 0.0))
    holding_pnl = float(fund.get("holding_pnl", 0.0))
    return round(max(0.0, current_value - holding_pnl), 2)


def get_stored_units(fund: dict) -> float | None:
    units = safe_float(fund.get("holding_units"))
    if units and units > 0:
        return round(units, 6)
    return None


def infer_units(current_value: float, unit_nav: float | None) -> float | None:
    if not unit_nav or unit_nav <= 0 or current_value <= 0:
        return None
    return round(current_value / unit_nav, 6)


def classify_quality(
    category: str,
    estimate_pct: float | None,
    proxy_pct: float | None,
    estimate_confidence: float,
    stale: bool,
) -> tuple[float, str, str]:
    if category == "qdii_index":
        if proxy_pct is not None:
            return 0.45, "proxy_primary", "QDII 估值常有滞后，优先采用代理行情方向，准确性中等偏低。"
        return 0.22, "stale", "QDII 缺少新鲜估值与代理行情时，只能低置信观察。"

    if estimate_pct is None and proxy_pct is None:
        return 0.10, "unavailable", "缺少实时估值和代理行情。"

    if estimate_pct is not None and not stale:
        if proxy_pct is None:
            return round(max(0.20, estimate_confidence), 2), "estimate_primary", "使用基金估值直接推算实时涨跌。"
        gap = abs(estimate_pct - proxy_pct)
        if gap <= 0.6:
            return round(min(0.98, estimate_confidence + 0.08), 2), "estimate_proxy_aligned", "估值与代理方向一致，可信度较高。"
        if gap <= 1.5:
            return round(max(0.35, estimate_confidence - 0.08), 2), "estimate_proxy_mixed", "估值与代理存在分歧，可信度下调。"
        return round(max(0.20, estimate_confidence - 0.18), 2), "estimate_proxy_diverged", "估值与代理明显背离，仅作谨慎参考。"

    if proxy_pct is not None:
        return 0.38, "proxy_fallback", "估值缺失或陈旧，退回代理行情估算。"

    return 0.18, "estimate_stale", "仅有陈旧估值，不适合做高置信实时收益判断。"


def pick_effective_pct(category: str, estimate_pct: float | None, proxy_pct: float | None, mode: str) -> float | None:
    if mode in {"estimate_primary", "estimate_proxy_aligned", "estimate_proxy_mixed", "estimate_proxy_diverged"}:
        return estimate_pct
    if mode in {"proxy_primary", "proxy_fallback"}:
        return proxy_pct
    if category == "qdii_index" and proxy_pct is not None:
        return proxy_pct
    return estimate_pct if estimate_pct is not None else proxy_pct


def derive_effective_nav(
    official_nav: float | None,
    estimate_nav: float | None,
    effective_pct: float | None,
    mode: str,
) -> float | None:
    if mode in {"estimate_primary", "estimate_proxy_aligned", "estimate_proxy_mixed", "estimate_proxy_diverged"}:
        return estimate_nav
    if official_nav is not None and effective_pct is not None:
        return round(official_nav * (1 + effective_pct / 100), 6)
    return estimate_nav or official_nav


def apply_realtime_policy(category: str, estimate: dict, valuation_config: dict) -> tuple[bool, bool, str]:
    realtime = valuation_config.get("realtime", {})
    if not bool(realtime.get("enabled", True)):
        return False, False, "实时收益策略已关闭。"
    enabled_categories = set(realtime.get("enable_for_categories", []))
    if enabled_categories and category not in enabled_categories:
        return False, bool(realtime.get("fallback_to_proxy", True)), "该基金类别按策略不直接使用基金估值，优先参考代理行情。"
    confidence_threshold = float(realtime.get("confidence_threshold", 0.0))
    estimate_confidence = float(estimate.get("confidence", 0.0) or 0.0)
    if estimate_confidence < confidence_threshold:
        return False, bool(realtime.get("fallback_to_proxy", True)), f"基金估值置信度低于阈值 {confidence_threshold:.2f}，退回代理行情。"
    if bool(estimate.get("stale", False)):
        return False, bool(realtime.get("fallback_to_proxy", True)), "基金估值已跨日，退回代理行情。"
    return True, bool(realtime.get("fallback_to_proxy", True)), ""


def build_market_timestamp(report_date: str, items: list[dict]) -> str:
    timezone = datetime.now().astimezone().tzinfo
    candidates: list[datetime] = []
    for item in items:
        for key in ("estimate_time", "proxy_time"):
            value = (item.get(key) or "").strip()
            if not value:
                continue
            for fmt in ("%H:%M:%S", "%H:%M"):
                try:
                    clock = datetime.strptime(value, fmt).time()
                    candidates.append(datetime.combine(datetime.strptime(report_date, "%Y-%m-%d").date(), clock, timezone))
                    break
                except ValueError:
                    continue
    if candidates:
        return max(candidates).isoformat(timespec="seconds")
    return timestamp_now()


def build_item(
    fund: PortfolioFund,
    quote_by_code: dict[str, QuoteSnapshot],
    estimate_by_code: dict[str, EstimateSnapshot],
    proxy_by_code: dict[str, ProxySnapshot],
    valuation_config: dict,
) -> RealtimeItem:
    code = fund["fund_code"]
    current_value = round(float(fund.get("current_value", 0.0)), 2)
    cost_basis_value = infer_cost_basis_value(fund)
    estimate = estimate_by_code.get(code, {})
    proxy = proxy_by_code.get(code, {})
    quote = quote_by_code.get(code, {})

    official_nav = safe_float(estimate.get("official_nav")) or safe_float(quote.get("nav"))
    estimate_nav = safe_float(estimate.get("estimate_nav"))
    estimate_pct = safe_float(estimate.get("estimate_change_pct"))
    proxy_pct = safe_float(proxy.get("change_pct"))
    stale = bool(estimate.get("stale", False))
    estimate_confidence = float(estimate.get("confidence", 0.0) or 0.0)
    category = estimate.get("category") or fund.get("category") or "unknown"
    estimate_allowed, proxy_allowed, policy_note = apply_realtime_policy(category, estimate, valuation_config)
    estimate_nav_for_use = estimate_nav if estimate_allowed else None
    estimate_pct_for_use = estimate_pct if estimate_allowed else None
    proxy_pct_for_use = proxy_pct if proxy_allowed else None
    stale_for_use = stale if estimate_allowed else True
    confidence_for_use = estimate_confidence if estimate_allowed else 0.0

    confidence, mode, reason = classify_quality(category, estimate_pct_for_use, proxy_pct_for_use, confidence_for_use, stale_for_use)
    if policy_note and mode in {"proxy_primary", "proxy_fallback", "unavailable", "estimate_stale", "stale"}:
        reason = policy_note
    effective_pct = pick_effective_pct(category, estimate_pct_for_use, proxy_pct_for_use, mode)
    divergence_pct = round(abs(estimate_pct - proxy_pct), 2) if estimate_pct is not None and proxy_pct is not None else None
    freshness_age_business_days = max(
        [
            max(0, int(value))
            for value in (
                estimate.get("estimate_freshness_business_day_gap"),
                estimate.get("official_nav_freshness_business_day_gap"),
                proxy.get("freshness_business_day_gap"),
            )
            if value not in (None, "")
        ]
        or [0]
    )

    stored_units = get_stored_units(fund)
    last_nav_for_units = safe_float(fund.get("last_valuation_nav")) or official_nav
    units = stored_units or infer_units(current_value, last_nav_for_units)
    unit_source = "stored" if stored_units is not None else "inferred_from_nav"
    unit_confidence = 0.99 if stored_units is not None else (0.92 if units is not None and last_nav_for_units is not None else 0.0)
    effective_nav = derive_effective_nav(official_nav, estimate_nav_for_use, effective_pct, mode)

    if units is not None and effective_nav is not None:
        estimated_position_value = round(units * effective_nav, 2)
        if official_nav is not None:
            estimated_intraday_pnl = round(units * (effective_nav - official_nav), 2)
        elif effective_pct is not None:
            estimated_intraday_pnl = round(current_value * effective_pct / 100, 2)
        else:
            estimated_intraday_pnl = 0.0
    elif effective_pct is not None:
        estimated_position_value = round(current_value * (1 + effective_pct / 100), 2)
        estimated_intraday_pnl = round(estimated_position_value - current_value, 2)
    else:
        estimated_position_value = current_value
        estimated_intraday_pnl = 0.0

    estimated_total_pnl = round(estimated_position_value - cost_basis_value, 2)
    estimated_total_return_pct = round((estimated_total_pnl / cost_basis_value) * 100, 2) if cost_basis_value > 0 else 0.0

    return {
        "fund_code": code,
        "fund_name": fund["fund_name"],
        "role": fund.get("role", ""),
        "style_group": fund.get("style_group", ""),
        "category": category,
        "base_position_value": current_value,
        "cost_basis_value": cost_basis_value,
        "holding_units": units,
        "unit_source": unit_source,
        "unit_confidence": unit_confidence,
        "effective_nav": effective_nav,
        "official_nav": official_nav,
        "official_nav_date": estimate.get("official_nav_date") or quote.get("as_of_date"),
        "official_nav_freshness_status": estimate.get("official_nav_freshness_status") or quote.get("date_match_type"),
        "official_nav_freshness_label": estimate.get("official_nav_freshness_label") or quote.get("freshness_label"),
        "estimate_nav": estimate_nav,
        "estimate_change_pct": estimate_pct,
        "estimate_freshness_status": estimate.get("estimate_freshness_status"),
        "estimate_freshness_label": estimate.get("estimate_freshness_label"),
        "estimate_freshness_business_day_gap": estimate.get("estimate_freshness_business_day_gap"),
        "proxy_change_pct": proxy_pct,
        "proxy_freshness_status": proxy.get("freshness_status"),
        "proxy_freshness_label": proxy.get("freshness_label"),
        "proxy_freshness_business_day_gap": proxy.get("freshness_business_day_gap"),
        "estimate_policy_allowed": estimate_allowed,
        "proxy_policy_allowed": proxy_allowed,
        "effective_change_pct": effective_pct,
        "estimated_intraday_pnl_pct": round((estimated_intraday_pnl / current_value) * 100, 4) if current_value > 0 else 0.0,
        "estimated_position_value": estimated_position_value,
        "estimated_intraday_pnl_amount": estimated_intraday_pnl,
        "estimated_total_pnl_amount": estimated_total_pnl,
        "estimated_total_return_pct": estimated_total_return_pct,
        "divergence_pct": divergence_pct,
        "freshness_age_business_days": freshness_age_business_days,
        "position_weight_pct": 0.0,
        "anomaly_score": 0.0,
        "confidence": confidence,
        "mode": mode,
        "reason": reason,
        "stale": stale and estimate_pct is not None,
        "estimate_time": estimate.get("estimate_time"),
        "proxy_time": proxy.get("trade_time"),
        "quote_day_change_pct": quote.get("day_change_pct"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build realtime profit snapshot from estimate and proxy sources.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)

    portfolio = load_portfolio(agent_home)
    valuation_config = load_realtime_valuation_config(agent_home)
    estimates = load_json(estimated_nav_path(agent_home, report_date)) if estimated_nav_path(agent_home, report_date).exists() else {"items": []}
    proxies = load_json(intraday_proxy_path(agent_home, report_date)) if intraday_proxy_path(agent_home, report_date).exists() else {"proxies": []}
    quotes = load_json(quote_path(agent_home, report_date)) if quote_path(agent_home, report_date).exists() else {"funds": []}

    estimate_by_code = {item["fund_code"]: item for item in estimates.get("items", [])}
    proxy_by_code = {item["proxy_fund_code"]: item for item in proxies.get("proxies", [])}
    quote_by_code = {item["code"]: item for item in quotes.get("funds", [])}

    items = [build_item(fund, quote_by_code, estimate_by_code, proxy_by_code, valuation_config) for fund in portfolio.get("funds", [])]
    totals = {
        "estimated_intraday_pnl_amount": round(sum(item["estimated_intraday_pnl_amount"] for item in items), 2),
        "estimated_position_value": round(sum(item["estimated_position_value"] for item in items), 2),
        "estimated_total_pnl_amount": round(sum(item["estimated_total_pnl_amount"] for item in items), 2),
    }
    total_position_value = totals["estimated_position_value"] or 0.0
    abs_intraday_total = sum(abs(float(item.get("estimated_intraday_pnl_amount", 0.0) or 0.0)) for item in items) or 1.0
    for item in items:
        position_weight_pct = round((float(item.get("estimated_position_value", 0.0) or 0.0) / total_position_value) * 100, 2) if total_position_value > 0 else 0.0
        impact_score = abs(float(item.get("estimated_intraday_pnl_amount", 0.0) or 0.0)) / abs_intraday_total * 8.0
        divergence_score = float(item.get("divergence_pct", 0.0) or 0.0) * 1.4
        freshness_score = float(item.get("freshness_age_business_days", 0.0) or 0.0) * 2.5
        confidence_penalty = max(0.0, 1.0 - float(item.get("confidence", 0.0) or 0.0)) * 8.0
        stale_penalty = 6.0 if item.get("stale") else 0.0
        item["position_weight_pct"] = position_weight_pct
        item["anomaly_score"] = round(impact_score + divergence_score + freshness_score + confidence_penalty + stale_penalty, 2)

    payload: RealtimeSnapshot = {
        "report_date": report_date,
        "generated_at": timestamp_now(),
        "market_timestamp": build_market_timestamp(report_date, items),
        "realtime_policy": valuation_config.get("realtime", {}),
        "totals": totals,
        "items": items,
    }
    print(dump_json(realtime_monitor_path(agent_home, report_date), payload))


if __name__ == "__main__":
    main()
