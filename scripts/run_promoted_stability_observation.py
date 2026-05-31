from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from artifact_boundary import assert_refactor_write_allowed, relative_posix
from common import dump_json, load_json, resolve_agent_home, resolve_date, timestamp_now
from run_promoted_advice_chain import PROMOTED_MODE, run_chain


SCHEMA_VERSION = "promoted_stability_observation.v1"
DEFAULT_DATES = ("2026-05-11", "2026-05-14", "2026-05-18", "2026-05-20", "2026-05-21", "2026-05-22")
OBSERVATION_ROOT = Path("db/phase8/promoted_observations")
OFFICIAL_RELATIVE_TEMPLATES = (
    "db/committee_advice/{date}.json",
    "db/committee_decision_bundle/{date}.json",
    "db/llm_advice/{date}.json",
    "db/llm_raw/{date}.json",
    "db/validated_advice/{date}.json",
    "db/decisions/{date}.json",
)
INPUT_RELATIVE_TEMPLATES = (
    "db/daily_scores/{date}.json",
    "db/llm_context/{date}.json",
    "db/portfolio_state/snapshots/{date}.json",
)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_paths(agent_home: Path, relatives: list[str]) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for relative in relatives:
        path = agent_home / relative
        snapshot[relative] = {
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "sha256": _hash_file(path) if path.exists() else "",
        }
    return snapshot


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def _input_preflight(agent_home: Path, report_date: str) -> dict[str, Any]:
    required = [template.format(date=report_date) for template in INPUT_RELATIVE_TEMPLATES]
    statuses = _snapshot_paths(agent_home, required)
    missing = [relative for relative, status in statuses.items() if not status["exists"] or int(status["size_bytes"] or 0) <= 0]
    return {
        "required_inputs": statuses,
        "missing_required_inputs": missing,
        "ready": not missing,
    }


def _inspect_outputs(agent_home: Path, report_date: str) -> dict[str, Any]:
    raw = _load_json_if_exists(agent_home / "db" / "llm_raw" / f"{report_date}.json")
    validated = _load_json_if_exists(agent_home / "db" / "validated_advice" / f"{report_date}.json")
    seed = _load_json_if_exists(agent_home / "db" / "action_seed" / f"{report_date}.json")
    run_status = _load_json_if_exists(agent_home / "db" / "phase8" / "promoted_runs" / f"{report_date}.json")
    decisions = _load_json_if_exists(agent_home / "db" / "decisions" / f"{report_date}.json")
    run_summary = run_status.get("summary", {}) if isinstance(run_status.get("summary"), dict) else {}
    official_paths = run_status.get("official_paths_written", {}) if isinstance(run_status.get("official_paths_written"), dict) else {}
    preview_quality = run_status.get("preview_quality", {}) if isinstance(run_status.get("preview_quality"), dict) else {}
    checks = {
        "run_status_passed": run_summary.get("promoted_run_passed") is True,
        "raw_mode_promoted": raw.get("mode") == PROMOTED_MODE,
        "validated_mode_promoted": validated.get("advice_mode") == PROMOTED_MODE,
        "validated_decision_source_promoted": validated.get("decision_source") == PROMOTED_MODE,
        "seed_native_independent": seed.get("summary", {}).get("native_independent_of_validated_advice") is True,
        "decisions_written": bool(decisions.get("decisions")),
        "official_paths_include_decisions": "decisions" in official_paths,
        "preview_has_no_missing_required_fields": not list(preview_quality.get("missing_required_fields", []) or []),
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "raw_mode": raw.get("mode", ""),
        "validated_mode": validated.get("advice_mode", ""),
        "decision_source": validated.get("decision_source", ""),
        "validated_action_count": run_summary.get("validated_action_count", 0),
        "tactical_action_count": run_summary.get("tactical_action_count", 0),
        "dca_action_count": run_summary.get("dca_action_count", 0),
        "hold_action_count": run_summary.get("hold_action_count", 0),
        "decision_count": len(decisions.get("decisions", []) or []),
        "official_paths_written": official_paths,
        "preview_quality": preview_quality,
    }


