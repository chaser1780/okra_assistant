from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

try:
    from ui_support import read_json
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ui_support import read_json


RANGE_LABELS = ["近1月", "近3月", "近6月", "近1年", "成立以来"]
RANGE_DAYS = {
    "近1月": 31,
    "近3月": 93,
    "近6月": 186,
    "近1年": 366,
    "成立以来": None,
}


@dataclass
class SeriesPoint:
    date: str
    value: float


@dataclass
class TradeMarker:
    date: str
    action: str
    amount: float
    fund_code: str
    fund_name: str


def _parse_date(text: str) -> date | None:
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _filter_points(points: list[SeriesPoint], range_label: str) -> list[SeriesPoint]:
    if range_label not in RANGE_DAYS or not points:
        return points
    days = RANGE_DAYS[range_label]
    if days is None:
        return points
    end = _parse_date(points[-1].date)
    if end is None:
        return points
    start = end - timedelta(days=days)
    return [point for point in points if (_parse_date(point.date) or end) >= start]


def _normalize(points: list[SeriesPoint], base: float = 100.0) -> list[SeriesPoint]:
    if not points:
        return []
    first = points[0].value
    if first == 0:
        return []
    return [SeriesPoint(point.date, round(point.value / first * base, 4)) for point in points]


def collect_quote_history(home: Path, fund_code: str, range_label: str = "成立以来") -> dict:
    stored_path = home / "db" / "fund_nav_history" / f"{fund_code}.json"
    stored = read_json(stored_path, {})
    if stored:
        items = stored.get("items", []) or []
        nav = [SeriesPoint(item.get("date", ""), float(item.get("nav", 0) or 0)) for item in items if item.get("date") and item.get("nav") not in (None, "")]
        daily = [SeriesPoint(item.get("date", ""), float(item.get("day_change_pct", 0) or 0)) for item in items if item.get("date") and item.get("day_change_pct") not in (None, "")]
        nav = _filter_points(nav, range_label)
        daily = _filter_points(daily, range_label)
        week = []
        month = []
        for idx, point in enumerate(nav):
            if idx >= 5:
                week.append(SeriesPoint(point.date, round((point.value / nav[idx - 5].value - 1) * 100, 2) if nav[idx - 5].value else 0.0))
            if idx >= 21:
                month.append(SeriesPoint(point.date, round((point.value / nav[idx - 21].value - 1) * 100, 2) if nav[idx - 21].value else 0.0))
        week = _filter_points(week, range_label)
        month = _filter_points(month, range_label)
        return {
            "nav": nav,
            "nav_normalized": _normalize(nav),
            "day_change_pct": daily,
            "week_change_pct": week,
            "month_change_pct": month,
            "source": "fund_nav_history",
        }

    rows: list[SeriesPoint] = []
    daily: list[SeriesPoint] = []
    week: list[SeriesPoint] = []
    month: list[SeriesPoint] = []
    for path in sorted((home / "raw" / "quotes").glob("*.json")):
        payload = read_json(path, {})
        for item in payload.get("funds", []) or []:
            if item.get("code") != fund_code:
                continue
            quote_date = item.get("requested_date") or item.get("report_date") or path.stem
            if item.get("nav") not in (None, ""):
                rows.append(SeriesPoint(quote_date, float(item.get("nav", 0) or 0)))
            if item.get("day_change_pct") not in (None, ""):
                daily.append(SeriesPoint(quote_date, float(item.get("day_change_pct", 0) or 0)))
            if item.get("week_change_pct") not in (None, ""):
                week.append(SeriesPoint(quote_date, float(item.get("week_change_pct", 0) or 0)))
            if item.get("month_change_pct") not in (None, ""):
                month.append(SeriesPoint(quote_date, float(item.get("month_change_pct", 0) or 0)))
            break
    rows = _filter_points(rows, range_label)
    daily = _filter_points(daily, range_label)
    week = _filter_points(week, range_label)
    month = _filter_points(month, range_label)
    return {
        "nav": rows,
        "nav_normalized": _normalize(rows),
        "day_change_pct": daily,
        "week_change_pct": week,
        "month_change_pct": month,
        "source": "raw_quotes_fallback",
    }


