from __future__ import annotations

import argparse
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from artifact_boundary import assert_refactor_write_allowed, relative_posix
from build_action_ticket_shadow import load_portfolio_state_for_report
from common import (
    actual_trade_path,
    benchmark_history_path,
    dump_json,
    load_benchmark_mappings,
    load_json,
    parse_date_text,
    quote_path,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
    trading_days_between,
)
from outcome_event_models import SCHEMA_VERSION, OutcomeEvent, OutcomeEventArtifact
from portfolio_state import daily_pnl_units_are_trusted
from revalue_portfolio_official_nav import has_cashflow_between_nav_dates


DEFAULT_HORIZONS = ("T+1", "T+5")
SCORABLE_ACTIONS = {"add", "scheduled_dca", "reduce", "hold", "switch_in", "switch_out"}
UNIT_REQUIRED_ACTIONS = {"reduce", "switch_out"}


def action_ticket_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "action_tickets" / f"{report_date}.json"


def outcome_event_path(agent_home: Path, base_date: str, horizon: str) -> Path:
    safe_horizon = str(horizon).replace("/", "_").replace("\\", "_").replace(":", "_")
    return agent_home / "db" / "outcome_events" / f"{base_date}__{safe_horizon}.json"


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def horizon_days(horizon: str) -> int:
    text = str(horizon or "").strip().upper()
    if not text.startswith("T+"):
        raise ValueError(f"unsupported horizon: {horizon}")
    try:
        days = int(text[2:])
    except ValueError as exc:
        raise ValueError(f"unsupported horizon: {horizon}") from exc
    if days <= 0:
        raise ValueError(f"unsupported horizon: {horizon}")
    return days


def target_date_for(base_date: str, horizon: str) -> str:
    base = parse_date_text(base_date)
    if base is None:
        raise ValueError(f"invalid base_date: {base_date}")
    return (base + timedelta(days=horizon_days(horizon))).isoformat()


def evaluation_date_for(base_date: str, horizon: str) -> str:
    return target_date_for(base_date, horizon)


def evaluation_date_selection(agent_home: Path, base_date: str, horizon: str) -> dict[str, str]:
    target_date = target_date_for(base_date, horizon)
    target_quote = quote_path(agent_home, target_date)
    if target_quote.exists():
        return {
            "target_date": target_date,
            "evaluation_date": target_date,
            "evaluation_date_used": target_date,
            "date_match_type": "same_day",
        }

    search_end = (parse_date_text(target_date) + timedelta(days=14)).isoformat() if parse_date_text(target_date) else target_date
    for candidate in trading_days_between(agent_home, target_date, search_end):
        if quote_path(agent_home, candidate).exists():
            return {
                "target_date": target_date,
                "evaluation_date": candidate,
                "evaluation_date_used": candidate,
                "date_match_type": "next_available_official_nav",
            }

    return {
        "target_date": target_date,
        "evaluation_date": target_date,
        "evaluation_date_used": "",
        "date_match_type": "missing_after_target",
    }


def next_quote_payload_for_code(
    agent_home: Path,
    code: str,
    target_date: str,
    preferred_date: str,
    preferred_payload: dict[str, Any],
) -> tuple[str, dict[str, Any], str]:
    if preferred_payload and quote_by_code(preferred_payload).get(code):
        return preferred_date, preferred_payload, "same_day" if preferred_date == target_date else "next_available_official_nav"

    parsed_target = parse_date_text(target_date)
    if parsed_target is None:
        return preferred_date, preferred_payload, "missing_after_target"
    search_end = (parsed_target + timedelta(days=14)).isoformat()
    for candidate in trading_days_between(agent_home, target_date, search_end):
        if candidate == preferred_date and preferred_payload:
            continue
        payload = load_json_if_exists(quote_path(agent_home, candidate))
        if quote_by_code(payload).get(code):
            return candidate, payload, "next_available_official_nav"
    return preferred_date, preferred_payload, "missing_after_target"


def quote_by_code(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("code") or item.get("fund_code") or ""): item
        for item in payload.get("funds", []) or payload.get("items", []) or []
        if isinstance(item, dict) and (item.get("code") or item.get("fund_code"))
    }


