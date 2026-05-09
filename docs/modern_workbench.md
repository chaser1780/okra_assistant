# OKRA Modern Workbench

The current workbench is a React + Tauri desktop UI on top of the local Python backend in `app/web_api.py`.

## Start

```powershell
.\run_desktop_app.ps1
```

The launcher is the current user-facing entrypoint. It:

- resolves the Python interpreter from `OKRA_PYTHON_EXE`, `project.toml`, `python`, or `py -3`
- starts `app/web_api.py --home F:\okra_assistant`
- builds or reuses the Tauri executable when Cargo is available
- falls back to the React dev workbench at `http://127.0.0.1:5173` when Cargo is unavailable

Primary local API:

- `http://127.0.0.1:8765`

## Frontend

```powershell
cd F:\okra_assistant\frontend
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
cd F:\okra_assistant\frontend
npm run build
npm run tauri:check
npm run tauri -- build --no-bundle
```

## Backend API

Direct start:

```powershell
python -B -X utf8 F:\okra_assistant\app\web_api.py --home F:\okra_assistant
```

Current workbench page endpoints:

- `GET /api/workbench/shell?date=YYYY-MM-DD`
- `GET /api/workbench/today?date=YYYY-MM-DD`
- `GET /api/workbench/portfolio?date=YYYY-MM-DD`
- `GET /api/workbench/execution?date=YYYY-MM-DD`
- `GET /api/workbench/research?date=YYYY-MM-DD`
- `GET /api/workbench/realtime?date=YYYY-MM-DD`
- `GET /api/workbench/review?date=YYYY-MM-DD`
- `GET /api/workbench/system?date=YYYY-MM-DD`
- `GET /api/fund/<fund_code>?date=YYYY-MM-DD`

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
