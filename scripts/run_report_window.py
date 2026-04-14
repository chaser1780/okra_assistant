from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, time
from pathlib import Path

from common import load_strategy, nightly_review_report_path, portfolio_report_path, report_path, resolve_agent_home

SCRIPT_DIR = Path(__file__).resolve().parent
KNOWN_INTRADAY_REPORT_MODES = {
    "intraday_proxy": "portfolio_report",
    "portfolio_report": "portfolio_report",
    "daily_report": "daily_report",
}


def parse_clock(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def intraday_report_target(agent_home: Path, strategy: dict, report_date: str) -> Path:
    report_mode = str(strategy.get("schedule", {}).get("report_mode", "intraday_proxy") or "intraday_proxy").strip()
    normalized = KNOWN_INTRADAY_REPORT_MODES.get(report_mode)
    if normalized == "daily_report":
        return report_path(agent_home, report_date)
    if normalized == "portfolio_report":
        return portfolio_report_path(agent_home, report_date)
    raise SystemExit(f"未识别的 intraday report_mode：{report_mode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scheduled intraday or nightly reports inside the configured window.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--mode", default="intraday", choices=["intraday", "nightly"])
    parser.add_argument("--demo", action="store_true", help="Run the underlying pipeline in demo mode.")
    parser.add_argument("--llm-mock", action="store_true", help="Run the LLM stage in mock mode.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    strategy = load_strategy(agent_home)
    schedule = strategy.get("schedule", {})
    now = datetime.now().astimezone()
    today = now.date().isoformat()

    if args.mode == "intraday":
        start_at = parse_clock(schedule["intraday_start"])
        end_at = parse_clock(schedule["intraday_end"])
        report_file = intraday_report_target(agent_home, strategy, today)
    else:
        start_at = parse_clock(schedule["nightly_start"])
        end_at = parse_clock(schedule["nightly_end"])
        report_file = nightly_review_report_path(agent_home, today)
    allow_catch_up = bool(schedule.get("run_if_missed_on_next_boot", True))

    if report_file.exists():
        print(f"already_generated={report_file}")
        return

    if now.time() < start_at:
        print(f"too_early_for_window={today}T{start_at.isoformat(timespec='minutes')}")
        return
    if now.time() > end_at and not allow_catch_up:
        print(f"too_late_for_window={today}T{end_at.isoformat(timespec='minutes')}")
        return
    if now.time() > end_at and allow_catch_up:
        print(f"missed_window_resuming={today}T{end_at.isoformat(timespec='minutes')}")

    command = [sys.executable, "-B", "-X", "utf8", str(SCRIPT_DIR / "run_daily_pipeline.py"), "--agent-home", str(agent_home), "--date", today, "--mode", args.mode]
    if args.demo:
        command.append("--demo")
    if args.llm_mock:
        command.append("--llm-mock")
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
