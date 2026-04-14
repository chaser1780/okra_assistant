from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget

try:
    from task_state import (
        TASK_CARD_SPECS,
        begin_task_status,
        finish_task_status,
        initial_task_status,
        interpret_run_output_line,
        update_task_elapsed,
        update_task_step,
    )
    from ui_prefs import load_ui_state, save_ui_state
    from ui_support import build_pipeline_command, build_preflight_command, build_realtime_command, build_runtime_env, collect_dates, desktop_log_path, fix_text, load_state, summarize_state, today_str
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from task_state import (
        TASK_CARD_SPECS,
        begin_task_status,
        finish_task_status,
        initial_task_status,
        interpret_run_output_line,
        update_task_elapsed,
        update_task_step,
    )
    from ui_prefs import load_ui_state, save_ui_state
    from ui_support import build_pipeline_command, build_preflight_command, build_realtime_command, build_runtime_env, collect_dates, desktop_log_path, fix_text, load_state, summarize_state, today_str

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from .pages.dashboard import DashboardPage
from .pages.data_pages import AgentsPage, PortfolioPage, RealtimePage, ResearchPage
from .pages.holding_pages import FundDetailPage, HoldingsTrendPage
from .pages.insights_pages import ReviewPage, SettingsPage
from .pages.runtime_page import RuntimePage
from .pages.trade_page import TradePage
from .theme import APP_TITLE, NAV_ITEMS, QT, STYLE
from .widgets import SectionBox


DEFAULT_AGENT_HOME = Path(r"F:\okra_assistant")


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
        self.current_page_key = "dash"
        self.previous_page_key = "dash"

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
            item.setData(256, key)
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
        self.chain_status = QLabel("")
        self.chain_status.setWordWrap(True)
        self.chain_status.setStyleSheet(f"color:{QT['text_soft']};")
        status.body.addWidget(self.status_badge)
        status.body.addWidget(self.chain_status)
        sidebar_layout.addWidget(status)
        shell.addWidget(sidebar)

        self.stack = QStackedWidget()
        shell.addWidget(self.stack, 1)

        self.dashboard_page = DashboardPage()
        self.portfolio_page = PortfolioPage()
        self.holdings_page = HoldingsTrendPage()
        self.research_page = ResearchPage()
        self.trade_page = TradePage(self)
        self.review_page = ReviewPage()
        self.realtime_page = RealtimePage()
        self.agents_page = AgentsPage()
        self.runtime_page = RuntimePage(self)
        self.settings_page = SettingsPage(self.home, self)
        self.fund_detail_page = FundDetailPage()

        self.pages = {
            "dash": self.dashboard_page,
            "portfolio": self.portfolio_page,
            "holdings": self.holdings_page,
            "research": self.research_page,
            "trade": self.trade_page,
            "review": self.review_page,
            "rt": self.realtime_page,
            "agents": self.agents_page,
            "runtime": self.runtime_page,
            "settings": self.settings_page,
            "fund_detail": self.fund_detail_page,
        }
        for key in [item[0] for item in NAV_ITEMS] + ["fund_detail"]:
            self.stack.addWidget(self.pages[key])

        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        self.date_combo.currentTextChanged.connect(self._on_date_changed)
        self.btn_today.clicked.connect(self._switch_to_today)
        self.btn_refresh.clicked.connect(self._refresh_selected_date)
        self.realtime_page.set_open_callback(lambda row: self.open_fund_detail(row.get("fund_code", ""), source_key="rt"))
        self.holdings_page.set_open_callback(lambda row: self.open_fund_detail(row.get("fund_code", ""), source_key="holdings"))
        self.fund_detail_page.back_button.clicked.connect(self.go_back)

        target = self.ui_state.get("last_tab", "dash")
        self._select_page(target if target in self.pages else "dash")
        self._set_status_badge("idle")

    def _select_page(self, key: str) -> None:
        keys = [self.nav_list.item(i).data(256) for i in range(self.nav_list.count())]
        if key not in keys:
            key = "dash"
        self.nav_list.setCurrentRow(keys.index(key))

    def _on_nav_changed(self, row: int) -> None:
        if row < 0:
            return
        key = self.nav_list.item(row).data(256)
        self.stack.setCurrentWidget(self.pages[key])
        self.current_page_key = key
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

        summary = summarize_state(self.state)
        self.chain_status.setText(self._today_chain_status_text())
        self._set_status_badge("running" if self.current_process and self.current_process.state() != QProcess.NotRunning else ("warning" if summary.get("preflight_status") == "warning" else "idle"))
        self.dashboard_page.refresh_data(self.home, self.state)
        self.portfolio_page.refresh_data(self.state)
        self.holdings_page.refresh_data(self.home, self.state)
        self.research_page.refresh_data(self.state)
        self.trade_page.refresh_data(self.state)
        self.review_page.refresh_data(self.home, self.state)
        self.realtime_page.refresh_data(self.state)
        self.agents_page.refresh_data(self.state)
        self.runtime_page.refresh_cards(self.home, self.task_status, self.active_job_name)
        self.settings_page.refresh_data(self.state)
        if self.current_page_key == "fund_detail" and getattr(self.fund_detail_page, "fund_code", ""):
            self.fund_detail_page.refresh_data(self.home, self.state, self.fund_detail_page.fund_code)
        self.statusBar().showMessage(
            f"查看日 {summary.get('selected_date', selected)} | 建议模式 {summary.get('advice_mode', 'unknown')} | "
            f"失败智能体 {len(summary.get('failed_agent_names', []))}"
        )

    def open_fund_detail(self, fund_code: str, *, source_key: str | None = None) -> None:
        if not fund_code:
            return
        self.previous_page_key = source_key or self.current_page_key or "dash"
        self.current_page_key = "fund_detail"
        self.fund_detail_page.refresh_data(self.home, self.state, fund_code)
        self.stack.setCurrentWidget(self.fund_detail_page)

    def go_back(self) -> None:
        target = self.previous_page_key or "dash"
        self.current_page_key = target
        if target in self.pages:
            self.stack.setCurrentWidget(self.pages[target])
            keys = [self.nav_list.item(i).data(256) for i in range(self.nav_list.count())]
            if target in keys and self.nav_list.currentRow() != keys.index(target):
                self.nav_list.setCurrentRow(keys.index(target))

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
        self.status_badge.setStyleSheet(f"background:{bg}; color:{fg}; border:1px solid {border}; border-radius:9px; padding:4px 8px; font-weight:600;")

    def run_pipeline(self, mode: str) -> None:
        self.start_process(task_kind=mode if mode in TASK_CARD_SPECS else None, job_name=mode, command=build_pipeline_command(self.home, today_str(), mode))

    def run_realtime(self) -> None:
        self.start_process(task_kind="realtime", job_name="realtime", command=build_realtime_command(self.home, today_str()))

    def run_preflight(self) -> None:
        self.start_process(task_kind=None, job_name="preflight", command=build_preflight_command(self.home, "desktop"))

    def run_history_sync(self) -> None:
        command = [sys.executable, "-B", "-X", "utf8", str(self.home / "scripts" / "sync_history_store.py"), "--agent-home", str(self.home)]
        self.start_process(task_kind=None, job_name="history_sync", command=command)

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
