from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from artifact_boundary import BoundaryViolation, assert_non_executable
from common import timestamp_now


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CORE_ARTIFACTS = {
    "legacyAdvice": "db/validated_advice/{date}.json",
    "actionTickets": "db/action_tickets/{date}.json",
    "retrievalPacks": "db/retrieval_packs/{date}.json",
    "actionDebates": "db/action_debates/{date}.json",
}
OPTIONAL_ARTIFACTS = {
    "adaptivePolicies": "db/strategy_memory/policies.json",
    "strategySkills": "db/strategy_skills/registry.json",
}
SHADOW_ARTIFACT_KINDS = {"actionTickets", "retrievalPacks", "actionDebates"}
LEARNING_ARTIFACT_KINDS = {"adaptivePolicies", "strategySkills", "outcomeEvents"}


@dataclass(slots=True)
class ArtifactRead:
    kind: str
    path: Path
    relative_path: str
    payload: dict[str, Any]
    state: str
    reason: str
    message: str

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def usable(self) -> bool:
        return self.state in {"ready", "degraded"}


class ShadowReviewService:
    def __init__(self, home: Path):
        self.home = home

    def build(self, report_date: str | None) -> dict[str, Any]:
        report_date = validate_report_date(report_date)
        generated_at = timestamp_now()
        artifacts = self._read_core_artifacts(report_date)
        optional = self._read_optional_artifacts()
        outcome_artifacts = self._read_outcome_artifacts(report_date)
        markdown_path = self.home / "db" / "refactor_reviews" / f"{report_date}.md"

        validated = artifacts["legacyAdvice"].payload
        action_tickets = artifacts["actionTickets"].payload
        retrieval_packs = artifacts["retrievalPacks"].payload
        action_debates = artifacts["actionDebates"].payload
        outcomes_by_ticket = index_outcomes_by_ticket(outcome_artifacts)

        items = []
        if artifacts["actionTickets"].usable:
            items = build_review_items(validated, action_tickets, retrieval_packs, action_debates, outcomes_by_ticket)
        page_status = review_status(artifacts, items)
        summary = build_summary(validated, action_tickets, items)
        missing = missing_artifact_rows(artifacts, optional, outcome_artifacts, markdown_path, report_date, self.home)
        runtime = build_runtime(action_debates)
        guardrails = {
            "nonExecutable": True,
            "executionDisabled": True,
            "affectsPortfolio": False,
            "affectsAdviceAccuracy": False,
            "affectsLongMemoryPromotion": False,
            "allowExecutionEvidence": False,
            "displayOnly": True,
        }

        return {
            "selectedDate": report_date,
            "status": page_status,
            "generatedAt": generated_at,
            "nonExecutable": True,
            "displayOnly": True,
            "summary": summary,
            "artifacts": {
                "legacyAdvicePath": artifacts["legacyAdvice"].relative_path,
                "shadowAdvicePath": artifacts["actionTickets"].relative_path,
                "shadowTracePath": artifacts["actionDebates"].relative_path,
                "retrievalPackPath": artifacts["retrievalPacks"].relative_path,
                "evalReportPath": relative_posix(markdown_path, self.home),
                "policyRegistryPath": optional["adaptivePolicies"].relative_path,
                "strategySkillRegistryPath": optional["strategySkills"].relative_path,
                "exists": {
                    "legacyAdvice": artifacts["legacyAdvice"].exists,
                    "shadowAdvice": artifacts["actionTickets"].exists,
                    "shadowTrace": artifacts["actionDebates"].exists,
                    "retrievalPack": artifacts["retrievalPacks"].exists,
                    "evalReport": markdown_path.exists(),
                    "outcomeEvents": bool(outcome_artifacts),
                    "adaptivePolicies": optional["adaptivePolicies"].exists,
                    "strategySkills": optional["strategySkills"].exists,
                },
                "states": {
                    **{kind: row.state for kind, row in artifacts.items()},
                    **{kind: row.state for kind, row in optional.items()},
                    "outcomeEvents": "ready" if outcome_artifacts else "not_run",
                    "evalReport": "ready" if markdown_path.exists() else "not_run",
                },
                "missing": missing,
            },
            "items": items,
            "runtime": runtime,
            "guardrails": guardrails,
            "policySummary": artifact_summary(optional["adaptivePolicies"].payload),
            "skillSummary": artifact_summary(optional["strategySkills"].payload),
            "outcomeSummary": outcome_summary(outcome_artifacts),
        }

    def _read_core_artifacts(self, report_date: str) -> dict[str, ArtifactRead]:
        return {
            kind: read_json_artifact(self.home, relative.format(date=report_date), kind)
            for kind, relative in CORE_ARTIFACTS.items()
        }

    def _read_optional_artifacts(self) -> dict[str, ArtifactRead]:
        return {
            kind: read_json_artifact(self.home, relative, kind)
            for kind, relative in OPTIONAL_ARTIFACTS.items()
        }

    def _read_outcome_artifacts(self, report_date: str) -> dict[str, ArtifactRead]:
        root = self.home / "db" / "outcome_events"
        result: dict[str, ArtifactRead] = {}
        for path in sorted(root.glob(f"{report_date}__*.json")):
            horizon = path.stem.split("__", 1)[1] if "__" in path.stem else path.stem
            relative = relative_posix(path, self.home)
            result[horizon] = read_json_artifact(self.home, relative, f"outcomeEvents:{horizon}")
        return result


