from __future__ import annotations

from common import timestamp_now
from models import CommitteeDecisionBundle
from run_multiagent_constants import DEFAULT_MANAGER_ORDER


def degradation_summary(aggregate: dict, manager_order: list[str]) -> dict:
    failed_names = [item.get("agent_name", "") for item in aggregate.get("failed_agents", []) if item.get("agent_name")]
    degraded_names = list(aggregate.get("degraded_agent_names", []) or [])
    blocking_failures = [name for name in manager_order if name in failed_names]
    core_statuses = {name: str(aggregate.get("agents", {}).get(name, {}).get("status", "")).lower() for name in manager_order}
    committee_ready = all(status == "ok" for status in core_statuses.values())
    degraded_ok = bool(failed_names or degraded_names) and committee_ready and not blocking_failures
    core_degraded = [name for name, status in core_statuses.items() if status == "degraded"]
    if blocking_failures:
        degradation_mode = "failed"
    elif core_degraded:
        degradation_mode = "decision_degraded"
    elif degraded_names:
        degradation_mode = "display_degraded"
    else:
        degradation_mode = "none"
    return {
        "failed_agent_names": failed_names,
        "degraded_agent_names": degraded_names,
        "blocking_failures": blocking_failures,
        "committee_ready": committee_ready,
        "degraded_ok": degraded_ok,
        "degradation_mode": degradation_mode,
        "execution_eligible": degradation_mode in {"none", "display_degraded"} and not failed_names,
    }


def _agent_output(aggregate: dict, agent_name: str) -> dict:
    return aggregate.get("agents", {}).get(agent_name, {}).get("output", {}) or {}


def _case_items(output: dict, *, limit: int = 6) -> list[dict]:
    items: list[dict] = []
    for card in output.get("decision_cards", []) or []:
        items.append(
            {
                "fund_code": card.get("fund_code", ""),
                "action_bias": card.get("action_bias", ""),
                "thesis": card.get("thesis", card.get("comment", "")),
                "evidence_refs": card.get("evidence_refs", []) or card.get("supporting_signal_ids", []),
            }
        )
    for view in output.get("fund_views", []) or []:
        if len(items) >= limit:
            break
        items.append(
            {
                "fund_code": view.get("fund_code", ""),
                "action_bias": view.get("action_bias", ""),
                "thesis": view.get("thesis", view.get("comment", "")),
                "evidence_refs": view.get("evidence_refs", []),
            }
        )
    return items[:limit]


def build_committee_summary(aggregate: dict) -> dict:
    bull = _agent_output(aggregate, "bull_researcher")
    bear = _agent_output(aggregate, "bear_researcher")
    manager = _agent_output(aggregate, "research_manager")
    risk = _agent_output(aggregate, "risk_manager")
    failed = aggregate.get("failed_agent_names", []) or [item.get("agent_name", "") for item in aggregate.get("failed_agents", [])]
    risk_vetoes = []
    for card in risk.get("decision_cards", []) or []:
        risk_decision = str(card.get("risk_decision", "") or "").lower()
        action_bias = str(card.get("action_bias", "") or "").lower()
        if risk_decision in {"reject", "veto"} or action_bias in {"reject", "avoid", "reduce"} or card.get("downgrade_reason"):
            risk_vetoes.append(
                {
                    "fund_code": card.get("fund_code", ""),
                    "risk_decision": card.get("risk_decision", ""),
                    "action_bias": card.get("action_bias", ""),
                    "reason": card.get("downgrade_reason") or card.get("comment") or card.get("thesis", ""),
                    "evidence_refs": card.get("evidence_refs", []) or card.get("opposing_signal_ids", []),
                }
            )
    confidence = "high" if aggregate.get("committee_ready") and not failed else "medium" if aggregate.get("degraded_ok") else "low"
    decision_source = "fallback" if failed and not aggregate.get("committee_ready") else "risk_constrained" if risk_vetoes else "manager_consensus"
    return {
        "schema_version": 1,
        "debate_summary": [item for item in [bull.get("summary", ""), bear.get("summary", ""), manager.get("summary", ""), risk.get("summary", "")] if item][:6],
        "bull_case": _case_items(bull),
        "bear_case": _case_items(bear),
        "risk_vetoes": risk_vetoes,
        "manager_decision": {
            "summary": manager.get("summary", ""),
            "portfolio_view": manager.get("portfolio_view", {}),
            "decision_cards": (manager.get("decision_cards", []) or [])[:8],
        },
        "manager_responses": manager.get("response_to_bear_case", []) or manager.get("key_points", [])[:6],
        "unresolved_conflicts": bear.get("key_points", [])[:3] if risk_vetoes or failed else [],
        "committee_confidence": confidence,
        "decision_source": decision_source,
    }


