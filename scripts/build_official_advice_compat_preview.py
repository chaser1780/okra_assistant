from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from artifact_boundary import assert_refactor_write_allowed, relative_posix
from common import dump_json, load_json, resolve_agent_home, resolve_date, timestamp_now, validated_advice_path


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


def risk_veto_for(ticket: dict[str, Any], debate: dict[str, Any]) -> bool:
    if ticket.get("ticket_status") in {"blocked", "degraded"}:
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


def build_committee_decision(ticket: dict[str, Any], pack: dict[str, Any], debate: dict[str, Any], priority: int) -> dict[str, Any]:
    amount = safe_float(ticket.get("validated_amount"))
    veto = risk_veto_for(ticket, debate)
    action = str(ticket.get("action_verb", "hold") or "hold")
    notes = guardrail_notes(ticket)
    debate_note = debate_summary(debate)
    if debate_note:
        notes.append(f"debate_referee: {debate_note}")
    return {
        "fund_code": str(ticket.get("fund_code", "") or ""),
        "fund_name": str(ticket.get("fund_name", "") or ""),
        "role": str(ticket.get("role", "") or ""),
        "proposed_action": action,
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
    return sections


def market_view_preview(validated: dict[str, Any], report_date: str, decision_count: int) -> dict[str, Any]:
    base = dict(validated.get("market_view", {}) or {})
    base.setdefault("regime", "mixed")
    base["summary"] = (
        "Shadow action-ticket chain produced an official-compatible advice preview "
        f"for {report_date}; decisions={decision_count}. This preview is non-executable."
    )
    drivers = list(base.get("key_drivers", []) or [])
    drivers.append("source_chain=action_ticket->retrieval_pack->action_debate")
    base["key_drivers"] = stable_list(drivers, limit=8)
    return base


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


def build_preview_payload(agent_home: Path, report_date: str, *, generated_at: str | None = None) -> dict[str, Any]:
    generated_at = generated_at or timestamp_now()
    ticket_file = action_ticket_path(agent_home, report_date)
    retrieval_file = retrieval_pack_path(agent_home, report_date)
    debate_file = action_debate_path(agent_home, report_date)
    validated_file = validated_advice_path(agent_home, report_date)
    ticket_artifact = load_json_dict(ticket_file, "action_ticket")
    retrieval_artifact = load_json_dict(retrieval_file, "retrieval_pack")
    debate_artifact = load_json_dict(debate_file, "action_debate")
    validated = load_optional_json_dict(validated_file)
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
    committee_decisions: list[dict[str, Any]] = []
    final_decisions: list[dict[str, Any]] = []
    validated_action_previews: list[dict[str, Any]] = []
    tickets = [item for item in ticket_artifact.get("tickets", []) or [] if isinstance(item, dict)]
    tickets.sort(key=lambda item: (int((item.get("legacy_mapping", {}) or {}).get("priority", 999) or 999), str(item.get("fund_code", ""))))
    for priority, ticket in enumerate(tickets, start=1):
        ticket_id = str(ticket.get("ticket_id", "") or "")
        pack = pack_map.get(ticket_id, {})
        debate = debate_map.get(ticket_id, {})
        committee_decision = build_committee_decision(ticket, pack, debate, priority)
        final_decision = build_final_decision(committee_decision, ticket, pack, debate)
        committee_decisions.append(committee_decision)
        final_decisions.append(final_decision)
        validated_action_previews.append(build_validated_action_preview(ticket, final_decision))

    root_execution_eligible = any(item.get("execution_eligible") for item in committee_decisions)
    committee_bundle_preview = {
        "schema_version": 1,
        "report_date": report_date,
        "generated_at": generated_at,
        "decision_mode": "shadow_preview",
        "decision_source": "action_debate_shadow_compat_preview",
        "degradation_mode": "none" if debate_artifact.get("summary", {}).get("status") == "ok" else "shadow_degraded",
        "execution_eligible": root_execution_eligible,
        "committee_confidence": "preview",
        "manager_order": ["action_ticket_shadow", "layered_retrieval_pack", "action_debate_shadow"],
        "fund_decisions": committee_decisions,
        "market_view": market_view_preview(validated, report_date, len(final_decisions)),
        "cross_fund_observations": [
            "Compatibility preview only; not written to db/committee_decision_bundle or db/llm_advice.",
            "Official validator, optimizer, ledger, execution sync, and long memory are unchanged.",
        ],
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
        "notes": ["Generated from shadow artifacts under a non-executable review boundary."],
    }
    final_advice_preview = {
        "market_view": committee_bundle_preview["market_view"],
        "fund_decisions": final_decisions,
        "cross_fund_observations": committee_bundle_preview["cross_fund_observations"],
    }
    section_preview = group_validated_sections(validated_action_previews)
    missing_fields = missing_required_fields(committee_decisions, REQUIRED_COMMITTEE_DECISION_FIELDS, "committee_decision")
    missing_fields.extend(missing_required_fields(final_decisions, REQUIRED_FINAL_DECISION_FIELDS, "final_decision"))
    missing_fields.extend(missing_required_fields(validated_action_previews, REQUIRED_VALIDATED_ACTION_FIELDS, "validated_action_preview"))
    comparison = compare_to_official(validated, final_decisions)
    summary = {
        "status": "ok" if not missing_fields else "degraded",
        "ticket_count": len(tickets),
        "committee_decision_count": len(committee_decisions),
        "final_advice_decision_count": len(final_decisions),
        "validated_section_preview_count": sum(len(items) for items in section_preview.values()),
        "official_compatible_advice": not missing_fields,
        "committee_bundle_compatible": not missing_fields,
        "llm_advice_compatible": not missing_fields,
        "validated_sections_preview_only": True,
        "fallback_switch_active": False,
        "promotion_ready": False,
        "official_output_unchanged": True,
        "official_paths_written": [],
        "missing_required_fields": missing_fields,
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
        "promotion_target": "scripts/generate_llm_advice.py::build_final_advice_from_committee_bundle",
        "source_artifacts": source_artifacts(agent_home, [ticket_file, retrieval_file, debate_file, validated_file]),
        "summary": summary,
        "compatibility_contract": {
            "old_entrypoint": "scripts/generate_llm_advice.py::build_final_advice_from_committee_bundle",
            "preview_entrypoint": "scripts/build_official_advice_compat_preview.py",
            "future_fallback_switch": "OKRA_USE_SHADOW_ADVICE_ADAPTER=0",
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
