from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import resolve_agent_home, resolve_date, timestamp_now


SCHEMA_VERSION = "phase8_readiness_audit.v1"

REQUIRED_CONSUMER_AREAS = {
    "validated_advice",
    "daily_workspace",
    "decision_ledger",
    "review_pages",
    "execution_sync",
    "rag_copilot",
    "workbench_api",
}


CONSUMER_MAP: list[dict[str, Any]] = [
    {
        "area": "validated_advice",
        "official_path": "db/validated_advice/<date>.json",
        "producers": [
            "scripts/validate_llm_advice.py::main",
            "scripts/validate_llm_advice.py::build_validated_payload",
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
        "action_fields": [
            "suggestion_id",
            "fund_code",
            "fund_name",
            "validated_action",
            "validated_amount",
            "model_action",
            "confidence",
            "thesis",
            "policy_rule_hits",
            "constraint_hits",
            "validation_notes",
            "execution_status",
        ],
        "replacement_risk": "high",
        "compatibility_note": "Do not replace this file first; it is the broad official consumer contract.",
    },
    {
        "area": "daily_workspace",
        "official_path": "db/daily_workspace/<date>/*",
        "producers": [
            "scripts/today_orchestrator.py::run_today_analysis",
        ],
        "consumers": [
            "app/ui_support.py::load_state",
            "app/web_api_services.py::today_analysis_payload",
            "app/web_api_services.py::system_payload",
            "frontend/src/app/pages/TodayPage.tsx",
            "frontend/src/app/pages/SystemPage.tsx",
        ],
        "required_fields": [
            "today_decision.json",
            "today_analysis.json",
            "today_analysis_meta.json",
            "today_analysis_runtime.json",
            "memory_cycle.json",
            "daily_brief.md",
            "runId",
            "status",
            "currentStep",
            "failedAgents",
            "degradedAgents",
            "resultReady",
        ],
        "replacement_risk": "medium",
        "compatibility_note": "Keep page DTOs stable; action tickets may be linked in review surfaces only.",
    },
    {
        "area": "decision_ledger",
        "official_path": "db/decisions/<date>.json, db/decision_ledger/*.jsonl, db/decision_latest/*.json",
        "producers": [
            "scripts/decision_ledger.py::build_and_write_decisions",
            "scripts/update_decision_outcomes.py::main",
        ],
        "consumers": [
            "scripts/build_daily_report.py",
            "scripts/run_replay_experiment.py",
            "scripts/update_decision_outcomes.py",
            "long memory review cycle inputs",
        ],
        "required_fields": [
            "decision_id",
            "suggestion_id",
            "report_date",
            "fund_code",
            "validated_action",
            "validated_amount",
            "action_section",
            "position_before",
            "constraints",
            "risk_notes",
            "evidence_refs",
            "outcomes",
            "attribution",
        ],
        "replacement_risk": "high",
        "compatibility_note": "Stable suggestion_id and action_section are required for idempotent ledger writes.",
    },
    {
        "area": "review_pages",
        "official_path": "db/review_results/<date>_T<horizon>.json, reports/daily/*",
        "producers": [
            "scripts/review_advice.py",
            "scripts/build_daily_report.py",
            "scripts/build_nightly_review_report.py",
        ],
        "consumers": [
            "app/ui_support.py::load_review_results_for_date",
            "app/workbench_state.py::build_review_view_model",
            "frontend/src/app/pages/ReviewPage.tsx",
        ],
        "required_fields": [
            "source",
            "base_date",
            "review_date",
            "horizon",
            "items",
            "summary",
            "diagnostic_summary",
            "suggestion_id",
        ],
        "replacement_risk": "medium",
        "compatibility_note": "Shadow outcome events can be shown beside review results but must not replace official review history yet.",
    },
    {
        "area": "execution_sync",
        "official_path": "db/execution_sync/*, db/execution_status/<date>.json",
        "producers": [
            "scripts/execution_sync.py::record_actual_trade",
            "scripts/execution_sync.py::record_conversion",
            "scripts/execution_sync.py::apply_reconciliation",
            "scripts/execution_sync.py::update_pending_confirmations",
        ],
        "consumers": [
            "app/web_api_services.py::ExecutionController",
            "app/web_api.py execution-sync endpoints",
            "frontend/src/app/pages/ExecutionPage.tsx",
            "scripts/review_advice.py::execution_source_items",
        ],
        "required_fields": [
            "linked_suggestion_id",
            "linked_advice_date",
            "suggestion_id",
            "validated_action",
            "validated_amount",
            "trade_id",
            "operation_type",
            "execution_deviation",
            "pending",
            "trades",
            "deviations",
            "reconciliationReports",
            "counts",
        ],
        "replacement_risk": "critical",
        "compatibility_note": "Never route shadow artifacts into execution mutation endpoints.",
    },
    {
        "area": "rag_copilot",
        "official_path": "db/rag/* plus source collectors",
        "producers": [
            "scripts/rag_sources.py::collect_validated_advice_documents",
            "scripts/rag_sources.py::collect_committee_bundle_documents",
            "scripts/rag_sources.py::collect_execution_sync_documents",
        ],
        "consumers": [
            "app/rag_answering.py",
            "app/rag_service.py",
            "app/copilot_service.py",
            "frontend/src/components/okra/CopilotPanel.tsx",
        ],
        "required_fields": [
            "source_kind",
            "source_path",
            "source_record_id",
            "title",
            "summary",
            "as_of_date",
            "available_from",
            "domain",
            "source_tier",
            "fund_codes",
            "visibility",
        ],
        "replacement_risk": "medium",
        "compatibility_note": "Retrieval packs can inform shadow debate but cannot become canonical RAG truth without a source adapter.",
    },
    {
        "area": "workbench_api",
        "official_path": "GET /api/snapshot, /api/today, /api/research, /api/shadow-review",
        "producers": [
            "app/web_api.py",
            "app/web_api_services.py::PageService",
            "app/shadow_review_service.py",
        ],
        "consumers": [
            "frontend/src/lib/workbenchApi.ts",
            "frontend/src/lib/schemas.ts",
            "frontend/src/app/routes.tsx",
            "frontend/src/app/pages/ShadowReviewPage.tsx",
        ],
        "required_fields": [
            "selectedDate",
            "summary",
            "dashboard",
            "research",
            "review",
            "executionSync",
            "todayAnalysis",
            "nonExecutable",
            "displayOnly",
            "executionDisabled",
        ],
        "replacement_risk": "medium",
        "compatibility_note": "Keep shadow-review read-only and separate from snapshot fallback synthesis.",
    },
]


MUTATION_BOUNDARIES = [
    {
        "path": "/api/execution-sync/trade",
        "owner": "app/web_api_services.py::ExecutionController.execution_trade",
        "shadow_allowed": False,
    },
    {
        "path": "/api/execution-sync/conversion",
        "owner": "app/web_api_services.py::ExecutionController.execution_conversion",
        "shadow_allowed": False,
    },
    {
        "path": "/api/execution-sync/reconcile/apply",
        "owner": "app/web_api_services.py::ExecutionController.execution_reconcile_apply",
        "shadow_allowed": False,
    },
    {
        "path": "/api/execution-sync/confirmation/update",
        "owner": "app/web_api_services.py::ExecutionController.execution_confirmation_update",
        "shadow_allowed": False,
    },
    {
        "path": "scripts/decision_ledger.py::build_and_write_decisions",
        "owner": "official validated-advice ledger writer",
        "shadow_allowed": False,
    },
    {
        "path": "scripts/update_decision_outcomes.py",
        "owner": "official decision outcome updater",
        "shadow_allowed": False,
    },
    {
        "path": "/api/long-memory/action",
        "owner": "app/web_api_services.py::PageService.long_memory_action",
        "shadow_allowed": False,
    },
]


FIRST_REPLACEMENT_CANDIDATE = {
    "candidate_id": "committee_bundle_to_final_advice_adapter",
    "legacy_layer": "scripts/generate_llm_advice.py::build_final_advice_from_committee_bundle",
    "why_first": (
        "It is downstream of committee/action formation and upstream of official validation. "
        "The current validator, optimizer, ledger, reports, Workbench, and execution sync can stay on the official contract."
    ),
    "must_keep": [
        "committee_decision_bundle/<date>.json",
        "llm_advice/<date>.json",
        "committee_advice/<date>.json",
        "llm_raw.mode in responses_api/mock/committee_fallback",
        "validate_llm_advice.py as official guardrail and ledger writer",
    ],
    "not_first": [
        "db/validated_advice/<date>.json direct replacement",
        "scripts/portfolio_optimizer.py replacement",
        "execution_sync mutation path integration",
        "long-memory promotion from shadow artifacts",
    ],
}


def _artifact_status(agent_home: Path, relative: str) -> dict[str, Any]:
    path = agent_home / relative
    return {"path": relative, "exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0}


def _count_json_array(path: Path, key: str) -> int:
    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    value = payload.get(key, []) if isinstance(payload, dict) else []
    return len(value) if isinstance(value, list) else 0


def _compat_preview_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "refactor_shadow_runs" / f"{report_date}__official_advice_compat_preview" / "official_advice_compat_preview.json"


def _compat_preview_status(agent_home: Path, report_date: str) -> dict[str, Any]:
    path = _compat_preview_path(agent_home, report_date)
    if not path.exists():
        return {
            "path": f"db/refactor_shadow_runs/{report_date}__official_advice_compat_preview/official_advice_compat_preview.json",
            "exists": False,
            "official_compatible_advice": False,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "path": f"db/refactor_shadow_runs/{report_date}__official_advice_compat_preview/official_advice_compat_preview.json",
            "exists": True,
            "official_compatible_advice": False,
            "error": str(exc),
        }
    summary = payload.get("summary", {}) if isinstance(payload, dict) and isinstance(payload.get("summary"), dict) else {}
    return {
        "path": f"db/refactor_shadow_runs/{report_date}__official_advice_compat_preview/official_advice_compat_preview.json",
        "exists": True,
        "official_compatible_advice": bool(summary.get("official_compatible_advice")),
        "committee_bundle_compatible": bool(summary.get("committee_bundle_compatible")),
        "llm_advice_compatible": bool(summary.get("llm_advice_compatible")),
        "official_output_unchanged": bool(summary.get("official_output_unchanged")),
        "fallback_switch_active": bool(summary.get("fallback_switch_active")),
        "missing_required_fields": list(summary.get("missing_required_fields", []) or []),
    }


def _evidence_statuses(agent_home: Path, report_date: str, *, promotion_approved: bool) -> list[dict[str, Any]]:
    action_ticket_path = agent_home / "db" / "action_tickets" / f"{report_date}.json"
    retrieval_path = agent_home / "db" / "retrieval_packs" / f"{report_date}.json"
    debate_path = agent_home / "db" / "action_debates" / f"{report_date}.json"
    review_path = agent_home / "db" / "refactor_reviews" / f"{report_date}.md"
    outcome_count = len(list((agent_home / "db" / "outcome_events").glob(f"{report_date}__*.json")))
    compat_preview = _compat_preview_status(agent_home, report_date)

    shadow_chain_ready = all(path.exists() for path in (action_ticket_path, retrieval_path, debate_path, review_path))
    action_ticket_count = _count_json_array(action_ticket_path, "tickets")
    pack_count = _count_json_array(retrieval_path, "packs")
    debate_count = _count_json_array(debate_path, "debates")

    return [
        {
            "gate_id": "new_chain_official_compatible_advice",
            "status": "ready" if compat_preview["official_compatible_advice"] else ("partial" if shadow_chain_ready else "missing"),
            "detail": "Official-compatible shadow preview exists; fallback switch is still separate." if compat_preview["official_compatible_advice"] else "Shadow chain exists, but no official-compatible adapter preview is available.",
            "evidence": {
                "action_ticket_count": action_ticket_count,
                "retrieval_pack_count": pack_count,
                "debate_count": debate_count,
                "markdown_review_exists": review_path.exists(),
                "compat_preview": compat_preview,
            },
        },
        {
            "gate_id": "workbench_old_new_comparison",
            "status": "ready" if shadow_chain_ready else "missing",
            "detail": "Read-only shadow-review surface exists for same-date old/new comparison.",
        },
        {
            "gate_id": "outcome_examples",
            "status": "partial" if outcome_count else "missing",
            "detail": "One-date outcome evidence is not enough for official replacement.",
            "evidence": {"outcome_file_count_for_date": outcome_count},
        },
        {
            "gate_id": "hard_constraints_mapped",
            "status": "ready" if (Path(__file__).resolve().parents[1] / "docs" / "refactor_runs" / "2026-05-agent-memory-refactor" / "hard_constraints_inventory.md").exists() else "missing",
            "detail": "Hard constraints are documented; official validator still owns enforcement.",
        },
        {
            "gate_id": "regression_baselines",
            "status": "partial",
            "detail": "Recent suites have passed, but Phase 8 needs a named replacement baseline before promotion.",
        },
        {
            "gate_id": "fallback_switch",
            "status": "missing",
            "detail": "No official-path fallback switch has been added yet; preview records only the future switch design.",
        },
        {
            "gate_id": "rollback_path",
            "status": "partial",
            "detail": "Rollback rules are documented; no concrete official replacement rollback command exists yet.",
        },
        {
            "gate_id": "explicit_promotion_decision",
            "status": "ready" if promotion_approved else "missing",
            "detail": "The current user instruction is to continue by document; no explicit official-path promotion was given.",
        },
    ]


def build_phase8_audit(
    agent_home: str | Path | None = None,
    report_date: str | None = None,
    *,
    generated_at: str | None = None,
    promotion_approved: bool = False,
) -> dict[str, Any]:
    home = resolve_agent_home(str(agent_home) if agent_home is not None else None)
    date_text = resolve_date(report_date)
    evidence = _evidence_statuses(home, date_text, promotion_approved=promotion_approved)
    blocking = [item["gate_id"] for item in evidence if item.get("status") != "ready"]
    mutation_violations = [item["path"] for item in MUTATION_BOUNDARIES if item.get("shadow_allowed")]
    covered_areas = {item["area"] for item in CONSUMER_MAP}
    missing_consumer_areas = sorted(REQUIRED_CONSUMER_AREAS - covered_areas)
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
            _artifact_status(home, f"db/validated_advice/{date_text}.json"),
            _artifact_status(home, f"db/action_tickets/{date_text}.json"),
            _artifact_status(home, f"db/retrieval_packs/{date_text}.json"),
            _artifact_status(home, f"db/action_debates/{date_text}.json"),
            _artifact_status(home, f"db/refactor_reviews/{date_text}.md"),
            _artifact_status(home, f"db/refactor_shadow_runs/{date_text}__official_advice_compat_preview/official_advice_compat_preview.json"),
        ],
        "consumer_map": CONSUMER_MAP,
        "mutation_boundaries": MUTATION_BOUNDARIES,
        "first_replacement_candidate": FIRST_REPLACEMENT_CANDIDATE,
        "required_evidence": evidence,
        "next_safe_step": "Add a compatibility adapter and fallback switch design before any official-path mutation.",
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
        "## First Replacement Candidate",
        "",
        f"- candidate_id: {audit['first_replacement_candidate']['candidate_id']}",
        f"- legacy_layer: {audit['first_replacement_candidate']['legacy_layer']}",
        f"- reason: {audit['first_replacement_candidate']['why_first']}",
        "",
        "## Consumer Map",
        "",
        "| Area | Official path | Risk | Compatibility note |",
        "|---|---|---|---|",
    ]
    for item in audit["consumer_map"]:
        lines.append(f"| {item['area']} | `{item['official_path']}` | {item['replacement_risk']} | {item['compatibility_note']} |")
    lines.extend(
        [
            "",
            "## Evidence Gates",
            "",
            "| Gate | Status | Detail |",
            "|---|---|---|",
        ]
    )
    for item in audit["required_evidence"]:
        lines.append(f"| {item['gate_id']} | {item['status']} | {item['detail']} |")
    lines.extend(
        [
            "",
            "## Mutation Boundaries",
            "",
            "| Path | Owner | Shadow allowed |",
            "|---|---|---|",
        ]
    )
    for item in audit["mutation_boundaries"]:
        lines.append(f"| `{item['path']}` | {item['owner']} | {str(item['shadow_allowed']).lower()} |")
    lines.extend(["", f"Next safe step: {audit['next_safe_step']}", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Phase 8 legacy-chain replacement readiness without mutating official paths.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--generated-at", help="Fixed generated_at value for tests.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--promotion-approved", action="store_true", help="Record an explicit official-path promotion decision.")
    args = parser.parse_args()

    audit = build_phase8_audit(
        args.agent_home,
        args.date,
        generated_at=args.generated_at,
        promotion_approved=args.promotion_approved,
    )
    if args.format == "markdown":
        print(render_markdown(audit))
    else:
        print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
