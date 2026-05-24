from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
import tomllib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PORTFOLIO_RUNTIME_FIELDS = {
    "current_value",
    "holding_pnl",
    "holding_return_pct",
    "holding_units",
    "cost_basis_value",
    "last_valuation_nav",
    "last_valuation_date",
    "last_official_nav",
    "last_official_nav_date",
    "units_source",
    "actual_daily_pnl",
    "actual_daily_pnl_date",
    "actual_daily_pnl_source",
    "official_daily_pnl",
    "official_daily_pnl_date",
    "official_daily_pnl_source",
    "official_daily_pnl_status",
    "official_daily_pnl_reason",
    "official_daily_pnl_units",
    "official_daily_pnl_nav",
    "official_daily_pnl_previous_nav",
    "official_daily_pnl_previous_nav_date",
    "actual_position_synced_at",
    "last_real_position_date",
    "real_position_source",
}

DEFAULT_AGENT_HOME = Path(r"F:\okra_assistant")
try:
    SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    from datetime import timezone

    SHANGHAI_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 0
TODAY_ANALYSIS_STALE_SECONDS = 20 * 60
REQUIRED_DIRS = (
    "config",
    "raw/quotes",
    "raw/news",
    "raw/fund_profiles",
    "db/news_query_plans",
    "db/source_health",
    "db/evidence_index",
    "db/recommendation_delta",
    "db/evaluation_snapshots",
    "db/replay_experiments",
    "db/daily_scores",
    "db/intraday_proxies",
    "db/realtime_monitor",
    "db/llm_context",
    "db/llm_advice",
    "db/committee_advice",
    "db/committee_decision_bundle",
    "db/llm_raw",
    "db/validated_advice",
    "db/decisions",
    "db/decision_ledger",
    "db/decision_latest",
    "db/agent_outputs",
    "db/agent_snapshots",
    "db/locks",
    "db/portfolio_valuation",
    "db/portfolio_state",
    "db/portfolio_state/snapshots",
    "db/portfolio_state/events",
    "db/portfolio_imports",
    "db/portfolio_daily_pnl",
    "db/preflight",
    "db/run_manifests",
    "db/review_results",
    "db/execution_reviews",
    "db/execution_status",
    "db/execution_sync",
    "db/execution_sync/actual_trades",
    "db/execution_sync/settlement_events",
    "db/execution_sync/position_snapshots",
    "db/execution_sync/reconciliation_reports",
    "db/execution_sync/imports",
    "db/execution_sync/imports/alipay_screenshots",
    "db/execution_sync/imports/parsed",
    "db/long_memory",
    "db/long_memory/funds",
    "db/long_memory/market",
    "db/long_memory/market/regime_daily",
    "db/long_memory/execution",
    "db/long_memory/portfolio",
    "db/long_memory/candidates",
    "db/long_memory/approvals",
    "db/long_memory/exports",
    "db/long_memory/cycles",
    "db/long_memory/cycles/pending",
    "db/long_memory/cycles/completed",
    "db/long_memory/cycles/failed",
    "db/legacy",
    "db/legacy/review_memory",
    "db/legacy/trade_journal",
    "db/daily_workspace",
    "db/estimated_nav",
    "db/fund_nav_history",
    "db/benchmark_history",
    "db/proxy_history",
    "reports/daily",
    "docs",
    "logs",
    "logs/llm",
    "logs/preflight",
    "logs/tasks",
    "temp",
    "cache",
)

MOJIBAKE_HINTS = set("?\ufffd")
COMMON_TEXT_HINTS = set("基金收益建议组合持仓实时详情智能体复盘夜间设置数据金额买卖现金回写估值策略研究市场风格主题新闻置信度风险")


def _text_quality(text: str) -> int:
    readable = sum(
        ch.isascii() or "\u4e00" <= ch <= "\u9fff" or ch in "，。；：！？（）《》【】、“”‘’—·+-/% "
        for ch in text
    )
    suspicious = sum(ch in MOJIBAKE_HINTS for ch in text)
    common = sum(ch in COMMON_TEXT_HINTS for ch in text)
    return readable + common * 2 - suspicious * 2


