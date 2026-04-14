from __future__ import annotations

import argparse
import re
import time

import requests

from common import classify_intraday_freshness, dump_json, ensure_layout, intraday_proxy_path, load_json, load_portfolio, load_settings, resolve_agent_home, resolve_date, timestamp_now
from provider_adapters import build_provider_payload, resolve_provider_config, stale_fallback_payload

SINA_HQ_URL = "https://hq.sinajs.cn/list="
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn/",
}
LINE_PATTERN = re.compile(r'^var\s+hq_str_(?P<symbol>[^=]+)="(?P<body>.*)";$')
DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
TIME_PATTERN = re.compile(r'^\d{2}:\d{2}:\d{2}$')


def round2(value: float) -> float:
    return round(value, 2)


def build_demo_payload(portfolio: dict, report_date: str) -> dict:
    proxies = []
    for index, fund in enumerate(portfolio["funds"]):
        proxy_symbol = fund.get("proxy_symbol")
        if not proxy_symbol:
            continue
        change_pct = round((index - 5) * 0.31, 2)
        proxies.append(
            {
                "symbol": proxy_symbol,
                "name": fund.get("proxy_name", proxy_symbol),
                "current": round(1.0 + index * 0.017, 4),
                "prev_close": round(1.0 + index * 0.014, 4),
                "change_pct": change_pct,
                "trade_date": report_date,
                "trade_time": "14:15:00",
                "stale": False,
                "freshness_status": "same_day",
                "freshness_label": "代理行情为当日",
                "freshness_business_day_gap": 0,
                "proxy_type": fund.get("proxy_type", "etf"),
                "style_group": fund.get("style_group", "unknown"),
                "proxy_fund_code": fund["fund_code"],
                "proxy_fund_name": fund["fund_name"],
                "proxy_name": fund.get("proxy_name", proxy_symbol),
            }
        )
    return {"report_date": report_date, "provider": "demo_intraday_proxy", "generated_at": timestamp_now(), "proxies": proxies}


def parse_trade_markers(parts: list[str]) -> tuple[str, str]:
    trade_date = ""
    trade_time = ""
    for index, value in enumerate(parts):
        if DATE_PATTERN.match(value):
            trade_date = value
            if index + 1 < len(parts) and TIME_PATTERN.match(parts[index + 1]):
                trade_time = parts[index + 1]
            break
    return trade_date, trade_time


def parse_equity_line(symbol: str, body: str) -> dict | None:
    parts = body.split(",")
    if len(parts) < 10 or not parts[0]:
        return None
    try:
        prev_close = float(parts[2])
        current = float(parts[3])
        open_price = float(parts[1]) if parts[1] else prev_close
        high = float(parts[4]) if parts[4] else current
        low = float(parts[5]) if parts[5] else current
    except ValueError:
        return None

    trade_date, trade_time = parse_trade_markers(parts)
    change_pct = round2((current / prev_close - 1) * 100) if prev_close else 0.0
    return {
        "symbol": symbol,
        "name": parts[0],
        "open": open_price,
        "current": current,
        "prev_close": prev_close,
        "high": high,
        "low": low,
        "volume": float(parts[8]) if parts[8] else 0.0,
        "amount": float(parts[9]) if parts[9] else 0.0,
        "change_pct": change_pct,
        "trade_date": trade_date,
        "trade_time": trade_time,
    }


def fetch_quotes(symbols: list[str], max_attempts: int = 3) -> dict[str, dict]:
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(SINA_HQ_URL + ",".join(symbols), timeout=20, headers=DEFAULT_HEADERS)
            response.raise_for_status()
            response.encoding = "gbk"
            parsed: dict[str, dict] = {}
            for raw_line in response.text.strip().splitlines():
                match = LINE_PATTERN.match(raw_line.strip())
                if not match:
                    continue
                item = parse_equity_line(match.group("symbol"), match.group("body"))
                if item:
                    parsed[item["symbol"]] = item
            if parsed:
                return parsed
            raise RuntimeError("No proxy quotes parsed from Sina HQ response.")
        except Exception as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"Failed to fetch intraday proxy quotes: {last_error}")


def attach_fund_meta(portfolio: dict, quote_map: dict[str, dict], report_date: str, stale_override: bool = False) -> list[dict]:
    proxies = []
    for fund in portfolio["funds"]:
        proxy_symbol = fund.get("proxy_symbol")
        if not proxy_symbol:
            continue
        item = quote_map.get(proxy_symbol)
        if not item:
            continue
        freshness = classify_intraday_freshness(report_date, item.get("trade_date"), "代理行情")
        proxies.append(
            {
                **item,
                "proxy_type": fund.get("proxy_type", "etf"),
                "style_group": fund.get("style_group", "unknown"),
                "proxy_fund_code": fund["fund_code"],
                "proxy_fund_name": fund["fund_name"],
                "proxy_name": fund.get("proxy_name", item["name"]),
                "stale": stale_override or freshness["is_stale"],
                "freshness_status": "cross_day" if stale_override and freshness["status"] == "same_day" else freshness["status"],
                "freshness_label": "代理行情沿用旧快照" if stale_override else freshness["label"],
                "freshness_business_day_gap": freshness["business_day_gap"],
            }
        )
    return proxies


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch intraday proxy quotes for portfolio holdings.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--provider", help="Override the configured proxy provider name.")
    parser.add_argument("--demo", action="store_true", help="Write deterministic mock proxy data.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    settings = load_settings(agent_home)
    report_date = resolve_date(args.date)
    provider_config = resolve_provider_config(settings, "intraday_proxy", args.provider)
    provider = provider_config.name
    portfolio = load_portfolio(agent_home)

    if args.demo or provider.startswith("demo"):
        payload = build_demo_payload(portfolio, report_date)
        payload["provider"] = provider
    else:
        symbols = sorted({fund["proxy_symbol"] for fund in portfolio["funds"] if fund.get("proxy_symbol")})
        try:
            quote_map = fetch_quotes(symbols)
            proxies = attach_fund_meta(portfolio, quote_map, report_date)
            payload = build_provider_payload(report_date, provider, "proxies", proxies)
        except Exception as exc:
            fallback_path = intraday_proxy_path(agent_home, report_date)
            if fallback_path.exists():
                payload = stale_fallback_payload(load_json(fallback_path), f"{provider}_fallback", "proxies", str(exc))
                for item in payload.get("proxies", []):
                    item["freshness_status"] = "cross_day"
                    item["freshness_label"] = "代理行情抓取失败，沿用旧快照"
            else:
                payload = build_provider_payload(report_date, f"{provider}_unavailable", "proxies", [])

    print(dump_json(intraday_proxy_path(agent_home, report_date), payload))


if __name__ == "__main__":
    main()
