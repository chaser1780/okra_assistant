# 04 LangGraph Shadow Orchestration Plan

Status: accepted direction, pending implementation design.

Baseline commit before this refactor: `7984fb1`.

## Goal

Introduce LangGraph as the orchestration layer for OKRA's new agent decision
loops without migrating the entire existing deterministic pipeline.

The target is:

```text
deterministic data pipeline remains local Python
new agent decision loops run as LangGraph shadow graphs
stable shadow outputs can later replace selected old responsibilities behind
fallback before monitored legacy downline
```

LangGraph should improve stateful orchestration, checkpointing, human-in-the-
loop flow, and traceability. It should not become the source of truth for
financial facts.

## Core Principle

Use LangGraph for orchestration state.

Do not use LangGraph as:

- the canonical financial database
- the portfolio state source
- the execution sync source
- the official NAV / PnL source
- the long-term memory store itself

Financial facts remain in structured local artifacts or SQLite-backed stores.
LangGraph reads those facts through controlled inputs and writes traceable
decision artifacts.

## Why LangGraph Fits

The new architecture contains naturally graph-shaped workflows:

- debate-to-action
- skill curation
- outcome evaluation
- human review and resume
- checkpointed multi-step agent decisions

These workflows need:

- durable node state
- resume after partial failure
- traceable node outputs
- human-in-the-loop interrupts
- explicit edges between reasoning steps

LangGraph is a good fit for these needs.

## What Should Use LangGraph

### Debate To Action Graph

Purpose: generate action tickets.

Flow:

```text
build layered retrieval pack
-> normalize analyst evidence
-> bull case
-> bear case
-> cross debate
-> strategy/trader synthesis
-> risk repricing
-> portfolio selection
-> write action tickets
```

Primary outputs:

- `db/action_debates/<date>.json`
- `db/action_tickets/<date>.json`

### Skill Curator Graph

Purpose: convert outcomes into adaptive policies and strategy skills.

Flow:

```text
collect outcomes
-> diagnose patterns
-> update adaptive policies
-> draft or revise skills
-> skill curator review
-> write skill events
```

Primary outputs:

- `db/strategy_memory/`
- `db/strategy_skills/`
- skill review artifacts

### Outcome Evaluation Graph

Purpose: evaluate action tickets over T+1 / T+5 / T+20 or other horizons.

Flow:

```text
load action tickets
-> load official outcomes
-> compare against no-action baseline
-> classify outcome
-> write outcome events
```

Primary outputs:

- `db/outcome_events/<date>.json`
- outcome references for memory and skill evaluation

## What Should Not Use LangGraph

Keep these as deterministic local code paths:

- quote fetching
- news fetching
- fund profile fetching
- official NAV and real daily PnL writing
- portfolio state reconciliation
- execution sync
- pending confirmation updates
- canonical fact writes
- local API and frontend shell

LangGraph can read outputs from these components, but it should not own them.

## LangGraph State Boundary

LangGraph state should be small and orchestration-focused.

Allowed state:

```json
{
  "run_id": "...",
  "report_date": "2026-05-23",
  "retrieval_pack_id": "...",
  "bull_case": {},
  "bear_case": {},
  "debate_summary": {},
  "draft_tickets": [],
  "risk_adjusted_tickets": [],
  "final_tickets": [],
  "errors": [],
  "node_timings": {}
}
```

Do not store these directly in LangGraph state:

- full portfolio history
- full news corpus
- full long-memory export
- full NAV history
- all execution records
- canonical fact source of truth

Use ids, refs, and artifact paths instead.

## Shadow Mode Entry Point

Initial entry point:

```text
scripts/run_action_debate_shadow.py
```

Responsibilities:

1. Load current date and project home.
2. Build or load layered retrieval pack.
3. Run the LangGraph `debate_to_action_graph`.
4. Write `db/action_debates/<date>.json`.
5. Write `db/action_tickets/<date>.json`.
6. Write graph runtime metadata and errors.
7. Do not alter existing `validated_advice` or execution artifacts.

This lets OKRA compare old and new decisions safely.

## Compatibility With Existing OKRA

During shadow mode:

- existing daily analysis remains the official output
- action tickets are experimental artifacts
- UI may display old advice and new action-ticket comparison
- tests should verify shadow graph does not change portfolio state
- long-memory learning can optionally read shadow tickets only after explicit
  design review

## Human-In-The-Loop

LangGraph should support future human review points.

Possible interrupt points:

- approve skill promotion
- approve high-impact action ticket
- resolve hard-constraint ambiguity
- archive or revise a strategy skill
- confirm soft-policy promotion

Human review should be explicit and recorded as an event.

## Failure And Resume

Graph runs should support:

- node-level failure capture
- checkpoint resume
- partial artifact inspection
- safe rerun with same input refs
- no portfolio mutation during shadow runs

This should reduce the current long-chain fragility of daily multi-agent
analysis.

## Implementation Sequence

1. Add dependency and small compatibility wrapper.
2. Define graph state schema.
3. Implement `debate_to_action_graph` in shadow mode.
4. Add `run_action_debate_shadow.py`.
5. Write action debates and action tickets.
6. Add comparison against existing validated advice.
7. Add tests that shadow graph cannot mutate canonical state.
8. Later add skill curator and outcome evaluation graphs.

## Accepted User Decision

This plan is accepted as the fourth formal refactor direction.

LangGraph should be introduced as a shadow orchestration layer for the new
agent decision loops. It should not replace the deterministic data pipeline or
become the source of truth for financial facts.
