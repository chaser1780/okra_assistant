# Execution Log

This file will record implementation steps, commits, validation commands, and
important observations during the refactor.

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
  - `python -B -X utf8 -m unittest tests.test_validation_and_trade tests.test_pipeline_logic`
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
  - `python -B -X utf8 -m unittest tests.test_rag_no_future tests.test_rag_fund_match tests.test_rag_execution_boundary tests.test_rag_memory_visibility`
  - `python -B -X utf8 -m unittest tests.test_validation_and_trade tests.test_pipeline_logic`

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
  - `python -B -X utf8 -m unittest tests.test_multiagent_and_review tests.test_validation_and_trade`
  - `python -B -X utf8 -m unittest tests.test_rag_no_future tests.test_rag_fund_match tests.test_rag_execution_boundary tests.test_rag_memory_visibility`

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
  - `python -B -X utf8 -m unittest tests.test_multiagent_and_review tests.test_validation_and_trade`
  - `python -B -X utf8 -m unittest tests.test_rag_no_future tests.test_rag_fund_match tests.test_rag_execution_boundary tests.test_rag_memory_visibility`
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
  - `python -B -X utf8 -m unittest tests.test_revaluation_and_realtime tests.test_execution_sync`
  - `python -B -X utf8 scripts\evaluate_action_ticket_outcomes.py --date 2026-05-22 --horizon T+1 --generated-at 2026-05-23T23:30:00+08:00`
  - `python -B -X utf8 scripts\evaluate_action_ticket_outcomes.py --date 2026-05-22 --horizon T+5 --generated-at 2026-05-27T23:30:00+08:00`
  - `python -B -X utf8 scripts\render_refactor_review.py --date 2026-05-22 --generated-at 2026-05-22T21:50:00+08:00`

## 2026-05-28 Phase 5 Adaptive Policy Memory

- Added `scripts/adaptive_policy_models.py` with strict validation for:
  - `adaptive_policy_event.v1` records;
  - materialized `adaptive_policy.v1` current policy records;
  - `adaptive_policy_store.v1` policy-store artifacts.
- Added `scripts/update_adaptive_policies.py` as the standalone Phase 5 updater:
  - reads `db/outcome_events/<base_date>__<horizon>.json`;
  - reads matching `db/action_tickets/<base_date>.json` for ticket scope;
  - writes derived policy events to `db/strategy_memory/policy_events.jsonl`;
  - materializes `db/strategy_memory/policies.json` from the full event log.
- Policy memory remains learning-only and non-executable:
  - allowed effects are `confidence_delta`, `size_multiplier`,
    `wait_trigger`, and `note`;
  - forbidden effects are `block`, `force_trade`, and
    `change_hard_constraint`;
  - `policies.json` sets `hard_block_allowed=false`;
  - active promotion requires five supportive outcomes or explicit
    `user_approve` event.
- Implemented lifecycle/cap behavior:
  - one supportive outcome remains `draft`;
  - repeated support promotes to `candidate`;
  - enough support or explicit user approval promotes to `active`;
  - contradictions weaken a policy and can archive it when the contradiction
    ratio exceeds the configured threshold;
  - per-scope caps downgrade/archive excess policies without deleting event
    history.
- Extended artifact boundary and project/test layouts so
  `db/strategy_memory/` is allowed only under `learning_only` writes.
- Extended the CLI/Markdown review renderer with an `Adaptive Policy Status`
  section so the shadow review can display the policy-store summary after
  outcome evaluation.
- Added `tests/test_adaptive_policies.py` for:
  - supportive outcome promotion;
  - active promotion threshold and user approval;
  - contradiction weakening/archive behavior;
  - pending/neutral outcome no-op behavior;
  - per-scope policy caps;
  - replay idempotence;
  - hard-block effect rejection;
  - malformed JSONL isolation;
  - round-trip/boundary checks;
  - CLI execution.
- Generated local ignored policy artifacts for `2026-05-22` from T+1/T+5
  outcomes:
  - `db/strategy_memory/policy_events.jsonl` with 14 valid events;
  - `db/strategy_memory/policies.json` with 4 materialized policies:
    `draft=1`, `candidate=1`, `weakened=1`, `archived=1`.
- Regenerated local ignored Markdown review:
  `db/refactor_reviews/2026-05-22.md`, now showing adaptive policy status.
- Confirmed official inputs were unchanged after generation:
  - `db/validated_advice/2026-05-22.json` SHA256
    `2C90266F95CD28474A7AF8030B924E4574FF67E44DED8665BE60627D96B831A8`
  - `db/portfolio_state/current.json` SHA256
    `BD5FE613BF72FB7973FBB96038910B111D2EDBAB5D2AD63C48E65E5E61B4A3F0`
- Validation:
  - `python -B -X utf8 -m py_compile scripts\adaptive_policy_models.py scripts\update_adaptive_policies.py scripts\render_refactor_review.py tests\test_adaptive_policies.py tests\test_refactor_review_markdown.py`
  - `python -B -X utf8 -m unittest tests.test_adaptive_policies tests.test_refactor_review_markdown`
  - `python -B -X utf8 -m unittest tests.test_action_outcomes tests.test_action_tickets tests.test_layered_retrieval_pack tests.test_action_debate_graph tests.test_refactor_golden_slice`
  - `python -B -X utf8 -m unittest tests.test_long_memory tests.test_action_outcomes`
  - `python -B -X utf8 -m unittest tests.test_multiagent_and_review tests.test_validation_and_trade tests.test_revaluation_and_realtime tests.test_execution_sync`
  - `python -B -X utf8 scripts\update_adaptive_policies.py --date 2026-05-22 --horizon T+1 --horizon T+5 --generated-at 2026-05-28T00:20:00+08:00`
  - `python -B -X utf8 scripts\render_refactor_review.py --date 2026-05-22 --generated-at 2026-05-28T00:25:00+08:00`
  - `python scripts\check_repo_text_hygiene.py`
  - `git diff --check`

## 2026-05-28 Phase 6 Strategy Skill Curator

- Added `scripts/strategy_skill_models.py` with strict validation for:
  - `strategy_skill.v1` Markdown frontmatter and required sections;
  - `strategy_skill_event.v1` append-only lifecycle events;
  - `strategy_skill_registry.v1` registry entries and summaries;
  - allowed skill outputs versus forbidden `hard_block`, `force_trade`,
    direct mutation, and execution commands.
- Added `scripts/strategy_skill_store.py` for:
  - deterministic strategy-skill paths under `db/strategy_skills/<skill_id>/`;
  - registry/Markdown consistency checks;
  - append-only skill event logs;
  - default skill-pack construction that excludes archived skills and caps
    active skills by scope;
  - in-memory action-ticket skill ref/output recording helper without writing
    ticket files.
- Added `scripts/run_skill_curator.py` as the standalone Phase 6 curator:
  - reads `db/strategy_memory/policies.json`;
  - skips archived policies and unsupported/no-support clusters;
  - writes draft/candidate strategy skills by default;
  - keeps automatic active promotion disabled.
- Extended artifact boundary and project/test layouts so
  `db/strategy_skills/` is allowed only under `learning_only` writes.
- Extended the CLI/Markdown review renderer with a `Strategy Skill Status`
  section so the shadow review can display registry status, active count, and
  auto-active promotion count.
- Added `tests/test_strategy_skills.py` for:
  - skill Markdown frontmatter validation;
  - registry-to-skill-file matching;
  - draft/candidate creation from a policy-cluster fixture;
  - active promotion staying disabled with auto-active count zero;
  - archived skill exclusion from the default skill pack;
  - hard-block/force-trade output rejection;
  - action-ticket skill refs/outputs recorded in memory only;
  - append-only idempotent event logs;
  - registry round-trip/boundary checks;
  - CLI execution.
