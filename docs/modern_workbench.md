# OKRA Modern Workbench

The current workbench is a React + Tauri desktop UI on top of the local Python backend in `app/web_api.py`.

## Start

```powershell
.\run_desktop_app.ps1
```

The launcher is the current user-facing entrypoint. It:

- resolves the Python interpreter from `OKRA_PYTHON_EXE`, `project.toml`, `python`, or `py -3`
- starts `app/web_api.py --home <project-root>`
- builds or reuses the Tauri executable when Cargo is available
- falls back to the React dev workbench at `http://127.0.0.1:5173` when Cargo is unavailable

Primary local API:

- `http://127.0.0.1:8765`

## Frontend

```powershell
cd .\frontend
npm install
npm run dev
```

Current frontend entry facts:

- routes live in `frontend/src/app/routes.tsx`
- page loading uses page-level `React.lazy` + `Suspense`
- workbench fetch/query entrypoints live in `frontend/src/lib/workbenchApi.ts` and `frontend/src/lib/workbenchQuery.ts`
- Tauri configuration lives under `frontend/src-tauri`

Useful checks:

```powershell
cd .\frontend
npm run build
npm run tauri:check
npm run tauri -- build --no-bundle
```

## Backend API

Direct start:

```powershell
python -B -X utf8 .\app\web_api.py --home .
```

## Current API Contract Notes

Current backend entrypoint is `app/web_api.py`, started through
`ContractRequestHandler`. The current contract handler wraps most page and
command responses in an API envelope:

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "meta": {
    "page": "today",
    "selected_date": "2026-05-24",
    "generated_at": "2026-05-24T22:00:00+08:00",
    "version": "v1"
  }
}
```

Error responses use the same envelope:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "error_code": "bad_request",
    "error_message": "...",
    "retryable": false,
    "details": {}
  },
  "meta": {
    "page": null,
    "selected_date": null,
    "generated_at": "2026-05-24T22:00:00+08:00",
    "version": "v1"
  }
}
```

Current workbench page endpoints:

- `GET /api/shell?date=YYYY-MM-DD`
- `GET /api/today?date=YYYY-MM-DD`
- `GET /api/portfolio?date=YYYY-MM-DD`
- `GET /api/execution?date=YYYY-MM-DD`
- `GET /api/research?date=YYYY-MM-DD`
- `GET /api/intelligence?date=YYYY-MM-DD`
- `GET /api/realtime?date=YYYY-MM-DD`
- `GET /api/review?date=YYYY-MM-DD`
- `GET /api/system?date=YYYY-MM-DD`
- `GET /api/fund/<fund_code>?date=YYYY-MM-DD&range=since_inception`
- `GET /api/dates`
- `GET /api/health`

Compatibility aliases:

- `GET /api/workbench/shell?date=YYYY-MM-DD`
- `GET /api/workbench/today?date=YYYY-MM-DD`
- `GET /api/workbench/portfolio?date=YYYY-MM-DD`
- `GET /api/workbench/execution?date=YYYY-MM-DD`
- `GET /api/workbench/research?date=YYYY-MM-DD`
- `GET /api/workbench/intelligence?date=YYYY-MM-DD`
- `GET /api/workbench/realtime?date=YYYY-MM-DD`
- `GET /api/workbench/review?date=YYYY-MM-DD`
- `GET /api/workbench/system?date=YYYY-MM-DD`

`GET /api/snapshot` intentionally remains a legacy raw payload and is not
envelope-wrapped.

Operational endpoints:

- `POST /api/run/daily`
- `POST /api/run/realtime`
- `GET /api/execution-sync`
- `POST /api/execution-sync/trade`
- `POST /api/execution-sync/conversion`
- `POST /api/execution-sync/alipay-screenshot/parse`
- `POST /api/execution-sync/reconcile/preview`
- `POST /api/execution-sync/reconcile/apply`
- `POST /api/execution-sync/confirmation/update`
- `POST /api/long-memory/action`
- `POST /api/copilot/explain`
- `POST /api/open-url`

RAG admin/debug endpoints:

- `GET /api/rag/status`
- `GET /api/rag/trace?id=<traceId>`
- `POST /api/rag/search`
- `POST /api/rag/reindex`
- `POST /api/rag/eval`
- `POST /api/rag/maintenance`

### DTO And Frontend Validation

Backend API-facing DTOs live in `app/api_contracts.py`. They use Pydantic
models with `extra="allow"`, so page payloads can evolve without breaking older
clients. Frontend runtime schemas live in `frontend/src/lib/schemas.ts` and use
`.passthrough()` for page payloads. Stable top-level page keys are enforced,
while nested analytical artifacts remain flexible.

Current page DTO top-level keys:

- `ShellPageDto`: `dates`, `selectedDate`, `chainStatus`,
  `statusBadgeState`, `statusBarText`, `summary`
