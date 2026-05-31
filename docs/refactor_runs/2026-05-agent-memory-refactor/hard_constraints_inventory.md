# Hard Constraints Inventory

Status: code-derived inventory for Phase 0 schema lock.

Reviewed code:

- `scripts/promoted_advice_guardrails.py`
- `scripts/portfolio_optimizer.py`
- `scripts/execution_sync.py`
- `scripts/trade_lifecycle.py`
- `scripts/portfolio_state.py`
- `scripts/trade_constraints.py`
- `config/strategy.toml`
- related tests under `tests/`

Purpose:

- Preserve existing deterministic safety behavior during the agent/memory
  refactor.
- Map current validator, optimizer, execution, reconciliation, and state rules
  into future action-ticket `hard_guardrail_results`.
- Keep adaptive policies and strategy skills from becoming hidden hard rules.

## Migration Rule

Hard constraints remain deterministic code. The new action-ticket chain can
explain them, map them, and display them, but it must not replace them with LLM
judgment or long-memory policy.

Allowed action-ticket mapping:

- `pass`: rule checked and allowed the action.
- `adjust`: rule deterministically changed amount, timing, status, or
  eligibility.
- `block`: rule deterministically prevented the action.
- `not_checked`: rule not applicable or not enough input exists.

Forbidden mapping:

- A soft adaptive policy cannot produce `block`.
- A strategy skill cannot edit a hard rule.
- A LangGraph node cannot bypass current validation before Phase 8 promotion.

## Constraint Table

