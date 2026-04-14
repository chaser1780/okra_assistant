from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from common import estimated_nav_path, load_json, load_portfolio, quote_path, resolve_agent_home, resolve_date
from preflight_check import perform_preflight
from run_manifest_utils import begin_step, finalize_manifest, finish_step, new_run_manifest, write_manifest

SCRIPT_DIR = Path(__file__).resolve().parent


def run_step(script_name: str, agent_home: Path, report_date: str, record_step=None) -> float:
    started_at = time.perf_counter()
    label = script_name.replace(".py", "")
    if record_step is not None:
        record_step("start", script_name, label)
    print(f">>> START {label}", flush=True)
    command = [
        sys.executable,
        "-B",
        "-X",
        "utf8",
        str(SCRIPT_DIR / script_name),
        "--agent-home",
        str(agent_home),
        "--date",
        report_date,
    ]
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


def run_parallel_steps(script_names: list[str], agent_home: Path, report_date: str, record_step=None) -> dict[str, float]:
    results: dict[str, float] = {}
    errors: list[tuple[str, Exception]] = []
    with ThreadPoolExecutor(max_workers=max(1, len(script_names))) as executor:
        futures = {
            executor.submit(run_step, script_name, agent_home, report_date, record_step): script_name
            for script_name in script_names
        }
        for future in as_completed(futures):
            script_name = futures[future]
            try:
                results[script_name] = future.result()
            except Exception as exc:
                errors.append((script_name, exc))
    if errors:
        first_script, first_error = errors[0]
        raise RuntimeError(f"Parallel realtime step failed: {first_script}: {first_error}") from first_error
    return results


def safe_float(value) -> float | None:
    try:
        if value in (None, "", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def should_sync_units(agent_home: Path, report_date: str) -> bool:
    portfolio = load_portfolio(agent_home)
    quotes = load_json(quote_path(agent_home, report_date)) if quote_path(agent_home, report_date).exists() else {"funds": []}
    estimates = load_json(estimated_nav_path(agent_home, report_date)) if estimated_nav_path(agent_home, report_date).exists() else {"items": []}
    quote_by_code = {item.get("code"): item for item in quotes.get("funds", [])}
    estimate_by_code = {item.get("fund_code"): item for item in estimates.get("items", [])}

    for fund in portfolio.get("funds", []):
        current_value = safe_float(fund.get("current_value")) or 0.0
        if current_value <= 0:
            continue
        estimate = estimate_by_code.get(fund.get("fund_code"), {})
        quote = quote_by_code.get(fund.get("fund_code"), {})
        official_nav = safe_float(estimate.get("official_nav")) or safe_float(quote.get("nav"))
        official_nav_date = str(estimate.get("official_nav_date") or quote.get("as_of_date") or "").strip()
        stored_units = safe_float(fund.get("holding_units"))
        last_valuation_date = str(fund.get("last_valuation_date") or "").strip()
        units_source = str(fund.get("units_source") or "").strip()

        if official_nav is None or official_nav <= 0:
            continue
        if stored_units is None or stored_units <= 0:
            return True
        if official_nav_date and official_nav_date != last_valuation_date:
            return True
        if units_source != "derived_from_official_nav":
            return True
    return False


def record_skipped_step(script_name: str, label: str, reason: str, record_step=None) -> None:
    if record_step is not None:
        record_step("start", script_name, label)
        record_step("finish", script_name, label, 0.0, "skipped", reason)
    print(f">>> SKIP {label} ({reason})", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh realtime estimate/proxy data and build realtime profit snapshot.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    pipeline_started = time.perf_counter()
    manifest = new_run_manifest(agent_home, "realtime_monitor", "realtime", report_date)
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
    print(f">>> PIPELINE_START mode=realtime date={report_date}", flush=True)

    try:
        preflight = perform_preflight(agent_home, "realtime", probe_llm=False)
        manifest["preflight_status"] = preflight["status"]
        manifest["preflight_output_path"] = preflight["output_path"]
        write_manifest(agent_home, manifest)
        if preflight["status"] == "failed":
            raise RuntimeError("Preflight failed. See db/preflight/latest.json for details.")
        run_parallel_steps(
            ["fetch_intraday_proxies.py", "fetch_realtime_estimate.py"],
            agent_home,
            report_date,
            record_step=record_step,
        )
        if should_sync_units(agent_home, report_date):
            run_step("sync_portfolio_units.py", agent_home, report_date, record_step=record_step)
        else:
            record_skipped_step("sync_portfolio_units.py", "sync_portfolio_units", "units_already_current", record_step=record_step)
        run_step("build_realtime_profit.py", agent_home, report_date, record_step=record_step)
        finalize_manifest(
            manifest,
            True,
            extra={
                "total_seconds": round(time.perf_counter() - pipeline_started, 3),
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
                "preflight_status": manifest.get("preflight_status", ""),
            },
        )
        write_manifest(agent_home, manifest)
        raise
    print(f">>> PIPELINE_DONE mode=realtime total={(time.perf_counter() - pipeline_started):.1f}s", flush=True)


if __name__ == "__main__":
    main()
