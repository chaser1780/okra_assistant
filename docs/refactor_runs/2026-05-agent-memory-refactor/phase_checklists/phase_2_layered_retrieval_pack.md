# Phase 2 Checklist: Layered Retrieval Pack

Status: design ready, implementation should follow Phase 1 schema stability.

## Goal

Build a structured context contract for the new debate chain. The graph should
consume a layered retrieval pack, not scattered JSON files or flat RAG hits.

## Allowed Write Set

- `scripts/layered_context_models.py`
- `scripts/build_layered_retrieval_pack.py`
- `tests/test_layered_retrieval_pack.py`
- `db/retrieval_packs/<report_date>.json`
- optional RAG trace artifacts when current RAG retriever is called

## Forbidden Write Set

- official advice outputs
- portfolio state
- execution sync
- long-memory records
- strategy policies/skills
- LangGraph orchestration code beyond minimal consumers

## Inputs

- action tickets from Phase 1
- Phase 0.5 golden slice fixtures and expected output
- current structured facts from portfolio state and current context
- existing RAG modules and active manifests
- long-memory records through approved source adapters
- validated advice and committee bundles as decision facts
- `schema_examples/retrieval_pack.example.json`
- `docs/okra_unified_rag_architecture.md` implementation-status section

## Outputs

- `db/retrieval_packs/<report_date>.json`
- pack-level trace metadata
- explicit missing/stale/conflicted data list

## Pack Sections

Required sections:

- `canonical_facts`
- `derived_signals`
- `decision_history`
- `outcome_history`
- `similar_cases`
- `anti_patterns`
- `adaptive_policies`
- `strategy_skill_candidates`
- `long_text_evidence`
- `missing_data`
- `rag_trace_refs`
- `visibility`

## Implementation Steps

1. Define dataclasses for pack root and section items.
2. Reuse current RAG query planner/retriever only for non-canonical evidence.
3. Pull portfolio values, cash, NAV, and current position facts from structured
   artifacts first.
4. Include RAG hits only in similar-case, anti-pattern, or long-text evidence
   sections.
5. Attach `source_path`, `source_record_id`, `as_of_date`, and
   `available_from` to every item.
6. Filter or mark execution-only data with `visibility.include_execution`.
7. Add no-future validation at pack build time.
8. Write one pack per report date, optionally with per-fund subsections.

## Required Tests

- no future `available_from`
- fund-specific pack does not use wrong fund as primary evidence
- canonical facts come from structured sources, not RAG text
- archived/rejected memory excluded unless review profile explicitly requests
  it
- execution-only data excluded by default
- missing/stale/conflicted data is explicit
- RAG failure falls back to empty evidence with `fallback_used`, not exception
- retrieval pack round-trip is stable
- `trace_completeness_rate` is computed

Suggested commands:

```powershell
python -B -X utf8 -m py_compile scripts\layered_context_models.py scripts\build_layered_retrieval_pack.py
python -B -X utf8 -m unittest tests.test_layered_retrieval_pack
python -B -X utf8 -m unittest discover -s tests -p "test_rag_*.py"
```

## Manual Verification

- Inspect one generated pack and confirm current facts are compact and sourced.
- Confirm RAG trace ids exist when RAG is used.
- Confirm source refs open to real local files.
- Confirm missing data is not silently empty.
- Confirm the same golden slice can produce a pack without broad pipeline
  integration.

## Rollback Notes

Delete `db/retrieval_packs/<date>.json`. Current daily analysis should remain
unchanged.

## Promotion Gate

Phase 3 can use retrieval packs only after:

- no-future and fund-match tests pass;
- canonical facts are separated from RAG evidence;
- execution visibility behavior is tested;
- RAG current implementation status and config defaults are documented.
