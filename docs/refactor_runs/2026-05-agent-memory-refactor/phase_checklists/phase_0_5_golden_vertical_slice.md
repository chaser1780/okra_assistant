# Phase 0.5 Checklist: Golden Vertical Slice

Status: required before broad Phase 1 implementation.

## Goal

Prove the first end-to-end refactor path on one fixed sample:

```text
validated_advice -> action_ticket -> retrieval_pack -> outcome_event
```

The purpose is auditability, replayability, and learning readiness before the
project expands to many funds, many dates, LangGraph orchestration, or UI.

## Allowed Write Set

- `tests/fixtures/golden_slices/<slice_id>/input/*`
- `tests/fixtures/golden_slices/<slice_id>/expected/*`
- `tests/test_refactor_golden_slice.py`
- `scripts/replay_refactor_slice.py`
- `scripts/diff_refactor_slice.py`
- optional `scripts/artifact_boundary.py`
- `db/refactor_shadow_runs/<slice_id>/*`
- documentation updates under the refactor folder

## Forbidden Write Set

- `db/validated_advice/*`
- `db/decision_latest/*`
- `db/decision_ledger/*`
- `db/portfolio_state/*`
- `db/execution_sync/*`
- `db/long_memory/*`
- production daily pipeline integration
- frontend UI

## Inputs

Fixed fixture copies or synthetic equivalents:

- one validated advice input
- one portfolio state input
- one strategy config input
- one minimal context/evidence input
- one official NAV/benchmark input for outcome scoring

Do not use mutable current runtime files directly in golden tests.

## Outputs

- `action_ticket.expected.json`
- `retrieval_pack.expected.json`
- `outcome_event.expected.json`
- `diff_report.expected.md`
- replay run outputs under `db/refactor_shadow_runs/<slice_id>/`

## Implementation Steps

1. Choose a slice id such as `2026-05-24__110011__add`.
2. Freeze minimal input fixtures.
3. Add replay script that runs only the slice path.
4. Add diff script that compares output to expected artifacts.
5. Add boundary checks for `shadow_only`, `learning_only`, and
   `non_executable`.
6. Generate expected output through explicit approval, not accidental overwrite.
7. Add test that fails on unapproved diff.

## KPI Snapshot

The diff report must include:

- `trace_completeness_rate`
- `silent_hold_rate`
- `shadow_official_comparable_rate`
- `non_executable_violation_count`
- `forbidden_write_count`
- `replay_diff_unapproved_count`
- `missing_critical_data_rate`

## Required Tests

- replay from fixtures is deterministic
- action ticket validates and round-trips
- retrieval pack validates and round-trips
- outcome event validates and round-trips
- diff report is generated
- forbidden writes are detected
- official fixture output remains unchanged

Suggested commands:

```powershell
python -B -X utf8 -m py_compile scripts\replay_refactor_slice.py scripts\diff_refactor_slice.py
python -B -X utf8 -m unittest tests.test_refactor_golden_slice
```

## Manual Verification

- Read the generated `diff_report.md`.
- Confirm the verdict is understandable without opening code.
- Confirm boundary checks are explicit.
- Confirm no broad portfolio behavior is implied by one slice.

## Rollback Notes

Delete `db/refactor_shadow_runs/<slice_id>/`. Fixture updates should be reviewed
like code changes.

## Promotion Gate

Broad Phase 1 can proceed only after:

- one golden slice passes replay;
- output diff is stable or explicitly approved;
- forbidden write count is zero;
- boundary checks pass;
- action-ticket core fields are stable enough for model implementation.
