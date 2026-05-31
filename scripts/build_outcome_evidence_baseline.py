from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed, relative_posix
from common import dump_json, resolve_agent_home, resolve_date, timestamp_now
from evaluate_action_ticket_outcomes import outcome_event_path, run_builder as run_outcome_builder


SCHEMA_VERSION = "outcome_evidence_baseline.v1"
DEFAULT_HORIZONS = ("T+1", "T+5")
DEFAULT_MIN_DATES = 3
DEFAULT_MIN_HORIZONS = 2
DEFAULT_MIN_SCORED_EVENTS = 30
DEFAULT_MIN_ACTION_TYPES = 2
DEFAULT_REQUIRED_ACTION_TYPES: tuple[str, ...] = ()


def baseline_dir(agent_home: Path, baseline_name: str) -> Path:
    return agent_home / "db" / "refactor_shadow_runs" / "outcome_evidence_baselines" / baseline_name


def baseline_path(agent_home: Path, baseline_name: str) -> Path:
    return baseline_dir(agent_home, baseline_name) / "baseline.json"


def markdown_path(agent_home: Path, baseline_name: str) -> Path:
    return baseline_dir(agent_home, baseline_name) / "baseline.md"


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def count_values(events: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(event.get(key, "") or "") for event in events if event.get(key)).items()))


def collect_outcome_artifact(
    agent_home: Path,
    report_date: str,
    horizon: str,
    *,
    generated_at: str,
    generate: bool = True,
) -> dict[str, Any]:
    path = outcome_event_path(agent_home, report_date, horizon)
    if generate:
        path, _artifact = run_outcome_builder(agent_home, report_date, horizon, generated_at=generated_at)

    payload = load_json_object(path)
    failures: list[str] = []
    if not path.exists():
        failures.append("missing_outcome_artifact")
    if not payload:
        failures.append("invalid_or_empty_outcome_artifact")
    if payload and payload.get("write_scope") != "learning_only":
        failures.append("write_scope")
    if payload and payload.get("non_executable") is not True:
        failures.append("non_executable")
    if payload:
        try:
            assert_refactor_write_allowed(path, payload, agent_home)
        except BoundaryViolation as exc:
            failures.append(f"boundary:{exc}")

    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    events = [event for event in payload.get("events", []) or [] if isinstance(event, dict)]
    status_counts = count_values(events, "scoring_status")
    action_type_counts = count_values(events, "action_verb")
    outcome_label_counts = count_values(events, "outcome_label")
    scored_count = status_counts.get("scored", 0)
    pending_count = status_counts.get("pending", 0)
    blocked_count = status_counts.get("blocked", 0)
    ready = not failures and scored_count > 0
    return {
        "report_date": report_date,
        "horizon": horizon,
        "status": "ready" if ready else "failed",
        "path": relative_posix(path, agent_home),
        "exists": path.exists(),
        "content_sha256": content_sha256(path) if path.exists() else "",
        "summary": {
            "event_count": len(events),
            "scored_count": scored_count,
            "pending_count": pending_count,
            "blocked_count": blocked_count,
            "learning_eligible_count": int(summary.get("learning_eligible_count", 0) or 0),
            "actual_evaluation_dates": list(summary.get("actual_evaluation_dates", []) or []),
            "official_output_unchanged": summary.get("official_output_unchanged") is True,
            "non_executable_violation_count": int(summary.get("non_executable_violation_count", 0) or 0),
        },
        "status_counts": status_counts,
        "action_type_counts": action_type_counts,
        "outcome_label_counts": outcome_label_counts,
        "failures": failures,
    }


