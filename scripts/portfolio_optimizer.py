from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any


def _bucket_value_map(items: list[dict[str, Any]] | None = None) -> dict[str, float]:
    mapping: dict[str, float] = {}
    for item in items or []:
        name = str(item.get("name", "") or "").strip()
        if not name:
            continue
        mapping[name] = float(item.get("value", 0.0) or 0.0)
    return mapping


def _bucket_pct_map(values: dict[str, float], total_value: float) -> dict[str, float]:
    if total_value <= 0:
        return {key: 0.0 for key in values}
    return {key: round(max(0.0, value) / total_value * 100.0, 2) for key, value in values.items()}


def _action_direction(action: str) -> str:
    if action == "add":
        return "buy"
    if action in {"reduce", "switch_out"}:
        return "sell"
    return "hold"


def _candidate_score(candidate: dict[str, Any], current_pct: dict[str, float], target_pct: dict[str, float]) -> float:
    action = str(candidate.get("action", "") or "")
    bucket = str(candidate.get("strategy_bucket", "") or "")
    confidence = float(candidate.get("confidence", 0.0) or 0.0)
    priority = int(candidate.get("priority", 999) or 999)
    support_count = len(candidate.get("agent_support", []) or [])
    evidence_count = len(candidate.get("evidence", []) or [])
    risk_count = len(candidate.get("risks", []) or [])
    cost = float(candidate.get("transaction_cost_amount", 0.0) or 0.0)
    amount = float(candidate.get("amount", 0.0) or 0.0)

    score = confidence * 100.0
    score += max(0.0, 16.0 - priority * 1.5)
    score += support_count * 3.0 + evidence_count * 1.2
    score -= risk_count * 4.0
    score -= cost * 0.08
    score += min(amount / 100.0, 4.0)

    current = float(current_pct.get(bucket, 0.0) or 0.0)
    target = float(target_pct.get(bucket, 0.0) or 0.0)
    drift = target - current
    if action == "add":
        score += 8.0 if drift > 0 else -6.0
    elif action in {"reduce", "switch_out"}:
        score += 8.0 if drift < 0 else 4.0
    return round(score, 4)


def _combo_metrics(
    selected: tuple[dict[str, Any], ...],
    *,
    current_bucket_values: dict[str, float],
    total_value: float,
) -> dict[str, Any]:
    gross_trade = 0.0
    net_buy = 0.0
    sell_proceeds = 0.0
    bucket_values = dict(current_bucket_values)
    for candidate in selected:
        action = str(candidate.get("action", "") or "")
        amount = float(candidate.get("amount", 0.0) or 0.0)
        bucket = str(candidate.get("strategy_bucket", "") or "")
        gross_trade += amount
        if action == "add":
            net_buy += amount
            bucket_values[bucket] = bucket_values.get(bucket, 0.0) + amount
        elif action in {"reduce", "switch_out"}:
            sell_proceeds += amount
            bucket_values[bucket] = bucket_values.get(bucket, 0.0) - amount
    return {
        "gross_trade": round(gross_trade, 2),
        "net_buy": round(net_buy, 2),
        "sell_proceeds": round(sell_proceeds, 2),
        "bucket_values": bucket_values,
        "bucket_pct": _bucket_pct_map(bucket_values, total_value),
    }


def _allocation_reasons(
    *,
    current_pct: dict[str, float],
    new_pct: dict[str, float],
    target_pct: dict[str, float],
    rebalance_band_pct: float,
) -> list[str]:
    reasons: list[str] = []
    keys = sorted(set(current_pct) | set(new_pct) | set(target_pct))
    for bucket in keys:
        current = float(current_pct.get(bucket, 0.0) or 0.0)
        new = float(new_pct.get(bucket, 0.0) or 0.0)
        target = float(target_pct.get(bucket, 0.0) or 0.0)
        upper = target + rebalance_band_pct
        lower = target - rebalance_band_pct
        # Keep the hard guardrail narrow for the tactical-short-term bucket.
        if bucket != "tactical_short_term":
            continue
        if lower <= current <= upper:
            if new > upper + 1e-9:
                reasons.append(f"allocation_band_upper:{bucket}")
            elif new < lower - 1e-9:
                reasons.append(f"allocation_band_lower:{bucket}")
            continue
        if current > upper + 1e-9 and new > current + 1e-9:
            reasons.append(f"allocation_worsens_overweight:{bucket}")
        if current < lower - 1e-9 and new < current - 1e-9:
            reasons.append(f"allocation_worsens_underweight:{bucket}")
    return reasons


