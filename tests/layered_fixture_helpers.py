"""确定性 synthetic fixture for layered retrieval pack / shadow regression tests.

不读取私人 db 历史；用虚构 fund 代码（保留测试断言所需的 "017641" 作为 fixture 键）复现输入形状。
"""
from __future__ import annotations

REPORT_DATE = "2026-05-22"
GENERATED_AT = "2026-05-22T21:35:00+08:00"

# 15 个持仓，其中 "017641" 为测试断言键，其余为虚构代码
FUND_CODES = ["017641"] + [f"F{i:03d}" for i in range(2, 16)]


def _position(code: str, index: int) -> dict:
    return {
        "fund_code": code,
        "fund_name": f"Synthetic Fund {code}",
        "role": "core" if index % 3 else "satellite",
        "style_group": "balanced",
        "cap_value": 10000.0 * index,
        "allow_trade": True,
        "proxy_symbol": "",
        "proxy_name": "",
        "proxy_type": "",
        "current_value": 10000.0 * index,
        "holding_pnl": 500.0 * index,
        "holding_return_pct": 5.0,
        "holding_units": 1000.0 * index,
        "cost_basis_value": 9500.0 * index,
        "last_valuation_nav": 1.0,
        "last_valuation_date": REPORT_DATE,
        "last_official_nav": 1.0,
        "last_official_nav_date": REPORT_DATE,
        "units_source": "manual",
    }


def _action(code: str, validated_action: str, amount: float, suggestion_id: str) -> dict:
    return {
        "fund_code": code,
        "fund_name": f"Synthetic Fund {code}",
        "strategy_bucket": "core",
        "validated_action": validated_action,
        "validated_amount": amount,
        "suggestion_id": suggestion_id,
        "model_action": validated_action,
        "priority": 1,
        "confidence": 0.8,
        "thesis": f"thesis for {code}",
        "evidence": [],
        "risks": [],
        "agent_support": [],
        "source_signal_ids": [],
        "opposing_signal_ids": [],
        "policy_rule_hits": [],
        "constraint_hits": [],
        "allocation_impact": {},
        "cash_impact": {},
        "change_vs_prev_day": {},
        "execution_friction": {},
        "validation_notes": "",
        "execution_status": "pending",
        "executed_amount": 0.0,
    }


def write_synthetic_inputs(agent, report_date: str = REPORT_DATE, memory_items: list | None = None) -> None:
    portfolio = {
        "portfolio_name": "Synthetic Portfolio",
        "as_of_date": report_date,
        "total_value": 1500000.0,
        "holding_pnl": 50000.0,
        "definition_bootstrapped_at": GENERATED_AT,
        "funds": [_position(code, i) for i, code in enumerate(FUND_CODES, start=1)],
        "state_metadata": {"generated_at": GENERATED_AT},
        "last_valuation_run_date": report_date,
        "last_valuation_generated_at": GENERATED_AT,
    }
    agent.write_json(f"db/portfolio_state/snapshots/{report_date}.json", portfolio)
    agent.write_json("db/portfolio_state/current.json", {**portfolio, "as_of_date": report_date})

    # 2 dca（017641 + F002）+ 13 hold（其余 13 个 fund）
    dca_actions = [
        _action("017641", "scheduled_dca", 200.0, f"{report_date}:017641:dca"),
        _action("F002", "scheduled_dca", 200.0, f"{report_date}:F002:dca"),
    ]
    hold_codes = [c for c in FUND_CODES if c not in {"017641", "F002"}]
    hold_actions = [_action(code, "hold", 0.0, f"{report_date}:{code}:hold") for code in hold_codes]

    validated = {
        "report_date": report_date,
        "generated_at": GENERATED_AT,
        "portfolio_name": "Synthetic Portfolio",
        "risk_profile": "balanced",
        "daily_max_trade_amount": 10000.0,
        "daily_max_gross_trade_amount": 20000.0,
        "daily_max_net_buy_amount": 15000.0,
        "fixed_dca_total": 400.0,
        "remaining_budget_after_validation": 8000.0,
        "remaining_gross_trade_budget_after_validation": 18000.0,
        "remaining_net_buy_budget_after_validation": 13000.0,
        "cash_hub_available": 50000.0,
        "immediately_available_cash": 50000.0,
        "delayed_sell_proceeds": 0.0,
        "market_view": {"regime": "neutral", "risk_bias": "neutral", "key_drivers": [], "portfolio_implications": "", "summary": ""},
        "cross_fund_observations": [],
        "allocation_plan": {"targets_pct": {}, "current_pct": {}, "drift_pct": {}, "rebalance_band_pct": 5.0, "max_single_theme_family_pct": 30.0, "max_high_volatility_theme_pct": 20.0, "status_by_bucket": {}, "bucket_checklist": [], "rebalance_needed": False, "rebalance_suggestions": []},
        "strategy_bucket_summary": [{"name": "core", "value": 100000.0, "weight_pct": 100.0}],
        "advice_mode": "standard",
        "advice_is_fallback": False,
        "advice_is_mock": False,
        "decision_source": "committee",
        "decision_mode": "standard",
        "degradation_mode": "normal",
        "execution_eligible": True,
        "committee": {"decision_source": "committee", "committee_confidence": 0.8, "risk_vetoes": []},
        "committee_decision_bundle": {},
        "risk_vetoes": [],
        "committee_confidence": 0.8,
        "narrative_mode": "standard",
        "transport_name": "synthetic",
        "failed_agents": [],
        "optimization_summary": {"mode": "off", "candidate_count": 0, "selected_candidate_count": 0, "search_space": 0, "feasible_combination_count": 0, "best_objective_score": 0.0, "selected_fund_codes": [], "selected_actions": [], "bucket_pct_before": {}, "bucket_pct_after": {}, "selected_gross_trade": 0.0, "selected_net_buy": 0.0, "selected_sell_proceeds": 0.0, "rejection_reason_counts": {}, "candidate_diagnostics_count": 0, "notes": ""},
        "optimizer_best_combo_metrics": {},
        "recommendation_deltas": [],
        "dca_actions": dca_actions,
        "tactical_actions": [],
        "hold_actions": hold_actions,
    }
    agent.write_json(f"db/validated_advice/{report_date}.json", validated)

    agent.write_json(f"db/llm_context/{report_date}.json", {
        "analysis_date": report_date,
        "mode": "standard",
        "generated_at": GENERATED_AT,
        "portfolio_summary": "",
        "exposure_summary": {},
        "constraints": {},
        "external_reference": {},
        "memory_digest": [],
        "news_digest": [],
        "sentiment_digest": [],
        "event_risks": [],
        "news_query_plan": {},
        "evidence_items": [],
        "fund_evidence_map": {},
        "source_health_summary": {},
        "funds": [
            {
                "fund_code": "017641",
                "quote": {"nav": 1.0, "as_of_date": report_date, "freshness_status": "current"},
            }
        ],
    })
    agent.write_json(f"db/evidence_index/{report_date}.json", {
        "analysis_date": report_date,
        "generated_at": GENERATED_AT,
        "entry_count": 0,
        "entries": [],
        "by_fund_code": {},
        "by_source_role": {},
        "by_evidence_type": {},
        "by_token": {},
    })
    agent.write_json("db/long_memory/exports/all_memory.json", {"updated_at": GENERATED_AT, "items": memory_items or []})