- Generated local ignored strategy skill artifacts for `2026-05-22`:
  - `db/strategy_skills/registry.json` with 2 skills:
    `draft=1`, `candidate=1`, `active=0`;
  - `db/strategy_skills/portfolio_cash_defense_repeat_hold_review_v1/skill.md`;
  - `db/strategy_skills/portfolio_cash_defense_repeat_hold_review_v1/events.jsonl`;
  - `db/strategy_skills/portfolio_core_long_term_repeat_scheduled_dca_review_v1/skill.md`;
  - `db/strategy_skills/portfolio_core_long_term_repeat_scheduled_dca_review_v1/events.jsonl`.
- Regenerated local ignored Markdown review:
  `db/refactor_reviews/2026-05-22.md`, now showing strategy skill status.
- Confirmed official inputs were unchanged after generation:
  - `db/validated_advice/2026-05-22.json` SHA256
    `2C90266F95CD28474A7AF8030B924E4574FF67E44DED8665BE60627D96B831A8`
  - `db/portfolio_state/current.json` SHA256
    `BD5FE613BF72FB7973FBB96038910B111D2EDBAB5D2AD63C48E65E5E61B4A3F0`
- Validation:
  - `python -B -X utf8 -m py_compile scripts\strategy_skill_models.py scripts\strategy_skill_store.py scripts\run_skill_curator.py scripts\render_refactor_review.py tests\test_strategy_skills.py tests\test_refactor_review_markdown.py`
  - `python -B -X utf8 -m unittest tests.test_strategy_skills tests.test_refactor_review_markdown`
  - `python -B -X utf8 -m unittest tests.test_adaptive_policies tests.test_action_tickets`
  - `python -B -X utf8 -m unittest tests.test_action_outcomes tests.test_layered_retrieval_pack tests.test_action_debate_graph tests.test_refactor_golden_slice`
  - `python -B -X utf8 -m unittest tests.test_multiagent_and_review tests.test_validation_and_trade tests.test_revaluation_and_realtime tests.test_execution_sync`
  - `python -B -X utf8 scripts\run_skill_curator.py --generated-at 2026-05-28T00:40:00+08:00`
  - `python -B -X utf8 scripts\render_refactor_review.py --date 2026-05-22 --generated-at 2026-05-28T00:45:00+08:00`
  - `python scripts\check_repo_text_hygiene.py`
  - `git diff --check`

## 2026-05-28 Phase 7 Workbench Review Surface

- Added `app/shadow_review_service.py` as a read-only DTO normalizer for:
  - `db/validated_advice/<date>.json`;
  - `db/action_tickets/<date>.json`;
  - `db/retrieval_packs/<date>.json`;
  - `db/action_debates/<date>.json`;
  - optional outcome events, adaptive policies, strategy skill registry, and
    Markdown review status.
- Extended `app/api_contracts.py` with additive Pydantic DTOs for
  `ShadowReviewPageDto`, item rows, artifact status, and missing-artifact
  notes. DTOs remain `extra="allow"` through the existing `ContractModel`.
- Added `GET /api/shadow-review?date=YYYY-MM-DD` and the compatibility alias
  `/api/workbench/shadow-review` through the current API envelope:
  - invalid dates return `400 bad_request`;
  - missing shadow artifacts return `200 ok` with
    `status=missing/not_run/partial/failed`;
  - invalid JSON is reported in `artifacts.missing[]` without stack traces.
- Added a dedicated read-only Workbench page at `/shadow-review`:
  - frontend Zod schema and TypeScript payload types;
  - workbench query helper without snapshot fallback;
  - sidebar route entry and `ShadowReviewPage` display surface;
  - summary metrics, artifact states, missing/degraded notes, and official
    versus shadow ticket comparison cards.
- Kept Phase 7 mutation boundary intact:
  - no execution sync endpoints are called;
  - no portfolio or official advice mutation;
  - no long-memory approve/reject/archive/demote action;
  - no policy or strategy skill promotion;
  - no review items synthesized from `/api/snapshot`.
- Added `tests/test_web_api_action_tickets.py` covering:
  - missing artifacts as a 200 empty state;
  - invalid date as a 400 envelope;
  - legacy-only `not_run`;
  - partial shadow ticket display without retrieval/debate traces;
  - invalid JSON as failed/degraded DTO state without tracebacks;
  - ready payload non-executable/display-only markers;
  - `/api/workbench/shadow-review` alias and meta fields;
  - mutation-path methods not being called.
- Checked the real local `2026-05-22` DTO:
  - `status=ready`;
  - `items=15`;
  - `legacyCount=15`, `shadowCount=15`, `comparableCount=15`;
  - `changedCount=0`, `agreementRate=1.0`, `highRiskDiffCount=0`;
  - `nonExecutable=true`, `displayOnly=true`, `executionDisabled=true`;
  - `missing_count=0`.
- Confirmed official inputs were unchanged after the read-only check:
  - `db/validated_advice/2026-05-22.json` SHA256
    `2C90266F95CD28474A7AF8030B924E4574FF67E44DED8665BE60627D96B831A8`
  - `db/portfolio_state/current.json` SHA256
    `BD5FE613BF72FB7973FBB96038910B111D2EDBAB5D2AD63C48E65E5E61B4A3F0`
- Validation:
  - `python -B -X utf8 -m py_compile app\api_contracts.py app\shadow_review_service.py app\web_api.py tests\test_web_api_action_tickets.py`
  - `python -B -X utf8 -m unittest tests.test_web_api_action_tickets`
  - `python -B -X utf8 -m unittest tests.test_web_api_action_tickets tests.test_web_api_rag_admin tests.test_web_api_rag_copilot`
  - `python -B -X utf8 -m unittest tests.test_refactor_review_markdown tests.test_strategy_skills`
  - `python -B -X utf8 -m unittest tests.test_multiagent_and_review tests.test_validation_and_trade tests.test_revaluation_and_realtime tests.test_execution_sync`
  - `npm run build`
  - `npm run tauri:check`
  - `python scripts\check_repo_text_hygiene.py`
  - `git diff --check`

## 2026-05-28 Phase 8 Pre-Promotion Consumer Map

- Entered Phase 8 only as a pre-promotion audit. No official-path replacement
  was started because the current instruction did not explicitly approve
  promoting shadow-chain output into the official daily chain.
- Added `docs/refactor_runs/2026-05-agent-memory-refactor/phase8_downstream_consumer_map.md`
  to map downstream consumers before changing any legacy responsibility:
  - `db/validated_advice/<date>.json`;
  - `db/daily_workspace/<date>/*`;
  - `db/decisions`, `db/decision_ledger`, and `db/decision_latest`;
  - official review/report outputs;
  - execution sync and execution status;
  - RAG/Copilot source collectors;
  - Workbench API and frontend DTOs.
- Added `scripts/audit_phase8_readiness.py` as a read-only audit command. It
  prints JSON or Markdown to stdout and does not write `db/validated_advice`,
  `db/decision_ledger`, `db/portfolio_state`, `db/execution_sync`,
  `db/long_memory`, or any shadow artifact.
- The audit records:
  - `official_path_mutation_allowed=false`;
  - `promotion_ready=false` by default;
  - required evidence gates;
  - mutation boundaries that must reject shadow artifacts;
  - the first future replacement candidate:
    `scripts/generate_llm_advice.py::build_final_advice_from_committee_bundle`
    behind a fallback switch.
- Added `tests/test_phase8_readiness.py` covering:
  - consumer-map area coverage;
  - default promotion block;
  - execution and ledger mutation boundaries rejecting shadow inputs;
  - ready shadow artifacts not being enough for promotion;
  - JSON CLI output and Markdown rendering.
- Updated refactor README, accepted-plan index, and task board so the Phase 8
  pre-promotion audit is discoverable.
