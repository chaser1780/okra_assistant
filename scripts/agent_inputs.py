from __future__ import annotations

from pathlib import Path

from evidence_index import retrieve_agent_evidence
from rag_config import rag_agent_default_settings, rag_agent_profile
from rag_query_planner import build_rag_query_plan
from rag_retriever import retrieve_rag_evidence
from run_multiagent_constants import DEFAULT_ANALYST_ORDER, DEFAULT_RESEARCHER_ORDER


def compact_fund_view(fund: dict) -> dict:
    return {
        "fund_code": fund["fund_code"],
        "fund_name": fund["fund_name"],
        "role": fund.get("role"),
        "style_group": fund.get("style_group"),
        "current_value": fund.get("current_value"),
        "holding_pnl": fund.get("holding_pnl"),
        "holding_return_pct": fund.get("holding_return_pct"),
        "cap_value": fund.get("cap_value"),
        "locked_amount": fund.get("locked_amount"),
        "allow_trade": fund.get("allow_trade"),
        "fixed_daily_buy_amount": fund.get("fixed_daily_buy_amount"),
        "quote": {
            "day_change_pct": fund.get("quote", {}).get("day_change_pct"),
            "week_change_pct": fund.get("quote", {}).get("week_change_pct"),
            "month_change_pct": fund.get("quote", {}).get("month_change_pct"),
        },
        "intraday_proxy": {
            "change_pct": fund.get("intraday_proxy", {}).get("change_pct"),
            "stale": fund.get("intraday_proxy", {}).get("stale"),
            "proxy_name": fund.get("intraday_proxy", {}).get("proxy_name") or fund.get("intraday_proxy", {}).get("name"),
        },
        "estimated_nav": {
            "estimate_change_pct": fund.get("estimated_nav", {}).get("estimate_change_pct"),
            "confidence": fund.get("estimated_nav", {}).get("confidence"),
            "stale": fund.get("estimated_nav", {}).get("stale"),
        },
        "fund_profile": {
            "inception_date": fund.get("fund_profile", {}).get("inception_date"),
            "fund_age_years": fund.get("fund_profile", {}).get("fund_age_years"),
            "fund_manager": fund.get("fund_profile", {}).get("fund_manager"),
            "fund_type": fund.get("fund_profile", {}).get("fund_type"),
            "management_company": fund.get("fund_profile", {}).get("management_company"),
            "fund_scale_billion": fund.get("fund_profile", {}).get("fund_scale_billion"),
            "management_fee_rate": fund.get("fund_profile", {}).get("management_fee_rate"),
            "custody_fee_rate": fund.get("fund_profile", {}).get("custody_fee_rate"),
            "status": fund.get("fund_profile", {}).get("status"),
        },
        "recent_news": fund.get("recent_news", [])[:3],
    }


def compact_decision_fund_view(fund: dict) -> dict:
    return {
        "fund_code": fund["fund_code"],
        "fund_name": fund["fund_name"],
        "role": fund.get("role"),
        "style_group": fund.get("style_group"),
        "current_value": fund.get("current_value"),
        "holding_pnl": fund.get("holding_pnl"),
        "holding_return_pct": fund.get("holding_return_pct"),
        "cap_value": fund.get("cap_value"),
        "locked_amount": fund.get("locked_amount"),
        "allow_trade": fund.get("allow_trade"),
        "fixed_daily_buy_amount": fund.get("fixed_daily_buy_amount"),
        "quote": {
            "day_change_pct": fund.get("quote", {}).get("day_change_pct"),
            "week_change_pct": fund.get("quote", {}).get("week_change_pct"),
            "month_change_pct": fund.get("quote", {}).get("month_change_pct"),
        },
        "intraday_proxy": {
            "change_pct": fund.get("intraday_proxy", {}).get("change_pct"),
            "stale": fund.get("intraday_proxy", {}).get("stale"),
        },
        "estimated_nav": {
            "estimate_change_pct": fund.get("estimated_nav", {}).get("estimate_change_pct"),
            "confidence": fund.get("estimated_nav", {}).get("confidence"),
            "stale": fund.get("estimated_nav", {}).get("stale"),
        },
        "fund_profile": {
            "fund_age_years": fund.get("fund_profile", {}).get("fund_age_years"),
            "fund_type": fund.get("fund_profile", {}).get("fund_type"),
            "fund_scale_billion": fund.get("fund_profile", {}).get("fund_scale_billion"),
            "status": fund.get("fund_profile", {}).get("status"),
        },
    }


