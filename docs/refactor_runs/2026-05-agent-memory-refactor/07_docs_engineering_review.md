# 07 Docs Engineering Review

Status: documentation review completed, follow-up gaps recorded.

Update on 2026-05-24: the implementation anchors identified in this review
have been added. The document still remains useful as the readiness audit, but
the highest-priority gaps below should now be treated as closed unless later
implementation exposes schema drift.

This review answers whether the current `docs/` folder is detailed enough to
guide the upcoming agent/memory refactor as an engineering project.

## Reviewed Scope

Current `docs/` includes:

- `docs/INDEX.md`
- `docs/modern_workbench.md`
- `docs/okra_unified_rag_architecture.md`
- `docs/refactor_runs/README.md`
- `docs/refactor_runs/2026-05-agent-memory-refactor/*`
- `docs/refactor_runs/2026-05-agent-memory-refactor/discussions/*`

The deleted old file `docs/fund_multiagent_design.md` is intentionally excluded.
Its useful content has been superseded by the accepted refactor plans.

## Overall Judgment

After the 2026-05-24 Phase 0 hardening pass, the documentation is strong enough
for:

- product direction
- architecture direction
- staged migration planning
- branch planning
- Phase 1 implementation setup
- preserving long-running design context

It is still not a substitute for code review during implementation, especially
for:

- exact dataclass field decisions when code is written
- edge-case tests discovered during implementation
- user acceptance of open policy/constraint questions
- production promotion evidence

The current plans are therefore best described as:

```text
architecture-complete
roadmap-complete
implementation-contract complete enough for Phase 1
schema examples present
phase checklists present
current-state notes present for RAG and Workbench
```

## Strong Existing Guidance

### `06_execution_technical_plan.md`

This is currently the strongest implementation document. It already provides:

- non-negotiable execution principles
- branch layout
- artifact boundaries
- runtime model style
- date semantics
- id conventions
- missing-data states
- Phase 0-8 candidate files
- phase-level acceptance checks
- validation matrix
- first coding branch lock points

Engineering use:

- Treat it as the implementation contract.
- When `05_implementation_roadmap_plan.md` and `06_execution_technical_plan.md`
  overlap, `06` is the more precise technical source of truth.

### `05_implementation_roadmap_plan.md`

This is the project-management roadmap. It is useful for:

- migration sequence
- branch shape
- phase separation
- broad risk management
- why legacy reduction is delayed

Engineering use:

- Use it for planning and merge order.
- Do not use it as the exact schema or field-level implementation source when
  `06` has more precise details.

### `02_data_memory_layering_plan.md`

This document is central to avoiding a weak RAG-only design. It correctly
separates:

- raw observations
- canonical facts
- derived signals
- decision events
- outcome events
- strategy memory
- strategy skills

Engineering use:

- Treat this as the conceptual data taxonomy.
- Concrete persisted fields should still be locked in schema examples before
  implementation.

### `03_closed_loop_strategy_skills_plan.md`

This document is strong for the long-learning layer. It correctly distinguishes:

- facts
- adaptive policies
- procedural strategy skills
- Skill Curator output
- skill lifecycle
- skill safety boundaries

Engineering use:

- Treat it as the product/behavioral contract for strategy skills.
- Actual skill registry fields and Markdown template still need examples.

### `04_langgraph_shadow_orchestration_plan.md`

This document makes the correct orchestration boundary explicit:

- LangGraph is for new reasoning graphs.
- LangGraph is not the source of financial truth.
- It should not own NAV, PnL, execution sync, or canonical facts.

Engineering use:

- Treat it as the boundary document for graph adoption.
- Detailed graph state schema still belongs in Phase 3 implementation docs.

### `okra_unified_rag_architecture.md`

This remains valuable as the RAG subsystem blueprint. It covers:

- document/chunk metadata
- source tiers
- hard filters
- no-future checks
- fund filtering
- memory status filtering
- execution boundary
- Copilot RAG
- daily-analysis shadow retrieval
- test and risk sections

Engineering use:

