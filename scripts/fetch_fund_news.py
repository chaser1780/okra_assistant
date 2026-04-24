from __future__ import annotations

import argparse
import base64
import html
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import local
from urllib.parse import quote

import requests
import win32crypt
from bs4 import BeautifulSoup

from common import dump_json, ensure_layout, load_portfolio, load_settings, load_watchlist, news_path, resolve_agent_home, resolve_date, timestamp_now
from portfolio_exposure import infer_theme_family
from provider_adapters import build_provider_payload, build_provider_result, build_source_health_item, normalize_provider_item, resolve_provider_chain

EASTMONEY_NOTICE_API = "https://api.fund.eastmoney.com/f10/JJGG"
EASTMONEY_FUND_PAGE = "https://fund.eastmoney.com/{code}.html"
XUEQIU_SEARCH_URL = "https://xueqiu.com/query/v1/search/status.json"
DOUYIN_SEARCH_API = "https://www.douyin.com/aweme/v1/web/general/search/single/"
CN_TZ = timezone(timedelta(hours=8))
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36",
    "Referer": "https://fund.eastmoney.com/",
}
XUEQIU_HEADERS = {
    "User-Agent": DEFAULT_HEADERS["User-Agent"],
    "Referer": "https://xueqiu.com/",
    "Accept": "application/json,text/plain,*/*",
}
DOUYIN_HEADERS = {
    "User-Agent": DEFAULT_HEADERS["User-Agent"],
    "Referer": "https://www.douyin.com/search/1?type=general",
    "Accept": "application/json,text/plain,*/*",
}
_SESSION_LOCAL = local()
NOTICE_CATEGORY_MAP = {"1": "发行运作", "2": "分红送配", "3": "定期报告", "4": "人事调整", "5": "基金销售", "6": "其他公告"}
NEGATIVE_KEYWORDS = ("风险", "下调", "离任", "清盘", "终止", "停牌", "处罚", "违约", "预警", "大幅回撤", "限制")
POSITIVE_KEYWORDS = ("分红", "增持", "上调", "获批", "成立", "开放", "扩募", "利好")
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


def derive_bucket_metadata(title: str, source_name: str, category: str, provider_name: str = "") -> tuple[str, str, str, float, float, float, float, str]:
    evidence_type = "theme_news"
    source_role = "fund_news"
    source_tier = "self_media"
    virality_score = 0.15
    novelty_score = 0.6
    historical_significance = 0.0
    crowding_signal = "neutral"
    lower_source = (source_name or provider_name or "").lower()
    if provider_name == "xueqiu_web":
        evidence_type = "social_post"
        source_role = "sentiment_news"
        source_tier = "social_post"
        virality_score = 0.5
        novelty_score = 0.72
    elif provider_name == "douyin_web":
        evidence_type = "short_video_signal"
        source_role = "sentiment_news"
        source_tier = "social_short_video"
        virality_score = 0.7
        novelty_score = 0.72
        crowding_signal = "warming"
    elif "notice" in lower_source or "公告" in title:
        evidence_type = "official_notice"
        source_role = "fund_news"
        source_tier = "official_notice"
        novelty_score = 0.8
    elif any(keyword in title for keyword in ("证监会", "发改委", "工信部", "财政部", "监管", "政策")):
        evidence_type = "policy_news"
        source_role = "market_news"
        source_tier = "official_policy"
        historical_significance = 0.7
        novelty_score = 0.75
    elif any(keyword in title for keyword in ("美股", "港股", "A股", "纳指", "标普", "人民币", "汇率", "利率")):
        evidence_type = "market_news"
        source_role = "market_news"
        source_tier = "market_media"
        novelty_score = 0.7
    elif any(keyword in title for keyword in ("视频", "直播", "#", "短视频")):
        evidence_type = "short_video_signal"
        source_role = "sentiment_news"
        source_tier = "social_short_video"
        virality_score = 0.75
        crowding_signal = "warming"
    elif any(keyword in title for keyword in ("揭秘", "调研团", "热议", "热度", "网友", "讨论")):
        evidence_type = "social_post"
        source_role = "sentiment_news"
        source_tier = "social_post"
        virality_score = 0.55
        crowding_signal = "warming"
    elif category:
        evidence_type = "theme_news"
        source_role = "theme_news"
        source_tier = "self_media"
    sentiment_score = 0.35 if infer_impact(title) == "positive" else (-0.35 if infer_impact(title) == "negative" else 0.0)
    if virality_score >= 0.7 and abs(sentiment_score) >= 0.3:
        crowding_signal = "crowded"
    return evidence_type, source_role, source_tier, sentiment_score, novelty_score, virality_score, historical_significance, crowding_signal


def mapping_mode(evidence_type: str) -> str:
    if evidence_type in {"policy_news", "market_news"}:
        return "market_background"
    if evidence_type in {"social_post", "short_video_signal"}:
        return "sentiment_background"
    if evidence_type == "theme_news":
        return "theme_match"
    return "direct_fund"


