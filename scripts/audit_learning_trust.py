from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from common import dump_json, resolve_agent_home, timestamp_now
from replay_trust import audit_replay_entry


SCHEMA_VERSION = "learning_trust_audit.v1"
TRUST_STATUSES = {"trusted", "legacy_untrusted", "blocked"}
DEFAULT_OUTPUT = "db/learning_trust_audits/latest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _confined_path(agent_home: Path, value: str | Path, *, root: Path | None = None) -> Path:
    raw = Path(value).expanduser()
    resolved = (raw if raw.is_absolute() else agent_home / raw).resolve()
    boundary = (root or agent_home).resolve()
    try:
        resolved.relative_to(boundary)
    except ValueError as exc:
        raise ValueError(f"path is outside allowed root {boundary}: {value}") from exc
    return resolved


def _relative(agent_home: Path, path: Path) -> str:
    return path.resolve().relative_to(agent_home.resolve()).as_posix()


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _finite_number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return {status: sum(item.get("trust_status") == status for item in records) for status in sorted(TRUST_STATUSES)}


def _aggregate_status(statuses: list[str]) -> str:
    if not statuses or "blocked" in statuses:
        return "blocked"
    if "legacy_untrusted" in statuses:
        return "legacy_untrusted"
    return "trusted"


def _source_artifact(agent_home: Path, path: Path, kind: str) -> dict[str, Any]:
    return {"kind": kind, "path": _relative(agent_home, path), "sha256": _sha256(path)}