def repair_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    current = text.replace("\ufeff", "")
    for _ in range(2):
        try:
            candidate = current.encode("gb18030").decode("utf-8")
        except UnicodeError:
            break
        if candidate == current:
            break
        if _text_quality(candidate) < _text_quality(current):
            break
        current = candidate
    return current


def repair_data(value):
    if isinstance(value, str):
        return repair_text(value)
    if isinstance(value, list):
        return [repair_data(item) for item in value]
    if isinstance(value, dict):
        return {repair_data(key) if isinstance(key, str) else key: repair_data(item) for key, item in value.items()}
    return value


def resolve_agent_home(candidate: str | None = None) -> Path:
    value = candidate or os.getenv("FUND_AGENT_HOME") or str(DEFAULT_AGENT_HOME)
    return Path(value).expanduser()


def ensure_layout(agent_home: Path) -> None:
    for relative in REQUIRED_DIRS:
        (agent_home / relative).mkdir(parents=True, exist_ok=True)


def resolve_date(date_text: str | None = None) -> str:
    if date_text:
        return datetime.strptime(date_text, "%Y-%m-%d").date().isoformat()
    return date.today().isoformat()


def shanghai_now(now: datetime | None = None) -> datetime:
    current = now.astimezone(SHANGHAI_TZ) if now and now.tzinfo else now
    return current or datetime.now(SHANGHAI_TZ)


def today_shanghai(now: datetime | None = None) -> str:
    return shanghai_now(now).date().isoformat()


def market_close_time() -> datetime_time:
    return datetime_time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)


def trading_calendar_path(agent_home: Path) -> Path:
    return agent_home / "config" / "trading_calendar.json"


def load_trading_calendar(agent_home: Path) -> dict:
    path = trading_calendar_path(agent_home)
    if not path.exists():
        return {"holidays": [], "makeup_trading_days": []}
    return repair_data(json.loads(path.read_text(encoding="utf-8")))


def _calendar_sets(agent_home: Path) -> tuple[set[str], set[str]]:
    payload = load_trading_calendar(agent_home)
    holidays = {str(item).strip() for item in payload.get("holidays", []) or [] if str(item).strip()}
    makeup_days = {str(item).strip() for item in payload.get("makeup_trading_days", []) or [] if str(item).strip()}
    return holidays, makeup_days


def is_trading_day(agent_home: Path, day: str | date) -> bool:
    target = parse_date_text(day) if isinstance(day, str) else day
    if target is None:
        return False
    day_text = target.isoformat()
    holidays, makeup_days = _calendar_sets(agent_home)
    if day_text in makeup_days:
        return True
    if day_text in holidays:
        return False
    return target.weekday() < 5


def previous_trading_day(agent_home: Path, day: str | date) -> str:
    target = parse_date_text(day) if isinstance(day, str) else day
    if target is None:
        raise ValueError(f"Invalid day: {day}")
    current = target - timedelta(days=1)
    while not is_trading_day(agent_home, current):
        current -= timedelta(days=1)
    return current.isoformat()


def trading_days_between(agent_home: Path, start_exclusive: str | date, end_inclusive: str | date) -> list[str]:
    start_day = parse_date_text(start_exclusive) if isinstance(start_exclusive, str) else start_exclusive
    end_day = parse_date_text(end_inclusive) if isinstance(end_inclusive, str) else end_inclusive
    if start_day is None or end_day is None or start_day >= end_day:
        return []
    current = start_day + timedelta(days=1)
    results: list[str] = []
    while current <= end_day:
        if is_trading_day(agent_home, current):
            results.append(current.isoformat())
        current += timedelta(days=1)
    return results


def analysis_quality_for_start(agent_home: Path, report_date: str, started_at: datetime) -> str:
    local = started_at.astimezone(SHANGHAI_TZ)
    if local.date().isoformat() != report_date:
        return "after_close" if local.date().isoformat() > report_date else "pre_close"
    if not is_trading_day(agent_home, report_date):
        return "after_close"
    return "after_close" if local.time() >= market_close_time() else "pre_close"


