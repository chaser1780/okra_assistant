from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

from common import load_review_config, resolve_agent_home, resolve_date
from common import (
    agent_output_dir,
    committee_advice_path,
    evidence_index_path,
    estimated_nav_path,
    fund_profile_path,
    intraday_proxy_path,
    learning_report_path,
    llm_advice_path,
    llm_context_path,
    news_path,
    portfolio_report_path,
    quote_path,
    recommendation_delta_path,
    report_path,
    score_path,
    source_health_path,
    evaluation_snapshot_path,
    validated_advice_path,
)
from preflight_check import perform_preflight
from run_manifest_utils import begin_step, finalize_manifest, finish_step, new_run_manifest, write_manifest

SCRIPT_DIR = Path(__file__).resolve().parent


def step_output_exists(agent_home: Path, report_date: str, script_name: str, extra_args: list[str] | None = None) -> bool:
    def is_up_to_date(target: Path, dependency: Path | None = None) -> bool:
        if not target.exists():
            return False
        if dependency is None or not dependency.exists():
            return True
        return target.stat().st_mtime >= dependency.stat().st_mtime

    if script_name == "fetch_fund_quotes.py":
        return quote_path(agent_home, report_date).exists()
    if script_name == "fetch_fund_news.py":
        return news_path(agent_home, report_date).exists()
    if script_name == "fetch_fund_profiles.py":
        return fund_profile_path(agent_home, report_date).exists()
    if script_name == "score_funds.py":
        return score_path(agent_home, report_date).exists()
    if script_name == "build_daily_report.py":
        return is_up_to_date(report_path(agent_home, report_date), validated_advice_path(agent_home, report_date))
    if script_name == "fetch_intraday_proxies.py":
        return intraday_proxy_path(agent_home, report_date).exists()
    if script_name == "fetch_realtime_estimate.py":
        return estimated_nav_path(agent_home, report_date).exists()
    if script_name == "build_llm_context.py":
        return llm_context_path(agent_home, report_date).exists()
    if script_name == "build_evidence_index.py":
        return evidence_index_path(agent_home, report_date).exists()
    if script_name == "build_source_health_snapshot.py":
        return source_health_path(agent_home, report_date).exists()
    if script_name == "run_learning_cycle.py":
        return learning_report_path(agent_home, report_date).exists()
    if script_name == "run_multiagent_research.py":
        aggregate = agent_output_dir(agent_home, report_date) / "aggregate.json"
        return aggregate.exists()
    if script_name == "generate_llm_advice.py":
        aggregate = agent_output_dir(agent_home, report_date) / "aggregate.json"
        return is_up_to_date(llm_advice_path(agent_home, report_date), aggregate) and is_up_to_date(committee_advice_path(agent_home, report_date), aggregate)
    if script_name == "validate_llm_advice.py":
        return is_up_to_date(validated_advice_path(agent_home, report_date), llm_advice_path(agent_home, report_date))
    if script_name == "build_recommendation_delta.py":
        return recommendation_delta_path(agent_home, report_date).exists()
    if script_name == "build_evaluation_snapshot.py":
        return evaluation_snapshot_path(agent_home, report_date).exists()
    if script_name == "build_portfolio_report.py":
        return is_up_to_date(portfolio_report_path(agent_home, report_date), validated_advice_path(agent_home, report_date))
    return False


def run_step(
    script_name: str,
    agent_home: Path,
    report_date: str,
    demo: bool,
    extra_args: list[str] | None = None,
    step_label: str | None = None,
    record_step=None,
) -> float:
    started_at = time.perf_counter()
    label = step_label or script_name.replace(".py", "")
    if record_step is not None:
        record_step("start", script_name, label)
    print(f">>> START {label}", flush=True)
    command = [sys.executable, "-B", "-X", "utf8", str(SCRIPT_DIR / script_name)]
    if extra_args and any(flag in extra_args for flag in ("--base-date", "--review-date")):
        command.extend(["--agent-home", str(agent_home)])
    else:
        command.extend(["--agent-home", str(agent_home), "--date", report_date])
    if demo:
        command.append("--demo")
    if extra_args:
        command.extend(extra_args)
    try:
        subprocess.run(command, check=True)
    except Exception as exc:
        elapsed = time.perf_counter() - started_at
        if record_step is not None:
            record_step("finish", script_name, label, elapsed, "failed", str(exc))
        raise
    elapsed = time.perf_counter() - started_at
    print(f">>> DONE {label} ({elapsed:.1f}s)", flush=True)
    if record_step is not None:
        record_step("finish", script_name, label, elapsed, "ok", "")
    return elapsed


