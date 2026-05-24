# 08 Phase Dependency And Impact Matrix

Status: dependency and impact matrix recorded before implementation.

This document makes the connections between Phase 0-8 explicit. It should be
used before creating or assigning implementation branches.

## Migration Principle

The accepted migration sequence remains:

```text
new chain first
old chain preserved
shadow comparison
gradual takeover
replacement with fallback
monitor
legacy downline after evidence
```

This means a phase can only mutate official outputs after an explicit promotion
decision. Until then, the new chain writes shadow artifacts.

## Main Dependency Chain

```text
Phase 0: Schema Lock
  -> Phase 0.5: Golden Vertical Slice
  -> Phase 1: Action Ticket Shadow Foundation
      -> Phase 2: Layered Retrieval Pack
          -> Phase 3: LangGraph Debate-To-Action Shadow
      -> Phase 4: Outcome Evaluation Loop
          -> Phase 5: Adaptive Policy Memory
              -> Phase 6: Strategy Skill Curator
      -> Phase 7: Workbench Review Surface
          -> Phase 8: Legacy Chain Reduction
```

The practical backbone is:

```text
action ticket
-> layered evidence
-> shadow debate
-> outcome event
-> adaptive policy
-> strategy skill
-> read-only review
-> legacy reduction
```

## Phase Dependency Table

| Phase | Depends on | Feeds | Can start before dependency is complete? | Notes |
|---|---|---|---|---|
| Phase 0: Schema Lock | Accepted plans | All phases | No | Owns schema examples, date semantics, id rules, missing-data states, phase checklists. |
| Phase 0.5: Golden Vertical Slice | Phase 0 | Phase 1, 2, 4, 7, 8 | No | Owns fixed sample, golden outputs, replay command, diff report, and boundary checks. |
| Phase 1: Action Ticket Shadow Foundation | Phase 0, Phase 0.5 fixtures | Phase 3, 4, 5, 6, 7, 8 | No | Action ticket is the shared decision id for debate, outcomes, policy, skill usage, UI review, and official promotion. |
| Phase 2: Layered Retrieval Pack | Phase 0, Phase 1 schema | Phase 3, 5, 6 | Schema design can overlap with Phase 1; implementation should follow Phase 1 | Prevents LangGraph from reading scattered context or flat RAG dumps. |
| Phase 3: LangGraph Debate-To-Action Shadow | Phase 1, Phase 2 | Phase 7, later official action generation | No for real graph implementation | Can prototype graph skeleton, but real nodes should consume retrieval packs and write action tickets. |
| Phase 4: Outcome Evaluation Loop | Phase 1, official NAV/PnL facts | Phase 5, 6 | Schema can start after Phase 1 schema locks | Cannot learn from outcomes until official data exists. Missing data must be pending/blocked. |
| Phase 5: Adaptive Policy Memory | Phase 4 outcome events | Phase 2, 3, 6 | Lifecycle schema can start early; promotion logic cannot | Soft policies reprice, annotate, or add triggers. They do not block. |
| Phase 6: Strategy Skill Curator | Phase 5 policy clusters, Phase 4 outcomes | Phase 2, 3, 7 | Registry/template can start early; active skills cannot | Curator defaults to draft/candidate. Active promotion needs evidence or user approval. |
| Phase 7: Workbench Review Surface | Phase 1/3 artifacts; optional Phase 4-6 | Phase 8 | API sketch can start early; UI should wait | First version must be read-only and non-executable. |
| Phase 8: Legacy Chain Reduction | Phase 1-7 evidence and migration | Final official chain | No | Last phase only. Requires compatibility and rollback plan. |

## Non-Parallelizable Work

### Phase 0 Before Code

Do not implement persisted artifacts before Phase 0 locks:

- model style
- action enum
- execution mode enum
- date semantics
- id prefixes
- missing-data states
- artifact paths
- write ownership

Reason:

- All later phases persist JSON artifacts that must remain stable across scripts,
  tests, UI, graph state, and long-memory updates.

### Phase 0.5 Before Broad Implementation

Do not expand to the whole portfolio before the golden slice can replay:

- action ticket
- retrieval pack
- outcome event
- diff report
- boundary check result

Reason:

