from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict
import re

from common import (
    dump_json,
    ensure_layout,
    estimated_nav_path,
    fund_profile_path,
    intraday_proxy_path,
    llm_context_path,
    load_json,
    load_market_overrides,
    load_portfolio,
    load_review_memory,
    load_strategy,
    news_path,
    parse_date_text,
    quote_path,
    resolve_agent_home,
    resolve_date,
    source_health_path,
    timestamp_now,
)
from models import EvidenceItem, EvidenceRef, EstimateSnapshot, FundContextItem, FundProfile, LlmContext, MemoryRecord, NewsItem, PortfolioFund, ProxySnapshot, QuoteSnapshot, SourceHealthItem
from portfolio_exposure import analyze_portfolio_exposure, infer_strategy_bucket, infer_theme_family
from provider_adapters import aggregate_source_health, build_source_health_item


def summarize_news(items: list[NewsItem], limit: int = 5) -> list[NewsItem]:
    ranked = sorted(items, key=lambda item: item.get("published_at", ""), reverse=True)
    return [
        {
            "published_at": item.get("published_at", ""),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "impact": item.get("impact", "neutral"),
            "source_name": item.get("source_name", ""),
            "url": item.get("url", ""),
        }
        for item in ranked[:limit]
    ]


def stable_evidence_id(prefix: str, entity_id: str, as_of: str, source_url: str = "") -> str:
    digest_source = f"{prefix}|{entity_id}|{as_of}|{source_url}".encode("utf-8")
    digest = hashlib.sha1(digest_source).hexdigest()[:12]
    return f"{prefix}:{entity_id}:{digest}"


def build_numeric_payload(item: dict) -> dict:
    payload = {}
    for key, value in item.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            payload[key] = value
    return payload


def infer_news_bucket(item: dict, fund: PortfolioFund | None = None) -> tuple[str, str, str]:
    source_name = str(item.get("source_name", "") or "").lower()
    title = str(item.get("title", "") or "")
    if item.get("evidence_type"):
        return (
            str(item.get("evidence_type")),
            str(item.get("source_role", "fund_news")),
            str(item.get("source_tier", "self_media")),
        )
    if "notice" in source_name or "公告" in title:
        return ("official_notice", "fund_news", "official_notice")
    if any(keyword in title for keyword in ("证监会", "发改委", "工信部", "财政部", "政策", "监管")):
        return ("policy_news", "market_news", "official_policy")
    if any(keyword in title for keyword in ("美股", "港股", "A股", "纳指", "标普", "人民币", "汇率", "利率")):
        return ("market_news", "market_news", "market_media")
    if any(keyword in title for keyword in ("直播", "视频", "#", "揭秘", "调研团", "博主", "短视频")):
        if any(keyword in title for keyword in ("视频", "直播", "#")):
            return ("short_video_signal", "sentiment_news", "social_short_video")
        return ("social_post", "sentiment_news", "social_post")
    if fund and str(fund.get("style_group", "")):
        return ("theme_news", "theme_news", "self_media")
    return ("theme_news", "fund_news", "self_media")


def infer_mapping_mode(item: dict, fund: PortfolioFund) -> str:
    if item.get("mapping_mode"):
        return str(item.get("mapping_mode"))
    evidence_type = str(item.get("evidence_type", "") or "")
    if evidence_type in {"market_news", "policy_news"}:
        return "market_background"
    if evidence_type in {"social_post", "short_video_signal"}:
        return "sentiment_background"
    if evidence_type == "theme_news":
        return "theme_match"
    return "direct_fund"


def news_scores(item: dict) -> tuple[float, float, float, float, str]:
    title = str(item.get("title", "") or "")
    impact = str(item.get("impact", "neutral") or "neutral")
    sentiment_score = float(item.get("sentiment_score", 0.0) or 0.0)
    if sentiment_score == 0.0:
        if impact == "positive":
            sentiment_score = 0.35
        elif impact == "negative":
            sentiment_score = -0.35
    novelty = float(item.get("novelty_score", 0.6) or 0.6)
    virality = float(item.get("virality_score", 0.0) or 0.0)
    if any(keyword in title for keyword in ("直播", "视频", "#")):
        virality = max(virality, 0.65)
    historical = float(item.get("historical_significance", 0.0) or 0.0)
    if any(keyword in title for keyword in ("政策", "监管", "制度", "供给侧", "汇率", "加息", "降息")):
        historical = max(historical, 0.7)
    crowding_signal = str(item.get("crowding_signal", "") or "")
    if not crowding_signal:
        if virality >= 0.7 and abs(sentiment_score) >= 0.3:
            crowding_signal = "crowded"
        elif virality >= 0.45:
            crowding_signal = "warming"
        else:
            crowding_signal = "neutral"
    return sentiment_score, novelty, virality, historical, crowding_signal


