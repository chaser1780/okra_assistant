from __future__ import annotations

from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QPushButton

from decision_support import summarize_fund_agent_signals
from ui_support import build_agent_detail_text, build_fund_detail_text, build_realtime_detail_text, build_realtime_summary_text, money, num, pct
from portfolio_exposure import analyze_portfolio_exposure

from ..theme import QT
from ..widgets import FilterableTablePage, RichTextPage, set_item_color


class PortfolioPage(RichTextPage):
    def __init__(self):
        super().__init__("组合配置", markdown=True)

    def refresh_data(self, state: dict) -> None:
        exposure = state.get("llm_context", {}).get("exposure_summary") or analyze_portfolio_exposure(state.get("portfolio", {}), state.get("strategy", {}))
        concentration = exposure.get("concentration_metrics", {}) or {}
        allocation_plan = exposure.get("allocation_plan", {}) or {}
        metrics = [
            ("总资产", money(state.get("portfolio", {}).get("total_value", 0)), state.get("portfolio", {}).get("portfolio_name", "暂无"), "accent"),
            ("再平衡", "需要" if allocation_plan.get("rebalance_needed") else "暂不", f"带宽 {pct(allocation_plan.get('rebalance_band_pct', 0), 2)}", "warning" if allocation_plan.get("rebalance_needed") else "success"),
            ("高波动主题", pct(concentration.get("high_volatility_theme_weight_pct", 0), 2), "短线风险预算", "danger"),
            ("防守缓冲", pct(concentration.get("defensive_buffer_weight_pct", 0), 2), "现金 / 债券占比", "success"),
        ]
        self.set_content(
            f"组合 {state.get('portfolio', {}).get('portfolio_name', '暂无')} | 总资产 {money(state.get('portfolio', {}).get('total_value', 0))}",
            state.get("portfolio_report") or "暂无组合报告。",
            metrics=metrics,
        )


class ResearchPage(FilterableTablePage):
    def __init__(self, shell=None):
        super().__init__("建议列表", ["代码", "基金", "动作", "金额", "共识", "执行"])
        self.shell = shell
        self.action_filter = self.add_filter_combo(["全部动作", "add", "reduce", "switch_out", "hold", "scheduled_dca"])
        self.status_filter = self.add_filter_combo(["全部状态", "pending", "partial", "executed", "not_applicable"])
        self.actionable_only = self.add_filter_check("仅看可执行")
        self.conflict_only = self.add_filter_check("仅看冲突")
        self.realtime_map: dict[str, dict] = {}
        self.review_map: dict[str, dict] = {}
        self.aggregate: dict = {}
        self.open_button = self.enable_open("进入基金详情", self._open_current_fund)
        self.configure(
            detail_builder=self._detail_builder,
            cells_builder=lambda row: [
                row.get("fund_code", ""),
                row.get("fund_name", ""),
                row.get("validated_action", ""),
                money(row.get("validated_amount", 0)),
                row.get("_consensus_text", ""),
                row.get("execution_status", ""),
            ],
            filter_handler=self._matches_filters,
            row_key_builder=lambda row: row.get("fund_code", ""),
            item_styler=self._style_item,
        )

    def bind_aux(self, realtime_map: dict[str, dict], review_map: dict[str, dict]) -> None:
        self.realtime_map = realtime_map
        self.review_map = review_map

    def _matches_filters(self, row: dict) -> bool:
        action = self.action_filter.currentText()
        status = self.status_filter.currentText()
        if action != "全部动作" and row.get("validated_action", "") != action:
            return False
        if status != "全部状态" and row.get("execution_status", "") != status:
            return False
        if self.actionable_only.isChecked() and not row.get("_is_actionable", False):
            return False
        if self.conflict_only.isChecked() and not row.get("_has_conflict", False):
            return False
        return True

    def _open_current_fund(self, row: dict) -> None:
        if self.shell:
            self.shell.open_fund_detail(row.get("fund_code", ""), source_key="research")

    def _detail_builder(self, row: dict) -> str:
        code = row.get("fund_code", "")
        return build_fund_detail_text(row, self.realtime_map.get(code), self.review_map.get(code), self.aggregate)

    def refresh_view_model(self, view_model) -> None:
        self.aggregate = view_model.aggregate
        self.bind_aux(view_model.realtime_map, view_model.review_map)
        self.set_metrics([(metric.title, metric.value, metric.body, metric.tone) for metric in view_model.metrics])
        self.load_rows(view_model.meta, view_model.rows)

    def _style_item(self, row: dict, col: int, item: QStandardItem) -> None:
        action = row.get("validated_action", "")
        status = row.get("execution_status", "")
        if col == 2:
            if action in {"add", "scheduled_dca"}:
                set_item_color(item, QT["success"])
            elif action in {"reduce", "switch_out"}:
                set_item_color(item, QT["danger"])
        elif col == 4 and row.get("_consensus_text") == "conflict":
            set_item_color(item, QT["warning"])
        elif col == 5:
            if status == "executed":
                set_item_color(item, QT["success"])
            elif status == "partial":
                set_item_color(item, QT["warning"])
            elif status == "pending":
                set_item_color(item, QT["info"])


