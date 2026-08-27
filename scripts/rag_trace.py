from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from common import dump_json, timestamp_now
from rag_config import rag_trace_dir
from rag_index_store import write_trace
from rag_models import RagTrace, json_dumps


def build_trace_payload(
    *,
    trace_id: str,
    caller: str,
    query_plan: dict[str, Any],
    hard_filters: dict[str, Any],
    source_manifest_ids: list[str],
    candidate_count_before_filter: int,
    candidate_count_after_filter: int,
    rejected_samples: list[dict[str, Any]],
    final_hits: list[dict[str, Any]],
    missing_data: list[dict[str, Any]],
    token_budget: int,
    fallback_reason: str = "",
    answer_citation_ids: list[str] | None = None,
    retrieval_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_pack_sha256 = hashlib.sha256(json_dumps(final_hits).encode("utf-8")).hexdigest()
    return {
        "trace_id": trace_id,
        "created_at": timestamp_now(),
        "caller": caller,
        "query_plan": query_plan,
        "hard_filters": hard_filters,
        "source_manifest_ids": source_manifest_ids,
        "candidate_count_before_filter": candidate_count_before_filter,
        "candidate_count_after_filter": candidate_count_after_filter,
        "rejected_samples": rejected_samples,
        "final_hits": final_hits,
        "missing_data": missing_data,
        "token_budget": token_budget,
        "evidence_pack_sha256": evidence_pack_sha256,
        "answer_citation_ids": answer_citation_ids or [],
        "fallback_reason": fallback_reason,
        "retrieval": retrieval_metadata or {},
    }


def write_rag_trace(agent_home: Path, payload: dict[str, Any]) -> Path:
    query_plan = payload.get("query_plan", {}) or {}
    date_text = str(query_plan.get("query_date") or query_plan.get("as_of_date") or "undated")[:10]
    output_dir = rag_trace_dir(agent_home) / date_text
    output_path = output_dir / f"{payload['trace_id']}.json"
    dump_json(output_path, payload)
    write_trace(
        agent_home,
        RagTrace(
            trace_id=payload["trace_id"],
            query_plan=query_plan,
            hits=payload.get("final_hits", []),
            rejected_samples=payload.get("rejected_samples", []),
            missing_data=payload.get("missing_data", []),
            created_at=payload.get("created_at", ""),
            metadata={
                "caller": payload.get("caller", ""),
                "hard_filters": payload.get("hard_filters", {}),
                "source_manifest_ids": payload.get("source_manifest_ids", []),
                "candidate_count_before_filter": payload.get("candidate_count_before_filter", 0),
                "candidate_count_after_filter": payload.get("candidate_count_after_filter", 0),
                "evidence_pack_sha256": payload.get("evidence_pack_sha256", ""),
                "fallback_reason": payload.get("fallback_reason", ""),
                "retrieval": payload.get("retrieval", {}),
            },
        ),
    )
    return output_path
