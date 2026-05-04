from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSplitter,
    QTableView,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QPushButton,
)

from .theme import QT, TONE


def tone_tokens(tone: str) -> dict:
    return TONE.get(tone, {"fg": QT["text_soft"], "bg": QT["surface_alt"], "border": QT["line"]})


def apply_shadow(widget: QWidget, blur: int = 22, alpha: int = 90, y_offset: int = 8) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


def style_button(button: QPushButton, variant: str = "secondary") -> QPushButton:
    button.setProperty("variant", variant)
    button.style().unpolish(button)
    button.style().polish(button)
    return button


def set_browser_text(target: QTextBrowser, text: str, *, markdown: bool = False) -> None:
    if markdown:
        target.setMarkdown(text or "")
    else:
        target.setPlainText(text or "")


def make_browser() -> QTextBrowser:
    view = QTextBrowser()
    view.setOpenExternalLinks(True)
    view.setReadOnly(True)
    return view


def bullet_lines(items: list[str], empty_text: str = "暂无") -> str:
    values = [item for item in (items or []) if item]
    if not values:
        return f"- {empty_text}"
    return "\n".join(f"- {item}" for item in values)


class SectionBox(QGroupBox):
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(13, 18, 13, 13)
        self.body.setSpacing(10)


class StatusPill(QLabel):
    def __init__(self, text: str = "", tone: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(22)
        self.set_tone(text, tone)

    def set_tone(self, text: str, tone: str = "neutral") -> None:
        token = tone_tokens(tone)
        self.setText(text)
        self.setStyleSheet(
            f"background:{token['bg']}; color:{token['fg']}; border:1px solid {token['border']}; "
            "border-radius:8px; padding:2px 9px; font-size:8.2pt; font-weight:800;"
        )


class HeroCard(QFrame):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("HeroCard")
        apply_shadow(self, blur=30, alpha=78, y_offset=9)
        layout = QVBoxLayout(self)
        self.setMinimumHeight(132)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setStyleSheet(f"color:{QT['text_soft']}; font-family:'Microsoft YaHei UI', 'Segoe UI'; font-size:8.5pt; font-weight:800;")
        self.pill = StatusPill("READY", "accent")
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.pill)
        self.value = QLabel("")
        self.value.setStyleSheet(f"color:{QT['text']}; font-family:'Microsoft YaHei UI', 'Segoe UI'; font-size:18pt; font-weight:850;")
        self.body = QLabel("")
        self.body.setWordWrap(True)
        self.body.setStyleSheet(f"color:{QT['text_soft']}; font-family:'Microsoft YaHei UI', 'Segoe UI'; font-size:8.7pt; line-height:130%;")
        layout.addLayout(header)
        layout.addWidget(self.value)
        layout.addWidget(self.body)

    def set_content(self, title: str, value: str, body: str, tone: str = "accent", pill: str | None = None) -> None:
        token = tone_tokens(tone)
        self.setStyleSheet(
            f"QFrame#HeroCard {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {QT['surface_alt']}, stop:0.58 {QT['surface']}, stop:1 {token['bg']}); "
            f"border:1px solid {token['border']}; border-radius:10px; }}"
        )
        self.title.setText(title)
        self.value.setText(value)
        self.body.setText(body)
        self.pill.set_tone(pill or tone.upper(), tone)


class MetricCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MetricCard")
        apply_shadow(self, blur=20, alpha=58, y_offset=6)
        layout = QVBoxLayout(self)
        self.setMinimumHeight(108)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(6)
        self.title = QLabel("")
        self.title.setStyleSheet(f"color:{QT['text_soft']}; font-size:8.5pt; font-weight:700;")
        self.value = QLabel("")
        self.value.setStyleSheet(f"color:{QT['text']}; font-family:'Microsoft YaHei UI', Bahnschrift; font-size:16pt; font-weight:850;")
        self.body = QLabel("")
        self.body.setWordWrap(True)
        self.body.setStyleSheet(f"color:{QT['muted']}; font-size:8.5pt; line-height:128%;")
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.body)

    def set_content(self, title: str, value: str, body: str, tone: str = "neutral") -> None:
        token = tone_tokens(tone)
        self.setStyleSheet(
            f"QFrame#MetricCard {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {QT['surface']}, stop:0.72 #111827, stop:1 {token['bg']}); "
            f"border:1px solid {token['border']}; border-radius:10px; }}"
        )
        self.title.setStyleSheet(f"color:{token['fg']}; font-size:8.5pt; font-weight:800;")
        self.title.setText(title)
        self.value.setText(value)
        self.body.setText(body)


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

    def set_content(self, meta: str, text: str, metrics: list[tuple[str, str, str, str]] | None = None) -> None:
        self.meta.setText(meta)
        metrics = metrics or []
        for idx, card in enumerate(self.metric_cards):
            if idx < len(metrics):
                title, value, body, tone = metrics[idx]
                card.set_content(title, value, body, tone=tone)
                card.show()
            else:
                card.hide()
        set_browser_text(self.view, text, markdown=self.markdown)