def successful_outputs(prior_outputs: dict, names: list[str] | None = None) -> dict:
    pool = names or list(prior_outputs.keys())
    return {key: prior_outputs[key]["output"] for key in pool if key in prior_outputs and prior_outputs[key]["status"] == "ok"}


def compact_agent_output(output: dict) -> dict:
    return {
        "agent_name": output.get("agent_name"),
        "mode": output.get("mode"),
        "summary": output.get("summary"),
        "confidence": output.get("confidence"),
        "evidence_strength": output.get("evidence_strength"),
        "data_freshness": output.get("data_freshness"),
        "abstain": output.get("abstain"),
        "key_points": (output.get("key_points") or [])[:6],
        "missing_info": (output.get("missing_info") or [])[:4],
        "watchouts": (output.get("watchouts") or [])[:4],
        "portfolio_view": {
            "regime": output.get("portfolio_view", {}).get("regime"),
            "risk_bias": output.get("portfolio_view", {}).get("risk_bias"),
            "key_drivers": (output.get("portfolio_view", {}).get("key_drivers") or [])[:4],
            "portfolio_implications": (output.get("portfolio_view", {}).get("portfolio_implications") or [])[:4],
        },
        "fund_views": [
            {
                "fund_code": item.get("fund_code"),
                "direction": item.get("direction"),
                "horizon": item.get("horizon"),
                "thesis": item.get("thesis"),
                "action_bias": item.get("action_bias"),
                "comment": item.get("comment"),
                "risks": (item.get("risks") or [])[:2],
            }
            for item in (output.get("fund_views") or [])[:6]
        ],
        "signal_cards": [
            {
                "signal_id": item.get("signal_id"),
                "fund_code": item.get("fund_code"),
                "signal_type": item.get("signal_type"),
                "direction": item.get("direction"),
                "action_bias": item.get("action_bias"),
                "confidence": item.get("confidence"),
                "supporting_evidence_ids": (item.get("supporting_evidence_ids") or [])[:4],
            }
            for item in (output.get("signal_cards") or [])[:8]
        ],
        "decision_cards": [
            {
                "decision_id": item.get("decision_id"),
                "fund_code": item.get("fund_code"),
                "proposed_action": item.get("proposed_action"),
                "size_bucket": item.get("size_bucket"),
                "risk_decision": item.get("risk_decision"),
                "supporting_signal_ids": (item.get("supporting_signal_ids") or [])[:4],
                "opposing_signal_ids": (item.get("opposing_signal_ids") or [])[:4],
            }
            for item in (output.get("decision_cards") or [])[:8]
        ],
    }


def _rag_shadow_enabled(context: dict) -> bool:
    settings = context.get("_rag_agent_shadow", {}) or {}
    return bool(settings.get("enabled", False))


def _rag_shadow_injects_prompt(context: dict) -> bool:
    settings = context.get("_rag_agent_shadow", {}) or {}
    return bool(settings.get("inject_into_prompt", False))


def _rag_default_settings(context: dict) -> dict:
    settings = context.get("_rag_agent_default", {}) or {}
    if settings:
        return dict(settings)
    agent_home_value = context.get("_agent_home")
    if not agent_home_value:
        return {}
    return rag_agent_default_settings(Path(agent_home_value))


def _rag_default_enabled(context: dict) -> bool:
    return bool(_rag_default_settings(context).get("enabled", False))


def _agent_profile(context: dict, agent_name: str) -> dict:
    profiles = context.get("_rag_agent_profiles", {}) or {}
    profile = profiles.get(agent_name, {}) if isinstance(profiles, dict) else {}
    if profile:
        return dict(profile)
    agent_home_value = context.get("_agent_home")
    if not agent_home_value:
        return {}
    return rag_agent_profile(Path(agent_home_value), agent_name)


def _positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _rag_shadow_query(agent_name: str, funds_payload: list[dict]) -> str:
    fund_codes = [str(item.get("fund_code", "") or "") for item in funds_payload[:6] if item.get("fund_code")]
    suffix = f" funds: {', '.join(fund_codes)}" if fund_codes else ""
    return f"agent shadow retrieval for {agent_name}{suffix}"


def _rag_default_query(agent_name: str, funds_payload: list[dict]) -> str:
    fund_codes = [str(item.get("fund_code", "") or "") for item in funds_payload[:6] if item.get("fund_code")]
    suffix = f" funds: {', '.join(fund_codes)}" if fund_codes else ""
    return f"{agent_name} portfolio research evidence{suffix}"


