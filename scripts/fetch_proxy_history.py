from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests

from common import benchmark_history_path, dump_json, ensure_layout, load_benchmark_mappings, proxy_history_path, resolve_agent_home, timestamp_now

EASTMONEY_NAV_API = "https://api.fund.eastmoney.com/f10/lsjz"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36",
    "Referer": "https://fundf10.eastmoney.com/",
}


def get_json_with_retry(code: str, page_index: int, page_size: int = 20, max_attempts: int = 4) -> dict:
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
    raise RuntimeError(f"Failed to fetch proxy history for {code}: {last_error}")


def fetch_proxy_nav_history(symbol: str) -> dict:
    code = (symbol or "").strip().lower()
    if code.startswith(("sh", "sz")):
        code = code[2:]
    rows: list[dict] = []
    seen_dates: set[str] = set()
    for page_index in range(1, 500 + 1):
        payload = get_json_with_retry(code, page_index, page_size=20)
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
        raise RuntimeError("empty proxy nav history")

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


def process_one(agent_home, proxy_symbol: str, proxy_name: str) -> str:
    benchmark_path = benchmark_history_path(agent_home, proxy_symbol)
    if benchmark_path.exists():
        payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
        payload["generated_at"] = timestamp_now()
        payload["provider"] = payload.get("provider", "eastmoney_nav_api")
    else:
        payload = fetch_proxy_nav_history(proxy_symbol)
    payload["proxy_symbol"] = proxy_symbol
    payload["proxy_name"] = proxy_name
    return str(dump_json(proxy_history_path(agent_home, proxy_symbol), payload))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch full proxy history based on benchmark mappings.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--only", nargs="*", help="Restrict to specific proxy symbols.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    mappings = load_benchmark_mappings(agent_home).get("fund_benchmarks", {}) or {}
    proxies: dict[str, str] = {}
    for item in mappings.values():
        symbol = str(item.get("proxy_symbol", "") or "").strip()
        if symbol:
            proxies[symbol] = str(item.get("proxy_name", symbol))
    selected = set(args.only or [])
    outputs: list[str] = []
    failures: list[str] = []
    for symbol, name in proxies.items():
        if selected and symbol not in selected:
            continue
        try:
            outputs.append(process_one(agent_home, symbol, name))
        except Exception as exc:
            failures.append(f"{symbol}: {exc}")
    for path in sorted(outputs):
        print(path)
    if failures:
        print(json.dumps({"failed": failures}, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
