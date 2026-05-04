from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QMessageBox, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget, QPushButton, QLabel

from trade_constraints import build_trade_constraints
from ui_support import (
    build_portfolio_sync_apply_command,
    build_portfolio_sync_apply_text,
    build_portfolio_sync_preview_command,
    build_portfolio_sync_preview_text,
    build_trade_command,
    build_trade_output_text,
    build_trade_preview_text,
    money,
    open_path,
    today_str,
)

from ..widgets import SectionBox, make_browser, set_browser_text


class TradePage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.state: dict = {}
        self.fund_lookup: dict[str, dict] = {}
        self.suggestion_lookup: dict[str, dict] = {}
        self.import_preview_path = ""
        self.import_preview_data: dict | None = None

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
        import_buttons = QHBoxLayout()
        self.import_button = QPushButton("导入支付宝持仓截图")
        self.apply_import_button = QPushButton("确认同步截图仓位")
        self.apply_import_button.setEnabled(False)
        import_buttons.addWidget(self.import_button)
        import_buttons.addWidget(self.apply_import_button)
        left_box.body.addLayout(import_buttons)
        self.auto_add_new_checkbox = QCheckBox("将截图中系统外新基金自动加入组合")
        left_box.body.addWidget(self.auto_add_new_checkbox)
        self.drop_missing_checkbox = QCheckBox("将未出现在截图中的现有持仓归零（完整持仓模式）")
        left_box.body.addWidget(self.drop_missing_checkbox)
        self.import_status = QLabel("截图导入：尚未开始。")
        left_box.body.addWidget(self.import_status)

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
        self.import_button.clicked.connect(self.import_portfolio_screenshots)
        self.apply_import_button.clicked.connect(self.apply_portfolio_import)

    def refresh_data(self, state: dict) -> None:
        self.state = state
        if self.import_preview_data and self.import_preview_data.get("sync_date") not in {"", state.get("selected_date", today_str())}:
            self.import_preview_path = ""
            self.import_preview_data = None
            self.import_status.setText("截图导入：已因日期切换清空旧预览。")
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
        if self.import_preview_data:
            set_browser_text(self.output, build_portfolio_sync_preview_text(self.import_preview_data))
            self.apply_import_button.setEnabled(bool(self.import_preview_data.get("apply_ready")))
        else:
            set_browser_text(self.output, build_trade_output_text(state.get("selected_date", ""), (state.get("trade_journal", {}) or {}).get("items", [])))
            self.apply_import_button.setEnabled(False)
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

    def import_portfolio_screenshots(self) -> None:
        files, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            "选择支付宝持仓截图",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not files:
            return
        self.import_status.setText(f"截图导入：正在识别 {len(files)} 张截图...")
        command = build_portfolio_sync_preview_command(
            self.shell.home,
            self.date_edit.text().strip() or today_str(),
            files,
            provider="alipay",
        )
        self.shell.start_process(task_kind=None, job_name="portfolio_sync_preview", command=command, on_finish=self._on_import_preview_finished)

    def _on_import_preview_finished(self, success: bool, output: str) -> None:
        if not success:
            self.import_status.setText("截图导入：识别失败。")
            set_browser_text(self.output, output or "截图识别失败。")
            return
        preview_path = ""
        for line in reversed([line.strip() for line in output.splitlines() if line.strip()]):
            if Path(line).exists():
                preview_path = line
                break
        if not preview_path:
            self.import_status.setText("截图导入：识别完成，但未找到预览文件。")
            set_browser_text(self.output, output or "截图识别完成，但未生成预览。")
            return
        self.import_preview_path = preview_path
        self.import_preview_data = json.loads(Path(preview_path).read_text(encoding="utf-8"))
        self.import_status.setText(
            f"截图导入：已生成预览 | 匹配 {len(self.import_preview_data.get('matched_items', []) or [])} "
            f"| 未匹配 {len(self.import_preview_data.get('unmatched_detected', []) or [])}"
            f"| 新基金候选 {len(self.import_preview_data.get('new_fund_candidates', []) or [])}"
        )
        set_browser_text(self.output, build_portfolio_sync_preview_text(self.import_preview_data))
        self.apply_import_button.setEnabled(bool(self.import_preview_data.get("apply_ready")))

    @staticmethod
    def _extract_json_tail(output: str) -> dict | None:
        text = str(output or "").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None

    def apply_portfolio_import(self) -> None:
        if not self.import_preview_data or not self.import_preview_path:
            QMessageBox.warning(self, "尚无可同步预览", "请先导入支付宝持仓截图并生成预览。")
            return
        preview = self.import_preview_data
        missing_count = len(preview.get("missing_portfolio_funds", []) or [])
        unmatched_count = len(preview.get("unmatched_detected", []) or [])
        new_fund_count = len(preview.get("new_fund_candidates", []) or [])
        if unmatched_count > 0:
            QMessageBox.warning(self, "仍有未匹配截图条目", "请先解决未匹配截图条目，再执行同步。")
            return
        drop_missing = self.drop_missing_checkbox.isChecked()
        auto_add_new = self.auto_add_new_checkbox.isChecked()
        if new_fund_count > 0 and not auto_add_new:
            QMessageBox.warning(self, "存在系统外新基金候选", "当前预览里有系统外新基金候选。若要一并加入组合，请勾选“自动加入新基金”。")
            return
        prompt = (
            f"将同步 {len(preview.get('matched_items', []) or [])} 只基金的持仓信息。"
            + (f"\n将新增系统外新基金：{new_fund_count} 只。" if auto_add_new and new_fund_count else "")
            + (f"\n未出现在截图中的现有持仓：{missing_count} 只。当前选择：{'归零' if drop_missing else '保留不变'}。" if missing_count else "")
            + "\n确认继续吗？"
        )
        if QMessageBox.question(self, "确认同步持仓截图", prompt) != QMessageBox.Yes:
            return
        self.import_status.setText("截图导入：正在应用同步结果...")
        command = build_portfolio_sync_apply_command(
            self.shell.home,
            self.date_edit.text().strip() or today_str(),
            self.import_preview_path,
            drop_missing=drop_missing,
            auto_add_new=auto_add_new,
        )
        self.shell.start_process(task_kind=None, job_name="portfolio_sync_apply", command=command, on_finish=self._on_import_apply_finished)

    def _on_import_apply_finished(self, success: bool, output: str) -> None:
        if not success:
            self.import_status.setText("截图导入：同步失败。")
            set_browser_text(self.output, output or "截图仓位同步失败。")
            return
        summary = self._extract_json_tail(output)
        self.import_status.setText("截图导入：同步完成。")
        self.import_preview_path = ""
        self.import_preview_data = None
        self.apply_import_button.setEnabled(False)
        if isinstance(summary, dict):
            set_browser_text(self.output, build_portfolio_sync_apply_text(summary))
        else:
            set_browser_text(self.output, output or "截图仓位同步已完成。")
