from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from task_state import TASK_CARD_SPECS, build_task_card_text, current_task_result_info

from ..theme import QT
from ..widgets import SectionBox, make_browser


class RuntimePage(QWidget):
    def __init__(self, shell):
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
        self.card_views = {}
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
        self.log.setPlainText(text)

    def append_log(self, text: str) -> None:
        self.log.appendPlainText(text)
