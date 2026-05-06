from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import ensure_layout, load_json, resolve_agent_home, resolve_date
from execution_sync import apply_reconciliation, preview_reconciliation


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or apply actual position reconciliation.")
    sub = parser.add_subparsers(dest="command", required=True)

    preview = sub.add_parser("preview")
    preview.add_argument("--agent-home")
    preview.add_argument("--date")
    preview.add_argument("--positions-json", required=True)
    preview.add_argument("--source", default="manual_position_snapshot")

    apply = sub.add_parser("apply")
    apply.add_argument("--agent-home")
    apply.add_argument("--preview-path", required=True)
    apply.add_argument("--drop-missing", action="store_true")

    args = parser.parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    if args.command == "preview":
        path = Path(args.positions_json)
        payload = load_json(path)
        positions = payload.get("items", payload if isinstance(payload, list) else [])
        result = preview_reconciliation(agent_home, positions, snapshot_date=resolve_date(args.date), source=args.source)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    preview_payload = load_json(Path(args.preview_path))
    result = apply_reconciliation(agent_home, preview_payload, drop_missing=bool(args.drop_missing))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
