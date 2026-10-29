from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from artifact_boundary import assert_refactor_write_allowed, relative_posix
from common import dump_json, load_json, load_strategy, resolve_agent_home, resolve_date, timestamp_now, validated_advice_path
from build_action_ticket_shadow import load_portfolio_state_for_report
from promoted_advice_guardrails import build_validated_payload
from simulation_policy import strictest_state, state_allows_trade


SCHEMA_VERSION = "official_advice_compat_preview.v1"
PREVIEW_SLUG = "official_advice_compat_preview"
ACTION_SECTIONS = ("tactical_actions", "dca_actions", "hold_actions")
REQUIRED_COMMITTEE_DECISION_FIELDS = {
    "fund_code",
    "fund_name",
    "role",
    "proposed_action",
    "size_bucket",
    "suggest_amount",
    "requested_amount",
    "validated_amount",
    "confidence",
    "thesis",
    "supporting_signal_ids",
    "opposing_signal_ids",
    "decision_card_ids",
    "risk_veto",
    "risk_decision",
    "constraint_notes",
    "execution_eligible",
}
REQUIRED_FINAL_DECISION_FIELDS = {
    "fund_code",
    "action",
    "suggest_amount",
    "requested_amount",
    "priority",
    "confidence",
    "thesis",
    "evidence",
    "risks",
    "agent_support",
    "source_signal_ids",
    "opposing_signal_ids",
    "decision_trace",
}
REQUIRED_VALIDATED_ACTION_FIELDS = {
    "suggestion_id",
    "fund_code",
    "fund_name",
    "validated_action",
    "validated_amount",
    "requested_amount",
    "model_action",
    "confidence",
    "thesis",
    "policy_rule_hits",
    "constraint_hits",
    "validation_notes",
    "execution_status",
    "source_signal_ids",
    "opposing_signal_ids",
    "cash_impact",
    "allocation_impact",
}


class CompatPreviewError(ValueError):
    pass


def action_ticket_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "action_tickets" / f"{report_date}.json"


def retrieval_pack_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "retrieval_packs" / f"{report_date}.json"


def action_debate_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "action_debates" / f"{report_date}.json"


