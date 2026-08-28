# OKRA Long-Memory Investment Workbench

OKRA is a local-first personal fund research, review, long-memory, user-simulation, and strategy-experiment system. It is organized around two canonical product loops:

- `today_analysis`: run the full same-day research and advice chain for one trading day.
- `long_memory`: promote validated observations into durable memory without contaminating unrelated learning domains.

> Disclaimer: OKRA is a personal research tool. It does not provide financial advice. Agent output, memory records, reviews, and strategy summaries are decision-support material only.

## Current Capabilities

- **React + Tauri desktop workbench** for the Portfolio Research Terminal, user simulation, Research, Realtime Observation, Review/Memory, strategy experiments, and System views.
- **Local Python API backend** in `app/web_api.py`, serving snapshot data, page-specific workbench payloads, execution sync APIs, fund detail APIs, and runtime task triggers.
- **Canonical today-analysis route** in `scripts/run_today_analysis.py`, backed by `scripts/today_orchestrator.py`, with runtime state written into `db/daily_workspace/YYYY-MM-DD/`.
- **Canonical committee research chain** that aggregates analyst outputs into `db/agent_outputs/<date>/aggregate.json`, then produces committee-oriented advice artifacts and validated advice.
- **Validated advice flow** under `db/validated_advice/`, used as the trusted downstream source for review, reporting, and long-memory promotion.
- **Two simulation tracks**: user simulation follows manual actions, configured DCA, and screenshot-confirmed portfolio snapshots; strategy experiments hold independent hypothetical portfolios.
- **Strict simulation boundary**: strategy experiments cannot mutate the user simulation portfolio; user operations and experiments carry separate memory provenance and do not relabel system advice quality.
- **Local-first storage** under `db/`, `config/`, `reports/`, `logs/`, and related folders for auditability, replay, and backup.

## Product Loops

### 1. Long-Memory Loop

The long-memory loop stores and promotes:

- Fund profile patterns learned from system advice and system reviews.
- Market and style regime observations.
- Execution discipline such as confirmation timing, conversions, fees, settlement, and manual deviation patterns.
- Portfolio policies and candidate strategy rules that may require user approval.

Main local storage:

```text
db/long_memory/
  memory.sqlite
  index.sqlite
  funds/
  market/
  execution/
  portfolio/
  candidates/
  approvals/
  exports/
```

Boundary rules:

- `db/validated_advice/<date>.json` and review outputs can feed fund/profile and market learning.
- `db/execution_sync/actual_trades/` is a compatibility directory for `user_simulation` operations and can feed execution discipline only.
- User simulation and strategy experiments do not change whether the system's own advice was correct.

### 2. Today Analysis Loop

Unified entry point:

```powershell
python scripts/run_today_analysis.py --date YYYY-MM-DD
```

What the canonical route does:

1. Preflight checks for environment and data sources.
2. Refresh user-simulation status and materialize configured same-day simulated DCA when eligible.
3. Refresh NAV, estimate, proxy, news, and portfolio context.
4. Process due reviews for earlier system advice.
5. Refresh long-memory context when eligible.
6. Run the multi-agent research chain and committee aggregation.
7. Generate validated advice, decision artifacts, and the daily brief.

Auto backfill policy:

- When `today_analysis` runs for the current trading day, OKRA only backfills missing trading-day runs within the most recent 3 calendar days.
- Older missing runs require an explicit manual rerun.

Daily workspace output:

```text
db/daily_workspace/YYYY-MM-DD/
  preflight.json
  execution_sync.json
  due_reviews.json
  memory_updates.json
  today_analysis.json
  today_analysis_meta.json
  today_analysis_runtime.json
  today_decision.json
  memory_cycle.json
  daily_brief.md
```

Runtime behavior:

- `today_analysis_runtime.json` records run status, phase, current step, active agent, and run id.
- `POST /api/run/daily` returns `409 already_running` when the same-day route is already active, and the workbench uses that runtime state for polling and resume behavior.

### 3. Canonical Committee and Validated Advice

The current research/advice chain is:

1. Multi-agent analysis writes raw outputs under `db/agent_outputs/<date>/`.
2. Committee synthesis builds a canonical committee summary in `aggregate.json`, including fields such as `bull_case`, `bear_case`, `risk_vetoes`, `manager_decision`, `committee_confidence`, and `decision_source`.
3. Committee-oriented advice is written to `db/committee_advice/<date>.json`.
4. Final validated advice is written to `db/validated_advice/<date>.json`.

Operationally, downstream review, reporting, memory promotion, and the Today page should treat validated advice as the stable advice artifact, while the committee artifact remains the canonical trace of how the decision was formed.

### 4. User Simulation and Strategy Experiments

The user-simulation track maintains the current simulated portfolio:

- Manual `buy`, `sell`, grouped `conversion`, and configured DCA records apply immediately to `user_simulation` after explicit user action or configuration.
- Screenshot imports remain preview-first and update the user-simulation portfolio only after confirmation.
- Strategy experiments have separate hypothetical portfolios under `db/strategy_simulation/`; their actions never mutate `user_simulation`.
- Every experiment-derived memory stores `sourceTrack=strategy_simulation`, `experimentId`, and `formalInfluence=false`.

Main local storage:

```text
db/execution_sync/
  actual_trades/
  position_snapshots/
  pending_confirmations.json
  reconciliation_reports/
  imports/alipay_screenshots/
  imports/parsed/
```

Compatibility writes:

```text
db/portfolio_state/current.json
db/portfolio_state/snapshots/
```

Legacy archives after cutover:

```text
db/legacy/review_memory/
db/legacy/trade_journal/
```

## Repository Layout

