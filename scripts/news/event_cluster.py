from __future__ import annotations

import hashlib
import re
import urllib.parse
from collections import Counter
from datetime import datetime
from typing import Any


AUTHORITY_SCORES = {
    "official_policy": 1.0,
    "official_notice": 0.95,
    "state_media": 0.82,
    "mainstream_media": 0.76,
    "financial_media": 0.68,
    "market_media": 0.62,
    "self_media": 0.42,
    "social_post": 0.28,
    "social_short_video": 0.2,
}


def cluster_news_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Attach stable event ids without changing per-fund news mappings."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    enriched: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        event_id = event_id_for(item)
        row = {**item, "event_id": event_id}
        enriched.append(row)
        grouped.setdefault(event_id, []).append(row)
    events = [_event_from_group(event_id, rows) for event_id, rows in grouped.items()]
    events.sort(key=lambda item: (float(item.get("priority_score", 0.0) or 0.0), str(item.get("published_at", ""))), reverse=True)
    summary = {
        "event_count": len(events),
        "mapped_item_count": len(enriched),
        "multi_fund_event_count": sum(1 for event in events if len(event["fund_codes"]) > 1),
        "multi_source_event_count": sum(1 for event in events if event["source_count"] > 1),
    }
    return enriched, events, summary


def event_id_for(item: dict[str, Any]) -> str:
    canonical_url = _canonical_url(str(item.get("canonical_url") or item.get("source_url") or item.get("url") or ""))
    title = _normalized_title(str(item.get("title") or ""))
    published_bucket = _time_bucket(str(item.get("published_at") or item.get("as_of") or ""))
    seed = canonical_url or f"{title}|{published_bucket}"
    return f"event_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"


def _event_from_group(event_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(rows, key=_row_rank, reverse=True)
    representative = ranked[0]
    fund_codes = _unique_text(row.get("code") or row.get("fund_code") for row in rows)
    providers = _unique_text(row.get("provider") or row.get("source_name") or row.get("source_key") for row in rows)
    source_tiers = _unique_text(row.get("source_tier") for row in rows)
    freshness = _freshness_status(rows)
    authority = max((authority_score(row.get("source_tier")) for row in rows), default=0.0)
    risk_level = _highest_risk(rows)
    sentiment = _weighted_sentiment(rows)
    heat = max((float(row.get("heat_score", 0.0) or 0.0) for row in rows), default=0.0)
    priority = round(heat * 0.45 + authority * 0.25 + _risk_weight(risk_level) * 0.2 + min(1.0, len(fund_codes) / 4) * 0.1, 4)
    return {
        "event_id": event_id,
        "title": str(representative.get("title") or "暂无标题"),
        "summary": str(representative.get("summary") or representative.get("title") or ""),
        "canonical_url": str(representative.get("canonical_url") or representative.get("source_url") or representative.get("url") or ""),
        "published_at": max((str(row.get("published_at") or "") for row in rows), default=""),
        "event_type": str(representative.get("evidence_type") or representative.get("source_role") or "theme_news"),
        "risk_level": risk_level,
        "sentiment_score": sentiment,
        "sentiment_label": _sentiment_label(sentiment),
        "heat_score": round(heat, 4),
        "priority_score": priority,
        "fund_codes": fund_codes,
        "providers": providers,
        "source_tiers": source_tiers,
        "source_count": len(providers),
        "mapped_item_count": len(rows),
        "source_authority": round(authority, 4),
        "freshness_status": freshness,
        "unverified": any(bool(row.get("unverified", False)) for row in rows),
        "news_ids": _unique_text(row.get("news_id") or row.get("id") for row in rows),
    }


def authority_score(value: Any) -> float:
    return AUTHORITY_SCORES.get(str(value or "").strip(), 0.35)


def _row_rank(row: dict[str, Any]) -> tuple[float, float, str]:
    return (
        authority_score(row.get("source_tier")),
        float(row.get("heat_score", 0.0) or 0.0),
        str(row.get("published_at") or ""),
    )


def _freshness_status(rows: list[dict[str, Any]]) -> str:
    values = {str(row.get("freshness_status") or "") for row in rows}
    if "future" in values:
        return "future"
    if "stale" in values:
        return "stale"
    if "fresh" in values:
        return "fresh"
    return "unknown"


def _highest_risk(rows: list[dict[str, Any]]) -> str:
    ranks = {"high": 3, "medium": 2, "low": 1}
    return max((str(row.get("risk_level") or "low") for row in rows), key=lambda value: ranks.get(value, 0), default="low")


def _weighted_sentiment(rows: list[dict[str, Any]]) -> float:
    weighted = []
    for row in rows:
        try:
            score = float(row.get("sentiment_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        weighted.append((score, max(0.1, authority_score(row.get("source_tier")))))
    total_weight = sum(weight for _score, weight in weighted)
    return round(sum(score * weight for score, weight in weighted) / total_weight, 4) if total_weight else 0.0


def _risk_weight(value: str) -> float:
    return {"high": 1.0, "medium": 0.58, "low": 0.18}.get(value, 0.0)


def _sentiment_label(value: float) -> str:
    if value >= 0.15:
        return "positive"
    if value <= -0.15:
        return "negative"
    return "neutral"


def _canonical_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    try:
        parsed = urllib.parse.urlparse(raw)
    except ValueError:
        return raw
    if not parsed.scheme or not parsed.netloc:
        return raw
    query = [(key, val) for key, val in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if not key.lower().startswith("utm_")]
    return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", urllib.parse.urlencode(sorted(query)), ""))


def _normalized_title(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def _time_bucket(value: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]
    return parsed.replace(hour=(parsed.hour // 6) * 6, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def _unique_text(values) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result
