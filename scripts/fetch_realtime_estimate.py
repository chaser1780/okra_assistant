from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import local

import requests

from common import (
    classify_intraday_freshness,
    classify_official_nav_freshness,
    dump_json,
    ensure_layout,
    estimated_nav_path,
    load_json,
    load_portfolio,
    load_settings,
    load_watchlist,
    quote_path,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
)
from provider_adapters import (
    attach_provider_metadata,
    build_provider_attempt,
    build_provider_payload,
    ok_item_count,
    resolve_provider_chain,
    resolve_provider_config,
    stale_fallback_from_recent_snapshot,
)

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
            "source_url": f"https://fundgz.1234567.com.cn/js/{code}.js",
            "source_title": fund["fund_name"],
            "entity_id": code,
            "entity_type": "fund",
            "provider": "fundgz_1234567",
            "retrieved_at": timestamp_now(),
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
            "source_url": f"https://fundgz.1234567.com.cn/js/{code}.js",
            "source_title": fund["fund_name"],
            "entity_id": code,
            "entity_type": "fund",
            "provider": "fundgz_1234567",
            "retrieved_at": timestamp_now(),
        }


def build_live_items(portfolio: dict, watchlist_by_code: dict, report_date: str) -> list[dict]:
    items_by_index: dict[int, dict] = {}
    workers = min(4, max(1, len(portfolio["funds"])))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_one_item, fund, watchlist_by_code, report_date): index
            for index, fund in enumerate(portfolio["funds"])
        }
        for future in as_completed(futures):
            items_by_index[futures[future]] = future.result()
    return [items_by_index[index] for index in sorted(items_by_index)]


def build_quote_derived_items(agent_home, portfolio: dict, watchlist_by_code: dict, report_date: str) -> list[dict]:
    quote_payload = load_json(quote_path(resolve_agent_home(agent_home), report_date))
    quote_by_code = {str(item.get("code", "") or ""): item for item in quote_payload.get("funds", []) or []}
    items: list[dict] = []
    for fund in portfolio["funds"]:
        code = str(fund.get("fund_code", "") or "")
        meta = watchlist_by_code.get(code, {})
        category = meta.get("category", "unknown")
        quote = quote_by_code.get(code)
        if not quote:
            items.append(
                {
                    "fund_code": code,
                    "fund_name": fund["fund_name"],
                    "category": category,
                    "estimate_nav": None,
                    "estimate_change_pct": None,
                    "estimate_time": None,
                    "estimate_date": None,
                    "estimate_freshness_status": "unknown",
                    "estimate_freshness_label": "官方净值回退源不可用",
                    "estimate_freshness_business_day_gap": None,
                    "official_nav": None,
                    "official_nav_date": None,
                    "official_nav_freshness_status": "unknown",
                    "official_nav_freshness_label": "官方净值不可用",
                    "official_nav_freshness_business_day_gap": None,
                    "stale": True,
                    "confidence": 0.0,
                    "status": "error: quote_nav_missing",
                    "source_url": "",
                    "source_title": fund["fund_name"],
                    "entity_id": code,
                    "entity_type": "fund",
                    "provider": "quote_nav_derived",
                    "retrieved_at": timestamp_now(),
                }
            )
            continue

        official_nav_date = quote.get("as_of_date")
        estimate_freshness = classify_intraday_freshness(report_date, official_nav_date, "基金估值回退源")
        official_nav_freshness = classify_official_nav_freshness(report_date, official_nav_date)
        stale = True
        items.append(
            {
                "fund_code": code,
                "fund_name": fund["fund_name"],
                "category": category,
                "estimate_nav": float(quote.get("nav", 0.0) or 0.0) if quote.get("nav") is not None else None,
                "estimate_change_pct": float(quote.get("day_change_pct", 0.0) or 0.0) if quote.get("day_change_pct") is not None else None,
                "estimate_time": None,
                "estimate_date": official_nav_date,
                "estimate_freshness_status": estimate_freshness["status"],
                "estimate_freshness_label": f"估值由官方净值回退生成，{official_nav_freshness['label']}",
                "estimate_freshness_business_day_gap": estimate_freshness["business_day_gap"],
                "official_nav": float(quote.get("nav", 0.0) or 0.0) if quote.get("nav") is not None else None,
                "official_nav_date": official_nav_date,
                "official_nav_freshness_status": official_nav_freshness["status"],
                "official_nav_freshness_label": official_nav_freshness["label"],
                "official_nav_freshness_business_day_gap": official_nav_freshness["business_day_gap"],
                "stale": stale,
                "confidence": max(0.08, round(classify_confidence(category, True) - 0.1, 2)),
                "status": "fallback: quote_nav_derived",
                "source_url": str(quote.get("source_url", "")),
                "source_title": fund["fund_name"],
                "entity_id": code,
                "entity_type": "fund",
                "provider": "quote_nav_derived",
                "retrieved_at": timestamp_now(),
            }
        )
    return items


