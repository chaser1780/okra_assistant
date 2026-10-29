from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rag_config import rag_profile_evidence_profile
from rag_query_planner import build_rag_query_plan
from rag_retriever import retrieve_rag_evidence


PROFILE_NAMES = {"decision", "memory", "review", "backtest"}


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _payload_sha256(value: Any) -> str:
    text = json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _timestamp_after_date(value: str, day: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            timestamp = datetime.fromisoformat(f"{text[:10]}T23:59:59+08:00")
        except ValueError:
            return False
    return timestamp > datetime.fromisoformat(f"{day}T23:59:59+08:00")


def _date_after(value: str, day: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        return text[:10] > day[:10]
    except TypeError:
        return False


def _profile_settings(agent_home: Path, profile_name: str) -> dict[str, Any]:
    if profile_name not in PROFILE_NAMES:
        raise ValueError(f"Unsupported RAG evidence profile: {profile_name}")
    return rag_profile_evidence_profile(agent_home, profile_name)


def profile_enabled(agent_home: Path, profile_name: str) -> bool:
    settings = _profile_settings(agent_home, profile_name)
    return bool(settings.get("enabled", False))


def _pack_from_retrieval(
    *,
    profile_name: str,
    plan: Any,
    retrieval: dict[str, Any],
    token_budget: int,
) -> dict[str, Any]:
    hits = list(retrieval.get("hits", []) or [])
    packed_hits = []
    citations = []
    for index, hit in enumerate(hits, start=1):
        citation_id = f"C{index}"
        metadata = hit.get("metadata", {}) if isinstance(hit.get("metadata"), dict) else {}
        citation = {
            "id": citation_id,
            "docId": str(hit.get("doc_id", "") or ""),
            "chunkId": str(hit.get("chunk_id", "") or ""),
            "sourceKind": str(hit.get("source_kind", "") or ""),
            "sourceRecordId": str(hit.get("source_record_id", "") or ""),
            "sourcePath": str(hit.get("source_path", "") or ""),
            "sourceTier": str(hit.get("source_tier", "") or ""),
            "title": str(hit.get("title", "") or ""),
            "summary": str(hit.get("summary", "") or "")[:420],
            "asOfDate": str(hit.get("as_of_date", "") or ""),
            "availableFrom": str(hit.get("available_from", "") or ""),
            "publishedAt": str(hit.get("published_at", "") or metadata.get("published_at", "") or ""),
            "domain": str(hit.get("domain", "") or ""),
            "entityId": str(hit.get("entity_id", "") or ""),
            "fundCodes": list(hit.get("fund_codes", []) or []),
            "score": hit.get("score", 0.0),
            "visibility": str(hit.get("visibility", "") or ""),
            "status": str(hit.get("status", "") or ""),
        }
        citations.append(citation)
        packed_hits.append(
            {
                **citation,
                "text": str(hit.get("text_for_llm") or hit.get("summary", "") or "")[:1400],
                "scoreBreakdown": hit.get("score_breakdown", {}),
                "metadata": metadata,
                "payload": hit.get("payload", {}) if isinstance(hit.get("payload"), dict) else {},
            }
        )
    missing_data = list(retrieval.get("missing_data", []) or [])
    trace_id = str(retrieval.get("trace_id", "") or "")
    trace_path = str(retrieval.get("trace_path", "") or "")
    return {
        "kind": f"{profile_name}_rag_evidence_pack",
        "version": 1,
        "profile": profile_name,
        "query_plan": plan.to_dict(),
        "hits": packed_hits,
        "citations": citations,
        "missingData": missing_data,
        "traceId": trace_id,
        "tracePath": trace_path,
        "tokenBudget": token_budget,
        "traceSummary": {
            "traceId": trace_id,
            "tracePath": trace_path,
            "hitCount": len(hits),
            "candidateCountBeforeFilter": retrieval.get("candidate_count_before_filter", 0),
            "candidateCountAfterFilter": retrieval.get("candidate_count_after_filter", 0),
            "citationIds": [item["id"] for item in citations],
            "missingData": missing_data,
        },
    }


def build_decision_evidence_pack(
    agent_home: Path,
    report_date: str,
    *,
    committee_bundle: dict[str, Any] | None,
    validated_advice: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = _profile_settings(agent_home, "decision")
    if not bool(settings.get("enabled", False)):
        return {"enabled": False, "profile": "decision", "fallback_reason": "profile_disabled"}
    if not committee_bundle:
        return {
            "enabled": True,
            "profile": "decision",
            "status": "missing",
            "missingData": [{"reason": "missing_committee_bundle", "query_date": report_date}],
            "hits": [],
            "citations": [],
            "traceSummary": {"hitCount": 0, "missingData": [{"reason": "missing_committee_bundle", "query_date": report_date}]},
        }

    fund_codes = [
        str(item.get("fund_code", "") or "").strip()
        for item in (committee_bundle.get("fund_decisions", []) or [])
        if str(item.get("fund_code", "") or "").strip()
    ]
    query = "decision evidence for existing committee and validated advice candidates"
    plan = build_rag_query_plan(
        query,
        query_date=report_date,
        retrieval_profile="decision_profile",
        intent="decision_support_existing_candidates_only",
        fund_codes=list(dict.fromkeys(fund_codes)),
        domains=_string_list(settings.get("domains")) or ["decision"],
        source_kinds=_string_list(settings.get("source_kinds")) or ["committee_bundle", "validated_advice"],
        top_k=_positive_int(settings.get("top_k"), 8),
        token_budget=_positive_int(settings.get("token_budget"), 6000),
        include_negative_memory=False,
        include_execution=False,
        metadata={
            "profile": "decision",
            "guardrail": "support_existing_committee_candidates_only",
            "committee_bundle_sha256": _payload_sha256(committee_bundle),
            "validated_advice_sha256": _payload_sha256(validated_advice or {}),
        },
    )
    retrieval = retrieve_rag_evidence(agent_home, plan, caller="decision_profile", write_trace_file=bool(settings.get("write_trace", True)))
    pack = _pack_from_retrieval(profile_name="decision", plan=plan, retrieval=retrieval, token_budget=plan.token_budget)
    pack["guardrails"] = {
        "mayGenerateNewAdvice": False,
        "requiresCommitteeBundle": True,
        "allowedSourceKinds": plan.source_kinds,
    }
    min_hits = _positive_int(settings.get("min_hits"), 1)
    pack["status"] = "ok" if len(pack.get("hits", []) or []) >= min_hits else "insufficient_hits"
    return pack


def build_memory_evidence_pack(
    agent_home: Path,
    report_date: str,
    *,
    domain: str,
    entity_key: str,
    title: str = "",
    text: str = "",
) -> dict[str, Any]:
    settings = _profile_settings(agent_home, "memory")
    if not bool(settings.get("enabled", False)):
        return {"enabled": False, "profile": "memory", "fallback_reason": "profile_disabled"}
    clean_domain = str(domain or "").strip()
    clean_entity = str(entity_key or "").strip()
    query_parts = [clean_domain, clean_entity, title, text]
    query = " ".join(str(item).strip() for item in query_parts if str(item).strip()) or "memory duplicate contradiction check"
    domains = [clean_domain] if clean_domain else []
    if clean_domain and clean_domain != "long_memory":
        domains.append("long_memory")
    plan = build_rag_query_plan(
        query,
        query_date=report_date,
        retrieval_profile="memory_profile",
        intent="memory_duplicate_contradiction_check",
        domains=domains,
        source_kinds=_string_list(settings.get("source_kinds")) or ["long_memory"],
        top_k=_positive_int(settings.get("top_k"), 6),
        token_budget=_positive_int(settings.get("token_budget"), 4000),
        include_negative_memory=False,
        include_execution=False,
        metadata={"profile": "memory", "domain": clean_domain, "entity_key": clean_entity},
    )
    retrieval = retrieve_rag_evidence(agent_home, plan, caller="memory_profile", write_trace_file=bool(settings.get("write_trace", True)))
    pack = _pack_from_retrieval(profile_name="memory", plan=plan, retrieval=retrieval, token_budget=plan.token_budget)
    same_entity_hits = []
    duplicate_permanent = False
    for hit in pack.get("hits", []) or []:
        entity_id = str(hit.get("entityId", "") or "")
        status = str(hit.get("status", "") or "")
        if clean_entity and entity_id == clean_entity:
            same_entity_hits.append(hit)
            if status == "permanent":
                duplicate_permanent = True
    pack["memoryCheck"] = {
        "domain": clean_domain,
        "entityKey": clean_entity,
        "sameEntityHitCount": len(same_entity_hits),
        "duplicatePermanent": duplicate_permanent,
        "skipWriteRecommended": bool(settings.get("skip_duplicate_permanent", True)) and duplicate_permanent,
    }
    return pack


def build_review_evidence_pack(
    agent_home: Path,
    base_date: str,
    *,
    review_date: str,
    fund_codes: list[str] | None = None,
    diagnostic_labels: list[str] | None = None,
) -> dict[str, Any]:
    settings = _profile_settings(agent_home, "review")
    if not bool(settings.get("enabled", False)):
        return {"enabled": False, "profile": "review", "fallback_reason": "profile_disabled"}
    query = "review historical counterexamples " + " ".join((diagnostic_labels or [])[:8])
    domains = _string_list(settings.get("domains"))
    if not domains:
        domains = ["long_memory", "portfolio", "market", "fund"]
    plan = build_rag_query_plan(
        query.strip(),
        query_date=review_date,
        retrieval_profile="review_profile",
        intent="historical_review_negative_examples",
        fund_codes=list(dict.fromkeys(fund_codes or [])),
        domains=domains,
        source_kinds=_string_list(settings.get("source_kinds")) or ["long_memory"],
        top_k=_positive_int(settings.get("top_k"), 8),
        token_budget=_positive_int(settings.get("token_budget"), 5000),
        include_negative_memory=bool(settings.get("include_negative_memory", True)),
        include_execution=False,
        metadata={"profile": "review", "base_date": base_date, "review_date": review_date, "diagnostic_labels": diagnostic_labels or []},
    )
    retrieval = retrieve_rag_evidence(agent_home, plan, caller="review_profile", write_trace_file=bool(settings.get("write_trace", True)))
    pack = _pack_from_retrieval(profile_name="review", plan=plan, retrieval=retrieval, token_budget=plan.token_budget)
    for hit in pack.get("hits", []) or []:
        negative = str(hit.get("visibility", "") or "") == "review_only" or str(hit.get("status", "") or "") in {"archived", "rejected"}
        hit["negativeExample"] = bool(negative)
    for citation in pack.get("citations", []) or []:
        negative = str(citation.get("visibility", "") or "") == "review_only" or str(citation.get("status", "") or "") in {"archived", "rejected"}
        citation["negativeExample"] = bool(negative)
    pack["guardrails"] = {"negativeExamplesMustBeLabeled": True, "includeExecution": False}
    return pack


def build_backtest_evidence_pack(
    agent_home: Path,
    replay_date: str,
    *,
    fund_codes: list[str] | None = None,
    mode: str = "baseline",
    decision_at: str | None = None,
) -> dict[str, Any]:
    settings = _profile_settings(agent_home, "backtest")
    if not bool(settings.get("enabled", False)):
        return {"enabled": False, "profile": "backtest", "fallback_reason": "profile_disabled"}
    query = f"backtest replay evidence available on {replay_date}"
    plan = build_rag_query_plan(
        query,
        query_date=replay_date,
        decision_at=decision_at,
        retrieval_profile="backtest_profile",
        intent="backtest_replay_no_future",
        fund_codes=list(dict.fromkeys(fund_codes or [])),
        source_kinds=_string_list(settings.get("source_kinds")) or ["long_memory", "validated_advice", "committee_bundle", "portfolio_state"],
        top_k=_positive_int(settings.get("top_k"), 8),
        token_budget=_positive_int(settings.get("token_budget"), 5000),
        include_negative_memory=False,
        include_execution=False,
        allow_future_data=False,
        metadata={"profile": "backtest", "replay_date": replay_date, "mode": mode},
    )
    retrieval = retrieve_rag_evidence(agent_home, plan, caller="backtest_profile", write_trace_file=bool(settings.get("write_trace", True)))
    pack = _pack_from_retrieval(profile_name="backtest", plan=plan, retrieval=retrieval, token_budget=plan.token_budget)
    rejected = list(retrieval.get("rejected_samples", []) or [])
    future_rejections = [item for item in rejected if str(item.get("reason", "") or "").startswith("future_")]
    violations = [
        item
        for item in pack.get("hits", []) or []
        if _date_after(str(item.get("asOfDate", "") or ""), replay_date) or _timestamp_after_date(str(item.get("availableFrom", "") or ""), replay_date)
    ]
    audit = {
        "strictNoFuture": bool(settings.get("strict_no_future", True)),
        "replayDate": replay_date,
        "cutoffPrecision": str(plan.metadata.get("cutoff_precision") or "end_of_day_legacy"),
        "decisionAt": plan.decision_at,
        "replayExactCutoff": bool(plan.decision_at),
        "intradayTrusted": bool(plan.decision_at),
        "futureRejectedCount": len(future_rejections),
        "violations": violations[:12],
        "passed": not violations,
    }
    pack["noFutureAudit"] = audit
    if audit["strictNoFuture"] and violations:
        pack["status"] = "failed_no_future_audit"
    else:
        pack["status"] = "ok"
    return pack
