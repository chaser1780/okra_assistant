from __future__ import annotations

import json
import os
import sys
import tomllib
from datetime import date, datetime, timedelta
from pathlib import Path


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def _read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_runtime_env(home: Path) -> dict[str, str]:
    temp = home / "temp"
    cache = home / "cache" / "pycache"
    log = home / "logs" / "desktop"
    for path in (temp, cache, log):
        path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "FUND_AGENT_HOME": str(home),
            "OKRA_PYTHON_EXE": sys.executable,
            "TEMP": str(temp),
            "TMP": str(temp),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(cache),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def desktop_log_path(home: Path, job_name: str, now: datetime | None = None) -> Path:
    current = now or datetime.now()
    log_dir = home / "logs" / "desktop"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{job_name}_{current.strftime('%Y-%m-%d_%H-%M-%S')}.log"


def build_python_script_command(script_path: Path, *args: str) -> list[str]:
    return [sys.executable, "-B", "-X", "utf8", str(script_path), *args]


def build_pipeline_command(home: Path, task_date: str, mode: str) -> list[str]:
    return build_python_script_command(
        home / "scripts" / "run_daily_pipeline.py",
        "--agent-home",
        str(home),
        "--date",
        task_date,
        "--mode",
        mode,
    )


def build_daily_first_open_command(home: Path, task_date: str, *, force: bool = False) -> list[str]:
    command = build_python_script_command(
        home / "scripts" / "run_daily_first_open.py",
        "--agent-home",
        str(home),
        "--date",
        task_date,
    )
    if force:
        command.append("--force")
    return command


def build_realtime_command(home: Path, task_date: str) -> list[str]:
    return build_python_script_command(
        home / "scripts" / "run_realtime_monitor.py",
        "--agent-home",
        str(home),
        "--date",
        task_date,
    )


def build_preflight_command(home: Path, scope: str) -> list[str]:
    return build_python_script_command(
        home / "scripts" / "preflight_check.py",
        "--agent-home",
        str(home),
        "--scope",
        scope,
    )


def build_replay_command(home: Path, start_date: str, end_date: str, mode: str, *, write_learning: bool = False, experiment_name: str = "") -> list[str]:
    command = build_python_script_command(
        home / "scripts" / "run_replay_experiment.py",
        "--agent-home",
        str(home),
        "--start-date",
        start_date,
        "--end-date",
        end_date,
        "--mode",
        mode,
    )
    if experiment_name.strip():
        command.extend(["--experiment-name", experiment_name.strip()])
    if write_learning:
        command.append("--write-learning")
    return command


def build_long_memory_approval_command(home: Path, memory_id: str, action: str, note: str = "") -> list[str]:
    command = build_python_script_command(
        home / "scripts" / "long_memory_store.py",
        "--agent-home",
        str(home),
        "--approve-memory-id",
        memory_id,
        "--action",
        action,
    )
    if note.strip():
        command.extend(["--note", note.strip()])
    return command


def build_trade_command(
    home: Path,
    trade_date: str,
    fund_code: str,
    fund_name: str,
    action: str,
    amount_text: str,
    note: str,
    suggestion_id: str,
    extra_args: list[str],
) -> list[str]:
    return build_python_script_command(
        home / "scripts" / "record_trade.py",
        "--agent-home",
        str(home),
        "--date",
        trade_date,
        "--fund-code",
        fund_code,
        "--fund-name",
        fund_name,
        "--action",
        action,
        "--amount",
        amount_text,
        "--note",
        note,
        *(["--suggestion-id", suggestion_id] if suggestion_id else []),
        *extra_args,
    )


def build_portfolio_sync_preview_command(home: Path, sync_date: str, image_paths: list[str], provider: str = "alipay") -> list[str]:
    return build_python_script_command(
        home / "scripts" / "sync_portfolio_from_screenshots.py",
        "preview",
        "--agent-home",
        str(home),
        "--date",
        sync_date,
        "--provider",
        provider,
        "--images",
        *image_paths,
    )


def build_portfolio_sync_apply_command(home: Path, sync_date: str, preview_path: str, drop_missing: bool, auto_add_new: bool) -> list[str]:
    return build_python_script_command(
        home / "scripts" / "sync_portfolio_from_screenshots.py",
        "apply",
        "--agent-home",
        str(home),
        "--date",
        sync_date,
        "--preview-path",
        preview_path,
        *(["--drop-missing"] if drop_missing else []),
        *(["--auto-add-new"] if auto_add_new else []),
    )


def should_resume_intraday(home: Path, report_date: str) -> bool:
    context_exists = (home / "db" / "llm_context" / f"{report_date}.json").exists()
    aggregate_exists = (home / "db" / "agent_outputs" / report_date / "aggregate.json").exists()
    advice_exists = (home / "db" / "llm_advice" / f"{report_date}.json").exists()
    validated_exists = (home / "db" / "validated_advice" / f"{report_date}.json").exists()
    return (context_exists or aggregate_exists or advice_exists) and not validated_exists


