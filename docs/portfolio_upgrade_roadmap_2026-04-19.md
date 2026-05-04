# okra assistant 2026-04-19 Upgrade Roadmap

## Scope

This roadmap expands three high-priority upgrades into an executable engineering plan:

1. Historical replay and experiment framework
2. Unified evidence indexing and agent-side retrieval
3. Portfolio-level optimization instead of per-fund sequential clipping

The goal is not to replace the current system. The goal is to preserve the current production path, add an experiment-safe layer beside it, and then move the production path onto the stronger foundation.

## Principles

1. Every new layer must be traceable and reversible.
2. Replay and optimization must run on frozen historical inputs.
3. Retrieval must reduce prompt noise without hiding evidence.
4. Portfolio decisions must be evaluated at the combination level, not only at the single-fund level.
5. New artifacts must be serializable to disk so the desktop layer can inspect them later.

## Current State

The current project already has strong building blocks:

- Structured context and evidence assembly in `scripts/build_llm_context.py`
- Multi-stage committee workflow in `scripts/run_multiagent_research.py`
- Rule validation in `scripts/validate_llm_advice.py`
- Review and memory loop in `scripts/review_advice.py` and `scripts/update_review_memory.py`
- Task manifests and desktop observability

The missing gap is not "whether the system works". The missing gap is "whether the system can be replayed, compared, and globally optimized with confidence".

## Track A: Historical Replay / Experiment Framework

### Objective

Turn historical runs into a reusable experiment set so prompt, model, validation, and optimizer changes can be compared on frozen data instead of judged from intuition.

### Phase A1: Artifact Standardization

Status:
- Start now

Work:
- Standardize replay input sources: `llm_advice`, `llm_raw`, `portfolio_state` snapshots, `validated_advice`, `review_results`, `execution_reviews`, `source_health`, `agent_outputs`
- Add a dedicated replay artifact directory under `db/replay_experiments/<experiment_id>`
- Define one replay summary schema with:
  - experiment metadata
  - processed dates
  - skipped dates and reasons
  - day-level action summaries
  - review outcome summaries
  - fallback / degraded / stale counts

Deliverables:
- `scripts/run_replay_experiment.py`
- replay summary JSON
- replay report markdown

Acceptance:
- A single command can replay a date range without mutating production validated artifacts by default.
- The experiment output shows date-level differences and aggregate metrics.

### Phase A2: Revalidation Mode

Status:
- Start now with validation-layer replay

Work:
- Support replaying historical `llm_advice` through the current validator and optimizer
- Load historical portfolio snapshots for the corresponding date
- Compare:
  - existing validated actions
  - replayed validated actions
  - action count
  - gross trade
  - net buy
  - review linkage

Deliverables:
- replay mode: `baseline`
- replay mode: `revalidate`

Acceptance:
- The same historical `llm_advice` can be re-run through a new validator without overwriting baseline files.
- The summary clearly states which dates changed and how.

### Phase A3: Frozen End-to-End Replay

Status:
- Next milestone after A1/A2

Work:
- Freeze and replay not only validation, but also context shaping and multi-agent execution
- Version prompt bundles and retrieval rules
- Store experiment config digests beside replay outputs

Deliverables:
- experiment config snapshots
- prompt/retrieval version trace

Acceptance:
- A user can answer: "Did the new prompt actually improve historical outcomes?"

## Track B: Unified Evidence Layer and Retrieval

### Objective

Move from "large context JSON pushed into every agent" to "indexed evidence plus role-aware retrieval", while preserving transparency and traceability.

### Phase B1: Evidence Index Foundation

Status:
- Start now

Work:
- Build a dedicated evidence index artifact from `llm_context`
- Index by:
  - evidence id
  - fund code
  - evidence type
  - source role
  - freshness
  - confidence
  - retrieval tokens
- Preserve raw evidence linkage instead of inventing new opaque summaries

