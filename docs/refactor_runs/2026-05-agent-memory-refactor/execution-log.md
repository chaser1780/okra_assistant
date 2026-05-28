# Execution Log

This file will record implementation steps, commits, validation commands, and
important observations during the refactor.

No implementation entries have been added yet.

## 2026-05-23 Documentation Completeness Check

- Confirmed Stage 1 formal plan exists: `01_debate_to_action_plan.md`.
- Confirmed Stage 2 formal plan exists: `02_data_memory_layering_plan.md`.
- Confirmed discussion records exist under `discussions/`.
- Confirmed `tasks.md` and `decisions.md` reflect both accepted directions.
- Added `accepted_plan_index.md` as a single-page cross-file index for the two
  accepted stages.

## 2026-05-23 Stage 3 Accepted

- Added `03_closed_loop_strategy_skills_plan.md`.
- Recorded the Skill Curator Agent as an accepted direction.
- Updated `README.md`, `tasks.md`, `decisions.md`, `accepted_plan_index.md`,
  and the closed-loop discussion note.

## 2026-05-23 Stage 4 Accepted

- Added `04_langgraph_shadow_orchestration_plan.md`.
- Recorded LangGraph shadow orchestration as accepted direction.
- Updated `README.md`, `tasks.md`, `decisions.md`, `accepted_plan_index.md`,
  and the LangGraph discussion note.

## 2026-05-23 Documentation Index Cleanup

- Updated `accepted_plan_index.md` from the earlier two-stage wording to the
  current multi-stage wording.
- Moved cross-file coverage after the stage entries so the index reads as a
  full accepted-plan map.

## 2026-05-23 Stage 5 Accepted

- Added `05_implementation_roadmap_plan.md`.
- Recorded staged implementation, branch strategy, and technical ambiguity
  handling as accepted direction.
- Updated `README.md`, `tasks.md`, `decisions.md`, `accepted_plan_index.md`,
  and the implementation-roadmap discussion note.

## 2026-05-23 Execution Technical Plan Recorded

- Added `06_execution_technical_plan.md`.
- Converted the accepted general principle into an execution contract covering
  branch layout, artifact paths, schema style, date semantics, id conventions,
  missing-data states, phase-level candidate files, and validation gates.
- Fixed the branch tree in `05_implementation_roadmap_plan.md` to use ASCII so
  it remains stable across Windows terminals.
- Updated `README.md`, `tasks.md`, `decisions.md`, and
  `accepted_plan_index.md` to include the execution technical plan.

## 2026-05-24 Docs Engineering Review

- Reviewed all current files under `docs/`.
- Added `07_docs_engineering_review.md` to assess whether the documentation is
  detailed enough for engineering execution.
- Added `08_phase_dependency_and_impact_matrix.md` to record Phase 0-8
  dependencies, data flow, non-parallelizable work, and test impacts.
- Added `09_untouched_function_impact_map.md` to record boundaries for NAV/PnL,
  execution sync, Alipay screenshots, Copilot, RAG, daily pipeline, long memory,
  Workbench, news collection, and LLM transport.
- Added `10_technical_route_assessment.md` to evaluate the route against
  LangGraph, CrewAI, TradingAgents, FinRobot/FinGPT, Mem0, Zep/Graphiti, and
  Letta-style patterns.
- Updated `README.md`, `tasks.md`, `decisions.md`, and
  `accepted_plan_index.md` so the review documents are discoverable.

## 2026-05-24 Phase 0 Documentation Hardening

- Added concrete schema examples under `schema_examples/`:
  - `action_ticket.example.json`
  - `retrieval_pack.example.json`
  - `outcome_event.example.json`
  - `adaptive_policy.example.json`
  - `strategy_skill.example.md`
- Added `hard_constraints_inventory.md` to map current deterministic rules from
  validator, optimizer, execution sync, trade lifecycle, reconciliation, and
  portfolio state code into future action-ticket guardrails.
- Added Phase 0-8 execution checklists under `phase_checklists/`, including
  allowed write sets, forbidden write sets, inputs, outputs, tests, manual
  verification, rollback, and promotion gates.
- Added `api_contracts_shadow_review.md` as the read-only Workbench API
  contract draft for old-versus-new shadow comparison.
- Updated `docs/okra_unified_rag_architecture.md` with implementation status,
  current config defaults, and relation to layered retrieval packs.
