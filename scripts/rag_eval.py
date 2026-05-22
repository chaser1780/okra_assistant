from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from common import dump_json, evidence_index_path, load_json, llm_context_path, resolve_agent_home, resolve_date, timestamp_now
from evidence_index import retrieve_agent_evidence
from rag_config import rag_eval_dir
from rag_query_planner import build_rag_query_plan
from rag_retriever import retrieve_rag_evidence
from run_multiagent_constants import DEFAULT_ANALYST_ORDER, DEFAULT_RESEARCHER_ORDER, DEFAULT_MANAGER_ORDER


AGENT_QUESTIONS = {
    "market_analyst": "market regime, proxy risk, policy and macro evidence",
    "theme_analyst": "theme rotation, style pressure and industry evidence",
    "fund_structure_analyst": "fund allocation, cap, structure and position constraints",
    "fund_quality_analyst": "fund quality, manager, profile, fee and scale evidence",
    "news_analyst": "fund news, market news, policy events and incremental risks",
    "sentiment_analyst": "sentiment heat, social virality and crowding evidence",
    "bull_researcher": "upside thesis, momentum support and positive evidence",
    "bear_researcher": "downside risk, weakness, crowding and negative evidence",
    "research_manager": "committee consensus, allocation tradeoff and decision evidence",
    "risk_manager": "portfolio risk, stale data, constraints and drawdown evidence",
    "portfolio_trader": "portfolio action priority, timing, funding and trade readiness",
}


def _agent_names() -> list[str]:
    names: list[str] = []
    for item in [*DEFAULT_ANALYST_ORDER, *DEFAULT_RESEARCHER_ORDER, *DEFAULT_MANAGER_ORDER]:
        if item not in names:
            names.append(item)
    return names


def _load_context(agent_home: Path, report_date: str) -> dict[str, Any]:
    path = llm_context_path(agent_home, report_date)
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def _legacy_payload(agent_home: Path, report_date: str, context: dict[str, Any]) -> dict[str, Any]:
    path = evidence_index_path(agent_home, report_date)
    if path.exists():
        payload = load_json(path)
        return payload if isinstance(payload, dict) else {}
    return {}


def _fund_codes(context: dict[str, Any], limit: int = 6) -> list[str]:
    result: list[str] = []
    for fund in context.get("funds", []) or []:
        code = str((fund or {}).get("fund_code", "") or "").strip()
        if code and code not in result:
            result.append(code)
    return result[:limit]


def _legacy_ids(payload: dict[str, Any], agent_name: str, context: dict[str, Any], funds: list[dict[str, Any]]) -> set[str]:
    if not payload:
        return set()
    retrieval = retrieve_agent_evidence(agent_name, context, index_payload=payload, relevant_funds=funds)
    ids = {str(item.get("evidence_id", "") or "") for item in retrieval.get("portfolio", []) or []}
    for items in (retrieval.get("funds", {}) or {}).values():
        ids.update(str(item.get("evidence_id", "") or "") for item in items or [])
    return {item for item in ids if item}


def _rag_query(agent_name: str, fund_code: str | None = None) -> str:
    base = AGENT_QUESTIONS.get(agent_name, agent_name)
    if fund_code:
        return f"{agent_name} {fund_code}: {base}"
    return f"{agent_name}: {base}"


def _rag_result(agent_home: Path, report_date: str, agent_name: str, fund_code: str | None, write_trace: bool) -> dict[str, Any]:
    plan = build_rag_query_plan(
        _rag_query(agent_name, fund_code),
        query_date=report_date,
        retrieval_profile="agent_shadow",
        intent=f"agent_shadow:{agent_name}",
        fund_codes=[fund_code] if fund_code else [],
        top_k=8,
        token_budget=6000,
        metadata={"agent_name": agent_name, "shadow": True},
    )
    return retrieve_rag_evidence(agent_home, plan, caller=f"agent_shadow:{agent_name}", write_trace_file=write_trace)


def _summarize_hits(hits: list[dict[str, Any]], target_fund: str | None) -> dict[str, Any]:
    source_counts = Counter(str(hit.get("source_kind", "") or "") for hit in hits)
    stale_count = sum(1 for hit in hits if (hit.get("metadata", {}) or {}).get("stale"))
    fund_match_count = 0
    for hit in hits:
        if not target_fund:
            continue
        fund_codes = set(hit.get("fund_codes", []) or [])
        entity_id = str(hit.get("entity_id", "") or "")
        if target_fund in fund_codes or target_fund == entity_id:
            fund_match_count += 1
    return {
        "hit_count": len(hits),
        "source_counts": dict(sorted(source_counts.items())),
        "stale_hit_count": stale_count,
        "fund_match_rate": round(fund_match_count / len(hits), 4) if hits and target_fund else None,
        "top_hit_ids": [str(hit.get("doc_id", "") or "") for hit in hits[:5]],
        "top_source_kinds": [str(hit.get("source_kind", "") or "") for hit in hits[:5]],
    }


