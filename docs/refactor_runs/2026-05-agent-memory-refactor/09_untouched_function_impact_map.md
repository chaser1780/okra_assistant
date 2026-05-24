# 09 Untouched Function Impact Map

Status: impact boundaries recorded before implementation.

This document lists product areas that are not the primary target of the
agent/memory refactor but can be affected by it. These areas must stay stable
while the new action-ticket and memory-learning chain is built in shadow mode.

## Global Protection Line

Until explicit promotion:

- official `validated_advice` remains the official advice artifact
- portfolio state remains deterministic and local
- execution sync remains the source for real operations
- official NAV/PnL remains deterministic
- Copilot remains an explanation interface
- RAG remains a retrieval component, not a financial fact source
- Workbench shadow views remain read-only

## Impact Matrix

| Function area | Current boundary | Possible impact | Must remain unchanged | Regression focus |
|---|---|---|---|---|
| Official NAV, valuation, daily PnL | `scripts/revalue_portfolio_official_nav.py`, `scripts/fetch_realtime_estimate.py`, `scripts/build_realtime_profit.py`, `scripts/portfolio_state.py`, `db/portfolio_state/` | Outcome events will read NAV/PnL; shadow outputs may be tempted to update state | LLM/LangGraph cannot write official NAV, daily PnL, units, or portfolio state; missing official values become `pending` or `blocked` | official NAV pending/blocked, stale NAV, cashflow crossing evaluation window, idempotent daily PnL |
| Execution sync | `scripts/execution_sync.py`, `scripts/trade_lifecycle.py`, `app/web_api_services.py`, `db/execution_sync/` | Retrieval pack and memory may read actual trades, confirmations, reconciliation | Execution data can explain execution behavior but cannot directly teach fund/market strategy unless routed as execution memory with visibility controls | execution-only visibility, actual trades excluded from general strategy memory, pending confirmation behavior unchanged |
| Alipay screenshot and position sync | `scripts/parse_alipay_position_screenshot.py`, `scripts/sync_portfolio_from_screenshots.py`, `/api/execution-sync/alipay-screenshot/parse` | New fund facts may want to use screenshot detections; RAG may ingest screenshot text accidentally | Preview does not write portfolio state; apply is the write boundary; screenshot text is not default RAG/fund profile memory | preview no-write, unmatched holdings remain blocked until classified, new holdings require explicit creation path |
| Copilot | `app/copilot_service.py`, `app/rag_service.py`, `app/web_api.py`, `frontend/src/components/okra/CopilotPanel.tsx` | Copilot may later explain action tickets, policies, and skills | Copilot cannot bypass official advice to generate executable trade decisions; RAG fallback behavior stays compatible | missing shadow files degrade gracefully, response schema compatibility, execution data only when explicitly needed |
| RAG subsystem | `config/rag.toml`, `scripts/rag_*.py`, `app/rag_service.py`, `db/rag/` | Layered retrieval pack may call RAG for similar cases and long text evidence | RAG is not primary fact source for current positions, NAV, cash, execution state, or hard constraints; no-future and visibility filters stay mandatory | `test_rag_*.py`, no-future, fund match, execution boundary, fallback reason, manifest integrity |
| Daily pipeline | `scripts/run_today_analysis.py`, `scripts/today_orchestrator.py`, `scripts/run_daily_pipeline.py`, `db/daily_workspace/`, `db/validated_advice/` | Shadow builders may later be inserted into the daily run | Existing official pipeline behavior and freshness/resume semantics stay unchanged until promotion | shadow step does not mutate official outputs, resume does not skip changed dependencies, runtime state remains accurate |
| Long memory store | `scripts/long_memory_store.py`, `scripts/run_long_memory_analysis.py`, `db/long_memory/` | Strategy memory, policies, and skills may reuse existing memory concepts | Existing memory status, approval flow, archived/rejected behavior, and execution memory boundary remain intact | archived not revived by default, policy lifecycle append-only, execution memory not mixed into fund/market learning |
| Workbench UI/API | `app/api_contracts.py`, `app/web_api_services.py`, `frontend/src/app/pages/*`, `frontend/src/lib/*` | Phase 7 may display old advice vs shadow tickets | First UI integration is read-only; no execution button on shadow tickets; existing page payloads remain compatible | DTO compatibility, missing shadow empty state, frontend build, Tauri check |
| News/source collection | `scripts/fetch_fund_news.py`, `scripts/build_llm_context.py`, `scripts/news_query_planner.py`, `raw/news/`, `db/llm_context/` | Retrieval pack will read news and source-health signals | Fetching, source priority, freshness labels, and source-health scoring should not be changed by action-ticket work | source health unchanged, query news counts unchanged, no-future availability respected |
| Provider/LLM transport | `scripts/multiagent_utils.py`, `scripts/provider_adapters.py`, `config/llm.toml` | New graph nodes and curator agents will call LLMs | Existing provider config and Responses-compatible transport remain compatible; LLM failures should degrade shadow artifacts, not official advice | retry/degraded output, transport mock tests, no official mutation on LLM failure |

## Detailed Function Boundaries

### Official NAV, Valuation, And Daily PnL

Current role:

- Maintains actual valuation and daily profit/loss from official NAV or trusted
  valuation sources.
- Feeds portfolio state and review logic.

Affected by refactor:

- Phase 4 outcome evaluation reads official NAV and trusted units.
- Phase 5/6 learning depends on Phase 4 labels.

Protection rules:

- New shadow scripts can read official valuation artifacts.
- New shadow scripts cannot write official valuation, units, cash, or daily PnL.
- If NAV is missing, stale, or contradicted, outcome scoring must use
  `pending`, `blocked`, or `conflicted`.
