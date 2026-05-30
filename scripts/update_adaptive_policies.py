from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from adaptive_policy_models import (
    ALLOWED_POLICY_EFFECTS,
    EVENT_SCHEMA_VERSION,
    FORBIDDEN_POLICY_EFFECTS,
    POLICY_SCHEMA_VERSION,
    STORE_SCHEMA_VERSION,
    AdaptivePolicy,
    AdaptivePolicyEvent,
    AdaptivePolicyStore,
)
from artifact_boundary import assert_refactor_write_allowed, relative_posix
from common import dump_json, load_json, resolve_agent_home, resolve_date, timestamp_now
from evaluate_action_ticket_outcomes import outcome_event_path
from outcome_event_models import OutcomeEventArtifact


SUPPORTIVE_OUTCOME_LABELS = {"helped", "avoided_loss"}
CONTRADICTORY_OUTCOME_LABELS = {"hurt", "missed_opportunity"}
DEFAULT_CAPS = {
    "min_support_count_for_candidate": 2,
    "min_support_count_for_active": 5,
    "max_contradiction_ratio_for_active": 0.25,
    "max_active_policies_per_scope": 5,
    "max_candidate_policies_per_scope": 20,
    "archive_if_contradiction_ratio_above": 0.6,
    "min_total_count_for_contradiction_archive": 3,
}


@dataclass
class PolicyAccumulator:
    policy_id: str
    scope: str
    statement: str
    when_to_apply: dict[str, Any]
    effect_type: str
    effect_value: Any
    support_count: int = 0
    contradiction_count: int = 0
    user_approved: bool = False
    weakened: bool = False
    revised: bool = False
    archived: bool = False
    source_outcome_ids: list[str] = field(default_factory=list)
    source_ticket_ids: list[str] = field(default_factory=list)
    last_supported_at: str = ""
    last_contradicted_at: str = ""
    first_event_at: str = ""
    last_event_at: str = ""
    version: int = 1


def strategy_memory_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "strategy_memory"


def policy_event_log_path(agent_home: Path) -> Path:
    return strategy_memory_dir(agent_home) / "policy_events.jsonl"


def policy_store_path(agent_home: Path) -> Path:
    return strategy_memory_dir(agent_home) / "policies.json"


def slug_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_") or "unknown"


def safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def load_ticket_index(agent_home: Path, base_date: str) -> dict[str, dict[str, Any]]:
    path = agent_home / "db" / "action_tickets" / f"{base_date}.json"
    payload = load_json_if_exists(path)
    return {
        str(item.get("ticket_id", "") or ""): item
        for item in payload.get("tickets", []) or []
        if isinstance(item, dict) and item.get("ticket_id")
    }


def policy_scope(ticket: dict[str, Any], outcome: dict[str, Any]) -> str:
    bucket = str(ticket.get("portfolio_bucket", "") or "").strip()
    if bucket:
        return f"portfolio:{slug_text(bucket)}"
    role = str(ticket.get("role", "") or "").strip()
    if role:
        return f"portfolio_role:{slug_text(role)}"
    fund_code = str(outcome.get("fund_code", "") or ticket.get("fund_code", "") or "").strip()
    return f"fund:{slug_text(fund_code)}"


def policy_statement(scope: str, action_verb: str) -> str:
    return (
        f"When reviewing {action_verb} tickets in {scope}, use prior outcome follow-through "
        "as a soft confidence note only; never as a veto or forced trade."
    )


def when_to_apply(scope: str, action_verb: str, ticket: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": scope,
        "portfolio_bucket": str(ticket.get("portfolio_bucket", "") or ""),
        "role": str(ticket.get("role", "") or ""),
        "fund_code": str(outcome.get("fund_code", "") or ticket.get("fund_code", "") or ""),
        "action_verb": action_verb,
        "conditions": [
            {
                "field": "similar_action_ticket_pattern",
                "operator": "matches",
                "value": action_verb,
            }
        ],
    }


def event_type_for_outcome(outcome: dict[str, Any]) -> str:
    if str(outcome.get("scoring_status", "") or "") != "scored":
        return ""
    decision_context = outcome.get("decision_context", {}) if isinstance(outcome.get("decision_context"), dict) else {}
    exposure_context = str(decision_context.get("exposure_context", "") or "")
    if decision_context.get("learning_eligible") is not True:
        return ""
    if str(outcome.get("action_verb", "") or "") == "hold" and exposure_context not in {"hold_existing_position", "blocked_add_or_cash_hold"}:
        return ""
    label = str(outcome.get("outcome_label", "") or "")
    if label in SUPPORTIVE_OUTCOME_LABELS:
        return "support"
    if label in CONTRADICTORY_OUTCOME_LABELS:
        return "contradict"
    return ""


