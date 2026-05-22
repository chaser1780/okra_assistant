from __future__ import annotations

import argparse
from datetime import datetime

from common import resolve_agent_home, resolve_date, shanghai_now, today_shanghai
from today_orchestrator import AlreadyRunningError, pending_backfill_dates, run_today_analysis

_pending_backfill_dates = pending_backfill_dates


def run_pending_backfills(
    agent_home,
    report_date: str,
    started: datetime,
    *,
    demo: bool,
    llm_mock: bool,
    resume_existing: bool,
) -> list[dict[str, str]]:
    skipped: list[dict[str, str]] = []
    for backfill_date in pending_backfill_dates(agent_home, report_date, started):
        try:
            run_today_analysis(
                agent_home,
                backfill_date,
                trigger="backfill",
                demo=demo,
                force=True,
                llm_mock=llm_mock,
                started_at=started,
                resume_existing=resume_existing,
            )
        except AlreadyRunningError as exc:
            skipped.append({"date": backfill_date, "reason": str(exc)})
            print(f"skip active backfill {backfill_date}: {exc}")
    return skipped


def should_run_pending_backfills(trigger: str, report_date: str, started: datetime) -> bool:
    return trigger in {"auto", "compat_first_open"} and report_date == today_shanghai(started)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the canonical today-analysis route.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--llm-mock", action="store_true")
    parser.add_argument("--resume-existing", action="store_true", help="Reuse completed pipeline step outputs where safe.")
    parser.add_argument("--trigger", default="manual", choices=["manual", "auto", "backfill", "compat_first_open"])
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    started = shanghai_now()

    if should_run_pending_backfills(args.trigger, report_date, started):
        run_pending_backfills(
            agent_home,
            report_date,
            started,
            demo=args.demo,
            llm_mock=args.llm_mock,
            resume_existing=args.resume_existing,
        )

    output_path = run_today_analysis(
        agent_home,
        report_date,
        trigger=args.trigger,
        demo=args.demo,
        force=args.force,
        llm_mock=args.llm_mock,
        started_at=started,
        resume_existing=args.resume_existing,
    )
    print(output_path)


if __name__ == "__main__":
    main()
