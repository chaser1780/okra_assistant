from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from artifact_boundary import assert_refactor_write_allowed, relative_posix
from build_action_ticket_shadow import action_ticket_path, load_portfolio_state_for_report, run_builder as run_action_ticket_builder, safe_float
from common import dump_json, load_json, resolve_agent_home, resolve_date, timestamp_now, validated_advice_path
from layered_context_models import (
    SCHEMA_VERSION,
    LayeredContextItem,
    MissingDataItem,
    RagTraceRef,
    RetrievalPack,
    RetrievalPackArtifact,
    Visibility,
)


def retrieval_pack_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "retrieval_packs" / f"{report_date}.json"


def llm_context_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "llm_context" / f"{report_date}.json"


def evidence_index_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "evidence_index" / f"{report_date}.json"


def long_memory_export_path(agent_home: Path) -> Path:
    return agent_home / "db" / "long_memory" / "exports" / "all_memory.json"


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def source_artifacts(agent_home: Path, paths: list[Path]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in paths:
        if path.exists():
            artifacts.append(
                {
                    "kind": infer_source_kind(path),
                    "path": relative_posix(path, agent_home),
                    "content_sha256": content_sha256(path),
                }
            )
    artifacts.append({"kind": "builder", "path": "scripts/build_layered_retrieval_pack.py", "content_sha256": ""})
    return artifacts


def infer_source_kind(path: Path) -> str:
    parts = [part.lower() for part in path.parts]
    if "action_tickets" in parts:
        return "action_ticket"
    if "validated_advice" in parts:
        return "validated_advice"
    if "portfolio_state" in parts:
        return "portfolio_state"
    if "llm_context" in parts:
        return "llm_context"
    if "evidence_index" in parts:
        return "evidence_index"
    if "long_memory" in parts:
        return "long_memory"
    return "source_artifact"


def decision_cutoff_for(report_date: str, generated_at: str, validated: dict[str, Any]) -> str:
    generated_at = str(generated_at or validated.get("generated_at", "") or "")
    if generated_at:
        return generated_at
    return f"{report_date}T23:59:59+08:00"


def as_available_from(payload: dict[str, Any], fallback: str) -> str:
    for key in ("available_from", "retrieved_at", "generated_at", "updated_at", "published_at", "created_at"):
        value = str(payload.get(key, "") or "").strip()
        if value:
            return normalize_timestamp(value, fallback)
    return fallback


def normalize_timestamp(value: str, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text}T23:59:59+08:00"
    if "T" not in text and len(text) >= 10:
        return f"{text[:10]}T23:59:59+08:00"
    return text


def as_of_date(payload: dict[str, Any], report_date: str) -> str:
    for key in ("as_of_date", "as_of", "trade_date", "estimate_date", "published_at", "generated_at", "updated_at"):
        value = str(payload.get(key, "") or "").strip()
        if value:
            return value[:10]
    return report_date


def fund_lookup(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("fund_code")): item for item in items if isinstance(item, dict) and item.get("fund_code")}


def evidence_lookup(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("evidence_id")): item for item in context.get("evidence_items", []) or [] if isinstance(item, dict) and item.get("evidence_id")}


def action_ticket_artifact(agent_home: Path, report_date: str, generated_at: str | None = None, source_mode: str = "validated") -> dict[str, Any]:
    path = action_ticket_path(agent_home, report_date)
    if not path.exists():
        run_action_ticket_builder(agent_home, report_date, generated_at=generated_at, source_mode=source_mode)
    return load_json(path)


def make_item(
    *,
    item_id: str,
    layer: str,
    source_kind: str,
    source_path: str,
    source_record_id: str,
    as_of_date_value: str,
    available_from: str,
    status: str,
    summary: str,
    domain: str = "",
    fund_code: str = "",
    value: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    score: float | None = None,
) -> LayeredContextItem:
    return LayeredContextItem(
        item_id=item_id,
        layer=layer,
        source_kind=source_kind,
        source_path=source_path,
        source_record_id=source_record_id,
        as_of_date=as_of_date_value,
        available_from=available_from,
        status=status,
        summary=summary,
        domain=domain,
        fund_code=fund_code,
        value=value or {},
        metadata=metadata or {},
        score=score,
    )