- The refactor goal is audit/replay/learning. If one fixed decision cannot be
  replayed and compared, broader infrastructure will hide defects instead of
  reducing risk.

### Phase 1 Before Outcome, Policy, Skill, UI, And Legacy Reduction

Do not implement outcome scoring, adaptive policy update, strategy skill usage,
or workbench review around a non-final ticket shape.

Reason:

- `ticket_id` is the shared join key.
- Changes to ticket shape after those phases start will cascade across the
  project.

### Phase 2 Before Real LangGraph Debate

Do not let LangGraph nodes directly read:

- raw `llm_context`
- raw RAG hits
- raw long-memory records
- raw portfolio snapshots
- scattered JSON from multiple directories

Reason:

- The accepted architecture requires data layering. The graph should consume a
  retrieval pack with explicit facts, signals, memory, policy, skills, source
  refs, visibility, and missing-data states.

### Phase 4 Before Policy Promotion

Do not promote adaptive policies from anecdotal LLM reasoning alone.

Reason:

- The accepted learning loop is outcome-backed.
- Without outcome events, policy memory becomes prompt drift rather than
  measurable strategy learning.

### Phase 8 Last

Do not delete or weaken legacy daily-analysis layers until replacement and
fallback have both proven stable:

- new chain produces official-compatible advice
- workbench can show new and old outputs
- downstream consumers are mapped
- compatibility outputs are preserved or intentionally replaced
- fallback switch exists
- fallback usage is monitored
- rollback checkpoint exists

Reason:

- Current OKRA already has a usable daily pipeline, execution sync, official
  valuation, Copilot, and workbench. Legacy reduction is the payoff, not the
  starting point.

## Work That Can Proceed In Parallel

### Documentation And Schema Drafting

Can proceed in parallel:

- action ticket schema example
- retrieval pack schema example
- outcome event schema example
- adaptive policy schema example
- strategy skill Markdown template
- phase checklist templates
- KPI/exit metric definitions

Constraint:

- These must converge before code writes persisted artifacts.

### Phase 1 And Phase 2 Design Discussion

Can overlap:

- ticket fields
- retrieval pack sections
- evidence refs
- missing-data semantics
- execution visibility labels

Implementation order:

1. Phase 0.5 golden slice fixtures.
2. Phase 1 minimal action ticket.
3. Phase 2 retrieval pack builder.

### Phase 4 Outcome Schema After Phase 1 Schema Lock

Can start before Phase 3:

- outcome event dataclass
- pending/blocked/scored states
- T+1/T+5 horizon definitions
- official NAV source mapping

Constraint:

- Real scoring must use official NAV and trusted units only.

### Phase 5/6 Lifecycle Design

Can start as schema/template work:

- policy lifecycle states
- policy event log shape
- strategy skill registry
- skill Markdown sections
- curator output contract

Constraint:

- Active policies and active skills must not be created without outcome support
  or explicit user approval.

### Phase 7 Interface Sketch

Can start as a draft:

- read-only API payload
- missing shadow artifact empty state
- non-executable display labels
- old-versus-new comparison fields
- CLI/Markdown review template

Constraint:

- Do not bind UI to raw artifact internals before Phase 1/3 artifact schemas
  stabilize.
- Do not wait for UI before reviewing the new chain; use CLI/Markdown review
  after the first slice.

### Phase 0.5 Data Flow

```text
fixed fixture inputs
-> replay_refactor_slice.py
-> action_ticket + retrieval_pack + outcome_event
-> diff_refactor_slice.py
-> diff_report
```

Writes:

- `db/refactor_shadow_runs/<slice_id>/`
- test fixture expected outputs only when explicitly approved

Must not write:

- official advice
- portfolio state
- execution sync
- long memory

## Data Flow By Phase

### Phase 1 Data Flow

```text
validated_advice + committee bundle + portfolio/fund metadata
-> build_action_ticket_shadow.py
-> db/action_tickets/<report_date>.json
-> optional db/action_debates/<report_date>.json
```

Writes:

- shadow ticket/debate only

Must not write:

- `db/validated_advice/`
- `db/portfolio_state/`
- `db/execution_sync/`
- `db/long_memory/`

### Phase 2 Data Flow

