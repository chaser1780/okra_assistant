from __future__ import annotations

import argparse

from common import dump_json, ensure_layout, llm_advice_path, llm_raw_path, load_json, load_portfolio, load_strategy, resolve_agent_home, resolve_date, timestamp_now, validated_advice_path
from decision_ledger import build_and_write_decisions
from models import FinalAdvice, PortfolioFund, PortfolioState, ValidatedAction, ValidatedAdvice
from portfolio_exposure import STRATEGY_BUCKET_LABELS, analyze_portfolio_exposure, infer_strategy_bucket, infer_theme_family, safe_float
from portfolio_optimizer import optimize_portfolio_actions
from trade_constraints import build_trade_constraints


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def normalize_amount(amount: float, ceiling: float, allow_full_exit: bool = False) -> float:
    amount = max(0.0, min(float(amount), float(ceiling)))
    if allow_full_exit and ceiling > 0 and amount >= ceiling * 0.85:
        return round(float(ceiling), 2)
    if amount < 100:
        return 0.0
    return float(int(amount // 100) * 100)


def default_hold(fund: PortfolioFund, reason: str) -> ValidatedAction:
    return {
        "suggestion_id": "",
        "fund_code": fund["fund_code"],
        "fund_name": fund["fund_name"],
        "strategy_bucket": infer_strategy_bucket(fund),
        "validated_action": "hold",
        "validated_amount": 0.0,
        "model_action": "hold",
        "priority": 999,
        "confidence": 0.0,
        "thesis": reason,
        "evidence": [],
        "risks": [],
        "agent_support": [],
        "source_signal_ids": [],
        "opposing_signal_ids": [],
        "policy_rule_hits": [],
        "constraint_hits": [],
        "allocation_impact": "",
        "cash_impact": "",
        "change_vs_prev_day": {},
        "execution_friction": [],
        "validation_notes": [reason],
        "execution_status": "not_applicable",
        "executed_amount": 0.0,
    }


def suggestion_id(report_date: str, fund_code: str, validated_action: str) -> str:
    return f"{report_date}:{fund_code}:{validated_action}"


def previous_validated_by_code(agent_home, report_date: str) -> dict[str, dict]:
    base_dir = resolve_agent_home(agent_home) / "db" / "validated_advice"
    if not base_dir.exists():
        return {}
    for path in sorted(base_dir.glob("*.json"), key=lambda item: item.stem, reverse=True):
        if path.stem >= report_date:
            continue
        payload = load_json(path)
        mapping = {}
        for section in ("tactical_actions", "dca_actions", "hold_actions"):
            for item in payload.get(section, []) or []:
                if item.get("fund_code"):
                    mapping[item["fund_code"]] = item
        if mapping:
            return mapping
    return {}


def change_vs_prev(current_action: str, current_amount: float, previous: dict | None) -> dict:
    if not previous:
        return {
            "previous_action": "",
            "previous_amount": 0.0,
            "changed": bool(current_action and current_action != "hold"),
            "reason_category": "new_decision",
        }
    prev_action = str(previous.get("validated_action", previous.get("model_action", "hold")) or "hold")
    prev_amount = float(previous.get("validated_amount", 0.0) or 0.0)
    changed = prev_action != current_action or round(prev_amount, 2) != round(float(current_amount), 2)
    if not changed:
        category = "unchanged"
    elif prev_action != current_action:
        category = "action_changed"
    else:
        category = "amount_changed"
    return {
        "previous_action": prev_action,
        "previous_amount": prev_amount,
        "changed": changed,
        "reason_category": category,
    }


def execution_friction_notes(constraint: dict) -> list[str]:
    notes: list[str] = []
    if constraint.get("redeem_settlement_days") is not None:
        notes.append(f"redeem_settlement_days=T+{constraint.get('redeem_settlement_days')}")
    if constraint.get("purchase_confirm_days") is not None:
        notes.append(f"purchase_confirm_days=T+{constraint.get('purchase_confirm_days')}")
    if constraint.get("estimated_redeem_fee_rate", 0.0):
        notes.append(f"estimated_redeem_fee_rate={constraint.get('estimated_redeem_fee_rate')}%")
    return notes


def dca_record(
    report_date: str,
    fund: PortfolioFund,
    amount: float,
    *,
    model_decision: dict,
    constraint: dict,
    previous: dict | None,
) -> ValidatedAction:
    return {
        "fund_code": fund["fund_code"],
        "fund_name": fund["fund_name"],
        "strategy_bucket": infer_strategy_bucket(fund),
        "validated_action": "scheduled_dca",
        "validated_amount": amount,
        "suggestion_id": suggestion_id(report_date, fund["fund_code"], "scheduled_dca"),
        "model_action": model_decision.get("action", "scheduled_dca"),
        "priority": model_decision.get("priority", 0),
        "confidence": model_decision.get("confidence", 1.0),
        "thesis": "Execute scheduled DCA plan.",
        "evidence": [
            f"{fund['fund_name']} is treated as core DCA.",
            f"Fixed DCA amount = {amount:.2f}.",
        ],
        "risks": [
            "Short-term timing noise remains possible after execution.",
            "DCA policy deliberately avoids discretionary intraday overfitting.",
        ],
        "agent_support": model_decision.get("agent_support", []),
        "source_signal_ids": model_decision.get("source_signal_ids", []),
        "opposing_signal_ids": model_decision.get("opposing_signal_ids", []),
        "policy_rule_hits": ["core_dca_only"],
        "constraint_hits": ["core_dca_fixed_rule"],
        "allocation_impact": "core_long_term + scheduled_dca",
        "cash_impact": f"cash_hub -{amount:.2f}",
        "change_vs_prev_day": change_vs_prev("scheduled_dca", amount, previous),
        "execution_friction": [f"purchase_confirm_days=T+{constraint.get('purchase_confirm_days', 1)}"],
        "validation_notes": ["Core DCA funds only execute fixed scheduled buys."],
        "execution_status": "pending",
        "executed_amount": 0.0,
    }


def build_candidate(
    fund: PortfolioFund,
    model: dict,
    *,
    strategy: dict,
    constraint: dict,
) -> dict | None:
    action = str(model.get("action", "hold") or "hold")
    if action not in {"add", "reduce", "switch_out"}:
        return None

    current_value = float(fund.get("current_value", 0.0) or 0.0)
    cap_value = float(fund.get("cap_value", strategy["tactical"]["default_cap_value"]) or strategy["tactical"]["default_cap_value"])
    available_to_sell = float(constraint.get("available_to_sell", current_value) or current_value)
    allow_full_exit = bool(strategy["portfolio"].get("allow_full_exit", True))
    requested_amount = float(model.get("suggest_amount", 0.0) or 0.0)
    policy_rule_hits: list[str] = []
    constraint_hits: list[str] = []
    validation_notes: list[str] = []

    if action == "add":
        policy_rule_hits.append("budget_gate")
        room = max(0.0, cap_value - current_value)
        normalized_amount = normalize_amount(requested_amount, room)
        if normalized_amount <= 0:
            constraint_hits.append("fund_capacity_or_granularity")
            validation_notes.append("Candidate removed before optimizer because no add room remained after fund-local cap and 100-CNY trade granularity.")
    else:
        policy_rule_hits.append("sell_gate")
        normalized_amount = normalize_amount(requested_amount, available_to_sell, allow_full_exit=allow_full_exit)
        if float(constraint.get("locked_amount", 0.0) or 0.0) > 0:
            constraint_hits.append("locked_amount")
            validation_notes.extend(list(constraint.get("notes", []) or []))
        if normalized_amount <= 0:
            constraint_hits.append("sellable_amount_or_granularity")
            validation_notes.append("Candidate removed before optimizer because sellable amount fell below executable size.")

    if normalized_amount <= 0:
        return None

    transaction_cost_amount = 0.0
    if action in {"reduce", "switch_out"}:
        transaction_cost_amount = round(normalized_amount * float(constraint.get("estimated_redeem_fee_rate", 0.0) or 0.0) / 100.0, 2)

    return {
        "candidate_id": fund["fund_code"],
        "fund_code": fund["fund_code"],
        "fund_name": fund["fund_name"],
        "action": action,
        "amount": normalized_amount,
        "requested_amount": requested_amount,
        "strategy_bucket": infer_strategy_bucket(fund),
        "theme_family": infer_theme_family(fund),
        "priority": int(model.get("priority", 999) or 999),
        "confidence": clamp(float(model.get("confidence", 0.0) or 0.0), 0.0, 1.0),
        "thesis": str(model.get("thesis", "") or ""),
        "evidence": list(model.get("evidence", []) or []),
        "risks": list(model.get("risks", []) or []),
        "agent_support": list(model.get("agent_support", []) or []),
        "source_signal_ids": list(model.get("source_signal_ids", []) or []),
        "opposing_signal_ids": list(model.get("opposing_signal_ids", []) or []),
        "policy_rule_hits": policy_rule_hits,
        "constraint_hits": constraint_hits,
        "validation_notes": validation_notes,
        "execution_friction": execution_friction_notes(constraint),
        "transaction_cost_amount": transaction_cost_amount,
    }


def build_record(
    report_date: str,
    fund: PortfolioFund,
    model: dict,
    *,
    validated_action: str,
    validated_amount: float,
    previous: dict | None,
    allocation_plan: dict,
    execution_friction: list[str],
    policy_rule_hits: list[str],
    constraint_hits: list[str],
    validation_notes: list[str],
    cash_note: str,
) -> ValidatedAction:
    strategy_bucket = infer_strategy_bucket(fund)
    model_action = str(model.get("action", "hold") or "hold")
    final_action_for_id = validated_action if validated_action != "hold" else model_action
    return {
        "suggestion_id": suggestion_id(report_date, fund["fund_code"], final_action_for_id),
        "fund_code": fund["fund_code"],
        "fund_name": fund["fund_name"],
        "strategy_bucket": strategy_bucket,
        "validated_action": validated_action,
        "validated_amount": validated_amount,
        "model_action": model_action,
        "priority": int(model.get("priority", 999) or 999),
        "confidence": clamp(float(model.get("confidence", 0.0) or 0.0), 0.0, 1.0),
        "thesis": str(model.get("thesis", "") or ""),
        "evidence": list(model.get("evidence", []) or []),
        "risks": list(model.get("risks", []) or []),
        "agent_support": list(model.get("agent_support", []) or []),
        "source_signal_ids": list(model.get("source_signal_ids", []) or []),
        "opposing_signal_ids": list(model.get("opposing_signal_ids", []) or []),
        "policy_rule_hits": policy_rule_hits,
        "constraint_hits": constraint_hits,
        "allocation_impact": f"{strategy_bucket}:{allocation_plan.get('current_pct', {}).get(strategy_bucket, 0.0)}->{allocation_plan.get('targets_pct', {}).get(strategy_bucket, 0.0)}",
        "cash_impact": cash_note,
        "change_vs_prev_day": change_vs_prev(validated_action, validated_amount, previous),
        "execution_friction": execution_friction,
        "validation_notes": validation_notes,
        "execution_status": "pending" if validated_action != "hold" else "not_applicable",
        "executed_amount": 0.0,
    }


def build_validated_payload(
    agent_home,
    report_date: str,
    *,
    portfolio: PortfolioState | None = None,
    strategy: dict | None = None,
    advice: FinalAdvice | None = None,
    llm_raw: dict | None = None,
    previous_actions: dict[str, dict] | None = None,
) -> ValidatedAdvice:
    agent_home = resolve_agent_home(agent_home)
    portfolio = portfolio or load_portfolio(agent_home)
    strategy = strategy or load_strategy(agent_home)
    advice = advice or load_json(llm_advice_path(agent_home, report_date))
    llm_raw = llm_raw or (load_json(llm_raw_path(agent_home, report_date)) if llm_raw_path(agent_home, report_date).exists() else {})
    constraint_map = build_trade_constraints(agent_home, portfolio, report_date)
    previous_actions = previous_actions if previous_actions is not None else previous_validated_by_code(agent_home, report_date)

    exposure = analyze_portfolio_exposure(portfolio, strategy)
    allocation_plan = exposure.get("allocation_plan", {})
    current_bucket_pct = allocation_plan.get("current_pct", {})
    target_bucket_pct = allocation_plan.get("targets_pct", {})
    rebalance_band_pct = float(allocation_plan.get("rebalance_band_pct", 5.0) or 5.0)
    total_value = float(exposure.get("total_value", 0.0) or 0.0)

    decisions = {item["fund_code"]: item for item in advice.get("fund_decisions", []) if item.get("fund_code")}
    gross_trade_limit = float(strategy["portfolio"].get("daily_max_gross_trade_amount", strategy["portfolio"]["daily_max_trade_amount"]))
    net_buy_limit = float(strategy["portfolio"].get("daily_max_net_buy_amount", strategy["portfolio"]["daily_max_trade_amount"]))

    dca_actions: list[ValidatedAction] = []
    hold_actions: list[ValidatedAction] = []
    candidate_pairs: list[tuple[PortfolioFund, dict, dict]] = []

    fixed_dca_total = 0.0
    available_cash_hub = 0.0

    for fund in portfolio["funds"]:
        model = decisions.get(
            fund["fund_code"],
            {
                "action": "hold",
                "suggest_amount": 0.0,
                "priority": 999,
                "confidence": 0.0,
                "thesis": "No actionable committee output for this fund.",
                "evidence": [],
                "risks": [],
                "agent_support": [],
                "source_signal_ids": [],
                "opposing_signal_ids": [],
            },
        )
        constraint = constraint_map.get(fund["fund_code"], {})
        if fund["role"] == "core_dca":
            amount = float(fund.get("fixed_daily_buy_amount", strategy["core_dca"]["amount_per_fund"]))
            fixed_dca_total += amount
            dca_actions.append(
                dca_record(
                    report_date,
                    fund,
                    amount,
                    model_decision=model,
                    constraint=constraint,
                    previous=previous_actions.get(fund["fund_code"]),
                )
            )
            continue
        if fund["role"] == "cash_hub":
            floor = float(strategy["portfolio"]["cash_hub_floor"])
            locked_amount = max(float(fund.get("locked_amount", 0.0) or 0.0), float(constraint.get("locked_amount", 0.0) or 0.0))
            available_cash_hub = max(0.0, float(fund.get("current_value", 0.0) or 0.0) - floor - locked_amount)
            hold_actions.append(default_hold(fund, f"Cash hub retains its buffer floor. Available reference funding = {available_cash_hub:.2f}."))
            continue
        if fund["role"] == "fixed_hold":
            hold_actions.append(default_hold(fund, "Fixed-hold position is not part of daily tactical validation."))
            continue

        candidate = build_candidate(fund, model, strategy=strategy, constraint=constraint)
        if candidate is None:
            notes = ["Model action resolves to hold after fund-local validation."]
            if str(model.get("action", "hold") or "hold") in {"add", "reduce", "switch_out"}:
                if str(model.get("action", "") or "") == "add":
                    notes.append("Candidate could not clear fund capacity / trade size checks.")
                else:
                    notes.append("Candidate could not clear sellable amount / trade size checks.")
            hold_actions.append(
                build_record(
                    report_date,
                    fund,
                    model,
                    validated_action="hold",
                    validated_amount=0.0,
                    previous=previous_actions.get(fund["fund_code"]),
                    allocation_plan=allocation_plan,
                    execution_friction=execution_friction_notes(constraint),
                    policy_rule_hits=["hold_default"] if model.get("action") == "hold" else ["candidate_rejected_pre_optimizer"],
                    constraint_hits=list(constraint.get("notes", []) or []) if float(constraint.get("locked_amount", 0.0) or 0.0) > 0 else [],
                    validation_notes=notes,
                    cash_note="candidate_not_selected",
                )
            )
            continue
        candidate_pairs.append((fund, model, candidate))

    remaining_gross_trade_budget = max(0.0, gross_trade_limit - fixed_dca_total)
    remaining_net_buy_budget = max(0.0, net_buy_limit - fixed_dca_total)
    max_actions = int(strategy["tactical"]["max_actions_per_day"])

    optimization = optimize_portfolio_actions(
        [candidate for _, _, candidate in candidate_pairs],
        strategy_bucket_summary=exposure.get("by_strategy_bucket", []),
        current_bucket_pct=current_bucket_pct,
        target_bucket_pct=target_bucket_pct,
        rebalance_band_pct=rebalance_band_pct,
        total_value=total_value,
        available_funding=available_cash_hub,
        gross_trade_budget=remaining_gross_trade_budget,
        net_buy_budget=remaining_net_buy_budget,
        max_actions=max_actions,
    )
    selected_by_id = {item["candidate_id"]: item for item in optimization.get("selected_candidates", [])}

    tactical_actions: list[ValidatedAction] = []
    for fund, model, candidate in sorted(candidate_pairs, key=lambda item: (int(item[1].get("priority", 999) or 999), -float(item[1].get("confidence", 0.0) or 0.0), item[0]["fund_code"])):
        candidate_id = candidate["candidate_id"]
        selected = selected_by_id.get(candidate_id)
        if selected:
            validation_notes = list(candidate.get("validation_notes", []) or [])
            validation_notes.append("Selected by portfolio-level optimizer.")
            validation_notes.append(f"Optimizer base objective = {selected.get('base_objective', 0.0):.4f}.")
            tactical_actions.append(
                build_record(
                    report_date,
                    fund,
                    model,
                    validated_action=selected["action"],
                    validated_amount=float(selected.get("amount", 0.0) or 0.0),
                    previous=previous_actions.get(fund["fund_code"]),
                    allocation_plan=allocation_plan,
                    execution_friction=list(candidate.get("execution_friction", []) or []),
                    policy_rule_hits=list(candidate.get("policy_rule_hits", []) or []),
                    constraint_hits=list(candidate.get("constraint_hits", []) or []),
                    validation_notes=validation_notes,
                    cash_note=f"optimizer_remaining_funding={optimization.get('remaining_available_funding', 0.0):.2f}",
                )
            )
            continue

        rejection_reasons = optimization.get("rejection_reasons", {}).get(candidate_id, ["dominated_by_higher_portfolio_objective"])
        validation_notes = list(candidate.get("validation_notes", []) or [])
        validation_notes.append("Candidate not selected by portfolio-level optimizer.")
        validation_notes.extend(rejection_reasons)
        hold_actions.append(
            build_record(
                report_date,
                fund,
                model,
                validated_action="hold",
                validated_amount=0.0,
                previous=previous_actions.get(fund["fund_code"]),
                allocation_plan=allocation_plan,
                execution_friction=list(candidate.get("execution_friction", []) or []),
                policy_rule_hits=list(candidate.get("policy_rule_hits", []) or []),
                constraint_hits=list(candidate.get("constraint_hits", []) or []),
                validation_notes=validation_notes,
                cash_note="candidate_rejected_by_optimizer",
            )
        )

    payload: ValidatedAdvice = {
        "report_date": report_date,
        "generated_at": timestamp_now(),
        "portfolio_name": portfolio["portfolio_name"],
        "risk_profile": strategy["portfolio"]["risk_profile"],
        "daily_max_trade_amount": gross_trade_limit,
        "daily_max_gross_trade_amount": gross_trade_limit,
        "daily_max_net_buy_amount": net_buy_limit,
        "fixed_dca_total": round(fixed_dca_total, 2),
        "remaining_budget_after_validation": round(float(optimization.get("remaining_gross_trade_budget", remaining_gross_trade_budget) or remaining_gross_trade_budget), 2),
        "remaining_gross_trade_budget_after_validation": round(float(optimization.get("remaining_gross_trade_budget", remaining_gross_trade_budget) or remaining_gross_trade_budget), 2),
        "remaining_net_buy_budget_after_validation": round(float(optimization.get("remaining_net_buy_budget", remaining_net_buy_budget) or remaining_net_buy_budget), 2),
        "cash_hub_available": round(available_cash_hub, 2),
        "market_view": advice.get("market_view", {}),
        "cross_fund_observations": advice.get("cross_fund_observations", []),
        "allocation_plan": allocation_plan,
        "strategy_bucket_summary": exposure.get("by_strategy_bucket", []),
        "advice_mode": llm_raw.get("mode", ""),
        "advice_is_fallback": llm_raw.get("mode") == "committee_fallback",
        "advice_is_mock": llm_raw.get("mode") == "mock",
        "decision_source": llm_raw.get("decision_source", ""),
        "committee": llm_raw.get("committee", {}),
        "risk_vetoes": (llm_raw.get("committee", {}) or {}).get("risk_vetoes", []),
        "committee_confidence": (llm_raw.get("committee", {}) or {}).get("committee_confidence", ""),
        "narrative_mode": llm_raw.get("narrative_mode", ""),
        "transport_name": llm_raw.get("transport_name", ""),
        "failed_agents": llm_raw.get("failed_agents", []),
        "optimization_summary": optimization.get("summary", {"mode": "portfolio_search", "candidate_count": 0, "selected_candidate_count": 0}),
        "optimizer_candidates": optimization.get("candidate_diagnostics", []),
        "optimizer_best_combo_metrics": optimization.get("best_combo_metrics", {}),
        "recommendation_deltas": [],
        "dca_actions": dca_actions,
        "tactical_actions": tactical_actions,
        "hold_actions": hold_actions,
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and optimize LLM advice under portfolio constraints.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    payload = build_validated_payload(agent_home, report_date)
    output_path = dump_json(validated_advice_path(agent_home, report_date), payload)
    build_and_write_decisions(agent_home, report_date)
    print(output_path)


if __name__ == "__main__":
    main()