def _compact_rag_hits(hits: list[dict], limit: int = 12) -> list[dict]:
    return [
        {
            "doc_id": hit.get("doc_id", ""),
            "chunk_id": hit.get("chunk_id", ""),
            "source_kind": hit.get("source_kind", ""),
            "source_record_id": hit.get("source_record_id", ""),
            "title": hit.get("title", ""),
            "summary": hit.get("summary", ""),
            "text_for_llm": hit.get("text_for_llm", ""),
            "as_of_date": hit.get("as_of_date", ""),
            "fund_codes": hit.get("fund_codes", []),
            "score": hit.get("score", 0.0),
            "stale": bool((hit.get("metadata", {}) or {}).get("stale")),
        }
        for hit in hits[:limit]
    ]


def _rag_evidence_id(hit: dict) -> str:
    doc_id = str(hit.get("doc_id", "") or "")
    chunk_id = str(hit.get("chunk_id", "") or "")
    return f"rag:{doc_id}#{chunk_id}" if doc_id and chunk_id else f"rag:{doc_id or chunk_id}"


def _rag_hit_to_evidence(hit: dict, *, trace_id: str = "") -> dict:
    metadata = hit.get("metadata", {}) if isinstance(hit.get("metadata"), dict) else {}
    return {
        "evidence_id": _rag_evidence_id(hit),
        "source": "rag",
        "doc_id": hit.get("doc_id", ""),
        "chunk_id": hit.get("chunk_id", ""),
        "source_kind": hit.get("source_kind", ""),
        "source_record_id": hit.get("source_record_id", ""),
        "source_path": hit.get("source_path", ""),
        "source_tier": hit.get("source_tier", ""),
        "title": hit.get("title", ""),
        "summary": hit.get("summary", ""),
        "text_for_llm": hit.get("text_for_llm", ""),
        "as_of": hit.get("as_of_date", ""),
        "as_of_date": hit.get("as_of_date", ""),
        "available_from": hit.get("available_from", ""),
        "published_at": hit.get("published_at", ""),
        "entity_type": "fund" if hit.get("fund_codes") else hit.get("domain", ""),
        "entity_id": hit.get("entity_id", ""),
        "fund_codes": list(hit.get("fund_codes", []) or []),
        "domain": hit.get("domain", ""),
        "retrieval_score": hit.get("score", 0.0),
        "mapping_mode": "rag_fund_code",
        "evidence_type": metadata.get("evidence_type", hit.get("source_kind", "")),
        "trace_id": trace_id,
        "metadata": metadata,
    }


def _rag_hits_to_evidence_items(rag_payload: dict) -> list[dict]:
    trace_id = str(rag_payload.get("trace_id", "") or "")
    return [_rag_hit_to_evidence(hit, trace_id=trace_id) for hit in list(rag_payload.get("hits", []) or [])]


def _fund_evidence_map_from_items(items: list[dict], fund_codes: list[str]) -> dict[str, list[dict]]:
    targets = [str(code) for code in fund_codes if str(code)]
    result: dict[str, list[dict]] = {code: [] for code in targets}
    for item in items:
        item_codes = {str(code) for code in (item.get("fund_codes", []) or []) if str(code)}
        for fund_code in targets:
            if fund_code not in item_codes:
                continue
            result.setdefault(fund_code, []).append(
                {
                    "evidence_id": item.get("evidence_id", ""),
                    "fund_code": fund_code,
                    "role": "retrieved",
                    "relevance_score": item.get("retrieval_score", 0.0),
                    "mapping_mode": item.get("mapping_mode", "rag_fund_code"),
                    "source_tier": item.get("source_tier", ""),
                    "evidence_type": item.get("evidence_type", ""),
                }
            )
    return {key: value for key, value in result.items() if value}


