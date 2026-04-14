from __future__ import annotations

import argparse

from common import dump_json, ensure_layout, llm_advice_path, llm_raw_path, load_json, load_portfolio, load_strategy, resolve_agent_home, resolve_date, timestamp_now, validated_advice_path
from models import FinalAdvice, PortfolioFund, PortfolioState, ValidatedAction, ValidatedAdvice
from portfolio_exposure import STRATEGY_BUCKET_LABELS, analyze_portfolio_exposure, infer_strategy_bucket, safe_float
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
        "validation_notes": [reason],
        "execution_status": "not_applicable",
        "executed_amount": 0.0,
    }


def suggestion_id(report_date: str, fund_code: str, validated_action: str) -> str:
    return f"{report_date}:{fund_code}:{validated_action}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and clamp LLM advice under portfolio constraints.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    portfolio: PortfolioState = load_portfolio(agent_home)
    strategy = load_strategy(agent_home)
    advice: FinalAdvice = load_json(llm_advice_path(agent_home, report_date))
    llm_raw = load_json(llm_raw_path(agent_home, report_date)) if llm_raw_path(agent_home, report_date).exists() else {}
    constraint_map = build_trade_constraints(agent_home, portfolio, report_date)
    exposure = analyze_portfolio_exposure(portfolio, strategy)
    allocation_plan = exposure.get("allocation_plan", {})
    current_bucket_pct = allocation_plan.get("current_pct", {})
    target_bucket_pct = allocation_plan.get("targets_pct", {})
    rebalance_band_pct = float(allocation_plan.get("rebalance_band_pct", 5.0) or 5.0)
    total_value = float(exposure.get("total_value", 0.0) or 0.0)

    decisions = {item["fund_code"]: item for item in advice.get("fund_decisions", [])}
    gross_trade_limit = float(strategy["portfolio"].get("daily_max_gross_trade_amount", strategy["portfolio"]["daily_max_trade_amount"]))
    net_buy_limit = float(strategy["portfolio"].get("daily_max_net_buy_amount", strategy["portfolio"]["daily_max_trade_amount"]))
    dca_actions = []
    hold_actions = []
    candidate_actions = []

    fixed_dca_total = 0.0
    available_cash_hub = 0.0
    for fund in portfolio["funds"]:
        if fund["role"] == "core_dca":
            amount = float(fund.get("fixed_daily_buy_amount", strategy["core_dca"]["amount_per_fund"]))
            fixed_dca_total += amount
            dca_actions.append(
                {
                    "fund_code": fund["fund_code"],
                    "fund_name": fund["fund_name"],
                    "strategy_bucket": infer_strategy_bucket(fund),
                    "validated_action": "scheduled_dca",
                    "validated_amount": amount,
                    "suggestion_id": suggestion_id(report_date, fund["fund_code"], "scheduled_dca"),
                    "model_action": decisions.get(fund["fund_code"], {}).get("action", "scheduled_dca"),
                    "priority": decisions.get(fund["fund_code"], {}).get("priority", 0),
                    "confidence": decisions.get(fund["fund_code"], {}).get("confidence", 1.0),
                    "thesis": "按固定定投规则执行。",
                    "evidence": [
                        f"{fund['fund_name']} 属于长期核心仓，当前只执行固定定投。",
                        "core_dca 规则不允许额外主动加仓或短线方向交易。",
                        f"本次定投金额按既定规则执行：{amount:.2f} 元。",
                    ],
                    "risks": [
                        "T+2/T+3 确认基金仍可能面临短线时点不佳。",
                        "执行后短期净值波动不改变其长期核心仓定位。",
                    ],
                    "agent_support": decisions.get(fund["fund_code"], {}).get("agent_support", []),
                    "validation_notes": ["core_dca 仅允许固定定投，不允许额外加仓。"],
                    "execution_status": "pending",
                    "executed_amount": 0.0,
                }
            )
        elif fund["role"] == "cash_hub":
            floor = float(strategy["portfolio"]["cash_hub_floor"])
            locked_amount = max(float(fund.get("locked_amount", 0.0)), float(constraint_map.get(fund["fund_code"], {}).get("locked_amount", 0.0)))
            available_cash_hub = max(0.0, float(fund["current_value"]) - floor - locked_amount)
            hold_actions.append(default_hold(fund, f"资金存储仓保留底仓，当前可调拨参考金额 {available_cash_hub:.2f} 元。"))
        elif fund["role"] == "fixed_hold":
            hold_actions.append(default_hold(fund, "固定持有仓，不纳入日常调仓。"))
        else:
            model = decisions.get(
                fund["fund_code"],
                {
                    "action": "hold",
                    "suggest_amount": 0,
                    "priority": 999,
                    "confidence": 0.0,
                    "thesis": "模型未给出明确动作，默认观望。",
                    "evidence": [],
                    "risks": [],
                    "agent_support": [],
                },
            )
            candidate_actions.append({"fund": fund, "model": model})

    remaining_gross_trade_budget = max(0.0, gross_trade_limit - fixed_dca_total)
    remaining_net_buy_budget = max(0.0, net_buy_limit - fixed_dca_total)
    available_funding = available_cash_hub
    max_actions = int(strategy["tactical"]["max_actions_per_day"])
    tactical_actions = []

    for item in sorted(candidate_actions, key=lambda x: (int(x["model"].get("priority", 999)), -float(x["model"].get("confidence", 0.0)))):
        fund = item["fund"]
        model = item["model"]
        action = model.get("action", "hold")
        validation = []
        final_action = "hold"
        final_amount = 0.0
        current_value = float(fund["current_value"])
        available_to_sell = float(constraint_map.get(fund["fund_code"], {}).get("available_to_sell", current_value))
        cap_value = float(fund.get("cap_value", strategy["tactical"]["default_cap_value"]))
        strategy_bucket = infer_strategy_bucket(fund)

        if action == "add":
            room = max(0.0, cap_value - current_value)
            amount = normalize_amount(float(model.get("suggest_amount", 0.0)), min(room, available_funding, remaining_gross_trade_budget, remaining_net_buy_budget))
            if amount > 0 and total_value > 0 and strategy_bucket == "tactical_short_term":
                projected_bucket_pct = round((safe_float(current_bucket_pct.get(strategy_bucket, 0.0)) * total_value / 100.0 + amount) / total_value * 100, 2)
                target_pct = safe_float(target_bucket_pct.get(strategy_bucket, 0.0))
                if target_pct > 0 and projected_bucket_pct > target_pct + rebalance_band_pct:
                    validation.append(
                        f"{STRATEGY_BUCKET_LABELS.get(strategy_bucket, strategy_bucket)} 交易后约为 {projected_bucket_pct:.2f}%，"
                        f"高于目标 {target_pct:.2f}% 与带宽 {rebalance_band_pct:.2f}%，本次加仓被组合层策略压制。"
                    )
                    amount = 0.0
            if amount > 0 and len(tactical_actions) < max_actions:
                final_action = "add"
                final_amount = amount
                available_funding -= amount
                remaining_gross_trade_budget -= amount
                remaining_net_buy_budget -= amount
            else:
                validation.append("加仓金额被仓位上限、资金仓余额、总交易额度或净买入额度约束裁剪为 0。")
        elif action in {"reduce", "switch_out"}:
            amount = normalize_amount(float(model.get("suggest_amount", 0.0)), available_to_sell, allow_full_exit=bool(strategy["portfolio"]["allow_full_exit"]))
            if amount > 0 and len(tactical_actions) < max_actions and remaining_gross_trade_budget >= amount:
                final_action = action
                final_amount = amount
                available_funding += amount
                remaining_gross_trade_budget -= amount
            else:
                validation.append("减仓金额被最小执行粒度、持仓金额或总交易额度约束裁剪为 0。")
            if constraint_map.get(fund["fund_code"], {}).get("locked_amount", 0.0) > 0:
                validation.extend(constraint_map[fund["fund_code"]]["notes"])
        else:
            validation.append("模型建议为观望，或已被校验器改为观望。")

        record = {
            "suggestion_id": suggestion_id(report_date, fund["fund_code"], final_action if final_action != "hold" else action),
            "fund_code": fund["fund_code"],
            "fund_name": fund["fund_name"],
            "strategy_bucket": strategy_bucket,
            "validated_action": final_action,
            "validated_amount": final_amount,
            "model_action": action,
            "priority": int(model.get("priority", 999)),
            "confidence": clamp(float(model.get("confidence", 0.0)), 0.0, 1.0),
            "thesis": model.get("thesis", ""),
            "evidence": model.get("evidence", []),
            "risks": model.get("risks", []),
            "agent_support": model.get("agent_support", []),
            "validation_notes": validation,
            "execution_status": "pending" if final_action != "hold" else "not_applicable",
            "executed_amount": 0.0,
        }
        if final_action == "hold":
            hold_actions.append(record)
        else:
            tactical_actions.append(record)

    payload: ValidatedAdvice = {
        "report_date": report_date,
        "generated_at": timestamp_now(),
        "portfolio_name": portfolio["portfolio_name"],
        "risk_profile": strategy["portfolio"]["risk_profile"],
        "daily_max_trade_amount": gross_trade_limit,
        "daily_max_gross_trade_amount": gross_trade_limit,
        "daily_max_net_buy_amount": net_buy_limit,
        "fixed_dca_total": round(fixed_dca_total, 2),
        "remaining_budget_after_validation": round(remaining_gross_trade_budget, 2),
        "remaining_gross_trade_budget_after_validation": round(remaining_gross_trade_budget, 2),
        "remaining_net_buy_budget_after_validation": round(remaining_net_buy_budget, 2),
        "cash_hub_available": round(available_cash_hub, 2),
        "market_view": advice.get("market_view", {}),
        "cross_fund_observations": advice.get("cross_fund_observations", []),
        "allocation_plan": allocation_plan,
        "strategy_bucket_summary": exposure.get("by_strategy_bucket", []),
        "advice_mode": llm_raw.get("mode", ""),
        "advice_is_fallback": llm_raw.get("mode") == "committee_fallback",
        "advice_is_mock": llm_raw.get("mode") == "mock",
        "transport_name": llm_raw.get("transport_name", ""),
        "failed_agents": llm_raw.get("failed_agents", []),
        "dca_actions": dca_actions,
        "tactical_actions": tactical_actions,
        "hold_actions": hold_actions,
    }
    output_path = dump_json(validated_advice_path(agent_home, report_date), payload)
    print(output_path)


if __name__ == "__main__":
    main()
