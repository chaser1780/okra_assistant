from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

from common import actual_trade_dir, load_review_config, resolve_agent_home, resolve_date
from common import (
    committee_advice_path,
    committee_decision_bundle_path,
    evidence_index_path,
    estimated_nav_path,
    fund_profile_path,
    intraday_proxy_path,
    learning_report_path,
    legacy_portfolio_path,
    llm_advice_path,
    llm_context_path,
    long_memory_export_path,
    news_path,
    portfolio_state_current_path,
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
from rag_config import rag_agent_shadow_settings, rag_db_path
from rag_index_store import connect_store
from run_manifest_utils import begin_step, finalize_manifest, finish_step, new_run_manifest, write_manifest

SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class PipelineStep:
    script_name: str
    outputs: tuple = field(default_factory=tuple)
    inputs: tuple = field(default_factory=tuple)
    can_resume: bool = True
    stale_policy: str = "outputs_newer_than_inputs"

    def output_paths(self, agent_home: Path, report_date: str) -> list[Path]:
        return [builder(agent_home, report_date) for builder in self.outputs]

    def input_paths(self, agent_home: Path, report_date: str) -> list[Path]:
        return [builder(agent_home, report_date) for builder in self.inputs]

    def is_fresh(self, agent_home: Path, report_date: str) -> bool:
        if not self.can_resume:
            return False
        outputs = self.output_paths(agent_home, report_date)
        if not outputs or any(not path.exists() for path in outputs):
            return False
        inputs = [path for path in self.input_paths(agent_home, report_date) if path.exists()]
        if not inputs:
            return True
        oldest_output_mtime = min(path.stat().st_mtime for path in outputs)
        newest_input_mtime = max(path.stat().st_mtime for path in inputs)
        return oldest_output_mtime >= newest_input_mtime


def _dated_path(builder):
    return lambda agent_home, report_date: builder(agent_home, report_date)


def _fixed_path(builder):
    return lambda agent_home, report_date: builder(agent_home)


def _config_path(name: str):
    return lambda agent_home, report_date: agent_home / "config" / name


def _project_path(*parts: str):
    return lambda agent_home, report_date: SCRIPT_DIR.parent.joinpath(*parts)


def _stable_digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _rag_manifest_freshness_marker(agent_home: Path, report_date: str) -> Path:
    marker = agent_home / "db" / "rag" / "active_manifest_set.sha256"
    try:
        db_path = rag_db_path(agent_home)
        if not db_path.exists():
            return marker
        manifest_rows = []
        with connect_store(agent_home) as conn:
            manifest_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT scope_key, manifest_id, activated_at
                    FROM active_manifests
                    ORDER BY scope_key
                    """
                ).fetchall()
            ]
        if not manifest_rows and not marker.exists():
            return marker
        digest = _stable_digest(manifest_rows)
        previous = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
        if digest != previous:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(digest, encoding="utf-8")
    except Exception:
        pass
    return marker


def _is_up_to_date(target: Path, dependency: Path | None = None) -> bool:
    if not target.exists():
        return False
    if dependency is None or not dependency.exists():
        return True
    return target.stat().st_mtime >= dependency.stat().st_mtime


STEP_OUTPUT_CHECKS = {
    "fetch_fund_quotes.py": PipelineStep("fetch_fund_quotes.py", outputs=(_dated_path(quote_path),)),
    "fetch_fund_news.py": PipelineStep("fetch_fund_news.py", outputs=(_dated_path(news_path),)),
    "fetch_fund_profiles.py": PipelineStep("fetch_fund_profiles.py", outputs=(_dated_path(fund_profile_path),)),
    "score_funds.py": PipelineStep(
        "score_funds.py",
        outputs=(_dated_path(score_path),),
        inputs=(_dated_path(quote_path), _dated_path(news_path)),
    ),
    "fetch_intraday_proxies.py": PipelineStep("fetch_intraday_proxies.py", outputs=(_dated_path(intraday_proxy_path),)),
    "fetch_realtime_estimate.py": PipelineStep(
        "fetch_realtime_estimate.py",
        outputs=(_dated_path(estimated_nav_path),),
        inputs=(_dated_path(quote_path),),
    ),
    "build_llm_context.py": PipelineStep(
        "build_llm_context.py",
        outputs=(_dated_path(llm_context_path),),
        inputs=(
            _dated_path(quote_path),
            _dated_path(news_path),
            _dated_path(fund_profile_path),
            _dated_path(intraday_proxy_path),
            _dated_path(estimated_nav_path),
            _fixed_path(portfolio_state_current_path),
            _fixed_path(legacy_portfolio_path),
            _fixed_path(long_memory_export_path),
        ),
    ),
    "build_evidence_index.py": PipelineStep(
        "build_evidence_index.py",
        outputs=(_dated_path(evidence_index_path),),
        inputs=(_dated_path(llm_context_path),),
    ),
    "build_source_health_snapshot.py": PipelineStep(
        "build_source_health_snapshot.py",
        outputs=(_dated_path(source_health_path),),
        inputs=(_dated_path(llm_context_path), _dated_path(quote_path), _dated_path(news_path), _dated_path(intraday_proxy_path), _dated_path(estimated_nav_path)),
    ),
    "run_learning_cycle.py": PipelineStep(
        "run_learning_cycle.py",
        outputs=(_dated_path(learning_report_path),),
        inputs=(_dated_path(validated_advice_path),),
    ),
    "run_promoted_advice_chain.py": PipelineStep(
        "run_promoted_advice_chain.py",
        outputs=(_dated_path(llm_advice_path), _dated_path(committee_advice_path), _dated_path(committee_decision_bundle_path), _dated_path(validated_advice_path)),
        inputs=(
            _dated_path(llm_context_path),
            _dated_path(score_path),
            _fixed_path(portfolio_state_current_path),
            _fixed_path(legacy_portfolio_path),
            _fixed_path(long_memory_export_path),
            _config_path("strategy.toml"),
            _project_path("scripts", "run_promoted_advice_chain.py"),
            _project_path("scripts", "build_layered_seed.py"),
            _project_path("scripts", "build_action_ticket_shadow.py"),
            _project_path("scripts", "build_layered_retrieval_pack.py"),
            _project_path("scripts", "action_debate_graph.py"),
            _project_path("scripts", "build_official_advice_compat_preview.py"),
            _project_path("scripts", "promoted_advice_guardrails.py"),
        ),
    ),
    "build_recommendation_delta.py": PipelineStep(
        "build_recommendation_delta.py",
        outputs=(_dated_path(recommendation_delta_path),),
        inputs=(_dated_path(validated_advice_path),),
    ),
    "build_evaluation_snapshot.py": PipelineStep(
        "build_evaluation_snapshot.py",
        outputs=(_dated_path(evaluation_snapshot_path),),
        inputs=(_dated_path(validated_advice_path),),
    ),
    "build_daily_report.py": PipelineStep(
        "build_daily_report.py",
        outputs=(_dated_path(report_path),),
        inputs=(_dated_path(validated_advice_path), _dated_path(llm_context_path)),
    ),
    "build_portfolio_report.py": PipelineStep(
        "build_portfolio_report.py",
        outputs=(_dated_path(portfolio_report_path),),
        inputs=(_dated_path(validated_advice_path), _fixed_path(portfolio_state_current_path), _fixed_path(legacy_portfolio_path)),
    ),
    "snapshot_run.py": PipelineStep("snapshot_run.py", can_resume=False),
    "rag_ingest.py": PipelineStep("rag_ingest.py", can_resume=False),
    "rag_eval.py": PipelineStep("rag_eval.py", can_resume=False),
}


def step_output_exists(agent_home: Path, report_date: str, script_name: str, extra_args: list[str] | None = None) -> bool:
    step = STEP_OUTPUT_CHECKS.get(script_name)
    return bool(step and step.is_fresh(agent_home, report_date))


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


def _rag_shadow_enabled(agent_home: Path, cli_enabled: bool = False) -> bool:
    settings = rag_agent_shadow_settings(agent_home)
    return bool(cli_enabled or settings.get("enabled", False))


def run_rag_shadow(agent_home: Path, report_date: str, *, strict: bool = False, record_step=None) -> dict[str, float]:
    settings = rag_agent_shadow_settings(agent_home)
    timings: dict[str, float] = {}
    failures: list[str] = []

    def run_optional(script_name: str, extra_args: list[str], label: str) -> None:
        try:
            timings[script_name] = run_step(
                script_name,
                agent_home,
                report_date,
                False,
                extra_args=extra_args,
                step_label=label,
                record_step=record_step,
            )
        except Exception as exc:
            message = f"{script_name}: {exc}"
            failures.append(message)
            print(f">>> RAG_SHADOW_DEGRADED {message}", flush=True)

    run_optional("rag_ingest.py", ["--write", "--all"], "rag_shadow_ingest")
    if settings.get("compare_legacy", True):
        eval_args = ["--compare-legacy"]
        if not settings.get("write_trace", True):
            eval_args.append("--no-trace")
        run_optional("rag_eval.py", eval_args, "rag_shadow_eval")

    if failures and strict:
        raise RuntimeError("; ".join(failures))
    if failures:
        timings["rag_shadow_degraded"] = 0.0
    return timings


def run_intraday(
    agent_home: Path,
    report_date: str,
    demo: bool,
    llm_mock: bool,
    resume_existing: bool,
    record_step=None,
    rag_shadow: bool = False,
    rag_strict: bool = False,
) -> dict[str, float]:
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
    timings["run_promoted_advice_chain.py"] = maybe_run_step(
        "run_promoted_advice_chain.py",
        agent_home,
        report_date,
        False,
        extra_args=["--llm-mock"] if llm_mock else None,
        resume_existing=resume_existing,
        record_step=record_step,
    )
    timings["build_recommendation_delta.py"] = maybe_run_step("build_recommendation_delta.py", agent_home, report_date, False, resume_existing=resume_existing, record_step=record_step)
    timings["build_evaluation_snapshot.py"] = maybe_run_step("build_evaluation_snapshot.py", agent_home, report_date, False, resume_existing=resume_existing, record_step=record_step)
    timings["build_daily_report.py"] = maybe_run_step("build_daily_report.py", agent_home, report_date, False, resume_existing=resume_existing, record_step=record_step)
    timings["build_portfolio_report.py"] = maybe_run_step("build_portfolio_report.py", agent_home, report_date, False, resume_existing=resume_existing, record_step=record_step)
    if _rag_shadow_enabled(agent_home, rag_shadow):
        timings.update(run_rag_shadow(agent_home, report_date, strict=rag_strict, record_step=record_step))
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
    trade_dir = actual_trade_dir(agent_home)
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
    parser.add_argument("--phase", choices=["intraday", "nightly", "realtime", "memory"], help="Compatibility phase alias.")
    parser.add_argument("--demo", action="store_true", help="Run the pipeline with deterministic mock data.")
    parser.add_argument("--llm-mock", action="store_true", help="Run the LLM stage in mock mode without calling the remote API.")
    parser.add_argument("--resume-existing", action="store_true", help="Resume from existing step outputs where safe.")
    parser.add_argument("--rag-shadow", action="store_true", help="Run optional RAG shadow ingest/eval without changing final advice.")
    parser.add_argument("--rag-strict", action="store_true", help="Fail the pipeline if RAG shadow ingest/eval fails.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    selected_mode = args.phase or args.mode
    if selected_mode in {"realtime", "memory"}:
        raise RuntimeError(f"Phase '{selected_mode}' is not handled by run_daily_pipeline.py. Use run_realtime_monitor.py or run_long_memory_analysis.py.")
    pipeline_started = time.perf_counter()
    manifest = new_run_manifest(agent_home, "daily_pipeline", selected_mode, report_date)
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
    print(f">>> PIPELINE_START mode={selected_mode} date={report_date}", flush=True)

    try:
        preflight = perform_preflight(
            agent_home,
            selected_mode,
            probe_llm=bool(selected_mode == "intraday" and not args.demo and not args.llm_mock),
        )
        manifest["preflight_status"] = preflight["status"]
        manifest["preflight_output_path"] = preflight["output_path"]
        write_manifest(agent_home, manifest)
        if preflight["status"] == "failed":
            raise RuntimeError("Preflight failed. See db/preflight/latest.json for details.")
        if selected_mode == "intraday":
            timings = run_intraday(
                agent_home,
                report_date,
                args.demo,
                args.llm_mock,
                args.resume_existing,
                record_step=record_step,
                rag_shadow=bool(args.rag_shadow),
                rag_strict=bool(args.rag_strict),
            )
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

    print_timing_summary(selected_mode, timings)
    print(f">>> PIPELINE_DONE mode={selected_mode} total={(time.perf_counter() - pipeline_started):.1f}s", flush=True)


if __name__ == "__main__":
    main()
