from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common import ensure_layout, resolve_agent_home, resolve_date
from learning_memory import run_learning_sync, write_learning_artifacts
from run_daily_pipeline import due_review_jobs


SCRIPT_DIR = Path(__file__).resolve().parent


def _run_script(script_name: str, *args: str) -> None:
    command = [sys.executable, "-B", "-X", "utf8", str(SCRIPT_DIR / script_name), *args]
    subprocess.run(command, check=True)


def collect_reviews(agent_home: Path, review_date: str) -> list[dict]:
    from common import execution_review_result_path, load_json, review_result_path

    items: list[dict] = []
    jobs = due_review_jobs(agent_home, review_date)
    for job in jobs:
        horizon = int(job.get("horizon", 0) or 0)
        base_date = str(job.get("base_date", "") or "")
        if job.get("has_advice"):
            path = review_result_path(agent_home, base_date, horizon)
            if path.exists():
                items.append(load_json(path))
        if job.get("has_execution"):
            path = execution_review_result_path(agent_home, base_date, horizon)
            if path.exists():
                items.append(load_json(path))
    items.sort(key=lambda item: (item.get("source", "advice"), int(item.get("horizon", 0)), item.get("base_date", "")))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the unified nightly learning cycle.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Learning cycle date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    review_date = resolve_date(args.date)
    jobs = due_review_jobs(agent_home, review_date)

    print(f">>> LEARNING_CYCLE_START date={review_date}", flush=True)
    if not jobs:
        print(f">>> LEARNING_INFO no_due_review_jobs review_date={review_date}", flush=True)
    for job in jobs:
        base_date = str(job["base_date"])
        horizon = str(job["horizon"])
        label = f"{base_date}_T{horizon}"
        if job.get("has_advice"):
            print(f">>> LEARNING_REVIEW advice {label}", flush=True)
            _run_script(
                "review_advice.py",
                "--agent-home",
                str(agent_home),
                "--base-date",
                base_date,
                "--review-date",
                review_date,
                "--horizon",
                horizon,
                "--source",
                "advice",
            )
        if job.get("has_execution"):
            print(f">>> LEARNING_REVIEW execution {label}", flush=True)
            _run_script(
                "review_advice.py",
                "--agent-home",
                str(agent_home),
                "--base-date",
                base_date,
                "--review-date",
                review_date,
                "--horizon",
                horizon,
                "--source",
                "execution",
            )

    review_batches = collect_reviews(agent_home, review_date)
    cycle_summary, ledger, memory = run_learning_sync(agent_home, review_date, review_batches)
    written = write_learning_artifacts(agent_home, review_date, cycle_summary, ledger, memory, review_batches)
    print(f">>> LEARNING_CYCLE_DONE date={review_date} batches={len(review_batches)}", flush=True)
    print(written["cycle_path"])


if __name__ == "__main__":
    main()
