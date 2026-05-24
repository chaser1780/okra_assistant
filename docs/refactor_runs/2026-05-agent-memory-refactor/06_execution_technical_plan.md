# 06 Execution Technical Plan

Status: accepted principle, implementation details recorded for review before
coding.

This document translates the accepted refactor direction into concrete branch
shape, implementation phases, artifact boundaries, and technical decisions that
can otherwise drift during execution.

It does not replace the five accepted architecture plans. It is the execution
contract for turning them into code.

## Non-Negotiable Execution Principles

The refined target is:

```text
make one decision auditable, replayable, and learnable
```

This narrows the engineering objective:

- Action ticket is a decision artifact, not a second knowledge base.
- Retrieval pack is a compact context contract, not a file dump.
- Outcome event is learning input, not official accounting state.
- Strategy skill is candidate procedural memory, not an automatic trading rule.

The refactor must follow this migration sequence:

```text
new chain first
old chain preserved
shadow comparison
gradual takeover
replace with fallback
legacy downline after evidence
```

Operational meaning:

- New artifacts are created in shadow paths first.
- Existing `validated_advice`, portfolio state, execution sync, official NAV
  revaluation, and current workbench behavior remain unchanged until explicit
  promotion.
- Every new reasoning artifact must point back to source facts, source files,
  and source dates.
- LLM outputs can propose, compare, and reprice; deterministic guardrails and
  official accounting remain structured code paths.
- Soft constraints can evolve through memory; hard constraints remain explicit
  and separately auditable.
- A `hold` decision is an explicit action ticket when it reflects a real
  investment choice, wait condition, blocked action, or meaningful opportunity
  cost.
- Every phase must expose measurable exit signals such as trace completeness,
  silent hold rate, shadow/official comparability, replay diff, fallback rate,
  and boundary violations.

## Branch Layout

Current baseline:

- `main` contains the latest cleanup commits.
- Planning documents should be committed or otherwise checkpointed before code
  branches are created.

Recommended branch sequence:

```text
main
`-- codex/agent-memory-refactor-planning
    |-- codex/golden-vertical-slice
    |-- codex/action-ticket-shadow-foundation
    |-- codex/layered-retrieval-pack
    |-- codex/langgraph-action-debate-shadow
    |-- codex/outcome-evaluation-loop
    |-- codex/adaptive-policy-memory
    |-- codex/strategy-skill-curator
    |-- codex/workbench-action-ticket-review
    `-- codex/legacy-chain-reduction
```

Branch rules:

- `codex/agent-memory-refactor-planning` contains documentation, schema drafts,
  and migration notes only.
- `codex/golden-vertical-slice` is the first implementation branch and owns the
  fixed sample, replay command, diff report, and boundary-check harness.
- Later implementation branches should be created from the latest planning
  checkpoint or from a merged prior implementation branch.
- Do not mix schema foundation, data-pack construction, LangGraph orchestration,
  UI surfaces, and legacy deletion in one branch.
- Branches may be reviewed independently, but merge order should follow the
  phase order because later phases depend on earlier artifact contracts.
- If a phase exposes a schema defect, fix the schema in the earliest branch that
  owns that schema, then rebase later branches.

## Artifact Boundary

Shadow artifacts should be added without mutating existing official artifacts.

Initial shadow paths:

```text
db/action_tickets/<report_date>.json
db/action_debates/<report_date>.json
db/retrieval_packs/<report_date>.json
db/outcome_events/<base_date>__<horizon>.json
db/strategy_memory/policies.json
db/strategy_memory/policy_events.jsonl
db/strategy_skills/registry.json
db/strategy_skills/<skill_id>/skill.md
db/strategy_skills/<skill_id>/events.jsonl
db/refactor_shadow_runs/<slice_id>/
db/refactor_reviews/<report_date>.md
```

Compatibility outputs that must not be silently changed:

```text
db/validated_advice/<report_date>.json
db/daily_workspace/<report_date>/*
db/portfolio_state/current.json
db/execution_sync/*
```