- Official-path mutation remained untouched:
  - no edits to `scripts/run_daily_pipeline.py`;
  - no edits to `scripts/generate_llm_advice.py`;
  - no edits to `scripts/validate_llm_advice.py`;
  - no edits to `scripts/execution_sync.py`;
  - no edits to portfolio-state, execution-sync, or long-memory mutation
    endpoints.

## 2026-05-28 Phase 8 Official Advice Compatibility Preview

- Added `scripts/build_official_advice_compat_preview.py` as a standalone
  shadow-only compatibility adapter preview:
  - reads `db/action_tickets/<date>.json`;
  - reads `db/retrieval_packs/<date>.json`;
  - reads `db/action_debates/<date>.json`;
  - optionally compares against `db/validated_advice/<date>.json`;
  - validates source hashes so mixed old/new shadow inputs are rejected;
  - writes only to
    `db/refactor_shadow_runs/<date>__official_advice_compat_preview/official_advice_compat_preview.json`.
- The preview produces three review-only compatibility shapes:
  - `committee_decision_bundle_preview`, matching the fields expected by the
    future replacement target
    `scripts/generate_llm_advice.py::build_final_advice_from_committee_bundle`;
  - `final_advice_preview`, matching the `market_view`, `fund_decisions`, and
    `cross_fund_observations` shape consumed before validation;
  - `validated_action_sections_preview`, grouped into `tactical_actions`,
    `dca_actions`, and `hold_actions` for downstream contract review only.
- Extended `scripts/audit_phase8_readiness.py` with an initial adapter-preview
  gate. This was later tightened on 2026-05-30; the old
  `official_compatible_advice=true` summary-only interpretation is obsolete.
- Promotion remains blocked by design:
  - `fallback_switch_active=false`;
  - `promotion_ready=false`;
  - no explicit official-path promotion decision exists;
  - outcome examples and regression baselines are still partial.
- Generated the real local preview for `2026-05-22`:
  - `ticket_count=15`;
  - `committee_decision_count=15`;
  - `final_advice_decision_count=15`;
  - `validated_section_preview_count=15`;
  - `official_compatible_advice=true` under the obsolete summary-only
    interpretation;
  - `committee_bundle_compatible=true`;
  - `llm_advice_compatible=true`;
  - `official_paths_written=[]`.
- The readiness audit for `2026-05-22` now reports:
  - `official_path_mutation_allowed=false`;
  - `promotion_ready=false`;
  - `new_chain_official_compatible_advice=ready` under the obsolete
    summary-only interpretation;
  - remaining blocking gates:
    `outcome_examples`, `regression_baselines`, `fallback_switch`,
    `rollback_path`, `explicit_promotion_decision`.
- Added `tests/test_official_advice_compat_preview.py` covering:
  - official-compatible preview shape;
  - no official artifact mutation;
  - golden `017641` scheduled-DCA mapping into final advice;
  - source-hash mismatch rejection;
  - CLI JSON summary output.
- Extended `tests/test_phase8_readiness.py` to prove the compatibility preview
  satisfies only the adapter gate and does not make promotion ready.
- Updated README, accepted-plan index, task board, and Phase 8 consumer map.
- Official-path mutation remained untouched:
  - no edits to `scripts/run_daily_pipeline.py`;
  - no edits to `scripts/generate_llm_advice.py`;
  - no edits to `scripts/validate_llm_advice.py`;
  - no edits to `scripts/execution_sync.py`;
  - no edits to decision ledger, portfolio state, execution sync, or long
    memory mutation paths.
- Validation:
  - `python -B -X utf8 -m py_compile scripts\build_official_advice_compat_preview.py scripts\audit_phase8_readiness.py scripts\artifact_boundary.py tests\test_official_advice_compat_preview.py tests\test_phase8_readiness.py`
  - `python -B -X utf8 -m unittest tests.test_official_advice_compat_preview tests.test_phase8_readiness`
  - `python -B -X utf8 scripts\build_official_advice_compat_preview.py --date 2026-05-22 --generated-at 2026-05-28T11:00:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --generated-at 2026-05-28T11:05:00+08:00`
  - `python -B -X utf8 -m unittest tests.test_official_advice_compat_preview tests.test_phase8_readiness tests.test_action_tickets tests.test_layered_retrieval_pack tests.test_action_debate_graph tests.test_refactor_review_markdown`
  - `python -B -X utf8 -m unittest tests.test_pipeline_logic tests.test_multiagent_and_review tests.test_validation_and_trade`
  - `python -B -X utf8 -m unittest tests.test_execution_sync tests.test_revaluation_and_realtime tests.test_long_memory`
  - `python -B -X utf8 -m unittest discover -s tests -p "test_rag_*.py"`
  - `npm run build`
  - `npm run tauri:check`
  - `python scripts\check_repo_text_hygiene.py`
  - `git diff --check` (CRLF warnings only; no whitespace errors)

## 2026-05-30 Completion Pass: Remaining Shadow Contracts

- Completed the remaining non-promotional documentation tasks as executable
  shadow/learning artifacts:
  - added `scripts/build_hard_constraint_catalog.py` to parse
    `hard_constraints_inventory.md` into a machine-readable
    `shadow_only` catalog at `db/refactor_shadow_runs/hard_constraint_catalog.json`;
  - added `scripts/build_strategy_skill_pack.py` to materialize
    `db/strategy_skills/skill_pack.json` and optional
    `db/strategy_skills/usage/<date>.json`;
  - added `scripts/build_phase8_fallback_contract.py` to write the Phase 8
    fallback/rollback contract at `db/phase8/fallback_contract.json`.
- Preserved boundaries:
  - hard constraints remain deterministic and official validator-owned;
  - strategy skill usage candidates keep `applied_to_ticket_file=false`;
  - shadow adapters remain design evidence only, not the project production path;
  - official path mutation remains disallowed.
- Updated Phase 8 audit:
  - rollback path becomes `ready` only when the fallback contract documents a
    rollback command;
  - fallback switch remains `partial`, because a designed but inactive switch
    must not unlock promotion.
- Updated `tasks.md`:
  - hard-constraint classification, skill-pack/usage, skill outcome
    promotion/revision design, and fallback/rollback contract are marked done;
  - official fallback enablement, official daily-chain mutation, and legacy
    deletion are explicitly `blocked-by-promotion`.
- Validation:
  - `python -B -X utf8 -m py_compile scripts\build_hard_constraint_catalog.py scripts\build_strategy_skill_pack.py scripts\build_phase8_fallback_contract.py scripts\audit_phase8_readiness.py scripts\strategy_skill_store.py scripts\artifact_boundary.py tests\test_hard_constraint_catalog.py tests\test_strategy_skill_pack.py tests\test_phase8_fallback_contract.py`
  - `python -B -X utf8 -m unittest tests.test_hard_constraint_catalog tests.test_strategy_skill_pack tests.test_phase8_fallback_contract`
  - `python -B -X utf8 scripts\build_hard_constraint_catalog.py --generated-at 2026-05-30T13:30:00+08:00 --format json`
  - `python -B -X utf8 scripts\build_strategy_skill_pack.py --date 2026-05-22 --generated-at 2026-05-30T13:35:00+08:00 --format json`
  - `python -B -X utf8 scripts\build_phase8_fallback_contract.py --generated-at 2026-05-30T13:40:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --generated-at 2026-05-30T13:45:00+08:00`
  - real-date audit result: `rollback_path=ready`, `fallback_switch=partial`,
    `promotion_ready=false`.

## 2026-05-30 Review Fix: Complete Preview Contract And Blocked-Reduce Attribution