def portfolio_fact(ticket: dict[str, Any], portfolio: dict[str, Any], generated_at: str, portfolio_source_path: str) -> LayeredContextItem | None:
    positions = fund_lookup(portfolio.get("funds", []) or [])
    fund_code = str(ticket.get("fund_code", "") or "")
    position = positions.get(fund_code)
    if not position:
        return None
    as_of = str(portfolio.get("as_of_date", "") or position.get("as_of_date", "") or ticket.get("report_date", ""))
    available = as_available_from(portfolio.get("state_metadata", {}) or {}, generated_at)
    total_value = safe_float(portfolio.get("total_value"))
    current_value = safe_float(position.get("current_value"))
    return make_item(
        item_id=f"fact:portfolio:{fund_code}:position",
        layer="canonical_fact",
        source_kind="portfolio_state",
        source_path=portfolio_source_path,
        source_record_id=f"fund:{fund_code}",
        as_of_date_value=as_of,
        available_from=available,
        status="present",
        summary=f"Position value CNY {current_value:.2f}; role={position.get('role', '')}.",
        domain="portfolio",
        fund_code=fund_code,
        value={
            "current_value": current_value,
            "holding_pnl": safe_float(position.get("holding_pnl")),
            "holding_return_pct": safe_float(position.get("holding_return_pct")),
            "holding_units": safe_float(position.get("holding_units")),
            "cost_basis_value": safe_float(position.get("cost_basis_value")),
            "weight_pct": round(current_value / total_value * 100.0, 4) if total_value else None,
            "role": position.get("role", ""),
            "style_group": position.get("style_group", ""),
            "strategy_bucket": position.get("strategy_bucket") or ticket.get("portfolio_bucket", ""),
            "fixed_daily_buy_amount": safe_float(position.get("fixed_daily_buy_amount")),
            "allow_trade": bool(position.get("allow_trade", True)),
        },
        metadata={"trust_level": "structured_current"},
    )


def ticket_fact(ticket: dict[str, Any], report_date: str) -> LayeredContextItem:
    return make_item(
        item_id=f"fact:ticket:{ticket.get('ticket_id', '')}",
        layer="canonical_fact",
        source_kind="action_ticket",
        source_path=f"db/action_tickets/{report_date}.json",
        source_record_id=str(ticket.get("ticket_id", "") or ""),
        as_of_date_value=report_date,
        available_from=str(ticket.get("generated_at", "") or f"{report_date}T23:59:59+08:00"),
        status="present",
        summary=f"Shadow ticket {ticket.get('action_verb')} amount {safe_float(ticket.get('validated_amount')):.2f}; status={ticket.get('ticket_status')}.",
        domain="decision",
        fund_code=str(ticket.get("fund_code", "") or ""),
        value={
            "action_verb": ticket.get("action_verb", ""),
            "execution_mode": ticket.get("execution_mode", ""),
            "ticket_status": ticket.get("ticket_status", ""),
            "validated_amount": ticket.get("validated_amount", 0.0),
            "requested_amount": ticket.get("requested_amount"),
            "confidence": ticket.get("confidence", 0.0),
            "hard_guardrail_results": ticket.get("hard_guardrail_results", []),
            "soft_policy_adjustments": ticket.get("soft_policy_adjustments", []),
        },
        metadata={"trust_level": "shadow_ticket"},
    )


def ticket_seed_source(ticket: dict[str, Any], report_date: str) -> tuple[str, str]:
    refs = ticket.get("supporting_evidence_refs", []) or []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        source_kind = str(ref.get("source_kind", "") or "")
        source_path = str(ref.get("source_path", "") or "")
        if source_kind and source_path:
            return source_kind, source_path
    return "validated_advice", f"db/validated_advice/{report_date}.json"


