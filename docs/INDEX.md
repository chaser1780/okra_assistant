# OKRA Documentation Index

This index describes the current React + Tauri workbench and canonical
today-analysis code path. Older Qt/PySide PRDs, handoff notes, completed
improvement lists, obsolete screenshot baselines, and superseded RAG task-split
notes were removed from the working documentation set; use git history if those
past artifacts are needed.

## Current Entrypoints

- `README.md`: project overview, canonical product loops, active CLI/API/UI entrypoints.
- `project.toml`: project metadata and current desktop/API/today-analysis/long-memory entrypoints.
- `docs/modern_workbench.md`: current React + Tauri workbench, local API surface, runtime behavior.
- `docs/cloud_migration_plan.md`: two-phase cloud migration plan, Tauri local/remote mode, Oracle VM + Cloudflare Access/Tunnel, and R2/D1 evolution checklist.
- `config/retention.toml`: retention policy for rebuildable runtime artifacts.
- `scripts/cleanup_retention.py`: dry-run-first cleanup planner; use explicit apply commands only after reviewing the generated plan.
- `docs/refactor_runs/`: run-specific planning and execution records for larger architecture changes.

## Current Design Docs

- `docs/okra_unified_rag_architecture.md`: unified vector RAG architecture for Copilot Q&A and future today-analysis retrieval.
- `docs/cloud_migration_plan.md`: current cloud-backend upgrade guide and TODO list.
- `docs/refactor_runs/2026-05-agent-memory-refactor/`: current agent, action-ticket, memory layering, LangGraph, strategy-skill, schema, hard-constraint, and phase-checklist refactor plan.

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
3. `docs/cloud_migration_plan.md`
4. `docs/refactor_runs/2026-05-agent-memory-refactor/accepted_plan_index.md`
5. `docs/refactor_runs/2026-05-agent-memory-refactor/06_execution_technical_plan.md`
6. `docs/refactor_runs/2026-05-agent-memory-refactor/hard_constraints_inventory.md`
7. `docs/refactor_runs/2026-05-agent-memory-refactor/11_review_refinement_and_vertical_slice.md`
8. `docs/refactor_runs/2026-05-agent-memory-refactor/phase_checklists/phase_0_5_golden_vertical_slice.md`
9. `docs/refactor_runs/2026-05-agent-memory-refactor/phase_checklists/phase_1_action_ticket_shadow.md`
10. `docs/okra_unified_rag_architecture.md`
