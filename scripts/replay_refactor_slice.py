from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from artifact_boundary import BoundaryCheck, assert_refactor_write_allowed, find_forbidden_write_paths, relative_posix


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLICE_ID = "2026-05-22__017641__scheduled_dca"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_dir(slice_id: str, fixture_root: Path | None = None) -> Path:
    root = fixture_root or PROJECT_ROOT / "tests" / "fixtures" / "golden_slices"
    return root / slice_id


def default_output_dir(slice_id: str) -> Path:
    return PROJECT_ROOT / "db" / "refactor_shadow_runs" / slice_id


def load_slice_inputs(slice_id: str, fixture_root: Path | None = None) -> dict[str, Any]:
    base = fixture_dir(slice_id, fixture_root)
    input_dir = base / "input"
    files = {
        "slice": input_dir / "slice.json",
        "validated_advice": input_dir / "validated_advice.json",
        "portfolio_state": input_dir / "portfolio_state.json",
        "context_evidence": input_dir / "context_evidence.json",
        "official_nav_benchmark": input_dir / "official_nav_benchmark.json",
    }
    payload = {name: load_json(path) for name, path in files.items()}
    payload["_paths"] = files
    payload["_fixture_dir"] = base
    return payload


def source_artifacts(inputs: dict[str, Any]) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for name in ("validated_advice", "portfolio_state", "context_evidence", "official_nav_benchmark"):
        path = inputs["_paths"][name]
        artifacts.append(
            {
                "kind": name,
                "path": relative_posix(path),
                "content_sha256": content_sha256(path),
            }
        )
    return artifacts


def select_legacy_action(validated: dict[str, Any], fund_code: str, action_verb: str) -> dict[str, Any]:
    for bucket in ("dca_actions", "tactical_actions", "hold_actions", "selected_actions"):
        for item in validated.get(bucket, []) or []:
            if item.get("fund_code") == fund_code and item.get("validated_action") == action_verb:
                selected = dict(item)
                selected["_source_bucket"] = bucket
                return selected
    raise ValueError(f"cannot find action {fund_code}/{action_verb} in validated advice fixture")


def select_position(portfolio_state: dict[str, Any], fund_code: str) -> dict[str, Any]:
    for item in portfolio_state.get("funds", []) or []:
        if item.get("fund_code") == fund_code:
            return dict(item)
    raise ValueError(f"cannot find fund {fund_code} in portfolio fixture")


def pct(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 6)


