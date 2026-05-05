from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from common import (
    dump_json,
    learning_report_path,
    load_json,
    load_review_memory,
    nightly_review_report_path,
    review_memory_cycle_path,
    review_memory_ledger_path,
    review_memory_path,
    timestamp_now,
)


RULE_TEMPLATES: dict[str, dict[str, Any]] = {
    "signal_failure": {
        "rule_key": "require_signal_confirmation_before_add",
        "title": "Require Signal Confirmation Before Add",
        "text": "Do not add tactical positions unless signal confirmation is aligned across proxy, estimate, and the immediate thesis path.",
        "category": "entry_validation",
        "applies_to": ["tactical_entries", "signal_validation"],
        "opposites": ["signal_confirmed", "timing_resilience"],
    },
    "signal_confirmed": {
        "rule_key": "reward_aligned_entry_signals",
        "title": "Reward Aligned Entry Signals",
        "text": "Aligned positive entry signals can be trusted more when proxy, estimate, and thesis direction confirm each other.",
        "category": "entry_confirmation",
        "applies_to": ["tactical_entries", "signal_confirmation"],
        "opposites": ["signal_failure"],
    },
    "timing_drag": {
        "rule_key": "avoid_unconfirmed_bottom_fishing",
        "title": "Avoid Unconfirmed Bottom Fishing",
        "text": "Avoid averaging into weakness when same-day confirmation is weak and the move is driven mainly by hope instead of synchronized evidence.",
        "category": "entry_timing",
        "applies_to": ["tactical_entries", "timing_control"],
        "opposites": ["timing_resilience"],
    },
    "timing_resilience": {
        "rule_key": "allow_staged_entry_under_medium_term_conviction",
        "title": "Allow Staged Entries Under Medium-Term Conviction",
        "text": "Staged entries can still work when medium-term conviction is strong even if same-day micro timing is noisy.",
        "category": "entry_timing",
        "applies_to": ["staged_entries", "medium_term_conviction"],
        "opposites": ["timing_drag"],
    },
    "good_risk_reduction": {
        "rule_key": "respect_confirmed_weakness_for_de_risk",
        "title": "Respect Confirmed Weakness For De-Risk",
        "text": "Reduce risk when weakness is confirmed and the position no longer deserves full exposure.",
        "category": "de_risking",
        "applies_to": ["risk_reduction", "confirmed_weakness"],
        "opposites": ["premature_de_risk"],
    },
    "premature_de_risk": {
        "rule_key": "do_not_trim_strength_too_early",
        "title": "Do Not Trim Strength Too Early",
        "text": "Do not de-risk too early when the position remains strong and weakness is not yet confirmed.",
        "category": "de_risking",
        "applies_to": ["trend_holding", "de_risk_timing"],
        "opposites": ["good_risk_reduction"],
    },
    "watchful_hold": {
        "rule_key": "hold_is_valid_when_move_amplitude_is_small",
        "title": "Hold Is Valid When Move Amplitude Is Small",
        "text": "Hold decisions are valid when expected move amplitude is small and the opportunity cost of action remains low.",
        "category": "hold_discipline",
        "applies_to": ["hold", "low_amplitude"],
        "opposites": ["hold_missed_move"],
    },
    "hold_missed_move": {
        "rule_key": "hold_requires_clear_wait_condition",
        "title": "Hold Requires A Clear Wait Condition",
        "text": "Hold decisions need an explicit wait condition; otherwise the system risks missing actionable moves.",
        "category": "hold_discipline",
        "applies_to": ["hold", "wait_condition"],
        "opposites": ["watchful_hold"],
    },
}


def _now() -> str:
    return timestamp_now()


def _stable_rule_id(rule_key: str) -> str:
    return f"rule:{rule_key}"


def new_memory_ledger() -> dict[str, Any]:
    return {
        "updated_at": "",
        "rules": [],
        "events": [],
        "cycle_history": [],
        "applied_replay_experiments": [],
        "summary": {
            "candidate": 0,
            "strategic": 0,
            "permanent": 0,
            "core_permanent": 0,
            "archived": 0,
        },
    }


