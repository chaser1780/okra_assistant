from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class QuoteSnapshot(TypedDict, total=False):
    code: str
    name: str
    category: str
    benchmark: str
    nav: float
    cumulative_nav: float
    day_change_pct: float
    week_change_pct: float
    month_change_pct: float
    as_of_date: str
    requested_date: str
    date_match_type: str
    freshness_label: str
    freshness_business_day_gap: int | None
    freshness_is_acceptable: bool
    freshness_is_delayed: bool
    provider: str
    retrieved_at: str


class NewsItem(TypedDict, total=False):
    code: str
    name: str
    published_at: str
    title: str
    summary: str
    source_name: str
    url: str
    impact: str
    relevance_score: float


class ProxySnapshot(TypedDict, total=False):
    proxy_fund_code: str
    proxy_fund_name: str
    proxy_name: str
    proxy_type: str
    style_group: str
    change_pct: float
    trade_date: str
    trade_time: str
    stale: bool
    freshness_status: str
    freshness_label: str
    freshness_business_day_gap: int | None


class EstimateSnapshot(TypedDict, total=False):
    fund_code: str
    fund_name: str
    category: str
    estimate_nav: float | None
    estimate_change_pct: float | None
    estimate_time: str | None
    estimate_date: str | None
    estimate_freshness_status: str
    estimate_freshness_label: str
    estimate_freshness_business_day_gap: int | None
    official_nav: float | None
    official_nav_date: str | None
    official_nav_freshness_status: str
    official_nav_freshness_label: str
    official_nav_freshness_business_day_gap: int | None
    stale: bool
    confidence: float
    status: str


class PortfolioFund(TypedDict, total=False):
    fund_code: str
    fund_name: str
    role: str
    strategy_bucket: str
    style_group: str
    current_value: float
    holding_pnl: float
    holding_return_pct: float
    cap_value: float
    allow_trade: bool
    locked_amount: float
    fixed_daily_buy_amount: float
    allow_extra_buys: bool
    proxy_symbol: str
    proxy_name: str
    proxy_type: str
    holding_units: float
    last_valuation_nav: float
    last_valuation_date: str
    last_official_nav: float
    last_official_nav_date: str
    units_source: str
    cost_basis_value: float
    min_hold_days: int
    redeem_settlement_days: int
    market: str
    category: str
    fund_profile: NotRequired["FundProfile"]
    quote: NotRequired[QuoteSnapshot]
    intraday_proxy: NotRequired[ProxySnapshot]
    estimated_nav: NotRequired[EstimateSnapshot]
    recent_news: NotRequired[list[NewsItem]]


class FundProfile(TypedDict, total=False):
    fund_code: str
    fund_name: str
    inception_date: str | None
    fund_age_years: float | None
    fund_manager: str | None
    fund_type: str | None
    management_company: str | None
    fund_scale_billion: float | None
    management_fee_rate: float | None
    custody_fee_rate: float | None
    category: str
    benchmark: str
    risk_level: str
    manager_tenure_years: float | None
    fund_scale_bucket: str
    fee_level: str
    style_drift_risk: str
    slow_factor_summary: list[str]
    profile_source: str
    status: str


class PortfolioState(TypedDict, total=False):
    portfolio_name: str
    as_of_date: str
    total_value: float
    holding_pnl: float
    last_valuation_run_date: str
    last_valuation_generated_at: str
    state_metadata: dict[str, Any]
    funds: list[PortfolioFund]


class FundContextItem(TypedDict, total=False):
    fund_code: str
    fund_name: str
    role: str
    strategy_bucket: str
    style_group: str
    current_value: float
    holding_pnl: float
    holding_return_pct: float
    cap_value: float
    allow_trade: bool
    locked_amount: float
    fixed_daily_buy_amount: float
    quote: QuoteSnapshot
    intraday_proxy: ProxySnapshot
    estimated_nav: EstimateSnapshot
    recent_news: list[NewsItem]


class PortfolioContextSummary(TypedDict, total=False):
    portfolio_name: str
    total_value: float
    holding_pnl: float
    risk_profile: str
    role_counts: dict[str, int]
    all_intraday_proxies_stale: bool
    all_estimates_stale: bool
    stale_proxy_count: int
    stale_estimate_count: int
    delayed_official_nav_count: int


class LlmContext(TypedDict, total=False):
    analysis_date: str
    mode: str
    generated_at: str
    portfolio_summary: PortfolioContextSummary
    exposure_summary: dict[str, Any]
    constraints: dict[str, Any]
    external_reference: dict[str, Any]
    memory_digest: dict[str, Any]
    funds: list[FundContextItem]