class RealtimePage(FilterableTablePage):
    def __init__(self, shell=None):
        super().__init__("实时收益", ["代码", "基金", "金额", "今日收益", "涨跌", "可信度", "模式"], show_summary=True, show_detail=True, split_sizes=(760, 460))
        self.shell = shell
        self.mode_filter = self.add_filter_combo(["全部模式", "estimate", "proxy", "official"])
        self.stale_only = self.add_filter_check("仅看陈旧")
        self.open_button = None
        self.refresh_button = None
        if self.shell is not None:
            self.refresh_button = QPushButton("刷新实时快照")
            self.toolbar.insertWidget(self.toolbar.count() - 1, self.refresh_button)
            self.refresh_button.clicked.connect(self.shell.run_realtime)
        self.configure(
            detail_builder=build_realtime_detail_text,
            cells_builder=lambda row: [row.get("fund_code", ""), row.get("fund_name", ""), money(row.get("estimated_position_value", row.get("base_position_value", 0))), money(row.get("estimated_intraday_pnl_amount", 0)), pct(row.get("effective_change_pct", 0), 2), num(row.get("confidence"), 2), row.get("mode", "")],
            filter_handler=self._matches_filters,
            row_key_builder=lambda row: row.get("fund_code", ""),
            item_styler=self._style_item,
        )

    def set_open_callback(self, handler) -> None:
        if self.open_button is None:
            self.open_button = self.enable_open("进入基金详情", handler)
        else:
            self.open_handler = handler

    def _matches_filters(self, row: dict) -> bool:
        mode = self.mode_filter.currentText()
        if mode != "全部模式" and row.get("mode", "") != mode:
            return False
        if self.stale_only.isChecked() and not row.get("stale"):
            return False
        return True

    def _style_item(self, row: dict, col: int, item: QStandardItem) -> None:
        pnl = float(row.get("estimated_intraday_pnl_amount", 0) or 0)
        if row.get("stale"):
            set_item_color(item, QT["warning"])
        if col in {3, 4}:
            if pnl > 0:
                set_item_color(item, QT["success"])
            elif pnl < 0:
                set_item_color(item, QT["danger"])

    def refresh_view_model(self, view_model) -> None:
        self.set_metrics([(metric.title, metric.value, metric.body, metric.tone) for metric in view_model.metrics])
        self.load_rows(view_model.meta, view_model.items, summary_text=view_model.summary_text)


class AgentsPage(FilterableTablePage):
    def __init__(self):
        super().__init__("智能体", ["阶段", "智能体", "状态", "置信度"])
        self.status_filter = self.add_filter_combo(["全部状态", "ok", "failed", "degraded", "unknown"])
        self.aggregate: dict = {}
        self.configure(
            detail_builder=lambda row: build_agent_detail_text(row.get("agent_name", ""), row, self.aggregate),
            cells_builder=lambda row: [row.get("role", ""), row.get("agent_name", ""), row.get("status", "unknown"), num((row.get("output", {}) or {}).get("confidence"), 2)],
            filter_handler=self._matches_filters,
            row_key_builder=lambda row: row.get("agent_name", ""),
            item_styler=self._style_item,
        )

    def _matches_filters(self, row: dict) -> bool:
        status = self.status_filter.currentText()
        return status == "全部状态" or row.get("status", "unknown") == status

    def _style_item(self, row: dict, col: int, item: QStandardItem) -> None:
        if col == 2:
            status = row.get("status", "unknown")
            if status == "ok":
                set_item_color(item, QT["success"])
            elif status == "failed":
                set_item_color(item, QT["danger"])
            elif status == "degraded":
                set_item_color(item, QT["warning"])

    def refresh_view_model(self, view_model) -> None:
        self.aggregate = view_model.aggregate
        self.set_metrics([(metric.title, metric.value, metric.body, metric.tone) for metric in view_model.metrics])
        self.load_rows(view_model.meta, view_model.rows)
