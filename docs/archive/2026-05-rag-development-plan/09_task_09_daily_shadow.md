# Task 9：Daily Shadow 接入

目标：不改变每日建议输出的前提下，让 RAG 与旧 `evidence_index.py` 并行跑，记录差异、trace 和质量指标。

## PR-21：Pipeline 可选 RAG Ingest/Eval

范围：

- 修改 `scripts/run_daily_pipeline.py`。
- 可选调用：

```text
rag_ingest.py --date {date} --daily
rag_eval.py --date {date} --compare-legacy
```

- 新增配置：

```toml
[rag.agent_shadow]
enabled = false
write_trace = true
inject_into_prompt = false
compare_legacy = true
```

- `inject_into_prompt=false` 时，只写 debug artifact，不进入 agent prompt。

验收：

```powershell
python -m unittest discover -s tests -p test_pipeline_logic.py
python scripts\run_daily_pipeline.py --date 2026-05-20 --mode intraday --demo --llm-mock --resume-existing
```

## PR-22：Agent Inputs Shadow 字段

范围：

- 修改 `scripts/agent_inputs.py`。
- 实施前先确认当前真实证据注入入口：`scripts/agent_inputs.py` 与 `scripts/run_multiagent_research.py` 中可能同时存在 evidence 组装/注入逻辑，PR 必须用 `rg "retrieved_evidence|attach_retrieved|evidence_index"` 确认最终主流程走哪一个入口。
- 如果主流程实际在 `run_multiagent_research.py` 内联组装 evidence，则先抽到或路由到 `agent_inputs.py` 的单一入口；如果 `agent_inputs.py` 已是 canonical entry，则 `run_multiagent_research.py` 只负责调用和透传，不重复写 shadow 字段。
- 在 shadow 开启时额外写：

```json
{
  "rag_retrieved_evidence": {},
  "rag_retrieval_trace_id": "...",
  "rag_legacy_diff": {}
}
```

- 旧字段 `retrieved_evidence` 保持不变。
- `run_multiagent_research.py` 或 aggregate artifact 记录每个 agent 的 trace/diff，但不能和 `agent_inputs.py` 各写一份导致重复或不一致。

验收：

```powershell
python -m unittest discover -s tests -p test_multiagent_and_review.py
python scripts\run_daily_pipeline.py --date 2026-05-20 --mode intraday --demo --llm-mock --resume-existing
```

## PR-23：RAG Eval Legacy 对比

范围：

- 新增 `scripts/rag_eval.py`。
- 输出 `db/rag/eval/YYYY-MM-DD.json`。
- 指标：
  - legacy top hits vs RAG top hits
  - fund match rate
  - source coverage
  - stale hit count
  - token budget
  - no-future violation
  - fallback reason

验收：

```powershell
python scripts\rag_eval.py --date 2026-05-20 --compare-legacy
```

质量门：

- Shadow 开启后，每日分析最终 `validated_advice` 不因 RAG 变化。
- 每个 agent 有独立 `trace_id`。
- 旧 `evidence_index.py` 仍是默认主输入。

回退：

- `rag.agent_shadow.enabled=false` 完全关闭。
- RAG eval 失败只标 degraded，不阻断 daily pipeline，除非显式 `--rag-strict`。

## Task 9 完成定义

- RAG 可以和 legacy evidence 并行跑。
- 差异可审计。
- 不改变最终建议。
- 后续 Task 10 有足够 shadow 评估依据。