def policy_event_from_outcome(
    *,
    outcome: dict[str, Any],
    ticket: dict[str, Any],
    source_artifact: Path,
    agent_home: Path,
    generated_at: str,
) -> AdaptivePolicyEvent | None:
    event_type = event_type_for_outcome(outcome)
    if not event_type:
        return None
    action_verb = str(outcome.get("action_verb", "") or ticket.get("action_verb", "") or "")
    scope = policy_scope(ticket, outcome)
    policy_id = f"policy:{scope}:repeat_{slug_text(action_verb)}:v1"
    outcome_id = str(outcome.get("outcome_id", "") or "")
    event_id = f"policy_event:{outcome_id}:{event_type}"
    label = str(outcome.get("outcome_label", "") or "")
    horizon = str(outcome.get("horizon", "") or "")
    fund_code = str(outcome.get("fund_code", "") or "")
    actual_return = safe_float(outcome.get("actual_return_pct"))
    return AdaptivePolicyEvent(
        event_id=event_id,
        policy_id=policy_id,
        schema_version=EVENT_SCHEMA_VERSION,
        event_type=event_type,
        event_time=generated_at,
        scope=scope,
        statement=policy_statement(scope, action_verb),
        when_to_apply=when_to_apply(scope, action_verb, ticket, outcome),
        effect_type="note",
        effect_value="review_outcome_history_before_repeating_action",
        source_outcome_id=outcome_id,
        source_ticket_id=str(outcome.get("ticket_id", "") or ticket.get("ticket_id", "") or ""),
        source_artifact=relative_posix(source_artifact, agent_home),
        outcome_label=label,
        diagnostic_label=str(outcome.get("diagnostic_label", "") or ""),
        delta={event_type: 1},
        notes=f"{label} outcome for {fund_code} over {horizon}; actual_return_pct={actual_return}.",
        write_scope="learning_only",
        non_executable=True,
        audit={"created_by": "scripts/update_adaptive_policies.py"},
    )


def outcome_paths(agent_home: Path, base_date: str, horizons: list[str] | None) -> list[Path]:
    if horizons:
        return [outcome_event_path(agent_home, base_date, horizon) for horizon in horizons]
    return sorted((agent_home / "db" / "outcome_events").glob(f"{base_date}__*.json"))


def derive_policy_events(agent_home: Path, base_date: str, horizons: list[str] | None, generated_at: str) -> list[AdaptivePolicyEvent]:
    paths = outcome_paths(agent_home, base_date, horizons)
    existing_paths = [path for path in paths if path.exists()]
    if not existing_paths:
        raise FileNotFoundError(f"no outcome event artifacts found for {base_date}")

    ticket_cache: dict[str, dict[str, dict[str, Any]]] = {}
    events: list[AdaptivePolicyEvent] = []
    for path in existing_paths:
        artifact = OutcomeEventArtifact.from_dict(load_json_if_exists(path))
        ticket_cache.setdefault(artifact.base_date, load_ticket_index(agent_home, artifact.base_date))
        tickets = ticket_cache[artifact.base_date]
        for outcome_event in artifact.events:
            outcome = outcome_event.to_dict()
            ticket = tickets.get(outcome_event.ticket_id, {})
            policy_event = policy_event_from_outcome(
                outcome=outcome,
                ticket=ticket,
                source_artifact=path,
                agent_home=agent_home,
                generated_at=generated_at,
            )
            if policy_event:
                events.append(policy_event)
    return events


def existing_event_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("event_id"):
            ids.add(str(payload.get("event_id")))
    return ids