If a new script reads existing artifacts, it should write only to the new shadow
paths unless a later promotion phase explicitly changes that rule.

Runtime boundary checks should enforce the written contract. Shadow and learning
artifacts must include enough metadata to reject forbidden writes at runtime:

```text
write_scope: shadow_only | learning_only | review_only | official
non_executable: true | false
```

Recommended helper:

```text
scripts/artifact_boundary.py
```

The helper should block:

- `shadow_only` writes to official advice, portfolio state, execution sync, or
  long memory.
- `learning_only` writes to execution or official advice.
- `non_executable=true` artifacts from being passed to execution endpoints.
- soft policies or skills emitting `block`, `force_trade`, or
  `change_hard_constraint`.

## Shared Schema Decisions

### Runtime Model Style

The current repository already uses three model styles:

- `scripts/models.py`: `TypedDict` contracts for existing pipeline payloads.
- `scripts/rag_models.py`: dataclasses with validation helpers for persisted
  RAG artifacts.
- `app/api_contracts.py`: Pydantic DTOs for API-facing contracts.

Recommended implementation:

- Use dataclasses with explicit validation for persisted shadow artifacts under
  `scripts/*_models.py`.
- Add `TypedDict` only when a legacy pipeline payload needs type documentation
  without runtime validation.
- Use Pydantic only for API/workbench DTOs after the review surface is added.
- Keep JSON examples in docs, but do not make JSON schema files the only source
  of truth during early implementation.

Reason:

- Dataclass validation matches the existing RAG artifact pattern.
- It avoids adding runtime dependency changes before LangGraph is introduced.
- Pydantic remains useful at API boundaries where coercion and aliases matter.

Single contract source:

- Once code exists, dataclass models are the source of truth for persisted
  shadow artifacts.
- JSON examples are examples and fixtures, not the only contract source.
- Pydantic models own API boundary contracts only.

Required round-trip pattern:

```text
dataclass -> to_dict -> JSON -> from_dict/model_validate -> to_dict
```

Tests should inject a fixed clock so round-trip output is stable.

### Date Semantics

New artifacts must avoid mixing date meanings.

Required fields where relevant:

- `report_date`: the OKRA daily analysis date.
- `as_of_date`: the financial data date represented by a fact.
- `available_from`: when the system could have known the item.
- `generated_at`: when OKRA created the artifact.
- `nav_date`: the official NAV date used for valuation or outcome scoring.
- `evaluation_date`: the date an outcome is evaluated.
- `horizon`: the evaluation window such as `T+1` or `T+5`.

No-future rule:

- A decision artifact for `report_date = D` can include only data whose
  `available_from` is not later than the decision time for D.
- If the exact availability time is unknown, store the conservative date and
  mark the item with `availability_precision = "date_only"`.

### Id Conventions

Use stable prefixed ids:

```text
ticket:<report_date>:<fund_code>:<action_verb>:<sequence>
debate:<report_date>:<fund_code>:<sequence>
pack:<report_date>:<fund_code>:<sequence>
outcome:<base_date>:<horizon>:<ticket_hash>
policy:<scope>:<slug>
skill:<slug>:v<version>
fact:<source_kind>:<source_record_id>
event:<event_date>:<event_type>:<sequence>
```

Implementation notes:

- Do not use list index alone as a durable id.
- Include `source_hash` or `content_sha256` where content identity matters.
- Keep a `schema_version` field on every persisted artifact root.

### Missing Data States

Use explicit states instead of silent empty fields:

```text
present
missing
stale
conflicted
pending
blocked
not_applicable
```

For decision-critical fields, include:

- `data_status`
- `status_reason`
- `source_refs`
- `fallback_used`

This prevents the LLM from treating missing official values as weak negative
signals or inventing values.

## Phase 0: Planning And Schema Lock

Purpose:

- Lock artifact contracts before code churn.
- Decide the first branch boundaries and validation commands.