def validated_decision_fact(ticket: dict[str, Any], validated: dict[str, Any], report_date: str) -> LayeredContextItem:
    source_kind, source_path = ticket_seed_source(ticket, report_date)
    trust_level = "native_seed_output" if source_kind == "native_action_seed" else "validated_output"
    mode = "native_action_seed" if source_kind == "native_action_seed" else str(validated.get("decision_mode", "") or "")
    return make_item(
        item_id=f"fact:validated:{report_date}:{ticket.get('fund_code')}:{ticket.get('action_verb')}",
        layer="canonical_fact",
        source_kind=source_kind,
        source_path=source_path,
        source_record_id=str((ticket.get("legacy_mapping", {}) or {}).get("suggestion_id", "") or ticket.get("ticket_id", "")),
        as_of_date_value=report_date,
        available_from=str(ticket.get("generated_at", "") or validated.get("generated_at", "") or f"{report_date}T23:59:59+08:00"),
        status="present",
        summary=f"Decision seed mode={mode}; execution_eligible={validated.get('execution_eligible', True)}.",
        domain="decision",
        fund_code=str(ticket.get("fund_code", "") or ""),
        value={
            "decision_mode": mode,
            "execution_eligible": validated.get("execution_eligible", True),
            "cash_hub_available": validated.get("cash_hub_available"),
            "immediately_available_cash": validated.get("immediately_available_cash"),
            "delayed_sell_proceeds": validated.get("delayed_sell_proceeds"),
        },
        metadata={"trust_level": trust_level},
    )


def context_fund(context: dict[str, Any], fund_code: str) -> dict[str, Any]:
    for item in context.get("funds", []) or []:
        if isinstance(item, dict) and str(item.get("fund_code")) == fund_code:
            return item
    return {}


def market_facts_from_context(ticket: dict[str, Any], context: dict[str, Any], report_date: str) -> list[LayeredContextItem]:
    fund_code = str(ticket.get("fund_code", "") or "")
    fund = context_fund(context, fund_code)
    generated_at = str(context.get("generated_at", "") or ticket.get("generated_at", "") or f"{report_date}T23:59:59+08:00")
    facts: list[LayeredContextItem] = []
    for field_name, source_kind, domain, summary_key in (
        ("quote", "quote_snapshot", "market_data", "nav"),
        ("intraday_proxy", "intraday_proxy", "market_data", "change_pct"),
        ("estimated_nav", "estimated_nav", "market_data", "estimate_change_pct"),
        ("fund_profile", "fund_profile", "fund", "fund_type"),
    ):
        payload = fund.get(field_name, {}) if isinstance(fund.get(field_name), dict) else {}
        if not payload:
            continue
        status = "stale" if payload.get("stale") or "delayed" in str(payload.get("freshness_status", payload.get("estimate_freshness_status", ""))) else "present"
        facts.append(
            make_item(
                item_id=f"fact:{source_kind}:{fund_code}",
                layer="canonical_fact",
                source_kind=source_kind,
                source_path=f"db/llm_context/{report_date}.json",
                source_record_id=f"{fund_code}:{field_name}",
                as_of_date_value=as_of_date(payload, report_date),
                available_from=as_available_from(payload, generated_at),
                status=status,
                summary=f"{source_kind} for {ticket.get('fund_name', fund_code)}; {summary_key}={payload.get(summary_key, '')}.",
                domain=domain,
                fund_code=fund_code,
                value={key: payload.get(key) for key in sorted(payload) if key not in {"raw_payload"}},
                metadata={"trust_level": "structured_context"},
            )
        )
    return facts


def derived_signals_from_context(ticket: dict[str, Any], context: dict[str, Any], report_date: str) -> list[LayeredContextItem]:
    fund_code = str(ticket.get("fund_code", "") or "")
    fund = context_fund(context, fund_code)
    generated_at = str(context.get("generated_at", "") or ticket.get("generated_at", "") or f"{report_date}T23:59:59+08:00")
    signals: list[LayeredContextItem] = []
    for source_field in ("intraday_proxy", "estimated_nav", "quote"):
        payload = fund.get(source_field, {}) if isinstance(fund.get(source_field), dict) else {}
        if not payload:
            continue
        direction_value = payload.get("change_pct", payload.get("estimate_change_pct", payload.get("day_change_pct", 0.0)))
        direction = "positive" if safe_float(direction_value) > 0 else "negative" if safe_float(direction_value) < 0 else "neutral"
        signals.append(
            make_item(
                item_id=f"signal:{fund_code}:{source_field}",
                layer="derived_signal",
                source_kind="llm_context",
                source_path=f"db/llm_context/{report_date}.json",
                source_record_id=f"{fund_code}:{source_field}",
                as_of_date_value=as_of_date(payload, report_date),
                available_from=as_available_from(payload, generated_at),
                status="stale" if payload.get("stale") else "present",
                summary=f"{source_field} signal is {direction}; value={direction_value}.",
                domain="market",
                fund_code=fund_code,
                value={"signal_type": source_field, "direction": direction, "value": direction_value, "confidence": payload.get("confidence")},
                metadata={"derived_from": source_field},
            )
        )
    return signals