def summarize(entries: list[dict[str, Any]], dates: list[str], horizons: list[str], thresholds: dict[str, Any]) -> dict[str, Any]:
    ready_entries = [entry for entry in entries if entry.get("status") == "ready"]
    action_types = sorted({key for entry in ready_entries for key in (entry.get("action_type_counts", {}) or {})})
    outcome_labels = sorted({key for entry in ready_entries for key in (entry.get("outcome_label_counts", {}) or {})})
    evaluation_dates = sorted(
        {
            item
            for entry in ready_entries
            for item in (entry.get("summary", {}).get("actual_evaluation_dates", []) or [])
            if item
        }
    )
    total_event_count = sum(int(entry.get("summary", {}).get("event_count", 0) or 0) for entry in ready_entries)
    total_scored_count = sum(int(entry.get("summary", {}).get("scored_count", 0) or 0) for entry in ready_entries)
    total_pending_count = sum(int(entry.get("summary", {}).get("pending_count", 0) or 0) for entry in ready_entries)
    total_blocked_count = sum(int(entry.get("summary", {}).get("blocked_count", 0) or 0) for entry in ready_entries)
    all_ready = len(ready_entries) == len(entries) and bool(entries)
    non_executable_violation_count = sum(
        int(entry.get("summary", {}).get("non_executable_violation_count", 0) or 0) for entry in entries
    )
    required_action_types = sorted({str(item).strip() for item in thresholds.get("required_action_types", []) if str(item).strip()})
    missing_required_action_types = sorted(set(required_action_types) - set(action_types))
    passed = (
        all_ready
        and len(set(dates)) >= thresholds["min_dates"]
        and len(set(horizons)) >= thresholds["min_horizons"]
        and total_scored_count >= thresholds["min_scored_events"]
        and len(action_types) >= thresholds["min_action_types"]
        and not missing_required_action_types
        and non_executable_violation_count == 0
    )
    return {
        "date_count": len(set(dates)),
        "horizon_count": len(set(horizons)),
        "outcome_artifact_count": len(entries),
        "ready_outcome_artifact_count": len(ready_entries),
        "failed_outcome_artifact_count": len(entries) - len(ready_entries),
        "total_event_count": total_event_count,
        "total_scored_count": total_scored_count,
        "total_pending_count": total_pending_count,
        "total_blocked_count": total_blocked_count,
        "distinct_action_types": action_types,
        "required_action_types": required_action_types,
        "missing_required_action_types": missing_required_action_types,
        "distinct_outcome_labels": outcome_labels,
        "actual_evaluation_dates": evaluation_dates,
        "non_executable_violation_count": non_executable_violation_count,
        "official_output_unchanged": all(entry.get("summary", {}).get("official_output_unchanged") is True for entry in ready_entries),
        "all_outcome_artifacts_ready": all_ready,
        "multi_date_outcome_evidence_passed": passed,
    }


def build_baseline(
    agent_home: Path,
    dates: list[str],
    horizons: list[str],
    baseline_name: str,
    generated_at: str,
    *,
    generate: bool = True,
    min_dates: int = DEFAULT_MIN_DATES,
    min_horizons: int = DEFAULT_MIN_HORIZONS,
    min_scored_events: int = DEFAULT_MIN_SCORED_EVENTS,
    min_action_types: int = DEFAULT_MIN_ACTION_TYPES,
    required_action_types: list[str] | tuple[str, ...] = DEFAULT_REQUIRED_ACTION_TYPES,
) -> dict[str, Any]:
    thresholds = {
        "min_dates": min_dates,
        "min_horizons": min_horizons,
        "min_scored_events": min_scored_events,
        "min_action_types": min_action_types,
        "required_action_types": sorted({str(item).strip() for item in required_action_types if str(item).strip()}),
    }
    entries: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for report_date in dates:
        for horizon in horizons:
            try:
                entry = collect_outcome_artifact(
                    agent_home,
                    report_date,
                    horizon,
                    generated_at=generated_at,
                    generate=generate,
                )
            except Exception as exc:
                entry = {
                    "report_date": report_date,
                    "horizon": horizon,
                    "status": "failed",
                    "path": relative_posix(outcome_event_path(agent_home, report_date, horizon), agent_home),
                    "summary": {},
                    "status_counts": {},
                    "action_type_counts": {},
                    "outcome_label_counts": {},
                    "failures": [str(exc)],
                }
            entries.append(entry)
            if entry.get("status") != "ready":
                failures.append({"report_date": report_date, "horizon": horizon, "failures": list(entry.get("failures", []) or [])})

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"outcome_evidence_baseline:{baseline_name}",
        "artifact_kind": "outcome_evidence_baseline",
        "baseline_name": baseline_name,
        "generated_at": generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "official_path_mutation_allowed": False,
        "thresholds": thresholds,
        "dates": dates,
        "horizons": horizons,
        "outcome_artifacts": entries,
        "summary": summarize(entries, dates, horizons, thresholds),
        "failures": failures,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        f"# Outcome Evidence Baseline - {payload['baseline_name']}",
        "",
        f"- generated_at: {payload['generated_at']}",
        "- write_scope: shadow_only",
        "- non_executable: true",
        "- official_path_mutation_allowed: false",
        f"- date_count: {summary['date_count']}",
        f"- horizon_count: {summary['horizon_count']}",
        f"- total_scored_count: {summary['total_scored_count']}",
        f"- distinct_action_types: {', '.join(summary['distinct_action_types'])}",
        f"- required_action_types: {', '.join(summary['required_action_types']) or 'none'}",
        f"- missing_required_action_types: {', '.join(summary['missing_required_action_types']) or 'none'}",
        f"- multi_date_outcome_evidence_passed: {str(summary['multi_date_outcome_evidence_passed']).lower()}",
        "",
        "| Date | Horizon | Status | Events | Scored | Pending | Blocked | Actions | Labels |",
        "|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for entry in payload.get("outcome_artifacts", []) or []:
        entry_summary = entry.get("summary", {}) if isinstance(entry.get("summary"), dict) else {}
        lines.append(
            "| {date} | {horizon} | {status} | {events} | {scored} | {pending} | {blocked} | {actions} | {labels} |".format(
                date=entry.get("report_date", ""),
                horizon=entry.get("horizon", ""),
                status=entry.get("status", ""),
                events=entry_summary.get("event_count", 0),
                scored=entry_summary.get("scored_count", 0),
                pending=entry_summary.get("pending_count", 0),
                blocked=entry_summary.get("blocked_count", 0),
                actions=", ".join((entry.get("action_type_counts", {}) or {}).keys()),
                labels=", ".join((entry.get("outcome_label_counts", {}) or {}).keys()),
            )
        )
    if payload.get("failures"):
        lines.extend(["", "## Failures"])
        for failure in payload["failures"]:
            lines.append(f"- {failure.get('report_date')} {failure.get('horizon')}: {', '.join(failure.get('failures', []) or [])}")
    return "\n".join(lines) + "\n"


