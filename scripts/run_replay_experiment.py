from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from common import (
    dump_json,
    ensure_layout,
    llm_advice_path,
    llm_raw_path,
    load_json,
    load_strategy,
    replay_experiment_dir,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
    validated_advice_path,
)
from learning_memory import apply_replay_summary_to_ledger
from long_memory_store import stable_memory_id, sync_legacy_review_memory, upsert_memory_record
from review_advice import classify_outcome, estimated_edge_vs_no_trade
from validate_llm_advice import build_validated_payload
from decision_ledger import load_decisions


def iter_report_dates(agent_home: Path, start_date: str, end_date: str) -> list[str]:
    base_dir = agent_home / "db" / "llm_advice"
    if not base_dir.exists():
        return []
    dates = []
    for path in sorted(base_dir.glob("*.json")):
        stem = path.stem[:10]
        if len(stem) != 10 or stem.count("-") != 2:
            continue
        if start_date <= stem <= end_date:
            dates.append(stem)
    return dates


def load_portfolio_for_replay(agent_home: Path, report_date: str) -> dict | None:
    snapshot = agent_home / "db" / "portfolio_state" / "snapshots" / f"{report_date}.json"
    if snapshot.exists():
        return load_json(snapshot)
    current = agent_home / "db" / "portfolio_state" / "current.json"
    if current.exists():
        payload = load_json(current)
        if str(payload.get("as_of_date", "") or "") == report_date:
            return payload
    legacy = agent_home / "config" / "portfolio.json"
    if legacy.exists():
        payload = load_json(legacy)
        if str(payload.get("as_of_date", "") or "") == report_date:
            return payload
    return None


def review_summary_for_base_date(agent_home: Path, base_date: str) -> dict:
    summary = {
        "supportive": 0,
        "adverse": 0,
        "missed_upside": 0,
        "neutral": 0,
        "unknown": 0,
        "item_count": 0,
        "sources": {"advice": 0, "execution": 0},
    }
    for relative, source_name in (("db/review_results", "advice"), ("db/execution_reviews", "execution")):
        base = agent_home / relative
        if not base.exists():
            continue
        for path in sorted(base.glob("*.json")):
            payload = load_json(path)
            if payload.get("base_date") != base_date:
                continue
            summary["sources"][source_name] += 1
            for item in payload.get("items", []) or []:
                outcome = str(item.get("outcome", "unknown") or "unknown")
                summary[outcome] = summary.get(outcome, 0) + 1
                summary["item_count"] += 1
    return summary


def advice_review_items_for_base_date(agent_home: Path, base_date: str) -> list[dict]:
    base = agent_home / "db" / "review_results"
    if not base.exists():
        return []
    items: list[dict] = []
    for path in sorted(base.glob("*.json")):
        payload = load_json(path)
        if payload.get("base_date") != base_date:
            continue
        if payload.get("source", "advice") != "advice":
            continue
        items.extend(payload.get("items", []) or [])
    return items


def _validated_metrics(payload: dict) -> dict:
    tactical_actions = payload.get("tactical_actions", []) or []
    add_count = sum(1 for item in tactical_actions if item.get("validated_action") == "add")
    reduce_count = sum(1 for item in tactical_actions if item.get("validated_action") in {"reduce", "switch_out"})
    gross_trade = round(sum(float(item.get("validated_amount", 0.0) or 0.0) for item in tactical_actions), 2)
    selected_codes = [item.get("fund_code", "") for item in tactical_actions if item.get("fund_code")]
    return {
        "tactical_action_count": len(tactical_actions),
        "add_count": add_count,
        "reduce_count": reduce_count,
        "gross_trade": gross_trade,
        "selected_fund_codes": selected_codes,
        "optimizer_mode": str((payload.get("optimization_summary", {}) or {}).get("mode", "") or ""),
    }


def _action_signature(payload: dict) -> dict[str, tuple[str, float]]:
    return {
        item.get("fund_code", ""): (str(item.get("validated_action", "") or ""), round(float(item.get("validated_amount", 0.0) or 0.0), 2))
        for item in (payload.get("tactical_actions", []) or [])
        if item.get("fund_code")
    }


