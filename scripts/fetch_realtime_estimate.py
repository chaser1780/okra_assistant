from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import local

import requests

from common import classify_intraday_freshness, classify_official_nav_freshness, dump_json, ensure_layout, estimated_nav_path, load_portfolio, load_settings, load_watchlist, resolve_agent_home, resolve_date, timestamp_now
from provider_adapters import build_provider_payload, resolve_provider_config

FUND_GZ_URL = "https://fundgz.1234567.com.cn/js/{code}.js?rt={stamp}"
JSONP_PATTERN = re.compile(r"jsonpgz\((.*)\)")
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36",
    "Referer": "https://fund.eastmoney.com/",
}
_SESSION_LOCAL = local()


def parse_timestamp(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    text = value.strip()
    if len(text) >= 16:
        return text[:10], text[11:16]
    return None, None


def classify_confidence(category: str, stale: bool) -> float:
    base = {
        "etf_linked": 0.88,
        "index_equity": 0.86,
        "active_equity": 0.72,
        "qdii_index": 0.58,
        "cash_management": 0.35,
        "bond": 0.30,
    }.get(category, 0.50)
    if stale:
        base -= 0.20
    return max(0.05, round(base, 2))


def get_text_with_retry(session: requests.Session, url: str, max_attempts: int = 3) -> str:
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def fetch_estimate(session: requests.Session, code: str) -> dict:
    body = get_text_with_retry(session, FUND_GZ_URL.format(code=code, stamp=int(time.time() * 1000)))
    match = JSONP_PATTERN.search(body)
    if not match:
        raise RuntimeError(f"Unexpected JSONP body for {code}: {body[:120]}")
    return json.loads(match.group(1))


def build_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(DEFAULT_HEADERS)
    return session


def get_thread_session() -> requests.Session:
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is None:
        session = build_session()
        _SESSION_LOCAL.session = session
    return session


def fetch_one_item(fund: dict, watchlist_by_code: dict, report_date: str) -> dict:
    code = fund["fund_code"]
    meta = watchlist_by_code.get(code, {})
    category = meta.get("category", "unknown")
    try:
        raw = fetch_estimate(get_thread_session(), code)
        estimate_date, estimate_time = parse_timestamp(raw.get("gztime"))
        estimate_freshness = classify_intraday_freshness(report_date, estimate_date, "基金估值")
        official_nav_freshness = classify_official_nav_freshness(report_date, raw.get("jzrq"))
        stale = estimate_freshness["is_stale"]
        return {
            "fund_code": code,
            "fund_name": fund["fund_name"],
            "category": category,
            "estimate_nav": float(raw["gsz"]) if raw.get("gsz") else None,
            "estimate_change_pct": float(raw["gszzl"]) if raw.get("gszzl") not in (None, "") else None,
            "estimate_time": estimate_time,
            "estimate_date": estimate_date,
            "estimate_freshness_status": estimate_freshness["status"],
            "estimate_freshness_label": estimate_freshness["label"],
            "estimate_freshness_business_day_gap": estimate_freshness["business_day_gap"],
            "official_nav": float(raw["dwjz"]) if raw.get("dwjz") else None,
            "official_nav_date": raw.get("jzrq"),
            "official_nav_freshness_status": official_nav_freshness["status"],
            "official_nav_freshness_label": official_nav_freshness["label"],
            "official_nav_freshness_business_day_gap": official_nav_freshness["business_day_gap"],
            "stale": stale,
            "confidence": classify_confidence(category, stale),
            "status": "ok",
        }
    except Exception as exc:
        return {
            "fund_code": code,
            "fund_name": fund["fund_name"],
            "category": category,
            "estimate_nav": None,
            "estimate_change_pct": None,
            "estimate_time": None,
            "estimate_date": None,
            "estimate_freshness_status": "unknown",
            "estimate_freshness_label": "基金估值不可用",
            "estimate_freshness_business_day_gap": None,
            "official_nav": None,
            "official_nav_date": None,
            "official_nav_freshness_status": "unknown",
            "official_nav_freshness_label": "官方净值不可用",
            "official_nav_freshness_business_day_gap": None,
            "stale": True,
            "confidence": 0.0,
            "status": f"error: {exc}",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch realtime fund valuation estimates.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--provider", help="Override the configured estimate provider name.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    portfolio = load_portfolio(agent_home)
    settings = load_settings(agent_home)
    provider_config = resolve_provider_config(settings, "estimated_nav", args.provider)
    provider = provider_config.name
    watchlist = load_watchlist(agent_home)
    watchlist_by_code = {item["code"]: item for item in watchlist.get("funds", [])}

    items_by_index: dict[int, dict] = {}
    workers = min(4, max(1, len(portfolio["funds"])))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_one_item, fund, watchlist_by_code, report_date): index
            for index, fund in enumerate(portfolio["funds"])
        }
        for future in as_completed(futures):
            items_by_index[futures[future]] = future.result()
    items = [items_by_index[index] for index in sorted(items_by_index)]

    payload = build_provider_payload(report_date, provider, "items", items, enabled=True)
    print(dump_json(estimated_nav_path(agent_home, report_date), payload))


if __name__ == "__main__":
    main()
