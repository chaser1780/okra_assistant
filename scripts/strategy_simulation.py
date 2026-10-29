from __future__ import annotations

import copy
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from common import dump_json, file_lock, load_json, load_portfolio, lock_path, resolve_date, timestamp_now
from update_portfolio_from_trade import apply_trade


TRACK_ID = "strategy_simulation"
EXPERIMENT_STATUSES = {"active", "paused", "archived"}
ACTION_TYPES = {"buy", "sell", "switch_in", "switch_out"}


def experiment_dir(agent_home: Path) -> Path:
    return agent_home / "db" / "strategy_simulation" / "experiments"


def experiment_path(agent_home: Path, experiment_id: str) -> Path:
    return experiment_dir(agent_home) / f"{_safe_id(experiment_id)}.json"


def list_experiments(agent_home: Path, *, limit: int = 40) -> list[dict[str, Any]]:
    base = experiment_dir(agent_home)
    if not base.exists():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        payload = _read(path)
        if payload:
            result.append(_summary(agent_home, payload, path))
    return result


def list_fund_experiment_results(agent_home: Path, fund_code: str, *, limit: int = 12) -> list[dict[str, Any]]:
    """Return read-only strategy-experiment results relevant to one fund."""
    code = str(fund_code or "").strip()
    if not code:
        return []
    base = experiment_dir(agent_home)
    if not base.exists():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        payload = _read(path)
        if not payload:
            continue
        actions = [
            item
            for item in payload.get("actions", []) or []
            if isinstance(item, dict) and str(item.get("fundCode") or "") == code
        ]
        if not actions:
            continue
        summary = _summary(agent_home, payload, path)
        fund = next(
            (
                item
                for item in (payload.get("portfolio", {}) or {}).get("funds", []) or []
                if isinstance(item, dict) and str(item.get("fund_code") or item.get("code") or "") == code
            ),
            {},
        )
        results.append(
            {
                **summary,
                "fundCode": code,
                "affectsFormalPortfolio": False,
                "actions": [
                    {
                        "action": str(item.get("action") or ""),
                        "amount": _optional_number(item.get("amount")),
                        "asOfDate": str(item.get("asOfDate") or ""),
                        "simulationStatus": str(item.get("simulationStatus") or "simulated"),
                    }
                    for item in actions[-6:]
                ],
                "fundValue": _optional_number(fund.get("current_value")),
                "fundHoldingPnl": _optional_number(fund.get("holding_pnl")),
                "fundHoldingUnits": _optional_number(fund.get("holding_units")),
            }
        )
        if len(results) >= limit:
            break
    return results


def create_experiment(agent_home: Path, payload: dict[str, Any]) -> dict[str, Any]:
    with file_lock(lock_path(agent_home, "strategy_simulation")):
        experiment_id = _safe_id(str(payload.get("experimentId") or payload.get("experiment_id") or f"experiment_{uuid.uuid4().hex[:12]}"))
        path = experiment_path(agent_home, experiment_id)
        if path.exists():
            existing = _read(path)
            if existing:
                return {"ok": True, "experiment": existing, "idempotentReplay": True}
        label = str(payload.get("label") or payload.get("name") or experiment_id).strip()
        if not label:
            raise ValueError("label is required")
        initial_portfolio = copy.deepcopy(payload.get("initialPortfolio") or payload.get("initial_portfolio") or load_portfolio(agent_home))
        if not isinstance(initial_portfolio, dict) or not isinstance(initial_portfolio.get("funds"), list):
            raise ValueError("initial portfolio must contain funds")
        report_date = resolve_date(str(payload.get("asOfDate") or payload.get("as_of_date") or initial_portfolio.get("as_of_date") or "") or None)
        now = timestamp_now()
        experiment = {
            "schemaVersion": "strategy_simulation.v1",
            "experimentId": experiment_id,
            "track": TRACK_ID,
            "experimental": True,
            "affectsFormalPortfolio": False,
            "label": label,
            "status": "active",
            "asOfDate": report_date,
            "createdAt": now,
            "updatedAt": now,
            "sourceSnapshotHash": _stable_hash(initial_portfolio),
            "initialPortfolio": initial_portfolio,
            "portfolio": copy.deepcopy(initial_portfolio),
            "actions": [],
            "notes": str(payload.get("note") or ""),
        }
        dump_json(path, experiment)
        return {"ok": True, "experiment": experiment, "idempotentReplay": False}