def _combo_score(
    selected: tuple[dict[str, Any], ...],
    *,
    current_pct: dict[str, float],
    new_pct: dict[str, float],
    target_pct: dict[str, float],
) -> float:
    score = sum(float(candidate.get("base_objective", 0.0) or 0.0) for candidate in selected)
    current_drift = sum(abs(float(current_pct.get(bucket, 0.0) or 0.0) - float(target_pct.get(bucket, 0.0) or 0.0)) for bucket in set(current_pct) | set(target_pct))
    new_drift = sum(abs(float(new_pct.get(bucket, 0.0) or 0.0) - float(target_pct.get(bucket, 0.0) or 0.0)) for bucket in set(new_pct) | set(target_pct))
    score += (current_drift - new_drift) * 1.4

    add_family_counter: Counter[str] = Counter()
    direction_counter: Counter[str] = Counter()
    for candidate in selected:
        direction_counter[_action_direction(str(candidate.get("action", "") or ""))] += 1
        if str(candidate.get("action", "") or "") == "add":
            add_family_counter[str(candidate.get("theme_family", "unknown") or "unknown")] += 1
    for _, count in add_family_counter.items():
        if count > 1:
            score -= (count - 1) * 8.0
    if len(selected) > 1:
        score -= (len(selected) - 1) * 1.5
    if direction_counter.get("buy", 0) >= 2:
        score -= (direction_counter["buy"] - 1) * 3.0
    return round(score, 4)


def _candidate_diagnostic(candidate: dict[str, Any], info: dict[str, Any], rejection_reasons: list[str], selected_ids: set[str]) -> dict[str, Any]:
    return {
        "candidate_id": candidate.get("candidate_id", ""),
        "fund_code": candidate.get("fund_code", ""),
        "fund_name": candidate.get("fund_name", ""),
        "action": candidate.get("action", ""),
        "amount": float(candidate.get("amount", 0.0) or 0.0),
        "strategy_bucket": candidate.get("strategy_bucket", ""),
        "theme_family": candidate.get("theme_family", ""),
        "priority": int(candidate.get("priority", 999) or 999),
        "confidence": float(candidate.get("confidence", 0.0) or 0.0),
        "base_objective": float(candidate.get("base_objective", 0.0) or 0.0),
        "support_count": len(candidate.get("agent_support", []) or []),
        "evidence_count": len(candidate.get("evidence", []) or []),
        "risk_count": len(candidate.get("risks", []) or []),
        "transaction_cost_amount": float(candidate.get("transaction_cost_amount", 0.0) or 0.0),
        "feasible_combination_count": int(info.get("feasible", 0) or 0),
        "best_combo_objective": float(info.get("best_with", 0.0) or 0.0),
        "selected": candidate.get("candidate_id", "") in selected_ids,
        "rejection_reasons": rejection_reasons,
    }


