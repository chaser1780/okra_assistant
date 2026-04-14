from __future__ import annotations

import argparse

from common import ensure_layout, resolve_agent_home, resolve_date
from portfolio_state import rebuild_portfolio_state, save_portfolio_state


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild derived portfolio state from definition, snapshots, and trade journal.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    target_date = resolve_date(args.date)
    portfolio = rebuild_portfolio_state(agent_home, target_date)
    current_path, snapshot_path = save_portfolio_state(
        agent_home,
        portfolio,
        source="state_rebuild",
        event_date=target_date,
        event_type="state_rebuild",
    )
    print(current_path)
    print(snapshot_path)


if __name__ == "__main__":
    main()