def _counterfactual_edge(action: str, amount: float, review_item: dict) -> float:
    evaluation_return = review_item.get("evaluation_return_pct")
    if evaluation_return is None:
        return 0.0
    edge = float(estimated_edge_vs_no_trade(action, amount, evaluation_return) or 0.0)
    fee_rate = float(review_item.get("estimated_redeem_fee_rate", 0.0) or 0.0)
    if action in {"reduce", "switch_out"} and fee_rate > 0:
        edge -= round(float(amount) * fee_rate / 100.0, 2)
    return round(edge, 2)


def compare_signatures_with_review(existing_signature: dict[str, tuple[str, float]], replay_signature: dict[str, tuple[str, float]], review_items: list[dict]) -> dict:
    metrics = {
        "changed_item_count": 0,
        "improved_item_count": 0,
        "worsened_item_count": 0,
        "edge_delta_total": 0.0,
        "existing_edge_total": 0.0,
        "replay_edge_total": 0.0,
        "learning_impacts": [],
        "item_deltas": [],
    }
    impact_map: dict[str, dict] = {}
    for item in review_items:
        fund_code = str(item.get("fund_code", "") or "")
        if not fund_code:
            continue
        existing_action, existing_amount = existing_signature.get(fund_code, ("hold", 0.0))
        replay_action, replay_amount = replay_signature.get(fund_code, ("hold", 0.0))
        existing_edge = _counterfactual_edge(existing_action, existing_amount, item)
        replay_edge = _counterfactual_edge(replay_action, replay_amount, item)
        delta = round(replay_edge - existing_edge, 2)
        changed = (existing_action, existing_amount) != (replay_action, replay_amount)
        metrics["existing_edge_total"] = round(metrics["existing_edge_total"] + existing_edge, 2)
        metrics["replay_edge_total"] = round(metrics["replay_edge_total"] + replay_edge, 2)
        metrics["edge_delta_total"] = round(metrics["edge_delta_total"] + delta, 2)
        if changed:
            metrics["changed_item_count"] += 1
            if delta > 0:
                metrics["improved_item_count"] += 1
            elif delta < 0:
                metrics["worsened_item_count"] += 1
        metrics["item_deltas"].append(
            {
                "fund_code": fund_code,
                "diagnostic_label": item.get("diagnostic_label", ""),
                "existing_action": existing_action,
                "replay_action": replay_action,
                "existing_edge": existing_edge,
                "replay_edge": replay_edge,
                "edge_delta": delta,
                "changed": changed,
                "evaluation_return_pct": item.get("evaluation_return_pct"),
                "existing_outcome": classify_outcome(existing_action, item.get("evaluation_return_pct")),
                "replay_outcome": classify_outcome(replay_action, item.get("evaluation_return_pct")),
            }
        )

        label = str(item.get("diagnostic_label", "") or "")
        if not changed or not label:
            continue
        impact = impact_map.setdefault(
            label,
            {
                "rule_label": label,
                "support_count": 0,
                "contradiction_count": 0,
                "changed_item_count": 0,
                "total_edge_delta": 0.0,
                "fund_codes": [],
            },
        )
        impact["changed_item_count"] += 1
        impact["total_edge_delta"] = round(float(impact["total_edge_delta"]) + delta, 2)
        if fund_code not in impact["fund_codes"]:
            impact["fund_codes"].append(fund_code)
        if delta > 0:
            impact["support_count"] += 1
        elif delta < 0:
            impact["contradiction_count"] += 1

    metrics["learning_impacts"] = sorted(impact_map.values(), key=lambda item: (-abs(float(item.get("total_edge_delta", 0.0))), item.get("rule_label", "")))
    return metrics


