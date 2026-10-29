"""Fetch and atomically publish an exchange-verified trading calendar.

The exchange endpoints are intentionally configurable because both exchanges
occasionally change their public report routes. A calendar is published only
when both sources return a non-empty, identical trading-date set.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from common import (
    SHANGHAI_TZ,
    file_lock,
    load_trading_calendar,
    lock_path,
    resolve_agent_home,
    timestamp_now,
    trading_calendar_path,
    trading_calendar_runtime_path,
    trading_calendar_update_state_path,
)


# The exchanges publish the annual stock-market holiday schedule as signed
# HTML notices.  The old JSON/report endpoints are not stable and currently
# return either an empty result or an access-denied page.
DEFAULT_SSE_URL = "https://www.sse.com.cn/disclosure/dealinstruc/closed/list/"
DEFAULT_SZSE_URL = "https://www.szse.cn/disclosure/notice/general/index.html"
MIN_TRADING_DAYS = 200


def _html_text(raw: str) -> str:
    class TextExtractor(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.skip_depth = 0
            self.parts: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag.lower() in {"script", "style", "noscript"}:
                self.skip_depth += 1

        def handle_endtag(self, tag: str) -> None:
            if tag.lower() in {"script", "style", "noscript"} and self.skip_depth:
                self.skip_depth -= 1

        def handle_data(self, data: str) -> None:
            if not self.skip_depth:
                self.parts.append(data)

    parser = TextExtractor()
    parser.feed(str(raw or ""))
    text = html.unescape(" ".join(parser.parts))
    # SZSE occasionally inserts spaces between digits in rendered HTML
    # (for example, ``202 6``); these spaces are not part of the notice.
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    return re.sub(r"\s+", "", text)


def _notice_date(year: int, month: str, day: str) -> date:
    return date(year, int(month), int(day))


def _notice_dates(text: str, expected_year: int) -> tuple[set[str], set[str]]:
    """Return (open weekdays, explicit open weekends) from an exchange notice.

    Annual notices enumerate every holiday closure.  Weekdays not listed in a
    complete notice are trading days; explicit weekend ``开市`` dates are kept
    separately so ``build_calendar_payload`` can preserve its makeup field.
    """
    clean = _html_text(text)
    if not re.search(rf"{expected_year}年.*休市安排", clean):
        raise RuntimeError(f"official notice does not identify the {expected_year} calendar")

    closed: set[date] = set()
    range_count = 0
    holiday_categories = {"元旦", "春节", "清明节", "劳动节", "端午节", "中秋节", "国庆节"}
    seen_categories: set[str] = set()
    weekdays = {"星期一": 0, "星期二": 1, "星期三": 2, "星期四": 3, "星期五": 4, "星期六": 5, "星期日": 6, "星期天": 6}
    # 1月1日（星期四）至1月3日（星期六）休市
    range_pattern = re.compile(
        r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日(?:（([^）]*)）)?"
        r"至(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日(?:（([^）]*)）)?休市"
    )
    range_spans: list[tuple[int, int]] = []
    for match in range_pattern.finditer(clean):
        range_spans.append(match.span())
        context = clean[max(0, match.start() - 30):match.start()]
        category = next((item for item in holiday_categories if item in context[-12:]), None)
        if category is None:
            raise RuntimeError("official notice holiday range has no recognized category")
        if category in seen_categories:
            raise RuntimeError(f"official notice repeats holiday category: {category}")
        seen_categories.add(category)
        first_year = int(match.group(1) or expected_year)
        second_year = int(match.group(5) or first_year)
        start = _notice_date(first_year, match.group(2), match.group(3))
        end = _notice_date(second_year, match.group(6), match.group(7))
        if start > end or start.year != expected_year or end.year != expected_year:
            raise RuntimeError("official notice contains an invalid holiday range")
        for item, label in ((start, match.group(4)), (end, match.group(8))):
            if label and label in weekdays and item.weekday() != weekdays[label]:
                raise RuntimeError(f"official notice weekday does not match {item.isoformat()}")
        range_count += 1
        cursor = start
        while cursor <= end:
            closed.add(cursor)
            cursor += timedelta(days=1)

    # ``另外，10月10日（星期六）为周末休市`` and similar explicit dates.
    single_pattern = re.compile(
        r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日(?:（([^）]*)）)?"
        r"(?:为|是)周末休市"
    )
    for match in single_pattern.finditer(clean):
        item = _notice_date(int(match.group(1) or expected_year), match.group(2), match.group(3))
        if item.year != expected_year:
            raise RuntimeError("official notice contains a date outside the requested year")
        label = match.group(4)
        if label in weekdays and item.weekday() != weekdays[label]:
            raise RuntimeError(f"official notice weekday does not match {item.isoformat()}")
        closed.add(item)

    # Some official notices express a holiday as a single weekday rather than
    # a ``至`` range (for example ``1月1日（星期三）休市``).  Keep these dates
    # while ignoring the end dates already consumed by a range above.
    single_holiday_pattern = re.compile(
        r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日(?:（([^）]*)）)?休市"
    )
    for match in single_holiday_pattern.finditer(clean):
        if any(start <= match.start() < end for start, end in range_spans):
            continue
        context = clean[max(0, match.start() - 30):match.start()]
        category = next((item for item in holiday_categories if item in context[-12:]), None)
        if category is None:
            continue
        item = _notice_date(int(match.group(1) or expected_year), match.group(2), match.group(3))
        if item.year != expected_year:
            raise RuntimeError("official notice contains a date outside the requested year")
        label = match.group(4)
        if label in weekdays and item.weekday() != weekdays[label]:
            raise RuntimeError(f"official notice weekday does not match {item.isoformat()}")
        seen_categories.add(category)
        closed.add(item)

    # The annual notices enumerate all seven mainland exchange holiday blocks.
    if len(seen_categories) != 7 or seen_categories != holiday_categories or len(closed) < 1:
        raise RuntimeError("official notice is incomplete: expected seven holiday ranges")

    # A weekend explicitly followed by ``开市`` is an exceptional makeup day.
    open_weekends: set[str] = set()
    open_pattern = re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日（(星期[一二三四五六日天])）[^。；，,]{0,20}(?:照常)?开市")
    for match in open_pattern.finditer(clean):
        item = _notice_date(int(match.group(1) or expected_year), match.group(2), match.group(3))
        if item.weekday() != weekdays.get(match.group(4)):
            raise RuntimeError(f"official notice weekday does not match {item.isoformat()}")
        if item.year != expected_year or item.weekday() < 5:
            continue
        if item in closed:
            raise RuntimeError(f"official notice lists {item.isoformat()} as both closed and open")
        open_weekends.add(item.isoformat())

    start = date(expected_year, 1, 1)
    end = date(expected_year, 12, 31)
    open_days = {
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
        if (start + timedelta(days=offset)).weekday() < 5 and (start + timedelta(days=offset)) not in closed
    }
    open_days.update(open_weekends)
    if len(open_days) < MIN_TRADING_DAYS:
        raise RuntimeError(f"official notice coverage is too small for {expected_year}: {len(open_days)} trading dates")
    return open_days, open_weekends


def parse_official_notice(text: str, *, expected_year: int) -> set[str]:
    """Parse an SSE/SZSE annual holiday notice into trading dates."""
    return _notice_dates(text, expected_year)[0]


def _notice_link_candidates(index_text: str, *, base_url: str, year: int) -> list[str]:
    matches: list[str] = []
    for attrs, body in re.findall(r"<a\b([^>]*)>(.*?)</a>", index_text, re.I | re.S):
        href = re.search(r"\bhref\s*=\s*['\"]([^'\"]+)['\"]", attrs, re.I)
        title = re.search(r"\btitle\s*=\s*['\"]([^'\"]+)['\"]", attrs, re.I)
        label = html.unescape(title.group(1) if title else re.sub(r"<[^>]*>", " ", body))
        if href and str(year) in label and "休市" in label and "节假日" in label:
            matches.append(urljoin(base_url, href.group(1)))

    # SZSE's static article index emits list entries as JavaScript variables.
    pattern = re.compile(
        r"var\s+curHref\s*=\s*['\"]([^'\"]+)['\"];.{0,500}?"
        r"var\s+curTitle\s*=\s*['\"]([^'\"]+)['\"]",
        re.I | re.S,
    )
    for href, title in pattern.findall(index_text):
        if str(year) in title and "休市" in title and "节假日" in title:
            matches.append(urljoin(base_url, href))
    return list(dict.fromkeys(matches))


def parse_calendar_text(text: str, *, expected_year: int) -> set[str]:
    """Compatibility alias for parsing the official HTML notice format."""
    return parse_official_notice(text, expected_year=expected_year)


def _request(http: requests.Session, url: str, *, source: str, year: int, timeout: int) -> str:
    referer = "https://www.sse.com.cn/" if source == "sse" else "https://www.szse.cn/"
    response = http.get(
        url,
        headers={"User-Agent": "OKRA/0.2 calendar updater", "Referer": referer},
        timeout=timeout,
    )
    response.raise_for_status()
    content = getattr(response, "content", None)
    if isinstance(content, bytes):
        text = content.decode("utf-8-sig", errors="replace")
    else:
        text = str(response.text)
    if "\ufffd" in text:
        raise RuntimeError(f"{source} returned undecodable calendar HTML")
    return text


def _fetch_exchange_calendar(
    url: str,
    *,
    year: int,
    source: str,
    session: requests.Session | None = None,
    timeout: int = 20,
) -> tuple[set[str], str]:
    http = session or requests.Session()
    first_page = _request(http, url, source=source, year=year, timeout=timeout)

    def extract(page_url: str, page_text: str) -> tuple[set[str], str] | None:
        try:
            dates = parse_official_notice(page_text, expected_year=year)
        except RuntimeError:
            dates = set()
        if dates:
            return dates, page_url
        candidates = _notice_link_candidates(page_text, base_url=page_url, year=year)
        for notice_url in candidates:
            notice_text = _request(http, notice_url, source=source, year=year, timeout=timeout)
            try:
                dates = parse_official_notice(notice_text, expected_year=year)
            except RuntimeError:
                continue
            return dates, notice_url
        return None

    result = extract(url, first_page)
    if result:
        return result
    if source == "szse" and re.search(r"/index\.html(?:$|\?)", url, re.I):
        count_match = re.search(r"pageCount\s*:\s*(\d+)", first_page)
        page_count = min(int(count_match.group(1)) if count_match else 16, 32)
        for index in range(1, page_count):
            page_url = urljoin(url, f"index_{index}.html")
            try:
                page_text = _request(http, page_url, source=source, year=year, timeout=timeout)
            except requests.RequestException:
                continue
            result = extract(page_url, page_text)
            if result:
                return result
    raise RuntimeError(f"{source} calendar returned no complete official notice for {year}")


def fetch_exchange_calendar(
    url: str,
    *,
    year: int,
    source: str,
    session: requests.Session | None = None,
    timeout: int = 20,
) -> set[str]:
    return _fetch_exchange_calendar(url, year=year, source=source, session=session, timeout=timeout)[0]


def build_calendar_payload(
    year: int,
    sse_days: set[str],
    szse_days: set[str],
    *,
    sse_url: str = DEFAULT_SSE_URL,
    szse_url: str = DEFAULT_SZSE_URL,
    sse_index_url: str = DEFAULT_SSE_URL,
    szse_index_url: str = DEFAULT_SZSE_URL,
) -> dict[str, Any]:
    if not sse_days or not szse_days:
        raise ValueError("both exchange calendars must contain dates")
    if sse_days != szse_days:
        only_sse = sorted(sse_days - szse_days)[:5]
        only_szse = sorted(szse_days - sse_days)[:5]
        raise ValueError(f"exchange calendar mismatch: sse_only={only_sse}, szse_only={only_szse}")
    expected_prefix = f"{year:04d}-"
    in_year = {item for item in sse_days if item.startswith(expected_prefix)}
    if len(in_year) < MIN_TRADING_DAYS:
        raise ValueError(f"exchange calendar coverage is too small for {year}: {len(in_year)} trading dates")
    if min(in_year) > f"{year:04d}-02-01" or max(in_year) < f"{year:04d}-11-30":
        raise ValueError(f"exchange calendar does not cover the full target year {year}")
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    holidays: list[str] = []
    makeup: list[str] = []
    cursor = start
    while cursor <= end:
        text = cursor.isoformat()
        if cursor.weekday() < 5 and text not in sse_days:
            holidays.append(text)
        elif cursor.weekday() >= 5 and text in sse_days:
            makeup.append(text)
        cursor += timedelta(days=1)
    now = timestamp_now()
    return {
        "calendar_version": str(year),
        "source": "sse+szse",
        "checked_at": now,
        "updated_at": now,
        "coverage_start": f"{year}-01-01",
        "coverage_end": f"{year}-12-31",
        "holidays": holidays,
        "makeup_trading_days": makeup,
        "sources": {"sse": sse_url, "szse": szse_url},
        "source_indexes": {"sse": sse_index_url, "szse": szse_index_url},
    }


def merge_calendar_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge validated annual payloads into one runtime cache."""
    if not payloads:
        raise ValueError("at least one annual calendar is required")
    years = sorted({str(item.get("calendar_version", "")) for item in payloads})
    holidays = sorted({value for item in payloads for value in item.get("holidays", []) or []})
    makeup = sorted({value for item in payloads for value in item.get("makeup_trading_days", []) or []})
    sources: dict[str, str] = {}
    indexes: dict[str, str] = {}
    for item in payloads:
        for key, value in (item.get("sources") or {}).items():
            sources[key] = str(value)
        for key, value in (item.get("source_indexes") or {}).items():
            indexes[key] = str(value)
    return {
        "calendar_version": "-".join(years),
        "source": "sse+szse",
        "checked_at": timestamp_now(),
        "updated_at": timestamp_now(),
        "coverage_start": min(str(item["coverage_start"]) for item in payloads),
        "coverage_end": max(str(item["coverage_end"]) for item in payloads),
        "holidays": holidays,
        "makeup_trading_days": makeup,
        "sources": sources,
        "source_indexes": indexes,
    }


