from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import load_json, resolve_agent_home, resolve_date, timestamp_now


SCHEMA_VERSION = "phase8_readiness_audit.v2"
PROMOTED_MODE = "action_debate_promoted"
REQUIRED_CONSUMER_AREAS = {
    "validated_advice",
    "daily_workspace",
    "decision_ledger",
    "review_pages",
    "execution_sync",
    "rag_copilot",
    "workbench_api",
}
LEGACY_SCRIPT_PATHS = (
    "scripts/run_multiagent_research.py",
    "scripts/committee_synthesis.py",
    "scripts/generate_llm_advice.py",
    "scripts/validate_llm_advice.py",
    "scripts/shadow_advice_adapter.py",
)


CONSUMER_MAP: list[dict[str, Any]] = [
    {
        "area": "validated_advice",
        "official_path": "db/validated_advice/<date>.json",
        "producers": [
            "scripts/run_promoted_advice_chain.py",
            "scripts/promoted_advice_guardrails.py::build_validated_payload",
        ],
        "consumers": [
            "scripts/decision_ledger.py::build_decisions_from_validated",
            "scripts/review_advice.py::advice_source_items",
            "scripts/rag_sources.py::collect_validated_advice_documents",
            "scripts/execution_sync.py::match_suggestion",
            "app/ui_support.py::load_state",
            "app/shadow_review_service.py::shadow_review_payload",
            "app/workbench_state.py::build_dashboard_view_model",
        ],
        "required_fields": [
            "report_date",
            "generated_at",
            "decision_mode",
            "degradation_mode",
            "execution_eligible",
            "advice_is_fallback",
            "advice_is_mock",
            "decision_source",
            "market_view",
            "cross_fund_observations",
            "optimization_summary",
            "optimizer_candidates",
            "committee_decision_bundle",
            "tactical_actions",
            "dca_actions",
            "hold_actions",
        ],
        "replacement_risk": "high",
        "compatibility_note": "Promoted action-debate chain now owns the official contract; hard guardrails still enforce executable constraints.",
    },
    {
        "area": "daily_workspace",
        "official_path": "db/daily_workspace/<date>/*",
        "producers": ["scripts/today_orchestrator.py::run_today_analysis"],
        "consumers": ["app/ui_support.py::load_state", "app/web_api_services.py::today_analysis_payload"],
        "required_fields": ["today_decision.json", "today_analysis.json", "today_analysis_meta.json"],
        "replacement_risk": "medium",
        "compatibility_note": "Today workspace remains a consumer of the official promoted advice files.",
    },
    {
        "area": "decision_ledger",
        "official_path": "db/decisions/<date>.json, db/decision_ledger/*.jsonl, db/decision_latest/*.json",
        "producers": ["scripts/decision_ledger.py::build_and_write_decisions"],
        "consumers": ["scripts/build_daily_report.py", "scripts/run_replay_experiment.py", "scripts/update_decision_outcomes.py"],
        "required_fields": ["decision_id", "suggestion_id", "report_date", "fund_code", "validated_action", "validated_amount"],
        "replacement_risk": "high",
        "compatibility_note": "Promoted run status must record that the ledger write surface was touched.",
    },
    {
        "area": "review_pages",
        "official_path": "db/review_results/<date>_T<horizon>.json, reports/daily/*",
        "producers": ["scripts/review_advice.py", "scripts/build_daily_report.py", "scripts/build_nightly_review_report.py"],
        "consumers": ["app/ui_support.py::load_review_results_for_date", "frontend/src/app/pages/ReviewPage.tsx"],
        "required_fields": ["source", "base_date", "review_date", "horizon", "items", "summary"],
        "replacement_risk": "medium",
        "compatibility_note": "Review reads promoted validated advice through the unchanged official shape.",
    },
    {
        "area": "execution_sync",
        "official_path": "db/execution_sync/*, db/execution_status/<date>.json",
        "producers": ["scripts/execution_sync.py::record_actual_trade", "scripts/execution_sync.py::record_conversion"],
        "consumers": ["app/web_api_services.py::ExecutionController", "frontend/src/app/pages/ExecutionPage.tsx"],
        "required_fields": ["linked_suggestion_id", "linked_advice_date", "validated_action", "validated_amount"],
        "replacement_risk": "critical",
        "compatibility_note": "Execution mutation endpoints must reject review/shadow artifacts and accept only official promoted advice references.",
    },
    {
        "area": "rag_copilot",
        "official_path": "db/rag/* plus source collectors",
        "producers": ["scripts/rag_sources.py"],
        "consumers": ["app/rag_answering.py", "app/rag_service.py", "app/copilot_service.py"],
        "required_fields": ["source_kind", "source_path", "source_record_id", "title", "summary", "available_from"],
        "replacement_risk": "medium",
        "compatibility_note": "Retrieval packs stay decision evidence; canonical RAG documents still come from official outputs.",
    },
    {
        "area": "workbench_api",
        "official_path": "GET /api/snapshot, /api/today, /api/research, /api/shadow-review",
        "producers": ["app/web_api.py", "app/web_api_services.py::PageService", "app/shadow_review_service.py"],
        "consumers": ["frontend/src/lib/workbenchApi.ts", "frontend/src/lib/schemas.ts"],
        "required_fields": ["selectedDate", "summary", "dashboard", "research", "review", "executionSync", "todayAnalysis"],
        "replacement_risk": "medium",
        "compatibility_note": "Workbench review surfaces show promoted-chain traces without creating execution controls.",
    },
]


