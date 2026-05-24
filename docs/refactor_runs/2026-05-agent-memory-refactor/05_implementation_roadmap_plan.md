# 05 Implementation Roadmap Plan

Status: accepted implementation principle, pending phase execution.

Baseline commit before this refactor: `7984fb1`.

## Goal

Implement the accepted OKRA refactor through staged, non-destructive migration.
The refined target is to make one decision auditable, replayable, and
learnable before expanding the system.

The accepted principle is:

```text
new chain first
old chain preserved
shadow comparison
gradual takeover
replace with fallback
then downline redundant legacy layers
```

This roadmap exists to prevent the refactor from becoming a risky one-shot
rewrite or a pile of disconnected infrastructure.

## Branch Strategy

The local `main` currently contains cleanup commits and uncommitted planning
docs. Implementation should branch only after the planning docs are committed or
otherwise checkpointed.

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

Practical rules:

- Keep planning docs on one planning branch or commit before code work.
- Each implementation branch should have one dominant artifact family.
- The first implementation branch should be `codex/golden-vertical-slice`,
  because broad action-ticket work must be proven on a fixed replayable slice
  before expansion.
- Do not mix UI review surfaces, schema changes, graph orchestration, and memory
  promotion in one branch.
- Merge only after tests and artifact compatibility checks pass.
- Keep `main` as rollback-safe checkpoint.

## Phase 0: Planning And Schema Lock

Purpose:

- finalize schemas before implementation churn
- avoid disagreement between action tickets, retrieval packs, outcomes, and
  skill records

Scope:

- docs only
- JSON schema examples
- compatibility notes
- test plan

Outputs:

- accepted plan docs
- schema drafts
- migration checklist

Do not:

- change daily-analysis behavior
- add LangGraph dependency yet
- alter validated advice outputs

Technical details to settle:

- whether schemas live as Pydantic models, TypedDicts, JSON schema files, or a
  combination
- naming convention for ids and refs
- whether dates are report date, observation date, NAV date, or evaluation date
- how to represent missing versus stale versus contradicted data

Recommended decision:

- Use Python model files for runtime validation and tests.
- Include JSON examples in docs.
- Use stable ids with prefixes such as `ticket:`, `event:`, `policy:`,
  `skill:`, and `fact:`.

## Phase 0.5: Golden Vertical Slice

Purpose:

- create a fixed sample set and replay harness before broad implementation
- prove the first end-to-end path on one date, one fund, and one action type

Scope:

- fixture inputs
- golden expected outputs
- replay command
- diff report
- runtime boundary checks

Vertical slice:

```text
validated_advice -> action_ticket -> retrieval_pack -> outcome_event
```

Candidate files:

- `tests/fixtures/golden_slices/<slice_id>/input/`
- `tests/fixtures/golden_slices/<slice_id>/expected/`
- `tests/test_refactor_golden_slice.py`
- `scripts/replay_refactor_slice.py`
- `scripts/diff_refactor_slice.py`
- `db/refactor_shadow_runs/<slice_id>/`

Acceptance:

- replay produces deterministic output
- diff report is generated
- forbidden write count is zero
- official artifacts are unchanged
- boundary checks for `shadow_only`, `learning_only`, and `non_executable` pass

## Phase 1: Action Ticket Shadow Foundation

Purpose:

- create the core action-ticket artifact without changing existing advice

Scope:

- action ticket schema
- action debate schema
- shadow builder using current validated advice and committee bundle as input
- tests

Candidate files:

- `scripts/action_ticket_models.py`
- `scripts/build_action_ticket_shadow.py`
- `tests/test_action_tickets.py`
- `db/action_tickets/<date>.json`
- `db/action_debates/<date>.json`

Behavior:

- reads current artifacts
- writes shadow artifacts
- does not mutate portfolio, execution state, validated advice, or long memory

Technical details that may diverge:

- Should action tickets be created per fund, per proposed action, or per
  portfolio-level move?
- Should `hold` always have a ticket, or only when it is meaningful?
- Should amount be fixed CNY amount, size bucket, percent of position, or all
  three?
- Should action type include `watch`, `conditional`, or represent those as
  timing states?
- Which fields are core versus extension fields?

Recommended decision:

- Ticket granularity: one ticket per fund/action candidate.
- Always produce a ticket for any held fund with non-trivial signal or explicit
  wait condition.
- Keep Phase 1 core fields compact; store amount/confidence/thesis/guardrails
  and source mapping first.
- Treat percent fields, rich debate, opportunity cost, skills, and soft policy
  details as extension fields.
- Represent `conditional` as timing/execution mode, not as a separate action
  verb.

