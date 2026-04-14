from __future__ import annotations

import argparse
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from threading import local

import requests
from bs4 import BeautifulSoup

from common import dump_json, ensure_layout, load_settings, load_watchlist, news_path, resolve_agent_home, resolve_date, timestamp_now
from provider_adapters import build_provider_payload, resolve_provider_config

EASTMONEY_NOTICE_API = "https://api.fund.eastmoney.com/f10/JJGG"
EASTMONEY_FUND_PAGE = "https://fund.eastmoney.com/{code}.html"
CN_TZ = timezone(timedelta(hours=8))
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36",
    "Referer": "https://fund.eastmoney.com/",
}
_SESSION_LOCAL = local()
NOTICE_CATEGORY_MAP = {"1": "发行运作", "2": "分红送配", "3": "定期报告", "4": "人事调整", "5": "基金销售", "6": "其他公告"}
NEGATIVE_KEYWORDS = ("风险", "下调", "离任", "清盘", "终止", "停牌", "处罚", "违约", "预警", "大幅回撤", "限制")
POSITIVE_KEYWORDS = ("分红", "增持", "上调", "获批", "成立", "开放", "扩募", "利好")


def infer_impact(title: str) -> str:
    if any(keyword in title for keyword in NEGATIVE_KEYWORDS):
        return "negative"
    if any(keyword in title for keyword in POSITIVE_KEYWORDS):
        return "positive"
    return "neutral"


def parse_article_timestamp(article_url: str) -> str | None:
    match = re.search(r"/news/(\d{14})", article_url)
    if not match:
        return None
    dt = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=CN_TZ)
    return dt.isoformat(timespec="seconds")


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    if len(candidate) == 10:
        candidate = f"{candidate}T00:00:00+08:00"
    elif candidate.endswith("T00:00:00"):
        candidate = candidate + "+08:00"
    return datetime.fromisoformat(candidate)


def within_lookback(published_at: str | None, report_date: str, lookback_hours: int) -> bool:
    published_dt = parse_iso_datetime(published_at)
    if published_dt is None:
        return True
    report_end = datetime.fromisoformat(f"{report_date}T23:59:59+08:00")
    return published_dt >= report_end - timedelta(hours=lookback_hours)


def get_response_with_retry(session: requests.Session, url: str, *, timeout_seconds: int, max_attempts: int = 3, **kwargs) -> requests.Response:
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(url, timeout=timeout_seconds, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"Failed to fetch from {url}: {last_error}")


def fetch_notice_items(session: requests.Session, fund: dict, settings: dict, report_date: str) -> list[dict]:
    provider_settings = settings["providers"]["news"]
    timeout_seconds = int(provider_settings.get("timeout_seconds", 15))
    page_size = int(provider_settings.get("max_notices", 4))
    lookback_hours = int(provider_settings.get("lookback_hours", 72))
    response = get_response_with_retry(
        session,
        EASTMONEY_NOTICE_API,
        timeout_seconds=timeout_seconds,
        params={"fundcode": fund["code"], "pageIndex": 1, "pageSize": page_size, "type": 0},
        headers={"Referer": f"https://fundf10.eastmoney.com/jjgg_{fund['code']}.html"},
    )
    payload = response.json()
    items = []
    for item in payload.get("Data", []):
        published_at = item.get("PUBLISHDATE")
        if published_at and published_at.endswith("T00:00:00"):
            published_at = published_at + "+08:00"
        if not within_lookback(published_at, report_date, lookback_hours):
            continue
        category = NOTICE_CATEGORY_MAP.get(item.get("NEWCATEGORY", ""), "基金公告")
        title = item.get("TITLE", "")
        items.append({
            "code": fund["code"],
            "name": fund["name"],
            "published_at": published_at or f"{item.get('PUBLISHDATEDesc', report_date)}T00:00:00+08:00",
            "title": title,
            "summary": f"基金公告，分类：{category}。",
            "source_name": "eastmoney_notice",
            "url": f"http://fund.eastmoney.com/gonggao/{fund['code']},{item.get('ID', '')}.html",
            "impact": infer_impact(title),
            "relevance_score": 0.95,
        })
    return items


