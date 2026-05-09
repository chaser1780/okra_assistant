from __future__ import annotations

import argparse

from common import resolve_agent_home, resolve_date
from run_today_analysis import run_today_analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="Compatibility wrapper for the legacy first-open command.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--llm-mock", action="store_true")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    output_path = run_today_analysis(
        agent_home,
        report_date,
        trigger="compat_first_open",
        demo=args.demo,
        force=args.force,
        llm_mock=args.llm_mock,
    )
    print(output_path)


if __name__ == "__main__":
    main()