Implementation steps:

1. Commit or checkpoint all planning docs.
2. Record schema decisions in this folder.
3. Draft minimal JSON examples for action ticket, retrieval pack, outcome
   event, adaptive policy, and strategy skill.
4. Confirm which scripts may write each artifact family.

Candidate documentation outputs:

```text
docs/refactor_runs/2026-05-agent-memory-refactor/schema_examples/
docs/refactor_runs/2026-05-agent-memory-refactor/phase_checklists/
```

Technical details that can drift:

- Model style: dataclass versus Pydantic versus plain dict.
- Date meaning: report date versus NAV date versus evaluation date.
- Whether `hold` is always emitted or only when meaningful.
- Whether a soft constraint can block an action.

Locked recommendation:

- Dataclasses for persisted shadow artifacts.
- `hold` is emitted when it is a real decision, wait condition, blocked action,
  or missed-opportunity candidate.
- Soft constraints reprice or annotate; they do not hard block.

## Phase 0.5: Golden Slice And Replay Harness

Purpose:

- Add a fixed vertical slice before broad implementation.
- Make replay, diff, rollback, and boundary checks measurable from the start.

Initial slice:

```text
single report_date
single fund
single action type
validated_advice -> action_ticket -> retrieval_pack -> outcome_event
```

Candidate files:

```text
tests/fixtures/golden_slices/<slice_id>/input/
tests/fixtures/golden_slices/<slice_id>/expected/
tests/test_refactor_golden_slice.py
scripts/replay_refactor_slice.py
scripts/diff_refactor_slice.py
db/refactor_shadow_runs/<slice_id>/
```

Golden outputs:

```text
action_ticket.expected.json
retrieval_pack.expected.json
outcome_event.expected.json
diff_report.expected.md
```

Acceptance checks:

- Replay produces deterministic artifacts from fixed fixtures.
- Diff report is generated and readable.
- Forbidden write count is zero.
- Boundary checks pass.
- Official output remains unchanged.

Phase 1 should start with this slice, not the whole portfolio.

## Phase 1: Action Ticket Shadow Foundation

Purpose:

- Create the future decision unit without changing the official decision chain.

Candidate files:

```text
scripts/action_ticket_models.py
scripts/build_action_ticket_shadow.py
tests/test_action_tickets.py
db/action_tickets/<report_date>.json
db/action_debates/<report_date>.json
```

Inputs:

- `db/validated_advice/<report_date>.json`
- committee bundle embedded in validated advice or stored separately
- existing portfolio/fund metadata from current context files

Outputs:

- one action-ticket file per report date
- optional action-debate summary file per report date

Action ticket core fields:

```text
ticket_id
schema_version
report_date
generated_at
fund_code
fund_name
action_verb
execution_mode
ticket_status
non_executable
write_scope
validated_amount
confidence
thesis
hard_guardrail_results
source_artifacts
legacy_mapping
```

Phase 1 extension fields:

```text
size_bucket
requested_amount
percent_of_position
percent_of_portfolio
supporting_evidence_refs
opposing_evidence_refs
soft_policy_adjustments
invalidation_conditions
opportunity_cost
skill_refs
skill_outputs
debate
debate_options
```

Core fields must be present for every Phase 1 ticket. Extension fields can be
present in examples and later phases, but Phase 1 code should not make all of
them mandatory.

Recommended enums:

```text
action_verb: add | reduce | hold | scheduled_dca | switch_in | switch_out
execution_mode: immediate | scheduled | conditional | watch
ticket_status: shadow_only | proposed | adjusted | blocked | degraded
guardrail_result: pass | adjust | block | not_checked
policy_effect: confidence_delta | size_multiplier | wait_trigger | note
```

Granularity decision:

- Phase 1 creates one primary ticket per legacy validated action.
- Held funds receive tickets only when they have position exposure, a meaningful
  wait condition, a blocked legacy action, or explicit non-action reasoning.
