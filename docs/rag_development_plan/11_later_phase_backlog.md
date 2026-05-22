# Later Phase Backlog

这些内容来自蓝图 Phase 7/8，建议放在 Task 10 之后，不进入第一批默认开发。原因是它们直接影响建议生成、长期记忆写入、历史复盘和真实交易隐私边界，风险比基础检索更高。

## PR-26：Decision / Memory / Review / Replay Profiles

目标：让最终建议、长期记忆分析、复盘、回测共享 RAG evidence pack，但不绕过现有验证链路。

范围：

- `scripts/generate_llm_advice.py`
- `scripts/run_long_memory_analysis.py`
- `scripts/review_advice.py`
- `scripts/run_replay_experiment.py`
- `tests/test_rag_decision_memory_review.py`

profile 设计：

- `decision_profile`：只能解释或辅助现有 committee/validated candidate，不允许用新闻绕过 `committee_decision_bundle` 生成新建议。
- `memory_profile`：写入新 memory 前检索同域同实体已有 memory，检查 duplicate、contradiction、superseded。
- `review_profile`：允许 archived/rejected，但必须标 `negative_example`。
- `backtest_profile`：强制 `available_from <= replay_date`，每次 replay 写 no-future audit。

验收：

- 长期记忆分析不会重复生成同一条已 permanent 的规则。
- review 能引用历史反例，但不会污染当前建议。
- replay 对历史日期不召回未来记忆和未来持仓。
- decision profile 缺少 committee bundle 时明确 missing，而不是用新闻生成新建议。

回退：

- 记忆写入继续保持人工审批链路。
- review/backtest profile 与当前建议 profile 分离配置。

## PR-27：Execution Profile 与隐私隔离

目标：支持“真实交易为什么和系统建议不同”“当前真实持仓为何不同”等问题，同时防止执行数据污染投研模型。

范围：

- `scripts/rag_sources.py`
- `scripts/execution_sync.py`
- `scripts/long_memory_store.py`
- `app/web_api.py`
- `frontend/src/app/pages/ExecutionPage.tsx`
- `tests/test_rag_execution_boundary.py`

硬规则：

- `rag.sources.execution_sync=false` 默认关闭。
- execution doc 必填：

```json
{
  "domain": "execution",
  "learning_scope": "execution_only",
  "visibility": "execution_only",
  "source_kind": "execution_sync"
}
```

- 只索引摘要，不 embedding 完整截图 OCR、账户截图、流水明细。
- Copilot planner 只有在 intent 为 `execution_explain`、`position_reconcile`、`pending_confirmation` 时打开 `include_execution=true`。
- `long_memory_store.build_execution_memory()` 继续只产出 execution memory，不进入 fund memory。

验收：

```powershell
python -m unittest discover -s tests -p test_rag_execution_boundary.py
python -m unittest discover -s tests -p test_execution_sync.py
```

安全门：

- 问真实持仓/待确认交易时能召回 execution。
- 问基金是否值得买、系统建议胜率、市场规律时不能召回 actual trades。
- execution trace 中所有 hit 都有 `learning_scope=execution_only`。

回退：

- `rag_maintenance.py --purge-domain execution` 可删除 RAG execution docs。
- 删除 `db/rag` execution docs 不影响原始 `db/execution_sync` 数据。
