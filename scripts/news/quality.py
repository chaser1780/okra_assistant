from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Callable


def compute_heat_metrics(items: list[dict[str, Any]], *, parse_datetime: Callable[[str], datetime | None]) -> None:
    if not items:
        return
    topic_counter: Counter[str] = Counter()
    source_counter: defaultdict[str, set[str]] = defaultdict(set)
    duplicate_counter: Counter[str] = Counter()
    for item in items:
        canonical_key = str(item.get("canonical_url", "") or item.get("content_hash", "") or item.get("title", ""))
        duplicate_counter[canonical_key] += 1
        for keyword in item.get("matched_keywords", []) or []: topic_counter[str(keyword)] += 1
        source_counter[canonical_key].add(str(item.get("source_name", "") or item.get("provider", "")))
    published_times = [parsed for item in items if (parsed := parse_datetime(str(item.get("published_at", "") or ""))) is not None]
    now = max(published_times, default=None)
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in items:
        canonical_key = str(item.get("canonical_url", "") or item.get("content_hash", "") or item.get("title", ""))
        topic_hits = sum(topic_counter[str(keyword)] for keyword in item.get("matched_keywords", []) or [])
        published_dt = parse_datetime(str(item.get("published_at", "") or ""))
        recency_bonus = max(0.0, 1.0 - min(max(0.0, (now - published_dt).total_seconds() / 3600.0), 24.0) / 24.0) if now and published_dt else 0.0
        query_bonus = 0.35 if str(item.get("query_type", "")) == "direct" else (0.22 if str(item.get("query_type", "")) == "theme" else 0.15)
        heat_score = round(min(1.0, 0.15 + recency_bonus * 0.3 + query_bonus + min(1.0, (duplicate_counter[canonical_key] - 1) * 0.2) + min(1.0, len(source_counter[canonical_key]) * 0.25) + min(1.0, topic_hits * 0.08)), 4)
        item["heat_score"] = heat_score
        item["virality_score"] = max(float(item.get("virality_score", 0.0) or 0.0), heat_score)
        sentiment_score = float(item.get("sentiment_score", 0.0) or 0.0)
        item["crowding_signal"] = "crowded" if heat_score >= 0.75 and sentiment_score > 0.2 else "capitulation" if heat_score >= 0.75 and sentiment_score < -0.2 else "warming" if heat_score >= 0.45 else str(item.get("crowding_signal", "") or "neutral")
        scored.append((heat_score, item))
    for rank, (_score, item) in enumerate(sorted(scored, key=lambda row: (row[0], row[1].get("published_at", "")), reverse=True), start=1):
        item["heat_rank"] = rank


def dedupe_news_items(items: list[dict[str, Any]], *, dedup_window_hours: int, enrich_item: Callable[..., dict[str, Any]], content_hash: Callable[[str, str, str], str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    canonical_seen: set[str] = set()
    mapped_seen: set[tuple[str, str]] = set()
    duplicate_item_count = dedup_drop_count = 0
    for item in sorted(items, key=lambda row: row.get("published_at", ""), reverse=True):
        enriched = enrich_item(item, query_type=str(item.get("query_type", "") or ""), matched_keywords=list(item.get("matched_keywords", []) or []))
        canonical_key = str(enriched.get("canonical_url", "") or content_hash(str(enriched.get("title", "")), str(enriched.get("summary", "")), ""))
        mapped_key = (str(enriched.get("code", "") or ""), canonical_key)
        if mapped_key in mapped_seen:
            dedup_drop_count += 1
            continue
        if canonical_key in canonical_seen: duplicate_item_count += 1
        canonical_seen.add(canonical_key)
        mapped_seen.add(mapped_key)
        deduped.append(enriched)
    return deduped, {"mapped_item_count": len(deduped), "unique_item_count": len(canonical_seen), "duplicate_item_count": duplicate_item_count, "dedup_drop_count": dedup_drop_count, "dedup_window_hours": dedup_window_hours}


def news_dedup_summary(items: list[dict[str, Any]], *, dedup_window_hours: int, enrich_item: Callable[..., dict[str, Any]], content_hash: Callable[[str, str, str], str]) -> dict[str, Any]:
    _items, summary = dedupe_news_items(items, dedup_window_hours=dedup_window_hours, enrich_item=enrich_item, content_hash=content_hash)
    summary["mapped_item_count"] = len({(str(item.get("code", "") or ""), str(item.get("canonical_url", "") or item.get("content_hash", "") or content_hash(str(item.get("title", "")), str(item.get("summary", "")), ""))) for item in items})
    return summary
