# Phase 1 Checklist: Action Ticket Shadow Foundation

Status: ready after Phase 0 schema lock.

## Goal

Create a standalone, non-mutating action-ticket artifact from existing official
validated advice. This establishes the future decision unit without changing
the official daily chain.

## Allowed Write Set

- `scripts/action_ticket_models.py`
- `scripts/build_action_ticket_shadow.py`
- `tests/test_action_tickets.py`
- `db/action_tickets/<report_date>.json`
- optional `db/action_debates/<report_date>.json`
- documentation updates under the refactor folder

## Forbidden Write Set

- `db/validated_advice/*`
- `db/decision_latest/*`
- `db/decision_ledger/*`
- `db/portfolio_state/*`
- `db/execution_sync/*`
- `db/long_memory/*`
- `scripts/run_daily_pipeline.py` integration by default
- frontend UI changes

## Inputs

- `db/validated_advice/<report_date>.json`
- committee bundle embedded in validated advice or daily workspace artifacts
- current portfolio/fund metadata
- `hard_constraints_inventory.md`
- `schema_examples/action_ticket.example.json`

## Outputs

- One action-ticket JSON per report date.
- Optional action-debate summary JSON per report date.
- Focused tests for model validation and builder behavior.

## Core Versus Extension Fields

Phase 1 should keep the required ticket surface compact.

Required core ticket fields:

- `ticket_id`
- `schema_version`
- `report_date`
- `generated_at`
- `fund_code`
- `fund_name`
- `action_verb`
- `execution_mode`
- `ticket_status`
- `non_executable`
- `write_scope`
- `validated_amount`
- `confidence`
- `thesis`
- `hard_guardrail_results`
- `source_artifacts`
- `legacy_mapping`

Extension fields may be present but should not be mandatory in Phase 1:

- `percent_of_position`
- `percent_of_portfolio`
- `supporting_evidence_refs`
- `opposing_evidence_refs`
- `soft_policy_adjustments`
- `skill_refs`
- `skill_outputs`
- `opportunity_cost`
- `debate`
- `invalidation_conditions`

## Implementation Steps

1. Add `ActionTicket`, `GuardrailResult`, `EvidenceRef`,
   `SoftPolicyAdjustment`, and root artifact dataclasses.
2. Validate required date fields and enum values in `__post_init__`.
3. Add stable id builders using the prefixes from `06_execution_technical_plan.md`.
4. Read official validated advice as input only.
5. Normalize legacy actions into `action_verb`.
6. Map DCA, tactical, and meaningful hold records into tickets.
7. Map existing `constraint_hits`, `policy_rule_hits`, `validation_notes`,
   budget fields, and optimizer notes into `hard_guardrail_results`.
8. Enforce `write_scope="shadow_only"` and `non_executable=true`.
9. Write only `db/action_tickets/<report_date>.json`.
10. Keep the script standalone: `python scripts\build_action_ticket_shadow.py --date YYYY-MM-DD`.

## Guardrail Mapping Requirements

Minimum mappings:

- amount normalization
- fixed DCA
- cash floor / funding
- fund capacity
- sellable amount
- committee global gate
- committee fund gate
- gross trade budget
- net buy budget
- action count
- allocation band
- concentration limits when present

If a guardrail cannot be inferred from existing output, set `result =
"not_checked"` with `status_reason`.

## Required Tests

- add ticket from tactical add
- reduce ticket from tactical reduce
- scheduled DCA ticket from core DCA
- meaningful hold ticket from blocked or position-bearing hold
- no ticket for irrelevant empty hold unless explicitly meaningful
- hard-blocked ticket maps `ticket_status = blocked`
- adjusted-size ticket maps `ticket_status = adjusted`
- missing input fields produce explicit `missing_data`
- official `validated_advice` file is not modified
- action ticket round-trip is stable
- `silent_hold_rate` is zero for emitted hold tickets
- `non_executable_violation_count` is zero

Suggested commands:

```powershell
python -B -X utf8 -m py_compile scripts\action_ticket_models.py scripts\build_action_ticket_shadow.py
python -B -X utf8 -m unittest tests.test_action_tickets
python -B -X utf8 -m unittest tests.test_pipeline_logic tests.test_multiagent_and_review tests.test_validation_and_trade
```

## Manual Verification

- Run builder for one existing date.
- Confirm output has `schema_version`, `report_date`, `generated_at`, source
  refs, and `non_executable=true`.
- Confirm every ticket has `ticket_id`, `fund_code`, `action_verb`,
  `ticket_status`, core source refs, and guardrail results.
- Confirm no official advice, portfolio state, or execution file timestamp
  changed.
- Confirm the golden slice diff report stays stable.

## Rollback Notes

Delete generated `db/action_tickets/<date>.json` and optional
`db/action_debates/<date>.json`. No production behavior should need rollback.

## Promotion Gate

Phase 2/3 can consume action tickets only after:

- Phase 1 model tests pass;
- generated artifacts validate deterministically;
- golden slice replay passes;
- meaningful hold rule is accepted;
- action enum and status enum are stable;
- official chain output remains unchanged.
