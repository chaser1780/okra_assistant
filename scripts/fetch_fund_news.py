from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from threading import local

import requests
import win32crypt
from bs4 import BeautifulSoup

from common import dump_json, ensure_layout, load_portfolio, load_settings, load_watchlist, news_path, news_query_plan_path, resolve_agent_home, resolve_date, timestamp_now
from multiagent_utils import call_json_agent
from news_query_planner import build_news_query_plan, sentiment_queries_from_plan
from provider_adapters import build_provider_payload, build_provider_result, build_source_health_item, normalize_provider_item, resolve_provider_chain

EASTMONEY_NOTICE_API = "https://api.fund.eastmoney.com/f10/JJGG"
EASTMONEY_FUND_PAGE = "https://fund.eastmoney.com/{code}.html"
EASTMONEY_SEARCH_API = "https://search-api-web.eastmoney.com/search/jsonp"
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
def infer_impact(title: str) -> str:
    if any(keyword in title for keyword in NEGATIVE_KEYWORDS):
        return "negative"
    if any(keyword in title for keyword in POSITIVE_KEYWORDS):
        return "positive"
    return "neutral"


HIGH_RISK_KEYWORDS = ("风险", "清盘", "停牌", "处罚", "违约", "预警", "暂停", "排查", "调查", "减持", "离任")
POLICY_KEYWORDS = ("证监会", "发改委", "工信部", "财政部", "政策", "监管", "制度", "指引", "改革")
HYPE_KEYWORDS = ("热议", "热度", "爆了", "揭秘", "直播", "视频", "#", "短视频", "新声计划", "创作浪潮")
CLASSIFIER_VERSION = "news_v1"

NEWS_CLASSIFICATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer"},
                    "sentiment_label": {"type": "string", "enum": ["positive", "neutral", "negative", "mixed"]},
                    "sentiment_score": {"type": "number"},
                    "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                    "risk_tags": {"type": "array", "items": {"type": "string"}},
                    "topic_tags": {"type": "array", "items": {"type": "string"}},
                    "is_policy_signal": {"type": "boolean"},
                    "is_hype_signal": {"type": "boolean"},
                    "reason_short": {"type": "string"},
                },
                "required": [
                    "index",
                    "sentiment_label",
                    "sentiment_score",
                    "risk_level",
                    "risk_tags",
                    "topic_tags",
                    "is_policy_signal",
                    "is_hype_signal",
                    "reason_short",
                ],
            },
        }
    },
    "required": ["items"],
}


def canonicalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    query_pairs = []
    for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("spm") or lowered in {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "from"}:
            continue
        query_pairs.append((key, value))
    clean_query = urllib.parse.urlencode(sorted(query_pairs))
    clean_path = re.sub(r"/+$", "", parsed.path or "")
    return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), clean_path, "", clean_query, ""))


def normalize_title_text(title: str) -> str:
    return re.sub(r"\s+", "", extract_plain_text(title or "").lower())