def raw_observation_refs(ticket: dict[str, Any], context: dict[str, Any], report_date: str) -> list[LayeredContextItem]:
    fund_code = str(ticket.get("fund_code", "") or "")
    evidence = evidence_lookup(context)
    generated_at = str(context.get("generated_at", "") or ticket.get("generated_at", "") or f"{report_date}T23:59:59+08:00")
    refs: list[LayeredContextItem] = []
    fund = context_fund(context, fund_code)
    for ref in list(fund.get("evidence_refs", []) or [])[:12]:
        evidence_id = ref.get("evidence_id") if isinstance(ref, dict) else ref
        item = evidence.get(str(evidence_id))
        if not item:
            continue
        refs.append(
            make_item(
                item_id=f"raw:{item.get('evidence_id')}",
                layer="raw_observation_ref",
                source_kind=str(item.get("evidence_type", "evidence_item") or "evidence_item"),
                source_path=f"db/llm_context/{report_date}.json",
                source_record_id=str(item.get("evidence_id", "") or ""),
                as_of_date_value=str(item.get("as_of") or report_date)[:10],
                available_from=as_available_from({"retrieved_at": item.get("retrieved_at")}, generated_at),
                status="stale" if item.get("stale") else "present",
                summary=str(item.get("summary", "") or item.get("source_title", "") or "structured evidence item"),
                domain=str(item.get("entity_type", "") or "fund"),
                fund_code=fund_code,
                value={"source_role": item.get("source_role"), "source_tier": item.get("source_tier"), "confidence": item.get("confidence")},
                metadata={"source_url": item.get("source_url", ""), "provider": item.get("provider", "")},
            )
        )
    return refs


def long_text_evidence_from_context(ticket: dict[str, Any], context: dict[str, Any], report_date: str) -> list[LayeredContextItem]:
    fund_code = str(ticket.get("fund_code", "") or "")
    fund = context_fund(context, fund_code)
    generated_at = str(context.get("generated_at", "") or ticket.get("generated_at", "") or f"{report_date}T23:59:59+08:00")
    evidence: list[LayeredContextItem] = []
    for index, item in enumerate(fund.get("recent_news", []) or []):
        if not isinstance(item, dict):
            continue
        evidence.append(
            make_item(
                item_id=f"text:{report_date}:{fund_code}:recent_news:{index}",
                layer="long_text_evidence",
                source_kind="llm_context",
                source_path=f"db/llm_context/{report_date}.json",
                source_record_id=f"{fund_code}:recent_news:{index}",
                as_of_date_value=str(item.get("published_at", report_date) or report_date)[:10],
                available_from=as_available_from(item, generated_at),
                status="present",
                summary=str(item.get("summary") or item.get("title") or "")[:500],
                domain="news",
                fund_code=fund_code,
                value={"title": item.get("title", ""), "impact": item.get("impact", ""), "source_name": item.get("source_name", "")},
                metadata={"url": item.get("url", "")},
            )
        )
    return evidence