Acceptance:

- Existing daily pipeline output unchanged.
- Shadow artifact validates against model.
- Core fields round-trip deterministically.
- Silent hold rate is zero for emitted hold tickets.
- Boundary violation count is zero.
- Tests cover add, reduce, hold, watch, blocked, and adjusted tickets.

## Phase 2: Layered Retrieval Pack

Purpose:

- create the data pack action-ticket generation will consume

Scope:

- adapters from existing artifacts
- fact/signal/memory/policy/skill sections
- missing-data classification

Candidate files:

- `scripts/layered_context_models.py`
- `scripts/build_layered_retrieval_pack.py`
- `tests/test_layered_retrieval_pack.py`
- `db/retrieval_packs/<date>.json`

Behavior:

- reads existing data
- normalizes into layered pack
- does not replace `build_llm_context.py`

Technical details that may diverge:

- Whether canonical facts should be copied into pack or referenced by id.
- Whether raw evidence text should be embedded in pack.
- Whether RAG hits should be included directly or represented as refs.
- How to avoid future data leakage in pack building.
- How to separate execution-only data from strategy memory.

Recommended decision:

- Include compact fact values needed for the decision and keep source refs.
- Store long text as refs plus summaries.
- Use structured lookup for canonical facts and RAG/vector retrieval only for
  recall enhancement.
- Add `available_from`, `as_of_date`, and `source_path` to every pack item.
- Preserve execution-only visibility flags.

Acceptance:

- Pack builds from current data.
- No-future and execution-boundary tests pass.
- Missing/stale data are explicit.
- Trace completeness is measured.

## Phase 3: LangGraph Debate-To-Action Shadow

Purpose:

- introduce graph orchestration for the new action pipeline

Scope:

- LangGraph dependency
- graph state schema
- graph nodes for debate-to-action
- shadow runner

Candidate files:

- `scripts/action_debate_graph.py`
- `scripts/run_action_debate_shadow.py`
- `scripts/action_debate_prompts.py`
- `tests/test_action_debate_graph.py`

Behavior:

- reads layered retrieval pack
- produces action tickets
- does not replace existing multi-agent output

Technical details that may diverge:

- Checkpoint backend: in-memory, SQLite, or file-backed checkpoint.
- Whether each agent call is a graph node or grouped into fewer nodes.
- Whether deterministic transforms should be graph nodes.
- How graph state references large artifacts.
- Whether LLM failures degrade to partial tickets or abort graph.

Recommended decision:

- Start with local checkpoint backend if available; otherwise file-backed graph
  runtime metadata.
- Keep large data outside state; store refs.
- Keep nodes thin and use graph nodes for meaningful reasoning or IO
  boundaries, not every helper function.
- On LLM failure, write explicit degraded shadow output rather than changing
  official advice.

Acceptance:

- Shadow graph is rerunnable.
- Partial failure is visible.
- Existing advice and execution state unchanged.

## Phase 4: Outcome Evaluation Loop

Purpose:

- evaluate action-ticket quality over time

Scope:

- outcome event schema
- comparison against official NAV and no-action baseline
- horizon evaluation

Candidate files:

- `scripts/outcome_event_models.py`
- `scripts/evaluate_action_ticket_outcomes.py`
- `tests/test_action_outcomes.py`
- `db/outcome_events/<date>.json`

Technical details that may diverge:

- Which horizon matters first: T+1, T+5, T+20, or all.
- How to score hold decisions and missed opportunities.
- How to evaluate conditional actions that did not trigger.
- How to handle cashflow between decision and outcome.
- How to compare against benchmark/proxy versus actual fund NAV.

Recommended decision:

- Start with T+1 and T+5.
- Treat hold as an action with missed-opportunity classification.
- Use official NAV when available; otherwise mark outcome pending.
- Explicitly block outcome scoring when cashflow makes units unreliable.

Acceptance:

- Outcomes are traceable to tickets.
- Pending/blocked outcome states are explicit.
- No official PnL assumptions are invented.

## Phase 5: Adaptive Policy Memory

Purpose:

- turn repeated outcomes into adaptive soft constraints

Scope:

- adaptive policy schema
- promotion/weakening rules
- link to action tickets and outcomes

Candidate files:

- `scripts/adaptive_policy_models.py`
- `scripts/update_adaptive_policies.py`
- `tests/test_adaptive_policies.py`
- `db/strategy_memory/policies.json`

Technical details that may diverge:

- Promotion thresholds.
- Contradiction weighting.
- Whether user feedback overrides outcome support.
- How to prevent policy explosion.
- How to keep soft policies from becoming hidden hard constraints.

