from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from common import dump_json, fund_profile_path, load_json, load_watchlist, project_relative_path, timestamp_now
from fetch_fund_profiles import fetch_one_profile
from portfolio_state import ensure_portfolio_definition
from sync_portfolio_from_screenshots import infer_role_for_new_fund, infer_style_group_for_new_fund, safe_portfolio_definition


FUND_SEARCH_URL = "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
FUND_PROFILE_URL = "https://fundf10.eastmoney.com/jbgk_{code}.html"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/134.0 Safari/537.36",
    "Referer": "https://fund.eastmoney.com/",
}


def normalize_fund_identity(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[\s\-_/（）()·,，.。]", "", text)
    return text.replace("人民币份额", "人民币")


def fund_name_similarity(query: str, candidate: dict[str, Any]) -> float:
    target = normalize_fund_identity(query)
    names = [candidate.get("fund_name", ""), *(candidate.get("aliases", []) or [])]
    best = 0.0
    for raw_name in names:
        name = normalize_fund_identity(raw_name)
        if not name:
            continue
        score = difflib.SequenceMatcher(a=target, b=name).ratio()
        if target == name:
            score = 1.0
        elif target in name or name in target:
            score = max(score, 0.94)
        best = max(best, score)
    return round(best, 4)


def infer_category(fund_type: str, fund_name: str) -> str:
    text = f"{fund_type} {fund_name}".lower()
    if "货币" in text or "存单" in text:
        return "cash_management"
    if "债" in text:
        return "bond"
    if "联接" in text:
        return "etf_linked"
    if "指数" in text:
        return "qdii_index" if "qdii" in text or "海外" in text else "index_equity"
    if any(token in text for token in ("股票", "混合", "qdii", "海外")):
        return "active_equity"
    return "unknown"


def infer_risk_level(category: str, fund_type: str) -> str:
    if category in {"cash_management", "bond"}:
        return "low"
    if category == "qdii_index" or "海外" in str(fund_type):
        return "high"
    if category in {"etf_linked", "index_equity", "active_equity"}:
        return "high"
    return "unknown"


def _search_variants(name: str) -> list[str]:
    raw = " ".join(str(name or "").split()).strip()
    without_parenthetical = re.sub(r"[（(][^）)]*[）)]", "", raw).strip()
    compact = re.sub(r"\s+", "", without_parenthetical)
    without_share_class = re.sub(r"(?:人民币|美元现汇)?[AC]$", "", compact, flags=re.IGNORECASE)
    variants = [raw, without_parenthetical, without_share_class]
    for prefix_length in (3, 2, 4):
        if len(without_share_class) - prefix_length >= 5:
            variants.append(without_share_class[prefix_length:])
    for length in (12, 10, 8):
        if len(compact) > length:
            variants.append(compact[-length:])
    result: list[str] = []
    for value in variants:
        if value and value not in result:
            result.append(value)
    return result[:5]


def _request_search_payload(query: str, *, timeout_seconds: int) -> dict[str, Any]:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(DEFAULT_HEADERS)
    response = session.get(FUND_SEARCH_URL, params={"m": 1, "key": query}, timeout=timeout_seconds)
    response.raise_for_status()
    return response.json()


def extract_eastmoney_fund_candidates(payload: dict[str, Any], query: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in payload.get("Datas", []) or []:
        code = str(row.get("CODE") or "").strip()
        if int(row.get("CATEGORY", 0) or 0) != 700 or not re.fullmatch(r"\d{6}", code):
            continue
        base = row.get("FundBaseInfo") if isinstance(row.get("FundBaseInfo"), dict) else {}
        name = str(base.get("SHORTNAME") or row.get("NAME") or "").strip()
        aliases = [item.strip() for item in str(base.get("OTHERNAME") or "").split(",") if item.strip()]
        fund_type = str(base.get("FTYPE") or "").strip()
        category = infer_category(fund_type, name)
        candidate = {
            "fund_code": code,
            "fund_name": name,
            "fund_type": fund_type,
            "category": category,
            "risk_level": infer_risk_level(category, fund_type),
            "company_name": str(base.get("JJGS") or "").strip(),
            "manager_name": str(base.get("JJJL") or "").strip(),
            "latest_nav": base.get("DWJZ"),
            "nav_date": str(base.get("FSRQ") or "").strip(),
            "aliases": aliases,
            "source_name": "东方财富基金搜索",
            "source_url": FUND_PROFILE_URL.format(code=code),
            "search_source_url": f"{FUND_SEARCH_URL}?m=1&key={quote(query)}",
        }
        candidate["match_score"] = fund_name_similarity(query, candidate)
        candidates.append(candidate)
    return candidates


def search_fund_candidates(name: str, *, timeout_seconds: int = 15, limit: int = 5) -> dict[str, Any]:
    query = str(name or "").strip()
    if not query:
        raise ValueError("fund name is required")
    by_code: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    searched: list[str] = []
    for variant in _search_variants(query):
        searched.append(variant)
        try:
            payload = _request_search_payload(variant, timeout_seconds=timeout_seconds)
        except Exception as exc:
            errors.append(str(exc))
            continue
        for candidate in extract_eastmoney_fund_candidates(payload, query):
            existing = by_code.get(candidate["fund_code"])
            if existing is None or float(candidate["match_score"]) > float(existing["match_score"]):
                by_code[candidate["fund_code"]] = candidate
        if by_code and max(float(item["match_score"]) for item in by_code.values()) >= 0.85:
            break
    candidates = sorted(by_code.values(), key=lambda item: (-float(item["match_score"]), item["fund_code"]))[:limit]
    return {
        "query": query,
        "candidates": candidates,
        "searched_queries": searched,
        "provider": "eastmoney_fund_search",
        "source_url": candidates[0]["search_source_url"] if candidates else "",
        "warnings": [] if candidates else (["基金查询暂时失败，请稍后重试。"] if errors else ["没有找到可核验的基金候选。"]),
    }


def lookup_fund_by_code(code: str, *, timeout_seconds: int = 15) -> dict[str, Any]:
    fund_code = str(code or "").strip()
    if not re.fullmatch(r"\d{6}", fund_code):
        raise ValueError("fund code must contain exactly 6 digits")
    payload = _request_search_payload(fund_code, timeout_seconds=timeout_seconds)
    candidates = extract_eastmoney_fund_candidates(payload, fund_code)
    candidate = next((item for item in candidates if item["fund_code"] == fund_code), None)
    if candidate is None:
        raise ValueError(f"fund code was not found in the provider: {fund_code}")
    return candidate


def register_fund_metadata(
    agent_home: Path,
    *,
    candidate: dict[str, Any],
    display_name: str,
    snapshot_date: str,
    registration_id: str,
) -> dict[str, Any]:
    code = str(candidate.get("fund_code") or "").strip()
    name = str(candidate.get("fund_name") or "").strip()
    profile = fetch_one_profile(
        {
            "code": code,
            "name": name,
            "category": candidate.get("category", "unknown"),
            "benchmark": "",
            "risk_level": candidate.get("risk_level", "unknown"),
        },
        snapshot_date,
    )
    benchmark = str(profile.get("benchmark") or "").strip()
    category = str(candidate.get("category") or profile.get("category") or "unknown")
    risk_level = str(candidate.get("risk_level") or profile.get("risk_level") or "unknown")

    portfolio = load_json(agent_home / "db" / "portfolio_state" / "current.json")
    try:
        definition = ensure_portfolio_definition(agent_home)
    except FileNotFoundError:
        definition = safe_portfolio_definition(agent_home, portfolio)
    existing_definition = next((item for item in definition.get("funds", []) or [] if str(item.get("fund_code")) == code), None)
    if existing_definition is None:
        style_group = infer_style_group_for_new_fund(name, benchmark, category)
        role = infer_role_for_new_fund(category, style_group, portfolio)
        definition.setdefault("funds", []).append(
            {
                "fund_code": code,
                "fund_name": name,
                "role": role,
                "style_group": style_group,
                "category": category,
                "benchmark": benchmark,
                "risk_level": risk_level,
                "allow_trade": False,
                "classification_status": "pending_review",
                "registry_source": "confirmed_screenshot_fund",
                "profile_source_url": candidate.get("source_url", ""),
                "opening_state": {
                    "current_value": 0.0,
                    "holding_pnl": 0.0,
                    "holding_return_pct": 0.0,
                    "holding_units": 0.0,
                    "cost_basis_value": 0.0,
                    "units_source": "registered_before_position_apply",
                },
            }
        )
    elif normalize_fund_identity(existing_definition.get("fund_name")) != normalize_fund_identity(name):
        raise ValueError(f"fund code {code} is already registered with a different name")
    definition["updated_at"] = timestamp_now()
    definition_path = dump_json(agent_home / "config" / "portfolio_definition.json", definition)

    watchlist = load_watchlist(agent_home)
    existing_watch = next((item for item in watchlist.get("funds", []) or [] if str(item.get("code")) == code), None)
    watch_item = {
        "code": code,
        "name": name,
        "category": category,
        "benchmark": benchmark,
        "risk_level": risk_level,
    }
    if existing_watch is None:
        watchlist.setdefault("funds", []).append(watch_item)
    else:
        existing_watch.update(watch_item)
    watchlist_path = dump_json(agent_home / "config" / "watchlist.json", watchlist)

    profile_path = fund_profile_path(agent_home, snapshot_date)
    profile_payload = load_json(profile_path) if profile_path.exists() else {
        "report_date": snapshot_date,
        "provider": "eastmoney_jbgk",
        "generated_at": timestamp_now(),
        "items": [],
    }
    profile_item = {
        **profile,
        "identity_source": "eastmoney_fund_search",
        "identity_source_url": candidate.get("search_source_url", ""),
        "screenshot_display_name": display_name,
        "registration_id": registration_id,
    }
    items = [item for item in profile_payload.get("items", []) or [] if str(item.get("fund_code")) != code]
    profile_payload["items"] = [*items, profile_item]
    profile_payload["generated_at"] = timestamp_now()
    dump_json(profile_path, profile_payload)

    return {
        "candidate": {**candidate, "benchmark": benchmark},
        "profile": profile_item,
        "definition_path": project_relative_path(agent_home, definition_path),
        "watchlist_path": project_relative_path(agent_home, watchlist_path),
        "profile_path": project_relative_path(agent_home, profile_path),
    }
