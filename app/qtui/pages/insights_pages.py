from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QSplitter, QVBoxLayout, QWidget

from portfolio_exposure import analyze_portfolio_exposure
from ui_support import build_review_detail_fallback, build_review_summary_text, build_settings_text, historical_operating_metrics, money, open_path, pct

from ..theme import QT
from ..widgets import MetricCard, SectionBox, bullet_lines, make_browser, set_browser_text


class ReviewPage(QWidget):
    def __init__(self):
        super().__init__()
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

        top_split = QSplitter()
        self.lessons_box = SectionBox("最新 Lessons")
        self.bias_box = SectionBox("Bias Adjustments")
        self.lessons_view = make_browser()
        self.bias_view = make_browser()
        self.lessons_box.body.addWidget(self.lessons_view)
        self.bias_box.body.addWidget(self.bias_view)
        top_split.addWidget(self.lessons_box)
        top_split.addWidget(self.bias_box)
        top_split.setSizes([520, 520])
        layout.addWidget(top_split)

        bottom_split = QSplitter()
        self.summary_box = SectionBox("复盘摘要")
        self.report_box = SectionBox("复盘报告")
        self.summary_view = make_browser()
        self.report_view = make_browser()
        self.summary_box.body.addWidget(self.summary_view)
        self.report_box.body.addWidget(self.report_view)
        bottom_split.addWidget(self.summary_box)
        bottom_split.addWidget(self.report_box)
        bottom_split.setSizes([520, 760])
        layout.addWidget(bottom_split, 1)

    def refresh_data(self, home: Path, state: dict) -> None:
        batches = state.get("review_results_for_date", []) or []
        memory = state.get("review_memory", {}) or {}
        summary_text = build_review_summary_text(state.get("selected_date", ""), batches, memory, historical_operating_metrics(home))
        detail_text = state.get("review_report") or build_review_detail_fallback(state.get("selected_date", ""), batches)
        total_supportive = sum(item.get("summary", {}).get("supportive", 0) for item in batches)
        total_adverse = sum(item.get("summary", {}).get("adverse", 0) for item in batches)
        total_missed = sum(item.get("summary", {}).get("missed_upside", 0) for item in batches)
        lessons = [item.get("text", "") for item in (memory.get("lessons", [])[-8:] or [])]
        bias = [f"[{item.get('scope', '')}] {item.get('target', '')}：{item.get('adjustment', '')}" for item in (memory.get("bias_adjustments", [])[-8:] or [])]
        self.meta.setText(f"查看日 {state.get('selected_date', '')} | 复盘批次 {len(batches)} | lessons {len(memory.get('lessons', []) or [])}")
        self.metric_cards[0].set_content("复盘批次", str(len(batches)), "当前查看日", tone="accent")
        self.metric_cards[1].set_content("supportive", str(total_supportive), "建议层验证", tone="success")
        self.metric_cards[2].set_content("adverse", str(total_adverse), "逆向结果", tone="danger")
        self.metric_cards[3].set_content("missed", str(total_missed), "错失上涨", tone="warning")
        set_browser_text(self.lessons_view, bullet_lines(lessons, "暂无 lessons"))
        set_browser_text(self.bias_view, bullet_lines(bias, "暂无 bias adjustments"))
        set_browser_text(self.summary_view, summary_text)
        set_browser_text(self.report_view, detail_text, markdown=True)


class SettingsPage(QWidget):
    def __init__(self, home: Path, shell=None):
        super().__init__()
        self.home = home
        self.shell = shell
        self.quick_paths = [
            ("打开 config", home / "config"),
            ("打开 db", home / "db"),
            ("打开 reports", home / "reports" / "daily"),
            ("打开 logs", home / "logs"),
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
            sync_button = QPushButton("同步历史数据")
            sync_button.clicked.connect(self.shell.run_history_sync)
            quick_row.addWidget(sync_button)
        quick_row.addStretch(1)
        layout.addLayout(quick_row)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(10)
        metric_grid.setVerticalSpacing(10)
        self.metric_cards = [MetricCard() for _ in range(4)]
        for idx, card in enumerate(self.metric_cards):
            metric_grid.addWidget(card, 0, idx)
        layout.addLayout(metric_grid)

        top_split = QSplitter()
        self.overview_box = SectionBox("系统概览")
        self.paths_box = SectionBox("路径与清单")
        self.overview_view = make_browser()
        self.paths_view = make_browser()
        self.overview_box.body.addWidget(self.overview_view)
        self.paths_box.body.addWidget(self.paths_view)
        top_split.addWidget(self.overview_box)
        top_split.addWidget(self.paths_box)
        top_split.setSizes([520, 520])
        layout.addWidget(top_split)

        bottom_box = SectionBox("完整系统详情")
        self.detail_view = make_browser()
        bottom_box.body.addWidget(self.detail_view)
        layout.addWidget(bottom_box, 1)

    def refresh_data(self, state: dict) -> None:
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
        self.meta.setText(f"查看日 {state.get('selected_date', '')} | 观察池 {len(state.get('watchlist', {}).get('funds', []) or [])} | 自检 {preflight.get('status', '暂无')}")
        self.metric_cards[0].set_content("观察池", str(len(state.get("watchlist", {}).get("funds", []) or [])), "基金样本", tone="info")
        self.metric_cards[1].set_content("模型", state.get("llm_config", {}).get("model", "暂无"), state.get("llm_config", {}).get("model_provider", ""), tone="accent")
        self.metric_cards[2].set_content("自检", preflight.get("status", "暂无"), "最近一次 preflight", tone="warning" if preflight.get("status") == "warning" else "success")
        self.metric_cards[3].set_content("总资产", money(state.get("portfolio", {}).get("total_value", 0)), state.get("portfolio", {}).get("portfolio_name", "暂无"), tone="accent")

        overview_lines = [
            f"模型：{state.get('llm_config', {}).get('model', '暂无')}",
            f"通道：{state.get('llm_config', {}).get('model_provider', '暂无')}",
            f"组合总资产：{money(state.get('portfolio', {}).get('total_value', 0))}",
            f"高波动主题：{pct((exposure.get('concentration_metrics', {}) or {}).get('high_volatility_theme_weight_pct', 0), 2)}",
            f"防守缓冲：{pct((exposure.get('concentration_metrics', {}) or {}).get('defensive_buffer_weight_pct', 0), 2)}",
        ]
        path_lines = [f"{label}：{path}" for label, path in self.quick_paths]
        for name, manifest in manifests.items():
            if manifest:
                path_lines.append(f"{name} manifest：{manifest.get('status', 'unknown')} | {manifest.get('current_step', '—')}")
        set_browser_text(self.overview_view, bullet_lines(overview_lines, "暂无"))
        set_browser_text(self.paths_view, bullet_lines(path_lines, "暂无"))
        set_browser_text(self.detail_view, detail_text)
