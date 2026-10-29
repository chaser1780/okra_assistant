from __future__ import annotations

STAGE_META = {
    "analyst": {
        "label": "Analyst Team",
        "description": "拆分市场、主题、结构、质量、新闻与情绪信号。",
        "tone": "info",
    },
    "researcher": {
        "label": "Research Debate",
        "description": "围绕 analyst 结论构造看多 / 看空论证。",
        "tone": "warning",
    },
    "manager": {
        "label": "Committee Decision",
        "description": "由研究经理、风险经理和组合交易员收敛为最终动作。",
        "tone": "success",
    },
}


def signal_bucket(action_bias: str) -> str:
    text = (action_bias or "").strip().lower()
    if any(token in text for token in ("add", "buy", "accumulate", "bull")):
        return "support"
    if any(token in text for token in ("reduce", "trim", "switch", "sell", "avoid", "reject", "bear")):
        return "caution"
    return "neutral"


def agent_stage(agent_name: str, aggregate: dict | None = None) -> str:
    roles = ((aggregate or {}).get("agent_roles", {}) or {})
    if agent_name in roles:
        return str(roles[agent_name] or "analyst")
    if agent_name.endswith("_analyst"):
        return "analyst"
    if agent_name.endswith("_researcher"):
        return "researcher"
    return "manager"


def stage_label(stage: str) -> str:
    return STAGE_META.get(stage, {}).get("label", stage or "Unknown")


def stage_tone(stage: str) -> str:
    return STAGE_META.get(stage, {}).get("tone", "info")


def agent_dependencies(agent_name: str, aggregate: dict | None = None) -> list[str]:
    dependencies = ((aggregate or {}).get("agent_dependencies", {}) or {})
    return list(dependencies.get(agent_name, []) or [])


def agent_consumers(agent_name: str, aggregate: dict | None = None) -> list[str]:
    consumers: list[str] = []
    dependencies = ((aggregate or {}).get("agent_dependencies", {}) or {})
    for candidate, upstream in dependencies.items():
        if agent_name in (upstream or []):
            consumers.append(candidate)
    return consumers


def build_agent_stage_snapshot(agent_name: str, aggregate: dict | None = None) -> dict:
    stage = agent_stage(agent_name, aggregate)
    meta = STAGE_META.get(stage, {})
    return {
        "stage": stage,
        "label": meta.get("label", stage),
        "description": meta.get("description", ""),
        "tone": meta.get("tone", "info"),
        "depends_on": agent_dependencies(agent_name, aggregate),
        "consumers": agent_consumers(agent_name, aggregate),
        "is_committee_core": agent_name in set(((aggregate or {}).get("required_committee_agents", []) or [])),
    }


def _first_text(card: dict, *keys: str) -> str:
    for key in keys:
        value = card.get(key)
        if value:
            return str(value).strip()
    return ""


def _view_comment_and_risks(view: dict) -> tuple[str, list[str]]:
    comment = str(view.get("comment") or view.get("thesis") or "").strip()
    risks = [str(item).strip() for item in (view.get("risks") or []) if str(item).strip()]
    return comment, risks


def _view_detail(view: dict) -> str:
    comment, risks = _view_comment_and_risks(view)
    return comment or (risks[0] if risks else "")


def _empty_stage_bucket() -> dict:
    return {"support": [], "caution": [], "neutral": [], "highlights": [], "has_conflict": False}


def _collect_stage_cards(summary: dict, agent_name: str, aggregate: dict, cards, *, fund_code: str, bias_key: str, detail_of) -> None:
    for card in cards:
        if card.get("fund_code") != fund_code:
            continue
        stage = agent_stage(agent_name, aggregate)
        stage_bucket = summary.setdefault(stage, _empty_stage_bucket())
        bucket = signal_bucket(card.get(bias_key, ""))
        detail = detail_of(card)
        if bucket == "support":
            stage_bucket["support"].append(agent_name)
        elif bucket == "caution":
            stage_bucket["caution"].append(agent_name)
        else:
            stage_bucket["neutral"].append(agent_name)
        if detail:
            stage_bucket["highlights"].append(f"{agent_name}: {detail}")