def load_memory_ledger(agent_home: Path) -> dict[str, Any]:
    path = review_memory_ledger_path(agent_home)
    if not path.exists():
        return new_memory_ledger()
    payload = load_json(path)
    if not isinstance(payload, dict):
        return new_memory_ledger()
    payload.setdefault("rules", [])
    payload.setdefault("events", [])
    payload.setdefault("cycle_history", [])
    payload.setdefault("applied_replay_experiments", [])
    payload.setdefault("summary", {})
    return payload


def _rule_index(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("rule_id", "") or ""): item for item in ledger.get("rules", []) if item.get("rule_id")}


def _new_rule_record(template: dict[str, Any], now: str) -> dict[str, Any]:
    return {
        "rule_id": _stable_rule_id(template["rule_key"]),
        "rule_key": template["rule_key"],
        "title": template["title"],
        "text": template["text"],
        "category": template["category"],
        "applies_to": list(template.get("applies_to", [])),
        "stage": "candidate",
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "last_supported_at": "",
        "last_contradicted_at": "",
        "review_support_count": 0,
        "review_contradiction_count": 0,
        "replay_support_count": 0,
        "replay_contradiction_count": 0,
        "user_confirmation_count": 0,
        "support_score": 0.0,
        "contradiction_score": 0.0,
        "confidence": 0.55,
        "evidence_examples": [],
        "recent_batches": [],
        "promotion_reason": "",
        "demotion_reason": "",
    }


def _record_example(record: dict[str, Any], example: str, batch_ref: str, limit: int = 12) -> None:
    if example:
        examples = list(record.get("evidence_examples", []) or [])
        if example not in examples:
            examples.append(example)
        record["evidence_examples"] = examples[-limit:]
    batches = list(record.get("recent_batches", []) or [])
    if batch_ref and batch_ref not in batches:
        batches.append(batch_ref)
    record["recent_batches"] = batches[-limit:]


def _support_example(template: dict[str, Any], label: str, batch: dict[str, Any]) -> str:
    source = str(batch.get("source", "advice") or "advice")
    horizon = int(batch.get("horizon", 0) or 0)
    base_date = str(batch.get("base_date", "") or "")
    return f"{source}:{'T0' if horizon == 0 else f'T+{horizon}'}:{base_date}:{label}"


def _apply_observation(
    ledger: dict[str, Any],
    *,
    label: str,
    count: int,
    batch: dict[str, Any],
    as_support: bool,
    source_kind: str = "review",
) -> None:
    template = RULE_TEMPLATES.get(label)
    if not template or count <= 0:
        return
    now = _now()
    index = _rule_index(ledger)
    rule_id = _stable_rule_id(template["rule_key"])
    record = index.get(rule_id)
    if record is None:
        record = _new_rule_record(template, now)
        ledger.setdefault("rules", []).append(record)
        index[rule_id] = record
    record["updated_at"] = now
    batch_ref = f"{batch.get('source', 'advice')}:{batch.get('base_date', '')}:T{batch.get('horizon', 0)}"
    _record_example(record, _support_example(template, label, batch), batch_ref)

    if source_kind == "review":
        if as_support:
            record["review_support_count"] = int(record.get("review_support_count", 0) or 0) + int(count)
            record["last_supported_at"] = str(batch.get("review_date", "") or "")
        else:
            record["review_contradiction_count"] = int(record.get("review_contradiction_count", 0) or 0) + int(count)
            record["last_contradicted_at"] = str(batch.get("review_date", "") or "")
    elif source_kind == "replay":
        if as_support:
            record["replay_support_count"] = int(record.get("replay_support_count", 0) or 0) + int(count)
            record["last_supported_at"] = str(batch.get("review_date", "") or batch.get("generated_at", "") or "")
        else:
            record["replay_contradiction_count"] = int(record.get("replay_contradiction_count", 0) or 0) + int(count)
            record["last_contradicted_at"] = str(batch.get("review_date", "") or batch.get("generated_at", "") or "")