def record_action(agent_home: Path, payload: dict[str, Any]) -> dict[str, Any]:
    with file_lock(lock_path(agent_home, "strategy_simulation")):
        experiment_id = _safe_id(str(payload.get("experimentId") or payload.get("experiment_id") or ""))
        if not experiment_id:
            raise ValueError("experimentId is required")
        path = experiment_path(agent_home, experiment_id)
        experiment = _read(path)
        if not experiment:
            raise ValueError("strategy simulation experiment was not found")
        if experiment.get("status") != "active":
            raise ValueError("strategy simulation experiment is not active")
        action = str(payload.get("action") or "").strip().lower()
        if action not in ACTION_TYPES:
            raise ValueError("action must be buy, sell, switch_in, or switch_out")
        fund_code = str(payload.get("fundCode") or payload.get("fund_code") or "").strip()
        if not fund_code:
            raise ValueError("fundCode is required")
        amount = _positive_money(payload.get("amount"))
        action_id = _safe_id(str(payload.get("actionId") or payload.get("action_id") or f"action_{uuid.uuid4().hex[:12]}"))
        record = {
            "actionId": action_id,
            "track": TRACK_ID,
            "simulationStatus": "simulated",
            "action": action,
            "fundCode": fund_code,
            "amount": amount,
            "tradeNav": _optional_number(payload.get("tradeNav") or payload.get("trade_nav")),
            "units": _optional_number(payload.get("units")),
            "asOfDate": resolve_date(str(payload.get("asOfDate") or payload.get("as_of_date") or experiment.get("asOfDate") or "") or None),
            "note": str(payload.get("note") or ""),
        }
        existing = next((item for item in experiment.get("actions", []) or [] if item.get("actionId") == action_id), None)
        if existing:
            if _action_identity(existing) != _action_identity(record):
                raise ValueError("actionId already exists with a different strategy simulation action")
            return {"ok": True, "experiment": experiment, "action": existing, "idempotentReplay": True}
        portfolio = copy.deepcopy(experiment.get("portfolio") or {})
        updated = apply_trade(portfolio, fund_code, action, amount, trade_nav=record["tradeNav"], trade_units=record["units"])
        updated["as_of_date"] = record["asOfDate"]
        # Accumulate signed external investment so valueDelta can be reported as RETURN
        # excluding principal (buy adds net assets funded from outside; not PnL).
        flow = _optional_number(updated.get("external_cashflow")) or 0.0
        updated["net_external_flow"] = round(float(updated.get("net_external_flow") or 0.0) + flow, 2)
        record["externalCashflow"] = flow
        record["createdAt"] = timestamp_now()
        record["portfolioHashAfter"] = _stable_hash(updated)
        experiment["portfolio"] = updated
        experiment.setdefault("actions", []).append(record)
        experiment["asOfDate"] = record["asOfDate"]
        experiment["updatedAt"] = timestamp_now()
        dump_json(path, experiment)
        return {"ok": True, "experiment": experiment, "action": record, "idempotentReplay": False}


def _summary(agent_home: Path, payload: dict[str, Any], path: Path) -> dict[str, Any]:
    portfolio = payload.get("portfolio", {}) if isinstance(payload.get("portfolio"), dict) else {}
    initial_portfolio = payload.get("initialPortfolio", {}) if isinstance(payload.get("initialPortfolio"), dict) else {}
    total_value = _optional_number(portfolio.get("total_value"))
    initial_total_value = _optional_number(initial_portfolio.get("total_value"))
    net_external_flow = _optional_number(portfolio.get("net_external_flow")) or 0.0
    actions = [item for item in payload.get("actions", []) or [] if isinstance(item, dict)]
    action_counts: dict[str, int] = {}
    for action in actions:
        name = str(action.get("action") or "unknown")
        action_counts[name] = action_counts.get(name, 0) + 1
    return {
        "experimentId": str(payload.get("experimentId") or path.stem),
        "label": str(payload.get("label") or path.stem),
        "status": str(payload.get("status") or "active"),
        "asOfDate": str(payload.get("asOfDate") or ""),
        "createdAt": str(payload.get("createdAt") or ""),
        "updatedAt": str(payload.get("updatedAt") or ""),
        "actionCount": len(actions),
        "actionCounts": action_counts,
        "totalValue": total_value,
        "initialTotalValue": initial_total_value,
        "netExternalFlow": net_external_flow,
        # return excluding external principal deposits/withdrawals
        "valueDelta": round(total_value - initial_total_value - net_external_flow, 2) if total_value is not None and initial_total_value is not None else None,
        "holdingPnl": portfolio.get("holding_pnl"),
        "sourcePath": str(path.relative_to(agent_home)).replace("\\", "/"),
    }


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(value or "").strip())[:80]


def _positive_money(value: Any) -> float:
    try:
        parsed = round(float(value), 2)
    except (TypeError, ValueError):
        parsed = 0.0
    if parsed <= 0:
        raise ValueError("amount must be greater than 0")
    return parsed


def _optional_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("tradeNav and units must be numeric") from exc


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _action_identity(item: dict[str, Any]) -> str:
    return _stable_hash(
        {
            key: item.get(key)
            for key in ("actionId", "track", "simulationStatus", "action", "fundCode", "amount", "tradeNav", "units", "asOfDate", "note")
        }
    )