- Updated `docs/modern_workbench.md` with current API envelope, routes, DTO
  boundaries, missing-file behavior, error behavior, and compatibility risks.
- Updated refactor README, accepted plan index, decisions, and task log so the
  new Phase 0 anchors are discoverable.

## 2026-05-24 Review Refinement Applied

- Added `11_review_refinement_and_vertical_slice.md` to incorporate user review
  feedback.
- Narrowed the implementation goal to one decision being auditable, replayable,
  and learnable.
- Added Phase 0.5 golden vertical slice to the roadmap and dependency matrix.
- Added `phase_checklists/phase_0_5_golden_vertical_slice.md`.
- Updated Phase 1 checklist to split action-ticket fields into compact core
  fields and optional extension fields.
- Updated schema examples with `write_scope`, `non_executable`, and core
  contract notes.
- Added KPI/exit metrics, replay/diff expectations, runtime boundary-check
  expectations, CLI/Markdown early review, and Phase 8 replacement/fallback
  semantics.

## 2026-05-24 Phase 0.5 Implemented

- Committed the planning checkpoint before code implementation:
  `ed4b8b8 docs: checkpoint agent memory refactor plan`.
- Per user decision, locked the first golden slice to
  `2026-05-22__017641__scheduled_dca`.
- Added fixed minimal input fixtures under
  `tests/fixtures/golden_slices/2026-05-22__017641__scheduled_dca/input/`.
- Added expected artifacts under the same slice's `expected/` directory:
  `action_ticket.expected.json`, `retrieval_pack.expected.json`,
  `outcome_event.expected.json`, and `diff_report.expected.md`.
- Added `scripts/artifact_boundary.py` with runtime checks for `shadow_only`,
  `learning_only`, forbidden official write paths, and `non_executable=true`.
- Added `scripts/replay_refactor_slice.py` to generate shadow-only action
  ticket and retrieval pack artifacts, plus a learning-only outcome event.
- Added `scripts/diff_refactor_slice.py` to compare replay output with golden
  expected artifacts and report Phase 0.5 KPIs.
- Preserved official outputs: no writes under `db/validated_advice`,
  `db/decision_latest`, `db/decision_ledger`, `db/portfolio_state`,
  `db/execution_sync`, or `db/long_memory`.
- Validation:
  - `python scripts/check_repo_text_hygiene.py`
  - `python -B -X utf8 -m py_compile scripts\artifact_boundary.py scripts\replay_refactor_slice.py scripts\diff_refactor_slice.py tests\test_refactor_golden_slice.py`
  - `python -B -X utf8 -m unittest tests.test_refactor_golden_slice`
  - `python -B -X utf8 scripts\replay_refactor_slice.py --slice-id 2026-05-22__017641__scheduled_dca`
  - `python -B -X utf8 scripts\diff_refactor_slice.py --slice-id 2026-05-22__017641__scheduled_dca`
- Final replay diff verdict: PASS, with forbidden write count 0 and
  non-executable violation count 0.

## 2026-05-24 Phase 1 Action Ticket Shadow Foundation Started

- Implemented the standalone Phase 1 action-ticket shadow foundation without
  wiring it into `scripts/run_daily_pipeline.py` or the Workbench UI.
- Added `scripts/action_ticket_models.py` with compact core dataclasses:
  `ActionTicket`, `ActionTicketArtifact`, `EvidenceRef`,
  `GuardrailResult`, and `SoftPolicyAdjustment`.
- Enforced the Phase 1 runtime boundary in the model layer:
  `write_scope=shadow_only` and `non_executable=true` are required for every
  ticket and root artifact.
- Extended `scripts/artifact_boundary.py` so `shadow_only` writes can target
  `db/action_tickets/` and optional `db/action_debates/`, while official output
  paths remain forbidden.
- Added `scripts/build_action_ticket_shadow.py` as a standalone CLI:
  `python scripts\build_action_ticket_shadow.py --date YYYY-MM-DD`.
- The builder reads official validated advice and current portfolio state as
  inputs only, then writes only `db/action_tickets/<date>.json`.
- Per user decision, generated one ticket for every current holding fund, not
  only active trades. For `2026-05-22`, this produced 15 tickets:
  2 `scheduled_dca` tickets and 13 `hold` tickets.
- Preserved the first locked golden slice behavior for
  `2026-05-22 + 017641 + scheduled_dca`: the generated ticket is
  `scheduled_dca`, `execution_mode=scheduled`, `ticket_status=shadow_only`,
  `requested_amount=25.0`, and `validated_amount=25.0`.
