from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sys

try:
    from decision_support import summarize_fund_agent_signals
    from portfolio_exposure import analyze_portfolio_exposure
    from task_state import TASK_CARD_SPECS, build_task_card_text, current_task_result_info
    from ui_support import (
        build_action_change_lines,
        build_dashboard_alerts,
        build_dashboard_text,
        build_learning_detail_fallback,
        build_learning_summary_text,
        build_plain_language_summary,
        build_realtime_summary_text,
        load_state,
        load_validated_for_date,
        money,
        num,
        pct,
        previous_date,
        summarize_state,
        today_str,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from decision_support import summarize_fund_agent_signals
    from portfolio_exposure import analyze_portfolio_exposure
    from task_state import TASK_CARD_SPECS, build_task_card_text, current_task_result_info
    from ui_support import (
        build_action_change_lines,
        build_dashboard_alerts,
        build_dashboard_text,
        build_learning_detail_fallback,
        build_learning_summary_text,
        build_plain_language_summary,
        build_realtime_summary_text,
        load_state,
        load_validated_for_date,
        money,
        num,
        pct,
        previous_date,
        summarize_state,
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
    dates: list[str]
    selected_date: str


@dataclass(frozen=True)
class RuntimeViewModel:
    banner: str
    cards: dict[str, str]


class DesktopStateService:
    def __init__(self, home: Path):
        self.home = home

    def load_snapshot(self, selected: str | None = None) -> DesktopSnapshot:
        state = load_state(self.home, selected)
        summary = summarize_state(state)
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
            f"查看日 {snapshot.summary.get('selected_date', snapshot.selected_date)} | "
            f"建议模式 {snapshot.summary.get('advice_mode', 'unknown')} | "
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
        alerts = build_dashboard_alerts({**state, "home": self.home})
        prev_date = previous_date(state.get("dates", []) or [], snapshot.selected_date)
        prev_validated = load_validated_for_date(self.home, prev_date)
        changes = build_action_change_lines(validated, prev_validated, prev_date)
        plain = build_plain_language_summary(snapshot.summary, validated, exposure, alerts)
        tactical = list(validated.get("tactical_actions", []) or [])
        dca = list(validated.get("dca_actions", []) or [])
        holds = list(validated.get("hold_actions", []) or [])
        top = tactical[0] if tactical else (dca[0] if dca else {})
        market = validated.get("market_view", {}) or {}
        decision_source = snapshot.summary.get("decision_source", "") or "unknown"
        aggregate = state.get("aggregate", {}) or {}
        committee = validated.get("committee", {}) or aggregate.get("committee", {}) or {}
        provider_text = self._provider_health_text(state)
        committee_text = self._committee_text(committee)
        metrics = [
            MetricViewModel("今日主动作", top.get("fund_name", "暂无"), top.get("thesis", "今天没有需要立刻执行的主动动作。"), "accent"),
            MetricViewModel("市场状态", market.get("regime", "暂无"), market.get("summary", "等待市场摘要。"), "info"),
            MetricViewModel("建议模式", snapshot.summary.get("advice_mode", "unknown"), f"决策源 {decision_source} | 通道 {snapshot.summary.get('transport_name', '暂无') or '暂无'}", "warning" if snapshot.summary.get("advice_is_fallback") else "success"),
            MetricViewModel("风险提醒", f"{len(alerts)} 条" if alerts else "稳定", alerts[0] if alerts else "暂无高优先级风险提醒。", "danger" if alerts else "success"),
        ]
        focus_lines = [
            f"{item.get('fund_name', item.get('fund_code', ''))}：{item.get('validated_action')} {item.get('validated_amount', 0)}"
            for item in (tactical[:3] + dca[:2])
        ]
        meta = (
            f"查看日 {snapshot.selected_date} | 持仓快照 {state.get('portfolio_date', '暂无')} | "
            f"建议 {len(tactical) + len(dca)} 条 | 观察 {len(holds)} 条 | "
            f"失败智能体 {len(snapshot.summary.get('failed_agent_names', []))}"
        )
        return DashboardViewModel(
            meta=meta,
            metrics=metrics,
            focus_text="\n".join(f"- {line}" for line in focus_lines) if focus_lines else "- 暂无需要立刻执行的动作",
            market_text="\n".join(f"- {line}" for line in ([market.get("summary", "暂无市场摘要")] + alerts[:5] if alerts or market.get("summary") else ["暂无额外风险提示"])),
            change_text="\n".join(changes or ["- 暂无明显变化"]),
            summary_text="\n".join(f"- {line}" for line in plain) if plain else "- 暂无摘要",
            detail_text=build_dashboard_text(snapshot.summary, validated, state.get("portfolio", {}), state.get("portfolio_report", ""), exposure, changes, alerts, plain),
            primary_fund_code=str(top.get("fund_code", "") or ""),
            committee_text=committee_text,
            provider_text=provider_text,
        )

    def _provider_health_text(self, state: dict[str, Any]) -> str:
        rows = []
        for label, payload in (
            ("组合快照", state.get("portfolio", {}) or {}),
            ("实时估值", state.get("realtime", {}) or {}),
            ("Agent 聚合", state.get("aggregate", {}) or {}),
        ):
            meta = payload.get("provider_metadata", {}) if isinstance(payload, dict) else {}
            if meta:
                rows.append(f"- {label}: {meta.get('provider_name', 'unknown')} | {meta.get('freshness_status', 'unknown')} | {meta.get('confidence', 'low')}")
        source_health = state.get("source_health", {}) or {}
        for item in (source_health.get("items", []) or [])[:4]:
            rows.append(f"- {item.get('source_key', '')}: status={item.get('status', 'unknown')} | stale={item.get('stale_count', 0)} | errors={item.get('error_count', 0)}")
        return "\n".join(rows or ["- 暂无结构化数据源健康信息；请先运行日内链路。"])

    def _committee_text(self, committee: dict[str, Any]) -> str:
        if not committee:
            return "- 暂无投委会结构化摘要；请先运行多 Agent 研究。"
        lines = [f"- 来源：{committee.get('decision_source', 'unknown')} | 置信度：{committee.get('committee_confidence', 'unknown')}"]
        for label, key in (("多头", "bull_case"), ("空头", "bear_case"), ("风控否决", "risk_vetoes")):
            items = committee.get(key, []) or []
            lines.append(f"- {label}: {len(items)} 条")
            for item in items[:2]:
                lines.append(f"  - {item.get('fund_code', '')}: {item.get('thesis', item.get('reason', ''))}")
        manager = committee.get("manager_decision", {}) or {}
        if manager.get("summary"):
            lines.append(f"- 研究经理：{manager.get('summary')}")
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
                enriched["_consensus_text"] = "conflict" if enriched["_has_conflict"] else f"{support_count}/{caution_count}"
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
            MetricViewModel("可执行", str(actionable_count), "非 hold 动作数量", "success" if actionable_count else "warning"),
            MetricViewModel("冲突", str(conflict_count), "委员会存在分歧的基金", "warning" if conflict_count else "success"),
            MetricViewModel("观察项", str(hold_count), "今天继续等待的基金", "info"),
        ]
        meta = f"建议 {len(rows)} 条 | tactical {tactical_count} | dca {dca_count} | hold {hold_count}"
        return ResearchViewModel(meta=meta, metrics=metrics, rows=rows, aggregate=aggregate, realtime_map=realtime_map, review_map=review_map)

    def build_realtime_view_model(self, snapshot: DesktopSnapshot) -> RealtimeViewModel:
        state = snapshot.state
        realtime = state.get("live_realtime", {}) or state.get("realtime", {}) or {}
        realtime_date = state.get("live_realtime_date", "") or state.get("realtime_date", "暂无")
        items = list(realtime.get("items", []) or [])
        stale_count = sum(1 for item in items if item.get("stale"))
        anomaly_max = max((float(item.get("anomaly_score", 0.0) or 0.0) for item in items), default=0.0)
        anomaly_top = next((item for item in items if float(item.get("anomaly_score", 0.0) or 0.0) == anomaly_max), {})
        high_confidence = sum(1 for item in items if float(item.get("confidence", 0.0) or 0.0) >= 0.7)
        metrics = [
            MetricViewModel("实时项", str(len(items)), f"快照 {realtime_date}", "accent"),
            MetricViewModel("陈旧数据", str(stale_count), "需要重点确认时效", "warning" if stale_count else "success"),
            MetricViewModel("最高异常", num(anomaly_max, 2), anomaly_top.get("fund_name", "暂无"), "danger" if anomaly_max > 0 else "info"),
            MetricViewModel("高置信", str(high_confidence), "confidence >= 0.70", "success" if high_confidence else "warning"),
        ]
        meta = f"实时项 {len(items)} 条 | 快照 {realtime_date}"
        if snapshot.selected_date and realtime_date and snapshot.selected_date != realtime_date:
            meta += f" | 当前查看日 {snapshot.selected_date}（实时页显示最新快照）"
        return RealtimeViewModel(meta=meta, metrics=metrics, items=items, summary_text=build_realtime_summary_text(realtime))

    def build_agents_view_model(self, snapshot: DesktopSnapshot) -> AgentsViewModel:
        aggregate = snapshot.state.get("aggregate", {}) or {}
        agents = aggregate.get("agents", {}) or {}
        roles = aggregate.get("agent_roles", {}) or {}
        ordered = aggregate.get("ordered_agents", []) or sorted(agents.keys())
        rows = [{"agent_name": name, "role": roles.get(name, "unknown"), **(agents.get(name, {}) or {})} for name in ordered]
        failed = len(aggregate.get("failed_agents", []) or [])
        degraded = len(aggregate.get("degraded_agent_names", []) or [])
        ready = sum(1 for row in rows if row.get("status") == "ok")
        metrics = [
            MetricViewModel("智能体总数", str(len(rows)), "当前聚合中的 agent 数量", "accent"),
            MetricViewModel("正常", str(ready), "状态为 ok", "success" if ready else "warning"),
            MetricViewModel("降级", str(degraded), "degraded fallback", "warning" if degraded else "success"),
            MetricViewModel("失败", str(failed), "需要排查的 agent", "danger" if failed else "success"),
        ]
        meta = f"智能体 {len(rows)} 个 | 失败 {failed} | 降级 {degraded}"
        return AgentsViewModel(meta=meta, metrics=metrics, rows=rows, aggregate=aggregate)

    def build_review_view_model(self, snapshot: DesktopSnapshot) -> ReviewViewModel:
        state = snapshot.state
        batches = state.get("review_results_for_date", []) or []
        memory = state.get("review_memory", {}) or {}
        cycle = state.get("learning_cycle", {}) or {}
        ledger = state.get("memory_ledger", {}) or {}
        replay_items = list(state.get("replay_experiments", []) or [])
        summary_text = build_learning_summary_text(snapshot.selected_date, cycle, ledger, replay_items, memory)
        detail_text = state.get("learning_report") or state.get("review_report") or build_learning_detail_fallback(snapshot.selected_date, cycle, ledger, batches)
        ledger_summary = ledger.get("summary", {}) or {}
        core_rules = [item for item in (ledger.get("rules", []) or []) if item.get("stage") == "core_permanent" and item.get("status") == "active"]
        permanent_rules = [item for item in (ledger.get("rules", []) or []) if item.get("stage") == "permanent" and item.get("status") == "active"]
        strategic_rules = [item for item in (ledger.get("rules", []) or []) if item.get("stage") == "strategic" and item.get("status") == "active"]
        core_lines = [f"{item.get('title', '')} | support={item.get('support_score', 0)} | confidence={item.get('confidence', 0)}" for item in (core_rules[:6] + permanent_rules[:6])]
        strategic_lines = [f"{item.get('title', '')} | support={item.get('support_score', 0)} | contradiction={item.get('contradiction_score', 0)}" for item in strategic_rules[:8]]
        replay_lines = [
            f"{item.get('experiment_id', '')} | {item.get('mode', '')} | changed_days={item.get('changed_days', 0)} | edge_delta={item.get('edge_delta_total', 0.0)} | applied={'yes' if item.get('applied_to_learning') else 'no'}"
            for item in replay_items[:6]
        ]
        metrics = [
            MetricViewModel("Tonight", str(cycle.get("batch_count", len(batches))), "Learning batches", "accent"),
            MetricViewModel("Strategic", str(ledger_summary.get("strategic", 0)), "Active strategic rules", "info"),
            MetricViewModel("Permanent", str(ledger_summary.get("permanent", 0)), "Active permanent rules", "success"),
            MetricViewModel("Core", str(ledger_summary.get("core_permanent", 0)), "Core permanent rules", "warning" if ledger_summary.get("core_permanent", 0) == 0 else "accent"),
        ]
        meta = (
            f"Date {snapshot.selected_date} | learning batches {cycle.get('batch_count', len(batches))} | "
            f"core {ledger_summary.get('core_permanent', 0)} | permanent {ledger_summary.get('permanent', 0)} | strategic {ledger_summary.get('strategic', 0)}"
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
            dates=snapshot.dates,
            selected_date=snapshot.selected_date,
        )

    def build_runtime_view_model(self, task_status: dict[str, dict], active_job_name: str) -> RuntimeViewModel:
        cards = {key: build_task_card_text(key, task_status[key], current_task_result_info(self.home, key)) for key in ("intraday", "realtime", "nightly")}
        runtime_parts = [f"{TASK_CARD_SPECS[k]['title']}={task_status[k].get('status')}" for k in task_status]
        if active_job_name:
            runtime_parts.append(f"当前任务={active_job_name}")
        return RuntimeViewModel(
            banner=" | ".join(runtime_parts) if runtime_parts else "运行控制台：当前没有任务。",
            cards=cards,
        )
