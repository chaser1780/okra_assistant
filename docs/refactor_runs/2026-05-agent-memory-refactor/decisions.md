# Decisions

This file records accepted architecture decisions and unresolved questions for
the refactor.

## Accepted Direction: Debate To Action

- OKRA will treat action tickets as the center of the future daily decision
  flow.
- Bull/bear debate must be action-centered and include timing, size,
  invalidation, and opportunity cost.
- The strategy/trader layer should own action formation.
- Risk should become hard guardrail plus soft repricing, not a default veto
  layer.
- Soft constraints should be adaptive and connected to long memory.
- Hard constraints stay preserved for now; their final boundary will be
  discussed later.

## Accepted Direction: Data And Memory Layering

- OKRA will not treat long memory as simple RAG.
- The future data model should distinguish raw observations, canonical facts,
  derived signals, decision events, outcome events, strategy memory, and strategy
  skills.
- Current facts and execution-critical values should use structured lookup, not
  vector retrieval as the primary mechanism.
- Similar cases, anti-patterns, long text evidence, and policy explanations can
  use retrieval/RAG.
- Adaptive soft constraints should grow from action outcomes and long-memory
  learning.
- Strategy skills should emerge from repeated, validated strategy procedures.

## Accepted Direction: Closed Loop Strategy Skills

- OKRA should convert experience into strategy memory, adaptive policies, and
  eventually reusable strategy skills.
- Strategy skills are procedural memory, not facts and not simple retrieved
  text.
- A new Skill Curator Agent is accepted.
- The Skill Curator Agent works in the learning loop, not as an intraday trading
  decision maker.
- Strategy skills should have explicit lifecycle states: draft, candidate,
  active, strengthened, revised, archived.
- Daily action tickets should record which skills were used and what outputs
  those skills produced.
- Skill outcome evaluation should strengthen, revise, or archive skills over
  time.

## Accepted Direction: LangGraph Shadow Orchestration

- LangGraph should be introduced for new agent decision loops in shadow mode.
- It should orchestrate debate-to-action, Skill Curator, and outcome evaluation
  graphs.
- It should not replace deterministic data fetching, official NAV/PnL writing,
  portfolio state reconciliation, execution sync, or canonical fact storage.
- LangGraph state should contain orchestration state and refs, not full
  financial source-of-truth data.
- The first likely entry point is `scripts/run_action_debate_shadow.py`.
- Shadow outputs should not mutate existing `validated_advice` or execution
  state.

## Accepted Direction: Staged Implementation

- Implementation should use a new chain first, preserve the old chain, run in
  shadow mode, compare outputs, replace selected responsibilities behind
  fallback, monitor compatibility, and only then downline redundant legacy
  layers.
- Branches should be split by artifact family and implementation phase.
- Each phase should document technical ambiguities before code changes.
- Shadow artifacts must be non-mutating until explicitly promoted.
- Compatibility outputs should remain until UI and downstream consumers migrate.

## Accepted Direction: Execution Technical Contract

- `06_execution_technical_plan.md` is the formal execution contract for turning
  accepted architecture principles into code.
- Planning documents should be committed or checkpointed before implementation
  branches are created.
- Initial shadow artifact paths are:
  - `db/action_tickets/<report_date>.json`
  - `db/action_debates/<report_date>.json`
  - `db/retrieval_packs/<report_date>.json`
  - `db/outcome_events/<base_date>__<horizon>.json`
  - `db/strategy_memory/policies.json`
  - `db/strategy_memory/policy_events.jsonl`
  - `db/strategy_skills/registry.json`
  - `db/strategy_skills/<skill_id>/skill.md`
- Persisted shadow artifacts should start with dataclass validation, following
  the existing `scripts/rag_models.py` pattern.
- API/workbench contracts should use Pydantic DTOs only when the review surface
  is added.
- New artifacts must distinguish `report_date`, `as_of_date`,
  `available_from`, `generated_at`, `nav_date`, and `evaluation_date`.
- Missing data must use explicit states such as `missing`, `stale`,
  `conflicted`, `pending`, and `blocked`.
- Phase 1 should keep `build_action_ticket_shadow.py` standalone; optional
  daily-pipeline integration should wait until the artifact format is stable.

## Accepted Direction: Documentation Review And Readiness

- `07_docs_engineering_review.md` records that the current documents are strong
  enough for architecture and roadmap guidance, but still need schema examples,
  hard-constraint inventory, phase checklists, RAG implementation status, and
  API contract drafts for implementation-level precision.
- `08_phase_dependency_and_impact_matrix.md` is the dependency map for Phase 0-8
  and should guide branch order and parallel work assignment.
- `09_untouched_function_impact_map.md` records protection boundaries for
  features not directly targeted by the refactor.
- `10_technical_route_assessment.md` records that the selected route is
  reasonable and advanced, with LangGraph used for orchestration, RAG used as
  retrieval evidence rather than truth, and local structured artifacts used for
  financial state and memory.
- If earlier plans conflict with the later engineering review:
  - `06_execution_technical_plan.md` owns implementation details.
  - `08_phase_dependency_and_impact_matrix.md` owns phase dependencies.
  - `09_untouched_function_impact_map.md` owns untouched-function protection
    boundaries.
  - `10_technical_route_assessment.md` owns the technical-route assessment.

## Accepted Direction: Phase 0 Implementation Anchors

- Schema examples are now the concrete artifact references before coding:
  action tickets, retrieval packs, outcome events, adaptive policies, and
  strategy skills.
- `hard_constraints_inventory.md` is the source for preserving current
  deterministic hard constraints during Phase 1 guardrail mapping.
- `phase_checklists/` is the per-phase execution boundary. A branch should not
  write outside its allowed scope without updating the relevant checklist first.
- `api_contracts_shadow_review.md` is the Phase 7 read-only API contract draft.
- Current RAG status is: implemented foundation with gated/partial production
  use, not a design-only blank slate and not the source of truth for financial
  facts.
- Current Workbench API status is: envelope-wrapped modern routes with
  `/api/workbench/*` compatibility aliases and legacy raw `/api/snapshot`.
- Shadow artifacts remain non-executable until an explicit later promotion.

## Accepted Direction: Review Refinement And Vertical Slice

- The practical implementation goal is now: make one decision auditable,
  replayable, and learnable.
- Action tickets should not become a second large knowledge base; Phase 1 uses
  compact core fields and optional extension fields.
- Add Phase 0.5 before broad Phase 1 implementation: one date, one fund, one
  action type, golden inputs, golden outputs, replay command, and diff report.
- Each phase needs exit metrics such as trace completeness, silent hold rate,
  shadow/official comparability, unapproved replay diff count, fallback rate,
  and boundary violation count.
- CLI/Markdown review should exist before the full Workbench UI.
- `shadow_only`, `learning_only`, and `non_executable` boundaries must be
  enforced in runtime checks, not only in documentation.
- Dataclass models become the single runtime contract for persisted shadow
  artifacts once code exists; JSON examples are fixtures/examples.
- Every persisted artifact family should get round-trip tests.
- LangGraph nodes should be thin, with small state containing refs and runtime
  status only.
- RAG/vector retrieval stays pluggable and secondary to structured lookup for
  current facts.
- Strategy skills stay draft/candidate unless outcome evidence or explicit user
  approval promotes them.
- Phase 8 means replacement plus fallback plus monitored downline, not direct
  deletion.
