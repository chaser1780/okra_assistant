from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import uuid

from common import resolve_agent_home, timestamp_now
from rag_embedding_client import RagEmbeddingClient
from rag_index_store import deactivate_missing_scope, list_pending_embedding_chunks, upsert_chunks, upsert_documents, write_ingest_run, write_manifest
from rag_sources import DATE_REQUIRED_SOURCES, DEFAULT_SOURCES, RagSourceBundle, collect_source


def _date_range(start: str, end: str) -> list[str]:
    start_day = date.fromisoformat(start)
    end_day = date.fromisoformat(end)
    if start_day > end_day:
        raise ValueError("--date-from must be <= --date-to")
    values = []
    current = start_day
    while current <= end_day:
        values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def _selected_domains(args: argparse.Namespace) -> list[str]:
    if args.all:
        return list(DEFAULT_SOURCES)
    domains = list(args.domain or [])
    return domains


def _source_dates(domain: str, args: argparse.Namespace) -> list[str | None]:
    if args.all_dates:
        if domain in DATE_REQUIRED_SOURCES:
            return _date_range(args.date_from, args.date_to)
        return [args.date or None]
    if args.date:
        return [args.date]
    if domain in DATE_REQUIRED_SOURCES:
        return [None]
    return [None]


def _manifest_for_bundle(bundle: RagSourceBundle) -> dict:
    summary = bundle.summary()
    manifest_id = f"manifest:{summary['scope_key']}:{uuid.uuid4().hex[:12]}"
    return {
        "manifest_id": manifest_id,
        "scope_key": summary["scope_key"],
        "source_kind": bundle.source_kind,
        "source_path": bundle.source_path or bundle.domain,
        "as_of_date": bundle.as_of_date,
        "status": bundle.status,
        "doc_count": len(bundle.documents),
        "chunk_count": len(bundle.chunks),
        "error": {"errors": bundle.errors, "missing_data": bundle.missing_data, "skipped_reason": bundle.skipped_reason},
        "payload": {"summary": summary},
    }


def _stamp_bundle_scope(bundle: RagSourceBundle, scope_key: str) -> None:
    for doc in bundle.documents:
        doc.metadata["scope_key"] = scope_key
    for chunk in bundle.chunks:
        chunk.metadata["scope_key"] = scope_key


def run_ingest(agent_home: Path, args: argparse.Namespace) -> dict:
    domains = _selected_domains(args)
    if not domains:
        raise SystemExit("Use --all or at least one --domain")
    if args.all_dates and (not args.date_from or not args.date_to):
        raise SystemExit("--all-dates requires --date-from and --date-to")
    started_at = timestamp_now()
    bundles: list[RagSourceBundle] = []
    for domain in domains:
        for report_date in _source_dates(domain, args):
            if domain in DATE_REQUIRED_SOURCES and not report_date:
                bundles.append(
                    RagSourceBundle(
                        domain=domain,
                        source_kind=domain,
                        source_path=domain,
                        skipped_reason="date_required",
                    )
                )
                continue
            bundles.append(collect_source(agent_home, domain, report_date))

    manifests = [_manifest_for_bundle(bundle) for bundle in bundles]
    wrote = False
    deactivated: list[dict] = []
    if args.write:
        for bundle, manifest in zip(bundles, manifests):
            scope_key = str(manifest.get("scope_key") or "")
            _stamp_bundle_scope(bundle, scope_key)
            if bundle.documents:
                upsert_documents(agent_home, bundle.documents)
            if bundle.chunks:
                upsert_chunks(agent_home, bundle.chunks)
            doc_ids = [doc.doc_id for doc in bundle.documents]
            chunk_ids = [chunk.chunk_id for chunk in bundle.chunks]
            deactivation = deactivate_missing_scope(agent_home, scope_key, document_ids=doc_ids, chunk_ids=chunk_ids)
            if deactivation["documents"] or deactivation["chunks"]:
                deactivated.append({"scope_key": scope_key, **deactivation})
            write_manifest(agent_home, manifest, activate=bundle.status in {"ok", "missing"}, document_ids=doc_ids, chunk_ids=chunk_ids)
        embedding_summary = None
        if args.embed:
            client = RagEmbeddingClient(agent_home)
            pending = list_pending_embedding_chunks(agent_home, limit=args.embed_limit)
            results = [client.embed_chunk_with_cache(chunk, dry_run=args.embedding_dry_run) for chunk in pending]
            embedding_summary = {
                "requested": len(pending),
                "embedded": sum(1 for item in results if item.get("status") == "embedded"),
                "cached": sum(1 for item in results if item.get("status") == "cached"),
                "error": sum(1 for item in results if item.get("status") == "error"),
                "results": results,
            }
        write_ingest_run(
            agent_home,
            {
                "run_id": f"rag-ingest:{uuid.uuid4().hex}",
                "status": "error" if any(bundle.errors for bundle in bundles) else "ok",
                "as_of_date": args.date or args.date_to or "",
                "source_count": len(bundles),
                "doc_count": sum(len(bundle.documents) for bundle in bundles),
                "chunk_count": sum(len(bundle.chunks) for bundle in bundles),
                "error": {
                    "bundles": [bundle.summary() for bundle in bundles if bundle.errors or bundle.missing_data or bundle.skipped_reason],
                    "embedding": embedding_summary or {},
                },
                "started_at": started_at,
                "ended_at": timestamp_now(),
            },
        )
        wrote = True

    return {
        "mode": "write" if args.write else "dry_run",
        "wrote": wrote,
        "agent_home": str(agent_home),
        "date": args.date,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "domains": domains,
        "summary": {
            "source_count": len(bundles),
            "doc_count": sum(len(bundle.documents) for bundle in bundles),
            "chunk_count": sum(len(bundle.chunks) for bundle in bundles),
            "missing_count": sum(len(bundle.missing_data) for bundle in bundles),
            "error_count": sum(len(bundle.errors) for bundle in bundles),
            "skipped_count": sum(1 for bundle in bundles if bundle.skipped_reason),
        },
        "sources": [bundle.summary() for bundle in bundles],
        "manifests": [{"manifest_id": item["manifest_id"], "scope_key": item["scope_key"], "status": item["status"]} for item in manifests],
        "deactivated": deactivated,
        "embedding": embedding_summary if args.write and args.embed else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build OKRA RAG source documents.")
    parser.add_argument("--agent-home", default=None)
    parser.add_argument("--date", default="")
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    parser.add_argument("--all-dates", action="store_true")
    parser.add_argument("--domain", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--embed", action="store_true")
    parser.add_argument("--embedding-dry-run", action="store_true")
    parser.add_argument("--embed-limit", type=int, default=200)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.dry_run and args.write:
        raise SystemExit("--dry-run and --write are mutually exclusive")
    agent_home = resolve_agent_home(args.agent_home)
    result = run_ingest(agent_home, args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