def should_resume_nightly(home: Path, report_date: str) -> bool:
    valuation_exists = (home / "db" / "portfolio_valuation" / f"{report_date}.json").exists()
    review_report_exists = (home / "reports" / "daily" / f"{report_date}_review.md").exists()
    review_batch_exists = any(
        _read_json(path, {}).get("review_date") == report_date
        for path in (home / "db" / "review_results").glob("*.json")
    ) if (home / "db" / "review_results").exists() else False
    return (valuation_exists or review_batch_exists) and not review_report_exists


def _parse_schedule_time(value: str | None, default: str) -> tuple[int, int]:
    text = str(value or default).strip()
    try:
        hour, minute = text.split(":", 1)
        return int(hour), int(minute)
    except Exception:
        hour, minute = default.split(":", 1)
        return int(hour), int(minute)


def _is_business_day(day: date) -> bool:
    return day.weekday() < 5


def _previous_business_day(day: date) -> date:
    current = day - timedelta(days=1)
    while not _is_business_day(current):
        current -= timedelta(days=1)
    return current


def _business_dates_between(start_exclusive: date, end_inclusive: date) -> list[str]:
    results: list[str] = []
    current = start_exclusive + timedelta(days=1)
    while current <= end_inclusive:
        if _is_business_day(current):
            results.append(current.isoformat())
        current += timedelta(days=1)
    return results


def latest_nightly_target_date(home: Path, now: datetime | None = None) -> str:
    strategy = _read_toml(home / "config" / "strategy.toml")
    schedule = strategy.get("schedule", {}) or {}
    current = now or datetime.now()
    today = current.date()
    nightly_hour, nightly_minute = _parse_schedule_time(schedule.get("nightly_start"), "21:00")
    nightly_reached = (current.hour, current.minute) >= (nightly_hour, nightly_minute)
    if _is_business_day(today) and nightly_reached:
        return today.isoformat()
    return _previous_business_day(today).isoformat()


def pending_nightly_catchup_dates(home: Path, portfolio_as_of_date: str, now: datetime | None = None) -> list[str]:
    strategy = _read_toml(home / "config" / "strategy.toml")
    schedule = strategy.get("schedule", {}) or {}
    if not bool(schedule.get("run_if_missed_on_next_boot", True)):
        return []
    try:
        start_date = datetime.strptime(str(portfolio_as_of_date or "").strip(), "%Y-%m-%d").date()
    except Exception:
        return []
    target_text = latest_nightly_target_date(home, now=now)
    target_date = datetime.strptime(target_text, "%Y-%m-%d").date()
    if start_date >= target_date:
        return []
    return _business_dates_between(start_date, target_date)


def should_autorun_intraday_on_boot(home: Path, report_date: str, now: datetime | None = None) -> bool:
    strategy = _read_toml(home / "config" / "strategy.toml")
    schedule = strategy.get("schedule", {}) or {}
    if not bool(schedule.get("run_if_missed_on_next_boot", True)):
        return False
    try:
        report_day = datetime.strptime(report_date, "%Y-%m-%d").date()
    except Exception:
        return False
    if not _is_business_day(report_day):
        return False
    current = now or datetime.now()
    intraday_hour, intraday_minute = _parse_schedule_time(schedule.get("intraday_start"), "14:00")
    if (current.hour, current.minute) < (intraday_hour, intraday_minute):
        return False
    validated_exists = (home / "db" / "validated_advice" / f"{report_date}.json").exists()
    return should_resume_intraday(home, report_date) or not validated_exists


def should_refresh_realtime_on_boot(home: Path, report_date: str, now: datetime | None = None, freshness_minutes: int = 15) -> bool:
    strategy = _read_toml(home / "config" / "strategy.toml")
    schedule = strategy.get("schedule", {}) or {}
    if not bool(schedule.get("run_if_missed_on_next_boot", True)):
        return False
    try:
        report_day = datetime.strptime(report_date, "%Y-%m-%d").date()
    except Exception:
        return False
    if not _is_business_day(report_day):
        return False
    current = now or datetime.now()
    intraday_hour, intraday_minute = _parse_schedule_time(schedule.get("intraday_start"), "14:00")
    if (current.hour, current.minute) < (intraday_hour, intraday_minute):
        return False
    snapshot = home / "db" / "realtime_monitor" / f"{report_date}.json"
    if not snapshot.exists():
        return True
    age_seconds = max(0.0, current.timestamp() - snapshot.stat().st_mtime)
    return age_seconds >= freshness_minutes * 60
