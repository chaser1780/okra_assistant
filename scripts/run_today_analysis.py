from __future__ import annotations

import argparse

from common import resolve_agent_home, resolve_date, shanghai_now, today_shanghai
from today_orchestrator import pending_backfill_dates, run_today_analysis

_pending_backfill_dates = pending_backfill_dates


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the canonical today-analysis route.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--llm-mock", action="store_true")
    parser.add_argument("--trigger", default="manual", choices=["manual", "auto", "backfill", "compat_first_open"])
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    started = shanghai_now()

    if args.trigger in {"auto", "manual", "compat_first_open"} and report_date == today_shanghai(started):
        for backfill_date in pending_backfill_dates(agent_home, report_date, started):
            run_today_analysis(
                agent_home,
                backfill_date,
                trigger="backfill",
                demo=args.demo,
                force=True,
                llm_mock=args.llm_mock,
                started_at=started,
            )

    output_path = run_today_analysis(
        agent_home,
        report_date,
        trigger=args.trigger,
        demo=args.demo,
        force=args.force,
        llm_mock=args.llm_mock,
        started_at=started,
    )
    print(output_path)


if __name__ == "__main__":
    main()