def parse_date_text(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def business_day_gap(older: str | date | None, newer: str | date | None) -> int | None:
    older_date = parse_date_text(older) if isinstance(older, str) or older is None else older
    newer_date = parse_date_text(newer) if isinstance(newer, str) or newer is None else newer
    if older_date is None or newer_date is None:
        return None
    if older_date == newer_date:
        return 0
    if older_date > newer_date:
        return -business_day_gap(newer_date, older_date)
    current = older_date
    gap = 0
    while current < newer_date:
        current = current.fromordinal(current.toordinal() + 1)
        if current.weekday() < 5:
            gap += 1
    return gap


def classify_official_nav_freshness(report_date: str, as_of_date: str | None) -> dict:
    gap = business_day_gap(as_of_date, report_date)
    if gap is None:
        return {
            "status": "unknown",
            "label": "官方净值日期未知",
            "business_day_gap": None,
            "is_acceptable": False,
            "is_delayed": True,
        }
    if gap == 0:
        return {
            "status": "same_day",
            "label": "官方净值为当日",
            "business_day_gap": 0,
            "is_acceptable": True,
            "is_delayed": False,
        }
    if gap == 1:
        return {
            "status": "previous_trading_day",
            "label": "官方净值为上一交易日",
            "business_day_gap": 1,
            "is_acceptable": True,
            "is_delayed": False,
        }
    if gap > 1:
        return {
            "status": "delayed",
            "label": f"官方净值滞后 {gap} 个交易日",
            "business_day_gap": gap,
            "is_acceptable": False,
            "is_delayed": True,
        }
    return {
        "status": "future_date",
        "label": "官方净值日期异常（晚于报告日）",
        "business_day_gap": gap,
        "is_acceptable": False,
        "is_delayed": True,
    }


def classify_intraday_freshness(report_date: str, data_date: str | None, source_name: str) -> dict:
    gap = business_day_gap(data_date, report_date)
    if gap is None:
        return {
            "status": "unknown",
            "label": f"{source_name} 日期未知",
            "business_day_gap": None,
            "is_fresh": False,
            "is_stale": True,
        }
    if gap == 0:
        return {
            "status": "same_day",
            "label": f"{source_name}为当日",
            "business_day_gap": 0,
            "is_fresh": True,
            "is_stale": False,
        }
    if gap > 0:
        return {
            "status": "cross_day",
            "label": f"{source_name}跨日，滞后 {gap} 个交易日",
            "business_day_gap": gap,
            "is_fresh": False,
            "is_stale": True,
        }
    return {
        "status": "future_date",
        "label": f"{source_name}日期异常（晚于报告日）",
        "business_day_gap": gap,
        "is_fresh": False,
        "is_stale": True,
    }


def timestamp_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_settings(agent_home: Path) -> dict:
    return tomllib.loads((agent_home / "config" / "settings.toml").read_text(encoding="utf-8"))


def load_project_toml(agent_home: Path) -> dict:
    path = agent_home / "project.toml"
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_strategy(agent_home: Path) -> dict:
    return tomllib.loads((agent_home / "config" / "strategy.toml").read_text(encoding="utf-8"))


def load_review_config(agent_home: Path) -> dict:
    return tomllib.loads((agent_home / "config" / "review.toml").read_text(encoding="utf-8"))


def load_agents_config(agent_home: Path) -> dict:
    return tomllib.loads((agent_home / "config" / "agents.toml").read_text(encoding="utf-8"))


def load_realtime_valuation_config(agent_home: Path) -> dict:
    return tomllib.loads((agent_home / "config" / "realtime_valuation.toml").read_text(encoding="utf-8"))


def load_llm_config(agent_home: Path) -> dict:
    return tomllib.loads((agent_home / "config" / "llm.toml").read_text(encoding="utf-8"))


def load_watchlist(agent_home: Path) -> dict:
    return repair_data(json.loads((agent_home / "config" / "watchlist.json").read_text(encoding="utf-8")))


def load_portfolio(agent_home: Path) -> dict:
    current_path = portfolio_state_current_path(agent_home)
    legacy_path = legacy_portfolio_path(agent_home)
    definition_path = portfolio_definition_path(agent_home)
    if current_path.exists():
        return repair_data(json.loads(current_path.read_text(encoding="utf-8")))

    payload = repair_data(json.loads(legacy_path.read_text(encoding="utf-8")))
    if not definition_path.exists():
        definition = {
            "portfolio_name": payload.get("portfolio_name", ""),
            "bootstrapped_at": timestamp_now(),
            "bootstrapped_from": str(legacy_path),
            "base_as_of_date": payload.get("as_of_date", ""),
            "funds": [],
        }
        for fund in payload.get("funds", []):
            opening_state = {
                "current_value": fund.get("current_value", 0.0),
                "holding_pnl": fund.get("holding_pnl", 0.0),
                "holding_return_pct": fund.get("holding_return_pct", 0.0),
                "holding_units": fund.get("holding_units", 0.0),
                "cost_basis_value": fund.get("cost_basis_value", 0.0),
                "last_valuation_nav": fund.get("last_valuation_nav"),
                "last_valuation_date": fund.get("last_valuation_date", ""),
                "last_official_nav": fund.get("last_official_nav"),
                "last_official_nav_date": fund.get("last_official_nav_date", ""),
                "units_source": fund.get("units_source", ""),
                "actual_daily_pnl": fund.get("actual_daily_pnl"),
                "actual_daily_pnl_date": fund.get("actual_daily_pnl_date", ""),
                "actual_daily_pnl_source": fund.get("actual_daily_pnl_source", ""),
                "official_daily_pnl": fund.get("official_daily_pnl"),
                "official_daily_pnl_date": fund.get("official_daily_pnl_date", ""),
                "official_daily_pnl_source": fund.get("official_daily_pnl_source", ""),
                "official_daily_pnl_status": fund.get("official_daily_pnl_status", ""),
                "official_daily_pnl_reason": fund.get("official_daily_pnl_reason", ""),
                "official_daily_pnl_units": fund.get("official_daily_pnl_units"),
                "official_daily_pnl_nav": fund.get("official_daily_pnl_nav"),
                "official_daily_pnl_previous_nav": fund.get("official_daily_pnl_previous_nav"),
                "official_daily_pnl_previous_nav_date": fund.get("official_daily_pnl_previous_nav_date", ""),
                "actual_position_synced_at": fund.get("actual_position_synced_at", ""),
                "last_real_position_date": fund.get("last_real_position_date", ""),
                "real_position_source": fund.get("real_position_source", ""),
            }
            config_fields = {
                key: value
                for key, value in fund.items()
                if key not in opening_state and key not in PORTFOLIO_RUNTIME_FIELDS
            }
            definition["funds"].append({**config_fields, "opening_state": opening_state})
        dump_json(definition_path, definition)
    dump_json(current_path, payload)
    return payload


def load_market_overrides(agent_home: Path) -> dict:
    path = agent_home / "config" / "market_overrides.json"
    if not path.exists():
        return {"biases": []}
    return repair_data(json.loads(path.read_text(encoding="utf-8")))


def load_long_memory_compat_view(agent_home: Path) -> dict:
    payload = _review_memory_from_long_memory(agent_home)
    if payload is not None:
        return payload
    path = legacy_review_memory_path(agent_home)
    if not path.exists():
        return _empty_review_memory()
    return repair_data(json.loads(path.read_text(encoding="utf-8")))


def dump_json(path: Path, payload: dict | list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    last_error = None
    for attempt in range(12):
        try:
            temp_path.replace(path)
            return path
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.03 * (attempt + 1))
    if temp_path.exists():
        try:
            temp_path.unlink()
        except OSError:
            pass
    raise last_error or PermissionError(f"Failed to replace {path}")
    return path


def lock_path(agent_home: Path, name: str) -> Path:
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(name or "default"))
    if not safe_name.endswith(".lock"):
        safe_name = f"{safe_name}.lock"
    return agent_home / "db" / "locks" / safe_name