def run_parallel_steps(step_specs: list[dict], resume_existing: bool = False, record_step=None) -> dict[str, float]:
    results: dict[str, float] = {}
    errors: list[tuple[str, Exception]] = []
    with ThreadPoolExecutor(max_workers=len(step_specs)) as executor:
        futures = {
            executor.submit(
                maybe_run_step,
                spec["script_name"],
                spec["agent_home"],
                spec["report_date"],
                spec.get("demo", False),
                extra_args=spec.get("extra_args"),
                step_label=spec.get("step_label"),
                resume_existing=resume_existing,
                record_step=record_step,
            ): spec["script_name"]
            for spec in step_specs
        }
        for future in as_completed(futures):
            script_name = futures[future]
            try:
                results[script_name] = future.result()
            except Exception as exc:
                errors.append((script_name, exc))
    if errors:
        first_name, first_error = errors[0]
        raise RuntimeError(f"Parallel step failed: {first_name}: {first_error}") from first_error
    return results


def maybe_run_step(
    script_name: str,
    agent_home: Path,
    report_date: str,
    demo: bool,
    *,
    extra_args: list[str] | None = None,
    step_label: str | None = None,
    resume_existing: bool = False,
    record_step=None,
) -> float:
    if resume_existing and step_output_exists(agent_home, report_date, script_name, extra_args):
        label = step_label or script_name.replace(".py", "")
        print(f">>> SKIP {label} (resume_existing)", flush=True)
        if record_step is not None:
            record_step("finish", script_name, label, 0.0, "skipped", "")
        return 0.0
    return run_step(script_name, agent_home, report_date, demo, extra_args, step_label, record_step=record_step)


def run_intraday(agent_home: Path, report_date: str, demo: bool, llm_mock: bool, resume_existing: bool, record_step=None) -> dict[str, float]:
    timings: dict[str, float] = {}
    timings.update(
        run_parallel_steps(
            [
                {"script_name": "fetch_fund_quotes.py", "agent_home": agent_home, "report_date": report_date, "demo": demo},
                {"script_name": "fetch_fund_news.py", "agent_home": agent_home, "report_date": report_date, "demo": demo},
                {"script_name": "fetch_fund_profiles.py", "agent_home": agent_home, "report_date": report_date, "demo": False},
            ],
            resume_existing=resume_existing,
            record_step=record_step,
        )
    )
    timings.update(
        run_parallel_steps(
            [
                {"script_name": "score_funds.py", "agent_home": agent_home, "report_date": report_date, "demo": False},
                {"script_name": "fetch_intraday_proxies.py", "agent_home": agent_home, "report_date": report_date, "demo": demo},
                {"script_name": "fetch_realtime_estimate.py", "agent_home": agent_home, "report_date": report_date, "demo": False},
            ],
            resume_existing=resume_existing,
            record_step=record_step,
        )
    )
    timings["build_llm_context.py"] = maybe_run_step(
        "build_llm_context.py",
        agent_home,
        report_date,
        False,
        extra_args=["--mode", "intraday"],
        resume_existing=resume_existing,
        record_step=record_step,
    )
    timings["build_evidence_index.py"] = maybe_run_step(
        "build_evidence_index.py",
        agent_home,
        report_date,
        False,
        resume_existing=resume_existing,
        record_step=record_step,
    )
    timings["build_source_health_snapshot.py"] = maybe_run_step(
        "build_source_health_snapshot.py",
        agent_home,
        report_date,
        False,
        resume_existing=resume_existing,
        record_step=record_step,
    )
    multiagent_args = ["--mock"] if llm_mock else []
    if resume_existing:
        multiagent_args.append("--use-existing")
    timings["run_multiagent_research.py"] = maybe_run_step(
        "run_multiagent_research.py",
        agent_home,
        report_date,
        False,
        extra_args=multiagent_args or None,
        resume_existing=resume_existing,
        record_step=record_step,
    )
    timings["generate_llm_advice.py"] = maybe_run_step(
        "generate_llm_advice.py",
        agent_home,
        report_date,
        False,
        extra_args=["--mock"] if llm_mock else None,
        resume_existing=resume_existing,
        record_step=record_step,
    )
    timings["validate_llm_advice.py"] = maybe_run_step("validate_llm_advice.py", agent_home, report_date, False, resume_existing=resume_existing, record_step=record_step)
    timings["build_recommendation_delta.py"] = maybe_run_step("build_recommendation_delta.py", agent_home, report_date, False, resume_existing=resume_existing, record_step=record_step)
    timings["build_evaluation_snapshot.py"] = maybe_run_step("build_evaluation_snapshot.py", agent_home, report_date, False, resume_existing=resume_existing, record_step=record_step)
    timings["build_daily_report.py"] = maybe_run_step("build_daily_report.py", agent_home, report_date, False, resume_existing=resume_existing, record_step=record_step)
    timings["build_portfolio_report.py"] = maybe_run_step("build_portfolio_report.py", agent_home, report_date, False, resume_existing=resume_existing, record_step=record_step)
    timings["snapshot_run.py"] = run_step("snapshot_run.py", agent_home, report_date, False, record_step=record_step)
    return timings


