# Task 1：RAG 配置和 SQLite Store

目标：把 RAG 注册为项目级能力，但默认关闭，不影响当前 Copilot、daily pipeline、long memory、execution sync。

## PR-01：RAG 配置、开关与目录约定

范围：

- 新增 `config/rag.toml`。
- 新增 `scripts/rag_config.py` 的安全默认配置读取。
- 约定 `db/rag/`、`db/rag/vector_store/`、`db/rag/manifests/`、`db/rag/traces/`、`db/rag/eval/`。
- 不修改现有 Copilot 或 daily pipeline 逻辑。

建议配置：

```toml
[rag]
enabled = false
default_profile = "copilot_qa"
index_dir = "db/rag"
trace_enabled = true
fallback_to_legacy = true

[rag.embedding]
enabled = false
provider = "OpenAI"
model = "text-embedding-3-large"
dimensions = 1536
batch_size = 64
timeout_seconds = 60
cache_enabled = true
dry_run = true

[rag.vector_store]
backend = "sqlite_mock"
sqlite_path = "db/rag/rag.sqlite"
allow_chroma = false
allow_faiss = false

[rag.sources]
long_memory = true
portfolio_state = true
llm_context = true
evidence_index = true
validated_advice = true
committee_bundle = true
agent_outputs = false
execution_sync = false
raw_news = false

[rag.safety]
require_available_from = true
require_source_path = true
exclude_archived_by_default = true
exclude_rejected_by_default = true
exclude_execution_by_default = true
```

验收：

```powershell
python -m unittest discover -s tests -p test_rag_models.py
```

回退：

- 删除 `config/rag.toml` 或设置 `rag.enabled=false`，所有新增逻辑只作为离线 CLI/debug 能力存在。

## PR-02：RAG 数据模型与字段校验

范围：

- 新增 `scripts/rag_models.py`。
- 定义 `RagDocument`、`RagChunk`、`RagQueryPlan`、`RagHit`、`RagTrace`。
- 字段名稳定，和蓝图中的 metadata schema 对齐。
- 对关键字段做轻量校验：`doc_id`、`source_kind`、`source_path`、`source_record_id`、`available_from`、`as_of_date`、`domain`、`source_tier`、`visibility`。

建议：

- 第一版用 `dataclass`，避免引入新依赖。
- `payload`、`metadata` 用 dict，入库前统一 JSON 序列化。
- `fund_codes` 始终是 list，不用逗号字符串。

验收：

```powershell
python -m unittest discover -s tests -p test_rag_config.py
```

风险：

- 字段名一旦被 adapter、retriever、trace 使用，后续改名成本高。因此 PR-02 单独评审。

## PR-03：SQLite Index Store 与表骨架

范围：

- 新增 `scripts/rag_index_store.py`。
- 初始化 `db/rag/rag.sqlite`。
- 建表：`documents`、`chunks`、`source_manifests`、`active_manifests`、`embedding_cache`、`query_traces`、`ingest_runs`。
- 提供 `init_store()`、`upsert_documents()`、`upsert_chunks()`、`write_manifest()`、`write_trace()` 的最小接口。

关键原则：

- SQLite 是 metadata 主控，即使后面接 Chroma/FAISS，业务仍以 SQLite manifest 与 trace 为准。
- 默认不物理删除 source 消失的 document，先标 `active=0`。
- 写入时显式 `encoding="utf-8"`，SQLite connection 设置合理 timeout，兼容 Windows 文件锁。

验收：

```powershell
python -m unittest discover -s tests -p test_rag_index_store.py
```

回退：

- 删除 `db/rag/` 不影响原始业务数据。
- `rag.enabled=false` 时不会被 Copilot/daily pipeline 调用。

## Task 1 完成定义

- `db/rag/rag.sqlite` 可初始化。
- RAG 默认不开启。
- dry-run 不需要 API key。
- 现有 tests 不因新增配置失败。
