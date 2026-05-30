from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from artifact_boundary import assert_refactor_write_allowed, relative_posix
from common import dump_json, resolve_agent_home, timestamp_now


SCHEMA_VERSION = "hard_constraint_catalog.v1"
INVENTORY_PATH = Path("docs/refactor_runs/2026-05-agent-memory-refactor/hard_constraints_inventory.md")
CATALOG_PATH = Path("db/refactor_shadow_runs/hard_constraint_catalog.json")

GUARDRAIL_RE = re.compile(r"`(guardrail:[^`]+)`")


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_artifacts(agent_home: Path, inventory_path: Path) -> list[dict[str, Any]]:
    return [
        {
            "kind": "hard_constraints_inventory",
            "path": relative_posix(inventory_path, agent_home),
            "content_sha256": content_sha256(inventory_path),
        },
        {
            "kind": "builder",
            "path": "scripts/build_hard_constraint_catalog.py",
            "content_sha256": "",
        },
    ]


def parse_table_rows(markdown: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    in_table = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("| Rule | Location | Inputs | Behavior |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            if rows:
                break
            continue
        if line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 7:
            continue
        guardrail_match = GUARDRAIL_RE.search(cells[5])
        rows.append(
            {
                "rule_id": guardrail_match.group(1) if guardrail_match else f"guardrail:unmapped:{len(rows) + 1:03d}",
                "rule": cells[0],
                "location": cells[1].strip("`"),
                "inputs": cells[2],
                "behavior": cells[3],
                "current_outputs": cells[4],
                "future_guardrail_mapping": cells[5].strip("`"),
                "test_status_or_additions": cells[6],
                "classification": classify_rule(cells[5]),
                "deterministic_owner": deterministic_owner(cells[1]),
                "phase1_mapping_required": True,
            }
        )
    return rows


def classify_rule(mapping_cell: str) -> str:
    text = mapping_cell.lower()
    if ":execution:" in text:
        return "execution_boundary"
    if ":reconciliation:" in text:
        return "reconciliation_boundary"
    if ":state:" in text:
        return "state_integrity"
    if any(token in text for token in (":budget:", ":cash:", ":allocation:", ":concentration:", ":fund:", ":sell:", ":dca:", ":amount:")):
        return "portfolio_guardrail"
    if ":committee:" in text or ":role:" in text:
        return "decision_guardrail"
    return "hard_guardrail"


def deterministic_owner(location: str) -> str:
    normalized = location.replace("`", "")
    normalized = normalized.split(",", 1)[0].strip()
    if normalized.startswith("scripts/"):
        return normalized.split()[0]
    if normalized.startswith("config/"):
        return normalized
    return normalized or "unknown"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_class: dict[str, int] = {}
    owners: dict[str, int] = {}
    missing_test_status = 0
    for row in rows:
        by_class[row["classification"]] = by_class.get(row["classification"], 0) + 1
        owners[row["deterministic_owner"]] = owners.get(row["deterministic_owner"], 0) + 1
        if not str(row.get("test_status_or_additions", "") or "").strip():
            missing_test_status += 1
    return {
        "rule_count": len(rows),
        "classification_counts": by_class,
        "owner_counts": owners,
        "missing_test_status_count": missing_test_status,
        "hard_constraints_remain_deterministic": True,
        "soft_policy_can_block": False,
        "strategy_skill_can_edit_hard_constraints": False,
    }


def build_catalog(agent_home: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    generated_at = generated_at or timestamp_now()
    inventory_path = agent_home / INVENTORY_PATH
    if not inventory_path.exists():
        raise FileNotFoundError(f"hard constraints inventory not found: {inventory_path}")
    rows = parse_table_rows(inventory_path.read_text(encoding="utf-8"))
    if not rows:
        raise ValueError(f"no hard constraint rows parsed from {inventory_path}")
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": "hard_constraint_catalog",
        "artifact_kind": "hard_constraint_catalog",
        "generated_at": generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "source_artifacts": source_artifacts(agent_home, inventory_path),
        "summary": summarize(rows),
        "rules": rows,
        "promotion_boundary": {
            "official_validator_remains_source_of_truth": True,
            "catalog_is_review_only": True,
            "phase8_required_before_behavior_change": True,
        },
    }


def write_catalog(agent_home: Path, payload: dict[str, Any]) -> Path:
    path = agent_home / CATALOG_PATH
    assert_refactor_write_allowed(path, payload, agent_home)
    return dump_json(path, payload)


def run_builder(agent_home: Path, *, generated_at: str | None = None) -> tuple[Path, dict[str, Any]]:
    payload = build_catalog(agent_home, generated_at=generated_at)
    path = write_catalog(agent_home, payload)
    return path, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a shadow-only machine-readable hard constraint catalog.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp for deterministic tests.")
    parser.add_argument("--format", choices=["json", "summary"], default="summary")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    path, payload = run_builder(agent_home, generated_at=args.generated_at or None)
    if args.format == "json":
        print(json.dumps({"path": relative_posix(path, agent_home), "summary": payload["summary"]}, ensure_ascii=False, indent=2))
    else:
        print(f"wrote {payload['summary']['rule_count']} hard constraint catalog rows: {relative_posix(path, agent_home)}")


if __name__ == "__main__":
    main()
