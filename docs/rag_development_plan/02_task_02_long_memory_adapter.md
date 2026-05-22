# Task 2：Long Memory Adapter

目标：把 `db/long_memory/memory.sqlite` 作为 RAG 第一批 source，读取同一套长期记忆记录，并尊重状态、有效期、覆盖关系。

## PR-04：long_memory 标准文档抽取

范围：

- 新增或扩展 `scripts/rag_sources.py`。
- 实现 `iter_long_memory_documents(date=None)`。
- 从 `db/long_memory/memory.sqlite` 读取，不以 `exports/all_memory.json` 为主源。
- 一条 memory record 生成一条 `RagDocument` 和默认一个 `RagChunk`。

字段映射：

| memory 字段 | RAG 字段 |
|---|---|
| `domain` | `domain` |
| `entity_key` | `entity_id` 或 `source_record_id` |
| `status` | `status` |
| `confidence` | `confidence` |
| `valid_from` | `valid_from` |
| `valid_until` | `valid_until` |
| `metadata_json.fund_codes` | `fund_codes` |
| `metadata_json.superseded_by` | `superseded_by` |
| `evidence_refs_json` | `payload.evidence_refs` |

source tier 建议：

- `permanent` -> `memory_approved`
- `strategic` -> `memory_strategic`
- `candidate` -> `memory_candidate`
- `archived` / `rejected` -> `negative_memory`

验收：

```powershell
python -m unittest discover -s tests -p test_rag_sources.py
python scripts\rag_ingest.py --domain long_memory --dry-run
```

## PR-05：记忆状态、可见性和生命周期过滤测试

范围：

- 增加 long memory adapter 测试。
- archived/rejected 标记为 `visibility=review_only`、`is_negative_example=true`。
- permanent/strategic/candidate 默认 `visibility=default`。
- `valid_from/valid_until` 可由 retriever hard filter 使用。
- `superseded_by` 存在时默认不作为 current 证据。

必须覆盖：

- 普通 profile 不召回 archived/rejected。
- review profile 可召回 archived/rejected，但 hit 必须标反例。
- 历史日期查询必须按 `available_from` 和 `valid_from/valid_until` 过滤。
- 缺少 timestamp 的旧 memory 需要标 `available_from_inferred=true`。

验收：

```powershell
python -m unittest discover -s tests -p test_rag_memory_visibility.py
python -m unittest discover -s tests -p test_rag_sources.py
```

回退：

- long memory adapter 失败只记录 manifest error，不阻断其他 source。
- 原有 `long_memory_store.py` 和 FTS5 不修改、不废弃。

## Task 2 完成定义

- permanent/strategic/candidate 默认可见。
- archived/rejected 普通 profile 不可见。
- valid_from/valid_until/superseded_by 进入 RAG metadata。
- RAG 不改变长期记忆写入和人工审批链路。