def portfolio_fund_by_code(portfolio: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("fund_code", "") or ""): item
        for item in portfolio.get("funds", []) or []
        if isinstance(item, dict) and item.get("fund_code")
    }


def safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def official_nav_ref(quote_payload: dict[str, Any], quote: dict[str, Any], source_path: str) -> dict[str, Any]:
    return {
        "nav_date": str(quote.get("as_of_date", "") or ""),
        "nav": safe_float(quote.get("nav")),
        "source_path": source_path,
        "available_from": str(quote.get("retrieved_at") or quote_payload.get("generated_at") or ""),
        "date_match_type": str(quote.get("date_match_type", "") or ""),
        "freshness_status": str(quote.get("freshness_status", "") or quote.get("date_match_type", "") or ""),
    }


def source_artifacts(agent_home: Path, paths: list[Path]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        artifacts.append(
            {
                "kind": infer_source_kind(path),
                "path": relative_posix(path, agent_home),
                "content_sha256": content_sha256(path),
            }
        )
    artifacts.append({"kind": "builder", "path": "scripts/evaluate_action_ticket_outcomes.py", "content_sha256": ""})
    return artifacts


def infer_source_kind(path: Path) -> str:
    parts = [part.lower() for part in path.parts]
    if "action_tickets" in parts:
        return "action_ticket"
    if "portfolio_state" in parts:
        return "portfolio_state"
    if "quotes" in parts:
        return "official_nav"
    if "benchmark_history" in parts:
        return "benchmark"
    if "actual_trades" in parts:
        return "actual_trades"
    return "source_artifact"


def benchmark_mapping(agent_home: Path, fund_code: str) -> dict[str, Any]:
    mappings = load_benchmark_mappings(agent_home).get("fund_benchmarks", {}) or {}
    item = mappings.get(fund_code, {}) or {}
    return item if isinstance(item, dict) else {}


def history_return_pct(path: Path, start_date: str, end_date: str) -> float | None:
    if not path.exists():
        return None
    payload = load_json_if_exists(path)
    items = {
        str(item.get("date", "") or ""): item
        for item in payload.get("items", []) or []
        if isinstance(item, dict) and item.get("date")
    }
    start = safe_float((items.get(start_date) or {}).get("nav"))
    end = safe_float((items.get(end_date) or {}).get("nav"))
    if start is None or end is None or start <= 0:
        return None
    return round((end / start - 1.0) * 100.0, 4)


def benchmark_ref(agent_home: Path, ticket: dict[str, Any], start_date: str, end_date: str) -> tuple[dict[str, Any], Path | None]:
    fund_code = str(ticket.get("fund_code", "") or "")
    mapping = benchmark_mapping(agent_home, fund_code)
    key = str(mapping.get("benchmark_key") or mapping.get("proxy_symbol") or "").strip()
    if not key:
        return {}, None
    path = benchmark_history_path(agent_home, key)
    return_pct = history_return_pct(path, start_date, end_date)
    return (
        {
            "benchmark_id": f"benchmark:{key}",
            "benchmark_name": str(mapping.get("benchmark_name") or mapping.get("proxy_name") or key),
            "return_pct": return_pct,
            "source_path": relative_posix(path, agent_home),
            "available_from": str(load_json_if_exists(path).get("generated_at", "") or "") if path.exists() else "",
            "status": "present" if return_pct is not None else "missing",
        },
        path if path.exists() else None,
    )


def has_existing_position(position: dict[str, Any]) -> bool:
    return bool(position) and (
        safe_float(position.get("current_value")) or 0.0
    ) > 0


def decision_context_for(ticket: dict[str, Any], position: dict[str, Any]) -> dict[str, Any]:
    action_verb = str(ticket.get("action_verb", "") or "")
    legacy = ticket.get("legacy_mapping", {}) if isinstance(ticket.get("legacy_mapping"), dict) else {}
    model_action = str(legacy.get("model_action", "") or "").strip()
    policy_hits = {
        str(item.get("effect_value", "") or item.get("policy_id", "") or "")
        for item in ticket.get("soft_policy_adjustments", []) or []
        if isinstance(item, dict)
    }
    constraint_hits = {
        str(item.get("rule_id", "") or "")
        for item in ticket.get("hard_guardrail_results", []) or []
        if isinstance(item, dict) and item.get("result") == "block"
    }
    existing = has_existing_position(position)
    if action_verb == "hold":
        if existing:
            exposure_context = "hold_existing_position"
        elif model_action and model_action != "hold":
            exposure_context = "blocked_add_or_cash_hold"
        elif policy_hits & {"committee_bundle_fund_gate", "committee_bundle_gate"} or constraint_hits:
            exposure_context = "blocked_add_or_cash_hold"
        else:
            exposure_context = "unclear_hold_context"
    elif action_verb in {"reduce", "switch_out"}:
        exposure_context = "reduce_exposure"
    elif action_verb in {"add", "scheduled_dca", "switch_in"}:
        exposure_context = "increase_exposure"
    else:
        exposure_context = "unknown"
    return {
        "exposure_context": exposure_context,
        "has_existing_position": existing,
        "position_value": safe_float(position.get("current_value")) if position else None,
        "model_action": model_action,
        "learning_eligible": exposure_context not in {"unclear_hold_context", "unknown"},
    }


def outcome_label(action_verb: str, actual_return_pct: float, exposure_context: str = "") -> tuple[str, str]:
    if action_verb == "hold":
        if exposure_context == "hold_existing_position":
            if actual_return_pct > 0:
                return "helped", "hold_existing_position_positive_nav_follow_through"
            if actual_return_pct < 0:
                return "hurt", "hold_existing_position_negative_nav_follow_through"
            return "neutral", "hold_existing_position_neutral_nav_follow_through"
        if exposure_context == "blocked_add_or_cash_hold":
            if actual_return_pct < 0:
                return "avoided_loss", "blocked_add_or_cash_hold_avoided_negative_nav_follow_through"
            if actual_return_pct > 0:
                return "missed_opportunity", "blocked_add_or_cash_hold_missed_positive_nav_follow_through"
            return "neutral", "blocked_add_or_cash_hold_neutral_nav_follow_through"
        return "neutral", "unclear_hold_context_not_scored_for_learning"
    if action_verb in {"reduce", "switch_out"}:
        if actual_return_pct < 0:
            return "avoided_loss", "reduce_exposure_avoided_negative_nav_follow_through"
        if actual_return_pct > 0:
            return "missed_opportunity", "reduce_exposure_missed_positive_nav_follow_through"
        return "neutral", "reduce_exposure_neutral_nav_follow_through"
    if actual_return_pct > 0:
        return "helped", f"{action_verb}_positive_nav_follow_through"
    if actual_return_pct < 0:
        return "hurt", f"{action_verb}_negative_nav_follow_through"
    return "neutral", f"{action_verb}_neutral_nav_follow_through"


def source_refs_for_event(agent_home: Path, base_date: str, evaluation_date: str, ticket_index: int, start_date: str, end_date: str) -> list[dict[str, Any]]:
    return [
        {
            "kind": "action_ticket",
            "path": relative_posix(action_ticket_path(agent_home, base_date), agent_home),
            "json_pointer": f"/tickets/{ticket_index}",
        },
        {
            "kind": "official_nav_start",
            "path": relative_posix(quote_path(agent_home, base_date), agent_home),
            "record_id": start_date,
        },
        {
            "kind": "official_nav_end",
            "path": relative_posix(quote_path(agent_home, evaluation_date), agent_home),
            "record_id": end_date,
        },
    ]


def pending_event(ticket: dict[str, Any], base_date: str, evaluation_date: str, horizon: str, ticket_index: int, reason: str) -> OutcomeEvent:
    return event_from_parts(
        ticket=ticket,
        base_date=base_date,
        evaluation_date=evaluation_date,
        horizon=horizon,
        ticket_index=ticket_index,
        scoring_status="pending",
        blocked_reason=reason,
        official_nav_start={},
        official_nav_end={},
        benchmark={},
        actual_return_pct=None,
        benchmark_return_pct=None,
        excess_return_pct=None,
        outcome_label_value="not_scored",
        diagnostic_label="pending_required_official_data",
        cashflow_checks={"cashflow_between_nav_dates": None, "units_trusted": None, "position_authoritative": None},
        source_refs=[],
    )


def not_applicable_event(ticket: dict[str, Any], base_date: str, evaluation_date: str, horizon: str, ticket_index: int, reason: str) -> OutcomeEvent:
    return event_from_parts(
        ticket=ticket,
        base_date=base_date,
        evaluation_date=evaluation_date,
        horizon=horizon,
        ticket_index=ticket_index,
        scoring_status="not_applicable",
        blocked_reason=reason,
        official_nav_start={},
        official_nav_end={},
        benchmark={},
        actual_return_pct=None,
        benchmark_return_pct=None,
        excess_return_pct=None,
        outcome_label_value="not_scored",
        diagnostic_label="not_applicable_for_horizon",
        cashflow_checks={"cashflow_between_nav_dates": None, "units_trusted": None, "position_authoritative": None},
        source_refs=[],
    )


def blocked_event(
    *,
    ticket: dict[str, Any],
    base_date: str,
    evaluation_date: str,
    horizon: str,
    ticket_index: int,
    reason: str,
    official_nav_start: dict[str, Any],
    official_nav_end: dict[str, Any],
    benchmark: dict[str, Any],
    cashflow_checks: dict[str, Any],
    source_refs: list[dict[str, Any]],
) -> OutcomeEvent:
    return event_from_parts(
        ticket=ticket,
        base_date=base_date,
        evaluation_date=evaluation_date,
        horizon=horizon,
        ticket_index=ticket_index,
        scoring_status="blocked",
        blocked_reason=reason,
        official_nav_start=official_nav_start,
        official_nav_end=official_nav_end,
        benchmark=benchmark,
        actual_return_pct=None,
        benchmark_return_pct=benchmark.get("return_pct"),
        excess_return_pct=None,
        outcome_label_value="not_scored",
        diagnostic_label=f"blocked:{reason}",
        cashflow_checks=cashflow_checks,
        source_refs=source_refs,
    )


def event_from_parts(
    *,
    ticket: dict[str, Any],
    base_date: str,
    evaluation_date: str,
    horizon: str,
    ticket_index: int,
    scoring_status: str,
    blocked_reason: str,
    official_nav_start: dict[str, Any],
    official_nav_end: dict[str, Any],
    benchmark: dict[str, Any],
    actual_return_pct: float | None,
    benchmark_return_pct: float | None,
    excess_return_pct: float | None,
    outcome_label_value: str,
    diagnostic_label: str,
    cashflow_checks: dict[str, Any],
    source_refs: list[dict[str, Any]],
    decision_context: dict[str, Any] | None = None,
) -> OutcomeEvent:
    action_verb = str(ticket.get("action_verb", "") or "")
    baseline_type = "hold_cash"
    if decision_context:
        exposure_context = str(decision_context.get("exposure_context", "") or "")
        if exposure_context == "hold_existing_position":
            baseline_type = "hold_existing_position"
        elif exposure_context == "reduce_exposure":
            baseline_type = "maintain_original_exposure"
    return OutcomeEvent(
        outcome_id=f"outcome:{base_date}:{horizon}:{ticket.get('fund_code')}:{action_verb}:{ticket_index + 1:03d}",
        ticket_id=str(ticket.get("ticket_id", "") or ""),
        base_date=base_date,
        evaluation_date=evaluation_date,
        horizon=horizon,
        fund_code=str(ticket.get("fund_code", "") or ""),
        fund_name=str(ticket.get("fund_name", "") or ticket.get("fund_code", "")),
        action_verb=action_verb,
        execution_mode=str(ticket.get("execution_mode", "") or ""),
        amount=float(safe_float(ticket.get("validated_amount")) or 0.0),
        amount_currency=str(ticket.get("amount_currency", "CNY") or "CNY"),
        scoring_status=scoring_status,
        blocked_reason=blocked_reason,
        official_nav_start=official_nav_start,
        official_nav_end=official_nav_end,
        benchmark=benchmark,
        actual_return_pct=actual_return_pct,
        benchmark_return_pct=benchmark_return_pct,
        excess_return_pct=excess_return_pct,
        no_action_baseline={
            "baseline_type": baseline_type,
            "return_pct": 0.0,
            "excess_vs_baseline_pct": actual_return_pct,
        },
        outcome_label=outcome_label_value,
        diagnostic_label=diagnostic_label,
        confidence=0.6 if scoring_status == "scored" else 0.0,
        cashflow_checks=cashflow_checks,
        decision_context=decision_context or {},
        learning_implications=[],
        source_refs=source_refs,
        audit={"builder": "scripts/evaluate_action_ticket_outcomes.py"},
    )


def evaluate_ticket(
    *,
    agent_home: Path,
    ticket: dict[str, Any],
    ticket_index: int,
    base_date: str,
    evaluation_date: str,
    horizon: str,
    base_quote_payload: dict[str, Any],
    evaluation_quote_payload: dict[str, Any],
    portfolio: dict[str, Any],
    target_date: str | None = None,
) -> tuple[OutcomeEvent, list[Path]]:
    action_verb = str(ticket.get("action_verb", "") or "")
    if action_verb not in SCORABLE_ACTIONS:
        return not_applicable_event(ticket, base_date, evaluation_date, horizon, ticket_index, "not_applicable_action"), []
    code = str(ticket.get("fund_code", "") or "")
    target_date = target_date or evaluation_date
    evaluation_date, evaluation_quote_payload, evaluation_file_match_type = next_quote_payload_for_code(
        agent_home,
        code,
        target_date,
        evaluation_date,
        evaluation_quote_payload,
    )
    if not evaluation_quote_payload:
        return pending_event(ticket, base_date, evaluation_date, horizon, ticket_index, "missing_evaluation_quote_file"), []

    base_quote = quote_by_code(base_quote_payload).get(code, {})
    evaluation_quote = quote_by_code(evaluation_quote_payload).get(code, {})
    if not base_quote:
        return pending_event(ticket, base_date, evaluation_date, horizon, ticket_index, "missing_official_nav_start"), []
    if not evaluation_quote:
        return pending_event(ticket, base_date, evaluation_date, horizon, ticket_index, "missing_official_nav_end"), []

    base_source = relative_posix(quote_path(agent_home, base_date), agent_home)
    evaluation_source = relative_posix(quote_path(agent_home, evaluation_date), agent_home)
    start = official_nav_ref(base_quote_payload, base_quote, base_source)
    end = official_nav_ref(evaluation_quote_payload, evaluation_quote, evaluation_source)
    end["target_date"] = target_date
    end["evaluation_date_used"] = evaluation_date
    end["evaluation_file_match_type"] = evaluation_file_match_type
    start_nav = safe_float(start.get("nav"))
    end_nav = safe_float(end.get("nav"))
    benchmark, benchmark_path = benchmark_ref(agent_home, ticket, str(start.get("nav_date", "")), str(end.get("nav_date", "")))
    source_refs = source_refs_for_event(
        agent_home,
        base_date,
        evaluation_date,
        ticket_index,
        str(start.get("nav_date", "")),
        str(end.get("nav_date", "")),
    )
    if benchmark_path:
        source_refs.append({"kind": "benchmark", "path": relative_posix(benchmark_path, agent_home), "record_id": benchmark.get("benchmark_id", "")})
    evaluation_path = quote_path(agent_home, evaluation_date)
    extra_sources = [path for path in (benchmark_path, evaluation_path) if path and path.exists()]
    if start_nav is None or start_nav <= 0:
        return blocked_event(
            ticket=ticket,
            base_date=base_date,
            evaluation_date=evaluation_date,
            horizon=horizon,
            ticket_index=ticket_index,
            reason="missing_official_nav_start",
            official_nav_start=start,
            official_nav_end=end,
            benchmark=benchmark,
            cashflow_checks={"cashflow_between_nav_dates": None, "units_trusted": None, "position_authoritative": None},
            source_refs=source_refs,
        ), extra_sources
    if end_nav is None or end_nav <= 0:
        return blocked_event(
            ticket=ticket,
            base_date=base_date,
            evaluation_date=evaluation_date,
            horizon=horizon,
            ticket_index=ticket_index,
            reason="missing_official_nav_end",
            official_nav_start=start,
            official_nav_end=end,
            benchmark=benchmark,
            cashflow_checks={"cashflow_between_nav_dates": None, "units_trusted": None, "position_authoritative": None},
            source_refs=source_refs,
        ), extra_sources
    if bool(base_quote.get("stale") or base_quote.get("fallback_reason") or evaluation_quote.get("stale") or evaluation_quote.get("fallback_reason")):
        return blocked_event(
            ticket=ticket,
            base_date=base_date,
            evaluation_date=evaluation_date,
            horizon=horizon,
            ticket_index=ticket_index,
            reason="stale_or_fallback_quote",
            official_nav_start=start,
            official_nav_end=end,
            benchmark=benchmark,
            cashflow_checks={"cashflow_between_nav_dates": None, "units_trusted": None, "position_authoritative": None},
            source_refs=source_refs,
        ), extra_sources

    position = portfolio_fund_by_code(portfolio).get(code, {})
    units_trusted, units_reason = daily_pnl_units_are_trusted(position) if position else (False, "missing_position")
    cashflow_between = has_cashflow_between_nav_dates(agent_home, code, str(start.get("nav_date", "")), str(end.get("nav_date", "")))
    cashflow_checks = {
        "cashflow_between_nav_dates": cashflow_between,
        "units_trusted": units_trusted,
        "position_authoritative": bool(position),
    }
    if cashflow_between:
        return blocked_event(
            ticket=ticket,
            base_date=base_date,
            evaluation_date=evaluation_date,
            horizon=horizon,
            ticket_index=ticket_index,
            reason="cashflow_between_nav_dates_requires_position_snapshot",
            official_nav_start=start,
            official_nav_end=end,
            benchmark=benchmark,
            cashflow_checks=cashflow_checks,
            source_refs=source_refs,
        ), [path for path in (*extra_sources, actual_trade_path(agent_home, evaluation_date)) if path and path.exists()]
    if action_verb in UNIT_REQUIRED_ACTIONS and not units_trusted:
        return blocked_event(
            ticket=ticket,
            base_date=base_date,
            evaluation_date=evaluation_date,
            horizon=horizon,
            ticket_index=ticket_index,
            reason=units_reason,
            official_nav_start=start,
            official_nav_end=end,
            benchmark=benchmark,
            cashflow_checks=cashflow_checks,
            source_refs=source_refs,
        ), extra_sources

    actual_return_pct = round((end_nav / start_nav - 1.0) * 100.0, 4)
    benchmark_return_pct = safe_float(benchmark.get("return_pct"))
    excess_return_pct = round(actual_return_pct - benchmark_return_pct, 4) if benchmark_return_pct is not None else None
    decision_context = decision_context_for(ticket, position)
    label, diagnostic = outcome_label(action_verb, actual_return_pct, str(decision_context.get("exposure_context", "") or ""))
    return event_from_parts(
        ticket=ticket,
        base_date=base_date,
        evaluation_date=evaluation_date,
        horizon=horizon,
        ticket_index=ticket_index,
        scoring_status="scored",
        blocked_reason="",
        official_nav_start=start,
        official_nav_end=end,
        benchmark=benchmark,
        actual_return_pct=actual_return_pct,
        benchmark_return_pct=benchmark_return_pct,
        excess_return_pct=excess_return_pct,
        outcome_label_value=label,
        diagnostic_label=diagnostic,
        cashflow_checks=cashflow_checks,
        decision_context=decision_context,
        source_refs=source_refs,
    ), extra_sources


def summarize(events: list[OutcomeEvent]) -> dict[str, Any]:
    statuses = [event.scoring_status for event in events]
    learning_eligible_count = sum(1 for event in events if event.scoring_status == "scored" and event.decision_context.get("learning_eligible") is True)
    return {
        "event_count": len(events),
        "scored_count": statuses.count("scored"),
        "pending_count": statuses.count("pending"),
        "blocked_count": statuses.count("blocked"),
        "not_applicable_count": statuses.count("not_applicable"),
        "learning_eligible_count": learning_eligible_count,
        "non_executable_violation_count": 0,
        "official_output_unchanged": True,
    }


def build_outcome_artifact(agent_home: Path, base_date: str, horizon: str, *, generated_at: str | None = None) -> OutcomeEventArtifact:
    generated_at = generated_at or timestamp_now()
    date_selection = evaluation_date_selection(agent_home, base_date, horizon)
    target_date = date_selection["target_date"]
    evaluation_date = date_selection["evaluation_date"]
    ticket_path = action_ticket_path(agent_home, base_date)
    if not ticket_path.exists():
        raise FileNotFoundError(f"action tickets not found: {ticket_path}")

    base_quote_path = quote_path(agent_home, base_date)
    evaluation_quote_path = quote_path(agent_home, evaluation_date)
    portfolio_path, portfolio = load_portfolio_state_for_report(agent_home, base_date)

    ticket_artifact = load_json_if_exists(ticket_path)
    base_quote_payload = load_json_if_exists(base_quote_path)
    evaluation_quote_payload = load_json_if_exists(evaluation_quote_path)
    source_paths = [ticket_path, base_quote_path, evaluation_quote_path, portfolio_path]
    events: list[OutcomeEvent] = []
    extra_source_paths: list[Path] = []
    for index, ticket in enumerate(ticket_artifact.get("tickets", []) or []):
        if not isinstance(ticket, dict):
            continue
        event, extra = evaluate_ticket(
            agent_home=agent_home,
            ticket=ticket,
            ticket_index=index,
            base_date=base_date,
            evaluation_date=evaluation_date,
            horizon=horizon,
            base_quote_payload=base_quote_payload,
            evaluation_quote_payload=evaluation_quote_payload,
            portfolio=portfolio,
            target_date=target_date,
        )
        events.append(event)
        extra_source_paths.extend(extra)
    unique_sources = []
    seen = set()
    for path in [*source_paths, *extra_source_paths]:
        key = str(path)
        if key not in seen:
            unique_sources.append(path)
            seen.add(key)
    return OutcomeEventArtifact(
        schema_version=SCHEMA_VERSION,
        artifact_id=f"outcome_events:{base_date}:{horizon}",
        base_date=base_date,
        target_date=target_date,
        evaluation_date=evaluation_date,
        evaluation_date_used=date_selection.get("evaluation_date_used", ""),
        date_match_type=date_selection.get("date_match_type", ""),
        horizon=horizon,
        generated_at=generated_at,
        write_scope="learning_only",
        non_executable=True,
        source_artifacts=source_artifacts(agent_home, unique_sources),
        events=events,
        summary=summarize(events),
    )


def write_outcome_artifact(agent_home: Path, artifact: OutcomeEventArtifact) -> Path:
    path = outcome_event_path(agent_home, artifact.base_date, artifact.horizon)
    payload = artifact.to_dict()
    assert_refactor_write_allowed(path, payload, agent_home)
    dump_json(path, payload)
    return path


def run_builder(agent_home: Path, base_date: str, horizon: str, *, generated_at: str | None = None) -> tuple[Path, OutcomeEventArtifact]:
    artifact = build_outcome_artifact(agent_home, base_date, horizon, generated_at=generated_at)
    path = write_outcome_artifact(agent_home, artifact)
    return path, artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate non-executable action-ticket outcome events.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", required=True, help="Base report date in YYYY-MM-DD.")
    parser.add_argument("--horizon", default="T+1", help="Outcome horizon such as T+1 or T+5.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp for deterministic tests.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    base_date = resolve_date(args.date)
    path, artifact = run_builder(agent_home, base_date, args.horizon, generated_at=args.generated_at or None)
    summary = artifact.summary
    print(
        "wrote "
        f"{summary.get('event_count', 0)} outcome events "
        f"({summary.get('scored_count', 0)} scored, {summary.get('pending_count', 0)} pending, {summary.get('blocked_count', 0)} blocked): "
        f"{relative_posix(path, agent_home)}"
    )


if __name__ == "__main__":
    main()
