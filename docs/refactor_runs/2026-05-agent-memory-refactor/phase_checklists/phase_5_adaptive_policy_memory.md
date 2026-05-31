# Phase 5 Checklist: Adaptive Policy Memory

Status: implemented as learning-only partial. Promotion into active trading
behavior remains blocked by Phase 6 skill curation and explicit user approval.

## Goal

Turn repeated action-ticket outcomes into adaptive soft policies. These policies
guide future sizing, confidence, and wait triggers, but never become hidden hard
constraints.

## Allowed Write Set

- `scripts/adaptive_policy_models.py`
- `scripts/update_adaptive_policies.py`
- `tests/test_adaptive_policies.py`
- `db/strategy_memory/policy_events.jsonl`
- `db/strategy_memory/policies.json`

## Forbidden Write Set

- hard-constraint code
- official advice
- portfolio state
- execution sync
- long-memory approval state except explicit future integration
- strategy skill files except through Phase 6

## Inputs

- outcome events
- action tickets
- user feedback if explicitly provided
- existing long-memory status semantics
- `schema_examples/adaptive_policy.example.json`

## Lifecycle

```text
draft -> candidate -> active -> weakened -> revised -> archived
```

## Allowed Policy Effects

- `confidence_delta`
- `size_multiplier`
- `wait_trigger`
- `note`

Forbidden effects:

- `block`
- `force_trade`
- `change_hard_constraint`
- direct execution command

## Implementation Steps

1. Add event model and materialized current-view model.
2. Store manual lifecycle changes as event history and replay derived outcome
   events by source outcome identity when the source artifact changes.
3. Materialize current policies into `policies.json`.
4. Require outcome support or explicit user feedback before promotion.
5. Track support count, contradiction count, confidence, and source ids.
6. Enforce caps per scope to prevent policy explosion.
7. Make contradictions weaken/archive policies rather than silently deleting
   them; accept explicit `revise` events as a separate manual lifecycle action.

## Required Tests

- supportive outcomes promote draft to candidate under threshold rules
- active promotion requires enough support or user approval
- contradictions weaken/archive according to rules
- explicit revise events update policy statement/effect without becoming a hard
  constraint
- policy cap per scope is enforced
- policy event replay is idempotent
- stale derived support/contradict events from the same outcome source are not
  both retained
- soft policy cannot produce hard block
- malformed policy event does not corrupt materialized view

Suggested commands:

```powershell
python -B -X utf8 -m py_compile scripts\adaptive_policy_models.py scripts\update_adaptive_policies.py
python -B -X utf8 -m unittest tests.test_adaptive_policies
python -B -X utf8 -m unittest tests.test_long_memory tests.test_action_outcomes
```

## Manual Verification

- Inspect `policy_events.jsonl` and confirm event history is auditable and
  derived events include source artifact identity/hash.
- Inspect `policies.json` and confirm it is a current view, not the only record.
- Confirm policy scopes are specific enough to avoid global overreach.

## Rollback Notes

If a manual or promoted policy is wrong, append an archive/weaken event rather
than editing history. Derived outcome events may be replayed from the current
source artifact so stale generated support/contradict labels do not survive
beside the corrected outcome.

## Promotion Gate

Phase 6 can curate skills from policies only after:

- policy lifecycle works;
- support/contradiction accounting is tested;
- soft-policy non-blocking rule is enforced;
- policy caps are configured.
