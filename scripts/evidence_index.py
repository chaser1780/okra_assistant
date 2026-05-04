from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any


ROLE_PREFERENCES: dict[str, dict[str, list[str]]] = {
    "market_analyst": {
        "source_roles": ["market_news", "theme_news"],
        "evidence_types": ["quote_snapshot", "intraday_proxy", "estimated_nav", "market_news", "policy_news"],
        "keywords": ["market", "regime", "risk", "proxy", "estimate", "policy", "macro"],
    },
    "theme_analyst": {
        "source_roles": ["theme_news", "fund_news"],
        "evidence_types": ["theme_news", "market_news", "intraday_proxy", "estimated_nav"],
        "keywords": ["theme", "rotation", "style", "industry", "crowding"],
    },
    "fund_structure_analyst": {
        "source_roles": ["fund_news", "market_news"],
        "evidence_types": ["fund_profile", "quote_snapshot", "estimated_nav", "intraday_proxy"],
        "keywords": ["allocation", "cap", "structure", "overlap", "bucket", "locked"],
    },
    "fund_quality_analyst": {
        "source_roles": ["fund_news", "theme_news"],
        "evidence_types": ["fund_profile", "quote_snapshot", "theme_news"],
        "keywords": ["quality", "manager", "tenure", "fee", "scale", "profile"],
    },
    "news_analyst": {
        "source_roles": ["fund_news", "market_news", "theme_news"],
        "evidence_types": ["official_notice", "policy_news", "theme_news", "market_news"],
        "keywords": ["event", "notice", "policy", "incremental", "news"],
    },
    "sentiment_analyst": {
        "source_roles": ["sentiment_news", "theme_news", "market_news"],
        "evidence_types": ["social_post", "short_video_signal", "theme_news", "market_news"],
        "keywords": ["sentiment", "virality", "crowding", "social", "heat"],
    },
    "bull_researcher": {
        "source_roles": ["fund_news", "theme_news", "market_news"],
        "evidence_types": ["quote_snapshot", "intraday_proxy", "estimated_nav", "theme_news", "fund_profile"],
        "keywords": ["upside", "trend", "support", "momentum", "continuation"],
    },
    "bear_researcher": {
        "source_roles": ["fund_news", "theme_news", "market_news", "sentiment_news"],
        "evidence_types": ["quote_snapshot", "intraday_proxy", "estimated_nav", "theme_news", "social_post", "short_video_signal"],
        "keywords": ["risk", "downside", "crowding", "weakness", "trim"],
    },
    "research_manager": {
        "source_roles": ["fund_news", "theme_news", "market_news", "sentiment_news"],
        "evidence_types": ["quote_snapshot", "intraday_proxy", "estimated_nav", "fund_profile", "theme_news", "market_news"],
        "keywords": ["committee", "allocation", "consensus", "portfolio", "candidate"],
    },
    "risk_manager": {
        "source_roles": ["market_news", "theme_news", "sentiment_news"],
        "evidence_types": ["intraday_proxy", "estimated_nav", "market_news", "policy_news", "social_post", "short_video_signal"],
        "keywords": ["risk", "stale", "crowding", "constraint", "drawdown"],
    },
    "portfolio_trader": {
        "source_roles": ["market_news", "theme_news", "fund_news"],
        "evidence_types": ["intraday_proxy", "estimated_nav", "quote_snapshot", "fund_profile", "theme_news"],
        "keywords": ["execution", "portfolio", "funding", "priority", "timing"],
    },
}


def _ascii_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _cjk_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        tokens.append(match)
        if len(match) <= 8:
            tokens.extend(match[index : index + 2] for index in range(len(match) - 1))
    return tokens


def tokenize_text(*values: object) -> list[str]:
    counter: Counter[str] = Counter()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        for token in _ascii_tokens(text):
            if len(token) >= 2:
                counter[token] += 1
        for token in _cjk_tokens(text):
            counter[token] += 1
    ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ordered[:48]]


def _entry_blob(item: dict[str, Any]) -> str:
    numeric = item.get("numeric_payload", {}) or {}
    numeric_bits = [f"{key}:{numeric[key]}" for key in sorted(numeric)[:8]]
    return " ".join(
        str(part or "")
        for part in [
            item.get("summary", ""),
            item.get("source_title", ""),
            item.get("source_role", ""),
            item.get("source_tier", ""),
            item.get("evidence_type", ""),
            item.get("mapping_mode", ""),
            item.get("entity_id", ""),
            " ".join(item.get("tags", []) or []),
            " ".join(numeric_bits),
        ]
        if str(part or "").strip()
    )


