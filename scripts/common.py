from __future__ import annotations

import json
import os
import time
import uuid
from datetime import date, datetime
from pathlib import Path
import tomllib

DEFAULT_AGENT_HOME = Path(r"F:\okra_assistant")
REQUIRED_DIRS = (
    "config",
    "raw/quotes",
    "raw/news",
    "raw/fund_profiles",
    "db/daily_scores",
    "db/intraday_proxies",
    "db/realtime_monitor",
    "db/portfolio_advice",
    "db/llm_context",
    "db/llm_advice",
    "db/llm_raw",
    "db/validated_advice",
    "db/agent_outputs",
    "db/agent_snapshots",
    "db/portfolio_valuation",
    "db/portfolio_state",
    "db/portfolio_state/snapshots",
    "db/preflight",
    "db/run_manifests",
    "db/review_results",
    "db/execution_reviews",
    "db/execution_status",
    "db/review_memory",
    "db/trade_journal",
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

MOJIBAKE_HINTS = set("鍩閲鏃鏀璇鎴鏅鐜缁閫鍔鐩浠鍗鍙璁鏍妗")
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
    legacy_path = agent_home / "config" / "portfolio.json"
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
            }
            config_fields = {
                key: value
                for key, value in fund.items()
                if key not in opening_state and key not in {"current_value", "holding_pnl", "holding_return_pct", "holding_units", "cost_basis_value", "last_valuation_nav", "last_valuation_date", "last_official_nav", "last_official_nav_date", "units_source"}
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


def load_review_memory(agent_home: Path) -> dict:
    path = review_memory_path(agent_home)
    if not path.exists():
        return {"updated_at": "", "lessons": [], "review_history": []}
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


def load_json(path: Path) -> dict | list:
    return repair_data(json.loads(path.read_text(encoding="utf-8")))


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


def portfolio_advice_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "portfolio_advice" / f"{report_date}.json"


def llm_context_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "llm_context" / f"{report_date}.json"


def llm_advice_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "llm_advice" / f"{report_date}.json"


def llm_raw_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "llm_raw" / f"{report_date}.json"


def validated_advice_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "validated_advice" / f"{report_date}.json"


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


def portfolio_definition_path(agent_home: Path) -> Path:
    return agent_home / "config" / "portfolio_definition.json"


def portfolio_state_current_path(agent_home: Path) -> Path:
    return agent_home / "db" / "portfolio_state" / "current.json"


def portfolio_state_snapshot_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "portfolio_state" / "snapshots" / f"{report_date}.json"


def execution_status_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "execution_status" / f"{report_date}.json"


def preflight_result_path(agent_home: Path) -> Path:
    return agent_home / "db" / "preflight" / "latest.json"


def run_manifest_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "run_manifests"


def review_memory_path(agent_home: Path) -> Path:
    return agent_home / "db" / "review_memory" / "memory.json"


def trade_journal_path(agent_home: Path, trade_date: str) -> Path:
    return agent_home / "db" / "trade_journal" / f"{trade_date}.json"


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


def load_benchmark_mappings(agent_home: Path) -> dict:
    path = agent_home / "config" / "benchmark_mappings.json"
    if not path.exists():
        return {"fund_benchmarks": {}}
    return repair_data(json.loads(path.read_text(encoding="utf-8")))
