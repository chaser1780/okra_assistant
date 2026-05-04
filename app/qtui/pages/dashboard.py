from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..theme import QT
from ..widgets import HeroCard, SectionBox, make_browser, set_browser_text, style_button


class DashboardPage(QWidget):
    def __init__(self, shell=None):
        super().__init__()
        self.shell = shell
        self.primary_fund_code = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header_frame = QFrame()
        header_frame.setObjectName("TopBar")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(16, 13, 16, 13)
        header.setSpacing(10)
        title_block = QVBoxLayout()
        title_block.setSpacing(3)
        self.title = QLabel("基金研究驾驶舱")
        self.title.setStyleSheet(f"color:{QT['text']}; font-family:'Microsoft YaHei UI', 'Segoe UI'; font-size:20pt; font-weight:850;")
        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{QT['text_soft']}; font-family:'Microsoft YaHei UI', 'Segoe UI'; font-size:9pt;")
        title_block.addWidget(self.title)
        title_block.addWidget(self.meta)
        header.addLayout(title_block)
        header.addStretch(1)

        self.open_research_button = style_button(QPushButton("研究"), "ghost")
        self.open_realtime_button = style_button(QPushButton("实时"), "ghost")
        self.run_intraday_button = style_button(QPushButton("运行日内"), "primary")
        self.run_realtime_button = style_button(QPushButton("刷新"), "secondary")
        self.open_primary_button = style_button(QPushButton("主基金"), "secondary")
        self.open_primary_button.setEnabled(False)
        for button in (self.open_research_button, self.open_realtime_button, self.run_intraday_button, self.run_realtime_button, self.open_primary_button):
            button.setMinimumWidth(76)
            button.setMinimumHeight(34)
            header.addWidget(button)
        layout.addWidget(header_frame)

        hero_grid = QGridLayout()
        hero_grid.setHorizontalSpacing(12)
        hero_grid.setVerticalSpacing(12)
        self.hero_cards = [HeroCard() for _ in range(4)]
        for idx, card in enumerate(self.hero_cards):
            hero_grid.addWidget(card, 0, idx)
        layout.addLayout(hero_grid)

        cockpit = QGridLayout()
        cockpit.setHorizontalSpacing(12)
        cockpit.setVerticalSpacing(12)
        self.focus_box = SectionBox("今日决策流")
        self.market_box = SectionBox("市场与风险")
        self.committee_box = SectionBox("投委会分歧与裁决")
        self.provider_box = SectionBox("数据可信度")
        self.focus_view = make_browser()
        self.market_view = make_browser()
        self.committee_view = make_browser()
        self.provider_view = make_browser()
        self.focus_box.body.addWidget(self.focus_view)
        self.market_box.body.addWidget(self.market_view)
        self.committee_box.body.addWidget(self.committee_view)
        self.provider_box.body.addWidget(self.provider_view)
        cockpit.addWidget(self.focus_box, 0, 0, 2, 1)
        cockpit.addWidget(self.market_box, 0, 1)
        cockpit.addWidget(self.committee_box, 1, 1)
        cockpit.addWidget(self.provider_box, 0, 2, 2, 1)
        layout.addLayout(cockpit, 3)

        lower_grid = QGridLayout()
        lower_grid.setHorizontalSpacing(12)
        lower_grid.setVerticalSpacing(12)
        self.change_box = SectionBox("与上一期相比")
        self.summary_box = SectionBox("一句话摘要")
        self.change_view = make_browser()
        self.summary_view = make_browser()
        self.change_box.body.addWidget(self.change_view)
        self.summary_box.body.addWidget(self.summary_view)
        lower_grid.addWidget(self.change_box, 0, 0)
        lower_grid.addWidget(self.summary_box, 0, 1)
        layout.addLayout(lower_grid)

        raw_box = SectionBox("工作台详情")
        self.raw_view = make_browser()
        raw_box.body.addWidget(self.raw_view)
        layout.addWidget(raw_box, 1)

        self.open_research_button.clicked.connect(lambda: self.shell.jump_to_page("research") if self.shell else None)
        self.open_realtime_button.clicked.connect(lambda: self.shell.jump_to_page("rt") if self.shell else None)
        self.run_intraday_button.clicked.connect(lambda: self.shell.run_pipeline("intraday") if self.shell else None)
        self.run_realtime_button.clicked.connect(lambda: self.shell.run_realtime() if self.shell else None)
        self.open_primary_button.clicked.connect(self._open_primary_fund)

    def _open_primary_fund(self) -> None:
        if self.shell and self.primary_fund_code:
            self.shell.open_fund_detail(self.primary_fund_code, source_key="dash")

    def refresh_view_model(self, view_model) -> None:
        self.meta.setText(view_model.meta)
        self.primary_fund_code = view_model.primary_fund_code
        self.open_primary_button.setEnabled(bool(self.primary_fund_code))
        for idx, metric in enumerate(view_model.metrics[:4]):
            self.hero_cards[idx].set_content(metric.title, metric.value, metric.body, tone=metric.tone, pill=metric.tone.upper())
        set_browser_text(self.focus_view, view_model.focus_text)
        set_browser_text(self.market_view, view_model.market_text)
        set_browser_text(self.change_view, view_model.change_text)
        set_browser_text(self.summary_view, view_model.summary_text)
        set_browser_text(self.raw_view, view_model.detail_text)
        set_browser_text(self.committee_view, getattr(view_model, "committee_text", "- 暂无投委会结构化摘要"))
        set_browser_text(self.provider_view, getattr(view_model, "provider_text", "- 暂无数据源健康摘要"))
