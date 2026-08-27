from __future__ import annotations

from typing import Any, Callable


SZSE_REPORT_ENDPOINTS = {
    "reg:szse_inquiry": "https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=main_wxhj",
    "reg:szse_supervision_measure": "https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1800_jgxxgk",
    "reg:szse_disciplinary_action": "https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1800_jgxxgk_cf",
}


def fetch_regulatory_news(
    provider_settings: dict[str, Any],
    report_date: str,
    *,
    fetch_html: Callable[..., str],
    fetch_json: Callable[..., str],
    parse_sse: Callable[[str, str, str], list[dict[str, Any]]],
    parse_amac: Callable[[str, str, str], list[dict[str, Any]]],
    parse_szse_page: Callable[[str, str, str], list[dict[str, Any]]],
    parse_szse_report: Callable[[str, str, str], list[dict[str, Any]]],
    normalize_item: Callable[..., dict[str, Any] | None],
    build_health: Callable[..., dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch official regulatory sources while preserving per-source health and fallback semantics."""
    if not bool(provider_settings.get("enabled", False)):
        return [], []
    timeout_seconds = int(provider_settings.get("timeout_seconds", 15) or 15)
    items: list[dict[str, Any]] = []
    health_rows: list[dict[str, Any]] = []
    for feed in provider_settings.get("feeds", []) or []:
        if not isinstance(feed, dict) or not bool(feed.get("enabled", True)):
            continue
        feed_url = str(feed.get("url", "") or "").strip()
        feed_name = str(feed.get("name", "") or feed_url or "regulatory_feed")
        provider_name = str(feed.get("provider", "") or f"reg:{feed_name}")
        errors: list[str] = []
        raw_item_count = 0
        normalized_count = 0
        try:
            rows = _fetch_feed_rows(
                provider_name,
                feed_url,
                report_date,
                timeout_seconds=timeout_seconds,
                fetch_html=fetch_html,
                fetch_json=fetch_json,
                parse_sse=parse_sse,
                parse_amac=parse_amac,
                parse_szse_page=parse_szse_page,
                parse_szse_report=parse_szse_report,
                errors=errors,
            )
            raw_item_count = len(rows)
            for raw_item in rows:
                normalized = normalize_item(raw_item, provider_name=provider_name, feed_name=feed_name, report_date=report_date)
                if normalized is not None:
                    items.append(normalized)
                    normalized_count += 1
        except Exception as exc:
            errors.append(str(exc))
        status = "ok" if normalized_count > 0 and not errors else "warning"
        provider_items = [item for item in items if item.get("provider") == provider_name]
        health_rows.append(
            build_health(
                source_key=f"regulatory_news:{provider_name}",
                source_role="regulatory_news",
                provider=provider_name,
                items=provider_items,
                configured=True,
                status=status,
                notes=[f"feed_url={feed_url}", f"raw_item_count={raw_item_count}", f"normalized_count={normalized_count}", *errors[:4]],
                error_count=len(errors),
                warning_count=1 if status == "warning" else 0,
                metrics={
                    "raw_item_count": raw_item_count,
                    "normalized_count": normalized_count,
                    "sample_titles": [str(item.get("title", "") or "")[:60] for item in provider_items[:3]],
                },
            )
        )
    return items, health_rows


def _fetch_feed_rows(
    provider_name: str,
    feed_url: str,
    report_date: str,
    *,
    timeout_seconds: int,
    fetch_html: Callable[..., str],
    fetch_json: Callable[..., str],
    parse_sse: Callable[[str, str, str], list[dict[str, Any]]],
    parse_amac: Callable[[str, str, str], list[dict[str, Any]]],
    parse_szse_page: Callable[[str, str, str], list[dict[str, Any]]],
    parse_szse_report: Callable[[str, str, str], list[dict[str, Any]]],
    errors: list[str],
) -> list[dict[str, Any]]:
    api_url = SZSE_REPORT_ENDPOINTS.get(provider_name)
    if api_url:
        return parse_szse_report(fetch_json(api_url, timeout_seconds=timeout_seconds, referer=feed_url), api_url, report_date)

    html_text = fetch_html(feed_url, timeout_seconds=timeout_seconds)
    if provider_name == "reg:sse_general":
        return parse_sse(html_text, feed_url, report_date)
    if provider_name == "reg:amac_notice":
        return parse_amac(html_text, feed_url, report_date)
    if provider_name == "reg:szse_listed_notice":
        rows = parse_szse_page(html_text, feed_url, report_date)
        if not rows:
            errors.append("szse listed notice page is dynamic; no official JSON endpoint enabled yet")
        return rows
    return []