- Treat it as RAG design history and subsystem reference.
- It needs an implementation-status section because parts of the RAG foundation
  already exist.

## Gaps To Close Before Coding Beyond Phase 1

### Gap 1: Schema Examples

Status: closed by `schema_examples/`.

`06_execution_technical_plan.md` correctly says Phase 0 should create
`schema_examples/`; that folder now exists.

Required examples:

- `schema_examples/action_ticket.example.json`
- `schema_examples/retrieval_pack.example.json`
- `schema_examples/outcome_event.example.json`
- `schema_examples/adaptive_policy.example.json`
- `schema_examples/strategy_skill.example.md`

Why it matters:

- Prevents field drift between model code, tests, UI DTOs, and future graph
  prompts.
- Gives subagents and future sessions a concrete contract.

Priority:

- Highest before Phase 1 implementation.

### Gap 2: Hard Constraints Inventory

Status: closed by `hard_constraints_inventory.md`.

Earlier plans said hard constraints are preserved but did not enumerate current
hard constraints. The inventory now provides that bridge.

Needed file:

- `hard_constraints_inventory.md`

Minimum contents:

- current hard rule
- source file
- input fields
- whether it blocks, adjusts, or annotates
- current output field
- future action-ticket guardrail mapping
- whether the rule is execution, allocation, cash, settlement, policy, or
  data-quality related

Why it matters:

- Prevents soft memory policies from accidentally replacing deterministic hard
  rules.
- Makes Phase 1 guardrail mapping testable.

Priority:

- Highest before Phase 1 guardrail implementation.

### Gap 3: Phase Checklists

Status: closed by `phase_checklists/`.

The roadmap is detailed, but there is no per-phase execution checklist.

Needed folder:

- `phase_checklists/`

Minimum first file:

- `phase_checklists/phase_1_action_ticket_shadow.md`

Each checklist should include:

- goal
- allowed write set
- forbidden write set
- input artifacts
- output artifacts
- required tests
- manual verification
- rollback notes
- promotion gate

Why it matters:

- Prevents a phase branch from expanding into unrelated UI, RAG, or pipeline
  changes.

Priority:

- High before Phase 1 implementation branch.

### Gap 4: API Contract For Shadow Review

Status: closed by `api_contracts_shadow_review.md`.

Phase 7 is intentionally later, but API shape should be drafted before frontend
work begins.

Needed file:

- `api_contracts_shadow_review.md`

Minimum contents:

- endpoint proposal
- response DTO
- missing-shadow-artifact behavior
- status fields
- display-safe labels
- non-executable flag
- frontend empty states
- compatibility with current workbench page payloads

Why it matters:

- Avoids UI prematurely binding to unstable raw artifact shapes.

Priority:

- Medium; needed before Phase 7, not before Phase 1.

### Gap 5: RAG Implementation Status

Status: closed by the `Implementation Status / Source Of Truth` section in
`docs/okra_unified_rag_architecture.md`.

`okra_unified_rag_architecture.md` is written like a design proposal. The repo
already has RAG implementation modules, tests, fallback behavior, and offline
foundation work.

Needed addition:

- `Implementation Status / Source Of Truth` section near the top of
  `okra_unified_rag_architecture.md`

Minimum contents:

- implemented
- partially implemented
- intentionally disabled or shadow-only
- still design-only
- relation to layered retrieval pack

Why it matters:

- Prevents future implementation from redoing completed RAG work.
- Prevents future sessions from treating RAG as production-default when it is
  still gated.

Priority:

- Medium before Phase 2.

### Gap 6: Tasks As Execution Board

Status: partially closed. `tasks.md` now includes a completed documentation task
table and an execution board template; real owner/status rows should be filled
when implementation branches begin.

Earlier `tasks.md` recorded pending tasks but not enough execution metadata.

Recommended fields:

- phase
- status
- owner or agent
- depends_on
- write scope
- output artifact
- validation command
- completion evidence
- notes

Why it matters:

- The user has explicitly allowed multi-agent work. Without ownership and write
  scopes, parallel implementation can collide.

Priority:

- High before multiple implementation branches or workers are started.

