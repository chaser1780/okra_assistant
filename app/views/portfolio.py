from __future__ import annotations

import tkinter as tk

from theme import SPACING, THEME
from views.common import build_page_header
from widgets import ScrollableSections, SectionCard


def build_portfolio_view(app):
    wrap = tk.Frame(app.tab_portfolio, bg=THEME["bg"])
    wrap.pack(fill="both", expand=True, padx=SPACING["page_x"], pady=SPACING["page_y"])

    build_page_header(wrap, "组合配置", "先看目标配置、当前偏离和再平衡建议，再决定今天的动作是在修结构还是只做短线调整。", app.portfolio_meta_var)
    report_card = SectionCard(
        wrap,
        "组合配置与执行报告",
        "把目标配置、偏离、再平衡建议、今日动作和组合原则合并成一份连续可滚动报告，减少碎片卡片。",
        tone="surface",
    )
    report_card.pack(fill="both", expand=True)
    app.portfolio_report_sections = ScrollableSections(report_card.body, tone="surface")
    app.portfolio_report_sections.pack(fill="both", expand=True)
