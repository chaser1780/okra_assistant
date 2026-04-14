from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from theme import SPACING, THEME, TYPOGRAPHY
from views.common import build_page_header
from widgets import ScrollableSections, SectionCard, WheelCombobox


def build_trade_view(app):
    wrap = tk.Frame(app.tab_trade, bg=THEME["bg"])
    wrap.pack(fill="both", expand=True, padx=SPACING["page_x"], pady=SPACING["page_y"])

    build_page_header(wrap, "交易执行", "左侧完成录入，右侧先看交易前检查台和交易后结果，再决定是否提交。", app.trade_meta_var)

    body = tk.PanedWindow(wrap, orient="horizontal", sashrelief="flat", sashwidth=8, bg=THEME["bg"], bd=0)
    body.pack(fill="both", expand=True)
    app.trade_pane = body
    left = tk.Frame(body, bg=THEME["bg"])
    right = tk.Frame(body, bg=THEME["bg"])
    body.add(left, minsize=480)
    body.add(right, stretch="always", minsize=420)

    form_card = SectionCard(left, "交易录入", "先绑定建议，再补动作、金额和成交细节。", tone="surface")
    form_card.pack(fill="both", expand=True)
    form_body = form_card.body
    form_body.grid_columnconfigure(0, weight=1)
    form_body.grid_columnconfigure(1, weight=1)

    tk.Label(form_body, text="绑定建议", bg=form_body.cget("bg"), fg=THEME["ink_soft"], font=TYPOGRAPHY["small_strong"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
    app.trade_suggestion = WheelCombobox(form_body, textvariable=app.trade_suggestion_var, state="readonly")
    app.trade_suggestion.grid(row=1, column=0, columnspan=2, sticky="ew")

    fields = [
        ("交易日期", ttk.Entry(form_body, textvariable=app.trade_date_var)),
        ("基金", WheelCombobox(form_body, textvariable=app.trade_fund_var, state="readonly")),
        ("动作", WheelCombobox(form_body, textvariable=app.trade_action_var, state="readonly", values=["buy", "sell", "switch_in", "switch_out"])),
        ("金额", ttk.Entry(form_body, textvariable=app.trade_amount_var)),
        ("成交净值", ttk.Entry(form_body, textvariable=app.trade_nav_var)),
        ("成交份额", ttk.Entry(form_body, textvariable=app.trade_units_var)),
    ]
    for idx, (label, widget) in enumerate(fields):
        row = 2 + (idx // 2) * 2
        col = idx % 2
        tk.Label(form_body, text=label, bg=form_body.cget("bg"), fg=THEME["ink_soft"], font=TYPOGRAPHY["small_strong"]).grid(row=row, column=col, sticky="w", padx=(0 if col == 0 else SPACING["gap_small"], 0), pady=(10, 4))
        widget.grid(row=row + 1, column=col, sticky="ew", padx=(0 if col == 0 else SPACING["gap_small"], 0))
    app.trade_fund = fields[1][1]

    tk.Label(form_body, text="备注", bg=form_body.cget("bg"), fg=THEME["ink_soft"], font=TYPOGRAPHY["small_strong"]).grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 4))
    app.trade_note = tk.Text(form_body, height=7, wrap="word", bg=THEME["surface_soft"], fg=THEME["ink"], insertbackground=THEME["ink"], relief="flat", borderwidth=0, padx=12, pady=12, highlightthickness=1, highlightbackground=THEME["line"], highlightcolor=THEME["accent"], font=TYPOGRAPHY["body"])
    app.trade_note.grid(row=9, column=0, columnspan=2, sticky="ew")

    btn_row = tk.Frame(form_body, bg=form_body.cget("bg"))
    btn_row.grid(row=10, column=0, columnspan=2, sticky="w", pady=(12, 0))
    app.btn_trade = ttk.Button(btn_row, text="记录交易并回写持仓", command=app.submit_trade, style="Primary.TButton")
    app.btn_trade.pack(side="left")
    ttk.Button(btn_row, text="打开交易流水", command=lambda: app.open_project_path(app.home / "db" / "trade_journal"), style="Secondary.TButton").pack(side="left", padx=(SPACING["gap_small"], 0))

    top_right = SectionCard(right, "交易前检查台", "红黄绿检查会在输入变化时即时刷新。", tone="soft")
    top_right.pack(fill="both", expand=True, pady=(0, SPACING["gap"]))
    app.trade_precheck_sections = ScrollableSections(top_right.body, tone="soft")
    app.trade_precheck_sections.pack(fill="both", expand=True)

    bottom_right = SectionCard(right, "交易结果与流水", "提交后在这里核对回写结果和当日流水。", tone="surface")
    bottom_right.pack(fill="both", expand=True)
    app.trade_output_sections = ScrollableSections(bottom_right.body, tone="surface")
    app.trade_output_sections.pack(fill="both", expand=True)
