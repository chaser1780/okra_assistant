from __future__ import annotations

from typing import Any

from provider_adapters import build_provider_payload, build_provider_result
from common import timestamp_now

from .contracts import ProviderResult
from .event_cluster import cluster_news_items


def build_news_repository_payload(
    *,
    report_date: str,
    provider_name: str,
    provider_chain: list[str],
    items: list[dict[str, Any]],
    source_health: list[dict[str, Any]],
    query_plan: dict[str, Any],
    sentiment_queries: list[dict[str, Any]],
    dedup_summary: dict[str, Any],
    global_dedup_summary: dict[str, Any],
    classification_summary: dict[str, Any],
) -> dict[str, Any]:
    normalized_items, events, event_summary = cluster_news_items(items)
    normalized_items.sort(key=lambda item: item.get("published_at", ""), reverse=True)
    freshness = "stale" if any(item.get("stale", False) for item in normalized_items) else "fresh"
    provider_result = ProviderResult(
        provider=provider_name,
        source_key=f"news:{provider_name}",
        retrieved_at=timestamp_now(),
        records=normalized_items,
        coverage={
            "mappedItemCount": len(normalized_items),
            "eventCount": event_summary["event_count"],
            "sourceHealthCount": len(source_health),
        },
        freshness=freshness,
        warnings=[str(item.get("source_key", "")) for item in source_health if str(item.get("status", "")) not in {"ok", "disabled"}],
        status="warning" if freshness == "stale" else "ok",
    )
    payload = build_provider_payload(
        report_date,
        provider_name,
        "items",
        normalized_items,
        source_health=source_health,
        query_plan=query_plan,
        sentiment_queries=sentiment_queries,
        dedup_summary=dedup_summary,
        global_dedup_summary=global_dedup_summary,
        classification_summary=classification_summary,
        events=events,
        event_summary=event_summary,
        providerResults=[provider_result.to_dict()],
    )
    return build_provider_result(
        payload,
        provider_name=provider_name,
        provider_chain=provider_chain,
        freshness_status=freshness,
        confidence="medium" if freshness == "stale" else "high",
    )
