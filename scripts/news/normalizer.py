from __future__ import annotations

import hashlib
import re
import urllib.parse
from typing import Any

from bs4 import BeautifulSoup


DEFAULT_CLASSIFIER_VERSION = "news_v1"


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
    return re.sub(r"\s+([）】])", r"\1", text)


def normalize_title_text(title: str) -> str:
    return re.sub(r"\s+", "", extract_plain_text(title or "").lower())


def news_content_hash(title: str, summary: str, canonical_url: str) -> str:
    digest = hashlib.sha1(f"{normalize_title_text(title)}|{extract_plain_text(summary)}|{canonical_url}".encode("utf-8")).hexdigest()
    return digest[:16]


def impact_from_classification(sentiment_label: str, risk_level: str) -> str:
    if sentiment_label == "negative" or risk_level == "high":
        return "negative"
    if sentiment_label == "positive":
        return "positive"
    return "neutral"


def enrich_news_item(
    item: dict[str, Any],
    *,
    query_type: str = "",
    matched_keywords: list[str] | None = None,
    classifier_version: str = DEFAULT_CLASSIFIER_VERSION,
) -> dict[str, Any]:
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
    enriched["classifier_version"] = str(item.get("classifier_version", "") or classifier_version)
    enriched["classification_status"] = str(item.get("classification_status", "") or "unclassified")
    confidence = item.get("classification_confidence")
    try:
        enriched["classification_confidence"] = max(0.0, min(1.0, float(confidence))) if confidence not in (None, "") else None
    except (TypeError, ValueError):
        enriched["classification_confidence"] = None
    enriched["classifier_model_run_id"] = str(item.get("classifier_model_run_id", "") or "")
    enriched["classifier_prompt_version"] = str(item.get("classifier_prompt_version", "") or "")
    enriched["impact"] = str(item.get("impact", "") or impact_from_classification(sentiment_label, risk_level))
    enriched["heat_score"] = float(item.get("heat_score", 0.0) or 0.0)
    enriched["heat_rank"] = int(item.get("heat_rank", 0) or 0)
    enriched["is_policy_signal"] = bool(item.get("is_policy_signal", False))
    enriched["is_hype_signal"] = bool(item.get("is_hype_signal", False))
    enriched["reason_short"] = str(item.get("reason_short", "") or "")
    return enriched