- Demoted legacy DCA-only/fixed-DCA restrictions out of hard guardrails for new
  action tickets. The legacy `core_dca_only` and `core_dca_fixed_rule` context
  is retained as soft policy notes, not as a hard Phase 1 blocker.
- Added `tests/test_action_tickets.py` covering model round-trip validation,
  non-executable enforcement, all-fund ticket coverage, DCA mapping,
  add/reduce normalization, blocked holds, adjusted sizing, missing-data
  reporting, CLI execution, and forbidden official write rejection.
- Generated local shadow artifact:
  `db/action_tickets/2026-05-22.json` with summary
  `ticket_count=15`, `action_count=2`, `hold_ticket_count=13`,
  `blocked_count=11`, `adjusted_count=0`, `silent_hold_rate=0.0`,
  and `non_executable_violation_count=0`.
- Confirmed official inputs were unchanged after generation:
  - `db/validated_advice/2026-05-22.json` SHA256
    `2C90266F95CD28474A7AF8030B924E4574FF67E44DED8665BE60627D96B831A8`
  - `db/portfolio_state/current.json` SHA256
    `BD5FE613BF72FB7973FBB96038910B111D2EDBAB5D2AD63C48E65E5E61B4A3F0`
- Validation:
  - `python scripts\check_repo_text_hygiene.py`
  - `python -B -X utf8 -m py_compile scripts\action_ticket_models.py scripts\build_action_ticket_shadow.py scripts\artifact_boundary.py tests\test_action_tickets.py`
  - `python -B -X utf8 -m unittest tests.test_action_tickets`
  - `python -B -X utf8 -m unittest tests.test_refactor_golden_slice`
  - `python -B -X utf8 scripts\replay_refactor_slice.py --slice-id 2026-05-22__017641__scheduled_dca`
  - `python -B -X utf8 scripts\diff_refactor_slice.py --slice-id 2026-05-22__017641__scheduled_dca`
  - `$env:PYTHONPATH='F:\okra_assistant\tests'; python -B -X utf8 -m unittest tests.test_validation_and_trade tests.test_pipeline_logic`
- Final golden-slice diff verdict remained PASS.

## 2026-05-27 Phase 2 Layered Retrieval Pack Implemented

- Implemented the standalone Phase 2 layered retrieval-pack shadow foundation
  without wiring it into `scripts/run_daily_pipeline.py`, LangGraph, or the
  Workbench UI.
- Added `scripts/layered_context_models.py` with dataclasses for
  `RetrievalPackArtifact`, `RetrievalPack`, `LayeredContextItem`,
  `MissingDataItem`, `RagTraceRef`, and `Visibility`.
- Enforced Phase 2 artifact boundaries:
  `write_scope=shadow_only`, `non_executable=true`, `include_execution=false`,
  source refs on every layered item, and no-future validation against
  `decision_cutoff`.
- Extended `scripts/artifact_boundary.py` so `shadow_only` writes can target
  `db/retrieval_packs/`.
- Added `scripts/build_layered_retrieval_pack.py` as a standalone CLI:
  `python scripts\build_layered_retrieval_pack.py --date YYYY-MM-DD`.
- The builder reads Phase 1 action tickets, validated advice, portfolio state,
  LLM context, evidence index, and long-memory export as inputs only, then
  writes only `db/retrieval_packs/<date>.json`.
- Canonical facts are built from structured sources only:
  `portfolio_state`, `action_ticket`, `validated_advice`, and structured
  `llm_context` fields. RAG is never used as a canonical fact source.
- RAG is optional and limited to non-canonical evidence. By default it is
  disabled for deterministic Phase 2 builds and recorded as an explicit
  fallback trace ref. If enabled and retrieval fails, the pack records missing
  non-canonical evidence instead of raising into the official chain.
- Execution-only, archived, and rejected memory are excluded by default.
- Generated local shadow artifact:
  `db/retrieval_packs/2026-05-22.json` with summary
  `pack_count=15`, `canonical_fact_count=103`, `derived_signal_count=43`,
  `long_text_evidence_count=65`, `trace_item_count=546`,
  `trace_completeness_rate=1.0`, `no_future_violation_count=0`,
  `execution_included_count=0`, and `canonical_from_rag_count=0`.
