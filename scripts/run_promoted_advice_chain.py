from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from action_debate_graph import run_debate_graph
from build_action_ticket_shadow import run_builder as run_action_ticket_builder
from build_layered_retrieval_pack import run_builder as run_retrieval_pack_builder
from build_official_advice_compat_preview import build_preview_payload
from capture_replay_snapshot import capture_decision_snapshot
from common import (
    committee_advice_path,
    committee_decision_bundle_path,
    decision_ledger_path,
    decision_latest_path,
    decisions_path,
    dump_json,
    ensure_layout,
    llm_advice_path,
    llm_raw_path,
    load_json,
    load_llm_config,
    project_relative_path,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
    validated_advice_path,
)
from decision_ledger import build_and_write_decisions
from promoted_advice_guardrails import build_validated_payload


PROMOTED_MODE = "action_debate_promoted"
MOCK_MODE = "action_debate_mock"
SCHEMA_VERSION = "promoted_advice_chain.v1"


def run_status_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "phase8" / "promoted_runs" / f"{report_date}.json"


def _section_count(payload: dict[str, Any]) -> int:
    return sum(len(payload.get(section, []) or []) for section in ("tactical_actions", "dca_actions", "hold_actions"))


def write_official_outputs(
    agent_home: Path,
    report_date: str,
    *,
    preview: dict[str, Any],
    generated_at: str,
    is_mock: bool,
    llm_model: str,
) -> dict[str, Path]:
    advice = dict(preview["final_advice_preview"])
    committee_bundle = dict(preview["committee_decision_bundle_preview"])
    mode = MOCK_MODE if is_mock else PROMOTED_MODE
    decision_source = "action_debate_mock" if is_mock else "action_debate_promoted"
    committee_bundle.update(
        {
            "decision_source": decision_source,
            "is_mock": is_mock,
            "llm_model": llm_model,
            "execution_eligible": False if is_mock else bool(committee_bundle.get("execution_eligible", True)),
        }
    )
    raw_payload = {
        "mode": mode,
        "decision_source": decision_source,
        "narrative_mode": mode,
        "generated_at": generated_at,
        "is_mock": is_mock,
        "llm_model": llm_model,
        "advice": advice,
        "committee": {
            "decision_source": decision_source,
            "committee_confidence": committee_bundle.get("committee_confidence", "promoted"),
            "risk_vetoes": committee_bundle.get("risk_vetoes", []),
        },
        "committee_decision_bundle": committee_bundle,
        "promoted_chain": {
            "schema_version": SCHEMA_VERSION,
            "source_preview_artifact_id": preview.get("artifact_id", ""),
            "native_independent_of_legacy_validated_seed": True,
            "official_path_mutation_allowed": True,
            "is_mock": is_mock,
            "production_eligible": not is_mock,
            "llm_model": llm_model,
        },
        "aggregate_all_agents_ok": True,
        "aggregate_degraded_ok": False,
        "failed_agents": [],
    }
    paths = {
        "committee_advice": dump_json(committee_advice_path(agent_home, report_date), advice),
        "llm_raw": dump_json(llm_raw_path(agent_home, report_date), raw_payload),
        "llm_advice": dump_json(llm_advice_path(agent_home, report_date), advice),
        "committee_decision_bundle": dump_json(committee_decision_bundle_path(agent_home, report_date), committee_bundle),
    }
    validated = build_validated_payload(
        agent_home,
        report_date,
        advice=advice,
        llm_raw=raw_payload,
        committee_bundle=committee_bundle,
    )
    paths["validated_advice"] = dump_json(validated_advice_path(agent_home, report_date), validated)
    decisions = build_and_write_decisions(agent_home, report_date)
    paths["decisions"] = decisions_path(agent_home, report_date)
    for decision in decisions.get("decisions", []) or []:
        fund_code = str(decision.get("fund_code", "") or "")
        if not fund_code:
            continue
        paths[f"decision_latest:{fund_code}"] = decision_latest_path(agent_home, fund_code)
        paths[f"decision_ledger:{fund_code}"] = decision_ledger_path(agent_home, fund_code)
    return paths


