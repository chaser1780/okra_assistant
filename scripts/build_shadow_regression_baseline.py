from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from action_debate_graph import run_debate_graph
from artifact_boundary import assert_refactor_write_allowed, relative_posix
from audit_phase8_readiness import build_phase8_audit
from build_action_ticket_shadow import run_builder as run_action_ticket_builder
from build_layered_retrieval_pack import run_builder as run_retrieval_pack_builder
from build_official_advice_compat_preview import run_builder as run_compat_preview_builder
from common import dump_json, resolve_agent_home, resolve_date, timestamp_now
from render_refactor_review import run_renderer


SCHEMA_VERSION = "shadow_regression_baseline.v1"
DEFAULT_REQUIRED_ACTION_TYPES: tuple[str, ...] = ()
REQUIRED_PREVIEW_SUMMARY_FLAGS = (
    "official_shape_compatible",
    "official_behavior_comparable",
    "official_adapter_dry_run_passed",
    "source_hash_verified",
    "official_compatible_advice",
    "official_output_unchanged",
)


def baseline_dir(agent_home: Path, baseline_name: str) -> Path:
    return agent_home / "db" / "refactor_shadow_runs" / "regression_baselines" / baseline_name


def baseline_path(agent_home: Path, baseline_name: str) -> Path:
    return baseline_dir(agent_home, baseline_name) / "baseline.json"


def markdown_path(agent_home: Path, baseline_name: str) -> Path:
    return baseline_dir(agent_home, baseline_name) / "baseline.md"


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_status(agent_home: Path, relative: str) -> dict[str, Any]:
    path = agent_home / relative
    return {
        "path": relative,
        "exists": path.exists(),
        "content_sha256": content_sha256(path) if path.exists() else "",
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def preview_action_types(preview: dict[str, Any]) -> list[str]:
    sections = preview.get("validated_action_sections_preview", {})
    if not isinstance(sections, dict):
        return []
    action_types = set()
    for section_items in sections.values():
        if not isinstance(section_items, list):
            continue
        for item in section_items:
            if not isinstance(item, dict):
                continue
            action = str(item.get("validated_action", "") or "").strip()
            if action:
                action_types.add(action)
    return sorted(action_types)


def preview_gate_failures(preview: dict[str, Any]) -> list[str]:
    summary = preview.get("summary", {}) if isinstance(preview.get("summary"), dict) else {}
    comparison = preview.get("comparison_to_official", {}) if isinstance(preview.get("comparison_to_official"), dict) else {}
    failures: list[str] = []
    for flag in REQUIRED_PREVIEW_SUMMARY_FLAGS:
        if summary.get(flag) is not True:
            failures.append(flag)
    if list(summary.get("official_paths_written", []) or []):
        failures.append("official_paths_written")
    if list(summary.get("missing_required_fields", []) or []):
        failures.append("missing_required_fields")
    if int(comparison.get("mismatched_count", 1) or 0) != 0:
        failures.append("comparison_mismatched_count")
    return failures


def run_date(agent_home: Path, report_date: str, generated_at: str) -> dict[str, Any]:
    run_action_ticket_builder(agent_home, report_date, generated_at=generated_at)
    run_retrieval_pack_builder(agent_home, report_date, generated_at=generated_at)
    run_debate_graph(agent_home, report_date, generated_at=generated_at)
    run_renderer(agent_home, report_date, generated_at=generated_at)
    _preview_path, preview = run_compat_preview_builder(agent_home, report_date, generated_at=generated_at)
    audit = build_phase8_audit(agent_home, report_date, promotion_approved=False, generated_at=generated_at)
    paths = [
        f"db/validated_advice/{report_date}.json",
        f"db/action_tickets/{report_date}.json",
        f"db/retrieval_packs/{report_date}.json",
        f"db/action_debates/{report_date}.json",
        f"db/refactor_reviews/{report_date}.md",
        f"db/refactor_shadow_runs/{report_date}__official_advice_compat_preview/official_advice_compat_preview.json",
    ]
    failures = preview_gate_failures(preview)
    return {
        "report_date": report_date,
        "status": "ready" if not failures else "failed",
        "artifact_statuses": [artifact_status(agent_home, item) for item in paths],
        "action_types": preview_action_types(preview),
        "preview_summary": preview.get("summary", {}),
        "comparison_to_official": preview.get("comparison_to_official", {}),
        "failures": failures,
        "phase8": {
            "promotion_ready": audit.get("promotion_ready"),
            "blocking_gates": list(audit.get("blocking_gates", []) or []),
        },
    }


def build_baseline(
    agent_home: Path,
    dates: list[str],
    baseline_name: str,
    generated_at: str,
    *,
    required_action_types: list[str] | tuple[str, ...] = DEFAULT_REQUIRED_ACTION_TYPES,
) -> dict[str, Any]:
    baseline_root = baseline_dir(agent_home, baseline_name)
    baseline_root.mkdir(parents=True, exist_ok=True)
    date_results = []
    failures = []
    for report_date in dates:
        try:
            result = run_date(agent_home, report_date, generated_at)
            date_results.append(result)
            if result.get("status") != "ready":
                failures.append({"report_date": report_date, "failures": list(result.get("failures", []) or [])})
        except Exception as exc:
            failures.append({"report_date": report_date, "error": str(exc)})
            date_results.append({"report_date": report_date, "status": "failed", "error": str(exc)})
    ready_results = [item for item in date_results if item.get("status") == "ready"]
    distinct_action_types = sorted(
        {
            action
            for item in date_results
            for action in (item.get("action_types", []) or [])
            if action
        }
    )
    required = sorted({str(item).strip() for item in required_action_types if str(item).strip()})
    missing_required = sorted(set(required) - set(distinct_action_types))
    all_dates_ready = len(failures) == 0 and len(ready_results) == len(dates)
    passed = all_dates_ready and not missing_required
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"shadow_regression_baseline:{baseline_name}",
        "artifact_kind": "shadow_regression_baseline",
        "baseline_name": baseline_name,
        "generated_at": generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "official_path_mutation_allowed": False,
        "thresholds": {
            "required_action_types": required,
        },
        "dates": date_results,
        "summary": {
            "date_count": len(dates),
            "ready_date_count": len(ready_results),
            "failed_date_count": len(failures),
            "official_compatible_date_count": len(ready_results),
            "all_dates_ready": all_dates_ready,
            "distinct_action_types": distinct_action_types,
            "required_action_types": required,
            "missing_required_action_types": missing_required,
            "promotion_ready": False,
            "official_output_unchanged": True,
            "named_regression_baseline_passed": passed,
        },
        "failures": failures,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Shadow Regression Baseline - {payload['baseline_name']}",
        "",
        f"- generated_at: {payload['generated_at']}",
        "- write_scope: shadow_only",
        "- non_executable: true",
        "- official_path_mutation_allowed: false",
        f"- date_count: {payload['summary']['date_count']}",
        f"- ready_date_count: {payload['summary']['ready_date_count']}",
        f"- failed_date_count: {payload['summary']['failed_date_count']}",
        f"- official_compatible_date_count: {payload['summary']['official_compatible_date_count']}",
        f"- distinct_action_types: {', '.join(payload['summary']['distinct_action_types'])}",
        f"- required_action_types: {', '.join(payload['summary']['required_action_types']) or 'none'}",
        f"- missing_required_action_types: {', '.join(payload['summary']['missing_required_action_types']) or 'none'}",
        f"- named_regression_baseline_passed: {str(payload['summary']['named_regression_baseline_passed']).lower()}",
        "",
        "| Date | Status | Official Compatible | Validator Dry Run | Mismatches | Actions | Failures | Promotion Ready | Blocking Gates |",
        "|---|---|---|---|---:|---|---|---|---|",
    ]
    for item in payload.get("dates", []) or []:
        summary = item.get("preview_summary", {}) if isinstance(item.get("preview_summary"), dict) else {}
        comparison = item.get("comparison_to_official", {}) if isinstance(item.get("comparison_to_official"), dict) else {}
        phase8 = item.get("phase8", {}) if isinstance(item.get("phase8"), dict) else {}
        lines.append(
            "| {date} | {status} | {compatible} | {dry_run} | {mismatch} | {actions} | {failures} | {promotion} | {gates} |".format(
                date=item.get("report_date", ""),
                status=item.get("status", ""),
                compatible=summary.get("official_compatible_advice", ""),
                dry_run=summary.get("official_adapter_dry_run_passed", ""),
                mismatch=comparison.get("mismatched_count", ""),
                actions=", ".join(item.get("action_types", []) or []),
                failures=", ".join(item.get("failures", []) or []),
                promotion=phase8.get("promotion_ready", ""),
                gates=", ".join(phase8.get("blocking_gates", []) or []),
            )
        )
    if payload.get("failures"):
        lines.extend(["", "## Failures"])
        for failure in payload["failures"]:
            lines.append(f"- {failure.get('report_date')}: {failure.get('error')}")
    return "\n".join(lines) + "\n"


