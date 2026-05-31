# Phase 7 Checklist: Workbench Review Surface

Status: implemented as a partial read-only Workbench surface. Remaining gates
are promotion-level only: broader outcome examples, official-compatible advice
evidence, inactive fallback switch, and explicit promotion.

## Goal

Expose old-versus-new shadow results to the user in a read-only Workbench
surface. The UI helps review and compare; it must not execute trades or mutate
learning state.

Before the full UI, provide CLI/Markdown review so Phase 1-4 outputs can be
reviewed early.

## Allowed Write Set

- `app/api_contracts.py`
- `app/web_api.py`
- `app/web_api_services.py`
- optional `app/shadow_review_service.py`
- `frontend/src/lib/schemas.ts`
- `frontend/src/lib/workbenchApi.ts`
- `frontend/src/lib/workbenchQuery.ts`
- `scripts/render_refactor_review.py`
- `db/refactor_reviews/<report_date>.md`
- a new read-only frontend page or a read-only panel in Today/Review
- `tests/test_web_api_action_tickets.py` or equivalent

## Forbidden Write Set

- execution sync mutation endpoints
- portfolio state
- official advice mutation
- long-memory approval/promotion
- policy/skill promotion
- raw shadow artifact schema changes unless coordinated with earlier phases

## Inputs

- `api_contracts_shadow_review.md`
- action tickets
- action debates
- retrieval packs
- outcome events
- adaptive policies
- strategy skill registry
- current Workbench API envelope behavior

## Outputs

- `GET /api/shadow-review?date=YYYY-MM-DD`
- compatibility alias:
  `GET /api/workbench/shadow-review?date=YYYY-MM-DD`
- optional `GET /api/shadow-review/<review_id>?date=YYYY-MM-DD`
- frontend schema and empty states
- read-only comparison UI

## Implementation Steps

1. Add DTOs only after shadow artifact fields are stable.
2. Add CLI/Markdown renderer from stable shadow artifacts.
3. Add service that normalizes artifacts into display DTOs.
4. Return 200 with `status=missing/not_run/partial` for valid route but missing
   artifacts.
5. Add `nonExecutable=true` and `displayOnly=true` at page and item levels.
6. Render old official advice beside new shadow ticket/debate information.
7. Show hard guardrails, soft policies, skill refs, outcome status, and missing
   artifact notes.
8. Do not add execution buttons or apply actions.

## Required Tests

- missing artifacts returns 200 with empty state
- Markdown review renders for missing, partial, and ready states
- invalid date returns 400
- invalid JSON produces degraded/failed status without stack trace
- ready payload includes non-executable markers
- boundary-invalid shadow artifacts are rejected as failed/degraded rather than
  silently displayed as non-executable
- same-fund multi-action dates keep action-level review rows
- DTO preserves existing page contracts
- frontend schema parses missing, partial, degraded, ready states
- no UI path calls execution-sync or long-memory action endpoints

Suggested commands:

```powershell
python -B -X utf8 -m py_compile app\api_contracts.py app\web_api.py app\web_api_services.py
python -B -X utf8 -m unittest tests.test_web_api_action_tickets tests.test_web_api_rag_admin tests.test_web_api_rag_copilot
cd frontend
npm run build
npm run tauri:check
```

## Manual Verification

- Load a date with no shadow artifacts and confirm a clean empty state.
- Read generated Markdown review before opening UI.
- Load a date with artifacts and confirm old/new comparison is readable.
- Confirm soft policy, skill, and outcome summaries are visible in each review
  card when the artifacts contain them.
- Confirm all shadow labels clearly say non-executable/display-only.
- Confirm `/api/snapshot` still returns legacy raw payload.

## Rollback Notes

Remove the new route/page or disable it behind a feature flag. Since it is
read-only, no investment state rollback should be needed.

## Promotion Gate

Phase 8 can begin only after:

- user can inspect old and new outputs for real dates;
- missing/degraded states are understandable;
- no execution mutation path exists from shadow review;
- downstream consumers of current official outputs are mapped.
