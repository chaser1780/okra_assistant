# 11 Review Refinement And Vertical Slice Plan

Status: accepted refinement from user review, to be applied before Phase 1
implementation.

This document refines the previous plan. It does not replace the accepted
architecture. It narrows the first implementation target and adds measurable
exit criteria so the refactor does not become infrastructure stacking.

## Refined Goal

The refactor target is:

```text
make one decision auditable, replayable, and learnable
```

Operational meaning:

- Auditable: every action has source refs, dates, guardrail results, and
  non-executable boundaries.
- Replayable: the same fixed inputs produce the same shadow artifacts and a
  stable diff report.
- Learnable: outcome events can later update soft policy or candidate skill
  state without mutating hard constraints.

Non-goal:

- Action ticket is not a second knowledge base.
- Retrieval pack is not a file dump.
- LangGraph state is not financial storage.
- Strategy skill registry is not an automatic live trading rulebook.

## Phase 0.5: Golden Slice And Replay Harness

Add a small phase between schema lock and Phase 1 implementation.

### Purpose

Build a fixed sample set, golden outputs, and diff report before expanding the
chain.

### Scope

Start with one vertical slice:

```text
single report_date
single fund
single action type
validated_advice -> action_ticket -> retrieval_pack -> outcome_event
```

Recommended first slice:

- One date that already has validated advice.
- One tactical fund with a clear `add`, `reduce`, or meaningful `hold`.
- One official NAV outcome horizon, preferably `T+1`.
- No LangGraph requirement in the first slice.
- No Workbench UI requirement in the first slice.

### Candidate Files

```text
tests/fixtures/golden_slices/<slice_id>/
tests/fixtures/golden_slices/<slice_id>/input/
tests/fixtures/golden_slices/<slice_id>/expected/
tests/test_refactor_golden_slice.py
scripts/replay_refactor_slice.py
scripts/diff_refactor_slice.py
db/refactor_shadow_runs/<slice_id>/
```

### Golden Inputs

Copy or synthesize a minimal fixture set:

- validated advice fixture
- portfolio state fixture
- llm context / evidence fixture if needed
- official NAV fixture for outcome scoring
- strategy config fixture

Do not depend on today's mutable runtime files in golden tests.

### Golden Outputs

Expected files:

- `action_ticket.expected.json`
- `retrieval_pack.expected.json`
- `outcome_event.expected.json`
- `diff_report.expected.md`

Golden outputs should allow approved updates, but only through an explicit
command or review step.

### Diff Report Contract

The diff report should answer:

- Did the artifact validate?
- Did the artifact change versus golden?
- Which fields changed?
- Are changes deterministic?
- Did any forbidden write occur?
- Did any non-executable boundary fail?
- Did official output remain unchanged?

Minimum report sections:

```text
# Refactor Slice Diff
## Inputs
## Output Status
## Artifact Diff
## KPI Snapshot
## Boundary Checks
## Verdict
```

## KPI And Exit Metrics

Each phase must have measurable exit signals. These are not product promises;
they are engineering gates that prevent blind infrastructure growth.

### Global Metrics

| Metric | Meaning | Target before promotion |
|---|---|---|
| `trace_completeness_rate` | Required source refs and dates are present | >= 95% for shadow artifacts |
| `shadow_official_comparable_rate` | Shadow tickets can be mapped to official advice | >= 90% on selected sample set |
| `shadow_official_action_agreement_rate` | Action verb agrees after normalization | track first, target later after debate changes |
| `silent_hold_rate` | Holds without explicit reason or wait condition | 0 for emitted hold tickets |
| `non_executable_violation_count` | Shadow or learning artifact attempts mutation/execution | 0 |
| `replay_diff_unapproved_count` | Replay output differs from golden without approval | 0 in CI/focused tests |
| `fallback_rate` | New layer falls back to legacy or missing data | tracked per phase, should decline before promotion |
| `missing_critical_data_rate` | Critical facts missing/stale/conflicted | tracked; must not be hidden |

### Phase-Level Exit Metrics

| Phase | Exit metrics |
|---|---|
| Phase 0 | Schema examples present; hard constraints mapped; checklist coverage 100% |
| Phase 0.5 | At least one golden slice replay passes; diff report is generated; forbidden write count is 0 |
| Phase 1 | Action ticket validation pass rate 100% on golden slice; silent hold rate 0; official output unchanged |
| Phase 2 | Retrieval pack trace completeness >= 95%; no-future violations 0; structured facts used for canonical facts |
| Phase 3 | Graph state size remains small; node failure produces degraded shadow artifact; replay is idempotent |
| Phase 4 | Outcome states are `scored`, `pending`, or `blocked`; unofficial PnL usage count 0 |
| Phase 5 | Soft policy hard-block attempts 0; policy event append-only tests pass |
| Phase 6 | Auto-active skill promotions 0 until approved; skill registry/Markdown round-trip passes |
| Phase 7 | Shadow review mutation endpoints called 0; missing artifact empty states pass |
| Phase 8 | Replacement has fallback; compatibility output tests pass; fallback usage monitored before downline |

## Core Versus Extension Fields

Phase 1 action ticket must start compact. Required fields should be enough to
audit and replay the decision. Everything else should be optional extension.

### Phase 1 Core Fields

Required on every ticket:

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

Required on root artifact:

- `schema_version`
- `artifact_id`
- `report_date`
- `generated_at`
- `write_scope`
- `non_executable`
- `source_artifacts`
- `tickets`

