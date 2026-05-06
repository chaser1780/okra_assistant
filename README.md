# OKRA Long-Memory Investment Workbench

OKRA is a local-first personal fund research, review, long-memory, and real-position synchronization system. It is designed around two product loops: continuously learning from system-generated investment decisions, and showing a daily first-open investment workbench when the desktop app starts.

> Disclaimer: OKRA is a personal research tool. It does not provide financial advice. Agent output, memory records, reviews, and strategy summaries should be treated as decision-support material only.

## Current Capabilities

- **Tauri + React + TypeScript desktop workbench** for Today, Portfolio, Actual Operations, Research, Realtime, Long Memory, and System views.
- **Local Python API backend** in `app/web_api.py`, aggregating local JSON/SQLite data, script status, agent context, and UI-ready payloads.
- **Daily first-open loop** that checks state, updates pending confirmations, refreshes market/fund data, runs due reviews, updates long memory, and builds the daily brief.
- **Long-memory loop** for fund profiles, market regimes, execution discipline, portfolio policies, and user-approved strategy rules.
- **Actual operation and real-position sync** for Alipay manual buy/sell/conversion records and Alipay position screenshot imports.
- **Strict learning boundary**: fund profiles and advice accuracy are learned from system advice and system reviews only; real trades only affect execution memory, execution deviation, and real portfolio state.
- **Multi-agent research pipeline** with structured analyst, risk, portfolio, review, and committee-style artifacts.
- **Local-first storage** under `db/`, `config/`, `reports/`, and related folders for auditability, replay, and backup.

## Product Loops

### 1. Long-Memory Loop

The long-memory loop learns and stores:

- Long-term behavior patterns for funds in the portfolio.
- Historical success and failure patterns of system-generated advice.
- Market and style regimes such as QDII, bonds, cash, growth, dividend, US equities, Hong Kong equities, and sector rotations.
- Execution rules around QDII confirmation dates, redemption settlement, conversions, fees, and DCA timing.
- Strategy rules that require user confirmation before becoming permanent.

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

### 2. Daily First-Open Loop

Unified entry point:

```powershell
python scripts/run_daily_first_open.py --date YYYY-MM-DD
```

The loop performs:

1. Environment and data-source preflight.
2. Pending real-trade confirmation updates.
3. Fund NAV, estimated NAV, proxy index, news, and portfolio state refresh.
4. Due reviews for previous system advice.
5. Long-memory updates.
6. Today analysis with relevant long-memory context.
7. Daily brief, decision summary, blocked actions, allowed actions, and watch list.

Daily workspace output:

```text
db/daily_workspace/YYYY-MM-DD/
  preflight.json
  execution_sync.json
  due_reviews.json
  memory_updates.json
  today_analysis.json
  today_decision.json
  daily_brief.md
```

### 3. Actual Operations and Real-Position Sync

The Actual Operations page maintains the real portfolio state:

- Manual **buy / sell / conversion** records.
- Buy orders remain pending before confirmation and do not immediately increase confirmed units.
- Sell orders follow confirmation and settlement lifecycle rules.
- Conversions are recorded as one grouped conversion order instead of unrelated buy/sell rows.
- Alipay position screenshots can be recognized and then applied in two modes:
  - **Update**: update funds detected in the screenshot and keep missing current holdings unchanged.
  - **Replace all**: make the real portfolio match the screenshot; current holdings missing from the screenshot are zeroed.

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
db/trade_journal/
db/execution_status/
db/portfolio_state/current.json
db/portfolio_state/snapshots/
```

## Repository Layout

```text
F:\okra_assistant
├─ app/                  Local API, state aggregation, desktop backend entry points
├─ frontend/             Tauri + React + TypeScript workbench
├─ scripts/              Data sync, daily loop, review, long memory, actual operations
├─ config/               Portfolio, strategy, model, and agent configuration
├─ db/                   Local structured data, long memory, real positions, review results
├─ reports/              Human-readable daily reports, reviews, and learning reports
├─ docs/                 Design docs, migration notes, development backlog
├─ assets/               Report templates and static assets
├─ references/           Rules, source priority, and scoring references
├─ logs/                 Runtime logs
└─ README.md             Project overview
```

## Common Entrypoints

Start the desktop workbench:

```powershell
powershell -ExecutionPolicy Bypass -File "F:\okra_assistant\run_desktop_app.ps1"
```

Run the daily first-open loop:

```powershell
python "F:\okra_assistant\scripts\run_daily_first_open.py" --date 2026-05-06
```

Run realtime refresh:

```powershell
python "F:\okra_assistant\scripts\run_realtime_pipeline.py"
```

Record an actual trade:

```powershell
python "F:\okra_assistant\scripts\record_actual_trade.py" --help
```

Parse Alipay position screenshots:

```powershell
python "F:\okra_assistant\scripts\parse_alipay_position_screenshot.py" --help
```

Refresh pending confirmations:

```powershell
python "F:\okra_assistant\scripts\update_pending_confirmations.py"
```

## Desktop Pages

- **Today**: daily first-open result, current view, blocked actions, key long memories.
- **Portfolio**: real portfolio state, allocation, return metrics, fund detail entry points.
- **Actual Operations**: buy/sell/conversion records, Alipay screenshot import, pending confirmations.
- **Research**: research pipeline and multi-agent artifacts.
- **Realtime**: estimated NAV, daily returns, and applied intraday change.
- **Memory**: fund profiles, market regimes, execution discipline, pending strategy rules.
- **System**: data health, task status, logs, and startup-loop state.

## Data Boundary

OKRA intentionally separates three kinds of data:

- **System advice and system reviews** drive fund profiles, market-regime learning, and advice accuracy.
- **Real trades and real positions** drive current portfolio state, cash constraints, sellable units, and execution checks.
- **Execution memory** learns confirmation dates, fees, settlement, conversions, delayed execution, and manual deviations.

Real operations can change the app's current portfolio and execution discipline, but they do not change the label for whether the system's own advice was correct.

## Development and Verification

Build the frontend:

```powershell
cd "F:\okra_assistant\frontend"
npm run build
```

Build the Tauri release executable:

```powershell
cd "F:\okra_assistant\frontend"
npm run tauri -- build --no-bundle
```

Run key tests:

```powershell
cd "F:\okra_assistant"
python -B -X utf8 -m unittest tests.test_execution_sync tests.test_portfolio_screenshot_sync tests.test_long_memory tests.test_web_api_long_memory
```

## Privacy and Local-First Design

- Portfolio state, trades, reviews, and long memory are stored locally by default.
- Embeddings are off by default. If API embeddings are enabled later, they are only a rebuildable index layer.
- Alipay screenshots are saved locally and converted into a preview first; they do not overwrite real positions until the user confirms.