def decision_replay_metrics(agent_home: Path, report_date: str, replay_payload: dict) -> dict:
    ledger = load_decisions(agent_home, report_date)
    decisions = ledger.get("decisions", []) or []
    replay_actions = []
    for section in ("tactical_actions", "dca_actions", "hold_actions"):
        replay_actions.extend(replay_payload.get(section, []) or [])
    replay_by_code = {item.get("fund_code", ""): item for item in replay_actions if item.get("fund_code")}
    items = []
    improved = 0
    worsened = 0
    for decision in decisions:
        code = decision.get("fund_code", "")
        replay = replay_by_code.get(code, {})
        outcomes = decision.get("outcomes", {}) or {}
        ready = [value for value in outcomes.values() if value.get("status") == "ready"]
        latest = ready[-1] if ready else {}
        nav_return = float(latest.get("nav_return", 0.0) or 0.0)
        action = str(replay.get("validated_action", decision.get("validated_action", "hold")) or "hold")
        vs_hold = 0.0
        if action in {"add", "buy", "scheduled_dca"}:
            vs_hold = nav_return
        elif action in {"reduce", "sell", "switch_out"}:
            vs_hold = -nav_return
        if vs_hold > 0:
            improved += 1
        elif vs_hold < 0:
            worsened += 1
        items.append({
            "decision_id": decision.get("decision_id", ""),
            "fund_code": code,
            "replay_action": action,
            "nav_return": nav_return,
            "vs_hold": round(vs_hold, 4),
            "outcome_status": latest.get("status", "pending"),
        })
    return {"decision_count": len(decisions), "improved_vs_hold": improved, "worsened_vs_hold": worsened, "items": items}


def build_markdown_report(summary: dict) -> str:
    lines = [
        f"# Replay Experiment {summary['experiment_id']}",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- mode: {summary['mode']}",
        f"- date_range: {summary['start_date']} -> {summary['end_date']}",
        f"- processed_dates: {len(summary['daily_results'])}",
        f"- skipped_dates: {len(summary['skipped_dates'])}",
        "",
        "## Aggregate",
        f"- total_tactical_actions: {summary['aggregate']['total_tactical_actions']}",
        f"- total_gross_trade: {summary['aggregate']['total_gross_trade']}",
        f"- supportive_reviews: {summary['aggregate']['supportive_reviews']}",
        f"- adverse_reviews: {summary['aggregate']['adverse_reviews']}",
        f"- changed_days: {summary['aggregate']['changed_days']}",
        f"- edge_delta_total: {summary['aggregate']['edge_delta_total']}",
        f"- improved_items: {summary['aggregate']['improved_items']}",
        f"- worsened_items: {summary['aggregate']['worsened_items']}",
        "",
        "## Optimizer",
        f"- days_with_optimizer: {summary['aggregate']['optimizer']['days_with_optimizer']}",
        f"- total_candidates: {summary['aggregate']['optimizer']['total_candidates']}",
        f"- total_selected_candidates: {summary['aggregate']['optimizer']['total_selected_candidates']}",
        f"- total_feasible_combinations: {summary['aggregate']['optimizer']['total_feasible_combinations']}",
        f"- selected_gross_trade_total: {summary['aggregate']['optimizer']['selected_gross_trade_total']}",
        f"- selected_net_buy_total: {summary['aggregate']['optimizer']['selected_net_buy_total']}",
    ]
    rejection_counts = summary["aggregate"]["optimizer"].get("rejection_reason_counts", {}) or {}
    if rejection_counts:
        lines.append("- rejection_reason_counts: " + ", ".join(f"{key}={value}" for key, value in sorted(rejection_counts.items())))
    else:
        lines.append("- rejection_reason_counts: none")
    lines.extend(["", "## Learning Impacts"])
    if summary.get("learning_impacts"):
        for item in summary["learning_impacts"]:
            lines.append(
                f"- {item['rule_label']} | support={item['support_count']} | contradiction={item['contradiction_count']} | "
                f"changed={item['changed_item_count']} | edge_delta={item['total_edge_delta']}"
            )
    else:
        lines.append("- No replay-derived learning impacts.")
    lines.extend(["", "## Daily Results"])
    for item in summary["daily_results"]:
        lines.append(
            "- "
            + f"{item['report_date']} | actions={item['metrics']['tactical_action_count']} | "
            + f"gross={item['metrics']['gross_trade']} | changed={item['changed_vs_existing']} | "
            + f"optimizer_candidates={item.get('optimizer', {}).get('candidate_count', 0)} | "
            + f"supportive={item['review_summary']['supportive']} | adverse={item['review_summary']['adverse']} | "
            + f"edge_delta={item.get('counterfactual', {}).get('edge_delta_total', 0.0)}"
        )
    if summary["skipped_dates"]:
        lines.extend(["", "## Skipped Dates"])
        for item in summary["skipped_dates"]:
            lines.append(f"- {item['report_date']}: {item['reason']}")
    return "\n".join(lines) + "\n"


