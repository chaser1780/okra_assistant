# OKRA Documentation Index

This index describes the current React + Tauri workbench and canonical
today-analysis code path. Older Qt/PySide PRDs, handoff notes, completed
improvement lists, and obsolete screenshot baselines were removed from the
working documentation set; use git history if those past artifacts are needed.

## Current Entrypoints

- `README.md`: project overview, canonical product loops, active CLI/API/UI entrypoints.
- `project.toml`: project metadata and current desktop/API/today-analysis/long-memory entrypoints.
- `docs/modern_workbench.md`: current React + Tauri workbench, local API surface, runtime behavior.
- `config/retention.toml`: retention policy for rebuildable runtime artifacts.
- `scripts/cleanup_retention.py`: dry-run-first cleanup planner; use explicit apply commands only after reviewing the generated plan.

## Current Design Docs

- `docs/fund_multiagent_design.md`: current fund multi-agent research chain, committee synthesis, validated advice, and execution boundary.
- `docs/okra_unified_rag_architecture.md`: unified vector RAG architecture for Copilot Q&A and future today-analysis retrieval.

## Archived Development Notes

- `docs/archive/2026-05-rag-development-plan/`: completed/stage-specific RAG task split, handoff notes, acceptance matrix, and subagent notes. Keep it for reference, but do not treat it as the current implementation plan.

## Data Retention

Permanent state must be preserved:

- `db/long_memory/`
- `db/execution_sync/`
- `db/portfolio_state/`
- `db/validated_advice/`
- `db/decision_ledger/`
- `db/decision_latest/`
- `db/decisions/`

Rebuildable or archivable material is managed by retention rules:

- `raw/news/`
- `db/news_query_plans/`
- `db/llm_context/`
- `db/evidence_index/`
- `db/daily_workspace/`
- expired `logs/`, `cache/`, and `temp/`

Preview cleanup first:

```powershell
python -B -X utf8 scripts\cleanup_retention.py --dry-run --assert-protected --report
```

## References

- `references/scoring_rules.md`
- `references/source_priority.md`

## Recommended Reading Order

1. `README.md`
2. `docs/modern_workbench.md`
3. `docs/fund_multiagent_design.md`
4. `docs/okra_unified_rag_architecture.md`