MUTATION_BOUNDARIES = [
    {"path": "/api/execution-sync/trade", "owner": "app/web_api_services.py::ExecutionController.execution_trade", "shadow_allowed": False},
    {"path": "/api/execution-sync/conversion", "owner": "app/web_api_services.py::ExecutionController.execution_conversion", "shadow_allowed": False},
    {"path": "/api/execution-sync/reconcile/apply", "owner": "app/web_api_services.py::ExecutionController.execution_reconcile_apply", "shadow_allowed": False},
    {"path": "scripts/decision_ledger.py::build_and_write_decisions", "owner": "official promoted ledger writer", "shadow_allowed": False},
    {"path": "/api/long-memory/action", "owner": "app/web_api_services.py::PageService.long_memory_action", "shadow_allowed": False},
]


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def _artifact_status(agent_home: Path, relative: str) -> dict[str, Any]:
    path = agent_home / relative
    return {"path": relative, "exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0}


def _promoted_run_status(agent_home: Path, report_date: str) -> dict[str, Any]:
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
    checks = {
        "promoted_status_exists": run_path.exists(),
        "status_schema": run.get("schema_version") == "promoted_advice_chain.v1",
        "status_mode": run.get("mode") == PROMOTED_MODE,
        "official_mutation_allowed": run.get("official_path_mutation_allowed") is True,
        "native_seed": run.get("native_independent_of_legacy_validated_seed") is True,
        "summary_passed": summary.get("promoted_run_passed") is True,
        "raw_mode": raw.get("mode") == PROMOTED_MODE,
        "validated_mode": validated.get("advice_mode") == PROMOTED_MODE,
        "validated_decision_source": validated.get("decision_source") == PROMOTED_MODE,
        "seed_independent": seed.get("summary", {}).get("native_independent_of_validated_advice") is True,
        "decisions_written": bool(decisions.get("decisions")),
        "official_paths_include_decisions": "decisions" in official_paths,
        "preview_has_no_missing_fields": not list(preview_quality.get("missing_required_fields", []) or []),
    }
    return {
        "path": f"db/phase8/promoted_runs/{report_date}.json",
        "valid": all(checks.values()),
        "checks": checks,
        "summary": summary,
        "preview_quality": preview_quality,
        "official_path_keys": sorted(official_paths),
        "decision_count": len(decisions.get("decisions", []) or []),
    }


def _legacy_scripts_status(agent_home: Path) -> dict[str, Any]:
    existing = [relative for relative in LEGACY_SCRIPT_PATHS if (agent_home / relative).exists()]
    return {"valid": not existing, "existing": existing, "required_absent": list(LEGACY_SCRIPT_PATHS)}


def _default_pipeline_status(agent_home: Path) -> dict[str, Any]:
    path = agent_home / "scripts" / "run_daily_pipeline.py"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    checks = {
        "uses_promoted_chain": "run_promoted_advice_chain.py" in text,
        "no_legacy_flag": "--legacy-advice-chain" not in text and "legacy_advice_chain" not in text,
        "no_legacy_steps": "run_multiagent_research.py" not in text and "generate_llm_advice.py" not in text and "validate_llm_advice.py" not in text,
    }
    return {"path": "scripts/run_daily_pipeline.py", "valid": all(checks.values()), "checks": checks}


def _evidence_statuses(agent_home: Path, report_date: str) -> list[dict[str, Any]]:
    promoted = _promoted_run_status(agent_home, report_date)
    legacy_scripts = _legacy_scripts_status(agent_home)
    default_pipeline = _default_pipeline_status(agent_home)
    return [
        {
            "gate_id": "promoted_official_run",
            "status": "ready" if promoted["valid"] else "partial",
            "detail": "Promoted action-debate chain wrote official advice and decision ledger outputs.",
            "evidence": {"promoted_run": promoted},
        },
        {
            "gate_id": "legacy_chain_removed",
            "status": "ready" if legacy_scripts["valid"] else "partial",
            "detail": "Legacy multi-agent, committee, old final-advice, validator, and adapter scripts are absent.",
            "evidence": {"legacy_scripts": legacy_scripts},
        },
        {
            "gate_id": "default_pipeline_promoted_only",
            "status": "ready" if default_pipeline["valid"] else "partial",
            "detail": "Daily pipeline exposes promoted chain as the only advice production path.",
            "evidence": {"default_pipeline": default_pipeline},
        },
        {
            "gate_id": "workbench_old_new_comparison",
            "status": "ready" if (agent_home / "db" / "refactor_reviews" / f"{report_date}.md").exists() else "partial",
            "detail": "Review surface exists for inspecting the promoted chain and its source artifacts.",
        },
        {
            "gate_id": "hard_constraints_mapped",
            "status": "ready" if (agent_home / "scripts" / "promoted_advice_guardrails.py").exists() else "missing",
            "detail": "Hard trading constraints are preserved under promoted_advice_guardrails.py.",
        },
    ]


def build_phase8_audit(
    agent_home: str | Path | None = None,
    report_date: str | None = None,
    *,
    generated_at: str | None = None,
    promotion_approved: bool = False,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    del promotion_approved, environ
    home = resolve_agent_home(str(agent_home) if agent_home is not None else None)
    date_text = resolve_date(report_date)
    evidence = _evidence_statuses(home, date_text)
    blocking = [item["gate_id"] for item in evidence if item.get("status") != "ready"]
    covered_areas = {item["area"] for item in CONSUMER_MAP}
    missing_consumer_areas = sorted(REQUIRED_CONSUMER_AREAS - covered_areas)
    mutation_violations = [item["path"] for item in MUTATION_BOUNDARIES if item.get("shadow_allowed")]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_date": date_text,
        "generated_at": generated_at or timestamp_now(),
        "write_scope": "review_only",
        "non_executable": True,
        "official_path_mutation_allowed": False,
        "promotion_ready": not blocking and not mutation_violations and not missing_consumer_areas,
        "blocking_gates": blocking,
        "missing_consumer_areas": missing_consumer_areas,
        "source_artifacts": [
            _artifact_status(home, f"db/phase8/promoted_runs/{date_text}.json"),
            _artifact_status(home, f"db/validated_advice/{date_text}.json"),
            _artifact_status(home, f"db/llm_raw/{date_text}.json"),
            _artifact_status(home, f"db/action_seed/{date_text}.json"),
            _artifact_status(home, f"db/decisions/{date_text}.json"),
        ],
        "consumer_map": CONSUMER_MAP,
        "mutation_boundaries": MUTATION_BOUNDARIES,
        "required_evidence": evidence,
        "next_safe_step": "Run multi-date promoted stability observation, then merge to main." if not blocking else "Resolve partial promoted rollout gates before merge.",
    }


def render_markdown(audit: dict[str, Any]) -> str:
    lines = [
        f"# Phase 8 Readiness Audit - {audit['report_date']}",
        "",
        f"- schema_version: {audit['schema_version']}",
        f"- generated_at: {audit['generated_at']}",
        f"- non_executable: {str(audit['non_executable']).lower()}",
        f"- official_path_mutation_allowed: {str(audit['official_path_mutation_allowed']).lower()}",
        f"- promotion_ready: {str(audit['promotion_ready']).lower()}",
        f"- blocking_gates: {', '.join(audit['blocking_gates']) or 'none'}",
        "",
        "## Consumer Map",
        "",
        "| Area | Official path | Risk | Compatibility note |",
        "|---|---|---|---|",
    ]
    for item in audit["consumer_map"]:
        lines.append(f"| {item['area']} | `{item['official_path']}` | {item['replacement_risk']} | {item['compatibility_note']} |")
    lines.extend(["", "## Evidence Gates", "", "| Gate | Status | Detail |", "|---|---|---|"])
    for item in audit["required_evidence"]:
        lines.append(f"| {item['gate_id']} | {item['status']} | {item['detail']} |")
    lines.extend(["", f"Next safe step: {audit['next_safe_step']}", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Phase 8 promoted-chain readiness without mutating official paths.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--generated-at", help="Fixed generated_at value for tests.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--promotion-approved", action="store_true", help="Accepted for CLI compatibility; readiness is based on promoted evidence.")
    args = parser.parse_args()
    audit = build_phase8_audit(args.agent_home, args.date, generated_at=args.generated_at, promotion_approved=args.promotion_approved)
    if args.format == "markdown":
        print(render_markdown(audit))
    else:
        print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
