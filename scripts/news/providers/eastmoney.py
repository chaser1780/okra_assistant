from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any, Callable


EASTMONEY_SEARCH_API = "https://search-api-web.eastmoney.com/search/jsonp"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36"


def search_jsonp(
    keyword: str,
    *,
    page_size: int,
    timeout_seconds: int,
    parse_jsonp: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    callback = f"jQuery{int(time.time() * 1000)}"
    payload = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "<em>",
                "postTag": "</em>",
            }
        },
    }
    encoded = urllib.parse.quote(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), safe="")
    url = f"{EASTMONEY_SEARCH_API}?cb={callback}&param={encoded}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": f"https://so.eastmoney.com/news/s?keyword={urllib.parse.quote(keyword)}",
            "Accept": "application/json,text/javascript,*/*;q=0.01",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8", errors="replace")
    return parse_jsonp(body)


def fetch_query_news(
    provider_settings: dict[str, Any],
    report_date: str,
    query_plan: dict[str, Any],
    *,
    default_timeout_seconds: int,
    search: Callable[..., dict[str, Any]],
    extract_items: Callable[[dict[str, Any]], list[dict[str, Any]]],
    query_matches: Callable[[str, dict[str, Any]], bool],
    normalize_item: Callable[..., list[dict[str, Any]]],
    dedupe_items: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]],
    build_health: Callable[..., dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run configured Eastmoney query buckets and report source health without changing item contracts."""
    if not bool(provider_settings.get("enabled", True)):
        return [], build_health(
            source_key="query_news:eastmoney_search_api",
            source_role="theme_news",
            provider="eastmoney_search_api",
            configured=False,
            status="disabled",
            notes=["query_news provider disabled"],
        )
    timeout_seconds = int(provider_settings.get("timeout_seconds", default_timeout_seconds) or default_timeout_seconds)
    page_size = int(provider_settings.get("results_per_query", 3) or 3)
    max_queries = int(provider_settings.get("max_queries", 10) or 10)
    query_buckets: list[tuple[str, list[dict[str, Any]]]] = []
    if bool(provider_settings.get("include_direct_queries", True)):
        query_buckets.append(("theme_news", list(query_plan.get("direct_queries", []) or [])))
    query_buckets.extend(
        [
            ("theme_news", list(query_plan.get("theme_queries", []) or [])),
            ("market_news", list(query_plan.get("market_queries", []) or [])),
        ]
    )
    per_bucket_limit = int(provider_settings.get("max_queries_per_bucket", max(1, max_queries // max(1, len(query_buckets)))) or 1)
    errors: list[str] = []
    raw_rows: list[dict[str, Any]] = []
    raw_article_keys: set[str] = set()
    used_queries = 0
    skipped_queries = 0
    for source_role, queries in query_buckets:
        used_bucket_queries = 0
        for query in queries:
            if used_queries >= max_queries or used_bucket_queries >= per_bucket_limit:
                break
            keyword = str(query.get("keyword", "") or "").strip()
            if len(keyword) < 2:
                skipped_queries += 1
                continue
            used_queries += 1
            used_bucket_queries += 1
            try:
                payload = search(keyword, page_size=page_size, timeout_seconds=timeout_seconds)
                extracted = [item for item in extract_items(payload) if query_matches(keyword, item)]
                for raw_item in extracted[:page_size]:
                    if raw_item.get("url"):
                        raw_article_keys.add(str(raw_item.get("url")))
                    raw_rows.extend(normalize_item(raw_item, query, source_role=source_role, report_date=report_date))
            except Exception as exc:
                errors.append(f"{keyword}: {exc}")

    dedup_window_hours = int(provider_settings.get("dedup_window_hours", 12) or 12)
    items, dedup_stats = dedupe_items(raw_rows, dedup_window_hours=dedup_window_hours)
    notes = [
        f"queries_used={used_queries}",
        f"queries_skipped={skipped_queries}",
        f"raw_article_count={len(raw_article_keys)}",
        f"unique_article_count={dedup_stats['unique_item_count']}",
        f"mapped_item_count={dedup_stats['mapped_item_count']}",
        f"dedup_drop_count={dedup_stats['dedup_drop_count']}",
        f"max_queries_per_bucket={per_bucket_limit}",
        f"results_per_query={page_size}",
        *errors[:6],
    ]
    return items, build_health(
        source_key="query_news:eastmoney_search_api",
        source_role="theme_news",
        provider="eastmoney_search_api",
        items=items,
        status="warning" if errors else "ok",
        notes=notes,
        error_count=len(errors),
        warning_count=1 if errors else 0,
        metrics={
            "queries_used": used_queries,
            "queries_skipped": skipped_queries,
            "raw_article_count": len(raw_article_keys),
            "unique_article_count": dedup_stats["unique_item_count"],
            "mapped_item_count": dedup_stats["mapped_item_count"],
            "duplicate_item_count": dedup_stats["duplicate_item_count"],
            "dedup_drop_count": dedup_stats["dedup_drop_count"],
            "stale_item_count": sum(1 for item in items if bool(item.get("stale", False))),
        },
    )