def decision_history_from_ticket(ticket: dict[str, Any], report_date: str) -> list[LayeredContextItem]:
    mapping = ticket.get("legacy_mapping", {}) or {}
    source_kind, source_path = ticket_seed_source(ticket, report_date)
    return [
        make_item(
            item_id=f"decision:{report_date}:{ticket.get('fund_code')}:{ticket.get('action_verb')}",
            layer="decision_event",
            source_kind=source_kind,
            source_path=source_path,
            source_record_id=str(mapping.get("suggestion_id", "") or ticket.get("ticket_id", "")),
            as_of_date_value=report_date,
            available_from=str(ticket.get("generated_at", "") or f"{report_date}T23:59:59+08:00"),
            status="present",
            summary=str(ticket.get("thesis", "") or f"{ticket.get('action_verb')} decision"),
            domain="decision",
            fund_code=str(ticket.get("fund_code", "") or ""),
            value={
                "model_action": mapping.get("model_action", ""),
                "validated_action": mapping.get("validated_action", ""),
                "execution_status": mapping.get("execution_status", ""),
                "priority": mapping.get("priority"),
            },
        )
    ]


def memory_items(ticket: dict[str, Any], memory_export: dict[str, Any], report_date: str, generated_at: str) -> tuple[list[LayeredContextItem], list[LayeredContextItem], list[LayeredContextItem]]:
    fund_code = str(ticket.get("fund_code", "") or "")
    style = str(ticket.get("portfolio_bucket", "") or ticket.get("role", "") or "")
    adaptive: list[LayeredContextItem] = []
    similar: list[LayeredContextItem] = []
    anti: list[LayeredContextItem] = []
    for item in memory_export.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "") or "")
        if status in {"archived", "rejected"}:
            continue
        metadata = item.get("metadata", {}) or {}
        learning_scope = str(item.get("learning_scope", "") or metadata.get("learning_scope", "") or "")
        if learning_scope == "execution_only" or item.get("domain") == "execution":
            continue
        entity_key = str(item.get("entity_key", "") or "")
        tags = {str(tag) for tag in (metadata.get("tags", []) or [])}
        text = f"{item.get('title', '')} {item.get('text', '')} {entity_key} {' '.join(tags)}"
        fund_match = fund_code and fund_code in text
        style_match = bool(style and style in text)
        portfolio_match = str(item.get("domain", "")) == "portfolio"
        if not (fund_match or style_match or portfolio_match):
            continue
        available = as_available_from(item, generated_at)
        as_of = str(item.get("valid_from") or item.get("updated_at") or item.get("created_at") or report_date)[:10]
        context_item = make_item(
            item_id=f"memory:{item.get('memory_id')}",
            layer="retrieved_memory",
            source_kind="long_memory",
            source_path="db/long_memory/exports/all_memory.json",
            source_record_id=str(item.get("memory_id", "") or ""),
            as_of_date_value=as_of,
            available_from=available,
            status="present",
            summary=str(item.get("text") or item.get("title") or "")[:500],
            domain=str(item.get("domain", "") or "memory"),
            fund_code=fund_code if fund_match else "",
            value={
                "memory_type": item.get("memory_type", ""),
                "status": status,
                "priority": item.get("priority", ""),
                "confidence": item.get("confidence", 0.0),
                "support_count": item.get("support_count", 0),
                "contradiction_count": item.get("contradiction_count", 0),
            },
            metadata={"entity_key": entity_key, "tags": sorted(tags), "horizon_bucket": item.get("horizon_bucket", ""), "learning_scope": learning_scope},
            score=safe_float(item.get("confidence")),
        )
        lower_text = text.lower()
        if item.get("memory_type") == "portfolio_policy_memory" and len(adaptive) < 4:
            adaptive.append(context_item)
        elif any(token in lower_text for token in ("avoid", "不要", "风险", "overweight", "拥挤", "回撤")) and len(anti) < 4:
            anti.append(context_item)
        elif len(similar) < 4:
            similar.append(context_item)
    return adaptive, similar, anti