def run_observation(
    agent_home: Path,
    dates: list[str],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or timestamp_now()
    date_results: list[dict[str, Any]] = []
    for report_date in dates:
        official_relatives = [template.format(date=report_date) for template in OFFICIAL_RELATIVE_TEMPLATES]
        before = _snapshot_paths(agent_home, official_relatives)
        preflight = _input_preflight(agent_home, report_date)
        error = ""
        status_path = ""
        if preflight["ready"]:
            try:
                path, _status = run_chain(agent_home, report_date, generated_at=generated_at)
                status_path = relative_posix(path, agent_home)
            except Exception as exc:  # pragma: no cover - surfaced in observation payload.
                error = str(exc)
        after = _snapshot_paths(agent_home, official_relatives)
        changed = [
            relative
            for relative in official_relatives
            if before.get(relative, {}).get("sha256") != after.get(relative, {}).get("sha256")
            or before.get(relative, {}).get("exists") != after.get(relative, {}).get("exists")
        ]
        output = _inspect_outputs(agent_home, report_date) if not error else {"passed": False, "checks": {}, "error": error}
        date_results.append(
            {
                "report_date": report_date,
                "preflight": preflight,
                "status_path": status_path,
                "error": error,
                "official_before": before,
                "official_after": after,
                "official_changed_paths": changed,
                "output": output,
                "passed": preflight["ready"] and not error and bool(output.get("passed")),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": "promoted_stability_observation",
        "artifact_kind": "promoted_stability_observation",
        "generated_at": generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "display_only": True,
        "mode": PROMOTED_MODE,
        "official_path_mutation_allowed": True,
        "dates": date_results,
        "summary": {
            "date_count": len(dates),
            "passed_date_count": sum(1 for item in date_results if item["passed"]),
            "failed_date_count": sum(1 for item in date_results if not item["passed"]),
            "all_passed": all(item["passed"] for item in date_results),
            "observation_dates": dates,
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Promoted Stability Observation",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- mode: {payload['mode']}",
        f"- official_path_mutation_allowed: {str(payload['official_path_mutation_allowed']).lower()}",
        f"- all_passed: {str(payload['summary']['all_passed']).lower()}",
        "",
        "| Date | Passed | Raw Mode | Validated Mode | Actions | Decisions | Changed Official Paths | Error |",
        "|---|---:|---|---|---:|---:|---|---|",
    ]
    for item in payload.get("dates", []) or []:
        output = item.get("output", {}) if isinstance(item.get("output"), dict) else {}
        lines.append(
            f"| {item.get('report_date', '')} | {str(item.get('passed')).lower()} | {output.get('raw_mode', '')} | "
            f"{output.get('validated_mode', '')} | {output.get('validated_action_count', 0)} | "
            f"{output.get('decision_count', 0)} | {len(item.get('official_changed_paths', []) or [])} | {item.get('error', '')} |"
        )
    return "\n".join(lines)


def observation_paths(agent_home: Path, label: str) -> tuple[Path, Path]:
    safe_label = label.replace(":", "-").replace("/", "-").replace("\\", "-")
    root = agent_home / OBSERVATION_ROOT
    return root / f"{safe_label}.json", root / f"{safe_label}.md"


def run_builder(
    agent_home: Path,
    dates: list[str],
    *,
    generated_at: str | None = None,
    label: str | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    payload = run_observation(agent_home, dates, generated_at=generated_at)
    label = label or f"{payload['generated_at']}__{dates[0]}__{dates[-1]}"
    json_path, md_path = observation_paths(agent_home, label)
    assert_refactor_write_allowed(json_path, payload, agent_home)
    dump_json(json_path, payload)
    markdown_artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": "promoted_stability_observation:markdown",
        "artifact_kind": "promoted_stability_observation_markdown",
        "write_scope": "shadow_only",
        "non_executable": True,
    }
    assert_refactor_write_allowed(md_path, markdown_artifact, agent_home)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(payload), encoding="utf-8", newline="\n")
    return json_path, md_path, payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-date promoted official advice observation.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", action="append", help="Observation date in YYYY-MM-DD. Repeatable.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp.")
    parser.add_argument("--label", default="", help="Output report label.")
    parser.add_argument("--format", choices=["path", "json", "markdown"], default="path")
    args = parser.parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    dates = [resolve_date(item) for item in args.date] if args.date else list(DEFAULT_DATES)
    json_path, md_path, payload = run_builder(
        agent_home,
        dates,
        generated_at=args.generated_at or None,
        label=args.label or None,
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
    elif args.format == "markdown":
        print(render_markdown(payload))
    else:
        print(f"{relative_posix(json_path, agent_home)}\n{relative_posix(md_path, agent_home)}")


if __name__ == "__main__":
    main()
