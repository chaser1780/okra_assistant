from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from common import (
    agent_output_dir,
    decision_ledger_path,
    decision_latest_path,
    decisions_path,
    dump_json,
    fund_profile_path,
    llm_advice_path,
    load_json,
    load_portfolio,
    news_path,
    project_relative_path,
    quote_path,
    resolve_agent_home,
    timestamp_now,
    validated_advice_path,
)

SCHEMA_VERSION = 1
ACTION_SECTIONS = ("tactical_actions", "dca_actions", "hold_actions")


def amount_hash(amount: float | int | str) -> str:
    try:
        normalized = f"{float(amount or 0.0):.2f}"
    except (TypeError, ValueError):
        normalized = str(amount or "0")
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]


def make_decision_id(
    report_date: str,
    fund_code: str,
    action: str,
    amount: float | int | str,
    suggestion_id: str = "",
    action_section: str = "",
) -> str:
    suffix = str(suggestion_id or action_section or "action")
    safe_suffix = suffix.replace("/", "_").replace("\\", "_").replace(":", "_")
    return f"{report_date}:{fund_code}:{safe_suffix}:{action}:{amount_hash(amount)}"


def _portfolio_positions(portfolio: dict) -> dict[str, dict]:
    positions: dict[str, dict] = {}
    for fund in portfolio.get("funds", []) or []:
        code = str(fund.get("fund_code") or fund.get("code") or "")
        if not code:
            continue
        positions[code] = {
            "fund_code": code,
            "fund_name": fund.get("fund_name") or fund.get("name", ""),
            "role": fund.get("role", ""),
            "current_value": fund.get("current_value", 0.0),
            "holding_pnl": fund.get("holding_pnl", 0.0),
            "holding_return_pct": fund.get("holding_return_pct", 0.0),
            "units": fund.get("units", fund.get("holding_units", 0.0)),
        }
    return positions


def _action_items(validated: dict) -> list[dict]:
    items: list[dict] = []
    for section in ACTION_SECTIONS:
        for item in validated.get(section, []) or []:
            if item.get("fund_code"):
                copied = dict(item)
                copied["action_section"] = section
                items.append(copied)
    return items


def _evidence_refs(agent_home: Path, report_date: str, action: dict) -> list[dict]:
    refs = [
        {"kind": "quotes", "path": project_relative_path(agent_home, quote_path(agent_home, report_date))},
        {"kind": "news", "path": project_relative_path(agent_home, news_path(agent_home, report_date))},
        {"kind": "fund_profiles", "path": project_relative_path(agent_home, fund_profile_path(agent_home, report_date))},
        {"kind": "agent_aggregate", "path": project_relative_path(agent_home, agent_output_dir(agent_home, report_date) / "aggregate.json")},
        {"kind": "validated_advice", "path": project_relative_path(agent_home, validated_advice_path(agent_home, report_date))},
        {"kind": "llm_advice", "path": project_relative_path(agent_home, llm_advice_path(agent_home, report_date))},
    ]
    for signal_id in action.get("source_signal_ids", []) or []:
        refs.append({"kind": "source_signal", "id": signal_id})
    for signal_id in action.get("opposing_signal_ids", []) or []:
        refs.append({"kind": "opposing_signal", "id": signal_id})
    return refs


def default_outcomes() -> dict:
    return {
        key: {"nav_return": 0.0, "vs_hold": 0.0, "status": "pending"}
        for key in ("t1", "t3", "t5", "t20")
    }


def default_attribution() -> dict:
    return {
        "primary_reason": "pending_outcome",
        "data_quality_issue": False,
        "risk_constraint_helped": False,
        "model_bias": "",
    }


def build_decisions_from_validated(agent_home, report_date: str) -> dict:
    agent_home = resolve_agent_home(agent_home)
    validated_path = validated_advice_path(agent_home, report_date)
    validated = load_json(validated_path) if validated_path.exists() else {}
    portfolio = load_portfolio(agent_home)
    positions = _portfolio_positions(portfolio)
    created_at = timestamp_now()
    advice_is_fallback = bool(validated.get("advice_is_fallback", False))
    decision_source = str(validated.get("decision_source", "") or "")

    decisions: list[dict] = []
    for action in _action_items(validated):
        fund_code = str(action.get("fund_code", ""))
        validated_action = str(action.get("validated_action", "hold") or "hold")
        validated_amount = float(action.get("validated_amount", 0.0) or 0.0)
        risk_notes = list(action.get("risks", []) or []) + list(action.get("validation_notes", []) or [])
        constraints = list(action.get("constraint_hits", []) or []) + list(action.get("policy_rule_hits", []) or [])
        decisions.append(
            {
                "schema_version": SCHEMA_VERSION,
                "decision_id": make_decision_id(
                    report_date,
                    fund_code,
                    validated_action,
                    validated_amount,
                    str(action.get("suggestion_id", "") or ""),
                    str(action.get("action_section", "") or ""),
                ),
                "suggestion_id": action.get("suggestion_id", ""),
                "report_date": report_date,
                "fund_code": fund_code,
                "fund_name": action.get("fund_name", ""),
                "validated_action": validated_action,
                "validated_amount": validated_amount,
                "model_action": action.get("model_action", ""),
                "action_section": action.get("action_section", ""),
                "position_before": positions.get(fund_code, {}),
                "constraints": constraints,
                "risk_notes": risk_notes,
                "evidence_refs": _evidence_refs(agent_home, report_date, action),
                "decision_source": decision_source,
                "advice_is_fallback": advice_is_fallback,
                "confidence": action.get("confidence", 0.0),
                "thesis": action.get("thesis", ""),
                "cash_impact": action.get("cash_impact", ""),
                "allocation_impact": action.get("allocation_impact", ""),
                "outcomes": default_outcomes(),
                "attribution": default_attribution(),
                "created_at": created_at,
            }
        )
    return {"schema_version": SCHEMA_VERSION, "report_date": report_date, "created_at": created_at, "decisions": decisions}