def _coverage_has_year(payload: dict[str, Any], year: int) -> bool:
    start = str(payload.get("coverage_start") or "")
    end = str(payload.get("coverage_end") or "")
    return bool(start <= f"{year:04d}-01-01" and end >= f"{year:04d}-12-31")


def update_calendar(
    agent_home: Path,
    *,
    year: int,
    sse_url: str = DEFAULT_SSE_URL,
    szse_url: str = DEFAULT_SZSE_URL,
    timeout: int = 20,
) -> Path:
    session = requests.Session()
    existing = load_trading_calendar(agent_home)
    years = [year - 1, year, year + 1]
    annual_payloads: list[dict[str, Any]] = []
    for target_year in years:
        # Always refresh the requested year. Adjacent years are fetched when
        # the existing cache does not already cover them.
        if target_year != year and _coverage_has_year(existing, target_year):
            continue
        sse_days, sse_notice_url = _fetch_exchange_calendar(sse_url, year=target_year, source="sse", session=session, timeout=timeout)
        szse_days, szse_notice_url = _fetch_exchange_calendar(szse_url, year=target_year, source="szse", session=session, timeout=timeout)
        annual_payloads.append(
            build_calendar_payload(
                target_year,
                sse_days,
                szse_days,
                sse_url=sse_notice_url,
                szse_url=szse_notice_url,
                sse_index_url=sse_url,
                szse_index_url=szse_url,
            )
        )
    if not annual_payloads:
        raise RuntimeError("no annual calendar was refreshed")
    if existing.get("coverage_start") and existing.get("coverage_end"):
        # Preserve cached dates outside the refreshed year while removing the
        # old target-year entries so an updated notice can replace them.
        prefix = f"{year:04d}-"
        retained = dict(existing)
        retained["holidays"] = [item for item in existing.get("holidays", []) or [] if not str(item).startswith(prefix)]
        retained["makeup_trading_days"] = [item for item in existing.get("makeup_trading_days", []) or [] if not str(item).startswith(prefix)]
        annual_payloads.insert(0, retained)
    payload = merge_calendar_payloads(annual_payloads)
    target = trading_calendar_runtime_path(agent_home)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with file_lock(lock_path(agent_home, "trading_calendar_cache"), timeout_seconds=30.0):
            temp.replace(target)
    finally:
        if temp.exists():
            temp.unlink()
    return target


