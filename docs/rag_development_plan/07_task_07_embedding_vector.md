# Task 7：Embedding Client 和 Vector Store

目标：在 SQLite metadata 主控的基础上接入真实 embedding 与可替换 vector backend。真实向量上线不能破坏 mock/FTS fallback。

## PR-15：Embedding 配置、Probe、Dry-run 与 Mock Fallback

范围：

- 新增 `scripts/rag_embedding_client.py`。
- 读取 `[rag.embedding]` 和可选 `[embedding_provider.*]`。
- 支持：

```powershell
python scripts\rag_embedding_client.py --probe
python scripts\rag_embedding_client.py --probe --dry-run
```

行为：

- 无 API key 时 dry-run/mock 成功，返回清晰状态。
- 当前 Responses 代理不支持 embeddings endpoint 时，允许单独配置 embedding base URL/key。
- embedding 请求只发送 `text_for_embedding`，不发送完整 `payload_json`、截图 OCR、账户流水。

验收：

```powershell
python -m unittest discover -s tests -p test_rag_embedding_client.py
python scripts\rag_embedding_client.py --probe
```

## PR-16：Embedding Cache

范围：

- `embedding_cache` 按 `embedding_model + text_sha256` 缓存。
- ingest 时 unchanged chunk 不重复请求 embedding。
- embedding 失败只标 chunk `embedding_status=error` 或 `pending`，不阻断旧链路。

验收：

```powershell
python -m unittest discover -s tests -p test_rag_embedding_client.py
python scripts\rag_ingest.py --date 2026-05-20 --write --all
python scripts\rag_ingest.py --date 2026-05-20 --write --all
```

第二次运行应能看到 unchanged chunk 未重复 embedding。

## PR-17：Vector Store Adapter

范围：

- 完善 `scripts/rag_vector_store.py`。
- 提供统一接口：

```python
class RagVectorStore:
    def upsert(self, chunks, vectors) -> None: ...
    def search(self, query_vector, *, filters, top_k): ...
    def delete_missing(self, manifest_id: str) -> None: ...
```

backend 顺序：

1. `sqlite_mock`：测试和 dry-run。
2. `chroma`：第一版真实向量落地候选。
3. `sqlite_faiss`：后续优化，不作为第一批阻塞项。

关键要求：

- 业务层只依赖 `RagVectorStore` 接口。
- metadata filter 仍由 SQLite 主控；vector backend 只负责相似度候选。
- backend 可从 `chroma` 切回 `sqlite_mock`。

验收：

```powershell
python -m unittest discover -s tests -p test_rag_embedding_client.py
python -m unittest discover -s tests -p test_rag_retriever_filters.py
```

## Task 7 完成定义

- 无 API key 可 dry-run/mock。
- embedding API 不可用不阻断 pipeline。
- unchanged chunk 不重复请求。
- vector backend 可替换，业务层不绑定 Chroma/FAISS。
