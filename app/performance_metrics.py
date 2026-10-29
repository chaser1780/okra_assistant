from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class CashFlow:
    date: str
    amount: float
    timing: str


def calculate_portfolio_performance(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Return cash-flow-adjusted performance using only snapshot-declared external flows.

    In virtual-external-flow mode, upstream writes the signed external principal net flow
    for buys/sells; dividends, fees and internal conversions are never external principal.
    Legacy snapshots without a flow map fall back to the single stored value.
    """
    ordered = _ordered_snapshots(snapshots)
    if len(ordered) < 2:
        return _unavailable("需要至少两个组合快照。", ordered)
    try:
        flows = _external_cashflows(ordered)
    except _CorruptFlowMap:
        return _unavailable("组合快照的外部现金流映射存在非有限数值，不回退单值假精确。", ordered)
    if not flows:
        return _unavailable("组合快照未记录显式外部入金/出金，不以资产变化估算投资收益。", ordered)
    if any(flow.timing not in {"start", "end"} for flow in flows):
        return _unavailable("外部现金流缺少发生时点，无法计算现金流调整收益。", ordered, flows)
    twr = _twr(ordered, flows)
    if twr is None:
        return _unavailable("现金流调整后的时间加权收益无法计算。", ordered, flows)
    mwr = _xirr(ordered, flows)
    adjusted_drawdown = _cashflow_adjusted_drawdown(ordered, flows)
    return {
        "status": "available",
        "methodology": "explicit_external_cashflow",
        "periodStart": ordered[0]["date"],
        "periodEnd": ordered[-1]["date"],
        "cashflowCount": len(flows),
        "twr": {"available": True, "returnPct": round(twr * 100.0, 4)},
        "mwr": {"available": mwr is not None, "returnPct": round(mwr * 100.0, 4) if mwr is not None else None},
        "cashflowAdjustedDrawdown": adjusted_drawdown,
        "reason": "仅使用快照声明的外部本金净流；虚拟资金模式的买卖由上游写入，分红/费用/换仓等内部项不额外当本金。",
    }


def _ordered_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in snapshots:
        try:
            value = float(item.get("total_value"))
        except (TypeError, ValueError):
            continue
        date_text = str(item.get("date") or item.get("as_of_date") or "")[:10]
        if _date(date_text) is None or not isfinite(value):
            continue
        rows.append({"date": date_text, "total_value": value, "payload": item})
    return sorted(rows, key=lambda item: item["date"])


class _CorruptFlowMap(Exception):
    """Raised when an external_flows_by_date map exists but carries a non-finite value."""


def _finite_flow(value: Any) -> float | None:
    """Return a finite float, rejecting bool/non-numeric/NaN/inf; None if unusable."""
    if isinstance(value, bool):
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if isfinite(amount) else None


def _external_cashflows(snapshots: list[dict[str, Any]]) -> list[CashFlow]:
    result = []
    for snapshot in snapshots:
        payload = snapshot["payload"]
        has_map = "external_flows_by_date" in payload
        flow_map = payload.get("external_flows_by_date")
        if has_map and flow_map is not None:
            # Authoritative per-day map. A non-dict container is corrupt data -> no scalar
            # fallback. A day absent from the map simply has no flow; a day present but
            # non-finite is also corrupt.
            if not isinstance(flow_map, dict):
                raise _CorruptFlowMap
            if snapshot["date"] not in flow_map:
                continue
            amount = _finite_flow(flow_map.get(snapshot["date"]))
            if amount is None:
                raise _CorruptFlowMap
        else:
            # No map field (legacy / explicit null): use the stored single value.
            raw = payload.get("external_cashflow")
            amount = _finite_flow(raw) if raw not in (None, "") else None
            if amount is None:
                continue
        if amount:
            result.append(CashFlow(snapshot["date"], amount, str(payload.get("external_cashflow_timing") or "").lower()))
    return result


def _twr(snapshots: list[dict[str, Any]], flows: list[CashFlow]) -> float | None:
    flow_by_date = {flow.date: flow for flow in flows}
    multiplier = 1.0
    for previous, current in zip(snapshots, snapshots[1:]):
        flow = flow_by_date.get(current["date"])
        denominator = previous["total_value"] + (flow.amount if flow and flow.timing == "start" else 0.0)
        numerator = current["total_value"] - (flow.amount if flow and flow.timing == "end" else 0.0)
        if denominator <= 0:
            return None
        multiplier *= numerator / denominator
    return multiplier - 1.0


def _xirr(snapshots: list[dict[str, Any]], flows: list[CashFlow]) -> float | None:
    start_date = _date(snapshots[0]["date"])
    end_date = _date(snapshots[-1]["date"])
    if not start_date or not end_date:
        return None
    values = [(start_date, -snapshots[0]["total_value"])]
    values.extend((_date(flow.date), -flow.amount) for flow in flows if _date(flow.date))
    values.append((end_date, snapshots[-1]["total_value"]))
    if not any(value < 0 for _day, value in values) or not any(value > 0 for _day, value in values):
        return None
    low, high = -0.999, 10.0
    low_value, high_value = _npv(low, start_date, values), _npv(high, start_date, values)
    # Very short periods can imply a numerically large annualized XIRR. Expand
    # the bracket before declaring the calculation unavailable.
    for _ in range(60):
        if low_value * high_value <= 0:
            break
        high *= 2
        high_value = _npv(high, start_date, values)
    else:
        return None
    for _ in range(100):
        middle = (low + high) / 2
        value = _npv(middle, start_date, values)
        if abs(value) < 1e-7:
            return middle
        if low_value * value <= 0:
            high, high_value = middle, value
        else:
            low, low_value = middle, value
    return (low + high) / 2


def _cashflow_adjusted_drawdown(snapshots: list[dict[str, Any]], flows: list[CashFlow]) -> dict[str, Any]:
    """Drawdown of a time-weighted unit series, not of raw assets after deposits or withdrawals."""
    flow_by_date = {flow.date: flow for flow in flows}
    unit_value = 1.0
    peak = 1.0
    points = [{"date": snapshots[0]["date"], "value": 0.0}]
    for previous, current in zip(snapshots, snapshots[1:]):
        flow = flow_by_date.get(current["date"])
        denominator = previous["total_value"] + (flow.amount if flow and flow.timing == "start" else 0.0)
        numerator = current["total_value"] - (flow.amount if flow and flow.timing == "end" else 0.0)
        if denominator <= 0:
            return {"available": False, "currentPct": None, "maxPct": None, "series": []}
        unit_value *= numerator / denominator
        peak = max(peak, unit_value)
        drawdown = ((unit_value / peak) - 1.0) * 100.0 if peak else 0.0
        points.append({"date": current["date"], "value": round(drawdown, 4)})
    values = [point["value"] for point in points]
    return {
        "available": True,
        "currentPct": points[-1]["value"] if points else None,
        "maxPct": min(values) if values else None,
        "series": points,
    }


def _npv(rate: float, start_date: date, values: list[tuple[date, float]]) -> float:
    return sum(value / ((1.0 + rate) ** ((day - start_date).days / 365.0)) for day, value in values)


def _unavailable(reason: str, snapshots: list[dict[str, Any]], flows: list[CashFlow] | None = None) -> dict[str, Any]:
    return {
        "status": "insufficient_cashflow_data",
        "methodology": "explicit_external_cashflow_required",
        "periodStart": snapshots[0]["date"] if snapshots else "",
        "periodEnd": snapshots[-1]["date"] if snapshots else "",
        "cashflowCount": len(flows or []),
        "twr": {"available": False, "returnPct": None},
        "mwr": {"available": False, "returnPct": None},
        "cashflowAdjustedDrawdown": {"available": False, "currentPct": None, "maxPct": None, "series": []},
        "reason": reason,
    }


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
