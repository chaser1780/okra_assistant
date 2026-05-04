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
    from page_registry import hidden_page_keys, qt_nav_items
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
    from ui_support import (
        build_pipeline_command,
        build_preflight_command,
        build_realtime_command,
        build_replay_command,
        build_runtime_env,
        collect_dates,
        desktop_log_path,
        fix_text,
        latest_manifest,
        pending_nightly_catchup_dates,
        should_autorun_intraday_on_boot,
        should_refresh_realtime_on_boot,
        today_str,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from page_registry import hidden_page_keys, qt_nav_items
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
    from ui_support import (
        build_pipeline_command,
        build_preflight_command,
        build_realtime_command,
        build_replay_command,
        build_runtime_env,
        collect_dates,
        desktop_log_path,
        fix_text,
        latest_manifest,
        pending_nightly_catchup_dates,
        should_autorun_intraday_on_boot,
        should_refresh_realtime_on_boot,
        today_str,
    )

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from .pages import create_qt_pages
from .state_service import DesktopStateService
from .theme import APP_TITLE, QT, STYLE
from .widgets import SectionBox, style_button


DEFAULT_AGENT_HOME = Path(r"F:\okra_assistant")

NAV_ICONS = {
    "dash": "◆",
    "portfolio": "◼",
    "holdings": "⌁",
    "research": "◎",
    "trade": "↔",
    "review": "✓",
    "rt": "◌",
    "agents": "✦",
    "runtime": "▣",
    "settings": "⚙",
}



class QtDesktopShell(QMainWindow):
    def __init__(self, home: Path, selected: str | None = None):
        super().__init__()
        self.home = home
        self.nav_items = qt_nav_items()
        self.state_service = DesktopStateService(home)
        self.ui_state = load_ui_state(home)
        self.snapshot = self.state_service.load_snapshot(selected)
        self.state = self.snapshot.state
        self.task_status = initial_task_status()
        self.current_process: QProcess | None = None
        self.process_lines: list[str] = []
        self.active_job_name = ""
        self.active_task_kind = ""
        self.active_job_started_at: datetime | None = None
        self.after_finish_callback = None
        self.current_page_key = "dash"
        self.previous_page_key = "dash"
        self.dirty_pages: set[str] = set()
        self.startup_task_queue: list[dict] = []
        self.startup_sync_active = False

        self.setWindowTitle(APP_TITLE)
        self.resize(1560, 980)
        self.setStyleSheet(STYLE)
        self._build_ui()
        self.refresh_all()

        self._runtime_timer = QTimer(self)
        self._runtime_timer.timeout.connect(self._tick_runtime)
        self._runtime_timer.start(1000)
        QTimer.singleShot(300, self._maybe_startup_sync)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(16, 16, 16, 16)
        shell.setSpacing(14)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(232)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(13, 13, 13, 13)
        sidebar_layout.setSpacing(11)
        title = QLabel("OKRA")
        title.setStyleSheet(f"color:{QT['text']}; font-family:Bahnschrift, 'Segoe UI'; font-size:24px; font-weight:850;")
        subtitle = QLabel("AI Fund Research Terminal")
        subtitle.setStyleSheet(f"color:{QT['accent']}; font-size:10px; font-weight:800;")
        sidebar_layout.addWidget(title)
        sidebar_layout.addWidget(subtitle)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("NavList")
        for key, label in self.nav_items:
            icon = NAV_ICONS.get(key, "•")
            item = QListWidgetItem(f"{icon}  {label}")
            item.setData(256, key)
            self.nav_list.addItem(item)
        sidebar_layout.addWidget(self.nav_list, 1)

        controls = SectionBox("控制")
        self.date_combo = QComboBox()
        self.btn_today = style_button(QPushButton("回到今天"), "secondary")
        self.btn_refresh = style_button(QPushButton("刷新"), "ghost")
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

        content_canvas = QFrame()
        content_canvas.setObjectName("ContentCanvas")
        content_layout = QVBoxLayout(content_canvas)
        content_layout.setContentsMargins(15, 15, 15, 15)
        content_layout.setSpacing(0)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)
        shell.addWidget(content_canvas, 1)

        self.pages = create_qt_pages(self)
        self.dashboard_page = self.pages["dash"]
        self.portfolio_page = self.pages["portfolio"]
        self.holdings_page = self.pages["holdings"]
        self.research_page = self.pages["research"]
        self.trade_page = self.pages["trade"]
        self.review_page = self.pages["review"]
        self.realtime_page = self.pages["rt"]
        self.agents_page = self.pages["agents"]
        self.runtime_page = self.pages["runtime"]
        self.settings_page = self.pages["settings"]
        self.fund_detail_page = self.pages["fund_detail"]

        for key in [item[0] for item in self.nav_items] + hidden_page_keys():
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
        self._mark_pages_dirty()
        self._set_status_badge("idle")

    def _select_page(self, key: str) -> None:
        keys = [item[0] for item in self.nav_items]
        if key not in keys:
            key = "dash"
        self.nav_list.setCurrentRow(keys.index(key))

    def _on_nav_changed(self, row: int) -> None:
        if row < 0:
            return
        key = self.nav_list.item(row).data(256)
        self.stack.setCurrentWidget(self.pages[key])
        self._activate_page(key)

    def _activate_page(self, key: str) -> None:
        self.current_page_key = key
        self._refresh_page_if_needed(key)
        self.ui_state["last_tab"] = key
        save_ui_state(self.home, self.ui_state)

    def _on_date_changed(self, text: str) -> None:
        if not text:
            return
        self._reload_snapshot(text)
        self.refresh_all()

    def _switch_to_today(self) -> None:
        today = today_str()
        idx = self.date_combo.findText(today)
        if idx >= 0:
            self.date_combo.setCurrentIndex(idx)
        self._refresh_selected_date()

    def _refresh_selected_date(self) -> None:
        self._reload_snapshot(self.date_combo.currentText() or today_str())
        self.refresh_all()

    def _reload_snapshot(self, selected: str | None = None) -> None:
        self.snapshot = self.state_service.load_snapshot(selected)
        self.state = self.snapshot.state

    def _mark_pages_dirty(self) -> None:
        self.dirty_pages = set(self.pages.keys())

    def _refresh_page(self, key: str) -> None:
        if key == "dash":
            self.dashboard_page.refresh_view_model(self.state_service.build_dashboard_view_model(self.snapshot))
        elif key == "portfolio":
            self.portfolio_page.refresh_data(self.state)
        elif key == "holdings":
            self.holdings_page.refresh_data(self.home, self.state)
        elif key == "research":
            self.research_page.refresh_view_model(self.state_service.build_research_view_model(self.snapshot))
        elif key == "trade":
            self.trade_page.refresh_data(self.state)
        elif key == "review":
            self.review_page.refresh_view_model(self.state_service.build_review_view_model(self.snapshot))
        elif key == "rt":
            self.realtime_page.refresh_view_model(self.state_service.build_realtime_view_model(self.snapshot))
        elif key == "agents":
            self.agents_page.refresh_view_model(self.state_service.build_agents_view_model(self.snapshot))
        elif key == "runtime":
            self.runtime_page.refresh_view_model(self.state_service.build_runtime_view_model(self.task_status, self.active_job_name))
        elif key == "settings":
            self.settings_page.refresh_data(self.state)
        elif key == "fund_detail" and getattr(self.fund_detail_page, "fund_code", ""):
            self.fund_detail_page.refresh_data(self.home, self.state, self.fund_detail_page.fund_code)
        self.dirty_pages.discard(key)

    def _refresh_page_if_needed(self, key: str) -> None:
        if key in self.dirty_pages or key == "runtime":
            self._refresh_page(key)

    def refresh_all(self) -> None:
        shell_vm = self.state_service.build_shell_view_model(
            self.snapshot,
            running=bool(self.current_process and self.current_process.state() != QProcess.NotRunning),
            chain_status=self._today_chain_status_text(),
        )
        dates = shell_vm.dates or collect_dates(self.home)
        selected = shell_vm.selected_date or today_str()
        self.date_combo.blockSignals(True)
        self.date_combo.clear()
        self.date_combo.addItems(dates)
        idx = self.date_combo.findText(selected)
        if idx >= 0:
            self.date_combo.setCurrentIndex(idx)
        self.date_combo.blockSignals(False)

        self.chain_status.setText(shell_vm.chain_status)
        self._set_status_badge(shell_vm.status_badge_state)
        self._mark_pages_dirty()
        self.runtime_page.refresh_view_model(self.state_service.build_runtime_view_model(self.task_status, self.active_job_name))
        self.dirty_pages.discard("runtime")
        self._refresh_page_if_needed(self.current_page_key if self.current_page_key in self.pages else "dash")
        self._show_status_message(shell_vm.status_bar_text)

    def _show_status_message(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def jump_to_page(self, key: str) -> None:
        self._select_page(key)

    def _refresh_runtime_page(self) -> None:
        self.runtime_page.refresh_view_model(self.state_service.build_runtime_view_model(self.task_status, self.active_job_name))

    def _append_runtime_log(self, line: str) -> None:
        clean = fix_text(str(line).strip())
        if not clean:
            return
        self.process_lines.append(clean)
        self.runtime_page.append_log(clean)

    def _build_startup_task_queue(self) -> list[dict]:
        queue: list[dict] = []
        portfolio_as_of = str(self.state.get("portfolio", {}).get("as_of_date", "") or self.state.get("portfolio_date", "") or "")
        today = today_str()
        for report_date in pending_nightly_catchup_dates(self.home, portfolio_as_of):
            queue.append(
                {
                    "task_kind": "nightly",
                    "job_name": f"startup_nightly_{report_date}",
                    "run_date": report_date,
                    "command": build_pipeline_command(self.home, report_date, "nightly"),
                    "label": f">>> AUTO_SYNC nightly {report_date}",
                }
            )
        if should_autorun_intraday_on_boot(self.home, today):
            command = build_pipeline_command(self.home, today, "intraday")
            if (self.home / "db" / "llm_context" / f"{today}.json").exists() or (self.home / "db" / "agent_outputs" / today / "aggregate.json").exists():
                command = [*command, "--resume-existing"]
            queue.append(
                {
                    "task_kind": "intraday",
                    "job_name": f"startup_intraday_{today}",
                    "run_date": today,
                    "command": command,
                    "label": f">>> AUTO_SYNC intraday {today}",
                }
            )
        if should_refresh_realtime_on_boot(self.home, today):
            queue.append(
                {
                    "task_kind": "realtime",
                    "job_name": f"startup_realtime_{today}",
                    "run_date": today,
                    "command": build_realtime_command(self.home, today),
                    "label": f">>> AUTO_SYNC realtime {today}",
                }
            )
        return queue

    def _maybe_startup_sync(self) -> None:
        if self.current_process and self.current_process.state() != QProcess.NotRunning:
            return
        if self.startup_sync_active:
            return
        self.startup_task_queue = self._build_startup_task_queue()
        if not self.startup_task_queue:
            return
        self.startup_sync_active = True
        self.runtime_page.set_log(">>> AUTO_SYNC_START")
        self._append_runtime_log(f">>> AUTO_SYNC_PLAN tasks={len(self.startup_task_queue)}")
        self._refresh_runtime_page()
        self._run_next_startup_task()

    def _run_next_startup_task(self) -> None:
        if not self.startup_task_queue:
            self.startup_sync_active = False
            self._append_runtime_log(">>> AUTO_SYNC_DONE")
            self._refresh_runtime_page()
            self.refresh_all()
            return
        task = self.startup_task_queue.pop(0)
        self._append_runtime_log(task["label"])
        self.start_process(
            task_kind=task.get("task_kind"),
            job_name=task["job_name"],
            command=task["command"],
            on_finish=lambda success, output, planned=task: self._handle_startup_task_finished(planned, success, output),
            run_date=task.get("run_date"),
        )

    def _handle_startup_task_finished(self, task: dict, success: bool, output: str) -> None:
        status = "ok" if success else "failed"
        self._append_runtime_log(f">>> AUTO_SYNC_RESULT {task.get('job_name')} {status}")
        if not success:
            self.startup_task_queue = []
            self.startup_sync_active = False
            self._refresh_runtime_page()
            self.statusBar().showMessage(f"自动补全失败：{task.get('job_name')}")
            return
        self._run_next_startup_task()

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
            self._refresh_page_if_needed(target)
            keys = [item[0] for item in self.nav_items]
            if target in keys and self.nav_list.currentRow() != keys.index(target):
                self.nav_list.setCurrentRow(keys.index(target))

    def _today_chain_status_text(self) -> str:
        today = today_str()
        manifest = self.state.get("today_intraday_manifest", {}) or {}
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

    def start_process(self, *, task_kind: str | None, job_name: str, command: list[str], on_finish=None, run_date: str | None = None) -> None:
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
            begin_task_status(self.task_status, task_kind, run_date or today_str(), self.active_job_started_at)
        self.runtime_page.set_log("\n".join(self.process_lines))
        self._refresh_runtime_page()
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
        self._refresh_runtime_page()

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
        self._reload_snapshot(self.date_combo.currentText() or today_str())
        self.refresh_all()
        if callback:
            callback(success, output)

    def _tick_runtime(self) -> None:
        if not self.current_process or self.current_process.state() == QProcess.NotRunning or not self.active_job_started_at:
            return
        elapsed = int((datetime.now() - self.active_job_started_at).total_seconds())
        if self.active_task_kind in self.task_status:
            update_task_elapsed(self.task_status, self.active_task_kind, elapsed)
            manifest = self._active_manifest_snapshot()
            current_step = fix_text(str((manifest or {}).get("current_step", "")).strip())
            if current_step:
                update_task_step(self.task_status, self.active_task_kind, current_step)
        self._refresh_runtime_page()

    def _active_manifest_snapshot(self) -> dict:
        if self.active_task_kind not in TASK_CARD_SPECS:
            return {}
        run_date = str(self.task_status.get(self.active_task_kind, {}).get("run_date") or today_str())
        if self.active_task_kind == "intraday":
            return latest_manifest(self.home, "daily_pipeline", run_date, mode="intraday")
        if self.active_task_kind == "nightly":
            return latest_manifest(self.home, "daily_pipeline", run_date, mode="nightly")
        if self.active_task_kind == "realtime":
            return latest_manifest(self.home, "realtime_monitor", run_date, mode="realtime")
        return {}

    def _set_status_badge(self, state: str) -> None:
        mapping = {
            "idle": ("就绪", QT["info_soft"], QT["info"], "#23405F"),
            "running": ("运行中", QT["accent_soft"], QT["info"], QT["accent"]),
            "warning": ("注意", QT["warning_soft"], QT["warning"], "#5C4020"),
        }
        text, bg, fg, border = mapping.get(state, mapping["idle"])
        self.status_badge.setText(text)
        self.status_badge.setStyleSheet(f"background:{bg}; color:{fg}; border:1px solid {border}; border-radius:11px; padding:4px 9px; font-weight:800;")

    def run_pipeline(self, mode: str, task_date: str | None = None) -> None:
        run_date = task_date or today_str()
        self.start_process(task_kind=mode if mode in TASK_CARD_SPECS else None, job_name=mode, command=build_pipeline_command(self.home, run_date, mode), run_date=run_date)

    def run_realtime(self, task_date: str | None = None) -> None:
        run_date = task_date or today_str()
        self.start_process(task_kind="realtime", job_name="realtime", command=build_realtime_command(self.home, run_date), run_date=run_date)

    def run_preflight(self) -> None:
        self.start_process(task_kind=None, job_name="preflight", command=build_preflight_command(self.home, "desktop"))

    def run_replay_experiment(self, start_date: str, end_date: str, mode: str, *, write_learning: bool = False) -> None:
        command = build_replay_command(
            self.home,
            start_date,
            end_date,
            mode,
            write_learning=write_learning,
            experiment_name=f"ui_{mode}_{start_date}_{end_date}",
        )

        def _after_finish(success: bool, output: str) -> None:
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            summary_path = lines[-1] if lines else ""
            if success:
                detail = f"Summary: {summary_path}" if summary_path else "Replay finished."
                if write_learning:
                    detail += "\nLearning ledger was updated."
                QMessageBox.information(self, "Replay Complete", detail)
            else:
                QMessageBox.warning(self, "Replay Failed", "Replay experiment failed. Check the runtime log for details.")

        self.start_process(task_kind=None, job_name="replay_experiment", command=command, on_finish=_after_finish)

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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PySide6 desktop shell for okra assistant.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date")
    parser.add_argument("--dump-state", action="store_true")
    args = parser.parse_args(argv)
    home = Path(args.agent_home).expanduser() if args.agent_home else DEFAULT_AGENT_HOME
    service = DesktopStateService(home)
    snapshot = service.load_snapshot(args.date)
    if args.dump_state:
        print(json.dumps(snapshot.summary, ensure_ascii=False, indent=2))
        return
    raise SystemExit(run_app(home, args.date))