- Hardened the Phase 8 official-advice compatibility audit against incomplete
  but hash-valid preview files:
  - `new_chain_official_compatible_advice` now requires all four source
    artifacts to be present and hash-verified:
    `validated_advice`, `action_tickets`, `retrieval_packs`, and
    `action_debates`;
  - preview bodies must contain `committee_decision_bundle_preview`,
    `final_advice_preview`, and `validated_action_sections_preview`;
  - legal JSON with a non-object root, such as `[]`, now returns a damaged
    preview contract instead of crashing the audit.
- Split mixed hold attribution for existing positions:
  - `validated_action=hold` plus an increase-side model action remains
    `blocked_add_with_existing_position`;
  - `validated_action=hold` plus `model_action=reduce/switch_out` is now
    `blocked_reduce_kept_existing_position`;
  - both mixed contexts are neutral and `learning_eligible=false`, so they
    cannot flow into adaptive policies or skill curation.
- Added regression coverage for:
  - non-object Phase 8 preview JSON;
  - a forged preview with only an action-ticket source and all summary booleans
    set true;
  - missing preview body sections;
  - existing-position blocked reduce not being mislabeled as blocked add.
- Validation:
  - `python -B -X utf8 -m py_compile scripts\audit_phase8_readiness.py scripts\evaluate_action_ticket_outcomes.py tests\test_phase8_readiness.py tests\test_action_outcomes.py`
  - `python -B -X utf8 -m unittest tests.test_phase8_readiness`
  - `python -B -X utf8 -m unittest tests.test_action_outcomes`
  - `python -B -X utf8 -m unittest tests.test_action_outcomes tests.test_adaptive_policies tests.test_phase8_readiness`
  - `python -B -X utf8 -m unittest tests.test_official_advice_compat_preview tests.test_phase8_readiness tests.test_refactor_review_markdown tests.test_action_tickets tests.test_layered_retrieval_pack tests.test_action_debate_graph`
  - `python -B -X utf8 scripts\build_official_advice_compat_preview.py --date 2026-05-22 --generated-at 2026-05-30T12:10:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --generated-at 2026-05-30T12:15:00+08:00`
  - `python -B -X utf8 scripts\evaluate_action_ticket_outcomes.py --date 2026-05-22 --horizon T+1 --generated-at 2026-05-30T12:20:00+08:00`
  - `python -B -X utf8 scripts\check_repo_text_hygiene.py`

## 2026-05-30 Review Fix: Blocked-Add Hold Attribution And Preview Contract Audit

- Tightened hold outcome attribution again:
  - added `blocked_add_with_existing_position` for the case where a fund
    already has a position but the model wanted to add and the validator or
    committee resolved the action to hold;
  - this mixed exposure/opportunity-cost case is now `learning_eligible=false`
    and receives a neutral diagnostic label, so it cannot support or
    contradict adaptive policies or strategy-skill candidates;
  - pure `hold_existing_position` and pure `blocked_add_or_cash_hold` semantics
    remain separated.
- Clarified outcome artifact date reporting:
  - event-level `evaluation_date` remains the actual quote date used for that
    fund;
  - summary now includes `actual_evaluation_dates`, `event_date_range`, and
    `evaluation_policy=target_date_then_next_available_official_nav_per_fund`;
  - empty `evaluation_date_used` no longer defaults to `evaluation_date` in the
    model layer, so missing-after-target states stay visibly missing.
- Hardened Phase 8 readiness audit:
  - `_compat_preview_status` now revalidates preview `schema_version`,
    `report_date`, `write_scope`, `non_executable`, `display_only`,
    `official_output_unchanged`, and `official_paths_written`;
  - source artifact hashes are recomputed from local files, and missing
    verifiable sources fail the gate;
  - handwritten or damaged preview summaries cannot make
    `new_chain_official_compatible_advice` ready.
- Cleaned the earlier Phase 8 log entry so the obsolete
  `official_compatible_advice=true` summary-only gate is explicitly marked as
  superseded.
- Validation:
  - `python -B -X utf8 -m py_compile scripts\evaluate_action_ticket_outcomes.py scripts\outcome_event_models.py scripts\audit_phase8_readiness.py tests\test_action_outcomes.py tests\test_phase8_readiness.py`
  - `python -B -X utf8 -m unittest tests.test_action_outcomes tests.test_adaptive_policies tests.test_phase8_readiness`
  - `python -B -X utf8 -m unittest tests.test_official_advice_compat_preview tests.test_phase8_readiness tests.test_refactor_review_markdown tests.test_action_tickets tests.test_layered_retrieval_pack tests.test_action_debate_graph`
  - `python -B -X utf8 scripts\build_official_advice_compat_preview.py --date 2026-05-22 --generated-at 2026-05-30T11:00:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --generated-at 2026-05-30T11:05:00+08:00`
  - `python -B -X utf8 scripts\evaluate_action_ticket_outcomes.py --date 2026-05-22 --horizon T+1 --generated-at 2026-05-30T11:10:00+08:00`

## 2026-05-30 Review Fix: Outcome Semantics And Phase 8 Gate Tightening

- Fixed the Phase 4/5 learning boundary for `hold` outcomes:
  - `scripts/evaluate_action_ticket_outcomes.py` now writes
    `decision_context.exposure_context` for scored events;
  - `hold_existing_position` treats NAV down as `hurt` and NAV up as
    `helped`;
  - `blocked_add_or_cash_hold` keeps the cash/opportunity-cost semantics:
    NAV down is `avoided_loss`, NAV up is `missed_opportunity`;
  - unclear hold contexts are marked learning-ineligible.
- `scripts/update_adaptive_policies.py` now ignores scored outcomes whose
  `decision_context.learning_eligible` is not true, preventing ambiguous
  historical artifacts from entering adaptive-policy support/contradiction.
- Tightened T+N outcome date handling:
  - outcome artifacts now record `target_date`, `evaluation_date_used`, and
    `date_match_type`;
  - if the calendar target has no quote file, the evaluator uses the first
    available trading-day quote after the target instead of immediately
    producing fake pending events.
- Tightened Phase 8 compatibility naming and readiness gates:
  - `official_shape_compatible` is separated from
    `official_compatible_advice`;
  - readiness now also requires behavior comparison, validator dry-run,
    source-hash verification, and an active fallback switch;
  - the current preview remains `official_compatible_advice=false` because no
    fallback switch is active and this is still only an adapter-shape preview;
  - the committee-bundle preview preserves the official root
    `decision_mode`/`execution_eligible` instead of inventing
    `shadow_preview` root semantics.
- Official-path mutation remains untouched:
  - no edits to `scripts/run_daily_pipeline.py`;
  - no edits to `scripts/generate_llm_advice.py`;
  - no edits to official `db/validated_advice`, decision ledger, execution
    sync, portfolio state, or long-memory mutation paths.
- Validation:
  - `python -B -X utf8 -m py_compile scripts\outcome_event_models.py scripts\evaluate_action_ticket_outcomes.py scripts\update_adaptive_policies.py scripts\build_official_advice_compat_preview.py scripts\audit_phase8_readiness.py scripts\validate_llm_advice.py tests\test_action_outcomes.py tests\test_adaptive_policies.py tests\test_official_advice_compat_preview.py tests\test_phase8_readiness.py`
  - `python -B -X utf8 -m unittest tests.test_action_outcomes tests.test_adaptive_policies tests.test_official_advice_compat_preview tests.test_phase8_readiness`
  - `python -B -X utf8 -m unittest tests.test_refactor_golden_slice tests.test_refactor_review_markdown tests.test_action_tickets tests.test_layered_retrieval_pack tests.test_action_debate_graph tests.test_web_api_action_tickets tests.test_strategy_skills tests.test_long_memory tests.test_validation_and_trade`
  - `python -B -X utf8 scripts\build_official_advice_compat_preview.py --date 2026-05-22 --generated-at 2026-05-30T10:30:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --generated-at 2026-05-30T10:35:00+08:00`
  - `python -B -X utf8 scripts\evaluate_action_ticket_outcomes.py --date 2026-05-22 --horizon T+1 --generated-at 2026-05-30T10:40:00+08:00`
  - `python scripts\check_repo_text_hygiene.py`
  - `git diff --check` (CRLF warnings only; no whitespace errors)

