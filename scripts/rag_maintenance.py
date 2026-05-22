from __future__ import annotations

import argparse
from contextlib import suppress
import json
from pathlib import Path
from typing import Any

from common import load_json, resolve_agent_home, timestamp_now
from rag_config import load_rag_config, rag_db_path, rag_eval_dir
from rag_index_store import connect_store, init_store
from rag_ingest import build_parser as build_ingest_parser, run_ingest


TABLES = {
    "documents",
    "chunks",
    "source_manifests",
    "active_manifests",
    "manifest_documents",
    "manifest_chunks",
    "embedding_cache",
    "query_traces",
    "ingest_runs",
}


def _table_count(agent_home: Path, table_name: str) -> int:
    if table_name not in TABLES:
        raise ValueError(f"Unsupported table: {table_name}")
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"] if row else 0)


def _group_counts(agent_home: Path, sql: str) -> dict[str, int]:
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        rows = conn.execute(sql).fetchall()
    return {str(row[0] or ""): int(row[1] or 0) for row in rows}


def _latest_rows(agent_home: Path, sql: str, limit: int = 10) -> list[dict[str, Any]]:
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        rows = conn.execute(sql, [limit]).fetchall()
    return [dict(row) for row in rows]


def _latest_eval(agent_home: Path) -> dict[str, Any]:
    base = rag_eval_dir(agent_home)
    if not base.exists():
        return {}
    files = sorted(base.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files:
        with suppress(Exception):
            payload = load_json(path)
            if isinstance(payload, dict):
                return {
                    "path": str(path),
                    "report_date": payload.get("report_date", path.stem),
                    "generated_at": payload.get("generated_at", ""),
                    "metrics": payload.get("metrics", {}),
                    "legacy": payload.get("legacy", {}),
                    "rag": payload.get("rag", {}),
                }
    return {}


def rag_status(agent_home: Path) -> dict[str, Any]:
    config = load_rag_config(agent_home)
    settings = config.get("rag", {}) or {}
    db_path = rag_db_path(agent_home, config)
    exists = db_path.exists()
    counts = {name: 0 for name in sorted(TABLES)}
    if exists:
        for table_name in counts:
            with suppress(Exception):
                counts[table_name] = _table_count(agent_home, table_name)
    source_counts = _group_counts(agent_home, "SELECT source_kind, COUNT(*) FROM documents WHERE active = 1 GROUP BY source_kind ORDER BY source_kind") if exists else {}
    embedding_status = _group_counts(agent_home, "SELECT embedding_status, COUNT(*) FROM chunks WHERE active = 1 GROUP BY embedding_status ORDER BY embedding_status") if exists else {}
    latest_ingest = _latest_rows(
        agent_home,
        "SELECT run_id, status, as_of_date, source_count, doc_count, chunk_count, started_at, ended_at FROM ingest_runs ORDER BY started_at DESC LIMIT ?",
    )
    latest_traces = _latest_rows(
        agent_home,
        "SELECT trace_id, created_at, query_plan_json, missing_data_json, metadata_json FROM query_traces ORDER BY created_at DESC LIMIT ?",
    )
    active_manifests = _latest_rows(
        agent_home,
        "SELECT scope_key, manifest_id, activated_at FROM active_manifests ORDER BY scope_key LIMIT ?",
        limit=50,
    )
    return {
        "generatedAt": timestamp_now(),
        "enabled": bool(settings.get("enabled", False)),
        "defaultProfile": str(settings.get("default_profile", "") or ""),
        "fallbackToLegacy": bool(settings.get("fallback_to_legacy", True)),
        "traceEnabled": bool(settings.get("trace_enabled", True)),
        "agentShadow": settings.get("agent_shadow", {}) or {},
        "agentDefault": settings.get("agent_default", {}) or {},
        "profileEvidence": settings.get("profile_evidence", {}) or {},
        "embedding": settings.get("embedding", {}) or {},
        "vectorStore": settings.get("vector_store", {}) or {},
        "dbPath": str(db_path),
        "dbExists": exists,
        "counts": counts,
        "sourceCounts": source_counts,
        "embeddingStatus": embedding_status,
        "latestIngestRuns": latest_ingest,
        "latestTraces": latest_traces,
        "activeManifests": active_manifests,
        "latestEval": _latest_eval(agent_home),
    }


def rag_trace(agent_home: Path, trace_id: str) -> dict[str, Any]:
    if not trace_id:
        raise ValueError("trace id is required")
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        row = conn.execute("SELECT * FROM query_traces WHERE trace_id = ?", [trace_id]).fetchone()
    if not row:
        return {"traceId": trace_id, "found": False}
    payload = dict(row)
    return {
        "traceId": trace_id,
        "found": True,
        "createdAt": payload.get("created_at", ""),
        "queryPlan": json.loads(payload.get("query_plan_json") or "{}"),
        "hits": json.loads(payload.get("hits_json") or "[]"),
        "rejectedSamples": json.loads(payload.get("rejected_samples_json") or "[]"),
        "missingData": json.loads(payload.get("missing_data_json") or "[]"),
        "metadata": json.loads(payload.get("metadata_json") or "{}"),
    }


def check_integrity(agent_home: Path) -> dict[str, Any]:
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
        active_without_chunk_membership = [
            dict(row)
            for row in conn.execute(
                """
                SELECT am.scope_key, am.manifest_id
                FROM active_manifests am
                JOIN source_manifests sm ON sm.manifest_id = am.manifest_id
                WHERE sm.status = 'ok'
                  AND sm.chunk_count > 0
                  AND NOT EXISTS (
                    SELECT 1 FROM manifest_chunks mc WHERE mc.manifest_id = am.manifest_id
                  )
                ORDER BY am.scope_key
                """
            ).fetchall()
        ]
        active_with_leaked_chunks = [
            dict(row)
            for row in conn.execute(
                """
                SELECT am.scope_key, am.manifest_id, c.chunk_id
                FROM active_manifests am
                JOIN manifest_chunks mc ON mc.manifest_id = am.manifest_id
                JOIN chunks c ON c.chunk_id = mc.chunk_id
                JOIN documents d ON d.doc_id = c.doc_id
                WHERE c.active = 1
                  AND d.active = 1
                  AND d.scope_key <> ''
                  AND d.scope_key <> am.scope_key
                LIMIT 20
                """
            ).fetchall()
        ]
    checks = [str(row[0]) for row in rows]
    ok = checks == ["ok"] and not active_without_chunk_membership and not active_with_leaked_chunks
    return {
        "ok": ok,
        "checks": checks,
        "activeWithoutChunkMembership": active_without_chunk_membership,
        "activeWithLeakedChunks": active_with_leaked_chunks,
    }


def vacuum(agent_home: Path) -> dict[str, Any]:
    init_store(agent_home)
    db_path = rag_db_path(agent_home)
    before = db_path.stat().st_size if db_path.exists() else 0
    with connect_store(agent_home) as conn:
        conn.execute("VACUUM")
    after = db_path.stat().st_size if db_path.exists() else 0
    return {"ok": True, "beforeBytes": before, "afterBytes": after}


def rebuild_domain(agent_home: Path, domain: str, *, report_date: str = "", embed: bool = False, embedding_dry_run: bool = True) -> dict[str, Any]:
    if not domain:
        raise ValueError("domain is required")
    args_list = ["--domain", domain, "--write"]
    if report_date:
        args_list.extend(["--date", report_date])
    if embed:
        args_list.append("--embed")
    if embedding_dry_run:
        args_list.append("--embedding-dry-run")
    args = build_ingest_parser().parse_args(args_list)
    result = run_ingest(agent_home, args)
    result["ok"] = True
    result["maintenanceAction"] = "rebuild"
    return result


def purge_domain(agent_home: Path, domain: str) -> dict[str, Any]:
    if not domain:
        raise ValueError("domain is required")
    init_store(agent_home)
    with connect_store(agent_home) as conn:
        doc_rows = conn.execute("SELECT doc_id FROM documents WHERE source_kind = ? OR domain = ?", [domain, domain]).fetchall()
        doc_ids = [str(row["doc_id"]) for row in doc_rows]
        if doc_ids:
            placeholders = ",".join("?" for _ in doc_ids)
            conn.execute(f"UPDATE chunks SET active = 0, updated_at = ? WHERE doc_id IN ({placeholders})", [timestamp_now(), *doc_ids])
            conn.execute(f"UPDATE documents SET active = 0, updated_at = ? WHERE doc_id IN ({placeholders})", [timestamp_now(), *doc_ids])
        manifest_rows = conn.execute("SELECT manifest_id FROM source_manifests WHERE source_kind = ? OR scope_key LIKE ?", [domain, f"%:{domain}:%"]).fetchall()
        manifest_ids = [str(row["manifest_id"]) for row in manifest_rows]
        if manifest_ids:
            placeholders = ",".join("?" for _ in manifest_ids)
            conn.execute(f"DELETE FROM active_manifests WHERE manifest_id IN ({placeholders})", manifest_ids)
            conn.execute(f"DELETE FROM manifest_chunks WHERE manifest_id IN ({placeholders})", manifest_ids)
            conn.execute(f"DELETE FROM manifest_documents WHERE manifest_id IN ({placeholders})", manifest_ids)
    return {
        "ok": True,
        "domain": domain,
        "deactivatedDocuments": len(doc_ids),
        "deactivatedManifests": len(manifest_ids),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and maintain OKRA RAG index artifacts.")
    parser.add_argument("--agent-home", default=None)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--check-integrity", action="store_true")
    parser.add_argument("--vacuum", action="store_true")
    parser.add_argument("--trace", default="")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--purge-domain", default="")
    parser.add_argument("--domain", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--embed", action="store_true")
    parser.add_argument("--embedding-dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    if args.check_integrity:
        payload = check_integrity(agent_home)
    elif args.vacuum:
        payload = vacuum(agent_home)
    elif args.trace:
        payload = rag_trace(agent_home, args.trace)
    elif args.rebuild:
        payload = rebuild_domain(agent_home, args.domain, report_date=args.date, embed=bool(args.embed), embedding_dry_run=bool(args.embedding_dry_run))
    elif args.purge_domain:
        payload = purge_domain(agent_home, args.purge_domain)
    else:
        payload = rag_status(agent_home)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
