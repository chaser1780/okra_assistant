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


def summarize_fund_stage_signals(aggregate: dict, fund_code: str) -> dict:
    summary = {
        "analyst": {"support": [], "caution": [], "neutral": [], "highlights": [], "has_conflict": False},
        "researcher": {"support": [], "caution": [], "neutral": [], "highlights": [], "has_conflict": False},
        "manager": {"support": [], "caution": [], "neutral": [], "highlights": [], "has_conflict": False},
    }
    for agent_name, record in (aggregate.get("agents", {}) or {}).items():
        output = record.get("output", {}) or {}
        for view in output.get("fund_views", []) or []:
            if view.get("fund_code") != fund_code:
                continue
            stage = agent_stage(agent_name, aggregate)
            stage_bucket = summary.setdefault(stage, {"support": [], "caution": [], "neutral": [], "highlights": [], "has_conflict": False})
            bucket = signal_bucket(view.get("action_bias", ""))
            comment = str(view.get("comment") or view.get("thesis") or "").strip()
            risks = [str(item).strip() for item in (view.get("risks") or []) if str(item).strip()]
            if bucket == "support":
                stage_bucket["support"].append(agent_name)
            elif bucket == "caution":
                stage_bucket["caution"].append(agent_name)
            else:
                stage_bucket["neutral"].append(agent_name)
            detail = comment or (risks[0] if risks else "")
            if detail:
                stage_bucket["highlights"].append(f"{agent_name}: {detail}")

    for stage_bucket in summary.values():
        stage_bucket["support"] = sorted(dict.fromkeys(stage_bucket["support"]))
        stage_bucket["caution"] = sorted(dict.fromkeys(stage_bucket["caution"]))
        stage_bucket["neutral"] = sorted(dict.fromkeys(stage_bucket["neutral"]))
        stage_bucket["highlights"] = list(dict.fromkeys(stage_bucket["highlights"]))[:3]
        stage_bucket["has_conflict"] = bool(stage_bucket["support"] and stage_bucket["caution"])
    return summary


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
        for view in output.get("fund_views", []) or []:
            if view.get("fund_code") != fund_code:
                continue
            bucket = signal_bucket(view.get("action_bias", ""))
            comment = str(view.get("comment") or view.get("thesis") or "").strip()
            risks = [str(item).strip() for item in (view.get("risks") or []) if str(item).strip()]
            if bucket == "support":
                summary["supporting_agents"].append(agent_name)
                if comment:
                    summary["support_points"].append(f"{agent_name}: {comment}")
            elif bucket == "caution":
                summary["caution_agents"].append(agent_name)
                if comment:
                    summary["caution_points"].append(f"{agent_name}: {comment}")
                elif risks:
                    summary["caution_points"].append(f"{agent_name}: {risks[0]}")
            else:
                summary["neutral_agents"].append(agent_name)
            if agent_name in committee_names:
                summary["committee_views"].append(
                    {
                        "agent_name": agent_name,
                        "bucket": bucket,
                        "action_bias": view.get("action_bias", ""),
                        "comment": comment or (risks[0] if risks else ""),
                    }
                )
    summary["supporting_agents"] = sorted(dict.fromkeys(summary["supporting_agents"]))
    summary["caution_agents"] = sorted(dict.fromkeys(summary["caution_agents"]))
    summary["neutral_agents"] = sorted(dict.fromkeys(summary["neutral_agents"]))
    summary["support_points"] = list(dict.fromkeys(summary["support_points"]))[:5]
    summary["caution_points"] = list(dict.fromkeys(summary["caution_points"]))[:5]
    summary["has_conflict"] = bool(summary["supporting_agents"] and summary["caution_agents"])
    return summary
