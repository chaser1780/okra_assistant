from __future__ import annotations

import argparse
from collections import Counter
import math
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

EVAL_SET_SCHEMA_VERSION = "rag_eval_set.v1"


def rag_eval_set_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "rag" / "eval_sets" / f"{report_date}.json"


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _eval_key(agent_name: str, scope: str, fund_code: str) -> str:
    return f"{agent_name}|{scope}|{fund_code}"


def _load_eval_set(agent_home: Path, report_date: str) -> dict[str, Any]:
    path = rag_eval_set_path(agent_home, report_date)
    base = {
        "available": False,
        "path": str(path),
        "schemaVersion": "",
        "reportDate": report_date,
        "queryCount": 0,
        "entries": {},
        "reason": "not_found",
    }
    if not path.exists():
        return base
    try:
        payload = load_json(path)
    except Exception as exc:
        return {**base, "reason": f"invalid_json:{exc}"}
    if not isinstance(payload, dict):
        return {**base, "reason": "invalid_root"}
    entries: dict[str, dict[str, Any]] = {}
    invalid_count = 0
    for item in payload.get("queries", []) or []:
        if not isinstance(item, dict):
            invalid_count += 1
            continue
        agent_name = str(item.get("agentName") or item.get("agent_name") or "").strip()
        fund_code = str(item.get("fundCode") or item.get("fund_code") or "").strip()
        scope = str(item.get("scope") or ("fund" if fund_code else "portfolio")).strip()
        if not agent_name or scope not in {"portfolio", "fund"}:
            invalid_count += 1
            continue
        should_abstain = item.get("shouldAbstain")
        entries[_eval_key(agent_name, scope, fund_code)] = {
            "queryId": str(item.get("queryId") or item.get("query_id") or _eval_key(agent_name, scope, fund_code)),
            "expectedEvidenceIds": _string_set(item.get("expectedEvidenceIds") or item.get("expected_evidence_ids")),
            "forbiddenEvidenceIds": _string_set(item.get("forbiddenEvidenceIds") or item.get("forbidden_evidence_ids")),
            "shouldAbstain": should_abstain if isinstance(should_abstain, bool) else None,
        }
    return {
        "available": bool(entries),
        "path": str(path),
        "schemaVersion": str(payload.get("schemaVersion") or payload.get("schema_version") or ""),
        "reportDate": str(payload.get("reportDate") or payload.get("report_date") or report_date),
        "queryCount": len(entries),
        "entries": entries,
        "reason": "ok" if entries else ("no_valid_queries" if invalid_count else "empty"),
        "invalidQueryCount": invalid_count,
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
        "citation_complete_count": sum(
            1
            for hit in hits
            if str(hit.get("source_path", "") or "")
            and str(hit.get("source_record_id", "") or hit.get("doc_id", "") or "")
            and str(hit.get("as_of_date", "") or "")
        ),
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


def _future_rejected_count(rejected_samples: list[dict[str, Any]]) -> int:
    return sum(1 for item in rejected_samples if str(item.get("reason") or "").startswith("future_"))


def _hit_identifier(hit: dict[str, Any]) -> str:
    return str(hit.get("source_record_id") or hit.get("doc_id") or "").strip()


def _has_complete_citation(hit: dict[str, Any]) -> bool:
    return bool(
        str(hit.get("source_path") or "").strip()
        and _hit_identifier(hit)
        and str(hit.get("as_of_date") or "").strip()
    )


def _dcg(relevance: list[bool]) -> float:
    return sum(1.0 / math.log2(index + 2) for index, value in enumerate(relevance) if value)


def _benchmark_query_metrics(hits: list[dict[str, Any]], expectation: dict[str, Any] | None) -> dict[str, Any]:
    if expectation is None:
        return {"labeled": False}
    expected = set(expectation.get("expectedEvidenceIds") or set())
    forbidden = set(expectation.get("forbiddenEvidenceIds") or set())
    retrieved_ids = [_hit_identifier(hit) for hit in hits]
    retrieved_expected = [hit for hit in hits if _hit_identifier(hit) in expected]
    relevant_count = len(retrieved_expected)
    expected_count = len(expected)
    recall = round(relevant_count / expected_count, 4) if expected_count else None
    ideal = _dcg([True] * min(expected_count, len(hits)))
    ndcg = round(_dcg([identifier in expected for identifier in retrieved_ids]) / ideal, 4) if ideal else None
    should_abstain = expectation.get("shouldAbstain")
    predicted_abstain = not hits
    return {
        "labeled": True,
        "queryId": expectation.get("queryId", ""),
        "expectedEvidenceCount": expected_count,
        "retrievedRelevantCount": relevant_count,
        "recallAtK": recall,
        "nDCGAtK": ndcg,
        "forbiddenHitCount": sum(1 for identifier in retrieved_ids if identifier in forbidden),
        "completeRelevantCitationCount": sum(1 for hit in retrieved_expected if _has_complete_citation(hit)),
        "shouldAbstain": should_abstain,
        "predictedAbstain": predicted_abstain,
        "abstentionCorrect": predicted_abstain == should_abstain if isinstance(should_abstain, bool) else None,
    }


def _aggregate_benchmark_metrics(query_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [item["benchmark"] for item in query_summaries if item.get("benchmark", {}).get("labeled")]
    with_expected = [item for item in labeled if int(item.get("expectedEvidenceCount") or 0) > 0]
    with_abstention = [item for item in labeled if item.get("abstentionCorrect") is not None]
    expected_count = sum(int(item.get("expectedEvidenceCount") or 0) for item in with_expected)
    relevant_count = sum(int(item.get("retrievedRelevantCount") or 0) for item in with_expected)
    forbidden_hits = sum(int(item.get("forbiddenHitCount") or 0) for item in labeled)
    retrieved_count = sum(int(item.get("hit_count") or 0) for item in query_summaries if item.get("benchmark", {}).get("labeled"))
    ndcgs = [float(item["nDCGAtK"]) for item in with_expected if item.get("nDCGAtK") is not None]
    correct_abstentions = sum(1 for item in with_abstention if item.get("abstentionCorrect") is True)
    complete_relevant_citations = sum(int(item.get("completeRelevantCitationCount") or 0) for item in with_expected)
    return {
        "gold_labeled_query_count": len(labeled),
        "gold_expected_evidence_count": expected_count,
        "recall_at_k": round(relevant_count / expected_count, 4) if expected_count else None,
        "nDCG_at_k": round(sum(ndcgs) / len(ndcgs), 4) if ndcgs else None,
        "evidence_coverage_rate": round(sum(1 for item in with_expected if int(item.get("retrievedRelevantCount") or 0) > 0) / len(with_expected), 4) if with_expected else None,
        "erroneous_recall_rate": round(forbidden_hits / retrieved_count, 4) if retrieved_count else None,
        "citation_correctness_rate": round(complete_relevant_citations / relevant_count, 4) if relevant_count else None,
        "abstention_quality": round(correct_abstentions / len(with_abstention), 4) if with_abstention else None,
    }


def run_eval(agent_home: Path, report_date: str, *, compare_legacy: bool = True, write_trace: bool = True) -> dict[str, Any]:
    context = _load_context(agent_home, report_date)
    legacy = _legacy_payload(agent_home, report_date, context)
    eval_set = _load_eval_set(agent_home, report_date)
    all_funds = list(context.get("funds", []) or [])
    funds_by_code = {str((fund or {}).get("fund_code", "") or ""): fund for fund in all_funds if isinstance(fund, dict)}
    fund_codes = _fund_codes(context)
    agents = _agent_names()
    agent_results: dict[str, Any] = {}
    totals = Counter()
    fallback_reasons: list[dict[str, Any]] = []
    query_summaries: list[dict[str, Any]] = []

    for agent_name in agents:
        legacy_top_ids = _legacy_ids(legacy, agent_name, context, all_funds) if compare_legacy else set()
        queries = [{"scope": "portfolio", "fund_code": ""}] + [{"scope": "fund", "fund_code": code} for code in fund_codes]
        query_results = []
        for query in queries:
            fund_code = query["fund_code"] or None
            try:
                result = _rag_result(agent_home, report_date, agent_name, fund_code, write_trace)
                hits = list(result.get("hits", []) or [])
                rejected_samples = list(result.get("rejected_samples", []) or [])
                rag_ids = {str(hit.get("source_record_id", "") or hit.get("doc_id", "") or "") for hit in hits}
                overlap = sorted(legacy_top_ids.intersection(rag_ids)) if compare_legacy else []
                summary = _summarize_hits(hits, fund_code)
                benchmark = _benchmark_query_metrics(
                    hits,
                    eval_set["entries"].get(_eval_key(agent_name, query["scope"], query["fund_code"])),
                )
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
                        "future_rejected_count": _future_rejected_count(rejected_samples),
                        "benchmark": benchmark,
                    }
                )
                totals["hit_count"] += summary["hit_count"]
                totals["stale_hit_count"] += summary["stale_hit_count"]
                totals["no_future_violation_count"] += summary["no_future_violation_count"]
                totals["future_rejected_count"] += summary["future_rejected_count"]
                totals["citation_complete_count"] += summary["citation_complete_count"]
                totals["query_count"] += 1
                if summary["hit_count"]:
                    totals["queries_with_hits"] += 1
                if summary["missing_data"]:
                    totals["missing_queries"] += 1
                query_results.append(summary)
                query_summaries.append(summary)
            except Exception as exc:
                fallback = {"scope": query["scope"], "fund_code": query["fund_code"], "reason": str(exc)}
                fallback_reasons.append({"agent_name": agent_name, **fallback})
                query_results.append({"scope": query["scope"], "fund_code": query["fund_code"], "fallback_reason": str(exc)})
                totals["fallback_count"] += 1
                totals["query_count"] += 1
        agent_results[agent_name] = {
            "legacy_evidence_count": len(legacy_top_ids),
            "queries": query_results,
            "fund_codes": [code for code in fund_codes if code in funds_by_code],
        }

    hit_count = int(totals.get("hit_count", 0))
    query_count = int(totals.get("query_count", 0))
    matched_rates = [float(item["fund_match_rate"]) for item in query_summaries if item.get("fund_match_rate") is not None]
    source_kinds = {kind for item in query_summaries for kind in item.get("top_source_kinds", []) if kind}
    future_rejected_count = int(totals.get("future_rejected_count", 0))
    future_violation_count = int(totals.get("no_future_violation_count", 0))
    benchmark_metrics = _aggregate_benchmark_metrics(query_summaries)
    evaluation_limits = ["当前检索模式为 lexical_rerank，不是生产向量语义检索。", "离线评估不会启用 embedding、混合检索或改变建议链路。"]
    if not eval_set["available"]:
        evaluation_limits.insert(0, f"未找到可用人工标注评估集（{eval_set['reason']}），Recall@K、nDCG、错误召回和 abstention 指标不可用。")
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
            "retrieval_mode": "lexical_rerank",
            "semantic_vector_enabled": False,
        },
        "benchmark": {key: value for key, value in eval_set.items() if key != "entries"},
        "metrics": {
            **dict(totals),
            "hit_rate": round(int(totals.get("queries_with_hits", 0)) / query_count, 4) if query_count else 0.0,
            "mean_hits_per_query": round(hit_count / query_count, 4) if query_count else 0.0,
            "citation_completeness_rate": round(int(totals.get("citation_complete_count", 0)) / hit_count, 4) if hit_count else 0.0,
            "mean_fund_match_rate": round(sum(matched_rates) / len(matched_rates), 4) if matched_rates else None,
            "source_diversity": len(source_kinds),
            "future_data_rejection_rate": round(future_rejected_count / (future_rejected_count + future_violation_count), 4) if future_rejected_count + future_violation_count else None,
            **benchmark_metrics,
        },
        "evaluationLimits": evaluation_limits,
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