def retrieve_agent_rag_shadow(agent_name: str, context: dict, funds_payload: list[dict]) -> dict:
    agent_home_value = context.get("_agent_home")
    agent_home = Path(agent_home_value) if agent_home_value else None
    report_date = str(context.get("analysis_date", "") or context.get("report_date", "") or "")
    if not agent_home or not report_date:
        return {"enabled": False, "fallback_reason": "missing_agent_home_or_date"}
    fund_codes = []
    for item in funds_payload[:6]:
        code = str(item.get("fund_code", "") or "").strip()
        if code and code not in fund_codes:
            fund_codes.append(code)
    plan = build_rag_query_plan(
        _rag_shadow_query(agent_name, funds_payload),
        query_date=report_date,
        retrieval_profile="agent_shadow",
        intent=f"agent_shadow:{agent_name}",
        fund_codes=fund_codes,
        top_k=8,
        token_budget=6000,
        metadata={"agent_name": agent_name, "shadow": True},
    )
    result = retrieve_rag_evidence(
        agent_home,
        plan,
        caller=f"agent_shadow:{agent_name}",
        write_trace_file=bool((context.get("_rag_agent_shadow", {}) or {}).get("write_trace", True)),
    )
    hits = list(result.get("hits", []) or [])
    return {
        "enabled": True,
        "trace_id": result.get("trace_id", ""),
        "hit_count": len(hits),
        "missing_data": result.get("missing_data", []),
        "candidate_count_before_filter": result.get("candidate_count_before_filter", 0),
        "candidate_count_after_filter": result.get("candidate_count_after_filter", 0),
        "hits": _compact_rag_hits(hits, limit=8),
    }


def retrieve_agent_rag_default(agent_name: str, context: dict, funds_payload: list[dict]) -> dict:
    settings = _rag_default_settings(context)
    agent_home_value = context.get("_agent_home")
    agent_home = Path(agent_home_value) if agent_home_value else None
    report_date = str(context.get("analysis_date", "") or context.get("report_date", "") or "")
    if not agent_home or not report_date:
        return {"enabled": False, "fallback_reason": "missing_agent_home_or_date"}
    profile = _agent_profile(context, agent_name)
    if profile and not bool(profile.get("enabled", True)):
        return {"enabled": False, "fallback_reason": "agent_profile_disabled"}
    fund_codes = []
    for item in funds_payload[:6]:
        code = str(item.get("fund_code", "") or "").strip()
        if code and code not in fund_codes:
            fund_codes.append(code)
    top_k = _positive_int(profile.get("top_k_portfolio"), _positive_int(settings.get("top_k"), 8))
    plan = build_rag_query_plan(
        _rag_default_query(agent_name, funds_payload),
        query_date=report_date,
        retrieval_profile=f"agent_default:{agent_name}",
        intent=f"agent_default:{agent_name}",
        fund_codes=fund_codes,
        domains=list(profile.get("domains", []) or []),
        source_kinds=list(profile.get("source_kinds", []) or []),
        top_k=top_k,
        token_budget=_positive_int(settings.get("token_budget"), 6000),
        include_negative_memory=bool(profile.get("allow_negative_memory", False)),
        include_execution=bool(profile.get("include_execution", False)),
        metadata={"agent_name": agent_name, "default": True},
    )
    result = retrieve_rag_evidence(
        agent_home,
        plan,
        caller=f"agent_default:{agent_name}",
        write_trace_file=bool(settings.get("write_trace", True)),
    )
    hits = list(result.get("hits", []) or [])
    min_hits = _positive_int(settings.get("min_hits"), 1)
    fallback_reason = "hit_count_below_min" if len(hits) < min_hits else ""
    return {
        "enabled": True,
        "profile": profile,
        "trace_id": result.get("trace_id", ""),
        "hit_count": len(hits),
        "missing_data": result.get("missing_data", []),
        "fallback_reason": fallback_reason,
        "candidate_count_before_filter": result.get("candidate_count_before_filter", 0),
        "candidate_count_after_filter": result.get("candidate_count_after_filter", 0),
        "hits": _compact_rag_hits(hits),
    }


def compact_successful_outputs(prior_outputs: dict, names: list[str] | None = None) -> dict:
    return {name: compact_agent_output(output) for name, output in successful_outputs(prior_outputs, names).items()}


