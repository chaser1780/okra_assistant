# Task 8：Copilot RAG 接入

目标：右侧智能助手成为第一个真实消费方，回答带引用、可追踪、可回退。第一版可以先让前端接收 citations/traceId，展示可分第二步做。

## PR-18：RAG Service 与 Evidence Pack

范围：

- 新增 `app/rag_service.py`。
- 新增 `app/rag_answering.py`。
- 实现 `build_copilot_rag_pack(payload) -> dict`。
- 内部调用 planner、retriever、trace、answering。

evidence pack 内容：

- `query_plan`
- `hits`
- `citations`
- `missingData`
- `structuredFacts`
- `traceId`
- `tokenBudget`

回答层约束：

- 数值事实优先从 structured payload 读取。
- stale hit 必须在 evidence 中标注。
- archived/rejected 只能作为历史反例。
- execution hit 只有 execution intent 可用。

验收：

```powershell
python -m unittest discover -s tests -p test_web_api_rag_copilot.py
```

## PR-19：Web API 和 Copilot Service 接入

范围：

- 修改 `app/web_api.py`。
- 修改 `app/copilot_service.py`。
- 保留旧 `_copilot_evidence()` fallback。
- `OkraWebApi.explain()` 新流程：

```text
payload/question
  -> build_copilot_rag_pack()
  -> call_copilot_llm(question, evidence_pack)
  -> answer + citations + traceId + retrieval
```

API 返回兼容扩展：

```json
{
  "answer": "...",
  "mode": "rag_llm",
  "sourceDate": "2026-05-20",
  "traceId": "ragq_...",
  "citations": [],
  "retrieval": {
    "intent": "fund_explain",
    "hitCount": 12,
    "missingData": []
  }
}
```

prompt 约束：

- 只基于 evidence pack 回答。
- 先给结论，再给证据和风险。
- 引用 `[C1]`、`[C2]`。
- 缺少 validated advice、持仓、行情、新闻时必须说明。
- 不得编造净值、收益、新闻或交易结论。

验收：

```powershell
python -m unittest discover -s tests -p test_web_api_rag_copilot.py
```

回退：

- RAG 异常：fallback 到当前 `_copilot_evidence()`。
- LLM 异常：fallback 到 `local_copilot_answer()`。

## PR-20：前端 API 类型与 CopilotPanel

范围：

- 修改 `frontend/src/lib/types.ts`。
- 修改 `frontend/src/lib/api.ts` 或现有 `askCopilot()` 类型。
- 修改 `frontend/src/components/okra/CopilotPanel.tsx`。
- 第一版只接收并保存 `citations/traceId/retrieval`；第二步再做“证据来源”折叠区。

UI 建议：

- 保持右侧助手紧凑，不做大卡片堆叠。
- citations 可用折叠列表展示：标题、source_kind、日期、基金代码。
- fallback mode 要让用户知道当前不是 RAG 证据回答。

验收：

```powershell
cd frontend
npm run build
```

## Task 8 完成定义

- RAG 关闭时旧行为可用。
- RAG 开启时返回 `mode=rag_llm`、`traceId`、`citations`。
- “这个回答用了哪些证据”能返回 trace 摘要。
- 前端 build 通过。