- Confirmed official inputs were unchanged after generation:
  - `db/validated_advice/2026-05-22.json` SHA256
    `2C90266F95CD28474A7AF8030B924E4574FF67E44DED8665BE60627D96B831A8`
  - `db/portfolio_state/current.json` SHA256
    `BD5FE613BF72FB7973FBB96038910B111D2EDBAB5D2AD63C48E65E5E61B4A3F0`
- Added `tests/test_layered_retrieval_pack.py` covering round-trip stability,
  no-future validation, fund-specific canonical facts, structured canonical
  source enforcement, memory visibility filtering, RAG failure fallback,
  trace-field requirements, CLI write behavior, and forbidden official write
  rejection.
- Validation:
  - `python scripts\check_repo_text_hygiene.py`
  - `python -B -X utf8 -m py_compile scripts\layered_context_models.py scripts\build_layered_retrieval_pack.py scripts\artifact_boundary.py tests\test_layered_retrieval_pack.py`
  - `python -B -X utf8 -m unittest tests.test_layered_retrieval_pack`
  - `python -B -X utf8 -m unittest tests.test_layered_retrieval_pack tests.test_action_tickets tests.test_refactor_golden_slice`
  - `$env:PYTHONPATH='F:\okra_assistant\tests'; python -B -X utf8 -m unittest tests.test_rag_no_future tests.test_rag_fund_match tests.test_rag_execution_boundary tests.test_rag_memory_visibility`
  - `$env:PYTHONPATH='F:\okra_assistant\tests'; python -B -X utf8 -m unittest tests.test_validation_and_trade tests.test_pipeline_logic`

## 2026-05-27 Phase 3 Action Debate Shadow Graph Implemented

- Implemented the standalone Phase 3 debate-to-action shadow graph without
  wiring it into `scripts/run_daily_pipeline.py`, the Workbench UI, official
  advice generation, portfolio state, execution sync, or long memory.
- Added `scripts/action_debate_prompts.py` with compact prompt/role constants
  and deterministic reference compaction helpers for the graph nodes.
- Added `scripts/action_debate_graph.py` with the required node sequence:
  `load_retrieval_pack -> analyst_evidence_view -> bull_case -> bear_case ->
  debate_referee -> action_former -> hard_guardrail_check ->
  soft_policy_reprice -> ticket_writer`.
- Dependency decision for this phase: no external `langgraph` package was
  introduced because no dependency/version is declared in the repo. The graph
  runs as a local file-backed shadow graph and records this explicitly in the
  runtime metadata. Migration to a LangGraph checkpoint backend remains a later
  dependency decision after rerun/recovery needs are clearer.
- The graph state is intentionally compact: run id, report date, artifact refs,
  source hashes, node status, compact summaries, trace refs, and failure
  metadata. It does not store full retrieval packs, portfolio state, raw news,
  official NAV, execution sync, or secrets.
- Added `scripts/run_action_debate_shadow.py` as a standalone CLI:
  `python scripts\run_action_debate_shadow.py --date YYYY-MM-DD`.
- The writer node writes only `db/action_debates/<date>.json` plus
  `db/action_debates/runtime/<date>.json`. It does not rewrite
  `db/action_tickets/<date>.json`; ticket changes are recorded only as
  non-executable `proposed_ticket_patch` entries inside the debate artifact.
- Failure behavior is visible and non-destructive: an injected node failure
  writes a degraded debate artifact and preserves official inputs.
- Generated local shadow artifact:
  `db/action_debates/2026-05-22.json` with summary `debate_count=15`,
  `degraded_count=0`, `node_failure_count=0`, `state_size_bytes=5960`,
  `official_output_unchanged=true`, and `writes_ticket_file=false`.
- Confirmed official inputs were unchanged after generation:
  - `db/validated_advice/2026-05-22.json` SHA256
    `2C90266F95CD28474A7AF8030B924E4574FF67E44DED8665BE60627D96B831A8`
  - `db/portfolio_state/current.json` SHA256
    `BD5FE613BF72FB7973FBB96038910B111D2EDBAB5D2AD63C48E65E5E61B4A3F0`
- Added `tests/test_action_debate_graph.py` covering graph execution from
  retrieval packs, node output capture, failure degradation, rerun idempotency,
  compact state boundary, forbidden official write rejection, missing input
  behavior, and CLI execution.