def attach_retrieved_evidence(agent_name: str, context: dict, base: dict, funds_payload: list[dict], source_funds: list[dict]) -> dict:
    retrieval = retrieve_agent_evidence(
        agent_name,
        context,
        index_payload=context.get("_evidence_index_payload"),
        relevant_funds=source_funds,
    )
    retrieval_backend = "legacy"
    rag_default = {}
    if _rag_default_enabled(context):
        try:
            rag_default = retrieve_agent_rag_default(agent_name, context, funds_payload)
        except Exception as exc:
            rag_default = {"enabled": True, "fallback_reason": str(exc), "hit_count": 0, "missing_data": []}
        fallback_reason = str(rag_default.get("fallback_reason", "") or "")
        if rag_default.get("enabled") and not fallback_reason:
            retrieval_backend = "rag"
            rag_evidence_items = _rag_hits_to_evidence_items(rag_default)
            base["rag_retrieved_evidence"] = rag_default
            base["evidence_items"] = rag_evidence_items
        elif bool(_rag_default_settings(context).get("fallback_to_legacy", True)):
            retrieval_backend = "legacy_fallback"
        else:
            retrieval_backend = "rag_failed"
    base["retrieved_evidence"] = retrieval
    if "evidence_items" not in base:
        base["evidence_items"] = retrieval.get("portfolio", [])
    if retrieval_backend == "rag":
        fund_codes = [str(item.get("fund_code", "") or "").strip() for item in source_funds if item.get("fund_code")]
        base["fund_evidence_map"] = _fund_evidence_map_from_items(base.get("evidence_items", []), fund_codes)
    else:
        base["fund_evidence_map"] = {
            fund_code: [
                {
                    "evidence_id": item.get("evidence_id", ""),
                    "fund_code": fund_code,
                    "role": "retrieved",
                    "relevance_score": item.get("retrieval_score", 0.0),
                    "mapping_mode": item.get("mapping_mode", ""),
                    "source_tier": item.get("source_tier", ""),
                    "evidence_type": item.get("evidence_type", ""),
                }
                for item in items
            ]
            for fund_code, items in (retrieval.get("funds", {}) or {}).items()
        }
    enriched_funds = []
    retrieved_by_fund = retrieval.get("funds", {}) or {}
    for item in funds_payload:
        enriched = dict(item)
        fund_code = str(item.get("fund_code", "") or "").strip()
        if fund_code:
            enriched["retrieved_evidence"] = retrieved_by_fund.get(fund_code, [])
        enriched_funds.append(enriched)
    base["funds"] = enriched_funds
    base["retrieval_backend"] = retrieval_backend
    base["rag_default_trace_id"] = rag_default.get("trace_id", "")
    base["rag_default_fallback_reason"] = rag_default.get("fallback_reason", "")
    base["rag_default_hit_count"] = rag_default.get("hit_count", 0)
    if _rag_shadow_enabled(context):
        try:
            rag_shadow = retrieve_agent_rag_shadow(agent_name, context, funds_payload)
        except Exception as exc:
            rag_shadow = {"enabled": True, "fallback_reason": str(exc), "hit_count": 0, "missing_data": []}
        base["rag_retrieval_trace_id"] = rag_shadow.get("trace_id", "")
        base["rag_legacy_diff"] = {
            "legacy_portfolio_hit_count": len(retrieval.get("portfolio", []) or []),
            "rag_hit_count": rag_shadow.get("hit_count", 0),
            "missing_data": rag_shadow.get("missing_data", []),
            "fallback_reason": rag_shadow.get("fallback_reason", ""),
            "inject_into_prompt": _rag_shadow_injects_prompt(context),
        }
        if _rag_shadow_injects_prompt(context):
            base["rag_retrieved_evidence"] = rag_shadow
    return base


