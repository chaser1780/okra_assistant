from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from artifact_boundary import assert_refactor_write_allowed, relative_posix
from common import dump_json, resolve_agent_home, timestamp_now


SCHEMA_VERSION = "phase8_fallback_contract.v1"
CONTRACT_PATH = Path("db/phase8/fallback_contract.json")
DOC_PATH = Path("docs/refactor_runs/2026-05-agent-memory-refactor/phase8_downstream_consumer_map.md")
SWITCH_ENV_VAR = "OKRA_USE_SHADOW_ADVICE_ADAPTER"


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_artifacts(agent_home: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    doc_path = agent_home / DOC_PATH
    if doc_path.exists():
        artifacts.append(
            {
                "kind": "phase8_consumer_map",
                "path": relative_posix(doc_path, agent_home),
                "content_sha256": content_sha256(doc_path),
            }
        )
    artifacts.append({"kind": "builder", "path": "scripts/build_phase8_fallback_contract.py", "content_sha256": ""})
    return artifacts


def build_contract(agent_home: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    generated_at = generated_at or timestamp_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": "phase8:fallback_contract",
        "artifact_kind": "phase8_fallback_contract",
        "generated_at": generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "display_only": True,
        "source_artifacts": source_artifacts(agent_home),
        "fallback_switch": {
            "env_var": SWITCH_ENV_VAR,
            "default_value": "0",
            "enabled_value": "1",
            "current_status": "design_only",
            "active": False,
            "official_path_mutation_allowed": False,
            "legacy_path_default": True,
            "candidate_adapter": "scripts/build_official_advice_compat_preview.py",
            "future_official_entrypoint": "scripts/generate_llm_advice.py::build_final_advice_from_committee_bundle",
        },
        "rollback": {
            "strategy": "environment_switch_revert_before_code_removal",
            "command_draft": f"set {SWITCH_ENV_VAR}=0",
            "powershell_command_draft": f"$env:{SWITCH_ENV_VAR}='0'",
            "files_to_restore_if_promoted_later": [
                "scripts/generate_llm_advice.py",
                "scripts/validate_llm_advice.py",
                "scripts/run_daily_pipeline.py",
                "app/shadow_review_service.py",
            ],
            "delete_shadow_preview_command": "Remove-Item -Recurse -Force db/refactor_shadow_runs/<date>__official_advice_compat_preview",
        },
        "promotion_prerequisites": [
            "preview_contract_valid",
            "official_shape_compatible",
            "official_behavior_comparable",
            "official_adapter_dry_run_passed",
            "source_hash_verified",
            "comparison_to_official.mismatched_count == 0",
            "named_regression_baseline_passed",
            "multi_date_old_new_comparison_passed",
            "explicit_user_promotion_decision",
        ],
        "forbidden_before_promotion": [
            "write db/validated_advice/* from shadow artifacts",
            "route execution sync from shadow artifacts",
            "delete legacy final-advice builder",
            "activate automatic strategy skills",
            "turn adaptive policy into hard block",
        ],
        "summary": {
            "fallback_switch_designed": True,
            "fallback_switch_active": False,
            "rollback_command_documented": True,
            "official_path_mutation_allowed": False,
            "promotion_ready": False,
        },
    }


def write_contract(agent_home: Path, payload: dict[str, Any]) -> Path:
    path = agent_home / CONTRACT_PATH
    assert_refactor_write_allowed(path, payload, agent_home)
    return dump_json(path, payload)


def run_builder(agent_home: Path, *, generated_at: str | None = None) -> tuple[Path, dict[str, Any]]:
    payload = build_contract(agent_home, generated_at=generated_at)
    path = write_contract(agent_home, payload)
    return path, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a shadow-only Phase 8 fallback and rollback contract.")
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
        print(f"wrote Phase 8 fallback contract: {relative_posix(path, agent_home)}")


if __name__ == "__main__":
    main()