class AgentFundView(TypedDict, total=False):
    fund_code: str
    direction: str
    horizon: str
    thesis: str
    catalysts: list[str]
    risks: list[str]
    invalidation: str
    portfolio_impact: str
    action_bias: str
    comment: str


class AgentOutput(TypedDict, total=False):
    agent_name: str
    mode: str
    summary: str
    confidence: float
    evidence_strength: str
    data_freshness: str
    abstain: bool
    missing_info: list[str]
    key_points: list[str]
    portfolio_view: dict[str, Any]
    fund_views: list[AgentFundView]
    watchouts: list[str]


class AgentRecord(TypedDict, total=False):
    status: str
    error: str
    output: AgentOutput


class FinalFundDecision(TypedDict, total=False):
    fund_code: str
    action: str
    suggest_amount: float
    priority: int
    confidence: float
    thesis: str
    evidence: list[str]
    risks: list[str]
    agent_support: list[str]


class FinalAdvice(TypedDict, total=False):
    market_view: dict[str, Any]
    fund_decisions: list[FinalFundDecision]
    cross_fund_observations: list[str]


class ValidatedAction(TypedDict, total=False):
    suggestion_id: str
    fund_code: str
    fund_name: str
    strategy_bucket: str
    validated_action: str
    validated_amount: float
    model_action: str
    priority: int
    confidence: float
    thesis: str
    evidence: list[str]
    risks: list[str]
    agent_support: list[str]
    validation_notes: list[str]
    execution_status: str
    executed_amount: float
    linked_trade_date: str
    trade_action: str


class ValidatedAdvice(TypedDict, total=False):
    report_date: str
    generated_at: str
    portfolio_name: str
    risk_profile: str
    daily_max_trade_amount: float
    daily_max_gross_trade_amount: float
    daily_max_net_buy_amount: float
    fixed_dca_total: float
    remaining_budget_after_validation: float
    remaining_gross_trade_budget_after_validation: float
    remaining_net_buy_budget_after_validation: float
    cash_hub_available: float
    market_view: dict[str, Any]
    cross_fund_observations: list[str]
    allocation_plan: dict[str, Any]
    strategy_bucket_summary: list[dict[str, Any]]
    advice_mode: str
    advice_is_fallback: bool
    advice_is_mock: bool
    transport_name: str
    failed_agents: list[dict[str, Any]]
    dca_actions: list[ValidatedAction]
    tactical_actions: list[ValidatedAction]
    hold_actions: list[ValidatedAction]


class RealtimeItem(TypedDict, total=False):
    fund_code: str
    fund_name: str
    role: str
    style_group: str
    category: str
    base_position_value: float
    cost_basis_value: float
    holding_units: float | None
    unit_source: str
    unit_confidence: float
    effective_nav: float | None
    official_nav: float | None
    official_nav_date: str | None
    official_nav_freshness_status: str
    official_nav_freshness_label: str
    estimate_nav: float | None
    estimate_change_pct: float | None
    estimate_freshness_status: str
    estimate_freshness_label: str
    estimate_freshness_business_day_gap: int | None
    proxy_change_pct: float | None
    proxy_freshness_status: str
    proxy_freshness_label: str
    proxy_freshness_business_day_gap: int | None
    estimate_policy_allowed: bool
    proxy_policy_allowed: bool
    effective_change_pct: float | None
    estimated_intraday_pnl_pct: float
    estimated_position_value: float
    estimated_intraday_pnl_amount: float
    estimated_total_pnl_amount: float
    estimated_total_return_pct: float
    divergence_pct: float | None
    freshness_age_business_days: int
    position_weight_pct: float
    anomaly_score: float
    confidence: float
    mode: str
    reason: str
    stale: bool
    estimate_time: str | None
    proxy_time: str | None
    quote_day_change_pct: float | None


class RealtimeSnapshot(TypedDict, total=False):
    report_date: str
    generated_at: str
    market_timestamp: str
    realtime_policy: dict[str, Any]
    totals: dict[str, float]
    items: list[RealtimeItem]


class ReviewMemory(TypedDict, total=False):
    updated_at: str
    lessons: list[dict[str, Any]]
    review_history: list[dict[str, Any]]
    bias_adjustments: list[dict[str, Any]]
    agent_feedback: list[dict[str, Any]]