def build_constraints(portfolio: dict, strategy: dict) -> dict:
    exposure = analyze_portfolio_exposure(portfolio, strategy)
    allocation_plan = exposure.get("allocation_plan", {})
    fixed_dca_total = sum(float(fund.get("fixed_daily_buy_amount", 0.0)) for fund in portfolio["funds"] if fund["role"] == "core_dca")
    tactical_budget = max(0.0, float(strategy["portfolio"]["daily_max_trade_amount"]) - fixed_dca_total)
    return {
        "daily_max_trade_amount": float(strategy["portfolio"]["daily_max_trade_amount"]),
        "fixed_dca_total": fixed_dca_total,
        "tactical_budget_after_dca": tactical_budget,
        "cash_hub_floor": float(strategy["portfolio"]["cash_hub_floor"]),
        "single_tactical_cap_value": float(strategy["tactical"]["default_cap_value"]),
        "dca_rule": "标普500和纳指100仅允许固定定投，不允许额外加仓。",
        "fixed_hold_rule": "华泰保兴尊睿6个月持有期债券A保持不动。",
        "cash_hub_rule": "兴业中证同业存单AAA指数7天持有期是资金存储仓，需要保留底仓。",
        "execution_rule": "允许清仓，允许换基，最低持仓为0。",
        "allocation_targets_pct": allocation_plan.get("targets_pct", {}),
        "allocation_current_pct": allocation_plan.get("current_pct", {}),
        "allocation_drift_pct": allocation_plan.get("drift_pct", {}),
        "rebalance_band_pct": allocation_plan.get("rebalance_band_pct", 5.0),
        "rebalance_needed": bool(allocation_plan.get("rebalance_needed", False)),
        "rebalance_suggestions": allocation_plan.get("rebalance_suggestions", []),
    }


def build_fund_snapshot(
    fund: PortfolioFund,
    quote: QuoteSnapshot,
    proxy: ProxySnapshot,
    estimate: EstimateSnapshot,
    profile: FundProfile,
    news_items: list[NewsItem],
    evidence_refs: list[EvidenceRef],
) -> FundContextItem:
    return {
        "fund_code": fund["fund_code"],
        "fund_name": fund["fund_name"],
        "role": fund["role"],
        "style_group": fund.get("style_group", "unknown"),
        "current_value": float(fund["current_value"]),
        "holding_pnl": float(fund.get("holding_pnl", 0.0)),
        "holding_return_pct": float(fund.get("holding_return_pct", 0.0)),
        "cap_value": float(fund.get("cap_value", 0.0)),
        "strategy_bucket": infer_strategy_bucket(fund),
        "allow_trade": bool(fund.get("allow_trade", False)),
        "locked_amount": float(fund.get("locked_amount", 0.0)),
        "fixed_daily_buy_amount": float(fund.get("fixed_daily_buy_amount", 0.0)),
        "quote": quote,
        "intraday_proxy": proxy,
        "estimated_nav": estimate,
        "fund_profile": profile,
        "recent_news": summarize_news(news_items),
        "evidence_refs": evidence_refs,
    }


def quote_evidence(fund: PortfolioFund, quote: QuoteSnapshot) -> EvidenceItem:
    as_of = str(quote.get("as_of_date", "") or "")
    return {
        "evidence_id": stable_evidence_id("quote_snapshot", fund["fund_code"], as_of, str(quote.get("source_url", ""))),
        "entity_id": fund["fund_code"],
        "entity_type": "fund",
        "evidence_type": "quote_snapshot",
        "source_role": "market_news",
        "source_tier": "official_market_data",
        "mapping_mode": "direct_fund",
        "provider": quote.get("provider", "quotes"),
        "source_url": quote.get("source_url", ""),
        "source_title": quote.get("source_title", fund.get("fund_name", "")),
        "as_of": as_of,
        "retrieved_at": quote.get("retrieved_at", ""),
        "freshness_status": quote.get("freshness_status", "fresh"),
        "stale": bool(quote.get("freshness_is_delayed", False)),
        "summary": f"{fund.get('fund_name', fund['fund_code'])} quote snapshot",
        "confidence": float(quote.get("confidence", 0.98) or 0.98),
        "numeric_payload": build_numeric_payload(quote),
        "raw_payload": dict(quote),
        "tags": [fund.get("style_group", ""), infer_strategy_bucket(fund)],
    }


