from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from artifact_boundary import assert_refactor_write_allowed, relative_posix
from common import dump_json, resolve_agent_home, resolve_date, timestamp_now


SCHEMA_VERSION = "phase8_completion_audit.v2"
DEFAULT_DATES = ("2026-05-11", "2026-05-14", "2026-05-18", "2026-05-20", "2026-05-21", "2026-05-22")
COMPLETION_PATH = Path("db/phase8/completion_audit.json")
COMPLETION_MD_PATH = Path("db/phase8/completion_audit.md")
LEGACY_SCRIPT_PATHS = (
    "scripts/run_multiagent_research.py",
    "scripts/committee_synthesis.py",
    "scripts/generate_llm_advice.py",
    "scripts/validate_llm_advice.py",
    "scripts/shadow_advice_adapter.py",
)
REQUIRED_PROMOTED_MODE = "action_debate_promoted"
PRODUCTION_CONFIG_PATH = Path("config/production.toml")


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _git_current_branch(agent_home: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=agent_home,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _promoted_date_status(agent_home: Path, report_date: str) -> dict[str, Any]:
    run_path = agent_home / "db" / "phase8" / "promoted_runs" / f"{report_date}.json"
    raw_path = agent_home / "db" / "llm_raw" / f"{report_date}.json"
    validated_path = agent_home / "db" / "validated_advice" / f"{report_date}.json"
    seed_path = agent_home / "db" / "action_seed" / f"{report_date}.json"
    decisions_path = agent_home / "db" / "decisions" / f"{report_date}.json"
    run = _load_json_object(run_path)
    raw = _load_json_object(raw_path)
    validated = _load_json_object(validated_path)
    seed = _load_json_object(seed_path)
    decisions = _load_json_object(decisions_path)
    summary = run.get("summary", {}) if isinstance(run.get("summary"), dict) else {}
    preview_quality = run.get("preview_quality", {}) if isinstance(run.get("preview_quality"), dict) else {}
    official_paths = run.get("official_paths_written", {}) if isinstance(run.get("official_paths_written"), dict) else {}
    required_paths = {
        "committee_advice",
        "committee_decision_bundle",
        "llm_advice",
        "llm_raw",
        "validated_advice",
        "decisions",
    }
    valid = (
        run.get("schema_version") == "promoted_advice_chain.v1"
        and run.get("mode") == REQUIRED_PROMOTED_MODE
        and run.get("official_path_mutation_allowed") is True
        and run.get("native_independent_of_legacy_validated_seed") is True
        and summary.get("promoted_run_passed") is True
        and summary.get("advice_mode") == REQUIRED_PROMOTED_MODE
        and summary.get("decision_source") == REQUIRED_PROMOTED_MODE
        and raw.get("mode") == REQUIRED_PROMOTED_MODE
        and raw.get("decision_source") == REQUIRED_PROMOTED_MODE
        and validated.get("advice_mode") == REQUIRED_PROMOTED_MODE
        and validated.get("decision_source") == REQUIRED_PROMOTED_MODE
        and seed.get("summary", {}).get("native_independent_of_validated_advice") is True
        and bool(decisions.get("decisions"))
        and required_paths.issubset(set(official_paths))
        and not list(preview_quality.get("missing_required_fields", []) or [])
    )
    missing_files = [
        relative
        for relative, path in {
            "promoted_run": run_path,
            "llm_raw": raw_path,
            "validated_advice": validated_path,
            "action_seed": seed_path,
            "decisions": decisions_path,
        }.items()
        if not path.exists()
    ]
    return {
        "report_date": report_date,
        "valid": valid,
        "missing_files": missing_files,
        "run_path": relative_posix(run_path, agent_home),
        "raw_mode": raw.get("mode", ""),
        "validated_mode": validated.get("advice_mode", ""),
        "decision_source": validated.get("decision_source", ""),
        "action_seed_independent": seed.get("summary", {}).get("native_independent_of_validated_advice") is True,
        "decision_count": len(decisions.get("decisions", []) or []),
        "validated_action_count": summary.get("validated_action_count", 0),
        "official_path_keys": sorted(official_paths),
        "preview_quality": preview_quality,
    }


def _legacy_scripts_status(agent_home: Path) -> dict[str, Any]:
    existing = [relative for relative in LEGACY_SCRIPT_PATHS if (agent_home / relative).exists()]
    return {
        "deleted": not existing,
        "existing": existing,
        "required_deleted": list(LEGACY_SCRIPT_PATHS),
    }


def _default_pipeline_status(agent_home: Path) -> dict[str, Any]:
    path = agent_home / "scripts" / "run_daily_pipeline.py"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {
        "path": relative_posix(path, agent_home),
        "uses_promoted_step": "run_promoted_advice_chain.py" in text,
        "legacy_flag_removed": "--legacy-advice-chain" not in text and "legacy_advice_chain" not in text,
        "legacy_step_removed": "run_multiagent_research.py" not in text and "generate_llm_advice.py" not in text and "validate_llm_advice.py" not in text,
    }


def _production_config_status(agent_home: Path) -> dict[str, Any]:
    path = agent_home / PRODUCTION_CONFIG_PATH
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            payload = {}
    advice = payload.get("advice", {}) if isinstance(payload.get("advice"), dict) else {}
    phase8 = payload.get("phase8", {}) if isinstance(payload.get("phase8"), dict) else {}
    compatibility = payload.get("compatibility", {}) if isinstance(payload.get("compatibility"), dict) else {}
    stable_dates = [str(item) for item in phase8.get("stable_observation_dates", []) or []]
    valid = (
        path.exists()
        and advice.get("default_chain") == REQUIRED_PROMOTED_MODE
        and advice.get("default_entrypoint") == "scripts/run_promoted_advice_chain.py"
        and advice.get("official_path_mutation_allowed") is True
        and advice.get("requires_legacy_validated_seed") is False
        and advice.get("legacy_multiagent_chain_enabled") is False
        and advice.get("legacy_committee_chain_enabled") is False
        and advice.get("legacy_validator_chain_enabled") is False
        and phase8.get("promoted_rollout_approved") is True
        and phase8.get("promoted_guardrails") == "scripts/promoted_advice_guardrails.py"
        and compatibility.get("okra_env_required") is False
    )
    return {
        "path": relative_posix(path, agent_home),
        "exists": path.exists(),
        "valid": valid,
        "default_chain": advice.get("default_chain", ""),
        "default_entrypoint": advice.get("default_entrypoint", ""),
        "promoted_rollout_approved": phase8.get("promoted_rollout_approved") is True,
        "okra_env_required": compatibility.get("okra_env_required", None),
        "stable_observation_dates": stable_dates,
    }


def build_completion_audit(
    agent_home: Path,
    report_date: str,
    *,
    dates: list[str],
    generated_at: str | None = None,
    require_main: bool = False,
) -> dict[str, Any]:
    generated_at = generated_at or timestamp_now()
    date_results = [_promoted_date_status(agent_home, item) for item in dates]
    legacy_scripts = _legacy_scripts_status(agent_home)
    default_pipeline = _default_pipeline_status(agent_home)
    production_config = _production_config_status(agent_home)
    current_branch = _git_current_branch(agent_home)
    all_promoted_dates_valid = all(item["valid"] for item in date_results)
    branch_ready = current_branch == "main" if require_main else True
    completion_ready = (
        all_promoted_dates_valid
        and legacy_scripts["deleted"]
        and default_pipeline["uses_promoted_step"]
        and default_pipeline["legacy_flag_removed"]
        and default_pipeline["legacy_step_removed"]
        and production_config["valid"]
        and branch_ready
    )
    remaining: list[str] = []
    if not all_promoted_dates_valid:
        remaining.append("Run and verify promoted official chain for every required observation date.")
    if not legacy_scripts["deleted"]:
        remaining.append("Delete remaining legacy multi-agent/committee/validator scripts.")
    if not (default_pipeline["uses_promoted_step"] and default_pipeline["legacy_flag_removed"] and default_pipeline["legacy_step_removed"]):
        remaining.append("Make promoted chain the only default production advice path.")
    if not production_config["valid"]:
        remaining.append("Commit project production config with promoted chain as the default and no machine-local runtime requirement.")
    if require_main and current_branch != "main":
        remaining.append("Merge the promoted branch into main.")
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": "phase8_completion_audit",
        "artifact_kind": "phase8_completion_audit",
        "generated_at": generated_at,
        "report_date": report_date,
        "write_scope": "shadow_only",
        "non_executable": True,
        "display_only": True,
        "official_path_mutation_allowed": False,
        "current_branch": current_branch,
        "require_main": require_main,
        "summary": {
            "completion_ready": completion_ready,
            "date_count": len(dates),
            "all_promoted_dates_valid": all_promoted_dates_valid,
            "legacy_scripts_deleted": legacy_scripts["deleted"],
            "default_pipeline_promoted_only": default_pipeline["uses_promoted_step"]
            and default_pipeline["legacy_flag_removed"]
            and default_pipeline["legacy_step_removed"],
            "project_production_config_ready": production_config["valid"],
            "main_merge_verified": current_branch == "main",
        },
        "dates": date_results,
        "legacy_scripts": legacy_scripts,
        "default_pipeline": default_pipeline,
        "production_config": production_config,
        "remaining_required": remaining,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Phase 8 Completion Audit",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- report_date: {payload['report_date']}",
        f"- current_branch: {payload['current_branch'] or 'unknown'}",
        "- write_scope: shadow_only",
        "- non_executable: true",
        "- display_only: true",
        f"- official_path_mutation_allowed: {str(payload['official_path_mutation_allowed']).lower()}",
        f"- completion_ready: {str(summary['completion_ready']).lower()}",
        f"- all_promoted_dates_valid: {str(summary['all_promoted_dates_valid']).lower()}",
        f"- legacy_scripts_deleted: {str(summary['legacy_scripts_deleted']).lower()}",
        f"- default_pipeline_promoted_only: {str(summary['default_pipeline_promoted_only']).lower()}",
        f"- project_production_config_ready: {str(summary['project_production_config_ready']).lower()}",
        f"- main_merge_verified: {str(summary['main_merge_verified']).lower()}",
        "",
        "## Promoted Dates",
        "",
        "| Date | Valid | Raw Mode | Validated Mode | Decisions | Missing |",
        "|---|---:|---|---|---:|---|",
    ]
    for item in payload.get("dates", []) or []:
        lines.append(
            f"| {item.get('report_date', '')} | {str(item.get('valid')).lower()} | {item.get('raw_mode', '')} | "
            f"{item.get('validated_mode', '')} | {item.get('decision_count', 0)} | {', '.join(item.get('missing_files', []) or []) or 'none'} |"
        )
    lines.extend(
        [
            "",
            "## Remaining",
            "",
        ]
    )
    remaining = payload.get("remaining_required", []) or []
    if remaining:
        lines.extend(f"- {item}" for item in remaining)
    else:
        lines.append("- none")
    return "\n".join(lines)


