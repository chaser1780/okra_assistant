from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget

from config_mutations import update_fund_dca_settings
from portfolio_exposure import analyze_portfolio_exposure
from ui_support import build_learning_detail_fallback, build_learning_summary_text, build_replay_differences_text, build_replay_rule_impact_text, build_settings_text, load_state, money, open_path, pct, today_str

from ..theme import QT
from ..widgets import MetricCard, SectionBox, bullet_lines, make_browser, set_browser_text


class ReviewPage(QWidget):
    def __init__(self, shell=None):
        super().__init__()
        self.shell = shell
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
            metric_grid.addWidget(card, 0, idx)
        layout.addLayout(metric_grid)

        replay_box = SectionBox("Replay Lab")
        replay_row = QHBoxLayout()
        self.replay_start_combo = QComboBox()
        self.replay_end_combo = QComboBox()
        self.replay_mode_combo = QComboBox()
        self.replay_mode_combo.addItems(["baseline", "revalidate"])
        self.replay_write_learning_check = QCheckBox("Write to learning system")
        self.replay_run_button = QPushButton("Run replay")
        replay_row.addWidget(QLabel("Start"))
        replay_row.addWidget(self.replay_start_combo, 1)
        replay_row.addWidget(QLabel("End"))
        replay_row.addWidget(self.replay_end_combo, 1)
        replay_row.addWidget(QLabel("Mode"))
        replay_row.addWidget(self.replay_mode_combo)
        replay_row.addWidget(self.replay_write_learning_check)
        replay_row.addWidget(self.replay_run_button)
        replay_box.body.addLayout(replay_row)
        self.replay_hint = QLabel("Replay runs historical validation experiments. Enable write-back only when you want the experiment to update the learning ledger.")
        self.replay_hint.setWordWrap(True)
        self.replay_hint.setStyleSheet(f"color:{QT['text_soft']};")
        replay_box.body.addWidget(self.replay_hint)
        inspect_row = QHBoxLayout()
        self.replay_select_combo = QComboBox()
        inspect_row.addWidget(QLabel("Inspect"))
        inspect_row.addWidget(self.replay_select_combo, 1)
        replay_box.body.addLayout(inspect_row)
        layout.addWidget(replay_box)

        replay_split = QSplitter()
        self.replay_diff_box = SectionBox("Replay Differences")
        self.replay_impact_box = SectionBox("Rule Impact")
        self.replay_diff_view = make_browser()
        self.replay_impact_view = make_browser()
        self.replay_diff_box.body.addWidget(self.replay_diff_view)
        self.replay_impact_box.body.addWidget(self.replay_impact_view)
        replay_split.addWidget(self.replay_diff_box)
        replay_split.addWidget(self.replay_impact_box)
        replay_split.setSizes([520, 520])
        layout.addWidget(replay_split)

        top_split = QSplitter()
        self.lessons_box = SectionBox("Core & Permanent")
        self.bias_box = SectionBox("Strategic & Replay")
        self.lessons_view = make_browser()
        self.bias_view = make_browser()
        self.lessons_box.body.addWidget(self.lessons_view)
        self.bias_box.body.addWidget(self.bias_view)
        top_split.addWidget(self.lessons_box)
        top_split.addWidget(self.bias_box)
        top_split.setSizes([520, 520])
        layout.addWidget(top_split)

        bottom_split = QSplitter()
        self.summary_box = SectionBox("Learning Summary")
        self.report_box = SectionBox("Learning Report")
        self.summary_view = make_browser()
        self.report_view = make_browser()
        self.summary_box.body.addWidget(self.summary_view)
        self.report_box.body.addWidget(self.report_view)
        bottom_split.addWidget(self.summary_box)
        bottom_split.addWidget(self.report_box)
        bottom_split.setSizes([520, 760])
        layout.addWidget(bottom_split, 1)

        self.replay_run_button.clicked.connect(self._run_replay)
        self.replay_select_combo.currentIndexChanged.connect(self._refresh_selected_replay_views)

    def _sync_replay_combos(self, dates: list[str], selected_date: str) -> None:
        current_start = self.replay_start_combo.currentText()
        current_end = self.replay_end_combo.currentText()
        values = dates or ([selected_date] if selected_date else [])
        for combo, current in ((self.replay_start_combo, current_start), (self.replay_end_combo, current_end)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(values)
            target = current if current in values else selected_date
            idx = combo.findText(target) if target else -1
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif combo.count():
                combo.setCurrentIndex(0)
            combo.blockSignals(False)

    def _sync_replay_selection(self, replay_items: list[dict]) -> None:
        current_id = self.replay_select_combo.currentData()
        self.replay_select_combo.blockSignals(True)
        self.replay_select_combo.clear()
        for item in replay_items:
            label = (
                f"{item.get('experiment_id', '')} | {item.get('mode', '')} | "
                f"delta={item.get('edge_delta_total', 0.0)} | applied={'yes' if item.get('applied_to_learning') else 'no'}"
            )
            self.replay_select_combo.addItem(label, item.get("experiment_id", ""))
        if current_id:
            idx = self.replay_select_combo.findData(current_id)
            if idx >= 0:
                self.replay_select_combo.setCurrentIndex(idx)
        if self.replay_select_combo.count() and self.replay_select_combo.currentIndex() < 0:
            self.replay_select_combo.setCurrentIndex(0)
        self.replay_select_combo.blockSignals(False)

    def _selected_replay_item(self) -> dict:
        target_id = self.replay_select_combo.currentData()
        replay_items = getattr(self, "_replay_items", []) or []
        if target_id:
            for item in replay_items:
                if item.get("experiment_id") == target_id:
                    return item
        return replay_items[0] if replay_items else {}

    def _refresh_selected_replay_views(self) -> None:
        selected = self._selected_replay_item()
        set_browser_text(self.replay_diff_view, build_replay_differences_text(selected))
        set_browser_text(self.replay_impact_view, build_replay_rule_impact_text(selected))

    def _run_replay(self) -> None:
        if self.shell is None:
            return
        start_date = self.replay_start_combo.currentText().strip()
        end_date = self.replay_end_combo.currentText().strip()
        mode = self.replay_mode_combo.currentText().strip() or "baseline"
        write_learning = self.replay_write_learning_check.isChecked()
        if not start_date or not end_date:
            QMessageBox.warning(self, "Missing Dates", "Choose both start and end dates.")
            return
        if start_date > end_date:
            QMessageBox.warning(self, "Invalid Range", "Start date must be earlier than or equal to end date.")
            return
        if write_learning:
            result = QMessageBox.question(
                self,
                "Write To Learning",
                "This replay will update the learning ledger and may promote or demote long-term rules. Continue?",
            )
            if result != QMessageBox.Yes:
                return
        self.shell.run_replay_experiment(start_date, end_date, mode, write_learning=write_learning)

    def refresh_view_model(self, view_model) -> None:
        self._replay_items = list(view_model.replay_items)
        self._sync_replay_combos(view_model.dates, view_model.selected_date)
        self._sync_replay_selection(self._replay_items)
        self.meta.setText(view_model.meta)
        for idx, metric in enumerate(view_model.metrics[:4]):
            self.metric_cards[idx].set_content(metric.title, metric.value, metric.body, tone=metric.tone)
        set_browser_text(self.lessons_view, bullet_lines(view_model.core_lines, "No core or permanent rules yet."))
        set_browser_text(self.bias_view, bullet_lines(view_model.strategic_lines + view_model.replay_lines, "No strategic rules or replay experiments yet."))
        set_browser_text(self.summary_view, view_model.summary_text)
        set_browser_text(self.report_view, view_model.detail_text, markdown=True)
        self._refresh_selected_replay_views()


class SettingsPage(QWidget):
    def __init__(self, home: Path, shell=None):
        super().__init__()
        self.home = home
        self.shell = shell
        self.state: dict = {}
        self._dca_fund_lookup: dict[str, dict] = {}
        self.quick_paths = [
            ("Open config", home / "config"),
            ("Open db", home / "db"),
            ("Open reports", home / "reports" / "daily"),
            ("Open logs", home / "logs"),
        ]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{QT['text_soft']};")
        layout.addWidget(self.meta)

        quick_row = QHBoxLayout()
        for label, path in self.quick_paths:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, p=path: open_path(p))
            quick_row.addWidget(button)
        if self.shell is not None:
            sync_button = QPushButton("Sync history")
            sync_button.clicked.connect(self.shell.run_history_sync)
            quick_row.addWidget(sync_button)
        quick_row.addStretch(1)
        layout.addLayout(quick_row)

        self.dca_box = SectionBox("Daily DCA")
        dca_row = QHBoxLayout()
        dca_form_host = QWidget()
        dca_form = QFormLayout(dca_form_host)
        dca_form.setContentsMargins(0, 0, 0, 0)
        dca_form.setSpacing(8)
        self.dca_fund_combo = QComboBox()
        self.dca_enabled_check = QCheckBox("Enable daily DCA")
        self.dca_amount_edit = QLineEdit()
        self.dca_extra_buy_check = QCheckBox("Allow extra discretionary buys")
        self.dca_save_button = QPushButton("Save DCA settings")
        dca_form.addRow("Fund", self.dca_fund_combo)
        dca_form.addRow("", self.dca_enabled_check)
        dca_form.addRow("Daily amount", self.dca_amount_edit)
        dca_form.addRow("", self.dca_extra_buy_check)
        dca_form.addRow("", self.dca_save_button)
        self.dca_summary_view = make_browser()
        dca_row.addWidget(dca_form_host, 1)
        dca_row.addWidget(self.dca_summary_view, 1)
        self.dca_box.body.addLayout(dca_row)
        layout.addWidget(self.dca_box)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(10)
        metric_grid.setVerticalSpacing(10)
        self.metric_cards = [MetricCard() for _ in range(4)]
        for idx, card in enumerate(self.metric_cards):
            metric_grid.addWidget(card, 0, idx)
        layout.addLayout(metric_grid)

        top_split = QSplitter()
        self.overview_box = SectionBox("System Overview")
        self.paths_box = SectionBox("Paths & Manifests")
        self.overview_view = make_browser()
        self.paths_view = make_browser()
        self.overview_box.body.addWidget(self.overview_view)
        self.paths_box.body.addWidget(self.paths_view)
        top_split.addWidget(self.overview_box)
        top_split.addWidget(self.paths_box)
        top_split.setSizes([520, 520])
        layout.addWidget(top_split)

        bottom_box = SectionBox("Detailed Settings")
        self.detail_view = make_browser()
        bottom_box.body.addWidget(self.detail_view)
        layout.addWidget(bottom_box, 1)

        self.dca_fund_combo.currentIndexChanged.connect(self._load_selected_dca_fund)
        self.dca_enabled_check.toggled.connect(self._refresh_dca_form_state)
        self.dca_save_button.clicked.connect(self._save_dca_settings)

    def refresh_data(self, state: dict) -> None:
        self.state = state
        manifests = {"intraday": state.get("intraday_manifest", {}), "nightly": state.get("nightly_manifest", {}), "realtime": state.get("realtime_manifest", {})}
        detail_text = build_settings_text(
            self.home,
            state.get("selected_date", ""),
            state.get("portfolio", {}),
            state.get("project", {}),
            state.get("strategy", {}),
            state.get("watchlist", {}),
            state.get("llm_config", {}),
            state.get("llm_raw", {}),
            state.get("realtime", {}),
            state.get("preflight", {}),
            manifests,
        )
        exposure = state.get("llm_context", {}).get("exposure_summary") or analyze_portfolio_exposure(state.get("portfolio", {}), state.get("strategy", {}))
        preflight = state.get("preflight", {}) or {}
        self.meta.setText(f"Date {state.get('selected_date', '')} | watchlist {len(state.get('watchlist', {}).get('funds', []) or [])} | preflight {preflight.get('status', 'n/a')}")
        self.metric_cards[0].set_content("Watchlist", str(len(state.get("watchlist", {}).get("funds", []) or [])), "Tracked instruments", tone="info")
        self.metric_cards[1].set_content("Model", state.get("llm_config", {}).get("model", "n/a"), state.get("llm_config", {}).get("model_provider", ""), tone="accent")
        self.metric_cards[2].set_content("Preflight", preflight.get("status", "n/a"), "Latest health check", tone="warning" if preflight.get("status") == "warning" else "success")
        self.metric_cards[3].set_content("Portfolio", money(state.get("portfolio", {}).get("total_value", 0)), state.get("portfolio", {}).get("portfolio_name", "n/a"), tone="accent")

        funds = state.get("portfolio", {}).get("funds", []) or []
        self._dca_fund_lookup = {
            item.get("fund_code", ""): item
            for item in funds
            if item.get("role") in {"tactical", "core_dca"}
        }
        selected_code = self.dca_fund_combo.currentData()
        default_dca_amount = float((state.get("strategy", {}).get("core_dca", {}) or {}).get("amount_per_fund", 25.0) or 25.0)
        self.dca_fund_combo.blockSignals(True)
        self.dca_fund_combo.clear()
        for code, item in self._dca_fund_lookup.items():
            self.dca_fund_combo.addItem(f"{code} | {item.get('fund_name', '')}", code)
        if selected_code:
            idx = self.dca_fund_combo.findData(selected_code)
            if idx >= 0:
                self.dca_fund_combo.setCurrentIndex(idx)
        if self.dca_fund_combo.count() and self.dca_fund_combo.currentIndex() < 0:
            self.dca_fund_combo.setCurrentIndex(0)
        self.dca_fund_combo.blockSignals(False)

        dca_lines = []
        for item in funds:
            if item.get("role") == "core_dca":
                dca_lines.append(
                    f"{item.get('fund_name', item.get('fund_code', ''))} | daily {money(item.get('fixed_daily_buy_amount', default_dca_amount))} | extra {'yes' if item.get('allow_extra_buys') else 'no'}"
                )
        set_browser_text(self.dca_summary_view, bullet_lines(dca_lines, "No active daily DCA funds."))
        self._load_selected_dca_fund()

        overview_lines = [
            f"model: {state.get('llm_config', {}).get('model', 'n/a')}",
            f"provider: {state.get('llm_config', {}).get('model_provider', 'n/a')}",
            f"portfolio value: {money(state.get('portfolio', {}).get('total_value', 0))}",
            f"high-vol theme weight: {pct((exposure.get('concentration_metrics', {}) or {}).get('high_volatility_theme_weight_pct', 0), 2)}",
            f"defensive buffer: {pct((exposure.get('concentration_metrics', {}) or {}).get('defensive_buffer_weight_pct', 0), 2)}",
        ]
        path_lines = [f"{label}: {path}" for label, path in self.quick_paths]
        for name, manifest in manifests.items():
            if manifest:
                path_lines.append(f"{name} manifest: {manifest.get('status', 'unknown')} | {manifest.get('current_step', '')}")
        set_browser_text(self.overview_view, bullet_lines(overview_lines, "n/a"))
        set_browser_text(self.paths_view, bullet_lines(path_lines, "n/a"))
        set_browser_text(self.detail_view, detail_text)

    def _load_selected_dca_fund(self) -> None:
        fund = self._dca_fund_lookup.get(self.dca_fund_combo.currentData() or "")
        if not fund:
            self.dca_enabled_check.setChecked(False)
            self.dca_amount_edit.setText("")
            self.dca_extra_buy_check.setChecked(False)
            self._refresh_dca_form_state()
            return
        default_amount = float((self.state.get("strategy", {}).get("core_dca", {}) or {}).get("amount_per_fund", 25.0) or 25.0)
        self.dca_enabled_check.blockSignals(True)
        self.dca_extra_buy_check.blockSignals(True)
        self.dca_enabled_check.setChecked(fund.get("role") == "core_dca")
        self.dca_amount_edit.setText(str(fund.get("fixed_daily_buy_amount", default_amount)))
        self.dca_extra_buy_check.setChecked(bool(fund.get("allow_extra_buys", False)))
        self.dca_enabled_check.blockSignals(False)
        self.dca_extra_buy_check.blockSignals(False)
        self._refresh_dca_form_state()

    def _refresh_dca_form_state(self) -> None:
        enabled = self.dca_enabled_check.isChecked()
        self.dca_amount_edit.setEnabled(enabled)
        self.dca_extra_buy_check.setEnabled(enabled)

    def _save_dca_settings(self) -> None:
        fund_code = self.dca_fund_combo.currentData()
        if not fund_code:
            QMessageBox.warning(self, "Missing fund", "Select a fund first.")
            return
        enabled = self.dca_enabled_check.isChecked()
        try:
            amount = float((self.dca_amount_edit.text().strip() or "0"))
            definition_path, current_path = update_fund_dca_settings(
                self.home,
                str(fund_code),
                enabled=enabled,
                daily_amount=amount,
                allow_extra_buys=self.dca_extra_buy_check.isChecked(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Failed to save DCA settings", str(exc))
            return
        if self.shell is not None:
            selected_date = self.shell.state.get("selected_date", "") or today_str()
            self.shell.state = load_state(self.home, selected_date)
            self.shell.refresh_all()
        QMessageBox.information(self, "DCA settings saved", f"{definition_path}\n{current_path}")
