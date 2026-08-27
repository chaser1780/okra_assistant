from __future__ import annotations

from pathlib import Path
from typing import Any

from common import load_json


COMPONENT_WEIGHTS = {
    "freshnessRisk": 0.24,
    "dataConflictRisk": 0.22,
    "volatilityRisk": 0.16,
    "crowdingRisk": 0.12,
    "newsRisk": 0.16,
    "executionFrictionRisk": 0.10,
}


def build_risk_breakdowns(
    agent_home: Path,
    *,
    selected_date: str,
    portfolio_items: list[dict[str, Any]],
    realtime_items: list[dict[str, Any]],
    context_funds: list[dict[str, Any]],
    pending_simulation_actions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create a display-only diagnostic decomposition without changing risk rules or actions."""
    realtime_by_code = {str(item.get("fund_code") or ""): item for item in realtime_items if isinstance(item, dict)}
    context_by_code = {str(item.get("fund_code") or ""): item for item in context_funds if isinstance(item, dict)}
    pending_by_code = _pending_by_fund(pending_simulation_actions)
    rows: list[dict[str, Any]] = []
    for item in portfolio_items:
        fund_code = str(item.get("fundCode") or "")
        realtime = realtime_by_code.get(fund_code, {})
        context = context_by_code.get(fund_code, {})
        components, reasons = _components(item, realtime, context, pending_by_code.get(fund_code, []))
        raw_anomaly = _number(realtime.get("anomaly_score"))
        history = _historical_anomaly_scores(agent_home, fund_code, selected_date)
        available = {key: value for key, value in components.items() if value is not None}
        total = _weighted_total(available)
        row = {
            "fundCode": fund_code,
            "fundName": str(item.get("fundName") or fund_code),
            "weightPct": _weight_pct(item.get("weight")),
            **components,
            "totalAnomalyScore": total,
            "observedAnomalyScore": raw_anomaly,
            "historicalPercentile": _percentile(raw_anomaly, history),
            "historicalSampleCount": len(history),
            "dataCoverage": {
                "availableComponentCount": len(available),
                "componentCount": len(COMPONENT_WEIGHTS),
                "isPartial": len(available) < len(COMPONENT_WEIGHTS),
            },
            "reasons": reasons,
            "methodology": "display_only_risk_breakdown.v1",
        }
        rows.append(row)
    rows.sort(key=lambda row: (row["totalAnomalyScore"] is None, -(row["totalAnomalyScore"] or 0), -float(row["weightPct"] or 0)))
    return rows, _summary(rows, selected_date)


def _components(
    portfolio_item: dict[str, Any],
    realtime: dict[str, Any],
    context: dict[str, Any],
    pending_actions: list[dict[str, Any]],
) -> tuple[dict[str, float | None], dict[str, str]]:
    reasons: dict[str, str] = {}
    if not realtime:
        freshness = None
        conflict = None
        volatility = None
        reasons.update(
            {
                "freshnessRisk": "本查看日没有对应的实时观察，不把缺失数据伪装成低风险。",
                "dataConflictRisk": "缺少估算净值与代理行情的可比观测。",
                "volatilityRisk": "缺少当日估算或代理涨跌幅。",
            }
        )
    else:
        age = max(0.0, _number(realtime.get("freshness_age_business_days")) or 0.0)
        stale = bool(realtime.get("stale"))
        confidence = _number(realtime.get("confidence"))
        mode = str(realtime.get("mode") or "")
        freshness = _clamp(age * 25 + (30 if stale else 0) + (max(0.0, 1.0 - confidence) * 25 if confidence is not None else 0))
        reasons["freshnessRisk"] = f"时效 {age:.0f} 个交易日；模式 {mode or '未知'}；{'标记为滞后' if stale else '未标记滞后'}。"
        estimate = _number(realtime.get("estimate_change_pct"))
        proxy = _number(realtime.get("proxy_change_pct"))
        divergence = abs(estimate - proxy) if estimate is not None and proxy is not None else _number(realtime.get("divergence_pct"))
        conflict = _clamp((divergence or 0.0) / 3.0 * 100) if divergence is not None else None
        reasons["dataConflictRisk"] = f"估算与代理差异 {divergence:.2f}% 。" if divergence is not None else "缺少可比较的估算与代理涨跌幅。"
        effective_change = _number(realtime.get("effective_change_pct"))
        volatility = _clamp(abs(effective_change) / 3.0 * 100) if effective_change is not None else None
        reasons["volatilityRisk"] = f"当日有效观察涨跌 {effective_change:+.2f}%（仅作波动代理，不代表历史波动率）。" if effective_change is not None else "缺少当日有效涨跌幅。"

    recent_news = [item for item in context.get("recent_news", []) or [] if isinstance(item, dict)]
    crowding = _crowding_risk(recent_news)
    news = _news_risk(recent_news)
    reasons["crowdingRisk"] = _crowding_reason(recent_news, crowding)
    reasons["newsRisk"] = _news_reason(recent_news, news)
    allow_trade = portfolio_item.get("allowTrade") is not False
    if not allow_trade:
        execution = 100.0
        reasons["executionFrictionRisk"] = "该基金当前标记为不可调仓。"
    elif pending_actions:
        execution = _clamp(len(pending_actions) * 45.0)
        reasons["executionFrictionRisk"] = f"存在 {len(pending_actions)} 笔待确认模拟动作。"
    else:
        execution = 0.0
        reasons["executionFrictionRisk"] = "没有待确认模拟动作。"
    return {
        "freshnessRisk": _round(freshness),
        "dataConflictRisk": _round(conflict),
        "volatilityRisk": _round(volatility),
        "crowdingRisk": _round(crowding),
        "newsRisk": _round(news),
        "executionFrictionRisk": _round(execution),
    }, reasons


def _pending_by_fund(actions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for action in actions:
        if not isinstance(action, dict):
            continue
        for key in ("fund_code", "out_fund_code", "in_fund_code"):
            code = str(action.get(key) or "").strip()
            if code:
                result.setdefault(code, []).append(action)
    return result


def _crowding_risk(news: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for item in news:
        signal = str(item.get("crowding_signal") or "").lower()
        if signal == "crowded":
            values.append(85.0)
        elif signal == "warming":
            values.append(55.0)
        elif signal == "capitulation":
            values.append(65.0)
        virality = _number(item.get("virality_score"))
        if virality is not None:
            values.append(_clamp(virality * 100))
    return max(values, default=0.0)


def _news_risk(news: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for item in news:
        level = str(item.get("risk_level") or "low").lower()
        sentiment = str(item.get("sentiment_label") or item.get("impact") or "").lower()
        evidence_type = str(item.get("evidence_type") or "").lower()
        if level == "high":
            values.append(100.0)
        elif level == "medium":
            values.append(65.0)
        if sentiment == "negative":
            values.append(70.0)
        if evidence_type in {"official_notice", "regulatory_notice", "policy_news"}:
            values.append(55.0)
    return max(values, default=0.0)


def _crowding_reason(news: list[dict[str, Any]], risk: float) -> str:
    if not news:
        return "没有直接关联新闻，不把缺失新闻解释为拥挤风险。"
    signals = sorted({str(item.get("crowding_signal") or "").strip() for item in news if str(item.get("crowding_signal") or "").strip()})
    return f"关联新闻 {len(news)} 条；拥挤信号 {', '.join(signals) if signals else '未标注'}；最高观察分 {risk:.0f}。"


def _news_reason(news: list[dict[str, Any]], risk: float) -> str:
    if not news:
        return "没有直接关联新闻。"
    high = sum(1 for item in news if str(item.get("risk_level") or "").lower() == "high")
    medium = sum(1 for item in news if str(item.get("risk_level") or "").lower() == "medium")
    negative = sum(1 for item in news if str(item.get("sentiment_label") or item.get("impact") or "").lower() == "negative")
    return f"关联新闻 {len(news)} 条；高风险 {high} / 中风险 {medium} / 负向 {negative}；最高观察分 {risk:.0f}。"


def _historical_anomaly_scores(agent_home: Path, fund_code: str, selected_date: str) -> list[float]:
    root = agent_home / "db" / "realtime_monitor"
    if not root.exists() or not fund_code:
        return []
    values: list[float] = []
    for path in sorted(root.glob("*.json")):
        if path.stem[:10] > selected_date[:10]:
            continue
        try:
            payload = load_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        for item in payload.get("items", []) or []:
            if isinstance(item, dict) and str(item.get("fund_code") or "") == fund_code:
                score = _number(item.get("anomaly_score"))
                if score is not None:
                    values.append(score)
                break
    return values


def _percentile(value: float | None, history: list[float]) -> float | None:
    if value is None or len(history) < 5:
        return None
    return round(sum(1 for item in history if item <= value) / len(history) * 100, 2)


def _weighted_total(values: dict[str, float]) -> float | None:
    if not values:
        return None
    weight = sum(COMPONENT_WEIGHTS[key] for key in values)
    if weight <= 0:
        return None
    return round(sum(values[key] * COMPONENT_WEIGHTS[key] for key in values) / weight, 2)


def _summary(rows: list[dict[str, Any]], selected_date: str) -> dict[str, Any]:
    scored = [row for row in rows if row.get("totalAnomalyScore") is not None]
    weighted = sum(float(row.get("totalAnomalyScore") or 0) * float(row.get("weightPct") or 0) for row in scored)
    weight = sum(float(row.get("weightPct") or 0) for row in scored)
    return {
        "selectedDate": selected_date,
        "methodology": "display_only_risk_breakdown.v1",
        "scoredFundCount": len(scored),
        "fundCount": len(rows),
        "weightedTotalAnomalyScore": round(weighted / weight, 2) if weight else None,
        "partialCoverageFundCount": sum(1 for row in rows if (row.get("dataCoverage") or {}).get("isPartial")),
        "historicalPercentileAvailableCount": sum(1 for row in rows if row.get("historicalPercentile") is not None),
    }


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _weight_pct(value: Any) -> float:
    parsed = _number(value) or 0.0
    return round(parsed * 100.0 if abs(parsed) <= 1 else parsed, 4)