| Rule | Location | Inputs | Behavior | Current outputs | Future guardrail mapping | Test status / additions |
|---|---|---|---|---|---|---|
| Trade amount non-negative, ceiling, and 100 CNY granularity | `scripts/promoted_advice_guardrails.py` `_normalise_amount()` | `suggest_amount`, `ceiling`, `allow_full_exit` | Adjusts amount into allowed range; below 100 becomes 0; otherwise rounds down to 100; full exit can use exact sellable amount | `validated_amount`, `validation_notes` | `guardrail:amount:normalization` | Existing clamp/full-exit tests; add `99/100/199/200` boundary tests |
| Fund-level add capacity | `scripts/promoted_advice_guardrails.py` candidate building | `action=add`, `current_value`, `cap_value`, `default_cap_value`, `suggest_amount` | Blocks or adjusts add amount by available room; normalized zero becomes hold | `constraint_hits=fund_capacity_or_granularity`, `validated_action`, `validated_amount` | `guardrail:fund:capacity` | Add current value at or above cap test |
| Sellable amount and recent-buy lock | `scripts/trade_constraints.py`, `scripts/promoted_advice_guardrails.py` | `min_hold_days`, actual trades, `current_value`, `suggest_amount` | Locks recent buy amount; sells only from `available_to_sell`; insufficient sell amount becomes hold | `locked_amount`, `available_to_sell`, `constraint_hits=locked_amount/sellable_amount_or_granularity` | `guardrail:sell:available_amount` | Existing lock tests; add buy-then-partial-sell lock netting test |
| Core DCA fixed schedule | `scripts/promoted_advice_guardrails.py`, `config/strategy.toml` | `role=core_dca`, `fixed_daily_buy_amount`, `core_dca.amount_per_fund` | Ignores free-form model action and emits `scheduled_dca`; consumes gross/net buy budgets | `dca_actions`, `fixed_dca_total`, `constraint_hits=core_dca_fixed_rule` | `guardrail:dca:fixed_schedule` | Existing DCA preservation tests; add DCA consumes whole budget test |
| Cash hub floor | `scripts/promoted_advice_guardrails.py`, `config/strategy.toml` | `cash_hub.current_value`, `cash_hub_floor`, locked/pending amounts | Cash hub is hold; available funding is cash above floor; adds cannot exceed available funding | `cash_hub_available`, `immediately_available_cash`, `cash_impact`, optimizer `cash_funding` rejection | `guardrail:cash:floor` | Existing cash/unsettled tests; add cash below floor rejects all adds |
| Fixed-hold funds do not participate in daily tactics | `scripts/promoted_advice_guardrails.py` | `role=fixed_hold` | Forced hold and skipped by optimizer | `hold_actions`, `validation_notes` | `guardrail:role:fixed_hold` | Add model add/reduce on fixed_hold remains hold |
| Promoted debate fund-level risk veto and execution eligibility | `scripts/promoted_advice_guardrails.py` | promoted fund decisions, `risk_veto`, `execution_eligible`, `constraint_notes` | Forced hold before optimizer | `policy_rule_hits=promoted_fund_gate`, `constraint_hits=risk_veto/execution_not_eligible` | `guardrail:promoted:fund_gate` | Existing risk-veto test; add `execution_eligible=false` without veto |
| Promoted debate global blocked or hold-only mode | `scripts/promoted_advice_guardrails.py` | promoted decision mode, fund role | Tactical funds forced hold when mode is `blocked` or `hold_only` | `policy_rule_hits=promoted_decision_gate`, `validation_notes`, `decision_mode` | `guardrail:promoted:global_mode` | Add `hold_only` all-tactical hold test; explicitly decide DCA behavior |
| Daily gross trade budget | `scripts/promoted_advice_guardrails.py`, `scripts/portfolio_optimizer.py`, `config/strategy.toml` | `daily_max_gross_trade_amount`, `daily_max_trade_amount`, `fixed_dca_total`, candidate amounts | Rejects combinations whose total gross trade exceeds remaining budget | `remaining_gross_trade_budget_after_validation`, optimizer rejection reason `gross_trade_budget` | `guardrail:budget:gross_trade` | Add DCA fills gross budget then tactical rejected |
| Daily net buy budget | `scripts/promoted_advice_guardrails.py`, `scripts/portfolio_optimizer.py`, `config/strategy.toml` | `daily_max_net_buy_amount`, `fixed_dca_total`, combination `net_buy` | Rejects combinations whose net buy exceeds remaining net buy budget | `remaining_net_buy_budget_after_validation`, optimizer rejection reason `net_buy_budget` | `guardrail:budget:net_buy` | Add sell+buy combo only limits net buy |
| Unsettled sell proceeds cannot fund same-day adds | `scripts/trade_constraints.py`, `scripts/promoted_advice_guardrails.py`, `scripts/portfolio_optimizer.py` | unsettled `sell/convert_out`, status, trade date, `delayed_sell_proceeds` | Adds use immediate available cash only; combinations relying on unsettled proceeds are rejected or annotated | `delayed_sell_proceeds`, rejection reasons `delayed_sell_proceeds/cash_funding` | `guardrail:cash:unsettled_proceeds` | Existing unsettled tests; add settled/canceled/failed exclusion |
| Max tactical actions per day | `scripts/promoted_advice_guardrails.py`, `scripts/portfolio_optimizer.py`, `config/strategy.toml` | `tactical.max_actions_per_day`, candidates | Optimizer searches only combinations within max action count | `optimization_summary.selected_candidate_count`, `selected_actions` | `guardrail:action:max_count` | Existing candidate competition tests; add max_actions 0/1 boundaries |
| Tactical short-term allocation band | `scripts/portfolio_optimizer.py`, `config/strategy.toml` | `current_bucket_pct`, `target_bucket_pct`, `rebalance_band_pct` | Rejects combinations that cross band or worsen an already out-of-band state | rejection reasons `allocation_band_upper/lower/allocation_worsens_*`, `bucket_pct_before/after` | `guardrail:allocation:tactical_band` | Add upper-band crossing and current-overweight worsening tests |
| Theme-family concentration | `scripts/portfolio_optimizer.py`, `config/strategy.toml` | `theme_family`, current/new theme weight, `max_single_theme_family_pct` | Rejects adds that worsen an already overweight theme family | `theme_family_worsens_overweight:*` | `guardrail:concentration:theme_family` | Existing overweight test; clarify whether first crossing should also block |
| High-volatility theme exposure | `scripts/portfolio_optimizer.py`, `config/strategy.toml` | high-volatility theme family set, `max_high_volatility_theme_pct` | Rejects adds that worsen already-overweight high-volatility exposure | `high_volatility_theme_worsens_overweight` | `guardrail:concentration:high_volatility` | Add multi-theme aggregate-overweight test |
| Top 3 fund concentration | `scripts/promoted_advice_guardrails.py`, `scripts/portfolio_optimizer.py` | current/new fund weights, hard-coded `top3_fund_limit_pct=45.0` | Rejects adds that exceed 45% top-3 or worsen existing top-3 overweight | `top3_fund_limit`, `top3_fund_worsens_overweight` | `guardrail:concentration:top3_funds` | Add 45% boundary and overweight reduction allowed tests |
| Single management company concentration | `scripts/promoted_advice_guardrails.py`, `scripts/portfolio_optimizer.py` | `management_company`, current/new company weight, hard-coded `25.0` | Rejects adds that exceed 25% company concentration or worsen existing overweight | `single_management_company_limit:*`, `management_company_worsens_overweight:*` | `guardrail:concentration:management_company` | Add unknown company skip and same-company multi-add tests |
| Trade lifecycle cutoff and business-day roll | `scripts/trade_lifecycle.py` | `trade_date`, `trade_time`, cutoff, confirm/settlement days | Rolls effective trade date after cutoff/weekend; derives confirm/settlement/status | `effective_trade_date`, `confirm_date`, `settlement_date`, `lifecycle.status` | `guardrail:execution:lifecycle_calendar` | Existing cutoff/weekend tests; add custom cutoff and fund-class differences |
| Actual operation type whitelist | `scripts/execution_sync.py` | `operation_type/action` | Rejects operations outside `buy/sell/dca/dividend/fee/cancel` | Raises `ValueError`; no trade file write | `guardrail:execution:operation_type` | Add no file write on illegal operation |
| Execution deviation is annotation-only | `scripts/execution_sync.py` | linked suggestion, validated action, actual operation/amount | Labels unlinked/opposite/partial/amount delta/matched; does not affect advice accuracy | `execution_deviation`, `deviations`, `affects_advice_accuracy=false` | `guardrail:execution:deviation_annotation` | Existing write tests; add opposite and amount-delta cases |
| Pending settlement does not directly mutate portfolio | `scripts/execution_sync.py` | status, confirm date, settlement date, lifecycle | Writes pending record; applies to portfolio only after settlement | `pending_confirmations.json`, `portfolio_applied_count`, `pending_count` | `guardrail:execution:pending_settlement` | Existing pending settlement test |
| Settlement idempotency | `scripts/execution_sync.py` | trade id/conversion id, event path, `portfolio_applied_at` | Skips duplicate settlement application | `skipped=true`, `reason=settlement_already_applied`, `settlement_event_path` | `guardrail:execution:idempotency` | Existing idempotency test; add fallback key when no trade id exists |
| Reconciliation unmatched holdings block apply | `scripts/execution_sync.py` | preview unmatched holdings, `apply_ready` | Rejects apply if unmatched holdings exist and preview is not apply-ready | Exception; no write to `portfolio_state/current.json` | `guardrail:reconciliation:unmatched_holdings` | Existing unmatched screenshot test |
| Reconciliation `drop_missing` must be explicit | `scripts/execution_sync.py` | `drop_missing`, `missing_items` | Default updates matched/new only; `drop_missing=true` can zero missing holdings | `dropped_missing_fund_codes`, `mode=replace/update` | `guardrail:reconciliation:drop_missing_explicit` | Existing replace-zero test; add default non-zeroing test |
| Portfolio state event chain and hash audit | `scripts/portfolio_state.py` | current portfolio, previous metadata, event type/id/source | Saves current, snapshot, journal; records parent linkage and event hash | `state_metadata`, event journal, snapshot path | `guardrail:state:audit_trail` | Add consecutive save parent-state chain test |
| Real position and units source authority | `scripts/portfolio_state.py` | `units_source`, `real_position_source`, `actual_daily_pnl_source`, `report_date` | Determines whether position and daily PnL units are trusted | `actual_position_is_authoritative()`, `daily_pnl_units_are_trusted()` reason | `guardrail:state:position_authority` | Add value-only cross-date and unknown-source reason tests |