- Validation:
  - `python -B -X utf8 -m py_compile scripts\action_debate_graph.py scripts\action_debate_prompts.py scripts\run_action_debate_shadow.py tests\test_action_debate_graph.py`
  - `python -B -X utf8 -m unittest tests.test_action_debate_graph`
  - `python -B -X utf8 scripts\run_action_debate_shadow.py --date 2026-05-22 --generated-at 2026-05-22T21:40:00+08:00`
  - `python scripts\check_repo_text_hygiene.py`
  - `python -B -X utf8 -m unittest tests.test_action_debate_graph tests.test_layered_retrieval_pack tests.test_action_tickets tests.test_refactor_golden_slice`
  - `$env:PYTHONPATH='F:\okra_assistant\tests'; python -B -X utf8 -m unittest tests.test_multiagent_and_review tests.test_validation_and_trade`
  - `$env:PYTHONPATH='F:\okra_assistant\tests'; python -B -X utf8 -m unittest tests.test_rag_no_future tests.test_rag_fund_match tests.test_rag_execution_boundary tests.test_rag_memory_visibility`

## 2026-05-27 Phase 2/3 Review Fixes Applied

- Applied the code-review findings before moving to UI, long-memory, or Phase 4
  work.
- Fixed historical replay portfolio sourcing in Phase 1 and Phase 2 builders:
  `db/portfolio_state/snapshots/<report_date>.json` is preferred when present;
  `db/portfolio_state/current.json` is used only when its `as_of_date` matches
  the report date. This prevents older report dates from silently reading a
  future current portfolio state.
- Updated action-ticket and retrieval-pack source refs so historical
  `2026-05-22` shadow artifacts now cite
  `db/portfolio_state/snapshots/2026-05-22.json`.
- Added Phase 3 input contract checks before graph node execution:
  root artifact schema, report date, `write_scope=shadow_only`,
  `non_executable=true`, child ticket/pack contracts, retrieval-pack
  source-artifact hash for the action-ticket file, and ticket id alignment.
  Contract mismatches now produce degraded shadow artifacts instead of `ok`.
- Changed the refactor artifact boundary walker to recursively scan all nested
  dictionaries and lists, so `debates[*]` and nested proposed ticket patches
  are covered by `non_executable=true` enforcement.
- Fixed graph failure metadata so natural node failures record the current node
  name instead of the generic `graph` label.
- Removed EOF blank-line issues previously reported by `git diff --check`.
- Regenerated local ignored shadow artifacts for `2026-05-22`:
  action tickets, retrieval packs, and action debates. Debate summary remained
  `debate_count=15`, `degraded_count=0`, `node_failure_count=0`,
  `state_size_bytes=5960`, and `writes_ticket_file=false`.
- Confirmed official inputs were unchanged after regeneration:
  - `db/validated_advice/2026-05-22.json` SHA256
    `2C90266F95CD28474A7AF8030B924E4574FF67E44DED8665BE60627D96B831A8`
  - `db/portfolio_state/current.json` SHA256
    `BD5FE613BF72FB7973FBB96038910B111D2EDBAB5D2AD63C48E65E5E61B4A3F0`
- Added focused tests for:
  - historical replay using snapshot instead of future `current.json`;
  - debate graph input hash mismatch degradation;
  - natural node failure using the concrete node name;
  - nested debate/proposed-patch `non_executable=false` boundary rejection.
- Validation:
  - `python -B -X utf8 -m py_compile scripts\artifact_boundary.py scripts\build_action_ticket_shadow.py scripts\build_layered_retrieval_pack.py scripts\action_debate_graph.py scripts\action_debate_prompts.py scripts\run_action_debate_shadow.py tests\test_action_tickets.py tests\test_layered_retrieval_pack.py tests\test_action_debate_graph.py tests\test_refactor_golden_slice.py`
  - `python scripts\check_repo_text_hygiene.py`
  - `python -B -X utf8 -m unittest tests.test_action_tickets tests.test_layered_retrieval_pack tests.test_action_debate_graph tests.test_refactor_golden_slice`
  - `$env:PYTHONPATH='F:\okra_assistant\tests'; python -B -X utf8 -m unittest tests.test_multiagent_and_review tests.test_validation_and_trade`
  - `$env:PYTHONPATH='F:\okra_assistant\tests'; python -B -X utf8 -m unittest tests.test_rag_no_future tests.test_rag_fund_match tests.test_rag_execution_boundary tests.test_rag_memory_visibility`
  - `python -B -X utf8 -m unittest tests.test_refactor_golden_slice tests.test_layered_retrieval_pack tests.test_action_debate_graph`
  - `python -B -X utf8 scripts\build_action_ticket_shadow.py --date 2026-05-22 --generated-at 2026-05-22T21:30:00+08:00`
  - `python -B -X utf8 scripts\build_layered_retrieval_pack.py --date 2026-05-22 --generated-at 2026-05-22T21:35:00+08:00`
  - `python -B -X utf8 scripts\run_action_debate_shadow.py --date 2026-05-22 --generated-at 2026-05-22T21:40:00+08:00`
  - `git diff --check`