def rag_noncanonical_evidence(agent_home: Path, ticket: dict[str, Any], report_date: str, *, enabled: bool) -> tuple[list[LayeredContextItem], list[RagTraceRef], list[MissingDataItem]]:
    if not enabled:
        return [], [RagTraceRef("rag-disabled", "", "portfolio_trader", fallback_used=True, fallback_reason="RAG disabled for deterministic Phase 2 build")], []
    try:
        from rag_query_planner import build_rag_query_plan
        from rag_retriever import retrieve_rag_evidence
    except Exception as exc:
        return [], [RagTraceRef("rag-import-failed", "", "portfolio_trader", fallback_used=True, fallback_reason=str(exc))], [
            MissingDataItem("rag_evidence", "missing", f"RAG import failed: {exc}", "Non-canonical evidence is empty; structured facts still drive the pack.")
        ]
    try:
        plan = build_rag_query_plan(
            f"{ticket.get('fund_name', '')} {ticket.get('action_verb', '')} {ticket.get('thesis', '')}",
            query_date=report_date,
            retrieval_profile="portfolio_trader",
            intent="action_ticket_context",
            fund_codes=[str(ticket.get("fund_code", ""))],
            top_k=4,
            include_execution=False,
            include_negative_memory=False,
        )
        result = retrieve_rag_evidence(agent_home, plan, caller="build_layered_retrieval_pack", write_trace_file=True)
    except Exception as exc:
        return [], [RagTraceRef("rag-retrieval-failed", "", "portfolio_trader", fallback_used=True, fallback_reason=str(exc))], [
            MissingDataItem("rag_evidence", "missing", f"RAG retrieval failed: {exc}", "Non-canonical evidence is empty; structured facts still drive the pack.")
        ]
    items: list[LayeredContextItem] = []
    for index, hit in enumerate(result.get("hits", []) or []):
        source_kind = str(hit.get("source_kind", "") or "")
        layer = "anti_pattern" if hit.get("is_negative_example") else "long_text_evidence"
        items.append(
            make_item(
                item_id=f"rag:{hit.get('doc_id')}:{hit.get('chunk_id') or index}",
                layer=layer,
                source_kind=source_kind,
                source_path=str(hit.get("source_path", "") or "db/rag/rag.sqlite"),
                source_record_id=str(hit.get("source_record_id", "") or hit.get("doc_id", "")),
                as_of_date_value=str(hit.get("as_of_date", "") or report_date)[:10],
                available_from=str(hit.get("available_from", "") or f"{report_date}T23:59:59+08:00"),
                status="present",
                summary=str(hit.get("summary") or hit.get("text_for_llm") or "")[:500],
                domain=str(hit.get("domain", "") or "rag"),
                fund_code=str(ticket.get("fund_code", "") or "") if str(ticket.get("fund_code", "")) in set(hit.get("fund_codes", []) or []) else "",
                value={"title": hit.get("title", ""), "text_for_llm": hit.get("text_for_llm", "")[:1200]},
                metadata={"retrieval_profile": "portfolio_trader", "doc_id": hit.get("doc_id", ""), "chunk_id": hit.get("chunk_id", "")},
                score=hit.get("score", hit.get("text_score")),
            )
        )
    missing = [
        MissingDataItem("rag_evidence", "missing", "No RAG hits after hard filters.", "Non-canonical evidence is empty; structured facts still drive the pack.")
    ] if result.get("missing_data") else []
    trace_ref = RagTraceRef(
        trace_id=str(result.get("trace_id", "") or "rag-empty"),
        path=relative_posix(result.get("trace_path", "") or "", agent_home) if result.get("trace_path") else "",
        profile="portfolio_trader",
        fallback_used=not bool(items),
        fallback_reason="no_hits_after_hard_filters" if not items else "",
    )
    return items, [trace_ref], missing


def missing_data_for_pack(ticket: dict[str, Any], portfolio_fact_item: LayeredContextItem | None, context: dict[str, Any], report_date: str) -> list[MissingDataItem]:
    missing: list[MissingDataItem] = []
    if portfolio_fact_item is None:
        missing.append(MissingDataItem("portfolio_position", "missing", "No matching fund in date-matched portfolio state.", "Position sizing and exposure facts are unavailable.", True))
    fund = context_fund(context, str(ticket.get("fund_code", "") or ""))
    if not fund:
        missing.append(MissingDataItem("llm_context_fund", "missing", "No matching fund in llm_context.", "Market and evidence context are unavailable.", False))
    if not (fund.get("recent_news") if fund else None):
        missing.append(MissingDataItem("fund_recent_news", "missing", "No recent fund news in llm_context.", "Long-text evidence relies on RAG or remains empty.", False))
    missing.append(
        MissingDataItem(
            f"official_nav_for_{report_date}",
            "pending",
            "Same-day official NAV is not known at decision time.",
            "Outcome scoring waits for later official NAV data.",
            False,
        )
    )
    return missing


