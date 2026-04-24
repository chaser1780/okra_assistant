from __future__ import annotations

import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import local

import requests
from bs4 import BeautifulSoup

from common import dump_json, ensure_layout, fund_profile_path, load_watchlist, resolve_agent_home, resolve_date, timestamp_now
from models import FundProfile
from provider_adapters import build_provider_result


PROFILE_URL = "https://fundf10.eastmoney.com/jbgk_{code}.html"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36",
    "Referer": "https://fund.eastmoney.com/",
}
_SESSION_LOCAL = local()


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def extract_text(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def extract_float(pattern: str, text: str) -> float | None:
    value = extract_text(pattern, text)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def profile_age_years(inception_date: str | None, report_date: str) -> float | None:
    if not inception_date:
        return None
    try:
        start = datetime.strptime(inception_date, "%Y-%m-%d").date()
        end = datetime.strptime(report_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    return round((end - start).days / 365.25, 2)


def scale_bucket(scale: float | None) -> str:
    if scale is None:
        return "unknown"
    if scale < 5:
        return "small"
    if scale < 20:
        return "medium"
    return "large"


def fee_level(management_fee: float | None, custody_fee: float | None) -> str:
    total = float(management_fee or 0.0) + float(custody_fee or 0.0)
    if total <= 0.3:
        return "low"
    if total <= 1.2:
        return "medium"
    return "high"


def style_drift_risk(category: str, fund_age: float | None) -> str:
    if category in {"active_equity"}:
        if fund_age is None or fund_age < 1:
            return "high"
        if fund_age < 3:
            return "medium"
        return "medium"
    if category in {"qdii_index", "index_equity", "etf_linked"}:
        return "low"
    return "medium"


def parse_profile_html(html: str, fund_or_code, fund_name: str | None = None, report_date: str | None = None) -> FundProfile:
    if isinstance(fund_or_code, dict):
        fund = fund_or_code
        effective_report_date = report_date or fund_name or datetime.now().date().isoformat()
    else:
        fund = {"code": fund_or_code, "name": fund_name or "", "category": "unknown", "benchmark": "", "risk_level": ""}
        effective_report_date = report_date or datetime.now().date().isoformat()
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_text(soup.get_text(" ", strip=True))
    inception_date = extract_text(r"成立日期[:：]\s*(\d{4}-\d{2}-\d{2})", text)
    fund_manager = extract_text(r"基金经理[:：]\s*([^\s]+)", text)
    fund_type = extract_text(r"类型[:：]\s*([^\s]+)", text)
    management_company = extract_text(r"管理人[:：]\s*([^\s]+)", text)
    scale = extract_float(r"基金规模[:：]\s*([\d.]+)亿元", text)
    management_fee = extract_float(r"管理费率[:：]\s*([\d.]+)%", text)
    custody_fee = extract_float(r"托管费率[:：]\s*([\d.]+)%", text)
    fund_age = profile_age_years(inception_date, effective_report_date)
    category = fund.get("category", "unknown")
    return {
        "fund_code": fund["code"],
        "fund_name": fund["name"],
        "inception_date": inception_date,
        "fund_age_years": fund_age,
        "fund_manager": fund_manager,
        "fund_type": fund_type,
        "management_company": management_company,
        "fund_scale_billion": scale,
        "management_fee_rate": management_fee,
        "custody_fee_rate": custody_fee,
        "category": category,
        "benchmark": fund.get("benchmark", ""),
        "risk_level": fund.get("risk_level", ""),
        "manager_tenure_years": fund_age if fund_manager else None,
        "fund_scale_bucket": scale_bucket(scale),
        "fee_level": fee_level(management_fee, custody_fee),
        "style_drift_risk": style_drift_risk(category, fund_age),
        "slow_factor_summary": [
            f"规模={scale_bucket(scale)}",
            f"费率={fee_level(management_fee, custody_fee)}",
            f"风格漂移风险={style_drift_risk(category, fund_age)}",
        ],
        "profile_source": "eastmoney_jbgk",
        "status": "ok",
        "source_url": PROFILE_URL.format(code=fund["code"]),
        "source_title": fund["name"],
        "provider": "eastmoney_jbgk",
        "as_of": effective_report_date,
        "retrieved_at": timestamp_now(),
    }


def fetch_one_profile(fund: dict, report_date: str) -> FundProfile:
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.trust_env = False
        session.headers.update(DEFAULT_HEADERS)
        _SESSION_LOCAL.session = session
    try:
        response = session.get(PROFILE_URL.format(code=fund["code"]), timeout=30)
        response.raise_for_status()
        response.encoding = "utf-8"
        return parse_profile_html(response.text, fund, report_date=report_date)
    except Exception as exc:
        return {
            "fund_code": fund["code"],
            "fund_name": fund["name"],
            "inception_date": None,
            "fund_age_years": None,
            "fund_manager": None,
            "fund_type": None,
            "management_company": None,
            "fund_scale_billion": None,
            "management_fee_rate": None,
            "custody_fee_rate": None,
            "category": fund.get("category", "unknown"),
            "benchmark": fund.get("benchmark", ""),
            "risk_level": fund.get("risk_level", ""),
            "manager_tenure_years": None,
            "fund_scale_bucket": "unknown",
            "fee_level": "unknown",
            "style_drift_risk": "unknown",
            "slow_factor_summary": [],
            "profile_source": "eastmoney_jbgk",
            "status": f"error: {exc}",
            "source_url": PROFILE_URL.format(code=fund["code"]),
            "source_title": fund["name"],
            "provider": "eastmoney_jbgk",
            "as_of": report_date,
            "retrieved_at": timestamp_now(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch slow-moving fund profile fields from Eastmoney basic profile pages.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    watchlist = load_watchlist(agent_home)

    items_by_index: dict[int, FundProfile] = {}
    workers = min(4, max(1, len(watchlist.get("funds", []))))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_one_profile, fund, report_date): index
            for index, fund in enumerate(watchlist.get("funds", []))
        }
        for future in as_completed(futures):
            items_by_index[futures[future]] = future.result()

    payload = {
        "report_date": report_date,
        "provider": "eastmoney_jbgk",
        "generated_at": timestamp_now(),
        "items": [items_by_index[index] for index in sorted(items_by_index)],
    }
    payload = build_provider_result(payload, provider_name="eastmoney_jbgk")
    print(dump_json(fund_profile_path(agent_home, report_date), payload))


if __name__ == "__main__":
    main()
