from __future__ import annotations

import argparse
import json

from common import ensure_layout, resolve_agent_home
from execution_sync import build_execution_sync_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build actual-vs-system execution deviation summary.")
    parser.add_argument("--agent-home")
    args = parser.parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    payload = build_execution_sync_payload(agent_home)
    print(json.dumps({"updated_at": payload["updatedAt"], "items": payload["deviations"], "counts": payload["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
