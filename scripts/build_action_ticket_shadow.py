from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from action_ticket_models import ActionTicket, ActionTicketArtifact, EvidenceRef, GuardrailResult, SoftPolicyAdjustment
from artifact_boundary import assert_refactor_write_allowed, relative_posix
from common import business_day_gap, dump_json, load_json, load_strategy, resolve_agent_home, resolve_date, score_path, timestamp_now, validated_advice_path
from build_layered_seed import build_native_action_seeds


ACTION_SECTIONS = ("tactical_actions", "dca_actions", "hold_actions")
SCHEMA_VERSION = "action_ticket.v1"


class MissingPortfolioStateError(FileNotFoundError):
    """Raised when a historical shadow replay has no matching portfolio state."""


def action_ticket_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "action_tickets" / f"{report_date}.json"


def current_portfolio_state_path(agent_home: Path) -> Path:
    return agent_home / "db" / "portfolio_state" / "current.json"


def portfolio_state_snapshot_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "portfolio_state" / "snapshots" / f"{report_date}.json"


def portfolio_as_of_date(portfolio: dict[str, Any]) -> str:
    return str(portfolio.get("as_of_date", "") or portfolio.get("state_metadata", {}).get("as_of_date", "") or "").strip()


def select_portfolio_state_path(agent_home: Path, report_date: str) -> Path:
    snapshot_path = portfolio_state_snapshot_path(agent_home, report_date)
    if snapshot_path.exists():
        return snapshot_path
    current_path = current_portfolio_state_path(agent_home)
    current = load_json_if_exists(current_path)
    if current and portfolio_as_of_date(current) == report_date:
        return current_path
    return snapshot_path


def load_portfolio_state_for_report(
    agent_home: Path,
    report_date: str,
    *,
    allow_prior_current: bool = False,
    max_prior_business_days: int = 1,
) -> tuple[Path, dict[str, Any]]:
    snapshot_path = portfolio_state_snapshot_path(agent_home, report_date)
    if snapshot_path.exists():
        return snapshot_path, load_json(snapshot_path)

    current_path = current_portfolio_state_path(agent_home)
    current = load_json_if_exists(current_path)
    current_as_of = portfolio_as_of_date(current) if current else ""
    if current and current_as_of == report_date:
        return current_path, current
    gap = business_day_gap(current_as_of, report_date) if current_as_of else None
    if allow_prior_current and current and gap is not None and 0 <= gap <= max_prior_business_days:
        return current_path, current

    raise MissingPortfolioStateError(
        "portfolio_state snapshot missing for "
        f"report_date={report_date}: expected {snapshot_path}; "
        f"current.as_of_date={current_as_of or '<missing>'}; "
        "current.json fallback is allowed only when current.as_of_date matches report_date"
    )


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_json(path)