def publish_time_bucket(published_at: str, bucket_hours: int = 6) -> str:
    published_dt = parse_iso_datetime(published_at)
    if published_dt is None:
        return ""
    hour = (published_dt.hour // max(1, bucket_hours)) * max(1, bucket_hours)
    return published_dt.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def news_content_hash(title: str, summary: str, canonical_url: str) -> str:
    digest = hashlib.sha1(f"{normalize_title_text(title)}|{extract_plain_text(summary)}|{canonical_url}".encode("utf-8")).hexdigest()
    return digest[:16]


def impact_from_classification(sentiment_label: str, risk_level: str) -> str:
    if sentiment_label == "negative" or risk_level == "high":
        return "negative"
    if sentiment_label == "positive":
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


def build_dynamic_sentiment_queries(portfolio: dict, watchlist: dict, settings: dict) -> list[dict]:
    return sentiment_queries_from_plan(build_news_query_plan(portfolio, watchlist, settings, ""))


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
        errors="replace",
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
        errors="replace",
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
    raw = str(value)
    if "<" not in raw and "&" not in raw:
        return " ".join(raw.split())
    soup = BeautifulSoup(raw, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    text = re.sub(r"\s+([，。、；：！？])", r"\1", text)
    text = re.sub(r"([（【])\s+", r"\1", text)
    text = re.sub(r"\s+([）】])", r"\1", text)
    return text


def parse_jsonp_payload(text: str) -> dict:
    match = re.search(r"^[^(]*\((.*)\)\s*;?\s*$", text.strip(), flags=re.S)
    if not match:
        return json.loads(text)
    return json.loads(match.group(1))


def enrich_news_item(item: dict, *, query_type: str = "", matched_keywords: list[str] | None = None) -> dict:
    canonical_url = canonicalize_url(str(item.get("canonical_url", "") or item.get("source_url", "") or item.get("url", "")))
    title = str(item.get("title", "") or "")
    summary = str(item.get("summary", "") or title)
    sentiment_label = str(item.get("sentiment_label", "") or "neutral")
    risk_level = str(item.get("risk_level", "") or "low")
    enriched = dict(item)
    enriched["canonical_url"] = canonical_url
    enriched["content_hash"] = str(item.get("content_hash", "") or news_content_hash(title, summary, canonical_url))
    enriched["query_type"] = str(query_type or item.get("query_type", "") or "")
    enriched["matched_keywords"] = list(matched_keywords or item.get("matched_keywords", []) or [])
    enriched["topic_tags"] = list(item.get("topic_tags", []) or [])
    enriched["risk_tags"] = list(item.get("risk_tags", []) or [])
    enriched["sentiment_label"] = sentiment_label
    enriched["risk_level"] = risk_level
    enriched["classifier"] = str(item.get("classifier", "") or "rule")
    enriched["classifier_version"] = str(item.get("classifier_version", "") or CLASSIFIER_VERSION)
    enriched["classification_status"] = str(item.get("classification_status", "") or "unclassified")
    enriched["impact"] = str(item.get("impact", "") or impact_from_classification(sentiment_label, risk_level))
    enriched["heat_score"] = float(item.get("heat_score", 0.0) or 0.0)
    enriched["heat_rank"] = int(item.get("heat_rank", 0) or 0)
    enriched["is_policy_signal"] = bool(item.get("is_policy_signal", False))
    enriched["is_hype_signal"] = bool(item.get("is_hype_signal", False))
    enriched["reason_short"] = str(item.get("reason_short", "") or "")
    return enriched


def rule_classify_news_item(item: dict) -> dict:
    title = str(item.get("title", "") or "")
    summary = str(item.get("summary", "") or "")
    source_name = str(item.get("source_name", "") or "")
    evidence_type = str(item.get("evidence_type", "") or "")
    joined = f"{title} {summary}"
    sentiment_label = "neutral"
    sentiment_score = float(item.get("sentiment_score", 0.0) or 0.0)
    if any(keyword in joined for keyword in NEGATIVE_KEYWORDS):
        sentiment_label = "negative"
        sentiment_score = min(sentiment_score, -0.45) if sentiment_score else -0.45
    elif any(keyword in joined for keyword in POSITIVE_KEYWORDS):
        sentiment_label = "positive"
        sentiment_score = max(sentiment_score, 0.45) if sentiment_score else 0.45
    risk_level = "high" if any(keyword in joined for keyword in HIGH_RISK_KEYWORDS) or evidence_type == "official_notice" else "low"
    if risk_level != "high" and any(keyword in joined for keyword in POLICY_KEYWORDS):
        risk_level = "medium"
    risk_tags = []
    if risk_level == "high":
        risk_tags.append("event_risk")
    if any(keyword in joined for keyword in POLICY_KEYWORDS):
        risk_tags.append("policy")
    topic_tags = list({keyword for keyword in (item.get("matched_keywords", []) or []) if keyword})
    is_policy_signal = any(keyword in joined for keyword in POLICY_KEYWORDS)
    is_hype_signal = any(keyword in joined for keyword in HYPE_KEYWORDS)
    if is_hype_signal and risk_level == "low":
        risk_level = "medium"
    if source_name == "eastmoney_notice" and risk_level == "low":
        risk_level = "medium"
    return {
        "sentiment_label": sentiment_label,
        "sentiment_score": round(max(-1.0, min(1.0, sentiment_score)), 4),
        "risk_level": risk_level,
        "risk_tags": risk_tags,
        "topic_tags": topic_tags,
        "is_policy_signal": is_policy_signal,
        "is_hype_signal": is_hype_signal,
        "reason_short": "rule fallback",
        "classifier": "rule",
        "classifier_version": CLASSIFIER_VERSION,
        "classification_status": "rule_fallback",
        "impact": impact_from_classification(sentiment_label, risk_level),
    }


def build_news_classification_prompts(batch: list[dict]) -> tuple[str, str]:
    system_prompt = (
        "You classify Chinese finance news into structured portfolio-research signals. "
        "Return strict JSON only. Use title and summary only. Be conservative on positive sentiment. "
        "High risk is for enforcement, liquidation, suspension, termination, manager departure, major policy shock, or severe warning."
    )
    lines = []
    for index, item in enumerate(batch):
        lines.append(
            json.dumps(
                {
                    "index": index,
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "source_name": item.get("source_name", ""),
                    "source_role": item.get("source_role", ""),
                    "published_at": item.get("published_at", ""),
                    "matched_keywords": item.get("matched_keywords", []),
                },
                ensure_ascii=False,
            )
        )
    user_prompt = (
        "Classify each item. topic_tags and risk_tags should be short identifiers. "
        "Return one result per input index.\n" + "\n".join(lines)
    )
    return system_prompt, user_prompt


def classify_news_with_llm(agent_home: Path, settings: dict, items: list[dict]) -> tuple[list[dict], dict]:
    cfg = settings.get("providers", {}).get("news_classification", {}) or {}
    if not bool(cfg.get("enabled", True)) or not items:
        return items, {"enabled": bool(cfg.get("enabled", True)), "mode": "disabled", "status": "disabled", "llm_batches": 0, "fallback_batches": 0}
    batch_size = int(cfg.get("batch_size", 20) or 20)
    timeout_seconds = int(cfg.get("timeout_seconds", 45) or 45)
    model_override = str(cfg.get("model", "") or "").strip()
    llm_batches = 0
    fallback_batches = 0
    classified = [dict(item) for item in items]
    for start in range(0, len(classified), batch_size):
        batch = classified[start : start + batch_size]
        system_prompt, user_prompt = build_news_classification_prompts(batch)
        try:
            response = call_json_agent(
                agent_home,
                system_prompt,
                user_prompt,
                schema=NEWS_CLASSIFICATION_SCHEMA,
                max_attempts=1,
                reasoning_effort="medium",
                request_name="news_batch_classifier",
                text_verbosity="low",
                temperature=0.1,
                timeout=(10, timeout_seconds),
            )
            result_items = {int(item.get("index", -1)): item for item in (response.get("response_json", {}) or {}).get("items", []) or []}
            llm_batches += 1
            for index, item in enumerate(batch):
                parsed = result_items.get(index)
                if not parsed:
                    parsed = rule_classify_news_item(item)
                else:
                    parsed = {
                        **parsed,
                        "classifier": model_override or "llm",
                        "classifier_version": CLASSIFIER_VERSION,
                        "classification_status": "llm",
                        "impact": impact_from_classification(str(parsed.get("sentiment_label", "neutral")), str(parsed.get("risk_level", "low"))),
                    }
                item.update(parsed)
        except Exception:
            fallback_batches += 1
            for item in batch:
                item.update(rule_classify_news_item(item))
    status = "ok" if llm_batches and fallback_batches == 0 else ("mixed" if llm_batches else "fallback_only")
    return classified, {
        "enabled": True,
        "mode": str(cfg.get("mode", "llm_first") or "llm_first"),
        "status": status,
        "llm_batches": llm_batches,
        "fallback_batches": fallback_batches,
        "batch_size": batch_size,
        "model": model_override or "default",
    }


def compute_heat_metrics(items: list[dict]) -> None:
    if not items:
        return
    topic_counter: Counter[str] = Counter()
    source_counter: defaultdict[str, set[str]] = defaultdict(set)
    duplicate_counter: Counter[str] = Counter()
    for item in items:
        canonical_key = str(item.get("canonical_url", "") or item.get("content_hash", "") or item.get("title", ""))
        duplicate_counter[canonical_key] += 1
        for keyword in item.get("matched_keywords", []) or []:
            topic_counter[str(keyword)] += 1
        source_counter[canonical_key].add(str(item.get("source_name", "") or item.get("provider", "")))
    scored: list[tuple[float, dict]] = []
    now = max((parse_iso_datetime(str(item.get("published_at", "") or "")) for item in items), default=None)
    for item in items:
        canonical_key = str(item.get("canonical_url", "") or item.get("content_hash", "") or item.get("title", ""))
        topic_hits = sum(topic_counter[str(keyword)] for keyword in item.get("matched_keywords", []) or [])
        source_diversity = len(source_counter[canonical_key])
        duplicate_count = duplicate_counter[canonical_key]
        published_dt = parse_iso_datetime(str(item.get("published_at", "") or ""))
        recency_bonus = 0.0
        if now and published_dt:
            age_hours = max(0.0, (now - published_dt).total_seconds() / 3600.0)
            recency_bonus = max(0.0, 1.0 - min(age_hours, 24.0) / 24.0)
        query_bonus = 0.35 if str(item.get("query_type", "")) == "direct" else (0.22 if str(item.get("query_type", "")) == "theme" else 0.15)
        duplicate_bonus = min(1.0, (duplicate_count - 1) * 0.2)
        source_bonus = min(1.0, source_diversity * 0.25)
        topic_bonus = min(1.0, topic_hits * 0.08)
        heat_score = round(min(1.0, 0.15 + recency_bonus * 0.3 + query_bonus + duplicate_bonus + source_bonus + topic_bonus), 4)
        item["heat_score"] = heat_score
        item["virality_score"] = max(float(item.get("virality_score", 0.0) or 0.0), heat_score)
        sentiment_score = float(item.get("sentiment_score", 0.0) or 0.0)
        if heat_score >= 0.75 and sentiment_score > 0.2:
            item["crowding_signal"] = "crowded"
        elif heat_score >= 0.75 and sentiment_score < -0.2:
            item["crowding_signal"] = "capitulation"
        elif heat_score >= 0.45:
            item["crowding_signal"] = "warming"
        else:
            item["crowding_signal"] = str(item.get("crowding_signal", "") or "neutral")
        scored.append((heat_score, item))
    scored.sort(key=lambda row: (row[0], row[1].get("published_at", "")), reverse=True)
    for rank, (_score, item) in enumerate(scored, start=1):
        item["heat_rank"] = rank


def dedupe_news_items(items: list[dict], *, dedup_window_hours: int) -> tuple[list[dict], dict]:
    deduped: list[dict] = []
    canonical_seen: set[str] = set()
    mapped_seen: set[tuple[str, str]] = set()
    duplicate_item_count = 0
    dedup_drop_count = 0
    for item in sorted(items, key=lambda row: row.get("published_at", ""), reverse=True):
        enriched = enrich_news_item(item, query_type=str(item.get("query_type", "") or ""), matched_keywords=list(item.get("matched_keywords", []) or []))
        canonical_key = str(enriched.get("canonical_url", "") or news_content_hash(str(enriched.get("title", "")), str(enriched.get("summary", "")), ""))
        mapped_key = (str(enriched.get("code", "") or ""), canonical_key)
        if mapped_key in mapped_seen:
            dedup_drop_count += 1
            continue
        if canonical_key in canonical_seen:
            duplicate_item_count += 1
        canonical_seen.add(canonical_key)
        mapped_seen.add(mapped_key)
        deduped.append(enriched)
    return deduped, {
        "mapped_item_count": len(deduped),
        "unique_item_count": len(canonical_seen),
        "duplicate_item_count": duplicate_item_count,
        "dedup_drop_count": dedup_drop_count,
        "dedup_window_hours": dedup_window_hours,
    }


def news_dedup_summary(items: list[dict], *, dedup_window_hours: int) -> dict:
    canonical_seen: set[str] = set()
    mapped_seen: set[tuple[str, str]] = set()
    duplicate_item_count = 0
    dedup_drop_count = 0
    for item in sorted(items, key=lambda row: row.get("published_at", ""), reverse=True):
        enriched = enrich_news_item(item, query_type=str(item.get("query_type", "") or ""), matched_keywords=list(item.get("matched_keywords", []) or []))
        canonical_key = str(enriched.get("canonical_url", "") or news_content_hash(str(enriched.get("title", "")), str(enriched.get("summary", "")), ""))
        mapped_key = (str(enriched.get("code", "") or ""), canonical_key)
        if mapped_key in mapped_seen:
            dedup_drop_count += 1
            continue
        if canonical_key in canonical_seen:
            duplicate_item_count += 1
        canonical_seen.add(canonical_key)
        mapped_seen.add(mapped_key)
    return {
        "mapped_item_count": len(mapped_seen),
        "unique_item_count": len(canonical_seen),
        "duplicate_item_count": duplicate_item_count,
        "dedup_drop_count": dedup_drop_count,
        "dedup_window_hours": dedup_window_hours,
    }


def parse_rss_datetime(value: str | None, report_date: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return f"{report_date}T00:00:00+08:00"
    if re.match(r"^\d{4}-\d{2}-\d{2}(?:[T\s]|$)", candidate):
        parsed = parse_iso_datetime(candidate)
        if parsed is not None:
            return parsed.isoformat(timespec="seconds")
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(candidate, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CN_TZ)
            return dt.isoformat(timespec="seconds")
        except ValueError:
            continue
    try:
        dt = parsedate_to_datetime(candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=CN_TZ)
        return dt.isoformat(timespec="seconds")
    except (TypeError, ValueError, IndexError):
        pass
    return f"{report_date}T00:00:00+08:00"


def fetch_xml_text(url: str, *, timeout_seconds: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json_text(url: str, *, timeout_seconds: int, referer: str = "") -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Referer": referer or DEFAULT_HEADERS["Referer"],
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_rss_feed(xml_text: str, report_date: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items: list[dict] = []
    for node in root.findall(".//item") + root.findall(".//entry"):
        title = extract_plain_text(node.findtext("title") or "")
        summary = extract_plain_text(node.findtext("description") or node.findtext("summary") or node.findtext("{http://www.w3.org/2005/Atom}summary") or title)
        link = node.findtext("link") or ""
        if not link:
            link_node = node.find("link")
            if link_node is not None:
                link = link_node.attrib.get("href", "")
        published_at = parse_rss_datetime(
            node.findtext("pubDate")
            or node.findtext("published")
            or node.findtext("{http://www.w3.org/2005/Atom}published")
            or node.findtext("updated")
            or node.findtext("{http://www.w3.org/2005/Atom}updated"),
            report_date,
        )
        if not title or not link:
            continue
        items.append(
            {
                "title": title[:120],
                "summary": summary[:240] or title[:120],
                "published_at": published_at,
                "url": link.strip(),
            }
        )
    return items


def rss_source_role(feed_name: str, query: dict) -> tuple[str, str, str]:
    query_type = str(query.get("query_type", "") or "")
    lower_name = str(feed_name or "").lower()
    if query_type == "market" or any(token in lower_name for token in ("market", "macro", "global")):
        return "market_news", "market_news", "market_media"
    if query_type == "direct":
        return "fund_news", "theme_news", "financial_media"
    return "theme_news", "theme_news", "financial_media"


def rss_feed_role(feed: dict, feed_name: str, query: dict) -> tuple[str, str, str]:
    configured_role = str(feed.get("source_role", "") or "").strip()
    configured_tier = str(feed.get("source_tier", "") or "").strip()
    if configured_role:
        evidence_type = "market_news" if configured_role == "market_news" else ("theme_news" if configured_role in {"theme_news", "fund_news"} else configured_role)
        source_tier = configured_tier or ("market_media" if configured_role == "market_news" else "financial_media")
        return configured_role, evidence_type, source_tier
    return rss_source_role(feed_name, query)


def normalize_rss_news_item(raw_item: dict, query: dict, *, feed_name: str, provider_name: str, report_date: str, feed: dict | None = None) -> list[dict]:
    source_role, evidence_type, source_tier = rss_feed_role(feed or {}, feed_name, query)
    mapping_mode = "market_background" if source_role == "market_news" else ("direct_fund" if source_role == "fund_news" else "theme_match")
    stale = not within_lookback(str(raw_item.get("published_at", "")), report_date, 96)
    normalized = []
    for fund_code, fund_name in fund_names_for_query(query):
        normalized.append(
            normalize_provider_item(
                {
                    **raw_item,
                    "code": fund_code,
                    "name": fund_name,
                    "matched_keywords": [str(query.get("keyword", "") or "")],
                    "source_name": feed_name,
                    "source_role": source_role,
                    "source_tier": source_tier,
                    "mapping_mode": mapping_mode,
                    "evidence_type": evidence_type,
                    "query_type": str(query.get("query_type", "") or ""),
                    "sentiment_score": 0.0,
                    "novelty_score": 0.64,
                    "virality_score": 0.18,
                    "historical_significance": 0.2 if source_role == "market_news" else 0.1,
                    "crowding_signal": "neutral",
                    "sentiment_label": "neutral",
                    "risk_level": "low",
                    "classification_status": "unclassified",
                },
                provider_name=provider_name,
                entity_id=fund_code,
                entity_type="fund",
                source_url=str(raw_item.get("url", "")),
                source_title=str(raw_item.get("title", "")),
                as_of=str(raw_item.get("published_at", "")),
                freshness_status="stale" if stale else "fresh",
                stale=stale,
                confidence=0.57,
                source_role=source_role,
                source_tier=source_tier,
                mapping_mode=mapping_mode,
                evidence_type=evidence_type,
            )
        )
    return normalized


def fetch_rss_news(settings: dict, report_date: str, query_plan: dict) -> tuple[list[dict], list[dict]]:
    provider_settings = settings.get("providers", {}).get("rss_news", {}) or {}
    if not bool(provider_settings.get("enabled", False)):
        return [], []
    timeout_seconds = int(provider_settings.get("timeout_seconds", 12) or 12)
    feeds = list(provider_settings.get("feeds", []) or [])
    if not feeds:
        return [], [
            build_source_health_item(
                source_key="rss_news:feeds",
                source_role="theme_news",
                provider="rss_news",
                configured=True,
                status="warning",
                notes=["rss feeds not configured"],
            )
        ]
    all_items: list[dict] = []
    health_rows: list[dict] = []
    combined_queries = [
        *(query_plan.get("direct_queries", []) or []),
        *(query_plan.get("theme_queries", []) or []),
        *(query_plan.get("market_queries", []) or []),
    ]
    for feed in feeds:
        if not bool(feed.get("enabled", True)):
            continue
        feed_url = str(feed.get("url", "") or "").strip()
        feed_name = str(feed.get("name", "") or feed_url or "rss_feed")
        provider_name = str(feed.get("provider", "") or f"rss:{feed_name}")
        if not feed_url:
            health_rows.append(
                build_source_health_item(
                    source_key=f"rss_news:{provider_name}",
                    source_role="theme_news",
                    provider=provider_name,
                    configured=False,
                    status="warning",
                    notes=["missing feed url"],
                )
            )
            continue
        errors: list[str] = []
        raw_item_count = 0
        matched_count = 0
        try:
            xml_text = fetch_xml_text(feed_url, timeout_seconds=timeout_seconds)
            rows = parse_rss_feed(xml_text, report_date)
            raw_item_count = len(rows)
            for raw_item in rows:
                for query in combined_queries:
                    keyword = str(query.get("keyword", "") or "").strip()
                    if not keyword or not query_matches_item(keyword, raw_item):
                        continue
                    matched_count += 1
                    all_items.extend(normalize_rss_news_item(raw_item, query, feed_name=feed_name, provider_name=provider_name, report_date=report_date, feed=feed))
        except ET.ParseError as exc:
            errors.append(f"parse_error={exc}")
        except Exception as exc:
            errors.append(str(exc))
        status = "ok" if matched_count > 0 and not errors else ("warning" if errors or raw_item_count == 0 else "ok")
        notes = [f"feed_url={feed_url}", f"raw_item_count={raw_item_count}", f"matched_item_count={matched_count}", *errors[:4]]
        health_rows.append(
            build_source_health_item(
                source_key=f"rss_news:{provider_name}",
                source_role="theme_news",
                provider=provider_name,
                items=[item for item in all_items if item.get("provider") == provider_name],
                configured=True,
                status=status,
                notes=notes,
                error_count=len(errors),
                warning_count=1 if status == "warning" else 0,
                metrics={
                    "raw_item_count": raw_item_count,
                    "matched_item_count": matched_count,
                    "feed_ok": int(not errors and raw_item_count > 0),
                    "parse_error": int(any("parse_error" in error for error in errors)),
                    "empty_feed": int(raw_item_count == 0),
                    "stale_feed": 0,
                },
            )
        )
    return all_items, health_rows


def absolute_url(base_url: str, href: str) -> str:
    return urllib.parse.urljoin(base_url, href)


def parse_sse_general_announcements(html_text: str, feed_url: str, report_date: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    rows: list[dict] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "") or "").strip()
        title = " ".join((anchor.get("title") or anchor.get_text(" ", strip=True) or "").split())
        if not href or not title or "/disclosure/announcement/general/" not in href:
            continue
        url = absolute_url(feed_url, href)
        if url in seen:
            continue
        seen.add(url)
        match = re.search(r"c_(\d{8})_", url)
        published_at = f"{report_date}T00:00:00+08:00"
        if match:
            date_text = match.group(1)
            published_at = f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:8]}T00:00:00+08:00"
        rows.append(
            {
                "title": title[:120],
                "summary": title[:240],
                "published_at": published_at,
                "url": url,
            }
        )
    return rows


def parse_amac_notice_board(html_text: str, feed_url: str, report_date: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    rows: list[dict] = []
    seen: set[str] = set()
    allowed_markers = ("/zlgl/jlcf/", "/zlgl/ycjy/ycjyjgclgg/", "/zlgl/sljg/sljgclgg/")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "") or "").strip()
        title = " ".join((anchor.get("title") or anchor.get_text(" ", strip=True) or "").split())
        if not href or not title or not any(marker in href for marker in allowed_markers):
            continue
        url = absolute_url(feed_url, href)
        if url in seen:
            continue
        seen.add(url)
        published_at = f"{report_date}T00:00:00+08:00"
        match = re.search(r"/(20\d{2})(\d{2})/(?:t|P)20\d+", href)
        if match:
            published_at = f"{match.group(1)}-{match.group(2)}-01T00:00:00+08:00"
        title_for_risk = title
        rows.append(
            {
                "title": title_for_risk[:120],
                "summary": title_for_risk[:240],
                "published_at": published_at,
                "url": url,
            }
        )
    return rows


def _extract_szse_attachment_url(value: object) -> str:
    text = str(value or "")
    match = re.search(r"encode-open=['\"]([^'\"]+)['\"]", text)
    if match:
        return absolute_url("https://www.szse.cn/", match.group(1))
    match = re.search(r"href=['\"]([^'\"]+)['\"]", text)
    if match:
        href = match.group(1)
        if not href.startswith("javascript:"):
            return absolute_url("https://www.szse.cn/", href)
    return ""


def parse_szse_report_json(json_text: str, feed_url: str, report_date: str) -> list[dict]:
    payload = json.loads(json_text)
    tabs = payload if isinstance(payload, list) else [payload]
    rows: list[dict] = []
    seen: set[str] = set()
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        metadata = tab.get("metadata", {}) or {}
        tab_name = str(metadata.get("name", "") or "")
        for item in tab.get("data", []) or tab.get("tableData", []) or []:
            if not isinstance(item, dict):
                continue
            code = str(item.get("gsdm") or item.get("gkxx_gsdm") or item.get("xx_gsdm") or "").strip()
            company = str(item.get("gsjc") or item.get("gkxx_gsjc") or item.get("jc_gsjc") or "").strip()
            event_date = str(item.get("fhrq") or item.get("gkxx_gdrq") or item.get("xx_fwrq") or report_date).strip()[:10]
            category = str(item.get("hjlb") or item.get("gkxx_jgcs") or item.get("xx_cflb") or tab_name or "监管信息").strip()
            explicit_title = extract_plain_text(str(item.get("xx_bt") or item.get("title") or ""))
            title = explicit_title or " ".join(part for part in (company, category) if part)
            if not title:
                continue
            url = _extract_szse_attachment_url(item.get("ck") or item.get("hjnr") or item.get("hfck") or "")
            dedupe_key = url or f"{code}|{event_date}|{title}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(
                {
                    "title": title[:120],
                    "summary": " | ".join(part for part in (code, company, category, tab_name) if part)[:240] or title[:240],
                    "published_at": f"{event_date or report_date}T00:00:00+08:00",
                    "url": url or feed_url,
                }
            )
    return rows


