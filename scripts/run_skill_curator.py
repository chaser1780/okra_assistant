from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adaptive_policy_models import AdaptivePolicyStore
from common import load_json, resolve_agent_home, timestamp_now
from strategy_skill_models import SKILL_SCHEMA_VERSION, StrategySkillDocument
from strategy_skill_store import write_registry, write_skill_document
from update_adaptive_policies import policy_store_path


@dataclass(slots=True)
class CuratedSkill:
    skill: StrategySkillDocument
    support_count: int
    contradiction_count: int
    confidence: float
    event_type: str
    notes: str


def slug_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_") or "unknown"


def load_policy_store(agent_home: Path) -> AdaptivePolicyStore:
    path = policy_store_path(agent_home)
    if not path.exists():
        raise FileNotFoundError(f"adaptive policy store not found: {path}")
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"adaptive policy store root is not an object: {path}")
    return AdaptivePolicyStore.from_dict(payload)


def skill_status_for_policy(policy: dict[str, Any]) -> str:
    support = int(policy.get("support_count", 0) or 0)
    status = str(policy.get("status", "") or "")
    if status == "archived":
        return "archived"
    if support >= 2 and status in {"candidate", "active"}:
        return "candidate"
    return "draft"


def skill_name(policy: dict[str, Any]) -> str:
    scope = str(policy.get("scope", "") or "unknown")
    action = str((policy.get("when_to_apply", {}) or {}).get("action_verb", "") or "action")
    return f"{scope.replace(':', ' ').replace('_', ' ').title()} {action.replace('_', ' ').title()} Review"


def skill_id_for_policy(policy: dict[str, Any]) -> str:
    scope = slug_text(policy.get("scope", ""))
    action = slug_text((policy.get("when_to_apply", {}) or {}).get("action_verb", ""))
    return f"skill:{scope}:repeat_{action}_review:v1"


def skill_sections(policy: dict[str, Any]) -> dict[str, str]:
    scope = str(policy.get("scope", "") or "unknown")
    action = str((policy.get("when_to_apply", {}) or {}).get("action_verb", "") or "action")
    return {
        "Purpose": (
            f"Review recurring `{action}` decisions in `{scope}` by turning supported policy/outcome history "
            "into a repeatable checklist. This is learning context only and cannot execute trades."
        ),
        "When To Apply": (
            f"- The action under review is `{action}`.\n"
            f"- The portfolio or fund scope matches `{scope}`.\n"
            "- A current action ticket already passed through hard guardrail evaluation.\n"
            "- The cited adaptive policy and outcome ids are available for audit."
        ),
        "Required Inputs": (
            "- Current action ticket fields: fund, action, amount, bucket, guardrails, and thesis.\n"
            "- Current structured portfolio state and allocation bucket status.\n"
            "- Official NAV or outcome event evidence for the cited historical cases.\n"
            "- Applicable adaptive policy records from `db/strategy_memory/policies.json`."
        ),
        "Procedure": (
            "1. Read structured action-ticket and portfolio facts first.\n"
            "2. Confirm hard guardrails remain authoritative and unchanged.\n"
            "3. Compare the current action with the cited policy/outcome pattern.\n"
            "4. Produce only soft notes: sizing note, confidence delta, wait trigger, or invalidation condition.\n"
            "5. Record the skill id and output in the ticket draft if a future phase selects this skill.\n"
            "6. Send contradictory outcomes back to the learning loop for revision or archive."
        ),
        "Position Sizing Notes": (
            "- This skill cannot increase size beyond validator-approved limits.\n"
            "- Use the cited policy effect only as a soft note unless later explicitly promoted.\n"
            "- If allocation or cash guardrails conflict, hard guardrails win."
        ),
        "Invalidation Conditions": (
            "- The latest official NAV or benchmark outcome contradicts the cited pattern.\n"
            "- Source policy status becomes weakened or archived.\n"
            "- Current action-ticket guardrails block the action.\n"
            "- Required structured inputs are missing or stale."
        ),
        "Anti-Patterns": (
            "- Treating a draft/candidate skill as a trading command.\n"
            "- Using the skill to bypass cash, allocation, sellability, or committee hard rules.\n"
            "- Promoting the skill to active from one isolated outcome.\n"
            "- Replacing structured facts with retrieved narrative text."
        ),
        "Evidence Requirements": (
            "- At least one source adaptive policy id.\n"
            "- At least one source outcome id.\n"
            "- Multiple supportive outcomes or explicit user approval before active use.\n"
            "- Contradictions must be kept in the event log rather than silently deleted."
        ),
        "Known Failure Modes": (
            "- The market regime changes and the historical action pattern stops working.\n"
            "- A policy cluster mixes unrelated funds or buckets.\n"
            "- Outcome scoring is pending or blocked due to missing official data.\n"
            "- Candidate skill context is mistaken for executable advice."
        ),
        "Output Contract": (
            "Allowed outputs:\n\n"
            "- `sizing_note`\n"
            "- `confidence_delta`\n"
            "- `wait_trigger`\n"
            "- `invalidation_condition`\n"
            "- `evidence_requirement_note`\n\n"
            "Forbidden outputs:\n\n"
            "- `hard_block`\n"
            "- `force_trade`\n"
            "- direct portfolio mutation\n"
            "- execution commands"
        ),
    }


