from __future__ import annotations

from datetime import date
from typing import Any

from rag_models import RagQueryPlan


SOURCE_TIER_SCORES = {
    "structured_current": 1.0,
    "structured_snapshot": 0.92,
    "decision_trace": 0.95,
    "official_market_data": 0.9,
    "memory_approved": 0.86,
    "daily_context": 0.76,
    "news_digest": 0.7,
    "daily_evidence": 0.68,
    "memory_strategic": 0.62,
    "memory_candidate": 0.42,
    "negative_memory": 0.1,
}


def _date_fit(as_of_date: str, query_date: str) -> float:
    try:
        older = date.fromisoformat(str(as_of_date)[:10])
        newer = date.fromisoformat(str(query_date)[:10])
    except ValueError:
        return 0.2
    delta = max(0, (newer - older).days)
    if delta == 0:
        return 1.0
    if delta <= 3:
        return 0.85
    if delta <= 14:
        return 0.65
    if delta <= 60:
        return 0.42
    return 0.22


def _entity_match(hit: dict[str, Any], plan: RagQueryPlan) -> float:
    if not plan.fund_codes:
        return 0.6
    target = set(plan.fund_codes)
    fund_codes = set(hit.get("fund_codes", []) or [])
    entity_id = str(hit.get("entity_id", "") or "")
    if target.intersection(fund_codes) or entity_id in target:
        return 1.0
    return 0.0


def _freshness(hit: dict[str, Any]) -> float:
    metadata = hit.get("metadata", {}) or {}
    status = str(metadata.get("freshness_status", "") or "")
    if metadata.get("stale"):
        return 0.15
    if status in {"same_day", "fresh"}:
        return 1.0
    if status in {"previous_trading_day", "acceptable"}:
        return 0.75
    if status:
        return 0.45
    return 0.55


def _confidence(hit: dict[str, Any]) -> float:
    metadata = hit.get("metadata", {}) or {}
    value = metadata.get("confidence")
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def rerank_hits(hits: list[dict[str, Any]], plan: RagQueryPlan, *, semantic_weight: float = 0.0) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for hit in hits:
        source_tier = str(hit.get("source_tier", "") or "")
        base_score = float(hit.get("text_score", 0.0) or 0.0)
        source_score = SOURCE_TIER_SCORES.get(source_tier, 0.45)
        date_score = _date_fit(str(hit.get("as_of_date", "") or ""), plan.query_date)
        entity_score = _entity_match(hit, plan)
        freshness_score = _freshness(hit)
        confidence_score = _confidence(hit)
        source_key = f"{hit.get('source_kind')}:{hit.get('source_record_id')}"
        diversity_score = 0.2 if source_key in seen_sources else 1.0
        seen_sources.add(source_key)
        penalty = 0.25 if hit.get("visibility") == "review_only" and not plan.include_negative_memory else 0.0
        normalized_semantic_weight = max(0.0, min(0.35, float(semantic_weight or 0.0))) if hit.get("semantic_score") is not None else 0.0
        lexical_weight = 0.45 - normalized_semantic_weight
        final = (
            base_score * lexical_weight
            + source_score * 0.18
            + date_score * 0.14
            + entity_score * 0.12
            + freshness_score * 0.05
            + confidence_score * 0.04
            + diversity_score * 0.02
            - penalty
        )
        if normalized_semantic_weight:
            final += float(hit.get("semantic_score", 0.0) or 0.0) * normalized_semantic_weight
        updated = dict(hit)
        updated["score"] = round(final, 6)
        updated["score_breakdown"] = {
            "text": round(base_score, 4),
            "semantic": round(float(hit.get("semantic_score", 0.0) or 0.0), 4),
            "source_tier": round(source_score, 4),
            "date_fit": round(date_score, 4),
            "entity_match": round(entity_score, 4),
            "freshness": round(freshness_score, 4),
            "confidence": round(confidence_score, 4),
            "diversity": round(diversity_score, 4),
            "penalty": round(penalty, 4),
        }
        scored.append(updated)
    scored.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return scored
