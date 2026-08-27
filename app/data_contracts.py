from __future__ import annotations

import hashlib
import json
from datetime import datetime, time
from typing import Any


FRESHNESS_STATUSES = {
    "latest",
    "market_closed",
    "official_nav_pending",
    "proxy_observation",
    "delayed_1d",
    "delayed_multi_day",
    "unavailable",
    "conflict",
}


def stable_payload_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_evidence_ref(item: dict[str, Any], *, default_kind: str = "evidence") -> dict[str, Any]:
    source_path = str(item.get("source_path") or item.get("path") or item.get("source") or "")
    source_record_id = str(item.get("source_record_id") or item.get("news_id") or item.get("id") or "")
    fund_codes = _string_list(item.get("fund_codes"))
    fund_code = str(item.get("fund_code") or item.get("fundCode") or "").strip()
    if fund_code and fund_code not in fund_codes:
        fund_codes.append(fund_code)
    source_kind = str(item.get("source_kind") or item.get("evidence_type") or item.get("source_role") or default_kind)
    available_at = str(item.get("available_at") or item.get("availableFrom") or item.get("retrieved_at") or item.get("generated_at") or "")
    payload_hash = stable_payload_hash(item)
    evidence_id = str(item.get("evidence_id") or item.get("evidenceId") or "").strip()
    if not evidence_id:
        evidence_id = f"evidence_{payload_hash[:16]}"
    return {
        "evidenceId": evidence_id,
        "kind": str(item.get("kind") or item.get("evidence_type") or default_kind),
        "sourceKind": source_kind,
        "sourceRecordId": source_record_id,
        "sourcePath": source_path,
        "subjectId": str(item.get("subject_id") or item.get("entity_id") or fund_code),
        "fundCodes": fund_codes,
        "eventAt": str(item.get("event_at") or item.get("published_at") or item.get("date") or ""),
        "asOfDate": str(item.get("as_of_date") or item.get("report_date") or item.get("date") or ""),
        "availableAt": available_at,
        "retrievedAt": str(item.get("retrieved_at") or item.get("generated_at") or ""),
        "freshnessStatus": str(item.get("freshness_status") or "unknown"),
        "authority": str(item.get("source_tier") or item.get("authority") or "unknown"),
        "confidence": _number(item.get("confidence"), None),
        "payloadHash": payload_hash,
        "tags": _string_list(item.get("tags") or item.get("matched_keywords")),
    }


def normalize_evidence_refs(items: list[dict[str, Any]] | None, *, limit: int = 12) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        reference = build_evidence_ref(item)
        evidence_id = reference["evidenceId"]
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        normalized.append(reference)
        if len(normalized) >= limit:
            break
    return normalized


