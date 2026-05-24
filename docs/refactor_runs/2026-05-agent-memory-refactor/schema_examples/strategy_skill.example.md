---
schema_version: strategy_skill.v1
skill_id: skill:small_reversal_add:v1
name: Small Reversal Add
status: candidate
version: 1
scope: fund:tactical_short_term
created_at: 2026-05-26T00:30:00+08:00
updated_at: 2026-05-26T00:30:00+08:00
source_policy_ids:
  - policy:portfolio:growth_cluster_overweight:v1
source_outcome_ids:
  - outcome:2026-05-24:T+1:ticket-hash-example
promotion:
  min_supported_outcomes: 5
  user_approval_required: true
hard_constraints_editable: false
default_write_scope: learning_only
non_executable: true
auto_activation_allowed: false
---

# Small Reversal Add

## Purpose

Use a reduced starter-size add when a tactical fund shows early reversal evidence after a drawdown, while the portfolio bucket is near its upper allocation band.

## When To Apply

- The fund role is `tactical_short_term`.
- The proposed action is `add`.
- The recent drawdown has improved the fund's forward risk/reward.
- At least one structured current signal supports reversal.
- The relevant portfolio bucket is near, but not beyond, the hard allocation band.
- No hard guardrail blocks the action.

## Required Inputs

- Current position value and portfolio weight from `portfolio_state`.
- Latest official NAV and proxy/benchmark data.
- Current cash hub availability after floor.
- Allocation bucket status.
- Recent decision and outcome history for the same fund or bucket.
- Applicable adaptive policies.
- RAG or long-text evidence only for similar cases, anti-patterns, and explanatory context.

## Procedure

1. Verify current facts through structured sources before reading retrieved text.
2. Check hard guardrails for cash floor, allocation band, capacity, sellability, and committee risk veto.
3. Build a bull case for why the reversal is actionable.
4. Build a bear case for why the move may be a false bounce or concentration risk.
5. If the action survives debate, set size to a starter amount.
6. Apply adaptive soft policies as size or confidence adjustments only.
7. Attach an explicit invalidation condition using the next official NAV or benchmark comparison.
8. Record the skill id and the sizing note on the action ticket.

## Position Sizing Notes

- Default size bucket: `small`.
- Default effect: size no larger than the lower of the validator-approved amount and the active policy multiplier.
- Do not use this skill to justify aggressive adds while the bucket is already above the hard allocation band.

## Invalidation Conditions

- The next official NAV underperforms the selected benchmark/proxy by more than the configured threshold.
- A new committee risk veto appears before execution.
- Cash hub availability falls below the configured floor.
- The fund's source data becomes stale or conflicted.

## Anti-Patterns

- Treating same-day estimated PnL as official outcome evidence.
- Using retrieved similar cases to override current position or cash facts.
- Promoting the skill to active after one good example.
- Converting this skill into a hard block or forced buy rule.

## Evidence Requirements

- At least one structured current fact.
- At least one recent derived signal.
- At least one relevant historical outcome or memory item for candidate status.
- Multiple supportive outcomes or explicit user approval for active status.

## Known Failure Modes

- False rebound in a weak market.
- Overweight growth exposure increases drawdown volatility.
- Incomplete official NAV data makes outcome evaluation pending.

## Output Contract

When selected into a daily skill pack, this skill may output:

- `sizing_note`
- `confidence_delta`
- `wait_trigger`
- `invalidation_condition`
- `evidence_requirement_note`

It must not output:

- `hard_block`
- `force_trade`
- direct portfolio mutation
- execution commands
