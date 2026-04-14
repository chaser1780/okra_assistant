from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

try:
    from task_state import (
        TASK_CARD_SPECS,
        begin_task_status,
        build_task_card_text,
        current_task_result_info,
        finish_task_status,
        interpret_run_output_line,
        initial_task_status,
        update_task_elapsed,
        update_task_step,
    )
    from ui_prefs import load_ui_state, save_ui_state
    from ui_support import (
        build_action_change_lines,
        build_agent_detail_text,
        build_dashboard_alerts,
        build_dashboard_text,
        build_fund_detail_text,
        build_pipeline_command,
        build_plain_language_summary,
        build_preflight_command,
        build_realtime_command,
        build_realtime_detail_text,
        build_realtime_summary_text,
        build_review_detail_fallback,
        build_review_summary_text,
        build_runtime_env,
        build_settings_text,
        build_trade_command,
        build_trade_output_text,
        build_trade_preview_text,
        collect_dates,
        desktop_log_path,
        fix_text,
        historical_operating_metrics,
        load_state,
        load_validated_for_date,
        money,
        num,
        open_path,
        pct,
        previous_date,
        summarize_state,
        today_str,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from task_state import (
        TASK_CARD_SPECS,
        begin_task_status,
        build_task_card_text,
        current_task_result_info,
        finish_task_status,
        interpret_run_output_line,
        initial_task_status,
        update_task_elapsed,
        update_task_step,
    )
    from ui_prefs import load_ui_state, save_ui_state
    from ui_support import (
        build_action_change_lines,
        build_agent_detail_text,
        build_dashboard_alerts,
        build_dashboard_text,
        build_fund_detail_text,
        build_pipeline_command,
        build_plain_language_summary,
        build_preflight_command,
        build_realtime_command,
        build_realtime_detail_text,
        build_realtime_summary_text,
        build_review_detail_fallback,
        build_review_summary_text,
        build_runtime_env,
        build_settings_text,
        build_trade_command,
        build_trade_output_text,
        build_trade_preview_text,
        collect_dates,
        desktop_log_path,
        fix_text,
        historical_operating_metrics,
        load_state,
        load_validated_for_date,
        money,
        num,
        open_path,
        pct,
        previous_date,
        summarize_state,
        today_str,
    )

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "scripts")))
from portfolio_exposure import analyze_portfolio_exposure
from trade_constraints import build_trade_constraints


APP_TITLE = "okra 小助手"
DEFAULT_AGENT_HOME = Path(r"F:\okra_assistant")

QT = {
    "bg": "#070B10",
    "panel": "#0D131A",
    "surface": "#10161D",
    "surface_alt": "#151E28",
    "surface_soft": "#141C24",
    "line": "#24303D",
    "text": "#EEF4FB",
    "text_soft": "#A8B4C5",
    "muted": "#738194",
    "accent": "#4F81D7",
    "accent_deep": "#3D69B4",
    "accent_soft": "#16283F",
    "success": "#2EC27E",
    "success_soft": "#10251E",
    "warning": "#E6A34A",
    "warning_soft": "#2A1E10",
    "danger": "#F05D6C",
    "danger_soft": "#2C1418",
    "info": "#6EA8FF",
    "info_soft": "#122236",
    "console_bg": "#05080D",
    "console_text": "#D8E1EC",
}

NAV_ITEMS = [
    ("dash", "◈  总览"),
    ("portfolio", "▣  配置"),
    ("research", "◆  研究"),
    ("trade", "◉  交易"),
    ("review", "◎  复盘"),
    ("rt", "◌  实时"),
    ("agents", "◍  智能体"),
    ("runtime", "▤  运行"),
    ("settings", "◫  设置"),
]

STYLE = f"""
QMainWindow, QWidget {{ background:{QT["bg"]}; color:{QT["text"]}; font-family:"Microsoft YaHei UI"; font-size:10pt; }}
QFrame#Sidebar {{ background:{QT["panel"]}; border:1px solid {QT["line"]}; border-radius:12px; }}
QGroupBox {{ background:{QT["surface"]}; border:1px solid {QT["line"]}; border-radius:12px; margin-top:10px; }}
QGroupBox::title {{ subcontrol-origin:margin; left:14px; padding:0 6px; color:{QT["text_soft"]}; }}
QListWidget#NavList {{ background:transparent; border:none; outline:none; color:{QT["text_soft"]}; }}
QListWidget#NavList::item {{ border-radius:10px; padding:11px 12px; margin:0 0 6px 0; }}
QListWidget#NavList::item:selected {{ background:{QT["surface_alt"]}; color:{QT["text"]}; border:1px solid {QT["line"]}; }}
QListWidget#NavList::item:hover {{ background:{QT["surface_soft"]}; color:{QT["text"]}; }}
QPushButton {{ background:{QT["surface_alt"]}; color:{QT["text"]}; border:1px solid {QT["line"]}; border-radius:10px; padding:10px 12px; font-weight:600; }}
QPushButton:hover {{ background:{QT["surface_soft"]}; }}
QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QTableWidget {{ background:{QT["surface"]}; color:{QT["text"]}; border:1px solid {QT["line"]}; border-radius:10px; padding:8px 10px; selection-background-color:{QT["accent_soft"]}; }}
QHeaderView::section {{ background:{QT["surface_alt"]}; color:{QT["text_soft"]}; border:none; border-bottom:1px solid {QT["line"]}; padding:8px; font-weight:600; }}
QCheckBox {{ color:{QT["text_soft"]}; spacing:8px; }}
QCheckBox::indicator {{ width:14px; height:14px; border-radius:4px; border:1px solid {QT["line"]}; background:{QT["surface_alt"]}; }}
QCheckBox::indicator:checked {{ background:{QT["accent"]}; border:1px solid {QT["accent_deep"]}; }}
QTableView {{ alternate-background-color:{QT["surface_soft"]}; }}
QStatusBar {{ background:{QT["panel"]}; color:{QT["text_soft"]}; }}
"""


