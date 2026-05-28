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
- [done] Finalize Phase 1 action-ticket dataclass fields and enums.
- [done] Implement standalone `build_action_ticket_shadow.py` without adding
  it to the official daily pipeline yet.
- [done] Add focused action-ticket tests for add, reduce, scheduled DCA,
  meaningful hold, hard-blocked, soft-adjusted, and missing-data tickets.
- [done] Add action-ticket dataclass round-trip tests with fixed clock.
- [done] Finalize Phase 2 retrieval-pack dataclasses and no-future checks.
- [done] Design retrieval-pack builder for action-ticket generation.
- [done] Add retrieval-pack round-trip tests and trace completeness metric.
- [pending] Classify existing hard constraints and keep them explicit.
- [done] Design adaptive soft-constraint memory lifecycle.
- [done] Design adaptive policy promotion, weakening, contradiction, and
  cap rules.
- [done] Define strategy skill Markdown and registry metadata schema.
- [done] Add strategy skill registry/Markdown frontmatter round-trip tests.
- [done] Design Skill Curator Agent input/output contract.
- [pending] Design skill-pack builder and skill usage tracking.
- [pending] Design skill outcome evaluation and promotion/revision rules.
- [done] Decide LangGraph dependency/version and checkpoint backend before
  Phase 3 coding.
- [done] Define graph state schema for `debate_to_action_graph`.
- [done] Implement `run_action_debate_shadow.py` as non-mutating shadow entry.
- [done] Implement Phase 4 outcome event model and standalone evaluator.
- [done] Add CLI/Markdown refactor review before full Workbench UI.
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
| Phase 1 | partial | Codex | Phase 0 + Phase 0.5 | `scripts/action_ticket_models.py`, `scripts/build_action_ticket_shadow.py`, `tests/test_action_tickets.py` | `db/action_tickets/<date>.json` | `python -B -X utf8 -m unittest tests.test_action_tickets` | PASS; `2026-05-22` produced 15 shadow-only tickets, including `017641` scheduled DCA | Standalone only; not integrated into daily pipeline/UI |
| Phase 2 | partial | Codex | Phase 1 | `scripts/layered_context_models.py`, `scripts/build_layered_retrieval_pack.py`, `tests/test_layered_retrieval_pack.py` | `db/retrieval_packs/<date>.json` | `python -B -X utf8 -m unittest tests.test_layered_retrieval_pack` | PASS; `2026-05-22` produced 15 packs, trace completeness 1.0, no-future violations 0 | Standalone only; RAG non-canonical and disabled by default |
| Phase 3 | partial | Codex | Phase 1 + Phase 2 | `scripts/action_debate_graph.py`, `scripts/action_debate_prompts.py`, `scripts/run_action_debate_shadow.py`, `tests/test_action_debate_graph.py` | `db/action_debates/<date>.json`, `db/action_debates/runtime/<date>.json` | `python -B -X utf8 -m unittest tests.test_action_debate_graph` | PASS; `2026-05-22` produced 15 shadow debates, node failures 0, state size 5960 bytes | Local file-backed shadow graph; no external LangGraph dependency yet; no ticket rewrite |
| Phase 4 | partial | Codex | Phase 1 + official NAV facts | `scripts/outcome_event_models.py`, `scripts/evaluate_action_ticket_outcomes.py`, `tests/test_action_outcomes.py` | `db/outcome_events/<base_date>__<horizon>.json` | `python -B -X utf8 -m unittest tests.test_action_outcomes` | PASS; `2026-05-22` T+1 produced 15 scored outcome events, T+5 produced 15 pending events | Learning-only, non-executable; no portfolio, execution, long-memory, policy, or skill writes |
| Phase 5 | partial | Codex | Phase 4 outcome events | `scripts/adaptive_policy_models.py`, `scripts/update_adaptive_policies.py`, `tests/test_adaptive_policies.py` | `db/strategy_memory/policy_events.jsonl`, `db/strategy_memory/policies.json` | `python -B -X utf8 -m unittest tests.test_adaptive_policies` | PASS; `2026-05-22` generated 14 policy events and 4 materialized policies; lifecycle, support/contradiction accounting, append-only idempotence, malformed-line isolation, non-blocking effects, and per-scope caps covered | Learning-only, non-executable; no hard constraints, official advice, portfolio state, execution sync, long-memory, or skill writes |
| Phase 6 | partial | Codex | Phase 5 policy clusters + Phase 4 outcomes | `scripts/strategy_skill_models.py`, `scripts/strategy_skill_store.py`, `scripts/run_skill_curator.py`, `tests/test_strategy_skills.py` | `db/strategy_skills/registry.json`, `db/strategy_skills/<skill_id>/skill.md`, `db/strategy_skills/<skill_id>/events.jsonl` | `python -B -X utf8 -m unittest tests.test_strategy_skills` | PASS; `2026-05-22` generated 2 strategy skills (`draft=1`, `candidate=1`, `active=0`) with append-only lifecycle events | Learning-only, non-executable; auto active promotion disabled; no hard constraints, official advice, portfolio state, execution sync, policy events, or direct graph outputs |
| Phase 7 early review | partial | Codex | Phase 1 + Phase 2 + Phase 3 + optional Phase 4/5/6 | `scripts/render_refactor_review.py`, `tests/test_refactor_review_markdown.py`, `scripts/artifact_boundary.py` | `db/refactor_reviews/<date>.md` | `python -B -X utf8 -m unittest tests.test_refactor_review_markdown` | PASS; `2026-05-22` Markdown review rendered ready status and chained official advice, tickets, packs, debates, outcome events, adaptive policy summary, and strategy skill registry summary | CLI/Markdown only; no API, UI, execution, or long-memory writes |
