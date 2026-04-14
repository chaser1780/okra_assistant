from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLineEdit, QMessageBox, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget, QPushButton, QLabel

from trade_constraints import build_trade_constraints
from ui_support import build_trade_command, build_trade_output_text, build_trade_preview_text, money, open_path, today_str

from ..widgets import SectionBox, make_browser, set_browser_text


class TradePage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.state: dict = {}
        self.fund_lookup: dict[str, dict] = {}
        self.suggestion_lookup: dict[str, dict] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.meta = QLabel("")
        layout.addWidget(self.meta)
        splitter = QSplitter()
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
