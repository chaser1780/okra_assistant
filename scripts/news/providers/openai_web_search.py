from __future__ import annotations

from typing import Any, Callable


def select_queries(provider_settings: dict[str, Any], query_plan: dict[str, Any]) -> list[dict[str, Any]]:
    include_direct = bool(provider_settings.get("include_direct_queries", True))
    query_buckets: list[tuple[str, list[dict[str, Any]]]] = []
    if include_direct:
        query_buckets.append(("fund_news", list(query_plan.get("direct_queries", []) or [])))
    query_buckets.extend(
        [
            ("theme_news", list(query_plan.get("theme_queries", []) or [])),
            ("market_news", list(query_plan.get("market_queries", []) or [])),
        ]
    )
    max_queries = int(provider_settings.get("max_queries", 6) or 6)
    per_bucket_limit = int(provider_settings.get("max_queries_per_bucket", max(1, max_queries // max(1, len(query_buckets)))) or 1)
    selected: list[dict[str, Any]] = []
    used_queries = 0
    for source_role, queries in query_buckets:
        used_bucket_queries = 0
        for query in queries:
            if used_queries >= max_queries or used_bucket_queries >= per_bucket_limit:
                break
            keyword = str(query.get("keyword", "") or "").strip()
            if len(keyword) < 2:
                continue
            selected.append({**query, "_source_role": source_role})
            used_queries += 1
            used_bucket_queries += 1
    return selected


def tool_candidates(provider_settings: dict[str, Any]) -> list[str]:
    configured = provider_settings.get("tool_types", provider_settings.get("tool_type", "web_search"))
    if isinstance(configured, str):
        values = [item.strip() for item in configured.split(",") if item.strip()]
    else:
        values = [str(item).strip() for item in configured or [] if str(item).strip()]
    if not values:
        values = ["web_search"]
    for fallback in ("web_search", "web_search_preview"):
        if fallback not in values:
            values.append(fallback)
    return values


def fetch_web_search_news(
    *,
    agent_home: Any,
    config: dict[str, Any],
    provider_settings: dict[str, Any],
    report_date: str,
    query_plan: dict[str, Any],
    build_payload: Callable[[dict[str, Any], dict[str, Any], list[dict[str, Any]], str, str], dict[str, Any]],
    call: Callable[..., dict[str, Any]],
    parse_output: Callable[[str], list[dict[str, Any]]],
    extract_citations: Callable[[dict[str, Any]], set[str]],
    normalize_item: Callable[..., dict[str, Any] | None],
    dedupe_items: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]],
    build_health: Callable[..., dict[str, Any]],
    should_stop_retry: Callable[[Exception], bool],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the optional web-search provider while keeping response citations mandatory."""
    if not bool(provider_settings.get("enabled", False)):
        return [], build_health(
            source_key="openai_web_search:openai_web_search",
            source_role="theme_news",
            provider="openai_web_search",
            configured=False,
            status="disabled",
            notes=["openai web search provider disabled"],
        )
    queries = select_queries(provider_settings, query_plan)
    if not queries:
        return [], build_health(
            source_key="openai_web_search:openai_web_search",
            source_role="theme_news",
            provider="openai_web_search",
            configured=True,
            status="warning",
            notes=["no eligible web search queries"],
            warning_count=1,
        )

    timeout_seconds = int(provider_settings.get("timeout_seconds", 90) or 90)
    max_attempts = int(provider_settings.get("max_attempts", 1) or 1)
    errors: list[str] = []
    raw_rows: list[dict[str, Any]] = []
    citation_urls: set[str] = set()
    selected_tool = ""
    for tool_type in tool_candidates(provider_settings):
        payload = build_payload(config, provider_settings, queries, report_date, tool_type)
        try:
            response = call(
                config,
                payload,
                request_kind="openai_web_search_news",
                max_attempts=max_attempts,
                agent_home=agent_home,
                timeout=(10, timeout_seconds),
            )
            raw_rows = parse_output(str(response.get("output_text", "") or ""))
            citation_urls = extract_citations(response)
            selected_tool = tool_type
            break
        except Exception as exc:
            errors.append(f"{tool_type}: {exc}")
            if should_stop_retry(exc):
                break

    items = []
    for raw_item in raw_rows:
        normalized = normalize_item(raw_item, report_date=report_date, citation_urls=citation_urls)
        if normalized:
            items.append(normalized)
    dedup_window_hours = int(provider_settings.get("dedup_window_hours", 12) or 12)
    items, dedup_stats = dedupe_items(items, dedup_window_hours=dedup_window_hours)
    status = "ok" if items and not errors else "warning"
    notes = [
        f"queries_used={len(queries)}",
        f"raw_item_count={len(raw_rows)}",
        f"mapped_item_count={dedup_stats['mapped_item_count']}",
        f"unique_item_count={dedup_stats['unique_item_count']}",
        f"selected_tool={selected_tool or 'none'}",
        f"citation_url_count={len(citation_urls)}",
        f"unverified_item_count={max(0, len(raw_rows) - len(items))}",
        *errors[:4],
    ]
    return items, build_health(
        source_key="openai_web_search:openai_web_search",
        source_role="theme_news",
        provider="openai_web_search",
        items=items,
        configured=True,
        status=status,
        notes=notes,
        error_count=len(errors),
        warning_count=1 if status == "warning" else 0,
        metrics={
            "queries_used": len(queries),
            "raw_item_count": len(raw_rows),
            "mapped_item_count": dedup_stats["mapped_item_count"],
            "unique_item_count": dedup_stats["unique_item_count"],
            "duplicate_item_count": dedup_stats["duplicate_item_count"],
            "dedup_drop_count": dedup_stats["dedup_drop_count"],
            "stale_item_count": sum(1 for item in items if bool(item.get("stale", False))),
            "selected_tool": selected_tool,
            "citation_url_count": len(citation_urls),
            "unverified_item_count": max(0, len(raw_rows) - len(items)),
        },
    )