- `TodayPageDto`: `selectedDate`, `summary`, `todayAnalysis`, `dashboard`,
  `dailyFirstOpen`, `portfolio`, `longMemory`, `system`
- `PortfolioPageDto`: `selectedDate`, `summary`, `portfolio`
- `ExecutionPageDto`: `selectedDate`, `executionSync`, `portfolio`, `system`
- `ResearchPageDto`: `selectedDate`, `summary`, `research`
- `IntelligencePageDto`: `selectedDate`, `intelligence`
- `RealtimePageDto`: `selectedDate`, `summary`, `realtime`
- `ReviewPageDto`: `selectedDate`, `summary`, `review`, `longMemory`
- `SystemPageDto`: `selectedDate`, `summary`, `system`, `shell`
- `FundDetailDto`: `fundCode`, `fundName`, `selectedDate`, `range`,
  `portfolio`, `realtime`, `research`, `analysisDetail`, `history`,
  `performance`, `tradeMarkers`, `longMemory`, `system`

Frontend page queries should use `frontend/src/lib/workbenchApi.ts` and
`frontend/src/lib/workbenchQuery.ts`, not raw `request()` calls. `request()`
still supports both envelope and legacy raw JSON so `/api/snapshot` and older
routes remain usable.

### Missing Files And Empty Data

The workbench prefers empty payloads over hard failure when local artifacts are
missing:

- `PageService.read_json_file()` returns `{}` when a JSON file is missing,
  unreadable, or invalid.
- Execution sync returns empty arrays and zero counts when execution files do
  not exist.
- Intelligence falls back from `raw/news/<date>.json` and `llm_context` to empty
  metrics/lists.
- Today analysis system fields expose existence flags such as
  `todayDecisionExists`, `todayAnalysisExists`, `todayAnalysisMetaExists`,
  `memoryCycleExists`, plus `autoRunNeeded`.
- RAG runtime errors are contained as `system.ragRuntime.statusError`.
- Frontend pages should render explicit empty states instead of treating empty
  lists as API failure.

### Error Behavior

- Unknown routes return `404 not_found`.
- Invalid JSON returns `400 invalid_json`.
- Validation or missing required fields return `400 bad_request`.
- Duplicate today-analysis runs return `409 already_running` with `runId`,
  `reportDate`, `startedAt`, `currentStep`, and `currentAgent`.
- Untrusted POST origins return `403 forbidden_origin`.
- Unexpected exceptions return `500 internal_error`.

CORS allows local React/Tauri origins including `127.0.0.1`, `localhost`, and
`tauri.localhost`.

### Compatibility Risks

- Documentation and UI work must include `/api/intelligence`; it is part of the
  current Workbench page contract.
- `/api/workbench/*` routes are compatibility aliases. New frontend code should
  prefer short `/api/<page>` routes.
- `/api/snapshot` is deliberately not envelope-wrapped; changing it would break
  fallback and older consumers.
- `summary` exists in several backend DTOs but is not required by every frontend
  page type. Additive use is safe, but frontend should not require `summary` on
  pages where schemas do not currently enforce it.
- `ExecutionPageDto` includes `system`, but current frontend
  `ExecutionPagePayload` and schema only require `selectedDate`,
  `executionSync`, and `portfolio`. This should remain additive unless the
  execution page starts rendering runtime diagnostics.
- `app/api_contracts.py` request DTOs currently validate only execution
  trade/conversion command payloads. Other command endpoints still accept
  flexible dictionaries.
- RAG config currently has `rag.enabled=true` and `rag.agent_default.enabled=true`,
  while `rag.agent_shadow.enabled=false`. Shadow review UI must not infer that
  agent shadow is active from global RAG alone.

## Shadow Review Contract

The future old-versus-new action-ticket comparison UI is specified in
`docs/refactor_runs/2026-05-agent-memory-refactor/api_contracts_shadow_review.md`.
It is read-only and non-executable by design.

## Runtime and Today Analysis

The workbench is now coupled to the canonical `today_analysis` runtime instead of older ad hoc first-open wording.

Key runtime facts:

- `POST /api/run/daily` triggers `run_today_analysis.py`
- duplicate same-day runs return `409 already_running`
- runtime state comes from `db/daily_workspace/<date>/today_analysis_runtime.json`
- page payloads also surface `today_analysis_meta.json`, `today_analysis.json`, `today_decision.json`, and `memory_cycle.json`

Practical UI implication:

- Today page shows validated advice, committee trace, and run status together
- System page surfaces the same runtime state for diagnostics
- auto-run and polling behavior in the React shell should treat `today_analysis_runtime.json` as the source of truth

## Product Boundaries

The workbench intentionally separates:

- research and validated advice
- execution sync and real-position state
- long-memory actions and approvals

Real operations can update:

- real portfolio state
- execution constraints
- execution memory

Real operations must not directly update:

- fund profile learning
- market regime learning
- system advice accuracy labels