def merge_estimate_items(primary_items: list[dict], fallback_items: list[dict], fallback_provider: str) -> tuple[list[dict], int]:
    merged = [dict(item) for item in primary_items]
    fallback_by_code = {str(item.get("fund_code", "") or ""): dict(item) for item in fallback_items}
    filled_count = 0
    for index, item in enumerate(merged):
        fund_code = str(item.get("fund_code", "") or "")
        if not fund_code:
            continue
        status = str(item.get("status", "ok") or "ok").lower()
        if status == "ok" and item.get("estimate_nav") is not None:
            continue
        fallback = fallback_by_code.get(fund_code)
        if fallback is None:
            continue
        fallback["fallback_parent_provider"] = str(item.get("provider", "") or "")
        fallback["fallback_parent_status"] = str(item.get("status", "") or "")
        fallback["provider"] = fallback_provider
        merged[index] = fallback
        filled_count += 1
    return merged, filled_count


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
    provider_chain = resolve_provider_chain(settings, "estimated_nav", args.provider)
    watchlist = load_watchlist(agent_home)
    watchlist_by_code = {item["code"]: item for item in watchlist.get("funds", [])}
    target_path = estimated_nav_path(agent_home, report_date)

    items: list[dict] = []
    payload: dict | None = None
    provider_attempts: list[dict] = []
    last_error = ""
    selected_provider = provider_config.name

    for provider in provider_chain:
        if provider == "fundgz_1234567":
            items = build_live_items(portfolio, watchlist_by_code, report_date)
            ok_count = ok_item_count(items)
            provider_attempts.append(
                build_provider_attempt(
                    provider,
                    "ok" if ok_count > 0 else "error",
                    detail="" if ok_count > 0 else "no_successful_estimates",
                    item_count=len(items),
                    ok_count=ok_count,
                    selected=ok_count > 0,
                )
            )
            if ok_count > 0:
                selected_provider = provider
                payload = build_provider_payload(report_date, provider, "items", items, enabled=True)
                continue
            last_error = "no_successful_estimates"
            continue

        if provider == "quote_nav_derived":
            try:
                fallback_items = build_quote_derived_items(agent_home, portfolio, watchlist_by_code, report_date)
                if payload is None:
                    items = fallback_items
                    ok_count = ok_item_count(items, ok_values={"ok", "fallback: quote_nav_derived"})
                    payload = build_provider_payload(report_date, provider, "items", items, enabled=True)
                    selected_provider = provider
                    provider_attempts.append(
                        build_provider_attempt(
                            provider,
                            "ok",
                            item_count=len(items),
                            ok_count=ok_count,
                            selected=True,
                            fallback_kind="quote_nav_derived",
                        )
                    )
                    break
                items, filled_count = merge_estimate_items(items, fallback_items, provider)
                ok_count = ok_item_count(items, ok_values={"ok", "fallback: quote_nav_derived"})
                payload["items"] = items
                provider_attempts.append(
                    build_provider_attempt(
                        provider,
                        "ok" if filled_count > 0 else "miss",
                        detail="" if filled_count > 0 else "no_missing_items_filled",
                        item_count=len(items),
                        ok_count=ok_count,
                        filled_count=filled_count,
                        selected=filled_count > 0,
                        fallback_kind="quote_nav_derived",
                    )
                )
                if filled_count > 0:
                    payload["provider"] = provider
                    selected_provider = provider
                    break
            except Exception as exc:
                last_error = str(exc)
                provider_attempts.append(build_provider_attempt(provider, "error", detail=last_error))
            continue

        if provider == "stale_snapshot":
            payload = stale_fallback_from_recent_snapshot(target_path, report_date, provider, "items", last_error or "fallback_requested")
            if payload is not None:
                item_count = len(payload.get("items", []))
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
                selected_provider = provider
                break
            provider_attempts.append(build_provider_attempt(provider, "miss", detail="no_snapshot_available"))
            continue

        provider_attempts.append(build_provider_attempt(provider, "unsupported", detail=f"Unsupported estimate provider: {provider}"))

    if payload is None and provider_config.allow_stale_fallback:
        payload = stale_fallback_from_recent_snapshot(target_path, report_date, "stale_snapshot_auto", "items", last_error or "all_providers_failed")
        if payload is not None:
            item_count = len(payload.get("items", []))
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
            selected_provider = "stale_snapshot_auto"

    if payload is None:
        payload = build_provider_payload(
            report_date,
            f"{provider_config.name}_unavailable",
            "items",
            [],
            enabled=True,
            error=last_error or "all configured estimate providers failed",
        )

    payload = attach_provider_metadata(
        payload,
        selected_provider=selected_provider,
        provider_chain=provider_chain,
        provider_attempts=provider_attempts,
        fallback_kind=str(payload.get("fallback_kind", "") or ""),
    )
    print(dump_json(target_path, payload))


if __name__ == "__main__":
    main()
