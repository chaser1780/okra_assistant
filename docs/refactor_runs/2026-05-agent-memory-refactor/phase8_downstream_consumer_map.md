# Phase 8 Downstream Consumer Map

Status: pre-promotion audit. No official-path replacement has started.

This document satisfies Phase 8 step 1 and records the current downstream
consumer map before any legacy daily-analysis responsibility is moved.

Update after Phase 8 step 3 preview:

- `scripts/build_official_advice_compat_preview.py` now builds a
  non-executable official-advice compatibility preview from action tickets,
  retrieval packs, and action debates.
- The preview writes only to
  `db/refactor_shadow_runs/<date>__official_advice_compat_preview/official_advice_compat_preview.json`.
- It produces committee-bundle-like, final-advice-like, and
  validated-section-like preview shapes for review.
- It does not write `db/committee_decision_bundle`, `db/llm_advice`,
  `db/validated_advice`, decision ledger, execution sync, portfolio state, or
  long memory.
- No fallback switch or official-path promotion is active yet.

## Boundary Decision

Phase 8 is not ready for official-path mutation yet.

Current state:

- Shadow artifacts exist for action tickets, retrieval packs, action debates,
  outcome events, adaptive policies, strategy skills, Markdown review, and a
  read-only Workbench review page.
- The official daily chain still owns `validated_advice`, decision ledger,
  execution sync, portfolio state, official reports, RAG source ingestion, and
  Workbench snapshot DTOs.
- No explicit promotion decision has been made for writing new-chain output into
  the official path.

Therefore the next safe Phase 8 step is a read-only readiness audit and
compatibility map, not a pipeline replacement.

After the compatibility preview exists, the next safe step remains fallback
switch design and explicit rollback documentation before any official-path
mutation.

## Official Consumer Areas

| Area | Official path | Key producers | Key consumers | Risk |
|---|---|---|---|---|
| validated advice | `db/validated_advice/<date>.json` | `scripts/validate_llm_advice.py` | decision ledger, review, RAG, execution sync, Workbench state, shadow review | high |
| daily workspace | `db/daily_workspace/<date>/*` | `scripts/today_orchestrator.py` | Today page, System page, task state, runtime status | medium |
| decision ledger | `db/decisions`, `db/decision_ledger`, `db/decision_latest` | `scripts/decision_ledger.py`, `scripts/update_decision_outcomes.py` | daily reports, replay experiments, long-memory review inputs | high |
| review pages | `db/review_results`, `db/execution_reviews`, `reports/daily` | `scripts/review_advice.py`, report builders | Review page, learning summaries | medium |
| execution sync | `db/execution_sync/*`, `db/execution_status/<date>.json` | `scripts/execution_sync.py`, execution API endpoints | Execution page, actual trade review, portfolio settlement | critical |
| RAG and Copilot | `db/rag/*` plus source collectors | `scripts/rag_sources.py` | `app/rag_answering.py`, `app/rag_service.py`, Copilot panel | medium |
| Workbench API | `/api/snapshot`, `/api/today`, `/api/research`, `/api/shadow-review` | `app/web_api.py`, `app/web_api_services.py`, `app/shadow_review_service.py` | frontend routes and schemas | medium |

## Compatibility Fields

Any future official adapter must preserve validated-advice-compatible action
sections until all downstream consumers are migrated:

```text
tactical_actions
dca_actions
hold_actions
```

Each action must continue to expose:

```text
suggestion_id
fund_code
fund_name
validated_action
validated_amount
model_action
confidence
thesis
policy_rule_hits
constraint_hits
validation_notes
execution_status
source_signal_ids
opposing_signal_ids
cash_impact
allocation_impact
```

Top-level compatibility fields:

```text
report_date
generated_at
decision_mode
degradation_mode
execution_eligible
advice_is_fallback
advice_is_mock
decision_source
market_view
cross_fund_observations
optimization_summary
optimizer_candidates
committee_decision_bundle
```

## Mutation Boundaries

These paths must not accept `db/action_tickets`, `db/retrieval_packs`, or
`db/action_debates` while artifacts remain `shadow_only` and
`non_executable=true`:

| Path | Owner |
|---|---|
| `/api/execution-sync/trade` | `app/web_api_services.py::ExecutionController.execution_trade` |
| `/api/execution-sync/conversion` | `app/web_api_services.py::ExecutionController.execution_conversion` |
| `/api/execution-sync/reconcile/apply` | `app/web_api_services.py::ExecutionController.execution_reconcile_apply` |
| `/api/execution-sync/confirmation/update` | `app/web_api_services.py::ExecutionController.execution_confirmation_update` |
| `scripts/decision_ledger.py::build_and_write_decisions` | official validated-advice ledger writer |
| `scripts/update_decision_outcomes.py` | official decision outcome updater |
| `/api/long-memory/action` | official long-memory action endpoint |

## First Replacement Candidate

The first candidate for a future promoted change should be:

```text
scripts/generate_llm_advice.py::build_final_advice_from_committee_bundle
```

More precisely, replace the committee-bundle-to-final-advice adapter behind a
fallback switch, while keeping `scripts/validate_llm_advice.py` as the official
guardrail, optimizer, `validated_advice`, and ledger writer.

Reason:

- This layer already separates canonical action formation from final narrative.
- It is upstream of official validation, so hard constraints remain enforced by
  the current validator.
- Existing Workbench, review, RAG, execution sync, reports, and ledger consumers
  can continue to consume official validated advice.

Do not replace these first:

- `db/validated_advice/<date>.json` direct producer contract;
- `scripts/portfolio_optimizer.py`;
- execution sync mutation paths;
- long-memory promotion from shadow artifacts.

## Required Gates Before Promotion

The readiness audit currently marks promotion as blocked until all of these are
true:

- fallback switch exists and is documented;
- old/new comparison is available for more than a single golden date;
- outcome examples cover enough real dates to expose obvious regressions;
- hard constraints remain mapped and tested;
- execution sync, NAV/PnL, Copilot, RAG, and Workbench regression baselines pass;
- rollback command and files are documented;
- user explicitly accepts official-path promotion evidence.

## Audit Command

Use this command for a deterministic pre-promotion status:

```powershell
python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22
```

Markdown output is available with:

```powershell
python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --format markdown
```

## Compatibility Preview Command

Use this command to regenerate the current preview evidence:

```powershell
python -B -X utf8 scripts\build_official_advice_compat_preview.py --date 2026-05-22 --format json
```

For the current golden date, the preview reports:

```text
official_compatible_advice=true
committee_bundle_compatible=true
llm_advice_compatible=true
fallback_switch_active=false
promotion_ready=false
official_paths_written=[]
```