def fetch_article_items(session: requests.Session, fund: dict, settings: dict, report_date: str) -> list[dict]:
    provider_settings = settings["providers"]["news"]
    timeout_seconds = int(provider_settings.get("timeout_seconds", 15))
    max_articles = int(provider_settings.get("max_articles", 3))
    lookback_hours = int(provider_settings.get("lookback_hours", 72))
    response = get_response_with_retry(session, EASTMONEY_FUND_PAGE.format(code=fund["code"]), timeout_seconds=timeout_seconds)
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    anchors = soup.select('li.cfh-new a[href*="caifuhao.eastmoney.com/news/"]')
    seen = set()
    items = []
    for anchor in anchors:
        href = anchor.get("href", "").strip()
        title = anchor.get("title") or " ".join(anchor.get_text(" ", strip=True).split())
        if not href or not title:
            continue
        key = (href, title)
        if key in seen:
            continue
        seen.add(key)
        published_at = parse_article_timestamp(href)
        if not within_lookback(published_at, report_date, lookback_hours):
            continue
        items.append({
            "code": fund["code"],
            "name": fund["name"],
            "published_at": published_at or timestamp_now(),
            "title": title,
            "summary": "基金主页相关文章；发布时间优先从官方文章 URL 中解析。",
            "source_name": "eastmoney_article",
            "url": href,
            "impact": infer_impact(title),
            "relevance_score": 0.72,
        })
        if len(items) >= max_articles:
            break
    return items


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


def fetch_one_fund_news(fund: dict, settings: dict, report_date: str) -> list[dict]:
    session = get_thread_session()
    items: list[dict] = []
    items.extend(fetch_notice_items(session, fund, settings, report_date))
    items.extend(fetch_article_items(session, fund, settings, report_date))
    return items


def build_demo_news(watchlist: dict, report_date: str) -> list[dict]:
    impact_cycle = ["positive", "neutral", "negative"]
    items = []
    for index, fund in enumerate(watchlist["funds"]):
        primary_impact = impact_cycle[index % len(impact_cycle)]
        secondary_impact = impact_cycle[(index + 1) % len(impact_cycle)]
        items.append({
            "code": fund["code"],
            "name": fund["name"],
            "published_at": f"{report_date}T08:30:00+08:00",
            "title": f"{fund['name']}：市场关注度与资金流向示例更新",
            "summary": "示例新闻，用于打通基金新闻抓取、摘要和评分链路。",
            "source_name": "demo_finance_wire",
            "url": f"https://example.com/funds/{fund['code']}/headline-1",
            "impact": primary_impact,
            "relevance_score": round(0.82 - index * 0.08, 2),
        })
        items.append({
            "code": fund["code"],
            "name": fund["name"],
            "published_at": f"{report_date}T13:30:00+08:00",
            "title": f"{fund['name']}：基金经理观点与行业景气度示例摘要",
            "summary": "第二条示例新闻，用于验证多条新闻合并和风险提示逻辑。",
            "source_name": "demo_finance_wire",
            "url": f"https://example.com/funds/{fund['code']}/headline-2",
            "impact": secondary_impact,
            "relevance_score": round(0.71 - index * 0.06, 2),
        })
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch daily fund news from Eastmoney or emit a demo payload.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--provider", help="Override the configured news provider name.")
    parser.add_argument("--demo", action="store_true", help="Write deterministic mock data.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    settings = load_settings(agent_home)
    watchlist = load_watchlist(agent_home)
    report_date = resolve_date(args.date)
    provider_config = resolve_provider_config(settings, "news", args.provider)
    provider = provider_config.name

    if args.demo or provider.startswith("demo"):
        payload = build_provider_payload(report_date, provider, "items", build_demo_news(watchlist, report_date))
    else:
        if provider not in {"eastmoney_notice_and_articles", "eastmoney"}:
            raise SystemExit(f"Unsupported news provider: {provider}")
        all_items = []
        workers = min(6, max(1, len(watchlist["funds"])))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_one_fund_news, fund, settings, report_date): fund for fund in watchlist["funds"]}
            for future in as_completed(futures):
                fund = futures[future]
                try:
                    all_items.extend(future.result())
                except Exception as exc:
                    all_items.append({
                        "code": fund["code"],
                        "name": fund["name"],
                        "published_at": timestamp_now(),
                        "title": f"{fund['name']}：新闻抓取失败占位记录",
                        "summary": f"抓取异常：{exc}",
                        "source_name": "system_placeholder",
                        "url": "",
                        "impact": "neutral",
                        "relevance_score": 0.1,
                    })
        all_items.sort(key=lambda item: item.get("published_at", ""), reverse=True)
        payload = build_provider_payload(report_date, provider, "items", all_items)

    print(dump_json(news_path(agent_home, report_date), payload))


if __name__ == "__main__":
    main()