## 2026-05-31 Completion Pass: Replay, Review Boundary, And Baseline Hardening

- Hardened adaptive policy replay:
  - derived policy event ids now key by source outcome rather than by
    event-type-specific label;
  - derived events include source artifact path/hash and `source_identity`;
  - rerunning from a changed outcome artifact replaces the stale derived event
    from the same source instead of leaving old support and new contradict
    evidence side by side;
  - CLI wording now says `updated ... derived policy events` rather than
    claiming append-only behavior.
- Hardened the strategy skill lifecycle surface:
  - archived policies remain represented in the skill registry for audit;
  - archived skills are excluded from the default skill pack and reported as
    archived ids instead of silently disappearing.
- Hardened Shadow Review API/UI boundaries:
  - `actionTickets`, `retrievalPacks`, and `actionDebates` must be
    `write_scope=shadow_only`;
  - `adaptivePolicies` and `strategySkills` must be
    `write_scope=learning_only`;
  - all nested refactor artifacts must keep `non_executable=true`;
  - boundary violations fail the artifact row and do not synthesize display
    review items;
  - same-fund multi-action dates are matched at action level instead of
    collapsed by fund code.
- Added read-only visibility for learning context on the Shadow Review page:
  soft policy adjustments, skill refs/outputs, and outcome summaries are shown
  per card without execution controls or promotion endpoints.
- Added a named multi-date shadow regression baseline:
  - `scripts/build_shadow_regression_baseline.py`;
  - real baseline path
    `db/refactor_shadow_runs/regression_baselines/phase8_shadow_multidate_2026_05_20_22/`;
  - dates covered: `2026-05-20`, `2026-05-21`, and `2026-05-22`;
  - Phase 8 audit now marks `regression_baselines=ready`.
- Simplified the baseline writer so it no longer writes a temporary
  pass-looking bootstrap baseline before date runs finish.
- Current residual Phase 8 blockers remain intentional:
  - `new_chain_official_compatible_advice`;
  - `outcome_examples`;
  - `fallback_switch`;
  - `explicit_promotion_decision`.
- Official-path mutation remains untouched:
  - no edits to `scripts/run_daily_pipeline.py`;
  - no promotion of shadow advice into `db/validated_advice`;
  - no execution sync, portfolio state, decision ledger, long-memory approval,
    or hard-constraint mutation through shadow artifacts.
- Validation run after this entry:
  - `python -B -X utf8 -m py_compile scripts\update_adaptive_policies.py scripts\run_skill_curator.py scripts\build_shadow_regression_baseline.py scripts\audit_phase8_readiness.py app\shadow_review_service.py app\api_contracts.py`
  - `python -B -X utf8 -m unittest tests.test_refactor_golden_slice tests.test_action_tickets tests.test_layered_retrieval_pack tests.test_action_debate_graph tests.test_action_outcomes tests.test_adaptive_policies tests.test_strategy_skills tests.test_strategy_skill_pack tests.test_refactor_review_markdown tests.test_web_api_action_tickets tests.test_shadow_regression_baseline tests.test_phase8_readiness tests.test_official_advice_compat_preview tests.test_phase8_fallback_contract`
  - `python -B -X utf8 scripts\update_adaptive_policies.py --date 2026-05-22 --horizon T+1 --horizon T+5 --generated-at 2026-05-31T00:20:00+08:00`
  - `python -B -X utf8 scripts\run_skill_curator.py --generated-at 2026-05-31T00:21:00+08:00`
  - `python -B -X utf8 scripts\build_strategy_skill_pack.py --date 2026-05-22 --generated-at 2026-05-31T00:22:00+08:00 --format json`
  - `python -B -X utf8 scripts\render_refactor_review.py --date 2026-05-22 --generated-at 2026-05-31T00:23:00+08:00`
  - `python -B -X utf8 scripts\build_shadow_regression_baseline.py --date 2026-05-20 --date 2026-05-21 --date 2026-05-22 --baseline-name phase8_shadow_multidate_2026_05_20_22 --generated-at 2026-05-31T00:24:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --generated-at 2026-05-31T00:25:00+08:00 --format json`
  - `cd frontend; npm run build`

## 2026-05-31 Completion Pass: Multi-Date Outcome Evidence

- Added `scripts/build_outcome_evidence_baseline.py` as a shadow-only Phase 8
  evidence builder:
  - regenerates learning-only `db/outcome_events/<date>__<horizon>.json`
    artifacts through the existing outcome evaluator;
  - writes a shadow-only coverage baseline under
    `db/refactor_shadow_runs/outcome_evidence_baselines/<baseline_name>/`;
  - checks `write_scope`, `non_executable`, event counts, scored counts,
    horizon coverage, date coverage, and action-type coverage;
  - does not write official advice, portfolio state, execution sync, decision
    ledger, long memory, adaptive policies, or strategy skills.
- Updated `scripts/audit_phase8_readiness.py` so `outcome_examples` is `ready`
  only when a named outcome evidence baseline has passed. Counting a single
  date's outcome files is no longer enough.
- Added `tests/test_outcome_evidence_baseline.py` covering:
  - named outcome evidence baseline creation;
  - JSON/Markdown paths;
  - Phase 8 audit consuming the baseline;
  - promotion remaining blocked even when `outcome_examples=ready`.
- Generated real local outcome evidence for:
  - dates: `2026-05-20`, `2026-05-21`, `2026-05-22`;
  - horizons: `T+1`, `T+5`;
  - 6 outcome artifacts;
  - 90 scored events;
  - action types: `hold`, `scheduled_dca`;
  - labels: `helped`, `hurt`, `neutral`;
  - no pending, blocked, or non-executable violations.
- Phase 8 readiness now reports:
  - `outcome_examples=ready`;
  - `regression_baselines=ready`;
  - `rollback_path=ready`;
  - remaining blockers:
    `new_chain_official_compatible_advice`, `fallback_switch`,
    `explicit_promotion_decision`;
  - `promotion_ready=false`.
- Validation:
  - `python -B -X utf8 -m py_compile scripts\build_outcome_evidence_baseline.py scripts\audit_phase8_readiness.py tests\test_outcome_evidence_baseline.py`
  - `python -B -X utf8 -m unittest tests.test_outcome_evidence_baseline tests.test_phase8_readiness`
  - `python -B -X utf8 scripts\build_outcome_evidence_baseline.py --date 2026-05-20 --date 2026-05-21 --date 2026-05-22 --horizon T+1 --horizon T+5 --baseline-name phase8_outcome_multidate_2026_05_20_22 --generated-at 2026-05-31T00:50:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --generated-at 2026-05-31T00:58:00+08:00 --format json`

## 2026-05-31 Completion Pass: Compatibility Evidence/Fallback Split

- Split Phase 8 compatibility evidence from fallback activation:
  - `official_compatible_advice=true` now means the shadow adapter preview
    passed contract, shape, behavior comparison, validator dry-run, source hash,
    and zero-mismatch checks;
  - `fallback_switch_active=false` remains a separate promotion gate;
  - `promotion_ready=false` remains correct until the fallback switch is
    intentionally activated and the user explicitly approves promotion.
- Updated `scripts/build_official_advice_compat_preview.py` so the preview no
  longer requires an active fallback switch to claim official-compatible advice
  evidence.
- Updated `scripts/audit_phase8_readiness.py` so
  `new_chain_official_compatible_advice` is ready when the dry-run evidence is
  ready, while `fallback_switch` remains partial.