def maybe_update_calendar(agent_home: Path, *, now: datetime | None = None, timeout: int = 8) -> dict[str, Any]:
    """Attempt one authoritative calendar refresh per Shanghai calendar day.

    The attempt marker is written before the network call, so repeated desktop/API
    starts cannot create a request storm. Existing cache contents are never replaced
    unless both exchange sources validate successfully.
    """
    root = agent_home.resolve()
    current = now or datetime.now(SHANGHAI_TZ)
    if current.tzinfo:
        current = current.astimezone(SHANGHAI_TZ)
    day = current.date().isoformat()
    marker = trading_calendar_update_state_path(root)
    legacy_marker = root / "config" / "trading_calendar_update_state.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(lock_path(root, "trading_calendar_update"), timeout_seconds=30.0):
        state: dict[str, Any] = {}
        source_marker = marker if marker.exists() else legacy_marker
        if source_marker.exists():
            try:
                state = json.loads(source_marker.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {}
        if state.get("last_attempt_date") == day:
            return {**state, "status": "already_attempted", "date": day}

        state = {"last_attempt_date": day, "attempted_at": timestamp_now()}
        temp_marker = marker.with_name(f"{marker.name}.{os.getpid()}.tmp")
        temp_marker.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_marker.replace(marker)
        existing = load_trading_calendar(root)
        indexes = existing.get("source_indexes") if isinstance(existing.get("source_indexes"), dict) else {}
        sse_url = str(indexes.get("sse") or DEFAULT_SSE_URL)
        szse_url = str(indexes.get("szse") or DEFAULT_SZSE_URL)
        year = current.date().year
        try:
            path = update_calendar(root, year=year, sse_url=sse_url, szse_url=szse_url, timeout=timeout)
        except Exception as exc:
            state.update({"status": "failed", "error": str(exc)})
            temp_marker.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_marker.replace(marker)
            return {"status": "failed", "date": day, "error": str(exc)}
        state.update({"status": "updated", "path": str(path)})
        temp_marker.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_marker.replace(marker)
        return {"status": "updated", "date": day, "path": str(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Update OKRA trading calendar from SSE and SZSE.")
    parser.add_argument("--agent-home", default=None)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--sse-url", default=DEFAULT_SSE_URL)
    parser.add_argument("--szse-url", default=DEFAULT_SZSE_URL)
    args = parser.parse_args()
    path = update_calendar(resolve_agent_home(args.agent_home), year=args.year, sse_url=args.sse_url, szse_url=args.szse_url)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
