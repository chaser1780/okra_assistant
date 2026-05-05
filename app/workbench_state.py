from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sys

try:
    from decision_support import summarize_fund_agent_signals
    from portfolio_exposure import analyze_portfolio_exposure
    from ui_support import (
        build_action_change_lines,
        build_dashboard_alerts,
        build_learning_detail_fallback,
        build_learning_summary_text,
        build_realtime_summary_text,
        load_state,
        load_validated_for_date,
        num,
        previous_date,
        today_str,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from decision_support import summarize_fund_agent_signals
    from portfolio_exposure import analyze_portfolio_exposure
    from ui_support import (
        build_action_change_lines,
        build_dashboard_alerts,
        build_learning_detail_fallback,
        build_learning_summary_text,
        build_realtime_summary_text,
        load_state,
        load_validated_for_date,
        num,
        previous_date,
        today_str,
    )


@dataclass(frozen=True)
class MetricViewModel:
    title: str
    value: str
    body: str
    tone: str = "neutral"


@dataclass(frozen=True)
class DesktopSnapshot:
    home: Path
    state: dict[str, Any]
    summary: dict[str, Any]
    selected_date: str
    dates: list[str]


@dataclass(frozen=True)
class ShellViewModel:
    dates: list[str]
    selected_date: str
    chain_status: str
    status_badge_state: str
    status_bar_text: str


@dataclass(frozen=True)
class DashboardViewModel:
    meta: str
    metrics: list[MetricViewModel]
    focus_text: str
    market_text: str
    change_text: str
    summary_text: str
    detail_text: str
    primary_fund_code: str
    committee_text: str = ""
    provider_text: str = ""


@dataclass(frozen=True)
class ResearchViewModel:
    meta: str
    metrics: list[MetricViewModel]
    rows: list[dict[str, Any]]
    aggregate: dict[str, Any]
    realtime_map: dict[str, dict[str, Any]]
    review_map: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class RealtimeViewModel:
    meta: str
    metrics: list[MetricViewModel]
    items: list[dict[str, Any]]
    summary_text: str


@dataclass(frozen=True)
class AgentsViewModel:
    meta: str
    metrics: list[MetricViewModel]
    rows: list[dict[str, Any]]
    aggregate: dict[str, Any]


@dataclass(frozen=True)
class ReviewViewModel:
    meta: str
    metrics: list[MetricViewModel]
    summary_text: str
    detail_text: str
    core_lines: list[str]
    strategic_lines: list[str]
    replay_lines: list[str]
    replay_items: list[dict[str, Any]]
    fund_memory_lines: list[str]
    market_memory_lines: list[str]
    execution_memory_lines: list[str]
    pending_memory_lines: list[str]
    pending_memory_items: list[dict[str, Any]]
    dates: list[str]
    selected_date: str


@dataclass(frozen=True)
class RuntimeViewModel:
    banner: str
    cards: dict[str, str]


class WorkbenchStateService:
    def __init__(self, home: Path):
        self.home = home

    def load_snapshot(self, selected: str | None = None) -> DesktopSnapshot:
        state = load_state(self.home, selected)
        summary = _summarize_state_clean(state)
        return DesktopSnapshot(
            home=self.home,
            state=state,
            summary=summary,
            selected_date=str(state.get("selected_date", "") or ""),
            dates=list(state.get("dates", []) or []),
        )

    def build_shell_view_model(self, snapshot: DesktopSnapshot, *, running: bool, chain_status: str) -> ShellViewModel:
        status_badge_state = "running" if running else ("warning" if snapshot.summary.get("preflight_status") == "warning" else "idle")
        status_bar_text = (
            f"查看日期 {snapshot.summary.get('selected_date', snapshot.selected_date)} | "
            f"建议模式 {snapshot.summary.get('advice_mode', '未知')} | "
            f"失败智能体 {len(snapshot.summary.get('failed_agent_names', []))}"
        )
        return ShellViewModel(
            dates=snapshot.dates,
            selected_date=snapshot.selected_date or today_str(),
            chain_status=chain_status,
            status_badge_state=status_badge_state,
            status_bar_text=status_bar_text,
        )

    def _exposure(self, snapshot: DesktopSnapshot) -> dict[str, Any]:
        exposure = snapshot.state.get("llm_context", {}).get("exposure_summary") or {}
        required_keys = {"allocation_plan", "concentration_metrics", "largest_style_group"}
        if required_keys.issubset(set(exposure.keys())):
            return exposure
        return analyze_portfolio_exposure(snapshot.state.get("portfolio", {}), snapshot.state.get("strategy", {}))

    def build_dashboard_view_model(self, snapshot: DesktopSnapshot) -> DashboardViewModel:
        state = snapshot.state
        validated = state.get("validated", {}) or {}
        exposure = self._exposure(snapshot)
        alerts = _safe_lines(build_dashboard_alerts({**state, "home": self.home}))
        prev_date = previous_date(state.get("dates", []) or [], snapshot.selected_date)
        prev_validated = load_validated_for_date(self.home, prev_date)
        changes = _safe_lines(build_action_change_lines(validated, prev_validated, prev_date))
        tactical = list(validated.get("tactical_actions", []) or [])
        dca = list(validated.get("dca_actions", []) or [])
        holds = list(validated.get("hold_actions", []) or [])
        actionable = tactical + dca
        top = actionable[0] if actionable else {}
        market = validated.get("market_view", {}) or {}
        aggregate = state.get("aggregate", {}) or {}
        committee = validated.get("committee", {}) or aggregate.get("committee", {}) or {}
        decision_source = snapshot.summary.get("decision_source", "") or "未知"
        provider_text = self._provider_health_text(state)
        committee_text = self._committee_text(committee)

        metrics = [
            MetricViewModel(
                "今日主动作",
                str(top.get("fund_name") or top.get("fund_code") or "暂无"),
                str(top.get("thesis") or top.get("reason") or "今天没有需要立即执行的主动作。"),
                "accent",
            ),
            MetricViewModel(
                "市场状态",
                str(market.get("regime") or "暂无"),
                str(market.get("summary") or "等待市场摘要生成。"),
                "info",
            ),
            MetricViewModel(
                "建议模式",
                str(snapshot.summary.get("advice_mode") or "未知"),
                f"决策源 {decision_source} | 通道 {snapshot.summary.get('transport_name') or '暂无'}",
                "warning" if snapshot.summary.get("advice_is_fallback") else "success",
            ),
            MetricViewModel(
                "风险提醒",
                f"{len(alerts)} 条" if alerts else "稳定",
                alerts[0] if alerts else "暂无高优先级风险提醒。",
                "danger" if alerts else "success",
            ),
        ]

        focus_lines = [_action_line(item) for item in actionable[:5]]
        market_lines = [str(market.get("summary") or "暂无市场摘要。")] + alerts[:5]
        summary_lines = [
            f"今日可执行建议 {len(actionable)} 条，观察 {len(holds)} 条。",
            f"组合快照日期 {state.get('portfolio_date') or '暂无'}。",
        ]
        largest_style = (exposure.get("largest_style_group") or {}).get("name")
        if largest_style:
            summary_lines.append(f"当前最大风格暴露为 {largest_style}。")

        meta = (
            f"查看日期 {snapshot.selected_date} | 持仓快照 {state.get('portfolio_date') or '暂无'} | "
            f"建议 {len(actionable)} 条 | 观察 {len(holds)} 条 | "
            f"失败智能体 {len(snapshot.summary.get('failed_agent_names', []))}"
        )
        return DashboardViewModel(
            meta=meta,
            metrics=metrics,
            focus_text="\n".join(f"- {line}" for line in focus_lines) if focus_lines else "- 暂无需要立即执行的动作",
            market_text="\n".join(f"- {line}" for line in market_lines if line),
            change_text="\n".join(changes or ["- 暂无明显变化"]),
            summary_text="\n".join(f"- {line}" for line in summary_lines),
            detail_text=_dashboard_detail(snapshot.summary, validated, exposure, changes, alerts),
            primary_fund_code=str(top.get("fund_code", "") or ""),
            committee_text=committee_text,
            provider_text=provider_text,
        )

    def _provider_health_text(self, state: dict[str, Any]) -> str:
        rows: list[str] = []
        for label, payload in (
            ("组合快照", state.get("portfolio", {}) or {}),
            ("实时估值", state.get("realtime", {}) or {}),
            ("Agent 聚合", state.get("aggregate", {}) or {}),
        ):
            meta = payload.get("provider_metadata", {}) if isinstance(payload, dict) else {}
            if meta:
                rows.append(
                    f"- {label}: {meta.get('provider_name', '未知')} | "
                    f"{meta.get('freshness_status', '未知')} | 置信度 {meta.get('confidence', '未知')}"
                )
        source_health = state.get("source_health", {}) or {}
        for item in (source_health.get("items", []) or [])[:4]:
            rows.append(
                f"- {item.get('source_key', '')}: 状态 {item.get('status', '未知')} | "
                f"过期 {item.get('stale_count', 0)} | 错误 {item.get('error_count', 0)}"
            )
        return "\n".join(rows or ["- 暂无结构化数据源健康信息，请先运行今日首启分析。"])

    def _committee_text(self, committee: dict[str, Any]) -> str:
        if not committee:
            return "- 暂无投委会结构化摘要，请先运行多 Agent 研究。"
        lines = [
            f"- 来源 {committee.get('decision_source', '未知')} | 委员会置信度 {committee.get('committee_confidence', '未知')}"
        ]
        for label, key in (("多头理由", "bull_case"), ("空头理由", "bear_case"), ("风控否决", "risk_vetoes")):
            items = committee.get(key, []) or []
            lines.append(f"- {label}: {len(items)} 条")
            for item in items[:2]:
                lines.append(f"  - {item.get('fund_code', '')}: {item.get('thesis') or item.get('reason') or ''}")
        manager = committee.get("manager_decision", {}) or {}
        if manager.get("summary"):
            lines.append(f"- 研究经理: {manager.get('summary')}")
        return "\n".join(lines)

    def build_research_view_model(self, snapshot: DesktopSnapshot) -> ResearchViewModel:
        state = snapshot.state
        aggregate = state.get("aggregate", {}) or {}
        rows: list[dict[str, Any]] = []
        for section in ("tactical_actions", "dca_actions", "hold_actions"):
            for item in state.get("validated", {}).get(section, []) or []:
                enriched = dict(item)
                enriched["_section"] = section
                signal_summary = summarize_fund_agent_signals(aggregate, item.get("fund_code", ""))
                support_count = len(signal_summary.get("supporting_agents", []) or [])
                caution_count = len(signal_summary.get("caution_agents", []) or [])
                enriched["_has_conflict"] = bool(signal_summary.get("has_conflict"))
                enriched["_is_actionable"] = enriched.get("validated_action") not in {"hold", "not_applicable"}
                enriched["_consensus_text"] = "存在分歧" if enriched["_has_conflict"] else f"支持 {support_count} / 谨慎 {caution_count}"
                enriched["_action_label"] = _action_label(enriched.get("validated_action"))
                rows.append(enriched)
        realtime_map = {entry.get("fund_code"): entry for entry in (state.get("realtime", {}).get("items", []) or [])}
        review_items = [entry for batch in state.get("review_results_for_date", []) for entry in (batch.get("items", []) or [])]
        review_map = {entry.get("fund_code"): entry for entry in review_items}
        tactical_count = len(state.get("validated", {}).get("tactical_actions", []) or [])
        dca_count = len(state.get("validated", {}).get("dca_actions", []) or [])
        hold_count = len(state.get("validated", {}).get("hold_actions", []) or [])
        conflict_count = sum(1 for row in rows if row.get("_has_conflict"))
        actionable_count = sum(1 for row in rows if row.get("_is_actionable"))
        metrics = [
            MetricViewModel("总建议", str(len(rows)), "全部建议与观察项", "accent"),
            MetricViewModel("可执行", str(actionable_count), "非观察动作数量", "success" if actionable_count else "warning"),
            MetricViewModel("分歧", str(conflict_count), "委员会存在分歧的基金", "warning" if conflict_count else "success"),
            MetricViewModel("观察项", str(hold_count), "今天继续等待的基金", "info"),
        ]
        meta = f"建议 {len(rows)} 条 | 战术 {tactical_count} | 定投 {dca_count} | 观察 {hold_count}"
        return ResearchViewModel(meta=meta, metrics=metrics, rows=rows, aggregate=aggregate, realtime_map=realtime_map, review_map=review_map)

    def build_realtime_view_model(self, snapshot: DesktopSnapshot) -> RealtimeViewModel:
        state = snapshot.state
        realtime = state.get("live_realtime", {}) or state.get("realtime", {}) or {}
        realtime_date = state.get("live_realtime_date", "") or state.get("realtime_date", "") or "暂无"
        items = list(realtime.get("items", []) or [])
        stale_count = sum(1 for item in items if item.get("stale"))
        anomaly_max = max((float(item.get("anomaly_score", 0.0) or 0.0) for item in items), default=0.0)
        anomaly_top = next((item for item in items if float(item.get("anomaly_score", 0.0) or 0.0) == anomaly_max), {})
        high_confidence = sum(1 for item in items if float(item.get("confidence", 0.0) or 0.0) >= 0.7)
        metrics = [
            MetricViewModel("实时项目", str(len(items)), f"快照 {realtime_date}", "accent"),
            MetricViewModel("陈旧数据", str(stale_count), "需要重点确认的项目", "warning" if stale_count else "success"),
            MetricViewModel("最高异常", num(anomaly_max, 2), anomaly_top.get("fund_name", "暂无"), "danger" if anomaly_max > 0 else "info"),
            MetricViewModel("高置信", str(high_confidence), "置信度不低于 0.70", "success" if high_confidence else "warning"),
        ]
        meta = f"实时项目 {len(items)} 条 | 快照 {realtime_date}"
        if snapshot.selected_date and realtime_date and snapshot.selected_date != realtime_date:
            meta += f" | 当前查看日期 {snapshot.selected_date}，实时页显示最新快照"
        summary_text = build_realtime_summary_text(realtime) if items else "暂无实时估值摘要。"
        return RealtimeViewModel(meta=meta, metrics=metrics, items=items, summary_text=summary_text)

    def build_agents_view_model(self, snapshot: DesktopSnapshot) -> AgentsViewModel:
        aggregate = snapshot.state.get("aggregate", {}) or {}
        agents = aggregate.get("agents", {}) or {}
        roles = aggregate.get("agent_roles", {}) or {}
        ordered = aggregate.get("ordered_agents", []) or sorted(agents.keys())
        rows = [{"agent_name": name, "role": roles.get(name, "未知"), **(agents.get(name, {}) or {})} for name in ordered]
        failed = len(aggregate.get("failed_agents", []) or [])
        degraded = len(aggregate.get("degraded_agent_names", []) or [])
        ready = sum(1 for row in rows if row.get("status") == "ok")
        metrics = [
            MetricViewModel("智能体总数", str(len(rows)), "当前参与聚合的 Agent 数量", "accent"),
            MetricViewModel("正常", str(ready), "状态为 ok", "success" if ready else "warning"),
            MetricViewModel("降级", str(degraded), "进入降级兜底的 Agent", "warning" if degraded else "success"),
            MetricViewModel("失败", str(failed), "需要排查的 Agent", "danger" if failed else "success"),
        ]
        meta = f"智能体 {len(rows)} 个 | 失败 {failed} | 降级 {degraded}"
        return AgentsViewModel(meta=meta, metrics=metrics, rows=rows, aggregate=aggregate)

    def build_review_view_model(self, snapshot: DesktopSnapshot) -> ReviewViewModel:
        state = snapshot.state
        batches = state.get("review_results_for_date", []) or []
        memory = state.get("review_memory", {}) or {}
        long_memory = state.get("long_memory", {}) or {}
        long_memory_items = list(long_memory.get("items", []) or [])
        pending_items = list((state.get("long_memory_pending", {}) or {}).get("items", []) or [])
        cycle = state.get("learning_cycle", {}) or {}
        ledger = state.get("memory_ledger", {}) or {}
        replay_items = list(state.get("replay_experiments", []) or [])
        summary_text = build_learning_summary_text(snapshot.selected_date, cycle, ledger, replay_items, memory)
        detail_text = state.get("learning_report") or state.get("review_report") or build_learning_detail_fallback(snapshot.selected_date, cycle, ledger, batches)
        ledger_summary = ledger.get("summary", {}) or {}
        core_rules = [item for item in (ledger.get("rules", []) or []) if item.get("stage") in {"core_permanent", "permanent"} and item.get("status") == "active"]
        strategic_rules = [item for item in (ledger.get("rules", []) or []) if item.get("stage") == "strategic" and item.get("status") == "active"]
        core_lines = [_rule_line(item) for item in core_rules[:12]]
        strategic_lines = [_rule_line(item) for item in strategic_rules[:8]]
        replay_lines = [
            (
                f"{item.get('experiment_id', '')} | 模式 {item.get('mode', '')} | "
                f"变化天数 {item.get('changed_days', 0)} | 边际变化 {item.get('edge_delta_total', 0.0)} | "
                f"已写入学习 {'是' if item.get('applied_to_learning') else '否'}"
            )
            for item in replay_items[:6]
        ]
        metrics = [
            MetricViewModel("复盘批次", str(cycle.get("batch_count", len(batches))), "当日学习批次", "accent"),
            MetricViewModel("战略规则", str(ledger_summary.get("strategic", 0)), "系统可自动升级到战略层", "info"),
            MetricViewModel("永久规则", str(ledger_summary.get("permanent", 0)), "已由用户确认的规则", "success"),
            MetricViewModel("核心规则", str(ledger_summary.get("core_permanent", 0)), "兼容旧核心规则", "warning" if ledger_summary.get("core_permanent", 0) == 0 else "accent"),
        ]
        meta = (
            f"日期 {snapshot.selected_date} | 学习批次 {cycle.get('batch_count', len(batches))} | "
            f"核心 {ledger_summary.get('core_permanent', 0)} | 永久 {ledger_summary.get('permanent', 0)} | "
            f"战略 {ledger_summary.get('strategic', 0)}"
        )
        return ReviewViewModel(
            meta=meta,
            metrics=metrics,
            summary_text=summary_text,
            detail_text=detail_text,
            core_lines=core_lines,
            strategic_lines=strategic_lines,
            replay_lines=replay_lines,
            replay_items=replay_items,
            fund_memory_lines=_memory_lines(long_memory_items, "fund"),
            market_memory_lines=_memory_lines(long_memory_items, "market"),
            execution_memory_lines=_memory_lines(long_memory_items, "execution"),
            pending_memory_lines=_memory_lines(pending_items, ""),
            pending_memory_items=pending_items,
            dates=snapshot.dates,
            selected_date=snapshot.selected_date,
        )

    def build_runtime_view_model(self, task_status: dict[str, dict], active_job_name: str) -> RuntimeViewModel:
        cards = {
            key: f"状态 {value.get('status', '未知')} | 上次运行 {value.get('last_run_at', '暂无')}"
            for key, value in task_status.items()
        }
        runtime_parts = [f"{key}={value.get('status', '未知')}" for key, value in task_status.items()]
        if active_job_name:
            runtime_parts.append(f"当前任务={active_job_name}")
        return RuntimeViewModel(
            banner=" | ".join(runtime_parts) if runtime_parts else "运行控制台：当前没有任务。",
            cards=cards,
        )


DesktopStateService = WorkbenchStateService


def _summarize_state_clean(state: dict[str, Any]) -> dict[str, Any]:
    validated = state.get("validated", {}) or {}
    aggregate = state.get("aggregate", {}) or {}
    failed = aggregate.get("failed_agents", []) or aggregate.get("failed_agent_names", []) or []
    return {
        "selected_date": state.get("selected_date", "") or "",
        "advice_mode": validated.get("advice_mode") or state.get("advice_mode") or "research",
        "decision_source": validated.get("decision_source") or aggregate.get("decision_source") or "本地结果",
        "transport_name": validated.get("transport_name") or aggregate.get("transport_name") or "",
        "advice_is_fallback": bool(validated.get("is_fallback") or aggregate.get("is_fallback")),
        "failed_agent_names": failed,
        "preflight_status": (state.get("preflight", {}) or {}).get("status", "unknown"),
    }


def _safe_lines(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [line.strip(" -") for line in value.splitlines() if line.strip()]
    return [str(item).strip(" -") for item in value if str(item).strip()]


def _action_label(action: Any) -> str:
    mapping = {
        "buy": "买入",
        "add": "加仓",
        "sell": "卖出",
        "reduce": "减仓",
        "hold": "观察",
        "scheduled_dca": "计划定投",
        "planned_dca": "计划定投",
        "not_applicable": "不适用",
        "switch": "转换",
    }
    return mapping.get(str(action or "").strip(), str(action or "观察"))


def _action_line(item: dict[str, Any]) -> str:
    name = item.get("fund_name") or item.get("fund_code") or "未知基金"
    action = _action_label(item.get("validated_action") or item.get("action"))
    amount = item.get("validated_amount") or item.get("amount") or 0
    reason = item.get("thesis") or item.get("reason") or ""
    if amount:
        return f"{name}: {action} {amount}。{reason}"
    return f"{name}: {action}。{reason}"


def _dashboard_detail(summary: dict[str, Any], validated: dict[str, Any], exposure: dict[str, Any], changes: list[str], alerts: list[str]) -> str:
    lines = [
        "今日工作台摘要",
        f"- 建议模式: {summary.get('advice_mode', '未知')}",
        f"- 决策源: {summary.get('decision_source', '未知')}",
        f"- 战术动作: {len(validated.get('tactical_actions', []) or [])}",
        f"- 定投动作: {len(validated.get('dca_actions', []) or [])}",
        f"- 观察动作: {len(validated.get('hold_actions', []) or [])}",
    ]
    largest_style = (exposure.get("largest_style_group") or {}).get("name")
    if largest_style:
        lines.append(f"- 最大风格暴露: {largest_style}")
    if changes:
        lines.append("建议变化:")
        lines.extend(f"- {line}" for line in changes[:6])
    if alerts:
        lines.append("风险提醒:")
        lines.extend(f"- {line}" for line in alerts[:6])
    return "\n".join(lines)


def _rule_line(item: dict[str, Any]) -> str:
    return (
        f"{item.get('title', '')} | 支持 {item.get('support_score', item.get('support_count', 0))} | "
        f"反例 {item.get('contradiction_score', item.get('contradiction_count', 0))} | "
        f"置信度 {item.get('confidence', 0)}"
    )


def _memory_lines(items: list[dict[str, Any]], domain: str) -> list[str]:
    rows = [item for item in items if not domain or item.get("domain") == domain]
    return [
        f"{item.get('title', '')} | {item.get('status', '')} | 置信度 {item.get('confidence', 0)}"
        for item in rows[:12]
    ]