```text
structured facts + derived signals + memory refs + RAG refs + execution visibility
-> build_layered_retrieval_pack.py
-> db/retrieval_packs/<report_date>.json
```

Writes:

- retrieval pack only

Must not do:

- treat RAG hits as truth
- expose execution-only data into general strategy memory
- include future data

### Phase 3 Data Flow

```text
retrieval pack
-> LangGraph debate-to-action graph
-> shadow debate metadata
-> shadow action tickets
```

Writes:

- graph run metadata
- shadow debate/ticket outputs

Must not write:

- official advice
- portfolio state
- execution sync

Graph state rule:

- State contains refs, compact summaries, node status, and failures only.
- Large financial facts remain in retrieval packs or source artifacts.

### Phase 4 Data Flow

```text
action tickets + official NAV + benchmark/proxy + trusted units/cashflow context
-> evaluate_action_ticket_outcomes.py
-> outcome events
```

Writes:

- outcome events only

Must not do:

- infer missing official NAV
- score through unreliable cashflow/unit states
- overwrite official valuation artifacts

### Phase 5 Data Flow

```text
outcome events + action tickets + user feedback
-> update_adaptive_policies.py
-> policy event log + current policy view
```

Writes:

- `db/strategy_memory/policy_events.jsonl`
- `db/strategy_memory/policies.json`

Must not do:

- create hidden hard vetoes
- mutate hard-constraint definitions
- promote unsupported policies to active

### Phase 6 Data Flow

```text
policy clusters + outcome support + action-ticket history
-> Skill Curator
-> draft/candidate strategy skills
```

Writes:

- `db/strategy_skills/registry.json`
- `db/strategy_skills/<skill_id>/skill.md`
- `db/strategy_skills/<skill_id>/events.jsonl`

Must not do:

- directly alter hard constraints
- make draft skills active without evidence or approval

### Phase 7 Data Flow

```text
validated_advice + action tickets + debates + outcomes + policies + skills
-> CLI/Markdown review
-> API DTO later
-> read-only workbench comparison later
```

Writes:

- no investment state
- UI code and API DTO only

Must not do:

- attach execution buttons to shadow tickets
- hide missing shadow artifacts as normal official output

### Phase 8 Data Flow

```text
shadow evidence + compatibility map + user review
-> selected official chain replacement behind fallback
-> monitor fallback and compatibility
-> legacy downline/reduction
```

Writes:

- official chain only after explicit promotion

Must preserve:

- rollback path
- compatibility output until consumers migrate
- hard guardrails

## Test Dependency Matrix

| Test area | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Phase 6 | Phase 7 | Phase 8 |
|---|---|---|---|---|---|---|---|---|
| `tests.test_pipeline_logic` | required | required | required | required | required | required | required | required |
| `tests.test_multiagent_and_review` | required | required | required | required | optional | optional | required | required |
| `tests.test_validation_and_trade` | required | optional | required | optional | optional | optional | required | required |
| `tests.test_revaluation_and_realtime` | optional | optional | optional | required | required | optional | optional | required |
| `tests.test_execution_sync` | optional | required | optional | required | required | optional | required | required |
| `test_rag_*.py` | optional | required | required | optional | optional | optional | optional | required if RAG consumers change |
| `tests.test_long_memory` | optional | required | optional | optional | required | required | required | required |
| frontend build | no | no | no | no | no | no | required | required |

Every implementation branch should also run focused tests for the new artifact
family it introduces.

Additional Phase 0.5 tests:

- golden slice replay;
- golden diff report;
- forbidden write detection;
- boundary check enforcement;
- deterministic round-trip for any artifact included in the slice.

## Merge Order

Recommended merge order:

1. planning checkpoint
2. Phase 0 schema examples and checklists
3. Phase 0.5 golden vertical slice
4. Phase 1 action ticket shadow
5. Phase 2 layered retrieval pack
6. Phase 3 LangGraph shadow debate
7. Phase 4 outcome evaluation
8. Phase 5 adaptive policy memory
9. Phase 6 strategy skill curator
10. Phase 7 read-only CLI/Workbench review
11. Phase 8 replacement, fallback, and legacy downline

If a later phase exposes a schema defect, the fix should be made in the earliest
owning phase and then propagated forward.
