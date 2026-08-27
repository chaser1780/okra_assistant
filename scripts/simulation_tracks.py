from __future__ import annotations

from pathlib import Path
from typing import Any

from common import actual_trade_dir, load_json, load_portfolio, timestamp_now


USER_SIMULATION_TRACK = "user_simulation"
STRATEGY_SIMULATION_TRACK = "strategy_simulation"
SIMULATION_STATUSES = {"planned", "simulated", "confirmed", "cancelled"}


def strategy_experiment_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "strategy_simulation" / "experiments"


def build_simulation_payload(agent_home: Path, *, portfolio: dict[str, Any] | None = None) -> dict[str, Any]:
    portfolio = portfolio if portfolio is not None else load_portfolio(agent_home)
    trades = _user_simulation_trades(agent_home)
    statuses = _counts(_simulation_status(item) for item in trades)
    experiments = _strategy_experiments(agent_home)
    as_of_date = str(portfolio.get("as_of_date") or "")
    user_summary = {
        "trackId": USER_SIMULATION_TRACK,
        "label": "用户模拟组合",
        "description": "只根据用户调仓和已配置的模拟定投更新。",
        "formalTrack": True,
        "affectsFormalPortfolio": True,
        "executionMode": "manual_and_configured_dca",
        "asOfDate": as_of_date,
        "positionCount": len(portfolio.get("funds", []) or portfolio.get("holdings", []) or []),
        "operationCounts": statuses,
        "recordSource": "execution_sync",
    }
    strategy_summary = {
        "trackId": STRATEGY_SIMULATION_TRACK,
        "label": "策略实验",
        "description": "自由执行的策略验证，不会改写用户模拟组合。",
        "formalTrack": False,
        "affectsFormalPortfolio": False,
        "executionMode": "experimental",
        "experimentCount": len(experiments),
        "activeExperimentCount": sum(1 for item in experiments if item.get("status") in {"active", "running", "ready"}),
        "experiments": experiments[:12],
        "recordSource": "strategy_simulation",
    }
    return {
        "activeTrack": USER_SIMULATION_TRACK,
        "formalTrack": USER_SIMULATION_TRACK,
        "simulationOnly": True,
        "updatedAt": timestamp_now(),
        "tracks": [user_summary, strategy_summary],
        "userSimulation": user_summary,
        "strategySimulation": strategy_summary,
    }


def simulation_fields(payload: dict[str, Any]) -> dict[str, Any]:
    track = str(payload.get("simulation_track") or payload.get("simulationTrack") or USER_SIMULATION_TRACK)
    if track not in {USER_SIMULATION_TRACK, STRATEGY_SIMULATION_TRACK}:
        raise ValueError(f"Unsupported simulation track: {track}")
    status = str(payload.get("simulation_status") or payload.get("simulationStatus") or "").lower()
    if not status:
        status = _simulation_status(payload)
    if status not in SIMULATION_STATUSES:
        raise ValueError(f"Unsupported simulation status: {status}")
    explicit_simulation = bool(payload.get("is_simulation")) or any(
        key in payload for key in ("simulation_track", "simulationTrack", "simulation_status", "simulationStatus")
    )
    return {
        "simulation_track": track,
        "simulation_status": status,
        "is_simulation": explicit_simulation,
    }


def user_simulation_fields(payload: dict[str, Any], *, default_status: str = "planned") -> dict[str, Any]:
    """Normalize desktop execution input to the only formal, local simulation track.

    The desktop API must never infer a broker/real-trade operation from legacy
    request fields. Missing simulation fields become a planned simulation; a
    legacy completion status is reduced to its equivalent simulation state.
    """
    requested_track = str(payload.get("simulation_track") or payload.get("simulationTrack") or USER_SIMULATION_TRACK)
    if requested_track != USER_SIMULATION_TRACK:
        raise ValueError("The simulation execution endpoint only records the user_simulation track.")
    requested_status = str(payload.get("simulation_status") or payload.get("simulationStatus") or "").lower()
    if not requested_status:
        requested_status = _simulation_status(payload)
        if requested_status == "planned" and not str(payload.get("status") or "").strip():
            requested_status = default_status
    if requested_status not in SIMULATION_STATUSES:
        raise ValueError(f"Unsupported simulation status: {requested_status}")
    return {
        "simulation_track": USER_SIMULATION_TRACK,
        "simulation_status": requested_status,
        "is_simulation": True,
    }


def _user_simulation_trades(agent_home: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    base = actual_trade_dir(agent_home)
    if not base.exists():
        return result
    for path in sorted(base.glob("*.json"), reverse=True):
        payload = load_json(path)
        for item in payload.get("items", []) or []:
            if str(item.get("simulation_track") or USER_SIMULATION_TRACK) == USER_SIMULATION_TRACK:
                result.append(item)
    return result


def _strategy_experiments(agent_home: Path) -> list[dict[str, Any]]:
    from strategy_simulation import list_experiments

    return list_experiments(agent_home)


def _simulation_status(item: dict[str, Any]) -> str:
    status = str(item.get("simulation_status") or item.get("status") or "").lower()
    if status in {"canceled", "cancelled", "failed"}:
        return "cancelled"
    if status in {"confirmed", "settled", "executed"}:
        return "confirmed"
    if status == "simulated":
        return "simulated"
    return "planned"


def _counts(values) -> dict[str, int]:
    result = {status: 0 for status in sorted(SIMULATION_STATUSES)}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result