def build_action_ticket(inputs: dict[str, Any]) -> dict[str, Any]:
    meta = inputs["slice"]
    validated = inputs["validated_advice"]
    portfolio = inputs["portfolio_state"]
    context = inputs["context_evidence"]
    fund_code = meta["fund_code"]
    action_verb = meta["action_verb"]
    action = select_legacy_action(validated, fund_code, action_verb)
    position = select_position(portfolio, fund_code)
    total_value = float(portfolio.get("total_value") or 0.0)
    current_value = float(position.get("current_value") or 0.0)
    amount = float(action.get("validated_amount") or 0.0)
    ticket_id = f"ticket:{meta['report_date']}:{fund_code}:{action_verb}:001"
    generated_at = meta["generated_at"]
    guardrails = [
        {
            "rule_id": "shadow_non_executable",
            "result": "pass",
            "reason": "Phase 0.5 artifacts are display-only and cannot be sent to execution.",
        },
        {
            "rule_id": "hold_only_execution_gate",
            "result": "pass",
            "reason": "decision_mode=hold_only is preserved as source context, but ticket generation remains allowed because the ticket is non-executable.",
        },
        {
            "rule_id": "core_dca_fixed_only",
            "result": "not_checked",
            "reason": "User confirmed the DCA-only hard restriction is removed for new action tickets; keep the old rule only as historical context.",
        },
    ]
    ticket = {
        "ticket_id": ticket_id,
        "schema_version": "action_ticket.v1",
        "report_date": meta["report_date"],
        "generated_at": generated_at,
        "fund_code": fund_code,
        "fund_name": action.get("fund_name") or position.get("fund_name", ""),
        "role": position.get("role", ""),
        "category": context.get("target", {}).get("category", ""),
        "portfolio_bucket": action.get("strategy_bucket") or position.get("strategy_bucket", ""),
        "action_verb": action_verb,
        "execution_mode": "scheduled",
        "ticket_status": "shadow_only",
        "decision_kind": "core_dca_action",
        "non_executable": True,
        "write_scope": "shadow_only",
        "amount_currency": "CNY",
        "requested_amount": amount,
        "validated_amount": amount,
        "size_bucket": "fixed_daily_buy",
        "percent_of_position": pct(amount, current_value),
        "percent_of_portfolio": pct(amount, total_value),
        "confidence": float(action.get("confidence") or 0.0),
        "confidence_reason": "Source advice was degraded/mock and assigned zero confidence; Phase 0.5 preserves that value instead of inventing confidence.",
        "thesis": action.get("thesis", ""),
        "hard_guardrail_results": guardrails,
        "soft_policy_adjustments": [
            {
                "policy_id": "legacy_context:core_dca_fixed_only",
                "effect_type": "note",
                "effect_value": "retained_as_context_not_hard_block",
                "reason": context.get("policy_context", {}).get("user_override", ""),
            }
        ],
        "supporting_evidence_refs": [
            {
                "ref_id": f"validated:{meta['report_date']}:{fund_code}:{action_verb}",
                "source_kind": "validated_advice",
                "source_path": "input/validated_advice.json",
                "source_record_id": action.get("suggestion_id", ""),
                "as_of_date": meta["report_date"],
                "available_from": generated_at,
                "summary": f"Validated action {action_verb} for CNY {amount:.2f}.",
            },
            {
                "ref_id": f"portfolio:{meta['report_date']}:{fund_code}:position",
                "source_kind": "portfolio_state",
                "source_path": "input/portfolio_state.json",
                "source_record_id": fund_code,
                "as_of_date": portfolio.get("as_of_date", meta["report_date"]),
                "available_from": portfolio.get("updated_at", generated_at),
                "summary": f"Current value CNY {current_value:.2f}; fixed_daily_buy_amount CNY {float(position.get('fixed_daily_buy_amount') or 0.0):.2f}.",
            },
        ],
        "opposing_evidence_refs": [
            {
                "ref_id": "committee:hold_only:execution_ineligible",
                "source_kind": "committee_decision_bundle",
                "source_path": "input/validated_advice.json",
                "source_record_id": f"committee:{fund_code}",
                "as_of_date": meta["report_date"],
                "available_from": generated_at,
                "summary": "Committee bundle was hold_only and execution_eligible=false; this is audit context, not a shadow ticket blocker.",
            }
        ],
        "invalidation_conditions": [
            "User disables the scheduled DCA plan.",
            "The fund becomes unavailable for purchase before execution.",
            "Cash allocation policy changes before this ticket is promoted beyond shadow review.",
        ],
        "source_artifacts": source_artifacts(inputs),
        "legacy_mapping": {
            "suggestion_id": action.get("suggestion_id", ""),
            "source_bucket": action.get("_source_bucket", ""),
            "model_action": action.get("model_action", ""),
            "validated_action": action.get("validated_action", ""),
            "execution_status": action.get("execution_status", ""),
        },
        "audit": {
            "builder": "scripts/replay_refactor_slice.py",
            "slice_id": meta["slice_id"],
        },
    }
    artifact = {
        "schema_version": "action_ticket.v1",
        "artifact_id": f"action_tickets:{meta['slice_id']}",
        "artifact_kind": "action_ticket_shadow",
        "report_date": meta["report_date"],
        "generated_at": generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "source_artifacts": source_artifacts(inputs),
        "summary": {
            "ticket_count": 1,
            "action_count": 1,
            "hold_ticket_count": 0,
            "blocked_count": 0,
            "degraded_count": 0,
            "official_advice_unchanged": True,
        },
        "tickets": [ticket],
    }
    return artifact


