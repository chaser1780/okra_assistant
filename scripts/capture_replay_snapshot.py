from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from common import ensure_layout, project_relative_path, resolve_agent_home, resolve_date
from replay_trust import _inspect_decision_json, audit_replay_entry


SNAPSHOT_SCHEMA_VERSION = "replay_decision_snapshot.v1"
CANDIDATE_SCHEMA_VERSION = "replay_trust_candidate.v1"
SOURCE_KIND_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def _default_sources(report_date: str) -> list[dict[str, str]]:
    dated = (
        ("quotes", f"raw/quotes/{report_date}.json"),
        ("news", f"raw/news/{report_date}.json"),
        ("fund_profiles", f"raw/fund_profiles/{report_date}.json"),
        ("daily_scores", f"db/daily_scores/{report_date}.json"),
        ("intraday_proxies", f"db/intraday_proxies/{report_date}.json"),
        ("realtime_monitor", f"db/realtime_monitor/{report_date}.json"),
        ("source_health", f"db/source_health/{report_date}.json"),
        ("news_query_plan", f"db/news_query_plans/{report_date}.json"),
        ("llm_context", f"db/llm_context/{report_date}.json"),
        ("evidence_index", f"db/evidence_index/{report_date}.json"),
        ("committee_advice", f"db/committee_advice/{report_date}.json"),
        ("llm_raw", f"db/llm_raw/{report_date}.json"),
        ("llm_advice", f"db/llm_advice/{report_date}.json"),
        ("committee_decision_bundle", f"db/committee_decision_bundle/{report_date}.json"),
        ("validated_advice", f"db/validated_advice/{report_date}.json"),
        ("action_seed", f"db/action_seed/{report_date}.json"),
        ("action_tickets", f"db/action_tickets/{report_date}.json"),
        ("retrieval_packs", f"db/retrieval_packs/{report_date}.json"),
        ("action_debates", f"db/action_debates/{report_date}.json"),
        ("decisions", f"db/decisions/{report_date}.json"),
        ("portfolio_state", f"db/portfolio_state/snapshots/{report_date}.json"),
    )
    config = (
        ("benchmark_mappings", "config/benchmark_mappings.json"),
        ("strategy_config", "config/strategy.toml"),
        ("watchlist", "config/watchlist.json"),
    )
    return [
        {"kind": kind, "role": "decision", "path": path}
        for kind, path in (*config, *dated)
    ]


def _parse_cutoff(report_date: str, value: str) -> tuple[datetime, str]:
    try:
        parsed = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("decision_cutoff must be an ISO-8601 timestamp with a UTC offset") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("decision_cutoff must include a UTC offset")
    if parsed.date().isoformat() != report_date:
        raise ValueError("decision_cutoff date must match report_date")
    normalized = parsed.isoformat(timespec="microseconds" if parsed.microsecond else "seconds")
    return parsed, normalized


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _normalize_source(agent_home: Path, raw: dict[str, Any]) -> dict[str, Any]:
    role = str(raw.get("role", "") or "").strip()
    kind = str(raw.get("kind", "") or "").strip()
    raw_path = str(raw.get("path", "") or "").strip()
    if role not in {"decision", "evaluation"}:
        raise ValueError(f"invalid source role: {role or '<empty>'}")
    if not SOURCE_KIND_PATTERN.fullmatch(kind):
        raise ValueError(f"invalid source kind: {kind or '<empty>'}")
    path = Path(raw_path)
    if not raw_path or path.is_absolute():
        raise ValueError("source paths must be non-empty paths relative to agent_home")
    resolved = (agent_home / path).resolve()
    try:
        relative = resolved.relative_to(agent_home)
    except ValueError as exc:
        raise ValueError(f"source path escapes agent_home: {raw_path}") from exc
    if relative.parts[:2] == ("db", "replay_snapshots"):
        raise ValueError("replay snapshots cannot be used as capture sources")
    if not resolved.is_file():
        raise FileNotFoundError(f"capture source does not exist: {relative.as_posix()}")
    content = resolved.read_bytes()
    return {
        "kind": kind,
        "role": role,
        "original_path": relative.as_posix(),
        "content": content,
        "sha256": _sha256_bytes(content),
    }