def preview_dir(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "refactor_shadow_runs" / f"{report_date}__{PREVIEW_SLUG}"


def preview_path(agent_home: Path, report_date: str) -> Path:
    return preview_dir(agent_home, report_date) / f"{PREVIEW_SLUG}.json"


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_dict(path: Path, artifact_name: str) -> dict[str, Any]:
    if not path.exists():
        raise CompatPreviewError(f"missing {artifact_name}: {path}")
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise CompatPreviewError(f"{artifact_name} root must be a JSON object: {path}")
    return payload


def load_optional_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def source_hash_for(artifact: dict[str, Any], relative_path: str) -> str:
    for item in artifact.get("source_artifacts", []) or []:
        if isinstance(item, dict) and item.get("path") == relative_path:
            return str(item.get("content_sha256", "") or "")
    return ""


def validate_root_contract(artifact: dict[str, Any], *, report_date: str, schema_version: str, artifact_name: str) -> None:
    if artifact.get("schema_version") != schema_version:
        raise CompatPreviewError(f"{artifact_name} schema mismatch: {artifact.get('schema_version')!r}")
    if artifact.get("report_date") != report_date:
        raise CompatPreviewError(f"{artifact_name} report_date mismatch: {artifact.get('report_date')!r}")
    if artifact.get("write_scope") != "shadow_only":
        raise CompatPreviewError(f"{artifact_name} write_scope must be shadow_only")
    if artifact.get("non_executable") is not True:
        raise CompatPreviewError(f"{artifact_name} non_executable must be true")


def validate_source_hash(artifact: dict[str, Any], source_path: Path, agent_home: Path, *, artifact_name: str, source_name: str) -> None:
    relative = relative_posix(source_path, agent_home)
    expected = content_sha256(source_path)
    actual = source_hash_for(artifact, relative)
    if actual != expected:
        raise CompatPreviewError(
            f"{artifact_name} source {source_name} hash mismatch: expected {expected}, got {actual or '<missing>'}"
        )


def validate_chain_contracts(
    *,
    agent_home: Path,
    report_date: str,
    ticket_path: Path,
    retrieval_path: Path,
    debate_path: Path,
    ticket_artifact: dict[str, Any],
    retrieval_artifact: dict[str, Any],
    debate_artifact: dict[str, Any],
) -> None:
    validate_root_contract(ticket_artifact, report_date=report_date, schema_version="action_ticket.v1", artifact_name="action_ticket")
    validate_root_contract(retrieval_artifact, report_date=report_date, schema_version="retrieval_pack.v1", artifact_name="retrieval_pack")
    validate_root_contract(debate_artifact, report_date=report_date, schema_version="action_debate.v1", artifact_name="action_debate")
    validate_source_hash(retrieval_artifact, ticket_path, agent_home, artifact_name="retrieval_pack", source_name="action_ticket")
    validate_source_hash(debate_artifact, ticket_path, agent_home, artifact_name="action_debate", source_name="action_ticket")
    validate_source_hash(debate_artifact, retrieval_path, agent_home, artifact_name="action_debate", source_name="retrieval_pack")

    ticket_ids = {str(item.get("ticket_id", "")) for item in ticket_artifact.get("tickets", []) or [] if isinstance(item, dict)}
    pack_ticket_ids = {
        str((item.get("target", {}) or {}).get("ticket_id", ""))
        for item in retrieval_artifact.get("packs", []) or []
        if isinstance(item, dict)
    }
    debate_ticket_ids = {
        str(item.get("ticket_id", ""))
        for item in debate_artifact.get("debates", []) or []
        if isinstance(item, dict)
    }
    ticket_ids.discard("")
    pack_ticket_ids.discard("")
    debate_ticket_ids.discard("")
    if not ticket_ids:
        raise CompatPreviewError("action_ticket contains no tickets")
    if ticket_ids != pack_ticket_ids:
        raise CompatPreviewError("retrieval_pack ticket ids do not match action_ticket ids")
    if ticket_ids != debate_ticket_ids:
        raise CompatPreviewError("action_debate ticket ids do not match action_ticket ids")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def stable_list(values: list[Any], *, limit: int = 12) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def size_bucket_for(amount: float, fallback: Any = "") -> str:
    text = str(fallback or "").strip()
    if text:
        return text
    if amount <= 0:
        return "0"
    if amount <= 50:
        return "small"
    if amount <= 200:
        return "medium"
    return "large"


def guardrail_rule_ids(ticket: dict[str, Any], results: set[str] | None = None) -> list[str]:
    ids: list[str] = []
    for item in ticket.get("hard_guardrail_results", []) or []:
        if not isinstance(item, dict):
            continue
        if results is not None and item.get("result") not in results:
            continue
        rule_id = str(item.get("rule_id", "") or "").strip()
        if rule_id:
            ids.append(rule_id)
    return stable_list(ids)


def guardrail_notes(ticket: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    for item in ticket.get("hard_guardrail_results", []) or []:
        if not isinstance(item, dict):
            continue
        result = str(item.get("result", "") or "")
        if result in {"pass", ""}:
            continue
        rule_id = str(item.get("rule_id", "") or "guardrail")
        reason = str(item.get("status_reason", "") or result)
        notes.append(f"{rule_id}: {result} - {reason}")
    for item in ticket.get("soft_policy_adjustments", []) or []:
        if not isinstance(item, dict):
            continue
        policy_id = str(item.get("policy_id", "") or "soft_policy")
        effect = str(item.get("effect_type", "") or "note")
        reason = str(item.get("reason", "") or item.get("effect_value", "") or "")
        notes.append(f"{policy_id}: {effect} - {reason}".strip())
    return stable_list(notes)


def first_summary(items: list[dict[str, Any]], limit: int = 4) -> list[str]:
    values: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            values.append(item.get("summary"))
    return stable_list(values, limit=limit)


def packs_by_ticket_id(retrieval_artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for pack in retrieval_artifact.get("packs", []) or []:
        if not isinstance(pack, dict):
            continue
        target = pack.get("target", {}) if isinstance(pack.get("target"), dict) else {}
        ticket_id = str(target.get("ticket_id", "") or "")
        if ticket_id:
            result[ticket_id] = pack
    return result


def debates_by_ticket_id(debate_artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("ticket_id", "")): item
        for item in debate_artifact.get("debates", []) or []
        if isinstance(item, dict) and item.get("ticket_id")
    }


def official_actions(validated: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for section in ACTION_SECTIONS:
        for index, item in enumerate(validated.get(section, []) or []):
            if isinstance(item, dict):
                copied = dict(item)
                copied["_section"] = section
                copied["_index"] = index
                actions.append(copied)
    return actions


def evidence_ids(ticket: dict[str, Any], pack: dict[str, Any], key: str) -> list[str]:
    refs = ticket.get(key, []) or []
    values = [item.get("ref_id") for item in refs if isinstance(item, dict)]
    if key == "supporting_evidence_refs":
        values.extend(item.get("item_id") for item in pack.get("derived_signals", []) or [] if isinstance(item, dict))
    else:
        values.extend(item.get("item_id") for item in pack.get("anti_patterns", []) or [] if isinstance(item, dict))
    return stable_list(values)


def debate_outputs(debate: dict[str, Any]) -> dict[str, Any]:
    return debate.get("node_outputs", {}) if isinstance(debate.get("node_outputs"), dict) else {}


def preview_confidence(ticket: dict[str, Any], debate: dict[str, Any]) -> float:
    outputs = debate_outputs(debate)
    writer = outputs.get("ticket_writer", {}) if isinstance(outputs.get("ticket_writer"), dict) else {}
    patch = writer.get("proposed_ticket_patch", {}) if isinstance(writer.get("proposed_ticket_patch"), dict) else {}
    if "confidence" in patch:
        return round(max(0.0, min(1.0, safe_float(patch.get("confidence")))), 4)
    return round(max(0.0, min(1.0, safe_float(ticket.get("confidence")))), 4)


def debate_summary(debate: dict[str, Any]) -> str:
    outputs = debate_outputs(debate)
    referee = outputs.get("debate_referee", {}) if isinstance(outputs.get("debate_referee"), dict) else {}
    summary = str(referee.get("summary", "") or "").strip()
    if summary:
        return summary
    former = outputs.get("action_former", {}) if isinstance(outputs.get("action_former"), dict) else {}
    return str(former.get("reason", "") or "").strip()


def effective_debate_state(ticket: dict[str, Any], debate: dict[str, Any]) -> str:
    """原 ticket / debate 自身 / former.target_status 三方取最严（契约 §5，fail-closed）。

    修复 P1 端到端闭合：此前投影只读原 ticket_status + hard_gate，
    referee/former 产出的 degraded/blocked 被丢弃，导致软降级照样下单。
    """
    outputs = debate_outputs(debate)
    former = outputs.get("action_former", {}) if isinstance(outputs.get("action_former"), dict) else {}
    former_state = former.get("target_status") if isinstance(former, dict) else None
    return strictest_state(ticket.get("ticket_status"), debate.get("ticket_status"), former_state)


def risk_veto_for(ticket: dict[str, Any], debate: dict[str, Any]) -> bool:
    if not state_allows_trade(effective_debate_state(ticket, debate)):
        return True
    outputs = debate_outputs(debate)
    guardrail = outputs.get("hard_guardrail_check", {}) if isinstance(outputs.get("hard_guardrail_check"), dict) else {}
    return str(guardrail.get("result", "") or "") == "block" or safe_float(guardrail.get("block_count")) > 0


def compact_decision_trace(ticket: dict[str, Any], pack: dict[str, Any], debate: dict[str, Any]) -> dict[str, Any]:
    return {
        "fund_code": str(ticket.get("fund_code", "") or ""),
        "supporting_signal_ids": evidence_ids(ticket, pack, "supporting_evidence_refs"),
        "opposing_signal_ids": evidence_ids(ticket, pack, "opposing_evidence_refs"),
        "decision_card_ids": stable_list([ticket.get("ticket_id"), pack.get("pack_id"), debate.get("debate_id")]),
        "constraint_hits": guardrail_rule_ids(ticket, {"adjust", "block", "not_checked"}),
    }


def tactical_amount_cap(strategy: dict[str, Any] | None, action: str) -> float | None:
    if not isinstance(strategy, dict) or action not in {"add", "reduce", "switch_out"}:
        return None
    tactical = strategy.get("tactical", {}) if isinstance(strategy.get("tactical"), dict) else {}
    key = "max_add_amount" if action == "add" else "max_reduce_amount"
    value = tactical.get(key)
    try:
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def build_committee_decision(
    ticket: dict[str, Any],
    pack: dict[str, Any],
    debate: dict[str, Any],
    priority: int,
    *,
    strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    amount = safe_float(ticket.get("validated_amount"))
    requested_amount = amount
    veto = risk_veto_for(ticket, debate)
    action = str(ticket.get("action_verb", "hold") or "hold")
    former = (debate_outputs(debate).get("action_former", {}) or {}) if isinstance(debate_outputs(debate).get("action_former", {}), dict) else {}
    if str(ticket.get("role", "") or "") == "tactical":
        proposed_action = str(former.get("action", former.get("action_verb", "")) or "").strip().lower()
        if proposed_action in {"add", "reduce", "switch_out", "hold", "watch"}:
            action = proposed_action
            if action == "hold":
                amount = 0.0
            elif former.get("size_tier"):
                # simulation_v2：LLM 只给方向+tier，金额由 guardrails 按冻结 basis 换算（此处不截固定额）。
                amount = 0.0
            elif "amount" in former:
                requested_amount = max(0.0, safe_float(former.get("amount")))
                amount = requested_amount
                cap = tactical_amount_cap(strategy, action)
                if cap is not None and amount > cap:
                    amount = cap
    notes = guardrail_notes(ticket)
    if action != "hold" and round(requested_amount, 2) != round(amount, 2):
        notes.append(f"tactical_amount_cap: requested={requested_amount:.2f}, validated={amount:.2f}")
    debate_note = debate_summary(debate)
    if debate_note:
        notes.append(f"debate_referee: {debate_note}")
    return {
        "fund_code": str(ticket.get("fund_code", "") or ""),
        "fund_name": str(ticket.get("fund_name", "") or ""),
        "role": str(ticket.get("role", "") or ""),
        "proposed_action": action,
        "proposed_amount_source": "action_former" if str(ticket.get("role", "") or "") == "tactical" and former.get("action") else "ticket",
        "requested_amount": requested_amount,
        "validated_amount": amount if action != "hold" else 0.0,
        "size_tier": str(former.get("size_tier", "none") or "none") if str(ticket.get("role", "") or "") == "tactical" else "none",
        "horizon": str(former.get("horizon", "unspecified") or "unspecified"),
        "evidence_quality": str(former.get("evidence_quality", "unavailable") or "unavailable"),
        "size_bucket": size_bucket_for(amount, ticket.get("size_bucket")),
        "suggest_amount": amount if action != "hold" else 0.0,
        "confidence": preview_confidence(ticket, debate),
        "thesis": str(ticket.get("thesis", "") or "Shadow ticket did not provide a thesis."),
        "supporting_signal_ids": evidence_ids(ticket, pack, "supporting_evidence_refs"),
        "opposing_signal_ids": evidence_ids(ticket, pack, "opposing_evidence_refs"),
        "decision_card_ids": stable_list([ticket.get("ticket_id"), pack.get("pack_id"), debate.get("debate_id")]),
        "risk_veto": veto,
        "risk_decision": "blocked_by_shadow_guardrail" if veto else "shadow_guardrails_passed",
        "constraint_notes": stable_list(notes, limit=16),
        "execution_eligible": bool(action != "hold" and not veto),
        "priority": priority,
        "source_ticket_id": str(ticket.get("ticket_id", "") or ""),
        "source_pack_id": str(pack.get("pack_id", "") or ""),
        "source_debate_id": str(debate.get("debate_id", "") or ""),
    }


def build_final_decision(committee_decision: dict[str, Any], ticket: dict[str, Any], pack: dict[str, Any], debate: dict[str, Any]) -> dict[str, Any]:
    action = str(committee_decision.get("proposed_action", "hold") or "hold")
    if committee_decision.get("risk_veto") or committee_decision.get("execution_eligible") is False:
        action = "hold"
    support_summaries = first_summary(ticket.get("supporting_evidence_refs", []) or [], 3)
    support_summaries.extend(first_summary(pack.get("derived_signals", []) or [], 3))
    risk_summaries = first_summary(ticket.get("opposing_evidence_refs", []) or [], 3)
    risk_summaries.extend(first_summary(pack.get("anti_patterns", []) or [], 3))
    return {
        "fund_code": committee_decision["fund_code"],
        "action": action,
        "suggest_amount": safe_float(committee_decision.get("suggest_amount")) if action != "hold" else 0.0,
        "requested_amount": safe_float(committee_decision.get("requested_amount")),
        "validated_amount": safe_float(committee_decision.get("validated_amount")) if action != "hold" else 0.0,
        "priority": int(committee_decision.get("priority", 999) or 999),
        "confidence": committee_decision["confidence"],
        "thesis": committee_decision["thesis"],
        "evidence": stable_list(support_summaries + committee_decision.get("constraint_notes", []), limit=12),
        "risks": stable_list(risk_summaries + ([committee_decision.get("risk_decision")] if committee_decision.get("risk_veto") else []), limit=8),
        "agent_support": ["action_ticket_shadow", "layered_retrieval_pack", "action_debate_shadow"],
        "source_signal_ids": committee_decision["supporting_signal_ids"],
        "opposing_signal_ids": committee_decision["opposing_signal_ids"],
        "decision_trace": compact_decision_trace(ticket, pack, debate),
    }


def build_validated_action_preview(ticket: dict[str, Any], final_decision: dict[str, Any]) -> dict[str, Any]:
    action = str(final_decision.get("action", "hold") or "hold")
    legacy = ticket.get("legacy_mapping", {}) if isinstance(ticket.get("legacy_mapping"), dict) else {}
    amount = safe_float(final_decision.get("suggest_amount")) if action != "hold" else 0.0
    bucket = str(ticket.get("portfolio_bucket", "") or "unknown_bucket")
    return {
        "suggestion_id": str(legacy.get("suggestion_id", "") or f"{ticket.get('report_date')}:{ticket.get('fund_code')}:{action}"),
        "fund_code": str(ticket.get("fund_code", "") or ""),
        "fund_name": str(ticket.get("fund_name", "") or ""),
        "strategy_bucket": bucket,
        "validated_action": action,
        "validated_amount": amount,
        "requested_amount": safe_float(final_decision.get("requested_amount")),
        "model_action": str(legacy.get("model_action", "") or ticket.get("action_verb", "") or action),
        "priority": int(final_decision.get("priority", 999) or 999),
        "confidence": safe_float(final_decision.get("confidence")),
        "thesis": str(final_decision.get("thesis", "") or ""),
        "evidence": list(final_decision.get("evidence", []) or []),
        "risks": list(final_decision.get("risks", []) or []),
        "agent_support": list(final_decision.get("agent_support", []) or []),
        "source_signal_ids": list(final_decision.get("source_signal_ids", []) or []),
        "opposing_signal_ids": list(final_decision.get("opposing_signal_ids", []) or []),
        "policy_rule_hits": [item.get("policy_id") for item in ticket.get("soft_policy_adjustments", []) or [] if isinstance(item, dict)],
        "constraint_hits": guardrail_rule_ids(ticket, {"adjust", "block"}),
        "allocation_impact": f"{bucket}:shadow_preview_no_official_allocation_mutation",
        "cash_impact": f"shadow_preview_amount={amount:.2f}; no official cash mutation",
        "validation_notes": guardrail_notes(ticket),
        "execution_status": "pending" if action != "hold" else "not_applicable",
        "executed_amount": 0.0,
        "legacy_source_bucket": str(legacy.get("source_bucket", "") or ""),
        "legacy_source_index": int(legacy.get("source_index", 999) if legacy.get("source_index") is not None else 999),
    }


def group_validated_sections(preview_actions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    sections = {"tactical_actions": [], "dca_actions": [], "hold_actions": []}
    for action in preview_actions:
        validated_action = str(action.get("validated_action", "") or "")
        if validated_action == "scheduled_dca":
            sections["dca_actions"].append(action)
        elif validated_action == "hold":
            sections["hold_actions"].append(action)
        else:
            sections["tactical_actions"].append(action)
    for section in sections:
        sections[section].sort(key=lambda item: (int(item.get("legacy_source_index", 999) if item.get("legacy_source_index") is not None else 999), int(item.get("priority", 999) or 999), str(item.get("fund_code", ""))))
    return sections


def replayable_validated_sections(section_preview: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {
        section: [dict(item) for item in section_preview.get(section, []) or [] if isinstance(item, dict)]
        for section in ACTION_SECTIONS
    }


def market_view_preview(
    validated: dict[str, Any],
    report_date: str,
    decision_count: int,
    *,
    promoted_run: bool = False,
    is_mock: bool = False,
) -> dict[str, Any]:
    base = dict(validated.get("market_view", {}) or {})
    base.setdefault("regime", "mixed")
    if promoted_run and not is_mock:
        base["summary"] = f"Promoted action-ticket chain produced official advice for {report_date}; decisions={decision_count}."
    elif promoted_run:
        base["summary"] = f"Mock action-ticket chain produced non-executable test advice for {report_date}; decisions={decision_count}."
    else:
        base["summary"] = (
            "Shadow action-ticket chain produced an adapter-shape advice preview "
            f"for {report_date}; decisions={decision_count}. This preview is non-executable."
        )
    drivers = list(base.get("key_drivers", []) or [])
    drivers.append("source_chain=action_ticket->retrieval_pack->action_debate")
    base["key_drivers"] = stable_list(drivers, limit=8)
    return base


def preview_sections_as_validated_payload(
    *,
    agent_home: Path,
    report_date: str,
    validated: dict[str, Any],
    committee_bundle: dict[str, Any],
    final_advice: dict[str, Any],
    section_preview: dict[str, list[dict[str, Any]]],
    is_mock: bool = False,
) -> dict[str, Any]:
    try:
        _portfolio_path, portfolio = load_portfolio_state_for_report(agent_home, report_date, allow_prior_current=True)
    except Exception:
        portfolio = {}
    fixed_dca_total = round(sum(safe_float(item.get("validated_amount")) for item in section_preview.get("dca_actions", []) or []), 2)
    return {
        "report_date": report_date,
        "generated_at": committee_bundle.get("generated_at", ""),
        "portfolio_name": portfolio.get("portfolio_name", ""),
        "risk_profile": validated.get("risk_profile", ""),
        "daily_max_trade_amount": validated.get("daily_max_trade_amount", 0.0),
        "daily_max_gross_trade_amount": validated.get("daily_max_gross_trade_amount", validated.get("daily_max_trade_amount", 0.0)),
        "daily_max_net_buy_amount": validated.get("daily_max_net_buy_amount", validated.get("daily_max_trade_amount", 0.0)),
        "fixed_dca_total": fixed_dca_total,
        "remaining_budget_after_validation": validated.get("remaining_budget_after_validation", 0.0),
        "remaining_gross_trade_budget_after_validation": validated.get("remaining_gross_trade_budget_after_validation", 0.0),
        "remaining_net_buy_budget_after_validation": validated.get("remaining_net_buy_budget_after_validation", 0.0),
        "cash_hub_available": validated.get("cash_hub_available", 0.0),
        "immediately_available_cash": validated.get("immediately_available_cash", 0.0),
        "delayed_sell_proceeds": validated.get("delayed_sell_proceeds", 0.0),
        "market_view": final_advice.get("market_view", {}),
        "cross_fund_observations": final_advice.get("cross_fund_observations", []),
        "allocation_plan": validated.get("allocation_plan", {}),
        "strategy_bucket_summary": validated.get("strategy_bucket_summary", []),
        "advice_mode": "action_debate_mock" if is_mock else "action_debate_promoted_preview",
        "advice_is_fallback": False,
        "advice_is_mock": is_mock,
        "decision_source": committee_bundle.get("decision_source", "action_debate_shadow_compat_preview"),
        "decision_mode": committee_bundle.get("decision_mode", "canonical"),
        "degradation_mode": committee_bundle.get("degradation_mode", "none"),
        "execution_eligible": committee_bundle.get("execution_eligible", True),
        "committee": {},
        "committee_decision_bundle": committee_bundle,
        "risk_vetoes": committee_bundle.get("risk_vetoes", []),
        "committee_confidence": committee_bundle.get("committee_confidence", ""),
        "narrative_mode": "action_debate_promoted_preview",
        "transport_name": "",
        "failed_agents": [],
        "optimization_summary": {
            "mode": "action_debate_preview",
            "candidate_count": len(final_advice.get("fund_decisions", []) or []),
            "selected_candidate_count": len(section_preview.get("tactical_actions", []) or []),
        },
        "optimizer_candidates": [],
        "optimizer_best_combo_metrics": {},
        "recommendation_deltas": [],
        "dca_actions": section_preview.get("dca_actions", []),
        "tactical_actions": section_preview.get("tactical_actions", []),
        "hold_actions": section_preview.get("hold_actions", []),
    }


def compare_to_official(validated: dict[str, Any], final_decisions: list[dict[str, Any]]) -> dict[str, Any]:
    if not validated:
        return {"status": "not_available", "detail": "validated_advice artifact is missing"}
    official_by_code = {
        str(item.get("fund_code", "") or ""): item
        for item in official_actions(validated)
        if item.get("fund_code")
    }
    preview_by_code = {
        str(item.get("fund_code", "") or ""): item
        for item in final_decisions
        if item.get("fund_code")
    }
    codes = sorted(set(official_by_code) | set(preview_by_code))
    mismatches = []
    for code in codes:
        official = official_by_code.get(code, {})
        preview = preview_by_code.get(code, {})
        official_action = str(official.get("validated_action", "") or "")
        preview_action = str(preview.get("action", "") or "")
        official_amount = safe_float(official.get("validated_amount"))
        preview_amount = safe_float(preview.get("suggest_amount"))
        if official_action != preview_action or round(official_amount, 2) != round(preview_amount, 2):
            mismatches.append(
                {
                    "fund_code": code,
                    "official_action": official_action,
                    "preview_action": preview_action,
                    "official_amount": official_amount,
                    "preview_amount": preview_amount,
                }
            )
    return {
        "status": "compared",
        "official_action_count": len(official_by_code),
        "preview_decision_count": len(preview_by_code),
        "matched_count": len(codes) - len(mismatches),
        "mismatched_count": len(mismatches),
        "mismatches": mismatches[:20],
    }


def validated_advice_is_comparable(candidate: dict[str, Any], official: dict[str, Any]) -> bool:
    if not candidate or not official:
        return False
    candidate_sections = {
        section: [
            {
                "fund_code": item.get("fund_code"),
                "validated_action": item.get("validated_action"),
                "validated_amount": round(safe_float(item.get("validated_amount")), 2),
            }
            for item in candidate.get(section, []) or []
            if isinstance(item, dict)
        ]
        for section in ACTION_SECTIONS
    }
    official_sections = {
        section: [
            {
                "fund_code": item.get("fund_code"),
                "validated_action": item.get("validated_action"),
                "validated_amount": round(safe_float(item.get("validated_amount")), 2),
            }
            for item in official.get(section, []) or []
            if isinstance(item, dict)
        ]
        for section in ACTION_SECTIONS
    }
    return candidate_sections == official_sections


def dry_run_official_validator(agent_home: Path, report_date: str, committee_bundle: dict[str, Any], final_advice: dict[str, Any], official: dict[str, Any]) -> dict[str, Any]:
    try:
        _portfolio_path, portfolio = load_portfolio_state_for_report(agent_home, report_date, allow_prior_current=True)
        candidate = build_validated_payload(
            agent_home,
            report_date,
            portfolio=portfolio,
            advice=final_advice,
            llm_raw={"mode": "action_debate_promoted_preview", "committee_decision_bundle": committee_bundle},
            committee_bundle=committee_bundle,
            previous_actions={},
        )
    except Exception as exc:  # pragma: no cover - exact validator failures are surfaced in payload.
        return {
            "passed": False,
            "error": str(exc),
            "comparable_to_official": False,
        }
    return {
        "passed": True,
        "error": "",
        "comparable_to_official": validated_advice_is_comparable(candidate, official),
    }


def historical_compat_replay_is_comparable(committee_bundle: dict[str, Any], official: dict[str, Any]) -> bool:
    replay_sections = committee_bundle.get("validated_action_sections_replay")
    if not isinstance(replay_sections, dict):
        return False
    candidate = {section: replay_sections.get(section, []) for section in ACTION_SECTIONS}
    return validated_advice_is_comparable(candidate, official)


def source_hashes_present(payload: dict[str, Any]) -> bool:
    for item in payload.get("source_artifacts", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "builder":
            continue
        if not str(item.get("content_sha256", "") or ""):
            return False
    return True


def missing_required_fields(items: list[dict[str, Any]], required: set[str], item_name: str) -> list[str]:
    missing: list[str] = []
    for index, item in enumerate(items):
        for field in sorted(required):
            if field not in item:
                missing.append(f"{item_name}[{index}].{field}")
    return missing


def source_artifacts(agent_home: Path, paths: list[Path]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        artifacts.append(
            {
                "kind": path.parent.name,
                "path": relative_posix(path, agent_home),
                "content_sha256": content_sha256(path),
            }
        )
    artifacts.append({"kind": "builder", "path": "scripts/build_official_advice_compat_preview.py", "content_sha256": ""})
    return artifacts


def build_preview_payload(
    agent_home: Path,
    report_date: str,
    *,
    generated_at: str | None = None,
    promoted_run: bool = False,
    is_mock: bool = False,
) -> dict[str, Any]:
    generated_at = generated_at or timestamp_now()
    ticket_file = action_ticket_path(agent_home, report_date)
    retrieval_file = retrieval_pack_path(agent_home, report_date)
    debate_file = action_debate_path(agent_home, report_date)
    validated_file = validated_advice_path(agent_home, report_date)
    ticket_artifact = load_json_dict(ticket_file, "action_ticket")
    retrieval_artifact = load_json_dict(retrieval_file, "retrieval_pack")
    debate_artifact = load_json_dict(debate_file, "action_debate")
    validated = load_optional_json_dict(validated_file)
    strategy = load_strategy(agent_home)
    validate_chain_contracts(
        agent_home=agent_home,
        report_date=report_date,
        ticket_path=ticket_file,
        retrieval_path=retrieval_file,
        debate_path=debate_file,
        ticket_artifact=ticket_artifact,
        retrieval_artifact=retrieval_artifact,
        debate_artifact=debate_artifact,
    )

    pack_map = packs_by_ticket_id(retrieval_artifact)
    debate_map = debates_by_ticket_id(debate_artifact)
    official_bundle = validated.get("committee_decision_bundle", {}) if isinstance(validated.get("committee_decision_bundle"), dict) else {}
    if promoted_run:
        root_decision_mode = "hold_only" if is_mock else "canonical"
        root_execution_eligible = not is_mock
    else:
        root_decision_mode = str(official_bundle.get("decision_mode", "") or validated.get("decision_mode", "") or "adapter_shape_preview")
        root_execution_eligible = bool(official_bundle.get("execution_eligible", validated.get("execution_eligible", False)))
    committee_decisions: list[dict[str, Any]] = []
    final_decisions: list[dict[str, Any]] = []
    validated_action_previews: list[dict[str, Any]] = []
    tickets = [item for item in ticket_artifact.get("tickets", []) or [] if isinstance(item, dict)]
    tickets.sort(key=lambda item: (int((item.get("legacy_mapping", {}) or {}).get("priority", 999) or 999), str(item.get("fund_code", ""))))
    for priority, ticket in enumerate(tickets, start=1):
        ticket_id = str(ticket.get("ticket_id", "") or "")
        pack = pack_map.get(ticket_id, {})
        debate = debate_map.get(ticket_id, {})
        committee_decision = build_committee_decision(ticket, pack, debate, priority, strategy=strategy)
        if is_mock:
            committee_decision["execution_eligible"] = False
            committee_decision["constraint_notes"] = stable_list(
                list(committee_decision.get("constraint_notes", []) or []) + ["Mock debate output is never execution eligible."],
                limit=16,
            )
        final_decision = build_final_decision(committee_decision, ticket, pack, debate)
        committee_decisions.append(committee_decision)
        final_decisions.append(final_decision)
        validated_action_previews.append(build_validated_action_preview(ticket, final_decision))

    # simulation_v2：promoted 运行即新建议 schema（不按当天是否有交易 tier 判定）；
    # 仅 shadow preview / 旧真 artifact 保持 legacy schema。
    _v2 = bool(promoted_run)
    committee_bundle_preview = {
        "schema_version": ("simulation_v2" if _v2 else 1),
        "report_date": report_date,
        "generated_at": generated_at,
        "decision_mode": root_decision_mode,
        "decision_source": "action_debate_shadow_compat_preview",
        "degradation_mode": str(official_bundle.get("degradation_mode", "") or ("none" if debate_artifact.get("summary", {}).get("status") == "ok" else "shadow_degraded")),
        "execution_eligible": root_execution_eligible,
        "is_mock": is_mock,
        "committee_confidence": "mock" if is_mock else ("promoted" if promoted_run else "preview"),
        "manager_order": ["action_ticket_shadow", "layered_retrieval_pack", "action_debate_shadow"],
        "fund_decisions": committee_decisions,
        "market_view": market_view_preview(
            validated,
            report_date,
            len(final_decisions),
            promoted_run=promoted_run,
            is_mock=is_mock,
        ),
        "cross_fund_observations": (
            [
                "Mock debate result is non-executable and must not be used for trading.",
                "Official-shaped artifacts are isolated by explicit is_mock and production_eligible flags.",
            ]
            if promoted_run and is_mock
            else [
                "Promoted action-ticket chain wrote the official advice contracts.",
                "Execution remains subject to validated portfolio and fund-level guardrails.",
            ]
            if promoted_run
            else [
                "Compatibility preview only; not written to db/committee_decision_bundle or db/llm_advice.",
                "Official validator, optimizer, ledger, execution sync, and long memory are unchanged.",
            ]
        ),
        "risk_vetoes": [
            {
                "fund_code": item["fund_code"],
                "risk_decision": item["risk_decision"],
                "constraint_notes": item["constraint_notes"],
            }
            for item in committee_decisions
            if item.get("risk_veto")
        ],
        "failed_agent_names": [],
        "degraded_agent_names": [],
        "notes": [
            "Mock promoted run; execution is disabled."
            if promoted_run and is_mock
            else "Promoted run passed the official-output gate."
            if promoted_run
            else "Generated from shadow artifacts under a non-executable adapter_shape_preview boundary."
        ],
    }
    final_advice_preview = {
        "schema_version": ("simulation_v2" if _v2 else 1),
        "market_view": committee_bundle_preview["market_view"],
        "fund_decisions": final_decisions,
        "cross_fund_observations": committee_bundle_preview["cross_fund_observations"],
    }
    section_preview = group_validated_sections(validated_action_previews)
    committee_bundle_preview["validated_action_sections_replay"] = replayable_validated_sections(section_preview)
    committee_bundle_preview["validated_action_sections_replay_scope"] = "promoted_preview_only"
    missing_fields = missing_required_fields(committee_decisions, REQUIRED_COMMITTEE_DECISION_FIELDS, "committee_decision")
    missing_fields.extend(missing_required_fields(final_decisions, REQUIRED_FINAL_DECISION_FIELDS, "final_decision"))
    missing_fields.extend(missing_required_fields(validated_action_previews, REQUIRED_VALIDATED_ACTION_FIELDS, "validated_action_preview"))
    comparison = compare_to_official(validated, final_decisions)
    source_hash_ok = source_hashes_present({"source_artifacts": source_artifacts(agent_home, [ticket_file, retrieval_file, debate_file, validated_file])})
    shape_compatible = not missing_fields
    behavior_comparable = comparison.get("status") == "compared" and int(comparison.get("mismatched_count", 0) or 0) == 0
    validator_dry_run = dry_run_official_validator(agent_home, report_date, committee_bundle_preview, final_advice_preview, validated)
    historical_replay_comparable = historical_compat_replay_is_comparable(committee_bundle_preview, validated)
    preview_validated_payload = preview_sections_as_validated_payload(
        agent_home=agent_home,
        report_date=report_date,
        validated=validated,
        committee_bundle=committee_bundle_preview,
        final_advice=final_advice_preview,
        section_preview=section_preview,
        is_mock=is_mock,
    )
    adapter_dry_run_passed = bool(
        shape_compatible
        and (
            (validator_dry_run.get("passed") and (validator_dry_run.get("comparable_to_official") or historical_replay_comparable))
            or comparison.get("status") == "not_available"
        )
    )
    fallback_switch_active = False
    official_compatible = shape_compatible and behavior_comparable and adapter_dry_run_passed and source_hash_ok
    summary = {
        "status": "ok" if not missing_fields else "degraded",
        "ticket_count": len(tickets),
        "committee_decision_count": len(committee_decisions),
        "final_advice_decision_count": len(final_decisions),
        "validated_section_preview_count": sum(len(items) for items in section_preview.values()),
        "official_shape_compatible": shape_compatible,
        "official_behavior_comparable": behavior_comparable,
        "official_adapter_dry_run_passed": adapter_dry_run_passed,
        "source_hash_verified": source_hash_ok,
        "official_compatible_advice": official_compatible,
        "committee_bundle_compatible": shape_compatible,
        "llm_advice_compatible": shape_compatible,
        "validated_sections_preview_only": True,
        "fallback_switch_active": fallback_switch_active,
        "promotion_ready": False,
        "official_output_unchanged": True,
        "official_paths_written": [],
        "missing_required_fields": missing_fields,
        "validator_dry_run": validator_dry_run,
        "historical_replay_comparable": historical_replay_comparable,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"{PREVIEW_SLUG}:{report_date}",
        "artifact_kind": PREVIEW_SLUG,
        "report_date": report_date,
        "generated_at": generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "display_only": True,
        "promotion_target": "scripts/run_promoted_advice_chain.py",
        "source_artifacts": source_artifacts(agent_home, [ticket_file, retrieval_file, debate_file, validated_file]),
        "summary": summary,
        "compatibility_contract": {
            "old_entrypoint": "removed_legacy_multiagent_committee_chain",
            "preview_entrypoint": "scripts/build_official_advice_compat_preview.py",
            "future_fallback_switch": "legacy_chain_removed",
            "official_write_paths_not_written": [
                "db/committee_decision_bundle/<date>.json",
                "db/llm_advice/<date>.json",
                "db/validated_advice/<date>.json",
                "db/decision_ledger/*",
                "db/execution_sync/*",
                "db/long_memory/*",
            ],
            "required_committee_decision_fields": sorted(REQUIRED_COMMITTEE_DECISION_FIELDS),
            "required_final_decision_fields": sorted(REQUIRED_FINAL_DECISION_FIELDS),
            "required_validated_action_preview_fields": sorted(REQUIRED_VALIDATED_ACTION_FIELDS),
            "rollback_note": "Delete this preview directory or ignore the feature flag design; official pipeline remains on the legacy adapter.",
        },
        "committee_decision_bundle_preview": committee_bundle_preview,
        "final_advice_preview": final_advice_preview,
        "validated_action_sections_preview": section_preview,
        "validated_advice_preview": preview_validated_payload,
        "comparison_to_official": comparison,
    }


def write_preview(agent_home: Path, report_date: str, payload: dict[str, Any]) -> Path:
    path = preview_path(agent_home, report_date)
    assert_refactor_write_allowed(path, payload, agent_home)
    return dump_json(path, payload)


def run_builder(agent_home: Path, report_date: str, *, generated_at: str | None = None) -> tuple[Path, dict[str, Any]]:
    payload = build_preview_payload(agent_home, report_date, generated_at=generated_at)
    path = write_preview(agent_home, report_date, payload)
    return path, payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a non-executable official-advice compatibility preview from shadow artifacts.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp.")
    parser.add_argument("--format", choices=["path", "json"], default="path")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    path, payload = run_builder(agent_home, report_date, generated_at=args.generated_at or None)
    if args.format == "json":
        print(json.dumps({"path": relative_posix(path, agent_home), "summary": payload["summary"]}, ensure_ascii=False, indent=2))
    else:
        print(path)


if __name__ == "__main__":
    main()