## Repetition And Source-Of-Truth Rules

There is intentional repetition between accepted plans, discussion notes,
decisions, tasks, and logs. This is acceptable if source-of-truth rules are
clear.

Recommended rules:

- `accepted_plan_index.md`: navigation and accepted-stage summary.
- `decisions.md`: final accepted decisions only.
- `tasks.md`: execution state only.
- `execution-log.md`: actual performed actions and validation only.
- `discussions/`: historical conversation checkpoints only.
- `05_implementation_roadmap_plan.md`: phase and branch roadmap.
- `06_execution_technical_plan.md`: technical implementation contract.

When documents conflict:

- Technical implementation details in `06_execution_technical_plan.md` override
  earlier rough schemas in `01` through `05`.
- Architecture intent in `01` through `04` still governs why the technical
  contract exists.
- Discussion notes do not override formal plans unless their accepted decisions
  have been copied into `decisions.md` or a numbered plan.

## Current Potential Conflicts To Clarify

### Action Enum

Earlier draft:

```text
action_type used buy, sell, switch, hold, and watch in one field.
```

Current recommended technical contract:

```text
action_verb: add | reduce | hold | scheduled_dca | switch_in | switch_out
execution_mode: immediate | scheduled | conditional | watch
```

Resolution:

- Use the `06_execution_technical_plan.md` version.
- `watch` is an execution mode, not a trade action.
- `buy/sell` should be normalized to `add/reduce` in OKRA artifacts.

### RAG Versus Layered Retrieval Pack

RAG architecture describes agent profile retrieval. The current refactor
requires layered retrieval packs.

Resolution:

- The new action-ticket chain consumes a layered retrieval pack.
- RAG hits enter the pack only as sections such as `similar_cases`,
  `anti_patterns`, or `long_text_evidence`.
- RAG is not the primary source for current facts, official NAV, positions,
  cash, execution status, or hard constraints.

### Model Style

RAG docs discuss `TypedDict` or dataclass options. Current technical contract
chooses dataclass validation for persisted shadow artifacts.

Resolution:

- Existing RAG model style remains as implemented.
- New persisted shadow artifacts use dataclasses with explicit validation.
- API/workbench DTOs use Pydantic only at the API boundary.

## Readiness By Phase

| Phase | Current readiness | Missing before coding |
|---|---|---|
| Phase 0 | Complete enough for implementation planning | none; keep updated if schemas change |
| Phase 0.5 | Must run before broad Phase 1 | fixed sample, golden output, diff report, and replay command |
| Phase 1 | Ready after Phase 0.5 passes | exact dataclass field names and hold-ticket filter should be finalized from golden-slice evidence |
| Phase 2 | Ready for implementation after Phase 1 schema stability | exact pack dataclass fields and no-future fixture set |
| Phase 3 | Direction ready | graph state schema, dependency decision, checkpoint backend decision |
| Phase 4 | Direction ready | official NAV source mapping and scoring fixtures |
| Phase 5 | Direction ready | promotion thresholds and policy cap values |
| Phase 6 | Direction ready | curator prompt/input contract and registry validation details |
| Phase 7 | Contract drafted | API DTO implementation and UI placement after artifacts stabilize |
| Phase 8 | Not ready by design | migration evidence, downstream consumer map, rollback checkpoint |

## Engineering Verdict

The current documentation is comprehensive at architecture and roadmap level.
It is deliberately cautious about preserving current reliable systems while
building a more autonomous action-ticket and strategy-memory chain.

The next work should not add more broad strategy. The implementation anchors now
exist, so the next engineering step is Phase 0.5 Golden Vertical Slice:

1. create or commit the planning checkpoint
2. create `codex/golden-vertical-slice`
3. select one report date, one fund, and one action type
4. replay `validated_advice -> action_ticket -> retrieval_pack -> outcome_event`
5. produce CLI/Markdown review plus a diff report against golden output
6. keep official daily outputs unchanged

Broad Phase 1 starts only after this slice proves the artifact chain is
auditable, replayable, and learnable without becoming a second knowledge base.
