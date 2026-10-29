"""本域合成 fixture：为 debate/ticket shadow 测试提供自包含最小 portfolio/llm_context/validated。
不拷贝用户真实 db。与 promoted chain 测试同构。"""

from __future__ import annotations

PORTFOLIO_FUNDS = [
    {"fund_code": "DCA1", "fund_name": "Core DCA", "role": "core_dca", "style_group": "core",
     "current_value": 100.0, "allow_trade": True, "fixed_daily_buy_amount": 25.0,
     "holding_units": 100.0, "last_valuation_nav": 1.0, "units_source": "stored"},
    {"fund_code": "CASH", "fund_name": "Cash", "role": "cash_hub", "style_group": "cash",
     "current_value": 500.0, "allow_trade": True, "holding_units": 500.0,
     "last_valuation_nav": 1.0, "units_source": "stored"},
    {"fund_code": "TADD", "fund_name": "Add Target", "role": "tactical", "style_group": "growth_rotation",
     "current_value": 200.0, "cap_value": 800.0, "allow_trade": True,
     "holding_units": 100.0, "last_valuation_nav": 2.0, "units_source": "stored"},
    {"fund_code": "TRED", "fund_name": "Reduce Target", "role": "tactical", "style_group": "industrial_metal",
     "current_value": 250.0, "cap_value": 800.0, "allow_trade": True,
     "holding_units": 125.0, "last_valuation_nav": 2.0, "units_source": "stored"},
]


def write_simulation_fixture(agent, date: str) -> None:
    """写最小自包含输入；agent 需有 write_json。"""
    agent.write_json("config/benchmark_mappings.json", {"fund_benchmarks": {}})
    portfolio = {"portfolio_name": "test", "as_of_date": date, "total_value": 1050.0,
                 "funds": [dict(f) for f in PORTFOLIO_FUNDS]}
    agent.write_json("db/portfolio_state/current.json", portfolio)
    agent.write_json(f"db/portfolio_state/snapshots/{date}.json", portfolio)
    agent.write_json(f"db/daily_scores/{date}.json", {
        "report_date": date, "generated_at": f"{date}T14:00:00+08:00",
        "funds": [
            {"code": "TADD", "name": "Add Target", "score": 88.0, "action": "add", "confidence": 0.84, "reasons": ["strong"], "risk_flags": []},
            {"code": "TRED", "name": "Reduce Target", "score": 24.0, "action": "avoid", "confidence": 0.8, "reasons": ["weak"], "risk_flags": ["drawdown"]},
        ]})
    agent.write_json(f"db/llm_context/{date}.json", {
        "analysis_date": date, "generated_at": f"{date}T14:00:00+08:00",
        "funds": [
            {"fund_code": "DCA1", "fund_name": "Core DCA", "role": "core_dca"},
            {"fund_code": "CASH", "fund_name": "Cash", "role": "cash_hub"},
            {"fund_code": "TADD", "fund_name": "Add Target", "role": "tactical",
             "quote": {"day_change_pct": 1.2, "as_of_date": "2026-05-29"},
             "recent_news": [{"title": "p", "summary": "p", "impact": "positive", "published_at": f"{date}T10:00:00+08:00"}],
             "intraday_proxy": {"change_pct": 2.1, "trade_date": date}},
            {"fund_code": "TRED", "fund_name": "Reduce Target", "role": "tactical",
             "quote": {"day_change_pct": -2.5, "as_of_date": "2026-05-29"},
             "recent_news": [{"title": "n", "summary": "n", "impact": "negative", "published_at": f"{date}T10:00:00+08:00"}],
             "intraday_proxy": {"change_pct": -1.7, "trade_date": date}},
        ], "evidence_items": []})
    agent.write_json(f"db/evidence_index/{date}.json", {"items": []})
    agent.write_json(f"db/validated_advice/{date}.json", {
        "report_date": date, "tactical_actions": [], "dca_actions": [], "hold_actions": [],
        "market_view": {"summary": "synthetic"}})