def parse_szse_notice_page(html_text: str, feed_url: str, report_date: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    rows: list[dict] = []
    seen: set[str] = set()
    allowed_markers = (
        "/disclosure/listed/notice/",
        "/disclosure/supervision/inquire/",
        "/disclosure/supervision/measure/",
        "/disclosure/supervision/discipline/",
    )
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "") or "").strip()
        title = " ".join((anchor.get("title") or anchor.get_text(" ", strip=True) or "").split())
        if anchor.find_parent("ul") or anchor.find_parent(class_=re.compile("menu|nav", re.I)):
            continue
        if not href or not title or not any(marker in href for marker in allowed_markers):
            continue
        if href.endswith("/index.html") or len(title) <= 4:
            continue
        url = absolute_url(feed_url, href)
        if url in seen:
            continue
        seen.add(url)
        published_at = f"{report_date}T00:00:00+08:00"
        match = re.search(r"(20\d{2})[-_/]?(\d{2})[-_/]?(\d{2})", href)
        if match:
            published_at = f"{match.group(1)}-{match.group(2)}-{match.group(3)}T00:00:00+08:00"
        rows.append(
            {
                "title": title[:120],
                "summary": title[:240],
                "published_at": published_at,
                "url": url,
            }
        )
    return rows


def normalize_regulatory_item(raw_item: dict, *, provider_name: str, feed_name: str, report_date: str) -> dict:
    title = str(raw_item.get("title", "") or "")
    summary = str(raw_item.get("summary", "") or title)
    published_at = str(raw_item.get("published_at", "") or f"{report_date}T00:00:00+08:00")
    stale = not within_lookback(published_at, report_date, 168)
    impact = "negative" if any(keyword in title for keyword in HIGH_RISK_KEYWORDS) else "neutral"
    risk_level = "high" if any(keyword in title for keyword in HIGH_RISK_KEYWORDS) else "medium"
    return normalize_provider_item(
        enrich_news_item(
            {
                "code": "GLOBAL",
                "name": "监管公告",
                "title": title,
                "summary": summary,
                "published_at": published_at,
                "source_name": feed_name,
                "source_role": "regulatory_news",
                "source_tier": "official_policy",
                "mapping_mode": "market_background",
                "evidence_type": "regulatory_notice",
                "impact": impact,
                "sentiment_label": "negative" if impact == "negative" else "neutral",
                "risk_level": risk_level,
                "risk_tags": ["regulatory"],
                "topic_tags": ["regulatory_notice"],
                "sentiment_score": -0.5 if impact == "negative" else 0.0,
                "novelty_score": 0.75,
                "virality_score": 0.15,
                "historical_significance": 0.8,
                "crowding_signal": "neutral",
                "classification_status": "rule_fallback",
                "classifier": "regulatory_rule",
                "classifier_version": CLASSIFIER_VERSION,
                "is_policy_signal": True,
                "is_hype_signal": False,
                "reason_short": "official regulatory notice",
                "url": str(raw_item.get("url", "") or ""),
            }
        ),
        provider_name=provider_name,
        entity_id="GLOBAL",
        entity_type="market",
        source_url=str(raw_item.get("url", "") or ""),
        source_title=title,
        as_of=published_at,
        freshness_status="stale" if stale else "fresh",
        stale=stale,
        confidence=0.88,
        source_role="regulatory_news",
        source_tier="official_policy",
        mapping_mode="market_background",
        evidence_type="regulatory_notice",
    )


