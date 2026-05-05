from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from common import (
    dump_json,
    ensure_layout,
    long_memory_db_path,
    long_memory_dir,
    long_memory_index_path,
    load_json,
    load_portfolio,
    load_review_memory,
    review_memory_ledger_path,
    review_memory_path,
    timestamp_now,
)


SCHEMA_VERSION = 1
ACTIVE_STATUSES = {"candidate", "strategic", "permanent"}
PERMANENT_REQUIRES_APPROVAL = True
PERMANENT_ELIGIBLE_DOMAINS = {"market", "execution", "portfolio"}
PERMANENT_ELIGIBLE_MEMORY_TYPES = {"market_regime_memory", "execution_memory", "portfolio_policy_memory"}


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    return conn


def init_long_memory(agent_home: Path) -> None:
    ensure_layout(agent_home)
    with _connect(long_memory_db_path(agent_home)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_records (
                memory_id TEXT PRIMARY KEY,
                memory_type TEXT NOT NULL,
                domain TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.0,
                support_count INTEGER NOT NULL DEFAULT 0,
                contradiction_count INTEGER NOT NULL DEFAULT 0,
                last_supported_at TEXT NOT NULL DEFAULT '',
                last_contradicted_at TEXT NOT NULL DEFAULT '',
                approved_by TEXT NOT NULL DEFAULT '',
                approved_at TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_approvals (
                approval_id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                action TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                actor TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_evidence_refs (
                memory_id TEXT NOT NULL,
                evidence_ref TEXT NOT NULL,
                evidence_kind TEXT NOT NULL DEFAULT '',
                evidence_date TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                PRIMARY KEY(memory_id, evidence_ref)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_domain_entity ON memory_records(domain, entity_key)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_status ON memory_records(status)")
    init_search_index(agent_home)


def init_search_index(agent_home: Path) -> None:
    with _connect(long_memory_index_path(agent_home)) as conn:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                memory_id UNINDEXED,
                domain,
                entity_key,
                title,
                text,
                tags
            )
            """
        )


def stable_memory_id(domain: str, entity_key: str, title: str, memory_type: str) -> str:
    import hashlib

    digest = hashlib.sha1(f"{domain}|{entity_key}|{memory_type}|{title}".encode("utf-8")).hexdigest()[:12]
    return f"{domain}:{entity_key}:{digest}".replace("/", "_").replace("\\", "_").replace(":", ":", 2)


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
    item["evidence_refs"] = json.loads(item.pop("evidence_refs_json") or "[]")
    item["can_promote_permanent"] = can_promote_to_permanent(item)
    return item


def can_promote_to_permanent(record: dict[str, Any]) -> bool:
    domain = str(record.get("domain", "") or "").strip()
    memory_type = str(record.get("memory_type", "") or "").strip()
    if domain == "fund" or memory_type == "fund_profile_memory":
        return False
    return domain in PERMANENT_ELIGIBLE_DOMAINS or memory_type in PERMANENT_ELIGIBLE_MEMORY_TYPES


def list_memory_records(
    agent_home: Path,
    *,
    domain: str | None = None,
    status: str | None = None,
    entity_key: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    init_long_memory(agent_home)
    clauses: list[str] = []
    params: list[Any] = []
    if domain:
        clauses.append("domain = ?")
        params.append(domain)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if entity_key:
        clauses.append("entity_key = ?")
        params.append(entity_key)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(long_memory_db_path(agent_home)) as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM memory_records
            {where}
            ORDER BY
                CASE status WHEN 'permanent' THEN 3 WHEN 'strategic' THEN 2 WHEN 'candidate' THEN 1 ELSE 0 END DESC,
                confidence DESC,
                updated_at DESC
            LIMIT ?
            """,
            [*params, int(limit)],
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def upsert_memory_record(agent_home: Path, record: dict[str, Any]) -> dict[str, Any]:
    init_long_memory(agent_home)
    now = timestamp_now()
    memory_id = str(record.get("memory_id", "") or "").strip()
    if not memory_id:
        memory_id = stable_memory_id(
            str(record.get("domain", "")),
            str(record.get("entity_key", "")),
            str(record.get("title", "")),
            str(record.get("memory_type", "")),
        )
    status = str(record.get("status", "candidate") or "candidate")
    approved_by = str(record.get("approved_by", "") or "")
    approved_at = str(record.get("approved_at", "") or "")
    if status == "permanent" and PERMANENT_REQUIRES_APPROVAL and not approved_by:
        status = "strategic"
        approved_at = ""
    normalized = {
        "memory_id": memory_id,
        "memory_type": str(record.get("memory_type", "semantic") or "semantic"),
        "domain": str(record.get("domain", "") or ""),
        "entity_key": str(record.get("entity_key", "") or ""),
        "title": str(record.get("title", "") or ""),
        "text": str(record.get("text", "") or ""),
        "status": status,
        "priority": str(record.get("priority", "") or ""),
        "confidence": float(record.get("confidence", 0.0) or 0.0),
        "support_count": int(record.get("support_count", 0) or 0),
        "contradiction_count": int(record.get("contradiction_count", 0) or 0),
        "last_supported_at": str(record.get("last_supported_at", "") or ""),
        "last_contradicted_at": str(record.get("last_contradicted_at", "") or ""),
        "approved_by": approved_by if status == "permanent" else "",
        "approved_at": approved_at if status == "permanent" else "",
        "source": str(record.get("source", "") or ""),
        "metadata": dict(record.get("metadata", {}) or {}),
        "evidence_refs": list(record.get("evidence_refs", []) or []),
        "created_at": str(record.get("created_at", "") or now),
        "updated_at": now,
    }
    normalized["can_promote_permanent"] = can_promote_to_permanent(normalized)
    with _connect(long_memory_db_path(agent_home)) as conn:
        existing = conn.execute("SELECT created_at, approved_by, approved_at, status FROM memory_records WHERE memory_id = ?", (memory_id,)).fetchone()
        if existing:
            normalized["created_at"] = existing["created_at"] or normalized["created_at"]
            if normalized["status"] != "permanent" and existing["status"] == "permanent":
                normalized["status"] = "permanent"
                normalized["approved_by"] = existing["approved_by"]
                normalized["approved_at"] = existing["approved_at"]
        conn.execute(
            """
            INSERT INTO memory_records (
                memory_id, memory_type, domain, entity_key, title, text, status, priority,
                confidence, support_count, contradiction_count, last_supported_at, last_contradicted_at,
                approved_by, approved_at, source, metadata_json, evidence_refs_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(memory_id) DO UPDATE SET
                memory_type=excluded.memory_type,
                domain=excluded.domain,
                entity_key=excluded.entity_key,
                title=excluded.title,
                text=excluded.text,
                status=excluded.status,
                priority=excluded.priority,
                confidence=excluded.confidence,
                support_count=excluded.support_count,
                contradiction_count=excluded.contradiction_count,
                last_supported_at=excluded.last_supported_at,
                last_contradicted_at=excluded.last_contradicted_at,
                approved_by=excluded.approved_by,
                approved_at=excluded.approved_at,
                source=excluded.source,
                metadata_json=excluded.metadata_json,
                evidence_refs_json=excluded.evidence_refs_json,
                updated_at=excluded.updated_at
            """,
            (
                normalized["memory_id"],
                normalized["memory_type"],
                normalized["domain"],
                normalized["entity_key"],
                normalized["title"],
                normalized["text"],
                normalized["status"],
                normalized["priority"],
                normalized["confidence"],
                normalized["support_count"],
                normalized["contradiction_count"],
                normalized["last_supported_at"],
                normalized["last_contradicted_at"],
                normalized["approved_by"],
                normalized["approved_at"],
                normalized["source"],
                _json_dumps(normalized["metadata"]),
                _json_dumps(normalized["evidence_refs"]),
                normalized["created_at"],
                normalized["updated_at"],
            ),
        )
        for ref in normalized["evidence_refs"]:
            if isinstance(ref, dict):
                ref_text = str(ref.get("path") or ref.get("id") or ref.get("ref") or "")
                kind = str(ref.get("kind", "") or "")
                evidence_date = str(ref.get("date", "") or ref.get("base_date", "") or "")
            else:
                ref_text = str(ref)
                kind = ""
                evidence_date = ""
            if ref_text:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO memory_evidence_refs(memory_id, evidence_ref, evidence_kind, evidence_date, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (normalized["memory_id"], ref_text, kind, evidence_date, now),
                )
    sync_search_index(agent_home, normalized)
    write_domain_mirrors(agent_home)
    return normalized


def sync_search_index(agent_home: Path, record: dict[str, Any]) -> None:
    init_search_index(agent_home)
    tags = " ".join(
        [
            str(record.get("memory_type", "")),
            str(record.get("status", "")),
            str(record.get("priority", "")),
            " ".join(str(x) for x in (record.get("metadata", {}) or {}).get("tags", []) or []),
        ]
    )
    with _connect(long_memory_index_path(agent_home)) as conn:
        conn.execute("DELETE FROM memory_fts WHERE memory_id = ?", (record["memory_id"],))
        if record.get("status") in ACTIVE_STATUSES:
            conn.execute(
                "INSERT INTO memory_fts(memory_id, domain, entity_key, title, text, tags) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.get("memory_id", ""),
                    record.get("domain", ""),
                    record.get("entity_key", ""),
                    record.get("title", ""),
                    record.get("text", ""),
                    tags,
                ),
            )


def search_long_memory(agent_home: Path, query: str, *, limit: int = 12) -> list[dict[str, Any]]:
    init_long_memory(agent_home)
    text = str(query or "").strip()
    if not text:
        return list_memory_records(agent_home, limit=limit)
    with _connect(long_memory_index_path(agent_home)) as index_conn:
        try:
            rows = index_conn.execute(
                """
                SELECT memory_id, bm25(memory_fts) AS rank
                FROM memory_fts
                WHERE memory_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (text, int(limit)),
            ).fetchall()
        except sqlite3.OperationalError:
            safe = " OR ".join(part for part in text.replace("'", " ").split() if part)
            if not safe:
                return []
            rows = index_conn.execute(
                "SELECT memory_id, bm25(memory_fts) AS rank FROM memory_fts WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
                (safe, int(limit)),
            ).fetchall()
    ids = [row["memory_id"] for row in rows]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with _connect(long_memory_db_path(agent_home)) as conn:
        record_rows = conn.execute(f"SELECT * FROM memory_records WHERE memory_id IN ({placeholders})", ids).fetchall()
    by_id = {row["memory_id"]: _row_to_record(row) for row in record_rows}
    return [by_id[item] for item in ids if item in by_id]


def approve_memory(agent_home: Path, memory_id: str, *, action: str, note: str = "", actor: str = "user") -> dict[str, Any]:
    init_long_memory(agent_home)
    now = timestamp_now()
    action = str(action or "").strip().lower()
    if action not in {"approve", "reject", "archive", "demote"}:
        raise ValueError(f"Unsupported approval action: {action}")
    with _connect(long_memory_db_path(agent_home)) as conn:
        row = conn.execute("SELECT * FROM memory_records WHERE memory_id = ?", (memory_id,)).fetchone()
        if not row:
            raise FileNotFoundError(f"Memory record not found: {memory_id}")
        current = _row_to_record(row)
        if action == "approve" and not can_promote_to_permanent(current):
            raise ValueError(
                "基金画像和单基金学习记录不能确认为永久规则；请保留为长期画像，"
                "或将可复用内容抽象为组合、执行或大盘策略规则后再确认。"
            )
        next_status = {
            "approve": "permanent",
            "reject": "rejected",
            "archive": "archived",
            "demote": "candidate",
        }[action]
        approved_by = actor if action == "approve" else ""
        approved_at = now if action == "approve" else ""
        current_metadata = dict(current.get("metadata", {}) or {})
        superseded_ids: list[str] = []
        superseded_records: list[dict[str, Any]] = []
        if action == "approve":
            previous_rows = conn.execute(
                """
                SELECT * FROM memory_records
                WHERE domain = ? AND entity_key = ? AND memory_type = ? AND status = 'permanent' AND memory_id <> ?
                """,
                (current.get("domain", ""), current.get("entity_key", ""), current.get("memory_type", ""), memory_id),
            ).fetchall()
            for previous_row in previous_rows:
                previous = _row_to_record(previous_row)
                superseded_ids.append(previous["memory_id"])
                previous_metadata = dict(previous.get("metadata", {}) or {})
                previous_metadata["superseded_by"] = memory_id
                previous_metadata["superseded_at"] = now
                previous_metadata["superseded_reason"] = note or "replaced_by_newer_strategy"
                previous["status"] = "archived"
                previous["metadata"] = previous_metadata
                previous["updated_at"] = now
                previous["can_promote_permanent"] = can_promote_to_permanent(previous)
                conn.execute(
                    """
                    UPDATE memory_records
                    SET status='archived', metadata_json=?, updated_at=?
                    WHERE memory_id=?
                    """,
                    (_json_dumps(previous_metadata), now, previous["memory_id"]),
                )
                superseded_records.append(previous)
        conn.execute(
            """
            UPDATE memory_records
            SET status=?, approved_by=?, approved_at=?, metadata_json=?, updated_at=?
            WHERE memory_id=?
            """,
            (
                next_status,
                approved_by,
                approved_at,
                _json_dumps({**current_metadata, "supersedes": superseded_ids, "version_state": "current" if action == "approve" else current_metadata.get("version_state", "")}),
                now,
                memory_id,
            ),
        )
        approval_id = f"{memory_id}:{action}:{now}"
        conn.execute(
            """
            INSERT INTO memory_approvals(approval_id, memory_id, action, note, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (approval_id, memory_id, action, note, actor, now),
        )
    updated = {
        **current,
        "status": next_status,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "updated_at": now,
        "metadata": {**dict(current.get("metadata", {}) or {}), "supersedes": superseded_ids, "version_state": "current" if action == "approve" else dict(current.get("metadata", {}) or {}).get("version_state", "")},
    }
    updated["can_promote_permanent"] = can_promote_to_permanent(updated)
    sync_search_index(agent_home, updated)
    for previous in superseded_records:
        sync_search_index(agent_home, previous)
    append_approval_mirror(agent_home, {"approval_id": approval_id, "memory_id": memory_id, "action": action, "note": note, "actor": actor, "created_at": now})
    write_domain_mirrors(agent_home)
    sync_legacy_review_memory(agent_home)
    return updated


def append_approval_mirror(agent_home: Path, item: dict[str, Any]) -> None:
    path = long_memory_dir(agent_home) / "approvals" / "approvals.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def write_domain_mirrors(agent_home: Path) -> None:
    init_long_memory(agent_home)
    records = list_memory_records(agent_home, limit=5000)
    base = long_memory_dir(agent_home)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        grouped[str(item.get("domain", ""))].append(item)
    dump_json(base / "exports" / "all_memory.json", {"updated_at": timestamp_now(), "items": records})
    fund_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in grouped.get("fund", []):
        fund_group[str(item.get("entity_key", "unknown"))].append(item)
    for code, items in fund_group.items():
        dump_json(base / "funds" / f"{code}.json", {"updated_at": timestamp_now(), "fund_code": code, "items": items})
    dump_json(base / "market" / "regime_memory.json", {"updated_at": timestamp_now(), "items": grouped.get("market", [])})
    dump_json(base / "execution" / "rules.json", {"updated_at": timestamp_now(), "items": grouped.get("execution", [])})
    dump_json(base / "portfolio" / "policies.json", {"updated_at": timestamp_now(), "items": grouped.get("portfolio", [])})
    candidates = [item for item in records if item.get("status") == "strategic" and can_promote_to_permanent(item)]
    dump_json(base / "candidates" / "pending_permanent.json", {"updated_at": timestamp_now(), "items": candidates})


def sync_legacy_review_memory(agent_home: Path) -> dict[str, Any]:
    memory = load_review_memory(agent_home)
    records = list_memory_records(agent_home, limit=5000)
    permanent = []
    strategic = []
    for item in records:
        legacy = {
            "memory_id": item["memory_id"],
            "memory_type": item.get("memory_type", "policy"),
            "scope": "permanent_memory" if item.get("status") == "permanent" else "strategic_memory",
            "entity_keys": [item.get("entity_key", ""), item.get("domain", "")],
            "text": item.get("text", ""),
            "provenance": {"source": "long_memory", "kind": item.get("memory_type", "")},
            "base_date": item.get("last_supported_at", "") or item.get("created_at", "")[:10],
            "expires_on": "",
            "promotion_level": "promoted" if item.get("status") == "permanent" else "candidate",
            "approved_by": item.get("approved_by", ""),
            "confidence": item.get("confidence", 0.0),
            "status": "active" if item.get("status") in ACTIVE_STATUSES else "inactive",
            "applies_to": item.get("entity_key", ""),
            "reason": item.get("title", ""),
            "source": "long_memory",
        }
        if item.get("status") == "permanent":
            permanent.append(legacy)
        elif item.get("status") == "strategic":
            strategic.append(legacy)
    memory["permanent_memory"] = _dedupe_memory((memory.get("permanent_memory", []) or []) + permanent)
    memory["strategic_memory"] = _dedupe_memory((memory.get("strategic_memory", []) or []) + strategic)[-240:]
    memory["updated_at"] = timestamp_now()
    return dump_json(review_memory_path(agent_home), memory)


def _dedupe_memory(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get("memory_id", "") or item.get("text", ""))
        if key:
            seen[key] = item
    return list(seen.values())


def action_family(action: str) -> str:
    value = str(action or "hold").lower()
    if value in {"buy", "add", "scheduled_dca", "switch_in"}:
        return "add" if value != "scheduled_dca" else "scheduled_dca"
    if value in {"sell", "reduce", "switch_out"}:
        return "reduce"
    return "hold"


def advice_success(action: str, outcome: str) -> bool | None:
    normalized = action_family(action)
    result = str(outcome or "").lower()
    if result in {"unknown", ""}:
        return None
    if normalized in {"add", "scheduled_dca"}:
        return result == "supportive"
    if normalized == "reduce":
        return result == "supportive"
    if normalized == "hold":
        return result in {"neutral", "watchful_hold"}
    return None


def build_fund_memory(agent_home: Path, *, write: bool = True) -> dict[str, Any]:
    init_long_memory(agent_home)
    review_dir = agent_home / "db" / "review_results"
    validated_dir = agent_home / "db" / "validated_advice"
    portfolio = load_portfolio(agent_home) if (agent_home / "config" / "portfolio.json").exists() or (agent_home / "db" / "portfolio_state" / "current.json").exists() else {"funds": []}
    names = {str(item.get("fund_code", "")): item.get("fund_name", "") for item in portfolio.get("funds", []) or []}
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "fund_code": "",
        "fund_name": "",
        "advice_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "unknown_count": 0,
        "by_action": defaultdict(lambda: {"count": 0, "success": 0, "failure": 0, "unknown": 0}),
        "diagnostics": Counter(),
        "agent_reliability": Counter(),
        "evidence_refs": [],
        "latest_review_date": "",
    })
    if review_dir.exists():
        for path in sorted(review_dir.glob("*.json")):
            payload = load_json(path)
            if not isinstance(payload, dict) or payload.get("source", "advice") != "advice":
                continue
            for item in payload.get("items", []) or []:
                code = str(item.get("fund_code", "") or "")
                if not code:
                    continue
                row = stats[code]
                row["fund_code"] = code
                row["fund_name"] = item.get("fund_name", "") or names.get(code, "")
                action = action_family(item.get("source_action") or item.get("validated_action") or "hold")
                outcome = str(item.get("outcome", "unknown") or "unknown")
                ok = advice_success(action, outcome)
                row["advice_count"] += 1
                row["by_action"][action]["count"] += 1
                if ok is True:
                    row["success_count"] += 1
                    row["by_action"][action]["success"] += 1
                elif ok is False:
                    row["failure_count"] += 1
                    row["by_action"][action]["failure"] += 1
                else:
                    row["unknown_count"] += 1
                    row["by_action"][action]["unknown"] += 1
                label = str(item.get("diagnostic_label", "") or "unknown")
                row["diagnostics"][label] += 1
                for agent_name in item.get("agent_support", []) or []:
                    row["agent_reliability"][str(agent_name)] += 1
                row["latest_review_date"] = max(row["latest_review_date"], str(payload.get("review_date", "") or ""))
                row["evidence_refs"].append({"kind": "review_result", "path": str(path), "date": payload.get("review_date", "")})
    if validated_dir.exists():
        for path in sorted(validated_dir.glob("*.json")):
            payload = load_json(path)
            if not isinstance(payload, dict):
                continue
            for section in ("tactical_actions", "dca_actions", "hold_actions"):
                for item in payload.get(section, []) or []:
                    code = str(item.get("fund_code", "") or "")
                    if code and code not in stats:
                        row = stats[code]
                        row["fund_code"] = code
                        row["fund_name"] = item.get("fund_name", "") or names.get(code, "")
    items = []
    for code, row in sorted(stats.items()):
        count = int(row["advice_count"])
        success = int(row["success_count"])
        failure = int(row["failure_count"])
        confidence = round(min(0.92, 0.45 + min(count, 30) * 0.012 + max(0, success - failure) * 0.01), 4)
        success_rate = round(success / count, 4) if count else 0.0
        top_diagnostics = row["diagnostics"].most_common(5)
        behavior_tags = []
        if row["by_action"]["add"]["success"] >= row["by_action"]["add"]["failure"] + 2:
            behavior_tags.append("add_signal_has_edge")
        if row["by_action"]["add"]["failure"] > row["by_action"]["add"]["success"]:
            behavior_tags.append("add_requires_confirmation")
        if row["by_action"]["reduce"]["failure"] > row["by_action"]["reduce"]["success"]:
            behavior_tags.append("reduce_tends_too_early")
        if row["by_action"]["scheduled_dca"]["failure"] > 0:
            behavior_tags.append("scheduled_dca_needs_timing_check")
        if any(label in {"signal_failure", "timing_drag"} for label, _ in top_diagnostics):
            behavior_tags.append("signal_or_timing_sensitive")
        title = f"{row['fund_name'] or code} advice profile"
        text = (
            f"{row['fund_name'] or code} has {count} reviewed system advice samples; "
            f"success_rate={success_rate:.2%}, success={success}, failure={failure}. "
            f"Top diagnostics: {', '.join(f'{k}={v}' for k, v in top_diagnostics) or 'none'}."
        )
        item = {
            "memory_id": stable_memory_id("fund", code, title, "fund_profile_memory"),
            "memory_type": "fund_profile_memory",
            "domain": "fund",
            "entity_key": code,
            "title": title,
            "text": text,
            "status": "strategic" if count >= 2 else "candidate",
            "confidence": confidence,
            "support_count": success,
            "contradiction_count": failure,
            "last_supported_at": row["latest_review_date"],
            "source": "system_advice_reviews",
            "metadata": {
                "fund_code": code,
                "fund_name": row["fund_name"],
                "advice_count": count,
                "success_rate": success_rate,
                "by_action": {k: dict(v) for k, v in row["by_action"].items()},
                "diagnostics": dict(row["diagnostics"]),
                "agent_reliability": dict(row["agent_reliability"]),
                "tags": behavior_tags,
            },
            "evidence_refs": row["evidence_refs"][-12:],
        }
        items.append(item)
        if write:
            upsert_memory_record(agent_home, item)
    payload = {"updated_at": timestamp_now(), "items": items}
    dump_json(long_memory_dir(agent_home) / "funds" / "_summary.json", payload)
    return payload


def infer_market_regime_from_validated(payload: dict) -> tuple[str, list[str]]:
    market = payload.get("market_view", {}) or {}
    text = " ".join(
        [
            str(market.get("regime", "")),
            str(market.get("summary", "")),
            " ".join(str(x) for x in market.get("key_drivers", []) or []),
        ]
    ).lower()
    buckets = []
    for key, words in {
        "growth": ["growth", "成长", "科技", "ai", "半导体"],
        "dividend": ["dividend", "红利", "高股息"],
        "hong_kong": ["港股", "hong kong", "恒生"],
        "us_qdii": ["qdii", "nasdaq", "纳指", "美股", "标普"],
        "bond_cash": ["债", "cash", "货币", "存单"],
        "resource": ["资源", "煤炭", "有色", "黄金"],
        "defensive": ["防御", "医药", "消费"],
    }.items():
        if any(word in text for word in words):
            buckets.append(key)
    return (buckets[0] if buckets else str(market.get("regime", "") or "mixed")), buckets


def build_market_memory(agent_home: Path, *, write: bool = True) -> dict[str, Any]:
    init_long_memory(agent_home)
    validated_dir = agent_home / "db" / "validated_advice"
    review_dir = agent_home / "db" / "review_results"
    review_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if review_dir.exists():
        for path in sorted(review_dir.glob("*.json")):
            payload = load_json(path)
            if isinstance(payload, dict) and payload.get("source", "advice") == "advice":
                review_by_date[str(payload.get("base_date", "") or "")].append(payload)
    regime_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"days": 0, "supportive": 0, "adverse": 0, "missed": 0, "actions": 0, "dates": [], "style_buckets": Counter()})
    daily_items = []
    if validated_dir.exists():
        for path in sorted(validated_dir.glob("*.json")):
            report_date = path.stem[:10]
            payload = load_json(path)
            if not isinstance(payload, dict):
                continue
            regime, buckets = infer_market_regime_from_validated(payload)
            reviews = review_by_date.get(report_date, [])
            supportive = sum(int((item.get("summary", {}) or {}).get("supportive", 0) or 0) for item in reviews)
            adverse = sum(int((item.get("summary", {}) or {}).get("adverse", 0) or 0) for item in reviews)
            missed = sum(int((item.get("summary", {}) or {}).get("missed_upside", 0) or 0) for item in reviews)
            actions = sum(len(payload.get(section, []) or []) for section in ("tactical_actions", "dca_actions"))
            stat = regime_stats[regime]
            stat["days"] += 1
            stat["supportive"] += supportive
            stat["adverse"] += adverse
            stat["missed"] += missed
            stat["actions"] += actions
            stat["dates"].append(report_date)
            stat["style_buckets"].update(buckets)
            daily = {"date": report_date, "regime": regime, "buckets": buckets, "supportive": supportive, "adverse": adverse, "missed_upside": missed, "actions": actions}
            daily_items.append(daily)
            dump_json(long_memory_dir(agent_home) / "market" / "regime_daily" / f"{report_date}.json", daily)
    items = []
    for regime, stat in sorted(regime_stats.items()):
        total = int(stat["supportive"] + stat["adverse"] + stat["missed"])
        success_rate = round(stat["supportive"] / total, 4) if total else 0.0
        title = f"Market regime memory: {regime}"
        text = (
            f"Regime {regime} appeared on {stat['days']} advice days; "
            f"review success_rate={success_rate:.2%}, supportive={stat['supportive']}, adverse={stat['adverse']}, missed={stat['missed']}."
        )
        item = {
            "memory_id": stable_memory_id("market", regime, title, "market_regime_memory"),
            "memory_type": "market_regime_memory",
            "domain": "market",
            "entity_key": regime,
            "title": title,
            "text": text,
            "status": "strategic" if stat["days"] >= 2 else "candidate",
            "confidence": round(min(0.9, 0.45 + stat["days"] * 0.02 + total * 0.005), 4),
            "support_count": int(stat["supportive"]),
            "contradiction_count": int(stat["adverse"] + stat["missed"]),
            "last_supported_at": max(stat["dates"]) if stat["dates"] else "",
            "source": "validated_advice_regime_reviews",
            "metadata": {"days": stat["days"], "success_rate": success_rate, "style_buckets": dict(stat["style_buckets"]), "sample_dates": stat["dates"][-12:], "tags": list(stat["style_buckets"].keys())},
            "evidence_refs": [{"kind": "validated_advice", "path": str(validated_dir / f"{date}.json"), "date": date} for date in stat["dates"][-8:]],
        }
        items.append(item)
        if write:
            upsert_memory_record(agent_home, item)
    payload = {"updated_at": timestamp_now(), "daily_items": daily_items, "items": items}
    dump_json(long_memory_dir(agent_home) / "market" / "regime_memory.json", payload)
    return payload


