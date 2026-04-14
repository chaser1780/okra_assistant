from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from theme import SPACING, THEME, TYPOGRAPHY
from widgets import FilterBar, SectionCard


def build_page_header(parent, title: str, subtitle: str, meta_var):
    card = SectionCard(parent, title, "", tone="rich", padding=SPACING["card_pad_small"])
    card.pack(fill="x", pady=(0, SPACING["gap_small"]))
    tk.Label(card.body, textvariable=meta_var, bg=card.body.cget("bg"), fg=THEME["ink_soft"], font=TYPOGRAPHY["small"], wraplength=1160, justify="left").pack(anchor="w")
    return card


def build_filter_card(parent, title: str = "筛选与定位", subtitle: str = "搜索、筛选和排序会即时生效。"):
    card = FilterBar(parent, title=title, subtitle="")
    card.pack(fill="x", pady=(0, SPACING["gap_small"]))
    return card


def configure_tree_columns(tree: ttk.Treeview, columns):
    for key, title, width, anchor in columns:
        tree.heading(key, text=title)
        tree.column(key, width=width, anchor=anchor, stretch=True)
