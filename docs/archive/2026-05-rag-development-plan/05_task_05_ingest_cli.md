# Task 5：RAG Ingest CLI

目标：提供稳定、可重复、可审计的索引入口。第一版先完成 dry-run 与 SQLite metadata 写入，真实 embedding 由 Task 7 独立接入。

## PR-10：`rag_ingest.py --dry-run`

范围：

- 新增 `scripts/rag_ingest.py`。
- 支持参数：

```powershell
python scripts\rag_ingest.py --date 2026-05-20 --all --dry-run
python scripts\rag_ingest.py --date 2026-05-20 --domain long_memory --domain portfolio_state --dry-run
python scripts\rag_ingest.py --domain long_memory --dry-run
python scripts\rag_ingest.py --all-dates --date-from 2026-05-01 --date-to 2026-05-20 --domain llm_context --domain validated_advice --domain committee_bundle --dry-run
```

参数约束：

- 日期型 source 必须显式传 `--date`，例如 `llm_context`、`validated_advice`、`committee_bundle`、`agent_outputs`、`raw_news`。
- 无 `--date` 时只允许读取日期无关 source，例如 `long_memory`，或读取明确 current source，例如 `portfolio_state/current.json`。
- 跨日期批量索引必须显式使用 `--all-dates --date-from ... --date-to ...`，避免 `--all` 在日期型 source 上产生歧义。
- 如果用户传了 `--all` 但没有 `--date` 或日期范围，CLI 应拒绝日期型 source，并在 summary 中列出 skipped domains。

dry-run 输出：

- 每个 source 的 doc count、chunk count、missing count、error count。
- 每个 source 的跳过原因。
- 预计写入 manifest id。
- 不写 `db/rag/rag.sqlite`，或只允许写临时 dry-run report。

阻塞依赖：

- PR-03 index store 表骨架。
- PR-04/06/07/08/09 source adapters。

验收：

```powershell
python -m unittest discover -s tests -p test_rag_sources.py
python scripts\rag_ingest.py --date 2026-05-20 --dry-run --all
```

## PR-11：`--write`、幂等写入与 Manifest

范围：

- `rag_ingest.py --write` 写入 `documents/chunks/source_manifests/active_manifests/ingest_runs`。
- 实现 `content_sha256` 和 chunk hash。
- `content_sha256` 未变时跳过更新。
- 写 manifest：
  - source file path
  - source mtime/size/hash
  - doc count
  - chunk count
  - skipped count
  - error list
  - active manifest id
- active manifest 切换使用临时 manifest 完成后再原子标记。

Active manifest 设计提前定为：

- `source_manifests` 保持 append-only，记录每次 source ingest 的 manifest 内容、hash、状态和错误。
- 新增 `active_manifests` 表，按 `scope_key` 指向当前生效 manifest，而不是只在 `source_manifests` 上用 `active=1`。
- `scope_key` 建议格式：`{date_or_global}:{domain}:{source_kind}`，例如 `2026-05-20:decision:validated_advice`、`global:memory:long_memory`。
- active 切换流程：先写 `source_manifests(status='staged')`，完成 doc/chunk 写入与校验后，在同一事务中 upsert `active_manifests(scope_key, manifest_id, activated_at)` 并把 manifest 标记为 `active`。
- agent reuse metadata 使用排序后的 active manifest ids/hash 计算 `manifest_set_sha256`，避免后续无法判断同一日期的检索输入是否变化。

命令：

```powershell
python scripts\rag_ingest.py --date 2026-05-20 --write --all
python scripts\rag_ingest.py --date 2026-05-20 --write --all
```

第二次运行用于验收幂等。

验收：

```powershell
python -m unittest discover -s tests -p test_rag_index_store.py
python -m unittest discover -s tests -p test_rag_sources.py
python scripts\rag_ingest.py --date 2026-05-20 --write --all
python scripts\rag_ingest.py --date 2026-05-20 --write --all
```

回退：

- 删除 `db/rag/` 即可清空 RAG 索引，不影响 `db/long_memory/`、`db/portfolio_state/`、`db/validated_advice/` 等原始数据。
- 单个 adapter 失败记录 manifest error，不影响其他 adapter。

## Task 5 完成定义

- `--dry-run` 可看清将索引什么。
- `--write` 幂等。
- manifest 可追踪 source 状态。
- 不影响现有 pipeline。