def build_execution_memory(agent_home: Path, *, write: bool = True) -> dict[str, Any]:
    init_long_memory(agent_home)
    trade_dir = agent_home / "db" / "trade_journal"
    review_dir = agent_home / "db" / "execution_reviews"
    definition_path = agent_home / "config" / "portfolio_definition.json"
    constraints_meta = load_json(definition_path) if definition_path.exists() else {}
    cases = []
    rules: dict[str, dict[str, Any]] = {}
    if trade_dir.exists():
        for path in sorted(trade_dir.glob("*.json")):
            payload = load_json(path)
            if not isinstance(payload, dict):
                continue
            for item in payload.get("items", []) or []:
                case = {
                    "trade_date": path.stem,
                    "fund_code": item.get("fund_code", ""),
                    "fund_name": item.get("fund_name", ""),
                    "action": item.get("action", ""),
                    "amount": item.get("amount", 0.0),
                    "suggestion_id": item.get("suggestion_id", ""),
                    "note": item.get("note", ""),
                    "source_path": str(path),
                }
                cases.append(case)
    if review_dir.exists():
        for path in sorted(review_dir.glob("*.json")):
            payload = load_json(path)
            if not isinstance(payload, dict):
                continue
            for item in payload.get("items", []) or []:
                label = str(item.get("diagnostic_label", "") or "")
                if label in {"timing_drag", "signal_failure"} and int(item.get("purchase_confirm_days", 0) or 0) > 1:
                    key = "qdii_confirmation_lag_check"
                    rules.setdefault(key, {"support": 0, "contra": 0, "refs": [], "codes": set()})
                    rules[key]["support"] += 1
                    rules[key]["refs"].append({"kind": "execution_review", "path": str(path), "date": payload.get("review_date", "")})
                    rules[key]["codes"].add(str(item.get("fund_code", "")))
                if float(item.get("estimated_transaction_cost_amount", 0.0) or 0.0) > 0:
                    key = "redeem_fee_requires_edge_check"
                    rules.setdefault(key, {"support": 0, "contra": 0, "refs": [], "codes": set()})
                    rules[key]["support"] += 1
                    rules[key]["refs"].append({"kind": "execution_review", "path": str(path), "date": payload.get("review_date", "")})
                    rules[key]["codes"].add(str(item.get("fund_code", "")))
    if not rules and cases:
        rules["manual_trade_deviation_tracking"] = {"support": len(cases), "contra": 0, "refs": [{"kind": "trade_journal", "path": item["source_path"], "date": item["trade_date"]} for item in cases[-8:]], "codes": {str(item.get("fund_code", "")) for item in cases}}
    items = []
    templates = {
        "qdii_confirmation_lag_check": "Check confirmation lag before QDII or delayed-confirmation buys; split or defer weak-window scheduled entries.",
        "redeem_fee_requires_edge_check": "Do not reduce positions unless expected edge survives redemption fee and settlement friction.",
        "manual_trade_deviation_tracking": "Track actual trades separately from system advice so execution drift does not contaminate advice accuracy.",
    }
    for key, stat in rules.items():
        title = key.replace("_", " ").title()
        item = {
            "memory_id": stable_memory_id("execution", key, title, "execution_memory"),
            "memory_type": "execution_memory",
            "domain": "execution",
            "entity_key": key,
            "title": title,
            "text": templates.get(key, title),
            "status": "strategic",
            "confidence": round(min(0.9, 0.55 + int(stat["support"]) * 0.03), 4),
            "support_count": int(stat["support"]),
            "contradiction_count": int(stat["contra"]),
            "last_supported_at": max((str(ref.get("date", "")) for ref in stat["refs"]), default=""),
            "source": "execution_reviews",
            "metadata": {"fund_codes": sorted(x for x in stat["codes"] if x), "constraints_source": str(definition_path) if constraints_meta else "", "tags": [key, "execution"]},
            "evidence_refs": stat["refs"][-12:],
        }
        items.append(item)
        if write:
            upsert_memory_record(agent_home, item)
    cases_path = long_memory_dir(agent_home) / "execution" / "cases.jsonl"
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    cases_path.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in cases), encoding="utf-8")
    payload = {"updated_at": timestamp_now(), "items": items, "case_count": len(cases)}
    dump_json(long_memory_dir(agent_home) / "execution" / "rules.json", payload)
    return payload