def fetch_regulatory_news(settings: dict, report_date: str) -> tuple[list[dict], list[dict]]:
    provider_settings = settings.get("providers", {}).get("regulatory_news", {}) or {}
    if not bool(provider_settings.get("enabled", False)):
        return [], []
    timeout_seconds = int(provider_settings.get("timeout_seconds", 15) or 15)
    feeds = list(provider_settings.get("feeds", []) or [])
    items: list[dict] = []
    health_rows: list[dict] = []
    for feed in feeds:
        if not bool(feed.get("enabled", True)):
            continue
        feed_url = str(feed.get("url", "") or "").strip()
        feed_name = str(feed.get("name", "") or feed_url or "regulatory_feed")
        provider_name = str(feed.get("provider", "") or f"reg:{feed_name}")
        errors: list[str] = []
        raw_item_count = 0
        normalized_count = 0
        try:
            if provider_name == "reg:szse_inquiry":
                api_url = "https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=main_wxhj"
                rows = parse_szse_report_json(fetch_json_text(api_url, timeout_seconds=timeout_seconds, referer=feed_url), api_url, report_date)
            elif provider_name == "reg:szse_supervision_measure":
                api_url = "https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1800_jgxxgk"
                rows = parse_szse_report_json(fetch_json_text(api_url, timeout_seconds=timeout_seconds, referer=feed_url), api_url, report_date)
            elif provider_name == "reg:szse_disciplinary_action":
                api_url = "https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1800_jgxxgk_cf"
                rows = parse_szse_report_json(fetch_json_text(api_url, timeout_seconds=timeout_seconds, referer=feed_url), api_url, report_date)
            else:
                html_text = fetch_xml_text(feed_url, timeout_seconds=timeout_seconds)
                if provider_name == "reg:sse_general":
                    rows = parse_sse_general_announcements(html_text, feed_url, report_date)
                elif provider_name == "reg:amac_notice":
                    rows = parse_amac_notice_board(html_text, feed_url, report_date)
                elif provider_name == "reg:szse_listed_notice":
                    rows = parse_szse_notice_page(html_text, feed_url, report_date)
                    if not rows:
                        errors.append("szse listed notice page is dynamic; no official JSON endpoint enabled yet")
                else:
                    rows = []
            raw_item_count = len(rows)
            for raw_item in rows:
                items.append(normalize_regulatory_item(raw_item, provider_name=provider_name, feed_name=feed_name, report_date=report_date))
                normalized_count += 1
        except Exception as exc:
            errors.append(str(exc))
        status = "ok" if normalized_count > 0 and not errors else "warning"
        health_rows.append(
            build_source_health_item(
                source_key=f"regulatory_news:{provider_name}",
                source_role="regulatory_news",
                provider=provider_name,
                items=[item for item in items if item.get("provider") == provider_name],
                configured=True,
                status=status,
                notes=[f"feed_url={feed_url}", f"raw_item_count={raw_item_count}", f"normalized_count={normalized_count}", *errors[:4]],
                error_count=len(errors),
                warning_count=1 if status == "warning" else 0,
                metrics={
                    "raw_item_count": raw_item_count,
                    "normalized_count": normalized_count,
                    "sample_titles": [str(item.get("title", "") or "")[:60] for item in items if item.get("provider") == provider_name][:3],
                },
            )
        )
    return items, health_rows


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