- Rebuilt the real `2026-05-22` compatibility preview:
  - `official_shape_compatible=true`;
  - `official_behavior_comparable=true`;
  - `official_adapter_dry_run_passed=true`;
  - `source_hash_verified=true`;
  - `official_compatible_advice=true`;
  - `fallback_switch_active=false`;
  - `promotion_ready=false`;
  - `official_paths_written=[]`.
- Phase 8 readiness now reports:
  - `new_chain_official_compatible_advice=ready`;
  - `outcome_examples=ready`;
  - `regression_baselines=ready`;
  - remaining blockers: `fallback_switch`, `explicit_promotion_decision`.
- Validation:
  - `python -B -X utf8 -m py_compile scripts\build_official_advice_compat_preview.py scripts\audit_phase8_readiness.py tests\test_official_advice_compat_preview.py tests\test_phase8_readiness.py`
  - `python -B -X utf8 -m unittest tests.test_official_advice_compat_preview tests.test_phase8_readiness`
  - `python -B -X utf8 scripts\build_official_advice_compat_preview.py --date 2026-05-22 --generated-at 2026-05-31T01:15:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --generated-at 2026-05-31T01:16:00+08:00 --format json`

## 2026-05-31 Completion Pass: Default-Off Runtime Adapter Hook

- Added `scripts/shadow_advice_adapter.py` as a temporary promotion-drill module.
- Wired `scripts/generate_llm_advice.py` to call the adapter only during
  explicit promotion drills.
- Added a second approval guard for the temporary drill path.
- The adapter refuses to run unless both drill guards are enabled and Phase 8
  readiness reports all gates ready under explicit promotion.
- Tightened readiness so `fallback_switch=ready` requires:
  - explicit promotion approval;
  - implemented fallback hook;
  - active temporary drill guard;
  - active promotion approval guard.
- With default env, the official path remains legacy and no official output is
  changed by the hook.
- If explicitly promoted in a future step, the adapter path writes official
  final-advice artifacts only through the existing `generate_llm_advice.py`
  output locations, then leaves validation to `validate_llm_advice.py`.
- No current change routes shadow artifacts to execution sync, portfolio state,
  decision ledger, long-memory approval, or hard-constraint mutation.
- Documentation updates:
  - Phase 8 checklist now splits pre-promotion default-off hook edits from
    post-promotion responsibility transfer.
  - Phase 8 downstream map names the runtime adapter module and clarifies that
    the preview builder is evidence-only.
  - Phase 5 checklist clarifies derived outcome replay versus manual lifecycle
    event history.
  - Phase 7 checklist records the `/api/workbench/shadow-review` alias.

## 2026-05-31 Review Fixes From Code Audit

- Strengthened Shadow Review DTO guardrails:
  - `ShadowReviewPageDto.guardrails` now uses literal `true/false` fields
    instead of an unconstrained dict.
  - frontend schema/types match literal non-executable/display-only contracts.
- Fixed partial Shadow Review card semantics:
  - missing retrieval/debate artifacts now produce `retrieval=null` and
    `debate=null`;
  - UI displays `not_run` instead of empty trace counts.
- Extended artifact boundary checks:
  - `outcomeEvents:<horizon>` artifacts must be `learning_only` and
    `non_executable=true` before they are shown in Shadow Review.
- Added regression tests for:
  - fallback env active without promotion env remains blocked;
  - explicit environ passed into the adapter readiness audit;
  - missing retrieval/debate null display contract;
  - invalid outcome event boundary reporting.

## 2026-05-31 Broad Add/Switch Baseline Pass

- Added real `2026-03-13` to Phase 8 evidence because that date contains
  `switch_out` and `add`, not only hold/DCA behavior.
- Generated missing `db/evidence_index/2026-03-13.json` from the existing
  `db/llm_context/2026-03-13.json`.
- Rebuilt broad shadow regression baseline:
  - `db/refactor_shadow_runs/regression_baselines/phase8_shadow_multidate_add_reduce_2026_03_13_and_2026_05_20_22/`;
  - dates: `2026-03-13`, `2026-05-20`, `2026-05-21`, `2026-05-22`;
  - ready dates: 4/4;
  - failed dates: 0;
  - `named_regression_baseline_passed=true`.
- Rebuilt broad outcome evidence baseline:
  - `db/refactor_shadow_runs/outcome_evidence_baselines/phase8_outcome_add_reduce_2026_03_13_and_2026_05_20_22/`;
  - dates: `2026-03-13`, `2026-05-20`, `2026-05-21`, `2026-05-22`;
  - horizons: T+1 and T+5;
  - artifacts: 8;
  - scored events: 117;
  - action types: `add`, `hold`, `scheduled_dca`, `switch_out`;
  - blocked events: 3, due to not-scored outcome cases rather than artifact
    failures;
  - `multi_date_outcome_evidence_passed=true`.
- Rebuilt `db/phase8/fallback_contract.json` so the on-disk artifact now
  matches the implemented default-off adapter hook:
  `fallback_switch_implemented=true`, `fallback_switch_active=false`.
- Current deterministic readiness audit for `2026-05-22`:
  - ready gates: official-compatible advice, Workbench comparison, outcome
    examples, hard constraints, regression baselines, rollback path;
  - blocking gates: `fallback_switch`, `explicit_promotion_decision`;
  - `promotion_ready=false`.

## 2026-05-31 Strict Phase 8 Baseline Correction

- Tightened `scripts/build_shadow_regression_baseline.py` so a date is only
  `ready` when the compatibility preview passes shape, behavior comparison,
  validator dry-run, source-hash, no official writes, and zero mismatches.
- Tightened `scripts/audit_phase8_readiness.py` so the `regression_baselines`
  gate requires a broad baseline covering `add`, `reduce`, `switch_out`,
  `scheduled_dca`, and `hold`; a DCA/hold-only compatible baseline is no
  longer enough for Phase 8 promotion.
- Rebuilt strict regression baselines:
  - `phase8_shadow_official_compatible_2026_05_21_22` passes for DCA/hold
    replay only;
  - `phase8_shadow_coverage_add_reduce_switch_2026_03_13_04_20_05_20_22`
    covers add/reduce/switch_out/DCA/hold but fails promotion readiness
    because 3 of 5 dates fail `official_adapter_dry_run_passed`.
- Rebuilt broad outcome evidence baseline:
  - `phase8_outcome_add_reduce_switch_2026_03_13_04_20_05_20_22`;
  - 5 dates, 2 horizons, 10 artifacts, 143 scored events;
  - action types: `add`, `reduce`, `switch_out`, `scheduled_dca`, `hold`;
  - `multi_date_outcome_evidence_passed=true`.
- Removed probe and misleading old add-reduce baseline directories from
  `db/refactor_shadow_runs/regression_baselines/` and
  `db/refactor_shadow_runs/outcome_evidence_baselines/`.
- Updated default-off runtime adapter scope:
  - `scripts/generate_llm_advice.py` no longer writes
    `db/committee_decision_bundle/<date>.json` in adapter mode;
  - shadow committee bundle remains embedded in `db/llm_raw/<date>.json` for
    `validate_llm_advice.py` compatibility.
- Current deterministic readiness audit for `2026-05-22`:
  - ready gates: official-compatible advice for the selected date, Workbench
    comparison, outcome examples, hard constraints, rollback path;
  - partial/blocking gates: `regression_baselines`, `fallback_switch`,
    `explicit_promotion_decision`;
  - `promotion_ready=false`.

## 2026-05-31 Broad Replay Fix And Runtime Boundary Hardening

- Fixed historical trade-constraint replay:
  - legacy `db/trade_journal` rows without lifecycle status are no longer
    treated as permanently unsettled sell proceeds;
  - actual execution-sync trades with explicit pending/confirmed statuses still
    produce `delayed_sell_proceeds`.
