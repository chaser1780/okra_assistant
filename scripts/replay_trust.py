from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "historical_replay_trust.v1"
TRUST_MODES = {"trusted", "structural_only", "blocked"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TIMESTAMP_KEYS = {"available_from", "retrieved_at", "published_at"}


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk(value: Any, location: str = "$"):
    yield location, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{location}[{index}]")


def _execution_evidence_reason(value: dict) -> str:
    domain = str(value.get("domain", "") or "").lower()
    memory_type = str(value.get("memory_type", "") or "").lower()
    source_kind = str(value.get("source_kind", "") or "").lower()
    source_path = str(value.get("source_path", "") or "").replace("\\", "/").lower()
    record_id = str(value.get("source_record_id", value.get("memory_id", "")) or "").lower()
    metadata = value.get("metadata", {}) or {}
    learning_scope = str(metadata.get("learning_scope", value.get("learning_scope", "")) or "").lower() if isinstance(metadata, dict) else ""
    if value.get("include_execution") is True:
        return "execution_visibility_enabled"
    if domain == "execution":
        return "execution_domain_visible"
    if memory_type == "execution_memory":
        return "execution_memory_visible"
    if learning_scope == "execution_only":
        return "execution_only_memory_visible"
    if source_kind == "execution" or source_kind.startswith("execution_"):
        return "execution_source_visible"
    if source_path.startswith("db/execution_sync/") or source_path.startswith("db/long_memory/execution/"):
        return "execution_source_path_visible"
    if record_id.startswith("execution:") or record_id.startswith("memory:execution:"):
        return "execution_record_visible"
    return ""


def _inspect_decision_json(payload: Any, cutoff: datetime) -> list[dict]:
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for location, value in _walk(payload):
        if not isinstance(value, dict):
            continue
        execution_reason = _execution_evidence_reason(value)
        if execution_reason and (execution_reason, location) not in seen:
            findings.append({"code": execution_reason, "location": location})
            seen.add((execution_reason, location))
        for key, raw_timestamp in value.items():
            check_timestamp = (
                key in TIMESTAMP_KEYS
                or (location == "$" and key == "generated_at")
                or (key == "updated_at" and location.endswith(".state_metadata"))
            )
            if not check_timestamp or raw_timestamp in (None, ""):
                continue
            parsed = _parse_timestamp(raw_timestamp)
            if parsed is None:
                code = "invalid_decision_timestamp"
            elif parsed > cutoff:
                code = "future_decision_evidence"
            else:
                continue
            marker = (code, f"{location}.{key}")
            if marker not in seen:
                findings.append({"code": code, "location": marker[1], "value": raw_timestamp})
                seen.add(marker)
    return findings


def _empty_audit(manifest_path: Path, key: str, entry_type: str) -> dict:
    return {
        "schema_version": "replay_trust_audit.v1",
        "manifest_path": str(manifest_path),
        "entry_type": entry_type,
        "replay_key": key,
        "mode": "blocked",
        "learning_eligible": False,
        "decision_cutoff": "",
        "integrity_passed": False,
        "contamination_findings": [],
        "reason_codes": [],
        "source_audits": [],
        "allowed_for_replay": False,
        "allowed_for_learning": False,
    }


def audit_replay_entry(
    agent_home: Path,
    key: str,
    *,
    entry_type: str = "dates",
    include_structural: bool = False,
    manifest_path: Path | None = None,
    required_sources: list[dict] | None = None,
) -> dict:
    agent_home = agent_home.resolve()
    manifest_path = (manifest_path or agent_home / "config" / "historical_replay_trust.json").resolve()
    audit = _empty_audit(manifest_path, key, entry_type)
    if not manifest_path.is_file():
        audit["reason_codes"].append("missing_trust_manifest")
        return audit
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        audit["reason_codes"].append("invalid_trust_manifest")
        return audit
    if manifest.get("schema_version") != SCHEMA_VERSION:
        audit["reason_codes"].append("unsupported_trust_manifest_schema")
        return audit
    entries = manifest.get(entry_type, {})
    if not isinstance(entries, dict):
        audit["reason_codes"].append("invalid_trust_manifest_entries")
        return audit
    entry = entries.get(key)
    if not isinstance(entry, dict):
        audit["mode"] = str(manifest.get("default_mode", "blocked") or "blocked")
        audit["reason_codes"].append("missing_trust_entry")
        return audit

    mode = str(entry.get("mode", "") or "")
    audit["mode"] = mode
    audit["learning_eligible"] = entry.get("learning_eligible") is True
    audit["decision_cutoff"] = str(entry.get("decision_cutoff", "") or "")
    if mode not in TRUST_MODES:
        audit["reason_codes"].append("unknown_trust_mode")
    cutoff = _parse_timestamp(entry.get("decision_cutoff"))
    if cutoff is None:
        audit["reason_codes"].append("invalid_decision_cutoff")
    expected_date = str(entry.get("report_date", key if entry_type == "dates" else "") or "")
    if entry_type == "dates" and expected_date != key:
        audit["reason_codes"].append("report_date_mismatch")

    sources = entry.get("sources", [])
    if not isinstance(sources, list) or not sources:
        audit["reason_codes"].append("missing_trust_sources")
        sources = []
    seen_paths: set[str] = set()
    contamination: list[dict] = []
    for source in sources:
        source_audit = {"kind": "", "role": "", "path": "", "integrity_passed": False, "findings": []}
        audit["source_audits"].append(source_audit)
        if not isinstance(source, dict):
            source_audit["error"] = "invalid_source_entry"
            audit["reason_codes"].append("invalid_source_entry")
            continue
        source_audit.update(
            {
                "kind": str(source.get("kind", "") or ""),
                "role": str(source.get("role", "decision") or "decision"),
                "path": str(source.get("path", "") or ""),
            }
        )
        if source_audit["role"] not in {"decision", "evaluation"}:
            source_audit["error"] = "invalid_source_role"
            audit["reason_codes"].append("invalid_source_role")
            continue
        relative_path = source_audit["path"]
        if not relative_path or relative_path in seen_paths:
            code = "duplicate_source_path" if relative_path in seen_paths else "missing_source_path"
            source_audit["error"] = code
            audit["reason_codes"].append(code)
            continue
        seen_paths.add(relative_path)
        resolved = (agent_home / relative_path).resolve()
        try:
            resolved.relative_to(agent_home)
        except ValueError:
            source_audit["error"] = "source_path_outside_agent_home"
            audit["reason_codes"].append("source_path_outside_agent_home")
            continue
        expected_hash = str(source.get("sha256", "") or "")
        if not SHA256_PATTERN.fullmatch(expected_hash):
            source_audit["error"] = "invalid_source_sha256"
            audit["reason_codes"].append("invalid_source_sha256")
            continue
        if not resolved.is_file():
            source_audit["error"] = "missing_source_file"
            audit["reason_codes"].append("missing_source_file")
            continue
        actual_hash = _sha256(resolved)
        source_audit["sha256"] = actual_hash
        if actual_hash != expected_hash:
            source_audit["error"] = "source_hash_mismatch"
            audit["reason_codes"].append("source_hash_mismatch")
            continue
        if resolved.suffix.lower() == ".json":
            try:
                payload = json.loads(resolved.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                source_audit["error"] = "invalid_source_json"
                audit["reason_codes"].append("invalid_source_json")
                continue
            if source_audit["role"] == "decision" and cutoff is not None:
                source_findings = _inspect_decision_json(payload, cutoff)
                source_audit["findings"] = source_findings
                contamination.extend({**item, "source_path": relative_path} for item in source_findings)
        source_audit["integrity_passed"] = True

    declared_sources = {(item.get("path"), item.get("role")) for item in audit["source_audits"]}
    for required in required_sources or []:
        required_path = str(required.get("path", "") or "")
        required_role = str(required.get("role", "decision") or "decision")
        if (required_path, required_role) not in declared_sources:
            audit["reason_codes"].append("unlisted_required_source")

    audit["reason_codes"] = sorted(set(audit["reason_codes"]))
    audit["contamination_findings"] = contamination
    audit["integrity_passed"] = not audit["reason_codes"] and all(item.get("integrity_passed") for item in audit["source_audits"])
    uncontaminated = not contamination
    audit["allowed_for_replay"] = bool(
        audit["integrity_passed"]
        and ((mode == "trusted" and uncontaminated) or (mode == "structural_only" and include_structural))
    )
    audit["allowed_for_learning"] = bool(
        audit["integrity_passed"]
        and uncontaminated
        and mode == "trusted"
        and audit["learning_eligible"]
    )
    return audit


def audit_replay_dates(
    agent_home: Path,
    report_dates: list[str],
    *,
    include_structural: bool = False,
    required_sources_by_date: dict[str, list[dict]] | None = None,
) -> dict:
    date_audits = [
        audit_replay_entry(
            agent_home,
            report_date,
            include_structural=include_structural,
            required_sources=(required_sources_by_date or {}).get(report_date, []),
        )
        for report_date in sorted(set(report_dates))
    ]
    return {
        "schema_version": "replay_trust_batch_audit.v1",
        "selected_dates": sorted(set(report_dates)),
        "all_allowed_for_replay": bool(date_audits) and all(item["allowed_for_replay"] for item in date_audits),
        "all_allowed_for_learning": bool(date_audits) and all(item["allowed_for_learning"] for item in date_audits),
        "date_audits": date_audits,
    }
