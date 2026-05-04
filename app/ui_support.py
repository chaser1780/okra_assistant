from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


MOJIBAKE = set("鍩閱鏃鏀璇鎴鏅鐜缁閫鍔鐩浠鍗鍙璁鏍妗")
COMMON = set("基金收益建议组合持仓实时详情智能体复盘夜间设置数据金额买卖现金回写估值策略研究市场风格主题新闻置信度风险")


def text_score(text: str) -> int:
    readable = sum(ch.isascii() or "\u4e00" <= ch <= "\u9fff" or ch in "，。；：！？（）《》【】、“”‘’—·+-/% " for ch in text)
    return readable + 2 * sum(ch in COMMON for ch in text) - 2 * sum(ch in MOJIBAKE for ch in text)


def fix_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    text = text.replace("\ufeff", "")
    for _ in range(2):
        try:
            candidate = text.encode("gb18030").decode("utf-8")
        except UnicodeError:
            break
        if candidate == text or text_score(candidate) < text_score(text):
            break
        text = candidate
    return text


def fix_value(value):
    if isinstance(value, str):
        return fix_text(value)
    if isinstance(value, list):
        return [fix_value(x) for x in value]
    if isinstance(value, dict):
        return {fix_value(k) if isinstance(k, str) else k: fix_value(v) for k, v in value.items()}
    return value


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return fix_value(json.loads(path.read_text(encoding="utf-8", errors="replace")))
    except Exception:
        return default


def read_text(path: Path) -> str:
    return fix_text(path.read_text(encoding="utf-8", errors="replace")) if path.exists() else ""


def read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    import tomllib

    return fix_value(tomllib.loads(path.read_text(encoding="utf-8")))


def normalize_failed_agents(items) -> list[dict]:
    normalized: list[dict] = []
    for item in items or []:
        if isinstance(item, dict):
            normalized.append(
                {
                    "agent_name": fix_text(str(item.get("agent_name", "")).strip()),
                    "error": fix_text(str(item.get("error", "")).strip()),
                }
            )
        elif item:
            normalized.append({"agent_name": fix_text(str(item).strip()), "error": ""})
    return [item for item in normalized if item.get("agent_name") or item.get("error")]


def apply_execution_status(validated: dict, execution_status: dict) -> dict:
    payload = fix_value(json.loads(json.dumps(validated, ensure_ascii=False))) if validated else {}
    status_by_id = {
        item.get("suggestion_id"): item
        for item in (execution_status.get("items", []) or [])
        if item.get("suggestion_id")
    }
    for section in ("tactical_actions", "dca_actions", "hold_actions"):
        updated_items = []
        for item in payload.get(section, []) or []:
            match = status_by_id.get(item.get("suggestion_id"))
            enriched = dict(item)
            if match:
                executed_amount = float(match.get("trade_amount", item.get("executed_amount", 0.0)) or 0.0)
                validated_amount = float(item.get("validated_amount", 0.0) or 0.0)
                if validated_amount > 0 and 0 < executed_amount < validated_amount:
                    status = "partial"
                elif validated_amount > 0 and executed_amount >= validated_amount:
                    status = "executed"
                else:
                    status = match.get("status", item.get("execution_status", "pending"))
                enriched["execution_status"] = status
                enriched["executed_amount"] = executed_amount
                enriched["linked_trade_date"] = match.get("linked_trade_date", "")
                enriched["trade_action"] = match.get("trade_action", "")
            updated_items.append(enriched)
        payload[section] = updated_items
    return payload


def latest_manifest(home: Path, pipeline_name: str, report_date: str, mode: str | None = None) -> dict:
    run_dir = home / "db" / "run_manifests" / report_date
    if not run_dir.exists():
        return {}
    candidates: list[tuple[float, dict]] = []
    for path in run_dir.glob(f"{pipeline_name}_*.json"):
        payload = read_json(path, {})
        if mode and payload.get("mode") != mode:
            continue
        candidates.append((path.stat().st_mtime, {**payload, "_manifest_path": str(path)}))
    if not candidates:
        return {}
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def latest_available_dated_payload(home: Path, relative_dir: str, report_date: str, default):
    primary = home / relative_dir / f"{report_date}.json"
    if primary.exists():
        return report_date, read_json(primary, default)
    base_dir = home / relative_dir
    if not base_dir.exists():
        return report_date, default
    candidates = sorted(
        [
            path
            for path in base_dir.glob("*.json")
            if len(path.stem) >= 10 and path.stem[:10].count("-") == 2
        ],
        key=lambda item: item.stem,
        reverse=True,
    )
    for path in candidates:
        payload = read_json(path, default)
        if payload:
            return path.stem[:10], payload
    return report_date, default


def latest_available_payload_on_or_before(home: Path, relative_dir: str, report_date: str, default):
    primary = home / relative_dir / f"{report_date}.json"
    if primary.exists():
        return report_date, read_json(primary, default)
    base_dir = home / relative_dir
    if not base_dir.exists():
        return report_date, default
    candidates = sorted(
        [
            path
            for path in base_dir.glob("*.json")
            if len(path.stem) >= 10 and path.stem[:10].count("-") == 2 and path.stem[:10] <= report_date
        ],
        key=lambda item: item.stem,
        reverse=True,
    )
    for path in candidates:
        payload = read_json(path, default)
        if payload:
            return path.stem[:10], payload
    return report_date, default


def load_portfolio_for_date(home: Path, report_date: str, today: str) -> tuple[str, dict]:
    if report_date == today:
        current = read_json(home / "db" / "portfolio_state" / "current.json", read_json(home / "config" / "portfolio.json", {}))
        if current:
            payload = dict(current)
            payload["_source_kind"] = "current"
            payload["_source_date"] = fix_text(str(payload.get("as_of_date", "") or today))
            return payload["_source_date"], payload

    snapshot_date, snapshot = latest_available_payload_on_or_before(home, "db/portfolio_state/snapshots", report_date, {})
    if snapshot:
        payload = dict(snapshot)
        payload["_source_kind"] = "snapshot"
        payload["_source_date"] = snapshot_date
        return snapshot_date, payload

    current = read_json(home / "db" / "portfolio_state" / "current.json", read_json(home / "config" / "portfolio.json", {}))
    if current:
        payload = dict(current)
        payload["_source_kind"] = "current"
        payload["_source_date"] = fix_text(str(payload.get("as_of_date", "") or today))
        return payload["_source_date"], payload

    return report_date, {}


def collect_dates(home: Path) -> list[str]:
    values = set()
    for pattern in ("db/validated_advice/*.json", "db/realtime_monitor/*.json", "db/trade_journal/*.json", "db/review_results/*.json", "db/review_memory/cycles/*.json"):
        for item in home.glob(pattern):
            stem = item.stem
            if len(stem) >= 10 and stem[:10].count("-") == 2:
                values.add(stem[:10])
    return sorted(values, reverse=True)


def load_review_results_for_date(home: Path, review_date: str) -> list[dict]:
    values = []
    for review_dir in (home / "db" / "review_results", home / "db" / "execution_reviews"):
        if not review_dir.exists():
            continue
        for path in sorted(review_dir.glob("*.json")):
            payload = read_json(path, {})
            if payload.get("review_date") == review_date:
                values.append(payload)
    values.sort(key=lambda item: (item.get("source", "advice"), int(item.get("horizon", 0)), item.get("base_date", "")))
    return values


