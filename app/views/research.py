from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from theme import SPACING, THEME
from views.common import build_filter_card, build_page_header, configure_tree_columns
from widgets import ScrollableSections, SectionCard, WheelCombobox, build_tree_shell


def build_research_view(app):
    wrap = tk.Frame(app.tab_research, bg=THEME["bg"])
    wrap.pack(fill="both", expand=True, padx=SPACING["page_x"], pady=SPACING["page_y"])

    build_page_header(wrap, "建议与动作", "先定位今天真正可执行的动作，再看可信度、依据、风险和规则校验。", app.research_meta_var)
    filter_card = build_filter_card(wrap, "建议筛选", "按动作、执行状态、基金代码或名称快速定位。")
    row = tk.Frame(filter_card.body, bg=filter_card.body.cget("bg"))
    row.pack(fill="x")
    tk.Entry(row, textvariable=app.research_search_var, relief="flat", bg=THEME["surface"], fg=THEME["ink"], font=("Microsoft YaHei UI", 10)).pack(side="left", fill="x", expand=True)
    WheelCombobox(row, textvariable=app.research_action_filter_var, values=["全部动作", "buy", "sell", "hold", "switch_out"], state="readonly", width=12).pack(side="left", padx=(SPACING["gap_small"], 0))
    WheelCombobox(row, textvariable=app.research_status_filter_var, values=["全部状态", "pending", "partial", "executed"], state="readonly", width=12).pack(side="left", padx=(SPACING["gap_small"], 0))

    body = tk.PanedWindow(wrap, orient="horizontal", sashrelief="flat", sashwidth=8, bg=THEME["bg"], bd=0)
    body.pack(fill="both", expand=True)
    app.research_pane = body
    left = tk.Frame(body, bg=THEME["bg"])
    right = tk.Frame(body, bg=THEME["bg"])
    body.add(left, minsize=360)
    body.add(right, stretch="always", minsize=520)

    list_card = SectionCard(left, "建议列表", "把动作、金额和执行状态放进表格，减少盲选。", tone="surface")
    list_card.pack(fill="both", expand=True)
    app.fund_tree = ttk.Treeview(list_card.body, columns=("code", "name", "action", "amount", "consensus", "status"), show="headings", style="Panel.Treeview")
    configure_tree_columns(
        app.fund_tree,
        [
            ("code", "代码", 90, "w"),
            ("name", "基金", 170, "w"),
            ("action", "动作", 90, "center"),
            ("amount", "金额", 100, "e"),
            ("consensus", "共识", 90, "center"),
            ("status", "执行", 90, "center"),
        ],
    )
    build_tree_shell(list_card.body, app.fund_tree).pack(fill="both", expand=True)

    detail_card = SectionCard(right, "建议详情", "首屏先看可信度横幅和核心判断，再下钻依据、风险和规则校验。", tone="surface")
    detail_card.pack(fill="both", expand=True)
    app.fund_detail_sections = ScrollableSections(detail_card.body, tone="surface")
    app.fund_detail_sections.pack(fill="both", expand=True)


def build_agents_view(app):
    wrap = tk.Frame(app.tab_agents, bg=THEME["bg"])
    wrap.pack(fill="both", expand=True, padx=SPACING["page_x"], pady=SPACING["page_y"])

    build_page_header(wrap, "智能体视角", "用筛选和结构化详情快速看出谁支持、谁犹豫、谁缺信息。", app.agents_meta_var)
    filter_card = build_filter_card(wrap, "智能体筛选", "支持按状态、名称和置信度快速定位。")
    row = tk.Frame(filter_card.body, bg=filter_card.body.cget("bg"))
    row.pack(fill="x")
    tk.Entry(row, textvariable=app.agent_search_var, relief="flat", bg=THEME["surface"], fg=THEME["ink"], font=("Microsoft YaHei UI", 10)).pack(side="left", fill="x", expand=True)
    WheelCombobox(row, textvariable=app.agent_status_filter_var, values=["全部状态", "success", "failed", "degraded", "unknown"], state="readonly", width=12).pack(side="left", padx=(SPACING["gap_small"], 0))

    body = tk.PanedWindow(wrap, orient="horizontal", sashrelief="flat", sashwidth=8, bg=THEME["bg"], bd=0)
    body.pack(fill="both", expand=True)
    app.agents_pane = body
    left = tk.Frame(body, bg=THEME["bg"])
    right = tk.Frame(body, bg=THEME["bg"])
    body.add(left, minsize=320)
    body.add(right, stretch="always", minsize=520)

    list_card = SectionCard(left, "智能体列表", "把状态和置信度放进列表，先筛选再下钻。", tone="surface")
    list_card.pack(fill="both", expand=True)
    app.agent_tree = ttk.Treeview(list_card.body, columns=("stage", "name", "status", "confidence"), show="headings", style="Panel.Treeview")
    configure_tree_columns(
        app.agent_tree,
        [
            ("stage", "阶段", 110, "center"),
            ("name", "智能体", 180, "w"),
            ("status", "状态", 90, "center"),
            ("confidence", "置信度", 90, "e"),
        ],
    )
    build_tree_shell(list_card.body, app.agent_tree).pack(fill="both", expand=True)

    detail_card = SectionCard(right, "智能体详情", "首屏看摘要、关键信号和缺失信息，再决定是否继续下钻。", tone="surface")
    detail_card.pack(fill="both", expand=True)
    app.agent_detail_sections = ScrollableSections(detail_card.body, tone="surface")
    app.agent_detail_sections.pack(fill="both", expand=True)
