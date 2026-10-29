from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from common import today_shanghai
from rag_answering import build_copilot_evidence_pack
from rag_config import load_rag_config
from rag_query_planner import build_rag_query_plan
from rag_retriever import retrieve_rag_evidence


class RagUnavailable(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


SOURCE_KIND_BY_CONFIG_KEY = {
    "long_memory": "long_memory",
    "portfolio_state": "portfolio_state",
    "llm_context": "llm_context",
    "evidence_index": "evidence_item",
    "validated_advice": "validated_advice",
    "committee_bundle": "committee_bundle",
    "agent_outputs": "agent_outputs",
    "execution_sync": "execution_sync",
    "raw_news": "raw_news",
}

EXECUTION_INTENTS = {"execution_explain", "position_reconcile", "pending_confirmation"}
EXECUTION_SOURCE_KINDS = {"execution_sync", "long_memory"}
EXECUTION_DOMAINS = {"execution"}


def _valid_date(value: Any) -> str:
    text = str(value or "").strip()
    if text:
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            raise ValueError(f"selectedDate must be a real YYYY-MM-DD date, got {text!r}")
    return today_shanghai()


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _enabled_source_kinds(settings: dict[str, Any]) -> list[str]:
    sources = settings.get("sources", {}) if isinstance(settings.get("sources"), dict) else {}
    result: list[str] = []
    for key, source_kind in SOURCE_KIND_BY_CONFIG_KEY.items():
        if sources.get(key, False) and source_kind not in result:
            result.append(source_kind)
    return result


def _question_from_payload(payload: dict[str, Any]) -> str:
    question = str(payload.get("question", "") or "").strip()
    if question:
        return question
    context = str(payload.get("context", "") or "").strip()
    return f"请解释当前页面的关键结论、风险和证据。{context}".strip()


def _intent_from_payload(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("intent", "") or "").strip()
    if explicit in {"page_explain", "fund_explain", "decision_explain", "risk_review", "memory_review"}:
        return explicit
    if explicit == "execution_review":
        return "execution_explain"
    page = str(payload.get("page", "") or "").strip()
    question = str(payload.get("question", "") or "").strip().lower()
    if page == "execution":
        if any(token in question for token in ("pending", "confirm", "confirmation", "settlement", "待确认", "确认", "结算")):
            return "pending_confirmation"
        if any(token in question for token in ("reconcile", "position", "持仓", "仓位", "对账", "同步")):
            return "position_reconcile"
        return "execution_explain"
    if page == "fundDetail" or str(payload.get("fundCode", "") or "").strip():
        return "fund_explain"
    if page in {"research", "intelligence", "realtime"}:
        return "market_explain"
    return "general_qa"


def _execution_enabled_sources(settings: dict[str, Any]) -> list[str]:
    source_kinds = _enabled_source_kinds(settings)
    return [item for item in source_kinds if item in EXECUTION_SOURCE_KINDS]


def build_copilot_rag_pack(agent_home: Path, payload: dict[str, Any]) -> dict[str, Any]:
    config = load_rag_config(agent_home)
    settings = config.get("rag", {}) or {}
    if not settings.get("enabled", False):
        raise RagUnavailable("rag_disabled")

    query_date = _valid_date(payload.get("selectedDate"))
    question = _question_from_payload(payload)
    # contract §6: optional timezone-aware decision time. Passed through to the
    # planner as decision_at (scripts side enforces Shanghai-local date ==
    # query_date, else ValueError -> 400). Absent => planner tags
    # cutoff_precision=end_of_day_legacy; we never default to now().
    decision_at = str(payload.get("decisionAt") or payload.get("decision_at") or "").strip() or None
    fund_code = str(payload.get("fundCode", "") or "").strip()
    top_k = _positive_int(settings.get("top_k"), 8)
    token_budget = _positive_int(settings.get("token_budget"), 6000)
    min_hits = _positive_int(settings.get("min_hits"), 1)
    retrieval_profile = str(settings.get("default_profile", "") or "copilot_qa")
    intent = _intent_from_payload(payload)
    include_execution = intent in EXECUTION_INTENTS
    source_kinds = _execution_enabled_sources(settings) if include_execution else _enabled_source_kinds(settings)
    plan = build_rag_query_plan(
        question,
        query_date=query_date,
        decision_at=decision_at,
        retrieval_profile="execution" if include_execution else retrieval_profile,
        intent=intent,
        fund_codes=[fund_code] if fund_code else [],
        domains=sorted(EXECUTION_DOMAINS) if include_execution else [],
        source_kinds=source_kinds,
        top_k=top_k,
        token_budget=token_budget,
        include_execution=include_execution,
        metadata={
            "consumer": "copilot",
            "page": str(payload.get("page", "") or ""),
            "context": str(payload.get("context", "") or ""),
        },
    )
    retrieval = retrieve_rag_evidence(
        agent_home,
        plan,
        caller="copilot",
        write_trace_file=bool(settings.get("trace_enabled", True)),
    )
    pack = build_copilot_evidence_pack(query_plan=plan.to_dict(), retrieval_result=retrieval, token_budget=token_budget)
    hit_count = len(pack.get("hits", []) or [])
    fallback_reason = ""
    if hit_count < min_hits:
        fallback_reason = "hit_count_below_min"
    elif pack.get("missingData"):
        fallback_reason = "missing_data"
    pack["sourceDate"] = query_date
    pack["decisionAt"] = plan.decision_at or ""
    pack["timeBasis"] = str(plan.metadata.get("cutoff_precision") or "end_of_day_legacy")
    pack["status"] = "insufficient_hits" if fallback_reason else "ok"
    pack["fallbackReason"] = fallback_reason
    pack["fallbackToLegacy"] = bool(settings.get("fallback_to_legacy", True))
    pack["retrieval"] = {
        "intent": plan.intent,
        "profile": plan.retrieval_profile,
        "hitCount": hit_count,
        "missingData": pack.get("missingData", []),
        "sourceCoverage": pack.get("sourceCoverage", {}),
        "candidateCountBeforeFilter": retrieval.get("candidate_count_before_filter", 0),
        "candidateCountAfterFilter": retrieval.get("candidate_count_after_filter", 0),
        "fallbackReason": fallback_reason,
        "mode": (retrieval.get("semantic", {}) or {}).get("mode", "lexical_rerank"),
    }
    return pack
