# Phase 8 Checklist: Legacy Chain Replacement And Downline

Status: intentionally last. Do not start until shadow evidence supports
promotion.

## Goal

Replace redundant legacy daily-analysis responsibilities one at a time, keep
fallback and compatibility outputs, monitor, and only then downline old layers.

## Allowed Write Set

Only after explicit promotion:

- `scripts/run_multiagent_research.py`
- `scripts/committee_synthesis.py`
- `scripts/generate_llm_advice.py`
- `scripts/validate_llm_advice.py`
- `scripts/portfolio_optimizer.py`
- review/reporting scripts
- Workbench consumers of official advice
- compatibility adapters

## Forbidden Write Set

Until promotion:

- do not delete compatibility outputs
- do not remove fallback paths
- do not weaken official validator behavior
- do not mutate execution sync through new shadow artifacts

## Inputs

- old/new shadow comparison history
- user review feedback
- action-ticket outcome quality
- policy/skill stability
- downstream consumer map
- rollback checkpoint

## Required Evidence Before Starting

- New chain can generate official-compatible advice.
- Workbench can compare old and new outputs.
- Outcome evaluation has enough examples to expose obvious regressions.
- Hard constraints are mapped and tested.
- Existing execution sync, official NAV/PnL, Copilot, RAG, and Workbench flows
  have regression baselines.
- Rollback path is documented.

## Implementation Steps

1. Build downstream consumer map for `validated_advice`, daily workspace,
   decision ledger, review pages, and execution sync.
2. Decide which legacy layer is replaced first.
3. Add compatibility adapter if old consumers still expect old field names.
4. Add fallback switch before changing the official path.
5. Move one official responsibility at a time.
6. Run old/new comparison after each responsibility transfer.
7. Monitor fallback usage.
8. Keep fallback switch until a stable release checkpoint exists.
9. Delete or archive legacy code only after tests, real-date review, and
   fallback monitoring pass.

## Candidate Reduction Targets

- committee prose-only synthesis that no longer owns action formation
- duplicated evidence packing replaced by layered retrieval pack
- validator-only explanations replaced by ticket guardrail mapping
- optimizer logic only after action-ticket portfolio selection is equivalent
- review pages only after API DTOs are stable

## Required Tests

- official advice compatibility
- validator/optimizer hard constraints
- pipeline logic
- multi-agent and review
- execution sync
- official revaluation/realtime
- RAG consumers if retrieval changes
- long memory
- frontend build and Tauri check

Suggested commands:

```powershell
python -B -X utf8 -m unittest tests.test_pipeline_logic tests.test_multiagent_and_review tests.test_validation_and_trade
python -B -X utf8 -m unittest tests.test_execution_sync tests.test_revaluation_and_realtime tests.test_long_memory
python -B -X utf8 -m unittest discover -s tests -p "test_rag_*.py"
cd frontend
npm run build
npm run tauri:check
```

## Manual Verification

- Compare official outputs before and after replacement for several dates.
- Confirm execution sync still links suggestions correctly.
- Confirm Workbench pages still render current and historical dates.
- Confirm rollback switch restores old path.
- Confirm fallback usage is logged.

## Rollback Notes

Every reduction PR must state:

- old entrypoint
- new entrypoint
- compatibility adapter
- feature flag or rollback command
- files to restore if the new path fails

Do not remove the last fallback path in the same branch that first promotes a
new official path.

## Promotion Gate

Legacy code can be deleted only after:

- new path is official for a stable period;
- fallback has not been used for real failures;
- replacement path has stable real-date comparison evidence;
- downstream consumers no longer depend on legacy fields;
- user accepts the migration evidence.
