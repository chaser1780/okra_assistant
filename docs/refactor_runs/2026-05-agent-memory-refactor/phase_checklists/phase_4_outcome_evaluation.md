# Phase 4 Checklist: Outcome Evaluation

Status: schema can start after Phase 1; scoring requires official data.

## Goal

Evaluate action-ticket quality using official NAV and trusted structured facts.
Outcome events feed adaptive policy and skill learning, but do not directly
rewrite official advice.

## Allowed Write Set

- `scripts/outcome_event_models.py`
- `scripts/evaluate_action_ticket_outcomes.py`
- `tests/test_action_outcomes.py`
- `db/outcome_events/<base_date>__<horizon>.json`

## Forbidden Write Set

- official NAV source files
- official revaluation output
- portfolio state
- execution sync
- long-memory records
- adaptive policies or skills except through later phases

## Inputs

- action tickets
- official NAV data
- benchmark/proxy data
- trusted position/unit/cashflow metadata
- `schema_examples/outcome_event.example.json`
- existing official NAV/PnL reliability rules

## Initial Horizons

- `T+1`
- `T+5`

## Scoring States

- `pending`: required official data not available yet.
- `blocked`: official data exists but scoring would be unreliable.
- `scored`: outcome is computed.
- `not_applicable`: ticket type cannot be scored with this horizon.

Blocked reasons include:

- missing official NAV
- stale or fallback quote
- missing previous NAV
- untrusted units
- cashflow between NAV dates
- already written/scored

## Implementation Steps

1. Add outcome dataclasses with strict date validation.
2. Reuse existing official NAV/revaluation helpers where possible.
3. Score actions only from official NAV and trusted benchmarks/proxies.
4. Evaluate holds for avoided loss or missed opportunity.
5. Treat conditional actions that did not trigger as timing/wait decisions.
6. Write append-compatible outcome event files by base date and horizon.
7. Include source refs and reliability status in every event.

## Required Tests

- pending when official NAV is missing
- blocked when units/cashflow data is unreliable
- scored add/reduce/hold cases
- benchmark/proxy excess return calculation
- no duplicate scoring on rerun
- outcome event links back to ticket id
- no mutation of official valuation artifacts

Suggested commands:

```powershell
python -B -X utf8 -m py_compile scripts\outcome_event_models.py scripts\evaluate_action_ticket_outcomes.py
python -B -X utf8 -m unittest tests.test_action_outcomes
python -B -X utf8 -m unittest tests.test_revaluation_and_realtime tests.test_execution_sync
```

## Manual Verification

- Inspect one `pending`, one `blocked`, and one `scored` outcome.
- Confirm official NAV dates and availability dates are explicit.
- Confirm no estimated realtime PnL is used as truth.

## Rollback Notes

Delete generated `db/outcome_events/*` files for the affected date/horizon. No
official accounting state should need rollback.

## Promotion Gate

Phase 5 can promote policy learning only after:

- outcome states are reliable and tested;
- official NAV and trusted-unit checks are enforced;
- duplicate scoring is idempotent;
- hold evaluation semantics are accepted.
