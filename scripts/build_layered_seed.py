from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from common import dump_json, load_json, llm_context_path, score_path, timestamp_now
from portfolio_exposure import infer_strategy_bucket


ACTION_SECTIONS = ("tactical_actions", "dca_actions", "hold_actions")
NATIVE_SEED_SCHEMA_VERSION = "native_action_seed.v1"


def native_action_seed_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "action_seed" / f"{report_date}.json"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def source_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _context_by_code(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("fund_code", "") or ""): item
        for item in context.get("funds", []) or []
        if isinstance(item, dict) and item.get("fund_code")
    }


def _score_by_code(score_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("code", item.get("fund_code", "")) or ""): item
        for item in score_payload.get("funds", []) or []
        if isinstance(item, dict) and (item.get("code") or item.get("fund_code"))
    }


def _strategy_thresholds(strategy: dict[str, Any]) -> dict[str, float]:
    tactical = strategy.get("tactical", {}) or {}
    return {
        "add": safe_float(tactical.get("strong_add_score"), 70.0),
        "reduce": safe_float(tactical.get("trim_score"), 38.0),
        "switch_out": safe_float(tactical.get("switch_out_score"), 28.0),
        "min_add": safe_float(tactical.get("min_add_amount"), 100.0),
        "mid_add": safe_float(tactical.get("mid_add_amount"), 200.0),
        "max_add": safe_float(tactical.get("max_add_amount"), 300.0),
        "min_reduce": safe_float(tactical.get("min_reduce_amount"), 100.0),
        "mid_reduce": safe_float(tactical.get("mid_reduce_amount"), 200.0),
        "max_reduce": safe_float(tactical.get("max_reduce_amount"), 300.0),
    }


def _score_action(score_item: dict[str, Any], thresholds: dict[str, float]) -> str:
    action = str(score_item.get("action", "") or "").strip()
    score = safe_float(score_item.get("score"), 50.0)
    if action in {"add", "reduce", "switch_out"}:
        return action
    if action == "avoid" or score <= thresholds["switch_out"]:
        return "switch_out"
    if score >= thresholds["add"]:
        return "add"
    if score <= thresholds["reduce"]:
        return "reduce"
    return "hold"


def _amount_for(action: str, fund: dict[str, Any], score_item: dict[str, Any], thresholds: dict[str, float]) -> float:
    current_value = safe_float(fund.get("current_value"))
    cap_value = safe_float(fund.get("cap_value"), 1000.0)
    score = safe_float(score_item.get("score"), 50.0)
    if action == "add":
        room = max(0.0, cap_value - current_value)
        if room < 100.0:
            return 0.0
        base = thresholds["max_add"] if score >= 82.0 else thresholds["mid_add"] if score >= thresholds["add"] else thresholds["min_add"]
        return min(base, room)
    if action in {"reduce", "switch_out"}:
        if current_value < 100.0:
            return 0.0
        if action == "switch_out":
            return min(max(thresholds["mid_reduce"], thresholds["min_reduce"]), current_value)
        return min(thresholds["mid_reduce"], current_value)
    return 0.0


def _confidence(score_item: dict[str, Any], action: str) -> float:
    base = safe_float(score_item.get("confidence"), 0.55)
    score = safe_float(score_item.get("score"), 50.0)
    distance = min(abs(score - 50.0) / 50.0, 1.0)
    if action == "hold":
        return round(max(0.35, min(0.7, base - 0.05)), 4)
    return round(max(0.45, min(0.92, base + distance * 0.12)), 4)


def _thesis(fund: dict[str, Any], score_item: dict[str, Any], action: str) -> str:
    name = str(fund.get("fund_name", fund.get("name", fund.get("fund_code", ""))) or "")
    reasons = [str(item) for item in score_item.get("reasons", []) or [] if str(item).strip()]
    if not reasons:
        reasons = [f"score={safe_float(score_item.get('score'), 50.0):.1f}", f"role={fund.get('role', '')}"]
    if action == "add":
        prefix = "Native chain proposes a small add"
    elif action in {"reduce", "switch_out"}:
        prefix = "Native chain proposes risk reduction"
    elif action == "scheduled_dca":
        prefix = "Native chain preserves scheduled DCA"
    else:
        prefix = "Native chain keeps watch"
    return f"{prefix} for {name}: " + "; ".join(reasons[:4])


def _evidence(score_item: dict[str, Any], context_item: dict[str, Any]) -> list[str]:
    evidence = [str(item) for item in score_item.get("reasons", []) or [] if str(item).strip()]
    proxy = context_item.get("intraday_proxy", {}) if isinstance(context_item.get("intraday_proxy"), dict) else {}
    quote = context_item.get("quote", {}) if isinstance(context_item.get("quote"), dict) else {}
    estimate = context_item.get("estimated_nav", {}) if isinstance(context_item.get("estimated_nav"), dict) else {}
    if proxy:
        evidence.append(f"intraday_proxy_change={proxy.get('change_pct', '')}")
    if quote:
        evidence.append(f"official_nav_change={quote.get('day_change_pct', '')}")
    if estimate:
        evidence.append(f"estimated_nav_change={estimate.get('estimate_change_pct', '')}")
    return evidence[:8]


def _risks(score_item: dict[str, Any], context_item: dict[str, Any]) -> list[str]:
    risks = [str(item) for item in score_item.get("risk_flags", []) or [] if str(item).strip()]
    recent_news = context_item.get("recent_news", []) if isinstance(context_item.get("recent_news"), list) else []
    for item in recent_news[:3]:
        if isinstance(item, dict) and str(item.get("impact", "") or "") == "negative":
            risks.append(str(item.get("title", "") or item.get("summary", "") or "negative news"))
    return risks[:8]


