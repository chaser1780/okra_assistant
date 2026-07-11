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
- [superseded] The proposed `codex/action-ticket-shadow-foundation` branch was
  not needed after the implementation advanced through the promoted-only
  rollout on the current project history.
- [done] Finalize Phase 1 action-ticket dataclass fields and enums.
- [done] Implement standalone `build_action_ticket_shadow.py` without adding
  it to the official daily pipeline yet.
- [done] Add focused action-ticket tests for add, reduce, scheduled DCA,
  meaningful hold, hard-blocked, soft-adjusted, and missing-data tickets.
- [done] Add action-ticket dataclass round-trip tests with fixed clock.
- [done] Finalize Phase 2 retrieval-pack dataclasses and no-future checks.
- [done] Design retrieval-pack builder for action-ticket generation.
- [done] Add retrieval-pack round-trip tests and trace completeness metric.
- [done] Classify existing hard constraints and keep them explicit.
- [done] Design adaptive soft-constraint memory lifecycle.
- [done] Design adaptive policy promotion, weakening, contradiction, and
  cap rules.
- [done] Define strategy skill Markdown and registry metadata schema.
- [done] Add strategy skill registry/Markdown frontmatter round-trip tests.
- [done] Design Skill Curator Agent input/output contract.
- [done] Design skill-pack builder and skill usage tracking.
- [done] Design skill outcome evaluation and promotion/revision rules.
- [done] Decide LangGraph dependency/version and checkpoint backend before
  Phase 3 coding.
- [done] Define graph state schema for `debate_to_action_graph`.
- [done] Implement `run_action_debate_shadow.py` as non-mutating shadow entry.
- [done] Implement Phase 4 outcome event model and standalone evaluator.
- [done] Add CLI/Markdown refactor review before full Workbench UI.
- [done] Add read-only Workbench comparison only after shadow artifacts
  stabilize.
- [done] Build Phase 8 downstream consumer map before official-path
  replacement.
- [done] Add read-only Phase 8 readiness audit before compatibility adapter or
  fallback switch work.
- [done] Add Phase 8 official-advice compatibility preview without official
  path mutation.
- [done] Design Phase 8 fallback switch and rollback command before
  touching the official daily chain.
- [done] Fix adaptive-policy replay so derived policy events are re-materialized
  from current outcome artifacts without stale support/contradict conflicts.
- [done] Harden Shadow Review API/UI safety contracts and same-fund multi-action
  comparison.
- [done] Build strict named multi-date shadow regression baselines:
  `2026-05-21..2026-05-22` passes official-compatible DCA/hold replay;
  the broader `2026-03-13`, `2026-04-20`, and `2026-05-20..2026-05-22`
  coverage baseline covers add/reduce/switch_out and now passes with the
  shadow-adapter-only validated-section replay contract.
- [done] Build named multi-date outcome evidence baseline for
  `2026-03-13`, `2026-04-20`, and `2026-05-20..2026-05-22` across T+1/T+5
  horizons.
- [done] Add Phase 8 canary scope guards, adapter event logging, promotion
  review, and completion audit so fallback/rollback readiness is auditable
  before any official-path mutation.
- [done] Add isolated Phase 8 canary drill so the promoted adapter path can be
  exercised in a temporary `FUND_AGENT_HOME` without mutating source-repo
  official outputs.
- [done] Complete the Phase 8 promoted-only rollout. The promoted action-debate
  chain is now the project default in `config/production.toml`, the legacy
  official chain has been removed, and `db/phase8/completion_audit.json`
  reports `completion_ready=true`.
- [done] Correct outcome-learning semantics so adaptive learning uses
  action-aligned benchmark excess return, excludes missing/non-finite/neutral
  relative signals, and removes stale derived policy events.
- [done] Add fail-closed historical replay trust validation, trusted-only
  default replay, explicit structural-only replay, atomic learning rejection,
  and replay audit sidecars.
- [done] Add immutable decision-snapshot capture and blocked trust-manifest
  candidates. Capture is integrated into the promoted chain, but candidates
  remain `blocked` and `learning_eligible=false` until reviewed.
- [done] Add historical learning lineage audits and fail-closed skill usage.
  Legacy absolute-return policy events, policies, and skills remain visible but
  cannot be consumed unless their learning trust status is `trusted`.
- [done] Expose replay and learning trust on the Review page with blocked
  defaults when the manifest or audit evidence is absent.
