from __future__ import annotations

import tkinter as tk
from tkinter import ttk


THEME = {
    "bg": "#070B10",
    "bg_alt": "#0C1117",
    "surface": "#10161D",
    "surface_soft": "#141C24",
    "surface_alt": "#1A2430",
    "panel": "#0D131A",
    "panel_rich": "#121A23",
    "hero": "#0A0F15",
    "hero_alt": "#17212C",
    "ink": "#EEF4FB",
    "ink_soft": "#A8B4C5",
    "muted": "#738194",
    "line": "#24303D",
    "line_strong": "#314253",
    "accent": "#4F81D7",
    "accent_deep": "#3D69B4",
    "accent_soft": "#16283F",
    "accent_glow": "#0F1825",
    "success": "#2EC27E",
    "success_soft": "#10251E",
    "warning": "#E6A34A",
    "warning_soft": "#2A1E10",
    "danger": "#F05D6C",
    "danger_soft": "#2C1418",
    "info": "#6EA8FF",
    "info_soft": "#122236",
    "console_bg": "#05080D",
    "console_fg": "#D8E1EC",
    "tab_idle": "#0F151C",
    "tab_active": "#151E28",
    "selection": "#345B94",
    "selection_soft": "#162942",
    "overlay": "#0A1017",
}

TYPOGRAPHY = {
    "display": ("Bahnschrift", 22, "bold"),
    "title": ("Microsoft YaHei UI", 13, "bold"),
    "subtitle": ("Georgia", 10, "italic"),
    "section": ("Microsoft YaHei UI", 10, "bold"),
    "body": ("Microsoft YaHei UI", 10),
    "body_strong": ("Microsoft YaHei UI", 10, "bold"),
    "small": ("Microsoft YaHei UI", 9),
    "small_strong": ("Microsoft YaHei UI", 9, "bold"),
    "metric": ("Bahnschrift", 18, "bold"),
    "metric_small": ("Bahnschrift", 13, "bold"),
    "mono": ("Consolas", 10),
}

SPACING = {
    "page_x": 14,
    "page_y": 10,
    "card_pad": 14,
    "card_pad_small": 10,
    "gap": 8,
    "gap_small": 6,
    "gap_tight": 4,
    "badge_x": 10,
    "badge_y": 4,
}


def panel_palette(tone: str = "surface") -> dict[str, str]:
    palettes = {
        "surface": {"bg": THEME["surface"], "line": THEME["line"], "title": THEME["ink"], "subtitle": THEME["muted"]},
        "soft": {"bg": THEME["surface_soft"], "line": THEME["line"], "title": THEME["ink"], "subtitle": THEME["muted"]},
        "rich": {"bg": THEME["panel_rich"], "line": THEME["line"], "title": THEME["ink"], "subtitle": THEME["ink_soft"]},
        "panel": {"bg": THEME["panel"], "line": THEME["line"], "title": THEME["ink"], "subtitle": THEME["ink_soft"]},
        "accent": {"bg": THEME["accent_glow"], "line": THEME["accent_soft"], "title": THEME["accent_deep"], "subtitle": THEME["accent_deep"]},
        "success": {"bg": THEME["success_soft"], "line": "#1D4C3A", "title": THEME["success"], "subtitle": THEME["success"]},
        "warning": {"bg": THEME["warning_soft"], "line": "#5C4020", "title": THEME["warning"], "subtitle": THEME["warning"]},
        "danger": {"bg": THEME["danger_soft"], "line": "#5C2630", "title": THEME["danger"], "subtitle": THEME["danger"]},
        "info": {"bg": THEME["info_soft"], "line": "#23405F", "title": THEME["info"], "subtitle": THEME["info"]},
        "hero": {"bg": THEME["hero"], "line": THEME["hero_alt"], "title": THEME["surface"], "subtitle": THEME["accent_soft"]},
    }
    return palettes.get(tone, palettes["surface"])


def badge_palette(tone: str = "neutral") -> tuple[str, str]:
    palettes = {
        "neutral": (THEME["surface_soft"], THEME["ink_soft"]),
        "accent": (THEME["accent_soft"], THEME["accent_deep"]),
        "success": (THEME["success_soft"], THEME["success"]),
        "warning": (THEME["warning_soft"], THEME["warning"]),
        "danger": (THEME["danger_soft"], THEME["danger"]),
        "info": (THEME["info_soft"], THEME["info"]),
        "hero": (THEME["hero_alt"], THEME["surface"]),
        "muted": (THEME["surface_alt"], THEME["muted"]),
    }
    return palettes.get(tone, palettes["neutral"])