```text
.\
+-- app/                  Local API, desktop backend, state aggregation
+-- frontend/             React + TypeScript + Tauri workbench
+-- scripts/              Today-analysis, long-memory, execution sync, reports
+-- config/               Portfolio, strategy, model, and agent configuration
+-- db/                   Local structured data, workspace artifacts, long memory
+-- reports/              Human-readable daily reports and review outputs
+-- docs/                 Active design docs, index, and focused planning notes
+-- assets/               Static assets and templates
+-- references/           Rules, source priority, and scoring references
+-- logs/                 Runtime logs
+-- README.md             Project overview
```

## Common Entrypoints

Start the desktop workbench:

```powershell
powershell -ExecutionPolicy Bypass -File ".\run_desktop_app.ps1"
```

Start the API directly:

```powershell
python -B -X utf8 ".\app\web_api.py" --home "."
```

Run today analysis:

```powershell
python ".\scripts\run_today_analysis.py" --date 2026-05-08
```

Build the Phase 8 official-advice compatibility preview from shadow artifacts:

```powershell
python -B -X utf8 ".\scripts\build_official_advice_compat_preview.py" --date 2026-05-22 --format json
```

This writes only under `db/refactor_shadow_runs/` and does not replace
`db/llm_advice/`, `db/validated_advice/`, ledger, execution sync, portfolio
state, or long memory.

Run long-memory analysis manually:

```powershell
python ".\scripts\run_long_memory_analysis.py" --date 2026-05-08
```

Run realtime refresh:

```powershell
python ".\scripts\run_realtime_monitor.py"
```

Record a user-simulation operation:

```powershell
python ".\scripts\record_actual_trade.py" --help
```

Parse Alipay position screenshots:

```powershell
python ".\scripts\parse_alipay_position_screenshot.py" --help
```

Refresh pending confirmations:

```powershell
python ".\scripts\update_pending_confirmations.py"
```

## Desktop Pages

- **Today**: portfolio research terminal with market facts, data freshness, research conclusions, risk, and simulation context.
- **Portfolio**: user-simulation allocation, guarded performance metrics, risk and fund detail entry points.
- **Simulation Execution**: user-simulation buy/sell/conversion records, configured DCA, screenshot import, and preview reconciliation.
- **Research**: multi-agent and committee artifacts for the selected day.
- **Realtime**: observation-only estimated NAV, daily change, proxy views, freshness, and anomaly signals.
- **Review / Memory**: review outcomes, long-memory candidates, approvals, and source-track provenance.
- **Experiment Review**: read-only shadow artifacts plus interactive strategy-simulation portfolios.
- **System**: data health, logs, task status, and current runtime metadata.
- **Intelligence**: news, related items, sentiment, source health, and regulatory information for the selected date.

## API and Frontend Entrypoints

Workbench frontend:

- React routes live under `frontend/src/app/routes.tsx`.
- The workbench fetch layer lives under `frontend/src/lib/workbenchApi.ts` and `frontend/src/lib/workbenchQuery.ts`.

Primary page APIs:

- `GET /api/workbench/shell?date=YYYY-MM-DD`
- `GET /api/workbench/today?date=YYYY-MM-DD`
- `GET /api/workbench/portfolio?date=YYYY-MM-DD`
- `GET /api/workbench/execution?date=YYYY-MM-DD`
- `GET /api/workbench/research?date=YYYY-MM-DD`
- `GET /api/workbench/intelligence?date=YYYY-MM-DD`
- `GET /api/workbench/realtime?date=YYYY-MM-DD`
- `GET /api/workbench/review?date=YYYY-MM-DD`
- `GET /api/workbench/system?date=YYYY-MM-DD`
- `GET /api/fund/<fund_code>?date=YYYY-MM-DD`

Operational APIs:

- `POST /api/run/daily`
- `POST /api/run/realtime`
- `GET /api/execution-sync`
- `POST /api/execution-sync/trade`
- `POST /api/execution-sync/conversion`
- `POST /api/execution-sync/alipay-screenshot/parse`
- `POST /api/execution-sync/reconcile/preview`
- `POST /api/execution-sync/reconcile/apply`
- `POST /api/execution-sync/confirmation/update`
- `GET /api/strategy-simulation`
- `POST /api/strategy-simulation/experiment`
- `POST /api/strategy-simulation/action`
- `POST /api/long-memory/action`
- `POST /api/copilot/explain`

## Development and Verification

Build the frontend:

```powershell
cd ".\frontend"
npm run build
```

Check the Tauri project:

```powershell
cd ".\frontend"
npm run tauri:check
```

Build the Tauri executable without bundling:

```powershell
cd ".\frontend"
npm run tauri -- build --no-bundle
```

Run targeted backend tests:

```powershell
python -B -X utf8 -m unittest tests.test_execution_sync tests.test_long_memory tests.test_multiagent_and_review tests.test_web_api_long_memory
```

Preview retention cleanup without changing files:

```powershell
python -B -X utf8 scripts\cleanup_retention.py --dry-run --assert-protected --report
```

Retention rules live in `config/retention.toml`. The cleanup script is dry-run by default, writes a local review report under `reports/maintenance/`, and protects long memory, execution sync, portfolio state, validated advice, and decision audit data.

## Privacy and Local-First Design

- Portfolio state, user-simulation operations, strategy experiments, reviews, and long memory are stored locally by default.
- `execution_sync` is retained as a compatibility API/storage name; it does not connect to a broker or represent real trades.
- Embeddings are optional and should be treated as a rebuildable index layer, not the source of truth.
- Screenshot reconciliation remains preview-first and does not overwrite the user-simulation portfolio until the user confirms.