def build_retrieval_pack(inputs: dict[str, Any], action_ticket: dict[str, Any]) -> dict[str, Any]:
    meta = inputs["slice"]
    portfolio = inputs["portfolio_state"]
    context = inputs["context_evidence"]
    nav = inputs["official_nav_benchmark"]
    ticket = action_ticket["tickets"][0]
    position = select_position(portfolio, meta["fund_code"])
    target = {
        "fund_code": meta["fund_code"],
        "fund_name": ticket["fund_name"],
        "role": position.get("role", ""),
        "category": context.get("target", {}).get("category", ""),
        "portfolio_bucket": ticket.get("portfolio_bucket", ""),
    }
    pack = {
        "schema_version": "retrieval_pack.v1",
        "pack_id": f"pack:{meta['report_date']}:{meta['fund_code']}:{meta['action_verb']}:001",
        "report_date": meta["report_date"],
        "generated_at": meta["generated_at"],
        "decision_cutoff": meta["decision_cutoff"],
        "write_scope": "shadow_only",
        "non_executable": True,
        "target": target,
        "visibility": {
            "include_execution": False,
            "include_private_position_details": True,
            "reason": "Phase 0.5 reads strategy and portfolio fixtures only; execution sync is excluded.",
        },
        "source_manifests": source_artifacts(inputs),
        "canonical_facts": [
            {
                "fact_id": f"fact:portfolio:{meta['fund_code']}:position",
                "layer": "canonical_fact",
                "domain": "portfolio",
                "source_kind": "portfolio_state",
                "source_path": "input/portfolio_state.json",
                "source_record_id": meta["fund_code"],
                "as_of_date": portfolio.get("as_of_date", meta["report_date"]),
                "available_from": portfolio.get("updated_at", meta["generated_at"]),
                "status": "present",
                "value": {
                    "current_value": position.get("current_value"),
                    "holding_units": position.get("holding_units"),
                    "cost_basis_value": position.get("cost_basis_value"),
                    "portfolio_total_value": portfolio.get("total_value"),
                    "fixed_daily_buy_amount": position.get("fixed_daily_buy_amount"),
                },
                "trust_level": "structured_fixture",
            },
            {
                "fact_id": f"fact:validated:{meta['fund_code']}:{meta['action_verb']}",
                "layer": "canonical_fact",
                "domain": "decision",
                "source_kind": "validated_advice",
                "source_path": "input/validated_advice.json",
                "source_record_id": ticket["legacy_mapping"]["suggestion_id"],
                "as_of_date": meta["report_date"],
                "available_from": meta["generated_at"],
                "status": "present",
                "value": {
                    "action_verb": ticket["action_verb"],
                    "validated_amount": ticket["validated_amount"],
                    "execution_mode": ticket["execution_mode"],
                    "decision_mode": inputs["validated_advice"].get("decision_mode", ""),
                    "execution_eligible": inputs["validated_advice"].get("execution_eligible"),
                },
                "trust_level": "validated_fixture",
            },
            {
                "fact_id": f"fact:nav:{meta['fund_code']}:start",
                "layer": "canonical_fact",
                "domain": "market_data",
                "source_kind": "official_nav",
                "source_path": "input/official_nav_benchmark.json",
                "source_record_id": nav["official_nav_start"]["nav_date"],
                "as_of_date": nav["official_nav_start"]["nav_date"],
                "available_from": nav["official_nav_start"]["available_from"],
                "status": "present",
                "value": nav["official_nav_start"],
                "trust_level": "official_or_structured_fixture",
            },
            {
                "fact_id": f"fact:nav:{meta['fund_code']}:end",
                "layer": "canonical_fact",
                "domain": "market_data",
                "source_kind": "official_nav",
                "source_path": "input/official_nav_benchmark.json",
                "source_record_id": nav["official_nav_end"]["nav_date"],
                "as_of_date": nav["official_nav_end"]["nav_date"],
                "available_from": nav["official_nav_end"]["available_from"],
                "status": "present",
                "value": nav["official_nav_end"],
                "trust_level": "official_or_structured_fixture",
            },
        ],
        "derived_signals": context.get("derived_signals", []),
        "decision_history": context.get("decision_history", []),
        "outcome_history": [],
        "similar_cases": context.get("similar_cases", []),
        "policy_context": context.get("policy_context", {}),
        "critical_data_checks": [
            {"name": "validated_action", "status": "present"},
            {"name": "portfolio_position", "status": "present"},
            {"name": "official_nav_start", "status": "present"},
            {"name": "official_nav_end", "status": "present"},
        ],
        "missing_critical_data": [],
        "audit": {
            "builder": "scripts/replay_refactor_slice.py",
            "slice_id": meta["slice_id"],
            "ticket_id": ticket["ticket_id"],
        },
    }
    return pack


