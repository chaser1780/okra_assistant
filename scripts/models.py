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
    freshness_status: str
    source_url: str
    source_title: str
    entity_id: str
    entity_type: str
    provider: str
    retrieved_at: str
    confidence: float


class NewsItem(TypedDict, total=False):
    code: str
    name: str
    entity_id: str
    entity_type: str
    published_at: str
    as_of: str
    title: str
    summary: str
    source_name: str
    source_role: str
    source_tier: str
    source_url: str
    source_title: str
    url: str
    provider: str
    mapping_mode: str
    evidence_type: str
    impact: str
    relevance_score: float
    sentiment_score: float
    novelty_score: float
    virality_score: float
    historical_significance: float
    crowding_signal: str
    freshness_status: str
    stale: bool
    confidence: float
    tags: list[str]
    theme_family: str
    style_group: str
    retrieved_at: str


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
    source_url: str
    source_title: str
    entity_id: str
    entity_type: str
    provider: str
    confidence: float
    retrieved_at: str


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
    source_url: str
    source_title: str
    entity_id: str
    entity_type: str
    provider: str
    retrieved_at: str


class EvidenceItem(TypedDict, total=False):
    evidence_id: str
    entity_id: str
    entity_type: str
    evidence_type: str
    source_role: str
    source_tier: str
    mapping_mode: str
    provider: str
    source_url: str
    source_title: str
    as_of: str
    published_at: str
    retrieved_at: str
    freshness_status: str
    stale: bool
    summary: str
    confidence: float
    sentiment_score: float
    novelty_score: float
    virality_score: float
    historical_significance: float
    crowding_signal: str
    tags: list[str]
    numeric_payload: dict[str, Any]
    raw_payload: dict[str, Any]


class EvidenceRef(TypedDict, total=False):
    evidence_id: str
    fund_code: str
    role: str
    relevance_score: float
    mapping_mode: str
    source_tier: str
    evidence_type: str


class SourceHealthItem(TypedDict, total=False):
    source_key: str
    source_role: str
    provider: str
    configured: bool
    status: str
    item_count: int
    stale_count: int
    error_count: int
    warning_count: int
    latest_as_of: str
    latest_retrieved_at: str
    notes: list[str]


class MemoryRecord(TypedDict, total=False):
    memory_id: str
    memory_type: str
    scope: str
    entity_keys: list[str]
    text: str
    provenance: dict[str, Any]
    base_date: str
    expires_on: str
    promotion_level: str
    approved_by: str
    confidence: float
    status: str
    applies_to: str
    reason: str
    source: str


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
    source_url: str
    source_title: str
    provider: str
    as_of: str
    retrieved_at: str


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
    fund_profile: FundProfile
    recent_news: list[NewsItem]
    evidence_refs: list[EvidenceRef]


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
    evidence_items: list[EvidenceItem]
    fund_evidence_map: dict[str, list[EvidenceRef]]
    source_health_summary: list[SourceHealthItem]
    funds: list[FundContextItem]


class OptimizationSummary(TypedDict, total=False):
    mode: str
    candidate_count: int
    selected_candidate_count: int
    search_space: int
    feasible_combination_count: int
    best_objective_score: float
    selected_fund_codes: list[str]
    selected_actions: list[dict[str, Any]]
    bucket_pct_before: dict[str, float]
    bucket_pct_after: dict[str, float]
    selected_gross_trade: float
    selected_net_buy: float
    selected_sell_proceeds: float
    rejection_reason_counts: dict[str, int]
    candidate_diagnostics_count: int
    notes: list[str]


class SignalCard(TypedDict, total=False):
    signal_id: str
    agent_name: str
    signal_type: str
    fund_code: str
    direction: str
    horizon: str
    thesis: str
    catalysts: list[str]
    risks: list[str]
    invalidation: str
    portfolio_impact: str
    action_bias: str
    supporting_evidence_ids: list[str]
    opposing_evidence_ids: list[str]
    sentiment_relevance: float
    novelty_relevance: float
    crowding_signal: str
    confidence: float
    comment: str
    abstain_reason: str


class DecisionCard(TypedDict, total=False):
    decision_id: str
    agent_name: str
    fund_code: str
    proposed_action: str
    size_bucket: str
    supporting_signal_ids: list[str]
    opposing_signal_ids: list[str]
    why_now: str
    why_not_more: str
    invalidate_when: str
    risk_decision: str
    manager_notes: str
    confidence: float
    priority: int


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
    supporting_evidence_ids: list[str]
    opposing_evidence_ids: list[str]
    sentiment_relevance: float
    novelty_relevance: float


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
    signal_cards: list[SignalCard]
    decision_cards: list[DecisionCard]
    no_trade_list: list[dict[str, Any]]
    watchouts: list[str]


class AgentRecord(TypedDict, total=False):
    status: str
    error: str
    output: AgentOutput


class DecisionTrace(TypedDict, total=False):
    fund_code: str
    supporting_signal_ids: list[str]
    opposing_signal_ids: list[str]
    decision_card_ids: list[str]
    constraint_hits: list[str]


class ConstraintImpact(TypedDict, total=False):
    rule_name: str
    impact_type: str
    before_action: str
    after_action: str
    before_amount: float
    after_amount: float
    reason: str


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
    source_signal_ids: list[str]
    opposing_signal_ids: list[str]
    decision_trace: DecisionTrace


class FinalAdvice(TypedDict, total=False):
    market_view: dict[str, Any]
    fund_decisions: list[FinalFundDecision]
    cross_fund_observations: list[str]


class RecommendationDelta(TypedDict, total=False):
    fund_code: str
    fund_name: str
    prev_action: str
    prev_amount: float
    new_action: str
    new_amount: float
    delta_reason: str
    reason_category: str
    new_evidence_ids: list[str]
    removed_evidence_ids: list[str]
    memory_ids: list[str]
    constraint_hits: list[str]


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
    source_signal_ids: list[str]
    opposing_signal_ids: list[str]
    policy_rule_hits: list[str]
    constraint_hits: list[str]
    allocation_impact: str
    cash_impact: str
    change_vs_prev_day: dict[str, Any]
    execution_friction: list[str]
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
    decision_source: str
    narrative_mode: str
    transport_name: str
    failed_agents: list[dict[str, Any]]
    optimization_summary: OptimizationSummary
    optimizer_candidates: list[dict[str, Any]]
    optimizer_best_combo_metrics: dict[str, Any]
    recommendation_deltas: list[RecommendationDelta]
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
    records: list[MemoryRecord]
    strategic_memory: list[MemoryRecord]
    permanent_memory: list[MemoryRecord]
    user_confirmed_memory: list[MemoryRecord]