def _expand_declared_sources(agent_home: Path, sources: list[dict[str, str]]) -> list[dict[str, str]]:
    expanded = list(sources)
    known_paths = {item["path"] for item in expanded}
    index = 0
    while index < len(expanded):
        source = expanded[index]
        index += 1
        source_path = (agent_home / source["path"]).resolve()
        if source_path.suffix.lower() != ".json":
            continue
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        declared = payload.get("source_artifacts", []) if isinstance(payload, dict) else []
        if not isinstance(declared, list):
            continue
        for dependency in declared:
            if not isinstance(dependency, dict):
                continue
            relative_text = str(dependency.get("path", "") or "").strip()
            dependency_path = Path(relative_text)
            if not relative_text or dependency_path.is_absolute():
                raise ValueError(f"invalid declared decision source path: {relative_text or '<empty>'}")
            resolved = (agent_home / dependency_path).resolve()
            try:
                relative = resolved.relative_to(agent_home).as_posix()
            except ValueError as exc:
                raise ValueError(f"declared decision source escapes agent_home: {relative_text}") from exc
            if not resolved.is_file():
                raise FileNotFoundError(f"declared decision source does not exist: {relative}")
            if relative in known_paths:
                continue
            raw_kind = str(dependency.get("kind", "declared_source") or "declared_source").strip().lower()
            kind = raw_kind if SOURCE_KIND_PATTERN.fullmatch(raw_kind) else "declared_source"
            expanded.append({"kind": kind, "role": "decision", "path": relative})
            known_paths.add(relative)
    return expanded


def discover_decision_sources(agent_home: Path, report_date: str) -> list[dict[str, str]]:
    discovered = [item for item in _default_sources(report_date) if (agent_home / item["path"]).is_file()]
    discovered = _expand_declared_sources(agent_home, discovered)
    by_kind = {item["kind"] for item in discovered}
    required = {"benchmark_mappings", "llm_advice", "validated_advice", "portfolio_state"}
    missing = sorted(required - by_kind)
    if missing:
        raise FileNotFoundError(f"required decision snapshot sources are missing: {', '.join(missing)}")
    return discovered


