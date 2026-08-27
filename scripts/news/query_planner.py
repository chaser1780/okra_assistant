from __future__ import annotations

import html
import re
from collections import defaultdict
from typing import Any

from portfolio_exposure import infer_theme_family

FUND_NAME_NOISE = ("发起式", "联接", "指数", "混合", "持有", "债券", "基金", "人民币", "A", "C", "QDII", "ETF")
STYLE_KEYWORDS = {
    "ai": ["AI", "算力", "大模型", "机器人"],
    "grid_equipment": ["电网设备", "特高压", "新型电力系统", "电力设备"],
    "chemical": ["化工", "磷化工", "煤化工", "制冷剂"],
    "grain_agriculture": ["粮食", "农业", "种业", "农产品"],
    "industrial_metal": ["有色", "铜", "铝", "资源"],
    "sp500_core": ["标普", "标普500", "美股大盘"],
    "nasdaq_core": ["纳指", "纳斯达克", "美股科技"],
    "china_us_internet": ["中概", "中概互联网", "中美互联网", "港股科技"],
    "carbon_neutral": ["碳中和", "新能源", "储能", "电力改革"],
    "precious_metals": ["黄金", "贵金属"],
    "high_end_equipment": ["高端装备", "先进制造"],
    "growth_rotation": ["成长", "成长轮动"],
    "tech_growth": ["科技成长", "TMT", "科技股"],
}
THEME_FAMILY_KEYWORDS = {
    "global_growth": ["global growth", "美股成长", "海外科技"],
    "growth_cluster": ["growth cluster", "成长股", "科技成长"],
    "cyclical_resources": ["cyclical resources", "周期资源", "有色金属"],
    "energy_transition": ["energy transition", "能源转型", "新能源"],
    "advanced_manufacturing": ["先进制造", "机器人", "高端装备"],
    "domestic_defensive_theme": ["防御主题", "农业", "红利"],
    "commodity_hedge": ["商品对冲", "黄金", "贵金属"],
}
MARKET_KEYWORDS_BY_CATEGORY = {
    "qdii_index": ["美股", "汇率", "人民币", "纳指", "标普"],
    "etf_linked": ["A股", "行业政策", "ETF资金流"],
    "index_equity": ["A股", "指数行情", "行业轮动"],
}


def clean_keyword(value: str) -> str:
    text = html.unescape(str(value or "").strip())
    text = re.sub(r"[（(].*?[）)]", " ", text)
    for token in FUND_NAME_NOISE:
        text = text.replace(token, " ")
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", text)
    return " ".join(text.split()).strip()[:24]


def _add_query(bucket: dict[str, dict[str, Any]], keyword: str, *, fund: dict[str, Any], priority: int, query_type: str) -> None:
    keyword = clean_keyword(keyword) if query_type != "sentiment" else str(keyword or "").strip()[:24]
    if len(keyword) < 2:
        return
    key = keyword.lower()
    entry = bucket.setdefault(
        key,
        {
            "keyword": keyword,
            "fund_codes": set(),
            "fund_names": set(),
            "style_groups": set(),
            "theme_families": set(),
            "priority": priority,
            "query_type": query_type,
        },
    )
    code = str(fund.get("code") or fund.get("fund_code") or "").strip()
    name = str(fund.get("name") or fund.get("fund_name") or code).strip()
    style_group = str(fund.get("style_group", "") or "").strip()
    theme_family = str(fund.get("theme_family", "") or "").strip()
    if code:
        entry["fund_codes"].add(code)
    if name:
        entry["fund_names"].add(name)
    if style_group:
        entry["style_groups"].add(style_group)
    if theme_family:
        entry["theme_families"].add(theme_family)
    entry["priority"] = max(int(entry.get("priority", 0) or 0), priority)