def collect_replay_experiment_summaries(home: Path, limit: int = 8) -> list[dict]:
    base = home / "db" / "replay_experiments"
    if not base.exists():
        return []
    items: list[dict] = []
    for path in sorted(base.glob("*/summary.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        payload = read_json(path, {})
        if not payload:
            continue
        differences = []
        for daily in payload.get("daily_results", []) or []:
            for item in ((daily.get("counterfactual", {}) or {}).get("item_deltas", []) or []):
                if not item.get("changed"):
                    continue
                differences.append(
                    {
                        "report_date": daily.get("report_date", ""),
                        "fund_code": item.get("fund_code", ""),
                        "existing_action": item.get("existing_action", ""),
                        "replay_action": item.get("replay_action", ""),
                        "existing_edge": item.get("existing_edge", 0.0),
                        "replay_edge": item.get("replay_edge", 0.0),
                        "edge_delta": item.get("edge_delta", 0.0),
                        "diagnostic_label": item.get("diagnostic_label", ""),
                        "existing_outcome": item.get("existing_outcome", ""),
                        "replay_outcome": item.get("replay_outcome", ""),
                    }
                )
        differences.sort(key=lambda item: (-abs(float(item.get("edge_delta", 0.0) or 0.0)), item.get("report_date", ""), item.get("fund_code", "")))
        learning_impacts = list(payload.get("learning_impacts", []) or [])
        items.append(
            {
                "experiment_id": payload.get("experiment_id", path.parent.name),
                "mode": payload.get("mode", ""),
                "generated_at": payload.get("generated_at", ""),
                "summary_path": str(path),
                "start_date": payload.get("start_date", ""),
                "end_date": payload.get("end_date", ""),
                "changed_days": (payload.get("aggregate", {}) or {}).get("changed_days", 0),
                "total_tactical_actions": (payload.get("aggregate", {}) or {}).get("total_tactical_actions", 0),
                "total_gross_trade": (payload.get("aggregate", {}) or {}).get("total_gross_trade", 0.0),
                "applied_to_learning": bool((payload.get("learning_update", {}) or {}).get("applied", False)),
                "edge_delta_total": (payload.get("aggregate", {}) or {}).get("edge_delta_total", 0.0),
                "improved_items": (payload.get("aggregate", {}) or {}).get("improved_items", 0),
                "worsened_items": (payload.get("aggregate", {}) or {}).get("worsened_items", 0),
                "learning_impacts": learning_impacts[:12],
                "top_differences": differences[:20],
                "difference_count": len(differences),
            }
        )
        if len(items) >= limit:
            break
    return items


def historical_operating_metrics(home: Path, lookback_days: int = 90) -> dict:
    dates = collect_dates(home)[:lookback_days]
    if not dates:
        return {"sample_days": 0, "fallback_days": 0, "stale_days": 0}
    fallback_days = 0
    stale_days = 0
    for report_date in dates:
        llm_raw = read_json(home / "db" / "llm_raw" / f"{report_date}.json", {})
        if llm_raw.get("mode") == "committee_fallback":
            fallback_days += 1
        realtime = read_json(home / "db" / "realtime_monitor" / f"{report_date}.json", {})
        if any(item.get("stale") for item in realtime.get("items", []) or []):
            stale_days += 1
    return {
        "sample_days": len(dates),
        "fallback_days": fallback_days,
        "stale_days": stale_days,
    }


def today_str() -> str:
    return date.today().isoformat()


def load_state(home: Path, selected: str | None = None) -> dict:
    dates = collect_dates(home)
    today = today_str()
    dates = sorted(set(dates + [today]), reverse=True)
    selected = selected or today
    if selected not in dates:
        dates = sorted(set(dates + [selected]), reverse=True)
    portfolio_date, portfolio = load_portfolio_for_date(home, selected, today)
    execution_status = read_json(home / "db" / "execution_status" / f"{selected}.json", {"items": []})
    validated = apply_execution_status(read_json(home / "db" / "validated_advice" / f"{selected}.json", {}), execution_status)
    realtime_date, realtime_payload = latest_available_payload_on_or_before(home, "db/realtime_monitor", selected, {})
    live_realtime_date, live_realtime_payload = latest_available_dated_payload(home, "db/realtime_monitor", today, {})
    selected_intraday_manifest = latest_manifest(home, "daily_pipeline", selected, mode="intraday")
    selected_nightly_manifest = latest_manifest(home, "daily_pipeline", selected, mode="nightly")
    selected_realtime_manifest = latest_manifest(home, "realtime_monitor", selected, mode="realtime")
    return {
        "selected_date": selected,
        "dates": dates,
        "project": read_toml(home / "project.toml"),
        "strategy": read_toml(home / "config" / "strategy.toml"),
        "watchlist": read_json(home / "config" / "watchlist.json", {"funds": []}),
        "portfolio": portfolio,
        "portfolio_date": portfolio_date,
        "llm_context": read_json(home / "db" / "llm_context" / f"{selected}.json", {}),
        "committee_advice": read_json(home / "db" / "committee_advice" / f"{selected}.json", {}),
        "validated": validated,
        "realtime": realtime_payload,
        "realtime_date": realtime_date,
        "live_realtime": live_realtime_payload,
        "live_realtime_date": live_realtime_date,
        "aggregate": read_json(home / "db" / "agent_outputs" / selected / "aggregate.json", {}),
        "llm_raw": read_json(home / "db" / "llm_raw" / f"{selected}.json", {}),
        "review_result": read_json(home / "db" / "review_results" / f"{selected}_T0.json", {}),
        "review_results_for_date": load_review_results_for_date(home, selected),
        "review_memory": read_json(home / "db" / "review_memory" / "memory.json", {}),
        "memory_ledger": read_json(home / "db" / "review_memory" / "ledger.json", {"rules": [], "events": [], "summary": {}}),
        "learning_cycle": read_json(home / "db" / "review_memory" / "cycles" / f"{selected}.json", {}),
        "review_report": read_text(home / "reports" / "daily" / f"{selected}_review.md"),
        "learning_report": read_text(home / "reports" / "daily" / f"{selected}_learning.md"),
        "portfolio_report": read_text(home / "reports" / "daily" / f"{selected}_portfolio.md"),
        "recommendation_delta": read_json(home / "db" / "recommendation_delta" / f"{selected}.json", {"items": []}),
        "source_health": read_json(home / "db" / "source_health" / f"{selected}.json", {"items": []}),
        "evaluation_snapshot": read_json(home / "db" / "evaluation_snapshots" / f"{selected}.json", {}),
        "trade_journal": read_json(home / "db" / "trade_journal" / f"{selected}.json", {"items": []}),
        "replay_experiments": collect_replay_experiment_summaries(home),
        "execution_status": execution_status,
        "llm_config": read_toml(home / "config" / "llm.toml"),
        "preflight": read_json(home / "db" / "preflight" / "latest.json", {}),
        "intraday_manifest": selected_intraday_manifest,
        "nightly_manifest": selected_nightly_manifest,
        "realtime_manifest": selected_realtime_manifest,
        "today_intraday_manifest": latest_manifest(home, "daily_pipeline", today, mode="intraday"),
        "today_nightly_manifest": latest_manifest(home, "daily_pipeline", today, mode="nightly"),
        "today_realtime_manifest": latest_manifest(home, "realtime_monitor", today, mode="realtime"),
    }


def summarize_state(state: dict) -> dict:
    validated, aggregate = state["validated"], state["aggregate"]
    failed_agents = normalize_failed_agents(aggregate.get("failed_agents", []) or [])
    llm_raw = state.get("llm_raw", {})
    advice_mode = llm_raw.get("mode", "")
    return {
        "selected_date": state["selected_date"],
        "portfolio_name": state["portfolio"].get("portfolio_name", ""),
        "portfolio_date": state.get("portfolio_date", ""),
        "market_regime": validated.get("market_view", {}).get("regime", ""),
        "all_agents_ok": bool(aggregate.get("all_agents_ok", False)),
        "failed_agents": failed_agents,
        "failed_agent_names": [item.get("agent_name", "") for item in failed_agents if item.get("agent_name")],
        "transport_name": llm_raw.get("transport_name", ""),
        "advice_mode": advice_mode,
        "decision_source": llm_raw.get("decision_source", ""),
        "narrative_mode": llm_raw.get("narrative_mode", ""),
        "advice_is_fallback": advice_mode == "committee_fallback",
        "advice_is_mock": advice_mode == "mock",
        "aggregate_degraded_ok": bool(aggregate.get("degraded_ok", False)),
        "preflight_status": state.get("preflight", {}).get("status", ""),
        "review_available": bool(state.get("review_results_for_date") or state.get("review_report")),
        "learning_cycle_available": bool(state.get("learning_cycle") or state.get("learning_report")),
        "recommendation_delta": state.get("recommendation_delta", {}),
        "source_health": state.get("source_health", {}),
        "evaluation_snapshot": state.get("evaluation_snapshot", {}),
    }


def previous_date(dates: list[str], selected_date: str) -> str | None:
    later = sorted(set(dates), reverse=True)
    if selected_date not in later:
        return later[0] if later else None
    index = later.index(selected_date)
    if index + 1 < len(later):
        return later[index + 1]
    return None


def load_validated_for_date(home: Path, report_date: str | None) -> dict:
    if not report_date:
        return {}
    return read_json(home / "db" / "validated_advice" / f"{report_date}.json", {})


def build_action_change_lines(current_validated: dict, previous_validated: dict, previous_date_text: str | None) -> list[str]:
    if not previous_validated:
        return ["- 暂无上一期建议可比较。"]

    def index_actions(payload: dict) -> dict[str, dict]:
        return {
            item.get("fund_code"): item
            for section in ("tactical_actions", "dca_actions", "hold_actions")
            for item in payload.get(section, []) or []
            if item.get("fund_code")
        }

    current_map = index_actions(current_validated)
    previous_map = index_actions(previous_validated)
    lines: list[str] = []
    for fund_code in sorted(set(current_map) | set(previous_map)):
        current = current_map.get(fund_code)
        previous = previous_map.get(fund_code)
        if current and not previous:
            lines.append(f"- {current.get('fund_name')}：本期新增 `{current.get('validated_action')}` {money(current.get('validated_amount', 0))}")
            continue
        if previous and not current:
            lines.append(f"- {previous.get('fund_name')}：相比 {previous_date_text} 已不在本期建议中")
            continue
        if not current or not previous:
            continue
        if current.get("validated_action") != previous.get("validated_action") or float(current.get("validated_amount", 0)) != float(previous.get("validated_amount", 0)):
            lines.append(
                f"- {current.get('fund_name')}：{previous.get('validated_action')} {money(previous.get('validated_amount', 0))}"
                f" → {current.get('validated_action')} {money(current.get('validated_amount', 0))}"
            )
    return lines or [f"- 相比 {previous_date_text}，动作结构没有明显变化。"]


def build_dashboard_alerts(state: dict) -> list[str]:
    alerts: list[str] = []
    selected_date = state.get("selected_date", today_str())
    today = today_str()
    if selected_date == today and not state.get("validated"):
        alerts.append("今日日内建议尚未生成。")
    failed_agents = normalize_failed_agents(state.get("aggregate", {}).get("failed_agents", []))
    if failed_agents:
        names = ", ".join(item.get("agent_name", "") for item in failed_agents if item.get("agent_name"))
        alerts.append(f"存在失败智能体：{names}。")
        if state.get("aggregate", {}).get("degraded_ok"):
            alerts.append("本次研究在非核心智能体失败后以降级模式继续生成结果。")
    preflight = state.get("preflight", {}) or {}
    if preflight.get("status") == "failed":
        alerts.append("最近一次 preflight 检查失败，请先查看 Settings 页的健康检查结果。")
    elif preflight.get("status") == "warning":
        alerts.append("最近一次 preflight 检查存在警告，建议先查看 Settings 页。")
    realtime = state.get("realtime") or {}
    if realtime:
        stale_count = sum(1 for item in realtime.get("items", []) if item.get("stale"))
        if stale_count > 0:
            alerts.append(f"实时收益中有 {stale_count} 只基金估值跨日或陈旧。")
    llm_raw = state.get("llm_raw", {}) or {}
    if llm_raw.get("mode") == "committee_fallback":
        alerts.append("本次最终建议由 committee fallback 合成，不是最终汇总模型的完整直出。")
    valuation = read_json(state.get("home") / "db" / "portfolio_valuation" / f"{selected_date}.json", {}) if state.get("home") else {}
    delayed_codes = valuation.get("stale_fund_codes", []) if valuation else []
    if delayed_codes:
        alerts.append(f"官方净值仍有滞后基金：{', '.join(delayed_codes[:5])}{'...' if len(delayed_codes) > 5 else ''}")
    intraday_manifest = state.get("intraday_manifest", {}) or {}
    if selected_date == today and intraday_manifest.get("status") == "failed":
        latest_error = (intraday_manifest.get("errors") or [{}])[-1].get("error", "未知错误")
        alerts.append(f"最近一次日内链路失败：{fix_text(str(latest_error))[:120]}")
    return alerts


def build_plain_language_summary(summary: dict, validated: dict, exposure: dict | None, alerts: list[str]) -> list[str]:
    actions = validated.get("tactical_actions", []) or []
    if actions:
        top_action = actions[0]
        action_text = f"今天最重要的动作是 {top_action.get('fund_name')}：{top_action.get('validated_action')} {money(top_action.get('validated_amount', 0))}。"
    else:
        action_text = "今天没有需要立刻执行的战术动作，主要以观察和按规则定投为主。"
    market_text = f"今天市场整体判断是：{validated.get('market_view', {}).get('summary', '暂无明确判断')}。"
    risk_text = alerts[0] if alerts else (
        f"当前组合最大的暴露点是 {exposure['largest_style_group']['name']} {exposure['largest_style_group']['weight_pct']}%。"
        if exposure and exposure.get("largest_style_group")
        else "当前没有额外高优先风险提醒。"
    )
    return [market_text, action_text, risk_text]


def money(v) -> str:
    try:
        return f"{float(v):,.2f} 元"
    except Exception:
        return "—"


def pct(v, digits=2) -> str:
    try:
        return f"{float(v):.{digits}f}%"
    except Exception:
        return "—"


def num(v, digits=4) -> str:
    try:
        return f"{float(v):.{digits}f}"
    except Exception:
        return "—"


def open_path(path: Path) -> None:
    try:
        os.startfile(str(path))
    except AttributeError:
        subprocess.Popen(["xdg-open", str(path)])


def format_timestamp(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if not value:
        return "—"
    return str(value)


def file_mtime_text(path: Path) -> str:
    if not path.exists():
        return "—"
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def build_auto_realtime_status_text(last_generated_at: str, next_run_at: datetime | None, busy: bool) -> str:
    parts = ["自动刷新：启动即刷新，应用开启期间每 5 分钟刷新一次。"]
    if last_generated_at:
        parts.append(f"最近成功刷新：{last_generated_at}")
    if next_run_at is not None:
        parts.append(f"下次计划刷新：{format_timestamp(next_run_at)}")
    if busy:
        parts.append("当前有其他任务运行，自动刷新会等待空闲后重试。")
    return " | ".join(parts)


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
        read_json(path, {}).get("review_date") == report_date
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
    strategy = read_toml(home / "config" / "strategy.toml")
    schedule = strategy.get("schedule", {}) or {}
    current = now or datetime.now()
    today = current.date()
    nightly_hour, nightly_minute = _parse_schedule_time(schedule.get("nightly_start"), "21:00")
    nightly_reached = (current.hour, current.minute) >= (nightly_hour, nightly_minute)
    if _is_business_day(today) and nightly_reached:
        return today.isoformat()
    return _previous_business_day(today).isoformat()


def pending_nightly_catchup_dates(home: Path, portfolio_as_of_date: str, now: datetime | None = None) -> list[str]:
    strategy = read_toml(home / "config" / "strategy.toml")
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
    strategy = read_toml(home / "config" / "strategy.toml")
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
    strategy = read_toml(home / "config" / "strategy.toml")
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


def build_realtime_detail_text(item: dict) -> str:
    return (
        f"基金代码：{item.get('fund_code')}\n"
        f"基金名称：{item.get('fund_name')}\n"
        f"角色：{item.get('role', '暂无')}\n"
        f"风格分组：{item.get('style_group', '暂无')}\n"
        f"估算模式：{item.get('mode', '暂无')}\n"
        f"模式说明：{item.get('reason', '暂无')}\n"
        f"置信度：{num(item.get('confidence'), 2)}\n\n"
        f"份额与净值：\n"
        f"持有份额：{num(item.get('holding_units'), 6)}\n"
        f"份额来源：{item.get('unit_source', '暂无')}\n"
        f"份额置信度：{num(item.get('unit_confidence'), 2)}\n"
        f"官方净值：{num(item.get('official_nav'), 6)}\n"
        f"官方净值日期：{item.get('official_nav_date', '暂无')}\n"
        f"官方净值时效：{item.get('official_nav_freshness_label', '暂无')}\n"
        f"有效净值：{num(item.get('effective_nav'), 6)}\n\n"
        f"涨跌与收益：\n"
        f"估值涨跌：{pct(item.get('estimate_change_pct'), 2)}\n"
        f"估值时效：{item.get('estimate_freshness_label', '暂无')}\n"
        f"估值策略允许：{'是' if item.get('estimate_policy_allowed', False) else '否'}\n"
        f"代理涨跌：{pct(item.get('proxy_change_pct'), 2)}\n"
        f"代理时效：{item.get('proxy_freshness_label', '暂无')}\n"
        f"代理策略允许：{'是' if item.get('proxy_policy_allowed', False) else '否'}\n"
        f"采用涨跌：{pct(item.get('effective_change_pct'), 2)}\n"
        f"今日估算收益：{money(item.get('estimated_intraday_pnl_amount', 0))}\n"
        f"今日估算收益率：{pct(item.get('estimated_intraday_pnl_pct', 0), 4)}\n"
        f"估算持仓市值：{money(item.get('estimated_position_value', 0))}\n"
        f"估算总盈亏：{money(item.get('estimated_total_pnl_amount', 0))}\n"
        f"估算总收益率：{pct(item.get('estimated_total_return_pct', 0), 2)}\n\n"
        f"时间信息：\n"
        f"估值时间：{item.get('estimate_time', '暂无')}\n"
        f"代理时间：{item.get('proxy_time', '暂无')}\n"
        f"估值跨日状态：{'是' if item.get('stale', False) else '否'}"
    )


def build_review_summary_text(selected_date: str, review_batches: list[dict], memory: dict, operating_metrics: dict | None = None) -> str:
    def history_totals(items: list[dict]) -> dict:
        return {
            "supportive": sum(entry.get("summary", {}).get("supportive", 0) for entry in items),
            "adverse": sum(entry.get("summary", {}).get("adverse", 0) for entry in items),
            "missed_upside": sum(entry.get("summary", {}).get("missed_upside", 0) for entry in items),
        }

    def diagnostic_totals(items: list[dict]) -> dict[str, int]:
        totals: dict[str, int] = {}
        for entry in items:
            for label, count in (entry.get("diagnostic_summary", {}) or {}).items():
                totals[label] = totals.get(label, 0) + int(count or 0)
        return totals

    summary = {
        "supportive": sum(item.get("summary", {}).get("supportive", 0) for item in review_batches),
        "adverse": sum(item.get("summary", {}).get("adverse", 0) for item in review_batches),
        "missed_upside": sum(item.get("summary", {}).get("missed_upside", 0) for item in review_batches),
        "unknown": sum(item.get("summary", {}).get("unknown", 0) for item in review_batches),
    }
    advice_batches = [item for item in review_batches if item.get("source", "advice") == "advice"]
    execution_batches = [item for item in review_batches if item.get("source") == "execution"]
    history = memory.get("review_history", [])
    advice_history = [item for item in history if item.get("source", "advice") == "advice"]
    execution_history = [item for item in history if item.get("source") == "execution"]
    advice_30 = history_totals(advice_history[-30:])
    advice_90 = history_totals(advice_history[-90:])
    diagnostics = diagnostic_totals(review_batches)
    top_diagnostics = sorted(diagnostics.items(), key=lambda item: (-item[1], item[0]))[:5]
    operating_metrics = operating_metrics or {"sample_days": 0, "fallback_days": 0, "stale_days": 0}
    diagnostic_lines = [f"- {label}={count}" for label, count in top_diagnostics] or ["- 暂无"]
    batch_lines = [
        f"- {('建议层' if item.get('source', 'advice') == 'advice' else '执行层')} {'T0' if int(item.get('horizon', 0)) == 0 else 'T+' + str(int(item.get('horizon', 0)))} | base={item.get('base_date')}"
        for item in review_batches
    ] or ["- 暂无"]
    text_lines = [
        f"复盘日期：{selected_date}",
        f"复盘批次数：{len(review_batches)}",
        f"建议层批次：{len(advice_batches)}",
        f"执行层批次：{len(execution_batches)}",
        f"supportive：{summary.get('supportive', 0)}",
        f"adverse：{summary.get('adverse', 0)}",
        f"missed_upside：{summary.get('missed_upside', 0)}",
        f"unknown：{summary.get('unknown', 0)}",
        "",
        "历史绩效面板：",
        f"- 最近30条建议层 supportive={advice_30['supportive']} | adverse={advice_30['adverse']} | missed={advice_30['missed_upside']}",
        f"- 最近90条建议层 supportive={advice_90['supportive']} | adverse={advice_90['adverse']} | missed={advice_90['missed_upside']}",
        f"- 累计执行层复盘记录：{len(execution_history)}",
        f"- 最近{operating_metrics.get('sample_days', 0)}天 fallback 天数：{operating_metrics.get('fallback_days', 0)}",
        f"- 最近{operating_metrics.get('sample_days', 0)}天 stale 实时快照天数：{operating_metrics.get('stale_days', 0)}",
        "",
        "高频诊断标签：",
        *diagnostic_lines,
        "",
        "当日批次：",
        *batch_lines,
        "",
        "最新 lessons：",
        *[f"- {x.get('text', '')}" for x in (memory.get("lessons", [])[-5:] or [{"text": "暂无"}])],
        "",
        "最新 bias adjustments：",
        *[
            f"- [{x.get('scope')}] {x.get('target')}：{x.get('adjustment')}"
            for x in (memory.get("bias_adjustments", [])[-5:] or [{"scope": "", "target": "", "adjustment": "暂无"}])
        ],
        "",
        "最新 agent feedback：",
        *[f"- {x.get('agent_name')}：{x.get('bias')}" for x in (memory.get("agent_feedback", [])[-5:] or [{"agent_name": "", "bias": "暂无"}])],
    ]
    return "\n".join(text_lines)


def build_fund_detail_text(item: dict, realtime_item: dict | None, review_item: dict | None, aggregate: dict | None = None) -> str:
    from decision_support import summarize_fund_agent_signals, summarize_fund_stage_signals

    agent_summary = summarize_fund_agent_signals(aggregate or {}, item.get("fund_code", ""))
    stage_summary = summarize_fund_stage_signals(aggregate or {}, item.get("fund_code", ""))
    text = (
        f"基金代码：{item.get('fund_code')}\n"
        f"基金名称：{item.get('fund_name')}\n"
        f"建议编号：{item.get('suggestion_id', '暂无')}\n"
        f"所属分组：{item.get('_section')}\n"
        f"校验后动作：{item.get('validated_action')}\n"
        f"校验后金额：{money(item.get('validated_amount', 0))}\n"
        f"执行状态：{item.get('execution_status', 'pending')}\n"
        f"已执行金额：{money(item.get('executed_amount', 0))}\n"
        f"模型原动作：{item.get('model_action', '暂无')}\n"
        f"置信度：{num(item.get('confidence'), 2)}\n\n"
        f"可信度横幅：\n"
        f"- 建议模式：{item.get('advice_mode', 'validated')}\n"
        f"- 是否已绑定交易：{'是' if item.get('linked_trade_date') else '否'}\n"
        f"- 最近交易日期：{item.get('linked_trade_date', '暂无')}\n\n"
        f"核心判断：\n{item.get('thesis', '暂无')}\n\n"
        f"依据：\n" + "\n".join(f"- {x}" for x in (item.get("evidence", []) or ["暂无"])) + "\n\n"
        f"风险：\n" + "\n".join(f"- {x}" for x in (item.get("risks", []) or ["暂无"])) + "\n\n"
        f"规则校验：\n" + "\n".join(f"- {x}" for x in (item.get("validation_notes", []) or ["暂无"])) + "\n\n"
        f"参考智能体：\n" + "\n".join(f"- {x}" for x in (item.get("agent_support", []) or ["暂无"]))
    )
    text += (
        f"\n\n委员会共识：\n"
        f"- 支持智能体：{len(agent_summary.get('supporting_agents', []) or [])}\n"
        f"- 谨慎/反对智能体：{len(agent_summary.get('caution_agents', []) or [])}\n"
        f"- 中性智能体：{len(agent_summary.get('neutral_agents', []) or [])}\n"
        f"- 是否存在分歧：{'是' if agent_summary.get('has_conflict') else '否'}"
    )
    if agent_summary.get("support_points"):
        text += "\n- 支持要点：\n" + "\n".join(f"  - {x}" for x in agent_summary.get("support_points", [])[:4])
    if agent_summary.get("caution_points"):
        text += "\n- 谨慎要点：\n" + "\n".join(f"  - {x}" for x in agent_summary.get("caution_points", [])[:4])
    stage_lines = []
    for stage in ("analyst", "researcher", "manager"):
        bucket = stage_summary.get(stage, {})
        if not bucket:
            continue
        total = len(bucket.get("support", []) or []) + len(bucket.get("caution", []) or []) + len(bucket.get("neutral", []) or [])
        if total <= 0:
            continue
        highlight = "；".join((bucket.get("highlights") or [])[:2])
        detail = f"{stage} | 支持 {len(bucket.get('support', []) or [])} | 谨慎 {len(bucket.get('caution', []) or [])} | 中性 {len(bucket.get('neutral', []) or [])}"
        if highlight:
            detail += f" | {highlight}"
        stage_lines.append(detail)
    if stage_lines:
        text += "\n\n研究链路：\n" + "\n".join(f"- {line}" for line in stage_lines)
    if realtime_item:
        text += (
            f"\n\n实时收益参考：\n- 模式：{realtime_item.get('mode')}\n"
            f"- 今日估算收益：{money(realtime_item.get('estimated_intraday_pnl_amount', 0))}\n"
            f"- 今日估算涨跌：{pct(realtime_item.get('effective_change_pct', 0), 2)}\n"
            f"- 说明：{realtime_item.get('reason')}"
        )
    if review_item:
        review_return = review_item.get("evaluation_return_pct", review_item.get("review_day_change_pct", 0))
        review_basis = review_item.get("evaluation_basis", "review_day_change")
        text += (
            f"\n\n复盘结果：\n- outcome：{review_item.get('outcome')}\n"
            f"- diagnostic：{review_item.get('diagnostic_label', 'unknown')}\n"
            f"- 评估口径：{review_basis}\n"
            f"- 评估收益：{pct(review_return, 2)}\n"
            f"- 当日真实涨跌：{pct(review_item.get('review_day_change_pct', 0), 2)}\n"
            f"- 一周涨跌：{pct(review_item.get('review_week_change_pct', 0), 2)}"
        )
        if review_item.get("review_period_return_pct") is not None:
            text += (
                f"\n- 持有期收益：{pct(review_item.get('review_period_return_pct', 0), 2)}"
                f" | {review_item.get('review_period_start_date', '暂无')} -> {review_item.get('review_period_end_date', '暂无')}"
            )
        if review_item.get("diagnostic_reason"):
            text += f"\n- 诊断原因：{review_item.get('diagnostic_reason')}"
    return text


def build_agent_detail_text(name: str, agent: dict, aggregate: dict | None = None) -> str:
    from decision_support import build_agent_stage_snapshot

    out = agent.get("output", {})
    stage_snapshot = build_agent_stage_snapshot(name, aggregate)
    lines = [
        f"智能体：{name}",
        f"研究阶段：{stage_snapshot.get('label', '暂无')}",
        f"职责：{stage_snapshot.get('description', '暂无')}",
        f"状态：{agent.get('status', 'unknown')}",
        f"置信度：{num(out.get('confidence'), 2)}",
        f"证据强度：{out.get('evidence_strength', '暂无')}",
        f"数据新鲜度：{out.get('data_freshness', '暂无')}",
        f"上游输入：{'、'.join(stage_snapshot.get('depends_on', []) or []) or '无'}",
        f"下游去向：{'、'.join(stage_snapshot.get('consumers', []) or []) or '无'}",
        f"委员会核心：{'是' if stage_snapshot.get('is_committee_core') else '否'}",
        "",
        "摘要：",
        out.get("summary", "暂无"),
        "",
        "关键点：",
    ]
    lines += [f"- {x}" for x in (out.get("key_points", []) or ["暂无"])]
    lines += ["", "缺失信息："] + [f"- {x}" for x in (out.get("missing_info", []) or ["暂无"])]
    lines += ["", "观察项："] + [f"- {x}" for x in (out.get("watchouts", []) or ["暂无"])]
    if out.get("portfolio_view"):
        pv = out["portfolio_view"]
        lines += ["", "组合视角：", f"- regime：{pv.get('regime')}", f"- risk_bias：{pv.get('risk_bias')}"]
    if out.get("fund_views"):
        lines += ["", "基金视角："] + [f"- {x.get('fund_code')} | {x.get('action_bias')} | {x.get('thesis')}" for x in out.get("fund_views", [])[:8]]
    return "\n".join(lines)


def build_trade_preview_text(selected: dict | None, cash: dict | None, constraint: dict | None = None) -> str:
    if not selected:
        return "未找到该基金。"
    constraint = constraint or {}
    text = (
        f"基金代码：{selected.get('fund_code')}\n"
        f"基金名称：{selected.get('fund_name')}\n"
        f"角色：{selected.get('role')}\n"
        f"当前市值：{money(selected.get('current_value', 0))}\n"
        f"持有盈亏：{money(selected.get('holding_pnl', 0))}\n"
        f"持有收益率：{pct(selected.get('holding_return_pct', 0), 2)}\n"
        f"持有份额：{num(selected.get('holding_units'), 6)}\n"
        f"最近估值净值：{num(selected.get('last_valuation_nav'), 6)}\n"
        f"份额来源：{selected.get('units_source', '暂无')}\n"
        f"锁定金额：{money(constraint.get('locked_amount', 0))}\n"
        f"当前可卖金额：{money(constraint.get('available_to_sell', selected.get('current_value', 0)))}\n"
        f"最短持有天数：{constraint.get('min_hold_days', 0)}\n"
        f"卖出到账时效：T+{constraint.get('redeem_settlement_days', 0)}\n"
        f"申购确认时效：T+{constraint.get('purchase_confirm_days', 0)}\n"
        f"净值确认时效：T+{constraint.get('nav_confirm_days', 0)}\n"
        f"支持转换：{'是' if constraint.get('conversion_supported', False) else '否'}\n"
        f"估算赎回费率：{pct(constraint.get('estimated_redeem_fee_rate', 0), 2)}"
    )
    if cash:
        text += f"\n\n资金存储仓：\n- {cash.get('fund_name')}\n- 当前市值：{money(cash.get('current_value', 0))}\n- 当前份额：{num(cash.get('holding_units'), 6)}"
    if constraint.get("notes"):
        text += "\n\n约束提示：\n" + "\n".join(f"- {note}" for note in constraint["notes"])
    text += "\n\n录入说明：\n- buy / switch_in 会优先从资金存储仓扣减。\n- sell / switch_out 会将回款写回资金存储仓。\n- 如已知成交净值或成交份额，建议录入，可提升持仓精度。"
    return text


def build_settings_text(
    home: Path,
    selected_date: str,
    portfolio: dict,
    project: dict,
    strategy: dict,
    watchlist: dict,
    llm_config: dict,
    llm_raw: dict,
    realtime: dict,
    preflight: dict,
    manifests: dict[str, dict],
) -> str:
    runtime = project.get("runtime", {})
    paths = project.get("paths", {})
    latest_checks = preflight.get("checks", [])[-8:]
    manifest_lines = []
    for label, payload in manifests.items():
        if not payload:
            manifest_lines.append(f"- {label}: 暂无 manifest")
            continue
        errors = payload.get("errors") or []
        extra_error = f" | error={errors[-1].get('error', '')}" if errors else ""
        manifest_lines.append(
            f"- {label}: status={payload.get('status', '')} | current_step={payload.get('current_step', '') or '—'} | total_seconds={payload.get('total_seconds', '—')}{extra_error}"
        )
    return (
        f"agent_home = {home}\n"
        f"selected_date = {selected_date}\n"
        f"configured_python_executable = {runtime.get('python_executable', '')}\n"
        f"desktop_launcher = {paths.get('desktop_launcher', '')}\n"
        f"strategy_risk_profile = {strategy.get('portfolio', {}).get('risk_profile', '')}\n"
        f"strategy_cash_hub_floor = {strategy.get('portfolio', {}).get('cash_hub_floor', '')}\n"
        f"strategy_daily_max_gross_trade_amount = {strategy.get('portfolio', {}).get('daily_max_gross_trade_amount', strategy.get('portfolio', {}).get('daily_max_trade_amount', ''))}\n"
        f"strategy_daily_max_net_buy_amount = {strategy.get('portfolio', {}).get('daily_max_net_buy_amount', strategy.get('portfolio', {}).get('daily_max_trade_amount', ''))}\n"
        f"strategy_dca_amount_per_fund = {strategy.get('core_dca', {}).get('amount_per_fund', '')}\n"
        f"strategy_report_mode = {strategy.get('schedule', {}).get('report_mode', '')}\n"
        f"watchlist_count = {len(watchlist.get('funds', []) or [])}\n"
        f"portfolio_as_of_date = {portfolio.get('as_of_date', '')}\n"
        f"portfolio_last_valuation_generated_at = {portfolio.get('last_valuation_generated_at', '')}\n"
        f"model_provider = {llm_config.get('model_provider', '')}\n"
        f"model = {llm_config.get('model', '')}\n"
        f"llm_mode = {llm_raw.get('mode', '')}\n"
        f"transport_name = {llm_raw.get('transport_name', '')}\n"
        f"stream_incomplete = {llm_raw.get('stream_incomplete', '')}\n\n"
        f"preflight_status = {preflight.get('status', '')}\n"
        f"preflight_checked_at = {preflight.get('checked_at', '')}\n"
        f"preflight_output = {home / 'db' / 'preflight' / 'latest.json'}\n"
        + ("preflight_recent_checks =\n" + "\n".join(f"- {item.get('name')} | {item.get('status')} | {item.get('detail')}" for item in latest_checks) + "\n\n" if latest_checks else "\n")
        + "latest_manifests =\n"
        + "\n".join(manifest_lines)
        + "\n\n"
        f"validated_advice = {home / 'db' / 'validated_advice' / (selected_date + '.json')}\n"
        f"portfolio_definition = {home / 'config' / 'portfolio_definition.json'}\n"
        f"portfolio_state_current = {home / 'db' / 'portfolio_state' / 'current.json'}\n"
        f"portfolio_state_snapshot = {home / 'db' / 'portfolio_state' / 'snapshots' / (selected_date + '.json')}\n"
        f"realtime_monitor = {home / 'db' / 'realtime_monitor' / (selected_date + '.json')}\n"
        f"portfolio_valuation = {home / 'db' / 'portfolio_valuation' / (selected_date + '.json')}\n"
        f"aggregate = {home / 'db' / 'agent_outputs' / selected_date / 'aggregate.json'}\n"
        f"review_result = {home / 'db' / 'review_results' / (selected_date + '_T0.json')}\n"
        f"trade_journal = {home / 'db' / 'trade_journal' / (selected_date + '.json')}\n"
        f"portfolio_report = {home / 'reports' / 'daily' / (selected_date + '_portfolio.md')}\n"
        f"review_report = {home / 'reports' / 'daily' / (selected_date + '_review.md')}\n\n"
        f"realtime_policy = {realtime.get('realtime_policy', {})}\n\n"
        f"说明：界面显示层已对历史乱码做自动修复；后续新数据会尽量保持 UTF-8 干净输出。"
    )


def build_dashboard_text(
    summary: dict,
    validated: dict,
    portfolio: dict,
    portfolio_report: str,
    exposure: dict | None = None,
    change_lines: list[str] | None = None,
    alerts: list[str] | None = None,
    plain_lines: list[str] | None = None,
) -> str:
    today = today_str()
    do_now = [
        f"{item.get('fund_name')}：{item.get('validated_action')} {money(item.get('validated_amount', 0))}"
        for section in ("tactical_actions", "dca_actions")
        for item in validated.get(section, []) or []
        if item.get("validated_action") not in {"hold"}
    ] or ["暂无需要立刻执行的动作"]
    wait_items = [
        f"{item.get('fund_name')}：{item.get('thesis', '继续观察')}"
        for item in validated.get("hold_actions", []) or []
        if item.get("agent_support")
    ] or ["暂无需要特别等待观察的动作"]
    avoid_items = alerts or ["暂无额外高优先风险提醒。"]
    failed_names = ", ".join(summary.get("failed_agent_names", []))
    failed = f"\n失败智能体：{failed_names}" if failed_names else ""
    advice_mode = summary.get("advice_mode", "") or "unknown"
    advice_note = "（fallback）" if summary.get("advice_is_fallback") else ("（mock）" if summary.get("advice_is_mock") else "")
    degraded = "（降级继续）" if summary.get("aggregate_degraded_ok") else ""
    stale_note = ""
    if validated.get("market_view"):
        stale_note = f"市场摘要：{validated.get('market_view', {}).get('summary', '暂无')}"
    text = (
        f"当前查看日期：{summary['selected_date']}\n"
        f"今天：{today}\n"
        f"实时刷新/日内链路/夜间复盘默认运行日期：{today}\n"
        f"组合估值日期：{portfolio.get('as_of_date', '暂无')}\n"
        f"当前界面持仓快照：{summary.get('portfolio_date', '暂无')}\n"
        f"组合重估生成时间：{portfolio.get('last_valuation_generated_at', '暂无')}\n"
        f"组合：{summary['portfolio_name'] or '暂无'}\n"
        f"市场状态：{validated.get('market_view', {}).get('regime', '暂无')}\n"
        f"智能体状态：{'全部正常' if summary['all_agents_ok'] else '存在失败'}{degraded}{failed}\n"
        f"运行前自检：{summary.get('preflight_status', '') or '暂无'}\n"
        f"建议生成模式：{advice_mode}{advice_note}\n"
        f"决策来源：{summary.get('decision_source', '') or '暂无'}\n"
        f"最终模型通道：{summary['transport_name'] or '暂无'}\n"
        f"可信度横幅：官方净值日期 {portfolio.get('as_of_date', '暂无')} | fallback={'是' if summary.get('advice_is_fallback') else '否'} | 失败智能体数={len(summary.get('failed_agent_names', []))}\n\n"
        f"{stale_note}\n\n"
        f"今天要做：\n" + "\n".join(f"- {x}" for x in do_now)
    )
    text += "\n\n今天可以等：\n" + "\n".join(f"- {line}" for line in wait_items[:8])
    text += "\n\n今天不建议做：\n" + "\n".join(f"- {line}" for line in avoid_items[:8])
    if plain_lines:
        text += "\n\n今天最重要的三件事：\n" + "\n".join(f"- {line}" for line in plain_lines)
    if change_lines:
        text += "\n\n与上一期相比：\n" + "\n".join(change_lines)
    delta_payload = summary.get("recommendation_delta", {}) if isinstance(summary, dict) else {}
    if isinstance(delta_payload, dict) and delta_payload.get("items"):
        text += "\n\n今日关键变化：\n" + "\n".join(
            f"- {item.get('fund_name', item.get('fund_code', ''))} | {item.get('reason_category', '')} | {item.get('delta_reason', '')}"
            for item in delta_payload.get("items", [])[:5]
        )
    if exposure:
        text += (
            f"\n\n组合暴露：\n"
            f"- 最大风格：{exposure['largest_style_group']['name']} {exposure['largest_style_group']['weight_pct']}%\n"
            f"- 前三风格集中度：{exposure['concentration_metrics']['top3_style_weight_pct']}%\n"
            f"- 海外权益占比：{exposure['concentration_metrics']['overseas_weight_pct']}%\n"
            f"- 防守缓冲占比：{exposure['concentration_metrics']['defensive_buffer_weight_pct']}%"
        )
        if exposure.get("alerts"):
            text += "\n" + "\n".join(f"- 暴露提醒：{item}" for item in exposure["alerts"])
    if portfolio_report:
        text += f"\n\n组合报告：\n{portfolio_report}"
    return text


def build_realtime_summary_text(realtime: dict) -> str:
    totals = realtime.get("totals", {})
    return (
        f"快照日期：{realtime.get('report_date', '暂无')}\n"
        f"实际生成时间：{realtime.get('generated_at', '暂无')}\n"
        f"行情时间（对应报告日）：{realtime.get('market_timestamp', '暂无')}\n"
        f"组合实时收益：{money(totals.get('estimated_intraday_pnl_amount', 0))}\n"
        f"组合估算市值：{money(totals.get('estimated_position_value', 0))}\n"
        f"组合估算总盈亏：{money(totals.get('estimated_total_pnl_amount', 0))}"
    )


def build_trade_output_text(trade_date: str, items: list[dict]) -> str:
    lines = [f"交易日期：{trade_date}", ""]
    for item in items:
        line = f"- {item.get('fund_code')} | {item.get('fund_name')} | {item.get('action')} | {money(item.get('amount', 0))}"
        if item.get("trade_nav") not in (None, ""):
            line += f" | 净值={item.get('trade_nav')}"
        if item.get("units") not in (None, ""):
            line += f" | 份额={item.get('units')}"
        if item.get("suggestion_id"):
            line += f" | 建议={item.get('suggestion_id')}"
        line += f" | {item.get('note', '')}"
        lines.append(line)
    if not items:
        lines.append("- 当日暂无交易记录。")
    return "\n".join(lines)


def build_portfolio_sync_preview_text(preview: dict) -> str:
    lines = [
        f"同步日期：{preview.get('sync_date', '暂无')}",
        f"来源：{preview.get('provider', 'alipay')}",
        f"截图数量：{preview.get('image_count', 0)}",
        f"可直接同步：{'是' if preview.get('apply_ready') else '否'}",
        f"识别条目：{len(preview.get('matched_items', []) or []) + len(preview.get('unmatched_detected', []) or [])}",
        f"已匹配持仓：{len(preview.get('matched_items', []) or [])}",
        f"未匹配条目：{len(preview.get('unmatched_detected', []) or [])}",
        f"系统中缺失于截图的持仓：{len(preview.get('missing_portfolio_funds', []) or [])}",
        "",
        "预警：",
    ]
    warning_lines = [str(item).strip() for item in (preview.get("warnings", []) or []) if str(item).strip()]
    warning_lines.extend(str(item).strip() for item in (preview.get("vision_warnings", []) or []) if str(item).strip())
    lines.extend(f"- {item}" for item in (warning_lines or ["暂无"]))
    lines.extend(["", "已匹配项目："])
    for item in preview.get("matched_items", []) or []:
        lines.append(
            f"- {item.get('display_name')} -> {item.get('matched_fund_name')} ({item.get('matched_fund_code')})"
            f" | score={item.get('match_score')}"
            f" | 市值 {money(item.get('before_current_value', 0))} -> {money(item.get('current_value', 0))}"
            f" | 持仓收益 {money(item.get('before_holding_pnl', 0))} -> {money(item.get('holding_pnl', 0))}"
            f" | 收益率 {pct(item.get('before_holding_return_pct', 0), 2)} -> {pct(item.get('holding_return_pct', 0), 2)}"
            f" | 状态 {item.get('match_status')}"
        )
    if not (preview.get("matched_items") or []):
        lines.append("- 暂无可同步项目。")

    lines.extend(["", "未匹配截图条目："])
    for item in preview.get("unmatched_detected", []) or []:
        lines.append(f"- {item.get('display_name')} | 市值 {money(item.get('current_value', 0))}")
    if not (preview.get("unmatched_detected") or []):
        lines.append("- 暂无。")

    lines.extend(["", "系统外新基金候选："])
    for item in preview.get("new_fund_candidates", []) or []:
        lines.append(
            f"- {item.get('display_name')} -> {item.get('matched_fund_name')} ({item.get('matched_fund_code')})"
            f" | 来源 {item.get('match_source')}"
            f" | 默认角色 {item.get('role') or '待推断'}"
        )
    if not (preview.get("new_fund_candidates") or []):
        lines.append("- 暂无。")

    lines.extend(["", "当前系统持仓但截图未出现："])
    for item in preview.get("missing_portfolio_funds", []) or []:
        lines.append(f"- {item.get('fund_name')} ({item.get('fund_code')}) | 当前市值 {money(item.get('current_value', 0))}")
    if not (preview.get("missing_portfolio_funds") or []):
        lines.append("- 暂无。")
    return "\n".join(lines)


def build_portfolio_sync_apply_text(summary: dict) -> str:
    lines = [
        f"同步日期：{summary.get('sync_date', '暂无')}",
        f"来源：{summary.get('provider', 'alipay')}",
        f"截图数量：{summary.get('image_count', 0)}",
        f"更新基金数：{summary.get('updated_fund_count', 0)}",
        f"新增基金数：{summary.get('added_fund_count', 0)}",
        f"归零缺失持仓数：{summary.get('dropped_missing_count', 0)}",
        f"未匹配截图条目数：{summary.get('unmatched_detected_count', 0)}",
        f"当前持仓文件：{summary.get('current_path', '')}",
        f"快照文件：{summary.get('snapshot_path', '')}",
        "",
        "已更新基金：",
    ]
    updated = summary.get("updated_fund_codes", []) or []
    added = summary.get("added_fund_codes", []) or []
    dropped = summary.get("dropped_missing_fund_codes", []) or []
    lines.extend(f"- {code}" for code in (updated or ["暂无"]))
    lines.extend(["", "已新增基金："])
    lines.extend(f"- {code}" for code in (added or ["暂无"]))
    lines.extend(["", "已归零基金："])
    lines.extend(f"- {code}" for code in (dropped or ["暂无"]))
    return "\n".join(lines)


def build_fund_list_label(item: dict) -> str:
    status = item.get("execution_status", "")
    status_text = f" | {status}" if status else ""
    return f"{item.get('fund_code')} | {item.get('fund_name')} | {item.get('validated_action')} {money(item.get('validated_amount', 0))}{status_text}"


def build_agent_list_label(name: str, agent: dict) -> str:
    confidence = agent.get("output", {}).get("confidence", "—")
    return f"{name} | {agent.get('status', 'unknown')} | {confidence}"


def build_realtime_row_values(item: dict) -> tuple[str, str, str, str, str, str]:
    return (
        f"{item['fund_code']} {item['fund_name'][:10]}",
        num(item.get("holding_units"), 2),
        f"{float(item.get('estimated_intraday_pnl_amount', 0.0)):.2f}",
        pct(item.get("effective_change_pct", 0), 2),
        num(item.get("confidence"), 2),
        item.get("mode", ""),
    )


def build_review_detail_fallback(selected_date: str, review_batches: list[dict]) -> str:
    items = [entry for batch in review_batches for entry in (batch.get("items", []) or [])]
    lines = [f"复盘日期：{selected_date}", ""]
    lines.extend(
        f"- {x.get('review_source', 'advice')} | {x.get('fund_code')} | {x.get('fund_name')} | "
        f"{x.get('source_action', x.get('validated_action'))} {money(x.get('source_amount', x.get('validated_amount', 0)))} | "
        f"outcome={x.get('outcome')} | diagnostic={x.get('diagnostic_label', 'unknown')} | "
        f"basis={x.get('evaluation_basis', 'review_day_change')} | return={pct(x.get('evaluation_return_pct'), 2)}"
        for x in items
    )
    if not items:
        lines.append("暂无夜间复盘报告。")
    return "\n".join(lines)


def build_learning_summary_text(selected_date: str, cycle: dict, ledger: dict, replay_experiments: list[dict], memory: dict) -> str:
    ledger_summary = ledger.get("summary", {}) or {}
    lines = [
        f"学习日期：{selected_date}",
        f"学习批次：{cycle.get('batch_count', 0)}",
        f"建议层批次：{cycle.get('advice_batch_count', 0)}",
        f"执行层批次：{cycle.get('execution_batch_count', 0)}",
        f"supportive：{cycle.get('summary', {}).get('supportive', 0)}",
        f"adverse：{cycle.get('summary', {}).get('adverse', 0)}",
        f"missed_upside：{cycle.get('summary', {}).get('missed_upside', 0)}",
        "",
        "记忆分层：",
        f"- candidate：{ledger_summary.get('candidate', 0)}",
        f"- strategic：{ledger_summary.get('strategic', 0)}",
        f"- permanent：{ledger_summary.get('permanent', 0)}",
        f"- core_permanent：{ledger_summary.get('core_permanent', 0)}",
        "",
        f"核心永久记忆命中池：{len(memory.get('core_permanent_memory', []) or [])}",
        f"永久记忆命中池：{len(memory.get('permanent_memory', []) or [])}",
        f"战略记忆命中池：{len(memory.get('strategic_memory', []) or [])}",
    ]
    headline = fix_text(str(cycle.get("headline", "") or "").strip())
    if headline:
        lines.extend(["", "今晚结论：", headline])
    promotions = cycle.get("promotion_events", []) or []
    if promotions:
        lines.extend(["", "阶段变化："])
        lines.extend(
            f"- {item.get('rule_id', '')}：{item.get('from_stage', '')} -> {item.get('to_stage', '')} | {item.get('reason', '')}"
            for item in promotions[:8]
        )
    diagnostics = cycle.get("diagnostic_summary", {}) or {}
    if diagnostics:
        lines.extend(["", "高频诊断："])
        lines.extend(f"- {label}={count}" for label, count in sorted(diagnostics.items(), key=lambda item: (-item[1], item[0]))[:8])
    if replay_experiments:
        lines.extend(["", "最近 Replay："])
        lines.extend(
            f"- {item.get('experiment_id', '')} | {item.get('mode', '')} | changed_days={item.get('changed_days', 0)} | "
            f"edge_delta={item.get('edge_delta_total', 0.0)} | applied={'yes' if item.get('applied_to_learning') else 'no'}"
            for item in replay_experiments[:5]
        )
    return "\n".join(lines)


def build_learning_detail_fallback(selected_date: str, cycle: dict, ledger: dict, review_batches: list[dict]) -> str:
    lines = [f"学习日期：{selected_date}", ""]
    if cycle:
        lines.append(f"headline：{cycle.get('headline', '')}")
        lines.append("")
    core_rules = [item for item in (ledger.get("rules", []) or []) if item.get("stage") == "core_permanent" and item.get("status") == "active"]
    permanent_rules = [item for item in (ledger.get("rules", []) or []) if item.get("stage") == "permanent" and item.get("status") == "active"]
    strategic_rules = [item for item in (ledger.get("rules", []) or []) if item.get("stage") == "strategic" and item.get("status") == "active"]
    lines.append("== Core Permanent ==")
    if core_rules:
        lines.extend(f"- {item.get('title', '')} | support={item.get('support_score', 0)} | confidence={item.get('confidence', 0)} | {item.get('text', '')}" for item in core_rules[:12])
    else:
        lines.append("- 暂无")
    lines.extend(["", "== Permanent =="])
    if permanent_rules:
        lines.extend(f"- {item.get('title', '')} | support={item.get('support_score', 0)} | contradiction={item.get('contradiction_score', 0)} | {item.get('text', '')}" for item in permanent_rules[:12])
    else:
        lines.append("- 暂无")
    lines.extend(["", "== Strategic =="])
    if strategic_rules:
        lines.extend(f"- {item.get('title', '')} | support={item.get('support_score', 0)} | contradiction={item.get('contradiction_score', 0)} | {item.get('text', '')}" for item in strategic_rules[:12])
    else:
        lines.append("- 暂无")
    if cycle.get("latest_replay_experiments"):
        lines.extend(["", "== Replay Lab =="])
        lines.extend(
            f"- {item.get('experiment_id', '')} | changed_days={item.get('changed_days', 0)} | edge_delta={item.get('edge_delta_total', 0.0)}"
            for item in cycle.get("latest_replay_experiments", [])[:6]
        )
    lines.extend(["", "== Tonight Batches =="])
    if review_batches:
        lines.extend(
            f"- {batch.get('source', 'advice')} | base={batch.get('base_date', '')} | horizon=T{batch.get('horizon', 0)} | primary={batch.get('primary_diagnostic', '')}"
            for batch in review_batches
        )
    else:
        lines.append("- 暂无")
    return "\n".join(lines)


def build_replay_differences_text(experiment: dict) -> str:
    if not experiment:
        return "- No replay experiment selected."
    lines = [
        f"experiment_id: {experiment.get('experiment_id', '')}",
        f"mode: {experiment.get('mode', '')}",
        f"range: {experiment.get('start_date', '')} -> {experiment.get('end_date', '')}",
        f"changed_days: {experiment.get('changed_days', 0)}",
        f"difference_count: {experiment.get('difference_count', 0)}",
        f"edge_delta_total: {experiment.get('edge_delta_total', 0.0)}",
        f"applied_to_learning: {'yes' if experiment.get('applied_to_learning') else 'no'}",
        "",
        "Top differences:",
    ]
    differences = experiment.get("top_differences", []) or []
    if differences:
        for item in differences[:12]:
            lines.append(
                f"- {item.get('report_date', '')} | {item.get('fund_code', '')} | "
                f"{item.get('existing_action', '')} -> {item.get('replay_action', '')} | "
                f"edge {item.get('existing_edge', 0.0)} -> {item.get('replay_edge', 0.0)} | "
                f"delta={item.get('edge_delta', 0.0)} | diagnostic={item.get('diagnostic_label', '')}"
            )
    else:
        lines.append("- No changed item deltas in this experiment.")
    return "\n".join(lines)


def build_replay_rule_impact_text(experiment: dict) -> str:
    if not experiment:
        return "- No replay experiment selected."
    lines = [
        f"experiment_id: {experiment.get('experiment_id', '')}",
        f"improved_items: {experiment.get('improved_items', 0)}",
        f"worsened_items: {experiment.get('worsened_items', 0)}",
        "",
        "Learning impacts:",
    ]
    impacts = experiment.get("learning_impacts", []) or []
    if impacts:
        for item in impacts[:12]:
            fund_codes = ", ".join(item.get("fund_codes", []) or [])
            lines.append(
                f"- {item.get('rule_label', '')} | support={item.get('support_count', 0)} | "
                f"contradiction={item.get('contradiction_count', 0)} | "
                f"changed={item.get('changed_item_count', 0)} | edge_delta={item.get('total_edge_delta', 0.0)} | "
                f"funds={fund_codes or '--'}"
            )
    else:
        lines.append("- No rule impacts were derived from this replay.")
    return "\n".join(lines)
