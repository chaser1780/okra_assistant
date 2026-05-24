# Phase 0 Checklist: Schema Lock

Status: required before implementation branches.

## Goal

Lock the shared artifact contracts, write scopes, date semantics, id rules,
missing-data states, and implementation ownership before any code writes new
shadow artifacts.

## Allowed Write Set

- `docs/refactor_runs/2026-05-agent-memory-refactor/schema_examples/*`
- `docs/refactor_runs/2026-05-agent-memory-refactor/phase_checklists/*`
- `docs/refactor_runs/2026-05-agent-memory-refactor/hard_constraints_inventory.md`
- `docs/refactor_runs/2026-05-agent-memory-refactor/api_contracts_shadow_review.md`
- `docs/refactor_runs/2026-05-agent-memory-refactor/*` planning/index/log files
- documentation updates in `docs/modern_workbench.md` and
  `docs/okra_unified_rag_architecture.md`

## Forbidden Write Set

- `db/validated_advice/*`
- `db/portfolio_state/*`
- `db/execution_sync/*`
- `db/long_memory/*`
- any production script behavior
- any frontend runtime behavior

## Inputs To Review

- `01_debate_to_action_plan.md`
- `02_data_memory_layering_plan.md`
- `03_closed_loop_strategy_skills_plan.md`
- `04_langgraph_shadow_orchestration_plan.md`
- `05_implementation_roadmap_plan.md`
- `06_execution_technical_plan.md`
- `07_docs_engineering_review.md`
- `08_phase_dependency_and_impact_matrix.md`
- `09_untouched_function_impact_map.md`
- `10_technical_route_assessment.md`
- current hard constraints in validator/optimizer/execution/state modules
- current RAG implementation state
- current Workbench API contract

## Required Outputs

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
- `11_review_refinement_and_vertical_slice.md`
- `phase_checklists/phase_0_5_golden_vertical_slice.md`
- updated RAG implementation status
- updated Workbench API contract notes

## Technical Decisions To Lock

- Persisted shadow artifacts use dataclasses with explicit validation.
- API-facing DTOs use Pydantic when the review surface is added.
- `action_verb` enum is `add | reduce | hold | scheduled_dca | switch_in | switch_out`.
- `execution_mode` enum is `immediate | scheduled | conditional | watch`.
- `hold` is emitted only for a meaningful investment choice, wait condition,
  blocked action, position exposure, or missed-opportunity candidate.
- Soft policies can reprice, annotate, or add wait triggers; they cannot block.
- RAG hits enter layered retrieval packs as evidence, similar cases, or
  anti-patterns; they are not canonical facts.
- LangGraph owns orchestration state and refs only, not financial source of
  truth.
- Early action-ticket implementation uses compact core fields plus optional
  extension fields.
- Every shadow/learning/review artifact should expose `write_scope` and
  `non_executable` where applicable.
- Phase 0.5 golden vertical slice is required before broad Phase 1 expansion.

## Required Validation

```powershell
python -B -X utf8 -m json.tool docs\refactor_runs\2026-05-agent-memory-refactor\schema_examples\action_ticket.example.json
python -B -X utf8 -m json.tool docs\refactor_runs\2026-05-agent-memory-refactor\schema_examples\retrieval_pack.example.json
python -B -X utf8 -m json.tool docs\refactor_runs\2026-05-agent-memory-refactor\schema_examples\outcome_event.example.json
python -B -X utf8 -m json.tool docs\refactor_runs\2026-05-agent-memory-refactor\schema_examples\adaptive_policy.example.json
rg -n "schema_examples|hard_constraints_inventory|phase_checklists|api_contracts_shadow_review" docs
```

## Manual Verification

- Every schema example includes `schema_version`.
- Every shadow example distinguishes core fields from extension fields in the
  implementation notes or checklist.
- Every decision-time artifact includes `report_date`, `generated_at`, and
  source refs.
- Every time-sensitive evidence item includes `as_of_date` and
  `available_from`.
- Every learning artifact distinguishes current view from append-only event
  history.
- Every phase checklist has allowed/forbidden writes.
- No document says shadow output is executable.
- Phase 0.5 has a fixed slice, golden output, and diff-report contract.

## Rollback Notes

Phase 0 has no runtime changes. Rollback is documentation-only. If schema
examples change after Phase 1 starts, update the earliest owning phase and
propagate forward before continuing.

## Promotion Gate

Phase 0.5 can start only when:

- schema examples exist and validate as JSON/Markdown;
- hard constraints are mapped to future guardrails;
- phase checklists exist;
- golden vertical slice scope is selected;
- runtime boundary-check expectations are documented;
- the planning checkpoint is committed or otherwise recorded;
- open questions are explicitly accepted or deferred.

Broad Phase 1 can start only after Phase 0.5 produces a stable golden output,
diff report, and CLI/Markdown review for the selected slice.