def migrate_legacy_review_memory(agent_home: Path) -> dict[str, Any]:
    init_long_memory(agent_home)
    migrated = 0
    ledger_path = review_memory_ledger_path(agent_home)
    if ledger_path.exists():
        ledger = load_json(ledger_path)
        for rule in (ledger.get("rules", []) if isinstance(ledger, dict) else []):
            stage = str(rule.get("stage", "candidate") or "candidate")
            status = "strategic" if stage in {"strategic", "permanent", "core_permanent"} else ("archived" if stage == "archived" else "candidate")
            priority = "core" if stage == "core_permanent" else ""
            title = str(rule.get("title", "") or rule.get("rule_key", "Legacy Rule"))
            item = {
                "memory_id": str(rule.get("rule_id", "") or stable_memory_id("portfolio", str(rule.get("rule_key", "")), title, "portfolio_policy_memory")),
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": str(rule.get("rule_key", "") or ""),
                "title": title,
                "text": str(rule.get("text", "") or ""),
                "status": status,
                "priority": priority,
                "confidence": float(rule.get("confidence", 0.0) or 0.0),
                "support_count": int(rule.get("review_support_count", 0) or 0) + int(rule.get("replay_support_count", 0) or 0),
                "contradiction_count": int(rule.get("review_contradiction_count", 0) or 0) + int(rule.get("replay_contradiction_count", 0) or 0),
                "last_supported_at": str(rule.get("last_supported_at", "") or ""),
                "last_contradicted_at": str(rule.get("last_contradicted_at", "") or ""),
                "source": "legacy_review_memory",
                "metadata": {"legacy_stage": stage, "category": rule.get("category", ""), "tags": rule.get("applies_to", []) or []},
                "evidence_refs": [{"kind": "legacy_review_memory", "path": str(ledger_path)}],
            }
            upsert_memory_record(agent_home, item)
            migrated += 1
    payload = {"updated_at": timestamp_now(), "migrated_count": migrated}
    dump_json(long_memory_dir(agent_home) / "exports" / "legacy_migration.json", payload)
    return payload


