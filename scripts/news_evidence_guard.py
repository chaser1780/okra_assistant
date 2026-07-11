from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonical_citation_url(value: str) -> str:
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, query, ""))


def extract_web_search_citation_urls(response: dict[str, Any]) -> set[str]:
    urls: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            item_type = str(value.get("type", "") or "").lower()
            if item_type in {"url_citation", "citation"}:
                canonical = canonical_citation_url(str(value.get("url", "") or ""))
                if canonical:
                    urls.add(canonical)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(response.get("completed_event", {}))
    walk(response.get("events", []))
    return urls


def timestamp_not_after_cutoff(value: str, cutoff: str) -> bool:
    if not cutoff:
        return True
    try:
        available = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
        decision_cutoff = datetime.fromisoformat(str(cutoff or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    if available.tzinfo is None or available.utcoffset() is None:
        return False
    if decision_cutoff.tzinfo is None or decision_cutoff.utcoffset() is None:
        return False
    return available <= decision_cutoff