def _bundle_fund_names(context: dict) -> dict[str, dict]:
    return {str(item.get("fund_code", "") or ""): item for item in (context.get("funds", []) or []) if item.get("fund_code")}


def build_committee_decision_bundle(aggregate: dict, context: dict) -> CommitteeDecisionBundle:
    manager = _agent_output(aggregate, "research_manager")
    risk = _agent_output(aggregate, "risk_manager")
    trader = _agent_output(aggregate, "portfolio_trader")
    manager_cards = {item.get("fund_code", ""): item for item in (manager.get("decision_cards", []) or []) if item.get("fund_code")}
    risk_cards = {item.get("fund_code", ""): item for item in (risk.get("decision_cards", []) or []) if item.get("fund_code")}
    trader_cards = {item.get("fund_code", ""): item for item in (trader.get("decision_cards", []) or []) if item.get("fund_code")}
    fund_meta = _bundle_fund_names(context)
    failed_agent_names = list(aggregate.get("failed_agent_names", []) or [])
    degraded_agent_names = list(aggregate.get("degraded_agent_names", []) or [])
    degradation_mode = str(aggregate.get("degradation_mode", "none") or "none")
    execution_eligible = bool(aggregate.get("execution_eligible", False))
    decision_mode = "canonical"
    notes: list[str] = []
    if degradation_mode == "decision_degraded":
        decision_mode = "hold_only"
        notes.append("Core committee degraded; bundle forces hold-only output.")
    elif degradation_mode == "failed":
        decision_mode = "blocked"
        notes.append("Blocking committee failure; bundle is not executable.")

    def map_amount_from_bucket(size_bucket: str, role: str) -> float:
        lowered = str(size_bucket or "").strip().lower()
        if decision_mode == "hold_only":
            return 0.0
        if role == "core_dca":
            return 0.0
        if lowered in {"0", "hold", "none", ""}:
            return 0.0
        if "300" in lowered or "large" in lowered:
            return 300.0
        if "200" in lowered or "medium" in lowered:
            return 200.0
        if "100" in lowered or "small" in lowered:
            return 100.0
        return 200.0

    fund_decisions = []
    for fund_code, fund in fund_meta.items():
        manager_card = manager_cards.get(fund_code, {})
        risk_card = risk_cards.get(fund_code, {})
        trader_card = trader_cards.get(fund_code, {})
        proposed_action = str(
            trader_card.get("proposed_action")
            or manager_card.get("proposed_action")
            or risk_card.get("proposed_action")
            or "hold"
        )
        if decision_mode == "hold_only":
            proposed_action = "hold"
        size_bucket = str(trader_card.get("size_bucket") or manager_card.get("size_bucket") or risk_card.get("size_bucket") or "0")
        confidence = max(
            float(trader_card.get("confidence", 0.0) or 0.0),
            float(manager_card.get("confidence", 0.0) or 0.0),
            float(risk_card.get("confidence", 0.0) or 0.0),
        )
        supporting_signal_ids = list(
            dict.fromkeys(
                list(trader_card.get("supporting_signal_ids", []) or [])
                + list(manager_card.get("supporting_signal_ids", []) or [])
                + list(risk_card.get("supporting_signal_ids", []) or [])
            )
        )
        opposing_signal_ids = list(
            dict.fromkeys(
                list(trader_card.get("opposing_signal_ids", []) or [])
                + list(manager_card.get("opposing_signal_ids", []) or [])
                + list(risk_card.get("opposing_signal_ids", []) or [])
            )
        )
        original_action = proposed_action
        risk_decision = str(risk_card.get("risk_decision", "") or "")
        risk_action = str(risk_card.get("action_bias") or risk_card.get("proposed_action") or "").strip().lower()
        risk_veto = (
            risk_decision.strip().lower() in {"reject", "veto", "block", "blocked"}
            or risk_action in {"avoid", "reject"}
            or bool(risk_card.get("downgrade_reason"))
            or original_action in {"avoid", "reject"}
        )
        constraint_notes = []
        if risk_veto:
            constraint_notes.append(str(risk_card.get("manager_notes") or risk_card.get("why_not_more") or risk_card.get("why_now") or "").strip())
            proposed_action = "hold"
            size_bucket = "0"
            constraint_notes.append(f"Risk veto forced hold; original proposed_action={original_action}.")
        fund_decisions.append(
            {
                "fund_code": fund_code,
                "fund_name": str(fund.get("fund_name", fund_code) or fund_code),
                "role": str(fund.get("role", "") or ""),
                "proposed_action": proposed_action,
                "size_bucket": size_bucket,
                "suggest_amount": 0.0 if proposed_action == "hold" or risk_veto else map_amount_from_bucket(size_bucket, str(fund.get("role", "") or "")),
                "confidence": round(confidence, 4),
                "thesis": str(
                    trader_card.get("why_now")
                    or manager_card.get("why_now")
                    or manager_card.get("manager_notes")
                    or trader_card.get("manager_notes")
                    or risk_card.get("manager_notes")
                    or ""
                ).strip(),
                "supporting_signal_ids": supporting_signal_ids,
                "opposing_signal_ids": opposing_signal_ids,
                "decision_card_ids": [item for item in [trader_card.get("decision_id"), manager_card.get("decision_id"), risk_card.get("decision_id")] if item],
                "risk_veto": risk_veto,
                "risk_decision": risk_decision,
                "constraint_notes": [item for item in constraint_notes if item],
                "execution_eligible": execution_eligible and not risk_veto,
            }
        )

    return {
        "schema_version": 1,
        "report_date": str(aggregate.get("report_date", "") or ""),
        "generated_at": timestamp_now(),
        "decision_mode": decision_mode,
        "decision_source": str((aggregate.get("committee", {}) or {}).get("decision_source", "") or "committee_canonical"),
        "degradation_mode": degradation_mode,
        "execution_eligible": execution_eligible,
        "committee_confidence": str((aggregate.get("committee", {}) or {}).get("committee_confidence", "") or "low"),
        "manager_order": [name for name in DEFAULT_MANAGER_ORDER if name in (aggregate.get("ordered_agents", []) or [])],
        "fund_decisions": fund_decisions,
        "market_view": dict(trader.get("portfolio_view") or manager.get("portfolio_view") or risk.get("portfolio_view") or {}),
        "cross_fund_observations": _sanitize_string_list(
            list(trader.get("watchouts", []) or []) + list(risk.get("watchouts", []) or []) + list(manager.get("watchouts", []) or []),
            limit=8,
        ),
        "risk_vetoes": list((aggregate.get("committee", {}) or {}).get("risk_vetoes", []) or []),
        "failed_agent_names": failed_agent_names,
        "degraded_agent_names": degraded_agent_names,
        "notes": notes,
    }


def _normalize_text_line(value: str) -> str:
    return " ".join(str(value).replace("\u3000", " ").split()).strip()


def _sanitize_string_list(values, limit: int | None = None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        text = _normalize_text_line(item)
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if limit is not None and len(cleaned) >= limit:
            break
    return cleaned