def collect_proxy_history(home: Path, fund_code: str, range_label: str = "成立以来") -> dict:
    mapping = load_benchmark_mapping(home, fund_code)
    proxy_symbol = str(mapping.get("proxy_symbol", "") or "").strip()
    if proxy_symbol:
        stored_path = home / "db" / "proxy_history" / f"{proxy_symbol}.json"
        stored = read_json(stored_path, {})
        if stored:
            items = stored.get("items", []) or []
            if items and "nav" in items[0]:
                price = [SeriesPoint(item.get("date", ""), float(item.get("nav", 0) or 0)) for item in items if item.get("date") and item.get("nav") not in (None, "")]
            else:
                price = [SeriesPoint(item.get("date", ""), float(item.get("close", 0) or 0)) for item in items if item.get("date") and item.get("close") not in (None, "")]
            daily = [SeriesPoint(item.get("date", ""), float(item.get("change_pct", 0) or 0)) for item in items if item.get("date") and item.get("change_pct") not in (None, "")]
            price = _filter_points(price, range_label)
            daily = _filter_points(daily, range_label)
            return {
                "day_change_pct": daily,
                "normalized": _normalize(price),
                "source": "proxy_history",
                "name": stored.get("proxy_name") or stored.get("name", proxy_symbol),
            }

    daily: list[SeriesPoint] = []
    for path in sorted((home / "db" / "intraday_proxies").glob("*.json")):
        payload = read_json(path, {})
        for item in payload.get("proxies", []) or []:
            if item.get("proxy_fund_code") != fund_code:
                continue
            daily.append(SeriesPoint(path.stem[:10], float(item.get("change_pct", 0) or 0)))
            break
    daily = _filter_points(daily, range_label)
    normalized: list[SeriesPoint] = []
    base = 100.0
    for point in daily:
        base = round(base * (1 + point.value / 100.0), 4)
        normalized.append(SeriesPoint(point.date, base))
    return {
        "day_change_pct": daily,
        "normalized": normalized,
        "source": "intraday_proxies_fallback",
    }


def collect_benchmark_history(home: Path, benchmark_key: str, range_label: str = "成立以来") -> dict:
    if not benchmark_key:
        return {"price": [], "normalized": [], "change_pct": [], "source": "none"}
    stored_path = home / "db" / "benchmark_history" / f"{benchmark_key}.json"
    stored = read_json(stored_path, {})
    if not stored:
        return {"price": [], "normalized": [], "change_pct": [], "source": "missing"}
    items = stored.get("items", []) or []
    if items and "nav" in items[0]:
        price = [SeriesPoint(item.get("date", ""), float(item.get("nav", 0) or 0)) for item in items if item.get("date") and item.get("nav") not in (None, "")]
    else:
        price = [SeriesPoint(item.get("date", ""), float(item.get("close", 0) or 0)) for item in items if item.get("date") and item.get("close") not in (None, "")]
    change = [SeriesPoint(item.get("date", ""), float(item.get("change_pct", 0) or 0)) for item in items if item.get("date") and item.get("change_pct") not in (None, "")]
    price = _filter_points(price, range_label)
    change = _filter_points(change, range_label)
    return {
        "price": price,
        "normalized": _normalize(price),
        "change_pct": change,
        "source": "benchmark_history",
        "name": stored.get("benchmark_name") or stored.get("name", ""),
    }


def collect_estimate_history(home: Path, fund_code: str, range_label: str = "成立以来") -> list[SeriesPoint]:
    points: list[SeriesPoint] = []
    for path in sorted((home / "db" / "estimated_nav").glob("*.json")):
        payload = read_json(path, {})
        for item in payload.get("items", []) or []:
            if item.get("fund_code") == fund_code and item.get("estimate_change_pct") not in (None, ""):
                points.append(SeriesPoint(path.stem[:10], float(item.get("estimate_change_pct", 0) or 0)))
                break
    return _filter_points(points, range_label)