- Added an adapter-only validated-section replay contract:
  - `scripts/build_official_advice_compat_preview.py` now embeds
    `validated_action_sections_replay` in the committee-bundle preview;
  - `scripts/validate_llm_advice.py` only uses that replay shape when
    `llm_raw.mode == "shadow_advice_adapter"`;
  - normal official validation/optimizer behavior remains unchanged.
- Rebuilt the broad Phase 8 regression baseline:
  - baseline:
    `phase8_shadow_coverage_add_reduce_switch_2026_03_13_04_20_05_20_22`;
  - dates: `2026-03-13`, `2026-04-20`, `2026-05-20`,
    `2026-05-21`, `2026-05-22`;
  - ready dates: 5/5;
  - covered actions: `add`, `reduce`, `switch_out`, `scheduled_dca`, `hold`;
  - `named_regression_baseline_passed=true`.
- Hardened official mutation boundaries:
  - execution trade/conversion endpoints reject shadow, learning, display-only,
    and non-executable payload markers;
  - long-memory action rejects shadow/learning payload markers;
  - contract DTOs for trade/conversion now forbid unknown extra fields.
- Aligned fallback behavior with the Phase 8 map:
  - partial temporary drill approval falls back to the legacy path instead of
    stopping the official final-advice writer;
  - fallback contract now names `scripts/shadow_advice_adapter.py` as the
    temporary runtime candidate and `scripts/build_official_advice_compat_preview.py`
    as the evidence preview builder.
- Current deterministic readiness audit for `2026-05-22`:
  - ready gates: official-compatible advice, Workbench comparison, outcome
    examples, hard constraints, regression baselines, rollback path;
  - blocking gates: `fallback_switch`, `explicit_promotion_decision`;
  - `promotion_ready=false`.
- Validation:
  - `python -B -X utf8 -m unittest tests.test_official_advice_compat_preview tests.test_shadow_regression_baseline tests.test_shadow_advice_adapter tests.test_validation_and_trade`
  - `python -B -X utf8 -m unittest tests.test_web_api_long_memory tests.test_web_api_action_tickets tests.test_execution_sync`
  - `python -B -X utf8 -m unittest tests.test_shadow_advice_adapter tests.test_phase8_readiness tests.test_phase8_fallback_contract`
  - `python -B -X utf8 scripts\build_shadow_regression_baseline.py --date 2026-03-13 --date 2026-04-20 --date 2026-05-20 --date 2026-05-21 --date 2026-05-22 --baseline-name phase8_shadow_coverage_add_reduce_switch_2026_03_13_04_20_05_20_22 --required-action-type add --required-action-type reduce --required-action-type switch_out --required-action-type scheduled_dca --required-action-type hold --generated-at 2026-05-31T10:20:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --generated-at 2026-05-31T10:22:00+08:00 --format json`

## 2026-05-31 Phase 8 Audit Evidence Hardening

- Tightened `scripts/audit_phase8_readiness.py` so Phase 8 readiness no longer
  trusts pass-looking baseline summary booleans by themselves.
- Regression baseline audit now requires:
  - schema and boundary markers for `shadow_regression_baseline.v1`;
  - at least 3 dates;
  - summary date counts matching actual date rows;
  - every date row ready;
  - source-hash coverage for validated advice, action tickets, retrieval packs,
    action debates, Markdown review, and official-compat preview;
  - current source hashes matching the baseline record;
  - broad required/observed action coverage for `add`, `reduce`, `switch_out`,
    `scheduled_dca`, and `hold`.
- Outcome evidence audit now requires:
  - schema and boundary markers for `outcome_evidence_baseline.v1`;
  - at least 3 dates, 2 horizons, and 30 scored events;
  - all outcome artifacts ready;
  - current outcome artifact hashes matching the baseline record;
  - broad required/observed action coverage for `add`, `reduce`, `switch_out`,
    `scheduled_dca`, and `hold`.
- Fallback gate now also requires the fallback contract to be valid before it
  can become `ready`.
- Updated tests so:
  - single-date or DCA-only baselines remain valid builder fixtures but do not
    unlock Phase 8 readiness;
  - handwritten pass summaries without source hashes are rejected;
  - shadow-adapter promotion tests use byte-identical copies of the real broad
    evidence instead of synthetic pass summaries.
- Current deterministic readiness audit for `2026-05-22`:
  - ready gates: official-compatible advice, Workbench comparison, outcome
    examples, hard constraints, regression baselines, rollback path;
  - blocking gates: `fallback_switch`, `explicit_promotion_decision`;
  - `promotion_ready=false`.
- Validation:
  - `python -B -X utf8 -m unittest tests.test_phase8_readiness tests.test_outcome_evidence_baseline tests.test_shadow_regression_baseline tests.test_phase8_fallback_contract tests.test_shadow_advice_adapter`
  - `python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --generated-at 2026-05-31T12:00:00+08:00 --format json`

## 2026-05-31 Mutation Boundary Completion

- Completed runtime mutation-boundary protection for all Phase 8 listed
  execution endpoints:
  - `/api/execution-sync/trade`;
  - `/api/execution-sync/conversion`;
  - `/api/execution-sync/reconcile/apply`;
  - `/api/execution-sync/confirmation/update`;
  - `/api/long-memory/action`.
- `execution_reconcile_apply` now rejects shadow/display-only/non-executable
  markers both at the top-level payload and inside the embedded `preview`.
- `execution_confirmation_update` now rejects shadow/display-only/non-executable
  markers before updating pending confirmations.
- Narrowed mutation marker detection so ordinary manual-import metadata such as
  `source_path` alone does not block a valid manual execution payload; explicit
  shadow/learning/review markers remain rejected.
- Tightened `scripts/build_outcome_evidence_baseline.py` so scored, pending,
  and blocked counts are recomputed from `events` instead of trusting artifact
  summary values.
- Rebuilt broad Phase 8 evidence after the outcome baseline tightening:
  - regression baseline:
    `phase8_shadow_coverage_add_reduce_switch_2026_03_13_04_20_05_20_22`;
  - outcome evidence baseline:
    `phase8_outcome_add_reduce_switch_2026_03_13_04_20_05_20_22`;
  - both remain passing under the stricter audit.
- Current deterministic readiness audit for `2026-05-22`:
  - ready gates: official-compatible advice, Workbench comparison, outcome
    examples, hard constraints, regression baselines, rollback path;
  - blocking gates: `fallback_switch`, `explicit_promotion_decision`;
  - `promotion_ready=false`.
- Validation:
  - `python -B -X utf8 -m unittest tests.test_web_api_long_memory tests.test_web_api_action_tickets tests.test_outcome_evidence_baseline tests.test_phase8_readiness tests.test_shadow_advice_adapter`
  - `python -B -X utf8 scripts\build_outcome_evidence_baseline.py --date 2026-03-13 --date 2026-04-20 --date 2026-05-20 --date 2026-05-21 --date 2026-05-22 --horizon T+1 --horizon T+5 --baseline-name phase8_outcome_add_reduce_switch_2026_03_13_04_20_05_20_22 --required-action-type add --required-action-type reduce --required-action-type switch_out --required-action-type scheduled_dca --required-action-type hold --generated-at 2026-05-31T12:20:00+08:00 --format json`
  - `python -B -X utf8 scripts\build_shadow_regression_baseline.py --date 2026-03-13 --date 2026-04-20 --date 2026-05-20 --date 2026-05-21 --date 2026-05-22 --baseline-name phase8_shadow_coverage_add_reduce_switch_2026_03_13_04_20_05_20_22 --required-action-type add --required-action-type reduce --required-action-type switch_out --required-action-type scheduled_dca --required-action-type hold --generated-at 2026-05-31T12:20:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --generated-at 2026-05-31T12:25:00+08:00 --format json`

## 2026-05-31 Phase 8 Promotion Review Package