def build_agent_input(agent_name: str, context: dict, prior_outputs: dict) -> dict:
    base = {
        "analysis_date": context.get("analysis_date"),
        "mode": context.get("mode"),
        "portfolio_summary": context.get("portfolio_summary", {}),
        "constraints": context.get("constraints", {}),
        "memory_digest": context.get("memory_digest", {}),
        "source_health_summary": context.get("source_health_summary", []),
        "news_digest": context.get("news_digest", {}),
        "sentiment_digest": context.get("sentiment_digest", {}),
        "event_risks": context.get("event_risks", []),
    }
    funds = context.get("funds", [])
    tactical_funds = [compact_fund_view(fund) for fund in funds if fund.get("role") == "tactical"]
    tactical_decision_funds = [compact_decision_fund_view(fund) for fund in funds if fund.get("role") == "tactical"]
    analyst_outputs = compact_successful_outputs(prior_outputs, DEFAULT_ANALYST_ORDER)

    if agent_name == "market_analyst":
        fund_payload = [
            {
                "fund_code": fund["fund_code"],
                "fund_name": fund["fund_name"],
                "role": fund["role"],
                "style_group": fund.get("style_group"),
                "intraday_proxy": compact_fund_view(fund)["intraday_proxy"],
                "estimated_nav": compact_fund_view(fund)["estimated_nav"],
                "quote": compact_fund_view(fund)["quote"],
            }
            for fund in funds
        ]
        return attach_retrieved_evidence(agent_name, context, base, fund_payload, funds)

    if agent_name == "theme_analyst":
        base["external_reference"] = context.get("external_reference", {})
        return attach_retrieved_evidence(agent_name, context, base, tactical_funds, [fund for fund in funds if fund.get("role") == "tactical"])

    if agent_name == "fund_structure_analyst":
        fund_payload = [
            {
                "fund_code": fund["fund_code"],
                "fund_name": fund["fund_name"],
                "role": fund["role"],
                "style_group": fund.get("style_group"),
                "current_value": fund.get("current_value"),
                "cap_value": fund.get("cap_value"),
                "locked_amount": fund.get("locked_amount"),
                "allow_trade": fund.get("allow_trade"),
            }
            for fund in funds
        ]
        return attach_retrieved_evidence(agent_name, context, base, fund_payload, funds)

    if agent_name == "fund_quality_analyst":
        fund_payload = tactical_funds + [
            {
                "fund_code": fund["fund_code"],
                "fund_name": fund["fund_name"],
                "role": fund["role"],
                "style_group": fund.get("style_group"),
                "quote": compact_fund_view(fund)["quote"],
                "recent_news": fund.get("recent_news", [])[:2],
            }
            for fund in funds
            if fund.get("role") in {"core_dca", "fixed_hold"}
        ]
        return attach_retrieved_evidence(agent_name, context, base, fund_payload, funds)

    if agent_name == "news_analyst":
        base["news_query_plan"] = context.get("news_query_plan", {})
        fund_payload = [
            {
                "fund_code": fund["fund_code"],
                "fund_name": fund["fund_name"],
                "recent_news": fund.get("recent_news", [])[:5],
                "evidence_refs": fund.get("evidence_refs", [])[:8],
            }
            for fund in funds
        ]
        return attach_retrieved_evidence(agent_name, context, base, fund_payload, funds)

    if agent_name == "sentiment_analyst":
        base["external_reference"] = context.get("external_reference", {})
        base["news_query_plan"] = {"sentiment_queries": (context.get("news_query_plan", {}) or {}).get("sentiment_queries", [])}
        fund_payload = [
            {
                "fund_code": fund["fund_code"],
                "fund_name": fund["fund_name"],
                "style_group": fund.get("style_group"),
                "intraday_proxy": compact_fund_view(fund)["intraday_proxy"],
                "estimated_nav": compact_fund_view(fund)["estimated_nav"],
                "quote": compact_fund_view(fund)["quote"],
                "recent_news": fund.get("recent_news", [])[:4],
                "evidence_refs": fund.get("evidence_refs", [])[:8],
            }
            for fund in funds
        ]
        return attach_retrieved_evidence(agent_name, context, base, fund_payload, funds)

    if agent_name in {"bull_researcher", "bear_researcher"}:
        base["analyst_outputs"] = analyst_outputs
        return attach_retrieved_evidence(agent_name, context, base, tactical_decision_funds, [fund for fund in funds if fund.get("role") == "tactical"])

    if agent_name == "research_manager":
        base["analyst_outputs"] = analyst_outputs
        base["researcher_outputs"] = compact_successful_outputs(prior_outputs, DEFAULT_RESEARCHER_ORDER)
        return attach_retrieved_evidence(agent_name, context, base, [compact_decision_fund_view(fund) for fund in funds], funds)

    if agent_name == "risk_manager":
        base["analyst_outputs"] = analyst_outputs
        base["researcher_outputs"] = compact_successful_outputs(prior_outputs, DEFAULT_RESEARCHER_ORDER)
        base["research_manager_output"] = compact_successful_outputs(prior_outputs, ["research_manager"]).get("research_manager", {})
        return attach_retrieved_evidence(agent_name, context, base, [compact_decision_fund_view(fund) for fund in funds], funds)

    if agent_name == "portfolio_trader":
        base["research_manager_output"] = compact_successful_outputs(prior_outputs, ["research_manager"]).get("research_manager", {})
        base["risk_manager_output"] = compact_successful_outputs(prior_outputs, ["risk_manager"]).get("risk_manager", {})
        return attach_retrieved_evidence(agent_name, context, base, [compact_decision_fund_view(fund) for fund in funds], funds)

    base["prior_outputs"] = compact_successful_outputs(prior_outputs)
    return attach_retrieved_evidence(agent_name, context, base, [compact_fund_view(fund) for fund in funds], funds)