def collect_portfolio_history(home: Path, range_label: str = "成立以来") -> dict:
    total_value: list[SeriesPoint] = []
    pnl: list[SeriesPoint] = []
    return_pct: list[SeriesPoint] = []
    for path in sorted((home / "db" / "portfolio_state" / "snapshots").glob("*.json")):
        payload = read_json(path, {})
        current_total = float(payload.get("total_value", 0) or 0)
        current_pnl = float(payload.get("holding_pnl", 0) or 0)
        cost_basis = current_total - current_pnl
        current_return = round((current_pnl / cost_basis) * 100, 4) if cost_basis > 0 else 0.0
        total_value.append(SeriesPoint(path.stem[:10], current_total))
        pnl.append(SeriesPoint(path.stem[:10], current_pnl))
        return_pct.append(SeriesPoint(path.stem[:10], current_return))
    total_value = _filter_points(total_value, range_label)
    pnl = _filter_points(pnl, range_label)
    return_pct = _filter_points(return_pct, range_label)
    return {
        "total_value": total_value,
        "holding_pnl": pnl,
        "holding_return_pct": return_pct,
        "total_value_normalized": _normalize(total_value),
    }


def collect_holding_history(home: Path, fund_code: str, range_label: str = "成立以来") -> dict:
    value_points: list[SeriesPoint] = []
    pnl_points: list[SeriesPoint] = []
    return_points: list[SeriesPoint] = []
    units_points: list[SeriesPoint] = []
    for path in sorted((home / "db" / "portfolio_state" / "snapshots").glob("*.json")):
        payload = read_json(path, {})
        for fund in payload.get("funds", []) or []:
            if fund.get("fund_code") != fund_code:
                continue
            value_points.append(SeriesPoint(path.stem[:10], float(fund.get("current_value", 0) or 0)))
            pnl_points.append(SeriesPoint(path.stem[:10], float(fund.get("holding_pnl", 0) or 0)))
            return_points.append(SeriesPoint(path.stem[:10], float(fund.get("holding_return_pct", 0) or 0)))
            units_points.append(SeriesPoint(path.stem[:10], float(fund.get("holding_units", 0) or 0)))
            break
    return {
        "current_value": _filter_points(value_points, range_label),
        "holding_pnl": _filter_points(pnl_points, range_label),
        "holding_return_pct": _filter_points(return_points, range_label),
        "holding_units": _filter_points(units_points, range_label),
    }


def collect_trade_markers(home: Path, fund_code: str | None = None, range_label: str = "成立以来") -> list[TradeMarker]:
    markers: list[TradeMarker] = []
    for path in sorted((home / "db" / "trade_journal").glob("*.json")):
        payload = read_json(path, {})
        trade_date = payload.get("trade_date") or path.stem[:10]
        for item in payload.get("items", []) or []:
            if fund_code and item.get("fund_code") != fund_code:
                continue
            markers.append(
                TradeMarker(
                    date=trade_date,
                    action=str(item.get("action", "") or ""),
                    amount=float(item.get("amount", 0) or 0),
                    fund_code=str(item.get("fund_code", "") or ""),
                    fund_name=str(item.get("fund_name", "") or ""),
                )
            )
    if not markers:
        return []
    points = [SeriesPoint(marker.date, 0.0) for marker in markers]
    filtered = _filter_points(points, range_label)
    allowed = {point.date for point in filtered}
    return [marker for marker in markers if marker.date in allowed]


def stage_return(points: list[SeriesPoint]) -> str:
    if not points or len(points) < 2 or points[0].value == 0:
        return "—"
    start = points[0].value
    end = points[-1].value
    return f"{((end / start) - 1) * 100:.2f}%"


def load_benchmark_mapping(home: Path, fund_code: str) -> dict:
    payload = read_json(home / "config" / "benchmark_mappings.json", {"fund_benchmarks": {}})
    return (payload.get("fund_benchmarks", {}) or {}).get(fund_code, {})
