from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from rag_models import RagQueryPlan


REVIEW_PROFILES = {"review", "lesson_review", "memory_review", "rag_admin"}
EXECUTION_PROFILES = {"execution", "execution_review"}


def end_of_day_iso(day: str) -> str:
    parsed = date.fromisoformat(str(day)[:10])
    return datetime.combine(parsed, time(23, 59, 59)).isoformat() + "+08:00"


def build_rag_query_plan(
    query: str,
    *,
    query_date: str,
    retrieval_profile: str = "copilot_qa",
    intent: str = "general_qa",
    fund_codes: list[str] | None = None,
    domains: list[str] | None = None,
    source_kinds: list[str] | None = None,
    top_k: int = 8,
    token_budget: int = 6000,
    time_mode: str = "selected_date",
    allow_future_data: bool = False,
    include_negative_memory: bool | None = None,
    include_execution: bool | None = None,
    require_structured_facts: bool = True,
    metadata: dict[str, Any] | None = None,
) -> RagQueryPlan:
    profile = str(retrieval_profile or "copilot_qa")
    return RagQueryPlan(
        query=query,
        retrieval_profile=profile,
        query_date=query_date,
        as_of_date=query_date,
        time_mode=time_mode,
        intent=intent,
        fund_codes=fund_codes or [],
        domains=domains or [],
        source_kinds=source_kinds or [],
        top_k=top_k,
        token_budget=token_budget,
        allow_future_data=allow_future_data,
        include_negative_memory=include_negative_memory if include_negative_memory is not None else profile in REVIEW_PROFILES,
        include_archived=include_negative_memory if include_negative_memory is not None else profile in REVIEW_PROFILES,
        include_rejected=include_negative_memory if include_negative_memory is not None else profile in REVIEW_PROFILES,
        include_execution=include_execution if include_execution is not None else profile in EXECUTION_PROFILES,
        require_structured_facts=require_structured_facts,
        metadata=metadata or {},
    )


def hard_filter_description(plan: RagQueryPlan) -> dict[str, Any]:
    return {
        "no_future": not plan.allow_future_data,
        "query_date_end": end_of_day_iso(plan.query_date),
        "fund_codes": plan.fund_codes,
        "domains": plan.domains,
        "source_kinds": plan.source_kinds,
        "include_negative_memory": plan.include_negative_memory,
        "include_execution": plan.include_execution,
        "retrieval_profile": plan.retrieval_profile,
    }