- Later debate graphs may attach rejected alternatives under the same fund via
  `debate_options`, but Phase 1 should not invent alternatives.

Amount decision:

- Store absolute CNY amounts because the current validator already does.
- Also store `size_bucket` for reasoning continuity.
- Store `percent_of_position` and `percent_of_portfolio` when inputs are
  available; otherwise mark them as `not_applicable` or `missing`.

Hard versus soft constraint decision:

- `hard_guardrail_results` records pass/adjust/block outcomes from deterministic
  rules.
- `soft_policy_adjustments` records memory-driven repricing only.
- A soft policy cannot set `ticket_status = blocked`.

Acceptance checks:

- Existing official daily output is byte-level or behavior-level unchanged.
- Shadow ticket file validates.
- Core fields pass round-trip tests.
- `silent_hold_rate` is zero for emitted hold tickets.
- `non_executable_violation_count` is zero.
- Tests cover add, reduce, hold, scheduled DCA, blocked-by-hard-guardrail,
  adjusted-size, and missing-data cases.

## Phase 2: Layered Retrieval Pack

Purpose:

- Feed the new action debate with structured facts, signals, memory, policy, and
  skill candidates instead of a flat RAG dump.

Candidate files:

```text
scripts/layered_context_models.py
scripts/build_layered_retrieval_pack.py
tests/test_layered_retrieval_pack.py
db/retrieval_packs/<report_date>.json
```

Pack sections:

```text
raw_observation_refs
canonical_facts
derived_signals
decision_history
outcome_history
similar_cases
adaptive_policies
strategy_skill_candidates
execution_visibility
missing_data
```

Technical decisions:

- Canonical facts needed for reasoning are copied into compact fields and keep
  source refs.
- Long text evidence is referenced and summarized, not fully copied.
- RAG hits are not treated as truth. They enter as `similar_cases`,
  `anti_patterns`, or `long_text_evidence`.
- Execution-only fields carry a visibility flag and must not be retrieved into
  public/general memory.
- Every item gets `as_of_date`, `available_from`, and `source_path`.

No-future protection:

- Reuse the existing RAG no-future testing pattern.
- Add pack-level tests that fail if `available_from` is later than the decision
  cutoff.

Acceptance checks:

- Pack builds from existing artifacts.
- Missing/stale/conflicted fields are explicit.
- Execution-only values are separated from strategy-learning values.
- `trace_completeness_rate` is measured.
- Canonical facts come from structured lookup, not semantic retrieval.

## Phase 3: LangGraph Debate-To-Action Shadow

Purpose:

- Introduce graph orchestration for the new daily decision loop while keeping
  old advice untouched.

Candidate files:

```text
scripts/action_debate_graph.py
scripts/action_debate_prompts.py
scripts/run_action_debate_shadow.py
tests/test_action_debate_graph.py
```

Graph shape:

```text
load_retrieval_pack
-> analyst_evidence_view
-> bull_case
-> bear_case
-> debate_referee
-> action_former
-> hard_guardrail_check
-> soft_policy_reprice
-> ticket_writer
```

State boundary:

- Graph state stores ids, refs, node status, compact summaries, and failure
  metadata.
- Large source facts stay in files and are referenced.
- Official portfolio state, official NAV, and execution sync are not owned by
  graph state.
- Nodes should stay thin. A node should represent a meaningful reasoning or IO
  boundary, not become a large financial transformation module.

Checkpoint decision:

- Start with local file-backed run metadata if LangGraph checkpoint setup is
  not yet stable in the local environment.
- Move to a LangGraph-supported checkpoint backend only after rerun/recovery
  needs are clear.

Failure behavior:

- If a reasoning node fails, write `ticket_status = degraded` or a degraded
  debate artifact.
- Do not fall back by mutating official `validated_advice`.
- Surface node-level failure in the workbench later.

Acceptance checks:

