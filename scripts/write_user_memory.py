from __future__ import annotations

import argparse

from common import dump_json, ensure_layout, load_review_memory, resolve_agent_home, resolve_date, review_memory_path, review_memory_permanent_path, review_memory_user_confirmed_path, timestamp_now


def make_memory_id(prefix: str, base_date: str, text: str) -> str:
    import hashlib

    digest = hashlib.sha1(f"{prefix}|{base_date}|{text}".encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{base_date}:{digest}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a user-confirmed memory record.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Memory date in YYYY-MM-DD format.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--scope", default="user_confirmed_memory", choices=["user_confirmed_memory", "permanent_memory", "strategic_memory"])
    parser.add_argument("--memory-type", default="preference")
    parser.add_argument("--entity-key", action="append", default=[])
    parser.add_argument("--approved-by", default="user")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    base_date = resolve_date(args.date)
    memory = load_review_memory(agent_home)
    memory.setdefault("user_confirmed_memory", [])
    memory.setdefault("permanent_memory", [])
    memory.setdefault("strategic_memory", [])

    record = {
        "memory_id": make_memory_id("user_memory", base_date, args.text),
        "memory_type": args.memory_type,
        "scope": args.scope,
        "entity_keys": args.entity_key,
        "text": args.text,
        "provenance": {"source": "user", "kind": "manual_write"},
        "base_date": base_date,
        "expires_on": "",
        "promotion_level": "promoted" if args.scope == "permanent_memory" else "manual",
        "approved_by": args.approved_by,
        "confidence": 1.0,
        "status": "active",
        "source": "user",
    }

    target = memory.setdefault(args.scope, [])
    target[:] = [item for item in target if item.get("memory_id") != record["memory_id"]]
    target.append(record)
    memory["updated_at"] = timestamp_now()
    dump_json(review_memory_user_confirmed_path(agent_home), {"updated_at": memory["updated_at"], "items": memory.get("user_confirmed_memory", [])})
    dump_json(review_memory_permanent_path(agent_home), {"updated_at": memory["updated_at"], "items": memory.get("permanent_memory", [])})
    print(dump_json(review_memory_path(agent_home), memory))


if __name__ == "__main__":
    main()
