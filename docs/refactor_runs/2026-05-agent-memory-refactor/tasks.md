# Task Log

This file will track agreed tasks, status, owners, validation, and follow-up
notes for the refactor.

## Accepted Planning Items

- [accepted] `01_debate_to_action_plan.md`: define the target debate-to-action
  mechanism and action-ticket-centered decision flow.
- [accepted] `02_data_memory_layering_plan.md`: define layered financial data,
  memory, adaptive soft constraints, and strategy skill direction.
- [accepted] `03_closed_loop_strategy_skills_plan.md`: define closed-loop
  strategy-skill growth and the Skill Curator Agent.
- [accepted] `04_langgraph_shadow_orchestration_plan.md`: define LangGraph as
  the shadow orchestration layer for new agent decision loops.
- [accepted] `05_implementation_roadmap_plan.md`: define staged branch,
  implementation, validation, and technical-ambiguity handling.
- [accepted] `06_execution_technical_plan.md`: define execution contract,
  branch layout, artifact boundaries, model-style choices, and phase-level
  technical lock points.
- [accepted] `07_docs_engineering_review.md`: review docs readiness and record
  implementation-level gaps.
- [accepted] `08_phase_dependency_and_impact_matrix.md`: record Phase 0-8
  dependencies, non-parallelizable work, data-flow dependencies, and test
  impacts.
- [accepted] `09_untouched_function_impact_map.md`: record boundaries and
  regression focus for unchanged but affected functions.
- [accepted] `10_technical_route_assessment.md`: assess the selected technical
  route against external reference patterns and OKRA constraints.
- [accepted] `schema_examples/`: lock concrete examples for action tickets,
  retrieval packs, outcome events, adaptive policies, and strategy skills.
- [accepted] `hard_constraints_inventory.md`: map current deterministic
  validator, optimizer, execution, reconciliation, and state rules to future
  action-ticket guardrails.
- [accepted] `phase_checklists/`: provide Phase 0-8 execution checklists with
  allowed writes, forbidden writes, tests, manual verification, rollback, and
  promotion gates.
- [accepted] `api_contracts_shadow_review.md`: draft read-only Workbench API
  contract for old-versus-new shadow review.
- [accepted] `11_review_refinement_and_vertical_slice.md`: narrow the
  implementation target to auditable/replayable/learnable decisions, add Phase
  0.5 golden vertical slice, KPIs, compact core fields, early Markdown review,
  and runtime boundary checks.

## Pending Implementation Tasks

- [done] Create or commit planning checkpoint before implementation branches.
- [done] Create Phase 0.5 golden slice fixtures and expected outputs.
- [done] Implement `scripts/replay_refactor_slice.py` and
  `scripts/diff_refactor_slice.py`.
- [done] Implement or stub `scripts/artifact_boundary.py` for runtime
  `shadow_only`, `learning_only`, and `non_executable` checks.
- [pending] Create `codex/action-ticket-shadow-foundation` only after Phase
  0.5 golden slice passes and the planning checkpoint is safe.
- [pending] Finalize Phase 1 action-ticket dataclass fields and enums.
- [pending] Implement standalone `build_action_ticket_shadow.py` without adding
  it to the official daily pipeline yet.
- [pending] Add focused action-ticket tests for add, reduce, scheduled DCA,
  meaningful hold, hard-blocked, soft-adjusted, and missing-data tickets.
- [pending] Add action-ticket dataclass round-trip tests with fixed clock.
- [pending] Finalize Phase 2 retrieval-pack dataclasses and no-future checks.
- [pending] Design retrieval-pack builder for action-ticket generation.
- [pending] Add retrieval-pack round-trip tests and trace completeness metric.
- [pending] Classify existing hard constraints and keep them explicit.
- [pending] Design adaptive soft-constraint memory lifecycle.
- [pending] Design adaptive policy promotion, weakening, contradiction, and
  cap rules.
- [pending] Define strategy skill Markdown and registry metadata schema.
- [pending] Add strategy skill registry/Markdown frontmatter round-trip tests.
- [pending] Design Skill Curator Agent input/output contract.
- [pending] Design skill-pack builder and skill usage tracking.
- [pending] Design skill outcome evaluation and promotion/revision rules.
- [pending] Decide LangGraph dependency/version and checkpoint backend before
  Phase 3 coding.
- [pending] Define graph state schema for `debate_to_action_graph`.
- [pending] Implement `run_action_debate_shadow.py` as non-mutating shadow entry.
- [pending] Add CLI/Markdown refactor review before full Workbench UI.
- [pending] Add read-only Workbench comparison only after shadow artifacts
  stabilize.

## Completed Documentation Tasks

| Task | Phase | Output | Completion evidence |
|---|---|---|---|
| Phase 0 schema examples | 0 | `schema_examples/*` | JSON/Markdown examples added for all planned artifact families |
| Hard constraints inventory | 0/1 | `hard_constraints_inventory.md` | Current deterministic rules mapped to future guardrails |
| Phase checklists | 0-8 | `phase_checklists/*` | Each phase now has allowed writes, forbidden writes, tests, rollback, and promotion gate |
| Shadow review API draft | 7 | `api_contracts_shadow_review.md` | Read-only DTO, empty states, and non-executable contract drafted |
| RAG current-status update | 2/RAG | `docs/okra_unified_rag_architecture.md` | Implemented/partial/design-only status recorded |
| Workbench API contract update | 7/UI | `docs/modern_workbench.md` | Current envelope, routes, DTOs, error behavior, and compatibility risks recorded |
| Review refinement | 0.5/all | `11_review_refinement_and_vertical_slice.md` | User review incorporated into route, KPIs, core fields, boundary checks, and replacement/fallback strategy |
| Phase 0.5 golden vertical slice | 0.5 | `tests/fixtures/golden_slices/2026-05-22__017641__scheduled_dca/`, `scripts/replay_refactor_slice.py`, `scripts/diff_refactor_slice.py`, `scripts/artifact_boundary.py` | `python -B -X utf8 -m unittest tests.test_refactor_golden_slice` passed; replay diff verdict PASS |

## Phase Execution Board Template

Use this structure once implementation branches begin:

| Phase | Status | Owner / agent | Depends on | Write scope | Output artifact | Validation command | Completion evidence | Notes |
|---|---|---|---|---|---|---|---|---|
| Phase 0.5 | done | Codex | Phase 0 | `tests/fixtures/golden_slices/*`, `scripts/replay_refactor_slice.py`, `scripts/diff_refactor_slice.py`, optional `scripts/artifact_boundary.py` | `db/refactor_shadow_runs/2026-05-22__017641__scheduled_dca/`, `diff_report.md` | `python -B -X utf8 -m unittest tests.test_refactor_golden_slice` | PASS; `2026-05-22 + 017641 + scheduled_dca` locked | One date, one fund, one action type |
| Phase 1 | pending | unassigned | Phase 0 + Phase 0.5 | `scripts/action_ticket_models.py`, `scripts/build_action_ticket_shadow.py`, `tests/test_action_tickets.py` | `db/action_tickets/<date>.json` | `python -B -X utf8 -m unittest tests.test_action_tickets` | to be filled after implementation | Keep standalone first |