def append_policy_events(agent_home: Path, events: list[AdaptivePolicyEvent]) -> tuple[Path, int]:
    path = policy_event_log_path(agent_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = existing_event_ids(path)
    appended = 0
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for event in events:
            if event.event_id in seen:
                continue
            payload = event.to_dict()
            assert_refactor_write_allowed(path, payload, agent_home)
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            seen.add(event.event_id)
            appended += 1
    return path, appended


def read_policy_events(path: Path) -> tuple[list[AdaptivePolicyEvent], int]:
    if not path.exists():
        return [], 0
    events: list[AdaptivePolicyEvent] = []
    invalid_count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("policy event line must be a JSON object")
            events.append(AdaptivePolicyEvent.from_dict(payload))
        except Exception:
            invalid_count += 1
    return events, invalid_count


def append_unique(target: list[str], value: str) -> None:
    if value and value not in target:
        target.append(value)


def apply_event(accumulators: dict[str, PolicyAccumulator], event: AdaptivePolicyEvent) -> None:
    acc = accumulators.get(event.policy_id)
    if acc is None:
        acc = PolicyAccumulator(
            policy_id=event.policy_id,
            scope=event.scope,
            statement=event.statement,
            when_to_apply=dict(event.when_to_apply),
            effect_type=event.effect_type,
            effect_value=event.effect_value,
            first_event_at=event.event_time,
        )
        accumulators[event.policy_id] = acc

    acc.last_event_at = event.event_time
    if event.event_type == "support":
        acc.support_count += 1
        acc.last_supported_at = event.event_time
    elif event.event_type == "contradict":
        acc.contradiction_count += 1
        acc.last_contradicted_at = event.event_time
    elif event.event_type == "user_approve":
        acc.user_approved = True
    elif event.event_type == "weaken":
        acc.weakened = True
    elif event.event_type == "archive":
        acc.archived = True
    elif event.event_type == "revise":
        acc.revised = True
        acc.version += 1
        acc.statement = event.statement
        acc.when_to_apply = dict(event.when_to_apply)
        acc.effect_type = event.effect_type
        acc.effect_value = event.effect_value

    append_unique(acc.source_outcome_ids, event.source_outcome_id)
    append_unique(acc.source_ticket_ids, event.source_ticket_id)


def contradiction_ratio(acc: PolicyAccumulator) -> float:
    total = acc.support_count + acc.contradiction_count
    if total <= 0:
        return 0.0
    return acc.contradiction_count / total


def policy_status(acc: PolicyAccumulator, caps: dict[str, Any]) -> str:
    total = acc.support_count + acc.contradiction_count
    ratio = contradiction_ratio(acc)
    if acc.archived:
        return "archived"
    if (
        total >= int(caps["min_total_count_for_contradiction_archive"])
        and acc.support_count > 0
        and ratio >= float(caps["archive_if_contradiction_ratio_above"])
    ):
        return "archived"
    if acc.weakened or (acc.contradiction_count > 0 and acc.contradiction_count >= acc.support_count):
        return "weakened"
    if acc.revised:
        return "revised"
    active_supported = (
        acc.support_count >= int(caps["min_support_count_for_active"])
        and ratio <= float(caps["max_contradiction_ratio_for_active"])
    )
    if acc.user_approved or active_supported:
        return "active"
    if acc.support_count >= int(caps["min_support_count_for_candidate"]):
        return "candidate"
    return "draft"


def policy_confidence(acc: PolicyAccumulator) -> float:
    value = 0.2 + acc.support_count * 0.08 - acc.contradiction_count * 0.12
    if acc.user_approved:
        value += 0.1
    return round(min(0.95, max(0.0, value)), 4)


def policy_from_accumulator(acc: PolicyAccumulator, caps: dict[str, Any], generated_at: str) -> AdaptivePolicy:
    return AdaptivePolicy(
        policy_id=acc.policy_id,
        schema_version=POLICY_SCHEMA_VERSION,
        scope=acc.scope,
        status=policy_status(acc, caps),
        statement=acc.statement,
        when_to_apply=acc.when_to_apply,
        effect_type=acc.effect_type,
        effect_value=acc.effect_value,
        effect_bounds={},
        allowed_effects=sorted(ALLOWED_POLICY_EFFECTS),
        forbidden_effects=sorted(FORBIDDEN_POLICY_EFFECTS),
        support_count=acc.support_count,
        contradiction_count=acc.contradiction_count,
        confidence=policy_confidence(acc),
        source_outcome_ids=list(acc.source_outcome_ids),
        source_ticket_ids=list(acc.source_ticket_ids),
        last_supported_at=acc.last_supported_at,
        last_contradicted_at=acc.last_contradicted_at,
        last_reviewed_at=generated_at,
        valid_from=(acc.first_event_at or generated_at)[:10],
        valid_until="",
        version=acc.version,
        promotion_rule={
            "min_support_count_for_candidate": caps["min_support_count_for_candidate"],
            "min_support_count_for_active": caps["min_support_count_for_active"],
            "max_contradiction_ratio_for_active": caps["max_contradiction_ratio_for_active"],
            "user_approval_can_activate": True,
        },
        audit={"created_by": "scripts/update_adaptive_policies.py"},
    )


def status_rank(policy: AdaptivePolicy) -> int:
    ranks = {"active": 0, "candidate": 1, "draft": 2, "revised": 3, "weakened": 4, "archived": 5}
    return ranks.get(policy.status, 9)


def enforce_scope_caps(policies: list[AdaptivePolicy], caps: dict[str, Any], generated_at: str) -> int:
    cap_adjusted = 0
    by_scope: dict[str, list[AdaptivePolicy]] = {}
    for policy in policies:
        by_scope.setdefault(policy.scope, []).append(policy)

    for scope_policies in by_scope.values():
        active = sorted(
            [policy for policy in scope_policies if policy.status == "active"],
            key=lambda item: (item.confidence, item.support_count, item.policy_id),
            reverse=True,
        )
        for policy in active[int(caps["max_active_policies_per_scope"]) :]:
            policy.status = "candidate"
            policy.audit["cap_adjustment"] = "downgraded_by_active_scope_cap"
            cap_adjusted += 1

        current = sorted(
            [policy for policy in scope_policies if policy.status != "archived"],
            key=lambda item: (status_rank(item), -item.confidence, item.policy_id),
        )
        for policy in current[int(caps["max_candidate_policies_per_scope"]) :]:
            policy.status = "archived"
            policy.valid_until = generated_at[:10]
            policy.audit["cap_adjustment"] = "archived_by_scope_policy_cap"
            cap_adjusted += 1
    return cap_adjusted


def materialize_policy_store(agent_home: Path, *, generated_at: str | None = None, caps: dict[str, Any] | None = None) -> AdaptivePolicyStore:
    generated_at = generated_at or timestamp_now()
    resolved_caps = dict(DEFAULT_CAPS)
    if caps:
        resolved_caps.update(caps)

    events, invalid_count = read_policy_events(policy_event_log_path(agent_home))
    accumulators: dict[str, PolicyAccumulator] = {}
    for event in events:
        apply_event(accumulators, event)

    policies = [policy_from_accumulator(acc, resolved_caps, generated_at) for acc in accumulators.values()]
    cap_adjusted_count = enforce_scope_caps(policies, resolved_caps, generated_at)
    policies.sort(key=lambda item: (item.scope, status_rank(item), item.policy_id))
    status_counts = {status: len([policy for policy in policies if policy.status == status]) for status in sorted({policy.status for policy in policies})}

    return AdaptivePolicyStore(
        schema_version=STORE_SCHEMA_VERSION,
        generated_at=generated_at,
        materialized_from="db/strategy_memory/policy_events.jsonl",
        write_scope="learning_only",
        non_executable=True,
        hard_block_allowed=False,
        policies=policies,
        recent_events=[event.to_dict() for event in events[-20:]],
        caps=resolved_caps,
        summary={
            "valid_event_count": len(events),
            "invalid_event_count": invalid_count,
            "policy_count": len(policies),
            "status_counts": status_counts,
            "cap_adjusted_count": cap_adjusted_count,
            "hard_block_allowed": False,
            "non_executable_violation_count": 0,
        },
    )


def write_policy_store(agent_home: Path, store: AdaptivePolicyStore) -> Path:
    path = policy_store_path(agent_home)
    payload = store.to_dict()
    assert_refactor_write_allowed(path, payload, agent_home)
    dump_json(path, payload)
    return path


def run_updater(
    agent_home: Path,
    base_date: str | None = None,
    horizons: list[str] | None = None,
    *,
    generated_at: str | None = None,
    materialize_only: bool = False,
) -> tuple[Path, Path, int, AdaptivePolicyStore]:
    generated_at = generated_at or timestamp_now()
    appended = 0
    event_path = policy_event_log_path(agent_home)
    if not materialize_only:
        if not base_date:
            raise ValueError("base_date is required unless materialize_only=true")
        events = derive_policy_events(agent_home, base_date, horizons, generated_at)
        event_path, appended = append_policy_events(agent_home, events)
    store = materialize_policy_store(agent_home, generated_at=generated_at)
    store_path = write_policy_store(agent_home, store)
    return event_path, store_path, appended, store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update non-executable adaptive policy memory from outcome events.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Base report date in YYYY-MM-DD.")
    parser.add_argument("--horizon", action="append", help="Outcome horizon to consume, such as T+1. Repeatable.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp for deterministic tests.")
    parser.add_argument("--materialize-only", action="store_true", help="Only rebuild policies.json from policy_events.jsonl.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    base_date = resolve_date(args.date) if args.date else None
    if not base_date and not args.materialize_only:
        raise SystemExit("--date is required unless --materialize-only is set")
    event_path, store_path, appended, store = run_updater(
        agent_home,
        base_date,
        args.horizon,
        generated_at=args.generated_at or None,
        materialize_only=args.materialize_only,
    )
    print(
        f"appended {appended} policy events to {relative_posix(event_path, agent_home)}; "
        f"materialized {len(store.policies)} policies at {relative_posix(store_path, agent_home)}"
    )


if __name__ == "__main__":
    main()
