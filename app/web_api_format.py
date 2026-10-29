from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from pathlib import Path


def _valid_sizing_ratio(value):
    """Return 0..1 ratio or None. Reject NaN/inf/negative/>1/bool/non-numeric/string. Preserve exact frozen value."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return None
    if isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    if num < 0.0 or num > 1.0:
        return None
    return num


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
    if value in (None, ""):
        return "不可用"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "不可用"


def percent(value) -> str:
    if value in (None, ""):
        return "不可用"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "不可用"


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


# --- simulation_v2 advice adapter (contract §1) -------------------------------
# Frontend DTO row additions (camelCase), additive only:
#   schemaVersion           "simulation_v2" | "legacy"
#   sizeTier                "small" | "medium" | "large" | "none" | "legacy"
#   sizeRatio               float 0.1/0.25/0.5 (v2) | null (legacy)
#   sizingBasis             "fund_position_value" (v2) | "" (legacy)
#   basisPositionValue      number | null
#   basisSnapshotSha256     str
#   decisionAt              ISO8601 offset datetime, may be ""
#   horizon                 "unspecified" default; never fabricate a financial horizon
#   evidenceQuality         "high" | "medium" | "low" | "unavailable"
# legacy rows keep their legacy amount fields untouched and are tagged
# sizeTier="legacy" -- the adapter must NOT infer a tier from legacy amounts.
ALLOWED_SIZE_TIERS = {"small", "medium", "large", "none"}
ALLOWED_EVIDENCE_QUALITY = {"high", "medium", "low", "unavailable"}
ALLOWED_HORIZONS = {"unspecified", "short", "medium", "long", "intraday", "swing"}


def adapt_simulation_advice_row(item: dict) -> dict:
    """Map internal simulation_v2 snake advice fields to frontend camel fields."""
    schema = str(item.get("schema_version", "") or "")
    if schema == "simulation_v2":
        tier = str(item.get("size_tier", "") or "none")
        tier = tier if tier in ALLOWED_SIZE_TIERS else "none"
        size_ratio = _valid_sizing_ratio(item.get("size_ratio"))
        if tier == "none":
            size_ratio = None  # no manual sizing basis; close ratio to null
        quality = str(item.get("evidence_quality", "") or "unavailable")
        quality = quality if quality in ALLOWED_EVIDENCE_QUALITY else "unavailable"
        horizon = str(item.get("horizon", "") or "unspecified")
        horizon = horizon if horizon in ALLOWED_HORIZONS else "unspecified"
        return {
            "schemaVersion": "simulation_v2",
            "sizeTier": tier,
            "sizeRatio": size_ratio,
            "sizingBasis": str(item.get("sizing_basis", "") or "fund_position_value"),
            "basisPositionValue": item.get("basis_position_value"),
            "basisSnapshotSha256": str(item.get("basis_snapshot_sha256", "") or ""),
            "decisionAt": str(item.get("decision_at", "") or ""),
            "horizon": horizon,
            "evidenceQuality": quality,
        }
    # legacy advice: no new fields, no fabricated tier.
    return {
        "schemaVersion": "legacy",
        "sizeTier": "legacy",
        "sizeRatio": None,
        "sizingBasis": "",
        "basisPositionValue": None,
        "basisSnapshotSha256": "",
        "decisionAt": "",
        "horizon": "unspecified",
        "evidenceQuality": "unavailable",
    }
