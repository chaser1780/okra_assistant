from __future__ import annotations

from dataclasses import is_dataclass
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from common import timestamp_now
from rag_config import ensure_rag_layout, rag_db_path
from rag_models import RagChunk, RagDocument, RagTrace, json_dumps


SCHEMA_VERSION = 2


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect_store(agent_home: Path, db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or rag_db_path(agent_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_store(agent_home: Path) -> Path:
    ensure_rag_layout(agent_home)
    path = rag_db_path(agent_home)
    with connect_store(agent_home, path) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                source_kind TEXT NOT NULL,
                source_path TEXT NOT NULL,
                scope_key TEXT NOT NULL DEFAULT '',
                source_record_id TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                event_date TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL DEFAULT '',
                available_from TEXT NOT NULL,
                entity_type TEXT NOT NULL DEFAULT '',
                entity_id TEXT NOT NULL DEFAULT '',
                fund_codes_json TEXT NOT NULL DEFAULT '[]',
                domain TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                valid_from TEXT NOT NULL DEFAULT '',
                valid_until TEXT NOT NULL DEFAULT '',
                source_tier TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'default',
                learning_scope TEXT NOT NULL DEFAULT '',
                is_negative_example INTEGER NOT NULL DEFAULT 0,
                content_sha256 TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                scope_key TEXT NOT NULL DEFAULT '',
                chunk_index INTEGER NOT NULL,
                text_for_embedding TEXT NOT NULL,
                text_for_llm TEXT NOT NULL,
                token_estimate INTEGER NOT NULL DEFAULT 0,
                embedding_model TEXT NOT NULL DEFAULT '',
                embedding_status TEXT NOT NULL DEFAULT 'pending',
                embedding_sha256 TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_manifests (
                manifest_id TEXT PRIMARY KEY,
                scope_key TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL,
                source_path TEXT NOT NULL,
                as_of_date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                doc_count INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                error_json TEXT NOT NULL DEFAULT '{}',
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_manifests (
                scope_key TEXT PRIMARY KEY,
                manifest_id TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                FOREIGN KEY(manifest_id) REFERENCES source_manifests(manifest_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS manifest_documents (
                manifest_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                scope_key TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL DEFAULT '',
                source_path TEXT NOT NULL DEFAULT '',
                as_of_date TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                PRIMARY KEY(manifest_id, doc_id),
                FOREIGN KEY(manifest_id) REFERENCES source_manifests(manifest_id),
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS manifest_chunks (
                manifest_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                scope_key TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                PRIMARY KEY(manifest_id, chunk_id),
                FOREIGN KEY(manifest_id) REFERENCES source_manifests(manifest_id),
                FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id),
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_cache (
                cache_key TEXT PRIMARY KEY,
                chunk_id TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                text_sha256 TEXT NOT NULL,
                vector_ref TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                error_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_vectors (
                vector_ref TEXT PRIMARY KEY,
                embedding_json TEXT NOT NULL,
                dimensions INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS query_traces (
                trace_id TEXT PRIMARY KEY,
                query_plan_json TEXT NOT NULL,
                hits_json TEXT NOT NULL DEFAULT '[]',
                rejected_samples_json TEXT NOT NULL DEFAULT '[]',
                missing_data_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ingest_runs (
                run_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                as_of_date TEXT NOT NULL DEFAULT '',
                source_count INTEGER NOT NULL DEFAULT 0,
                doc_count INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                error_json TEXT NOT NULL DEFAULT '{}',
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_kind, source_record_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_as_of ON documents(as_of_date, available_from)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain, visibility, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, chunk_index)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_manifest_documents_scope ON manifest_documents(scope_key, doc_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_manifest_chunks_doc ON manifest_chunks(doc_id, chunk_id)")
        _ensure_store_schema(conn)
    return path


def _ensure_store_schema(conn: sqlite3.Connection) -> None:
    doc_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "scope_key" not in doc_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN scope_key TEXT NOT NULL DEFAULT ''")

    chunk_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    if "scope_key" not in chunk_columns:
        conn.execute("ALTER TABLE chunks ADD COLUMN scope_key TEXT NOT NULL DEFAULT ''")

    manifest_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(source_manifests)").fetchall()}
    if "scope_key" not in manifest_columns:
        conn.execute("ALTER TABLE source_manifests ADD COLUMN scope_key TEXT NOT NULL DEFAULT ''")

    active_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(active_manifests)").fetchall()}
    if active_columns and "scope_key" not in active_columns:
        conn.execute("DROP TABLE active_manifests")
        conn.execute(
            """
            CREATE TABLE active_manifests (
                scope_key TEXT PRIMARY KEY,
                manifest_id TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                FOREIGN KEY(manifest_id) REFERENCES source_manifests(manifest_id)
            )
            """
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS manifest_documents (
            manifest_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            scope_key TEXT NOT NULL DEFAULT '',
            source_kind TEXT NOT NULL DEFAULT '',
            source_path TEXT NOT NULL DEFAULT '',
            as_of_date TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            PRIMARY KEY(manifest_id, doc_id),
            FOREIGN KEY(manifest_id) REFERENCES source_manifests(manifest_id),
            FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS manifest_chunks (
            manifest_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            scope_key TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            PRIMARY KEY(manifest_id, chunk_id),
            FOREIGN KEY(manifest_id) REFERENCES source_manifests(manifest_id),
            FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id),
            FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_scope ON documents(scope_key, active)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_scope ON chunks(scope_key, active)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_manifest_documents_scope ON manifest_documents(scope_key, doc_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_manifest_chunks_doc ON manifest_chunks(doc_id, chunk_id)")
    _backfill_active_manifest_membership(conn)


def _legacy_scope_match_sql(alias: str = "d") -> str:
    return f"""
        {alias}.source_kind = sm.source_kind
        AND (
            sm.as_of_date = ''
            OR {alias}.as_of_date = sm.as_of_date
            OR sm.scope_key LIKE 'current:%'
            OR sm.scope_key LIKE 'global:%'
        )
    """


def _backfill_active_manifest_membership(conn: sqlite3.Connection) -> None:
    active_count = int(conn.execute("SELECT COUNT(*) FROM active_manifests").fetchone()[0])
    if not active_count:
        return
    now = timestamp_now()
    conn.execute(
        f"""
        UPDATE documents
        SET scope_key = (
            SELECT am.scope_key
            FROM active_manifests am
            JOIN source_manifests sm ON sm.manifest_id = am.manifest_id
            WHERE {_legacy_scope_match_sql("documents")}
            ORDER BY sm.created_at DESC
            LIMIT 1
        )
        WHERE scope_key = ''
          AND EXISTS (
            SELECT 1
            FROM active_manifests am
            JOIN source_manifests sm ON sm.manifest_id = am.manifest_id
            WHERE {_legacy_scope_match_sql("documents")}
          )
        """
    )
    conn.execute(
        """
        UPDATE chunks
        SET scope_key = COALESCE((SELECT scope_key FROM documents WHERE documents.doc_id = chunks.doc_id), '')
        WHERE scope_key = ''
        """
    )
    conn.execute(
        f"""
        INSERT OR IGNORE INTO manifest_documents (
            manifest_id, doc_id, scope_key, source_kind, source_path, as_of_date, created_at
        )
        SELECT am.manifest_id, d.doc_id, am.scope_key, d.source_kind, d.source_path, d.as_of_date, ?
        FROM active_manifests am
        JOIN source_manifests sm ON sm.manifest_id = am.manifest_id
        JOIN documents d ON {_legacy_scope_match_sql("d")}
        WHERE d.active = 1
          AND NOT EXISTS (
            SELECT 1 FROM manifest_chunks existing WHERE existing.manifest_id = am.manifest_id
          )
        """,
        [now],
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO manifest_documents (
            manifest_id, doc_id, scope_key, source_kind, source_path, as_of_date, created_at
        )
        SELECT am.manifest_id, d.doc_id, am.scope_key, d.source_kind, d.source_path, d.as_of_date, ?
        FROM active_manifests am
        JOIN source_manifests sm ON sm.manifest_id = am.manifest_id
        JOIN documents d ON d.source_kind = 'evidence_item'
        WHERE sm.source_kind = 'llm_context'
          AND d.active = 1
          AND (
            sm.as_of_date = ''
            OR d.as_of_date = sm.as_of_date
            OR sm.scope_key LIKE 'current:%'
            OR sm.scope_key LIKE 'global:%'
          )
          AND NOT EXISTS (
            SELECT 1
            FROM manifest_documents existing
            JOIN documents existing_doc ON existing_doc.doc_id = existing.doc_id
            WHERE existing.manifest_id = am.manifest_id
              AND existing_doc.source_kind = 'evidence_item'
          )
        """,
        [now],
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO manifest_chunks (
            manifest_id, chunk_id, doc_id, scope_key, created_at
        )
        SELECT md.manifest_id, c.chunk_id, c.doc_id, md.scope_key, ?
        FROM manifest_documents md
        JOIN chunks c ON c.doc_id = md.doc_id
        WHERE c.active = 1
        """,
        [now],
    )


def _as_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "to_dict"):
        return item.to_dict()
    if is_dataclass(item):
        from dataclasses import asdict

        return asdict(item)
    if isinstance(item, dict):
        return dict(item)
    raise TypeError(f"Unsupported RAG store item: {type(item)!r}")


def upsert_documents(agent_home: Path, documents: Iterable[RagDocument | dict[str, Any]]) -> int:
    init_store(agent_home)
    now = timestamp_now()
    count = 0
    with connect_store(agent_home) as conn:
        for item in documents:
            doc = _as_dict(item)
            metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
            scope_key = str(doc.get("scope_key") or metadata.get("scope_key", "") or "")
            conn.execute(
                """
                INSERT INTO documents (
                    doc_id, source_kind, source_path, scope_key, source_record_id, title, summary,
                    as_of_date, event_date, published_at, available_from,
                    entity_type, entity_id, fund_codes_json, domain, status,
                    valid_from, valid_until, source_tier, visibility, learning_scope,
                    is_negative_example, content_sha256, payload_json, metadata_json,
                    active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    source_kind=excluded.source_kind,
                    source_path=excluded.source_path,
                    scope_key=excluded.scope_key,
                    source_record_id=excluded.source_record_id,
                    title=excluded.title,
                    summary=excluded.summary,
                    as_of_date=excluded.as_of_date,
                    event_date=excluded.event_date,
                    published_at=excluded.published_at,
                    available_from=excluded.available_from,
                    entity_type=excluded.entity_type,
                    entity_id=excluded.entity_id,
                    fund_codes_json=excluded.fund_codes_json,
                    domain=excluded.domain,
                    status=excluded.status,
                    valid_from=excluded.valid_from,
                    valid_until=excluded.valid_until,
                    source_tier=excluded.source_tier,
                    visibility=excluded.visibility,
                    learning_scope=excluded.learning_scope,
                    is_negative_example=excluded.is_negative_example,
                    content_sha256=excluded.content_sha256,
                    payload_json=excluded.payload_json,
                    metadata_json=excluded.metadata_json,
                    active=1,
                    updated_at=excluded.updated_at
                """,
                [
                    doc["doc_id"],
                    doc["source_kind"],
                    doc["source_path"],
                    scope_key,
                    doc["source_record_id"],
                    doc["title"],
                    doc["summary"],
                    doc["as_of_date"],
                    doc.get("event_date", ""),
                    doc.get("published_at", ""),
                    doc["available_from"],
                    doc.get("entity_type", ""),
                    doc.get("entity_id", ""),
                    json_dumps(doc.get("fund_codes", [])),
                    doc.get("domain", ""),
                    doc.get("status", ""),
                    doc.get("valid_from", ""),
                    doc.get("valid_until", ""),
                    doc.get("source_tier", ""),
                    doc.get("visibility", "default"),
                    doc.get("learning_scope", ""),
                    1 if doc.get("is_negative_example") else 0,
                    doc["content_sha256"],
                    json_dumps(doc.get("payload", {})),
                    json_dumps(doc.get("metadata", {})),
                    now,
                    now,
                ],
            )
            count += 1
    return count


def upsert_chunks(agent_home: Path, chunks: Iterable[RagChunk | dict[str, Any]]) -> int:
    init_store(agent_home)
    now = timestamp_now()
    count = 0
    with connect_store(agent_home) as conn:
        for item in chunks:
            chunk = _as_dict(item)
            metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
            scope_key = str(chunk.get("scope_key") or metadata.get("scope_key", "") or "")
            conn.execute(
                """
                INSERT INTO chunks (
                    chunk_id, doc_id, scope_key, chunk_index, text_for_embedding, text_for_llm,
                    token_estimate, embedding_model, embedding_status, embedding_sha256,
                    metadata_json, active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    doc_id=excluded.doc_id,
                    scope_key=excluded.scope_key,
                    chunk_index=excluded.chunk_index,
                    text_for_embedding=excluded.text_for_embedding,
                    text_for_llm=excluded.text_for_llm,
                    token_estimate=excluded.token_estimate,
                    embedding_model=excluded.embedding_model,
                    embedding_status=excluded.embedding_status,
                    embedding_sha256=excluded.embedding_sha256,
                    metadata_json=excluded.metadata_json,
                    active=1,
                    updated_at=excluded.updated_at
                """,
                [
                    chunk["chunk_id"],
                    chunk["doc_id"],
                    scope_key,
                    int(chunk["chunk_index"]),
                    chunk["text_for_embedding"],
                    chunk["text_for_llm"],
                    int(chunk.get("token_estimate", 0)),
                    chunk.get("embedding_model", ""),
                    chunk.get("embedding_status", "pending"),
                    chunk.get("embedding_sha256", ""),
                    json_dumps(chunk.get("metadata", {})),
                    now,
                    now,
                ],
            )
            count += 1
    return count


def list_pending_embedding_chunks(agent_home: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        rows = conn.execute(
            """
            SELECT
                c.chunk_id, c.doc_id, c.text_for_embedding, c.embedding_sha256,
                c.embedding_model, c.embedding_status, d.source_kind, d.source_record_id
            FROM chunks c
            JOIN documents d ON d.doc_id = c.doc_id
            WHERE c.active = 1
              AND (c.embedding_status IN ('pending', 'error') OR c.embedding_model = '')
            ORDER BY c.updated_at DESC, c.chunk_id
            LIMIT ?
            """,
            [int(limit)],
        ).fetchall()
    return [dict(row) for row in rows]


def get_embedding_cache(agent_home: Path, cache_key: str) -> dict[str, Any] | None:
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        row = conn.execute("SELECT * FROM embedding_cache WHERE cache_key = ?", [cache_key]).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["error"] = json.loads(item.pop("error_json") or "{}")
    return item


def upsert_embedding_cache(agent_home: Path, entry: dict[str, Any]) -> str:
    init_store(agent_home)
    now = timestamp_now()
    cache_key = str(entry.get("cache_key", "") or "")
    if not cache_key:
        raise ValueError("cache_key is required")
    with connect_store(agent_home) as conn:
        conn.execute(
            """
            INSERT INTO embedding_cache (
                cache_key, chunk_id, embedding_model, text_sha256,
                vector_ref, status, error_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                chunk_id=excluded.chunk_id,
                embedding_model=excluded.embedding_model,
                text_sha256=excluded.text_sha256,
                vector_ref=excluded.vector_ref,
                status=excluded.status,
                error_json=excluded.error_json,
                updated_at=excluded.updated_at
            """,
            [
                cache_key,
                str(entry.get("chunk_id", "")),
                str(entry.get("embedding_model", "")),
                str(entry.get("text_sha256", "")),
                str(entry.get("vector_ref", "")),
                str(entry.get("status", "ok")),
                json_dumps(entry.get("error", {})),
                now,
                now,
            ],
        )
    return cache_key


def upsert_embedding_vector(agent_home: Path, vector_ref: str, vector: list[float]) -> None:
    init_store(agent_home)
    values = [float(value) for value in vector]
    if not vector_ref or not values:
        raise ValueError("vector_ref and vector are required")
    now = timestamp_now()
    with connect_store(agent_home) as conn:
        conn.execute(
            """
            INSERT INTO embedding_vectors(vector_ref, embedding_json, dimensions, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(vector_ref) DO UPDATE SET
                embedding_json=excluded.embedding_json,
                dimensions=excluded.dimensions,
                updated_at=excluded.updated_at
            """,
            [vector_ref, json_dumps(values), len(values), now, now],
        )


def get_embedding_vector(agent_home: Path, vector_ref: str) -> list[float] | None:
    if not vector_ref:
        return None
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        row = conn.execute("SELECT embedding_json FROM embedding_vectors WHERE vector_ref = ?", [vector_ref]).fetchone()
    if row is None:
        return None
    try:
        values = json.loads(row["embedding_json"] or "[]")
        return [float(value) for value in values] if isinstance(values, list) and values else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def list_embedding_vectors(agent_home: Path) -> dict[str, list[float]]:
    """Load persisted local vectors for the mock backend without an external service."""
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        rows = conn.execute("SELECT vector_ref, embedding_json FROM embedding_vectors ORDER BY vector_ref").fetchall()
    vectors: dict[str, list[float]] = {}
    for row in rows:
        try:
            values = json.loads(row["embedding_json"] or "[]")
            if isinstance(values, list) and values:
                vectors[str(row["vector_ref"])] = [float(value) for value in values]
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return vectors


def get_chunk_embedding_vector(agent_home: Path, chunk_id: str, *, model: str = "") -> list[float] | None:
    init_store(agent_home)
    clauses = ["chunk_id = ?", "status = 'ok'", "vector_ref <> ''"]
    params: list[Any] = [chunk_id]
    if model:
        clauses.append("embedding_model = ?")
        params.append(model)
    with connect_store(agent_home) as conn:
        row = conn.execute(
            f"SELECT vector_ref FROM embedding_cache WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT 1",
            params,
        ).fetchone()
    return get_embedding_vector(agent_home, str(row["vector_ref"] or "")) if row else None


def mark_chunk_embedding(agent_home: Path, chunk_id: str, *, model: str, status: str, embedding_sha256: str = "") -> None:
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        conn.execute(
            """
            UPDATE chunks
            SET embedding_model = ?, embedding_status = ?, embedding_sha256 = ?, updated_at = ?
            WHERE chunk_id = ?
            """,
            [model, status, embedding_sha256, timestamp_now(), chunk_id],
        )


def _replace_manifest_membership(
    conn: sqlite3.Connection,
    *,
    manifest_id: str,
    scope_key: str,
    document_ids: Iterable[str],
    chunk_ids: Iterable[str],
) -> None:
    now = timestamp_now()
    doc_ids = [str(item) for item in document_ids if str(item)]
    chunk_id_list = [str(item) for item in chunk_ids if str(item)]
    conn.execute("DELETE FROM manifest_documents WHERE manifest_id = ?", [manifest_id])
    conn.execute("DELETE FROM manifest_chunks WHERE manifest_id = ?", [manifest_id])
    if doc_ids:
        placeholders = ",".join("?" for _ in doc_ids)
        conn.execute(
            f"""
            INSERT OR IGNORE INTO manifest_documents (
                manifest_id, doc_id, scope_key, source_kind, source_path, as_of_date, created_at
            )
            SELECT ?, doc_id, ?, source_kind, source_path, as_of_date, ?
            FROM documents
            WHERE doc_id IN ({placeholders})
            """,
            [manifest_id, scope_key, now, *doc_ids],
        )
    if chunk_id_list:
        placeholders = ",".join("?" for _ in chunk_id_list)
        conn.execute(
            f"""
            INSERT OR IGNORE INTO manifest_chunks (
                manifest_id, chunk_id, doc_id, scope_key, created_at
            )
            SELECT ?, chunk_id, doc_id, ?, ?
            FROM chunks
            WHERE chunk_id IN ({placeholders})
            """,
            [manifest_id, scope_key, now, *chunk_id_list],
        )


def deactivate_missing_scope(agent_home: Path, scope_key: str, *, document_ids: Iterable[str], chunk_ids: Iterable[str]) -> dict[str, int]:
    clean_scope = str(scope_key or "").strip()
    if not clean_scope:
        return {"documents": 0, "chunks": 0}
    init_store(agent_home)
    now = timestamp_now()
    doc_ids = [str(item) for item in document_ids if str(item)]
    chunk_id_list = [str(item) for item in chunk_ids if str(item)]
    with connect_store(agent_home) as conn:
        if doc_ids:
            placeholders = ",".join("?" for _ in doc_ids)
            doc_cursor = conn.execute(
                f"UPDATE documents SET active = 0, updated_at = ? WHERE scope_key = ? AND doc_id NOT IN ({placeholders})",
                [now, clean_scope, *doc_ids],
            )
        else:
            doc_cursor = conn.execute("UPDATE documents SET active = 0, updated_at = ? WHERE scope_key = ?", [now, clean_scope])
        if chunk_id_list:
            placeholders = ",".join("?" for _ in chunk_id_list)
            chunk_cursor = conn.execute(
                f"UPDATE chunks SET active = 0, updated_at = ? WHERE scope_key = ? AND chunk_id NOT IN ({placeholders})",
                [now, clean_scope, *chunk_id_list],
            )
        else:
            chunk_cursor = conn.execute("UPDATE chunks SET active = 0, updated_at = ? WHERE scope_key = ?", [now, clean_scope])
    return {"documents": int(doc_cursor.rowcount or 0), "chunks": int(chunk_cursor.rowcount or 0)}


def write_manifest(
    agent_home: Path,
    manifest: dict[str, Any],
    *,
    activate: bool = True,
    document_ids: Iterable[str] | None = None,
    chunk_ids: Iterable[str] | None = None,
) -> str:
    init_store(agent_home)
    now = timestamp_now()
    manifest_id = str(manifest.get("manifest_id") or f"manifest:{manifest.get('source_kind', 'unknown')}:{now}")
    source_kind = str(manifest.get("source_kind", ""))
    source_path = str(manifest.get("source_path", ""))
    scope_key = str(manifest.get("scope_key") or f"global:{source_kind}:{source_path}")
    if not source_kind or not source_path:
        raise ValueError("manifest source_kind and source_path are required")
    with connect_store(agent_home) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO source_manifests (
                manifest_id, scope_key, source_kind, source_path, as_of_date, status,
                doc_count, chunk_count, error_json, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                manifest_id,
                scope_key,
                source_kind,
                source_path,
                str(manifest.get("as_of_date", "")),
                str(manifest.get("status", "ok")),
                int(manifest.get("doc_count", 0)),
                int(manifest.get("chunk_count", 0)),
                json_dumps(manifest.get("error", {})),
                json_dumps(manifest.get("payload", {})),
                now,
            ],
        )
        if activate:
            conn.execute(
                """
                INSERT INTO active_manifests (scope_key, manifest_id, activated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(scope_key) DO UPDATE SET
                    manifest_id=excluded.manifest_id,
                    activated_at=excluded.activated_at
                """,
                [scope_key, manifest_id, now],
            )
        if document_ids is not None or chunk_ids is not None:
            _replace_manifest_membership(
                conn,
                manifest_id=manifest_id,
                scope_key=scope_key,
                document_ids=document_ids or [],
                chunk_ids=chunk_ids or [],
            )
    return manifest_id


def write_trace(agent_home: Path, trace: RagTrace | dict[str, Any]) -> str:
    init_store(agent_home)
    payload = _as_dict(trace)
    trace_id = str(payload.get("trace_id", "") or "")
    if not trace_id:
        raise ValueError("trace_id is required")
    with connect_store(agent_home) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO query_traces (
                trace_id, query_plan_json, hits_json, rejected_samples_json,
                missing_data_json, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                trace_id,
                json_dumps(payload.get("query_plan", {})),
                json_dumps(payload.get("hits", [])),
                json_dumps(payload.get("rejected_samples", [])),
                json_dumps(payload.get("missing_data", [])),
                json_dumps(payload.get("metadata", {})),
                payload.get("created_at") or timestamp_now(),
            ],
        )
    return trace_id


def count_rows(agent_home: Path, table_name: str) -> int:
    if table_name not in {
        "documents",
        "chunks",
        "source_manifests",
        "active_manifests",
        "manifest_documents",
        "manifest_chunks",
        "embedding_cache",
        "embedding_vectors",
        "query_traces",
        "ingest_runs",
    }:
        raise ValueError(f"Unsupported table: {table_name}")
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def write_ingest_run(agent_home: Path, run: dict[str, Any]) -> str:
    init_store(agent_home)
    now = timestamp_now()
    run_id = str(run.get("run_id") or f"rag-ingest:{now}")
    with connect_store(agent_home) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO ingest_runs (
                run_id, status, as_of_date, source_count, doc_count,
                chunk_count, error_json, started_at, ended_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                str(run.get("status", "ok")),
                str(run.get("as_of_date", "")),
                int(run.get("source_count", 0)),
                int(run.get("doc_count", 0)),
                int(run.get("chunk_count", 0)),
                json_dumps(run.get("error", {})),
                str(run.get("started_at", now)),
                str(run.get("ended_at", now)),
            ],
        )
    return run_id
