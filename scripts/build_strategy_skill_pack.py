from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from artifact_boundary import assert_refactor_write_allowed, relative_posix
from common import dump_json, load_json, resolve_agent_home, resolve_date, timestamp_now
from strategy_skill_store import (
    SKILL_PACK_SCHEMA_VERSION,
    SKILL_USAGE_SCHEMA_VERSION,
    build_default_skill_pack,
    registry_path,
    skill_pack_path,
    skill_usage_path,
    write_skill_pack,
)


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def source_artifacts(agent_home: Path, paths: list[Path]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        artifacts.append(
            {
                "kind": path.parent.name,
                "path": relative_posix(path, agent_home),
                "content_sha256": content_sha256(path),
            }
        )
    artifacts.append({"kind": "builder", "path": "scripts/build_strategy_skill_pack.py", "content_sha256": ""})
    return artifacts


def tickets_for_date(agent_home: Path, report_date: str) -> list[dict[str, Any]]:
    payload = load_json_if_exists(agent_home / "db" / "action_tickets" / f"{report_date}.json")
    return [item for item in payload.get("tickets", []) or [] if isinstance(item, dict)]


def scope_matches_ticket(skill: dict[str, Any], ticket: dict[str, Any]) -> bool:
    scope = str(skill.get("scope", "") or "")
    if scope.startswith("fund:"):
        return scope.split(":", 1)[1] == str(ticket.get("fund_code", "") or "").lower()
    bucket = str(ticket.get("portfolio_bucket", "") or "").strip().lower()
    if scope.startswith("portfolio:") and bucket:
        return scope.split(":", 1)[1] == bucket.replace(" ", "_")
    role = str(ticket.get("role", "") or "").strip().lower()
    if scope.startswith("portfolio_role:") and role:
        return scope.split(":", 1)[1] == role.replace(" ", "_")
    return False


def action_matches_skill(skill: dict[str, Any], ticket: dict[str, Any]) -> bool:
    skill_id = str(skill.get("skill_id", "") or "")
    action = str(ticket.get("action_verb", "") or "")
    return f"repeat_{action}_" in skill_id or f"repeat_{action}:" in skill_id


def usage_candidate(skill: dict[str, Any], ticket: dict[str, Any]) -> dict[str, Any] | None:
    if str(skill.get("status", "") or "") not in {"candidate", "active", "strengthened", "revised"}:
        return None
    if not action_matches_skill(skill, ticket):
        return None
    if not scope_matches_ticket(skill, ticket):
        return None
    return {
        "ticket_id": str(ticket.get("ticket_id", "") or ""),
        "fund_code": str(ticket.get("fund_code", "") or ""),
        "action_verb": str(ticket.get("action_verb", "") or ""),
        "skill_ref": {
            "skill_id": str(skill.get("skill_id", "") or ""),
            "status": str(skill.get("status", "") or ""),
            "scope": str(skill.get("scope", "") or ""),
            "confidence": skill.get("confidence", 0.0),
            "non_executable": True,
        },
        "recommended_outputs": [
            {
                "skill_id": str(skill.get("skill_id", "") or ""),
                "output_type": "evidence_requirement_note",
                "value": "Review cited policy/outcome evidence before repeating this action pattern.",
                "non_executable": True,
            }
        ],
        "usage_status": "candidate_match",
        "applied_to_ticket_file": False,
        "write_scope": "learning_only",
        "non_executable": True,
    }


def build_usage_artifact(agent_home: Path, report_date: str, pack: dict[str, Any], *, generated_at: str | None = None) -> dict[str, Any]:
    generated_at = generated_at or timestamp_now()
    tickets = tickets_for_date(agent_home, report_date)
    skills = list(pack.get("active_skills", []) or []) + list(pack.get("candidate_skills", []) or [])
    usage: list[dict[str, Any]] = []
    for ticket in tickets:
        for skill in skills:
            if not isinstance(skill, dict):
                continue
            candidate = usage_candidate(skill, ticket)
            if candidate:
                usage.append(candidate)
    sources = [
        registry_path(agent_home),
        skill_pack_path(agent_home),
        agent_home / "db" / "action_tickets" / f"{report_date}.json",
    ]
    return {
        "schema_version": SKILL_USAGE_SCHEMA_VERSION,
        "artifact_id": f"strategy_skill_usage:{report_date}",
        "artifact_kind": "strategy_skill_usage",
        "report_date": report_date,
        "generated_at": generated_at,
        "write_scope": "learning_only",
        "non_executable": True,
        "source_artifacts": source_artifacts(agent_home, sources),
        "usage": usage,
        "summary": {
            "ticket_count": len(tickets),
            "skill_count": len(skills),
            "usage_candidate_count": len(usage),
            "applied_to_ticket_file_count": 0,
            "auto_activation_allowed": False,
            "official_path_mutation_allowed": False,
        },
    }


def write_usage_artifact(agent_home: Path, payload: dict[str, Any]) -> Path:
    path = skill_usage_path(agent_home, str(payload.get("report_date", "") or "unknown"))
    assert_refactor_write_allowed(path, payload, agent_home)
    dump_json(path, payload)
    return path


def build_skill_pack(agent_home: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    generated_at = generated_at or timestamp_now()
    pack = build_default_skill_pack(agent_home)
    pack["artifact_id"] = "strategy_skill_pack:default"
    pack["artifact_kind"] = "strategy_skill_pack"
    pack["generated_at"] = generated_at
    pack["source_artifacts"] = source_artifacts(agent_home, [registry_path(agent_home)])
    pack["selection_policy"] = {
        "active_statuses": ["active", "strengthened", "revised"],
        "candidate_statuses": ["candidate"],
        "archived_excluded": True,
        "max_active_skills_per_scope": 5,
        "writes_action_tickets": False,
    }
    return pack


def run_builder(agent_home: Path, report_date: str | None = None, *, generated_at: str | None = None) -> tuple[Path, Path | None, dict[str, Any], dict[str, Any] | None]:
    generated_at = generated_at or timestamp_now()
    pack = build_skill_pack(agent_home, generated_at=generated_at)
    pack_path = write_skill_pack(agent_home, pack)
    if not report_date:
        return pack_path, None, pack, None
    usage = build_usage_artifact(agent_home, report_date, pack, generated_at=generated_at)
    usage_path = write_usage_artifact(agent_home, usage)
    return pack_path, usage_path, pack, usage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build non-executable strategy skill pack and optional ticket usage candidates.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date for optional usage candidates.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp for deterministic tests.")
    parser.add_argument("--format", choices=["json", "summary"], default="summary")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date) if args.date else None
    pack_path, usage_path, pack, usage = run_builder(agent_home, report_date, generated_at=args.generated_at or None)
    summary = {
        "skill_pack_path": relative_posix(pack_path, agent_home),
        "usage_path": relative_posix(usage_path, agent_home) if usage_path else "",
        "pack_summary": pack.get("summary", {}),
        "usage_summary": (usage or {}).get("summary", {}),
    }
    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"wrote strategy skill pack: {summary['skill_pack_path']}")
        if usage_path:
            print(f"wrote strategy skill usage: {summary['usage_path']}")


if __name__ == "__main__":
    main()
