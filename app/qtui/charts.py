from __future__ import annotations

from datetime import datetime

from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QScatterSeries, QValueAxis
from PySide6.QtCore import QDateTime, QMargins, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QToolTip, QVBoxLayout, QWidget

from .history import SeriesPoint, TradeMarker
from .theme import QT


SERIES_COLORS = [
    QT["accent"],
    QT["success"],
    QT["warning"],
    QT["danger"],
    QT["info"],
]


def _to_msecs(text: str) -> int:
    dt = datetime.fromisoformat(text[:10])
    return int(dt.timestamp() * 1000)


def _lookup_value(points: list[SeriesPoint], target_date: str) -> float | None:
    if not points:
        return None
    target = datetime.fromisoformat(target_date[:10]).date()
    chosen: SeriesPoint | None = None
    for point in points:
        point_date = datetime.fromisoformat(point.date[:10]).date()
        if point_date <= target:
            chosen = point
        else:
            break
    if chosen is None:
        chosen = points[0]
    return chosen.value


def _marker_key(x_value: float, y_value: float) -> tuple[int, float]:
    return int(round(x_value)), round(y_value, 6)


def _marker_tooltip(markers: list[TradeMarker]) -> str:
    action_map = {
        "buy": "BUY",
        "switch_in": "BUY",
        "sell": "SELL",
        "switch_out": "SELL",
    }
    show_fund = len({marker.fund_code for marker in markers if marker.fund_code}) > 1
    lines: list[str] = []
    for marker in markers:
        action_text = action_map.get(marker.action, marker.action or "UNKNOWN")
        line = f"{marker.date} | {action_text} | Amount {marker.amount:,.2f}"
        if show_fund and marker.fund_code:
            line += f" | {marker.fund_code}"
        lines.append(line)
    return "\n".join(lines)


