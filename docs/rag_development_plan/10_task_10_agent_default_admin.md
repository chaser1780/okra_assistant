# Task 10：Agent 默认接入和长期维护

目标：当 shadow 评估稳定后，让不同 Agent 使用不同 RAG profile，同时保留 legacy fallback，并提供维护/可观测能力。

## PR-24：Agent Profiles 默认接入

范围：

- 将 agent profiles 写入 `config/rag.toml`。
- 修改 `scripts/agent_inputs.py` 默认读 RAG profile。
- 延续 Task 9 的单一 evidence 注入入口约定：先确认 `agent_inputs.py` 与 `run_multiagent_research.py` 的真实调用关系，再在 canonical entry 切默认 backend，避免只改 `agent_inputs.py` 而主流程仍走内联 legacy evidence。
- RAG 失败或 hit 不足时回退 legacy `retrieve_agent_evidence()`。
- `scripts/run_multiagent_research.py` 的 `workflow_meta` 记录：
  - `retrieval_backend`
  - `rag_enabled`
  - `fallback_used`
  - 每个 agent 的 `trace_id`
  - active manifest ids/hash
  - `manifest_set_sha256`

初始 profile：

```toml
[rag.agent_profiles.market_analyst]
domains = ["market", "news", "fund"]
source_kinds = ["llm_context", "evidence_item", "long_memory"]
prefer_evidence_types = ["quote_snapshot", "intraday_proxy", "market_news", "policy_news"]
top_k_portfolio = 8
top_k_per_fund = 3
allow_negative_memory = false
include_execution = false

[rag.agent_profiles.risk_manager]
domains = ["market", "portfolio", "news", "memory"]
prefer_evidence_types = ["regulatory_notice", "risk_event", "stale_data", "crowding"]
top_k_portfolio = 12
top_k_per_fund = 4
allow_negative_memory = false
include_execution = false

[rag.agent_profiles.portfolio_trader]
domains = ["portfolio", "decision", "fund", "market"]
prefer_source_tiers = ["structured_current", "decision_trace", "market_data"]
top_k_portfolio = 10
top_k_per_fund = 4
include_execution = false
```

验收：

```powershell
python -m unittest discover -s tests -p test_multiagent_and_review.py
python scripts\run_daily_pipeline.py --date 2026-05-20 --mode intraday --demo --llm-mock --resume-existing
```

质量门：

- 开启 RAG 默认输入后，agent output schema 不变。
- 关闭 RAG 后，旧链路行为不变。
- 对同一日期重复运行时，agent reuse metadata 可识别 RAG manifest 是否变化。

回退：

- 每个 agent profile 可独立关闭。
- `fallback_to_legacy=true` 时 legacy evidence 自动补位。
- token 超预算时优先降级新闻/情绪/低 tier，保留结构化事实和决策证据。

## PR-25：Maintenance、Admin API 与系统页

范围：

- 新增 `scripts/rag_maintenance.py`。
- 修改 `app/web_api.py` / `app/web_api_services.py`。
- 修改 `frontend/src/app/pages/SystemPage.tsx` 或当前系统/设置页。
- 可选补充 `ResearchPage.tsx` 展示最近 trace。

维护命令：

```powershell
python scripts\rag_maintenance.py --vacuum
python scripts\rag_maintenance.py --rebuild --domain long_memory
python scripts\rag_maintenance.py --purge-domain execution
python scripts\rag_maintenance.py --check-integrity
```

Admin API：

```text
GET  /api/rag/status
POST /api/rag/search
POST /api/rag/reindex
GET  /api/rag/trace?id=...
POST /api/rag/eval
```

系统页展示：

- RAG enabled / shadow / fallback 状态。
- 最近 ingest 时间。
- documents/chunks 数量。
- 各 source doc count。
- embedding pending/error count。
- 最近 10 次 trace。
- no-future/fund-match eval 是否通过。

验收：

```powershell
python -m unittest discover -s tests -p test_web_api_rag_admin.py
cd frontend
npm run build
```

## Task 10 完成定义

- daily agent 可默认使用 RAG，legacy fallback 可用。
- workflow metadata 记录 RAG manifest。
- 系统页/API 能看见 RAG 状态、trace 和失败原因。
- reindex 不删除原始业务数据。