def _seed_action(
    *,
    report_date: str,
    fund: dict[str, Any],
    context_item: dict[str, Any],
    score_item: dict[str, Any],
    action: str,
    amount: float,
    priority: int,
    seed_relative_path: str,
) -> dict[str, Any]:
    code = str(fund.get("fund_code", fund.get("code", "")) or "")
    return {
        "suggestion_id": f"{report_date}:{code}:{action}:native",
        "fund_code": code,
        "fund_name": str(fund.get("fund_name", fund.get("name", code)) or code),
        "strategy_bucket": infer_strategy_bucket(fund),
        "validated_action": action,
        "validated_amount": amount,
        "model_action": action,
        "requested_amount": amount,
        "priority": priority,
        "confidence": _confidence(score_item, action),
        "thesis": _thesis(fund, score_item, action),
        "evidence": _evidence(score_item, context_item),
        "risks": _risks(score_item, context_item),
        "agent_support": ["native_action_seed", "layered_retrieval_pack", "action_debate"],
        "source_signal_ids": [],
        "opposing_signal_ids": [],
        "policy_rule_hits": ["native_seed_role_policy"] if action in {"scheduled_dca", "hold"} else ["native_seed_score_policy"],
        "constraint_hits": [],
        "allocation_impact": f"{infer_strategy_bucket(fund)}:native_seed",
        "cash_impact": f"native_seed_amount={amount:.2f}",
        "change_vs_prev_day": {"changed": action != "hold", "reason_category": "native_seed"},
        "execution_friction": [],
        "validation_notes": ["Native action seed; official validator remains responsible for executable sizing and portfolio constraints."],
        "execution_status": "pending" if action != "hold" else "not_applicable",
        "executed_amount": 0.0,
        "ticket_status": "shadow_only",
        "_source_bucket": "native_seed",
        "_source_index": priority,
        "_seed_source_kind": "native_action_seed",
        "_seed_source_path": seed_relative_path,
    }


def build_native_action_seed_payload(
    agent_home: Path,
    report_date: str,
    *,
    portfolio: dict[str, Any],
    strategy: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or timestamp_now()
    context_path = llm_context_path(agent_home, report_date)
    scores_path = score_path(agent_home, report_date)
    context = load_json_if_exists(context_path)
    scores = load_json_if_exists(scores_path)
    context_by_code = _context_by_code(context)
    score_by_code = _score_by_code(scores)
    thresholds = _strategy_thresholds(strategy)
    seed_relative_path = f"db/action_seed/{report_date}.json"

    actions: list[dict[str, Any]] = []
    for index, fund in enumerate(portfolio.get("funds", []) or [], start=1):
        if not isinstance(fund, dict) or not fund.get("fund_code"):
            continue
        code = str(fund.get("fund_code", "") or "")
        role = str(fund.get("role", "") or "")
        context_item = context_by_code.get(code, {})
        score_item = score_by_code.get(code, {})
        if role == "core_dca":
            action = "scheduled_dca"
            amount = safe_float(fund.get("fixed_daily_buy_amount"), safe_float((strategy.get("core_dca", {}) or {}).get("amount_per_fund"), 25.0))
        elif role in {"cash_hub", "fixed_hold"} or fund.get("allow_trade") is False:
            action = "hold"
            amount = 0.0
        else:
            action = _score_action(score_item, thresholds)
            amount = _amount_for(action, fund, score_item, thresholds)
            if amount <= 0.0:
                action = "hold"
                amount = 0.0
        actions.append(
            _seed_action(
                report_date=report_date,
                fund=fund,
                context_item=context_item,
                score_item=score_item,
                action=action,
                amount=round(amount, 2),
                priority=index,
                seed_relative_path=seed_relative_path,
            )
        )

    source_artifacts = []
    for kind, path in (
        ("portfolio_state", Path(portfolio.get("_source_path", "")) if portfolio.get("_source_path") else None),
        ("daily_score", scores_path),
        ("llm_context", context_path),
    ):
        if path and path.exists():
            try:
                relative = path.resolve().relative_to(agent_home.resolve()).as_posix()
            except ValueError:
                relative = path.as_posix()
            source_artifacts.append({"kind": kind, "path": relative, "content_sha256": source_hash(path)})
    return {
        "schema_version": NATIVE_SEED_SCHEMA_VERSION,
        "artifact_id": f"native_action_seed:{report_date}",
        "artifact_kind": "native_action_seed",
        "report_date": report_date,
        "generated_at": generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "source_artifacts": source_artifacts,
        "summary": {
            "seed_count": len(actions),
            "action_count": sum(1 for item in actions if item.get("validated_action") != "hold"),
            "dca_count": sum(1 for item in actions if item.get("validated_action") == "scheduled_dca"),
            "native_independent_of_validated_advice": True,
        },
        "actions": actions,
    }


def build_native_action_seeds(
    agent_home: Path,
    report_date: str,
    *,
    portfolio: dict[str, Any],
    portfolio_source_path: Path,
    strategy: dict[str, Any],
    generated_at: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    payload = build_native_action_seed_payload(agent_home, report_date, portfolio={**portfolio, "_source_path": str(portfolio_source_path)}, strategy=strategy, generated_at=generated_at)
    path = native_action_seed_path(agent_home, report_date)
    return dump_json(path, payload), payload