def build_data_context(
    *,
    selected_date: str,
    portfolio: dict[str, Any] | None,
    realtime: dict[str, Any] | None,
    portfolio_as_of_date: str = "",
    realtime_as_of_date: str = "",
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    portfolio = portfolio or {}
    realtime = realtime or {}
    decision = decision or {}
    items = [item for item in realtime.get("items", []) or [] if isinstance(item, dict)]
    portfolio_date = portfolio_as_of_date or str(portfolio.get("as_of_date") or portfolio.get("_source_date") or "")
    realtime_date = realtime_as_of_date or str(realtime.get("report_date") or "")
    retrieved_at = str(realtime.get("generated_at") or realtime.get("market_timestamp") or "")
    decision_cutoff = str(
        decision.get("decision_cutoff")
        or decision.get("generated_at")
        or decision.get("started_at_shanghai")
        or ""
    )
    session_status = market_session_status(retrieved_at, realtime_date or selected_date)
    freshness_status, freshness_reason = _freshness(items, session_status)
    source_key = str(
        (realtime.get("provider_metadata") or {}).get("provider_name")
        or (realtime.get("realtime_policy") or {}).get("provider")
        or ""
    )
    confidence_values = [_number(item.get("confidence"), None) for item in items]
    available_confidence = [value for value in confidence_values if value is not None]
    modes = _counts(str(item.get("mode") or "unavailable") for item in items)
    stale_count = sum(1 for item in items if bool(item.get("stale")))
    conflict_count = sum(1 for item in items if _has_estimate_proxy_conflict(item))
    snapshot_payload = {
        "selectedDate": selected_date,
        "portfolioAsOfDate": portfolio_date,
        "realtimeAsOfDate": realtime_date,
        "latestRetrievedAt": retrieved_at,
        "sourceKey": source_key,
        "itemCount": len(items),
        "modes": modes,
    }
    payload_hash = stable_payload_hash(snapshot_payload)
    return {
        "snapshotId": f"data_{payload_hash[:16]}",
        "selectedDate": selected_date,
        "portfolioAsOfDate": portfolio_date,
        "realtimeAsOfDate": realtime_date,
        "latestRetrievedAt": retrieved_at,
        "decisionCutoff": decision_cutoff,
        "sessionStatus": session_status,
        "freshnessStatus": freshness_status,
        "freshnessReason": freshness_reason,
        "sourceKey": source_key,
        "sourceAuthority": "derived_realtime_observation",
        "sourceConfidence": round(sum(available_confidence) / len(available_confidence), 4) if available_confidence else None,
        "payloadHash": payload_hash,
        "itemCount": len(items),
        "staleItemCount": stale_count,
        "conflictItemCount": conflict_count,
        "modeCounts": modes,
    }


def market_session_status(timestamp: str, reference_date: str = "") -> str:
    parsed = _parse_datetime(timestamp)
    if parsed is None:
        return "unknown"
    if reference_date and parsed.date().isoformat() != reference_date[:10]:
        return "historical_snapshot"
    clock = parsed.time()
    if time(9, 30) <= clock < time(15, 0):
        return "market_open"
    return "market_closed"


def _freshness(items: list[dict[str, Any]], session_status: str) -> tuple[str, str]:
    if not items:
        return "unavailable", "没有可用的实时观察数据。"
    available = [item for item in items if str(item.get("mode") or "") != "unavailable" and _has_observation(item)]
    if not available:
        return "unavailable", "全部基金缺少可用估值或代理观察。"
    conflicts = [item for item in available if _has_estimate_proxy_conflict(item)]
    if len(conflicts) == len(available):
        return "conflict", "估算净值与代理行情全部存在方向或幅度冲突。"
    stale = [item for item in available if bool(item.get("stale"))]
    if not stale:
        return "latest", "实时观察数据在当前可用窗口内。"
    max_age = max((_business_age(item) for item in stale), default=0)
    if max_age >= 2:
        return "delayed_multi_day", f"{len(stale)} 项观察数据已滞后 {max_age} 个交易日。"
    if max_age >= 1:
        return "delayed_1d", f"{len(stale)} 项观察数据滞后 1 个交易日。"
    modes = {str(item.get("mode") or "") for item in available}
    if session_status == "market_closed":
        return "official_nav_pending", "市场已收盘，当前仅用于观察，等待官方净值确认。"
    if modes and modes.issubset({"proxy_primary", "proxy_fallback"}):
        return "proxy_observation", "当前使用代理行情，仅用于实时观察和风险提示。"
    return "delayed_1d", f"{len(stale)} 项观察数据未达到最新状态。"


def _has_observation(item: dict[str, Any]) -> bool:
    return any(item.get(key) not in (None, "") for key in ("effective_change_pct", "effective_nav", "estimate_change_pct", "proxy_change_pct"))


def _has_estimate_proxy_conflict(item: dict[str, Any]) -> bool:
    estimate = _number(item.get("estimate_change_pct"), None)
    proxy = _number(item.get("proxy_change_pct"), None)
    if estimate is None or proxy is None:
        return False
    return abs(estimate - proxy) >= 1.5


def _business_age(item: dict[str, Any]) -> int:
    value = _number(item.get("freshness_age_business_days"), 0)
    return max(0, int(value or 0))


def _number(value: Any, default: float | None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed else default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _counts(values) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def _parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text.replace("Z", "+00:00"), text):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None
