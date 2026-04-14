from __future__ import annotations

from PySide6.QtGui import QStandardItem

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
    def __init__(self):
        super().__init__("建议列表", ["代码", "基金", "动作", "金额", "执行"])
        self.action_filter = self.add_filter_combo(["全部动作", "add", "reduce", "switch_out", "hold", "scheduled_dca"])
        self.status_filter = self.add_filter_combo(["全部状态", "pending", "partial", "executed", "not_applicable"])
        self.realtime_map: dict[str, dict] = {}
        self.review_map: dict[str, dict] = {}
        self.configure(
            detail_builder=self._detail_builder,
            cells_builder=lambda row: [row.get("fund_code", ""), row.get("fund_name", ""), row.get("validated_action", ""), money(row.get("validated_amount", 0)), row.get("execution_status", "")],
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
        return True

    def _detail_builder(self, row: dict) -> str:
        code = row.get("fund_code", "")
        return build_fund_detail_text(row, self.realtime_map.get(code), self.review_map.get(code))

    def refresh_data(self, state: dict) -> None:
        items = []
        for section in ("tactical_actions", "dca_actions", "hold_actions"):
            for item in state.get("validated", {}).get(section, []) or []:
                enriched = dict(item)
                enriched["_section"] = section
                items.append(enriched)
        realtime_map = {entry.get("fund_code"): entry for entry in (state.get("realtime", {}).get("items", []) or [])}
        review_items = [entry for batch in state.get("review_results_for_date", []) for entry in (batch.get("items", []) or [])]
        review_map = {entry.get("fund_code"): entry for entry in review_items}
        self.bind_aux(realtime_map, review_map)
        tactical_count = len(state.get("validated", {}).get("tactical_actions", []) or [])
        dca_count = len(state.get("validated", {}).get("dca_actions", []) or [])
        hold_count = len(state.get("validated", {}).get("hold_actions", []) or [])
        self.load_rows(f"建议 {len(items)} 条 | tactical {tactical_count} | dca {dca_count} | hold {hold_count}", items)

    def _style_item(self, row: dict, col: int, item: QStandardItem) -> None:
        action = row.get("validated_action", "")
        status = row.get("execution_status", "")
        if col == 2:
            if action in {"add", "scheduled_dca"}:
                set_item_color(item, QT["success"])
            elif action in {"reduce", "switch_out"}:
                set_item_color(item, QT["danger"])
        elif col == 4:
            if status == "executed":
                set_item_color(item, QT["success"])
            elif status == "partial":
                set_item_color(item, QT["warning"])
            elif status == "pending":
                set_item_color(item, QT["info"])


class RealtimePage(FilterableTablePage):
    def __init__(self):
        super().__init__("实时收益", ["代码", "基金", "金额", "今日收益", "涨跌", "可信度", "模式"], show_summary=True, show_detail=True, split_sizes=(760, 460))
        self.mode_filter = self.add_filter_combo(["全部模式", "estimate", "proxy", "official"])
        self.stale_only = self.add_filter_check("仅看陈旧")
        self.open_button = None
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

    def refresh_data(self, state: dict) -> None:
        items = state.get("realtime", {}).get("items", []) or []
        self.load_rows(
            f"实时项 {len(items)} 条 | 快照 {state.get('realtime_date', '暂无')}",
            items,
            summary_text=build_realtime_summary_text(state.get("realtime", {})),
        )


class AgentsPage(FilterableTablePage):
    def __init__(self):
        super().__init__("智能体", ["阶段", "智能体", "状态", "置信度"])
        self.status_filter = self.add_filter_combo(["全部状态", "ok", "failed", "degraded", "unknown"])
        self.configure(
            detail_builder=lambda row: build_agent_detail_text(row.get("agent_name", ""), row),
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

    def refresh_data(self, state: dict) -> None:
        aggregate = state.get("aggregate", {}) or {}
        agents = aggregate.get("agents", {}) or {}
        roles = aggregate.get("agent_roles", {}) or {}
        ordered = aggregate.get("ordered_agents", []) or sorted(agents.keys())
        rows = [{"agent_name": name, "role": roles.get(name, "unknown"), **(agents.get(name, {}) or {})} for name in ordered]
        self.load_rows(f"智能体 {len(rows)} 个 | 失败 {len(aggregate.get('failed_agents', []) or [])}", rows)
