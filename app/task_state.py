from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ui_support import file_mtime_text, latest_manifest, money, num, pct, read_json, today_str


TASK_CARD_SPECS = {
    "intraday": {
        "title": "日内链路",
        "purpose": "生成当日分析建议与调仓建议",
    },
    "realtime": {
        "title": "实时刷新",
        "purpose": "生成当日实时收益估算快照",
    },
    "nightly": {
        "title": "夜间复盘",
        "purpose": "收盘后复盘当日建议是否有效",
    },
}


def current_task_result_info(home: Path, task_kind: str) -> dict:
    run_date = today_str()
    if task_kind == "intraday":
        path = home / "db" / "validated_advice" / f"{run_date}.json"
        payload = read_json(path, {})
        manifest = latest_manifest(home, "daily_pipeline", run_date, mode="intraday")
        return {
            "exists": path.exists(),
            "result_date": payload.get("report_date", "—"),
            "generated_at": payload.get("generated_at", file_mtime_text(path)),
            "market_time": "—",
            "extra": payload.get("market_view", {}).get("regime", "—"),
            "extra_label": "市场状态",
            "manifest_status": manifest.get("status", ""),
            "manifest_current_step": manifest.get("current_step", ""),
            "manifest_error": ((manifest.get("errors") or [{}])[-1].get("error", "")),
        }
    if task_kind == "realtime":
        path = home / "db" / "realtime_monitor" / f"{run_date}.json"
        payload = read_json(path, {})
        manifest = latest_manifest(home, "realtime_monitor", run_date, mode="realtime")
        return {
            "exists": path.exists(),
            "result_date": payload.get("report_date", "—"),
            "generated_at": payload.get("generated_at", file_mtime_text(path)),
            "market_time": payload.get("market_timestamp", "—"),
            "extra": money(payload.get("totals", {}).get("estimated_intraday_pnl_amount", 0)) if path.exists() else "—",
            "extra_label": "组合实时收益",
            "manifest_status": manifest.get("status", ""),
            "manifest_current_step": manifest.get("current_step", ""),
            "manifest_error": ((manifest.get("errors") or [{}])[-1].get("error", "")),
        }
    path = home / "db" / "review_results" / f"{run_date}_T0.json"
    report_path = home / "reports" / "daily" / f"{run_date}_review.md"
    valuation_path = home / "db" / "portfolio_valuation" / f"{run_date}.json"
    valuation_payload = read_json(valuation_path, {})
    manifest = latest_manifest(home, "daily_pipeline", run_date, mode="nightly")
    review_batches = []
    review_dir = home / "db" / "review_results"
    if review_dir.exists():
        for review_path in sorted(review_dir.glob("*.json")):
            payload = read_json(review_path, {})
            if payload.get("review_date") == run_date:
                review_batches.append(payload)
    review_batches.sort(key=lambda item: (int(item.get("horizon", 0)), item.get("base_date", "")))
    payload = read_json(path, {})
    aggregated_supportive = sum(item.get("summary", {}).get("supportive", 0) for item in review_batches)
    aggregated_adverse = sum(item.get("summary", {}).get("adverse", 0) for item in review_batches)
    return {
        "exists": bool(review_batches) or report_path.exists(),
        "result_date": (review_batches[0].get("review_date") if review_batches else payload.get("review_date", run_date if report_path.exists() else "—")),
        "generated_at": file_mtime_text(report_path if report_path.exists() else path),
        "market_time": "—",
        "extra": (
            f"supportive={aggregated_supportive} / adverse={aggregated_adverse} / 批次={len(review_batches)}"
            if review_batches
            else ("已完成官方净值重估" if valuation_path.exists() else "—")
        ),
        "extra_label": "复盘摘要",
        "valuation_exists": valuation_path.exists(),
        "valuation_generated_at": valuation_payload.get("generated_at", file_mtime_text(valuation_path)),
        "manifest_status": manifest.get("status", ""),
        "manifest_current_step": manifest.get("current_step", ""),
        "manifest_error": ((manifest.get("errors") or [{}])[-1].get("error", "")),
    }