def parse_eastmoney_article_time(value: str | None) -> str:
    if not value:
        return timestamp_now()
    candidate = str(value).strip()
    try:
        return datetime.strptime(candidate, "%Y-%m-%d %H:%M:%S").replace(tzinfo=CN_TZ).isoformat(timespec="seconds")
    except ValueError:
        try:
            parsed = parse_iso_datetime(candidate)
        except ValueError:
            parsed = None
        return parsed.isoformat(timespec="seconds") if parsed else timestamp_now()


def extract_eastmoney_search_items(payload: dict) -> list[dict]:
    rows = ((payload.get("result") or {}).get("cmsArticleWebOld") or [])
    items = []
    seen = set()
    for row in rows:
        title = extract_plain_text(str(row.get("title", "") or ""))
        url = str(row.get("url", "") or "")
        if not title or not url or (url, title) in seen:
            continue
        seen.add((url, title))
        content = extract_plain_text(str(row.get("content", "") or ""))
        items.append(
            {
                "title": title[:120],
                "summary": content[:240] or title[:120],
                "published_at": parse_eastmoney_article_time(row.get("date")),
                "source_name": str(row.get("mediaName", "") or "eastmoney_search"),
                "url": url,
                "relevance_score": 0.66,
                "source_code": str(row.get("code", "") or ""),
            }
        )
    return items


