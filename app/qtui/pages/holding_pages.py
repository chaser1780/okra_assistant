from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSplitter, QVBoxLayout, QWidget

from portfolio_exposure import analyze_portfolio_exposure
from ui_support import money, num, pct

from ..charts import TimeSeriesChart
from ..history import RANGE_LABELS, collect_benchmark_history, collect_holding_history, collect_portfolio_history, collect_proxy_history, collect_quote_history, collect_trade_markers, load_benchmark_mapping, stage_return
from ..theme import QT
from ..widgets import FilterableTablePage, MetricCard, SectionBox, bullet_lines, make_browser, set_browser_text


class HoldingsTrendPage(QWidget):
    def __init__(self):
        super().__init__()
        self.state: dict = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{QT['text_soft']};")
        self.range_combo = QComboBox()
        self.range_combo.addItems(RANGE_LABELS)
        self.range_combo.setCurrentText("近6月")
        top_row.addWidget(self.meta, 1)
        top_row.addWidget(QLabel("时间范围"))
        top_row.addWidget(self.range_combo)
        layout.addLayout(top_row)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(10)
        self.metric_cards = [MetricCard() for _ in range(4)]
        for idx, card in enumerate(self.metric_cards):
            metric_grid.addWidget(card, 0, idx)
        layout.addLayout(metric_grid)

        charts_split = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.total_chart = TimeSeriesChart("组合总资产走势")
        self.pnl_chart = TimeSeriesChart("组合累计盈亏走势")
        self.return_chart = TimeSeriesChart("组合收益率走势")
        left_layout.addWidget(self.total_chart, 2)
        left_layout.addWidget(self.pnl_chart, 1)
        left_layout.addWidget(self.return_chart, 1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.holding_table = FilterableTablePage("持仓基金", ["代码", "基金", "市值", "收益率", "占比"], show_summary=False, show_detail=False)
        self.open_button = self.holding_table.enable_open("进入基金详情", lambda row: None)
        right_layout.addWidget(self.holding_table, 1)

        charts_split.addWidget(left)
        charts_split.addWidget(right)
        charts_split.setSizes([900, 520])
        layout.addWidget(charts_split, 1)

        self.range_combo.currentTextChanged.connect(self._refresh_visuals)

    def set_open_callback(self, handler) -> None:
        self.holding_table.open_handler = handler

    def refresh_data(self, home, state: dict) -> None:
        self.state = state
        self.home = home
        self._refresh_visuals()

    def _refresh_visuals(self) -> None:
        if not getattr(self, "state", None):
            return
        range_label = self.range_combo.currentText()
        portfolio_history = collect_portfolio_history(self.home, range_label)
        trade_markers = collect_trade_markers(self.home, None, range_label)
        exposure = self.state.get("llm_context", {}).get("exposure_summary") or analyze_portfolio_exposure(self.state.get("portfolio", {}), self.state.get("strategy", {}))
        total_points = portfolio_history.get("total_value", [])
        pnl_points = portfolio_history.get("holding_pnl", [])
        return_points = portfolio_history.get("holding_return_pct", [])
        self.meta.setText(
            f"查看日 {self.state.get('selected_date', '')} | 范围 {range_label} | "
            f"组合总资产 {money(self.state.get('portfolio', {}).get('total_value', 0))}"
        )
        self.metric_cards[0].set_content("总资产", money(self.state.get("portfolio", {}).get("total_value", 0)), "当前组合市值", tone="accent")
        self.metric_cards[1].set_content("累计盈亏", money(self.state.get("portfolio", {}).get("holding_pnl", 0)), "当前组合盈亏", tone="danger" if float(self.state.get("portfolio", {}).get("holding_pnl", 0) or 0) < 0 else "success")
        self.metric_cards[2].set_content("区间收益", stage_return(portfolio_history.get("total_value_normalized", [])), "相对区间起点", tone="info")
        self.metric_cards[3].set_content("持仓基金", str(len(self.state.get("portfolio", {}).get("funds", []) or [])), "当前持仓数量", tone="warning")
        coverage = f"{total_points[0].date} -> {total_points[-1].date}" if total_points else "暂无覆盖区间"
        self.total_chart.set_series(
            "组合总资产走势",
            [("总资产", total_points)],
            percent=False,
            meta_text=f"来源：portfolio_state snapshots | 区间：{coverage}",
            trade_markers=trade_markers,
        )
        pnl_coverage = f"{pnl_points[0].date} -> {pnl_points[-1].date}" if pnl_points else "暂无覆盖区间"
        self.pnl_chart.set_series("组合累计盈亏走势", [("累计盈亏", pnl_points)], percent=False, meta_text=f"来源：portfolio_state snapshots | 区间：{pnl_coverage}")
        return_coverage = f"{return_points[0].date} -> {return_points[-1].date}" if return_points else "暂无覆盖区间"
        self.return_chart.set_series("组合收益率走势", [("收益率", return_points)], percent=True, meta_text=f"来源：portfolio_state snapshots | 区间：{return_coverage}")

        funds = self.state.get("portfolio", {}).get("funds", []) or []
        total_value = float(self.state.get("portfolio", {}).get("total_value", 0) or 0)
        rows = []
        for fund in funds:
            current_value = float(fund.get("current_value", 0) or 0)
            rows.append({
                "fund_code": fund.get("fund_code", ""),
                "fund_name": fund.get("fund_name", ""),
                "current_value": current_value,
                "holding_return_pct": float(fund.get("holding_return_pct", 0) or 0),
                "weight_pct": round((current_value / total_value) * 100, 2) if total_value > 0 else 0.0,
            })
        rows.sort(key=lambda item: item.get("current_value", 0), reverse=True)
        self.holding_table.configure(
            detail_builder=lambda row: f"{row.get('fund_name')}\\n市值：{money(row.get('current_value', 0))}\\n收益率：{pct(row.get('holding_return_pct', 0), 2)}\\n占比：{pct(row.get('weight_pct', 0), 2)}",
            cells_builder=lambda row: [row.get("fund_code", ""), row.get("fund_name", ""), money(row.get("current_value", 0)), pct(row.get("holding_return_pct", 0), 2), pct(row.get("weight_pct", 0), 2)],
            row_key_builder=lambda row: row.get("fund_code", ""),
        )
        self.holding_table.load_rows(f"持仓基金 {len(rows)} 只", rows)


class FundDetailPage(QWidget):
    def __init__(self):
        super().__init__()
        self.state: dict = {}
        self.fund_code = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        self.back_button = QPushButton("← 返回")
        self.title = QLabel("基金详情")
        self.title.setStyleSheet(f"color:{QT['text']}; font-size:16px; font-weight:700;")
        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{QT['text_soft']};")
        self.range_combo = QComboBox()
        self.range_combo.addItems(RANGE_LABELS)
        self.range_combo.setCurrentText("近6月")
        top_row.addWidget(self.back_button)
        top_row.addWidget(self.title)
        top_row.addStretch(1)
        top_row.addWidget(self.meta)
        top_row.addSpacing(8)
        top_row.addWidget(QLabel("时间范围"))
        top_row.addWidget(self.range_combo)
        layout.addLayout(top_row)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(10)
        self.metric_cards = [MetricCard() for _ in range(4)]
        for idx, card in enumerate(self.metric_cards):
            metric_grid.addWidget(card, 0, idx)
        layout.addLayout(metric_grid)

        charts_split = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.nav_chart = TimeSeriesChart("基金净值历史")
        self.change_chart = TimeSeriesChart("日涨跌走势")
        self.compare_chart = TimeSeriesChart("基金 vs 代理（归一化）")
        left_layout.addWidget(self.nav_chart, 2)
        left_layout.addWidget(self.change_chart, 1)
        left_layout.addWidget(self.compare_chart, 1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.holding_chart = TimeSeriesChart("我的持仓收益率走势")
        self.info_box = SectionBox("基金信息与说明")
        self.info_view = make_browser()
        self.info_box.body.addWidget(self.info_view)
        right_layout.addWidget(self.holding_chart, 1)
        right_layout.addWidget(self.info_box, 1)

        charts_split.addWidget(left)
        charts_split.addWidget(right)
        charts_split.setSizes([900, 520])
        layout.addWidget(charts_split, 1)

        self.range_combo.currentTextChanged.connect(self._refresh_visuals)

    def refresh_data(self, home, state: dict, fund_code: str) -> None:
        self.home = home
        self.state = state
        self.fund_code = fund_code
        self._refresh_visuals()

    def _refresh_visuals(self) -> None:
        if not self.fund_code:
            return
        range_label = self.range_combo.currentText()
        quote_history = collect_quote_history(self.home, self.fund_code, range_label)
        benchmark_map = load_benchmark_mapping(self.home, self.fund_code)
        benchmark_history = collect_benchmark_history(self.home, benchmark_map.get("benchmark_key", ""), range_label)
        proxy_history = collect_proxy_history(self.home, self.fund_code, range_label)
        holding_history = collect_holding_history(self.home, self.fund_code, range_label)
        trade_markers = collect_trade_markers(self.home, self.fund_code, range_label)
        fund = next((item for item in (self.state.get("portfolio", {}).get("funds", []) or []) if item.get("fund_code") == self.fund_code), {})
        watch = next((item for item in (self.state.get("watchlist", {}).get("funds", []) or []) if item.get("code") == self.fund_code), {})
        self.title.setText(fund.get("fund_name", self.fund_code))
        self.meta.setText(self.fund_code)
        self.metric_cards[0].set_content("当前市值", money(fund.get("current_value", 0)), "我的持仓", tone="accent")
        self.metric_cards[1].set_content("持仓收益率", pct(fund.get("holding_return_pct", 0), 2), "当前持仓收益", tone="success" if float(fund.get("holding_return_pct", 0) or 0) >= 0 else "danger")
        self.metric_cards[2].set_content("区间净值", stage_return(quote_history.get("nav_normalized", [])), "净值区间变化", tone="info")
        self.metric_cards[3].set_content("基准区间", stage_return(benchmark_history.get("normalized", [])), benchmark_map.get("benchmark_name", "暂无基准"), tone="warning")

        nav_points = quote_history.get("nav", [])
        nav_meta = f"来源：{quote_history.get('source', 'unknown')} | 区间：{nav_points[0].date} -> {nav_points[-1].date}" if nav_points else f"来源：{quote_history.get('source', 'unknown')}"
        self.nav_chart.set_series("基金净值历史", [("基金净值", nav_points)], percent=False, meta_text=nav_meta, trade_markers=trade_markers)
        self.change_chart.set_series(
            "日涨跌 / 阶段收益",
            [
                ("日涨跌", quote_history.get("day_change_pct", [])),
                ("近1周收益", quote_history.get("week_change_pct", [])),
                ("近1月收益", quote_history.get("month_change_pct", [])),
            ],
            percent=True,
            meta_text=f"来源：{quote_history.get('source', 'unknown')} | 展示：日涨跌 / 1周 / 1月",
        )
        compare_series = [("基金净值", quote_history.get("nav_normalized", []))]
        if benchmark_history.get("normalized"):
            compare_series.append((benchmark_map.get("benchmark_name", "基准"), benchmark_history.get("normalized", [])))
        if proxy_history.get("normalized"):
            compare_series.append(("代理", proxy_history.get("normalized", [])))
        compare_meta = f"基金：{quote_history.get('source', 'unknown')} | 基准：{benchmark_history.get('source', 'unknown')} | 代理：{proxy_history.get('source', 'unknown')}"
        self.compare_chart.set_series("基金 vs 基准 / 代理（归一化）", compare_series, percent=False, meta_text=compare_meta)
        holding_points = holding_history.get("holding_return_pct", [])
        holding_meta = f"来源：portfolio_state snapshots | 区间：{holding_points[0].date} -> {holding_points[-1].date}" if holding_points else "来源：portfolio_state snapshots"
        self.holding_chart.set_series(
            "我的持仓收益率走势",
            [("持仓收益率", holding_points)],
            percent=True,
            meta_text=holding_meta,
            trade_markers=trade_markers,
        )

        info_lines = [
            f"基金代码：{self.fund_code}",
            f"基金名称：{fund.get('fund_name', '暂无')}",
            f"角色：{fund.get('role', '暂无')}",
            f"风格：{fund.get('style_group', '暂无')}",
            f"基准：{benchmark_map.get('benchmark_name') or watch.get('benchmark', '暂无')}",
            f"基准代码：{benchmark_map.get('benchmark_symbol', '暂无') or '暂无'}",
            f"代理：{fund.get('proxy_name', '暂无')}",
            f"当前份额：{num(fund.get('holding_units', 0), 4)}",
            f"成本金额：{money(fund.get('cost_basis_value', 0))}",
            f"当前市值：{money(fund.get('current_value', 0))}",
            f"当前盈亏：{money(fund.get('holding_pnl', 0))}",
            f"最新净值日期：{fund.get('last_valuation_date', '暂无')}",
            f"基金历史来源：{quote_history.get('source', 'unknown')}",
            f"基准历史来源：{benchmark_history.get('source', 'unknown')}",
            f"代理历史来源：{proxy_history.get('source', 'unknown')}",
        ]
        if not benchmark_history.get("normalized"):
            info_lines.append("基准历史对比：当前尚未同步正式 benchmark 历史时会显示为空。")
        if not proxy_history.get("normalized"):
            info_lines.append("代理历史对比：当前尚未同步正式 proxy 历史时会显示为空。")
        set_browser_text(self.info_view, bullet_lines(info_lines, "暂无信息"))
