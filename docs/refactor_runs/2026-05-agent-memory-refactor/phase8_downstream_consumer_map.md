# Phase 8 Downstream Consumer Map

Status: promoted-only rollout. The legacy multi-agent, committee synthesis,
final-advice, validator, and runtime adapter chain has been removed from the
production path.

This document records the current downstream consumer map after official-path
promotion. It supersedes earlier default-off adapter notes in the execution log.

## Production Contract

The project-level production contract is stored in:

```text
config/production.toml
```

The contract intentionally belongs to the project, not to a machine-local
environment variable. This keeps the promoted path portable when the project is
moved to another computer, packaged as an app, or run in CI.

Current production advice path:

```text
scripts/run_daily_pipeline.py
  -> scripts/run_promoted_advice_chain.py
       -> scripts/build_layered_seed.py
       -> scripts/build_action_ticket_shadow.py
       -> scripts/build_layered_retrieval_pack.py
       -> scripts/action_debate_graph.py
       -> scripts/build_official_advice_compat_preview.py
       -> scripts/promoted_advice_guardrails.py
       -> scripts/decision_ledger.py
```

The promoted chain writes the official-compatible outputs:

```text
db/committee_advice/<date>.json
db/committee_decision_bundle/<date>.json
db/llm_raw/<date>.json
db/llm_advice/<date>.json
db/validated_advice/<date>.json
db/decisions/<date>.json
db/decision_latest/<fund_code>.json
db/decision_ledger/<fund_code>.jsonl
db/phase8/promoted_runs/<date>.json
```

Deleted legacy entrypoints:

```text
scripts/run_multiagent_research.py
scripts/committee_synthesis.py
scripts/generate_llm_advice.py
scripts/validate_llm_advice.py
scripts/shadow_advice_adapter.py
```

No project completion gate depends on `OKRA_*` environment variables. Those
environment variable names may appear in old historical notes only.

## Official Consumer Areas

| Area | Official path | Current producer | Key consumers | Risk |
|---|---|---|---|---|
| validated advice | `db/validated_advice/<date>.json` | `scripts/run_promoted_advice_chain.py` via `promoted_advice_guardrails.py` | decision ledger, review, RAG, execution sync, Workbench state, shadow review | high |
| daily workspace | `db/daily_workspace/<date>/*` | `scripts/today_orchestrator.py` and daily pipeline | Today page, System page, task state, runtime status | medium |
| decision ledger | `db/decisions`, `db/decision_ledger`, `db/decision_latest` | `scripts/decision_ledger.py` called by promoted chain | daily reports, replay experiments, long-memory review inputs | high |
| review pages | `db/review_results`, `db/execution_reviews`, `reports/daily` | review/report builders reading promoted validated advice | Review page, learning summaries | medium |
| execution sync | `db/execution_sync/*`, `db/execution_status/<date>.json` | execution API endpoints only | Execution page, actual trade review, portfolio settlement | critical |
| RAG and Copilot | `db/rag/*` plus source collectors | RAG ingestion/eval scripts; still optional and gated | `app/rag_answering.py`, `app/rag_service.py`, Copilot panel | medium |
| Workbench API | `/api/snapshot`, `/api/today`, `/api/research`, `/api/shadow-review` | `app/web_api.py`, `app/web_api_services.py`, `app/shadow_review_service.py` | frontend routes and schemas | medium |

## Compatibility Fields

The promoted chain preserves the old validated-advice shape for downstream
consumers while replacing the old implementation. These action sections remain
official:

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

Shadow and learning artifacts remain non-executable review artifacts unless a
future phase explicitly promotes them. These mutation paths must reject
`shadow_only`, `learning_only`, `display_only`, or `non_executable` payloads:

| Path | Owner |
|---|---|
| `/api/execution-sync/trade` | `app/web_api_services.py::ExecutionController.execution_trade` |
| `/api/execution-sync/conversion` | `app/web_api_services.py::ExecutionController.execution_conversion` |
| `/api/execution-sync/reconcile/apply` | `app/web_api_services.py::ExecutionController.execution_reconcile_apply` |
| `/api/execution-sync/confirmation/update` | `app/web_api_services.py::ExecutionController.execution_confirmation_update` |
| `scripts/decision_ledger.py::build_and_write_decisions` | official promoted ledger writer |
| `scripts/update_decision_outcomes.py` | official decision outcome updater |
| `/api/long-memory/action` | official long-memory action endpoint |

## Verification Commands

Readiness audit:

```powershell
python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --format markdown
```

Multi-date promoted official observation:

```powershell
python -B -X utf8 scripts\run_promoted_stability_observation.py --date 2026-05-11 --date 2026-05-14 --date 2026-05-18 --date 2026-05-20 --date 2026-05-21 --date 2026-05-22 --label phase8_promoted_official_2026_05_11_14_18_20_22 --format markdown
```

Completion audit:

```powershell
python -B -X utf8 scripts\audit_phase8_completion.py --date 2026-05-22 --require-main --format markdown
```

The completion audit is considered ready only when:

- every required promoted observation date is valid;
- legacy scripts are deleted;
- `run_daily_pipeline.py` uses the promoted chain as the only advice step;
- `config/production.toml` approves the promoted project-level production path;
- the branch is merged into `main` when `--require-main` is used.