def set_browser_text(target: QTextBrowser, text: str, *, markdown: bool = False) -> None:
    cleaned = fix_text(text or "")
    if markdown:
        target.setMarkdown(cleaned)
    else:
        target.setPlainText(cleaned)


def make_browser() -> QTextBrowser:
    view = QTextBrowser()
    view.setOpenExternalLinks(True)
    view.setReadOnly(True)
    return view


class SectionBox(QGroupBox):
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(12, 18, 12, 12)
        self.body.setSpacing(10)


class MetricCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{QT['surface']}; border:1px solid {QT['line']}; border-radius:12px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        self.title = QLabel("")
        self.title.setStyleSheet(f"color:{QT['text_soft']}; font-size:9pt; font-weight:600;")
        self.value = QLabel("")
        self.value.setStyleSheet(f"color:{QT['text']}; font-family:Bahnschrift; font-size:18pt; font-weight:700;")
        self.body = QLabel("")
        self.body.setWordWrap(True)
        self.body.setStyleSheet(f"color:{QT['muted']}; font-size:9pt;")
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.body)

    def set_content(self, title: str, value: str, body: str) -> None:
        self.title.setText(title)
        self.value.setText(value)
        self.body.setText(body)


class TextPage(QWidget):
    def __init__(self, title: str, *, markdown: bool = False):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{QT['text_soft']};")
        self.view = make_browser()
        self.markdown = markdown
        layout.addWidget(self.meta)
        box = SectionBox(title)
        box.body.addWidget(self.view)
        layout.addWidget(box, 1)

    def set_content(self, meta: str, text: str) -> None:
        self.meta.setText(meta)
        set_browser_text(self.view, text, markdown=self.markdown)


class RichTextPage(QWidget):
    def __init__(self, title: str, *, markdown: bool = False):
        super().__init__()
        self.markdown = markdown
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{QT['text_soft']};")
        layout.addWidget(self.meta)
        self.cards_layout = QGridLayout()
        self.cards_layout.setHorizontalSpacing(10)
        self.cards_layout.setVerticalSpacing(10)
        self.metric_cards = [MetricCard() for _ in range(4)]
        for idx, card in enumerate(self.metric_cards):
            self.cards_layout.addWidget(card, 0, idx)
            card.hide()
        layout.addLayout(self.cards_layout)
        box = SectionBox(title)
        self.view = make_browser()
        box.body.addWidget(self.view)
        layout.addWidget(box, 1)

    def set_content(self, meta: str, text: str, metrics: list[tuple[str, str, str]] | None = None) -> None:
        self.meta.setText(meta)
        metrics = metrics or []
        for idx, card in enumerate(self.metric_cards):
            if idx < len(metrics):
                title, value, body = metrics[idx]
                card.set_content(title, value, body)
                card.show()
            else:
                card.hide()
        set_browser_text(self.view, text, markdown=self.markdown)


