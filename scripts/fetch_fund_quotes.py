from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import local
from typing import Any

import requests

from common import classify_official_nav_freshness, dump_json, ensure_layout, load_settings, load_watchlist, quote_path, resolve_agent_home, resolve_date, timestamp_now
from provider_adapters import (
    attach_provider_metadata,
    build_provider_attempt,
    build_provider_payload,
    resolve_provider_chain,
    resolve_provider_config,
    stale_fallback_from_recent_snapshot,
)

EASTMONEY_NAV_API = "https://api.fund.eastmoney.com/f10/lsjz"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36",
    "Referer": "https://fundf10.eastmoney.com/",
}
_SESSION_LOCAL = local()


def safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_return(latest_nav: float | None, baseline_nav: float | None) -> float:
    if latest_nav in (None, 0) or baseline_nav in (None, 0):
        return 0.0
    return round((latest_nav / baseline_nav - 1) * 100, 2)


def pick_baseline(rows: list[dict], preferred_index: int) -> dict | None:
    if not rows:
        return None
    index = min(preferred_index, len(rows) - 1)
    return rows[index]


def parse_row_date(row: dict) -> datetime.date | None:
    value = (row.get("FSRQ") or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def select_target_index(rows: list[dict], report_date: str) -> int:
    target_date = datetime.strptime(report_date, "%Y-%m-%d").date()
    fallback = None
    for index, row in enumerate(rows):
        row_date = parse_row_date(row)
        if row_date is None:
            continue
        if fallback is None:
            fallback = index
        if row_date <= target_date:
            return index
    return fallback or 0


def build_demo_quotes(watchlist: dict, report_date: str) -> list[dict]:
    quotes = []
    for index, fund in enumerate(watchlist["funds"]):
        offset = index - 1
        day_change_pct = round(offset * 0.85, 2)
        quotes.append({
            "code": fund["code"],
            "name": fund["name"],
            "category": fund.get("category", "unknown"),
            "benchmark": fund.get("benchmark", ""),
            "nav": round(1.0 + index * 0.137, 4),
            "cumulative_nav": round(1.0 + index * 0.161, 4),
            "day_change_pct": day_change_pct,
            "week_change_pct": round(day_change_pct * 2.1, 2),
            "month_change_pct": round(day_change_pct * 4.3, 2),
            "as_of_date": report_date,
            "freshness_status": "fresh",
            "source_url": f"https://fundf10.eastmoney.com/jjjz_{fund['code']}.html",
            "source_title": fund["name"],
            "entity_id": fund["code"],
            "entity_type": "fund",
            "provider": "demo",
            "retrieved_at": timestamp_now(),
            "confidence": 0.98,
        })
    return quotes


def get_json_with_retry(session: requests.Session, url: str, *, timeout_seconds: int, max_attempts: int = 3, **kwargs) -> dict:
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(url, timeout=timeout_seconds, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"Failed to fetch JSON from {url}: {last_error}")


def fetch_nav_history(session: requests.Session, fund_code: str, page_size: int, timeout_seconds: int) -> list[dict]:
    payload = get_json_with_retry(
        session,
        EASTMONEY_NAV_API,
        timeout_seconds=timeout_seconds,
        params={
            "fundCode": fund_code,
            "pageIndex": 1,
            "pageSize": page_size,
            "startDate": "",
            "endDate": "",
        },
    )
    rows = payload.get("Data", {}).get("LSJZList", [])
    if not rows:
        raise RuntimeError(f"No NAV data returned for fund {fund_code}.")
    return rows


def build_real_quote(session: requests.Session, fund: dict, settings: dict, report_date: str) -> dict:
    timeout_seconds = int(settings["providers"]["quotes"].get("timeout_seconds", 15))
    page_size = int(settings["providers"]["quotes"].get("history_page_size", 120))
    rows = fetch_nav_history(session, fund["code"], page_size=page_size, timeout_seconds=timeout_seconds)
    target_index = select_target_index(rows, report_date)
    latest = rows[target_index]
    previous = rows[target_index + 1] if target_index + 1 < len(rows) else None
    week_baseline = pick_baseline(rows[target_index:], 5)
    month_baseline = pick_baseline(rows[target_index:], 21)
    latest_nav = safe_float(latest.get("DWJZ"))
    cumulative_nav = safe_float(latest.get("LJJZ"))
    previous_nav = safe_float(previous.get("DWJZ")) if previous else None
    week_nav = safe_float(week_baseline.get("DWJZ")) if week_baseline else None
    month_nav = safe_float(month_baseline.get("DWJZ")) if month_baseline else None
    day_change_pct = safe_float(latest.get("JZZZL"))
    freshness = classify_official_nav_freshness(report_date, latest.get("FSRQ", ""))
    if day_change_pct is None:
        day_change_pct = compute_return(latest_nav, previous_nav)
    return {
        "code": fund["code"],
        "name": fund["name"],
        "category": fund.get("category", "unknown"),
        "benchmark": fund.get("benchmark", ""),
        "nav": round(latest_nav or 0.0, 4),
        "cumulative_nav": round(cumulative_nav or 0.0, 4),
        "day_change_pct": round(day_change_pct, 2),
        "week_change_pct": compute_return(latest_nav, week_nav),
        "month_change_pct": compute_return(latest_nav, month_nav),
        "as_of_date": latest.get("FSRQ", ""),
        "requested_date": report_date,
        "date_match_type": freshness["status"],
        "freshness_label": freshness["label"],
        "freshness_business_day_gap": freshness["business_day_gap"],
        "freshness_is_acceptable": freshness["is_acceptable"],
        "freshness_is_delayed": freshness["is_delayed"],
        "freshness_status": freshness["status"],
        "source_url": f"https://fundf10.eastmoney.com/jjjz_{fund['code']}.html",
        "source_title": fund["name"],
        "entity_id": fund["code"],
        "entity_type": "fund",
        "provider": "eastmoney_nav_api",
        "retrieved_at": timestamp_now(),
        "confidence": 0.98 if freshness["is_acceptable"] else 0.85,
        "trade_status_purchase": latest.get("SGZT", ""),
        "trade_status_redeem": latest.get("SHZT", ""),
    }


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


def fetch_one_quote(fund: dict, settings: dict, report_date: str) -> dict:
    return build_real_quote(get_thread_session(), fund, settings, report_date)


def build_realtime_payload(watchlist: dict, settings: dict, report_date: str, provider_name: str) -> dict:
    workers = min(6, max(1, len(watchlist["funds"])))
    items_by_index: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_one_quote, fund, settings, report_date): index
            for index, fund in enumerate(watchlist["funds"])
        }
        for future in as_completed(futures):
            items_by_index[futures[future]] = future.result()
    funds = [items_by_index[index] for index in sorted(items_by_index)]
    return build_provider_payload(report_date, provider_name, "funds", funds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch daily fund quotes from Eastmoney or emit a demo payload.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--provider", help="Override the configured quotes provider name.")
    parser.add_argument("--demo", action="store_true", help="Write deterministic mock data.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    settings = load_settings(agent_home)
    watchlist = load_watchlist(agent_home)
    report_date = resolve_date(args.date)
    provider_config = resolve_provider_config(settings, "quotes", args.provider)
    provider_chain = resolve_provider_chain(settings, "quotes", args.provider)
    target_path = quote_path(agent_home, report_date)

    payload: dict | None = None
    provider_attempts: list[dict] = []
    last_error = ""

    for provider in provider_chain:
        if args.demo or provider.startswith("demo"):
            payload = build_provider_payload(report_date, provider, "funds", build_demo_quotes(watchlist, report_date))
            provider_attempts.append(
                build_provider_attempt(provider, "ok", item_count=len(payload.get("funds", [])), ok_count=len(payload.get("funds", [])), selected=True)
            )
            break

        if provider in {"eastmoney_nav_api", "eastmoney"}:
            try:
                payload = build_realtime_payload(watchlist, settings, report_date, provider)
                item_count = len(payload.get("funds", []))
                provider_attempts.append(build_provider_attempt(provider, "ok", item_count=item_count, ok_count=item_count, selected=True))
                break
            except Exception as exc:
                last_error = str(exc)
                provider_attempts.append(build_provider_attempt(provider, "error", detail=last_error))
                continue

        if provider == "stale_snapshot":
            payload = stale_fallback_from_recent_snapshot(target_path, report_date, provider, "funds", last_error or "fallback_requested")
            if payload is not None:
                item_count = len(payload.get("funds", []))
                provider_attempts.append(
                    build_provider_attempt(
                        provider,
                        "ok",
                        detail=payload.get("fallback_source_date", ""),
                        item_count=item_count,
                        ok_count=item_count,
                        selected=True,
                        fallback_kind="stale_snapshot",
                    )
                )
                break
            provider_attempts.append(build_provider_attempt(provider, "miss", detail="no_snapshot_available"))
            continue

        provider_attempts.append(build_provider_attempt(provider, "unsupported", detail=f"Unsupported quotes provider: {provider}"))

    if payload is None and provider_config.allow_stale_fallback:
        payload = stale_fallback_from_recent_snapshot(target_path, report_date, "stale_snapshot_auto", "funds", last_error or "all_providers_failed")
        if payload is not None:
            item_count = len(payload.get("funds", []))
            provider_attempts.append(
                build_provider_attempt(
                    "stale_snapshot_auto",
                    "ok",
                    detail=payload.get("fallback_source_date", ""),
                    item_count=item_count,
                    ok_count=item_count,
                    selected=True,
                    fallback_kind="stale_snapshot",
                )
            )

    if payload is None:
        payload = build_provider_payload(
            report_date,
            f"{provider_config.name}_unavailable",
            "funds",
            [],
            error=last_error or "all configured quote providers failed",
        )

    payload = attach_provider_metadata(
        payload,
        selected_provider=str(payload.get("provider", provider_config.name) or provider_config.name),
        provider_chain=provider_chain,
        provider_attempts=provider_attempts,
        fallback_kind=str(payload.get("fallback_kind", "") or ""),
    )

    print(dump_json(target_path, payload))


if __name__ == "__main__":
    main()
