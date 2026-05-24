# Accepted Plan Index

This file confirms the accepted stages discussed so far are fully recorded.

## Stage 1: Debate To Action

Formal plan:

- `01_debate_to_action_plan.md`

Discussion record:

- `discussions/2026-05-23-debate-to-action.md`

Accepted decisions:

- Action tickets become the center of the future daily decision flow.
- Bull/bear debate must be action-centered and include timing, size,
  invalidation, and opportunity cost.
- Strategy/trader owns action formation.
- Risk becomes hard guardrail plus soft repricing.
- `hold` must be an explicit action ticket, not a silent fallback.
- Soft constraints are adaptive and connected to long memory.
- Hard constraints stay preserved for now and will be discussed separately.

## Stage 2: Data And Memory Layering

Formal plan:

- `02_data_memory_layering_plan.md`

Discussion record:

- `discussions/2026-05-23-data-memory-layering.md`

Accepted decisions:

- OKRA's memory is a layered financial memory system, not a simple RAG library.
- Adopt raw observations, canonical facts, derived signals, decision events,
  outcome events, strategy memory, and strategy skills.
- Current facts and execution-critical values use structured lookup first.
- Similar cases, anti-patterns, long text evidence, and policy explanations can
  use retrieval/RAG.
- Adaptive soft constraints grow from outcomes and long-memory learning.
- Strategy skills emerge from repeated, validated procedures.

## Stage 3: Closed Loop Strategy Skills

Formal plan:

- `03_closed_loop_strategy_skills_plan.md`

Discussion record:

- `discussions/2026-05-23-closed-loop-strategy-skills.md`

Accepted decisions:

- OKRA should convert experience into strategy memory, adaptive policies, and
  reusable strategy skills.
- Strategy skills are procedural memory.
- A new Skill Curator Agent is accepted.
- Skill lifecycle states are draft, candidate, active, strengthened, revised,
  and archived.
- Daily action tickets should record skill usage and skill outputs.
- Skill outcome evaluation should strengthen, revise, or archive skills.

## Stage 4: LangGraph Shadow Orchestration

Formal plan:

- `04_langgraph_shadow_orchestration_plan.md`

Discussion record:

- `discussions/2026-05-23-langgraph-shadow-orchestration.md`

Accepted decisions:

- Introduce LangGraph as a shadow orchestration layer for new agent decision
  loops.
- Use LangGraph for debate-to-action, Skill Curator, and outcome evaluation
  graphs.
- Keep deterministic data fetching, official NAV/PnL, portfolio reconciliation,
  execution sync, and canonical facts outside LangGraph.
- LangGraph state stores orchestration state and refs, not full financial facts.
- Initial entry point should be a non-mutating shadow script such as
  `scripts/run_action_debate_shadow.py`.

## Stage 5: Implementation Roadmap

Formal plan:

- `05_implementation_roadmap_plan.md`

Discussion record:

- `discussions/2026-05-23-implementation-roadmap.md`

Accepted decisions:

- Implement through staged migration, not a one-shot rewrite.
- Preserve old chain while the new chain runs in shadow mode.
- Split implementation branches by artifact family and phase.
- Document technical ambiguities before each phase.
- Keep shadow artifacts non-mutating until explicitly promoted.
- Delay legacy deletion until the new chain proves itself.

## Stage 6: Execution Technical Plan

Formal plan:

- `06_execution_technical_plan.md`

Discussion record:

- Current user instruction: accepted general principles, require branch
  organization, phase-by-phase implementation steps, and explicit discussion of
  technical details that may diverge.
- `discussions/2026-05-23-execution-technical-plan.md`

Accepted decisions:

- The roadmap is now treated as an implementation contract, not only a strategy
  note.
- Branches are organized by artifact family and phase.
- Persisted shadow artifacts should start with dataclass validation, matching
  the repository's RAG artifact style.
- API/workbench exposure can use Pydantic DTOs later, matching existing
  `app/api_contracts.py`.
- New shadow paths are defined for action tickets, debates, retrieval packs,
  outcome events, adaptive policies, and strategy skills.
- Date semantics, id prefixes, missing-data states, and soft/hard constraint
  boundaries must be explicit before coding each phase.