def annotate_news_item(item: dict, fund: dict, provider_name: str, report_date: str) -> dict:
    title = str(item.get("title", "") or "")
    source_name = str(item.get("source_name", "") or provider_name)
    category = str(fund.get("category", "") or "")
    evidence_type, source_role, source_tier, sentiment_score, novelty_score, virality_score, historical_significance, crowding_signal = derive_bucket_metadata(title, source_name, category, provider_name)
    published_at = str(item.get("published_at", "") or f"{report_date}T00:00:00+08:00")
    entity_id = str(item.get("code", "") or fund.get("code", ""))
    confidence = float(item.get("confidence", 0.0) or 0.0)
    if confidence <= 0:
        confidence = 0.95 if evidence_type == "official_notice" else (0.72 if evidence_type in {"policy_news", "market_news"} else 0.58)
    return normalize_provider_item(
        {
            **item,
            "code": fund["code"],
            "name": fund["name"],
            "published_at": published_at,
            "impact": infer_impact(title),
            "source_name": source_name,
            "source_role": source_role,
            "source_tier": source_tier,
            "mapping_mode": mapping_mode(evidence_type),
            "evidence_type": evidence_type,
            "sentiment_score": sentiment_score if item.get("sentiment_score") is None else item.get("sentiment_score"),
            "novelty_score": novelty_score if item.get("novelty_score") is None else item.get("novelty_score"),
            "virality_score": virality_score if item.get("virality_score") is None else item.get("virality_score"),
            "historical_significance": historical_significance if item.get("historical_significance") is None else item.get("historical_significance"),
            "crowding_signal": crowding_signal if not item.get("crowding_signal") else item.get("crowding_signal"),
            "freshness_status": item.get("freshness_status", "fresh"),
            "stale": bool(item.get("stale", False)),
            "matched_keywords": item.get("matched_keywords", []),
        },
        provider_name=provider_name,
        entity_id=entity_id,
        entity_type="fund",
        source_url=str(item.get("url", "")),
        source_title=title,
        as_of=published_at,
        freshness_status=item.get("freshness_status", "fresh"),
        stale=bool(item.get("stale", False)),
        confidence=confidence,
        source_role=source_role,
        source_tier=source_tier,
        mapping_mode=mapping_mode(evidence_type),
        evidence_type=evidence_type,
    )


def clean_keyword(value: str) -> str:
    text = html.unescape(str(value or "").strip())
    text = re.sub(r"[（(].*?[）)]", " ", text)
    for token in FUND_NAME_NOISE:
        text = text.replace(token, " ")
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", text)
    return " ".join(text.split()).strip()[:24]


def keyword_terms_for_fund(fund: dict) -> list[tuple[str, int]]:
    values: list[tuple[str, int]] = []
    name = clean_keyword(fund.get("name", ""))
    benchmark = clean_keyword(fund.get("benchmark", ""))
    style_group = str(fund.get("style_group", "") or "")
    if name:
        values.append((name, 60))
    if benchmark and benchmark != name:
        values.append((benchmark, 80))
    values.extend((item, 100) for item in STYLE_KEYWORDS.get(style_group, []))
    theme_family = infer_theme_family(
        {
            "fund_code": fund.get("code", ""),
            "fund_name": fund.get("name", ""),
            "style_group": style_group,
            "category": fund.get("category", ""),
            "benchmark": benchmark,
        }
    )
    if theme_family:
        theme_term = clean_keyword(theme_family.replace("_", " "))
        if theme_term:
            values.append((theme_term, 20))
    if fund.get("category") == "qdii_index":
        values.extend((item, 95) for item in ("中概", "纳指", "标普"))
    seen = set()
    result = []
    for item, priority in values:
        key = item.lower()
        if len(item) < 2 or key in seen:
            continue
        seen.add(key)
        result.append((item, priority))
    return result


def build_dynamic_sentiment_queries(portfolio: dict, watchlist: dict, settings: dict) -> list[dict]:
    holdings = {
        item.get("fund_code"): item
        for item in portfolio.get("funds", []) or []
        if float(item.get("current_value", 0.0) or 0.0) > 0 and item.get("role") not in {"cash_hub", "fixed_hold"}
    }
    watch_by_code = {item.get("code"): item for item in watchlist.get("funds", []) or []}
    keyword_limit = int((settings.get("providers", {}).get("sentiment_news", {}) or {}).get("keyword_limit", 18) or 18)
    query_map: dict[str, dict] = {}
    for fund_code, holding in holdings.items():
        watch = watch_by_code.get(fund_code, {})
        merged = {
            **watch,
            "code": fund_code,
            "style_group": holding.get("style_group", ""),
            "benchmark": watch.get("benchmark", ""),
            "category": watch.get("category", ""),
            "name": holding.get("fund_name", watch.get("name", fund_code)),
        }
        for term, priority in keyword_terms_for_fund(merged):
            entry = query_map.setdefault(
                term,
                {"keyword": term, "fund_codes": set(), "fund_names": set(), "style_groups": set(), "priority": priority},
            )
            entry["fund_codes"].add(fund_code)
            entry["fund_names"].add(merged.get("name", fund_code))
            if merged.get("style_group"):
                entry["style_groups"].add(merged["style_group"])
            entry["priority"] = max(int(entry.get("priority", 0) or 0), priority)
    ranked = sorted(query_map.values(), key=lambda item: (-len(item["fund_codes"]), -int(item.get("priority", 0) or 0), item["keyword"]))
    return [
        {
            "keyword": item["keyword"],
            "fund_codes": sorted(item["fund_codes"]),
            "fund_names": sorted(item["fund_names"]),
            "style_groups": sorted(item["style_groups"]),
        }
        for item in ranked[:keyword_limit]
    ]