def _aggregate_learning_impacts(daily_results: list[dict]) -> list[dict]:
    aggregate: dict[str, dict] = defaultdict(lambda: {"rule_label": "", "support_count": 0, "contradiction_count": 0, "changed_item_count": 0, "total_edge_delta": 0.0, "fund_codes": set()})
    for item in daily_results:
        for impact in item.get("counterfactual", {}).get("learning_impacts", []) or []:
            label = str(impact.get("rule_label", "") or "")
            if not label:
                continue
            current = aggregate[label]
            current["rule_label"] = label
            current["support_count"] += int(impact.get("support_count", 0) or 0)
            current["contradiction_count"] += int(impact.get("contradiction_count", 0) or 0)
            current["changed_item_count"] += int(impact.get("changed_item_count", 0) or 0)
            current["total_edge_delta"] = round(float(current.get("total_edge_delta", 0.0)) + float(impact.get("total_edge_delta", 0.0) or 0.0), 2)
            current["fund_codes"].update(impact.get("fund_codes", []) or [])
    results = []
    for value in aggregate.values():
        results.append({**value, "fund_codes": sorted(value["fund_codes"])})
    results.sort(key=lambda item: (-abs(float(item.get("total_edge_delta", 0.0) or 0.0)), item.get("rule_label", "")))
    return results


def optimizer_snapshot(payload: dict) -> dict:
    summary = dict(payload.get("optimization_summary", {}) or {})
    candidates = list(payload.get("optimizer_candidates", []) or [])
    return {
        "mode": str(summary.get("mode", "") or ""),
        "candidate_count": int(summary.get("candidate_count", len(candidates)) or len(candidates)),
        "selected_candidate_count": int(summary.get("selected_candidate_count", 0) or 0),
        "feasible_combination_count": int(summary.get("feasible_combination_count", 0) or 0),
        "best_objective_score": float(summary.get("best_objective_score", 0.0) or 0.0),
        "selected_gross_trade": float(summary.get("selected_gross_trade", 0.0) or 0.0),
        "selected_net_buy": float(summary.get("selected_net_buy", 0.0) or 0.0),
        "selected_sell_proceeds": float(summary.get("selected_sell_proceeds", 0.0) or 0.0),
        "rejection_reason_counts": dict(summary.get("rejection_reason_counts", {}) or {}),
        "selected_candidate_ids": [item.get("candidate_id", "") for item in candidates if item.get("selected")],
        "rejected_candidate_ids": [item.get("candidate_id", "") for item in candidates if not item.get("selected")],
        "candidate_diagnostics": [
            {
                "candidate_id": item.get("candidate_id", ""),
                "fund_code": item.get("fund_code", ""),
                "action": item.get("action", ""),
                "amount": float(item.get("amount", 0.0) or 0.0),
                "base_objective": float(item.get("base_objective", 0.0) or 0.0),
                "selected": bool(item.get("selected", False)),
                "rejection_reasons": list(item.get("rejection_reasons", []) or []),
            }
            for item in candidates
        ],
    }


def empty_optimizer_aggregate() -> dict:
    return {
        "days_with_optimizer": 0,
        "total_candidates": 0,
        "total_selected_candidates": 0,
        "total_feasible_combinations": 0,
        "selected_gross_trade_total": 0.0,
        "selected_net_buy_total": 0.0,
        "selected_sell_proceeds_total": 0.0,
        "rejection_reason_counts": {},
    }