def write_baseline(agent_home: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    json_path = baseline_path(agent_home, payload["baseline_name"])
    md_path = markdown_path(agent_home, payload["baseline_name"])
    assert_refactor_write_allowed(json_path, payload, agent_home)
    dump_json(json_path, payload)
    markdown_payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"{payload['artifact_id']}:markdown",
        "artifact_kind": "outcome_evidence_baseline_markdown",
        "write_scope": "shadow_only",
        "non_executable": True,
    }
    assert_refactor_write_allowed(md_path, markdown_payload, agent_home)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(payload), encoding="utf-8", newline="\n")
    return json_path, md_path


def run_builder(
    agent_home: Path,
    dates: list[str],
    horizons: list[str],
    baseline_name: str,
    *,
    generated_at: str | None = None,
    generate: bool = True,
    min_dates: int = DEFAULT_MIN_DATES,
    min_horizons: int = DEFAULT_MIN_HORIZONS,
    min_scored_events: int = DEFAULT_MIN_SCORED_EVENTS,
    min_action_types: int = DEFAULT_MIN_ACTION_TYPES,
    required_action_types: list[str] | tuple[str, ...] = DEFAULT_REQUIRED_ACTION_TYPES,
) -> tuple[Path, Path, dict[str, Any]]:
    generated_at = generated_at or timestamp_now()
    payload = build_baseline(
        agent_home,
        dates,
        horizons,
        baseline_name,
        generated_at,
        generate=generate,
        min_dates=min_dates,
        min_horizons=min_horizons,
        min_scored_events=min_scored_events,
        min_action_types=min_action_types,
        required_action_types=required_action_types,
    )
    json_path, md_path = write_baseline(agent_home, payload)
    return json_path, md_path, payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a shadow-only multi-date outcome evidence baseline.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", action="append", required=True, help="Report date to include. Repeatable.")
    parser.add_argument("--horizon", action="append", help="Outcome horizon to include. Repeatable. Defaults to T+1 and T+5.")
    parser.add_argument("--baseline-name", default="phase8_outcome_multidate", help="Stable baseline name.")
    parser.add_argument("--required-action-type", action="append", help="Action type that must be covered by ready outcome artifacts. Repeatable.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp.")
    parser.add_argument("--format", choices=["path", "json"], default="path")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    dates = [resolve_date(item) for item in args.date]
    horizons = list(args.horizon or DEFAULT_HORIZONS)
    json_path, md_path, payload = run_builder(
        agent_home,
        dates,
        horizons,
        args.baseline_name,
        generated_at=args.generated_at or None,
        required_action_types=list(args.required_action_type or []),
    )
    if args.format == "json":
        print(
            json.dumps(
                {
                    "path": relative_posix(json_path, agent_home),
                    "markdown_path": relative_posix(md_path, agent_home),
                    "summary": payload["summary"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"{relative_posix(json_path, agent_home)}\n{relative_posix(md_path, agent_home)}")


if __name__ == "__main__":
    main()