def validate_report_date(value: str | None) -> str:
    text = str(value or "").strip()
    if not DATE_RE.match(text):
        raise ValueError("date is required in YYYY-MM-DD format")
    return text


def relative_posix(path: Path, home: Path) -> str:
    try:
        return path.relative_to(home).as_posix()
    except ValueError:
        return path.as_posix()


def read_json_artifact(home: Path, relative: str, kind: str) -> ArtifactRead:
    path = home / relative
    if not path.exists():
        return ArtifactRead(kind, path, relative, {}, "not_run", "not_generated", f"{kind} artifact has not been generated.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ArtifactRead(kind, path, relative, {}, "failed", "invalid_json", f"{kind} artifact is invalid JSON: {exc}")
    if not isinstance(payload, dict):
        return ArtifactRead(kind, path, relative, {}, "failed", "invalid_json", f"{kind} artifact root is not an object.")
    if not payload:
        return ArtifactRead(kind, path, relative, {}, "degraded", "empty", f"{kind} artifact is empty.")
    boundary_message = validate_artifact_boundary(kind, payload)
    if boundary_message:
        return ArtifactRead(kind, path, relative, payload, "failed", "boundary_violation", boundary_message)
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    summary_status = str(summary.get("status", "") or "")
    if summary_status in {"degraded", "failed", "missing_inputs"}:
        return ArtifactRead(kind, path, relative, payload, "degraded", summary_status, f"{kind} artifact summary status is {summary_status}.")
    return ArtifactRead(kind, path, relative, payload, "ready", "loaded", f"{kind} artifact loaded.")


def validate_artifact_boundary(kind: str, payload: dict[str, Any]) -> str:
    base_kind = kind.split(":", 1)[0]
    if base_kind not in SHADOW_ARTIFACT_KINDS and base_kind not in LEARNING_ARTIFACT_KINDS:
        return ""
    expected_scope = "shadow_only" if base_kind in SHADOW_ARTIFACT_KINDS else "learning_only"
    if payload.get("write_scope") != expected_scope:
        return f"{kind} boundary violation: write_scope must be {expected_scope}."
    try:
        assert_non_executable(payload)
    except BoundaryViolation as exc:
        return f"{kind} boundary violation: {exc}"
    return ""


def missing_artifact_rows(
    core: dict[str, ArtifactRead],
    optional: dict[str, ArtifactRead],
    outcomes: dict[str, ArtifactRead],
    markdown_path: Path,
    report_date: str,
    home: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in list(core.values()) + list(optional.values()):
        if item.state == "ready":
            continue
        reason = item.reason
        if item.kind == "legacyAdvice" and reason == "not_generated":
            reason = "missing_source"
        rows.append({"kind": item.kind, "path": item.relative_path, "reason": reason, "message": item.message})
    for item in outcomes.values():
        if item.state == "ready":
            continue
        rows.append({"kind": item.kind, "path": item.relative_path, "reason": item.reason, "message": item.message})
    if not outcomes:
        rows.append(
            {
                "kind": "outcomeEvents",
                "path": f"db/outcome_events/{report_date}__<horizon>.json",
                "reason": "not_generated",
                "message": "No outcome event artifact exists for this date.",
            }
        )
    if not markdown_path.exists():
        rows.append(
            {
                "kind": "evalReport",
                "path": relative_posix(markdown_path, home),
                "reason": "not_generated",
                "message": "Markdown review has not been rendered for this date.",
            }
        )
    return rows


def review_status(artifacts: dict[str, ArtifactRead], items: list[dict[str, Any]]) -> str:
    states = {key: value.state for key, value in artifacts.items()}
    if all(state == "not_run" for state in states.values()):
        return "missing"
    if states["legacyAdvice"] == "ready" and states["actionTickets"] == "not_run":
        return "not_run"
    if any(state == "failed" for state in states.values()):
        return "degraded" if items else "failed"
    if any(state in {"not_run", "degraded"} for state in states.values()):
        return "partial"
    return "ready"


def official_actions(validated: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for bucket in ("tactical_actions", "dca_actions", "hold_actions"):
        for index, item in enumerate(validated.get(bucket, []) or []):
            if not isinstance(item, dict):
                continue
            copied = dict(item)
            copied["_bucket"] = bucket
            copied["_source_index"] = index
            actions.append(copied)
    return actions


def review_key_for_legacy(action: dict[str, Any]) -> str:
    suggestion_id = str(action.get("suggestion_id", "") or "").strip()
    if suggestion_id:
        return f"suggestion:{suggestion_id}"
    code = str(action.get("fund_code", "") or "").strip()
    action_label_text = action_label(action, "legacy")
    bucket = str(action.get("_bucket", "") or action.get("_source_bucket", "") or "").strip()
    index = str(action.get("_source_index", "") if action.get("_source_index") is not None else "")
    return f"{code}:{action_label_text}:{bucket}:{index}"


def review_key_for_ticket(ticket: dict[str, Any]) -> str:
    mapping = ticket.get("legacy_mapping", {}) if isinstance(ticket.get("legacy_mapping"), dict) else {}
    suggestion_id = str(mapping.get("suggestion_id", "") or "").strip()
    if suggestion_id:
        return f"suggestion:{suggestion_id}"
    code = str(ticket.get("fund_code", "") or "").strip()
    action_label_text = action_label(ticket, "shadow")
    bucket = str(mapping.get("source_bucket", "") or ticket.get("portfolio_bucket", "") or "").strip()
    index = str(mapping.get("source_index", "") if mapping.get("source_index") is not None else "")
    return f"{code}:{action_label_text}:{bucket}:{index}"


def official_by_review_key(validated: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for action in official_actions(validated):
        key = review_key_for_legacy(action)
        if key:
            result.setdefault(key, action)
    return result


def tickets_by_review_key(action_tickets: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for ticket in action_tickets.get("tickets", []) or []:
        if not isinstance(ticket, dict):
            continue
        key = review_key_for_ticket(ticket)
        if key:
            result.setdefault(key, ticket)
    return result


def packs_by_ticket_id(retrieval_packs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for pack in retrieval_packs.get("packs", []) or []:
        if not isinstance(pack, dict):
            continue
        target = pack.get("target", {}) if isinstance(pack.get("target"), dict) else {}
        ticket_id = str(target.get("ticket_id", "") or "")
        if ticket_id:
            result[ticket_id] = pack
    return result


def debates_by_ticket_id(action_debates: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(debate.get("ticket_id", "") or ""): debate
        for debate in action_debates.get("debates", []) or []
        if isinstance(debate, dict) and debate.get("ticket_id")
    }


def index_outcomes_by_ticket(outcome_artifacts: dict[str, ArtifactRead]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for horizon, artifact in outcome_artifacts.items():
        if not artifact.usable:
            continue
        for event in artifact.payload.get("events", []) or []:
            if not isinstance(event, dict) or not event.get("ticket_id"):
                continue
            copied = dict(event)
            copied["horizon"] = horizon
            result.setdefault(str(event["ticket_id"]), []).append(copied)
    return result


def build_summary(validated: dict[str, Any], action_tickets: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    changed_count = sum(1 for item in items if item.get("category") == "changed")
    comparable_count = sum(1 for item in items if item.get("legacy") and item.get("shadow"))
    high_risk_count = sum(1 for item in items if item.get("severity") == "high")
    return {
        "legacyCount": len(official_actions(validated)),
        "shadowCount": len([item for item in action_tickets.get("tickets", []) or [] if isinstance(item, dict)]),
        "comparableCount": comparable_count,
        "changedCount": changed_count,
        "agreementRate": round((comparable_count - changed_count) / comparable_count, 4) if comparable_count else None,
        "highRiskDiffCount": high_risk_count,
    }


def build_review_items(
    validated: dict[str, Any],
    action_tickets: dict[str, Any],
    retrieval_packs: dict[str, Any],
    action_debates: dict[str, Any],
    outcomes_by_ticket: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    official_map = official_by_review_key(validated)
    ticket_map = tickets_by_review_key(action_tickets)
    official_map, ticket_map = align_single_action_fallbacks(official_map, ticket_map)
    pack_map = packs_by_ticket_id(retrieval_packs)
    debate_map = debates_by_ticket_id(action_debates)
    keys = sorted(set(official_map) | set(ticket_map))
    items: list[dict[str, Any]] = []
    for key in keys:
        legacy = official_map.get(key)
        ticket = ticket_map.get(key)
        code = str((ticket or {}).get("fund_code") or (legacy or {}).get("fund_code") or key)
        ticket_id = str((ticket or {}).get("ticket_id", "") or "")
        pack = pack_map.get(ticket_id)
        debate = debate_map.get(ticket_id)
        outcomes = outcomes_by_ticket.get(ticket_id, [])
        items.append(build_item(code, legacy, ticket, pack, debate, outcomes))
    return items


def fallback_action_key(record: dict[str, Any] | None, kind: str) -> str:
    if not record:
        return ""
    return f"{str(record.get('fund_code', '') or '')}:{action_label(record, kind)}"


def align_single_action_fallbacks(
    official_map: dict[str, dict[str, Any]],
    ticket_map: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    official_by_fund_action: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    ticket_by_fund_action: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for key, action in official_map.items():
        official_by_fund_action.setdefault(fallback_action_key(action, "legacy"), []).append((key, action))
    for key, ticket in ticket_map.items():
        ticket_by_fund_action.setdefault(fallback_action_key(ticket, "shadow"), []).append((key, ticket))

    aligned_official = dict(official_map)
    aligned_ticket = dict(ticket_map)
    for fallback_key, official_items in official_by_fund_action.items():
        ticket_items = ticket_by_fund_action.get(fallback_key, [])
        if len(official_items) != 1 or len(ticket_items) != 1:
            continue
        official_key, official_action = official_items[0]
        ticket_key, ticket = ticket_items[0]
        if official_key == ticket_key:
            continue
        merged_key = f"matched:{fallback_key}"
        aligned_official.pop(official_key, None)
        aligned_ticket.pop(ticket_key, None)
        aligned_official[merged_key] = official_action
        aligned_ticket[merged_key] = ticket

    official_by_fund: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    ticket_by_fund: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for key, action in aligned_official.items():
        official_by_fund.setdefault(str(action.get("fund_code", "") or ""), []).append((key, action))
    for key, ticket in aligned_ticket.items():
        ticket_by_fund.setdefault(str(ticket.get("fund_code", "") or ""), []).append((key, ticket))
    for fund_code, official_items in official_by_fund.items():
        ticket_items = ticket_by_fund.get(fund_code, [])
        if len(official_items) != 1 or len(ticket_items) != 1:
            continue
        official_key, official_action = official_items[0]
        ticket_key, ticket = ticket_items[0]
        if official_key == ticket_key:
            continue
        merged_key = f"matched:{fund_code}:single_action"
        aligned_official.pop(official_key, None)
        aligned_ticket.pop(ticket_key, None)
        aligned_official[merged_key] = official_action
        aligned_ticket[merged_key] = ticket
    return aligned_official, aligned_ticket


def build_item(
    fund_code: str,
    legacy: dict[str, Any] | None,
    ticket: dict[str, Any] | None,
    pack: dict[str, Any] | None,
    debate: dict[str, Any] | None,
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    legacy_action = action_label(legacy, "legacy")
    shadow_action = action_label(ticket, "shadow")
    has_legacy = bool(legacy)
    has_shadow = bool(ticket)
    action_changed = has_legacy and has_shadow and legacy_action != shadow_action
    category = item_category(has_legacy, has_shadow, action_changed)
    guardrails = guardrail_summary(ticket or {})
    severity = item_severity(category, guardrails)
    confidence_delta = confidence(ticket) - confidence(legacy) if has_legacy and has_shadow else None
    notes = diff_notes(legacy_action, shadow_action, guardrails, pack, debate, outcomes)
    fund_name = str((ticket or {}).get("fund_name") or (legacy or {}).get("fund_name") or fund_code)
    display_label = f"{fund_code} {fund_name}".strip()
    return {
        "reviewId": str((ticket or {}).get("ticket_id") or (legacy or {}).get("suggestion_id") or f"review:{fund_code}"),
        "fundCode": fund_code,
        "fundName": fund_name,
        "category": category,
        "severity": severity,
        "displayLabel": display_label,
        "nonExecutable": True,
        "displayOnly": True,
        "legacy": legacy_block(legacy) if legacy else None,
        "shadow": shadow_block(ticket, pack or {}, debate or {}) if ticket else None,
        "diff": {
            "actionChanged": action_changed,
            "confidenceDelta": round(confidence_delta, 4) if confidence_delta is not None else None,
            "riskChanged": bool(guardrails.get("block") or guardrails.get("adjust")),
            "evidenceChanged": evidence_count(legacy) != evidence_count(ticket),
            "notes": notes,
        },
        "display": {
            "primaryText": f"official={legacy_action}; shadow={shadow_action}",
            "secondaryText": "; ".join(notes[:2]),
            "badges": item_badges(category, severity, ticket, debate, outcomes),
        },
        "guardrails": guardrails,
        "softPolicies": list((ticket or {}).get("soft_policy_adjustments", []) or []),
        "skillRefs": list((ticket or {}).get("skill_refs", []) or []),
        "skillOutputs": list((ticket or {}).get("skill_outputs", []) or []),
        "outcomeEvents": outcomes,
        "retrieval": retrieval_block(pack) if pack else None,
        "debate": debate_block(debate) if debate else None,
    }


def action_label(item: dict[str, Any] | None, kind: str) -> str:
    if not item:
        return "none" if kind == "legacy" else "not_run"
    keys = ("validated_action", "action", "model_action") if kind == "legacy" else ("action_verb", "validated_action", "action")
    for key in keys:
        text = str(item.get(key, "") or "").strip()
        if text:
            return text
    return "none" if kind == "legacy" else "not_run"


def item_category(has_legacy: bool, has_shadow: bool, action_changed: bool) -> str:
    if has_legacy and has_shadow:
        return "changed" if action_changed else "same"
    if has_shadow:
        return "new_shadow_only"
    if has_legacy:
        return "legacy_only"
    return "missing"


def item_severity(category: str, guardrails: dict[str, Any]) -> str:
    if category == "changed" and int(guardrails.get("block", 0) or 0) > 0:
        return "high"
    if category == "changed":
        return "medium"
    if category in {"new_shadow_only", "legacy_only"}:
        return "low"
    return "info"


def confidence(item: dict[str, Any] | None) -> float:
    if not item:
        return 0.0
    for key in ("confidence", "committee_confidence", "score"):
        value = item.get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def evidence_count(item: dict[str, Any] | None) -> int:
    if not item:
        return 0
    return sum(
        len(item.get(key, []) or [])
        for key in ("supporting_evidence_refs", "opposing_evidence_refs", "evidence_refs", "supporting_signal_ids", "opposing_signal_ids")
    )


def compact_strings(value: Any, *, limit: int = 4) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        result = []
        for item in value[:limit]:
            if isinstance(item, dict):
                result.append(str(item.get("summary") or item.get("status_reason") or item.get("source_record_id") or item)[:240])
            else:
                result.append(str(item)[:240])
        return [item for item in result if item]
    return [str(value)[:240]]


def legacy_block(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": action_label(item, "legacy"),
        "confidence": confidence(item),
        "thesis": str(item.get("thesis", "") or ""),
        "risks": compact_strings(item.get("constraint_hits") or item.get("risk_notes") or item.get("validation_notes")),
        "evidence": compact_strings(item.get("supporting_signal_ids") or item.get("evidence_refs")),
        "sourcePath": "db/validated_advice/<date>.json",
        "bucket": item.get("_bucket", ""),
    }


def shadow_block(ticket: dict[str, Any], pack: dict[str, Any], debate: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": action_label(ticket, "shadow"),
        "confidence": confidence(ticket),
        "thesis": str(ticket.get("thesis", "") or ""),
        "risks": compact_strings(ticket.get("opposing_evidence_refs") or ticket.get("validation_notes")),
        "evidence": compact_strings(ticket.get("supporting_evidence_refs")),
        "traceId": str(debate.get("debate_id") or pack.get("pack_id") or ""),
        "sourcePath": "db/action_tickets/<date>.json",
        "fallbackReason": str(ticket.get("fallback_reason", "") or ""),
        "missingData": list(ticket.get("missing_data", []) or []) + list(pack.get("missing_data", []) or []),
        "ticketStatus": str(ticket.get("ticket_status", "") or ""),
        "executionMode": str(ticket.get("execution_mode", "") or ""),
        "validatedAmount": ticket.get("validated_amount"),
        "sizeBucket": ticket.get("size_bucket", ""),
    }


def guardrail_summary(ticket: dict[str, Any]) -> dict[str, Any]:
    counts = {"pass": 0, "adjust": 0, "block": 0, "not_checked": 0}
    results = []
    for item in ticket.get("hard_guardrail_results", []) or []:
        if not isinstance(item, dict):
            continue
        result = str(item.get("result", "") or "not_checked")
        counts[result] = counts.get(result, 0) + 1
        results.append(
            {
                "ruleId": item.get("rule_id", ""),
                "result": result,
                "statusReason": item.get("status_reason", ""),
            }
        )
    return {**counts, "results": results}


def retrieval_block(pack: dict[str, Any]) -> dict[str, Any]:
    audit = pack.get("audit", {}) if isinstance(pack.get("audit"), dict) else {}
    return {
        "packId": pack.get("pack_id", ""),
        "traceCompletenessRate": audit.get("trace_completeness_rate", pack.get("trace_completeness_rate")),
        "missingDataCount": len(pack.get("missing_data", []) or []),
        "ragTraceCount": len(pack.get("rag_trace_refs", []) or []),
    }


def debate_block(debate: dict[str, Any]) -> dict[str, Any]:
    outputs = debate.get("node_outputs", {}) if isinstance(debate.get("node_outputs"), dict) else {}
    referee = outputs.get("debate_referee", {}) if isinstance(outputs.get("debate_referee"), dict) else {}
    writer = outputs.get("ticket_writer", {}) if isinstance(outputs.get("ticket_writer"), dict) else {}
    patch = writer.get("proposed_ticket_patch", {}) if isinstance(writer.get("proposed_ticket_patch"), dict) else {}
    return {
        "debateId": debate.get("debate_id", ""),
        "verdict": referee.get("verdict", ""),
        "degraded": bool(debate.get("degraded")),
        "writesTicketFile": bool(writer.get("writes_ticket_file", False)),
        "proposedPatch": patch,
    }


def diff_notes(
    legacy_action: str,
    shadow_action: str,
    guardrails: dict[str, Any],
    pack: dict[str, Any] | None,
    debate: dict[str, Any] | None,
    outcomes: list[dict[str, Any]],
) -> list[str]:
    notes = []
    if legacy_action != shadow_action:
        notes.append(f"Action differs: official {legacy_action}, shadow {shadow_action}.")
    if guardrails.get("block"):
        notes.append(f"Hard guardrail blocks: {guardrails.get('block')}.")
    if pack and pack.get("missing_data"):
        notes.append(f"Retrieval missing data: {len(pack.get('missing_data', []) or [])}.")
    debate_view = debate_block(debate) if debate else {}
    if debate_view.get("verdict"):
        notes.append(f"Debate verdict: {debate_view['verdict']}.")
    if outcomes:
        notes.append(f"Outcome events: {len(outcomes)}.")
    if not notes:
        notes.append("No material display diff detected.")
    return notes


def item_badges(
    category: str,
    severity: str,
    ticket: dict[str, Any] | None,
    debate: dict[str, Any],
    outcomes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    tone_by_severity = {"high": "danger", "medium": "warning", "low": "info", "info": "neutral"}
    badges = [
        {"label": category, "tone": tone_by_severity.get(severity, "neutral")},
        {"label": "display-only", "tone": "neutral"},
    ]
    if ticket:
        badges.append({"label": str(ticket.get("ticket_status", "") or "shadow"), "tone": "info"})
    if debate:
        badges.append({"label": "debate", "tone": "purple"})
    if outcomes:
        badges.append({"label": f"outcomes:{len(outcomes)}", "tone": "success"})
    return badges


def build_runtime(action_debates: dict[str, Any]) -> dict[str, Any]:
    runtime = action_debates.get("runtime", {}) if isinstance(action_debates.get("runtime"), dict) else {}
    summary = action_debates.get("summary", {}) if isinstance(action_debates.get("summary"), dict) else {}
    return {
        "runId": runtime.get("run_id", ""),
        "status": summary.get("status") or ("ready" if action_debates else "not_run"),
        "currentStep": "",
        "currentAgent": "",
        "startedAt": action_debates.get("generated_at", ""),
        "endedAt": action_debates.get("generated_at", ""),
        "lastError": summary.get("last_error", ""),
        "nodeStatus": runtime.get("node_status", {}),
        "nodeFailureCount": summary.get("node_failure_count", 0),
    }


def artifact_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    return dict(summary)


def outcome_summary(outcome_artifacts: dict[str, ArtifactRead]) -> dict[str, Any]:
    rows = {}
    for horizon, artifact in outcome_artifacts.items():
        rows[horizon] = artifact_summary(artifact.payload)
    return rows