class TimeSeriesChart(QWidget):
    def __init__(self, title: str):
        super().__init__()
        self.chart = QChart()
        self.chart.setTitle(title)
        self.chart.setBackgroundVisible(False)
        self.chart.setPlotAreaBackgroundVisible(False)
        self.chart.setMargins(QMargins(8, 8, 8, 8))
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)
        self.chart.legend().setLabelColor(QColor(QT["text_soft"]))
        self.chart.setTitleBrush(QColor(QT["text"]))
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setMouseTracking(True)
        self.chart_view.setStyleSheet(
            f"QChartView {{ background:{QT['surface']}; border:1px solid {QT['line']}; border-radius:12px; }}"
        )
        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet(f"color:{QT['text_soft']}; font-size:9pt; padding:2px 4px;")
        self.empty_label = QLabel("")
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet(f"color:{QT['muted']}; font-size:9pt; padding:2px 4px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.chart_view)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.empty_label)

    def _toggle_marker_tooltip(
        self,
        series: QScatterSeries,
        marker_entries: dict[tuple[int, float], list[TradeMarker]],
        point,
        state: bool,
    ) -> None:
        if not state:
            QToolTip.hideText()
            return
        markers = marker_entries.get(_marker_key(point.x(), point.y()), [])
        if not markers:
            QToolTip.hideText()
            return
        chart_pos = self.chart.mapToPosition(point, series)
        global_pos = self.chart_view.mapToGlobal(chart_pos.toPoint())
        QToolTip.showText(global_pos, _marker_tooltip(markers), self.chart_view)

    def set_series(
        self,
        title: str,
        series_map: list[tuple[str, list[SeriesPoint]]],
        *,
        percent: bool = False,
        meta_text: str = "",
        empty_text: str = "暂无可用历史数据",
        trade_markers: list[TradeMarker] | None = None,
    ) -> None:
        QToolTip.hideText()
        self.chart.removeAllSeries()
        axes = self.chart.axes()
        for axis in axes:
            self.chart.removeAxis(axis)
        self.chart.setTitle(title)
        self.meta_label.setText(meta_text)
        self.empty_label.clear()

        x_axis = QDateTimeAxis()
        x_axis.setFormat("MM-dd")
        x_axis.setLabelsColor(QColor(QT["text_soft"]))
        x_axis.setGridLineColor(QColor(QT["line"]))
        self.chart.addAxis(x_axis, Qt.AlignBottom)

        y_axis = QValueAxis()
        y_axis.setLabelsColor(QColor(QT["text_soft"]))
        y_axis.setGridLineColor(QColor(QT["line"]))
        y_axis.setLabelFormat("%.2f%%" if percent else "%.2f")
        self.chart.addAxis(y_axis, Qt.AlignLeft)

        valid_values: list[float] = []
        valid_dates: list[int] = []
        primary_points: list[SeriesPoint] = []
        for idx, (name, points) in enumerate(series_map):
            if not points:
                continue
            if not primary_points:
                primary_points = points
            series = QLineSeries()
            series.setName(name)
            pen = QPen(QColor(SERIES_COLORS[idx % len(SERIES_COLORS)]))
            pen.setWidth(2)
            series.setPen(pen)
            for point in points:
                msecs = _to_msecs(point.date)
                series.append(msecs, point.value)
                valid_values.append(point.value)
                valid_dates.append(msecs)
            self.chart.addSeries(series)
            series.attachAxis(x_axis)
            series.attachAxis(y_axis)

        marker_counts = {"buy": 0, "sell": 0}
        if primary_points and trade_markers:
            marker_map = {
                "buy": (QT["success"], "买入"),
                "switch_in": (QT["success"], "买入"),
                "sell": (QT["danger"], "卖出"),
                "switch_out": (QT["danger"], "卖出"),
            }
            grouped: dict[str, QScatterSeries] = {}
            marker_entries: dict[str, dict[tuple[int, float], list[TradeMarker]]] = {}
            for marker in trade_markers:
                if marker.action not in marker_map:
                    continue
                y_value = _lookup_value(primary_points, marker.date)
                if y_value is None:
                    continue
                x_value = _to_msecs(marker.date)
                point_key = _marker_key(x_value, y_value)
                color, label = marker_map[marker.action]
                if label not in grouped:
                    scatter = QScatterSeries()
                    scatter.setName(label)
                    scatter.setColor(QColor(color))
                    scatter.setBorderColor(QColor(color))
                    scatter.setMarkerSize(10.0)
                    grouped[label] = scatter
                    marker_entries[label] = {}
                marker_entries[label].setdefault(point_key, []).append(marker)
                if label == "买入":
                    marker_counts["buy"] += 1
                else:
                    marker_counts["sell"] += 1
            for label, scatter in grouped.items():
                for (x_value, y_value), markers in marker_entries[label].items():
                    scatter.append(x_value, y_value)
                scatter.hovered.connect(
                    lambda point, state, current_series=scatter, entries=marker_entries[label]: self._toggle_marker_tooltip(
                        current_series, entries, point, state
                    )
                )
                self.chart.addSeries(scatter)
                scatter.attachAxis(x_axis)
                scatter.attachAxis(y_axis)

        if valid_values and valid_dates:
            span_days = max(1, int((max(valid_dates) - min(valid_dates)) / 86400000))
            x_axis.setFormat("yyyy-MM" if span_days > 400 else ("MM-dd" if span_days <= 120 else "yyyy-MM-dd"))
            y_min = min(valid_values)
            y_max = max(valid_values)
            if y_min == y_max:
                padding = max(abs(y_min) * 0.05, 1.0)
                y_min -= padding
                y_max += padding
            else:
                padding = (y_max - y_min) * 0.08
                y_min -= padding
                y_max += padding
            y_axis.setRange(y_min, y_max)
            x_axis.setRange(QDateTime.fromMSecsSinceEpoch(min(valid_dates)), QDateTime.fromMSecsSinceEpoch(max(valid_dates)))
            self.chart.legend().setVisible(True)
            if trade_markers and (marker_counts["buy"] or marker_counts["sell"]):
                marker_text = f" | 交易打点：买入 {marker_counts['buy']} / 卖出 {marker_counts['sell']}"
                self.meta_label.setText((meta_text or "") + marker_text)
        else:
            self.chart.legend().setVisible(False)
            self.empty_label.setText(empty_text)