def compact_entry(entry: dict[str, Any], score: float | None = None) -> dict[str, Any]:
    payload = {
        "evidence_id": entry.get("evidence_id", ""),
        "entity_id": entry.get("entity_id", ""),
        "evidence_type": entry.get("evidence_type", ""),
        "source_role": entry.get("source_role", ""),
        "source_tier": entry.get("source_tier", ""),
        "mapping_mode": entry.get("mapping_mode", ""),
        "summary": entry.get("summary", ""),
        "source_title": entry.get("source_title", ""),
        "as_of": entry.get("as_of", ""),
        "published_at": entry.get("published_at", ""),
        "freshness_status": entry.get("freshness_status", ""),
        "stale": bool(entry.get("stale", False)),
        "confidence": float(entry.get("confidence", 0.0) or 0.0),
        "sentiment_score": float(entry.get("sentiment_score", 0.0) or 0.0),
        "novelty_score": float(entry.get("novelty_score", 0.0) or 0.0),
        "virality_score": float(entry.get("virality_score", 0.0) or 0.0),
        "historical_significance": float(entry.get("historical_significance", 0.0) or 0.0),
        "crowding_signal": entry.get("crowding_signal", ""),
        "fund_codes": list(entry.get("fund_codes", []) or []),
        "tags": list(entry.get("tags", []) or [])[:6],
    }
    if score is not None:
        payload["retrieval_score"] = round(float(score), 4)
    return payload


def build_evidence_index_payload(context: dict[str, Any]) -> dict[str, Any]:
    fund_map = context.get("fund_evidence_map", {}) or {}
    evidence_items = context.get("evidence_items", []) or []
    evidence_to_funds: dict[str, set[str]] = defaultdict(set)
    for fund_code, refs in fund_map.items():
        for ref in refs or []:
            evidence_id = str((ref or {}).get("evidence_id", "") or "").strip()
            if evidence_id:
                evidence_to_funds[evidence_id].add(str(fund_code))

    entries: list[dict[str, Any]] = []
    by_fund_code: dict[str, list[str]] = defaultdict(list)
    by_source_role: dict[str, list[str]] = defaultdict(list)
    by_evidence_type: dict[str, list[str]] = defaultdict(list)
    by_token: dict[str, list[str]] = defaultdict(list)

    for item in evidence_items:
        evidence_id = str(item.get("evidence_id", "") or "").strip()
        if not evidence_id:
            continue
        fund_codes = sorted(evidence_to_funds.get(evidence_id, set()))
        if not fund_codes and item.get("entity_type") == "fund" and item.get("entity_id"):
            fund_codes = [str(item.get("entity_id"))]
        tokens = tokenize_text(_entry_blob(item))
        entry = {
            "evidence_id": evidence_id,
            "entity_id": str(item.get("entity_id", "") or ""),
            "entity_type": str(item.get("entity_type", "") or ""),
            "evidence_type": str(item.get("evidence_type", "") or ""),
            "source_role": str(item.get("source_role", "") or ""),
            "source_tier": str(item.get("source_tier", "") or ""),
            "mapping_mode": str(item.get("mapping_mode", "") or ""),
            "summary": str(item.get("summary", "") or ""),
            "source_title": str(item.get("source_title", "") or ""),
            "source_url": str(item.get("source_url", "") or ""),
            "provider": str(item.get("provider", "") or ""),
            "as_of": str(item.get("as_of", "") or ""),
            "published_at": str(item.get("published_at", "") or ""),
            "retrieved_at": str(item.get("retrieved_at", "") or ""),
            "freshness_status": str(item.get("freshness_status", "") or ""),
            "stale": bool(item.get("stale", False)),
            "confidence": float(item.get("confidence", 0.0) or 0.0),
            "sentiment_score": float(item.get("sentiment_score", 0.0) or 0.0),
            "novelty_score": float(item.get("novelty_score", 0.0) or 0.0),
            "virality_score": float(item.get("virality_score", 0.0) or 0.0),
            "historical_significance": float(item.get("historical_significance", 0.0) or 0.0),
            "crowding_signal": str(item.get("crowding_signal", "") or ""),
            "tags": list(item.get("tags", []) or [])[:8],
            "fund_codes": fund_codes,
            "tokens": tokens,
        }
        entries.append(entry)
        for fund_code in fund_codes:
            by_fund_code[fund_code].append(evidence_id)
        if entry["source_role"]:
            by_source_role[entry["source_role"]].append(evidence_id)
        if entry["evidence_type"]:
            by_evidence_type[entry["evidence_type"]].append(evidence_id)
        for token in tokens[:24]:
            by_token[token].append(evidence_id)

    return {
        "analysis_date": context.get("analysis_date", ""),
        "generated_at": context.get("generated_at", ""),
        "entry_count": len(entries),
        "entries": entries,
        "by_fund_code": {key: value for key, value in sorted(by_fund_code.items())},
        "by_source_role": {key: value for key, value in sorted(by_source_role.items())},
        "by_evidence_type": {key: value for key, value in sorted(by_evidence_type.items())},
        "by_token": {key: value for key, value in sorted(by_token.items())},
    }