Recommended decision:

- Require multiple supports before active status.
- Keep contradiction counts and decay.
- Limit active policies by scope and confidence.
- Every policy effect must be additive or repricing, not direct veto.

Acceptance:

- Soft policies can reduce size/confidence or add trigger.
- Soft policies cannot hard-block actions.
- Policy provenance is auditable.

## Phase 6: Strategy Skill Curator

Purpose:

- convert stable policy clusters into reusable strategy skills

Scope:

- skill Markdown/metadata registry
- Skill Curator Agent
- skill usage tracking
- skill review events

Candidate files:

- `scripts/strategy_skill_models.py`
- `scripts/strategy_skill_store.py`
- `scripts/run_skill_curator.py`
- `tests/test_strategy_skills.py`
- `db/strategy_skills/`

Technical details that may diverge:

- Whether skills are Markdown, JSON, SQLite rows, or hybrid.
- Whether Skill Curator writes active skills directly.
- How to version skills.
- How user review is represented.
- How to detect skill failure.

Recommended decision:

- Store human-readable Markdown plus registry metadata.
- Skill Curator writes draft/candidate by default.
- Active promotion requires outcome support or explicit user approval.
- Do not automatically activate skills in the early implementation.
- Version skills and keep skill events append-only.

Acceptance:

- Skill Curator cannot alter hard constraints.
- Skills can be selected into a skill pack.
- Action tickets can record skill usage and outputs.

## Phase 7: Workbench Review Surface

Purpose:

- expose old versus new decisions and allow review

Scope:

- action ticket list
- old advice comparison
- skill and policy visibility
- manual promote/demote/archive controls later

Technical details that may diverge:

- Whether this belongs in Today Analysis, Review, or a new Strategy Lab page.
- How much raw debate text to show.
- How to display uncertainty without overwhelming the user.

Recommended decision:

- Add a CLI/Markdown review before the full Workbench UI.
- Start with read-only comparison in Today Analysis or Research page.
- Add management controls only after artifacts stabilize.

Acceptance:

- Markdown review can show official advice, shadow tickets, guardrails, trace
  completeness, outcome status, diff, and boundary checks.
- User can compare old validated advice and new shadow tickets.
- No execution button is attached to shadow tickets initially.

## Phase 8: Legacy Chain Replacement And Downline

Purpose:

- replace old responsibilities one by one, keep fallback, then downline old
  layers only after shadow evidence is strong

Scope:

- reduce committee/validator duplication
- replace legacy action generation
- keep hard guardrails
- keep compatibility output and fallback during transition

Technical details that may diverge:

- Which old artifact remains as compatibility output.
- Whether validator becomes guardrail-only or disappears.
- Whether optimizer becomes selector-only.

Recommended decision:

- Keep compatibility output until UI and downstream consumers migrate.
- Promote replacement behind a fallback switch.
- Monitor fallback usage before deleting old code.
- Convert validator into hard-guardrail checker.
- Convert optimizer into portfolio selector over action tickets.

Acceptance:

- New chain can produce official advice.
- Old chain can still be restored through fallback before code is downlined.
- Tests cover old-output compatibility until removal is intentional.

## Technical Risks And Clarifications

### Risk: RAG Is Mistaken For Memory

Clarification:

- RAG is only retrieval.
- Facts, policies, skills, and outcomes need explicit schemas.

### Risk: LangGraph State Becomes A Database

Clarification:

- LangGraph state stores orchestration state and refs only.
- Financial truth stays in structured artifacts.

### Risk: Soft Constraints Become Hidden Hard Constraints

Clarification:

- Soft constraints can reprice actions.
- They cannot veto unless separately promoted into a hard constraint by later
  design.

### Risk: Skill Curator Overwrites Strategy Too Aggressively

Clarification:

- Skill Curator starts with draft/candidate outputs.
- Promotion requires evidence or user review.

### Risk: Shadow Outputs Accidentally Affect Execution

Clarification:

- Shadow artifacts must be read-only for decision display.
- They cannot mutate validated advice, portfolio state, or execution sync.
- Runtime boundary checks should enforce `shadow_only`, `learning_only`, and
  `non_executable`; documentation labels alone are insufficient.

### Risk: Outcome Evaluation Uses Inaccurate Data

Clarification:

- Use official NAV and trusted units.
- Mark outcomes pending or blocked when data is insufficient.

## Accepted User Decision

The staged implementation principle is accepted.

The implementation should proceed step by step, with detailed technical
decisions documented before each phase. Ambiguous technical details should be
made explicit rather than assumed.

Detailed execution and technical lock points are recorded in
`06_execution_technical_plan.md`.
