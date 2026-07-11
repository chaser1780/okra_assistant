# OKRA Modern Workbench

The current workbench is a React + Tauri desktop UI on top of the Python backend in `app/web_api.py`. Local mode remains the default; remote mode connects the same desktop UI to an explicitly configured cloud API.

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

Remote mode never starts the local Python backend:

```powershell
$env:OKRA_REMOTE_API_BASE="https://okra.example.com"
.\run_desktop_app_remote.ps1
```

`OKRA_DESKTOP_MODE` defaults to `local`. In remote mode the API base comes from
`OKRA_REMOTE_API_BASE` or `VITE_OKRA_API_BASE`; the System page shows the mode,
sanitized API target, and configuration source. The frontend example is
`frontend/.env.remote.example`. Do not put API tokens in Vite environment
files because Vite values are compiled into browser assets.

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

The backend remains loopback-only. Its default bind address is `127.0.0.1`, and
startup rejects non-loopback values such as `0.0.0.0` or a LAN address. Cloud
access must terminate through a local reverse proxy or Cloudflare Tunnel; the
API port itself is never exposed publicly.

When `OKRA_PUBLIC_BASE_URL`, `OKRA_API_TOKEN`, or
`OKRA_TRUST_CLOUDFLARE_ACCESS` enables remote protection:

- `OKRA_ALLOWED_ORIGINS` adds exact cloud origins; wildcards are ignored.
- `/api/health` stays public and omits the local workspace path.
- page reads accept a trusted Cloudflare Access identity or bearer token.
- mutations and RAG admin/debug endpoints require the configured stronger
  checks; when both Access trust and a token are configured, both are required.
- `OKRA_DISABLE_REMOTE_MUTATIONS=1` rejects every remote mutation.
- mutation authorization decisions are appended to
  `logs/cloud/mutation_audit.jsonl` without payloads or credentials.
- remote error envelopes redact local paths, tokens, and internal 500 details.

`OKRA_TRUST_CLOUDFLARE_ACCESS=1` is valid only when the API remains behind the
Tunnel/Access boundary and has no direct public inbound route. Deployment
templates and dry-run-first scripts live under `deploy/`.

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

Reconciliation is a two-step server-bound contract:

1. Preview writes a server-side artifact containing `reconcile_id`,
   `preview_sha256`, and `portfolio_state_sha256`.
2. Apply accepts only `reconcileId`, `previewSha256`,
   `expectedPortfolioStateSha256`, `dropMissing`, and optional confirmation.
3. Apply reloads the saved preview, verifies its digest, rejects a changed
   portfolio state, and records an apply-request digest for idempotent replay.

The client must never submit an arbitrary preview object as the apply source of
truth.

RAG admin/debug endpoints:

- `GET /api/rag/status`
- `GET /api/rag/trace?id=<traceId>`
- `POST /api/rag/search`
- `POST /api/rag/reindex`
- `POST /api/rag/eval`
- `POST /api/rag/maintenance`

### Current RAG Mode

RAG is enabled for Copilot and default agent retrieval with legacy fallback.
The production retrieval path currently ranks candidates with lexical text
scoring after active-manifest and safety filters. It is therefore accurate to
describe current RAG as operational lexical retrieval, not production vector
retrieval.

Vector capability remains gated:

- `rag.embedding.enabled=false`
- `rag.embedding.dry_run=true`
- `rag.vector_store.backend="sqlite_mock"`
- FAISS and Chroma are not enabled
- profile-evidence and agent-shadow modes remain disabled by default
- execution evidence remains excluded from ordinary retrieval

Embedding/vector code and tests exist, but enabling a real backend requires a
separate measured gray release. UI labels and operational reports must not
claim semantic/vector retrieval while these defaults remain in place.

### Replay And Learning Trust

Historical replay and derived learning are fail-closed:

- `config/historical_replay_trust.json` is the source-controlled trust list.
- Normal replay accepts only `trusted` dates; `structural_only` requires an
  explicit diagnostic opt-in and can never write learning.
- Replay audits are written under `db/replay_audits/`.
- The promoted chain attempts to capture immutable exact-byte inputs under
  `db/replay_snapshots/<report-date>__<cutoff-hash>/`. Capture failure is recorded and remains
  ineligible; a successful generated manifest candidate still remains
  `blocked` and `learning_eligible=false` until separately reviewed.
- Learning lineage audits are written under `db/learning_trust_audits/` and
  classify outcomes, policy events, policies, and skills as `trusted`,
  `legacy_untrusted`, or `blocked`.
- Strategy skills remain visible for diagnosis, but only `trusted` skills may
  produce usage candidates. Long-memory learning-derived writes use the same
  fail-closed trust requirement.

The Review page exposes the selected date's manifest mode, learning
eligibility, replay audit path, and latest learning audit summary. Missing
manifest or audit evidence renders as blocked; the UI does not promote trust.

### DTO And Frontend Validation

Backend API-facing DTOs live in `app/api_contracts.py`. They use Pydantic
models. Read/page contracts retain `extra="allow"` so analytical payloads can
evolve without breaking older clients. Mutation request DTOs inherit
`MutationRequestModel` with `extra="forbid"`; unknown top-level command fields
fail validation instead of being silently accepted. Frontend runtime schemas
live in `frontend/src/lib/schemas.ts` and use `.passthrough()` for page payloads.
Stable top-level page keys are enforced, while nested analytical artifacts
remain flexible.

Strict mutation DTO coverage includes run commands, execution trade and
conversion, screenshot parsing, reconciliation preview/apply, confirmation
updates, long-memory actions, RAG search/reindex/eval/maintenance, and
open-url. Copilot explain is query-like and still accepts its flexible request
shape. Some DTOs intentionally retain flexible nested analytical rows, but
their top-level command envelope is strict.

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
- Non-loopback bind targets are rejected at startup before the HTTP server is
  created.
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
- Mutation DTO strictness is top-level. Reconciliation preview rows and other
  nested analytical structures remain flexible where their source formats are
  intentionally heterogeneous.
- `rag.enabled=true` and `rag.agent_default.enabled=true` mean lexical RAG is
  live. They do not mean embedding, a production vector store, profile
  evidence, or agent shadow is active.
- A captured replay snapshot is evidence, not trust approval. Generated
  candidates remain blocked until the source-controlled manifest is explicitly
  updated after review.

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

Learning-derived memory, policy, and strategy-skill consumers additionally
require trusted replay lineage. Historical or structurally replayable evidence
may remain visible for audit, but it must not influence learning or skill usage
without a `trusted` learning audit.