def update_optimizer_aggregate(aggregate_optimizer: dict, snapshot: dict) -> None:
    if not snapshot.get("mode"):
        return
    aggregate_optimizer["days_with_optimizer"] += 1
    aggregate_optimizer["total_candidates"] += int(snapshot.get("candidate_count", 0) or 0)
    aggregate_optimizer["total_selected_candidates"] += int(snapshot.get("selected_candidate_count", 0) or 0)
    aggregate_optimizer["total_feasible_combinations"] += int(snapshot.get("feasible_combination_count", 0) or 0)
    aggregate_optimizer["selected_gross_trade_total"] = round(float(aggregate_optimizer.get("selected_gross_trade_total", 0.0)) + float(snapshot.get("selected_gross_trade", 0.0) or 0.0), 2)
    aggregate_optimizer["selected_net_buy_total"] = round(float(aggregate_optimizer.get("selected_net_buy_total", 0.0)) + float(snapshot.get("selected_net_buy", 0.0) or 0.0), 2)
    aggregate_optimizer["selected_sell_proceeds_total"] = round(float(aggregate_optimizer.get("selected_sell_proceeds_total", 0.0)) + float(snapshot.get("selected_sell_proceeds", 0.0) or 0.0), 2)
    counter = Counter(aggregate_optimizer.get("rejection_reason_counts", {}) or {})
    counter.update(snapshot.get("rejection_reason_counts", {}) or {})
    aggregate_optimizer["rejection_reason_counts"] = dict(sorted(counter.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay historical artifacts for baseline analysis or validation re-runs.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--start-date", required=True, help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", required=True, help="End date in YYYY-MM-DD format.")
    parser.add_argument("--mode", choices=["baseline", "revalidate"], default="baseline")
    parser.add_argument("--experiment-name", default="", help="Optional stable experiment label.")
    parser.add_argument("--write-learning", action="store_true", help="Apply replay learning impacts to the memory ledger.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    start_date = resolve_date(args.start_date)
    end_date = resolve_date(args.end_date)
    strategy = load_strategy(agent_home)

    experiment_label = args.experiment_name.strip().replace(" ", "_")
    experiment_id = experiment_label or f"{timestamp_now().replace(':', '-').replace('+', '_')}_{args.mode}_{start_date}_{end_date}"
    target_dir = replay_experiment_dir(agent_home, experiment_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    daily_results = []
    skipped_dates = []
    aggregate = {
        "total_tactical_actions": 0,
        "total_gross_trade": 0.0,
        "supportive_reviews": 0,
        "adverse_reviews": 0,
        "changed_days": 0,
        "edge_delta_total": 0.0,
        "improved_items": 0,
        "worsened_items": 0,
        "optimizer": empty_optimizer_aggregate(),
    }

    for report_date in iter_report_dates(agent_home, start_date, end_date):
        advice_path = llm_advice_path(agent_home, report_date)
        if not advice_path.exists():
            skipped_dates.append({"report_date": report_date, "reason": "missing_llm_advice"})
            continue
        advice = load_json(advice_path)
        llm_raw = load_json(llm_raw_path(agent_home, report_date)) if llm_raw_path(agent_home, report_date).exists() else {}
        existing = load_json(validated_advice_path(agent_home, report_date)) if validated_advice_path(agent_home, report_date).exists() else {}
        if args.mode == "baseline":
            if not existing:
                skipped_dates.append({"report_date": report_date, "reason": "missing_validated_advice_for_baseline"})
                continue
            replay_payload = existing
        else:
            portfolio = load_portfolio_for_replay(agent_home, report_date)
            if not portfolio:
                skipped_dates.append({"report_date": report_date, "reason": "missing_portfolio_snapshot"})
                continue
            replay_payload = build_validated_payload(
                agent_home,
                report_date,
                portfolio=portfolio,
                strategy=strategy,
                advice=advice,
                llm_raw=llm_raw,
            )

        metrics = _validated_metrics(replay_payload)
        decision_metrics = decision_replay_metrics(agent_home, report_date, replay_payload)
        existing_signature = _action_signature(existing) if existing else {}
        replay_signature = _action_signature(replay_payload)
        changed = existing_signature != replay_signature if existing else False
        if changed:
            aggregate["changed_days"] += 1

        review_summary = review_summary_for_base_date(agent_home, report_date)
        counterfactual = compare_signatures_with_review(existing_signature, replay_signature, advice_review_items_for_base_date(agent_home, report_date))
        optimizer = optimizer_snapshot(replay_payload)
        aggregate["total_tactical_actions"] += metrics["tactical_action_count"]
        aggregate["total_gross_trade"] = round(aggregate["total_gross_trade"] + metrics["gross_trade"], 2)
        aggregate["supportive_reviews"] += review_summary["supportive"]
        aggregate["adverse_reviews"] += review_summary["adverse"]
        aggregate["edge_delta_total"] = round(aggregate["edge_delta_total"] + counterfactual.get("edge_delta_total", 0.0), 2)
        aggregate["improved_items"] += int(counterfactual.get("improved_item_count", 0) or 0)
        aggregate["worsened_items"] += int(counterfactual.get("worsened_item_count", 0) or 0)
        update_optimizer_aggregate(aggregate["optimizer"], optimizer)

        daily_results.append(
            {
                "report_date": report_date,
                "mode": args.mode,
                "metrics": metrics,
                "decision_metrics": decision_metrics,
                "changed_vs_existing": changed,
                "existing_signature": existing_signature,
                "replay_signature": replay_signature,
                "review_summary": review_summary,
                "advice_mode": str(llm_raw.get("mode", "") or ""),
                "counterfactual": counterfactual,
                "optimizer": optimizer,
            }
        )

    summary = {
        "experiment_id": experiment_id,
        "generated_at": timestamp_now(),
        "mode": args.mode,
        "start_date": start_date,
        "end_date": end_date,
        "daily_results": daily_results,
        "skipped_dates": skipped_dates,
        "aggregate": aggregate,
        "learning_impacts": _aggregate_learning_impacts(daily_results),
    }

    if args.write_learning:
        ledger, memory = apply_replay_summary_to_ledger(agent_home, summary)
        for impact in summary.get("learning_impacts", []) or []:
            label = str(impact.get("rule_label", "") or "")
            if not label:
                continue
            title = f"Replay impact: {label}"
            support = int(impact.get("support_count", 0) or 0)
            contradiction = int(impact.get("contradiction_count", 0) or 0)
            upsert_memory_record(
                agent_home,
                {
                    "memory_id": stable_memory_id("portfolio", label, title, "portfolio_policy_memory"),
                    "memory_type": "portfolio_policy_memory",
                    "domain": "portfolio",
                    "entity_key": label,
                    "title": title,
                    "text": (
                        f"Replay {summary.get('experiment_id', '')} tested rule label {label}: "
                        f"support={support}, contradiction={contradiction}, edge_delta={impact.get('total_edge_delta', 0.0)}."
                    ),
                    "status": "strategic",
                    "confidence": min(0.9, 0.55 + support * 0.04 - contradiction * 0.03),
                    "support_count": support,
                    "contradiction_count": contradiction,
                    "last_supported_at": str(summary.get("generated_at", "") or "")[:10],
                    "source": "replay_experiment",
                    "metadata": {
                        "experiment_id": summary.get("experiment_id", ""),
                        "mode": summary.get("mode", ""),
                        "fund_codes": impact.get("fund_codes", []),
                        "tags": [label, "replay"],
                    },
                    "evidence_refs": [{"kind": "replay_summary", "path": str(target_dir / "summary.json"), "date": str(summary.get("generated_at", "") or "")[:10]}],
                },
            )
        sync_legacy_review_memory(agent_home)
        summary["learning_update"] = {
            "applied": True,
            "ledger_summary": ledger.get("summary", {}),
            "updated_at": ledger.get("updated_at", ""),
        }
        dump_json(agent_home / "db" / "review_memory" / "ledger.json", ledger)
        dump_json(agent_home / "db" / "review_memory" / "memory.json", memory)
    else:
        summary["learning_update"] = {"applied": False}

    dump_json(target_dir / "summary.json", summary)
    (target_dir / "report.md").write_text(build_markdown_report(summary), encoding="utf-8")
    print(target_dir / "summary.json")


if __name__ == "__main__":
    main()