def source_artifacts(
    agent_home: Path,
    report_date: str,
    validated_path: Path | None,
    portfolio_path: Path,
    *,
    source_mode: str = "validated",
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    if source_mode == "validated" and validated_path is not None:
        artifacts.append(
            {
                "kind": "validated_advice",
                "path": relative_posix(validated_path, agent_home),
                "content_sha256": content_sha256(validated_path),
            }
        )
    elif source_mode == "native":
        for kind, path in (
            ("native_action_seed", agent_home / "db" / "action_seed" / f"{report_date}.json"),
            ("daily_score", score_path(agent_home, report_date)),
            ("llm_context", agent_home / "db" / "llm_context" / f"{report_date}.json"),
        ):
            if path.exists():
                artifacts.append(
                    {
                        "kind": kind,
                        "path": relative_posix(path, agent_home),
                        "content_sha256": content_sha256(path),
                    }
                )
    if portfolio_path.exists():
        artifacts.append(
            {
                "kind": "portfolio_state",
                "path": relative_posix(portfolio_path, agent_home),
                "content_sha256": content_sha256(portfolio_path),
            }
        )
    artifacts.append({"kind": "builder", "path": "scripts/build_action_ticket_shadow.py", "content_sha256": ""})
    return artifacts


def normalize_action(value: Any) -> str:
    action = str(value or "hold").strip()
    aliases = {"buy": "add", "sell": "reduce", "dca": "scheduled_dca"}
    return aliases.get(action, action)


def execution_mode_for(action_verb: str) -> str:
    if action_verb == "scheduled_dca":
        return "scheduled"
    if action_verb == "hold":
        return "watch"
    return "immediate"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def ratio(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 6)


def collect_legacy_actions(validated: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    by_code: dict[str, dict[str, Any]] = {}
    for section in ACTION_SECTIONS:
        for index, item in enumerate(validated.get(section, []) or []):
            if not isinstance(item, dict) or not item.get("fund_code"):
                continue
            copied = dict(item)
            copied["_source_bucket"] = section
            copied["_source_index"] = index
            actions.append(copied)
            by_code.setdefault(str(copied["fund_code"]), copied)
    return actions, by_code


def committee_decision_by_code(validated: dict[str, Any]) -> dict[str, dict[str, Any]]:
    bundle = validated.get("committee_decision_bundle", {})
    if not isinstance(bundle, dict):
        return {}
    return {
        str(item.get("fund_code")): item
        for item in bundle.get("fund_decisions", []) or []
        if isinstance(item, dict) and item.get("fund_code")
    }


def portfolio_funds(portfolio: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in (portfolio.get("funds", []) or []) if isinstance(item, dict) and item.get("fund_code")]


def fund_lookup(portfolio: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("fund_code")): item for item in portfolio_funds(portfolio)}


def requested_amount_for(action: dict[str, Any], committee: dict[str, Any]) -> float | None:
    for key in ("requested_amount", "model_amount", "suggest_amount", "raw_amount"):
        if key in action:
            return safe_float(action.get(key))
    if normalize_action(action.get("validated_action")) == "scheduled_dca":
        return safe_float(action.get("validated_amount"))
    for key in ("suggest_amount", "requested_amount"):
        if key in committee:
            return safe_float(committee.get(key))
    return None


def infer_status(action: dict[str, Any], committee: dict[str, Any]) -> str:
    explicit = str(action.get("ticket_status", "") or "").strip()
    if explicit:
        return explicit
    action_verb = normalize_action(action.get("validated_action"))
    model_action = normalize_action(action.get("model_action"))
    constraint_hits = {str(item) for item in (action.get("constraint_hits", []) or [])}
    policy_hits = {str(item) for item in (action.get("policy_rule_hits", []) or [])}
    if not action.get("fund_code"):
        return "degraded"
    if committee.get("risk_veto") or "risk_veto" in constraint_hits:
        return "blocked"
    if action_verb == "hold" and model_action != "hold":
        return "blocked"
    if action_verb == "hold" and ("committee_bundle_fund_gate" in policy_hits or "execution_not_eligible" in constraint_hits):
        return "blocked"
    requested = requested_amount_for(action, committee)
    validated = safe_float(action.get("validated_amount"))
    if requested is not None and abs(requested - validated) >= 0.01:
        return "adjusted"
    return "shadow_only"


def source_record_id(action: dict[str, Any]) -> str:
    return str(action.get("suggestion_id") or f"{action.get('fund_code', '')}:{normalize_action(action.get('validated_action'))}")


def portfolio_source_path(source_artifacts: list[dict[str, Any]]) -> str:
    for item in source_artifacts:
        if item.get("kind") == "portfolio_state":
            return str(item.get("path", "") or "")
    return ""


def build_guardrails(validated: dict[str, Any], action: dict[str, Any], committee: dict[str, Any]) -> list[GuardrailResult]:
    action_verb = normalize_action(action.get("validated_action"))
    validated_amount = safe_float(action.get("validated_amount"))
    constraint_hits = {str(item) for item in (action.get("constraint_hits", []) or [])}
    policy_hits = {str(item) for item in (action.get("policy_rule_hits", []) or [])}
    requested = requested_amount_for(action, committee)

    guardrails = [
        GuardrailResult("amount_normalization", "pass", f"validated_amount={validated_amount:.2f}"),
        GuardrailResult(
            "committee_global_gate",
            "block" if validated.get("decision_mode") in {"blocked", "hold_only"} and action_verb == "hold" else "pass",
            f"decision_mode={validated.get('decision_mode', '')}; execution_eligible={validated.get('execution_eligible')}",
        ),
        GuardrailResult(
            "committee_fund_gate",
            "block" if committee.get("risk_veto") or "committee_bundle_fund_gate" in policy_hits or "execution_not_eligible" in constraint_hits else "pass",
            "fund-level committee gate hit" if committee.get("risk_veto") or "committee_bundle_fund_gate" in policy_hits or "execution_not_eligible" in constraint_hits else "no fund-level committee block",
        ),
        GuardrailResult(
            "requested_vs_validated_amount",
            "adjust" if requested is not None and abs(requested - validated_amount) >= 0.01 else "pass",
            "requested amount adjusted by validator" if requested is not None and abs(requested - validated_amount) >= 0.01 else "requested amount matches validated amount or is unavailable",
        ),
        GuardrailResult("cash_floor_funding", "not_checked", str(action.get("cash_impact", "") or "cash impact not structured enough for deterministic Phase 1 mapping")),
        GuardrailResult("fund_capacity", "not_checked", "capacity details are not consistently persisted on legacy actions"),
        GuardrailResult("sellable_amount", "not_checked", "sellable amount details are not consistently persisted on legacy actions"),
        GuardrailResult("gross_trade_budget", "not_checked", "portfolio optimizer budget details remain root-level legacy context"),
        GuardrailResult("net_buy_budget", "not_checked", "portfolio optimizer budget details remain root-level legacy context"),
        GuardrailResult("action_count", "not_checked", "max action count is not persisted per legacy action"),
        GuardrailResult("allocation_band", "not_checked", str(action.get("allocation_impact", "") or "allocation impact unavailable")),
        GuardrailResult("concentration_limits", "not_checked", "theme/company/top-3 concentration details are not persisted per legacy action"),
    ]
    for hit in sorted(constraint_hits):
        if hit == "core_dca_fixed_rule":
            continue
        result = "block" if hit in {"risk_veto", "execution_not_eligible"} or "block" in hit else "pass"
        guardrails.append(GuardrailResult(f"legacy_constraint:{hit}", result, f"legacy constraint hit: {hit}"))
    return guardrails


def evidence_refs(report_date: str, generated_at: str, action: dict[str, Any], position: dict[str, Any], portfolio_source_path: str, *, kind: str) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    seed_kind = str(action.get("_seed_source_kind", "validated_advice") or "validated_advice")
    seed_path = str(action.get("_seed_source_path", f"db/validated_advice/{report_date}.json") or f"db/validated_advice/{report_date}.json")
    seed_label = "Native action seed" if seed_kind == "native_action_seed" else "Legacy validated action"
    if kind == "support":
        refs.append(
            EvidenceRef(
                ref_id=f"validated:{report_date}:{source_record_id(action)}",
                source_kind=seed_kind,
                source_path=seed_path,
                source_record_id=source_record_id(action),
                as_of_date=report_date,
                available_from=generated_at,
                summary=f"{seed_label} {normalize_action(action.get('validated_action'))} amount {safe_float(action.get('validated_amount')):.2f}.",
            )
        )
        if position:
            refs.append(
                EvidenceRef(
                    ref_id=f"portfolio:{report_date}:{position.get('fund_code')}",
                    source_kind="portfolio_state",
                    source_path=portfolio_source_path,
                    source_record_id=str(position.get("fund_code", "")),
                    as_of_date=str(position.get("as_of_date", report_date) or report_date),
                    available_from=generated_at,
                    summary=f"Position value {safe_float(position.get('current_value')):.2f}.",
                )
            )
    else:
        for index, item in enumerate(action.get("risks", []) or []):
            refs.append(
                EvidenceRef(
                    ref_id=f"risk:{report_date}:{action.get('fund_code')}:{index}",
                    source_kind=seed_kind,
                    source_path=seed_path,
                    source_record_id=source_record_id(action),
                    as_of_date=report_date,
                    available_from=generated_at,
                    summary=str(item),
                )
            )
        for hit in action.get("constraint_hits", []) or []:
            refs.append(
                EvidenceRef(
                    ref_id=f"constraint:{report_date}:{action.get('fund_code')}:{hit}",
                    source_kind=seed_kind,
                    source_path=seed_path,
                    source_record_id=source_record_id(action),
                    as_of_date=report_date,
                    available_from=generated_at,
                    summary=f"Legacy constraint hit: {hit}",
                )
            )
    return refs


def soft_adjustments(action: dict[str, Any]) -> list[SoftPolicyAdjustment]:
    adjustments: list[SoftPolicyAdjustment] = []
    for hit in action.get("policy_rule_hits", []) or []:
        if str(hit).startswith("legacy_constraint:"):
            adjustments.append(
                SoftPolicyAdjustment(
                    policy_id=str(hit),
                    effect_type="note",
                    effect_value=str(hit),
                    reason="legacy constraint carried in policy_rule_hits by adapter replay",
                )
            )
            continue
        reason = "carried from legacy policy_rule_hits"
        if hit == "core_dca_only":
            reason = "legacy DCA-only context retained as a soft note; it is not a hard Phase 1 ticket constraint"
        adjustments.append(SoftPolicyAdjustment(policy_id=f"legacy_policy:{hit}", effect_type="note", effect_value=str(hit), reason=reason))
    if "core_dca_fixed_rule" in {str(item) for item in (action.get("constraint_hits", []) or [])}:
        adjustments.append(
            SoftPolicyAdjustment(
                policy_id="legacy_constraint:core_dca_fixed_rule",
                effect_type="note",
                effect_value="retained_as_context_not_hard_block",
                reason="user removed the DCA-only hard recommendation restriction for new action tickets",
            )
        )
    for note in action.get("validation_notes", []) or []:
        if "optimizer" in str(note).lower():
            adjustments.append(SoftPolicyAdjustment(policy_id="legacy_optimizer_note", effect_type="note", effect_value=str(note), reason="carried from legacy validation_notes"))
    return adjustments


def synthesize_missing_hold(report_date: str, fund: dict[str, Any]) -> dict[str, Any]:
    return {
        "suggestion_id": f"{report_date}:{fund.get('fund_code')}:hold:synthetic",
        "fund_code": fund.get("fund_code", ""),
        "fund_name": fund.get("fund_name", ""),
        "strategy_bucket": fund.get("strategy_bucket", fund.get("role", "")),
        "validated_action": "hold",
        "validated_amount": 0.0,
        "model_action": "hold",
        "priority": 999,
        "confidence": 0.0,
        "thesis": "No legacy validated action was found for this fund; Phase 1 emits an all-fund shadow hold ticket for review coverage.",
        "evidence": [],
        "risks": [],
        "agent_support": [],
        "policy_rule_hits": ["all_fund_ticket_coverage"],
        "constraint_hits": [],
        "allocation_impact": "",
        "cash_impact": "",
        "change_vs_prev_day": {"changed": False, "reason_category": "missing_legacy_action"},
        "execution_friction": [],
        "validation_notes": ["Synthetic shadow hold generated to satisfy all-fund ticket coverage."],
        "execution_status": "not_applicable",
        "executed_amount": 0.0,
        "_source_bucket": "synthetic_missing_action",
        "_source_index": 0,
        "_missing_data": ["legacy_validated_action"],
    }


def ticket_from_action(
    *,
    report_date: str,
    generated_at: str,
    sequence: int,
    validated: dict[str, Any],
    action: dict[str, Any],
    position: dict[str, Any],
    committee: dict[str, Any],
    root_source_artifacts: list[dict[str, Any]],
    total_value: float,
) -> ActionTicket:
    action_verb = normalize_action(action.get("validated_action"))
    validated_amount = safe_float(action.get("validated_amount"))
    current_value = safe_float(position.get("current_value")) if position else 0.0
    requested = requested_amount_for(action, committee)
    thesis = str(action.get("thesis", "") or "").strip()
    if not thesis:
        thesis = f"{action.get('fund_name') or position.get('fund_name', '')} has no legacy thesis; emitted as an explicit shadow ticket for review."
    ticket_status = infer_status(action, committee)
    missing_data = list(action.get("_missing_data", []) or [])
    if not position:
        missing_data.append("portfolio_position")
    return ActionTicket(
        ticket_id=f"ticket:{report_date}:{action.get('fund_code')}:{action_verb}:{sequence:03d}",
        schema_version=SCHEMA_VERSION,
        report_date=report_date,
        generated_at=generated_at,
        fund_code=str(action.get("fund_code", "") or ""),
        fund_name=str(action.get("fund_name") or position.get("fund_name", "") or ""),
        role=str(position.get("role", "") or ""),
        category=str(action.get("category") or position.get("category", "") or ""),
        portfolio_bucket=str(action.get("strategy_bucket") or position.get("strategy_bucket") or position.get("role", "") or ""),
        action_verb=action_verb,
        execution_mode=execution_mode_for(action_verb),
        ticket_status=ticket_status,
        non_executable=True,
        write_scope="shadow_only",
        requested_amount=requested,
        validated_amount=validated_amount,
        size_bucket=str(action.get("size_bucket") or ("zero" if validated_amount == 0 else "legacy_amount")),
        percent_of_position=ratio(validated_amount, current_value),
        percent_of_portfolio=ratio(validated_amount, total_value),
        confidence=safe_float(action.get("confidence")),
        thesis=thesis,
        hard_guardrail_results=build_guardrails(validated, action, committee),
        supporting_evidence_refs=evidence_refs(report_date, generated_at, action, position, portfolio_source_path(root_source_artifacts), kind="support"),
        opposing_evidence_refs=evidence_refs(report_date, generated_at, action, position, portfolio_source_path(root_source_artifacts), kind="oppose"),
        soft_policy_adjustments=soft_adjustments(action),
        opportunity_cost={
            "status": "not_estimated" if action_verb == "hold" else "not_applicable",
            "reason": "Phase 1 records the ticket; outcome attribution is handled in later phases.",
        },
        invalidation_conditions=list(action.get("risks", []) or [])[:3],
        missing_data=missing_data,
        source_artifacts=root_source_artifacts,
        legacy_mapping={
            "suggestion_id": action.get("suggestion_id", ""),
            "source_bucket": action.get("_source_bucket", ""),
            "source_index": action.get("_source_index"),
            "model_action": action.get("model_action", ""),
            "validated_action": action.get("validated_action", ""),
            "execution_status": action.get("execution_status", ""),
            "priority": action.get("priority"),
        },
    )


def build_action_ticket_artifact(
    agent_home: Path,
    report_date: str,
    *,
    generated_at: str | None = None,
    all_funds: bool = True,
    source_mode: str = "validated",
) -> ActionTicketArtifact:
    if source_mode not in {"validated", "native"}:
        raise ValueError(f"unsupported action ticket source_mode: {source_mode}")
    validated_path = validated_advice_path(agent_home, report_date)
    if source_mode == "validated" and not validated_path.exists():
        raise FileNotFoundError(f"validated advice not found: {validated_path}")
    portfolio_path, portfolio = load_portfolio_state_for_report(
        agent_home,
        report_date,
        allow_prior_current=source_mode == "native",
    )
    if source_mode == "native":
        seed_path, seed_payload = build_native_action_seeds(
            agent_home,
            report_date,
            portfolio=portfolio,
            portfolio_source_path=portfolio_path,
            strategy=load_strategy(agent_home),
            generated_at=generated_at,
        )
        validated: dict[str, Any] = {
            "generated_at": seed_payload.get("generated_at", ""),
            "decision_mode": "canonical",
            "execution_eligible": True,
            "committee_decision_bundle": {"fund_decisions": []},
        }
        actions = list(seed_payload.get("actions", []) or [])
        by_code = {str(item.get("fund_code", "")): item for item in actions if isinstance(item, dict) and item.get("fund_code")}
        committee_by_code: dict[str, dict[str, Any]] = {}
        generated_at = generated_at or str(seed_payload.get("generated_at", "") or timestamp_now())
    else:
        seed_path = validated_path
        validated = load_json(validated_path)
        generated_at = generated_at or str(validated.get("generated_at", "") or timestamp_now())
        actions, by_code = collect_legacy_actions(validated)
        committee_by_code = committee_decision_by_code(validated)
    portfolio_state_date = portfolio_as_of_date(portfolio)
    root_sources = source_artifacts(agent_home, report_date, seed_path, portfolio_path, source_mode=source_mode)
    for source in root_sources:
        if source.get("kind") == "portfolio_state":
            source["as_of_date"] = portfolio_state_date
            source["carried_forward"] = bool(portfolio_state_date and portfolio_state_date != report_date)
    positions = {
        code: {**position, "as_of_date": str(position.get("as_of_date", "") or portfolio_state_date or report_date)}
        for code, position in fund_lookup(portfolio).items()
    }
    if all_funds:
        for fund in portfolio_funds(portfolio):
            code = str(fund.get("fund_code"))
            if code not in by_code:
                action = synthesize_missing_hold(report_date, fund)
                actions.append(action)
                by_code[code] = action
    total_value = safe_float(portfolio.get("total_value"))
    sequence_by_key: dict[tuple[str, str], int] = {}
    tickets: list[ActionTicket] = []
    for action in sorted(actions, key=lambda item: (int(item.get("priority", 999) or 999), str(item.get("fund_code", "")), str(item.get("_source_bucket", "")))):
        code = str(action.get("fund_code", "") or "")
        action_verb = normalize_action(action.get("validated_action"))
        key = (code, action_verb)
        sequence_by_key[key] = sequence_by_key.get(key, 0) + 1
        tickets.append(
            ticket_from_action(
                report_date=report_date,
                generated_at=generated_at,
                sequence=sequence_by_key[key],
                validated=validated,
                action=action,
                position=positions.get(code, {}),
                committee=committee_by_code.get(code, {}),
                root_source_artifacts=root_sources,
                total_value=total_value,
            )
        )
    hold_tickets = [item for item in tickets if item.action_verb == "hold"]
    silent_holds = [item for item in hold_tickets if not item.thesis and not item.supporting_evidence_refs]
    blocked_count = sum(1 for item in tickets if item.ticket_status == "blocked")
    adjusted_count = sum(1 for item in tickets if item.ticket_status == "adjusted")
    return ActionTicketArtifact(
        schema_version=SCHEMA_VERSION,
        artifact_id=f"action_tickets:{report_date}",
        artifact_kind="action_ticket_shadow",
        report_date=report_date,
        generated_at=generated_at,
        write_scope="shadow_only",
        non_executable=True,
        source_artifacts=root_sources,
        summary={
            "ticket_count": len(tickets),
            "action_count": sum(1 for item in tickets if item.action_verb != "hold"),
            "hold_ticket_count": len(hold_tickets),
            "all_fund_ticket_count": len(tickets),
            "blocked_count": blocked_count,
            "adjusted_count": adjusted_count,
            "degraded_count": sum(1 for item in tickets if item.ticket_status == "degraded"),
            "missing_data_ticket_count": sum(1 for item in tickets if item.missing_data),
            "silent_hold_rate": round(len(silent_holds) / len(hold_tickets), 4) if hold_tickets else 0.0,
            "non_executable_violation_count": 0,
            "official_advice_unchanged": True,
            "source_mode": source_mode,
            "portfolio_state_as_of_date": portfolio_state_date,
            "portfolio_state_carried_forward": bool(portfolio_state_date and portfolio_state_date != report_date),
        },
        tickets=tickets,
    )


def write_action_ticket_artifact(agent_home: Path, artifact: ActionTicketArtifact) -> Path:
    path = action_ticket_path(agent_home, artifact.report_date)
    payload = artifact.to_dict()
    assert_refactor_write_allowed(path, payload, agent_home)
    dump_json(path, payload)
    return path


def run_builder(
    agent_home: Path,
    report_date: str,
    *,
    generated_at: str | None = None,
    all_funds: bool = True,
    source_mode: str = "validated",
) -> tuple[Path, ActionTicketArtifact]:
    artifact = build_action_ticket_artifact(agent_home, report_date, generated_at=generated_at, all_funds=all_funds, source_mode=source_mode)
    path = write_action_ticket_artifact(agent_home, artifact)
    return path, artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build standalone non-executable action tickets from validated advice.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", required=True, help="Report date in YYYY-MM-DD.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp for deterministic tests.")
    parser.add_argument("--no-all-funds", action="store_true", help="Only emit tickets for legacy validated actions.")
    parser.add_argument("--source-mode", choices=["validated", "native"], default="validated", help="Seed tickets from legacy validated advice or native portfolio/context facts.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    path, artifact = run_builder(agent_home, report_date, generated_at=args.generated_at or None, all_funds=not args.no_all_funds, source_mode=args.source_mode)
    print(f"wrote {len(artifact.tickets)} action tickets: {relative_posix(path, agent_home)}")


if __name__ == "__main__":
    main()