def eastmoney_search_jsonp(keyword: str, *, page_size: int, timeout_seconds: int) -> dict:
    callback = f"jQuery{int(time.time() * 1000)}"
    payload = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "<em>",
                "postTag": "</em>",
            }
        },
    }
    encoded = urllib.parse.quote(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), safe="")
    url = f"{EASTMONEY_SEARCH_API}?cb={callback}&param={encoded}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Referer": f"https://so.eastmoney.com/news/s?keyword={urllib.parse.quote(keyword)}",
            "Accept": "application/json,text/javascript,*/*;q=0.01",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8", errors="replace")
    return parse_jsonp_payload(body)


def query_matches_item(keyword: str, item: dict) -> bool:
    lowered_keyword = str(keyword or "").lower()
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return bool(lowered_keyword and lowered_keyword in haystack)


def fund_names_for_query(query: dict) -> list[tuple[str, str]]:
    codes = [str(item) for item in query.get("fund_codes", []) or []]
    names = [str(item) for item in query.get("fund_names", []) or []]
    if not codes:
        return []
    if len(names) < len(codes):
        names = [*names, *codes[len(names) :]]
    return list(zip(codes, names))


def normalize_query_news_item(raw_item: dict, query: dict, *, source_role: str, report_date: str) -> list[dict]:
    keyword = str(query.get("keyword", "") or "")
    query_type = str(query.get("query_type", "") or "")
    evidence_type = "market_news" if source_role == "market_news" else "theme_news"
    source_tier = "market_media" if source_role == "market_news" else "financial_media"
    mapping_mode = "market_background" if source_role == "market_news" else "theme_match"
    normalized = []
    stale = not within_lookback(str(raw_item.get("published_at", "")), report_date, 96)
    for fund_code, fund_name in fund_names_for_query(query):
        normalized.append(
            normalize_provider_item(
                {
                    **raw_item,
                    "code": fund_code,
                    "name": fund_name,
                    "matched_keywords": [keyword],
                    "source_name": raw_item.get("source_name", "eastmoney_search"),
                    "source_role": source_role,
                    "source_tier": source_tier,
                    "mapping_mode": mapping_mode,
                    "evidence_type": evidence_type,
                    "query_type": query_type,
                    "sentiment_score": 0.0,
                    "novelty_score": 0.68,
                    "virality_score": 0.2,
                    "historical_significance": 0.3 if source_role == "market_news" else 0.15,
                    "crowding_signal": "neutral",
                    "sentiment_label": "neutral",
                    "risk_level": "low",
                    "classification_status": "unclassified",
                },
                provider_name="eastmoney_search_api",
                entity_id=fund_code,
                entity_type="fund",
                source_url=str(raw_item.get("url", "")),
                source_title=str(raw_item.get("title", "")),
                as_of=str(raw_item.get("published_at", "")),
                freshness_status="stale" if stale else "fresh",
                stale=stale,
                confidence=0.62 if query_matches_item(keyword, raw_item) else 0.45,
                source_role=source_role,
                source_tier=source_tier,
                mapping_mode=mapping_mode,
                evidence_type=evidence_type,
            )
        )
    return normalized


