from __future__ import annotations

import argparse
import json

from common import ensure_layout, resolve_agent_home
from execution_sync import update_pending_confirmations


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh actual-trade pending confirmations.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date")
    args = parser.parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    print(json.dumps(update_pending_confirmations(agent_home, args.date), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