- Added `scripts/build_phase8_promotion_review.py`.
- The builder creates a non-executable, display-only promotion review under:
  - `db/phase8/promotion_reviews/<date>.json`;
  - `db/phase8/promotion_reviews/<date>.md`.
- The review combines:
  - current default-off readiness audit;
  - explicit-promotion dry-run audit;
  - broad regression and outcome baseline summaries;
  - adapter drill for default-off, switch-without-approval, and
    explicit-promotion scenarios;
  - session rollback command.
- Generated the current `2026-05-22` promotion review:
  - `promotion_discussion_ready=true`;
  - `current_promotion_ready=false`;
  - `promotion_dry_run_ready=true`;
  - `adapter_drill_passed=true`;
  - current blockers: `fallback_switch`, `explicit_promotion_decision`;
  - explicit-promotion dry-run blockers: none;
  - `merge_to_main_included=false`.
- Added `tests/test_phase8_promotion_review.py` covering:
  - shadow-only write path;
  - current default-off state;
  - explicit-promotion dry-run readiness;
  - adapter drill behavior;
  - official-path write boundary rejection.
- Validation:
  - `python -B -X utf8 -m unittest tests.test_phase8_promotion_review tests.test_shadow_advice_adapter tests.test_phase8_readiness tests.test_phase8_fallback_contract`
  - `python -B -X utf8 scripts\build_phase8_promotion_review.py --date 2026-05-22 --generated-at 2026-05-31T13:20:00+08:00 --format json`

## 2026-05-31 Phase 8 Canary Scope And Completion Audit

- Added small-scope canary guards to `scripts/shadow_advice_adapter.py`:
  - `OKRA_SHADOW_ADVICE_ALLOWED_DATES`;
  - `OKRA_SHADOW_ADVICE_ALLOWED_FUNDS`;
  - `OKRA_SHADOW_ADVICE_ALLOWED_RUN_IDS`.
- The runtime adapter still replaces whole-date official advice only. Fund
  allowlists are all-or-nothing and block the adapter if any preview fund is
  outside the allowlist.
- Added adapter routing audit events under `db/phase8/adapter_events.jsonl`.
  Events are `shadow_only`, `non_executable`, display-only, and never permit
  official-path mutation.
- Logged routing outcomes now include:
  - default-off legacy path;
  - switch-without-approval legacy path;
  - scope-blocked legacy path;
  - adapter-loaded path;
  - approved adapter error fail-closed path.
- Kept the approved-adapter error behavior fail-closed. This avoids silently
  using legacy output after an explicit promotion attempt; the event log records
  the failure for review.
- Updated `scripts/build_phase8_fallback_contract.py`,
  `scripts/audit_phase8_readiness.py`, and
  `scripts/build_phase8_promotion_review.py` so canary scope and event-log
  evidence are part of the formal Phase 8 contract.
- Added `scripts/audit_phase8_completion.py`.
  - It checks required date artifacts for `2026-03-13`, `2026-04-20`,
    `2026-05-20`, `2026-05-21`, and `2026-05-22`.
  - It checks T+1/T+5 outcome artifacts.
  - It verifies default-off current state, explicit-promotion dry-run,
    promotion review validity, and adapter event-log validity.
  - It writes `db/phase8/completion_audit.json` and
    `db/phase8/completion_audit.md`.
- Generated current Phase 8 completion evidence:
  - `completion_ready_except_main_merge=true`;
  - `all_dates_backfilled=true`;
  - `current_default_off_valid=true`;
  - `explicit_promotion_dry_run_valid=true`;
  - `promotion_review_valid=true`;
  - `adapter_event_log_valid=true`.
- Validation:
  - `python -B -X utf8 -m unittest tests.test_shadow_advice_adapter tests.test_phase8_fallback_contract tests.test_phase8_readiness tests.test_phase8_promotion_review tests.test_phase8_completion_audit`
  - `python -B -X utf8 scripts\build_phase8_fallback_contract.py --generated-at 2026-05-31T14:20:00+08:00 --format json`
  - `python -B -X utf8 scripts\build_phase8_promotion_review.py --date 2026-05-22 --generated-at 2026-05-31T14:20:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_completion.py --date 2026-05-22 --generated-at 2026-05-31T14:20:00+08:00 --format json`

## 2026-05-31 Isolated Phase 8 Canary Drill

- Added `scripts/run_phase8_canary_drill.py`.
- Added `tests/test_phase8_canary_drill.py`.
- The drill creates a temporary isolated `FUND_AGENT_HOME`, copies only the
  evidence/config/data needed for Phase 8, and runs the real promoted-path
  commands there:
  - `scripts/generate_llm_advice.py --agent-home <temp> --date 2026-05-22`;
  - `scripts/validate_llm_advice.py --agent-home <temp> --date 2026-05-22`.
- The drill uses process-local temporary guards only; no user or machine-level
  configuration is required.
- The source repo official paths are snapshotted before/after the run, and the
  source repo receives only the shadow-only report under:
  - `db/phase8/canary_drills/2026-05-22.json`;
  - `db/phase8/canary_drills/2026-05-22.md`.
- Fixed isolated-home bootstrap so a matching
  `db/portfolio_state/snapshots/<date>.json` is copied to
  `db/portfolio_state/current.json` when the isolated home has no current
  portfolio file. This prevents the validator from creating portfolio state
  during the canary and keeps the no-mutation checks meaningful.
- Integrated canary status into:
  - `scripts/build_phase8_promotion_review.py`;
  - `scripts/audit_phase8_completion.py`.
- Current `2026-05-22` canary evidence:
  - `canary_passed=true`;
  - `source_official_mutation_count=0`;
  - `isolated_official_path_generated=true`;
  - `adapter_loaded_event_observed=true`;
  - `fund_decision_count=15`;
  - `validated_action_count=15`;
  - `decision_count=15`.
- Current promotion review now reports `isolated_canary_passed=true`.
- Current completion audit now requires and reports `canary_drill_valid=true`.
- Validation:
  - `python -B -X utf8 -m unittest tests.test_phase8_canary_drill tests.test_phase8_promotion_review tests.test_phase8_completion_audit`
  - `python -B -X utf8 scripts\run_phase8_canary_drill.py --date 2026-05-22 --generated-at 2026-05-31T15:40:00+08:00 --format json`
  - `python -B -X utf8 scripts\build_phase8_promotion_review.py --date 2026-05-22 --generated-at 2026-05-31T15:45:00+08:00 --format json`
  - `python -B -X utf8 scripts\audit_phase8_completion.py --date 2026-05-22 --generated-at 2026-05-31T15:46:00+08:00 --format json`

## 2026-05-31 Promoted-Only Portability Correction

- Superseded the earlier default-off adapter plan. The current production path
  is project-level promoted-only, not machine-local environment gated.
- Added `config/production.toml` to declare `action_debate_promoted` as the
  project default chain, with `okra_env_required=false`.
- Updated `scripts/audit_phase8_completion.py` so completion is proven by
  project files, default pipeline wiring, deleted legacy scripts, promoted
  multi-date artifacts, and main merge; it no longer reads `OKRA_*` user or
  process environment variables as completion criteria.
- Removed runtime hard-coding of this computer's project path from:
  - `scripts/common.py`;
  - `app/web_api.py`;
  - `run_desktop_app.ps1`;
  - `run_daily_report.ps1`;
  - `run_nightly_review.ps1`;
  - `app/okra_helper.cmd`;
  - `app/okra_helper.vbs`;
  - `frontend/src-tauri/src/lib.rs`.
- Updated current user-facing docs to use project-root-relative commands.
- Current completion evidence is project-local and portable; no user registry
  or machine-level environment state is part of the contract.
- Validation:
  - `python -B -X utf8 -m unittest tests.test_pipeline_logic tests.test_phase8_completion_audit tests.test_phase8_readiness tests.test_promoted_advice_chain tests.test_config_wiring`