### Phase 1 Extension Fields

Optional or later fields:

- `percent_of_position`
- `percent_of_portfolio`
- `opposing_evidence_refs`
- `soft_policy_adjustments`
- `skill_refs`
- `skill_outputs`
- `opportunity_cost`
- `debate`
- `debate_options`
- `invalidation_conditions`
- rich timing triggers

Rule:

- Extension fields may exist in examples, but Phase 1 implementation should not
  fail just because they are absent.
- Tests should verify core fields first and extension fields only where the
  fixture includes them.

## Single Contract Source And Round-Trip Tests

Dataclasses are the contract source for persisted shadow artifacts after code is
added.

Docs examples are contract examples, not the runtime source of truth.

Required implementation rule:

```text
dataclass model -> to_dict -> JSON -> from_dict/model_validate -> to_dict
```

The round-trip output must be stable except for explicitly generated timestamps
when tests inject a fixed clock.

Required tests:

- action ticket round-trip
- retrieval pack round-trip
- outcome event round-trip
- policy event/current-view round-trip
- strategy skill registry + Markdown frontmatter round-trip
- API DTO round-trip when Pydantic boundary is introduced
- frontend schema parse test when UI schema is introduced

## Runtime Boundary Enforcement

Documentation labels are not enough. Code must validate artifact boundary
semantics.

Required boundary fields:

- `write_scope`: `shadow_only | learning_only | review_only | official`
- `non_executable`: boolean
- `allowed_writes`: optional list for run metadata
- `forbidden_writes`: optional list for run metadata

Minimum runtime checks:

- A `shadow_only` artifact cannot write official advice, portfolio state,
  execution sync, or long memory.
- A `learning_only` artifact cannot execute trades or update official advice.
- A `non_executable=true` ticket cannot be sent to execution endpoints.
- A strategy skill in `draft` or `candidate` status cannot be selected as an
  active rule without approval.
- A soft policy cannot emit `block`, `force_trade`, or `change_hard_constraint`.

Recommended helper:

```text
scripts/artifact_boundary.py
```

Candidate APIs:

```text
assert_shadow_write_allowed(path, artifact)
assert_non_executable(artifact)
assert_learning_write_allowed(path, artifact)
record_boundary_check(run_id, result)
```

## Early CLI/Markdown Review

Do not wait until the full Workbench UI to review new-chain output.

Add a pre-UI review layer:

```text
scripts/render_refactor_review.py
db/refactor_reviews/<report_date>.md
```

Minimum review sections:

- official validated advice summary
- shadow action-ticket summary
- guardrail map
- retrieval trace completeness
- outcome status if available
- diff versus golden or versus official
- boundary check result
- open questions

This lets Phase 1-4 be reviewed before Phase 7 UI exists.

## Phase 8 Refinement: Replace, Fallback, Then Downline

Phase 8 should not be framed as direct deletion. The safer sequence is:

```text
replace one responsibility
keep compatibility output
keep fallback switch
monitor
then downline or delete
```

Required before removing a legacy layer:

- replacement owner is explicit;
- fallback path is implemented;
- compatibility output exists or consumers are migrated;
- golden slice and real-date comparison pass;
- rollback checkpoint exists;
- user accepts evidence.

Use "legacy chain reduction" as the phase name, but implement it as
replacement-first, fallback-preserving migration.

## Technology Refinements

### LangGraph

- Use LangGraph for orchestration, not financial data storage.
- Nodes should be thin and map to meaningful reasoning or IO boundaries.
- Graph state stores refs, node status, compact summaries, and failure metadata.
- Large facts stay in structured artifacts.
- Side effects are isolated in writer nodes and boundary-checked.

### RAG

- Keep vector backend pluggable.
- Structured lookup remains primary for current facts.
- Semantic retrieval is recall enhancement for similar cases, anti-patterns,
  policy explanations, and long text evidence.
- RAG failures return explicit missing/fallback metadata; they do not mutate
  official outputs.

### Strategy Skills

- Markdown skill plus registry metadata remains the preferred local format.
- Early lifecycle is draft/candidate by default.
- Automatic activation is disabled until outcome evidence or explicit user
  approval exists.
- Skill outputs are notes, sizing suggestions, wait triggers, or invalidation
  suggestions; they are not execution commands.

## Documentation Changes Required

Apply this refinement to:

- `05_implementation_roadmap_plan.md`
- `06_execution_technical_plan.md`
- `08_phase_dependency_and_impact_matrix.md`
- `phase_checklists/phase_0_schema_lock.md`
- `phase_checklists/phase_1_action_ticket_shadow.md`
- `phase_checklists/phase_2_layered_retrieval_pack.md`
- `phase_checklists/phase_3_langgraph_debate_shadow.md`
- `phase_checklists/phase_6_strategy_skill_curator.md`
- `phase_checklists/phase_7_workbench_review_surface.md`
- `phase_checklists/phase_8_legacy_chain_reduction.md`
- `tasks.md`
- `decisions.md`
- `execution-log.md`

## Next Engineering Step

Do not jump directly to the full Phase 1 branch.

Next implementation should be:

```text
Phase 0.5 golden vertical slice
-> Phase 1 compact action-ticket shadow builder
-> Phase 2 retrieval pack for the same slice
-> Phase 4 outcome event for the same slice
```

Only after the slice is replayable should the project expand to more funds,
more dates, LangGraph orchestration, UI review, and legacy replacement.