def write_daily_decisions(agent_home, report_date: str, decisions: dict) -> Path:
    agent_home = resolve_agent_home(agent_home)
    path = dump_json(decisions_path(agent_home, report_date), decisions)
    write_decision_latest(agent_home, decisions)
    return path


def append_decision_ledger(agent_home, decisions: dict) -> list[Path]:
    agent_home = resolve_agent_home(agent_home)
    written: list[Path] = []
    for decision in decisions.get("decisions", []) or []:
        fund_code = str(decision.get("fund_code", ""))
        if not fund_code:
            continue
        path = decision_ledger_path(agent_home, fund_code)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing_ids: set[str] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    existing_ids.add(str(json.loads(line).get("decision_id", "")))
                except json.JSONDecodeError:
                    continue
        if decision.get("decision_id") not in existing_ids:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n")
        written.append(path)
    return written


def append_decision_outcome_events(agent_home, decisions: dict) -> list[Path]:
    agent_home = resolve_agent_home(agent_home)
    written: list[Path] = []
    updated_at = str(decisions.get("outcomes_updated_at") or timestamp_now())
    for decision in decisions.get("decisions", []) or []:
        fund_code = str(decision.get("fund_code", ""))
        decision_id = str(decision.get("decision_id", ""))
        if not fund_code or not decision_id:
            continue
        path = decision_ledger_path(agent_home, fund_code)
        path.parent.mkdir(parents=True, exist_ok=True)
        event_id = f"{decision_id}:outcome:{updated_at}"
        exists = False
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    if str(json.loads(line).get("event_id", "")) == event_id:
                        exists = True
                        break
                except json.JSONDecodeError:
                    continue
        if not exists:
            event = {
                "schema_version": SCHEMA_VERSION,
                "event_type": "outcome_update",
                "event_id": event_id,
                "decision_id": decision_id,
                "fund_code": fund_code,
                "report_date": decision.get("report_date", decisions.get("report_date", "")),
                "outcomes": decision.get("outcomes", {}),
                "attribution": decision.get("attribution", {}),
                "updated_at": updated_at,
            }
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        written.append(path)
    return written


def write_decision_latest(agent_home, decisions: dict) -> list[Path]:
    agent_home = resolve_agent_home(agent_home)
    grouped: dict[str, list[dict]] = {}
    for decision in decisions.get("decisions", []) or []:
        fund_code = str(decision.get("fund_code", ""))
        if not fund_code:
            continue
        grouped.setdefault(fund_code, []).append(decision)

    written: list[Path] = []
    for fund_code, fund_decisions in grouped.items():
        latest_date = max(str(item.get("report_date", "")) for item in fund_decisions)
        path = decision_latest_path(agent_home, fund_code)
        if path.exists():
            existing = load_json(path)
            if isinstance(existing, dict) and str(existing.get("report_date", "")) > latest_date:
                continue
        latest_decisions = [item for item in fund_decisions if str(item.get("report_date", "")) == latest_date]
        latest_decisions.sort(key=lambda item: str(item.get("decision_id", "")))
        decision = latest_decisions[-1] if latest_decisions else {}
        payload = {
            "schema_version": SCHEMA_VERSION,
            "fund_code": fund_code,
            "report_date": latest_date,
            "updated_at": timestamp_now(),
            "decision": decision,
            "decisions": latest_decisions,
        }
        dump_json(path, payload)
        written.append(path)
    return written


def load_decision_latest(agent_home, fund_code: str) -> dict:
    agent_home = resolve_agent_home(agent_home)
    path = decision_latest_path(agent_home, fund_code)
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def load_decisions(agent_home, report_date: str) -> dict:
    agent_home = resolve_agent_home(agent_home)
    path = decisions_path(agent_home, report_date)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "report_date": report_date, "decisions": []}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {"schema_version": SCHEMA_VERSION, "report_date": report_date, "decisions": []}


def build_and_write_decisions(agent_home, report_date: str) -> dict:
    decisions = build_decisions_from_validated(agent_home, report_date)
    write_daily_decisions(agent_home, report_date, decisions)
    append_decision_ledger(agent_home, decisions)
    return decisions
