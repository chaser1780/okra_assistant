from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from common import (
    analysis_quality_for_start,
    committee_advice_path,
    committee_decision_bundle_path,
    daily_workspace_dir,
    dump_json,
    ensure_layout,
    is_runtime_stale,
    process_exists,
    refresh_runtime_heartbeat,
    llm_context_path,
    load_json,
    market_close_time,
    resolve_date,
    shanghai_now,
    timestamp_now,
    today_analysis_runtime_path,
    trading_days_between,
    validated_advice_path,
    is_trading_day,
    today_shanghai,
)
from execution_sync import build_execution_sync_payload, update_pending_confirmations


SCRIPT_DIR = Path(__file__).resolve().parent
MAX_AUTO_BACKFILL_CALENDAR_DAYS = 3


RUNTIME_STATUS = {
    "running": "running",
    "ok": "ok",
    "degraded": "degraded",
    "retryable_failure": "retryable_failure",
    "blocking_failure": "blocking_failure",
}


@dataclass(frozen=True)
class OrchestratorPaths:
    workspace: Path
    decision: Path
    analysis: Path
    summary: Path
    brief: Path
    meta: Path
    lock: Path


def _run_script(agent_home: Path, script_name: str, *args: str, allow_fail: bool = False) -> dict:
    command = [sys.executable, "-B", "-X", "utf8", str(SCRIPT_DIR / script_name), "--agent-home", str(agent_home), *args]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    payload = {"command": command, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    if completed.returncode != 0 and not allow_fail:
        raise RuntimeError(f"{script_name} failed: {completed.stderr or completed.stdout}")
    return payload


def _paths(agent_home: Path, report_date: str) -> OrchestratorPaths:
    workspace = daily_workspace_dir(agent_home, report_date)
    return OrchestratorPaths(
        workspace=workspace,
        decision=workspace / "today_decision.json",
        analysis=workspace / "today_analysis.json",
        summary=workspace / "today_summary.json",
        brief=workspace / "daily_brief.md",
        meta=workspace / "today_analysis_meta.json",
        lock=workspace / ".today_analysis.lock",
    )


def _write_runtime(agent_home: Path, report_date: str, payload: dict) -> None:
    refresh_runtime_heartbeat(payload)
    dump_json(today_analysis_runtime_path(agent_home, report_date), payload)


def _runtime_path(agent_home: Path, report_date: str) -> Path:
    return today_analysis_runtime_path(agent_home, report_date)


def read_runtime(agent_home: Path, report_date: str) -> dict:
    path = _runtime_path(agent_home, report_date)
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def ensure_runtime_not_stale(agent_home: Path, report_date: str) -> dict:
    runtime = read_runtime(agent_home, report_date)
    if not runtime:
        return {}
    if not is_runtime_stale(runtime):
        return runtime
    runtime.update(
        {
            "status": RUNTIME_STATUS["retryable_failure"],
            "phase": "aborted",
            "currentStep": "",
            "currentAgent": "",
            "currentAgentStage": "",
            "runningAgents": [],
            "endedAt": timestamp_now(),
            "resultReady": False,
            "resultRunId": str(runtime.get("resultRunId", "") or ""),
            "lastError": str(runtime.get("lastError", "") or "stale_today_analysis_runtime"),
        }
    )
    _write_runtime(agent_home, report_date, runtime)
    return runtime


def get_active_runtime(agent_home: Path, report_date: str) -> dict:
    runtime = ensure_runtime_not_stale(agent_home, report_date)
    if str(runtime.get("status", "") or "").lower() != "running":
        return {}
    if not process_exists(runtime.get("pid")):
        return {}
    return runtime


class AlreadyRunningError(RuntimeError):
    def __init__(self, runtime: dict):
        self.runtime = runtime
        run_id = str(runtime.get("runId", "") or "")
        report_date = str(runtime.get("reportDate", "") or "")
        super().__init__(f"today_analysis already running for {report_date} ({run_id})")


def acquire_today_lock(paths: OrchestratorPaths, run_id: str, *, pid: int | None = None) -> None:
    if paths.lock.exists():
        payload = load_json(paths.lock)
        if isinstance(payload, dict):
            lock_pid = payload.get("pid")
            if process_exists(lock_pid):
                raise AlreadyRunningError(
                    {
                        "runId": str(payload.get("runId", "") or ""),
                        "reportDate": str(payload.get("reportDate", "") or ""),
                        "startedAt": str(payload.get("startedAt", "") or ""),
                        "currentStep": str(payload.get("currentStep", "") or ""),
                        "currentAgent": str(payload.get("currentAgent", "") or ""),
                        "status": "running",
                        "pid": lock_pid,
                    }
                )
    dump_json(
        paths.lock,
        {
            "runId": run_id,
            "reportDate": paths.workspace.name,
            "pid": pid or os.getpid(),
            "startedAt": timestamp_now(),
            "currentStep": "preflight",
            "currentAgent": "",
        },
    )


def release_today_lock(paths: OrchestratorPaths) -> None:
    try:
        if paths.lock.exists():
            paths.lock.unlink()
    except OSError:
        pass


def _elapsed_seconds(started_at_text: str) -> int:
    try:
        started_at = datetime.fromisoformat(started_at_text)
        return max(0, int((datetime.fromisoformat(timestamp_now()) - started_at).total_seconds()))
    except ValueError:
        return 0


def _decision_state(agent_home: Path, report_date: str) -> dict:
    aggregate_path = agent_home / "db" / "agent_outputs" / report_date / "aggregate.json"
    aggregate = load_json(aggregate_path) if aggregate_path.exists() else {}
    bundle_path = committee_decision_bundle_path(agent_home, report_date)
    bundle = load_json(bundle_path) if bundle_path.exists() else {}
    validated_path = validated_advice_path(agent_home, report_date)
    validated = load_json(validated_path) if validated_path.exists() else {}

    degraded_agents = list(aggregate.get("degraded_agent_names", []) or [])
    failed_agents = list(aggregate.get("failed_agents", []) or [])
    failed_agent_names = list(aggregate.get("failed_agent_names", []) or [])
    degradation_mode = str(
        bundle.get("degradation_mode")
        or aggregate.get("degradation_mode")
        or validated.get("degradation_mode")
        or ""
    )
    decision_mode = str(bundle.get("decision_mode") or validated.get("decision_mode") or "")
    execution_eligible_values = [
        aggregate.get("execution_eligible"),
        bundle.get("execution_eligible"),
        validated.get("execution_eligible"),
    ]
    execution_eligible = all(value is not False for value in execution_eligible_values)
    committee_ready = bool(aggregate.get("committee_ready", bool(bundle)))
    is_degraded = (
        bool(degraded_agents)
        or bool(failed_agents)
        or bool(failed_agent_names)
        or degradation_mode not in {"", "none", "ok"}
        or decision_mode in {"hold_only", "degraded", "fallback"}
        or not execution_eligible
        or not committee_ready
    )
    status = RUNTIME_STATUS["degraded"] if is_degraded else RUNTIME_STATUS["ok"]
    return {
        "status": status,
        "is_degraded": is_degraded,
        "degradation_mode": degradation_mode,
        "decision_mode": decision_mode,
        "execution_eligible": execution_eligible,
        "committee_ready": committee_ready,
        "degraded_agents": degraded_agents,
        "failed_agents": failed_agents,
        "failed_agent_names": failed_agent_names,
    }


def _today_analysis_payload(agent_home: Path, report_date: str, run_meta: dict, memory_cycle: dict) -> dict:
    context = load_json(llm_context_path(agent_home, report_date)) if llm_context_path(agent_home, report_date).exists() else {}
    validated = load_json(validated_advice_path(agent_home, report_date)) if validated_advice_path(agent_home, report_date).exists() else {}
    committee = load_json(committee_advice_path(agent_home, report_date)) if committee_advice_path(agent_home, report_date).exists() else {}
    decision_state = _decision_state(agent_home, report_date)
    return {
        "analysis_run_id": run_meta["analysis_run_id"],
        "analysis_date": report_date,
        "generated_at": timestamp_now(),
        "trigger": run_meta["trigger"],
        "started_at_shanghai": run_meta["started_at_shanghai"],
        "analysis_quality": run_meta["analysis_quality"],
        "memory_eligible": run_meta["memory_eligible"],
        "market_close_time": run_meta["market_close_time"],
        "portfolio_summary": context.get("portfolio_summary", {}) or {},
        "market_view": validated.get("market_view", {}) or {},
        "cross_fund_observations": validated.get("cross_fund_observations", []) or [],
        "committee": committee or validated.get("committee", {}) or {},
        "memory_digest": context.get("memory_digest", {}) or {},
        "memory_cycle": memory_cycle,
        "validated_available": bool(validated),
        "context_available": bool(context),
        "decision_state": decision_state,
        "degradation_mode": decision_state["degradation_mode"],
        "decision_mode": decision_state["decision_mode"],
        "execution_eligible": decision_state["execution_eligible"],
        "committee_ready": decision_state["committee_ready"],
    }


def _today_decision_payload(agent_home: Path, report_date: str, run_meta: dict, analysis: dict) -> dict:
    validated = load_json(validated_advice_path(agent_home, report_date)) if validated_advice_path(agent_home, report_date).exists() else {}
    aggregate_path = agent_home / "db" / "agent_outputs" / report_date / "aggregate.json"
    aggregate = load_json(aggregate_path) if aggregate_path.exists() else {}
    tactical = list(validated.get("tactical_actions", []) or [])
    dca = list(validated.get("dca_actions", []) or [])
    holds = list(validated.get("hold_actions", []) or [])
    actionable = tactical + dca
    primary = actionable[0] if actionable else {}
    decision_state = _decision_state(agent_home, report_date)
    return {
        "analysis_run_id": run_meta["analysis_run_id"],
        "analysis_date": report_date,
        "generated_at": timestamp_now(),
        "trigger": run_meta["trigger"],
        "started_at_shanghai": run_meta["started_at_shanghai"],
        "analysis_quality": run_meta["analysis_quality"],
        "memory_eligible": run_meta["memory_eligible"],
        "market_close_time": run_meta["market_close_time"],
        "summary": (
            f"Today analysis completed. Actionable items={len(actionable)}, hold items={len(holds)}, "
            f"analysis_quality={run_meta['analysis_quality']}."
        ),
        "primary_action": primary,
        "market_judgement": validated.get("market_view", {}) or {},
        "committee": validated.get("committee", {}) or aggregate.get("committee", {}) or {},
        "prohibited_actions": analysis.get("memory_digest", {}).get("execution_memory_hits", []),
        "allowed_with_conditions": analysis.get("memory_digest", {}).get("strategic_memory_hits", []),
        "decision_state": decision_state,
        "degradation_mode": decision_state["degradation_mode"],
        "decision_mode": decision_state["decision_mode"],
        "execution_eligible": decision_state["execution_eligible"],
        "committee_ready": decision_state["committee_ready"],
        "degradedAgents": decision_state["degraded_agents"],
    }


def _brief_text(report_date: str, decision: dict, analysis: dict) -> str:
    lines = [
        f"# Today Analysis Brief - {report_date}",
        "",
        f"- analysis_run_id: {decision.get('analysis_run_id', '')}",
        f"- generated_at: {decision.get('generated_at', '')}",
        f"- trigger: {decision.get('trigger', '')}",
        f"- started_at_shanghai: {decision.get('started_at_shanghai', '')}",
        f"- analysis_quality: {decision.get('analysis_quality', '')}",
        f"- memory_eligible: {decision.get('memory_eligible', False)}",
        "",
        "## Today",
        decision.get("summary", ""),
        "",
        "## Market",
        str((decision.get("market_judgement", {}) or {}).get("summary", "") or "No market summary."),
        "",
        "## Cross Fund Observations",
    ]
    observations = analysis.get("cross_fund_observations", []) or []
    lines.extend([f"- {item}" for item in observations[:8]] or ["- None"])
    return "\n".join(lines) + "\n"


def _read_today_meta(agent_home: Path, report_date: str) -> dict:
    path = _paths(agent_home, report_date).meta
    return load_json(path) if path.exists() else {}


def _read_memory_cycle(agent_home: Path, report_date: str) -> dict:
    path = _paths(agent_home, report_date).workspace / "memory_cycle.json"
    return load_json(path) if path.exists() else {}


def _needs_after_close_rerun(agent_home: Path, report_date: str) -> bool:
    meta = _read_today_meta(agent_home, report_date)
    if not meta:
        return True
    cycle = _read_memory_cycle(agent_home, report_date)
    cycle_status = str(cycle.get("status", "") or "")
    return (
        str(meta.get("analysis_quality", "")) != "after_close"
        or not bool(meta.get("memory_eligible", False))
        or cycle_status not in {"ok", "skipped"}
    )


def pending_backfill_dates(agent_home: Path, report_date: str, started_at: datetime) -> list[str]:
    if report_date != today_shanghai(started_at):
        return []
    if not is_trading_day(agent_home, report_date):
        return []
    try:
        report_day = datetime.strptime(report_date, "%Y-%m-%d").date()
    except ValueError:
        return []
    window_start = (report_day - timedelta(days=MAX_AUTO_BACKFILL_CALENDAR_DAYS + 1)).isoformat()
    candidates = [day for day in trading_days_between(agent_home, window_start, report_date) if day < report_date]
    return [day for day in candidates if _needs_after_close_rerun(agent_home, day)]


def _run_memory_cycle(agent_home: Path, report_date: str, *, allow_fail: bool, llm_mock: bool) -> dict:
    args = ["--date", report_date]
    if llm_mock:
        args.append("--mock")
    payload = _run_script(agent_home, "run_long_memory_analysis.py", *args, allow_fail=allow_fail)
    stdout = str(payload.get("stdout", "") or "").strip()
    if stdout:
        last_line = stdout.splitlines()[-1].strip()
        try:
            parsed = json.loads(last_line)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {"status": "ok" if payload.get("returncode", 1) == 0 else "retryable_failure", "runner": payload}


def run_today_analysis(
    agent_home: Path,
    report_date: str,
    *,
    trigger: str,
    demo: bool,
    force: bool,
    llm_mock: bool,
    started_at: datetime | None = None,
    resume_existing: bool = False,
) -> Path:
    ensure_layout(agent_home)
    started = started_at or shanghai_now()
    paths = _paths(agent_home, report_date)
    paths.workspace.mkdir(parents=True, exist_ok=True)
    active_runtime = get_active_runtime(agent_home, report_date)
    if active_runtime:
        raise AlreadyRunningError(active_runtime)
    run_meta = {
        "analysis_run_id": str(uuid.uuid4()),
        "task": "today_analysis",
        "trigger": trigger,
        "runAt": started.astimezone().isoformat(timespec="seconds"),
        "started_at_shanghai": started.astimezone().isoformat(timespec="seconds"),
        "market_close_time": market_close_time().strftime("%H:%M"),
        "analysis_quality": analysis_quality_for_start(agent_home, report_date, started),
    }
    run_meta["memory_eligible"] = bool(run_meta["analysis_quality"] == "after_close")
    runtime = {
        "status": RUNTIME_STATUS["running"],
        "phase": "startup",
        "runId": run_meta["analysis_run_id"],
        "pid": os.getpid(),
        "reportDate": report_date,
        "startedAt": run_meta["started_at_shanghai"],
        "endedAt": "",
        "heartbeatAt": run_meta["started_at_shanghai"],
        "elapsedSeconds": 0,
        "currentStep": "preflight",
        "currentAgent": "",
        "currentAgentStage": "",
        "runningAgents": [],
        "failedAgents": [],
        "degradedAgents": [],
        "lastError": "",
        "resultReady": False,
        "resultRunId": "",
        "analysisQuality": run_meta["analysis_quality"],
        "memoryEligible": run_meta["memory_eligible"],
    }
    acquire_today_lock(paths, run_meta["analysis_run_id"], pid=runtime["pid"])
    try:
        _write_runtime(agent_home, report_date, runtime)
        if paths.decision.exists() and not force:
            existing = load_json(paths.decision)
            cycle_status = str(_read_memory_cycle(agent_home, report_date).get("status", "") or "")
            if existing and (existing.get("memory_eligible") or run_meta["analysis_quality"] == "pre_close") and cycle_status in {"ok", "skipped"}:
                runtime.update(
                    {
                        "status": RUNTIME_STATUS["ok"],
                        "phase": "completed",
                        "currentStep": "",
                        "endedAt": timestamp_now(),
                        "resultReady": True,
                        "resultRunId": run_meta["analysis_run_id"],
                    }
                )
                _write_runtime(agent_home, report_date, runtime)
                return paths.decision

        from preflight_check import perform_preflight

        preflight = perform_preflight(agent_home, scope="desktop", probe_llm=not demo and not llm_mock)
        dump_json(paths.workspace / "preflight.json", preflight)

        runtime.update({"phase": "execution_sync", "currentStep": "update_pending_confirmations", "elapsedSeconds": _elapsed_seconds(run_meta["started_at_shanghai"])})
        _write_runtime(agent_home, report_date, runtime)
        confirmation_updates = update_pending_confirmations(agent_home, report_date)
        execution_sync = build_execution_sync_payload(agent_home)
        dump_json(paths.workspace / "execution_sync.json", {"confirmation_updates": confirmation_updates, "execution_sync": execution_sync})

        runtime.update({"phase": "today_analysis", "currentStep": "run_daily_pipeline", "elapsedSeconds": _elapsed_seconds(run_meta["started_at_shanghai"])})
        _write_runtime(agent_home, report_date, runtime)
        sync_args = ["--date", report_date, "--mode", "intraday"]
        if resume_existing:
            sync_args.append("--resume-existing")
        if demo:
            sync_args.append("--demo")
        if llm_mock or demo:
            sync_args.append("--llm-mock")
        sync_state = _run_script(agent_home, "run_daily_pipeline.py", *sync_args, allow_fail=demo)
        dump_json(paths.workspace / "sync_state.json", sync_state)
        aggregate_path = agent_home / "db" / "agent_outputs" / report_date / "aggregate.json"
        if aggregate_path.exists():
            aggregate = load_json(aggregate_path)
            workflow_trace = aggregate.get("workflow_trace", {}) or {}
            running = [name for name, item in workflow_trace.items() if str(item.get("status", "")).lower() == "running"]
            latest_agent = max(
                ((name, item) for name, item in workflow_trace.items() if item.get("started_at")),
                key=lambda pair: str(pair[1].get("started_at", "")),
                default=(None, {}),
            )
            failed_agents = aggregate.get("failed_agents", []) or []
            degraded_agents = aggregate.get("degraded_agent_names", []) or []
            runtime.update(
                {
                    "phase": "agent_research",
                    "currentStep": "multiagent_research",
                    "currentAgent": latest_agent[0] or "",
                    "currentAgentStage": str((latest_agent[1] or {}).get("stage", "") or ""),
                    "runningAgents": running,
                    "failedAgents": failed_agents,
                    "degradedAgents": degraded_agents,
                    "elapsedSeconds": _elapsed_seconds(run_meta["started_at_shanghai"]),
                    "lastError": str(failed_agents[-1].get("error", "") if failed_agents else runtime.get("lastError", "")),
                }
            )
            _write_runtime(agent_home, report_date, runtime)
        dump_json(paths.meta, run_meta)

        memory_cycle = {"status": "skipped", "reason": "pre_close"}
        if run_meta["memory_eligible"]:
            try:
                runtime.update({"phase": "long_memory", "currentStep": "run_long_memory_analysis", "elapsedSeconds": _elapsed_seconds(run_meta["started_at_shanghai"])})
                _write_runtime(agent_home, report_date, runtime)
                memory_cycle = _run_memory_cycle(agent_home, report_date, allow_fail=demo, llm_mock=llm_mock or demo)
            except Exception as exc:
                memory_cycle = {
                    "report_date": report_date,
                    "generated_at": timestamp_now(),
                    "status": RUNTIME_STATUS["retryable_failure"],
                    "error": str(exc),
                }
                runtime.update({"lastError": str(exc)})
        dump_json(paths.workspace / "memory_cycle.json", memory_cycle)
        dump_json(paths.workspace / "memory_updates.json", memory_cycle)

        analysis = _today_analysis_payload(agent_home, report_date, run_meta, memory_cycle)
        dump_json(paths.analysis, analysis)
        decision = _today_decision_payload(agent_home, report_date, run_meta, analysis)
        dump_json(paths.decision, decision)
        dump_json(paths.summary, {"analysis": analysis, "decision": decision})
        brief = _brief_text(report_date, decision, analysis)
        paths.brief.write_text(brief, encoding="utf-8")
        (agent_home / "reports" / "daily" / f"{report_date}_daily_brief.md").write_text(brief, encoding="utf-8")
        decision_state = decision.get("decision_state", {}) or _decision_state(agent_home, report_date)
        failed_agents = list(decision_state.get("failed_agents", []) or [])
        memory_failed_agents = memory_cycle.get("failedAgents", []) if isinstance(memory_cycle, dict) else []
        if memory_failed_agents:
            failed_agents.extend(memory_failed_agents)
        runtime.update(
            {
                "status": str(decision_state.get("status") or RUNTIME_STATUS["ok"]),
                "phase": "completed",
                "currentStep": "",
                "currentAgent": "",
                "currentAgentStage": "",
                "runningAgents": [],
                "failedAgents": failed_agents,
                "degradedAgents": list(decision_state.get("degraded_agents", []) or []),
                "degradationMode": str(decision_state.get("degradation_mode", "") or ""),
                "decisionMode": str(decision_state.get("decision_mode", "") or ""),
                "executionEligible": bool(decision_state.get("execution_eligible", True)),
                "committeeReady": bool(decision_state.get("committee_ready", False)),
                "elapsedSeconds": _elapsed_seconds(run_meta["started_at_shanghai"]),
                "endedAt": timestamp_now(),
                "resultReady": True,
                "resultRunId": run_meta["analysis_run_id"],
            }
        )
        _write_runtime(agent_home, report_date, runtime)
        return paths.decision
    except Exception as exc:
        runtime.update(
            {
                "status": RUNTIME_STATUS["retryable_failure"],
                "phase": "failed",
                "currentStep": "",
                "currentAgent": "",
                "currentAgentStage": "",
                "runningAgents": [],
                "elapsedSeconds": _elapsed_seconds(run_meta["started_at_shanghai"]),
                "endedAt": timestamp_now(),
                "resultReady": False,
                "lastError": str(exc),
            }
        )
        _write_runtime(agent_home, report_date, runtime)
        raise
    finally:
        release_today_lock(paths)