def _contamination_findings(source: dict[str, Any], cutoff: datetime, snapshot_path: str) -> list[dict[str, Any]]:
    if source["role"] != "decision" or not source["original_path"].endswith(".json"):
        return []
    try:
        payload = json.loads(source["content"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return [
            {
                "code": "invalid_source_json",
                "location": "$",
                "source_path": snapshot_path,
                "original_path": source["original_path"],
            }
        ]
    return [
        {
            **finding,
            "source_path": snapshot_path,
            "original_path": source["original_path"],
        }
        for finding in _inspect_decision_json(payload, cutoff)
    ]


def _verify_existing_snapshot(snapshot_dir: Path, expected_files: dict[Path, bytes]) -> None:
    actual_files = {path.relative_to(snapshot_dir) for path in snapshot_dir.rglob("*") if path.is_file()}
    if actual_files != set(expected_files):
        raise RuntimeError(f"immutable replay snapshot contents changed: {snapshot_dir}")
    for relative, expected in expected_files.items():
        if (snapshot_dir / relative).read_bytes() != expected:
            raise RuntimeError(f"immutable replay snapshot conflict: {(snapshot_dir / relative).as_posix()}")


def capture_decision_snapshot(
    agent_home: Path,
    report_date: str,
    decision_cutoff: str,
    *,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    agent_home = agent_home.resolve()
    report_date = resolve_date(report_date)
    cutoff, normalized_cutoff = _parse_cutoff(report_date, decision_cutoff)
    ensure_layout(agent_home)
    source_specs = sources if sources is not None else discover_decision_sources(agent_home, report_date)
    if not source_specs:
        raise ValueError("at least one capture source is required")
    normalized_sources = [_normalize_source(agent_home, item) for item in source_specs]
    original_paths = [item["original_path"] for item in normalized_sources]
    if len(set(original_paths)) != len(original_paths):
        raise ValueError("duplicate capture source path")
    normalized_sources.sort(key=lambda item: (item["role"], item["kind"], item["original_path"]))

    cutoff_key = hashlib.sha256(normalized_cutoff.encode("utf-8")).hexdigest()[:12]
    snapshot_id = f"{report_date}__{cutoff_key}"
    snapshot_dir = agent_home / "db" / "replay_snapshots" / snapshot_id
    candidate_relative = Path("manifest_candidate.json")
    candidate_path = snapshot_dir / candidate_relative

    candidate_sources: list[dict[str, str]] = []
    source_origins: list[dict[str, str]] = []
    expected_files: dict[Path, bytes] = {}
    findings: list[dict[str, Any]] = []
    for source in normalized_sources:
        copy_relative = Path("sources") / Path(source["original_path"])
        snapshot_source_path = snapshot_dir / copy_relative
        snapshot_source_relative = snapshot_source_path.relative_to(agent_home).as_posix()
        expected_files[copy_relative] = source["content"]
        candidate_sources.append(
            {
                "kind": source["kind"],
                "role": source["role"],
                "path": snapshot_source_relative,
                "sha256": source["sha256"],
            }
        )
        source_origins.append(
            {
                "kind": source["kind"],
                "role": source["role"],
                "original_path": source["original_path"],
                "snapshot_path": snapshot_source_relative,
                "sha256": source["sha256"],
            }
        )
        findings.extend(_contamination_findings(source, cutoff, snapshot_source_relative))

    reason_codes = sorted({"candidate_not_reviewed", *(item["code"] for item in findings)})
    candidate = {
        "schema_version": "historical_replay_trust.v1",
        "default_mode": "blocked",
        "dates": {
            report_date: {
                "report_date": report_date,
                "mode": "blocked",
                "learning_eligible": False,
                "decision_cutoff": normalized_cutoff,
                "reason_codes": reason_codes,
                "sources": candidate_sources,
            }
        },
        "slices": {},
        "candidate_metadata": {
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "status": "blocked_pending_review",
            "promotion_required": True,
            "source_count": len(candidate_sources),
            "source_origins": source_origins,
            "contamination_findings": findings,
        },
    }
    expected_files[candidate_relative] = _json_bytes(candidate)

    created = False
    if snapshot_dir.exists():
        _verify_existing_snapshot(snapshot_dir, expected_files)
    else:
        temp_dir = snapshot_dir.with_name(f".{snapshot_dir.name}.{uuid.uuid4().hex}.tmp")
        try:
            for relative, content in expected_files.items():
                target = temp_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            try:
                temp_dir.replace(snapshot_dir)
                created = True
            except FileExistsError:
                _verify_existing_snapshot(snapshot_dir, expected_files)
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    audit = audit_replay_entry(
        agent_home,
        report_date,
        manifest_path=candidate_path,
    )
    if not audit["integrity_passed"]:
        raise RuntimeError(f"captured replay snapshot failed integrity audit: {audit['reason_codes']}")
    return {
        "snapshot_id": snapshot_id,
        "snapshot_path": project_relative_path(agent_home, snapshot_dir),
        "manifest_candidate_path": project_relative_path(agent_home, candidate_path),
        "created": created,
        "source_count": len(candidate_sources),
        "contamination_findings": findings,
        "audit": audit,
    }


def _parse_source_arg(value: str) -> dict[str, str]:
    parts = str(value or "").split(":", 2)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("source must use ROLE:KIND:RELATIVE_PATH")
    return {"role": parts[0], "kind": parts[1], "path": parts[2]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze replay decision inputs and emit a blocked trust-manifest candidate.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--decision-cutoff", required=True, help="Timezone-aware ISO-8601 decision cutoff.")
    parser.add_argument(
        "--source",
        action="append",
        type=_parse_source_arg,
        help="Explicit ROLE:KIND:RELATIVE_PATH source; repeat to override standard discovery.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = capture_decision_snapshot(
        resolve_agent_home(args.agent_home),
        args.date,
        args.decision_cutoff,
        sources=args.source,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