def _query_terms(agent_name: str, fund: dict[str, Any] | None = None) -> list[str]:
    preferences = ROLE_PREFERENCES.get(agent_name, {})
    terms = list(preferences.get("keywords", []))
    if fund:
        terms.extend(
            [
                fund.get("fund_code", ""),
                fund.get("fund_name", ""),
                fund.get("role", ""),
                fund.get("strategy_bucket", ""),
                fund.get("style_group", ""),
            ]
        )
        for item in fund.get("recent_news", [])[:3]:
            terms.append(item.get("title", ""))
            terms.append(item.get("summary", ""))
    return tokenize_text(*terms)


def _score_entry(
    entry: dict[str, Any],
    *,
    fund_code: str | None,
    query_tokens: list[str],
    source_roles: list[str],
    evidence_types: list[str],
) -> float:
    score = 0.0
    token_overlap = len(set(query_tokens).intersection(entry.get("tokens", [])))
    score += token_overlap * 2.8
    if fund_code and fund_code in (entry.get("fund_codes", []) or []):
        score += 8.0
    if fund_code and fund_code == entry.get("entity_id"):
        score += 2.0
    if entry.get("mapping_mode") == "direct_fund":
        score += 1.5
    if entry.get("source_role") in source_roles:
        score += 2.0
    if entry.get("evidence_type") in evidence_types:
        score += 2.5
    if not bool(entry.get("stale", False)):
        score += 1.2
    else:
        score -= 3.5
    score += float(entry.get("confidence", 0.0) or 0.0) * 2.0
    score += float(entry.get("novelty_score", 0.0) or 0.0)
    score += float(entry.get("historical_significance", 0.0) or 0.0) * 0.7
    if entry.get("crowding_signal") == "crowded":
        score += 0.5
    return score


def retrieve_agent_evidence(
    agent_name: str,
    context: dict[str, Any],
    *,
    index_payload: dict[str, Any] | None = None,
    relevant_funds: list[dict[str, Any]] | None = None,
    portfolio_limit: int = 8,
    fund_limit: int = 4,
) -> dict[str, Any]:
    index = index_payload or build_evidence_index_payload(context)
    entries = index.get("entries", []) or []
    preferences = ROLE_PREFERENCES.get(agent_name, {})
    source_roles = preferences.get("source_roles", [])
    evidence_types = preferences.get("evidence_types", [])
    funds = relevant_funds if relevant_funds is not None else list(context.get("funds", []) or [])

    portfolio_query = _query_terms(agent_name)
    portfolio_hits = []
    for entry in entries:
        score = _score_entry(
            entry,
            fund_code=None,
            query_tokens=portfolio_query,
            source_roles=source_roles,
            evidence_types=evidence_types,
        )
        if score > 0:
            portfolio_hits.append((score, compact_entry(entry, score)))
    portfolio_hits.sort(key=lambda item: (-item[0], item[1]["stale"], -item[1]["confidence"], item[1]["evidence_id"]))

    fund_hits: dict[str, list[dict[str, Any]]] = {}
    for fund in funds:
        fund_code = str(fund.get("fund_code", "") or "").strip()
        if not fund_code:
            continue
        query_tokens = _query_terms(agent_name, fund)
        ranked = []
        for entry in entries:
            score = _score_entry(
                entry,
                fund_code=fund_code,
                query_tokens=query_tokens,
                source_roles=source_roles,
                evidence_types=evidence_types,
            )
            if score > 0:
                ranked.append((score, compact_entry(entry, score)))
        ranked.sort(key=lambda item: (-item[0], item[1]["stale"], -item[1]["confidence"], item[1]["evidence_id"]))
        fund_hits[fund_code] = [payload for _, payload in ranked[:fund_limit]]

    return {
        "portfolio": [payload for _, payload in portfolio_hits[:portfolio_limit]],
        "funds": fund_hits,
        "retrieval_meta": {
            "agent_name": agent_name,
            "entry_count": len(entries),
            "portfolio_hit_count": min(len(portfolio_hits), portfolio_limit),
            "fund_hit_counts": {code: len(items) for code, items in sorted(fund_hits.items())},
        },
    }
