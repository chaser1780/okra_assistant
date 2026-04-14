from __future__ import annotations

import tkinter as tk

from theme import SPACING, THEME
from widgets import ScrollableSections, SectionCard


def build_dashboard_view(app):
    wrap = tk.Frame(app.tab_dash, bg=THEME["bg"])
    wrap.pack(fill="both", expand=True, padx=SPACING["page_x"], pady=SPACING["page_y"])
    decision_card = SectionCard(
        wrap,
        "今天先看什么",
        "把今天要做什么、市场怎么看、组合风险和与上一期相比的变化合并到一个可滚动面板里，减少来回扫视。",
        tone="surface",
    )
    decision_card.pack(fill="both", expand=True)
    app.dashboard_detail = ScrollableSections(decision_card.body, tone="surface")
    app.dashboard_detail.pack(fill="both", expand=True)
