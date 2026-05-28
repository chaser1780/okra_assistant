from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from artifact_boundary import assert_refactor_write_allowed, relative_posix
from common import dump_json, load_json, timestamp_now
from strategy_skill_models import (
    REGISTRY_SCHEMA_VERSION,
    SKILL_EVENT_SCHEMA_VERSION,
    StrategySkillDocument,
    StrategySkillEvent,
    StrategySkillRegistry,
    StrategySkillRegistryEntry,
    StrategySkillValidationError,
    validate_skill_output,
)


MAX_ACTIVE_SKILLS_PER_SCOPE = 5


def strategy_skills_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "strategy_skills"


def registry_path(agent_home: Path) -> Path:
    return strategy_skills_dir(agent_home) / "registry.json"


def safe_skill_slug(skill_id: str) -> str:
    text = str(skill_id or "").strip().lower()
    text = re.sub(r"^skill:", "", text)
    text = re.sub(r"[^a-z0-9_:-]+", "_", text)
    text = text.replace(":", "__")
    return re.sub(r"_+", "_", text).strip("_") or "unknown_skill"


def skill_dir(agent_home: Path, skill_id: str) -> Path:
    return strategy_skills_dir(agent_home) / safe_skill_slug(skill_id)


def skill_markdown_path(agent_home: Path, skill_id: str) -> Path:
    return skill_dir(agent_home, skill_id) / "skill.md"


def skill_event_log_path(agent_home: Path, skill_id: str) -> Path:
    return skill_dir(agent_home, skill_id) / "events.jsonl"


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def load_registry(agent_home: Path) -> StrategySkillRegistry:
    path = registry_path(agent_home)
    if not path.exists():
        return StrategySkillRegistry(
            schema_version=REGISTRY_SCHEMA_VERSION,
            generated_at=timestamp_now(),
            write_scope="learning_only",
            non_executable=True,
            auto_activation_allowed=False,
            entries=[],
            summary={},
        )
    return StrategySkillRegistry.from_dict(load_json_if_exists(path))


def event_exists(path: Path, event_id: str) -> bool:
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("event_id") == event_id:
            return True
    return False