- Shadow graph is rerunnable for the same report date.
- Partial failure is visible and non-destructive.
- Graph state size remains small and contains refs rather than large facts.
- The old multi-agent chain still produces the same official output.

## Phase 4: Outcome Evaluation Loop

Purpose:

- Score action-ticket quality with official data and feed learning.

Candidate files:

```text
scripts/outcome_event_models.py
scripts/evaluate_action_ticket_outcomes.py
tests/test_action_outcomes.py
db/outcome_events/<base_date>__<horizon>.json
```

Initial horizons:

```text
T+1
T+5
```

Outcome fields:

```text
outcome_id
ticket_id
base_date
evaluation_date
horizon
fund_code
action_verb
amount
official_nav_start
official_nav_end
actual_return_pct
benchmark_return_pct
excess_return_pct
no_action_baseline
outcome_label
diagnostic_label
scoring_status
blocked_reason
source_refs
```

Technical decisions:

- Use official NAV when available.
- If official NAV is missing, mark outcome `pending`.
- If cashflow, unit mismatch, or reconciliation uncertainty makes scoring
  unreliable, mark outcome `blocked`.
- Hold decisions are evaluated for missed opportunity and avoided loss, not
  ignored.
- Conditional actions that did not trigger are evaluated as timing/wait
  decisions, not as failed trades by default.

Acceptance checks:

- Outcome events trace back to action tickets.
- Pending and blocked states are explicit.
- No unofficial PnL is promoted into outcome truth.

## Phase 5: Adaptive Policy Memory

Purpose:

- Turn repeated outcomes into adaptive soft constraints and preferences.

Candidate files:

```text
scripts/adaptive_policy_models.py
scripts/update_adaptive_policies.py
tests/test_adaptive_policies.py
db/strategy_memory/policies.json
db/strategy_memory/policy_events.jsonl
```

Policy lifecycle:

```text
draft -> candidate -> active -> weakened -> revised -> archived
```

Policy fields:

```text
policy_id
scope
status
statement
when_to_apply
effect_type
effect_value
support_count
contradiction_count
confidence
source_outcome_ids
last_reviewed_at
version
```

Technical decisions:

- Policy events are append-only.
- `policies.json` is a materialized current view.
- Active soft policies are capped by scope and confidence to prevent memory
  explosion.
- User feedback can promote, weaken, or archive a policy, but the event remains
  auditable.
- Soft policy effects are additive or repricing effects, not vetoes.

Acceptance checks:

- Repeated supportive outcomes can promote a candidate policy.
- Contradictions weaken or revise policies.
- Soft policies cannot hard-block a ticket.

## Phase 6: Strategy Skill Curator

Purpose:

- Convert stable policy clusters and repeated decision procedures into reusable
  strategy skills.

Candidate files:

```text
scripts/strategy_skill_models.py
scripts/strategy_skill_store.py
scripts/run_skill_curator.py
tests/test_strategy_skills.py
db/strategy_skills/registry.json
db/strategy_skills/<skill_id>/skill.md
db/strategy_skills/<skill_id>/events.jsonl
```

Skill lifecycle:

```text
draft -> candidate -> active -> strengthened -> revised -> archived
```

Skill document sections:

```text
name
status
version
scope
when_to_apply
required_inputs
procedure
position_sizing_notes
invalidation_conditions
anti_patterns
evidence_requirements
known_failure_modes
source_policy_ids
source_outcome_ids
```

Technical decisions:

- Store human-readable Markdown plus registry metadata.
- Skill Curator writes draft or candidate skills by default.
- Active promotion requires outcome evidence or explicit user approval.
- Automatic activation remains disabled in early implementation.
- Skill use is recorded on action tickets through `skill_refs` and
  `skill_outputs`.
- Skill Curator does not edit hard constraints.

Acceptance checks:

- Skill Curator can propose a draft skill from policy/outcome clusters.
- Active skills can be selected into a skill pack.
- Ticket output records which skills were used and what they contributed.

## Phase 7: Workbench Review Surface

