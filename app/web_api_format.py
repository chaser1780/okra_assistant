from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path


def to_jsonable(value):
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    return value


def money(value) -> str:
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def percent(value) -> str:
    try:
        return f"{float(value or 0):.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def series(points) -> list[dict]:
    return [{"date": point.date, "value": point.value} for point in points]


def action_text(action: str) -> str:
    mapping = {
        "buy": "买入",
        "sell": "卖出",
        "scheduled_dca": "计划定投",
        "planned_dca": "计划定投",
        "add": "买入",
        "reduce": "卖出",
        "hold": "观察",
        "locked": "固定持有",
    }
    return mapping.get(str(action or "").strip(), str(action or "记录"))


def markers(markers) -> list[dict]:
    return [
        {
            "date": marker.date,
            "action": action_text(marker.action),
            "amount": marker.amount,
            "amountText": money(marker.amount),
            "fundCode": marker.fund_code,
            "fundName": marker.fund_name,
            "source": "actual",
        }
        for marker in markers
    ]
