from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable


CN_TZ = timezone(timedelta(hours=8))


def parse_rss_datetime(value: str | None, report_date: str) -> str:
    """Normalize RSS/Atom timestamps to Shanghai time; report_date stays for API compatibility."""
    del report_date
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}(?:[T\s]|$)", candidate):
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=CN_TZ)
            return parsed.astimezone(CN_TZ).isoformat(timespec="seconds")
        except ValueError:
            pass
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(candidate, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=CN_TZ)
            return parsed.astimezone(CN_TZ).isoformat(timespec="seconds")
        except ValueError:
            continue
    try:
        parsed = parsedate_to_datetime(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=CN_TZ)
        return parsed.astimezone(CN_TZ).isoformat(timespec="seconds")
    except (TypeError, ValueError, IndexError):
        return ""


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, *names: str) -> str:
    accepted = set(names)
    for child in node:
        if _local_name(str(child.tag)) in accepted:
            return str(child.text or "")
    return ""


def _child(node: ET.Element, name: str) -> ET.Element | None:
    for child in node:
        if _local_name(str(child.tag)) == name:
            return child
    return None


def parse_rss_feed(xml_text: str, report_date: str, *, plain_text: Callable[[str], str]) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, str]] = []
    for node in root.iter():
        if _local_name(str(node.tag)) not in {"item", "entry"}:
            continue
        title = plain_text(_child_text(node, "title"))
        summary = plain_text(
            _child_text(node, "description")
            or _child_text(node, "summary")
            or title
        )
        link = _child_text(node, "link")
        if not link:
            link_node = _child(node, "link")
            if link_node is not None:
                link = str(link_node.attrib.get("href", "") or "")
        published_at = parse_rss_datetime(
            _child_text(node, "pubDate") or _child_text(node, "published") or _child_text(node, "updated"),
            report_date,
        )
        if not title or not link:
            continue
        items.append(
            {
                "title": title[:120],
                "summary": (summary[:240] or title[:120]),
                "published_at": published_at,
                "url": link.strip(),
            }
        )
    return items


def fetch_rss_news(
    provider_settings: dict[str, Any],
    report_date: str,
    query_plan: dict[str, Any],
    *,
    fetch_xml: Callable[..., str],
    parse_feed: Callable[[str, str], list[dict[str, Any]]],
    query_matches: Callable[[str, dict[str, Any]], bool],
    normalize_item: Callable[..., list[dict[str, Any]]],
    build_health: Callable[..., dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect configured RSS feeds without knowing the application's storage or DTO shape."""
    if not bool(provider_settings.get("enabled", False)):
        return [], []
    timeout_seconds = int(provider_settings.get("timeout_seconds", 12) or 12)
    feeds = list(provider_settings.get("feeds", []) or [])
    if not feeds:
        return [], [
            build_health(
                source_key="rss_news:feeds",
                source_role="theme_news",
                provider="rss_news",
                configured=True,
                status="warning",
                notes=["rss feeds not configured"],
            )
        ]

    all_items: list[dict[str, Any]] = []
    health_rows: list[dict[str, Any]] = []
    combined_queries = [
        *(query_plan.get("direct_queries", []) or []),
        *(query_plan.get("theme_queries", []) or []),
        *(query_plan.get("market_queries", []) or []),
    ]
    for feed in feeds:
        if not bool(feed.get("enabled", True)):
            continue
        feed_url = str(feed.get("url", "") or "").strip()
        feed_name = str(feed.get("name", "") or feed_url or "rss_feed")
        provider_name = str(feed.get("provider", "") or f"rss:{feed_name}")
        if not feed_url:
            health_rows.append(
                build_health(
                    source_key=f"rss_news:{provider_name}",
                    source_role="theme_news",
                    provider=provider_name,
                    configured=False,
                    status="warning",
                    notes=["missing feed url"],
                )
            )
            continue

        errors: list[str] = []
        raw_item_count = 0
        matched_count = 0
        try:
            rows = parse_feed(fetch_xml(feed_url, timeout_seconds=timeout_seconds), report_date)
            raw_item_count = len(rows)
            for raw_item in rows:
                for query in combined_queries:
                    keyword = str(query.get("keyword", "") or "").strip()
                    if not keyword or not query_matches(keyword, raw_item):
                        continue
                    matched_count += 1
                    all_items.extend(
                        normalize_item(
                            raw_item,
                            query,
                            feed_name=feed_name,
                            provider_name=provider_name,
                            report_date=report_date,
                            feed=feed,
                        )
                    )
        except ET.ParseError as exc:
            errors.append(f"parse_error={exc}")
        except Exception as exc:
            errors.append(str(exc))

        status = "ok" if matched_count > 0 and not errors else ("warning" if errors or raw_item_count == 0 else "ok")
        health_rows.append(
            build_health(
                source_key=f"rss_news:{provider_name}",
                source_role="theme_news",
                provider=provider_name,
                items=[item for item in all_items if item.get("provider") == provider_name],
                configured=True,
                status=status,
                notes=[f"feed_url={feed_url}", f"raw_item_count={raw_item_count}", f"matched_item_count={matched_count}", *errors[:4]],
                error_count=len(errors),
                warning_count=1 if status == "warning" else 0,
                metrics={
                    "raw_item_count": raw_item_count,
                    "matched_item_count": matched_count,
                    "feed_ok": int(not errors and raw_item_count > 0),
                    "parse_error": int(any("parse_error" in error for error in errors)),
                    "empty_feed": int(raw_item_count == 0),
                    "stale_feed": 0,
                },
            )
        )
    return all_items, health_rows
