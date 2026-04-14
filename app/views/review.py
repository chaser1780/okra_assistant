from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from theme import SPACING, THEME
from views.common import build_filter_card, build_page_header
from widgets import ScrollableSections, SectionCard, WheelCombobox, build_scrolled_text


def build_review_view(app):
    wrap = tk.Frame(app.tab_review, bg=THEME["bg"])
    wrap.pack(fill="both", expand=True, padx=SPACING["page_x"], pady=SPACING["page_y"])

    build_page_header(
        wrap,
        "复盘记忆",
        "把结果分布、批次、lessons、bias adjustments 和夜间报告整合成可直接扫读的复盘工作台。",
        app.review_meta_var,
    )

    filter_card = build_filter_card(wrap, "复盘筛选", "支持按来源和周期聚焦，不必只从长报告里找结果。")
    row = tk.Frame(filter_card.body, bg=filter_card.body.cget("bg"))
    row.pack(fill="x")
    WheelCombobox(row, textvariable=app.review_source_filter_var, values=["全部来源", "advice", "execution"], state="readonly", width=12).pack(side="left")
    WheelCombobox(row, textvariable=app.review_horizon_filter_var, values=["全部周期", "0", "1", "5", "20"], state="readonly", width=12).pack(side="left", padx=(SPACING["gap_small"], 0))

    body = tk.PanedWindow(wrap, orient="horizontal", sashrelief="flat", sashwidth=8, bg=THEME["bg"], bd=0)
    body.pack(fill="both", expand=True)
    app.review_pane = body
    left = tk.Frame(body, bg=THEME["bg"])
    right = tk.Frame(body, bg=THEME["bg"])
    body.add(left, minsize=360)
    body.add(right, stretch="always", minsize=520)

    summary_card = SectionCard(left, "复盘统计与学习项", "左侧先看结果分布、历史趋势和最新 lessons / bias adjustments。", tone="surface")
    summary_card.pack(fill="both", expand=True)
    app.review_summary_sections = ScrollableSections(summary_card.body, tone="surface")
    app.review_summary_sections.pack(fill="both", expand=True)

    detail_card = SectionCard(right, "夜间复盘报告", "右侧保留完整报告或 fallback 详情，便于对照结构化摘要。", tone="surface")
    detail_card.pack(fill="both", expand=True)
    shell, app.review_detail_text = build_scrolled_text(detail_card.body, variant="body")
    shell.pack(fill="both", expand=True)