def summarize_fund_stage_signals(aggregate: dict, fund_code: str) -> dict:
    summary = {
        "analyst": _empty_stage_bucket(),
        "researcher": _empty_stage_bucket(),
        "manager": _empty_stage_bucket(),
    }
    for agent_name, record in (aggregate.get("agents", {}) or {}).items():
        output = record.get("output", {}) or {}
        signal_cards = output.get("signal_cards", []) or []
        decision_cards = output.get("decision_cards", []) or []
        _collect_stage_cards(
            summary, agent_name, aggregate, signal_cards,
            fund_code=fund_code, bias_key="action_bias",
            detail_of=lambda card: _first_text(card, "comment", "thesis"),
        )
        _collect_stage_cards(
            summary, agent_name, aggregate, decision_cards,
            fund_code=fund_code, bias_key="proposed_action",
            detail_of=lambda card: _first_text(card, "why_now", "manager_notes"),
        )
        _collect_stage_cards(
            summary, agent_name, aggregate, output.get("fund_views", []) or [],
            fund_code=fund_code, bias_key="action_bias",
            detail_of=_view_detail,
        )

    for stage_bucket in summary.values():
        stage_bucket["support"] = sorted(dict.fromkeys(stage_bucket["support"]))
        stage_bucket["caution"] = sorted(dict.fromkeys(stage_bucket["caution"]))
        stage_bucket["neutral"] = sorted(dict.fromkeys(stage_bucket["neutral"]))
        stage_bucket["highlights"] = list(dict.fromkeys(stage_bucket["highlights"]))[:3]
        stage_bucket["has_conflict"] = bool(stage_bucket["support"] and stage_bucket["caution"])
    return summary


def _append_agent_bucket(summary: dict, agent_name: str, bucket: str, point: str) -> None:
    if bucket == "support":
        summary["supporting_agents"].append(agent_name)
        if point:
            summary["support_points"].append(f"{agent_name}: {point}")
    elif bucket == "caution":
        summary["caution_agents"].append(agent_name)
        if point:
            summary["caution_points"].append(f"{agent_name}: {point}")
    else:
        summary["neutral_agents"].append(agent_name)


def _append_committee_view(summary: dict, agent_name: str, bucket: str, bias_value, comment: str) -> None:
    summary["committee_views"].append(
        {
            "agent_name": agent_name,
            "bucket": bucket,
            "action_bias": bias_value,
            "comment": comment,
        }
    )


def summarize_fund_agent_signals(aggregate: dict, fund_code: str) -> dict:
    summary = {
        "supporting_agents": [],
        "caution_agents": [],
        "neutral_agents": [],
        "support_points": [],
        "caution_points": [],
        "committee_views": [],
        "has_conflict": False,
    }
    committee_names = {"research_manager", "risk_manager", "portfolio_trader"}
    for agent_name, record in (aggregate.get("agents", {}) or {}).items():
        output = record.get("output", {}) or {}
        for card in output.get("signal_cards", []) or []:
            if card.get("fund_code") != fund_code:
                continue
            bucket = signal_bucket(card.get("action_bias", ""))
            comment = str(card.get("comment") or card.get("thesis") or "").strip()
            risks = [str(item).strip() for item in (card.get("risks") or []) if str(item).strip()]
            point = comment if bucket == "support" else (comment or (risks[0] if risks else ""))
            _append_agent_bucket(summary, agent_name, bucket, point)
        for card in output.get("decision_cards", []) or []:
            if card.get("fund_code") != fund_code:
                continue
            bucket = signal_bucket(card.get("proposed_action", ""))
            comment = str(card.get("why_now") or card.get("manager_notes") or "").strip()
            _append_agent_bucket(summary, agent_name, bucket, comment)
            if agent_name in committee_names:
                _append_committee_view(summary, agent_name, bucket, card.get("proposed_action", ""), comment)
        for view in output.get("fund_views", []) or []:
            if view.get("fund_code") != fund_code:
                continue
            bucket = signal_bucket(view.get("action_bias", ""))
            comment, risks = _view_comment_and_risks(view)
            point = comment if bucket == "support" else (comment or (risks[0] if risks else ""))
            _append_agent_bucket(summary, agent_name, bucket, point)
            if agent_name in committee_names:
                _append_committee_view(summary, agent_name, bucket, view.get("action_bias", ""), comment or (risks[0] if risks else ""))
    summary["supporting_agents"] = sorted(dict.fromkeys(summary["supporting_agents"]))
    summary["caution_agents"] = sorted(dict.fromkeys(summary["caution_agents"]))
    summary["neutral_agents"] = sorted(dict.fromkeys(summary["neutral_agents"]))
    summary["support_points"] = list(dict.fromkeys(summary["support_points"]))[:5]
    summary["caution_points"] = list(dict.fromkeys(summary["caution_points"]))[:5]
    summary["has_conflict"] = bool(summary["supporting_agents"] and summary["caution_agents"])
    return summary