- [done] Restrict the Python API to loopback bind targets and approved local
  React/Tauri origins.
- [done] Apply strict top-level mutation DTOs (`extra="forbid"`) to run,
  execution, long-memory, RAG admin, and open-url commands.
- [done] Bind reconciliation apply to a server-saved preview SHA-256, expected
  portfolio-state SHA-256, and an idempotent apply-request digest.
- [pending] Capture and review the first clean real date that can be promoted
  from a blocked manifest candidate to `trusted` and
  `learning_eligible=true`. No current historical date qualifies.
- [pending] Keep production embedding/vector retrieval gated until a measured
  gray release is approved. Current RAG retrieval is enabled with lexical text
  scoring and legacy fallback; embedding is disabled/dry-run and the vector
  backend remains `sqlite_mock`.

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
| Phase 8 downstream consumer map | 8 | `phase8_downstream_consumer_map.md`, `scripts/audit_phase8_readiness.py`, `tests/test_phase8_readiness.py` | Read-only audit marks `promotion_ready=false` until official-compatible adapter, fallback switch, broader outcome evidence, regression baselines, rollback path, and explicit promotion are present |
| Phase 8 compatibility preview | 8 | `scripts/build_official_advice_compat_preview.py`, `tests/test_official_advice_compat_preview.py` | `2026-05-22` preview produced committee-bundle-like, final-advice-like, and validated-section-like shapes under `db/refactor_shadow_runs/`; official outputs remain unchanged and promotion remains blocked |
| Hard constraint catalog | 0/1/8 | `scripts/build_hard_constraint_catalog.py`, `tests/test_hard_constraint_catalog.py`, `db/refactor_shadow_runs/hard_constraint_catalog.json` | Machine-readable `shadow_only` catalog parsed from `hard_constraints_inventory.md`; deterministic hard constraints remain official source of truth |
| Strategy skill pack and usage candidates | 6 | `scripts/build_strategy_skill_pack.py`, `tests/test_strategy_skill_pack.py`, `db/strategy_skills/skill_pack.json`, `db/strategy_skills/usage/<date>.json` | Learning-only skill pack and non-mutating usage candidates are written with `applied_to_ticket_file=false` and `auto_activation_allowed=false` |
| Phase 8 fallback and rollback contract | 8 | `scripts/build_phase8_fallback_contract.py`, `tests/test_phase8_fallback_contract.py`, `db/phase8/fallback_contract.json` | Fallback switch, rollback command, small-scope canary env vars, and adapter event log are documented as `shadow_only`; switch remains inactive and promotion remains blocked |
| Adaptive policy replay hardening | 5 | `scripts/update_adaptive_policies.py`, `tests/test_adaptive_policies.py`, `db/strategy_memory/policy_events.jsonl`, `db/strategy_memory/policies.json` | Derived policy events are keyed by source outcome and rewritten from current outcome artifacts; `2026-05-22` now has 14 valid events with no source-outcome support/contradict conflicts |
| Shadow review contract hardening | 7 | `app/shadow_review_service.py`, `app/api_contracts.py`, `frontend/src/lib/schemas.ts`, `frontend/src/app/pages/ShadowReviewPage.tsx`, `tests/test_web_api_action_tickets.py` | Boundary-invalid artifacts fail instead of being silently displayed; same-fund multi-action rows remain distinct; policy/skill/outcome summaries are displayed |
| Multi-date shadow regression baseline | 8 | `scripts/build_shadow_regression_baseline.py`, `tests/test_shadow_regression_baseline.py`, `db/refactor_shadow_runs/regression_baselines/phase8_shadow_official_compatible_2026_05_21_22/`, `db/refactor_shadow_runs/regression_baselines/phase8_shadow_coverage_add_reduce_switch_2026_03_13_04_20_05_20_22/` | DCA/hold official-compatible baseline remains a local compatibility fixture; broad add/reduce/switch_out/scheduled_dca/hold baseline passes for all 5 dates and now must also satisfy audit-time source-hash, date-count, ready-row, and broad-action checks before `regression_baselines=ready` |
| Multi-date outcome evidence baseline | 4/8 | `scripts/build_outcome_evidence_baseline.py`, `tests/test_outcome_evidence_baseline.py`, `db/refactor_shadow_runs/outcome_evidence_baselines/phase8_outcome_add_reduce_switch_2026_03_13_04_20_05_20_22/` | Broad baseline passed for `2026-03-13`, `2026-04-20`, and `2026-05-20..2026-05-22` across T+1/T+5; 10 artifacts, 143 scored events, action types `add`, `reduce`, `switch_out`, `scheduled_dca`, `hold`; Phase 8 audit now rejects single-date/DCA-only or stale-hash baselines for `outcome_examples=ready` |
| Phase 8 isolated canary drill | 8 | `scripts/run_phase8_canary_drill.py`, `tests/test_phase8_canary_drill.py`, `db/phase8/canary_drills/2026-05-22.json`, `db/phase8/canary_drills/2026-05-22.md` | Canary reports `canary_passed=true`, source official mutation count 0, isolated official path generated, adapter-loaded event observed, and 15 validated decisions |
| Phase 8 promotion review package | 8 | `scripts/build_phase8_promotion_review.py`, `tests/test_phase8_promotion_review.py`, `db/phase8/promotion_reviews/2026-05-22.json`, `db/phase8/promotion_reviews/2026-05-22.md` | Historical pre-promotion package retained as evidence; superseded by the promoted-only rollout row below |
| Phase 8 completion audit | 8 | `scripts/audit_phase8_completion.py`, `tests/test_phase8_completion_audit.py`, `db/phase8/completion_audit.json`, `db/phase8/completion_audit.md` | Current audit verifies promoted dates, legacy deletion, promoted-only default pipeline, project production config, and main merge; machine-local OKRA environment variables are not completion criteria |
| Relative learning semantics | 10A | `scripts/evaluate_action_ticket_outcomes.py`, `scripts/update_adaptive_policies.py`, `tests/test_action_outcomes.py`, `tests/test_adaptive_policies.py` | Learning labels and policy events use action-aligned benchmark excess return; missing benchmark, non-finite and neutral signals do not create learning events; stale derived events are removed |
| Historical replay trust gate | 10B | `config/historical_replay_trust.json`, `scripts/replay_trust.py`, `scripts/run_replay_experiment.py`, `tests/test_replay_trust.py`, `tests/test_evidence_and_replay.py` | Replay defaults to trusted dates; structural replay requires explicit opt-in and never learns; untrusted learning batches abort before ledger/SQLite/long-memory mutation; audits write under `db/replay_audits/` |
| Immutable replay snapshot capture | 10C | `scripts/capture_replay_snapshot.py`, `tests/test_capture_replay_snapshot.py`, `scripts/run_promoted_advice_chain.py`, `db/replay_snapshots/<report-date>__<cutoff-hash>/` | Decision inputs are copied byte-for-byte with source hashes and contamination findings; generated manifest candidates are immutable, blocked, and never auto-promoted to the source-controlled trust manifest |
| Historical learning quarantine | 10D | `scripts/audit_learning_trust.py`, `tests/test_learning_trust_audit.py`, `db/learning_trust_audits/latest.json`, `scripts/build_strategy_skill_pack.py` | Outcome-to-policy-to-skill lineage is classified as `trusted`, `legacy_untrusted`, or `blocked`; current old policy/skill outputs remain visible but fail closed for skill usage; source artifacts are not rewritten |
| Workbench learning trust surface | 7/10 | `app/workbench_state.py`, `frontend/src/app/pages/ReviewPage.tsx`, `tests/test_workbench_learning_trust.py` | Review view exposes manifest mode, learning eligibility, replay audit path, learning audit summary, and a blocked default when trust evidence is absent |
| Local mutation API hardening | API/execution | `app/api_contracts.py`, `app/web_api.py`, `scripts/execution_sync.py`, `tests/test_web_api_long_memory.py`, `tests/test_execution_sync.py` | Server rejects non-loopback bind targets and untrusted origins; mutation DTOs reject extra top-level fields; reconcile apply verifies saved preview and portfolio hashes and supports idempotent replay |