def proxy_evidence(fund: PortfolioFund, proxy: ProxySnapshot) -> EvidenceItem:
    as_of = str(proxy.get("trade_date", "") or "")
    return {
        "evidence_id": stable_evidence_id("intraday_proxy", fund["fund_code"], as_of, str(proxy.get("source_url", ""))),
        "entity_id": fund["fund_code"],
        "entity_type": "fund",
        "evidence_type": "intraday_proxy",
        "source_role": "market_news",
        "source_tier": "derived_market_data",
        "mapping_mode": "direct_fund",
        "provider": proxy.get("provider", "intraday_proxy"),
        "source_url": proxy.get("source_url", ""),
        "source_title": proxy.get("source_title", proxy.get("proxy_name", "")),
        "as_of": as_of,
        "retrieved_at": proxy.get("retrieved_at", ""),
        "freshness_status": proxy.get("freshness_status", "fresh"),
        "stale": bool(proxy.get("stale", False)),
        "summary": f"{fund.get('fund_name', fund['fund_code'])} intraday proxy",
        "confidence": float(proxy.get("confidence", 0.72) or 0.72),
        "numeric_payload": build_numeric_payload(proxy),
        "raw_payload": dict(proxy),
        "tags": [fund.get("style_group", ""), infer_strategy_bucket(fund), "intraday"],
    }


def estimate_evidence(fund: PortfolioFund, estimate: EstimateSnapshot) -> EvidenceItem:
    as_of = str(estimate.get("estimate_date", "") or estimate.get("official_nav_date", "") or "")
    return {
        "evidence_id": stable_evidence_id("estimated_nav", fund["fund_code"], as_of, str(estimate.get("source_url", ""))),
        "entity_id": fund["fund_code"],
        "entity_type": "fund",
        "evidence_type": "estimated_nav",
        "source_role": "market_news",
        "source_tier": "derived_market_data",
        "mapping_mode": "direct_fund",
        "provider": estimate.get("provider", "estimated_nav"),
        "source_url": estimate.get("source_url", ""),
        "source_title": estimate.get("source_title", fund.get("fund_name", "")),
        "as_of": as_of,
        "retrieved_at": estimate.get("retrieved_at", ""),
        "freshness_status": estimate.get("estimate_freshness_status", "fresh"),
        "stale": bool(estimate.get("stale", False)),
        "summary": f"{fund.get('fund_name', fund['fund_code'])} realtime estimate",
        "confidence": float(estimate.get("confidence", 0.7) or 0.7),
        "numeric_payload": build_numeric_payload(estimate),
        "raw_payload": dict(estimate),
        "tags": [fund.get("style_group", ""), infer_strategy_bucket(fund), "estimate"],
    }


def profile_evidence(fund: PortfolioFund, profile: FundProfile) -> EvidenceItem:
    as_of = str(profile.get("as_of", "") or "")
    return {
        "evidence_id": stable_evidence_id("fund_profile", fund["fund_code"], as_of, str(profile.get("source_url", ""))),
        "entity_id": fund["fund_code"],
        "entity_type": "fund",
        "evidence_type": "fund_profile",
        "source_role": "fund_news",
        "source_tier": "official_fund",
        "mapping_mode": "direct_fund",
        "provider": profile.get("provider", profile.get("profile_source", "fund_profile")),
        "source_url": profile.get("source_url", ""),
        "source_title": profile.get("source_title", profile.get("fund_name", "")),
        "as_of": as_of,
        "retrieved_at": profile.get("retrieved_at", ""),
        "freshness_status": "fresh",
        "stale": False,
        "summary": f"{fund.get('fund_name', fund['fund_code'])} profile snapshot",
        "confidence": 0.9,
        "numeric_payload": build_numeric_payload(profile),
        "raw_payload": dict(profile),
        "tags": [fund.get("style_group", ""), infer_strategy_bucket(fund), "slow_factor"],
    }


def news_evidence(item: dict, fund: PortfolioFund) -> EvidenceItem:
    evidence_type, source_role, source_tier = infer_news_bucket(item, fund)
    mapping_mode = infer_mapping_mode({**item, "evidence_type": evidence_type}, fund)
    sentiment_score, novelty, virality, historical, crowding_signal = news_scores(item)
    as_of = str(item.get("as_of", "") or item.get("published_at", "") or "")
    source_url = str(item.get("source_url", "") or item.get("url", "") or "")
    return {
        "evidence_id": stable_evidence_id(evidence_type, fund["fund_code"], as_of, source_url),
        "entity_id": fund["fund_code"],
        "entity_type": "fund",
        "evidence_type": evidence_type,
        "source_role": source_role,
        "source_tier": source_tier,
        "mapping_mode": mapping_mode,
        "provider": item.get("provider", item.get("source_name", "news")),
        "source_url": source_url,
        "source_title": item.get("source_title", item.get("title", "")),
        "as_of": as_of,
        "published_at": item.get("published_at", ""),
        "retrieved_at": item.get("retrieved_at", ""),
        "freshness_status": item.get("freshness_status", "fresh"),
        "stale": bool(item.get("stale", False)),
        "summary": item.get("summary", item.get("title", "")),
        "confidence": float(item.get("confidence", item.get("relevance_score", 0.65)) or 0.65),
        "sentiment_score": sentiment_score,
        "novelty_score": novelty,
        "virality_score": virality,
        "historical_significance": historical,
        "crowding_signal": crowding_signal,
        "tags": [fund.get("style_group", ""), infer_strategy_bucket(fund), infer_theme_family(fund), evidence_type],
        "numeric_payload": {
            "relevance_score": float(item.get("relevance_score", 0.0) or 0.0),
            "sentiment_score": sentiment_score,
            "novelty_score": novelty,
            "virality_score": virality,
            "historical_significance": historical,
        },
        "raw_payload": dict(item),
    }