def build_task_card_text(task_kind: str, runtime: dict, info: dict) -> str:
    spec = TASK_CARD_SPECS[task_kind]
    status_map = {
        "idle": "空闲",
        "running": "运行中",
        "done": "已完成",
        "failed": "失败",
    }
    lines = [
        f"定位：{spec['purpose']}",
        f"手动运行日期：{today_str()}",
        f"当前状态：{status_map.get(runtime['status'], runtime['status'])}",
        f"当前步骤：{runtime.get('step', '—')}",
        f"今日结果：{'已生成' if info['exists'] else '未生成'}",
        f"结果日期：{info['result_date']}",
        f"结果生成时间：{info['generated_at']}",
    ]
    if task_kind == "realtime":
        lines.append(f"行情时间：{info['market_time']}")
    if info.get("extra_label"):
        lines.append(f"{info['extra_label']}：{info['extra']}")
    if task_kind == "nightly":
        lines.append(f"官方净值重估：{'已生成' if info.get('valuation_exists') else '未生成'}")
        lines.append(f"重估生成时间：{info.get('valuation_generated_at', '—')}")
    if info.get("manifest_status"):
        lines.append(f"最近 manifest 状态：{info.get('manifest_status')}")
    if info.get("manifest_current_step"):
        lines.append(f"最近 manifest 当前步骤：{info.get('manifest_current_step')}")
    if info.get("manifest_error"):
        lines.append(f"最近 manifest 错误：{info.get('manifest_error')}")
    if runtime.get("started_at"):
        lines.append(f"开始时间：{format_timestamp(runtime['started_at'])}")
    if runtime.get("ended_at"):
        lines.append(f"结束时间：{format_timestamp(runtime['ended_at'])}")
    if runtime.get("elapsed") is not None:
        lines.append(f"最近耗时：{runtime['elapsed']}s")
    if runtime.get("last_log"):
        lines.append(f"最近日志：{runtime['last_log']}")
    return "\n".join(lines)


def interpret_run_output_line(clean: str) -> str | None:
    mapping = [
        (">>> START ", "当前步骤："),
        (">>> DONE ", "最近完成："),
        (">>> AGENT_START ", "当前 Agent："),
        (">>> AGENT_DONE ", "最近完成 Agent："),
        (">>> AGENT_FAIL ", "Agent 失败："),
        (">>> PIPELINE_DONE ", "流水线完成："),
    ]
    for prefix, label in mapping:
        if clean.startswith(prefix):
            return label + clean.removeprefix(prefix).strip()
    return None


def normalize_task_step_text(step_label: str) -> str:
    value = step_label or ""
    for prefix in ("当前步骤：", "最近完成：", "当前 Agent：", "最近完成 Agent：", "流水线完成：", "Agent 失败："):
        value = value.replace(prefix, "")
    return value or "—"


def running_hint_text(job_name: str, task_date: str, elapsed: int) -> str:
    return f"当前任务：{job_name}｜运行日期 {task_date}｜已运行 {elapsed}s"


def finished_hint_text(job_name: str, task_date: str, elapsed: int, success: bool) -> str:
    return f"最近任务：{job_name}｜运行日期 {task_date}｜耗时 {elapsed}s｜{'已完成' if success else '失败'}"


def initial_task_status() -> dict[str, dict]:
    return {
        key: {
            "status": "idle",
            "step": "—",
            "run_date": today_str(),
            "started_at": None,
            "ended_at": None,
            "elapsed": None,
            "last_log": "",
        }
        for key in TASK_CARD_SPECS
    }


def begin_task_status(task_status: dict[str, dict], task_kind: str, task_date: str, started_at: datetime) -> None:
    if task_kind not in task_status:
        return
    task_status[task_kind].update(
        {
            "status": "running",
            "step": "准备启动",
            "run_date": task_date,
            "started_at": started_at,
            "ended_at": None,
            "elapsed": 0,
            "last_log": "",
        }
    )


def update_task_elapsed(task_status: dict[str, dict], task_kind: str, elapsed: int) -> None:
    if task_kind not in task_status:
        return
    task_status[task_kind]["elapsed"] = elapsed


def update_task_step(task_status: dict[str, dict], task_kind: str, step_label: str) -> None:
    if task_kind not in task_status:
        return
    task_status[task_kind]["step"] = normalize_task_step_text(step_label)


def finish_task_status(task_status: dict[str, dict], task_kind: str, success: bool, ended_at: datetime, elapsed: int, log_path: str) -> None:
    if task_kind not in task_status:
        return
    task_status[task_kind].update(
        {
            "status": "done" if success else "failed",
            "ended_at": ended_at,
            "elapsed": elapsed,
            "last_log": log_path,
        }
    )


def format_timestamp(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if not value:
        return "—"
    return str(value)
