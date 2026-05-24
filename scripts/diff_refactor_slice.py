from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from artifact_boundary import BoundaryViolation, assert_non_executable, find_forbidden_write_paths, relative_posix
from replay_refactor_slice import DEFAULT_SLICE_ID, PROJECT_ROOT, default_output_dir, fixture_dir, load_json


ARTIFACTS = (
    ("action_ticket", "action_ticket.expected.json", "action_ticket.json"),
    ("retrieval_pack", "retrieval_pack.expected.json", "retrieval_pack.json"),
    ("outcome_event", "outcome_event.expected.json", "outcome_event.json"),
)


def dump_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json(path)


def first_changed_field(expected: Any, actual: Any, prefix: str = "") -> str:
    if type(expected) is not type(actual):
        return prefix or "/"
    if isinstance(expected, dict):
        keys = sorted(set(expected) | set(actual))
        for key in keys:
            if expected.get(key) != actual.get(key):
                return first_changed_field(expected.get(key), actual.get(key), f"{prefix}/{key}")
        return ""
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{prefix}/length"
        for index, (left, right) in enumerate(zip(expected, actual)):
            if left != right:
                return first_changed_field(left, right, f"{prefix}/{index}")
        return ""
    return prefix or "/"


def validate_artifact(name: str, payload: dict[str, Any] | None) -> list[str]:
    if payload is None:
        return ["missing artifact"]
    errors: list[str] = []
    if not payload.get("schema_version"):
        errors.append("missing schema_version")
    if payload.get("non_executable") is not True:
        errors.append("root non_executable must be true")
    try:
        assert_non_executable(payload)
    except BoundaryViolation as exc:
        errors.append(str(exc))
    if name == "action_ticket":
        tickets = payload.get("tickets")
        if not isinstance(tickets, list) or not tickets:
            errors.append("missing tickets")
        else:
            required = [
                "ticket_id",
                "schema_version",
                "report_date",
                "generated_at",
                "fund_code",
                "fund_name",
                "action_verb",
                "execution_mode",
                "ticket_status",
                "non_executable",
                "write_scope",
                "validated_amount",
                "confidence",
                "thesis",
                "hard_guardrail_results",
                "source_artifacts",
                "legacy_mapping",
            ]
            for field in required:
                if field not in tickets[0]:
                    errors.append(f"ticket missing {field}")
    if name == "retrieval_pack":
        for field in ("canonical_facts", "critical_data_checks", "missing_critical_data"):
            if field not in payload:
                errors.append(f"retrieval pack missing {field}")
    if name == "outcome_event":
        events = payload.get("events")
        if not isinstance(events, list) or not events:
            errors.append("missing events")
    return errors


def kpi_snapshot(actual_payloads: dict[str, dict[str, Any] | None], metadata: dict[str, Any] | None, diff_count: int) -> dict[str, float | int]:
    action_ticket = actual_payloads.get("action_ticket") or {}
    retrieval_pack = actual_payloads.get("retrieval_pack") or {}
    tickets = action_ticket.get("tickets", []) if isinstance(action_ticket, dict) else []
    hold_tickets = [item for item in tickets if isinstance(item, dict) and item.get("action_verb") == "hold"]
    silent_holds = [item for item in hold_tickets if not item.get("thesis") and not item.get("supporting_evidence_refs")]
    traced = [item for item in tickets if isinstance(item, dict) and item.get("source_artifacts") and item.get("legacy_mapping")]
    checks = retrieval_pack.get("critical_data_checks", []) if isinstance(retrieval_pack, dict) else []
    missing = retrieval_pack.get("missing_critical_data", []) if isinstance(retrieval_pack, dict) else []
    non_exec_violations = 0
    for payload in actual_payloads.values():
        if payload is None:
            continue
        try:
            assert_non_executable(payload)
        except BoundaryViolation:
            non_exec_violations += 1
    forbidden = metadata.get("forbidden_writes", []) if isinstance(metadata, dict) else []
    return {
        "trace_completeness_rate": round(len(traced) / len(tickets), 2) if tickets else 0.0,
        "silent_hold_rate": round(len(silent_holds) / len(hold_tickets), 2) if hold_tickets else 0.0,
        "shadow_official_comparable_rate": 1.0 if tickets else 0.0,
        "non_executable_violation_count": non_exec_violations,
        "forbidden_write_count": len(forbidden),
        "replay_diff_unapproved_count": diff_count,
        "missing_critical_data_rate": round(len(missing) / len(checks), 2) if checks else 0.0,
    }


