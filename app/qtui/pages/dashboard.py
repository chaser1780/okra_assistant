from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from ui_support import (
    build_action_change_lines,
    build_dashboard_alerts,
    build_dashboard_text,
    build_plain_language_summary,
    load_validated_for_date,
    previous_date,
    summarize_state,
)
from portfolio_exposure import analyze_portfolio_exposure

from ..theme import QT
from ..widgets import MetricCard, SectionBox, bullet_lines, make_browser, set_browser_text


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{QT['text_soft']};")
        layout.addWidget(self.meta)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(10)
        metric_grid.setVerticalSpacing(10)
        self.metric_cards = [MetricCard() for _ in range(4)]
        for idx, card in enumerate(self.metric_cards):
            metric_grid.addWidget(card, idx // 2, idx % 2)
        layout.addLayout(metric_grid)

        sections = QGridLayout()
        sections.setHorizontalSpacing(10)
        sections.setVerticalSpacing(10)
        self.focus_box = SectionBox("今日关注")
        self.market_box = SectionBox("市场与风险")
        self.change_box = SectionBox("与上一期相比")
        self.summary_box = SectionBox("一句话摘要")
        self.focus_view = make_browser()
        self.market_view = make_browser()
        self.change_view = make_browser()
        self.summary_view = make_browser()
        self.focus_box.body.addWidget(self.focus_view)
        self.market_box.body.addWidget(self.market_view)
        self.change_box.body.addWidget(self.change_view)
        self.summary_box.body.addWidget(self.summary_view)
        sections.addWidget(self.focus_box, 0, 0)
        sections.addWidget(self.market_box, 0, 1)
        sections.addWidget(self.change_box, 1, 0)
        sections.addWidget(self.summary_box, 1, 1)
        layout.addLayout(sections)

        raw_box = SectionBox("工作台详情")
        self.raw_view = make_browser()
        raw_box.body.addWidget(self.raw_view)
        layout.addWidget(raw_box, 1)

    def refresh_data(self, home: Path, state: dict) -> None:
        summary = summarize_state(state)
        validated = state.get("validated", {})
        exposure = state.get("llm_context", {}).get("exposure_summary") or analyze_portfolio_exposure(state.get("portfolio", {}), state.get("strategy", {}))
        alerts = build_dashboard_alerts({**state, "home": home})
        prev_date = previous_date(state.get("dates", []), state.get("selected_date", ""))
        prev_validated = load_validated_for_date(home, prev_date)
        changes = build_action_change_lines(validated, prev_validated, prev_date)
        plain = build_plain_language_summary(summary, validated, exposure, alerts)
        tactical = validated.get("tactical_actions", []) or []
        dca = validated.get("dca_actions", []) or []
        holds = validated.get("hold_actions", []) or []
        top = tactical[0] if tactical else (dca[0] if dca else {})
        market = validated.get("market_view", {}) or {}
        self.meta.setText(
            f"查看日 {state.get('selected_date', '')} | "
            f"建议 {len(tactical) + len(dca)} 条 | 观察 {len(holds)} 条 | "
            f"失败智能体 {len(summary.get('failed_agent_names', []))}"
        )

        self.metric_cards[0].set_content("今日主动作", top.get("fund_name", "暂无"), top.get("thesis", "今天没有需要立刻执行的主动动作。"), tone="accent")
        self.metric_cards[1].set_content("市场状态", market.get("regime", "暂无"), market.get("summary", "等待市场摘要。"), tone="info")
        self.metric_cards[2].set_content("建议模式", summary.get("advice_mode", "unknown"), f"通道 {summary.get('transport_name', '暂无') or '暂无'}", tone="warning" if summary.get("advice_is_fallback") else "success")
        self.metric_cards[3].set_content("风险提醒", f"{len(alerts)} 条" if alerts else "稳定", alerts[0] if alerts else "暂无高优先级风险提醒。", tone="danger" if alerts else "success")

        focus_lines = []
        for item in (tactical[:3] + dca[:2]):
            focus_lines.append(f"{item.get('fund_name', item.get('fund_code', ''))}：{item.get('validated_action')} {item.get('validated_amount', 0)}")
        set_browser_text(self.focus_view, bullet_lines(focus_lines, "暂无需要立刻执行的动作"))

        market_lines = [market.get("summary", "暂无市场摘要")] + alerts[:5]
        set_browser_text(self.market_view, bullet_lines(market_lines, "暂无额外风险提示"))
        set_browser_text(self.change_view, "\n".join(changes or ["- 暂无明显变化"]))
        set_browser_text(self.summary_view, bullet_lines(plain, "暂无摘要"))
        set_browser_text(
            self.raw_view,
            build_dashboard_text(summary, validated, state.get("portfolio", {}), state.get("portfolio_report", ""), exposure, changes, alerts, plain),
        )