def browser_base_dir(browser_name: str) -> Path:
    if browser_name == "edge":
        return Path.home() / "AppData/Local/Microsoft/Edge/User Data"
    return Path.home() / "AppData/Local/Google/Chrome/User Data"


def profile_cookie_tuple(browser_name: str, profile_dir: Path) -> tuple[Path, Path] | None:
    base = browser_base_dir(browser_name)
    local_state = base / "Local State"
    cookies_path = profile_dir / "Network" / "Cookies"
    if local_state.exists() and cookies_path.exists():
        return local_state, cookies_path
    return None


def cookie_paths_for_browser(browser_name: str) -> list[tuple[Path, Path]]:
    base = browser_base_dir(browser_name)
    paths = []
    for profile_dir in [base / "Default", *sorted(base.glob("Profile *"))]:
        item = profile_cookie_tuple(browser_name, profile_dir)
        if item:
            paths.append(item)
    return paths


def resolve_preferred_profile_dir(settings: dict, platform: str) -> tuple[str, Path] | None:
    sentiment_settings = settings.get("providers", {}).get("sentiment_news", {}) or {}
    profile_path_value = str(sentiment_settings.get(f"{platform}_profile_path", "") or "").strip()
    if profile_path_value:
        profile_dir = Path(profile_path_value).expanduser()
        browser_name = str(sentiment_settings.get(f"{platform}_browser", "edge") or "edge").strip().lower()
        return browser_name, profile_dir
    browser_name = str(sentiment_settings.get(f"{platform}_browser", "") or "").strip().lower()
    profile_name = str(sentiment_settings.get(f"{platform}_profile", "") or "").strip()
    if browser_name and profile_name:
        return browser_name, browser_base_dir(browser_name) / profile_name
    return None


def browser_cookie_candidates(settings: dict | None = None, platform: str | None = None) -> list[tuple[str, Path, Path]]:
    results = []
    seen = set()
    if settings and platform:
        preferred = resolve_preferred_profile_dir(settings, platform)
        if preferred:
            browser_name, profile_dir = preferred
            item = profile_cookie_tuple(browser_name, profile_dir)
            if item:
                key = (browser_name, str(item[0]), str(item[1]))
                seen.add(key)
                results.append((browser_name, item[0], item[1]))
    for browser_name in ("chrome", "edge"):
        for local_state, cookies_path in cookie_paths_for_browser(browser_name):
            key = (browser_name, str(local_state), str(cookies_path))
            if key in seen:
                continue
            results.append((browser_name, local_state, cookies_path))
    return results


def browser_candidate_metadata(browser_name: str, cookies_path: Path) -> dict:
    try:
        modified_at = datetime.fromtimestamp(cookies_path.stat().st_mtime, tz=CN_TZ).isoformat(timespec="seconds")
    except Exception:
        modified_at = ""
    return {
        "browser": browser_name,
        "profile": cookies_path.parent.parent.name,
        "cookies_path": str(cookies_path),
        "modified_at": modified_at,
    }


def read_cookie_file(cookie_file: str | Path | None, agent_home: Path) -> str:
    if not cookie_file:
        return ""
    path = Path(cookie_file)
    if not path.is_absolute():
        path = agent_home / path
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()
    return text


def write_cookie_file(cookie_file: str | Path | None, agent_home: Path, cookie_value: str) -> None:
    if not cookie_file or not cookie_value:
        return
    path = Path(cookie_file)
    if not path.is_absolute():
        path = agent_home / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cookie_value, encoding="utf-8")


def parse_cookie_pairs(cookie_value: str) -> dict[str, str]:
    mapping = {}
    for item in (cookie_value or "").split(";"):
        if "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            mapping[name] = value
    return mapping


def cookie_has_required_tokens(platform: str, cookie_value: str) -> bool:
    pairs = parse_cookie_pairs(cookie_value)
    if platform == "xueqiu":
        return all(key in pairs for key in ("xq_a_token", "xq_r_token"))
    if platform == "douyin":
        return all(key in pairs for key in ("sessionid", "ttwid"))
    return bool(pairs)


def chrome_master_key(local_state_path: Path) -> bytes:
    payload = json.loads(local_state_path.read_text(encoding="utf-8"))
    encrypted_key = base64.b64decode(payload["os_crypt"]["encrypted_key"])
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]


def decrypt_cookie_with_powershell(key: bytes, encrypted_value: bytes) -> str:
    key_b64 = base64.b64encode(key).decode("ascii")
    value_b64 = base64.b64encode(encrypted_value).decode("ascii")
    script = r"""
$key=[Convert]::FromBase64String($env:COOKIE_KEY_B64)
$data=[Convert]::FromBase64String($env:COOKIE_VALUE_B64)
if ($data.Length -lt 31) { exit 2 }
$nonce = $data[3..14]
$cipher = $data[15..($data.Length-17)]
$tag = $data[($data.Length-16)..($data.Length-1)]
$plain = New-Object byte[] ($cipher.Length)
$aes = [System.Security.Cryptography.AesGcm]::new($key)
$aes.Decrypt($nonce, $cipher, $tag, $plain, $null)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[System.Text.Encoding]::UTF8.GetString($plain)
"""
    env = os.environ.copy()
    env["COOKIE_KEY_B64"] = key_b64
    env["COOKIE_VALUE_B64"] = value_b64
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "powershell_aes_decrypt_failed")
    return result.stdout.strip()