def write_baseline(agent_home: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    json_path = baseline_path(agent_home, payload["baseline_name"])
    md_path = markdown_path(agent_home, payload["baseline_name"])
    assert_refactor_write_allowed(json_path, payload, agent_home)
    dump_json(json_path, payload)
    markdown_payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"{payload['artifact_id']}:markdown",
        "artifact_kind": "shadow_regression_baseline_markdown",
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
    baseline_name: str,
    *,
    generated_at: str | None = None,
    required_action_types: list[str] | tuple[str, ...] = DEFAULT_REQUIRED_ACTION_TYPES,
) -> tuple[Path, Path, dict[str, Any]]:
    generated_at = generated_at or timestamp_now()
    payload = build_baseline(
        agent_home,
        dates,
        baseline_name,
        generated_at,
        required_action_types=required_action_types,
    )
    json_path, md_path = write_baseline(agent_home, payload)
    return json_path, md_path, payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a shadow-only multi-date regression baseline without mutating official paths.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", action="append", required=True, help="Report date to include. Repeatable.")
    parser.add_argument("--baseline-name", default="phase8_shadow_baseline", help="Stable baseline name.")
    parser.add_argument("--required-action-type", action="append", help="Action type that must be covered by the baseline. Repeatable.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp.")
    parser.add_argument("--format", choices=["path", "json"], default="path")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    dates = [resolve_date(item) for item in args.date]
    json_path, md_path, payload = run_builder(
        agent_home,
        dates,
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