## 2026-05-28 Missing Portfolio Snapshot Boundary Fix

- Closed the remaining review gap where a historical shadow replay could select
  `db/portfolio_state/snapshots/<report_date>.json`, fail to find it, and then
  silently continue with an empty `{}` portfolio state.
- Added `MissingPortfolioStateError` and a strict
  `load_portfolio_state_for_report()` helper in
  `scripts/build_action_ticket_shadow.py`.
- Phase 1 action-ticket and Phase 2 retrieval-pack builders now:
  - prefer `db/portfolio_state/snapshots/<report_date>.json` when it exists;
  - allow `db/portfolio_state/current.json` only when `current.as_of_date`
    equals `report_date`;
  - fail with a clear message when the date snapshot is missing and current is
    from another date.
- Added focused regression tests for the missing-snapshot/future-current case
  in both `tests/test_action_tickets.py` and
  `tests/test_layered_retrieval_pack.py`.
- Validation:
  - `python -B -X utf8 -m py_compile scripts\build_action_ticket_shadow.py scripts\build_layered_retrieval_pack.py tests\test_action_tickets.py tests\test_layered_retrieval_pack.py`
  - `python -B -X utf8 -m unittest tests.test_action_tickets`
  - `python -B -X utf8 -m unittest tests.test_layered_retrieval_pack`
  - `git diff --check`

## 2026-05-28 Early CLI/Markdown Shadow Review

- Added `scripts/render_refactor_review.py` as the pre-UI review layer required
  by `11_review_refinement_and_vertical_slice.md` and Phase 7 checklist.
- The renderer reads only:
  - `db/validated_advice/<report_date>.json`
  - `db/action_tickets/<report_date>.json`
  - `db/retrieval_packs/<report_date>.json`
  - `db/action_debates/<report_date>.json`
- It writes only `db/refactor_reviews/<report_date>.md` after passing the
  `shadow_only` and `non_executable=true` artifact boundary check.
- The Markdown report includes:
  - official validated advice summary;
  - shadow action-ticket summary;
  - retrieval trace completeness;
  - action debate status;
  - per-fund review tickets;
  - guardrail map;
  - diff versus official validated actions;
  - boundary check result;
  - open questions.
- Missing shadow artifacts render as `partial`/`not_run` empty states, and
  invalid JSON renders as `failed` without surfacing a stack trace.
- Extended shadow allowed write roots to include `db/refactor_reviews/`, and
  added the new shadow directories to `common.REQUIRED_DIRS` and test
  `TempAgentHome` layout.
- Generated local ignored Markdown review:
  `db/refactor_reviews/2026-05-22.md` with `status=ready`,
  `compared_fund_count=15`, `matched_action_count=15`, and
  `mismatched_action_count=0`.
- Confirmed official inputs were unchanged after generation:
  - `db/validated_advice/2026-05-22.json` SHA256
    `2C90266F95CD28474A7AF8030B924E4574FF67E44DED8665BE60627D96B831A8`
  - `db/portfolio_state/current.json` SHA256
    `BD5FE613BF72FB7973FBB96038910B111D2EDBAB5D2AD63C48E65E5E61B4A3F0`
- Validation:
  - `python -B -X utf8 -m py_compile scripts\artifact_boundary.py scripts\common.py scripts\render_refactor_review.py tests\helpers.py tests\test_refactor_review_markdown.py`
  - `python -B -X utf8 -m unittest tests.test_refactor_review_markdown`
  - `python -B -X utf8 -m unittest tests.test_action_tickets tests.test_layered_retrieval_pack tests.test_action_debate_graph`
  - `python -B -X utf8 scripts\build_action_ticket_shadow.py --date 2026-05-22 --generated-at 2026-05-22T21:30:00+08:00`
  - `python -B -X utf8 scripts\build_layered_retrieval_pack.py --date 2026-05-22 --generated-at 2026-05-22T21:35:00+08:00`
  - `python -B -X utf8 scripts\run_action_debate_shadow.py --date 2026-05-22 --generated-at 2026-05-22T21:40:00+08:00`
  - `python -B -X utf8 scripts\render_refactor_review.py --date 2026-05-22 --generated-at 2026-05-22T21:45:00+08:00`