## Phase Execution Board Template

Use this structure once implementation branches begin:

| Phase | Status | Owner / agent | Depends on | Write scope | Output artifact | Validation command | Completion evidence | Notes |
|---|---|---|---|---|---|---|---|---|
| Phase 0.5 | done | Codex | Phase 0 | `tests/fixtures/golden_slices/*`, `scripts/replay_refactor_slice.py`, `scripts/diff_refactor_slice.py`, optional `scripts/artifact_boundary.py` | `db/refactor_shadow_runs/2026-05-22__017641__scheduled_dca/`, `diff_report.md` | `python -B -X utf8 -m unittest tests.test_refactor_golden_slice` | PASS; `2026-05-22 + 017641 + scheduled_dca` locked | One date, one fund, one action type |
| Phase 1 | partial | Codex | Phase 0 + Phase 0.5 | `scripts/action_ticket_models.py`, `scripts/build_action_ticket_shadow.py`, `tests/test_action_tickets.py` | `db/action_tickets/<date>.json` | `python -B -X utf8 -m unittest tests.test_action_tickets` | PASS; `2026-05-22` produced 15 shadow-only tickets, including `017641` scheduled DCA | Standalone only; not integrated into daily pipeline/UI |
| Phase 2 | partial | Codex | Phase 1 | `scripts/layered_context_models.py`, `scripts/build_layered_retrieval_pack.py`, `tests/test_layered_retrieval_pack.py` | `db/retrieval_packs/<date>.json` | `python -B -X utf8 -m unittest tests.test_layered_retrieval_pack` | PASS; `2026-05-22` produced 15 packs, trace completeness 1.0, no-future violations 0 | Lexical RAG retrieval is enabled with legacy fallback; production embedding/vector retrieval remains gated |
| Phase 3 | partial | Codex | Phase 1 + Phase 2 | `scripts/action_debate_graph.py`, `scripts/action_debate_prompts.py`, `scripts/run_action_debate_shadow.py`, `tests/test_action_debate_graph.py` | `db/action_debates/<date>.json`, `db/action_debates/runtime/<date>.json` | `python -B -X utf8 -m unittest tests.test_action_debate_graph` | PASS; `2026-05-22` produced 15 shadow debates, node failures 0, state size 5960 bytes | Local file-backed shadow graph; no external LangGraph dependency yet; no ticket rewrite |
| Phase 4 | partial | Codex | Phase 1 + official NAV facts | `scripts/outcome_event_models.py`, `scripts/evaluate_action_ticket_outcomes.py`, `scripts/build_outcome_evidence_baseline.py`, `tests/test_action_outcomes.py`, `tests/test_outcome_evidence_baseline.py` | `db/outcome_events/<base_date>__<horizon>.json`, `db/refactor_shadow_runs/outcome_evidence_baselines/<baseline_name>/` | `python -B -X utf8 -m unittest tests.test_action_outcomes tests.test_outcome_evidence_baseline` | PASS; evaluator now emits action-aligned benchmark excess return and optional explicit-cost-adjusted learning basis | Existing historical outcome artifacts remain immutable and are blocked by the Phase 10D audit until a trusted replay lineage exists |
| Phase 5 | partial | Codex | Phase 4 outcome events | `scripts/adaptive_policy_models.py`, `scripts/update_adaptive_policies.py`, `tests/test_adaptive_policies.py` | `db/strategy_memory/policy_events.jsonl`, `db/strategy_memory/policies.json` | `python -B -X utf8 -m unittest tests.test_adaptive_policies` | PASS; relative learning semantics, lifecycle, replay idempotence, stale derived-event replacement, malformed-line isolation, non-blocking effects, and per-scope caps covered | Current historical 14 policy events and 4 policies are retained as `legacy_untrusted`; none are trusted learning inputs |
| Phase 6 | done-for-shadow | Codex | Phase 5 policy clusters + Phase 4 outcomes | `scripts/strategy_skill_models.py`, `scripts/strategy_skill_store.py`, `scripts/run_skill_curator.py`, `scripts/build_strategy_skill_pack.py`, `tests/test_strategy_skills.py`, `tests/test_strategy_skill_pack.py` | `db/strategy_skills/registry.json`, `db/strategy_skills/<skill_id>/skill.md`, `db/strategy_skills/<skill_id>/events.jsonl`, `db/strategy_skills/skill_pack.json`, `db/strategy_skills/usage/<date>.json` | `python -B -X utf8 -m unittest tests.test_strategy_skills tests.test_strategy_skill_pack` | PASS; current real registry has 3 candidate skills and 0 active skills; trust status is attached to pack entries | Learning-only and non-executable; untrusted skills remain visible but produce no usage candidates; auto active promotion remains disabled |
| Phase 7 early review | partial | Codex | Phase 1 + Phase 2 + Phase 3 + optional Phase 4/5/6 | `scripts/render_refactor_review.py`, `tests/test_refactor_review_markdown.py`, `scripts/artifact_boundary.py` | `db/refactor_reviews/<date>.md` | `python -B -X utf8 -m unittest tests.test_refactor_review_markdown` | PASS; `2026-05-22` Markdown review rendered ready status and chained official advice, tickets, packs, debates, outcome events, adaptive policy summary, and strategy skill registry summary | CLI/Markdown only; no API, UI, execution, or long-memory writes |
| Phase 7 Workbench review surface | partial | Codex | Phase 1 + Phase 2 + Phase 3 + optional Phase 4/5/6 | `app/api_contracts.py`, `app/shadow_review_service.py`, `app/web_api.py`, `frontend/src/lib/schemas.ts`, `frontend/src/lib/workbenchApi.ts`, `frontend/src/lib/workbenchQuery.ts`, `frontend/src/lib/types.ts`, `frontend/src/app/routes.tsx`, `frontend/src/app/routeMeta.ts`, `frontend/src/components/okra/WorkbenchLayout.tsx`, `frontend/src/app/pages/ShadowReviewPage.tsx`, `tests/test_web_api_action_tickets.py` | `GET /api/shadow-review?date=YYYY-MM-DD`, `/shadow-review` Workbench page | `python -B -X utf8 -m unittest tests.test_web_api_action_tickets`; `npm run build` | PASS; `2026-05-22` API DTO status `ready`, 15 items, agreement 1.0, `nonExecutable=true`, `displayOnly=true`, `executionDisabled=true`; boundary violations fail; same-fund multi-action rows remain distinct | Read-only API/UI only; no execution buttons, portfolio mutation, official advice mutation, long-memory action, policy/skill promotion, or snapshot-synthesized review items |
| Phase 8 promoted-only rollout | done | Codex | Phase 1-7 evidence + Phase 8 audits | `config/production.toml`, `scripts/run_daily_pipeline.py`, `scripts/run_promoted_advice_chain.py`, `scripts/promoted_advice_guardrails.py`, `scripts/audit_phase8_readiness.py`, `scripts/audit_phase8_completion.py`, `scripts/run_promoted_stability_observation.py`, `tests/test_phase8_readiness.py`, `tests/test_phase8_completion_audit.py`, `tests/test_promoted_advice_chain.py` | official-compatible advice outputs, `db/phase8/promoted_runs/<date>.json`, multi-date promoted observation report, completion audit | `python -B -X utf8 -m unittest tests.test_pipeline_logic tests.test_phase8_readiness tests.test_phase8_completion_audit tests.test_promoted_advice_chain tests.test_validation_and_trade`; `python -B -X utf8 scripts\audit_phase8_completion.py --date 2026-05-22 --require-main --format json` | Promoted chain is the default official path; legacy official-chain scripts are deleted; `db/phase8/completion_audit.json` reports `completion_ready=true` | Completed; historical pre-promotion artifacts remain evidence only |
| Phase 10A relative learning semantics | done | Codex | Phase 4/5 | outcome evaluator and adaptive policy updater | relative outcome and derived policy artifacts | `python -B -X utf8 -m unittest tests.test_action_outcomes tests.test_adaptive_policies` | Benchmark-relative, action-aligned learning with explicit-cost support and stale-event removal | Historical artifacts are not rewritten |
| Phase 10B replay trust gate | done | Codex | Phase 10A | trust manifest, replay validator, replay preflight/audit | `config/historical_replay_trust.json`, `db/replay_audits/<experiment>.json` | `python -B -X utf8 -m unittest tests.test_replay_trust tests.test_evidence_and_replay` | Fail-closed replay and atomic learning rejection | Structural replay is diagnostic-only |
| Phase 10C immutable snapshot capture | done-for-capture | Codex | Phase 10B + promoted chain | replay snapshot capture | `db/replay_snapshots/<date>/manifest_candidate.json` | `python -B -X utf8 -m unittest tests.test_capture_replay_snapshot tests.test_promoted_advice_chain` | Exact-byte snapshots, hashes, contamination audit, immutable conflicts, promoted-chain capture hook | First real trusted date is still pending review and promotion |
| Phase 10D learning quarantine | done | Codex | Phase 10A/10B | lineage audit and consumer gate | `db/learning_trust_audits/latest.json` | `python -B -X utf8 -m unittest tests.test_learning_trust_audit tests.test_strategy_skill_pack` | Current legacy policy/skill artifacts are quarantined; only trusted skills can create usage candidates | Audit/UI are read-only; no automatic activation |
