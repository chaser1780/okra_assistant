from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from task_state import TASK_CARD_SPECS
from theme import SPACING, THEME, TYPOGRAPHY
from widgets import SectionCard, build_scrolled_text


def build_runtime_view(app):
    wrap = tk.Frame(app.tab_runtime, bg=THEME["bg"])
    wrap.pack(fill="both", expand=True, padx=SPACING["page_x"], pady=SPACING["page_y"])

    top = tk.Frame(wrap, bg=THEME["bg"])
    top.pack(fill="x")
    top.grid_columnconfigure(0, weight=4)
    top.grid_columnconfigure(1, weight=5)

    actions = SectionCard(top, "任务指挥台", "手动触发日内链路、实时刷新、夜间复盘，并查看通知与日志。", tone="rich")
    actions.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["gap"]))
    row = tk.Frame(actions.body, bg=actions.body.cget("bg"))
    row.pack(fill="x")
    app.btn_intra = ttk.Button(row, text="运行日内链路", command=lambda: app.run_pipeline("intraday"), style="Primary.TButton")
    app.btn_intra.pack(side="left")
    app.btn_rt = ttk.Button(row, text="刷新实时快照", command=app.run_realtime, style="Secondary.TButton")
    app.btn_rt.pack(side="left", padx=(SPACING["gap_small"], 0))
    app.btn_night = ttk.Button(row, text="运行夜间复盘", command=lambda: app.run_pipeline("nightly"), style="Ghost.TButton")
    app.btn_night.pack(side="left", padx=(SPACING["gap_small"], 0))
    ttk.Button(row, text="打开桌面日志", command=lambda: app.open_project_path(app.home / "logs" / "desktop"), style="Ghost.TButton").pack(side="left", padx=(SPACING["gap_small"], 0))
    tk.Label(actions.body, text="查看日期用于浏览历史结果；运行按钮默认操作今天。自动实时刷新在应用开启期间按计划触发。", bg=actions.body.cget("bg"), fg=THEME["ink_soft"], font=TYPOGRAPHY["small"], wraplength=520, justify="left").pack(anchor="w", pady=(12, 0))

    overview = SectionCard(top, "当前运行概况", "把任务状态、当前步骤、自动刷新状态和最近通知放到同一视野。", tone="surface")
    overview.grid(row=0, column=1, sticky="nsew")
    tk.Label(overview.body, textvariable=app.runtime_banner_var, bg=overview.body.cget("bg"), fg=THEME["accent_deep"], font=TYPOGRAPHY["body_strong"], wraplength=760, justify="left").pack(anchor="w")
    tk.Label(overview.body, textvariable=app.auto_realtime_var, bg=overview.body.cget("bg"), fg=THEME["ink_soft"], font=TYPOGRAPHY["small"], wraplength=760, justify="left").pack(anchor="w", pady=(8, 0))

    cards = tk.Frame(wrap, bg=THEME["bg"])
    cards.pack(fill="x", pady=(SPACING["gap"], SPACING["gap"]))
    for index, task_kind in enumerate(("intraday", "realtime", "nightly")):
        cards.grid_columnconfigure(index, weight=1)
        panel = SectionCard(cards, TASK_CARD_SPECS[task_kind]["title"], "最近结果、耗时、manifest 状态和关键步骤。", tone="surface")
        panel.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else SPACING["gap"], 0))
        shell, text = build_scrolled_text(panel.body, height=10, variant="soft")
        shell.pack(fill="both", expand=True)
        app.task_cards[task_kind] = text

    bottom = tk.PanedWindow(wrap, orient="horizontal", sashrelief="flat", sashwidth=8, bg=THEME["bg"], bd=0)
    bottom.pack(fill="both", expand=True)
    app.runtime_pane = bottom
    left = tk.Frame(bottom, bg=THEME["bg"])
    center = tk.Frame(bottom, bg=THEME["bg"])
    right = tk.Frame(bottom, bg=THEME["bg"])
    bottom.add(left, minsize=280)
    bottom.add(center, stretch="always", minsize=420)
    bottom.add(right, minsize=280)

    step_card = SectionCard(left, "当前步骤", "运行中的状态反馈先在这里看，再决定是否下钻日志。", tone="surface")
    step_card.pack(fill="both", expand=True)
    tk.Label(step_card.body, textvariable=app.run_hint_var, bg=step_card.body.cget("bg"), fg=THEME["ink"], font=TYPOGRAPHY["body_strong"], wraplength=360, justify="left").pack(anchor="w")
    tk.Label(step_card.body, textvariable=app.run_step_var, bg=step_card.body.cget("bg"), fg=THEME["ink_soft"], font=TYPOGRAPHY["body"], wraplength=360, justify="left").pack(anchor="w", pady=(10, 0))

    log_card = SectionCard(center, "运行日志", "保留原始输出，但放进稳定可读的日志容器里。", tone="soft")
    log_card.pack(fill="both", expand=True)
    shell, app.run_log_text = build_scrolled_text(log_card.body, variant="log")
    shell.pack(fill="both", expand=True)

    note_card = SectionCard(right, "通知中心", "最近完成、失败、保存结果和提醒都会出现在这里。", tone="panel")
    note_card.pack(fill="both", expand=True)
    shell, app.notification_text = build_scrolled_text(note_card.body, variant="soft")
    shell.pack(fill="both", expand=True)
