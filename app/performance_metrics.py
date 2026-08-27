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
    """Only calculate returns when snapshots declare external cash flows.

    Internal fund trades and cash-pool transfers are never external cash flows.
    """
    ordered = _ordered_snapshots(snapshots)
    if len(ordered) < 2:
        return _unavailable("需要至少两个组合快照。", ordered)
    flows = _external_cashflows(ordered)
    if not flows:
        return _unavailable("组合快照未记录显式外部入金/出金，不以资产变化估算投资收益。", ordered)
    if any(flow.timing not in {"start", "end"} for flow in flows):
        return _unavailable("外部现金流缺少发生时点，无法计算现金流调整收益。", ordered, flows)
    twr = _twr(ordered, flows)
    if twr is None:
        return _unavailable("现金流调整后的时间加权收益无法计算。", ordered, flows)
    mwr = _xirr(ordered, flows)
    return {
        "status": "available",
        "methodology": "explicit_external_cashflow",
        "periodStart": ordered[0]["date"],
        "periodEnd": ordered[-1]["date"],
        "cashflowCount": len(flows),
        "twr": {"available": True, "returnPct": round(twr * 100.0, 4)},
        "mwr": {"available": mwr is not None, "returnPct": round(mwr * 100.0, 4) if mwr is not None else None},
        "reason": "仅使用显式外部现金流；基金买卖、定投、换仓和现金池内部转移不计为外部现金流。",
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


def _external_cashflows(snapshots: list[dict[str, Any]]) -> list[CashFlow]:
    result = []
    for snapshot in snapshots:
        raw = snapshot["payload"].get("external_cashflow")
        if raw in (None, ""):
            continue
        try:
            amount = float(raw)
        except (TypeError, ValueError):
            continue
        if amount:
            result.append(CashFlow(snapshot["date"], amount, str(snapshot["payload"].get("external_cashflow_timing") or "").lower()))
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
        "reason": reason,
    }


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