Purpose:

- Let the user inspect old advice versus new shadow tickets before promotion.
- Full UI can wait, but CLI/Markdown review should exist earlier.

Candidate files:

```text
app/api_contracts.py
app/web_api_services.py
scripts/render_refactor_review.py
frontend/src/app/pages/TodayPage.tsx
frontend/src/app/pages/ResearchPage.tsx
frontend/src/lib/api.ts
tests/test_web_api_action_tickets.py
db/refactor_reviews/<report_date>.md
```

Initial UI decision:

- Start read-only.
- Show old official advice beside new shadow tickets.
- Show hard guardrail results, soft policy adjustments, debate summary, and
  outcome status.
- Do not attach execution buttons to shadow tickets.

Possible placement:

- Today Analysis if the goal is daily decision review.
- Research/Strategy Lab if the goal is long-term learning inspection.

Recommended first cut:

- Before UI: render CLI/Markdown review from shadow artifacts.
- Add read-only comparison to Today Analysis.
- Add management controls only after ticket/policy/skill artifacts stabilize.

Acceptance checks:

- Markdown review can be generated before UI exists.
- User can compare official advice and shadow tickets for the same date.
- Shadow artifacts are clearly marked as non-executable.
- UI remains usable when shadow files are missing.

## Phase 8: Legacy Chain Replacement And Downline

Purpose:

- Replace legacy responsibilities one at a time, keep fallback and compatibility
  outputs, then downline old layers only after evidence is strong.

Candidate targets:

```text
scripts/committee_synthesis.py
scripts/generate_llm_advice.py
scripts/review_advice.py
scripts/portfolio_optimizer.py
scripts/run_multiagent_research.py
```

Reduction rules:

- Do not delete compatibility outputs until every downstream consumer has
  migrated.
- Keep a fallback switch during replacement.
- Monitor fallback usage before deleting old code.
- Convert validator behavior into hard-guardrail checks.
- Convert optimizer behavior into action-ticket portfolio selection.
- Keep legacy restore path documented until a stable release checkpoint exists.

Acceptance checks:

- New chain can produce official advice.
- Compatibility tests pass during transition.
- Fallback restores the old path.
- Downlined legacy behavior is intentionally documented, not accidental cleanup.

## Cross-Phase Validation Matrix

Minimum validation after each implementation branch:

```text
python -B -X utf8 -m py_compile <changed python files>
python -B -X utf8 -m unittest <new focused tests>
python -B -X utf8 -m unittest tests.test_pipeline_logic tests.test_multiagent_and_review tests.test_validation_and_trade
```

Additional checks by phase:

- Phase 0.5: golden slice replay and diff report tests.
- Phase 1: action-ticket artifact validation and no mutation of official advice.
- Phase 2: no-future retrieval-pack tests and visibility-boundary tests.
- Phase 3: graph rerun/degraded-output tests.
- Phase 4: official NAV pending/blocked/scored outcome tests.
- Phase 5: policy promotion, contradiction, and no-hard-block tests.
- Phase 6: skill lifecycle and draft-only curator tests.
- Phase 7: API DTO and missing-shadow-file UI tests.
- Phase 8: compatibility-output and rollback-path tests.

## First Coding Branch Lock Points

Before starting `codex/action-ticket-shadow-foundation`, lock these details:

- exact action ticket dataclass fields
- exact action and execution-mode enums
- whether legacy `hold_actions` are all converted or filtered to meaningful
  holds
- whether Phase 1 includes `db/action_debates` or only ticket-level debate
  summaries
- path helper names in `scripts/common.py`
- whether `build_action_ticket_shadow.py` runs standalone only or is also added
  to `run_daily_pipeline.py` as an optional shadow step

Recommended first implementation choice:

- Keep `build_action_ticket_shadow.py` standalone.
- Add common path helpers only if they are needed by tests or later scripts.
- Add pipeline integration in a later branch after the artifact format is stable.