def sentiment_snapshot_evidence(fund: PortfolioFund, quote: QuoteSnapshot, proxy: ProxySnapshot, estimate: EstimateSnapshot, news_items: list[NewsItem]) -> EvidenceItem:
    news_count = len(news_items)
    positive = sum(1 for item in news_items if str(item.get("impact", "")).lower() == "positive")
    negative = sum(1 for item in news_items if str(item.get("impact", "")).lower() == "negative")
    virality = max((float(item.get("virality_score", 0.0) or 0.0) for item in news_items), default=0.0)
    proxy_change = float(proxy.get("change_pct", 0.0) or 0.0)
    estimate_change = float(estimate.get("estimate_change_pct", 0.0) or 0.0)
    quote_change = float(quote.get("day_change_pct", 0.0) or 0.0)
    sentiment = max(-1.0, min(1.0, (positive - negative) * 0.2 + proxy_change * 0.08 + estimate_change * 0.05))
    crowding_signal = "crowded" if virality >= 0.7 and sentiment > 0.2 else ("capitulation" if virality >= 0.7 and sentiment < -0.2 else "neutral")
    as_of = str(proxy.get("trade_date", "") or estimate.get("estimate_date", "") or quote.get("as_of_date", ""))
    return {
        "evidence_id": stable_evidence_id("crowd_sentiment_snapshot", fund["fund_code"], as_of),
        "entity_id": fund["fund_code"],
        "entity_type": "fund",
        "evidence_type": "crowd_sentiment_snapshot",
        "source_role": "sentiment_news",
        "source_tier": "derived_sentiment",
        "mapping_mode": "direct_fund",
        "provider": "derived_sentiment",
        "source_url": "",
        "source_title": f"{fund.get('fund_name', fund['fund_code'])} sentiment snapshot",
        "as_of": as_of,
        "retrieved_at": timestamp_now(),
        "freshness_status": "fresh" if not proxy.get("stale") and not estimate.get("stale") else "mixed",
        "stale": bool(proxy.get("stale", False) and estimate.get("stale", False)),
        "summary": f"Derived crowd sentiment from proxy={proxy_change:.2f}, estimate={estimate_change:.2f}, quote={quote_change:.2f}, news_count={news_count}",
        "confidence": 0.58 if news_count else 0.42,
        "sentiment_score": sentiment,
        "novelty_score": min(1.0, news_count / 4.0),
        "virality_score": virality,
        "historical_significance": 0.0,
        "crowding_signal": crowding_signal,
        "tags": [fund.get("style_group", ""), infer_theme_family(fund), "sentiment"],
        "numeric_payload": {
            "news_count": news_count,
            "positive_count": positive,
            "negative_count": negative,
            "proxy_change_pct": proxy_change,
            "estimate_change_pct": estimate_change,
            "quote_day_change_pct": quote_change,
            "sentiment_score": sentiment,
        },
        "raw_payload": {},
    }


def evidence_ref(fund_code: str, evidence: EvidenceItem, *, role: str, relevance_score: float = 1.0) -> EvidenceRef:
    return {
        "evidence_id": evidence["evidence_id"],
        "fund_code": fund_code,
        "role": role,
        "relevance_score": relevance_score,
        "mapping_mode": evidence.get("mapping_mode", "direct_fund"),
        "source_tier": evidence.get("source_tier", ""),
        "evidence_type": evidence.get("evidence_type", ""),
    }


def tokenize_memory_text(*values: object) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        text = str(value or "").strip().lower().replace("-", "_")
        if not text:
            continue
        tokens.update(part for part in re.findall(r"[a-z0-9_]+", text) if len(part) >= 2)
    return tokens