## 2026-05-28 Phase 4 Outcome Event Shadow Evaluation

- Added `scripts/outcome_event_models.py` with strict dataclass validation for
  `outcome_event.v1` learning-only, non-executable artifacts.
- Added `scripts/evaluate_action_ticket_outcomes.py` as the standalone Phase 4
  evaluator:
  - reads `db/action_tickets/<base_date>.json`;
  - reads `db/portfolio_state/snapshots/<base_date>.json` through the strict
    dated portfolio-state helper;
  - reads official NAV from `raw/quotes/<base_date>.json` and
    `raw/quotes/<evaluation_date>.json`;
  - optionally reads `db/benchmark_history/<benchmark>.json`;
  - writes only `db/outcome_events/<base_date>__<horizon>.json`.
- Outcome artifacts use `write_scope=learning_only` and `non_executable=true`.
  They do not mutate official NAV, revaluation output, portfolio state,
  execution sync, long-memory records, adaptive policies, or skills.
- Implemented explicit states:
  - `scored` when official NAV start/end are available and reliability checks
    pass;
  - `pending` when required evaluation-date quote data is missing;
  - `blocked` when scoring would be unreliable due to stale/fallback quotes,
    cashflow between NAV dates, or untrusted units for unit-sensitive actions;
  - `not_applicable` for unsupported action verbs.
- Added focused tests in `tests/test_action_outcomes.py` for scored add/reduce
  and hold outcomes, benchmark excess return, pending missing NAV, blocked
  cashflow, blocked untrusted units, idempotent rerun, ticket-id linkage,
  artifact round-trip, boundary rejection, CLI execution, and no mutation of
  official inputs.
- Extended the CLI/Markdown review renderer so available outcome events are
  shown in:
  - the scope chain;
  - an `Outcome Event Status` table for `T+1` and `T+5`;
  - each fund review ticket row;
  - open questions when pending or blocked outcomes exist.
- Generated local ignored outcome artifacts for `2026-05-22`:
  - `db/outcome_events/2026-05-22__T+1.json` with `event_count=15`,
    `scored_count=15`, `pending_count=0`, `blocked_count=0`;
  - `db/outcome_events/2026-05-22__T+5.json` with `event_count=15`,
    `scored_count=0`, `pending_count=15`, `blocked_count=0`.
- Regenerated local ignored Markdown review:
  `db/refactor_reviews/2026-05-22.md`, now showing outcome status.
- Confirmed official inputs were unchanged after generation:
  - `db/validated_advice/2026-05-22.json` SHA256
    `2C90266F95CD28474A7AF8030B924E4574FF67E44DED8665BE60627D96B831A8`
  - `db/portfolio_state/current.json` SHA256
    `BD5FE613BF72FB7973FBB96038910B111D2EDBAB5D2AD63C48E65E5E61B4A3F0`
- Validation:
  - `python -B -X utf8 -m py_compile scripts\outcome_event_models.py scripts\evaluate_action_ticket_outcomes.py scripts\render_refactor_review.py tests\test_action_outcomes.py tests\test_refactor_review_markdown.py`
  - `python -B -X utf8 -m unittest tests.test_action_outcomes tests.test_refactor_review_markdown`
  - `python -B -X utf8 -m unittest tests.test_action_tickets tests.test_layered_retrieval_pack tests.test_action_debate_graph tests.test_refactor_golden_slice`
  - `$env:PYTHONPATH='F:\okra_assistant\tests'; python -B -X utf8 -m unittest tests.test_revaluation_and_realtime tests.test_execution_sync`
  - `python -B -X utf8 scripts\evaluate_action_ticket_outcomes.py --date 2026-05-22 --horizon T+1 --generated-at 2026-05-23T23:30:00+08:00`
  - `python -B -X utf8 scripts\evaluate_action_ticket_outcomes.py --date 2026-05-22 --horizon T+5 --generated-at 2026-05-27T23:30:00+08:00`
  - `python -B -X utf8 scripts\render_refactor_review.py --date 2026-05-22 --generated-at 2026-05-22T21:50:00+08:00`