def fetch_eastmoney_query_news(settings: dict, report_date: str, query_plan: dict) -> tuple[list[dict], dict]:
    provider_settings = settings.get("providers", {}).get("query_news", {}) or {}
    if not bool(provider_settings.get("enabled", True)):
        return [], build_source_health_item(
            source_key="query_news:eastmoney_search_api",
            source_role="theme_news",
            provider="eastmoney_search_api",
            configured=False,
            status="disabled",
            notes=["query_news provider disabled"],
        )
    timeout_seconds = int(provider_settings.get("timeout_seconds", settings.get("providers", {}).get("news", {}).get("timeout_seconds", 15)) or 15)
    page_size = int(provider_settings.get("results_per_query", 3) or 3)
    max_queries = int(provider_settings.get("max_queries", 10) or 10)
    query_buckets = []
    if bool(provider_settings.get("include_direct_queries", True)):
        query_buckets.append(("theme_news", list(query_plan.get("direct_queries", []) or [])))
    query_buckets.extend(
        [
            ("theme_news", list(query_plan.get("theme_queries", []) or [])),
            ("market_news", list(query_plan.get("market_queries", []) or [])),
        ]
    )
    per_bucket_limit = int(provider_settings.get("max_queries_per_bucket", max(1, max_queries // max(1, len(query_buckets)))) or 1)
    items: list[dict] = []
    errors: list[str] = []
    raw_rows: list[dict] = []
    raw_article_keys: set[str] = set()
    used_queries = 0
    skipped_queries = 0
    for source_role, queries in query_buckets:
        used_bucket_queries = 0
        for query in queries:
            if used_queries >= max_queries or used_bucket_queries >= per_bucket_limit:
                break
            keyword = str(query.get("keyword", "") or "").strip()
            if len(keyword) < 2:
                skipped_queries += 1
                continue
            used_queries += 1
            used_bucket_queries += 1
            try:
                payload = eastmoney_search_jsonp(keyword, page_size=page_size, timeout_seconds=timeout_seconds)
                extracted = [item for item in extract_eastmoney_search_items(payload) if query_matches_item(keyword, item)]
                for raw_item in extracted[:page_size]:
                    if raw_item.get("url"):
                        raw_article_keys.add(str(raw_item.get("url")))
                    raw_rows.extend(normalize_query_news_item(raw_item, query, source_role=source_role, report_date=report_date))
            except Exception as exc:
                errors.append(f"{keyword}: {exc}")
    dedup_window_hours = int(provider_settings.get("dedup_window_hours", 12) or 12)
    items, dedup_stats = dedupe_news_items(raw_rows, dedup_window_hours=dedup_window_hours)
    notes = [
        f"queries_used={used_queries}",
        f"queries_skipped={skipped_queries}",
        f"raw_article_count={len(raw_article_keys)}",
        f"unique_article_count={dedup_stats['unique_item_count']}",
        f"mapped_item_count={dedup_stats['mapped_item_count']}",
        f"dedup_drop_count={dedup_stats['dedup_drop_count']}",
        f"max_queries_per_bucket={per_bucket_limit}",
        f"results_per_query={page_size}",
        *errors[:6],
    ]
    return items, build_source_health_item(
        source_key="query_news:eastmoney_search_api",
        source_role="theme_news",
        provider="eastmoney_search_api",
        items=items,
        status="warning" if errors else "ok",
        notes=notes,
        error_count=len(errors),
        warning_count=1 if errors else 0,
        metrics={
            "queries_used": used_queries,
            "queries_skipped": skipped_queries,
            "raw_article_count": len(raw_article_keys),
            "unique_article_count": dedup_stats["unique_item_count"],
            "mapped_item_count": dedup_stats["mapped_item_count"],
            "duplicate_item_count": dedup_stats["duplicate_item_count"],
            "dedup_drop_count": dedup_stats["dedup_drop_count"],
            "stale_item_count": sum(1 for item in items if bool(item.get("stale", False))),
        },
    )


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


def disabled_social_source_health(provider: str) -> dict:
    return build_source_health_item(
        source_key=f"sentiment:{provider}",
        source_role="sentiment_news",
        provider=provider,
        configured=False,
        status="disabled",
        notes=["provider disabled by default"],
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
    query_plan = build_news_query_plan(portfolio, watchlist, settings, report_date)
    dump_json(news_query_plan_path(agent_home, report_date), query_plan)
    classification_summary = {"enabled": False, "mode": "disabled", "status": "disabled", "llm_batches": 0, "fallback_batches": 0}

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
        query_items, query_health = fetch_eastmoney_query_news(settings, report_date, query_plan)
        items.extend(query_items)
        source_health.append(query_health)
        rss_items, rss_health = fetch_rss_news(settings, report_date, query_plan)
        items.extend(rss_items)
        source_health.extend(rss_health)
        regulatory_items, regulatory_health = fetch_regulatory_news(settings, report_date)
        items.extend(regulatory_items)
        source_health.extend(regulatory_health)
    dedup_window_hours = int((settings.get("providers", {}).get("query_news", {}) or {}).get("dedup_window_hours", 12) or 12)
    items, dedup_stats = dedupe_news_items(items, dedup_window_hours=dedup_window_hours)
    items, classification_summary = classify_news_with_llm(agent_home, settings, items)
    items = [enrich_news_item(item, query_type=str(item.get("query_type", "") or ""), matched_keywords=list(item.get("matched_keywords", []) or [])) for item in items]
    compute_heat_metrics(items)
    provider_items = [
        item
        for item in items
        if item.get("provider") == provider_name and item.get("source_role") in {"fund_news", "theme_news", "market_news"}
    ]
    provider_dedup_stats = news_dedup_summary(provider_items, dedup_window_hours=dedup_window_hours)
    source_health.append(
        build_source_health_item(
            source_key=f"news:{provider_name}",
            source_role="fund_news",
            provider=provider_name,
            items=provider_items,
            status="warning" if any(item.get("stale", False) for item in items if item.get("provider") == provider_name) else "ok",
            metrics={
                "mapped_item_count": provider_dedup_stats["mapped_item_count"],
                "unique_item_count": provider_dedup_stats["unique_item_count"],
                "duplicate_item_count": provider_dedup_stats["duplicate_item_count"],
            },
        )
    )

    sentiment_queries = sentiment_queries_from_plan(query_plan)
    sentiment_enabled = bool((settings.get("providers", {}).get("sentiment_news", {}) or {}).get("enabled", False))
    if sentiment_enabled:
        for sentiment_provider in sentiment_provider_chain:
            if sentiment_provider == "xueqiu_web":
                extra_items, health = fetch_xueqiu_items(agent_home, settings, report_date, sentiment_queries)
                items.extend(extra_items)
                source_health.append(health)
            elif sentiment_provider == "douyin_web":
                extra_items, health = fetch_douyin_items(agent_home, settings, report_date, sentiment_queries)
                items.extend(extra_items)
                source_health.append(health)
    else:
        source_health.extend(disabled_social_source_health(provider) for provider in sentiment_provider_chain if provider in {"xueqiu_web", "douyin_web"})

    global_dedup_summary = news_dedup_summary(items, dedup_window_hours=dedup_window_hours)
    items.sort(key=lambda item: item.get("published_at", ""), reverse=True)
    payload = build_provider_payload(
        report_date,
        provider_name,
        "items",
        items,
        source_health=source_health,
        query_plan=query_plan,
        sentiment_queries=sentiment_queries,
        dedup_summary=dedup_stats,
        global_dedup_summary=global_dedup_summary,
        classification_summary=classification_summary,
    )
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