def write_completion_audit(agent_home: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    json_path = agent_home / COMPLETION_PATH
    md_path = agent_home / COMPLETION_MD_PATH
    assert_refactor_write_allowed(json_path, payload, agent_home)
    dump_json(json_path, payload)
    markdown_artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": "phase8_completion_audit:markdown",
        "artifact_kind": "phase8_completion_audit_markdown",
        "write_scope": "shadow_only",
        "non_executable": True,
    }
    assert_refactor_write_allowed(md_path, markdown_artifact, agent_home)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(payload), encoding="utf-8", newline="\n")
    return json_path, md_path


def run_builder(
    agent_home: Path,
    report_date: str,
    *,
    dates: list[str] | None = None,
    generated_at: str | None = None,
    require_main: bool = False,
) -> tuple[Path, Path, dict[str, Any]]:
    selected_dates = dates or list(DEFAULT_DATES)
    payload = build_completion_audit(
        agent_home,
        report_date,
        dates=selected_dates,
        generated_at=generated_at,
        require_main=require_main,
    )
    json_path, md_path = write_completion_audit(agent_home, payload)
    return json_path, md_path, payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit whether promoted Phase 8 rollout is complete.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Primary report date in YYYY-MM-DD format.")
    parser.add_argument("--observation-date", action="append", help="Promoted observation date to require. Repeatable.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp.")
    parser.add_argument("--require-main", action="store_true", help="Require current branch to be main.")
    parser.add_argument("--format", choices=["path", "json", "markdown"], default="path")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    dates = [resolve_date(item) for item in args.observation_date] if args.observation_date else list(DEFAULT_DATES)
    json_path, md_path, payload = run_builder(
        agent_home,
        report_date,
        dates=dates,
        generated_at=args.generated_at or None,
        require_main=bool(args.require_main),
    )
    if args.format == "json":
        print(
            json.dumps(
                {
                    "path": relative_posix(json_path, agent_home),
                    "markdown_path": relative_posix(md_path, agent_home),
                    "summary": payload["summary"],
                    "remaining_required": payload["remaining_required"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.format == "markdown":
        print(render_markdown(payload))
    else:
        print(f"{relative_posix(json_path, agent_home)}\n{relative_posix(md_path, agent_home)}")


if __name__ == "__main__":
    main()