def curate_skill_from_policy(policy: dict[str, Any], generated_at: str) -> CuratedSkill | None:
    source_policy_ids = [str(policy.get("policy_id", "") or "")]
    source_outcome_ids = [str(item) for item in list(policy.get("source_outcome_ids", []) or [])]
    if not source_policy_ids[0] or not source_outcome_ids:
        return None
    support_count = int(policy.get("support_count", 0) or 0)
    contradiction_count = int(policy.get("contradiction_count", 0) or 0)
    if support_count <= 0:
        return None

    status = skill_status_for_policy(policy)
    skill = StrategySkillDocument(
        schema_version=SKILL_SCHEMA_VERSION,
        skill_id=skill_id_for_policy(policy),
        name=skill_name(policy),
        status=status,
        version=1,
        scope=str(policy.get("scope", "") or ""),
        created_at=generated_at,
        updated_at=generated_at,
        source_policy_ids=source_policy_ids,
        source_outcome_ids=source_outcome_ids,
        promotion={"min_supported_outcomes": 5, "user_approval_required": True},
        hard_constraints_editable=False,
        default_write_scope="learning_only",
        non_executable=True,
        auto_activation_allowed=False,
        sections=skill_sections(policy),
    )
    if status == "archived":
        event_type = "archived"
    else:
        event_type = "candidate_created" if status == "candidate" else "draft_created"
    return CuratedSkill(
        skill=skill,
        support_count=support_count,
        contradiction_count=contradiction_count,
        confidence=float(policy.get("confidence", 0.0) or 0.0),
        event_type=event_type,
        notes=f"Created {status} strategy skill from adaptive policy {source_policy_ids[0]}.",
    )


def curate_skills(agent_home: Path, *, generated_at: str | None = None) -> list[CuratedSkill]:
    generated_at = generated_at or timestamp_now()
    store = load_policy_store(agent_home)
    curated: list[CuratedSkill] = []
    for policy in store.to_dict().get("policies", []) or []:
        if not isinstance(policy, dict):
            continue
        skill = curate_skill_from_policy(policy, generated_at)
        if skill:
            curated.append(skill)
    return curated


def run_curator(agent_home: Path, *, generated_at: str | None = None) -> tuple[Path, list[Path], list[Path], int]:
    generated_at = generated_at or timestamp_now()
    curated = curate_skills(agent_home, generated_at=generated_at)
    entries = []
    skill_paths: list[Path] = []
    event_paths: list[Path] = []
    appended_count = 0
    for item in curated:
        skill_path, event_path, appended, entry = write_skill_document(
            agent_home,
            item.skill,
            support_count=item.support_count,
            contradiction_count=item.contradiction_count,
            confidence=item.confidence,
            generated_at=generated_at,
            event_type=item.event_type,
            notes=item.notes,
        )
        skill_paths.append(skill_path)
        event_paths.append(event_path)
        appended_count += 1 if appended else 0
        entries.append(entry)
    path = write_registry(agent_home, entries, generated_at=generated_at)
    return path, skill_paths, event_paths, appended_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create non-executable draft/candidate strategy skills from adaptive policies.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp for deterministic tests.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    registry, skill_paths, _event_paths, appended_count = run_curator(agent_home, generated_at=args.generated_at or None)
    print(
        f"wrote strategy skill registry with {len(skill_paths)} skills "
        f"({appended_count} new events): {registry.relative_to(agent_home).as_posix()}"
    )


if __name__ == "__main__":
    main()