def append_skill_event(agent_home: Path, event: StrategySkillEvent) -> bool:
    path = skill_event_log_path(agent_home, event.skill_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if event_exists(path, event.event_id):
        return False
    payload = event.to_dict()
    assert_refactor_write_allowed(path, payload, agent_home)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return True


def read_skill_events(agent_home: Path, skill_id: str) -> tuple[list[StrategySkillEvent], int]:
    path = skill_event_log_path(agent_home, skill_id)
    if not path.exists():
        return [], 0
    events: list[StrategySkillEvent] = []
    invalid_count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("skill event must be a JSON object")
            events.append(StrategySkillEvent.from_dict(payload))
        except Exception:
            invalid_count += 1
    return events, invalid_count


def registry_entry_from_skill(agent_home: Path, skill: StrategySkillDocument, *, support_count: int, contradiction_count: int, confidence: float) -> StrategySkillRegistryEntry:
    return StrategySkillRegistryEntry(
        skill_id=skill.skill_id,
        name=skill.name,
        status=skill.status,
        version=skill.version,
        scope=skill.scope,
        confidence=confidence,
        support_count=support_count,
        contradiction_count=contradiction_count,
        source_policy_ids=list(skill.source_policy_ids),
        source_outcome_ids=list(skill.source_outcome_ids),
        skill_path=relative_posix(skill_markdown_path(agent_home, skill.skill_id), agent_home),
        event_log_path=relative_posix(skill_event_log_path(agent_home, skill.skill_id), agent_home),
        updated_at=skill.updated_at,
        auto_activation_allowed=skill.auto_activation_allowed,
        non_executable=skill.non_executable,
        write_scope=skill.default_write_scope,
    )


def summarize_entries(entries: list[StrategySkillRegistryEntry], invalid_event_count: int = 0) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for entry in entries:
        status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
    return {
        "skill_count": len(entries),
        "status_counts": status_counts,
        "active_skill_count": status_counts.get("active", 0),
        "auto_active_promotion_count": 0,
        "invalid_event_count": invalid_event_count,
        "non_executable_violation_count": 0,
    }


def write_registry(agent_home: Path, entries: list[StrategySkillRegistryEntry], *, generated_at: str) -> Path:
    entries = sorted(entries, key=lambda item: (item.scope, item.status, item.skill_id))
    registry = StrategySkillRegistry(
        schema_version=REGISTRY_SCHEMA_VERSION,
        generated_at=generated_at,
        write_scope="learning_only",
        non_executable=True,
        auto_activation_allowed=False,
        entries=entries,
        summary=summarize_entries(entries),
    )
    path = registry_path(agent_home)
    payload = registry.to_dict()
    assert_refactor_write_allowed(path, payload, agent_home)
    dump_json(path, payload)
    return path


def write_skill_document(
    agent_home: Path,
    skill: StrategySkillDocument,
    *,
    support_count: int,
    contradiction_count: int,
    confidence: float,
    generated_at: str,
    event_type: str,
    notes: str,
) -> tuple[Path, Path, bool, StrategySkillRegistryEntry]:
    markdown_path = skill_markdown_path(agent_home, skill.skill_id)
    assert_refactor_write_allowed(markdown_path, skill.to_boundary_payload(), agent_home)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(skill.to_markdown(), encoding="utf-8", newline="\n")

    event = StrategySkillEvent(
        event_id=f"skill_event:{skill.skill_id}:{event_type}:{skill.version}",
        skill_id=skill.skill_id,
        schema_version=SKILL_EVENT_SCHEMA_VERSION,
        event_type=event_type,
        event_time=generated_at,
        status_after=skill.status,
        source_policy_ids=list(skill.source_policy_ids),
        source_outcome_ids=list(skill.source_outcome_ids),
        notes=notes,
        write_scope="learning_only",
        non_executable=True,
        audit={"created_by": "scripts/run_skill_curator.py"},
    )
    appended = append_skill_event(agent_home, event)
    entry = registry_entry_from_skill(
        agent_home,
        skill,
        support_count=support_count,
        contradiction_count=contradiction_count,
        confidence=confidence,
    )
    return markdown_path, skill_event_log_path(agent_home, skill.skill_id), appended, entry


def validate_registry_matches_files(agent_home: Path) -> list[str]:
    registry = load_registry(agent_home)
    errors: list[str] = []
    for entry in registry.entries:
        path = agent_home / entry.skill_path
        if not path.exists():
            errors.append(f"missing skill file for {entry.skill_id}: {entry.skill_path}")
            continue
        try:
            skill = StrategySkillDocument.from_markdown(path.read_text(encoding="utf-8"))
        except StrategySkillValidationError as exc:
            errors.append(f"invalid skill Markdown for {entry.skill_id}: {exc}")
            continue
        if skill.skill_id != entry.skill_id:
            errors.append(f"registry skill_id mismatch: {entry.skill_id} != {skill.skill_id}")
        if skill.status != entry.status:
            errors.append(f"registry status mismatch for {entry.skill_id}: {entry.status} != {skill.status}")
        if skill.version != entry.version:
            errors.append(f"registry version mismatch for {entry.skill_id}: {entry.version} != {skill.version}")
        if skill.source_policy_ids != entry.source_policy_ids:
            errors.append(f"registry source_policy_ids mismatch for {entry.skill_id}")
    return errors


def build_default_skill_pack(agent_home: Path) -> dict[str, Any]:
    registry = load_registry(agent_home)
    active_by_scope: dict[str, list[StrategySkillRegistryEntry]] = {}
    candidate_skills: list[dict[str, Any]] = []
    archived_skills: list[str] = []
    for entry in registry.entries:
        if entry.status == "archived":
            archived_skills.append(entry.skill_id)
            continue
        if entry.status == "active":
            active_by_scope.setdefault(entry.scope, []).append(entry)
        elif entry.status == "candidate":
            candidate_skills.append(entry.to_dict())

    active_skills: list[dict[str, Any]] = []
    for entries in active_by_scope.values():
        entries = sorted(entries, key=lambda item: (item.confidence, item.support_count, item.skill_id), reverse=True)
        active_skills.extend(item.to_dict() for item in entries[:MAX_ACTIVE_SKILLS_PER_SCOPE])

    return {
        "schema_version": "strategy_skill_pack.v1",
        "write_scope": "learning_only",
        "non_executable": True,
        "active_skills": active_skills,
        "candidate_skills": sorted(candidate_skills, key=lambda item: item["skill_id"]),
        "archived_skill_ids": sorted(archived_skills),
        "summary": {
            "active_skill_count": len(active_skills),
            "candidate_skill_count": len(candidate_skills),
            "archived_skill_count": len(archived_skills),
            "auto_activation_allowed": False,
        },
    }


def record_skill_output_on_ticket(ticket: dict[str, Any], skill_ref: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    copied = dict(ticket)
    validated_output = validate_skill_output(output)
    copied.setdefault("skill_refs", [])
    copied.setdefault("skill_outputs", [])
    copied["skill_refs"] = [*list(copied.get("skill_refs", []) or []), dict(skill_ref)]
    copied["skill_outputs"] = [*list(copied.get("skill_outputs", []) or []), validated_output]
    return copied
