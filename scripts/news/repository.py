from __future__ import annotations

from typing import Any

from provider_adapters import build_provider_payload, build_provider_result
from common import timestamp_now

from .contracts import ProviderResult
from .event_cluster import cluster_news_items


def build_provider_results(
    *,
    provider_name: str,
    items: list[dict[str, Any]],
    source_health: list[dict[str, Any]],
    retrieved_at: str,
) -> list[dict[str, Any]]:
    """Build one ProviderResult for every observed provider, including disabled or empty sources."""
    by_provider: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        provider = str(item.get("provider") or provider_name or "unknown")
        by_provider.setdefault(provider, []).append(item)
    health_by_provider: dict[str, dict[str, Any]] = {}
    for health in source_health:
        if not isinstance(health, dict):
            continue
        provider = str(health.get("provider") or "")
        if provider:
            health_by_provider[provider] = health
    provider_names = sorted(set(by_provider) | set(health_by_provider) | ({provider_name} if provider_name else set()))
    results = []
    for provider in provider_names:
        health = health_by_provider.get(provider, {})
        records = by_provider.get(provider, [])
        health_status = str(health.get("status") or "")
        stale_count = sum(1 for item in records if bool(item.get("stale", False)))
        freshness = "unavailable" if health_status == "disabled" else "stale" if stale_count else "fresh" if records else "unknown"
        status = health_status or ("warning" if stale_count else "ok")
        metrics = health.get("metrics", {}) if isinstance(health.get("metrics"), dict) else {}
        warnings = [str(item) for item in health.get("notes", []) or [] if str(item)] if status not in {"ok", "disabled"} else []
        results.append(
            ProviderResult(
                provider=provider,
                source_key=str(health.get("source_key") or f"news:{provider}"),
                retrieved_at=str(health.get("latest_retrieved_at") or retrieved_at),
                records=records,
                coverage={
                    "itemCount": len(records),
                    "staleCount": stale_count,
                    "mappedItemCount": int(metrics.get("mapped_item_count", len(records)) or 0),
                    "uniqueItemCount": int(metrics.get("unique_item_count", len(records)) or 0),
                    "sourceRole": str(health.get("source_role") or ""),
                },
                freshness=freshness,
                warnings=warnings,
                retry_count=int(metrics.get("retry_count", 0) or 0),
                latency_ms=_optional_int(metrics.get("latency_ms")),
                status=status,
            ).to_dict()
        )
    return results


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


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
    provider_results = build_provider_results(
        provider_name=provider_name,
        items=normalized_items,
        source_health=source_health,
        retrieved_at=timestamp_now(),
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
        providerResults=provider_results,
    )
    return build_provider_result(
        payload,
        provider_name=provider_name,
        provider_chain=provider_chain,
        freshness_status=freshness,
        confidence="medium" if freshness == "stale" else "high",
    )