def _merged_funds(portfolio: dict, watchlist: dict) -> list[dict[str, Any]]:
    holdings = {
        item.get("fund_code"): item
        for item in portfolio.get("funds", []) or []
        if float(item.get("current_value", 0.0) or 0.0) > 0 and item.get("role") not in {"cash_hub", "fixed_hold"}
    }
    watch_by_code = {item.get("code"): item for item in watchlist.get("funds", []) or []}
    funds: list[dict[str, Any]] = []
    for fund_code, holding in holdings.items():
        watch = watch_by_code.get(fund_code, {}) or {}
        merged = {
            **watch,
            "code": fund_code,
            "name": holding.get("fund_name", watch.get("name", fund_code)),
            "style_group": holding.get("style_group", watch.get("style_group", "")),
            "benchmark": watch.get("benchmark", ""),
            "category": watch.get("category", holding.get("category", "")),
            "role": holding.get("role", ""),
        }
        merged["theme_family"] = infer_theme_family(
            {
                "fund_code": fund_code,
                "fund_name": merged.get("name", ""),
                "style_group": merged.get("style_group", ""),
            }
        )
        funds.append(merged)
    return funds


def _rank_queries(items: dict[str, dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ranked = sorted(
        items.values(),
        key=lambda item: (-len(item["fund_codes"]), -int(item.get("priority", 0) or 0), item["keyword"]),
    )
    return [
        {
            "keyword": item["keyword"],
            "fund_codes": sorted(item["fund_codes"]),
            "fund_names": sorted(item["fund_names"]),
            "style_groups": sorted(item["style_groups"]),
            "theme_families": sorted(item["theme_families"]),
            "priority": int(item.get("priority", 0) or 0),
            "query_type": item.get("query_type", ""),
        }
        for item in ranked[:limit]
    ]


def build_news_query_plan(portfolio: dict, watchlist: dict, settings: dict, report_date: str) -> dict[str, Any]:
    provider_settings = settings.get("providers", {}) or {}
    sentiment_limit = int((provider_settings.get("sentiment_news", {}) or {}).get("keyword_limit", 18) or 18)
    news_limit = int((provider_settings.get("news", {}) or {}).get("query_limit", 24) or 24)
    funds = _merged_funds(portfolio, watchlist)
    direct: dict[str, dict[str, Any]] = {}
    theme: dict[str, dict[str, Any]] = {}
    market: dict[str, dict[str, Any]] = {}
    sentiment: dict[str, dict[str, Any]] = {}

    for fund in funds:
        code = str(fund.get("code", "") or "")
        name = clean_keyword(str(fund.get("name", "") or ""))
        benchmark = clean_keyword(str(fund.get("benchmark", "") or ""))
        style_group = str(fund.get("style_group", "") or "")
        theme_family = str(fund.get("theme_family", "") or "")
        category = str(fund.get("category", "") or "")

        for keyword, priority in ((code, 95), (name, 85), (benchmark, 80)):
            _add_query(direct, keyword, fund=fund, priority=priority, query_type="direct")
            if keyword != code:
                _add_query(sentiment, keyword, fund=fund, priority=priority, query_type="sentiment")

        for keyword in STYLE_KEYWORDS.get(style_group, []):
            _add_query(theme, keyword, fund=fund, priority=78, query_type="theme")
            _add_query(sentiment, keyword, fund=fund, priority=100, query_type="sentiment")

        for keyword in THEME_FAMILY_KEYWORDS.get(theme_family, []):
            _add_query(theme, keyword, fund=fund, priority=64, query_type="theme")
            _add_query(sentiment, keyword, fund=fund, priority=70, query_type="sentiment")

        for keyword in MARKET_KEYWORDS_BY_CATEGORY.get(category, []):
            _add_query(market, keyword, fund=fund, priority=58, query_type="market")

        if category == "qdii_index":
            for keyword in ("中概", "纳指", "标普"):
                _add_query(sentiment, keyword, fund=fund, priority=95, query_type="sentiment")

    return {
        "schema_version": 1,
        "report_date": report_date,
        "fund_count": len(funds),
        "direct_queries": _rank_queries(direct, news_limit),
        "theme_queries": _rank_queries(theme, news_limit),
        "market_queries": _rank_queries(market, news_limit),
        "sentiment_queries": _rank_queries(sentiment, sentiment_limit),
    }


def sentiment_queries_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "keyword": item.get("keyword", ""),
            "fund_codes": list(item.get("fund_codes", []) or []),
            "fund_names": list(item.get("fund_names", []) or []),
            "style_groups": list(item.get("style_groups", []) or []),
        }
        for item in plan.get("sentiment_queries", []) or []
        if item.get("keyword")
    ]
