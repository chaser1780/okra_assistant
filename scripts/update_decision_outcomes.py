from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from common import decisions_path, dump_json, ensure_layout, fund_nav_history_path, load_json, resolve_agent_home, resolve_date, timestamp_now
from decision_ledger import append_decision_ledger, default_attribution, default_outcomes, load_decisions

WINDOWS = {"t1": 1, "t3": 3, "t5": 5, "t20": 20}


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def load_nav_items(agent_home: Path, fund_code: str) -> list[dict]:
    path = fund_nav_history_path(agent_home, fund_code)
    if not path.exists():
        return []
    payload = load_json(path)
    return list(payload.get("items", []) or []) if isinstance(payload, dict) else []


def nav_on_or_after(items: list[dict], date_text: str) -> dict | None:
    for item in sorted(items, key=lambda value: str(value.get("date", ""))):
        if str(item.get("date", "")) >= date_text and item.get("nav") is not None:
            return item
    return None


def classify_attribution(decision: dict, ready_outcomes: list[dict]) -> dict:
    attribution = dict(decision.get("attribution", {}) or default_attribution())
    if not ready_outcomes:
        attribution["primary_reason"] = "pending_outcome"
        return attribution
    latest = ready_outcomes[-1]
    action = str(decision.get("validated_action", "hold"))
    nav_return = float(latest.get("nav_return", 0.0) or 0.0)
    if action in {"add", "buy", "scheduled_dca"} and nav_return > 0:
        reason = "action_supported_by_outcome"
    elif action in {"reduce", "sell", "switch_out"} and nav_return < 0:
        reason = "risk_reduction_helped"
        attribution["risk_constraint_helped"] = bool(decision.get("constraints"))
    elif action == "hold":
        reason = "hold_baseline"
    else:
        reason = "action_not_supported_by_outcome"
    attribution["primary_reason"] = reason
    attribution["data_quality_issue"] = any("stale" in str(ref).lower() or "fallback" in str(ref).lower() for ref in decision.get("evidence_refs", []))
    return attribution


def update_decision(agent_home: Path, decision: dict, today: str) -> dict:
    updated = dict(decision)
    outcomes = dict(updated.get("outcomes", {}) or default_outcomes())
    report_date = str(updated.get("report_date", ""))
    fund_code = str(updated.get("fund_code", ""))
    if not report_date or not fund_code:
        updated["outcomes"] = outcomes
        updated["attribution"] = dict(updated.get("attribution", {}) or default_attribution())
        return updated
    nav_items = load_nav_items(agent_home, fund_code)
    base = nav_on_or_after(nav_items, report_date)
    ready: list[dict] = []
    for key, days in WINDOWS.items():
        current = dict(outcomes.get(key, {}) or {"nav_return": 0.0, "vs_hold": 0.0, "status": "pending"})
        target_date = (parse_date(report_date) + timedelta(days=days)).date().isoformat()
        if target_date > today:
            current.update({"status": "pending"})
        elif base is None:
            current.update({"status": "missing"})
        else:
            target = nav_on_or_after(nav_items, target_date)
            if target is None:
                current.update({"status": "missing"})
            else:
                base_nav = float(base.get("nav", 0.0) or 0.0)
                target_nav = float(target.get("nav", 0.0) or 0.0)
                nav_return = round((target_nav / base_nav - 1.0) * 100.0, 4) if base_nav else 0.0
                current.update({
                    "nav_return": nav_return,
                    "vs_hold": 0.0,
                    "status": "ready",
                    "base_date": base.get("date", report_date),
                    "target_date": target.get("date", target_date),
                })
                ready.append(current)
        outcomes[key] = current
    updated["outcomes"] = outcomes
    updated["attribution"] = classify_attribution(updated, ready)
    updated["outcomes_updated_at"] = timestamp_now()
    return updated


def update_outcomes(agent_home: Path, report_date: str, today: str) -> dict:
    payload = load_decisions(agent_home, report_date)
    updated_decisions = [update_decision(agent_home, decision, today) for decision in payload.get("decisions", []) or []]
    updated = dict(payload)
    updated["decisions"] = updated_decisions
    updated["outcomes_updated_at"] = timestamp_now()
    dump_json(decisions_path(agent_home, report_date), updated)
    append_decision_ledger(agent_home, updated)
    return updated


def candidate_dates(agent_home: Path, today: str, lookback_days: int) -> list[str]:
    root = agent_home / "db" / "decisions"
    if not root.exists():
        return []
    floor = (parse_date(today) - timedelta(days=lookback_days)).date().isoformat()
    return sorted(path.stem for path in root.glob("*.json") if floor <= path.stem <= today)


def main() -> None:
    parser = argparse.ArgumentParser(description="Update decision ledger outcome windows from official NAV history.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Today/date boundary in YYYY-MM-DD format.")
    parser.add_argument("--lookback-days", type=int, default=30)
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    today = resolve_date(args.date)
    updated = []
    for report_date in candidate_dates(agent_home, today, args.lookback_days):
        updated.append(update_outcomes(agent_home, report_date, today))
    print(dump_json(agent_home / "db" / "decisions" / f"outcome_update_{today}.json", {"date": today, "updated_count": len(updated), "updated_dates": [item.get("report_date") for item in updated]}))


if __name__ == "__main__":
    main()
