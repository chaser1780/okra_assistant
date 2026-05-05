from __future__ import annotations

import argparse
import json

from common import ensure_layout, resolve_agent_home
from long_memory_store import build_execution_memory, build_fund_memory, build_market_memory, migrate_legacy_review_memory, update_all_long_memory


def main() -> None:
    parser = argparse.ArgumentParser(description="Update long memory domains.")
    parser.add_argument("--agent-home")
    parser.add_argument("--domain", default="all", choices=["all", "fund", "market", "execution", "legacy"])
    args = parser.parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    if args.domain == "fund":
        payload = build_fund_memory(agent_home)
    elif args.domain == "market":
        payload = build_market_memory(agent_home)
    elif args.domain == "execution":
        payload = build_execution_memory(agent_home)
    elif args.domain == "legacy":
        payload = migrate_legacy_review_memory(agent_home)
    else:
        payload = update_all_long_memory(agent_home)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