class FilterableTablePage(QWidget):
    def __init__(self, title: str, headers: list[str], *, show_summary: bool = False):
        super().__init__()
        self.headers = headers
        self.raw_rows: list[dict] = []
        self.filtered_rows: list[dict] = []
        self.detail_builder = None
        self.cells_builder = None
        self.filter_handler = None
        self.row_key_builder = None
        self.item_styler = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{QT['text_soft']};")
        layout.addWidget(self.meta)

        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索代码、名称或摘要")
        self.toolbar.addWidget(self.search, 1)
        self.toolbar.addStretch(1)
        layout.addLayout(self.toolbar)

        splitter = QSplitter(Qt.Horizontal)
        left = SectionBox(title)
        self.table = QTableView()
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.model = QStandardItemModel(0, len(headers), self)
        self.model.setHorizontalHeaderLabels(headers)
        self.table.setModel(self.model)
        left.body.addWidget(self.table)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        if show_summary:
            summary_box = SectionBox("摘要")
            self.summary = make_browser()
            summary_box.body.addWidget(self.summary)
            right_layout.addWidget(summary_box, 1)
        else:
            self.summary = None
        detail_box = SectionBox("详情")
        self.detail = make_browser()
        detail_box.body.addWidget(self.detail)
        right_layout.addWidget(detail_box, 2)
        splitter.addWidget(right)
        splitter.setSizes([560, 760])
        layout.addWidget(splitter, 1)

        self.search.textChanged.connect(self._apply_filters)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_detail())

    def add_filter_combo(self, placeholder: str, values: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentText(placeholder)
        self.toolbar.insertWidget(self.toolbar.count() - 1, combo)
        combo.currentTextChanged.connect(self._apply_filters)
        return combo

    def add_filter_check(self, label: str) -> QCheckBox:
        box = QCheckBox(label)
        box.setStyleSheet(f"color:{QT['text_soft']};")
        self.toolbar.insertWidget(self.toolbar.count() - 1, box)
        box.stateChanged.connect(self._apply_filters)
        return box

    def configure(self, *, detail_builder, cells_builder, filter_handler=None, row_key_builder=None, item_styler=None) -> None:
        self.detail_builder = detail_builder
        self.cells_builder = cells_builder
        self.filter_handler = filter_handler
        self.row_key_builder = row_key_builder or (lambda row: row.get("fund_code") or row.get("agent_name") or "")
        self.item_styler = item_styler

    def load_rows(self, meta: str, rows: list[dict], summary_text: str | None = None) -> None:
        self.meta.setText(meta)
        self.raw_rows = rows
        if self.summary is not None:
            set_browser_text(self.summary, summary_text or "暂无摘要。")
        self._apply_filters()

    def _matches_search(self, row: dict) -> bool:
        query = self.search.text().strip().lower()
        if not query:
            return True
        haystack = json.dumps(row, ensure_ascii=False).lower()
        return query in haystack

    def _apply_filters(self) -> None:
        selected_key = ""
        current_index = self.table.currentIndex()
        if current_index.isValid() and current_index.row() < len(self.filtered_rows):
            selected_key = self.row_key_builder(self.filtered_rows[current_index.row()])
        self.filtered_rows = []
        for row in self.raw_rows:
            if not self._matches_search(row):
                continue
            if self.filter_handler and not self.filter_handler(row):
                continue
            self.filtered_rows.append(row)
        self._reload_model(selected_key)

    def _reload_model(self, selected_key: str = "") -> None:
        self.table.setSortingEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        for row in self.filtered_rows:
            items: list[QStandardItem] = []
            for col_index, value in enumerate(self.cells_builder(row)):
                item = QStandardItem(str(value))
                item.setEditable(False)
                if self._is_numeric_like(str(value)):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if self.item_styler:
                    self.item_styler(row, col_index, item)
                items.append(item)
            self.model.appendRow(items)
        self.table.setSortingEnabled(True)
        if self.filtered_rows:
            target_row = 0
            if selected_key:
                for idx, row in enumerate(self.filtered_rows):
                    if self.row_key_builder(row) == selected_key:
                        target_row = idx
                        break
            self.table.selectRow(target_row)
            self._update_detail()
        else:
            set_browser_text(self.detail, "暂无内容。")

    def _update_detail(self) -> None:
        index = self.table.currentIndex()
        if not index.isValid() or index.row() >= len(self.filtered_rows) or not self.detail_builder:
            return
        set_browser_text(self.detail, self.detail_builder(self.filtered_rows[index.row()]))

    @staticmethod
    def _is_numeric_like(value: str) -> bool:
        cleaned = value.replace(",", "").replace("元", "").replace("%", "").strip()
        if not cleaned:
            return False
        try:
            float(cleaned)
            return True
        except ValueError:
            return False


class RuntimePage(QWidget):
    def __init__(self, shell: "QtDesktopShell"):
        super().__init__()
        self.shell = shell
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        actions = QHBoxLayout()
        self.btn_intraday = QPushButton("运行日内链路")
        self.btn_realtime = QPushButton("刷新实时快照")
        self.btn_nightly = QPushButton("运行夜间复盘")
        self.btn_preflight = QPushButton("运行健康检查")
        self.btn_intraday.setStyleSheet(f"background:{QT['accent']}; border:1px solid {QT['accent_deep']}; color:#F7FBFF;")
        for button in (self.btn_intraday, self.btn_realtime, self.btn_nightly, self.btn_preflight):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        cards = QGridLayout()
        self.card_views: dict[str, QTextBrowser] = {}
        for idx, key in enumerate(("intraday", "realtime", "nightly")):
            box = SectionBox(TASK_CARD_SPECS[key]["title"])
            view = make_browser()
            box.body.addWidget(view)
            cards.addWidget(box, 0, idx)
            self.card_views[key] = view
        layout.addLayout(cards)

        self.banner = QLabel("运行控制台：等待任务调度。")
        self.banner.setStyleSheet(f"color:{QT['text_soft']}; font-weight:600;")
        layout.addWidget(self.banner)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(
            f"QPlainTextEdit {{ background:{QT['console_bg']}; color:{QT['console_text']}; "
            f"border:1px solid {QT['line']}; border-radius:12px; padding:10px; font-family:Consolas; }}"
        )
        layout.addWidget(self.log, 1)

        self.btn_intraday.clicked.connect(lambda: self.shell.run_pipeline("intraday"))
        self.btn_realtime.clicked.connect(self.shell.run_realtime)
        self.btn_nightly.clicked.connect(lambda: self.shell.run_pipeline("nightly"))
        self.btn_preflight.clicked.connect(self.shell.run_preflight)

    def refresh_cards(self, home: Path, task_status: dict[str, dict], active_job_name: str) -> None:
        for key, view in self.card_views.items():
            view.setPlainText(build_task_card_text(key, task_status[key], current_task_result_info(home, key)))
        runtime_parts = [f"{TASK_CARD_SPECS[k]['title']}={task_status[k].get('status')}" for k in task_status]
        if active_job_name:
            runtime_parts.append(f"当前任务={active_job_name}")
        self.banner.setText(" | ".join(runtime_parts) if runtime_parts else "运行控制台：当前没有任务。")

    def set_log(self, text: str) -> None:
        self.log.setPlainText(fix_text(text))

    def append_log(self, text: str) -> None:
        self.log.appendPlainText(fix_text(text))


class TradePage(QWidget):
    def __init__(self, shell: "QtDesktopShell"):
        super().__init__()
        self.shell = shell
        self.state: dict = {}
        self.fund_lookup: dict[str, dict] = {}
        self.suggestion_lookup: dict[str, dict] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{QT['text_soft']};")
        layout.addWidget(self.meta)

        splitter = QSplitter(Qt.Horizontal)
        left_box = SectionBox("交易执行")
        form = QFormLayout()
        self.suggestion_combo = QComboBox()
        self.date_edit = QLineEdit()
        self.fund_combo = QComboBox()
        self.action_combo = QComboBox()
        self.action_combo.addItems(["buy", "sell", "switch_in", "switch_out"])
        self.amount_edit = QLineEdit("100")
        self.nav_edit = QLineEdit()
        self.units_edit = QLineEdit()
        self.note_edit = QPlainTextEdit()
        self.note_edit.setFixedHeight(110)
        for label, widget in [
            ("绑定建议", self.suggestion_combo),
            ("交易日期", self.date_edit),
            ("基金", self.fund_combo),
            ("动作", self.action_combo),
            ("金额", self.amount_edit),
            ("成交净值", self.nav_edit),
            ("成交份额", self.units_edit),
            ("备注", self.note_edit),
        ]:
            form.addRow(label, widget)
        left_box.body.addLayout(form)
        buttons = QHBoxLayout()
        self.submit_button = QPushButton("记录交易并回写持仓")
        self.open_button = QPushButton("打开交易流水")
        buttons.addWidget(self.submit_button)
        buttons.addWidget(self.open_button)
        left_box.body.addLayout(buttons)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.preview = make_browser()
        self.output = make_browser()
        preview_box = SectionBox("交易前检查")
        preview_box.body.addWidget(self.preview)
        output_box = SectionBox("交易输出")
        output_box.body.addWidget(self.output)
        right_layout.addWidget(preview_box, 1)
        right_layout.addWidget(output_box, 1)

        splitter.addWidget(left_box)
        splitter.addWidget(right)
        splitter.setSizes([430, 760])
        layout.addWidget(splitter, 1)

        self.suggestion_combo.currentIndexChanged.connect(self.apply_suggestion)
        self.fund_combo.currentIndexChanged.connect(self.refresh_preview)
        self.action_combo.currentIndexChanged.connect(self.refresh_preview)
        self.amount_edit.textChanged.connect(self.refresh_preview)
        self.nav_edit.textChanged.connect(self.refresh_preview)
        self.units_edit.textChanged.connect(self.refresh_preview)
        self.submit_button.clicked.connect(self.submit_trade)
        self.open_button.clicked.connect(lambda: open_path(self.shell.home / "db" / "trade_journal"))

    def refresh_data(self, state: dict) -> None:
        self.state = state
        self.meta.setText(f"交易日期 {state.get('selected_date', today_str())}")
        self.date_edit.setText(state.get("selected_date", today_str()))
        self.fund_lookup = {item.get("fund_code", ""): item for item in state.get("portfolio", {}).get("funds", []) or []}
        self.fund_combo.blockSignals(True)
        self.fund_combo.clear()
        for code, fund in self.fund_lookup.items():
            self.fund_combo.addItem(f"{code} | {fund.get('fund_name', '')}", code)
        self.fund_combo.blockSignals(False)

        suggestions = [item for section in ("tactical_actions", "dca_actions") for item in state.get("validated", {}).get(section, []) or []]
        self.suggestion_lookup = {item.get("suggestion_id", ""): item for item in suggestions if item.get("suggestion_id")}
        self.suggestion_combo.blockSignals(True)
        self.suggestion_combo.clear()
        self.suggestion_combo.addItem("不绑定建议", "")
        for item in suggestions:
            label = f"{item.get('fund_name', item.get('fund_code', ''))} | {item.get('validated_action')} | {money(item.get('validated_amount', 0))}"
            self.suggestion_combo.addItem(label, item.get("suggestion_id", ""))
        self.suggestion_combo.blockSignals(False)
        set_browser_text(self.output, build_trade_output_text(state.get("selected_date", ""), (state.get("trade_journal", {}) or {}).get("items", [])))
        self.refresh_preview()

    def selected_fund(self) -> dict | None:
        return self.fund_lookup.get(self.fund_combo.currentData() or "")

    def apply_suggestion(self) -> None:
        suggestion_id = self.suggestion_combo.currentData()
        if not suggestion_id:
            self.refresh_preview()
            return
        item = self.suggestion_lookup.get(suggestion_id)
        if not item:
            return
        index = self.fund_combo.findData(item.get("fund_code", ""))
        if index >= 0:
            self.fund_combo.setCurrentIndex(index)
        mapped = {"add": "buy", "scheduled_dca": "buy", "reduce": "sell", "switch_out": "switch_out"}.get(item.get("validated_action", ""), "buy")
        self.action_combo.setCurrentText(mapped)
        self.amount_edit.setText(str(item.get("validated_amount", 0)))
        self.refresh_preview()

    def refresh_preview(self) -> None:
        selected = self.selected_fund()
        cash = next((fund for fund in self.fund_lookup.values() if fund.get("role") == "cash_hub"), None)
        constraints = build_trade_constraints(self.shell.home, self.state.get("portfolio", {}), self.state.get("selected_date", today_str()))
        set_browser_text(self.preview, build_trade_preview_text(selected, cash, constraints.get((selected or {}).get("fund_code", ""), {})))

    def submit_trade(self) -> None:
        selected = self.selected_fund()
        if not selected:
            QMessageBox.warning(self, "交易未提交", "请先选择基金。")
            return
        extra_args: list[str] = []
        if self.nav_edit.text().strip():
            extra_args.extend(["--trade-nav", self.nav_edit.text().strip()])
        if self.units_edit.text().strip():
            extra_args.extend(["--units", self.units_edit.text().strip()])
        command = build_trade_command(
            self.shell.home,
            self.date_edit.text().strip() or today_str(),
            selected.get("fund_code", ""),
            selected.get("fund_name", ""),
            self.action_combo.currentText().strip(),
            self.amount_edit.text().strip() or "0",
            self.note_edit.toPlainText().strip(),
            self.suggestion_combo.currentData() or "",
            extra_args,
        )
        self.shell.start_process(task_kind=None, job_name="trade_record", command=command, on_finish=lambda success, output: set_browser_text(self.output, output or ("交易已完成。" if success else "交易执行失败。")))


class ResearchPage(FilterableTablePage):
    def __init__(self):
        super().__init__("建议列表", ["代码", "基金", "动作", "金额", "执行"])
        self.action_filter = self.add_filter_combo("全部动作", ["全部动作", "add", "reduce", "switch_out", "hold", "scheduled_dca"])
        self.status_filter = self.add_filter_combo("全部状态", ["全部状态", "pending", "partial", "executed", "not_applicable"])
        self.configure(
            detail_builder=lambda row: self._detail_builder(row),
            cells_builder=lambda row: [row.get("fund_code", ""), row.get("fund_name", ""), row.get("validated_action", ""), money(row.get("validated_amount", 0)), row.get("execution_status", "")],
            filter_handler=self._matches_filters,
            row_key_builder=lambda row: row.get("fund_code", ""),
            item_styler=self._style_item,
        )
        self.realtime_map: dict[str, dict] = {}
        self.review_map: dict[str, dict] = {}

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

    def _style_item(self, row: dict, col: int, item: QStandardItem) -> None:
        action = row.get("validated_action", "")
        status = row.get("execution_status", "")
        if col == 2:
            color = QT["text"]
            if action in {"add", "scheduled_dca"}:
                color = QT["success"]
            elif action in {"reduce", "switch_out"}:
                color = QT["danger"]
            item.setForeground(QColor(color))
        elif col == 4:
            color = QT["muted"]
            if status == "executed":
                color = QT["success"]
            elif status == "partial":
                color = QT["warning"]
            elif status == "pending":
                color = QT["info"]
            item.setForeground(QColor(color))


class RealtimePage(FilterableTablePage):
    def __init__(self):
        super().__init__("实时收益", ["代码", "基金", "今日收益", "涨跌", "可信度", "模式"], show_summary=True)
        self.mode_filter = self.add_filter_combo("全部模式", ["全部模式", "estimate", "proxy", "official"])
        self.stale_only = self.add_filter_check("仅看陈旧")
        self.configure(
            detail_builder=build_realtime_detail_text,
            cells_builder=lambda row: [row.get("fund_code", ""), row.get("fund_name", ""), money(row.get("estimated_intraday_pnl_amount", 0)), pct(row.get("effective_change_pct", 0), 2), num(row.get("confidence"), 2), row.get("mode", "")],
            filter_handler=self._matches_filters,
            row_key_builder=lambda row: row.get("fund_code", ""),
            item_styler=self._style_item,
        )

    def _matches_filters(self, row: dict) -> bool:
        mode = self.mode_filter.currentText()
        if mode != "全部模式" and row.get("mode", "") != mode:
            return False
        if self.stale_only.isChecked() and not row.get("stale"):
            return False
        return True

    def _style_item(self, row: dict, col: int, item: QStandardItem) -> None:
        pnl = float(row.get("estimated_intraday_pnl_amount", 0) or 0)
        stale = bool(row.get("stale"))
        if stale:
            item.setForeground(QColor(QT["warning"]))
        if col in {2, 3}:
            if pnl > 0:
                item.setForeground(QColor(QT["success"]))
            elif pnl < 0:
                item.setForeground(QColor(QT["danger"]))


class AgentsPage(FilterableTablePage):
    def __init__(self):
        super().__init__("智能体", ["阶段", "智能体", "状态", "置信度"])
        self.status_filter = self.add_filter_combo("全部状态", ["全部状态", "ok", "failed", "degraded", "unknown"])
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
            color = QT["muted"]
            if status == "ok":
                color = QT["success"]
            elif status == "failed":
                color = QT["danger"]
            elif status == "degraded":
                color = QT["warning"]
            item.setForeground(QColor(color))


class ReviewPage(RichTextPage):
    def __init__(self):
        super().__init__("夜间复盘", markdown=True)


class SettingsPage(RichTextPage):
    def __init__(self, shell: "QtDesktopShell"):
        super().__init__("系统与路径")
        self.shell = shell
        self.quick_buttons = QHBoxLayout()
        for label, path in [
            ("打开 config", shell.home / "config"),
            ("打开 db", shell.home / "db"),
            ("打开 reports", shell.home / "reports" / "daily"),
            ("打开 logs", shell.home / "logs"),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, p=path: open_path(p))
            self.quick_buttons.addWidget(button)
        self.quick_buttons.addStretch(1)
        self.layout().insertLayout(1, self.quick_buttons)


class QtDesktopShell(QMainWindow):
    def __init__(self, home: Path, selected: str | None = None):
        super().__init__()
        self.home = home
        self.ui_state = load_ui_state(home)
        self.state = load_state(home, selected)
        self.task_status = initial_task_status()
        self.current_process: QProcess | None = None
        self.process_lines: list[str] = []
        self.active_job_name = ""
        self.active_task_kind = ""
        self.active_job_started_at: datetime | None = None
        self.after_finish_callback = None

        self.setWindowTitle(APP_TITLE)
        self.resize(1560, 980)
        self.setStyleSheet(STYLE)
        self._build_ui()
        self.refresh_all()
        self._runtime_timer = QTimer(self)
        self._runtime_timer.timeout.connect(self._tick_runtime)
        self._runtime_timer.start(1000)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(14, 14, 14, 14)
        shell.setSpacing(10)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(10)
        title = QLabel("OKRA")
        title.setStyleSheet(f"color:{QT['text']}; font-family:Bahnschrift; font-size:22px; font-weight:700;")
        subtitle = QLabel("小助手")
        subtitle.setStyleSheet(f"color:{QT['muted']}; font-size:11px; font-weight:600;")
        sidebar_layout.addWidget(title)
        sidebar_layout.addWidget(subtitle)
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("NavList")
        for key, label in NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            self.nav_list.addItem(item)
        sidebar_layout.addWidget(self.nav_list, 1)
        controls = SectionBox("控制")
        self.date_combo = QComboBox()
        self.btn_today = QPushButton("回到今天")
        self.btn_refresh = QPushButton("刷新")
        controls.body.addWidget(QLabel("查看日期"))
        controls.body.addWidget(self.date_combo)
        controls.body.addWidget(self.btn_today)
        controls.body.addWidget(self.btn_refresh)
        sidebar_layout.addWidget(controls)
        status = SectionBox("状态")
        self.status_badge = QLabel("就绪")
        self.status_badge.setStyleSheet(f"background:{QT['info_soft']}; color:{QT['info']}; border:1px solid #23405F; border-radius:9px; padding:4px 8px; font-weight:600;")
        self.chain_status = QLabel("")
        self.chain_status.setWordWrap(True)
        self.chain_status.setStyleSheet(f"color:{QT['text_soft']};")
        status.body.addWidget(self.status_badge)
        status.body.addWidget(self.chain_status)
        sidebar_layout.addWidget(status)
        shell.addWidget(sidebar)

        self.stack = QStackedWidget()
        shell.addWidget(self.stack, 1)

        self.dashboard_page = QWidget()
        dash_layout = QVBoxLayout(self.dashboard_page)
        dash_layout.setContentsMargins(0, 0, 0, 0)
        self.metric_cards = [MetricCard() for _ in range(4)]
        metric_grid = QGridLayout()
        for idx, card in enumerate(self.metric_cards):
            metric_grid.addWidget(card, idx // 2, idx % 2)
        dash_layout.addLayout(metric_grid)
        dash_section = SectionBox("今日工作台")
        self.dashboard_text = make_browser()
        dash_section.body.addWidget(self.dashboard_text)
        dash_layout.addWidget(dash_section, 1)

        self.portfolio_page = RichTextPage("组合配置", markdown=True)
        self.review_page = ReviewPage()
        self.settings_page = SettingsPage(self)
        self.research_page = ResearchPage()
        self.realtime_page = RealtimePage()
        self.agents_page = AgentsPage()
        self.runtime_page = RuntimePage(self)
        self.trade_page = TradePage(self)

        self.pages = {
            "dash": self.dashboard_page,
            "portfolio": self.portfolio_page,
            "research": self.research_page,
            "trade": self.trade_page,
            "review": self.review_page,
            "rt": self.realtime_page,
            "agents": self.agents_page,
            "runtime": self.runtime_page,
            "settings": self.settings_page,
        }
        for key, _label in NAV_ITEMS:
            self.stack.addWidget(self.pages[key])

        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        self.date_combo.currentTextChanged.connect(self._on_date_changed)
        self.btn_today.clicked.connect(self._switch_to_today)
        self.btn_refresh.clicked.connect(self._refresh_selected_date)
        target = self.ui_state.get("last_tab", "dash")
        self._select_page(target if target in self.pages else "dash")
        self._set_status_badge("idle")

    def _select_page(self, key: str) -> None:
        keys = [self.nav_list.item(i).data(Qt.UserRole) for i in range(self.nav_list.count())]
        if key not in keys:
            key = "dash"
        self.nav_list.setCurrentRow(keys.index(key))

    def _on_nav_changed(self, row: int) -> None:
        if row < 0:
            return
        key = self.nav_list.item(row).data(Qt.UserRole)
        self.stack.setCurrentWidget(self.pages[key])
        self.ui_state["last_tab"] = key
        save_ui_state(self.home, self.ui_state)

    def _on_date_changed(self, text: str) -> None:
        if not text:
            return
        self.state = load_state(self.home, text)
        self.refresh_all()

    def _switch_to_today(self) -> None:
        today = today_str()
        idx = self.date_combo.findText(today)
        if idx >= 0:
            self.date_combo.setCurrentIndex(idx)
        self._refresh_selected_date()

    def _refresh_selected_date(self) -> None:
        self.state = load_state(self.home, self.date_combo.currentText() or today_str())
        self.refresh_all()

    def refresh_all(self) -> None:
        dates = self.state.get("dates", []) or collect_dates(self.home)
        selected = self.state.get("selected_date", today_str())
        self.date_combo.blockSignals(True)
        self.date_combo.clear()
        self.date_combo.addItems(dates)
        idx = self.date_combo.findText(selected)
        if idx >= 0:
            self.date_combo.setCurrentIndex(idx)
        self.date_combo.blockSignals(False)
        self.chain_status.setText(self._today_chain_status_text())
        summary = summarize_state(self.state)
        self._set_status_badge("running" if self.current_process and self.current_process.state() != QProcess.NotRunning else ("warning" if summary.get("preflight_status") == "warning" else "idle"))
        self._refresh_dashboard()
        self._refresh_portfolio()
        self._refresh_research()
        self.trade_page.refresh_data(self.state)
        self._refresh_review()
        self._refresh_realtime()
        self._refresh_agents()
        self.runtime_page.refresh_cards(self.home, self.task_status, self.active_job_name)
        self._refresh_settings()

    def _refresh_dashboard(self) -> None:
        summary = summarize_state(self.state)
        validated = self.state.get("validated", {})
        exposure = self.state.get("llm_context", {}).get("exposure_summary") or analyze_portfolio_exposure(self.state.get("portfolio", {}), self.state.get("strategy", {}))
        alerts = build_dashboard_alerts({**self.state, "home": self.home})
        prev_date = previous_date(self.state.get("dates", []), self.state.get("selected_date", ""))
        prev_validated = load_validated_for_date(self.home, prev_date)
        changes = build_action_change_lines(validated, prev_validated, prev_date)
        plain = build_plain_language_summary(summary, validated, exposure, alerts)
        top = (validated.get("tactical_actions", []) or validated.get("dca_actions", []) or [{}])[0]
        market = validated.get("market_view", {}) or {}
        self.metric_cards[0].set_content("今日主动作", top.get("fund_name", "暂无"), top.get("thesis", "今天没有需要立刻执行的主动动作。"))
        self.metric_cards[1].set_content("市场状态", market.get("regime", "暂无"), market.get("summary", "等待市场摘要。"))
        self.metric_cards[2].set_content("建议模式", summary.get("advice_mode", "unknown"), f"通道 {summary.get('transport_name', '暂无') or '暂无'}")
        self.metric_cards[3].set_content("风险提醒", f"{len(alerts)} 条" if alerts else "稳定", alerts[0] if alerts else "暂无高优先级风险提醒。")
        set_browser_text(self.dashboard_text, build_dashboard_text(summary, validated, self.state.get("portfolio", {}), self.state.get("portfolio_report", ""), exposure, changes, alerts, plain))

    def _refresh_portfolio(self) -> None:
        exposure = self.state.get("llm_context", {}).get("exposure_summary") or analyze_portfolio_exposure(self.state.get("portfolio", {}), self.state.get("strategy", {}))
        concentration = exposure.get("concentration_metrics", {}) or {}
        allocation_plan = exposure.get("allocation_plan", {}) or {}
        metrics = [
            ("总资产", money(self.state.get("portfolio", {}).get("total_value", 0)), self.state.get("portfolio", {}).get("portfolio_name", "暂无")),
            ("再平衡", "需要" if allocation_plan.get("rebalance_needed") else "暂不", f"带宽 {pct(allocation_plan.get('rebalance_band_pct', 0), 2)}"),
            ("高波动主题", pct(concentration.get("high_volatility_theme_weight_pct", 0), 2), "短线风险预算"),
            ("防守缓冲", pct(concentration.get("defensive_buffer_weight_pct", 0), 2), "现金 / 债券占比"),
        ]
        self.portfolio_page.set_content(
            f"组合 {self.state.get('portfolio', {}).get('portfolio_name', '暂无')} | 总资产 {money(self.state.get('portfolio', {}).get('total_value', 0))}",
            self.state.get("portfolio_report") or "暂无组合报告。",
            metrics=metrics,
        )

    def _refresh_research(self) -> None:
        items = []
        for section in ("tactical_actions", "dca_actions", "hold_actions"):
            for item in self.state.get("validated", {}).get(section, []) or []:
                enriched = dict(item)
                enriched["_section"] = section
                items.append(enriched)
        realtime_map = {entry.get("fund_code"): entry for entry in (self.state.get("realtime", {}).get("items", []) or [])}
        review_items = [entry for batch in self.state.get("review_results_for_date", []) for entry in (batch.get("items", []) or [])]
        review_map = {entry.get("fund_code"): entry for entry in review_items}
        self.research_page.bind_aux(realtime_map, review_map)
        tactical_count = len(self.state.get("validated", {}).get("tactical_actions", []) or [])
        dca_count = len(self.state.get("validated", {}).get("dca_actions", []) or [])
        hold_count = len(self.state.get("validated", {}).get("hold_actions", []) or [])
        self.research_page.load_rows(f"建议 {len(items)} 条 | tactical {tactical_count} | dca {dca_count} | hold {hold_count}", items)

    def _refresh_realtime(self) -> None:
        items = self.state.get("realtime", {}).get("items", []) or []
        self.realtime_page.load_rows(
            f"实时项 {len(items)} 条 | 快照 {self.state.get('realtime_date', '暂无')}",
            items,
            summary_text=build_realtime_summary_text(self.state.get("realtime", {})),
        )

    def _refresh_agents(self) -> None:
        aggregate = self.state.get("aggregate", {}) or {}
        agents = aggregate.get("agents", {}) or {}
        roles = aggregate.get("agent_roles", {}) or {}
        ordered = aggregate.get("ordered_agents", []) or sorted(agents.keys())
        rows = [{"agent_name": name, "role": roles.get(name, "unknown"), **(agents.get(name, {}) or {})} for name in ordered]
        self.agents_page.load_rows(f"智能体 {len(rows)} 个 | 失败 {len(aggregate.get('failed_agents', []) or [])}", rows)

    def _refresh_review(self) -> None:
        batches = self.state.get("review_results_for_date", []) or []
        summary_text = build_review_summary_text(self.state.get("selected_date", ""), batches, self.state.get("review_memory", {}), historical_operating_metrics(self.home))
        detail_text = self.state.get("review_report") or build_review_detail_fallback(self.state.get("selected_date", ""), batches)
        total_supportive = sum(item.get("summary", {}).get("supportive", 0) for item in batches)
        total_adverse = sum(item.get("summary", {}).get("adverse", 0) for item in batches)
        total_missed = sum(item.get("summary", {}).get("missed_upside", 0) for item in batches)
        metrics = [
            ("复盘批次", str(len(batches)), "当前查看日"),
            ("supportive", str(total_supportive), "建议层验证"),
            ("adverse", str(total_adverse), "逆向结果"),
            ("missed", str(total_missed), "错失上涨"),
        ]
        self.review_page.set_content(f"复盘批次 {len(batches)}", summary_text + "\n\n" + detail_text, metrics=metrics)

    def _refresh_settings(self) -> None:
        manifests = {"intraday": self.state.get("intraday_manifest", {}), "nightly": self.state.get("nightly_manifest", {}), "realtime": self.state.get("realtime_manifest", {})}
        text = build_settings_text(
            self.home,
            self.state.get("selected_date", ""),
            self.state.get("portfolio", {}),
            self.state.get("project", {}),
            self.state.get("strategy", {}),
            self.state.get("watchlist", {}),
            self.state.get("llm_config", {}),
            self.state.get("llm_raw", {}),
            self.state.get("realtime", {}),
            self.state.get("preflight", {}),
            manifests,
        )
        metrics = [
            ("观察池", str(len(self.state.get("watchlist", {}).get("funds", []) or [])), "基金样本"),
            ("模型", self.state.get("llm_config", {}).get("model", "暂无"), self.state.get("llm_config", {}).get("model_provider", "")),
            ("自检", self.state.get("preflight", {}).get("status", "暂无"), "最近一次 preflight"),
            ("查看日", self.state.get("selected_date", ""), "当前页面数据"),
        ]
        self.settings_page.set_content("系统与路径", text, metrics=metrics)

    def _today_chain_status_text(self) -> str:
        today = today_str()
        manifest = self.state.get("intraday_manifest", {}) or {}
        strategy = self.state.get("strategy", {}) or {}
        report_mode = str(strategy.get("schedule", {}).get("report_mode", "intraday_proxy") or "intraday_proxy").strip()
        report_name = f"{today}.md" if report_mode == "daily_report" else f"{today}_portfolio.md"
        report_exists = (self.home / "reports" / "daily" / report_name).exists()
        validated_exists = (self.home / "db" / "validated_advice" / f"{today}.json").exists()
        status = str(manifest.get("status", "") or "").lower()
        current_step = fix_text(str(manifest.get("current_step", "") or "").strip())
        finished_at = fix_text(str(manifest.get("finished_at", "") or "").strip())
        if status == "running":
            return f"今日链路：运行中 | {current_step}" if current_step else "今日链路：运行中"
        if status == "ok" or (report_exists and validated_exists):
            return f"今日链路：已更新 | {finished_at}" if finished_at else "今日链路：已更新"
        if status == "failed":
            errors = manifest.get("errors") or []
            latest_error = fix_text(str(errors[-1].get("error", "")).strip()) if errors else ""
            return f"今日链路：失败 | {latest_error[:64]}" if latest_error else "今日链路：失败"
        return "今日链路：尚未生成今日研报"

    def _build_env(self) -> QProcessEnvironment:
        env = QProcessEnvironment.systemEnvironment()
        for key, value in build_runtime_env(self.home).items():
            env.insert(key, value)
        return env

    def start_process(self, *, task_kind: str | None, job_name: str, command: list[str], on_finish=None) -> None:
        if self.current_process and self.current_process.state() != QProcess.NotRunning:
            QMessageBox.warning(self, "任务忙碌", f"当前仍有任务在运行：{self.active_job_name}")
            return
        self.after_finish_callback = on_finish
        self.current_process = QProcess(self)
        self.current_process.setProcessEnvironment(self._build_env())
        self.current_process.setProgram(command[0])
        self.current_process.setArguments(command[1:])
        self.current_process.readyReadStandardOutput.connect(self._handle_output)
        self.current_process.readyReadStandardError.connect(self._handle_output)
        self.current_process.finished.connect(self._handle_finished)
        self.process_lines = [f"$ {' '.join(command)}"]
        self.active_job_name = job_name
        self.active_task_kind = task_kind or ""
        self.active_job_started_at = datetime.now()
        if task_kind in self.task_status:
            begin_task_status(self.task_status, task_kind, today_str(), self.active_job_started_at)
        self.runtime_page.set_log("\n".join(self.process_lines))
        self.runtime_page.refresh_cards(self.home, self.task_status, self.active_job_name)
        self._set_status_badge("running")
        self.current_process.start()

    def _handle_output(self) -> None:
        if not self.current_process:
            return
        data = bytes(self.current_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not data:
            data = bytes(self.current_process.readAllStandardError()).decode("utf-8", errors="replace")
        if not data:
            return
        for raw in data.splitlines():
            clean = fix_text(raw.rstrip())
            if clean:
                self.process_lines.append(clean)
                self.runtime_page.append_log(clean)
            step = interpret_run_output_line(clean)
            if step and self.active_task_kind in self.task_status:
                update_task_step(self.task_status, self.active_task_kind, step)
        self.runtime_page.refresh_cards(self.home, self.task_status, self.active_job_name)

    def _handle_finished(self, exit_code: int, _status) -> None:
        output = "\n".join(self.process_lines).strip()
        log_path = desktop_log_path(self.home, self.active_job_name or "desktop_qt")
        log_path.write_text(output, encoding="utf-8")
        success = exit_code == 0
        elapsed = int((datetime.now() - self.active_job_started_at).total_seconds()) if self.active_job_started_at else 0
        if self.active_task_kind in self.task_status:
            finish_task_status(self.task_status, self.active_task_kind, success, datetime.now(), elapsed, str(log_path))
        callback = self.after_finish_callback
        self.after_finish_callback = None
        self.active_job_name = ""
        self.active_task_kind = ""
        self.active_job_started_at = None
        self.state = load_state(self.home, self.date_combo.currentText() or today_str())
        self.refresh_all()
        if callback:
            callback(success, output)

    def _tick_runtime(self) -> None:
        if not self.current_process or self.current_process.state() == QProcess.NotRunning or not self.active_job_started_at:
            return
        elapsed = int((datetime.now() - self.active_job_started_at).total_seconds())
        if self.active_task_kind in self.task_status:
            update_task_elapsed(self.task_status, self.active_task_kind, elapsed)
        self.runtime_page.refresh_cards(self.home, self.task_status, self.active_job_name)

    def _set_status_badge(self, state: str) -> None:
        mapping = {
            "idle": ("就绪", QT["info_soft"], QT["info"], "#23405F"),
            "running": ("运行中", QT["accent_soft"], QT["info"], QT["accent"]),
            "warning": ("注意", QT["warning_soft"], QT["warning"], "#5C4020"),
        }
        text, bg, fg, border = mapping.get(state, mapping["idle"])
        self.status_badge.setText(text)
        self.status_badge.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid {border}; border-radius:9px; padding:4px 8px; font-weight:600;"
        )

    def run_pipeline(self, mode: str) -> None:
        self.start_process(task_kind=mode if mode in TASK_CARD_SPECS else None, job_name=mode, command=build_pipeline_command(self.home, today_str(), mode))

    def run_realtime(self) -> None:
        self.start_process(task_kind="realtime", job_name="realtime", command=build_realtime_command(self.home, today_str()))

    def run_preflight(self) -> None:
        self.start_process(task_kind=None, job_name="preflight", command=build_preflight_command(self.home, "desktop"))

    def closeEvent(self, event) -> None:
        save_ui_state(self.home, self.ui_state)
        super().closeEvent(event)


def run_app(home: Path, selected: str | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    window = QtDesktopShell(home, selected)
    window.show()
    return app.exec()


def main() -> None:
    parser = argparse.ArgumentParser(description="PySide6 desktop shell for okra assistant.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date")
    parser.add_argument("--dump-state", action="store_true")
    args = parser.parse_args()
    home = Path(args.agent_home).expanduser() if args.agent_home else DEFAULT_AGENT_HOME
    state = load_state(home, args.date)
    if args.dump_state:
        print(json.dumps(summarize_state(state), ensure_ascii=False, indent=2))
        return
    raise SystemExit(run_app(home, args.date))


if __name__ == "__main__":
    main()