def build_memory_context_tags(portfolio: dict, exposure_summary: dict) -> set[str]:
    tags: set[str] = set()
    for fund in portfolio.get("funds", []) or []:
        tags.update(
            tokenize_memory_text(
                fund.get("fund_code", ""),
                fund.get("role", ""),
                fund.get("style_group", ""),
                fund.get("category", ""),
                infer_strategy_bucket(fund),
                infer_theme_family(fund),
            )
        )
    allocation_plan = exposure_summary.get("allocation_plan", {}) or {}
    for bucket, status in (allocation_plan.get("status_by_bucket", {}) or {}).items():
        tags.update(tokenize_memory_text(bucket, status, f"{bucket}_{status}"))
    return tags


def build_memory_id(prefix: str, base_date: str, text: str, scope: str) -> str:
    digest = hashlib.sha1(f"{prefix}|{base_date}|{scope}|{text}".encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{base_date}:{digest}"


def normalize_memory_records(memory: dict) -> list[MemoryRecord]:
    records = [dict(item) for item in memory.get("records", []) or []]
    strategic = [dict(item) for item in memory.get("strategic_memory", []) or []]
    permanent = [dict(item) for item in memory.get("permanent_memory", []) or []]
    core_permanent = [dict(item) for item in memory.get("core_permanent_memory", []) or []]
    confirmed = [dict(item) for item in memory.get("user_confirmed_memory", []) or []]

    for item in memory.get("lessons", []) or []:
        records.append(
            {
                "memory_id": item.get("memory_id") or build_memory_id("lesson", item.get("base_date", ""), item.get("text", ""), "review_memory"),
                "memory_type": item.get("type", "semantic"),
                "scope": "review_memory",
                "entity_keys": [str(item.get("applies_to", "")).strip()] if item.get("applies_to") else [],
                "text": item.get("text", ""),
                "provenance": {"source": item.get("source", "advice"), "kind": "lesson"},
                "base_date": item.get("base_date", ""),
                "expires_on": item.get("expires_on", ""),
                "promotion_level": "normal",
                "approved_by": "",
                "confidence": float(item.get("confidence", 0.0) or 0.0),
                "status": "active",
                "applies_to": item.get("applies_to", ""),
                "source": item.get("source", "advice"),
            }
        )
    for item in memory.get("bias_adjustments", []) or []:
        strategic.append(
            {
                "memory_id": item.get("memory_id") or build_memory_id("bias", item.get("base_date", ""), item.get("adjustment", ""), "strategic_memory"),
                "memory_type": "caveat",
                "scope": "strategic_memory",
                "entity_keys": [str(item.get("scope", "")).strip(), str(item.get("target", "")).strip()],
                "text": item.get("adjustment", ""),
                "provenance": {"source": item.get("source", "advice"), "kind": "bias_adjustment"},
                "base_date": item.get("base_date", ""),
                "expires_on": item.get("expires_on", ""),
                "promotion_level": "normal",
                "approved_by": "",
                "confidence": float(item.get("confidence", 0.0) or 0.7),
                "status": "active",
                "reason": item.get("reason", ""),
                "source": item.get("source", "advice"),
            }
        )
    for item in memory.get("agent_feedback", []) or []:
        records.append(
            {
                "memory_id": item.get("memory_id") or build_memory_id("agent_feedback", item.get("base_date", ""), item.get("reason", ""), "review_memory"),
                "memory_type": "procedural",
                "scope": "review_memory",
                "entity_keys": [str(item.get("agent_name", "")).strip()],
                "text": f"{item.get('agent_name', '')}: {item.get('bias', '')}",
                "provenance": {"source": item.get("source", "advice"), "kind": "agent_feedback"},
                "base_date": item.get("base_date", ""),
                "expires_on": item.get("expires_on", ""),
                "promotion_level": "normal",
                "approved_by": "",
                "confidence": float(item.get("confidence", 0.0) or 0.0),
                "status": "active",
                "reason": item.get("reason", ""),
                "source": item.get("source", "advice"),
            }
        )
    for item in memory.get("review_history", []) or []:
        records.append(
            {
                "memory_id": item.get("memory_id") or build_memory_id("review_history", item.get("base_date", ""), item.get("memory_summary", ""), "review_memory"),
                "memory_type": "episodic",
                "scope": "review_memory",
                "entity_keys": [str(item.get("source", "")).strip()],
                "text": item.get("memory_summary", ""),
                "provenance": {"source": item.get("source", "advice"), "kind": "review_history"},
                "base_date": item.get("base_date", ""),
                "expires_on": item.get("expires_on", ""),
                "promotion_level": "normal",
                "approved_by": "",
                "confidence": 0.5,
                "status": "active",
                "source": item.get("source", "advice"),
            }
        )

    for item in core_permanent:
        item.setdefault("scope", "core_permanent_memory")
        item.setdefault("promotion_level", "promoted")
        item.setdefault("memory_type", "policy")
    combined = records + strategic + permanent + core_permanent + confirmed
    deduped: dict[str, MemoryRecord] = {}
    for item in combined:
        memory_id = str(item.get("memory_id", "")).strip() or build_memory_id("memory", item.get("base_date", ""), item.get("text", ""), item.get("scope", "review_memory"))
        deduped[memory_id] = {**item, "memory_id": memory_id}
    return list(deduped.values())


def memory_score(item: MemoryRecord, context_tags: set[str], analysis_day) -> float:
    if str(item.get("status", "active") or "active") == "inactive":
        return -1.0
    expires_on = parse_date_text(item.get("expires_on"))
    if analysis_day is not None and expires_on is not None and expires_on < analysis_day:
        return -1.0
    keys = tokenize_memory_text(*(item.get("entity_keys", []) or []), item.get("applies_to", ""), item.get("text", ""), item.get("reason", ""))
    overlap = len(keys & context_tags)
    scope = str(item.get("scope", "") or "")
    promotion_level = str(item.get("promotion_level", "") or "")
    approved_by = str(item.get("approved_by", "") or "")
    memory_type = str(item.get("memory_type", "") or "")
    base_score = overlap * 12.0
    if scope == "core_permanent_memory":
        base_score += 26.0
    elif scope == "permanent_memory":
        base_score += 18.0
    elif scope == "strategic_memory":
        base_score += 10.0
    elif scope == "review_memory":
        base_score += 5.0
    if promotion_level == "promoted":
        base_score += 5.0
    if approved_by:
        base_score += 10.0
    if memory_type == "historical_event":
        base_score += 8.0
    base_date = parse_date_text(item.get("base_date"))
    if analysis_day is not None and base_date is not None and overlap == 0 and scope != "permanent_memory" and (analysis_day - base_date).days > 45:
        return -1.0
    if analysis_day is not None and base_date is not None and scope != "permanent_memory":
        age_days = max(0, (analysis_day - base_date).days)
        base_score += max(0.0, 45.0 - age_days) / 8.0
    return base_score + float(item.get("confidence", 0.0) or 0.0) * 5.0


def select_memory_records(records: list[MemoryRecord], context_tags: set[str], analysis_day, *, limit: int, scopes: set[str] | None = None, memory_types: set[str] | None = None) -> list[MemoryRecord]:
    ranked: list[tuple[float, MemoryRecord]] = []
    for item in records:
        if scopes and str(item.get("scope", "") or "") not in scopes:
            continue
        if memory_types and str(item.get("memory_type", "") or "") not in memory_types:
            continue
        score = memory_score(item, context_tags, analysis_day)
        if score < 0:
            continue
        ranked.append((score, item))
    ranked.sort(key=lambda row: (row[0], row[1].get("base_date", "")), reverse=True)
    return [item for _score, item in ranked[:limit]]


def build_memory_digest(memory: dict, portfolio: dict, exposure_summary: dict) -> dict:
    analysis_date = memory.get("_analysis_date", "")
    analysis_day = parse_date_text(analysis_date)
    context_tags = build_memory_context_tags(portfolio, exposure_summary)
    records = normalize_memory_records(memory)
    recent_review_memory = select_memory_records(records, context_tags, analysis_day, limit=10, scopes={"review_memory"})
    strategic_memory_hits = select_memory_records(records, context_tags, analysis_day, limit=8, scopes={"strategic_memory"})
    core_permanent_memory_hits = select_memory_records(records, context_tags, analysis_day, limit=6, scopes={"core_permanent_memory"})
    permanent_memory_hits = select_memory_records(records, context_tags, analysis_day, limit=8, scopes={"permanent_memory"})
    historical_event_hits = select_memory_records(records, context_tags, analysis_day, limit=6, memory_types={"historical_event"})
    expired_bias_count = sum(
        1
        for item in memory.get("bias_adjustments", [])
        if analysis_day is not None and parse_date_text(item.get("expires_on")) is not None and parse_date_text(item.get("expires_on")) < analysis_day
    )
    return {
        "updated_at": memory.get("updated_at", ""),
        "memory_ledger_summary": memory.get("memory_ledger_summary", {}),
        "retrieval_context_tags": sorted(context_tags)[:20],
        "recent_lessons": [item for item in recent_review_memory if item.get("provenance", {}).get("kind") == "lesson"][:8],
        "recent_review_history": [item for item in recent_review_memory if item.get("provenance", {}).get("kind") == "review_history"][:5],
        "recent_bias_adjustments": strategic_memory_hits[:8],
        "expired_bias_adjustment_count": expired_bias_count,
        "recent_agent_feedback": [item for item in recent_review_memory if item.get("provenance", {}).get("kind") == "agent_feedback"][:8],
        "strategic_memory_hits": strategic_memory_hits,
        "core_permanent_memory_hits": core_permanent_memory_hits,
        "permanent_memory_hits": permanent_memory_hits,
        "historical_event_hits": historical_event_hits,
        "active_memory_records": (core_permanent_memory_hits + permanent_memory_hits + strategic_memory_hits + recent_review_memory)[:16],
    }


def build_source_health_summary(
    quotes_payload: dict,
    news_payload: dict,
    proxies_payload: dict,
    estimate_payload: dict,
    profile_payload: dict,
    evidence_items: list[EvidenceItem],
) -> list[SourceHealthItem]:
    summary: list[SourceHealthItem] = []
    summary.append(
        build_source_health_item(
            source_key=f"quotes:{quotes_payload.get('provider', 'quotes')}",
            source_role="market_news",
            provider=str(quotes_payload.get("provider", "quotes")),
            items=quotes_payload.get("funds", []) or [],
            status="warning" if any(bool(item.get("freshness_is_delayed", False)) for item in quotes_payload.get("funds", []) or []) else "ok",
        )
    )
    summary.append(
        build_source_health_item(
            source_key=f"intraday_proxy:{proxies_payload.get('provider', 'intraday_proxy')}",
            source_role="market_news",
            provider=str(proxies_payload.get("provider", "intraday_proxy")),
            items=proxies_payload.get("proxies", []) or [],
            status="warning" if any(bool(item.get("stale", False)) for item in proxies_payload.get("proxies", []) or []) else "ok",
        )
    )
    summary.append(
        build_source_health_item(
            source_key=f"estimated_nav:{estimate_payload.get('provider', 'estimated_nav')}",
            source_role="market_news",
            provider=str(estimate_payload.get("provider", "estimated_nav")),
            items=estimate_payload.get("items", []) or [],
            status="warning" if any(bool(item.get("stale", False)) for item in estimate_payload.get("items", []) or []) else "ok",
        )
    )
    summary.append(
        build_source_health_item(
            source_key=f"fund_profile:{profile_payload.get('provider', 'fund_profile')}",
            source_role="fund_news",
            provider=str(profile_payload.get("provider", "fund_profile")),
            items=profile_payload.get("items", []) or [],
            status="ok",
        )
    )
    summary.extend(aggregate_source_health(evidence_items))
    deduped: dict[str, SourceHealthItem] = {}
    for item in summary:
        deduped[str(item.get("source_key", ""))] = item
    return list(deduped.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the structured LLM context for portfolio advice.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--mode", default="intraday", choices=["intraday", "nightly"])
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    portfolio = load_portfolio(agent_home)
    strategy = load_strategy(agent_home)
    overrides = load_market_overrides(agent_home)
    memory = load_review_memory(agent_home)
    memory["_analysis_date"] = report_date
    quotes_payload = load_json(quote_path(agent_home, report_date))
    news_payload = load_json(news_path(agent_home, report_date))
    proxies_payload = load_json(intraday_proxy_path(agent_home, report_date))
    estimate_payload = load_json(estimated_nav_path(agent_home, report_date)) if estimated_nav_path(agent_home, report_date).exists() else {"items": []}
    profile_payload = load_json(fund_profile_path(agent_home, report_date)) if fund_profile_path(agent_home, report_date).exists() else {"items": []}

    quotes_by_code = {item["code"]: item for item in quotes_payload.get("funds", [])}
    proxies_by_code = {
        item.get("proxy_fund_code") or item.get("fund_code"): item
        for item in proxies_payload.get("proxies", [])
        if item.get("proxy_fund_code") or item.get("fund_code")
    }
    estimates_by_code = {item["fund_code"]: item for item in estimate_payload.get("items", [])}
    profiles_by_code = {item["fund_code"]: item for item in profile_payload.get("items", [])}
    news_by_code: dict[str, list[dict]] = defaultdict(list)
    for item in news_payload.get("items", []):
        news_by_code[item["code"]].append(item)

    role_counts = Counter(fund["role"] for fund in portfolio["funds"])
    all_proxies_stale = all(bool(item.get("stale", False)) for item in proxies_payload.get("proxies", [])) if proxies_payload.get("proxies") else True
    all_estimates_stale = all(bool(item.get("stale", False)) for item in estimate_payload.get("items", [])) if estimate_payload.get("items") else True
    delayed_official_nav_count = sum(1 for item in quotes_payload.get("funds", []) if bool(item.get("freshness_is_delayed", False)))
    stale_proxy_count = sum(1 for item in proxies_payload.get("proxies", []) if bool(item.get("stale", False)))
    stale_estimate_count = sum(1 for item in estimate_payload.get("items", []) if bool(item.get("stale", False)))
    exposure_summary = analyze_portfolio_exposure(portfolio, strategy)
    evidence_items: list[EvidenceItem] = []
    fund_evidence_map: dict[str, list[EvidenceRef]] = defaultdict(list)
    fund_rows: list[FundContextItem] = []

    for fund in portfolio["funds"]:
        fund_code = fund["fund_code"]
        quote = quotes_by_code.get(fund_code, {})
        proxy = proxies_by_code.get(fund_code, {})
        estimate = estimates_by_code.get(fund_code, {})
        profile = profiles_by_code.get(fund_code, {})
        fund_news = news_by_code.get(fund_code, [])
        refs: list[EvidenceRef] = []

        if quote:
            evidence = quote_evidence(fund, quote)
            evidence_items.append(evidence)
            refs.append(evidence_ref(fund_code, evidence, role=fund.get("role", "unknown"), relevance_score=0.95))
        if proxy:
            evidence = proxy_evidence(fund, proxy)
            evidence_items.append(evidence)
            refs.append(evidence_ref(fund_code, evidence, role=fund.get("role", "unknown"), relevance_score=0.82))
        if estimate:
            evidence = estimate_evidence(fund, estimate)
            evidence_items.append(evidence)
            refs.append(evidence_ref(fund_code, evidence, role=fund.get("role", "unknown"), relevance_score=0.8))
        if profile:
            evidence = profile_evidence(fund, profile)
            evidence_items.append(evidence)
            refs.append(evidence_ref(fund_code, evidence, role=fund.get("role", "unknown"), relevance_score=0.75))

        normalized_news: list[NewsItem] = []
        for item in fund_news:
            evidence = news_evidence(item, fund)
            evidence_items.append(evidence)
            refs.append(
                evidence_ref(
                    fund_code,
                    evidence,
                    role=fund.get("role", "unknown"),
                    relevance_score=float(item.get("relevance_score", 0.65) or 0.65),
                )
            )
            normalized_news.append(
                {
                    **item,
                    "source_role": evidence.get("source_role", ""),
                    "source_tier": evidence.get("source_tier", ""),
                    "mapping_mode": evidence.get("mapping_mode", ""),
                    "sentiment_score": evidence.get("sentiment_score", 0.0),
                    "novelty_score": evidence.get("novelty_score", 0.0),
                    "virality_score": evidence.get("virality_score", 0.0),
                    "historical_significance": evidence.get("historical_significance", 0.0),
                    "crowding_signal": evidence.get("crowding_signal", "neutral"),
                    "confidence": evidence.get("confidence", 0.65),
                }
            )

        sentiment_evidence = sentiment_snapshot_evidence(fund, quote, proxy, estimate, normalized_news)
        evidence_items.append(sentiment_evidence)
        refs.append(evidence_ref(fund_code, sentiment_evidence, role=fund.get("role", "unknown"), relevance_score=0.55))

        fund_evidence_map[fund_code] = refs
        fund_rows.append(build_fund_snapshot(fund, quote, proxy, estimate, profile, normalized_news, refs))

    source_health_summary = build_source_health_summary(quotes_payload, news_payload, proxies_payload, estimate_payload, profile_payload, evidence_items)

    context: LlmContext = {
        "analysis_date": report_date,
        "mode": args.mode,
        "generated_at": timestamp_now(),
        "portfolio_summary": {
            "portfolio_name": portfolio["portfolio_name"],
            "total_value": float(portfolio.get("total_value", 0.0)),
            "holding_pnl": float(portfolio.get("holding_pnl", 0.0)),
            "risk_profile": strategy["portfolio"]["risk_profile"],
            "role_counts": dict(role_counts),
            "all_intraday_proxies_stale": all_proxies_stale,
            "all_estimates_stale": all_estimates_stale,
            "stale_proxy_count": stale_proxy_count,
            "stale_estimate_count": stale_estimate_count,
            "delayed_official_nav_count": delayed_official_nav_count,
        },
        "exposure_summary": exposure_summary,
        "constraints": build_constraints(portfolio, strategy),
        "external_reference": {
            "manual_theme_reference_enabled": bool(strategy["manual_references"]["use_yangjibao_board_heat"]),
            "manual_biases": overrides.get("biases", []),
        },
        "memory_digest": build_memory_digest(memory, portfolio, exposure_summary),
        "evidence_items": evidence_items,
        "fund_evidence_map": dict(fund_evidence_map),
        "source_health_summary": source_health_summary,
        "funds": fund_rows,
    }

    output_path = dump_json(llm_context_path(agent_home, report_date), context)
    dump_json(source_health_path(agent_home, report_date), {"report_date": report_date, "generated_at": timestamp_now(), "items": source_health_summary})
    print(output_path)


if __name__ == "__main__":
    main()
