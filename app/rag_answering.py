from __future__ import annotations

import json
from typing import Any


PACK_KIND = "copilot_rag_pack"


def _trim_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}..."


def _compact_json(value: Any, max_chars: int) -> Any:
    if value in (None, "", [], {}):
        return {} if isinstance(value, dict) else value
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        text = json.dumps(str(value), ensure_ascii=False)
    if len(text) <= max_chars:
        return value
    return {"truncated": True, "preview": text[:max_chars], "originalChars": len(text)}


def _is_stale(hit: dict[str, Any]) -> bool:
    metadata = hit.get("metadata", {}) if isinstance(hit.get("metadata"), dict) else {}
    freshness = str(metadata.get("freshness_status", "") or "").lower()
    return bool(metadata.get("stale")) or freshness in {"stale", "expired", "delayed", "cross_day"}


def build_citations(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for index, hit in enumerate(hits, start=1):
        metadata = hit.get("metadata", {}) if isinstance(hit.get("metadata"), dict) else {}
        citations.append(
            {
                "id": f"C{index}",
                "docId": str(hit.get("doc_id", "") or ""),
                "chunkId": str(hit.get("chunk_id", "") or ""),
                "sourceKind": str(hit.get("source_kind", "") or ""),
                "sourceRecordId": str(hit.get("source_record_id", "") or ""),
                "sourcePath": str(hit.get("source_path", "") or ""),
                "sourceTier": str(hit.get("source_tier", "") or ""),
                "title": str(hit.get("title", "") or ""),
                "summary": _trim_text(hit.get("summary", ""), 360),
                "asOfDate": str(hit.get("as_of_date", "") or ""),
                "availableFrom": str(hit.get("available_from", "") or ""),
                "publishedAt": str(hit.get("published_at", "") or metadata.get("published_at", "") or ""),
                "domain": str(hit.get("domain", "") or ""),
                "entityId": str(hit.get("entity_id", "") or ""),
                "fundCodes": list(hit.get("fund_codes", []) or []),
                "score": hit.get("score", 0.0),
                "stale": _is_stale(hit),
                "freshnessStatus": str(metadata.get("freshness_status", "") or ""),
                "visibility": str(hit.get("visibility", "") or ""),
                "status": str(hit.get("status", "") or ""),
                "url": str(metadata.get("url", "") or metadata.get("canonical_url", "") or ""),
            }
        )
    return citations


def extract_structured_facts(hits: list[dict[str, Any]], citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for hit, citation in zip(hits, citations):
        payload = hit.get("payload", {})
        if not isinstance(payload, dict) or not payload:
            continue
        facts.append(
            {
                "citationId": citation["id"],
                "sourceKind": citation["sourceKind"],
                "title": citation["title"],
                "asOfDate": citation["asOfDate"],
                "fundCodes": citation["fundCodes"],
                "stale": citation["stale"],
                "facts": _compact_json(payload, 2200),
            }
        )
    return facts


def build_source_coverage(hits: list[dict[str, Any]]) -> dict[str, Any]:
    found = {str(hit.get("source_kind", "") or "") for hit in hits}
    expected = ["portfolio_state", "llm_context", "evidence_item", "validated_advice", "committee_bundle", "long_memory"]
    return {
        "foundSourceKinds": sorted(item for item in found if item),
        "missingSourceKinds": [item for item in expected if item not in found],
        "hasPortfolio": "portfolio_state" in found,
        "hasMarketOrNews": bool({"llm_context", "evidence_item"}.intersection(found)),
        "hasValidatedAdvice": "validated_advice" in found,
        "hasCommitteeDecision": "committee_bundle" in found,
        "hasLongMemory": "long_memory" in found,
    }


def build_copilot_evidence_pack(
    *,
    query_plan: dict[str, Any],
    retrieval_result: dict[str, Any],
    token_budget: int,
) -> dict[str, Any]:
    hits = list(retrieval_result.get("hits", []) or [])
    citations = build_citations(hits)
    packed_hits: list[dict[str, Any]] = []
    for hit, citation in zip(hits, citations):
        packed_hits.append(
            {
                "citationId": citation["id"],
                "docId": citation["docId"],
                "chunkId": citation["chunkId"],
                "sourceKind": citation["sourceKind"],
                "title": citation["title"],
                "summary": citation["summary"],
                "text": _trim_text(hit.get("text_for_llm") or hit.get("summary", ""), 1400),
                "asOfDate": citation["asOfDate"],
                "availableFrom": citation["availableFrom"],
                "publishedAt": citation["publishedAt"],
                "fundCodes": citation["fundCodes"],
                "domain": citation["domain"],
                "entityId": citation["entityId"],
                "score": citation["score"],
                "scoreBreakdown": hit.get("score_breakdown", {}),
                "stale": citation["stale"],
                "visibility": citation["visibility"],
                "status": citation["status"],
                "payload": _compact_json(hit.get("payload", {}), 2400),
                "metadata": _compact_json(hit.get("metadata", {}), 1200),
            }
        )

    missing_data = list(retrieval_result.get("missing_data", []) or [])
    source_coverage = build_source_coverage(hits)
    trace_id = str(retrieval_result.get("trace_id", "") or "")
    trace_path = str(retrieval_result.get("trace_path", "") or "")
    return {
        "kind": PACK_KIND,
        "version": 1,
        "query_plan": query_plan,
        "hits": packed_hits,
        "citations": citations,
        "missingData": missing_data,
        "structuredFacts": extract_structured_facts(hits, citations),
        "sourceCoverage": source_coverage,
        "traceId": trace_id,
        "tracePath": trace_path,
        "tokenBudget": token_budget,
        "traceSummary": {
            "traceId": trace_id,
            "tracePath": trace_path,
            "hitCount": len(hits),
            "candidateCountBeforeFilter": retrieval_result.get("candidate_count_before_filter", 0),
            "candidateCountAfterFilter": retrieval_result.get("candidate_count_after_filter", 0),
            "citationIds": [item["id"] for item in citations],
            "missingData": missing_data,
            "sourceCoverage": source_coverage,
        },
    }