@contextmanager
def file_lock(path: Path, *, timeout_seconds: float = 15.0, poll_seconds: float = 0.05, stale_seconds: float = 300.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    descriptor: int | None = None
    while True:
        try:
            descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            payload = json.dumps({"pid": os.getpid(), "created_at": timestamp_now()}, ensure_ascii=False)
            os.write(descriptor, payload.encode("utf-8"))
            break
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
                if stale_seconds > 0 and age > stale_seconds:
                    path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() - started >= timeout_seconds:
                raise TimeoutError(f"Timed out waiting for lock {path}")
            time.sleep(poll_seconds)
    try:
        yield path
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def load_json(path: Path) -> dict | list:
    last_error = None
    for attempt in range(12):
        try:
            return repair_data(json.loads(path.read_text(encoding="utf-8")))
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.03 * (attempt + 1))
    raise last_error or PermissionError(f"Failed to read {path}")


def quote_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "raw" / "quotes" / f"{report_date}.json"


def news_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "raw" / "news" / f"{report_date}.json"


def fund_profile_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "raw" / "fund_profiles" / f"{report_date}.json"


def score_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "daily_scores" / f"{report_date}.json"


def intraday_proxy_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "intraday_proxies" / f"{report_date}.json"


def realtime_monitor_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "realtime_monitor" / f"{report_date}.json"


