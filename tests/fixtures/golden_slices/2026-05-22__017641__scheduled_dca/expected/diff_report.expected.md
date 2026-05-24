# Refactor Slice Diff

## Inputs
- slice_id: 2026-05-22__017641__scheduled_dca
- report_date: 2026-05-22
- fund_code: 017641
- action_verb: scheduled_dca
- fixture_kind: synthetic_minimal_from_2026-05-22_runtime

## Output Status
- verdict: PASS
- trace_completeness_rate: 1.00
- silent_hold_rate: 0.00
- shadow_official_comparable_rate: 1.00
- non_executable_violation_count: 0
- forbidden_write_count: 0
- replay_diff_unapproved_count: 0
- missing_critical_data_rate: 0.00
- official_output_unchanged: true

## Artifact Diff
- action_ticket: unchanged; first_changed_field=none; validation_errors=none
- retrieval_pack: unchanged; first_changed_field=none; validation_errors=none
- outcome_event: unchanged; first_changed_field=none; validation_errors=none

## Boundary Checks
- non_executable: pass - all refactor artifacts are non-executable
- shadow_write: pass - db/refactor_shadow_runs/2026-05-22__017641__scheduled_dca/action_ticket.json allowed
- non_executable: pass - all refactor artifacts are non-executable
- shadow_write: pass - db/refactor_shadow_runs/2026-05-22__017641__scheduled_dca/retrieval_pack.json allowed
- non_executable: pass - all refactor artifacts are non-executable
- learning_write: pass - db/refactor_shadow_runs/2026-05-22__017641__scheduled_dca/outcome_event.json allowed

## Official Output
- production pipeline integration: not touched
- official advice / ledger / portfolio / execution / long memory writes: none