def decrypt_cookie_value(master_key: bytes, encrypted_value: bytes, value: str) -> str:
    if value:
        return value
    if not encrypted_value:
        return ""
    blob = bytes(encrypted_value)
    if blob.startswith(b"v10") or blob.startswith(b"v11"):
        return decrypt_cookie_with_powershell(master_key, blob)
    return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1].decode("utf-8", errors="replace")


def copy_cookie_db(src: Path, dst: Path) -> str:
    try:
        shutil.copy2(src, dst)
        return "copy2"
    except Exception as exc:
        copy2_error = str(exc)
    script = rf"""
$src = '{str(src)}'
$dst = '{str(dst)}'
try {{
  $in = [System.IO.File]::Open($src,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::ReadWrite)
  $out = [System.IO.File]::Open($dst,[System.IO.FileMode]::Create,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
  $in.CopyTo($out)
  $out.Close()
  $in.Close()
}} catch {{
  Write-Error $_
  exit 2
}}
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"copy2={copy2_error} | powershell={result.stderr.strip() or result.stdout.strip() or 'copy_cookie_db_failed'}")
    return "powershell_copy"


def browser_cookie_string(domain_keyword: str, browser_name: str, local_state_path: Path, cookies_path: Path) -> tuple[str, dict]:
    master_key = chrome_master_key(local_state_path)
    with tempfile.TemporaryDirectory() as temp_dir:
        copied = Path(temp_dir) / "Cookies"
        copy_method = copy_cookie_db(cookies_path, copied)
        conn = sqlite3.connect(str(copied))
        try:
            rows = conn.execute(
                "select name, value, encrypted_value, host_key from cookies where host_key like ?",
                (f"%{domain_keyword}%",),
            ).fetchall()
        finally:
            conn.close()
    parts = []
    seen = set()
    for name, value, encrypted_value, host_key in rows:
        if not name or name in seen:
            continue
        try:
            cookie_value = decrypt_cookie_value(master_key, encrypted_value, value)
        except Exception:
            continue
        if cookie_value == "":
            continue
        seen.add(name)
        parts.append(f"{name}={cookie_value}")
    return "; ".join(parts), {"copy_method": copy_method, "cookie_count": len(parts)}


def auto_sync_cookie_from_browser(agent_home: Path, settings: dict, platform: str, cookie_file: str | Path | None) -> tuple[str, dict]:
    domain_keyword = "xueqiu.com" if platform == "xueqiu" else "douyin.com"
    last_error = ""
    tried = []
    for browser_name, local_state, cookies_path in browser_cookie_candidates(settings, platform):
        meta = browser_candidate_metadata(browser_name, cookies_path)
        try:
            cookie_value, detail = browser_cookie_string(domain_keyword, browser_name, local_state, cookies_path)
        except Exception as exc:
            last_error = str(exc)
            tried.append({**meta, "status": "error", "error": last_error})
            continue
        tried.append({**meta, "status": "ok", **detail})
        if cookie_has_required_tokens(platform, cookie_value):
            write_cookie_file(cookie_file, agent_home, cookie_value)
            return cookie_value, {"source": f"{browser_name}:{cookies_path.parent.parent.name}", "synced": True, "error": "", "tried": tried}
    return "", {"source": "", "synced": False, "error": last_error, "tried": tried}


def build_cookie_session(headers: dict, cookie_value: str, *, use_env_proxy: bool) -> requests.Session:
    session = requests.Session()
    session.trust_env = use_env_proxy
    session.headers.update(headers)
    if cookie_value:
        session.headers["Cookie"] = cookie_value
    return session


def probe_xueqiu_cookie(cookie_value: str, use_env_proxy: bool, timeout_seconds: int) -> tuple[bool, str]:
    if not cookie_has_required_tokens("xueqiu", cookie_value):
        return False, "missing required xueqiu tokens"
    session = build_cookie_session(XUEQIU_HEADERS, cookie_value, use_env_proxy=use_env_proxy)
    try:
        response = get_response_with_retry(
            session,
            XUEQIU_SEARCH_URL,
            timeout_seconds=timeout_seconds,
            params={"q": "AI", "count": 1, "page": 1},
        )
        if "json" not in response.headers.get("Content-Type", "").lower():
            return False, "xueqiu non-json response"
        payload = response.json()
        if str(payload.get("error_code", "")).strip() in {"400016"} or payload.get("success") is False:
            return False, "xueqiu login expired"
        return True, "ok"
    except Exception as exc:
        return False, str(exc)
    finally:
        session.close()


def probe_douyin_cookie(cookie_value: str, use_env_proxy: bool, timeout_seconds: int) -> tuple[bool, str]:
    if not cookie_has_required_tokens("douyin", cookie_value):
        return False, "missing required douyin tokens"
    session = build_cookie_session(DOUYIN_HEADERS, cookie_value, use_env_proxy=use_env_proxy)
    try:
        response = get_response_with_retry(
            session,
            DOUYIN_SEARCH_API,
            timeout_seconds=timeout_seconds,
            params={
                "device_platform": "webapp",
                "aid": "6383",
                "channel": "channel_pc_web",
                "search_channel": "aweme_video_web",
                "sort_type": 0,
                "publish_time": 0,
                "keyword": "AI",
                "search_source": "normal_search",
                "query_correct_type": 1,
                "is_filter_search": 0,
                "offset": 0,
                "count": 1,
                "from_group_id": "",
                "pd": "synthesis",
            },
        )
        payload = response.json()
        nil_info = payload.get("search_nil_info", {}) or {}
        if nil_info.get("search_nil_type") == "verify_check":
            return False, "douyin verify_check"
        return True, "ok"
    except Exception as exc:
        return False, str(exc)
    finally:
        session.close()


def resolve_cookie_with_auto_sync(agent_home: Path, settings: dict, platform: str, cookie_file: str | Path | None, *, use_env_proxy: bool, timeout_seconds: int) -> tuple[str, dict]:
    cookie_value = read_cookie_file(cookie_file, agent_home)
    source = "file"
    synced = False
    tried = []
    if not cookie_value or not cookie_has_required_tokens(platform, cookie_value):
        cookie_value, meta = auto_sync_cookie_from_browser(agent_home, settings, platform, cookie_file)
        source = meta.get("source", "browser")
        synced = bool(meta.get("synced", False))
        tried = meta.get("tried", [])
    probe_ok, detail = (probe_xueqiu_cookie(cookie_value, use_env_proxy, timeout_seconds) if platform == "xueqiu" else probe_douyin_cookie(cookie_value, use_env_proxy, timeout_seconds))
    if not probe_ok:
        refreshed_value, meta = auto_sync_cookie_from_browser(agent_home, settings, platform, cookie_file)
        if refreshed_value and refreshed_value != cookie_value:
            cookie_value = refreshed_value
            source = meta.get("source", "browser")
            synced = True
            tried = meta.get("tried", tried)
            probe_ok, detail = (probe_xueqiu_cookie(cookie_value, use_env_proxy, timeout_seconds) if platform == "xueqiu" else probe_douyin_cookie(cookie_value, use_env_proxy, timeout_seconds))
        else:
            tried = meta.get("tried", tried)
    return cookie_value, {"source": source, "synced": synced, "probe_ok": probe_ok, "probe_detail": detail, "tried": tried}


def parse_xueqiu_time(value) -> str:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return timestamp_now()
    if numeric > 10_000_000_000:
        numeric = numeric / 1000
    return datetime.fromtimestamp(numeric, tz=CN_TZ).isoformat(timespec="seconds")


def extract_plain_text(value: str) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(str(value), "html.parser")
    return " ".join(soup.get_text(" ", strip=True).split())


def extract_xueqiu_status_items(payload: dict) -> list[dict]:
    candidates = []
    stack = [payload]
    seen_keys = set()
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            text = extract_plain_text(node.get("text") or node.get("description") or node.get("title") or "")
            created_at = node.get("created_at") or node.get("createdAt")
            user = node.get("user") or {}
            user_name = user.get("screen_name") or node.get("screen_name") or node.get("user_name") or ""
            if text and (created_at or user_name):
                status_id = node.get("id") or node.get("status_id") or node.get("target") or text[:48]
                key = str(status_id)
                if key not in seen_keys:
                    seen_keys.add(key)
                    url = ""
                    if user.get("id") and node.get("id"):
                        url = f"https://xueqiu.com/{user.get('id')}/{node.get('id')}"
                    elif node.get("target"):
                        url = str(node.get("target"))
                    like_count = int(node.get("like_count", 0) or 0)
                    comment_count = int(node.get("comment_count", 0) or 0)
                    retweet_count = int(node.get("retweet_count", 0) or 0)
                    candidates.append(
                        {
                            "title": text[:80],
                            "summary": text[:220],
                            "published_at": parse_xueqiu_time(created_at),
                            "source_name": "xueqiu_web",
                            "url": url or "https://xueqiu.com/",
                            "relevance_score": 0.68,
                            "author_name": user_name,
                            "like_count": like_count,
                            "comment_count": comment_count,
                            "retweet_count": retweet_count,
                            "virality_score": min(1.0, math.log1p(like_count + comment_count + retweet_count) / 8.0),
                        }
                    )
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return candidates


def parse_douyin_time(value) -> str:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return timestamp_now()
    return datetime.fromtimestamp(numeric, tz=CN_TZ).isoformat(timespec="seconds")


def extract_douyin_aweme_items(payload: dict) -> list[dict]:
    items = []
    seen = set()
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            aweme = node.get("aweme_info") if isinstance(node.get("aweme_info"), dict) else node if node.get("aweme_id") else None
            if aweme:
                aweme_id = str(aweme.get("aweme_id", "") or "")
                desc = " ".join(str(aweme.get("desc", "") or "").split())
                if aweme_id and desc and aweme_id not in seen:
                    seen.add(aweme_id)
                    stats = aweme.get("statistics", {}) or {}
                    like_count = int(stats.get("digg_count", 0) or 0)
                    comment_count = int(stats.get("comment_count", 0) or 0)
                    share_count = int(stats.get("share_count", 0) or 0)
                    view_count = int(stats.get("play_count", 0) or 0)
                    engagement = like_count + comment_count * 2 + share_count * 2 + view_count / 1000
                    items.append(
                        {
                            "title": desc[:80],
                            "summary": desc[:220],
                            "published_at": parse_douyin_time(aweme.get("create_time")),
                            "source_name": "douyin_web",
                            "url": f"https://www.douyin.com/video/{aweme_id}",
                            "relevance_score": 0.7,
                            "author_name": (aweme.get("author") or {}).get("nickname", ""),
                            "like_count": like_count,
                            "comment_count": comment_count,
                            "share_count": share_count,
                            "view_count": view_count,
                            "virality_score": min(1.0, math.log1p(engagement) / 10.0),
                        }
                    )
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return items


def fetch_notice_items(session: requests.Session, fund: dict, settings: dict, report_date: str, provider_name: str) -> list[dict]:
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
        items.append(
            annotate_news_item(
                {
                    "published_at": published_at or f"{item.get('PUBLISHDATEDesc', report_date)}T00:00:00+08:00",
                    "title": title,
                    "summary": f"基金公告，分类：{category}。",
                    "source_name": "eastmoney_notice",
                    "url": f"http://fund.eastmoney.com/gonggao/{fund['code']},{item.get('ID', '')}.html",
                    "relevance_score": 0.95,
                },
                fund,
                provider_name,
                report_date,
            )
        )
    return items


def fetch_article_items(session: requests.Session, fund: dict, settings: dict, report_date: str, provider_name: str) -> list[dict]:
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
        items.append(
            annotate_news_item(
                {
                    "published_at": published_at or timestamp_now(),
                    "title": title,
                    "summary": "基金页面文章，时间优先从 URL 解析。",
                    "source_name": "eastmoney_article",
                    "url": href,
                    "relevance_score": 0.72,
                },
                fund,
                provider_name,
                report_date,
            )
        )
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


def fetch_one_fund_news(fund: dict, settings: dict, report_date: str, provider_name: str) -> list[dict]:
    session = get_thread_session()
    items: list[dict] = []
    items.extend(fetch_notice_items(session, fund, settings, report_date, provider_name))
    items.extend(fetch_article_items(session, fund, settings, report_date, provider_name))
    return items


def build_demo_news(watchlist: dict, report_date: str, provider_name: str) -> list[dict]:
    impact_cycle = ["positive", "neutral", "negative"]
    items = []
    for index, fund in enumerate(watchlist["funds"]):
        primary_impact = impact_cycle[index % len(impact_cycle)]
        secondary_impact = impact_cycle[(index + 1) % len(impact_cycle)]
        items.append(
            annotate_news_item(
                {
                    "published_at": f"{report_date}T08:30:00+08:00",
                    "title": f"{fund['name']}：市场关注度与资金流向示例更新",
                    "summary": "示例新闻，用于打通基金新闻抓取、摘要和评分链路。",
                    "source_name": "demo_finance_wire",
                    "url": f"https://example.com/funds/{fund['code']}/headline-1",
                    "impact": primary_impact,
                    "relevance_score": round(0.82 - index * 0.08, 2),
                },
                fund,
                provider_name,
                report_date,
            )
        )
        items.append(
            annotate_news_item(
                {
                    "published_at": f"{report_date}T13:30:00+08:00",
                    "title": f"{fund['name']}：#短视频热议 行业景气与情绪扩散示例",
                    "summary": "第二条示例新闻，用于验证主题/情绪分层和风险提示逻辑。",
                    "source_name": "demo_finance_wire",
                    "url": f"https://example.com/funds/{fund['code']}/headline-2",
                    "impact": secondary_impact,
                    "relevance_score": round(0.71 - index * 0.06, 2),
                },
                fund,
                provider_name,
                report_date,
            )
        )
    return items


def fetch_xueqiu_items(agent_home: Path, settings: dict, report_date: str, queries: list[dict]) -> tuple[list[dict], dict]:
    sentiment_settings = settings.get("providers", {}).get("sentiment_news", {}) or {}
    timeout_seconds = int(sentiment_settings.get("timeout_seconds", 20) or 20)
    results_per_keyword = int(sentiment_settings.get("results_per_keyword", 6) or 6)
    use_env_proxy = bool(sentiment_settings.get("use_env_proxy", True))
    cookie_value, cookie_meta = resolve_cookie_with_auto_sync(
        agent_home,
        settings,
        "xueqiu",
        sentiment_settings.get("xueqiu_cookie_file", ""),
        use_env_proxy=use_env_proxy,
        timeout_seconds=timeout_seconds,
    )
    if not cookie_value:
        return [], build_source_health_item(
            source_key="sentiment:xueqiu_web",
            source_role="sentiment_news",
            provider="xueqiu_web",
            status="warning",
            notes=[f"missing xueqiu cookie and browser sync failed: {cookie_meta.get('error', '')}"],
            configured=False,
        )
    session = build_cookie_session(XUEQIU_HEADERS, cookie_value, use_env_proxy=use_env_proxy)
    items = []
    errors = []
    try:
        for query in queries:
            response = get_response_with_retry(
                session,
                XUEQIU_SEARCH_URL,
                timeout_seconds=timeout_seconds,
                params={"q": query["keyword"], "count": results_per_keyword, "page": 1},
            )
            if "json" not in response.headers.get("Content-Type", "").lower():
                raise RuntimeError("xueqiu search returned non-json content, likely waf/captcha")
            payload = response.json()
            extracted = extract_xueqiu_status_items(payload)
            for raw_item in extracted[:results_per_keyword]:
                for fund_code, fund_name in zip(query["fund_codes"], query["fund_names"] or query["fund_codes"]):
                    items.append(
                        normalize_provider_item(
                            {
                                **raw_item,
                                "code": fund_code,
                                "name": fund_name,
                                "matched_keywords": [query["keyword"]],
                                "source_name": "xueqiu_web",
                                "source_role": "sentiment_news",
                                "source_tier": "social_post",
                                "mapping_mode": "sentiment_background",
                                "evidence_type": "social_post",
                                "novelty_score": 0.72,
                                "historical_significance": 0.15,
                                "crowding_signal": "crowded" if float(raw_item.get("virality_score", 0.0) or 0.0) >= 0.65 else "warming",
                            },
                            provider_name="xueqiu_web",
                            entity_id=fund_code,
                            entity_type="fund",
                            source_url=str(raw_item.get("url", "")),
                            source_title=str(raw_item.get("title", "")),
                            as_of=str(raw_item.get("published_at", "")),
                            freshness_status="fresh",
                            stale=not within_lookback(str(raw_item.get("published_at", "")), report_date, int(sentiment_settings.get("lookback_hours", 48) or 48)),
                            confidence=0.66,
                            source_role="sentiment_news",
                            source_tier="social_post",
                            mapping_mode="sentiment_background",
                            evidence_type="social_post",
                        )
                    )
    except Exception as exc:
        errors.append(str(exc))
    finally:
        session.close()
    return items, build_source_health_item(
        source_key="sentiment:xueqiu_web",
        source_role="sentiment_news",
        provider="xueqiu_web",
        items=items,
        status="warning" if errors else "ok",
        notes=[
            f"cookie_source={cookie_meta.get('source', 'file')}",
            f"cookie_probe={cookie_meta.get('probe_detail', '')}",
            *[
                f"candidate={item.get('browser')}:{item.get('profile')} | status={item.get('status')} | modified_at={item.get('modified_at')} | copy_method={item.get('copy_method', '')} | cookie_count={item.get('cookie_count', '')} | error={item.get('error', '')}"
                for item in (cookie_meta.get("tried", []) or [])
            ],
            *errors,
        ],
        configured=True,
        error_count=len(errors),
    )


def fetch_douyin_items(agent_home: Path, settings: dict, report_date: str, queries: list[dict]) -> tuple[list[dict], dict]:
    sentiment_settings = settings.get("providers", {}).get("sentiment_news", {}) or {}
    timeout_seconds = int(sentiment_settings.get("timeout_seconds", 20) or 20)
    results_per_keyword = int(sentiment_settings.get("results_per_keyword", 6) or 6)
    use_env_proxy = bool(sentiment_settings.get("use_env_proxy", True))
    cookie_value, cookie_meta = resolve_cookie_with_auto_sync(
        agent_home,
        settings,
        "douyin",
        sentiment_settings.get("douyin_cookie_file", ""),
        use_env_proxy=use_env_proxy,
        timeout_seconds=timeout_seconds,
    )
    if not cookie_value:
        return [], build_source_health_item(
            source_key="sentiment:douyin_web",
            source_role="sentiment_news",
            provider="douyin_web",
            status="warning",
            notes=[f"missing douyin cookie and browser sync failed: {cookie_meta.get('error', '')}"],
            configured=False,
        )
    session = build_cookie_session(DOUYIN_HEADERS, cookie_value, use_env_proxy=use_env_proxy)
    items = []
    errors = []
    try:
        for query in queries:
            response = get_response_with_retry(
                session,
                DOUYIN_SEARCH_API,
                timeout_seconds=timeout_seconds,
                params={
                    "device_platform": "webapp",
                    "aid": "6383",
                    "channel": "channel_pc_web",
                    "search_channel": "aweme_video_web",
                    "sort_type": 0,
                    "publish_time": 0,
                    "keyword": query["keyword"],
                    "search_source": "normal_search",
                    "query_correct_type": 1,
                    "is_filter_search": 0,
                    "offset": 0,
                    "count": results_per_keyword,
                    "from_group_id": "",
                    "pd": "synthesis",
                },
            )
            payload = response.json()
            extracted = extract_douyin_aweme_items(payload)
            if not extracted and (payload.get("search_nil_info", {}) or {}).get("search_nil_type") == "verify_check":
                errors.append(f"douyin verify_check keyword={query['keyword']}")
            for raw_item in extracted[:results_per_keyword]:
                for fund_code, fund_name in zip(query["fund_codes"], query["fund_names"] or query["fund_codes"]):
                    items.append(
                        normalize_provider_item(
                            {
                                **raw_item,
                                "code": fund_code,
                                "name": fund_name,
                                "matched_keywords": [query["keyword"]],
                                "source_name": "douyin_web",
                                "source_role": "sentiment_news",
                                "source_tier": "social_short_video",
                                "mapping_mode": "sentiment_background",
                                "evidence_type": "short_video_signal",
                                "sentiment_score": 0.15,
                                "novelty_score": 0.75,
                                "historical_significance": 0.1,
                                "crowding_signal": "crowded" if float(raw_item.get("virality_score", 0.0) or 0.0) >= 0.7 else "warming",
                            },
                            provider_name="douyin_web",
                            entity_id=fund_code,
                            entity_type="fund",
                            source_url=str(raw_item.get("url", "")),
                            source_title=str(raw_item.get("title", "")),
                            as_of=str(raw_item.get("published_at", "")),
                            freshness_status="fresh",
                            stale=not within_lookback(str(raw_item.get("published_at", "")), report_date, int(sentiment_settings.get("lookback_hours", 48) or 48)),
                            confidence=0.64,
                            source_role="sentiment_news",
                            source_tier="social_short_video",
                            mapping_mode="sentiment_background",
                            evidence_type="short_video_signal",
                        )
                    )
    except Exception as exc:
        errors.append(str(exc))
    finally:
        session.close()
    return items, build_source_health_item(
        source_key="sentiment:douyin_web",
        source_role="sentiment_news",
        provider="douyin_web",
        items=items,
        status="warning" if errors else "ok",
        notes=[
            f"cookie_source={cookie_meta.get('source', 'file')}",
            f"cookie_probe={cookie_meta.get('probe_detail', '')}",
            *[
                f"candidate={item.get('browser')}:{item.get('profile')} | status={item.get('status')} | modified_at={item.get('modified_at')} | copy_method={item.get('copy_method', '')} | cookie_count={item.get('cookie_count', '')} | error={item.get('error', '')}"
                for item in (cookie_meta.get("tried", []) or [])
            ],
            *errors,
        ],
        configured=True,
        error_count=len(errors),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch daily fund news and sentiment from configured providers or emit a demo payload.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--provider", help="Override the configured news provider name.")
    parser.add_argument("--demo", action="store_true", help="Write deterministic mock data.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    settings = load_settings(agent_home)
    watchlist = load_watchlist(agent_home)
    portfolio = load_portfolio(agent_home)
    report_date = resolve_date(args.date)
    fund_provider_chain = resolve_provider_chain(settings, "news", args.provider)
    sentiment_provider_chain = resolve_provider_chain(settings, "sentiment_news", None)
    provider_name = fund_provider_chain[0]
    source_health = []

    if args.demo or provider_name.startswith("demo"):
        items = build_demo_news(watchlist, report_date, provider_name)
    else:
        if provider_name not in {"eastmoney_notice_and_articles", "eastmoney"}:
            raise SystemExit(f"Unsupported news provider: {provider_name}")
        items = []
        workers = min(6, max(1, len(watchlist["funds"])))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_one_fund_news, fund, settings, report_date, provider_name): fund for fund in watchlist["funds"]}
            for future in as_completed(futures):
                fund = futures[future]
                try:
                    items.extend(future.result())
                except Exception as exc:
                    items.append(
                        annotate_news_item(
                            {
                                "published_at": timestamp_now(),
                                "title": f"{fund['name']}：新闻抓取失败占位记录",
                                "summary": f"抓取异常：{exc}",
                                "source_name": "system_placeholder",
                                "url": "",
                                "relevance_score": 0.1,
                            },
                            fund,
                            "system_placeholder",
                            report_date,
                        )
                    )
    source_health.append(
        build_source_health_item(
            source_key=f"news:{provider_name}",
            source_role="fund_news",
            provider=provider_name,
            items=[item for item in items if item.get("source_role") in {"fund_news", "theme_news", "market_news"}],
            status="warning" if any(item.get("stale", False) for item in items) else "ok",
        )
    )

    sentiment_queries = build_dynamic_sentiment_queries(portfolio, watchlist, settings)
    for sentiment_provider in sentiment_provider_chain:
        if sentiment_provider == "xueqiu_web":
            extra_items, health = fetch_xueqiu_items(agent_home, settings, report_date, sentiment_queries)
            items.extend(extra_items)
            source_health.append(health)
        elif sentiment_provider == "douyin_web":
            extra_items, health = fetch_douyin_items(agent_home, settings, report_date, sentiment_queries)
            items.extend(extra_items)
            source_health.append(health)

    items.sort(key=lambda item: item.get("published_at", ""), reverse=True)
    payload = build_provider_payload(report_date, provider_name, "items", items, source_health=source_health, sentiment_queries=sentiment_queries)
    freshness_status = "stale" if any(item.get("stale", False) for item in items) else "fresh"
    payload = build_provider_result(
        payload,
        provider_name=provider_name,
        provider_chain=[provider_name, *sentiment_provider_chain],
        freshness_status=freshness_status,
        confidence="medium" if freshness_status == "stale" else "high",
    )
    print(dump_json(news_path(agent_home, report_date), payload))


if __name__ == "__main__":
    main()
