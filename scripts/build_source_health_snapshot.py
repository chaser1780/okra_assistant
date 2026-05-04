from __future__ import annotations

import argparse

from common import dump_json, ensure_layout, load_json, resolve_agent_home, resolve_date, source_health_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a normalized source health snapshot.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    existing = load_json(source_health_path(agent_home, report_date)) if source_health_path(agent_home, report_date).exists() else {"items": []}
    items = existing.get("items", []) if isinstance(existing, dict) else []
    snapshot = {
        "report_date": report_date,
        "generated_at": existing.get("generated_at", ""),
        "summary": {
            "source_count": len(items),
            "warning_count": sum(1 for item in items if item.get("status") == "warning"),
            "error_count": sum(int(item.get("error_count", 0) or 0) for item in items),
            "stale_count": sum(int(item.get("stale_count", 0) or 0) for item in items),
        },
        "items": items,
    }
    print(dump_json(source_health_path(agent_home, report_date), snapshot))


if __name__ == "__main__":
    main()