def optimize_portfolio_actions(
    candidates: list[dict[str, Any]],
    *,
    strategy_bucket_summary: list[dict[str, Any]],
    current_bucket_pct: dict[str, float],
    target_bucket_pct: dict[str, float],
    rebalance_band_pct: float,
    total_value: float,
    available_funding: float,
    gross_trade_budget: float,
    net_buy_budget: float,
    max_actions: int,
) -> dict[str, Any]:
    normalized_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        prepared = dict(candidate)
        prepared["base_objective"] = _candidate_score(prepared, current_bucket_pct, target_bucket_pct)
        normalized_candidates.append(prepared)

    current_bucket_values = _bucket_value_map(strategy_bucket_summary)
    search_space = 1
    for size in range(1, min(len(normalized_candidates), max_actions) + 1):
        search_space += len(list(combinations(normalized_candidates, size)))

    best_combo: tuple[dict[str, Any], ...] = ()
    best_score = 0.0
    feasible_count = 1
    candidate_diagnostics: dict[str, dict[str, Any]] = {
        candidate["candidate_id"]: {"feasible": 0, "best_with": None, "reasons": Counter()}
        for candidate in normalized_candidates
    }

    for size in range(1, min(len(normalized_candidates), max_actions) + 1):
        for selected in combinations(normalized_candidates, size):
            metrics = _combo_metrics(selected, current_bucket_values=current_bucket_values, total_value=total_value)
            reasons: list[str] = []
            if metrics["gross_trade"] > gross_trade_budget + 1e-9:
                reasons.append("gross_trade_budget")
            if metrics["net_buy"] > net_buy_budget + 1e-9:
                reasons.append("net_buy_budget")
            if metrics["net_buy"] > available_funding + metrics["sell_proceeds"] + 1e-9:
                reasons.append("cash_funding")
            reasons.extend(
                _allocation_reasons(
                    current_pct=current_bucket_pct,
                    new_pct=metrics["bucket_pct"],
                    target_pct=target_bucket_pct,
                    rebalance_band_pct=rebalance_band_pct,
                )
            )
            for candidate in selected:
                info = candidate_diagnostics[candidate["candidate_id"]]
                if reasons:
                    info["reasons"].update(reasons)
                    continue
                info["feasible"] += 1
            if reasons:
                continue
            feasible_count += 1
            score = _combo_score(selected, current_pct=current_bucket_pct, new_pct=metrics["bucket_pct"], target_pct=target_bucket_pct)
            for candidate in selected:
                info = candidate_diagnostics[candidate["candidate_id"]]
                current_best = info["best_with"]
                if current_best is None or score > current_best:
                    info["best_with"] = score
            if score > best_score + 1e-9:
                best_combo = selected
                best_score = score

    selected_ids = {candidate["candidate_id"] for candidate in best_combo}
    rejection_reasons: dict[str, list[str]] = {}
    for candidate in normalized_candidates:
        candidate_id = candidate["candidate_id"]
        if candidate_id in selected_ids:
            continue
        info = candidate_diagnostics[candidate_id]
        if info["feasible"] == 0:
            top = [reason for reason, _ in info["reasons"].most_common(3)] or ["candidate_not_feasible"]
            rejection_reasons[candidate_id] = top
        else:
            rejection_reasons[candidate_id] = ["dominated_by_higher_portfolio_objective"]

    best_metrics = _combo_metrics(best_combo, current_bucket_values=current_bucket_values, total_value=total_value)
    remaining_gross = round(max(0.0, gross_trade_budget - best_metrics["gross_trade"]), 2)
    remaining_net_buy = round(max(0.0, net_buy_budget - best_metrics["net_buy"]), 2)
    remaining_funding = round(max(0.0, available_funding + best_metrics["sell_proceeds"] - best_metrics["net_buy"]), 2)
    diagnostic_items = [
        _candidate_diagnostic(
            candidate,
            candidate_diagnostics.get(candidate["candidate_id"], {}),
            rejection_reasons.get(candidate["candidate_id"], []),
            selected_ids,
        )
        for candidate in normalized_candidates
    ]
    diagnostic_items.sort(key=lambda item: (-float(item.get("base_objective", 0.0) or 0.0), int(item.get("priority", 999) or 999), item.get("fund_code", "")))
    rejection_reason_counter: Counter[str] = Counter()
    for reasons in rejection_reasons.values():
        rejection_reason_counter.update(reasons)

    return {
        "selected_candidates": [dict(candidate) for candidate in best_combo],
        "selected_candidate_ids": sorted(selected_ids),
        "rejection_reasons": rejection_reasons,
        "candidate_diagnostics": diagnostic_items,
        "best_combo_metrics": best_metrics,
        "remaining_gross_trade_budget": remaining_gross,
        "remaining_net_buy_budget": remaining_net_buy,
        "remaining_available_funding": remaining_funding,
        "summary": {
            "mode": "portfolio_search",
            "candidate_count": len(normalized_candidates),
            "selected_candidate_count": len(best_combo),
            "search_space": search_space,
            "feasible_combination_count": feasible_count,
            "best_objective_score": round(best_score, 4),
            "selected_fund_codes": [candidate.get("fund_code", "") for candidate in best_combo],
            "selected_actions": [
                {
                    "fund_code": candidate.get("fund_code", ""),
                    "action": candidate.get("action", ""),
                    "amount": float(candidate.get("amount", 0.0) or 0.0),
                    "base_objective": float(candidate.get("base_objective", 0.0) or 0.0),
                }
                for candidate in best_combo
            ],
            "bucket_pct_before": {key: round(float(value or 0.0), 2) for key, value in sorted(current_bucket_pct.items())},
            "bucket_pct_after": best_metrics["bucket_pct"],
            "selected_gross_trade": best_metrics["gross_trade"],
            "selected_net_buy": best_metrics["net_buy"],
            "selected_sell_proceeds": best_metrics["sell_proceeds"],
            "rejection_reason_counts": dict(sorted(rejection_reason_counter.items())),
            "candidate_diagnostics_count": len(diagnostic_items),
            "notes": [
                "Search the best feasible action combination under shared cash, gross trade, net buy, and allocation guardrails.",
                "Reject candidates that worsen an already out-of-band allocation bucket.",
            ],
        },
    }