Deliverables:
- `scripts/evidence_index.py`
- `scripts/build_evidence_index.py`
- `db/evidence_index/<date>.json`

Acceptance:
- A historical day has a stable on-disk evidence index that can be loaded without rebuilding the whole context.

### Phase B2: Agent-Aware Retrieval

Status:
- Start now

Work:
- Add role-aware retrieval preferences per agent:
  - market / regime
  - theme / structure
  - quality / profile
  - event / sentiment
  - committee / execution
- Add fund-scoped and portfolio-scoped retrieval
- Inject only retrieved evidence into agent inputs instead of the entire evidence pool
- Preserve retrieval scores and evidence ids so outputs remain auditable

Deliverables:
- retrieval metadata in agent input
- compact retrieved evidence blocks

Acceptance:
- Agent prompts receive smaller, more focused evidence bundles.
- The desktop/debug artifacts can still explain which evidence was shown to each agent.

### Phase B3: Retrieval Evaluation

Status:
- Next milestone

Work:
- Track retrieval coverage:
  - how many retrieved evidence hits were stale
  - how many were direct-fund vs background evidence
  - which source roles dominate each agent
- Add retrieval diagnostics to replay experiments

Deliverables:
- retrieval diagnostics summary
- retrieval hit distributions

Acceptance:
- The team can detect when an agent is repeatedly fed low-value or stale evidence.

## Track C: Portfolio-Level Optimization

### Objective

Replace the current greedy per-fund clipping with combination-level selection under shared cash, gross trade, net buy, allocation, and friction constraints.

### Phase C1: Candidate Normalization

Status:
- Start now

Work:
- Normalize every non-hold committee output into a portfolio candidate with:
  - action
  - amount after fund-local caps
  - bucket / theme metadata
  - confidence
  - evidence count
  - support count
  - risk count
  - estimated friction
- Preserve rejected candidates as first-class records, not silent drops

Deliverables:
- `scripts/portfolio_optimizer.py`
- optimizer candidate schema

Acceptance:
- Validation can explain why a candidate existed even if it was not selected.

### Phase C2: Combination Search

Status:
- Start now

Work:
- Search over feasible action combinations subject to:
  - gross trade budget
  - net buy budget
  - available funding after sells
  - max actions per day
  - locked amount / sellable amount
  - allocation band guardrails
- Score combinations using:
  - model confidence
  - priority
  - evidence/support density
  - risk and cost penalties
  - drift improvement
  - concentration penalties

Deliverables:
- optimizer summary embedded in validated advice
- selected and rejected candidate traces

Acceptance:
- The chosen action set is the best feasible portfolio combination found, not simply the first feasible items in priority order.

### Phase C3: Optimization Replay

Status:
- Start now through Track A integration

Work:
- Run the optimizer in replay mode across historical days
- Compare optimizer-selected actions versus existing validated actions
- Track whether optimizer changes reduce:
  - over-concentration
  - wasted gross trade
  - low-confidence adds

Deliverables:
- replay delta metrics for optimizer impact

Acceptance:
- The team can answer whether portfolio optimization improved historical decision quality.

## Implementation Order

1. Add artifact paths, typed schemas, and test fixtures.
2. Build the evidence index and wire retrieval into multi-agent inputs.
3. Refactor validation into a reusable function and add the optimizer.
4. Add replay experiment commands and reports.
5. Extend tests to cover retrieval, optimization, and replay summaries.

## Immediate Deliverables In This Iteration

1. Evidence index artifact and role-aware retrieval wiring
2. Combination-based portfolio optimizer in the validator
3. Replay experiment command for baseline and revalidate modes
4. Tests covering the new foundation

## Deferred But Required Follow-Up

1. End-to-end frozen replay for context and agent outputs
2. Retrieval quality dashboards in desktop UI
3. Richer execution-cost modeling
4. Prompt/version digests attached to replay outputs
