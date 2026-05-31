# OKRA Long-Memory Investment Workbench

OKRA is a local-first personal fund research, review, long-memory, and real-position synchronization system. It is organized around two canonical product loops:

- `today_analysis`: run the full same-day research and advice chain for one trading day.
- `long_memory`: promote validated observations into durable memory without contaminating unrelated learning domains.

> Disclaimer: OKRA is a personal research tool. It does not provide financial advice. Agent output, memory records, reviews, and strategy summaries are decision-support material only.

## Current Capabilities

- **React + Tauri desktop workbench** for Today, Portfolio, Actual Operations, Research, Realtime, Review/Memory, and System views.
- **Local Python API backend** in `app/web_api.py`, serving snapshot data, page-specific workbench payloads, execution sync APIs, fund detail APIs, and runtime task triggers.
- **Canonical today-analysis route** in `scripts/run_today_analysis.py`, backed by `scripts/today_orchestrator.py`, with runtime state written into `db/daily_workspace/YYYY-MM-DD/`.
- **Canonical committee research chain** that aggregates analyst outputs into `db/agent_outputs/<date>/aggregate.json`, then produces committee-oriented advice artifacts and validated advice.
- **Validated advice flow** under `db/validated_advice/`, used as the trusted downstream source for review, reporting, and long-memory promotion.
- **Actual operation and real-position sync** for manual buy/sell/conversion records and Alipay position screenshot reconciliation.
- **Strict execution boundary**: real trades affect execution memory and real portfolio state, but do not relabel fund-profile learning, market-regime learning, or system advice win rate.
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
- `db/execution_sync/actual_trades/` can feed `execution_memory` only.
- Real execution does not change whether the system's own advice was correct.

### 2. Today Analysis Loop

Unified entry point:

```powershell
python scripts/run_today_analysis.py --date YYYY-MM-DD
```

What the canonical route does:

1. Preflight checks for environment and data sources.
2. Update pending real-trade confirmations.
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

### 4. Actual Operations and Real-Position Sync

The Actual Operations page maintains real portfolio state:

- Manual `buy`, `sell`, and grouped `conversion` records.
- Buy orders can remain pending before confirmation and do not immediately increase confirmed units.
- Sell orders follow confirmation and settlement lifecycle rules.
- Conversions are modeled as one grouped conversion order via a shared `conversion_id`, not unrelated buy/sell rows.
- Alipay position screenshots are parsed into a preview first, then applied by user confirmation.

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

Record an actual trade:

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

- **Today**: today-analysis result, validated advice, committee trace, key long memories, and runtime status.
- **Portfolio**: real portfolio state, allocation, return metrics, and fund detail entry points.
- **Actual Operations**: buy/sell/conversion records, screenshot import, preview reconciliation, and pending confirmations.
- **Research**: multi-agent and committee artifacts for the selected day.
- **Realtime**: estimated NAV, daily return change, and intraday proxy views.
- **Review / Memory**: review outcomes, long-memory candidates, approvals, and execution memory traces.
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

- Portfolio state, trades, reviews, and long memory are stored locally by default.
- Execution sync, screenshot reconciliation, and memory artifacts are written into repo-local storage.
- Embeddings are optional and should be treated as a rebuildable index layer, not the source of truth.
- Screenshot reconciliation remains preview-first and does not overwrite real positions until the user confirms.