def add_business_days(base_date: str, offset: int) -> str:
    current = datetime.strptime(base_date, "%Y-%m-%d").date()
    remaining = int(offset)
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current.isoformat()


def due_review_jobs(agent_home: Path, review_date: str) -> list[dict]:
    review_config = load_review_config(agent_home)
    if not review_config.get("review", {}).get("enabled", True):
        return []

    configured = sorted({int(value) for value in review_config.get("review", {}).get("horizons", [])})
    horizons = [0] + [value for value in configured if value > 0]
    candidate_dates: set[str] = set()
    validated_dir = agent_home / "db" / "validated_advice"
    trade_dir = agent_home / "db" / "trade_journal"
    if validated_dir.exists():
        for path in sorted(validated_dir.glob("*.json")):
            base_date = path.stem
            if len(base_date) == 10:
                candidate_dates.add(base_date)
    if trade_dir.exists():
        for path in sorted(trade_dir.glob("*.json")):
            base_date = path.stem
            if len(base_date) == 10:
                candidate_dates.add(base_date)
    if not candidate_dates:
        return []

    jobs: list[dict] = []
    for base_date in sorted(candidate_dates):
        has_advice = (validated_dir / f"{base_date}.json").exists()
        has_execution = (trade_dir / f"{base_date}.json").exists()
        for horizon in horizons:
            due_date = add_business_days(base_date, horizon)
            if due_date != review_date:
                continue
            jobs.append(
                {
                    "base_date": base_date,
                    "review_date": review_date,
                    "horizon": horizon,
                    "label": f"review_{base_date}_T{horizon}",
                    "has_advice": has_advice,
                    "has_execution": has_execution,
                }
            )
    jobs.sort(key=lambda item: (item["horizon"], item["base_date"]))
    return jobs