## Stage 7: Documentation Engineering Review

Review documents:

- `07_docs_engineering_review.md`
- `08_phase_dependency_and_impact_matrix.md`
- `09_untouched_function_impact_map.md`
- `10_technical_route_assessment.md`

Discussion record:

- `discussions/2026-05-24-docs-engineering-review.md`

Accepted review conclusions:

- Current docs are architecture-complete and roadmap-complete, but still need
  schema examples, hard-constraint inventory, and phase checklists before
  implementation can proceed without drift.
- `06_execution_technical_plan.md` is the technical implementation contract when
  earlier plans and later engineering details overlap.
- Phase 1 action tickets are the central join point for debate, outcomes,
  policies, skills, UI review, and legacy reduction.
- The current route is reasonable and advanced because it combines debate,
  layered data, deterministic financial facts, outcome-backed learning, strategy
  skills, shadow orchestration, and read-only human review.
- Unchanged systems such as NAV/PnL, execution sync, Alipay screenshot sync,
  Copilot, RAG, daily pipeline, long memory, and Workbench must keep explicit
  protection boundaries during the refactor.

## Stage 8: Phase 0 Implementation Anchors

Implementation contract documents:

- `schema_examples/action_ticket.example.json`
- `schema_examples/retrieval_pack.example.json`
- `schema_examples/outcome_event.example.json`
- `schema_examples/adaptive_policy.example.json`
- `schema_examples/strategy_skill.example.md`
- `hard_constraints_inventory.md`
- `phase_checklists/phase_0_schema_lock.md`
- `phase_checklists/phase_1_action_ticket_shadow.md`
- `phase_checklists/phase_2_layered_retrieval_pack.md`
- `phase_checklists/phase_3_langgraph_debate_shadow.md`
- `phase_checklists/phase_4_outcome_evaluation.md`
- `phase_checklists/phase_5_adaptive_policy_memory.md`
- `phase_checklists/phase_6_strategy_skill_curator.md`
- `phase_checklists/phase_7_workbench_review_surface.md`
- `phase_checklists/phase_8_legacy_chain_reduction.md`
- `api_contracts_shadow_review.md`

Current-state updates:

- `docs/okra_unified_rag_architecture.md`: implementation status and source of
  truth.
- `docs/modern_workbench.md`: current API contract and compatibility notes.

Accepted decisions:

- Phase 0 is now complete enough for implementation planning: examples,
  constraints, phase checklists, and later API review contract all exist.
- Hard constraints remain deterministic and map into future action-ticket
  guardrails.
- Shadow review is read-only, non-executable, and must not mutate portfolio,
  execution, official advice, policy, or skill state.
- RAG is an implemented but gated subsystem: it can feed layered retrieval
  packs, but it is not the source of truth for current financial facts.

## Stage 9: Review Refinement And Vertical Slice

Formal refinement:

- `11_review_refinement_and_vertical_slice.md`

Accepted decisions:

- The implementation target is narrowed to making one decision auditable,
  replayable, and learnable.
- Add Phase 0.5 before broad Phase 1 implementation.
- Start with one fixed vertical slice:
  `validated_advice -> action_ticket -> retrieval_pack -> outcome_event`.
- Use golden fixtures, golden outputs, replay command, and diff report.
- Phase 1 action-ticket fields are split into compact core fields and optional
  extension fields.
- Add runtime boundary checks for `shadow_only`, `learning_only`, and
  `non_executable`; documentation labels alone are insufficient.
- Full Phase 7 UI can wait, but CLI/Markdown review should appear earlier.
- Phase 8 is replacement plus fallback plus monitored downline, not direct
  deletion.
- LangGraph nodes stay thin and graph state stays small.
- RAG remains pluggable retrieval enhancement; structured lookup owns current
  facts.
- Strategy skills stay draft/candidate by default and require evidence or user
  approval before activation.

## Cross-File Coverage

- `README.md` lists all accepted formal plans.
- `tasks.md` lists accepted planning items and pending implementation tasks.
- `decisions.md` records accepted architecture directions.
- `execution-log.md` records documentation completeness checks and accepted
  stages.
- `discussions/` preserves step-by-step conversation checkpoints.