def build_pack_for_ticket(
    *,
    agent_home: Path,
    report_date: str,
    generated_at: str,
    decision_cutoff: str,
    ticket: dict[str, Any],
    validated: dict[str, Any],
    portfolio: dict[str, Any],
    context: dict[str, Any],
    memory_export: dict[str, Any],
    root_sources: list[dict[str, Any]],
    portfolio_source_path: str,
    use_rag: bool,
) -> RetrievalPack:
    fund_code = str(ticket.get("fund_code", "") or "")
    p_fact = portfolio_fact(ticket, portfolio, generated_at, portfolio_source_path)
    canonical = [ticket_fact(ticket, report_date), validated_decision_fact(ticket, validated, report_date)]
    if p_fact is not None:
        canonical.insert(0, p_fact)
    canonical.extend(market_facts_from_context(ticket, context, report_date))
    adaptive, similar, anti = memory_items(ticket, memory_export, report_date, generated_at)
    rag_items, rag_refs, rag_missing = rag_noncanonical_evidence(agent_home, ticket, report_date, enabled=use_rag)
    long_text = long_text_evidence_from_context(ticket, context, report_date)
    if rag_items:
        long_text.extend(item for item in rag_items if item.layer == "long_text_evidence")
        anti.extend(item for item in rag_items if item.layer == "anti_pattern")
    missing = missing_data_for_pack(ticket, p_fact, context, report_date) + rag_missing
    pack = RetrievalPack(
        schema_version=SCHEMA_VERSION,
        pack_id=f"pack:{report_date}:{fund_code}:{ticket.get('action_verb')}:001",
        report_date=report_date,
        generated_at=generated_at,
        decision_cutoff=decision_cutoff,
        write_scope="shadow_only",
        non_executable=True,
        target={
            "fund_code": fund_code,
            "fund_name": ticket.get("fund_name", ""),
            "role": ticket.get("role", ""),
            "category": ticket.get("category", ""),
            "portfolio_bucket": ticket.get("portfolio_bucket", ""),
            "ticket_id": ticket.get("ticket_id", ""),
            "action_verb": ticket.get("action_verb", ""),
        },
        visibility=Visibility(
            include_execution=False,
            include_private_position_details=True,
            reason="Daily strategy reasoning can read current portfolio facts; execution-only records are excluded in Phase 2.",
        ),
        source_manifests=root_sources,
        raw_observation_refs=raw_observation_refs(ticket, context, report_date),
        canonical_facts=canonical,
        derived_signals=derived_signals_from_context(ticket, context, report_date),
        decision_history=decision_history_from_ticket(ticket, report_date),
        outcome_history=[],
        similar_cases=similar,
        anti_patterns=anti,
        adaptive_policies=adaptive,
        strategy_skill_candidates=[],
        long_text_evidence=long_text[:8],
        missing_data=missing,
        rag_trace_refs=rag_refs,
        audit={"builder": "scripts/build_layered_retrieval_pack.py", "builder_version": "phase2-shadow"},
    )
    pack.audit["trace_completeness_rate"] = pack.trace_completeness_rate()
    return pack


def summarize_packs(packs: list[RetrievalPack]) -> dict[str, Any]:
    trace_rates = [pack.trace_completeness_rate() for pack in packs]
    item_count = sum(len(pack.iter_items()) for pack in packs)
    return {
        "pack_count": len(packs),
        "canonical_fact_count": sum(len(pack.canonical_facts) for pack in packs),
        "derived_signal_count": sum(len(pack.derived_signals) for pack in packs),
        "long_text_evidence_count": sum(len(pack.long_text_evidence) for pack in packs),
        "similar_case_count": sum(len(pack.similar_cases) for pack in packs),
        "anti_pattern_count": sum(len(pack.anti_patterns) for pack in packs),
        "adaptive_policy_count": sum(len(pack.adaptive_policies) for pack in packs),
        "missing_data_count": sum(len(pack.missing_data) for pack in packs),
        "rag_trace_count": sum(len(pack.rag_trace_refs) for pack in packs),
        "trace_item_count": item_count,
        "trace_completeness_rate": round(sum(trace_rates) / len(trace_rates), 4) if trace_rates else 1.0,
        "no_future_violation_count": 0,
        "execution_included_count": sum(1 for pack in packs if pack.visibility.include_execution),
        "canonical_from_rag_count": sum(1 for pack in packs for item in pack.canonical_facts if item.source_kind.startswith("rag")),
    }