def configure_theme(root: tk.Misc) -> ttk.Style:
    root.configure(bg=THEME["bg"])
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    style.configure(".", background=THEME["bg"], foreground=THEME["ink"], fieldbackground=THEME["surface"])
    style.map(".", foreground=[("disabled", THEME["muted"])])

    style.configure("TButton", padding=(14, 8), background=THEME["surface_alt"], foreground=THEME["ink_soft"], borderwidth=0, focusthickness=0)
    style.map("TButton", background=[("active", THEME["accent_soft"]), ("disabled", THEME["surface_alt"])], foreground=[("active", THEME["ink"]), ("disabled", THEME["muted"])])
    style.configure("Primary.TButton", padding=(16, 10), background=THEME["accent"], foreground=THEME["surface"], borderwidth=0, font=TYPOGRAPHY["body_strong"])
    style.map("Primary.TButton", background=[("active", THEME["accent_deep"]), ("disabled", THEME["surface_alt"])], foreground=[("active", THEME["surface"]), ("disabled", THEME["muted"])])
    style.configure("Secondary.TButton", padding=(14, 9), background=THEME["surface_alt"], foreground=THEME["ink"], borderwidth=0, font=TYPOGRAPHY["body_strong"])
    style.map("Secondary.TButton", background=[("active", THEME["hero_alt"]), ("disabled", THEME["surface_alt"])], foreground=[("active", THEME["surface"]), ("disabled", THEME["muted"])])
    style.configure("Ghost.TButton", padding=(12, 8), background=THEME["surface"], foreground=THEME["ink_soft"], bordercolor=THEME["line"])
    style.map("Ghost.TButton", background=[("active", THEME["selection_soft"])], foreground=[("active", THEME["ink"])])

    style.configure("TEntry", fieldbackground=THEME["surface"], foreground=THEME["ink"], insertcolor=THEME["ink"], padding=(10, 8), relief="flat")
    style.configure("TCombobox", fieldbackground=THEME["surface"], foreground=THEME["ink"], padding=(10, 8), relief="flat")
    style.map("TCombobox", fieldbackground=[("readonly", THEME["surface"]), ("disabled", THEME["surface_alt"])], selectbackground=[("readonly", THEME["selection_soft"])], foreground=[("disabled", THEME["muted"])])

    style.configure("Workspace.TNotebook", background=THEME["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("Workspace.TNotebook.Tab", background=THEME["tab_idle"], foreground=THEME["muted"], padding=(18, 11), font=TYPOGRAPHY["body_strong"], borderwidth=0)
    style.map("Workspace.TNotebook.Tab", background=[("selected", THEME["tab_active"]), ("active", THEME["surface_alt"])], foreground=[("selected", THEME["ink"]), ("active", THEME["ink_soft"])])
    style.configure("Content.TNotebook", background=THEME["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.layout("Content.TNotebook.Tab", [])

    style.configure("SideNav.TButton", padding=(14, 12), background=THEME["panel"], foreground=THEME["ink_soft"], borderwidth=0, anchor="w", font=TYPOGRAPHY["body_strong"])
    style.map("SideNav.TButton", background=[("active", THEME["surface_soft"])], foreground=[("active", THEME["ink"])])
    style.configure("SideNavActive.TButton", padding=(14, 12), background=THEME["surface_alt"], foreground=THEME["ink"], borderwidth=0, anchor="w", font=TYPOGRAPHY["body_strong"])
    style.map("SideNavActive.TButton", background=[("active", THEME["surface_alt"])], foreground=[("active", THEME["ink"])])

    style.configure("Panel.Treeview", background=THEME["surface"], fieldbackground=THEME["surface"], foreground=THEME["ink"], rowheight=32, bordercolor=THEME["line"], borderwidth=0, relief="flat")
    style.map("Panel.Treeview", background=[("selected", THEME["selection_soft"])], foreground=[("selected", THEME["ink"])])
    style.configure("Panel.Treeview.Heading", background=THEME["surface_alt"], foreground=THEME["ink_soft"], font=TYPOGRAPHY["small_strong"], relief="flat", padding=(10, 8))
    style.map("Panel.Treeview.Heading", background=[("active", THEME["surface_soft"])], foreground=[("active", THEME["ink"])])

    style.configure("App.Vertical.TScrollbar", troughcolor=THEME["bg_alt"], background=THEME["surface_alt"], bordercolor=THEME["bg_alt"], arrowcolor=THEME["ink_soft"], darkcolor=THEME["surface_alt"], lightcolor=THEME["surface_alt"], gripcount=0)
    style.configure("App.Horizontal.TScrollbar", troughcolor=THEME["bg_alt"], background=THEME["surface_alt"], bordercolor=THEME["bg_alt"], arrowcolor=THEME["ink_soft"], darkcolor=THEME["surface_alt"], lightcolor=THEME["surface_alt"], gripcount=0)
    return style