## Current Output Fields To Preserve

`validated_advice` root currently exposes:

- `daily_max_gross_trade_amount`
- `daily_max_net_buy_amount`
- `fixed_dca_total`
- `remaining_gross_trade_budget_after_validation`
- `remaining_net_buy_budget_after_validation`
- `cash_hub_available`
- `immediately_available_cash`
- `delayed_sell_proceeds`
- `allocation_plan`
- `optimization_summary`
- `optimizer_candidates`
- `optimizer_best_combo_metrics`
- `dca_actions`
- `tactical_actions`
- `hold_actions`

Single action records currently expose:

- `suggestion_id`
- `fund_code`
- `validated_action`
- `validated_amount`
- `model_action`
- `policy_rule_hits`
- `constraint_hits`
- `allocation_impact`
- `cash_impact`
- `execution_friction`
- `validation_notes`
- `execution_status`
- `executed_amount`
- `change_vs_prev_day`

Execution sync currently exposes:

- `actual_trades`
- `pending_confirmations`
- `execution_deviation`
- `settlement_event_path`
- `portfolio_applied_count`
- `reconciliationReports`
- `dropped_missing_fund_codes`
- portfolio `state_metadata`

## Phase 1 Guardrail Mapping

Phase 1 action tickets should map current rule outputs into
`hard_guardrail_results` but should not reimplement the full optimizer.

Minimum Phase 1 mapping:

- amount normalization
- fixed DCA
- cash floor and available funding
- fund capacity
- sellable amount
- committee global/fund gate
- action-count and budget summaries if present in `validated_advice`
- execution/reconciliation guardrails as references only when a ticket is tied
  to execution state

The official validator remains the final source for current official advice
until Phase 8 promotion.

## Open Questions

- Should `decision_mode=hold_only` still allow fixed DCA, or should it suppress
  all new buys? Current behavior needs an explicit locked expectation before
  migration.
- Should theme-family concentration block the first crossing above the limit, or
  only additions that worsen an already-overweight state? Current optimizer
  appears focused on worsening already-overweight exposure.
- Should top-3 and management-company limits remain hard-coded or move to
  `config/strategy.toml` before Phase 8? Phase 1 should document current values
  without changing behavior.

## Priority Tests Before Promotion

1. Global `decision_mode=hold_only/blocked`.
2. Cash below `cash_hub_floor` rejects all adds.
3. Gross trade budget and net buy budget trigger separately.
4. Top-3, management-company, and high-volatility concentration boundaries.
5. Screenshot reconciliation does not `drop_missing` unless explicitly set.
6. Illegal execution operation writes no trade or pending file.
7. Settlement idempotency with missing `trade_id` fallback key.