def update_all_long_memory(agent_home: Path) -> dict[str, Any]:
    migration = migrate_legacy_review_memory(agent_home)
    fund = build_fund_memory(agent_home)
    market = build_market_memory(agent_home)
    execution = build_execution_memory(agent_home)
    sync_legacy_review_memory(agent_home)
    return {
        "updated_at": timestamp_now(),
        "migration": migration,
        "fund": {"count": len(fund.get("items", []))},
        "market": {"count": len(market.get("items", []))},
        "execution": {"count": len(execution.get("items", [])), "case_count": execution.get("case_count", 0)},
        "pending_permanent": len(
            [item for item in list_memory_records(agent_home, status="strategic", limit=5000) if can_promote_to_permanent(item)]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and manage local long memory.")
    parser.add_argument("--agent-home")
    parser.add_argument("--domain", default="all", choices=["all", "fund", "market", "execution", "legacy"])
    parser.add_argument("--approve-memory-id", default="")
    parser.add_argument("--action", default="approve", choices=["approve", "reject", "archive", "demote"])
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    from common import resolve_agent_home

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    if args.approve_memory_id:
        result = approve_memory(agent_home, args.approve_memory_id, action=args.action, note=args.note)
    elif args.domain == "fund":
        result = build_fund_memory(agent_home)
    elif args.domain == "market":
        result = build_market_memory(agent_home)
    elif args.domain == "execution":
        result = build_execution_memory(agent_home)
    elif args.domain == "legacy":
        result = migrate_legacy_review_memory(agent_home)
    else:
        result = update_all_long_memory(agent_home)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