def llm_context_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "llm_context" / f"{report_date}.json"


def llm_advice_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "llm_advice" / f"{report_date}.json"


def committee_advice_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "committee_advice" / f"{report_date}.json"


def committee_decision_bundle_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "committee_decision_bundle" / f"{report_date}.json"


def llm_raw_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "llm_raw" / f"{report_date}.json"


def validated_advice_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "validated_advice" / f"{report_date}.json"


def decisions_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "decisions" / f"{report_date}.json"


def decision_ledger_path(agent_home: Path, fund_code: str) -> Path:
    safe = str(fund_code or "unknown").replace("/", "_").replace("\\", "_").replace(":", "_")
    return agent_home / "db" / "decision_ledger" / f"{safe}.jsonl"


def decision_latest_path(agent_home: Path, fund_code: str) -> Path:
    safe = str(fund_code or "unknown").replace("/", "_").replace("\\", "_").replace(":", "_")
    return agent_home / "db" / "decision_latest" / f"{safe}.json"


def agent_output_dir(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "agent_outputs" / report_date


def agent_snapshot_root(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "agent_snapshots" / report_date


def review_result_path(agent_home: Path, base_date: str, horizon: int) -> Path:
    return agent_home / "db" / "review_results" / f"{base_date}_T{horizon}.json"


def execution_review_result_path(agent_home: Path, base_date: str, horizon: int) -> Path:
    return agent_home / "db" / "execution_reviews" / f"{base_date}_execution_T{horizon}.json"


def portfolio_valuation_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "portfolio_valuation" / f"{report_date}.json"


def portfolio_daily_pnl_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "portfolio_daily_pnl" / f"{report_date}.json"


def portfolio_definition_path(agent_home: Path) -> Path:
    return agent_home / "config" / "portfolio_definition.json"


def legacy_portfolio_path(agent_home: Path) -> Path:
    return agent_home / "config" / "portfolio.json"


def portfolio_state_current_path(agent_home: Path) -> Path:
    return agent_home / "db" / "portfolio_state" / "current.json"


def has_portfolio_source(agent_home: Path) -> bool:
    return portfolio_state_current_path(agent_home).exists() or legacy_portfolio_path(agent_home).exists()


def portfolio_state_snapshot_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "portfolio_state" / "snapshots" / f"{report_date}.json"


def portfolio_state_event_dir(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "portfolio_state" / "events" / report_date


def portfolio_import_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "portfolio_imports"


def execution_status_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "execution_status" / f"{report_date}.json"


def preflight_result_path(agent_home: Path) -> Path:
    return agent_home / "db" / "preflight" / "latest.json"


def run_manifest_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "run_manifests"


def legacy_review_memory_path(agent_home: Path) -> Path:
    return agent_home / "db" / "review_memory" / "memory.json"


def legacy_review_memory_ledger_path(agent_home: Path) -> Path:
    return agent_home / "db" / "review_memory" / "ledger.json"


def long_memory_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "long_memory"


def long_memory_db_path(agent_home: Path) -> Path:
    return long_memory_dir(agent_home) / "memory.sqlite"


def long_memory_index_path(agent_home: Path) -> Path:
    return long_memory_dir(agent_home) / "index.sqlite"


def long_memory_cycle_dir(agent_home: Path, status: str = "completed") -> Path:
    normalized = status if status in {"pending", "completed", "failed"} else "completed"
    return long_memory_dir(agent_home) / "cycles" / normalized


def long_memory_cycle_path(agent_home: Path, report_date: str, status: str = "completed") -> Path:
    return long_memory_cycle_dir(agent_home, status) / f"{report_date}.json"


def long_memory_export_path(agent_home: Path) -> Path:
    return long_memory_dir(agent_home) / "exports" / "all_memory.json"


def long_memory_pending_export_path(agent_home: Path) -> Path:
    return long_memory_dir(agent_home) / "candidates" / "pending_permanent.json"


def long_memory_learning_ledger_path(agent_home: Path) -> Path:
    return long_memory_dir(agent_home) / "portfolio" / "learning_ledger.json"


def long_memory_learning_cycle_path(agent_home: Path, review_date: str) -> Path:
    return long_memory_dir(agent_home) / "cycles" / "completed" / f"{review_date}.learning.json"


def long_memory_compat_view_path(agent_home: Path) -> Path:
    return long_memory_dir(agent_home) / "exports" / "compat_review_memory.json"


def daily_workspace_dir(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "daily_workspace" / report_date


def today_analysis_runtime_path(agent_home: Path, report_date: str) -> Path:
    return daily_workspace_dir(agent_home, report_date) / "today_analysis_runtime.json"


def long_memory_runtime_path(agent_home: Path, report_date: str) -> Path:
    return daily_workspace_dir(agent_home, report_date) / "long_memory_runtime.json"


def process_exists(pid: object) -> bool:
    try:
        resolved = int(pid)
    except Exception:
        return False
    if resolved <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            process_query_limited_information = 0x1000
            still_active = 259
            handle = kernel32.OpenProcess(process_query_limited_information, False, resolved)
            if not handle:
                return False
            try:
                exit_code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == still_active
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(resolved, 0)
    except OSError:
        return False
    return True


def is_runtime_stale(runtime: dict, *, now: datetime | None = None, stale_seconds: int = TODAY_ANALYSIS_STALE_SECONDS) -> bool:
    if str(runtime.get("status", "") or "").lower() != "running":
        return False
    if process_exists(runtime.get("pid")):
        return False
    heartbeat_text = str(runtime.get("heartbeatAt", "") or runtime.get("startedAt", "") or "").strip()
    if not heartbeat_text:
        return True
    try:
        heartbeat = datetime.fromisoformat(heartbeat_text)
    except ValueError:
        return True
    current = now or shanghai_now()
    return max(0.0, (current - heartbeat).total_seconds()) >= stale_seconds


def refresh_runtime_heartbeat(runtime: dict, *, now_text: str | None = None) -> dict:
    heartbeat_text = now_text or timestamp_now()
    runtime["heartbeatAt"] = heartbeat_text
    if not runtime.get("startedAt"):
        runtime["startedAt"] = heartbeat_text
    return runtime


def legacy_trade_journal_path(agent_home: Path, trade_date: str) -> Path:
    return agent_home / "db" / "trade_journal" / f"{trade_date}.json"


def actual_trade_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "execution_sync" / "actual_trades"


def actual_trade_path(agent_home: Path, trade_date: str) -> Path:
    return actual_trade_dir(agent_home) / f"{trade_date}.json"


def settlement_event_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "execution_sync" / "settlement_events"


def settlement_event_path(agent_home: Path, idempotency_key: str) -> Path:
    safe = str(idempotency_key or "unknown").replace("/", "_").replace("\\", "_").replace(":", "_")
    return settlement_event_dir(agent_home) / f"{safe}.json"


def load_actual_trade_payload(agent_home: Path, trade_date: str) -> dict:
    path = actual_trade_path(agent_home, trade_date)
    if not path.exists():
        return {"trade_date": trade_date, "items": []}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {"trade_date": trade_date, "items": []}


def iter_actual_trade_items(agent_home: Path, target_date: str | None = None) -> list[dict]:
    base = actual_trade_dir(agent_home)
    target = parse_date_text(target_date) if target_date else None
    items: list[dict] = []
    if base.exists():
        for path in sorted(base.glob("*.json")):
            trade_date = parse_date_text(path.stem[:10])
            if target is not None and trade_date is not None and trade_date > target:
                continue
            payload = load_json(path)
            if not isinstance(payload, dict):
                continue
            effective_date = str(payload.get("trade_date", "") or path.stem[:10])
            for item in payload.get("items", []) or []:
                items.append({"trade_date": effective_date, **item})
    legacy_dir = legacy_trade_journal_path(agent_home, "1970-01-01").parent
    if legacy_dir.exists():
        seen_legacy_ids = {str(item.get("trade_id", item.get("conversion_id", "")) or "") for item in items}
        for path in sorted(legacy_dir.glob("*.json")):
            trade_date = parse_date_text(path.stem[:10])
            if target is not None and trade_date is not None and trade_date > target:
                continue
            payload = load_json(path)
            if not isinstance(payload, dict):
                continue
            effective_date = str(payload.get("trade_date", "") or path.stem[:10])
            for index, item in enumerate(payload.get("items", []) or [], start=1):
                trade_id = str(item.get("trade_id", "") or f"legacy:{effective_date}:{index}:{item.get('fund_code', '')}:{item.get('action', '')}")
                if trade_id in seen_legacy_ids:
                    continue
                mapped_operation = {
                    "buy": "buy",
                    "sell": "sell",
                    "switch_in": "convert_in",
                    "switch_out": "convert_out",
                }.get(str(item.get("action", "") or ""), str(item.get("action", "") or ""))
                items.append(
                    {
                        "trade_date": effective_date,
                        "trade_id": trade_id,
                        "operation_type": mapped_operation,
                        "fund_code": item.get("fund_code", ""),
                        "fund_name": item.get("fund_name", ""),
                        "amount": item.get("amount", 0.0),
                        "units": item.get("units"),
                        "nav": item.get("trade_nav"),
                        "linked_suggestion_id": item.get("suggestion_id", ""),
                        "linked_advice_date": item.get("suggestion_date", effective_date),
                        "user_note": item.get("note", ""),
                        "source": item.get("source", "legacy_trade_journal"),
                    }
                )
    items.sort(key=lambda item: (str(item.get("trade_date", "")), str(item.get("trade_id", item.get("conversion_id", "")))))
    return items


def legacy_root(agent_home: Path) -> Path:
    return agent_home / "db" / "legacy"


def legacy_review_memory_dir(agent_home: Path) -> Path:
    return legacy_root(agent_home) / "review_memory"


def legacy_trade_journal_dir(agent_home: Path) -> Path:
    return legacy_root(agent_home) / "trade_journal"


def estimated_nav_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "estimated_nav" / f"{report_date}.json"


def fund_nav_history_path(agent_home: Path, fund_code: str) -> Path:
    return agent_home / "db" / "fund_nav_history" / f"{fund_code}.json"


def benchmark_history_path(agent_home: Path, benchmark_key: str) -> Path:
    safe = benchmark_key.replace("/", "_").replace("\\", "_").replace(":", "_")
    return agent_home / "db" / "benchmark_history" / f"{safe}.json"


def proxy_history_path(agent_home: Path, proxy_key: str) -> Path:
    safe = proxy_key.replace("/", "_").replace("\\", "_").replace(":", "_")
    return agent_home / "db" / "proxy_history" / f"{safe}.json"


def report_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "reports" / "daily" / f"{report_date}.md"


def portfolio_report_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "reports" / "daily" / f"{report_date}_portfolio.md"


def nightly_review_report_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "reports" / "daily" / f"{report_date}_review.md"


def learning_report_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "reports" / "daily" / f"{report_date}_learning.md"


def load_benchmark_mappings(agent_home: Path) -> dict:
    path = agent_home / "config" / "benchmark_mappings.json"
    if not path.exists():
        return {"fund_benchmarks": {}}
    return repair_data(json.loads(path.read_text(encoding="utf-8")))


def source_health_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "source_health" / f"{report_date}.json"


def news_query_plan_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "news_query_plans" / f"{report_date}.json"


def evidence_index_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "evidence_index" / f"{report_date}.json"


def recommendation_delta_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "recommendation_delta" / f"{report_date}.json"


def evaluation_snapshot_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "evaluation_snapshots" / f"{report_date}.json"


def replay_experiment_dir(agent_home: Path, experiment_id: str) -> Path:
    return agent_home / "db" / "replay_experiments" / experiment_id


def _empty_review_memory() -> dict:
    return {
        "updated_at": "",
        "lessons": [],
        "review_history": [],
        "bias_adjustments": [],
        "agent_feedback": [],
        "records": [],
        "strategic_memory": [],
        "permanent_memory": [],
        "core_permanent_memory": [],
        "user_confirmed_memory": [],
        "memory_ledger_summary": {},
    }


def _review_memory_from_long_memory(agent_home: Path) -> dict | None:
    export_path = long_memory_export_path(agent_home)
    if not export_path.exists():
        return None
    payload = load_json(export_path)
    if not isinstance(payload, dict):
        return None
    items = list(payload.get("items", []) or [])
    if not items:
        return None
    strategic_memory = [item for item in items if item.get("status") == "strategic"]
    permanent_memory = [item for item in items if item.get("status") == "permanent" and item.get("priority") != "core"]
    core_memory = [item for item in items if item.get("status") == "permanent" and item.get("priority") == "core"]
    lessons = []
    bias_adjustments = []
    agent_feedback = []
    for item in items:
        if item.get("horizon_bucket") in {"5d", "10d", "30d", "90d"}:
            lessons.append(
                {
                    "base_date": str(item.get("valid_from", "") or item.get("updated_at", ""))[:10],
                    "horizon": item.get("horizon_bucket", "long_term"),
                    "source": item.get("source", "long_memory"),
                    "type": item.get("memory_type", "semantic"),
                    "text": item.get("text", ""),
                    "confidence": item.get("confidence", 0.0),
                    "applies_to": item.get("entity_key", ""),
                }
            )
        if item.get("domain") in {"market", "portfolio"} and item.get("horizon_bucket") in {"5d", "10d", "30d", "90d"}:
            bias_adjustments.append(
                {
                    "base_date": str(item.get("valid_from", "") or item.get("updated_at", ""))[:10],
                    "scope": item.get("horizon_bucket", "long_term"),
                    "target": item.get("entity_key", ""),
                    "adjustment": item.get("title", ""),
                    "reason": item.get("text", ""),
                    "expires_on": item.get("valid_until", ""),
                }
            )
        if item.get("source_agent"):
            agent_feedback.append(
                {
                    "base_date": str(item.get("valid_from", "") or item.get("updated_at", ""))[:10],
                    "agent_name": item.get("source_agent", ""),
                    "bias": item.get("title", ""),
                    "reason": item.get("text", ""),
                }
            )
    review_history = []
    completed_dir = long_memory_cycle_dir(agent_home, "completed")
    if completed_dir.exists():
        for path in sorted(completed_dir.glob("*.json"), reverse=True)[:20]:
            cycle = load_json(path)
            if not isinstance(cycle, dict):
                continue
            review_history.append(
                {
                    "base_date": cycle.get("report_date", path.stem[:10]),
                    "horizon": 0,
                    "source": "long_memory_cycle",
                    "summary": {
                        "written_count": cycle.get("written_count", 0),
                        "status": cycle.get("status", ""),
                    },
                    "diagnostic_summary": {},
                    "memory_summary": (cycle.get("manager_output", {}) or {}).get("summary", ""),
                    "watchouts": [],
                }
            )
    ledger_summary = {
        "candidate": len([item for item in items if item.get("status") == "candidate"]),
        "strategic": len(strategic_memory),
        "permanent": len(permanent_memory),
        "core_permanent": len(core_memory),
    }
    return {
        "updated_at": str(payload.get("updated_at", "") or ""),
        "lessons": lessons[-80:],
        "review_history": review_history[:20],
        "bias_adjustments": bias_adjustments[-40:],
        "agent_feedback": agent_feedback[-40:],
        "records": items,
        "strategic_memory": strategic_memory,
        "permanent_memory": permanent_memory,
        "core_permanent_memory": core_memory,
        "user_confirmed_memory": permanent_memory + core_memory,
        "memory_ledger_summary": ledger_summary,
    }
