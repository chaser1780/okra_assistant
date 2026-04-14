from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from theme import SPACING, THEME, TYPOGRAPHY
from views.common import build_filter_card, build_page_header, configure_tree_columns
from widgets import ScrollableSections, SectionCard, WheelCombobox, build_tree_shell


def build_settings_view(app):
    wrap = tk.Frame(app.tab_settings, bg=THEME["bg"])
    wrap.pack(fill="both", expand=True, padx=SPACING["page_x"], pady=SPACING["page_y"])

    build_page_header(wrap, "设置与数据", "把策略控制、观察池维护、系统健康和关键路径放在同一页里。", app.settings_meta_var)

    quick = SectionCard(wrap, "快捷入口", "常用目录和系统检查要放在第一屏，避免埋在长表单里。", tone="surface")
    quick.pack(fill="x", pady=(0, SPACING["gap"]))
    row = tk.Frame(quick.body, bg=quick.body.cget("bg"))
    row.pack(fill="x")
    for label, path in [("打开 config", app.home / "config"), ("打开 db", app.home / "db"), ("打开 reports", app.home / "reports" / "daily"), ("打开 logs", app.home / "logs")]:
        ttk.Button(row, text=label, command=lambda p=path: app.open_project_path(p), style="Ghost.TButton").pack(side="left", padx=(0, SPACING["gap_small"]))
    app.btn_preflight = ttk.Button(row, text="运行健康检查", command=app.run_preflight, style="Primary.TButton")
    app.btn_preflight.pack(side="left")

    body = tk.PanedWindow(wrap, orient="horizontal", sashrelief="flat", sashwidth=8, bg=THEME["bg"], bd=0)
    body.pack(fill="both", expand=True)
    app.settings_pane = body
    left = tk.Frame(body, bg=THEME["bg"])
    right = tk.Frame(body, bg=THEME["bg"])
    body.add(left, stretch="always", minsize=560)
    body.add(right, minsize=420)

    editor = tk.Frame(left, bg=THEME["bg"])
    editor.pack(fill="x", pady=(0, SPACING["gap"]))
    editor.grid_columnconfigure(0, weight=1)
    editor.grid_columnconfigure(1, weight=1)

    strategy = SectionCard(editor, "策略控制", "高频会调整的参数放在一张卡片里。", tone="surface")
    strategy.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["gap"]))
    strategy.body.grid_columnconfigure(0, weight=1)
    entries = [
        ("风险偏好", WheelCombobox(strategy.body, textvariable=app.settings_risk_profile_var, values=["balanced", "conservative", "aggressive"], state="readonly")),
        ("现金底仓", ttk.Entry(strategy.body, textvariable=app.settings_cash_floor_var)),
        ("总交易额度", ttk.Entry(strategy.body, textvariable=app.settings_gross_limit_var)),
        ("净买入额度", ttk.Entry(strategy.body, textvariable=app.settings_net_limit_var)),
        ("每只定投额", ttk.Entry(strategy.body, textvariable=app.settings_dca_amount_var)),
        ("日内报告模式", WheelCombobox(strategy.body, textvariable=app.settings_report_mode_var, values=["intraday_proxy", "portfolio_report", "daily_report"], state="readonly")),
        ("长期核心目标%", ttk.Entry(strategy.body, textvariable=app.settings_core_target_var)),
        ("中期卫星目标%", ttk.Entry(strategy.body, textvariable=app.settings_satellite_target_var)),
        ("短期战术目标%", ttk.Entry(strategy.body, textvariable=app.settings_tactical_target_var)),
        ("防守/现金目标%", ttk.Entry(strategy.body, textvariable=app.settings_defense_target_var)),
        ("再平衡带宽%", ttk.Entry(strategy.body, textvariable=app.settings_rebalance_band_var)),
    ]
    for idx, (label, widget) in enumerate(entries):
        tk.Label(strategy.body, text=label, bg=strategy.body.cget("bg"), fg=THEME["ink_soft"], font=TYPOGRAPHY["small_strong"]).grid(row=idx * 2, column=0, sticky="w", pady=(0 if idx == 0 else 8, 4))
        widget.grid(row=idx * 2 + 1, column=0, sticky="ew")
    ttk.Button(strategy.body, text="保存策略控制", command=app.save_strategy_controls, style="Primary.TButton").grid(row=len(entries) * 2, column=0, sticky="w", pady=(12, 0))

    cap = SectionCard(editor, "单只上限", "把 tactical cap 调整集中在独立区域，减少误操作。", tone="surface")
    cap.grid(row=0, column=1, sticky="nsew")
    cap.body.grid_columnconfigure(0, weight=1)
    tk.Label(cap.body, text="基金", bg=cap.body.cget("bg"), fg=THEME["ink_soft"], font=TYPOGRAPHY["small_strong"]).grid(row=0, column=0, sticky="w", pady=(0, 4))
    app.settings_cap_fund = WheelCombobox(cap.body, textvariable=app.settings_cap_fund_var, state="readonly")
    app.settings_cap_fund.grid(row=1, column=0, sticky="ew")
    tk.Label(cap.body, text="上限金额", bg=cap.body.cget("bg"), fg=THEME["ink_soft"], font=TYPOGRAPHY["small_strong"]).grid(row=2, column=0, sticky="w", pady=(10, 4))
    ttk.Entry(cap.body, textvariable=app.settings_cap_value_var).grid(row=3, column=0, sticky="ew")
    ttk.Button(cap.body, text="保存单只上限", command=app.save_fund_cap, style="Primary.TButton").grid(row=4, column=0, sticky="w", pady=(12, 0))

    watch = SectionCard(left, "观察池", "左侧筛选和浏览，右侧编辑，保留研究节奏。", tone="surface")
    watch.pack(fill="both", expand=True)
    watch_filter = build_filter_card(watch.body, "观察池筛选", "按代码、名称、类别和风险等级快速定位。")
    row = tk.Frame(watch_filter.body, bg=watch_filter.body.cget("bg"))
    row.pack(fill="x")
    tk.Entry(row, textvariable=app.watchlist_search_var, relief="flat", bg=THEME["surface"], fg=THEME["ink"], font=("Microsoft YaHei UI", 10)).pack(side="left", fill="x", expand=True)
    WheelCombobox(row, textvariable=app.watchlist_category_filter_var, values=["全部类别", "active_equity", "index_equity", "etf_linked", "qdii_index", "bond", "cash_management"], state="readonly", width=14).pack(side="left", padx=(SPACING["gap_small"], 0))
    WheelCombobox(row, textvariable=app.watchlist_risk_filter_var, values=["全部风险", "low", "medium", "high"], state="readonly", width=12).pack(side="left", padx=(SPACING["gap_small"], 0))

    watch_body = tk.Frame(watch.body, bg=watch.body.cget("bg"))
    watch_body.pack(fill="both", expand=True)
    watch_body.grid_columnconfigure(0, weight=3)
    watch_body.grid_columnconfigure(1, weight=4)
    watch_body.grid_rowconfigure(0, weight=1)

    left_list = SectionCard(watch_body, "观察池列表", "先选中，再在右侧编辑。", tone="soft")
    left_list.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["gap"]))
    app.watchlist_tree = ttk.Treeview(left_list.body, columns=("code", "name", "category", "risk"), show="headings", style="Panel.Treeview")
    configure_tree_columns(
        app.watchlist_tree,
        [
            ("code", "代码", 90, "w"),
            ("name", "名称", 160, "w"),
            ("category", "类别", 110, "center"),
            ("risk", "风险", 80, "center"),
        ],
    )
    build_tree_shell(left_list.body, app.watchlist_tree).pack(fill="both", expand=True)

    editor_card = SectionCard(watch_body, "观察池编辑", "直接编辑当前选中项，也可以新增。", tone="surface")
    editor_card.grid(row=0, column=1, sticky="nsew")
    editor_card.body.grid_columnconfigure(0, weight=1)
    editor_card.body.grid_columnconfigure(1, weight=1)
    fields = [("代码", app.watchlist_code_var), ("名称", app.watchlist_name_var), ("类别", app.watchlist_category_var), ("基准", app.watchlist_benchmark_var), ("风险等级", app.watchlist_risk_var)]
    for idx, (label, var) in enumerate(fields):
        column = idx % 2
        row_num = (idx // 2) * 2
        tk.Label(editor_card.body, text=label, bg=editor_card.body.cget("bg"), fg=THEME["ink_soft"], font=TYPOGRAPHY["small_strong"]).grid(row=row_num, column=column, sticky="w", padx=(0 if column == 0 else SPACING["gap_small"], 0), pady=(0 if row_num == 0 else 8, 4))
        if label in {"类别", "风险等级"}:
            values = ["active_equity", "index_equity", "etf_linked", "qdii_index", "bond", "cash_management"] if label == "类别" else ["low", "medium", "high"]
            widget = WheelCombobox(editor_card.body, textvariable=var, values=values, state="readonly")
        else:
            widget = ttk.Entry(editor_card.body, textvariable=var)
        widget.grid(row=row_num + 1, column=column, sticky="ew", padx=(0 if column == 0 else SPACING["gap_small"], 0))
    btn_row = tk.Frame(editor_card.body, bg=editor_card.body.cget("bg"))
    btn_row.grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 0))
    ttk.Button(btn_row, text="新增/更新观察池", command=app.save_watchlist_item, style="Primary.TButton").pack(side="left")
    ttk.Button(btn_row, text="删除选中观察池", command=app.remove_watchlist_item, style="Secondary.TButton").pack(side="left", padx=(SPACING["gap_small"], 0))

    system = SectionCard(right, "系统健康与路径", "把 manifest、自检、路径和底层设置整理成结构化视图。", tone="soft")
    system.pack(fill="both", expand=True)
    app.settings_system_sections = ScrollableSections(system.body, tone="soft")
    app.settings_system_sections.pack(fill="both", expand=True)
