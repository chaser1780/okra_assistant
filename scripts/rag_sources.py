from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import closing
from datetime import date, datetime
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from common import (
    actual_trade_dir,
    committee_decision_bundle_path,
    llm_context_path,
    load_json,
    long_memory_db_path,
    portfolio_state_current_path,
    portfolio_state_snapshot_path,
    timestamp_now,
    validated_advice_path,
)
from rag_models import RagChunk, RagDocument, json_dumps, stable_sha256


SHANGHAI_END_OF_DAY = "T23:59:59+08:00"
ACTIVE_MEMORY_STATUSES = {"permanent", "strategic", "candidate"}
NEGATIVE_MEMORY_STATUSES = {"archived", "rejected"}
EXECUTION_SOURCE_KIND = "execution_sync"
EXECUTION_DOMAIN = "execution"
EXECUTION_VISIBILITY = "execution_only"
EXECUTION_LEARNING_SCOPE = "execution_only"


@dataclass(slots=True)
class RagSourceBundle:
    domain: str
    source_kind: str
    source_path: str
    as_of_date: str = ""
    documents: list[RagDocument] = field(default_factory=list)
    chunks: list[RagChunk] = field(default_factory=list)
    missing_data: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    skipped_reason: str = ""
    scope_key: str = ""

    @property
    def status(self) -> str:
        if self.errors:
            return "error"
        if self.missing_data:
            return "missing"
        if self.skipped_reason:
            return "skipped"
        return "ok"

    def summary(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "source_kind": self.source_kind,
            "source_path": self.source_path,
            "scope_key": self.scope_key or build_scope_key(self.as_of_date, self.domain, self.source_kind),
            "as_of_date": self.as_of_date,
            "status": self.status,
            "doc_count": len(self.documents),
            "chunk_count": len(self.chunks),
            "missing_count": len(self.missing_data),
            "error_count": len(self.errors),
            "skipped_reason": self.skipped_reason,
        }


def build_scope_key(as_of_date: str | None, domain: str, source_kind: str) -> str:
    date_part = str(as_of_date or "global")
    return f"{date_part}:{domain}:{source_kind}"


def canonical_scope_key(source_kind: str, as_of_date: str | None = None, *, source_path: str = "") -> str:
    if source_kind in {"llm_context", "evidence_item"}:
        return build_scope_key(as_of_date, "context", source_kind)
    if source_kind in {"validated_advice", "committee_bundle"}:
        return build_scope_key(as_of_date, "decision", source_kind)
    if source_kind == "portfolio_state":
        scope_date = as_of_date if source_path and not source_path.endswith("current.json") and as_of_date else "current"
        return build_scope_key(scope_date, "portfolio", "portfolio_state")
    if source_kind == "long_memory":
        return build_scope_key(None, "long_memory", "long_memory")
    if source_kind == EXECUTION_SOURCE_KIND:
        return build_scope_key(as_of_date or "global", EXECUTION_DOMAIN, EXECUTION_SOURCE_KIND)
    return build_scope_key(as_of_date, source_kind, source_kind)


def _hash_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def _doc_id(source_kind: str, source_record_id: str) -> str:
    return f"ragdoc:{source_kind}:{_hash_text(source_record_id)}"


def _chunk_id(doc_id: str, index: int = 0) -> str:
    return f"{doc_id}:chunk:{index}"


def _source_path_text(agent_home: Path, path: Path) -> str:
    try:
        return path.relative_to(agent_home).as_posix()
    except ValueError:
        return str(path)


def _date_or_default(value: Any, fallback: str | None = None) -> str:
    text = str(value or "").strip()
    if text:
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            pass
    if fallback:
        return date.fromisoformat(str(fallback)[:10]).isoformat()
    return datetime.now().astimezone().date().isoformat()


def _timestamp_or_inferred(value: Any, fallback_date: str, metadata: dict[str, Any], field: str = "available_from") -> str:
    text = str(value or "").strip()
    if text:
        if "T" not in text and len(text) == 10:
            metadata[f"{field}_inferred"] = True
            return f"{text}{SHANGHAI_END_OF_DAY}"
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
            return text
        except ValueError:
            pass
    metadata[f"{field}_inferred"] = True
    return f"{fallback_date}{SHANGHAI_END_OF_DAY}"


def _long_memory_available_from(item: dict[str, Any], fallback_date: str, metadata: dict[str, Any]) -> str:
    approved_at = str(item.get("approved_at", "") or "").strip()
    if approved_at:
        return _timestamp_or_inferred(approved_at, fallback_date, metadata)
    valid_from = str(item.get("valid_from", "") or "").strip()
    if valid_from:
        return _timestamp_or_inferred(valid_from, fallback_date, metadata)
    return _timestamp_or_inferred(item.get("updated_at") or item.get("created_at"), fallback_date, metadata)


def _safe_json_loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def _compact_value(value: Any, *, max_length: int = 520) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, (int, float, bool)):
        text = str(value)
    elif isinstance(value, list):
        parts = [_compact_value(item, max_length=160) for item in value[:8]]
        text = "；".join(part for part in parts if part)
    elif isinstance(value, dict):
        parts = []
        for key, item in list(value.items())[:12]:
            compact = _compact_value(item, max_length=120)
            if compact:
                parts.append(f"{key}: {compact}")
        text = "；".join(parts)
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) > max_length:
        return f"{text[:max_length].rstrip()}..."
    return text