def _promote_stage(record: dict[str, Any], new_stage: str, reason: str, events: list[dict], review_date: str) -> None:
    old_stage = str(record.get("stage", "candidate") or "candidate")
    if old_stage == new_stage:
        return
    record["stage"] = new_stage
    if new_stage in {"strategic", "permanent", "core_permanent"}:
        record["promotion_reason"] = reason
    else:
        record["demotion_reason"] = reason
    events.append(
        {
            "event_type": "stage_change",
            "rule_id": record.get("rule_id", ""),
            "from_stage": old_stage,
            "to_stage": new_stage,
            "review_date": review_date,
            "reason": reason,
            "generated_at": _now(),
        }
    )


def _resolve_stage(record: dict[str, Any]) -> tuple[str, float, float]:
    review_support = float(record.get("review_support_count", 0) or 0)
    review_contra = float(record.get("review_contradiction_count", 0) or 0)
    replay_support = float(record.get("replay_support_count", 0) or 0)
    replay_contra = float(record.get("replay_contradiction_count", 0) or 0)
    user_confirm = float(record.get("user_confirmation_count", 0) or 0)
    support_score = review_support + replay_support * 2.0 + user_confirm * 3.0
    contradiction_score = review_contra + replay_contra * 2.0
    return (
        (
            "archived"
            if support_score <= 0 and contradiction_score > 0
            else "core_permanent"
            if support_score >= 8 and contradiction_score <= 1
            else "permanent"
            if support_score >= 5 and (support_score - contradiction_score) >= 4
            else "strategic"
            if support_score >= 2 and (support_score - contradiction_score) >= 1
            else "candidate"
        ),
        support_score,
        contradiction_score,
    )


def _apply_stage_transitions(ledger: dict[str, Any], review_date: str) -> list[dict]:
    events: list[dict] = []
    for record in ledger.get("rules", []) or []:
        next_stage, support_score, contradiction_score = _resolve_stage(record)
        record["support_score"] = round(support_score, 2)
        record["contradiction_score"] = round(contradiction_score, 2)
        record["confidence"] = round(max(0.35, min(0.95, 0.45 + support_score * 0.05 - contradiction_score * 0.04)), 4)
        if next_stage != record.get("stage"):
            reason = (
                f"support_score={support_score:.2f}, contradiction_score={contradiction_score:.2f}"
                if next_stage in {"strategic", "permanent", "core_permanent"}
                else f"demoted by contradiction score {contradiction_score:.2f}"
            )
            _promote_stage(record, next_stage, reason, events, review_date)
        record["status"] = "active" if next_stage != "archived" else "archived"
    return events


def _ledger_summary(ledger: dict[str, Any]) -> dict[str, int]:
    counts = Counter(str(item.get("stage", "candidate") or "candidate") for item in ledger.get("rules", []) or [])
    return {
        "candidate": int(counts.get("candidate", 0)),
        "strategic": int(counts.get("strategic", 0)),
        "permanent": int(counts.get("permanent", 0)),
        "core_permanent": int(counts.get("core_permanent", 0)),
        "archived": int(counts.get("archived", 0)),
    }


def collect_replay_summaries(agent_home: Path, limit: int = 8) -> list[dict[str, Any]]:
    base = agent_home / "db" / "replay_experiments"
    if not base.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(base.glob("*/summary.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = load_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        items.append(
            {
                "experiment_id": str(payload.get("experiment_id", "") or path.parent.name),
                "mode": str(payload.get("mode", "") or ""),
                "generated_at": str(payload.get("generated_at", "") or ""),
                "start_date": str(payload.get("start_date", "") or ""),
                "end_date": str(payload.get("end_date", "") or ""),
                "changed_days": int((payload.get("aggregate", {}) or {}).get("changed_days", 0) or 0),
                "total_tactical_actions": int((payload.get("aggregate", {}) or {}).get("total_tactical_actions", 0) or 0),
                "total_gross_trade": float((payload.get("aggregate", {}) or {}).get("total_gross_trade", 0.0) or 0.0),
            }
        )
        if len(items) >= limit:
            break
    return items


def _rule_memory_record(rule: dict[str, Any], *, scope: str, promotion_level: str) -> dict[str, Any]:
    return {
        "memory_id": str(rule.get("rule_id", "") or ""),
        "memory_type": "policy",
        "scope": scope,
        "entity_keys": list(rule.get("applies_to", []) or []),
        "text": str(rule.get("text", "") or ""),
        "provenance": {
            "source": "learning_ledger",
            "kind": "policy_rule",
            "rule_key": rule.get("rule_key", ""),
            "title": rule.get("title", ""),
        },
        "base_date": str(rule.get("last_supported_at", "") or rule.get("created_at", "") or "")[:10],
        "expires_on": "",
        "promotion_level": promotion_level,
        "approved_by": "",
        "confidence": float(rule.get("confidence", 0.0) or 0.0),
        "status": "active" if str(rule.get("status", "active") or "active") != "archived" else "inactive",
        "applies_to": ", ".join(rule.get("applies_to", []) or []),
        "reason": str(rule.get("promotion_reason", "") or rule.get("demotion_reason", "") or ""),
        "source": "learning_ledger",
    }


def _dedupe_by_memory_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get("memory_id", "") or "")
        if not key:
            continue
        deduped[key] = item
    return list(deduped.values())


