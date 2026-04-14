from __future__ import annotations

import tkinter as tk

from theme import SPACING, THEME
from widgets import ScrollableSections, SectionCard, build_metric_tile


def build_realtime_view(app):
    wrap = tk.Frame(app.tab_rt, bg=THEME["bg"])
    wrap.pack(fill="both", expand=True, padx=SPACING["page_x"], pady=(10, 10))

    metrics = tk.Frame(wrap, bg=THEME["bg"])
    metrics.pack(fill="x", pady=(0, SPACING["gap_small"]))
    for index in range(4):
        metrics.grid_columnconfigure(index, weight=1)
    app.rt_snapshot_card = build_metric_tile(metrics, app.rt_cards["snapshot_title"], app.rt_cards["snapshot_value"], app.rt_cards["snapshot_body"], tone="neutral", compact=True)
    app.rt_snapshot_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["gap"]))
    app.rt_pnl_card = build_metric_tile(metrics, app.rt_cards["pnl_title"], app.rt_cards["pnl_value"], app.rt_cards["pnl_body"], tone="accent", compact=True)
    app.rt_pnl_card.grid(row=0, column=1, sticky="nsew", padx=(0, SPACING["gap"]))
    app.rt_value_card = build_metric_tile(metrics, app.rt_cards["value_title"], app.rt_cards["value_value"], app.rt_cards["value_body"], tone="success", compact=True)
    app.rt_value_card.grid(row=0, column=2, sticky="nsew", padx=(0, SPACING["gap"]))
    app.rt_fresh_card = build_metric_tile(metrics, app.rt_cards["fresh_title"], app.rt_cards["fresh_value"], app.rt_cards["fresh_body"], tone="warning", compact=True)
    app.rt_fresh_card.grid(row=0, column=3, sticky="nsew")

    body = tk.PanedWindow(wrap, orient="horizontal", sashrelief="flat", sashwidth=8, bg=THEME["bg"], bd=0)
    body.pack(fill="both", expand=True)
    app.realtime_pane = body
    left = tk.Frame(body, bg=THEME["bg"])
    right = tk.Frame(body, bg=THEME["bg"])
    body.add(left, stretch="always", minsize=980)
    body.add(right, minsize=320)

    list_card = SectionCard(left, "基金实时收益", "按基金逐只展示实时收益和波动细节，点击卡片可在右侧展开完整说明。", tone="surface")
    list_card.pack(fill="both", expand=True)
    app.rt_list_sections = ScrollableSections(list_card.body, tone="surface")
    app.rt_list_sections.pack(fill="both", expand=True)

    summary_card = SectionCard(right, "组合级摘要", "先看组合层异常和高影响基金，再看右下角单基金详情。", tone="rich")
    summary_card.pack(fill="x", pady=(0, SPACING["gap"]))
    app.rt_summary_detail = ScrollableSections(summary_card.body, tone="panel")
    app.rt_summary_detail.pack(fill="both", expand=True)

    detail_card = SectionCard(right, "基金详情", "聚焦时间语义、模式来源、异常原因、可信度和盈亏。", tone="surface")
    detail_card.pack(fill="both", expand=True)
    app.rt_detail_sections = ScrollableSections(detail_card.body, tone="surface")
    app.rt_detail_sections.pack(fill="both", expand=True)