def build_outcome_event(inputs: dict[str, Any], action_ticket: dict[str, Any]) -> dict[str, Any]:
    meta = inputs["slice"]
    nav = inputs["official_nav_benchmark"]
    ticket = action_ticket["tickets"][0]
    start = nav["official_nav_start"]
    end = nav["official_nav_end"]
    start_nav = float(start["nav"])
    end_nav = float(end["nav"])
    actual_return_pct = round((end_nav / start_nav - 1.0) * 100.0, 4) if start_nav else 0.0
    benchmark_return_pct = float(nav.get("benchmark", {}).get("return_pct") or 0.0)
    excess_return_pct = round(actual_return_pct - benchmark_return_pct, 4)
    label = "helped" if actual_return_pct > 0 else "hurt" if actual_return_pct < 0 else "neutral"
    event = {
        "outcome_id": f"outcome:{meta['report_date']}:{meta['horizon']}:{meta['fund_code']}:{meta['action_verb']}:001",
        "ticket_id": ticket["ticket_id"],
        "base_date": meta["report_date"],
        "evaluation_date": meta["evaluation_date"],
        "horizon": meta["horizon"],
        "fund_code": meta["fund_code"],
        "fund_name": ticket["fund_name"],
        "action_verb": ticket["action_verb"],
        "execution_mode": ticket["execution_mode"],
        "amount": ticket["validated_amount"],
        "amount_currency": "CNY",
        "scoring_status": "scored",
        "blocked_reason": "",
        "official_nav_start": start,
        "official_nav_end": end,
        "benchmark": nav.get("benchmark", {}),
        "actual_return_pct": actual_return_pct,
        "benchmark_return_pct": benchmark_return_pct,
        "excess_return_pct": excess_return_pct,
        "no_action_baseline": {
            "baseline_type": "hold_cash",
            "return_pct": 0.0,
            "excess_vs_baseline_pct": actual_return_pct,
        },
        "outcome_label": label,
        "diagnostic_label": "scheduled_dca_positive_nav_follow_through" if label == "helped" else "scheduled_dca_nav_follow_through_not_positive",
        "confidence": 0.6,
        "cashflow_checks": {
            "cashflow_between_nav_dates": False,
            "units_trusted": True,
            "position_authoritative": True,
        },
        "learning_implications": [
            {
                "target_type": "strategy_skill",
                "target_id": "skill:scheduled_dca_shadow_review:v0",
                "effect": "support" if label == "helped" else "neutral",
                "notes": "Phase 0.5 records the outcome for audit only; it does not promote or mutate strategy memory.",
            }
        ],
        "source_refs": [
            {"kind": "action_ticket", "path": "action_ticket.json", "json_pointer": "/tickets/0"},
            {"kind": "official_nav_start", "path": "input/official_nav_benchmark.json", "record_id": start["nav_date"]},
            {"kind": "official_nav_end", "path": "input/official_nav_benchmark.json", "record_id": end["nav_date"]},
        ],
        "audit": {
            "builder": "scripts/replay_refactor_slice.py",
            "content_basis": "fixed golden fixture",
        },
    }
    return {
        "schema_version": "outcome_event.v1",
        "artifact_id": f"outcome_events:{meta['slice_id']}:{meta['horizon']}",
        "base_date": meta["report_date"],
        "evaluation_date": meta["evaluation_date"],
        "horizon": meta["horizon"],
        "generated_at": meta["generated_at"],
        "write_scope": "learning_only",
        "non_executable": True,
        "source_artifacts": [
            {
                "kind": "action_ticket",
                "path": "action_ticket.json",
                "content_sha256": hashlib.sha256(json.dumps(action_ticket, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
            },
            *source_artifacts(inputs),
        ],
        "events": [event],
        "summary": {
            "event_count": 1,
            "scored_count": 1,
            "pending_count": 0,
            "blocked_count": 0,
        },
    }


def build_artifacts(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    action_ticket = build_action_ticket(inputs)
    retrieval_pack = build_retrieval_pack(inputs, action_ticket)
    outcome_event = build_outcome_event(inputs, action_ticket)
    return {
        "action_ticket": action_ticket,
        "retrieval_pack": retrieval_pack,
        "outcome_event": outcome_event,
    }


def write_artifacts(output_dir: Path, artifacts: dict[str, dict[str, Any]], *, expected: bool = False) -> dict[str, Any]:
    suffix = ".expected.json" if expected else ".json"
    file_map = {
        "action_ticket": output_dir / f"action_ticket{suffix}",
        "retrieval_pack": output_dir / f"retrieval_pack{suffix}",
        "outcome_event": output_dir / f"outcome_event{suffix}",
    }
    boundary_checks: list[BoundaryCheck] = []
    written_paths: list[Path] = []
    for name, artifact in artifacts.items():
        path = file_map[name]
        boundary_checks.extend(assert_refactor_write_allowed(path, artifact))
        dump_json(path, artifact)
        written_paths.append(path)
    forbidden = find_forbidden_write_paths(written_paths)
    return {
        "written_paths": [relative_posix(path) for path in written_paths],
        "boundary_checks": [check.to_dict() for check in boundary_checks],
        "forbidden_write_attempts": forbidden,
    }


def run_slice(slice_id: str = DEFAULT_SLICE_ID, fixture_root: Path | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    inputs = load_slice_inputs(slice_id, fixture_root)
    artifacts = build_artifacts(inputs)
    output = output_dir or default_output_dir(slice_id)
    write_result = write_artifacts(output, artifacts)
    metadata = {
        "schema_version": "refactor_slice_run.v1",
        "slice_id": slice_id,
        "generated_at": inputs["slice"]["generated_at"],
        "write_scope": "shadow_only",
        "non_executable": True,
        "allowed_writes": write_result["written_paths"] + [relative_posix(output / "run_metadata.json")],
        "forbidden_writes": write_result["forbidden_write_attempts"],
        "boundary_checks": write_result["boundary_checks"],
        "official_output_unchanged": True,
        "artifacts": {
            "action_ticket": "action_ticket.json",
            "retrieval_pack": "retrieval_pack.json",
            "outcome_event": "outcome_event.json",
        },
    }
    assert_refactor_write_allowed(output / "run_metadata.json", metadata)
    dump_json(output / "run_metadata.json", metadata)
    return {"output_dir": output, "artifacts": artifacts, "metadata": metadata}


def update_expected(slice_id: str = DEFAULT_SLICE_ID, fixture_root: Path | None = None) -> Path:
    inputs = load_slice_inputs(slice_id, fixture_root)
    artifacts = build_artifacts(inputs)
    expected_dir = inputs["_fixture_dir"] / "expected"
    write_artifacts(expected_dir, artifacts, expected=True)
    return expected_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay one fixed refactor golden slice into shadow-only artifacts.")
    parser.add_argument("--slice-id", default=DEFAULT_SLICE_ID)
    parser.add_argument("--fixture-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--update-expected", action="store_true", help="Explicitly regenerate expected JSON artifacts from fixed fixtures.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.update_expected:
        expected = update_expected(args.slice_id, args.fixture_root)
        print(f"updated expected artifacts: {relative_posix(expected)}")
        return
    result = run_slice(args.slice_id, args.fixture_root, args.output_dir)
    print(f"replayed slice {args.slice_id}: {relative_posix(result['output_dir'])}")


if __name__ == "__main__":
    main()