def _dedupe_legacy(items: list[dict[str, Any]], key_builder) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        deduped[key_builder(item)] = item
    return list(deduped.values())


def update_memory_from_ledger(memory: dict[str, Any], ledger: dict[str, Any], cycle_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    updated = dict(memory or {})
    updated.setdefault("lessons", [])
    updated.setdefault("review_history", [])
    updated.setdefault("bias_adjustments", [])
    updated.setdefault("agent_feedback", [])
    updated.setdefault("records", [])
    updated.setdefault("strategic_memory", [])
    updated.setdefault("permanent_memory", [])
    updated.setdefault("core_permanent_memory", [])
    updated.setdefault("user_confirmed_memory", [])

    strategic_rules = [item for item in ledger.get("rules", []) if item.get("stage") == "strategic" and item.get("status") == "active"]
    permanent_rules = [item for item in ledger.get("rules", []) if item.get("stage") == "permanent" and item.get("status") == "active"]
    core_rules = [item for item in ledger.get("rules", []) if item.get("stage") == "core_permanent" and item.get("status") == "active"]

    updated["strategic_memory"] = _dedupe_by_memory_id(
        list(updated.get("strategic_memory", []) or [])
        + [_rule_memory_record(rule, scope="strategic_memory", promotion_level="promoted") for rule in strategic_rules]
    )[-160:]
    updated["permanent_memory"] = _dedupe_by_memory_id(
        list(updated.get("permanent_memory", []) or [])
        + [_rule_memory_record(rule, scope="permanent_memory", promotion_level="promoted") for rule in permanent_rules]
    )
    updated["core_permanent_memory"] = _dedupe_by_memory_id(
        list(updated.get("core_permanent_memory", []) or [])
        + [_rule_memory_record(rule, scope="core_permanent_memory", promotion_level="promoted") for rule in core_rules]
    )

    if cycle_summary:
        cycle_date = str(cycle_summary.get("review_date", "") or "")
        headline = str(cycle_summary.get("headline", "") or "")
        top_lessons = list(cycle_summary.get("top_lessons", []) or [])
        for lesson in top_lessons[:8]:
            updated["lessons"].append(
                {
                    "base_date": cycle_date,
                    "horizon": 0,
                    "source": "learning_cycle",
                    "type": lesson.get("category", "policy"),
                    "text": lesson.get("text", ""),
                    "confidence": float(lesson.get("confidence", 0.0) or 0.0),
                    "applies_to": lesson.get("applies_to", ""),
                }
            )
        updated["lessons"] = _dedupe_legacy(
            updated["lessons"],
            lambda item: (item.get("base_date"), item.get("source"), item.get("type"), item.get("text"), item.get("applies_to")),
        )[-160:]
        updated["review_history"].append(
            {
                "base_date": cycle_date,
                "horizon": 0,
                "source": "learning_cycle",
                "summary": cycle_summary.get("summary", {}),
                "diagnostic_summary": cycle_summary.get("diagnostic_summary", {}),
                "memory_summary": headline,
                "watchouts": cycle_summary.get("watchouts", []),
            }
        )
        updated["review_history"] = _dedupe_legacy(
            updated["review_history"],
            lambda item: (item.get("base_date"), item.get("source"), json.dumps(item.get("summary", {}), ensure_ascii=False, sort_keys=True), item.get("memory_summary")),
        )[-120:]
    updated["memory_ledger_summary"] = ledger.get("summary", {})
    updated["updated_at"] = _now()
    return updated


def _batch_rule_events(review_batches: list[dict[str, Any]]) -> tuple[Counter[str], Counter[str], list[str]]:
    support_counter: Counter[str] = Counter()
    contradiction_counter: Counter[str] = Counter()
    watchouts: list[str] = []
    for batch in review_batches:
        diagnostics = batch.get("diagnostic_summary", {}) or {}
        for label, count in diagnostics.items():
            if label not in RULE_TEMPLATES:
                continue
            support_counter[label] += int(count or 0)
            for opposite in RULE_TEMPLATES[label].get("opposites", []):
                contradiction_counter[opposite] += int(count or 0)
        if batch.get("summary", {}).get("adverse", 0) > batch.get("summary", {}).get("supportive", 0):
            watchouts.append(f"{batch.get('source', 'advice')}:{batch.get('base_date', '')}:adverse_bias")
    return support_counter, contradiction_counter, watchouts


def run_learning_sync(agent_home: Path, review_date: str, review_batches: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ledger = load_memory_ledger(agent_home)
    memory = load_review_memory(agent_home)
    support_counter, contradiction_counter, watchouts = _batch_rule_events(review_batches)
    now = _now()

    for batch in review_batches:
        diagnostics = batch.get("diagnostic_summary", {}) or {}
        for label, count in diagnostics.items():
            _apply_observation(ledger, label=label, count=int(count or 0), batch=batch, as_support=True, source_kind="review")
            for opposite in RULE_TEMPLATES.get(label, {}).get("opposites", []):
                _apply_observation(ledger, label=opposite, count=int(count or 0), batch=batch, as_support=False, source_kind="review")

    stage_events = _apply_stage_transitions(ledger, review_date)
    ledger.setdefault("events", []).extend(stage_events)
    ledger["events"] = ledger["events"][-240:]
    ledger["summary"] = _ledger_summary(ledger)
    ledger["updated_at"] = now

    rule_rank = sorted(
        [item for item in ledger.get("rules", []) if item.get("status") == "active"],
        key=lambda item: (float(item.get("support_score", 0.0) or 0.0), float(item.get("confidence", 0.0) or 0.0), item.get("updated_at", "")),
        reverse=True,
    )
    summary = {
        "review_date": review_date,
        "generated_at": now,
        "batch_count": len(review_batches),
        "advice_batch_count": sum(1 for item in review_batches if item.get("source", "advice") == "advice"),
        "execution_batch_count": sum(1 for item in review_batches if item.get("source") == "execution"),
        "summary": {
            "supportive": sum(item.get("summary", {}).get("supportive", 0) for item in review_batches),
            "adverse": sum(item.get("summary", {}).get("adverse", 0) for item in review_batches),
            "missed_upside": sum(item.get("summary", {}).get("missed_upside", 0) for item in review_batches),
            "unknown": sum(item.get("summary", {}).get("unknown", 0) for item in review_batches),
        },
        "diagnostic_summary": dict(sorted(support_counter.items(), key=lambda item: (-item[1], item[0]))),
        "watchouts": watchouts[:8],
        "headline": (
            f"Tonight processed {len(review_batches)} review batches and now tracks "
            f"{ledger['summary']['strategic']} strategic, {ledger['summary']['permanent']} permanent, "
            f"and {ledger['summary']['core_permanent']} core permanent rules."
        ),
        "top_lessons": [
            {
                "rule_id": item.get("rule_id", ""),
                "title": item.get("title", ""),
                "text": item.get("text", ""),
                "category": item.get("category", ""),
                "applies_to": ", ".join(item.get("applies_to", []) or []),
                "stage": item.get("stage", ""),
                "confidence": item.get("confidence", 0.0),
            }
            for item in rule_rank[:8]
        ],
        "promotion_events": stage_events[:24],
        "memory_ledger_summary": ledger["summary"],
        "latest_replay_experiments": collect_replay_summaries(agent_home),
    }

    ledger.setdefault("cycle_history", []).append(
        {
            "review_date": review_date,
            "generated_at": now,
            "batch_count": len(review_batches),
            "headline": summary["headline"],
            "memory_ledger_summary": ledger["summary"],
        }
    )
    ledger["cycle_history"] = ledger["cycle_history"][-120:]

    updated_memory = update_memory_from_ledger(memory, ledger, summary)
    return summary, ledger, updated_memory


def apply_replay_summary_to_ledger(agent_home: Path, replay_summary: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger = load_memory_ledger(agent_home)
    memory = load_review_memory(agent_home)
    replay_id = str(replay_summary.get("experiment_id", "") or "")
    if not replay_id:
        return ledger, memory

    applied = set(ledger.get("applied_replay_experiments", []) or [])
    if replay_id in applied:
        return ledger, memory

    review_date = str(replay_summary.get("generated_at", "") or "")[:10]
    impacts = replay_summary.get("learning_impacts", []) or []
    for impact in impacts:
        label = str(impact.get("rule_label", "") or "")
        batch = {
            "source": "replay",
            "base_date": f"{replay_summary.get('start_date', '')}->{replay_summary.get('end_date', '')}",
            "review_date": review_date,
            "horizon": 0,
            "generated_at": replay_summary.get("generated_at", ""),
        }
        support_count = int(impact.get("support_count", 0) or 0)
        contradiction_count = int(impact.get("contradiction_count", 0) or 0)
        if support_count > 0:
            _apply_observation(ledger, label=label, count=support_count, batch=batch, as_support=True, source_kind="replay")
        if contradiction_count > 0:
            _apply_observation(ledger, label=label, count=contradiction_count, batch=batch, as_support=False, source_kind="replay")

    stage_events = _apply_stage_transitions(ledger, review_date)
    ledger.setdefault("events", []).append(
        {
            "event_type": "replay_ingested",
            "review_date": review_date,
            "experiment_id": replay_id,
            "mode": replay_summary.get("mode", ""),
            "generated_at": _now(),
            "changed_days": (replay_summary.get("aggregate", {}) or {}).get("changed_days", 0),
            "edge_delta_total": (replay_summary.get("aggregate", {}) or {}).get("edge_delta_total", 0.0),
        }
    )
    ledger.setdefault("events", []).extend(stage_events)
    ledger["events"] = ledger["events"][-280:]
    ledger.setdefault("applied_replay_experiments", []).append(replay_id)
    ledger["applied_replay_experiments"] = list(dict.fromkeys(ledger["applied_replay_experiments"]))[-120:]
    ledger["summary"] = _ledger_summary(ledger)
    ledger["updated_at"] = _now()

    updated_memory = update_memory_from_ledger(memory, ledger, None)
    return ledger, updated_memory


def build_learning_report_text(review_date: str, cycle_summary: dict[str, Any], ledger: dict[str, Any], memory: dict[str, Any], review_batches: list[dict[str, Any]]) -> str:
    lines = [
        f"# Learning Center Report - {review_date}",
        "",
        f"- generated_at: {cycle_summary.get('generated_at', '')}",
        f"- review_batches: {cycle_summary.get('batch_count', 0)}",
        f"- advice_batches: {cycle_summary.get('advice_batch_count', 0)}",
        f"- execution_batches: {cycle_summary.get('execution_batch_count', 0)}",
        f"- supportive: {cycle_summary.get('summary', {}).get('supportive', 0)}",
        f"- adverse: {cycle_summary.get('summary', {}).get('adverse', 0)}",
        f"- missed_upside: {cycle_summary.get('summary', {}).get('missed_upside', 0)}",
        "",
        "## Headline",
        cycle_summary.get("headline", "No learning summary available."),
        "",
        "## Promotion Events",
    ]
    events = cycle_summary.get("promotion_events", []) or []
    if events:
        for item in events[:16]:
            lines.append(f"- {item.get('rule_id', '')}: {item.get('from_stage', '')} -> {item.get('to_stage', '')} | {item.get('reason', '')}")
    else:
        lines.append("- No stage changes tonight.")

    lines.extend(["", "## Active Core Permanent Memory"])
    core_rules = [item for item in ledger.get("rules", []) if item.get("stage") == "core_permanent" and item.get("status") == "active"]
    if core_rules:
        for item in core_rules[:12]:
            lines.append(f"- {item.get('title', '')} | support={item.get('support_score', 0)} | confidence={item.get('confidence', 0)}")
            lines.append(f"  {item.get('text', '')}")
    else:
        lines.append("- No core permanent rules yet.")

    lines.extend(["", "## Active Permanent Memory"])
    permanent_rules = [item for item in ledger.get("rules", []) if item.get("stage") == "permanent" and item.get("status") == "active"]
    if permanent_rules:
        for item in permanent_rules[:12]:
            lines.append(f"- {item.get('title', '')} | support={item.get('support_score', 0)} | contradiction={item.get('contradiction_score', 0)}")
            lines.append(f"  {item.get('text', '')}")
    else:
        lines.append("- No permanent rules yet.")

    lines.extend(["", "## Active Strategic Memory"])
    strategic_rules = [item for item in ledger.get("rules", []) if item.get("stage") == "strategic" and item.get("status") == "active"]
    if strategic_rules:
        for item in strategic_rules[:12]:
            lines.append(f"- {item.get('title', '')} | support={item.get('support_score', 0)} | contradiction={item.get('contradiction_score', 0)}")
            lines.append(f"  {item.get('text', '')}")
    else:
        lines.append("- No strategic rules yet.")

    lines.extend(["", "## Replay Lab"])
    replay_items = cycle_summary.get("latest_replay_experiments", []) or []
    if replay_items:
        for item in replay_items[:8]:
            lines.append(
                f"- {item.get('experiment_id', '')} | {item.get('mode', '')} | "
                f"{item.get('start_date', '')} -> {item.get('end_date', '')} | "
                f"changed_days={item.get('changed_days', 0)} | gross={item.get('total_gross_trade', 0.0)}"
            )
    else:
        lines.append("- No replay experiments recorded yet.")

    lines.extend(["", "## Tonight Batches"])
    if review_batches:
        for batch in review_batches:
            lines.append(
                f"- {batch.get('source', 'advice')} | base={batch.get('base_date', '')} | "
                f"horizon=T{batch.get('horizon', 0)} | supportive={batch.get('summary', {}).get('supportive', 0)} | "
                f"adverse={batch.get('summary', {}).get('adverse', 0)} | primary={batch.get('primary_diagnostic', '')}"
            )
    else:
        lines.append("- No due review batches tonight.")

    if memory.get("memory_ledger_summary"):
        lines.extend(["", "## Ledger Summary"])
        for key, value in (memory.get("memory_ledger_summary", {}) or {}).items():
            lines.append(f"- {key}: {value}")

    return "\n".join(lines) + "\n"


def write_learning_artifacts(agent_home: Path, review_date: str, cycle_summary: dict[str, Any], ledger: dict[str, Any], memory: dict[str, Any], review_batches: list[dict[str, Any]]) -> dict[str, Path]:
    cycle_path = dump_json(review_memory_cycle_path(agent_home, review_date), cycle_summary)
    ledger_path = dump_json(review_memory_ledger_path(agent_home), ledger)
    memory_path = dump_json(review_memory_path(agent_home), memory)
    report_text = build_learning_report_text(review_date, cycle_summary, ledger, memory, review_batches)
    learning_path = learning_report_path(agent_home, review_date)
    legacy_path = nightly_review_report_path(agent_home, review_date)
    learning_path.write_text(report_text, encoding="utf-8")
    legacy_path.write_text(report_text, encoding="utf-8")
    return {
        "cycle_path": cycle_path,
        "ledger_path": ledger_path,
        "memory_path": memory_path,
        "learning_report_path": learning_path,
        "legacy_review_report_path": legacy_path,
    }
