from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

import requests

from common import benchmark_history_path, dump_json, ensure_layout, load_benchmark_mappings, resolve_agent_home, timestamp_now

EASTMONEY_NAV_API = "https://api.fund.eastmoney.com/f10/lsjz"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36",
    "Referer": "https://fundf10.eastmoney.com/",
}


def get_json_with_retry(code: str, page_index: int, page_size: int = 200, max_attempts: int = 4) -> dict:
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(
                EASTMONEY_NAV_API,
                params={"fundCode": code, "pageIndex": page_index, "pageSize": page_size, "startDate": "", "endDate": ""},
                timeout=20,
                headers=DEFAULT_HEADERS,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError(f"unexpected payload type: {type(payload).__name__}")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(2.0 * attempt)
    raise RuntimeError(f"Failed to fetch benchmark history for {code}: {last_error}")


def fetch_nav_history(symbol: str, page_size: int = 20, max_pages: int = 500) -> dict:
    code = (symbol or "").strip().lower()
    if code.startswith(("sh", "sz")):
        code = code[2:]
    rows: list[dict] = []
    seen_dates: set[str] = set()
    for page_index in range(1, max_pages + 1):
        payload = get_json_with_retry(code, page_index, page_size=page_size)
        data = payload.get("Data", {})
        if not isinstance(data, dict):
            raise RuntimeError(f"unexpected Data type: {type(data).__name__}")
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
    if not rows:
        raise RuntimeError("empty benchmark nav history")

    rows.sort(key=lambda item: datetime.strptime(item.get("FSRQ", "1900-01-01"), "%Y-%m-%d"))
    items = []
    for row in rows:
        items.append(
            {
                "date": row.get("FSRQ", ""),
                "nav": float(row.get("DWJZ", 0) or 0),
                "cumulative_nav": float(row.get("LJJZ", 0) or 0),
                "change_pct": float(row.get("JZZZL", 0) or 0),
                "purchase_status": row.get("SGZT", ""),
                "redeem_status": row.get("SHZT", ""),
            }
        )
    return {
        "symbol": symbol,
        "name": code,
        "provider": "eastmoney_nav_api",
        "generated_at": timestamp_now(),
        "first_date": items[0]["date"] if items else "",
        "last_date": items[-1]["date"] if items else "",
        "item_count": len(items),
        "items": items,
    }


def process_one(agent_home, benchmark_key: str, benchmark_name: str, symbol: str) -> str:
    payload = fetch_nav_history(symbol)
    payload["benchmark_key"] = benchmark_key
    payload["benchmark_name"] = benchmark_name
    return str(dump_json(benchmark_history_path(agent_home, benchmark_key), payload))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch full benchmark history using Eastmoney fund NAV history API.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--only", nargs="*", help="Restrict to specific benchmark keys.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    mappings = load_benchmark_mappings(agent_home).get("fund_benchmarks", {}) or {}
    seen: dict[str, tuple[str, str]] = {}
    for item in mappings.values():
        symbol = str(item.get("benchmark_symbol", "") or "").strip()
        key = str(item.get("benchmark_key", "") or "").strip()
        if not symbol or not key:
            continue
        seen[key] = (str(item.get("benchmark_name", key)), symbol)
    selected = set(args.only or [])
    outputs: list[str] = []
    failures: list[str] = []
    for key, (name, symbol) in seen.items():
        if selected and key not in selected:
            continue
        try:
            outputs.append(process_one(agent_home, key, name, symbol))
        except Exception as exc:
            failures.append(f"{key}: {exc}")
    for path in sorted(outputs):
        print(path)
    if failures:
        print(json.dumps({"failed": failures}, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