def build_status_payload(
    agent_home: Path,
    report_date: str,
    *,
    generated_at: str,
    preview: dict[str, Any],
    paths: dict[str, Path],
    replay_snapshot_capture: dict[str, Any],
    debate_mode: str,
    llm_model: str,
    is_mock: bool,
) -> dict[str, Any]:
    validated = load_json(validated_advice_path(agent_home, report_date))
    preview_summary = preview.get("summary", {}) if isinstance(preview.get("summary"), dict) else {}
    preview_quality = {
        "official_shape_compatible": bool(preview_summary.get("official_shape_compatible")),
        "official_behavior_comparable": bool(preview_summary.get("official_behavior_comparable")),
        "official_adapter_dry_run_passed": bool(preview_summary.get("official_adapter_dry_run_passed")),
        "source_hash_verified": bool(preview_summary.get("source_hash_verified")),
        "missing_required_fields": list(preview_summary.get("missing_required_fields", []) or []),
        "historical_replay_comparable": bool(preview_summary.get("historical_replay_comparable")),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"promoted_advice_chain:{report_date}",
        "artifact_kind": "promoted_advice_chain_run",
        "report_date": report_date,
        "generated_at": generated_at,
        "status": "ok",
        "mode": MOCK_MODE if is_mock else PROMOTED_MODE,
        "debate_mode": debate_mode,
        "llm_model": llm_model,
        "is_mock": is_mock,
        "production_eligible": not is_mock,
        "official_path_mutation_allowed": True,
        "native_independent_of_legacy_validated_seed": True,
        "source_preview_artifact_id": preview.get("artifact_id", ""),
        "official_paths_written": {
            name: path.resolve().relative_to(agent_home.resolve()).as_posix()
            for name, path in sorted(paths.items())
        },
        "official_path_count": len(paths),
        "replay_snapshot_capture": replay_snapshot_capture,
        "preview_quality": preview_quality,
        "summary": {
            "promoted_run_passed": True,
            "validated_action_count": _section_count(validated),
            "tactical_action_count": len(validated.get("tactical_actions", []) or []),
            "dca_action_count": len(validated.get("dca_actions", []) or []),
            "hold_action_count": len(validated.get("hold_actions", []) or []),
            "advice_mode": validated.get("advice_mode", ""),
            "decision_source": validated.get("decision_source", ""),
            "execution_eligible": bool(validated.get("execution_eligible")),
            "is_mock": bool(validated.get("advice_is_mock")),
        },
    }


def run_chain(
    agent_home: Path,
    report_date: str,
    *,
    generated_at: str | None = None,
    use_rag: bool = False,
    debate_mode: str = "llm",
) -> tuple[Path, dict[str, Any]]:
    generated_at = generated_at or timestamp_now()
    is_mock = debate_mode != "llm"
    llm_model = str(load_llm_config(agent_home).get("model", "") or "")
    ensure_layout(agent_home)
    (agent_home / "db" / "action_seed").mkdir(parents=True, exist_ok=True)
    run_action_ticket_builder(agent_home, report_date, generated_at=generated_at, source_mode="native")
    run_retrieval_pack_builder(agent_home, report_date, generated_at=generated_at, source_mode="native", use_rag=use_rag)
    _debate_path, debate_artifact = run_debate_graph(agent_home, report_date, generated_at=generated_at, debate_mode=debate_mode)
    if debate_mode == "llm" and debate_artifact.get("summary", {}).get("status") != "ok":
        raise RuntimeError("promoted advice chain requires successful LLM debate graph before official outputs are written")
    preview = build_preview_payload(
        agent_home,
        report_date,
        generated_at=generated_at,
        promoted_run=True,
        is_mock=is_mock,
    )
    paths = write_official_outputs(
        agent_home,
        report_date,
        preview=preview,
        generated_at=generated_at,
        is_mock=is_mock,
        llm_model=llm_model,
    )
    try:
        capture = capture_decision_snapshot(agent_home, report_date, generated_at)
        replay_snapshot_capture = {
            "status": "captured",
            "snapshot_id": capture["snapshot_id"],
            "snapshot_path": capture["snapshot_path"],
            "manifest_candidate_path": capture["manifest_candidate_path"],
            "created": capture["created"],
            "source_count": capture["source_count"],
            "contamination_finding_count": len(capture["contamination_findings"]),
            "learning_eligible": False,
        }
    except Exception as exc:
        replay_snapshot_capture = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "learning_eligible": False,
        }
    status = build_status_payload(
        agent_home,
        report_date,
        generated_at=generated_at,
        preview=preview,
        paths=paths,
        replay_snapshot_capture=replay_snapshot_capture,
        debate_mode=debate_mode,
        llm_model=llm_model,
        is_mock=is_mock,
    )
    path = dump_json(run_status_path(agent_home, report_date), status)
    return path, status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run promoted action-ticket/retrieval/debate chain and write official advice contracts.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp.")
    parser.add_argument("--use-rag", action="store_true", help="Use non-canonical RAG evidence inside retrieval packs.")
    parser.add_argument("--llm-mock", action="store_true", help="Use deterministic debate nodes instead of live LLM debate calls.")
    parser.add_argument("--format", choices=["path", "json"], default="path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    path, payload = run_chain(agent_home, report_date, generated_at=args.generated_at or None, use_rag=args.use_rag, debate_mode="deterministic" if args.llm_mock else "llm")
    if args.format == "json":
        print(json.dumps({"path": project_relative_path(agent_home, path), "summary": payload["summary"]}, ensure_ascii=False, indent=2))
    else:
        print(project_relative_path(agent_home, path))


if __name__ == "__main__":
    main()