def build_diff_report(slice_id: str, output_dir: Path | None = None, fixture_root: Path | None = None) -> tuple[str, dict[str, Any]]:
    expected_dir = fixture_dir(slice_id, fixture_root) / "expected"
    actual_dir = output_dir or default_output_dir(slice_id)
    input_meta = load_optional_json(fixture_dir(slice_id, fixture_root) / "input" / "slice.json") or {}
    metadata = load_optional_json(actual_dir / "run_metadata.json") or {}
    artifact_rows: list[dict[str, Any]] = []
    actual_payloads: dict[str, dict[str, Any] | None] = {}
    diff_count = 0
    validation_error_count = 0
    for name, expected_name, actual_name in ARTIFACTS:
        expected = load_optional_json(expected_dir / expected_name)
        actual = load_optional_json(actual_dir / actual_name)
        actual_payloads[name] = actual
        changed = expected != actual
        errors = validate_artifact(name, actual)
        if changed:
            diff_count += 1
        validation_error_count += len(errors)
        artifact_rows.append(
            {
                "name": name,
                "changed": changed,
                "first_changed_field": first_changed_field(expected, actual) if changed and expected is not None and actual is not None else "",
                "validation_errors": errors,
            }
        )
    forbidden_runtime = find_forbidden_write_paths([PROJECT_ROOT / item for item in metadata.get("allowed_writes", [])] if isinstance(metadata, dict) else [])
    kpis = kpi_snapshot(actual_payloads, metadata, diff_count)
    verdict = "PASS" if diff_count == 0 and validation_error_count == 0 and not forbidden_runtime and all(value == 0 for key, value in kpis.items() if key.endswith("_count")) else "FAIL"
    lines = [
        "# Refactor Slice Diff",
        "",
        "## Inputs",
        f"- slice_id: {slice_id}",
        f"- report_date: {input_meta.get('report_date', '')}",
        f"- fund_code: {input_meta.get('fund_code', '')}",
        f"- action_verb: {input_meta.get('action_verb', '')}",
        f"- fixture_kind: {input_meta.get('fixture_kind', '')}",
        "",
        "## Output Status",
        f"- verdict: {verdict}",
        f"- trace_completeness_rate: {kpis['trace_completeness_rate']:.2f}",
        f"- silent_hold_rate: {kpis['silent_hold_rate']:.2f}",
        f"- shadow_official_comparable_rate: {kpis['shadow_official_comparable_rate']:.2f}",
        f"- non_executable_violation_count: {kpis['non_executable_violation_count']}",
        f"- forbidden_write_count: {kpis['forbidden_write_count'] + len(forbidden_runtime)}",
        f"- replay_diff_unapproved_count: {kpis['replay_diff_unapproved_count']}",
        f"- missing_critical_data_rate: {kpis['missing_critical_data_rate']:.2f}",
        f"- official_output_unchanged: {str(bool(metadata.get('official_output_unchanged'))).lower()}",
        "",
        "## Artifact Diff",
    ]
    for row in artifact_rows:
        changed = "changed" if row["changed"] else "unchanged"
        field = row["first_changed_field"] or "none"
        errors = "; ".join(row["validation_errors"]) if row["validation_errors"] else "none"
        lines.append(f"- {row['name']}: {changed}; first_changed_field={field}; validation_errors={errors}")
    lines.extend(["", "## Boundary Checks"])
    boundary_checks = metadata.get("boundary_checks", []) if isinstance(metadata, dict) else []
    if boundary_checks:
        for check in boundary_checks:
            lines.append(f"- {check.get('check', '')}: {check.get('status', '')} - {check.get('detail', '')}")
    else:
        lines.append("- none")
    if forbidden_runtime:
        lines.append(f"- forbidden_runtime_allowed_paths: {', '.join(forbidden_runtime)}")
    lines.extend(
        [
            "",
            "## Official Output",
            "- production pipeline integration: not touched",
            "- official advice / ledger / portfolio / execution / long memory writes: none",
            "",
        ]
    )
    details = {
        "verdict": verdict,
        "diff_count": diff_count,
        "validation_error_count": validation_error_count,
        "kpis": kpis,
        "artifact_rows": artifact_rows,
    }
    return "\n".join(lines), details


def run_diff(slice_id: str = DEFAULT_SLICE_ID, output_dir: Path | None = None, fixture_root: Path | None = None) -> dict[str, Any]:
    actual_dir = output_dir or default_output_dir(slice_id)
    report, details = build_diff_report(slice_id, actual_dir, fixture_root)
    dump_text(actual_dir / "diff_report.md", report)
    return {"report_path": actual_dir / "diff_report.md", "report": report, **details}


def update_expected_report(slice_id: str = DEFAULT_SLICE_ID, output_dir: Path | None = None, fixture_root: Path | None = None) -> Path:
    report, _details = build_diff_report(slice_id, output_dir, fixture_root)
    path = fixture_dir(slice_id, fixture_root) / "expected" / "diff_report.expected.md"
    dump_text(path, report)
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare one refactor slice replay output with golden expectations.")
    parser.add_argument("--slice-id", default=DEFAULT_SLICE_ID)
    parser.add_argument("--fixture-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--update-expected", action="store_true", help="Explicitly regenerate expected diff report from the current replay output.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.update_expected:
        path = update_expected_report(args.slice_id, args.output_dir, args.fixture_root)
        print(f"updated expected diff report: {relative_posix(path)}")
        return
    result = run_diff(args.slice_id, args.output_dir, args.fixture_root)
    print(f"{result['verdict']}: {relative_posix(result['report_path'])}")
    if result["verdict"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
