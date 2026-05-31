# Phase 8 Checklist: Legacy Chain Replacement And Downline

Status: promoted-only implementation.

## Goal

Make the action-ticket, layered retrieval, debate, and promoted guardrail chain
the default official daily-analysis path. Remove the old multi-agent,
committee, final-advice, validator, and runtime adapter layers after evidence
shows the promoted chain is official-compatible and stable.

## Final Write Set

Production code:

- `scripts/run_daily_pipeline.py`
- `scripts/run_promoted_advice_chain.py`
- `scripts/promoted_advice_guardrails.py`
- `scripts/build_layered_seed.py`
- `scripts/build_action_ticket_shadow.py`
- `scripts/build_layered_retrieval_pack.py`
- `scripts/action_debate_graph.py`
- `scripts/build_official_advice_compat_preview.py`
- `scripts/decision_ledger.py`
- `config/production.toml`

Audit and observation:

- `scripts/audit_phase8_readiness.py`
- `scripts/audit_phase8_completion.py`
- `scripts/run_promoted_stability_observation.py`
- `scripts/build_shadow_regression_baseline.py`
- `scripts/build_outcome_evidence_baseline.py`

Deleted legacy code:

- `scripts/run_multiagent_research.py`
- `scripts/committee_synthesis.py`
- `scripts/generate_llm_advice.py`
- `scripts/validate_llm_advice.py`
- `scripts/shadow_advice_adapter.py`

Project state must not rely on machine-local environment variables or
hard-coded local paths. Promotion state belongs in project files and code
defaults so it survives migration and app packaging.

## Completion Evidence

Phase 8 is complete only when all of these are true:

- `run_daily_pipeline.py` invokes `run_promoted_advice_chain.py` as the only
  official advice-generation step.
- The old multi-agent, committee, final-advice, validator, and runtime adapter
  scripts are absent.
- `config/production.toml` declares `action_debate_promoted` as the project
  default chain and sets `okra_env_required=false`.
- Promoted official outputs exist and validate for the required multi-date
  observation set.
- Mutation endpoints reject `shadow_only`, `learning_only`, `display_only`, and
  `non_executable` payload markers.
- Backend, frontend, hygiene, readiness, and completion checks pass.
- The branch has been merged to `main`.

## Required Observation Dates

Current promoted stability observation set:

```text
2026-05-11
2026-05-14
2026-05-18
2026-05-20
2026-05-21
2026-05-22
```

Each date must have valid promoted artifacts:

```text
db/phase8/promoted_runs/<date>.json
db/llm_raw/<date>.json
db/validated_advice/<date>.json
db/action_seed/<date>.json
db/decisions/<date>.json
```

The promoted run must report:

```text
mode=action_debate_promoted
summary.promoted_run_passed=true
summary.advice_mode=action_debate_promoted
summary.decision_source=action_debate_promoted
native_independent_of_legacy_validated_seed=true
```

## Required Tests

Backend focused tests:

```powershell
python -B -X utf8 -m unittest tests.test_pipeline_logic tests.test_phase8_readiness tests.test_phase8_completion_audit tests.test_promoted_advice_chain tests.test_validation_and_trade
```

Broader backend suite:

```powershell
python -B -X utf8 -m unittest discover -s tests
```

Frontend checks:

```powershell
cd frontend
npm run build
npm run tauri:check
```

Hygiene:

```powershell
python -B -X utf8 scripts\check_repo_text_hygiene.py
git diff --check
```

## Audit Commands

Readiness:

```powershell
python -B -X utf8 scripts\audit_phase8_readiness.py --date 2026-05-22 --format json
```

Multi-date promoted stability:

```powershell
python -B -X utf8 scripts\run_promoted_stability_observation.py --date 2026-05-11 --date 2026-05-14 --date 2026-05-18 --date 2026-05-20 --date 2026-05-21 --date 2026-05-22 --label phase8_promoted_official_2026_05_11_14_18_20_22 --format json
```

Completion:

```powershell
python -B -X utf8 scripts\audit_phase8_completion.py --date 2026-05-22 --require-main --format json
```

## Rollback Notes

The old chain has been removed. Rollback is a git operation, not a runtime
environment switch:

1. Revert the commit that deletes the legacy scripts and sets
   `run_promoted_advice_chain.py` as default.
2. Restore `config/production.toml` to the previous non-promoted contract.
3. Re-run completion/readiness audits and focused tests before using restored
   outputs.

Do not introduce machine-local rollback switches as a substitute for project
state. Temporary operator environment variables are allowed only for ad hoc
experiments and must not be completion criteria.