def _audit_outcomes(
    agent_home: Path,
    manifest_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    artifacts: list[dict[str, Any]] = []
    errors: list[str] = []
    trust_by_date: dict[str, dict[str, Any]] = {}
    for path in sorted((agent_home / "db" / "outcome_events").glob("*.json")):
        artifacts.append(_source_artifact(agent_home, path, "outcome_event_artifact"))
        try:
            payload = _load_json_object(path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"invalid_outcome_artifact:{_relative(agent_home, path)}:{exc}")
            continue
        for position, outcome in enumerate(payload.get("events", []) or []):
            if not isinstance(outcome, dict):
                errors.append(f"invalid_outcome_record:{_relative(agent_home, path)}:{position}")
                continue
            outcome_id = str(outcome.get("outcome_id", "") or "")
            base_date = str(outcome.get("base_date", payload.get("base_date", "")) or "")
            decision_context = outcome.get("decision_context", {})
            decision_context = decision_context if isinstance(decision_context, dict) else {}
            reasons: list[str] = []
            excess_return = _finite_number(outcome.get("excess_return_pct"))
            if not outcome_id:
                reasons.append("missing_outcome_id")
            if str(outcome.get("scoring_status", "") or "") != "scored":
                reasons.append("outcome_not_scored")
            if decision_context.get("learning_eligible") is not True:
                reasons.append("source_outcome_not_learning_eligible")
            if str(decision_context.get("learning_basis", "") or "") not in {"benchmark_excess_return", "benchmark_excess_return_net_cost"}:
                reasons.append("missing_relative_learning_basis")
            if excess_return is None:
                reasons.append("missing_or_nonfinite_excess_return")
            elif excess_return == 0.0:
                reasons.append("neutral_excess_return")
            if not base_date:
                reasons.append("missing_base_date")

            data_valid = not reasons
            replay_audit = trust_by_date.get(base_date)
            if replay_audit is None and base_date:
                replay_audit = audit_replay_entry(agent_home, base_date, manifest_path=manifest_path)
                trust_by_date[base_date] = replay_audit
            replay_audit = replay_audit or {
                "mode": "blocked",
                "allowed_for_learning": False,
                "reason_codes": ["missing_base_date"],
            }
            if data_valid and replay_audit.get("allowed_for_learning") is True:
                trust_status = "trusted"
            elif data_valid:
                trust_status = "legacy_untrusted"
                reasons.append("replay_not_trusted_for_learning")
            else:
                trust_status = "blocked"

            record = {
                "outcome_id": outcome_id or f"missing:{_relative(agent_home, path)}:{position}",
                "source_artifact": _relative(agent_home, path),
                "source_artifact_sha256": _sha256(path),
                "base_date": base_date,
                "horizon": str(outcome.get("horizon", payload.get("horizon", "")) or ""),
                "learning_eligible": decision_context.get("learning_eligible") is True,
                "learning_basis": str(decision_context.get("learning_basis", "") or ""),
                "excess_return_pct": excess_return,
                "trust_status": trust_status,
                "reason_codes": sorted(set(reasons)),
                "replay_trust": {
                    "mode": replay_audit.get("mode", "blocked"),
                    "allowed_for_learning": replay_audit.get("allowed_for_learning") is True,
                    "reason_codes": list(replay_audit.get("reason_codes", []) or []),
                    "contamination_codes": sorted(
                        {str(item.get("code", "") or "") for item in replay_audit.get("contamination_findings", []) or []}
                        - {""}
                    ),
                },
            }
            records.append(record)
            if outcome_id:
                if outcome_id in index:
                    record["trust_status"] = "blocked"
                    record["reason_codes"] = sorted(set(record["reason_codes"] + ["duplicate_outcome_id"]))
                    index[outcome_id]["trust_status"] = "blocked"
                    index[outcome_id]["reason_codes"] = sorted(
                        set(index[outcome_id]["reason_codes"] + ["duplicate_outcome_id"])
                    )
                else:
                    index[outcome_id] = record
    records.sort(key=lambda item: (item["outcome_id"], item["source_artifact"]))
    return records, index, artifacts, errors


def _audit_policy_events(
    agent_home: Path,
    outcome_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[str]]:
    path = agent_home / "db" / "strategy_memory" / "policy_events.jsonl"
    if not path.is_file():
        return [], {}, [], ["missing_policy_event_log"]
    artifacts = [_source_artifact(agent_home, path, "policy_event_log")]
    records: list[dict[str, Any]] = []
    by_policy: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("event must be an object")
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(f"invalid_policy_event:{line_number}:{exc}")
            records.append(
                {
                    "event_id": f"invalid_line:{line_number}",
                    "policy_id": "",
                    "source_outcome_id": "",
                    "trust_status": "blocked",
                    "reason_codes": ["invalid_policy_event"],
                }
            )
            continue

        event_id = str(event.get("event_id", "") or f"missing_line:{line_number}")
        policy_id = str(event.get("policy_id", "") or "")
        outcome_id = str(event.get("source_outcome_id", "") or "")
        event_audit = event.get("audit", {})
        event_audit = event_audit if isinstance(event_audit, dict) else {}
        reasons: list[str] = []
        critical = False
        if not policy_id:
            reasons.append("missing_policy_id")
            critical = True
        source_outcome = outcome_index.get(outcome_id)
        if not outcome_id or source_outcome is None:
            reasons.append("missing_source_outcome")
            critical = True
        if event.get("non_executable") is not True or str(event.get("write_scope", "") or "") != "learning_only":
            reasons.append("policy_event_boundary_violation")
            critical = True

        source_path_text = str(event.get("source_artifact", "") or "")
        source_hash_matches = False
        try:
            source_path = _confined_path(agent_home, source_path_text)
        except ValueError:
            reasons.append("source_artifact_path_outside_agent_home")
            critical = True
        else:
            if not source_path.is_file():
                reasons.append("missing_source_artifact")
                critical = True
            else:
                expected_hash = str(event_audit.get("source_artifact_sha256", "") or "")
                source_hash_matches = bool(expected_hash) and _sha256(source_path) == expected_hash
                if not source_hash_matches:
                    reasons.append("source_artifact_hash_mismatch")

        relative_semantics = str(event_audit.get("learning_signal_basis", "") or "") in {"benchmark_excess_return", "benchmark_excess_return_net_cost"}
        if not relative_semantics:
            reasons.append("legacy_absolute_return_semantics")
        if critical:
            trust_status = "blocked"
        elif not relative_semantics:
            trust_status = "legacy_untrusted"
        elif not source_hash_matches:
            trust_status = "blocked"
        else:
            trust_status = str(source_outcome.get("trust_status", "blocked"))
            if trust_status != "trusted":
                reasons.append("source_outcome_not_trusted")
        record = {
            "event_id": event_id,
            "policy_id": policy_id,
            "source_outcome_id": outcome_id,
            "source_artifact": source_path_text.replace("\\", "/"),
            "source_artifact_hash_matches": source_hash_matches,
            "learning_signal_basis": str(event_audit.get("learning_signal_basis", "") or ""),
            "trust_status": trust_status,
            "reason_codes": sorted(set(reasons)),
        }
        records.append(record)
        if policy_id:
            by_policy.setdefault(policy_id, []).append(record)
    records.sort(key=lambda item: item["event_id"])
    return records, by_policy, artifacts, errors


def _audit_policies(
    agent_home: Path,
    outcome_index: dict[str, dict[str, Any]],
    events_by_policy: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    path = agent_home / "db" / "strategy_memory" / "policies.json"
    if not path.is_file():
        return [], {}, [], ["missing_policy_store"]
    artifacts = [_source_artifact(agent_home, path, "policy_store")]
    try:
        payload = _load_json_object(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [], {}, artifacts, [f"invalid_policy_store:{exc}"]
    records: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for position, policy in enumerate(payload.get("policies", []) or []):
        if not isinstance(policy, dict):
            errors.append(f"invalid_policy_record:{position}")
            continue
        policy_id = str(policy.get("policy_id", "") or "")
        source_ids = sorted({str(item) for item in policy.get("source_outcome_ids", []) or [] if str(item)})
        reasons: list[str] = []
        event_records = events_by_policy.get(policy_id, [])
        statuses = [item["trust_status"] for item in event_records]
        if not event_records:
            reasons.append("missing_source_policy_events")
        missing_outcomes = [item for item in source_ids if item not in outcome_index]
        if not source_ids:
            reasons.append("missing_source_outcome_ids")
        if missing_outcomes:
            reasons.append("missing_source_outcomes")
            statuses.append("blocked")
        outcome_statuses = [outcome_index[item]["trust_status"] for item in source_ids if item in outcome_index]
        if statuses and all(item == "legacy_untrusted" for item in statuses):
            trust_status = "legacy_untrusted"
        else:
            trust_status = _aggregate_status(statuses + outcome_statuses)
        if not event_records:
            trust_status = "blocked"
        if trust_status != "trusted":
            reasons.append("policy_lineage_not_trusted")
        record = {
            "policy_id": policy_id or f"missing:{position}",
            "original_status": str(policy.get("status", "") or ""),
            "source_outcome_ids": source_ids,
            "source_policy_event_ids": sorted(item["event_id"] for item in event_records),
            "trust_status": trust_status,
            "reason_codes": sorted(set(reasons)),
        }
        records.append(record)
        if policy_id:
            index[policy_id] = record
    records.sort(key=lambda item: item["policy_id"])
    return records, index, artifacts, errors


def _audit_skills(
    agent_home: Path,
    outcome_index: dict[str, dict[str, Any]],
    policy_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    registry_path = agent_home / "db" / "strategy_skills" / "registry.json"
    if not registry_path.is_file():
        return [], [], ["missing_skill_registry"]
    artifacts = [_source_artifact(agent_home, registry_path, "strategy_skill_registry")]
    try:
        payload = _load_json_object(registry_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [], artifacts, [f"invalid_skill_registry:{exc}"]
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    registry_boundary_ok = payload.get("non_executable") is True and payload.get("auto_activation_allowed") is False
    for position, entry in enumerate(payload.get("entries", []) or []):
        if not isinstance(entry, dict):
            errors.append(f"invalid_skill_registry_entry:{position}")
            continue
        skill_id = str(entry.get("skill_id", "") or "")
        policy_ids = sorted({str(item) for item in entry.get("source_policy_ids", []) or [] if str(item)})
        outcome_ids = sorted({str(item) for item in entry.get("source_outcome_ids", []) or [] if str(item)})
        reasons: list[str] = []
        critical = not registry_boundary_ok
        if critical:
            reasons.append("skill_registry_boundary_violation")
        if entry.get("non_executable") is not True or entry.get("auto_activation_allowed") is not False:
            reasons.append("skill_boundary_violation")
            critical = True
        policy_statuses: list[str] = []
        outcome_statuses: list[str] = []
        for policy_id in policy_ids:
            policy = policy_index.get(policy_id)
            if policy is None:
                reasons.append("missing_source_policy")
                critical = True
            else:
                policy_statuses.append(policy["trust_status"])
        for outcome_id in outcome_ids:
            outcome = outcome_index.get(outcome_id)
            if outcome is None:
                reasons.append("missing_source_outcome")
                critical = True
            else:
                outcome_statuses.append(outcome["trust_status"])
        if not policy_ids or not outcome_ids:
            reasons.append("incomplete_skill_lineage")
            critical = True

        paths: dict[str, str] = {}
        for field, kind in (("skill_path", "strategy_skill_markdown"), ("event_log_path", "strategy_skill_event_log")):
            value = str(entry.get(field, "") or "")
            paths[field] = value.replace("\\", "/")
            try:
                source_path = _confined_path(agent_home, value)
            except ValueError:
                reasons.append(f"{field}_outside_agent_home")
                critical = True
                continue
            if not source_path.is_file():
                reasons.append(f"missing_{field}")
                critical = True
                continue
            artifacts.append(_source_artifact(agent_home, source_path, kind))

        if critical:
            trust_status = "blocked"
        elif policy_statuses and all(item == "legacy_untrusted" for item in policy_statuses):
            trust_status = "legacy_untrusted"
        else:
            trust_status = _aggregate_status(policy_statuses + outcome_statuses)
        if trust_status != "trusted":
            reasons.append("skill_lineage_not_trusted")
        records.append(
            {
                "skill_id": skill_id or f"missing:{position}",
                "original_status": str(entry.get("status", "") or ""),
                "source_policy_ids": policy_ids,
                "source_outcome_ids": outcome_ids,
                **paths,
                "trust_status": trust_status,
                "reason_codes": sorted(set(reasons)),
            }
        )
    records.sort(key=lambda item: item["skill_id"])
    artifacts = sorted({item["path"]: item for item in artifacts}.values(), key=lambda item: item["path"])
    return records, artifacts, errors


def build_learning_trust_audit(
    agent_home: Path,
    *,
    generated_at: str | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    agent_home = agent_home.resolve()
    manifest = _confined_path(
        agent_home,
        manifest_path or agent_home / "config" / "historical_replay_trust.json",
    )
    outcomes, outcome_index, outcome_artifacts, outcome_errors = _audit_outcomes(agent_home, manifest)
    policy_events, events_by_policy, event_artifacts, event_errors = _audit_policy_events(agent_home, outcome_index)
    policies, policy_index, policy_artifacts, policy_errors = _audit_policies(agent_home, outcome_index, events_by_policy)
    skills, skill_artifacts, skill_errors = _audit_skills(agent_home, outcome_index, policy_index)
    source_artifacts = outcome_artifacts + event_artifacts + policy_artifacts + skill_artifacts
    if manifest.is_file():
        source_artifacts.append(_source_artifact(agent_home, manifest, "historical_replay_trust_manifest"))
    source_artifacts = sorted({item["path"]: item for item in source_artifacts}.values(), key=lambda item: item["path"])
    input_errors = sorted(outcome_errors + event_errors + policy_errors + skill_errors)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or timestamp_now(),
        "write_scope": "audit_only",
        "non_executable": True,
        "manifest_path": _relative(agent_home, manifest),
        "source_artifacts": source_artifacts,
        "input_errors": input_errors,
        "outcomes": outcomes,
        "policy_events": policy_events,
        "policies": policies,
        "skills": skills,
        "summary": {
            "outcomes": _status_counts(outcomes),
            "policy_events": _status_counts(policy_events),
            "policies": _status_counts(policies),
            "skills": _status_counts(skills),
            "input_error_count": len(input_errors),
            "trusted_learning_artifact_count": sum(
                item.get("trust_status") == "trusted"
                for group in (outcomes, policy_events, policies, skills)
                for item in group
            ),
            "source_mutation_count": 0,
            "activation_change_count": 0,
        },
    }


def write_learning_trust_audit(
    agent_home: Path,
    audit: dict[str, Any],
    *,
    output: str | Path = DEFAULT_OUTPUT,
) -> Path:
    agent_home = agent_home.resolve()
    path = _confined_path(agent_home, output, root=agent_home / "db" / "learning_trust_audits")
    if path.suffix.lower() != ".json":
        raise ValueError("learning trust audit output must be a .json file")
    dump_json(path, audit)
    return path


def run_audit(
    agent_home: Path,
    *,
    generated_at: str | None = None,
    manifest_path: Path | None = None,
    output: str | Path = DEFAULT_OUTPUT,
) -> tuple[Path, dict[str, Any]]:
    audit = build_learning_trust_audit(agent_home, generated_at=generated_at, manifest_path=manifest_path)
    path = write_learning_trust_audit(agent_home, audit, output=output)
    return path, audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit historical learning lineage without mutating source artifacts.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--manifest", help="Replay trust manifest path inside agent home.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="JSON path under db/learning_trust_audits.")
    parser.add_argument("--generated-at", default="", help="Fixed timestamp for deterministic output.")
    parser.add_argument("--format", choices=["summary", "json"], default="summary")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    manifest = Path(args.manifest) if args.manifest else None
    path, audit = run_audit(
        agent_home,
        generated_at=args.generated_at or None,
        manifest_path=manifest,
        output=args.output,
    )
    if args.format == "json":
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        print(f"wrote learning trust audit: {_relative(agent_home, path)}")
        print(json.dumps(audit["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
