from __future__ import annotations

import argparse

from action_debate_graph import run_debate_graph
from artifact_boundary import relative_posix
from common import resolve_agent_home, resolve_date


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the non-executable action debate shadow graph.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", required=True, help="Report date in YYYY-MM-DD.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp for deterministic tests.")
    parser.add_argument("--fail-node", default="", help="Test hook: inject a degraded node failure by node name.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    path, artifact = run_debate_graph(
        agent_home,
        report_date,
        generated_at=args.generated_at or None,
        fail_node=args.fail_node,
    )
    print(
        "wrote "
        f"{artifact.get('summary', {}).get('debate_count', 0)} action debates: "
        f"{relative_posix(path, agent_home)}"
    )


if __name__ == "__main__":
    main()