class FilterableTablePage(QWidget):
    def __init__(self, title: str, headers: list[str], *, show_summary: bool = False, show_detail: bool = True, split_sizes: tuple[int, int] = (560, 760)):
        super().__init__()
        self.headers = headers
        self.raw_rows: list[dict] = []
        self.filtered_rows: list[dict] = []
        self.detail_builder = None
        self.cells_builder = None
        self.filter_handler = None
        self.row_key_builder = None
        self.item_styler = None
        self.open_handler = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{QT['text_soft']};")
        layout.addWidget(self.meta)

        self.metrics_layout = QGridLayout()
        self.metrics_layout.setHorizontalSpacing(10)
        self.metrics_layout.setVerticalSpacing(10)
        self.metric_cards = [MetricCard() for _ in range(4)]
        for idx, card in enumerate(self.metric_cards):
            self.metrics_layout.addWidget(card, 0, idx)
            card.hide()
        layout.addLayout(self.metrics_layout)

        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索代码、名称或摘要")
        self.toolbar.addWidget(self.search, 1)
        self.toolbar.addStretch(1)
        layout.addLayout(self.toolbar)

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
        self.summary = None
        self.detail = None
        if show_summary or show_detail:
            splitter = QSplitter(Qt.Horizontal)
            splitter.addWidget(left)

            right = QWidget()
            right_layout = QVBoxLayout(right)
            right_layout.setContentsMargins(0, 0, 0, 0)
            if show_summary:
                summary_box = SectionBox("摘要")
                self.summary = make_browser()
                summary_box.body.addWidget(self.summary)
                right_layout.addWidget(summary_box, 1)
            if show_detail:
                detail_box = SectionBox("详情")
                self.detail = make_browser()
                detail_box.body.addWidget(self.detail)
                right_layout.addWidget(detail_box, 2 if show_summary else 1)
            splitter.addWidget(right)
            splitter.setSizes([split_sizes[0], split_sizes[1]])
            layout.addWidget(splitter, 1)
        else:
            layout.addWidget(left, 1)

        self.search.textChanged.connect(self._apply_filters)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_detail())
        self.table.doubleClicked.connect(lambda *_: self.open_current())

    def add_filter_combo(self, values: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(values)
        self.toolbar.insertWidget(self.toolbar.count() - 1, combo)
        combo.currentTextChanged.connect(self._apply_filters)
        return combo

    def add_filter_check(self, label: str) -> QCheckBox:
        box = QCheckBox(label)
        self.toolbar.insertWidget(self.toolbar.count() - 1, box)
        box.stateChanged.connect(self._apply_filters)
        return box

    def enable_open(self, label: str, handler) -> QPushButton:
        self.open_handler = handler
        button = style_button(QPushButton(label), "secondary")
        self.toolbar.insertWidget(self.toolbar.count() - 1, button)
        button.clicked.connect(self.open_current)
        return button

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

    def set_metrics(self, metrics: list[tuple[str, str, str, str]] | None = None) -> None:
        values = metrics or []
        for idx, card in enumerate(self.metric_cards):
            if idx < len(values):
                title, value, body, tone = values[idx]
                card.set_content(title, value, body, tone=tone)
                card.show()
            else:
                card.hide()

    def _matches_search(self, row: dict) -> bool:
        query = self.search.text().strip().lower()
        if not query:
            return True
        return query in str(row).lower()

    def _apply_filters(self) -> None:
        selected_key = ""
        current_row = self.current_row()
        if current_row is not None:
            selected_key = self.row_key_builder(current_row)
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
            row_key = self.row_key_builder(row)
            items: list[QStandardItem] = []
            for col_index, value in enumerate(self.cells_builder(row)):
                item = QStandardItem(str(value))
                item.setEditable(False)
                item.setData(row_key, Qt.UserRole)
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
        elif self.detail is not None:
            set_browser_text(self.detail, "暂无内容。")

    def _row_for_index(self, index) -> dict | None:
        if not index.isValid():
            return None
        key_index = index.siblingAtColumn(0)
        row_key = key_index.data(Qt.UserRole)
        if row_key is None:
            return None
        return next((row for row in self.filtered_rows if self.row_key_builder(row) == row_key), None)

    def _update_detail(self) -> None:
        index = self.table.currentIndex()
        if self.detail is None or not self.detail_builder:
            return
        row = self._row_for_index(index)
        if row is None:
            set_browser_text(self.detail, "暂无内容。")
            return
        set_browser_text(self.detail, self.detail_builder(row))

    def current_row(self) -> dict | None:
        index = self.table.currentIndex()
        return self._row_for_index(index)

    def open_current(self) -> None:
        if self.open_handler:
            row = self.current_row()
            if row is not None:
                self.open_handler(row)

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

def set_item_color(item: QStandardItem, color: str) -> None:
    item.setForeground(QColor(color))