- No LLM output can fill official NAV or PnL.

Regression tests:

- `tests.test_revaluation_and_realtime`
- focused tests for blocked outcome when cashflow or units are unreliable
- focused tests that outcome evaluation does not mutate `db/portfolio_state/current.json`

### Execution Sync

Current role:

- Records real trades, conversions, pending confirmations, and reconciliation.
- Separates real operations from advice-learning.

Affected by refactor:

- Retrieval packs may need execution state for execution-aware decisions.
- Outcome evaluation may need to know whether an action was executed.
- Copilot may explain divergence between advice and real trades.

Protection rules:

- Execution data stays in execution memory or execution-only visibility.
- It must not become fund-profile learning or market-regime learning by default.
- It must not change action-ticket recommendations unless explicitly included
  as execution context.

Regression tests:

- `tests.test_execution_sync`
- retrieval pack visibility tests
- long-memory tests that actual trades remain execution-scoped

### Alipay Screenshot And Position Sync

Current role:

- Parses user screenshots.
- Builds preview.
- Applies preview to portfolio state only when explicitly accepted.

Affected by refactor:

- New-fund detection and canonical facts may later consume screenshot preview
  output.
- RAG/layered context may reference position metadata.

Protection rules:

- Preview remains non-mutating.
- Apply remains the portfolio-state mutation boundary.
- Unmatched holdings remain blocked until classified or created.
- Screenshot OCR/VLM text should not enter general RAG or strategy memory by
  default.

Regression tests:

- `tests.test_portfolio_screenshot_sync`
- preview no-write tests
- unmatched new-holding blocked tests

### Copilot

Current role:

- Explains current workbench context.
- Uses RAG pack when enabled and falls back when retrieval is insufficient.

Affected by refactor:

- Future Copilot can explain action tickets, debates, policies, skills, and
  outcome events.

Protection rules:

- Copilot is not an execution decision maker.
- It should cite official advice or shadow artifact status clearly.
- It should not present shadow ticket suggestions as official actions.
- Existing response shape must remain compatible.

Regression tests:

- `tests.test_web_api_rag_copilot`
- missing shadow artifact fallback
- execution-only question includes execution data only when intended

### RAG

Current role:

- Provides retrieval infrastructure and Copilot evidence pack.
- Has hard-filter requirements around date, fund, memory status, and execution
  boundary.

Affected by refactor:

- Phase 2 layered retrieval pack may call RAG for similar cases, anti-patterns,
  and long text evidence.

Protection rules:

- RAG is a retrieval layer, not memory itself.
- RAG is not the first source for current facts.
- RAG hits must carry source refs, date constraints, visibility, and fallback
  status.
- No-future and execution-only filters remain mandatory.

Regression tests:

- `test_rag_no_future.py`
- `test_rag_execution_boundary.py`
- `test_rag_memory_visibility.py`
- `test_rag_retriever_filters.py`
- `test_web_api_rag_copilot.py`

### Daily Pipeline

Current role:

- Runs canonical daily analysis and writes official artifacts.

Affected by refactor:

- Shadow builders may later become optional pipeline steps.

Protection rules:

- Phase 1 starts as standalone script.
- Pipeline integration waits until artifact format is stable.
- Existing `validated_advice` remains official until promotion.
- Runtime status must distinguish official steps from shadow steps if added.

Regression tests:

- `tests.test_pipeline_logic`
- `tests.test_multiagent_and_review`
- `tests.test_validation_and_trade`
- focused tests for no official mutation from shadow steps

### Long Memory Store

Current role:

- Maintains long-memory records, statuses, approval flow, exports, and learning
  artifacts.

Affected by refactor:

- Adaptive policies and strategy skills may reuse long-memory outputs.
- Skill Curator may read historical memory and outcomes.

Protection rules:

- Existing long-memory lifecycle remains respected.
- Archived/rejected records are not revived by default.
- New strategy policies/skills use append-only event logs.
- Execution memory remains separate.

Regression tests:

- `tests.test_long_memory`
- `tests.test_learning_memory`
- `tests.test_web_api_long_memory`
- focused policy lifecycle tests

### Workbench UI/API

Current role:

- Presents Today, Portfolio, Execution, Research, Realtime, Review, System, and
  Copilot surfaces through the local Python API.

Affected by refactor:

- Phase 7 will add old-versus-new shadow review.

Protection rules:

- First shadow UI is read-only.
- Missing shadow artifacts are valid empty states.
- Shadow tickets are explicitly non-executable.
- Existing pages must not break when shadow artifacts are absent.

Regression tests:

- API DTO tests
- frontend build
- Tauri check
- empty-state UI verification

## Cross-Cutting Guardrails

### Official-State Guardrail

Shadow scripts must not write:

```text
db/validated_advice/
db/portfolio_state/current.json
db/execution_sync/
db/portfolio_valuation/
db/portfolio_daily_pnl/
```

unless the phase explicitly promotes that behavior and documents the migration.

### Visibility Guardrail

Every data item that can be execution-only must carry a visibility or scope
field before entering retrieval or memory.

Recommended values:

```text
default
strategy_learning
execution_only
private_user_input
shadow_only
```

### Missing-Data Guardrail

Decision-critical missing data must not be collapsed into empty strings.

Use:

```text
present
missing
stale
conflicted
pending
blocked
not_applicable
```

### UI Guardrail

Shadow artifacts must be displayed as:

```text
shadow_only
non_executable
not_official_advice
```

until explicit promotion.

