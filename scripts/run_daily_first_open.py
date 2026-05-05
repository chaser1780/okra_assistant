from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common import daily_workspace_dir, dump_json, ensure_layout, load_json, resolve_agent_home, resolve_date, timestamp_now
from long_memory_store import list_memory_records, update_all_long_memory
from preflight_check import perform_preflight
from run_daily_pipeline import due_review_jobs


SCRIPT_DIR = Path(__file__).resolve().parent


def _run_script(agent_home: Path, script_name: str, *args: str, allow_fail: bool = False) -> dict:
    command = [sys.executable, "-B", "-X", "utf8", str(SCRIPT_DIR / script_name), "--agent-home", str(agent_home), *args]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    payload = {"command": command, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    if completed.returncode != 0 and not allow_fail:
        raise RuntimeError(f"{script_name} failed: {completed.stderr or completed.stdout}")
    return payload


def _workspace_done(path: Path) -> bool:
    marker = path / "today_decision.json"
    return marker.exists()


def _collect_due_reviews(agent_home: Path, report_date: str, *, demo: bool) -> dict:
    jobs = due_review_jobs(agent_home, report_date)
    executed = []
    for job in jobs:
        horizon = str(job.get("horizon", 0))
        base_date = str(job.get("base_date", ""))
        if job.get("has_advice"):
            executed.append(
                _run_script(
                    agent_home,
                    "review_advice.py",
                    "--base-date",
                    base_date,
                    "--review-date",
                    report_date,
                    "--horizon",
                    horizon,
                    "--source",
                    "advice",
                    allow_fail=demo,
                )
            )
        if job.get("has_execution"):
            executed.append(
                _run_script(
                    agent_home,
                    "review_advice.py",
                    "--base-date",
                    base_date,
                    "--review-date",
                    report_date,
                    "--horizon",
                    horizon,
                    "--source",
                    "execution",
                    allow_fail=demo,
                )
            )
    return {"jobs": jobs, "executed": executed}


def _today_analysis(agent_home: Path, report_date: str) -> dict:
    context_path = agent_home / "db" / "llm_context" / f"{report_date}.json"
    validated_path = agent_home / "db" / "validated_advice" / f"{report_date}.json"
    context = load_json(context_path) if context_path.exists() else {}
    validated = load_json(validated_path) if validated_path.exists() else {}
    records = list_memory_records(agent_home, limit=80)
    fund_records = [item for item in records if item.get("domain") == "fund"][:12]
    market_records = [item for item in records if item.get("domain") == "market"][:8]
    execution_records = [item for item in records if item.get("domain") == "execution"][:8]
    prohibited = [item.get("text", "") for item in execution_records if item.get("status") == "permanent"]
    watch = [item.get("text", "") for item in fund_records[:5]]
    market_view = validated.get("market_view", {}) or {}
    return {
        "analysis_date": report_date,
        "generated_at": timestamp_now(),
        "market_view": market_view,
        "memory_counts": {
            "fund": len(fund_records),
            "market": len(market_records),
            "execution": len(execution_records),
            "active_total": len(records),
        },
        "key_long_memory": {
            "fund": fund_records[:6],
            "market": market_records[:4],
            "execution": execution_records[:4],
        },
        "today_watchlist": watch,
        "prohibited_actions": prohibited,
        "allowed_with_conditions": [item.get("text", "") for item in records if item.get("status") in {"strategic", "permanent"}][:10],
        "context_available": bool(context),
        "validated_available": bool(validated),
    }


def _today_decision(today_analysis: dict, memory_updates: dict) -> dict:
    return {
        "analysis_date": today_analysis.get("analysis_date", ""),
        "generated_at": timestamp_now(),
        "summary": (
            f"Daily first-open analysis loaded {today_analysis.get('memory_counts', {}).get('active_total', 0)} active long-memory records "
            f"and refreshed fund/market/execution learning."
        ),
        "market_judgement": today_analysis.get("market_view", {}),
        "prohibited_actions": today_analysis.get("prohibited_actions", []),
        "allowed_with_conditions": today_analysis.get("allowed_with_conditions", []),
        "memory_update_summary": memory_updates,
    }


def _brief_text(report_date: str, due_reviews: dict, memory_updates: dict, today_analysis: dict, today_decision: dict) -> str:
    lines = [
        f"# Daily First-Open Brief - {report_date}",
        "",
        f"- generated_at: {today_decision.get('generated_at', '')}",
        f"- due_review_jobs: {len(due_reviews.get('jobs', []) or [])}",
        f"- active_long_memory: {today_analysis.get('memory_counts', {}).get('active_total', 0)}",
        f"- pending_permanent: {memory_updates.get('pending_permanent', 0)}",
        "",
        "## Today",
        today_decision.get("summary", ""),
        "",
        "## Prohibited Actions",
    ]
    prohibited = today_decision.get("prohibited_actions", []) or []
    lines.extend([f"- {item}" for item in prohibited[:8]] or ["- None"])
    lines.extend(["", "## Long Memory Highlights"])
    for domain in ("fund", "market", "execution"):
        lines.append(f"### {domain}")
        items = (today_analysis.get("key_long_memory", {}) or {}).get(domain, []) or []
        lines.extend([f"- {item.get('title', '')}: {item.get('text', '')}" for item in items[:4]] or ["- None"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the unified daily first-open route.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    workspace = daily_workspace_dir(agent_home, report_date)
    workspace.mkdir(parents=True, exist_ok=True)
    if _workspace_done(workspace) and not args.force:
        print(workspace / "today_decision.json")
        return

    print(f">>> FIRST_OPEN_START date={report_date}", flush=True)
    preflight = perform_preflight(agent_home, scope="desktop", probe_llm=not args.demo)
    dump_json(workspace / "preflight.json", preflight)

    print(">>> FIRST_OPEN sync_state", flush=True)
    sync_state = _run_script(agent_home, "run_daily_pipeline.py", "--date", report_date, "--mode", "intraday", *(["--demo", "--llm-mock"] if args.demo else []), allow_fail=args.demo)
    dump_json(workspace / "sync_state.json", sync_state)

    print(">>> FIRST_OPEN due_review", flush=True)
    due_reviews = _collect_due_reviews(agent_home, report_date, demo=args.demo)
    dump_json(workspace / "due_reviews.json", due_reviews)

    print(">>> FIRST_OPEN long_memory_update", flush=True)
    memory_updates = update_all_long_memory(agent_home)
    dump_json(workspace / "memory_updates.json", memory_updates)

    print(">>> FIRST_OPEN today_analysis", flush=True)
    today_analysis = _today_analysis(agent_home, report_date)
    dump_json(workspace / "today_analysis.json", today_analysis)

    today_decision = _today_decision(today_analysis, memory_updates)
    dump_json(workspace / "today_decision.json", today_decision)
    brief = _brief_text(report_date, due_reviews, memory_updates, today_analysis, today_decision)
    (workspace / "daily_brief.md").write_text(brief, encoding="utf-8")
    (agent_home / "reports" / "daily" / f"{report_date}_daily_brief.md").write_text(brief, encoding="utf-8")
    print(f">>> FIRST_OPEN_DONE date={report_date}", flush=True)
    print(workspace / "today_decision.json")


if __name__ == "__main__":
    main()