def run_nightly(agent_home: Path, report_date: str, demo: bool, resume_existing: bool = False, record_step=None) -> dict[str, float]:
    timings: dict[str, float] = {}
    timings.update(
        run_parallel_steps(
            [
                {"script_name": "fetch_fund_quotes.py", "agent_home": agent_home, "report_date": report_date, "demo": demo},
                {"script_name": "fetch_fund_news.py", "agent_home": agent_home, "report_date": report_date, "demo": demo},
                {"script_name": "fetch_fund_profiles.py", "agent_home": agent_home, "report_date": report_date},
            ],
            resume_existing=resume_existing,
            record_step=record_step,
        )
    )
    timings["revalue_portfolio_official_nav.py"] = run_step("revalue_portfolio_official_nav.py", agent_home, report_date, False, record_step=record_step)
    timings["run_learning_cycle.py"] = maybe_run_step(
        "run_learning_cycle.py",
        agent_home,
        report_date,
        False,
        resume_existing=resume_existing,
        record_step=record_step,
    )
    timings["build_evaluation_snapshot.py"] = maybe_run_step(
        "build_evaluation_snapshot.py",
        agent_home,
        report_date,
        False,
        resume_existing=resume_existing,
        record_step=record_step,
    )
    return timings


def print_timing_summary(mode: str, timings: dict[str, float]) -> None:
    total = sum(timings.values())
    print(f">>> SUMMARY {mode} total={total:.1f}s", flush=True)
    for name, seconds in sorted(timings.items(), key=lambda item: item[1], reverse=True):
        print(f">>> TIMING {name.replace('.py', '')} {seconds:.1f}s", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full daily fund pipeline.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--mode", default="intraday", choices=["intraday", "nightly"])
    parser.add_argument("--demo", action="store_true", help="Run the pipeline with deterministic mock data.")
    parser.add_argument("--llm-mock", action="store_true", help="Run the LLM stage in mock mode without calling the remote API.")
    parser.add_argument("--resume-existing", action="store_true", help="Resume from existing step outputs where safe.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    pipeline_started = time.perf_counter()
    manifest = new_run_manifest(agent_home, "daily_pipeline", args.mode, report_date)
    manifest_lock = threading.Lock()

    def record_step(event: str, step_name: str, display_name: str, seconds: float = 0.0, status: str = "ok", error: str = "") -> None:
        with manifest_lock:
            if event == "start":
                begin_step(manifest, step_name, display_name)
            else:
                finish_step(
                    manifest,
                    step_name,
                    seconds,
                    status=status,
                    error=error or None,
                    extra={"display_name": display_name},
                )
            write_manifest(agent_home, manifest)

    write_manifest(agent_home, manifest)
    print(f">>> PIPELINE_START mode={args.mode} date={report_date}", flush=True)

    try:
        preflight = perform_preflight(
            agent_home,
            args.mode,
            probe_llm=bool(args.mode == "intraday" and not args.demo and not args.llm_mock),
        )
        manifest["preflight_status"] = preflight["status"]
        manifest["preflight_output_path"] = preflight["output_path"]
        write_manifest(agent_home, manifest)
        if preflight["status"] == "failed":
            raise RuntimeError("Preflight failed. See db/preflight/latest.json for details.")
        if args.mode == "intraday":
            timings = run_intraday(agent_home, report_date, args.demo, args.llm_mock, args.resume_existing, record_step=record_step)
        else:
            timings = run_nightly(agent_home, report_date, args.demo, args.resume_existing, record_step=record_step)
        finalize_manifest(
            manifest,
            True,
            extra={
                "total_seconds": round(time.perf_counter() - pipeline_started, 3),
                "demo": bool(args.demo),
                "llm_mock": bool(args.llm_mock),
                "resume_existing": bool(args.resume_existing),
                "preflight_status": manifest.get("preflight_status", ""),
            },
        )
        write_manifest(agent_home, manifest)
    except Exception as exc:
        finalize_manifest(
            manifest,
            False,
            errors=[{"error": str(exc)}],
            extra={
                "total_seconds": round(time.perf_counter() - pipeline_started, 3),
                "demo": bool(args.demo),
                "llm_mock": bool(args.llm_mock),
                "resume_existing": bool(args.resume_existing),
                "preflight_status": manifest.get("preflight_status", ""),
            },
        )
        write_manifest(agent_home, manifest)
        raise

    print_timing_summary(args.mode, timings)
    print(f">>> PIPELINE_DONE mode={args.mode} total={(time.perf_counter() - pipeline_started):.1f}s", flush=True)


if __name__ == "__main__":
    main()
