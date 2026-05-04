from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from task_state import TASK_CARD_SPECS

from ..theme import QT
from ..widgets import SectionBox, make_browser, set_browser_text, style_button


class RuntimePage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        actions = QHBoxLayout()
        self.btn_intraday = style_button(QPushButton("运行日内链路"), "primary")
        self.btn_realtime = style_button(QPushButton("刷新实时快照"), "secondary")
        self.btn_nightly = style_button(QPushButton("运行学习周期"), "secondary")
        self.btn_preflight = style_button(QPushButton("运行健康检查"), "ghost")
        for button in (self.btn_intraday, self.btn_realtime, self.btn_nightly, self.btn_preflight):
            actions.addWidget(button)
        self.copy_log_button = style_button(QPushButton("复制日志"), "ghost")
        self.clear_log_button = style_button(QPushButton("清空日志"), "ghost")
        self.auto_scroll_check = QCheckBox("自动滚动")
        self.auto_scroll_check.setChecked(True)
        actions.addWidget(self.copy_log_button)
        actions.addWidget(self.clear_log_button)
        actions.addWidget(self.auto_scroll_check)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.banner = QLabel("运行控制台：等待任务调度。")
        self.banner.setStyleSheet(f"color:{QT['text_soft']}; font-weight:600;")
        layout.addWidget(self.banner)

        cards = QGridLayout()
        cards.setHorizontalSpacing(10)
        self.card_views = {}
        for idx, key in enumerate(("intraday", "realtime", "nightly")):
            box = SectionBox(TASK_CARD_SPECS[key]["title"])
            view = make_browser()
            box.body.addWidget(view)
            cards.addWidget(box, 0, idx)
            self.card_views[key] = view
        layout.addLayout(cards)

        log_card = SectionBox("实时日志")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(
            f"QPlainTextEdit {{ background:{QT['console_bg']}; color:{QT['console_text']}; "
            f"border:1px solid {QT['line']}; border-radius:12px; padding:10px; font-family:Consolas; }}"
        )
        log_card.body.addWidget(self.log)
        self.log_hint = QLabel("日志输出会实时写入；复制日志便于排查失败链路。")
        self.log_hint.setStyleSheet(f"color:{QT['text_soft']};")
        log_card.body.addWidget(self.log_hint)
        layout.addWidget(log_card, 1)

        self.btn_intraday.clicked.connect(lambda: self.shell.run_pipeline("intraday"))
        self.btn_realtime.clicked.connect(self.shell.run_realtime)
        self.btn_nightly.clicked.connect(lambda: self.shell.run_pipeline("nightly"))
        self.btn_preflight.clicked.connect(self.shell.run_preflight)
        self.copy_log_button.clicked.connect(self.copy_log)
        self.clear_log_button.clicked.connect(self.clear_log)

    def refresh_view_model(self, view_model) -> None:
        for key, view in self.card_views.items():
            set_browser_text(view, view_model.cards.get(key, "暂无任务信息。"))
        self.banner.setText(view_model.banner)

    def set_log(self, text: str) -> None:
        self.log.setPlainText(text)
        if self.auto_scroll_check.isChecked():
            self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def append_log(self, text: str) -> None:
        self.log.appendPlainText(text)
        if self.auto_scroll_check.isChecked():
            self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def copy_log(self) -> None:
        QGuiApplication.clipboard().setText(self.log.toPlainText())

    def clear_log(self) -> None:
        self.log.clear()
