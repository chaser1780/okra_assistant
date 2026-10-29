from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import uuid
from typing import Any

from rag_config import load_rag_config, rag_embedding_settings, rag_hybrid_settings
from rag_embedding_client import RagEmbeddingClient
from rag_index_store import connect_store, get_chunk_embedding_vector, init_store
from rag_models import RagQueryPlan
from rag_query_planner import hard_filter_description
from rag_rerank import rerank_hits
from rag_trace import build_trace_payload, write_rag_trace


TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+")


def _parse_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone(timedelta(hours=8)))
        return parsed
    except ValueError:
        if len(text) >= 10:
            try:
                return datetime.fromisoformat(f"{text[:10]}T23:59:59+08:00")
            except ValueError:
                return None
    return None


def _query_end(plan: RagQueryPlan) -> datetime:
    if plan.decision_at:
        try:
            return datetime.fromisoformat(plan.decision_at.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.fromisoformat(f"{plan.query_date}T23:59:59+08:00")


def _tokens(text: str) -> set[str]:
    return {item.lower() for item in TOKEN_RE.findall(str(text or "")) if item.strip()}


def _text_score(query: str, *texts: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.1
    haystack = _tokens(" ".join(texts))
    overlap = len(query_tokens.intersection(haystack))
    return min(1.0, overlap / max(1, len(query_tokens)) + (0.08 if overlap else 0.0))


def _is_fund_entity_id(entity_id: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", str(entity_id or "").strip()))


def _load_candidates(agent_home: Path, plan: RagQueryPlan) -> list[dict[str, Any]]:
    init_store(agent_home)
    clauses = ["d.active = 1", "c.active = 1"]
    params: list[Any] = []
    active_manifest_ids: list[str] = []
    with connect_store(agent_home) as conn:
        active_manifest_ids = [str(row["manifest_id"]) for row in conn.execute("SELECT manifest_id FROM active_manifests ORDER BY scope_key").fetchall()]
    if plan.source_kinds:
        placeholders = ",".join("?" for _ in plan.source_kinds)
        clauses.append(f"d.source_kind IN ({placeholders})")
        params.extend(plan.source_kinds)
    if plan.domains:
        placeholders = ",".join("?" for _ in plan.domains)
        clauses.append(f"d.domain IN ({placeholders})")
        params.extend(plan.domains)
    where = " AND ".join(clauses)
    if active_manifest_ids:
        placeholders = ",".join("?" for _ in active_manifest_ids)
        membership_join = f"""
            JOIN manifest_chunks mc ON mc.chunk_id = c.chunk_id
            JOIN active_manifests am ON am.manifest_id = mc.manifest_id
        """
        membership_where = f" AND mc.manifest_id IN ({placeholders})"
        query_params = [*params, *active_manifest_ids]
    else:
        membership_join = ""
        membership_where = ""
        query_params = params
    with connect_store(agent_home) as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT
                d.*, c.chunk_id, c.chunk_index, c.text_for_embedding, c.text_for_llm,
                c.token_estimate, c.embedding_status, c.metadata_json AS chunk_metadata_json
            FROM documents d
            JOIN chunks c ON c.doc_id = d.doc_id
            {membership_join}
            WHERE {where}
            {membership_where}
            """,
            query_params,
        ).fetchall()
    candidates = []
    for row in rows:
        item = dict(row)
        item["fund_codes"] = json.loads(item.pop("fund_codes_json") or "[]")
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item["chunk_metadata"] = json.loads(item.pop("chunk_metadata_json") or "{}")
        candidates.append(item)
    return candidates


def _reject(reason: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "reason": reason,
        "doc_id": item.get("doc_id", ""),
        "chunk_id": item.get("chunk_id", ""),
        "source_kind": item.get("source_kind", ""),
        "source_record_id": item.get("source_record_id", ""),
        "as_of_date": item.get("as_of_date", ""),
        "available_from": item.get("available_from", ""),
        "entity_id": item.get("entity_id", ""),
        "fund_codes": item.get("fund_codes", []),
        "visibility": item.get("visibility", ""),
        "learning_scope": item.get("learning_scope", ""),
    }


def _passes_hard_filters(item: dict[str, Any], plan: RagQueryPlan) -> tuple[bool, str]:
    query_day = _parse_date(plan.query_date)
    if query_day and not plan.allow_future_data:
        as_of = _parse_date(str(item.get("as_of_date", "")))
        if as_of and as_of > query_day:
            return False, "future_as_of_date"
        event = _parse_date(str(item.get("event_date", "")))
        if event and event > query_day:
            return False, "future_event_date"
        available_from = _parse_timestamp(str(item.get("available_from", "")))
        if available_from and available_from > _query_end(plan):
            return False, "future_available_from"
        published_at = _parse_timestamp(str(item.get("published_at", "")))
        if published_at and published_at > _query_end(plan):
            return False, "future_published_at"

    if plan.fund_codes:
        target = set(plan.fund_codes)
        fund_codes = set(item.get("fund_codes", []) or [])
        entity_id = str(item.get("entity_id", "") or "")
        entity_type = str(item.get("entity_type", "") or "")
        has_fund_binding = bool(fund_codes) or entity_type == "fund" or _is_fund_entity_id(entity_id)
        if has_fund_binding and not (target.intersection(fund_codes) or entity_id in target):
            return False, "fund_mismatch"

    visibility = str(item.get("visibility", "") or "")
    status = str(item.get("status", "") or "")
    if not plan.include_negative_memory and (visibility == "review_only" or status in {"archived", "rejected"}):
        return False, "memory_visibility"

    valid_from = _parse_date(str(item.get("valid_from", "")))
    valid_until = _parse_date(str(item.get("valid_until", "")))
    if query_day and valid_from and valid_from > query_day:
        return False, "memory_not_yet_valid"
    if query_day and valid_until and valid_until < query_day:
        return False, "memory_expired"
    metadata = item.get("metadata", {}) or {}
    if not plan.include_negative_memory and metadata.get("superseded_by"):
        return False, "memory_superseded"

    learning_scope = str(item.get("learning_scope", "") or metadata.get("learning_scope", "") or "")
    if not plan.include_execution and learning_scope == "execution_only":
        return False, "execution_boundary"
    if not plan.include_execution and str(item.get("source_kind", "")) == "execution_sync":
        return False, "execution_boundary"
    if not plan.include_execution and str(item.get("domain", "")) == "execution":
        return False, "execution_boundary"
    return True, ""


def _hit_from_candidate(item: dict[str, Any], plan: RagQueryPlan) -> dict[str, Any]:
    text_score = _text_score(plan.query, item.get("title", ""), item.get("summary", ""), item.get("text_for_embedding", ""))
    return {
        "chunk_id": item.get("chunk_id", ""),
        "doc_id": item.get("doc_id", ""),
        "source_kind": item.get("source_kind", ""),
        "source_record_id": item.get("source_record_id", ""),
        "source_path": item.get("source_path", ""),
        "source_tier": item.get("source_tier", ""),
        "title": item.get("title", ""),
        "summary": item.get("summary", ""),
        "text_for_llm": item.get("text_for_llm", ""),
        "as_of_date": item.get("as_of_date", ""),
        "available_from": item.get("available_from", ""),
        "published_at": item.get("published_at", ""),
        "domain": item.get("domain", ""),
        "entity_id": item.get("entity_id", ""),
        "fund_codes": item.get("fund_codes", []),
        "visibility": item.get("visibility", ""),
        "status": item.get("status", ""),
        "learning_scope": item.get("learning_scope", ""),
        "metadata": item.get("metadata", {}),
        "payload": item.get("payload", {}),
        "text_score": text_score,
    }


def _active_manifest_ids(agent_home: Path) -> list[str]:
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        rows = conn.execute("SELECT manifest_id FROM active_manifests ORDER BY scope_key").fetchall()
    return [str(row["manifest_id"]) for row in rows]


def _semantic_scores(agent_home: Path, candidates: list[dict[str, Any]], plan: RagQueryPlan) -> tuple[dict[str, float], dict[str, Any]]:
    """Optional semantic gray-release path; disabled by default."""
    config = load_rag_config(agent_home)
    hybrid = rag_hybrid_settings(agent_home, config)
    embedding = rag_embedding_settings(agent_home, config)
    if not hybrid.get("enabled", False):
        return {}, {"enabled": False, "mode": "lexical_rerank", "reason": "hybrid_disabled"}
    if not embedding.get("enabled", False) or embedding.get("dry_run", True):
        return {}, {"enabled": False, "mode": "lexical_rerank", "reason": "embedding_not_live"}
    model = str(embedding.get("model", "") or "")
    vectors: dict[str, list[float]] = {}
    for candidate in candidates:
        chunk_id = str(candidate.get("chunk_id", ""))
        vector = get_chunk_embedding_vector(agent_home, chunk_id, model=model)
        if vector:
            vectors[chunk_id] = vector
    coverage = len(vectors) / len(candidates) if candidates else 0.0
    minimum_coverage = float(hybrid.get("minimum_vector_coverage", 0.6) or 0.6)
    if coverage < minimum_coverage:
        return {}, {"enabled": False, "mode": "lexical_rerank", "reason": "insufficient_vector_coverage", "coverage": round(coverage, 4)}
    try:
        query_vector = RagEmbeddingClient(agent_home, config).embed_texts([plan.query], dry_run=False)[0]
    except Exception as exc:
        return {}, {"enabled": False, "mode": "lexical_rerank", "reason": "query_embedding_failed", "detail": str(exc)[:240], "coverage": round(coverage, 4)}
    return {chunk_id: _cosine_similarity(query_vector, vector) for chunk_id, vector in vectors.items()}, {
        "enabled": True,
        "mode": "hybrid_lexical_semantic",
        "coverage": round(coverage, 4),
        "semanticWeight": float(hybrid.get("semantic_weight", 0.2) or 0.2),
    }


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if not size:
        return 0.0
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = sum(left[index] * left[index] for index in range(size)) ** 0.5
    right_norm = sum(right[index] * right[index] for index in range(size)) ** 0.5
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def retrieve_rag_evidence(
    agent_home: Path,
    plan: RagQueryPlan,
    *,
    caller: str = "rag_retriever",
    write_trace_file: bool = True,
) -> dict[str, Any]:
    candidates = _load_candidates(agent_home, plan)
    accepted = []
    rejected = []
    for item in candidates:
        ok, reason = _passes_hard_filters(item, plan)
        if ok:
            accepted.append(item)
        elif len(rejected) < 80:
            rejected.append(_reject(reason, item))
    semantic_scores, semantic_status = _semantic_scores(agent_home, accepted, plan)
    hits = [_hit_from_candidate(item, plan) for item in accepted]
    for hit in hits:
        score = semantic_scores.get(str(hit.get("chunk_id", "")))
        if score is not None:
            hit["semantic_score"] = score
    ranked = rerank_hits(hits, plan, semantic_weight=float(semantic_status.get("semanticWeight", 0.0) or 0.0))[: plan.top_k]
    missing_data = []
    if not ranked:
        missing_data.append(
            {
                "reason": "no_hits_after_hard_filters",
                "query": plan.query,
                "fund_codes": plan.fund_codes,
                "query_date": plan.query_date,
            }
        )
    plan.metadata = {**plan.metadata, "retrieval_mode": semantic_status.get("mode", "lexical_rerank"), "semantic": semantic_status}
    trace_id = f"ragq_{uuid.uuid4().hex[:16]}"
    trace_payload = build_trace_payload(
        trace_id=trace_id,
        caller=caller,
        query_plan=plan.to_dict(),
        hard_filters=hard_filter_description(plan),
        source_manifest_ids=_active_manifest_ids(agent_home),
        candidate_count_before_filter=len(candidates),
        candidate_count_after_filter=len(accepted),
        rejected_samples=rejected,
        final_hits=ranked,
        missing_data=missing_data,
        token_budget=plan.token_budget,
        retrieval_metadata={
            "mode": semantic_status.get("mode", "lexical_rerank"),
            "semantic": semantic_status,
        },
    )
    trace_path = None
    if write_trace_file:
        trace_path = write_rag_trace(agent_home, trace_payload)
    return {
        "trace_id": trace_id,
        "trace_path": str(trace_path) if trace_path else "",
        "hits": ranked,
        "missing_data": missing_data,
        "rejected_samples": rejected,
        "candidate_count_before_filter": len(candidates),
        "candidate_count_after_filter": len(accepted),
        "semantic": semantic_status,
    }
