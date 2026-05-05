from __future__ import annotations

import argparse
import json

from common import ensure_layout, resolve_agent_home
from long_memory_store import build_fund_memory


def main() -> None:
    parser = argparse.ArgumentParser(description="Build long-term fund profile memory from system advice reviews.")
    parser.add_argument("--agent-home")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    payload = build_fund_memory(agent_home, write=not args.dry_run)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
