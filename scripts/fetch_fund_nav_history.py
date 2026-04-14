from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import local

import requests

from common import dump_json, ensure_layout, fund_nav_history_path, load_watchlist, resolve_agent_home, timestamp_now

EASTMONEY_NAV_API = "https://api.fund.eastmoney.com/f10/lsjz"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36",
    "Referer": "https://fundf10.eastmoney.com/",
}
_SESSION_LOCAL = local()


def safe_float(value):
    try:
        if value in (None, "", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def get_session() -> requests.Session:
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.trust_env = False
        session.headers.update(DEFAULT_HEADERS)
        _SESSION_LOCAL.session = session
    return session


def get_json_with_retry(session: requests.Session, params: dict, max_attempts: int = 3) -> dict:
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(EASTMONEY_NAV_API, params=params, timeout=20)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"Failed to fetch fund nav history: {last_error}")


def fetch_all_rows(session: requests.Session, fund_code: str, page_size: int = 20, max_pages: int = 500) -> list[dict]:
    rows: list[dict] = []
    seen_dates: set[str] = set()
    for page_index in range(1, max_pages + 1):
        payload = get_json_with_retry(
            session,
            {
                "fundCode": fund_code,
                "pageIndex": page_index,
                "pageSize": page_size,
                "startDate": "",
                "endDate": "",
            },
        )
        data = payload.get("Data", {}) or {}
        page_rows = list(data.get("LSJZList", []) or [])
        if not page_rows:
            break
        new_rows = []
        for row in page_rows:
            row_date = str(row.get("FSRQ", "")).strip()
            if row_date and row_date not in seen_dates:
                seen_dates.add(row_date)
                new_rows.append(row)
        if not new_rows:
            break
        rows.extend(new_rows)
    rows.sort(key=lambda item: datetime.strptime(item.get("FSRQ", "1900-01-01"), "%Y-%m-%d"))
    return rows


def build_history_payload(fund: dict) -> dict:
    session = get_session()
    rows = fetch_all_rows(session, fund["code"])
    items = []
    for row in rows:
        items.append(
            {
                "date": row.get("FSRQ", ""),
                "nav": safe_float(row.get("DWJZ")),
                "cumulative_nav": safe_float(row.get("LJJZ")),
                "day_change_pct": safe_float(row.get("JZZZL")),
                "purchase_status": row.get("SGZT", ""),
                "redeem_status": row.get("SHZT", ""),
            }
        )
    valid_dates = [item["date"] for item in items if item.get("date")]
    return {
        "fund_code": fund["code"],
        "fund_name": fund["name"],
        "category": fund.get("category", "unknown"),
        "benchmark": fund.get("benchmark", ""),
        "provider": "eastmoney_nav_api",
        "generated_at": timestamp_now(),
        "first_date": valid_dates[0] if valid_dates else "",
        "last_date": valid_dates[-1] if valid_dates else "",
        "item_count": len(items),
        "items": items,
    }


def process_one(agent_home, fund: dict) -> str:
    payload = build_history_payload(fund)
    return str(dump_json(fund_nav_history_path(agent_home, fund["code"]), payload))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch full official NAV history for watchlist funds.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--only", nargs="*", help="Restrict to specific fund codes.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    watchlist = load_watchlist(agent_home).get("funds", []) or []
    selected = set(args.only or [])
    funds = [fund for fund in watchlist if not selected or fund.get("code") in selected]

    outputs: list[str] = []
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(funds)))) as executor:
        futures = {executor.submit(process_one, agent_home, fund): fund for fund in funds}
        for future in as_completed(futures):
            outputs.append(future.result())

    for path in sorted(outputs):
        print(path)


if __name__ == "__main__":
    main()