def _no_future_violations(hits: list[dict[str, Any]], report_date: str) -> int:
    count = 0
    for hit in hits:
        for key in ("as_of_date", "published_at", "available_from"):
            value = str(hit.get(key, "") or "")
            if len(value) >= 10 and value[:10] > report_date:
                count += 1
                break
    return count


def run_eval(agent_home: Path, report_date: str, *, compare_legacy: bool = True, write_trace: bool = True) -> dict[str, Any]:
    context = _load_context(agent_home, report_date)
    legacy = _legacy_payload(agent_home, report_date, context)
    all_funds = list(context.get("funds", []) or [])
    funds_by_code = {str((fund or {}).get("fund_code", "") or ""): fund for fund in all_funds if isinstance(fund, dict)}
    fund_codes = _fund_codes(context)
    agents = _agent_names()
    agent_results: dict[str, Any] = {}
    totals = Counter()
    fallback_reasons: list[dict[str, Any]] = []

    for agent_name in agents:
        legacy_top_ids = _legacy_ids(legacy, agent_name, context, all_funds) if compare_legacy else set()
        queries = [{"scope": "portfolio", "fund_code": ""}] + [{"scope": "fund", "fund_code": code} for code in fund_codes]
        query_results = []
        for query in queries:
            fund_code = query["fund_code"] or None
            try:
                result = _rag_result(agent_home, report_date, agent_name, fund_code, write_trace)
                hits = list(result.get("hits", []) or [])
                rag_ids = {str(hit.get("source_record_id", "") or hit.get("doc_id", "") or "") for hit in hits}
                overlap = sorted(legacy_top_ids.intersection(rag_ids)) if compare_legacy else []
                summary = _summarize_hits(hits, fund_code)
                summary.update(
                    {
                        "scope": query["scope"],
                        "fund_code": query["fund_code"],
                        "trace_id": result.get("trace_id", ""),
                        "missing_data": result.get("missing_data", []),
                        "candidate_count_before_filter": result.get("candidate_count_before_filter", 0),
                        "candidate_count_after_filter": result.get("candidate_count_after_filter", 0),
                        "legacy_overlap_ids": overlap,
                        "legacy_overlap_count": len(overlap),
                        "no_future_violation_count": _no_future_violations(hits, report_date),
                    }
                )
                totals["hit_count"] += summary["hit_count"]
                totals["stale_hit_count"] += summary["stale_hit_count"]
                totals["no_future_violation_count"] += summary["no_future_violation_count"]
                if summary["missing_data"]:
                    totals["missing_queries"] += 1
                query_results.append(summary)
            except Exception as exc:
                fallback = {"scope": query["scope"], "fund_code": query["fund_code"], "reason": str(exc)}
                fallback_reasons.append({"agent_name": agent_name, **fallback})
                query_results.append({"scope": query["scope"], "fund_code": query["fund_code"], "fallback_reason": str(exc)})
                totals["fallback_count"] += 1
        agent_results[agent_name] = {
            "legacy_evidence_count": len(legacy_top_ids),
            "queries": query_results,
            "fund_codes": [code for code in fund_codes if code in funds_by_code],
        }

    payload = {
        "report_date": report_date,
        "generated_at": timestamp_now(),
        "mode": "compare_legacy" if compare_legacy else "rag_only",
        "legacy": {
            "available": bool(legacy),
            "entry_count": len(legacy.get("entries", []) or []) if isinstance(legacy, dict) else 0,
            "source_path": str(evidence_index_path(agent_home, report_date)),
        },
        "rag": {
            "write_trace": write_trace,
            "agent_count": len(agents),
            "fund_codes": fund_codes,
        },
        "metrics": dict(totals),
        "fallback_reasons": fallback_reasons,
        "agents": agent_results,
    }
    output_path = rag_eval_dir(agent_home) / f"{report_date}.json"
    dump_json(output_path, payload)
    payload["output_path"] = str(output_path)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate OKRA RAG shadow retrieval against legacy evidence.")
    parser.add_argument("--agent-home", default=None)
    parser.add_argument("--date", default="")
    parser.add_argument("--compare-legacy", action="store_true")
    parser.add_argument("--no-trace", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    payload = run_eval(agent_home, report_date, compare_legacy=bool(args.compare_legacy), write_trace=not args.no_trace)
    print(output_path := payload.get("output_path", ""))
    return 0 if output_path else 1


if __name__ == "__main__":
    raise SystemExit(main())