def _make_chunk(document: RagDocument, text_for_embedding: str, text_for_llm: str, index: int = 0) -> RagChunk:
    return RagChunk(
        chunk_id=_chunk_id(document.doc_id, index),
        doc_id=document.doc_id,
        chunk_index=index,
        text_for_embedding=text_for_embedding,
        text_for_llm=text_for_llm,
        token_estimate=max(1, len(text_for_embedding) // 2),
        metadata={
            "source_kind": document.source_kind,
            "source_record_id": document.source_record_id,
            "as_of_date": document.as_of_date,
            "fund_codes": document.fund_codes,
            "visibility": document.visibility,
        },
    )


def _bundle_missing(agent_home: Path, *, domain: str, source_kind: str, path: Path, as_of_date: str = "", reason: str = "missing_source") -> RagSourceBundle:
    source_path = _source_path_text(agent_home, path)
    return RagSourceBundle(
        domain=domain,
        source_kind=source_kind,
        source_path=source_path,
        as_of_date=as_of_date,
        missing_data=[{"source_kind": source_kind, "source_path": source_path, "reason": reason}],
        scope_key=canonical_scope_key(source_kind, as_of_date, source_path=source_path),
    )


def collect_long_memory_documents(agent_home: Path, report_date: str | None = None) -> RagSourceBundle:
    path = long_memory_db_path(agent_home)
    source_path = _source_path_text(agent_home, path)
    bundle = RagSourceBundle(
        domain="long_memory",
        source_kind="long_memory",
        source_path=source_path,
        as_of_date=report_date or "",
        scope_key=build_scope_key(None, "long_memory", "long_memory"),
    )
    if not path.exists():
        bundle.missing_data.append({"source_kind": "long_memory", "source_path": source_path, "reason": "missing_source"})
        return bundle

    try:
        with closing(sqlite3.connect(path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM memory_records ORDER BY updated_at DESC, memory_id").fetchall()
    except sqlite3.Error as exc:
        bundle.errors.append({"source_kind": "long_memory", "source_path": source_path, "error": str(exc)})
        return bundle

    for row in rows:
        item = dict(row)
        metadata_json = _safe_json_loads(item.get("metadata_json"), {})
        evidence_refs = _safe_json_loads(item.get("evidence_refs_json"), [])
        status = str(item.get("status", "") or "")
        source_record_id = str(item.get("memory_id", "") or "")
        fallback_date = _date_or_default(item.get("valid_from") or item.get("updated_at") or item.get("created_at") or report_date)
        metadata = {
            **metadata_json,
            "memory_type": item.get("memory_type", ""),
            "priority": item.get("priority", ""),
            "confidence": item.get("confidence", 0.0),
            "support_count": item.get("support_count", 0),
            "contradiction_count": item.get("contradiction_count", 0),
            "horizon_bucket": item.get("horizon_bucket", ""),
            "source_agent": item.get("source_agent", ""),
            "source_analysis_quality": item.get("source_analysis_quality", ""),
        }
        superseded_by = metadata_json.get("superseded_by") or metadata_json.get("superseded_by_id")
        if superseded_by:
            metadata["superseded_by"] = superseded_by
        visibility = "review_only" if status in NEGATIVE_MEMORY_STATUSES or superseded_by else "default"
        learning_scope = str(metadata_json.get("learning_scope", "") or "")
        if item.get("domain") == EXECUTION_DOMAIN or metadata_json.get("visibility") == EXECUTION_VISIBILITY:
            learning_scope = EXECUTION_LEARNING_SCOPE
            visibility = EXECUTION_VISIBILITY
            metadata["learning_scope"] = EXECUTION_LEARNING_SCOPE
            metadata["visibility"] = EXECUTION_VISIBILITY
        source_tier = {
            "permanent": "memory_approved",
            "strategic": "memory_strategic",
            "candidate": "memory_candidate",
            "archived": "negative_memory",
            "rejected": "negative_memory",
        }.get(status, "memory_candidate")
        fund_codes = metadata_json.get("fund_codes", [])
        if not fund_codes and item.get("domain") == "fund" and item.get("entity_key"):
            fund_codes = [str(item.get("entity_key"))]
        available_from = _long_memory_available_from(item, fallback_date, metadata)
        doc = RagDocument(
            doc_id=_doc_id("long_memory", source_record_id),
            source_kind="long_memory",
            source_path=source_path,
            source_record_id=source_record_id,
            title=str(item.get("title", "") or source_record_id),
            summary=str(item.get("text", "") or item.get("title", "") or source_record_id),
            as_of_date=fallback_date,
            available_from=available_from,
            domain=str(item.get("domain", "") or "memory"),
            source_tier=source_tier,
            visibility=visibility,
            entity_type=str(item.get("domain", "") or ""),
            entity_id=str(item.get("entity_key", "") or ""),
            fund_codes=fund_codes,
            status=status,
            valid_from=str(item.get("valid_from", "") or ""),
            valid_until=str(item.get("valid_until", "") or ""),
            learning_scope=learning_scope,
            is_negative_example=status in NEGATIVE_MEMORY_STATUSES,
            payload={"record": {key: value for key, value in item.items() if not key.endswith("_json")}, "evidence_refs": evidence_refs},
            metadata=metadata,
        )
        text = f"长期记忆：{doc.title}。内容：{doc.summary}。状态：{status}。领域：{doc.domain}。实体：{doc.entity_id}"
        bundle.documents.append(doc)
        bundle.chunks.append(_make_chunk(doc, text, doc.summary))
    return bundle


def iter_long_memory_documents(agent_home: Path, date: str | None = None) -> list[RagDocument]:
    return collect_long_memory_documents(agent_home, date).documents


def collect_portfolio_documents(agent_home: Path, report_date: str | None = None) -> RagSourceBundle:
    if report_date:
        snapshot = portfolio_state_snapshot_path(agent_home, report_date)
        path = snapshot if snapshot.exists() else portfolio_state_current_path(agent_home)
    else:
        path = portfolio_state_current_path(agent_home)
    if not path.exists():
        return _bundle_missing(agent_home, domain="portfolio_state", source_kind="portfolio_state", path=path, as_of_date=report_date or "")
    payload = load_json(path)
    if not isinstance(payload, dict):
        return _bundle_missing(agent_home, domain="portfolio_state", source_kind="portfolio_state", path=path, as_of_date=report_date or "", reason="invalid_payload")
    source_path = _source_path_text(agent_home, path)
    as_of_date = _date_or_default(payload.get("as_of_date") or report_date)
    source_tier = "structured_snapshot" if path.name != "current.json" else "structured_current"
    metadata: dict[str, Any] = {"source_name": "portfolio_state", "portfolio_name": payload.get("portfolio_name", "")}
    available_from = _timestamp_or_inferred(payload.get("generated_at") or payload.get("updated_at"), as_of_date, metadata)
    bundle = RagSourceBundle(
        domain="portfolio_state",
        source_kind="portfolio_state",
        source_path=source_path,
        as_of_date=as_of_date,
        scope_key=build_scope_key(report_date if path.name != "current.json" and report_date else "current", "portfolio", "portfolio_state"),
    )
    funds = list(payload.get("funds", []) or [])
    portfolio_summary = {
        "portfolio_name": payload.get("portfolio_name", ""),
        "as_of_date": as_of_date,
        "total_value": payload.get("total_value", 0.0),
        "holding_pnl": payload.get("holding_pnl", 0.0),
        "fund_count": len(funds),
    }
    doc = RagDocument(
        doc_id=_doc_id("portfolio_state", f"{source_path}:portfolio"),
        source_kind="portfolio_state",
        source_path=source_path,
        source_record_id="portfolio",
        title=f"组合持仓：{payload.get('portfolio_name', 'portfolio')}",
        summary=f"组合总市值 {portfolio_summary['total_value']}，持仓收益 {portfolio_summary['holding_pnl']}，基金数量 {len(funds)}。",
        as_of_date=as_of_date,
        available_from=available_from,
        domain="portfolio",
        source_tier=source_tier,
        visibility="default",
        entity_type="portfolio",
        entity_id="portfolio",
        payload=portfolio_summary,
        metadata=metadata,
    )
    bundle.documents.append(doc)
    bundle.chunks.append(_make_chunk(doc, f"组合持仓摘要：{doc.summary}", doc.summary))
    for fund in funds:
        if not isinstance(fund, dict):
            continue
        fund_code = str(fund.get("fund_code", "") or fund.get("code", "") or "")
        fund_name = str(fund.get("fund_name", "") or fund.get("name", "") or fund_code)
        fund_payload = dict(fund)
        fund_summary = (
            f"{fund_name} 当前市值 {fund.get('current_value', 0.0)}，持仓收益 {fund.get('holding_pnl', 0.0)}，"
            f"收益率 {fund.get('holding_return_pct', 0.0)}%，角色 {fund.get('role', '')}，风格 {fund.get('style_group', '')}。"
        )
        fund_doc = RagDocument(
            doc_id=_doc_id("portfolio_state", f"{source_path}:fund:{fund_code or fund_name}"),
            source_kind="portfolio_state",
            source_path=source_path,
            source_record_id=f"fund:{fund_code or fund_name}",
            title=f"持仓基金：{fund_name}",
            summary=fund_summary,
            as_of_date=as_of_date,
            available_from=available_from,
            domain="fund",
            source_tier=source_tier,
            visibility="default",
            entity_type="fund",
            entity_id=fund_code,
            fund_codes=[fund_code] if fund_code else [],
            payload=fund_payload,
            metadata={"role": fund.get("role", ""), "style_group": fund.get("style_group", ""), "source_name": "portfolio_state"},
        )
        bundle.documents.append(fund_doc)
        bundle.chunks.append(_make_chunk(fund_doc, f"基金持仓摘要：{fund_summary}", fund_summary))
    return bundle


def iter_portfolio_documents(agent_home: Path, date: str | None = None) -> list[RagDocument]:
    return collect_portfolio_documents(agent_home, date).documents


def _context_available_from(payload: dict[str, Any], report_date: str, metadata: dict[str, Any]) -> str:
    return _timestamp_or_inferred(payload.get("generated_at") or payload.get("retrieved_at") or payload.get("updated_at"), report_date, metadata)


def _section_document(
    *,
    source_kind: str,
    source_path: str,
    source_record_id: str,
    title: str,
    value: Any,
    as_of_date: str,
    available_from: str,
    domain: str,
    source_tier: str,
    metadata: dict[str, Any] | None = None,
    fund_codes: list[str] | None = None,
    entity_id: str = "",
) -> tuple[RagDocument, RagChunk]:
    summary = _compact_value(value)
    doc = RagDocument(
        doc_id=_doc_id(source_kind, f"{source_path}:{source_record_id}"),
        source_kind=source_kind,
        source_path=source_path,
        source_record_id=source_record_id,
        title=title,
        summary=summary or title,
        as_of_date=as_of_date,
        available_from=available_from,
        domain=domain,
        source_tier=source_tier,
        visibility="default",
        entity_type="fund" if fund_codes else domain,
        entity_id=entity_id,
        fund_codes=fund_codes or [],
        payload=value if isinstance(value, dict) else {"value": value},
        metadata=metadata or {},
    )
    text = f"{title}：{summary}"
    return doc, _make_chunk(doc, text, summary or title)


def collect_llm_context_documents(agent_home: Path, report_date: str | None) -> RagSourceBundle:
    if not report_date:
        return RagSourceBundle(
            domain="llm_context",
            source_kind="llm_context",
            source_path="db/llm_context",
            skipped_reason="date_required",
            scope_key=build_scope_key("", "llm_context", "llm_context"),
        )
    path = llm_context_path(agent_home, report_date)
    if not path.exists():
        return _bundle_missing(agent_home, domain="llm_context", source_kind="llm_context", path=path, as_of_date=report_date)
    payload = load_json(path)
    if not isinstance(payload, dict):
        return _bundle_missing(agent_home, domain="llm_context", source_kind="llm_context", path=path, as_of_date=report_date, reason="invalid_payload")
    source_path = _source_path_text(agent_home, path)
    as_of_date = _date_or_default(payload.get("analysis_date") or report_date)
    metadata = {"mode": payload.get("mode", "")}
    available_from = _context_available_from(payload, as_of_date, metadata)
    bundle = RagSourceBundle(
        domain="llm_context",
        source_kind="llm_context",
        source_path=source_path,
        as_of_date=as_of_date,
        scope_key=build_scope_key(as_of_date, "context", "llm_context"),
    )
    for section, domain in (
        ("portfolio_summary", "portfolio"),
        ("exposure_summary", "portfolio"),
        ("constraints", "portfolio"),
        ("memory_digest", "memory"),
        ("news_digest", "market"),
        ("sentiment_digest", "market"),
    ):
        value = payload.get(section)
        if value:
            doc, chunk = _section_document(
                source_kind="llm_context",
                source_path=source_path,
                source_record_id=section,
                title=f"LLM 上下文：{section}",
                value=value,
                as_of_date=as_of_date,
                available_from=available_from,
                domain=domain,
                source_tier="daily_context",
                metadata={"section": section, **metadata},
            )
            bundle.documents.append(doc)
            bundle.chunks.append(chunk)
    for index, fund in enumerate(payload.get("funds", []) or []):
        if not isinstance(fund, dict):
            continue
        fund_code = str(fund.get("fund_code", "") or "")
        fund_name = str(fund.get("fund_name", "") or fund_code)
        doc, chunk = _section_document(
            source_kind="llm_context",
            source_path=source_path,
            source_record_id=f"fund:{fund_code or index}",
            title=f"LLM 上下文基金：{fund_name}",
            value=fund,
            as_of_date=as_of_date,
            available_from=available_from,
            domain="fund",
            source_tier="daily_context",
            metadata={"section": "funds", "role": fund.get("role", ""), "style_group": fund.get("style_group", "")},
            fund_codes=[fund_code] if fund_code else [],
            entity_id=fund_code,
        )
        bundle.documents.append(doc)
        bundle.chunks.append(chunk)
    for index, item in enumerate(payload.get("event_risks", []) or []):
        if not isinstance(item, dict):
            continue
        item_meta = {
            "section": "event_risks",
            "published_at": item.get("published_at", ""),
            "url": item.get("url", "") or item.get("source_url", ""),
            "source_role": item.get("source_role", ""),
            "evidence_type": item.get("evidence_type", ""),
            "risk_level": item.get("risk_level", "") or item.get("severity", ""),
        }
        doc, chunk = _section_document(
            source_kind="llm_context",
            source_path=source_path,
            source_record_id=f"event_risk:{index}:{item.get('title', '')}",
            title=f"事件风险：{item.get('title', '') or index}",
            value=item,
            as_of_date=as_of_date,
            available_from=_timestamp_or_inferred(item.get("published_at") or item.get("retrieved_at"), as_of_date, item_meta),
            domain="risk",
            source_tier=str(item.get("source_tier", "") or "news_digest"),
            metadata=item_meta,
            fund_codes=[str(item.get("fund_code"))] if item.get("fund_code") and item.get("fund_code") != "GLOBAL" else [],
            entity_id=str(item.get("fund_code", "") or ""),
        )
        bundle.documents.append(doc)
        bundle.chunks.append(chunk)
    evidence_bundle = collect_evidence_item_documents(agent_home, report_date, payload=payload)
    bundle.documents.extend(evidence_bundle.documents)
    bundle.chunks.extend(evidence_bundle.chunks)
    bundle.missing_data.extend(evidence_bundle.missing_data)
    bundle.errors.extend(evidence_bundle.errors)
    return bundle


def iter_llm_context_documents(agent_home: Path, date: str) -> list[RagDocument]:
    return [doc for doc in collect_llm_context_documents(agent_home, date).documents if doc.source_kind == "llm_context"]


def collect_evidence_item_documents(agent_home: Path, report_date: str | None, payload: dict[str, Any] | None = None) -> RagSourceBundle:
    if not report_date:
        return RagSourceBundle(domain="evidence_item", source_kind="evidence_item", source_path="db/llm_context", skipped_reason="date_required")
    context = payload
    path = llm_context_path(agent_home, report_date)
    if context is None:
        if not path.exists():
            return _bundle_missing(agent_home, domain="evidence_item", source_kind="evidence_item", path=path, as_of_date=report_date)
        loaded = load_json(path)
        context = loaded if isinstance(loaded, dict) else {}
    source_path = _source_path_text(agent_home, path)
    as_of_date = _date_or_default(context.get("analysis_date") or report_date)
    bundle = RagSourceBundle(
        domain="evidence_item",
        source_kind="evidence_item",
        source_path=source_path,
        as_of_date=as_of_date,
        scope_key=build_scope_key(as_of_date, "context", "evidence_item"),
    )
    for index, item in enumerate(context.get("evidence_items", []) or []):
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("entity_id", "") or item.get("fund_code", "") or "")
        fund_codes = [entity_id] if item.get("entity_type") == "fund" and entity_id else []
        metadata = {
            "source_role": item.get("source_role", ""),
            "source_tier": item.get("source_tier", ""),
            "evidence_type": item.get("evidence_type", ""),
            "mapping_mode": item.get("mapping_mode", ""),
            "provider": item.get("provider", ""),
            "published_at": item.get("published_at", ""),
            "retrieved_at": item.get("retrieved_at", ""),
            "url": item.get("url", "") or item.get("source_url", ""),
            "canonical_url": item.get("canonical_url", ""),
            "freshness_status": item.get("freshness_status", ""),
            "stale": item.get("stale", False),
            "source_health": item.get("source_health", {}),
        }
        item_as_of = _date_or_default(item.get("as_of") or item.get("published_at") or as_of_date, as_of_date)
        available_from = _timestamp_or_inferred(item.get("retrieved_at") or item.get("published_at"), item_as_of, metadata)
        title = str(item.get("source_title", "") or item.get("title", "") or item.get("evidence_id", "") or f"evidence {index}")
        summary = str(item.get("summary", "") or title)
        doc = RagDocument(
            doc_id=_doc_id("evidence_item", str(item.get("evidence_id", "") or f"{source_path}:{index}:{title}")),
            source_kind="evidence_item",
            source_path=source_path,
            source_record_id=str(item.get("evidence_id", "") or f"evidence:{index}"),
            title=title,
            summary=summary,
            as_of_date=item_as_of,
            published_at=str(item.get("published_at", "") or ""),
            available_from=available_from,
            domain="fund" if fund_codes else "market",
            source_tier=str(item.get("source_tier", "") or "daily_evidence"),
            visibility="default",
            entity_type=str(item.get("entity_type", "") or ""),
            entity_id=entity_id,
            fund_codes=fund_codes,
            payload={
                "numeric_payload": item.get("numeric_payload", {}),
                "raw_payload": item.get("raw_payload", {}),
                "summary": summary,
            },
            metadata=metadata,
        )
        text = f"证据：{title}。摘要：{summary}。类型：{metadata['evidence_type']}。映射：{metadata['mapping_mode']}"
        bundle.documents.append(doc)
        bundle.chunks.append(_make_chunk(doc, text, summary))
    return bundle


def iter_evidence_item_documents(agent_home: Path, date: str) -> list[RagDocument]:
    return collect_evidence_item_documents(agent_home, date).documents


def collect_validated_advice_documents(agent_home: Path, report_date: str | None) -> RagSourceBundle:
    if not report_date:
        return RagSourceBundle(domain="validated_advice", source_kind="validated_advice", source_path="db/validated_advice", skipped_reason="date_required")
    path = validated_advice_path(agent_home, report_date)
    if not path.exists():
        return _bundle_missing(agent_home, domain="validated_advice", source_kind="validated_advice", path=path, as_of_date=report_date)
    payload = load_json(path)
    if not isinstance(payload, dict):
        return _bundle_missing(agent_home, domain="validated_advice", source_kind="validated_advice", path=path, as_of_date=report_date, reason="invalid_payload")
    source_path = _source_path_text(agent_home, path)
    as_of_date = _date_or_default(payload.get("report_date") or report_date)
    metadata = {"advice_mode": payload.get("advice_mode", ""), "decision_mode": payload.get("decision_mode", "")}
    available_from = _context_available_from(payload, as_of_date, metadata)
    bundle = RagSourceBundle(
        domain="validated_advice",
        source_kind="validated_advice",
        source_path=source_path,
        as_of_date=as_of_date,
        scope_key=build_scope_key(as_of_date, "decision", "validated_advice"),
    )
    section_specs: list[tuple[str, str, str]] = [
        ("market_view", "decision", "market_view"),
        ("optimization_summary", "decision", "optimization_summary"),
    ]
    for section, domain, record_id in section_specs:
        if payload.get(section):
            doc, chunk = _section_document(
                source_kind="validated_advice",
                source_path=source_path,
                source_record_id=record_id,
                title=f"已验证建议：{section}",
                value=payload.get(section),
                as_of_date=as_of_date,
                available_from=available_from,
                domain=domain,
                source_tier="decision_trace",
                metadata={"section": section, **metadata},
            )
            bundle.documents.append(doc)
            bundle.chunks.append(chunk)
    for index, observation in enumerate(payload.get("cross_fund_observations", []) or []):
        doc, chunk = _section_document(
            source_kind="validated_advice",
            source_path=source_path,
            source_record_id=f"cross_fund_observation:{index}",
            title=f"跨基金观察：{index + 1}",
            value={"observation": observation},
            as_of_date=as_of_date,
            available_from=available_from,
            domain="decision",
            source_tier="decision_trace",
            metadata={"section": "cross_fund_observations", **metadata},
        )
        bundle.documents.append(doc)
        bundle.chunks.append(chunk)
    for section in ("tactical_actions", "dca_actions", "hold_actions"):
        for index, action in enumerate(payload.get(section, []) or []):
            if not isinstance(action, dict):
                continue
            fund_code = str(action.get("fund_code", "") or "")
            fund_name = str(action.get("fund_name", "") or fund_code)
            title = f"已验证动作：{fund_name} {action.get('validated_action', action.get('action', ''))}"
            doc, chunk = _section_document(
                source_kind="validated_advice",
                source_path=source_path,
                source_record_id=f"{section}:{fund_code or index}",
                title=title,
                value=action,
                as_of_date=as_of_date,
                available_from=available_from,
                domain="fund" if fund_code else "decision",
                source_tier="decision_trace",
                metadata={"section": section, "validation_status": action.get("validation_status", ""), **metadata},
                fund_codes=[fund_code] if fund_code else [],
                entity_id=fund_code,
            )
            bundle.documents.append(doc)
            bundle.chunks.append(chunk)
    return bundle


def iter_validated_advice_documents(agent_home: Path, date: str) -> list[RagDocument]:
    return collect_validated_advice_documents(agent_home, date).documents


def collect_committee_bundle_documents(agent_home: Path, report_date: str | None) -> RagSourceBundle:
    if not report_date:
        return RagSourceBundle(domain="committee_bundle", source_kind="committee_bundle", source_path="db/committee_decision_bundle", skipped_reason="date_required")
    path = committee_decision_bundle_path(agent_home, report_date)
    if not path.exists():
        return _bundle_missing(agent_home, domain="committee_bundle", source_kind="committee_bundle", path=path, as_of_date=report_date)
    payload = load_json(path)
    if not isinstance(payload, dict):
        return _bundle_missing(agent_home, domain="committee_bundle", source_kind="committee_bundle", path=path, as_of_date=report_date, reason="invalid_payload")
    source_path = _source_path_text(agent_home, path)
    as_of_date = _date_or_default(payload.get("report_date") or report_date)
    metadata = {
        "decision_mode": payload.get("decision_mode", ""),
        "decision_source": payload.get("decision_source", ""),
        "degradation_mode": payload.get("degradation_mode", ""),
        "execution_eligible": payload.get("execution_eligible", False),
        "committee_confidence": payload.get("committee_confidence", ""),
    }
    available_from = _context_available_from(payload, as_of_date, metadata)
    bundle = RagSourceBundle(
        domain="committee_bundle",
        source_kind="committee_bundle",
        source_path=source_path,
        as_of_date=as_of_date,
        scope_key=build_scope_key(as_of_date, "decision", "committee_bundle"),
    )
    summary_value = {key: payload.get(key) for key in ("decision_mode", "decision_source", "degradation_mode", "execution_eligible", "committee_confidence", "manager_order", "notes") if key in payload}
    doc, chunk = _section_document(
        source_kind="committee_bundle",
        source_path=source_path,
        source_record_id="bundle_summary",
        title="委员会决策包摘要",
        value=summary_value,
        as_of_date=as_of_date,
        available_from=available_from,
        domain="decision",
        source_tier="decision_trace",
        metadata=metadata,
    )
    bundle.documents.append(doc)
    bundle.chunks.append(chunk)
    for index, decision in enumerate(payload.get("fund_decisions", []) or []):
        if not isinstance(decision, dict):
            continue
        fund_code = str(decision.get("fund_code", "") or "")
        fund_name = str(decision.get("fund_name", "") or fund_code)
        doc, chunk = _section_document(
            source_kind="committee_bundle",
            source_path=source_path,
            source_record_id=f"fund_decision:{fund_code or index}",
            title=f"委员会基金决策：{fund_name} {decision.get('proposed_action', '')}",
            value=decision,
            as_of_date=as_of_date,
            available_from=available_from,
            domain="decision",
            source_tier="decision_trace",
            metadata={"section": "fund_decisions", **metadata},
            fund_codes=[fund_code] if fund_code else [],
            entity_id=fund_code,
        )
        bundle.documents.append(doc)
        bundle.chunks.append(chunk)
    return bundle


def iter_committee_bundle_documents(agent_home: Path, date: str) -> list[RagDocument]:
    return collect_committee_bundle_documents(agent_home, date).documents


def _execution_sync_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "execution_sync"


def _execution_metadata(kind: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = {
        "source_kind": EXECUTION_SOURCE_KIND,
        "execution_record_kind": kind,
        "learning_scope": EXECUTION_LEARNING_SCOPE,
        "visibility": EXECUTION_VISIBILITY,
        "redaction": "structured_summary_only",
    }
    if extra:
        metadata.update(extra)
    return metadata


def _execution_doc(
    *,
    agent_home: Path,
    path: Path,
    record_kind: str,
    source_record_id: str,
    title: str,
    summary: str,
    as_of_date: str,
    available_from: str,
    entity_type: str = "",
    entity_id: str = "",
    fund_codes: list[str] | None = None,
    status: str = "",
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RagDocument:
    source_path = _source_path_text(agent_home, path)
    return RagDocument(
        doc_id=_doc_id(EXECUTION_SOURCE_KIND, f"{source_path}:{source_record_id}"),
        source_kind=EXECUTION_SOURCE_KIND,
        source_path=source_path,
        source_record_id=source_record_id,
        title=title,
        summary=summary,
        as_of_date=as_of_date,
        available_from=available_from,
        domain=EXECUTION_DOMAIN,
        source_tier="execution_structured_summary",
        visibility=EXECUTION_VISIBILITY,
        entity_type=entity_type,
        entity_id=entity_id,
        fund_codes=fund_codes or [],
        status=status,
        learning_scope=EXECUTION_LEARNING_SCOPE,
        payload=payload or {},
        metadata=_execution_metadata(record_kind, metadata),
    )


def _execution_available_from(item: dict[str, Any], fallback_date: str, metadata: dict[str, Any]) -> str:
    return _timestamp_or_inferred(
        item.get("updated_at") or item.get("created_at") or item.get("generated_at"),
        fallback_date,
        metadata,
    )


def _trade_summary(item: dict[str, Any]) -> str:
    operation = str(item.get("operation_type", "") or "trade")
    fund_name = str(item.get("fund_name") or item.get("out_fund_name") or item.get("in_fund_name") or item.get("fund_code") or item.get("out_fund_code") or "fund")
    amount = item.get("amount", item.get("out_amount", ""))
    status = str(item.get("status", "") or "")
    deviation = item.get("execution_deviation", {}) if isinstance(item.get("execution_deviation"), dict) else {}
    deviation_label = deviation.get("label") or deviation.get("type") or "matched_or_unlinked"
    confirm = item.get("confirm_date") or item.get("out_confirm_date") or item.get("in_confirm_date") or ""
    settlement = item.get("settlement_date", "")
    parts = [
        f"Execution trade {operation} {fund_name}",
        f"amount {amount}",
        f"status {status}",
        f"deviation {deviation_label}",
    ]
    if confirm:
        parts.append(f"confirm {confirm}")
    if settlement:
        parts.append(f"settlement {settlement}")
    return "; ".join(part for part in parts if part)


def _safe_trade_payload(item: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "trade_id",
        "conversion_id",
        "operation_type",
        "trade_date",
        "effective_trade_date",
        "fund_code",
        "fund_name",
        "amount",
        "out_fund_code",
        "out_fund_name",
        "out_amount",
        "in_fund_code",
        "in_fund_name",
        "in_amount",
        "status",
        "confirm_date",
        "out_confirm_date",
        "in_confirm_date",
        "settlement_date",
        "linked_suggestion_id",
        "linked_advice_date",
        "execution_deviation",
    )
    return {key: item.get(key) for key in allowed if key in item}


def _fund_codes_from_trade(item: dict[str, Any]) -> list[str]:
    codes = []
    for key in ("fund_code", "out_fund_code", "in_fund_code"):
        value = str(item.get(key, "") or "").strip()
        if value and value not in codes:
            codes.append(value)
    return codes


def _collect_actual_trade_documents(agent_home: Path, bundle: RagSourceBundle) -> None:
    base = actual_trade_dir(agent_home)
    if not base.exists():
        return
    for path in sorted(base.glob("*.json")):
        payload = load_json(path)
        if not isinstance(payload, dict):
            continue
        fallback_date = _date_or_default(payload.get("trade_date") or path.stem[:10] or bundle.as_of_date)
        for index, item in enumerate(payload.get("items", []) or []):
            if not isinstance(item, dict):
                continue
            trade_date = _date_or_default(item.get("trade_date") or payload.get("trade_date") or fallback_date, fallback_date)
            metadata = {"source_file_kind": "actual_trades"}
            available_from = _execution_available_from(item, trade_date, metadata)
            record_id = str(item.get("trade_id") or item.get("conversion_id") or f"{path.stem}:{index}")
            fund_codes = _fund_codes_from_trade(item)
            doc = _execution_doc(
                agent_home=agent_home,
                path=path,
                record_kind="actual_trade",
                source_record_id=f"actual_trade:{record_id}",
                title=f"Execution actual trade: {item.get('operation_type', 'trade')} {item.get('fund_name') or item.get('fund_code') or record_id}",
                summary=_trade_summary(item),
                as_of_date=trade_date,
                available_from=available_from,
                entity_type="fund" if fund_codes else "execution",
                entity_id=fund_codes[0] if fund_codes else record_id,
                fund_codes=fund_codes,
                status=str(item.get("status", "") or ""),
                payload=_safe_trade_payload(item),
                metadata=metadata,
            )
            bundle.documents.append(doc)
            bundle.chunks.append(_make_chunk(doc, f"Execution actual trade summary: {doc.summary}", doc.summary))


def _collect_pending_confirmation_documents(agent_home: Path, bundle: RagSourceBundle) -> None:
    path = _execution_sync_dir(agent_home) / "pending_confirmations.json"
    if not path.exists():
        return
    payload = load_json(path)
    if not isinstance(payload, dict):
        return
    fallback_date = _date_or_default(payload.get("updated_at") or bundle.as_of_date)
    for index, item in enumerate(payload.get("items", []) or []):
        if not isinstance(item, dict):
            continue
        trade_date = _date_or_default(item.get("trade_date") or item.get("confirm_date") or item.get("settlement_date") or fallback_date, fallback_date)
        metadata = {"source_file_kind": "pending_confirmations", "pending_list_updated_at": payload.get("updated_at", "")}
        available_from = _execution_available_from(item, trade_date, metadata)
        record_id = str(item.get("trade_id") or item.get("conversion_id") or f"pending:{index}")
        fund_codes = _fund_codes_from_trade(item)
        doc = _execution_doc(
            agent_home=agent_home,
            path=path,
            record_kind="pending_confirmation",
            source_record_id=f"pending_confirmation:{record_id}",
            title=f"Execution pending confirmation: {item.get('operation_type', 'trade')} {item.get('fund_name') or item.get('fund_code') or record_id}",
            summary=_trade_summary(item),
            as_of_date=trade_date,
            available_from=available_from,
            entity_type="fund" if fund_codes else "execution",
            entity_id=fund_codes[0] if fund_codes else record_id,
            fund_codes=fund_codes,
            status=str(item.get("status", "") or "pending"),
            payload=_safe_trade_payload(item),
            metadata=metadata,
        )
        bundle.documents.append(doc)
        bundle.chunks.append(_make_chunk(doc, f"Execution pending confirmation summary: {doc.summary}", doc.summary))


def _safe_position_payload(item: dict[str, Any]) -> dict[str, Any]:
    allowed = ("fund_code", "fund_name", "current_value", "holding_units", "cost_basis_value", "holding_pnl", "holding_return_pct")
    return {key: item.get(key) for key in allowed if key in item}


def _collect_position_snapshot_documents(agent_home: Path, bundle: RagSourceBundle) -> None:
    base = _execution_sync_dir(agent_home) / "position_snapshots"
    if not base.exists():
        return
    for path in sorted(base.glob("*.json")):
        payload = load_json(path)
        if not isinstance(payload, dict):
            continue
        snapshot_date = _date_or_default(payload.get("snapshot_date") or path.stem[:10] or bundle.as_of_date)
        metadata = {
            "source_file_kind": "position_snapshots",
            "platform": payload.get("platform", ""),
            "reconcile_id": payload.get("reconcile_id", ""),
        }
        available_from = _timestamp_or_inferred(payload.get("updated_at") or payload.get("generated_at"), snapshot_date, metadata)
        portfolio = payload.get("portfolio", {}) if isinstance(payload.get("portfolio"), dict) else {}
        funds = list(portfolio.get("funds", []) or payload.get("funds", []) or [])
        summary = f"Execution position snapshot {snapshot_date}; fund_count {len(funds)}; total_value {portfolio.get('total_value', '')}; source {payload.get('source', '')}"
        doc = _execution_doc(
            agent_home=agent_home,
            path=path,
            record_kind="position_snapshot",
            source_record_id=f"position_snapshot:{snapshot_date}",
            title=f"Execution position snapshot: {snapshot_date}",
            summary=summary,
            as_of_date=snapshot_date,
            available_from=available_from,
            entity_type="portfolio",
            entity_id="execution_portfolio",
            payload={
                "snapshot_date": snapshot_date,
                "fund_count": len(funds),
                "total_value": portfolio.get("total_value", ""),
                "holding_pnl": portfolio.get("holding_pnl", ""),
            },
            metadata=metadata,
        )
        bundle.documents.append(doc)
        bundle.chunks.append(_make_chunk(doc, f"Execution position snapshot summary: {summary}", summary))
        for index, fund in enumerate(funds):
            if not isinstance(fund, dict):
                continue
            fund_code = str(fund.get("fund_code", "") or "").strip()
            fund_name = str(fund.get("fund_name", "") or fund_code or f"fund {index}")
            fund_summary = (
                f"Execution synced position {fund_name}; current_value {fund.get('current_value', '')}; "
                f"holding_units {fund.get('holding_units', '')}; pnl {fund.get('holding_pnl', '')}; "
                f"return_pct {fund.get('holding_return_pct', '')}"
            )
            fund_doc = _execution_doc(
                agent_home=agent_home,
                path=path,
                record_kind="position_snapshot_fund",
                source_record_id=f"position_snapshot:{snapshot_date}:fund:{fund_code or index}",
                title=f"Execution synced position: {fund_name}",
                summary=fund_summary,
                as_of_date=snapshot_date,
                available_from=available_from,
                entity_type="fund",
                entity_id=fund_code,
                fund_codes=[fund_code] if fund_code else [],
                payload=_safe_position_payload(fund),
                metadata=metadata,
            )
            bundle.documents.append(fund_doc)
            bundle.chunks.append(_make_chunk(fund_doc, f"Execution synced position summary: {fund_summary}", fund_summary))


def _collect_reconciliation_report_documents(agent_home: Path, bundle: RagSourceBundle) -> None:
    base = _execution_sync_dir(agent_home) / "reconciliation_reports"
    if not base.exists():
        return
    for path in sorted(base.glob("*.json")):
        payload = load_json(path)
        if not isinstance(payload, dict):
            continue
        snapshot_date = _date_or_default(payload.get("snapshot_date") or path.stem[:10] or bundle.as_of_date)
        metadata = {"source_file_kind": "reconciliation_reports", "mode": payload.get("mode", "")}
        available_from = _timestamp_or_inferred(payload.get("updated_at") or payload.get("generated_at") or payload.get("created_at"), snapshot_date, metadata)
        updated_codes = [str(code) for code in payload.get("updated_fund_codes", []) or [] if str(code)]
        added_codes = [str(code) for code in payload.get("added_fund_codes", []) or [] if str(code)]
        dropped_codes = [str(code) for code in payload.get("dropped_missing_fund_codes", []) or [] if str(code)]
        summary = (
            f"Execution reconciliation {snapshot_date}; updated {payload.get('updated_fund_count', len(updated_codes))}; "
            f"added {payload.get('added_fund_count', len(added_codes))}; dropped_missing {payload.get('dropped_missing_count', len(dropped_codes))}; "
            f"mode {payload.get('mode', '')}"
        )
        doc = _execution_doc(
            agent_home=agent_home,
            path=path,
            record_kind="reconciliation_report",
            source_record_id=f"reconciliation_report:{snapshot_date}",
            title=f"Execution reconciliation report: {snapshot_date}",
            summary=summary,
            as_of_date=snapshot_date,
            available_from=available_from,
            entity_type="portfolio",
            entity_id="execution_portfolio",
            fund_codes=sorted({*updated_codes, *added_codes, *dropped_codes}),
            status="ok" if payload.get("ok", False) else "",
            payload={
                "snapshot_date": snapshot_date,
                "updated_fund_count": payload.get("updated_fund_count", len(updated_codes)),
                "added_fund_count": payload.get("added_fund_count", len(added_codes)),
                "dropped_missing_count": payload.get("dropped_missing_count", len(dropped_codes)),
                "updated_fund_codes": updated_codes,
                "added_fund_codes": added_codes,
                "dropped_missing_fund_codes": dropped_codes,
                "mode": payload.get("mode", ""),
            },
            metadata=metadata,
        )
        bundle.documents.append(doc)
        bundle.chunks.append(_make_chunk(doc, f"Execution reconciliation report summary: {summary}", summary))


def collect_execution_sync_documents(agent_home: Path, report_date: str | None = None) -> RagSourceBundle:
    base = _execution_sync_dir(agent_home)
    bundle = RagSourceBundle(
        domain=EXECUTION_DOMAIN,
        source_kind=EXECUTION_SOURCE_KIND,
        source_path=_source_path_text(agent_home, base),
        as_of_date=report_date or "",
        scope_key=build_scope_key(report_date or "global", EXECUTION_DOMAIN, EXECUTION_SOURCE_KIND),
    )
    if not base.exists():
        bundle.missing_data.append({"source_kind": EXECUTION_SOURCE_KIND, "source_path": bundle.source_path, "reason": "missing_source"})
        return bundle
    _collect_actual_trade_documents(agent_home, bundle)
    _collect_pending_confirmation_documents(agent_home, bundle)
    _collect_position_snapshot_documents(agent_home, bundle)
    _collect_reconciliation_report_documents(agent_home, bundle)
    return bundle


def iter_execution_sync_documents(agent_home: Path, date: str | None = None) -> list[RagDocument]:
    return collect_execution_sync_documents(agent_home, date).documents


SOURCE_COLLECTORS: dict[str, Callable[[Path, str | None], RagSourceBundle]] = {
    "long_memory": collect_long_memory_documents,
    "portfolio_state": collect_portfolio_documents,
    "llm_context": collect_llm_context_documents,
    "validated_advice": collect_validated_advice_documents,
    "committee_bundle": collect_committee_bundle_documents,
    "execution_sync": collect_execution_sync_documents,
}

DATE_REQUIRED_SOURCES = {"llm_context", "validated_advice", "committee_bundle"}
DEFAULT_SOURCES = ["long_memory", "portfolio_state", "llm_context", "validated_advice", "committee_bundle"]


def collect_source(agent_home: Path, domain: str, report_date: str | None = None) -> RagSourceBundle:
    collector = SOURCE_COLLECTORS.get(domain)
    if collector is None:
        return RagSourceBundle(domain=domain, source_kind=domain, source_path="", skipped_reason="unsupported_domain")
    try:
        return collector(agent_home, report_date)
    except Exception as exc:
        return RagSourceBundle(
            domain=domain,
            source_kind=domain,
            source_path="",
            as_of_date=report_date or "",
            errors=[{"source_kind": domain, "error": str(exc)}],
            scope_key=canonical_scope_key(domain, report_date),
        )