def build_retrieval_pack_artifact(agent_home: Path, report_date: str, *, generated_at: str | None = None, use_rag: bool = False, source_mode: str = "validated") -> RetrievalPackArtifact:
    action_artifact = action_ticket_artifact(agent_home, report_date, generated_at=generated_at, source_mode=source_mode)
    action_path = action_ticket_path(agent_home, report_date)
    validated_path = validated_advice_path(agent_home, report_date)
    portfolio_path, portfolio = load_portfolio_state_for_report(agent_home, report_date)
    context_path = llm_context_path(agent_home, report_date)
    evidence_path = evidence_index_path(agent_home, report_date)
    memory_path = long_memory_export_path(agent_home)
    validated = load_json_if_exists(validated_path)
    context = load_json_if_exists(context_path)
    memory_export = load_json_if_exists(memory_path)
    generated_at = generated_at or str(action_artifact.get("generated_at", "") or timestamp_now())
    decision_cutoff = decision_cutoff_for(report_date, generated_at, validated)
    root_sources = source_artifacts(agent_home, [action_path, validated_path, portfolio_path, context_path, evidence_path, memory_path])
    packs = [
        build_pack_for_ticket(
            agent_home=agent_home,
            report_date=report_date,
            generated_at=generated_at,
            decision_cutoff=decision_cutoff,
            ticket=ticket,
            validated=validated,
            portfolio=portfolio,
            context=context,
            memory_export=memory_export,
            root_sources=root_sources,
            portfolio_source_path=relative_posix(portfolio_path, agent_home) if portfolio_path.exists() else "",
            use_rag=use_rag,
        )
        for ticket in action_artifact.get("tickets", []) or []
    ]
    return RetrievalPackArtifact(
        schema_version=SCHEMA_VERSION,
        artifact_id=f"retrieval_packs:{report_date}",
        artifact_kind="layered_retrieval_pack_shadow",
        report_date=report_date,
        generated_at=generated_at,
        decision_cutoff=decision_cutoff,
        write_scope="shadow_only",
        non_executable=True,
        source_artifacts=root_sources,
        summary=summarize_packs(packs),
        packs=packs,
    )


def write_retrieval_pack_artifact(agent_home: Path, artifact: RetrievalPackArtifact) -> Path:
    path = retrieval_pack_path(agent_home, artifact.report_date)
    payload = artifact.to_dict()
    assert_refactor_write_allowed(path, payload, agent_home)
    dump_json(path, payload)
    return path


def run_builder(agent_home: Path, report_date: str, *, generated_at: str | None = None, use_rag: bool = False, source_mode: str = "validated") -> tuple[Path, RetrievalPackArtifact]:
    artifact = build_retrieval_pack_artifact(agent_home, report_date, generated_at=generated_at, use_rag=use_rag, source_mode=source_mode)
    path = write_retrieval_pack_artifact(agent_home, artifact)
    return path, artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build standalone non-executable layered retrieval packs from action tickets.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", required=True, help="Report date in YYYY-MM-DD.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp for deterministic tests.")
    parser.add_argument("--use-rag", action="store_true", help="Call current RAG retriever for non-canonical evidence.")
    parser.add_argument("--source-mode", choices=["validated", "native"], default="validated", help="Build missing action tickets from legacy validated advice or native seeds.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    path, artifact = run_builder(agent_home, report_date, generated_at=args.generated_at or None, use_rag=args.use_rag, source_mode=args.source_mode)
    print(f"wrote {len(artifact.packs)} retrieval packs: {relative_posix(path, agent_home)}")


if __name__ == "__main__":
    main()
