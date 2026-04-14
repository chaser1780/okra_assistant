from __future__ import annotations

QT = {
    "bg": "#070B10",
    "panel": "#0D131A",
    "surface": "#10161D",
    "surface_alt": "#151E28",
    "surface_soft": "#141C24",
    "line": "#24303D",
    "text": "#EEF4FB",
    "text_soft": "#A8B4C5",
    "muted": "#738194",
    "accent": "#4F81D7",
    "accent_deep": "#3D69B4",
    "accent_soft": "#16283F",
    "success": "#2EC27E",
    "success_soft": "#10251E",
    "warning": "#E6A34A",
    "warning_soft": "#2A1E10",
    "danger": "#F05D6C",
    "danger_soft": "#2C1418",
    "info": "#6EA8FF",
    "info_soft": "#122236",
    "console_bg": "#05080D",
    "console_text": "#D8E1EC",
}

APP_TITLE = "okra 小助手"

NAV_ITEMS = [
    ("dash", "◈  总览"),
    ("portfolio", "▣  配置"),
    ("holdings", "◐  持仓走势"),
    ("research", "◆  研究"),
    ("trade", "◉  交易"),
    ("review", "◎  复盘"),
    ("rt", "◌  实时"),
    ("agents", "◍  智能体"),
    ("runtime", "▤  运行"),
    ("settings", "◫  设置"),
]

STYLE = f"""
QMainWindow, QWidget {{ background:{QT["bg"]}; color:{QT["text"]}; font-family:"Microsoft YaHei UI"; font-size:10pt; }}
QFrame#Sidebar {{ background:{QT["panel"]}; border:1px solid {QT["line"]}; border-radius:12px; }}
QGroupBox {{ background:{QT["surface"]}; border:1px solid {QT["line"]}; border-radius:12px; margin-top:10px; }}
QGroupBox::title {{ subcontrol-origin:margin; left:14px; padding:0 6px; color:{QT["text_soft"]}; }}
QListWidget#NavList {{ background:transparent; border:none; outline:none; color:{QT["text_soft"]}; }}
QListWidget#NavList::item {{ border-radius:10px; padding:11px 12px; margin:0 0 6px 0; }}
QListWidget#NavList::item:selected {{ background:{QT["surface_alt"]}; color:{QT["text"]}; border:1px solid {QT["line"]}; }}
QListWidget#NavList::item:hover {{ background:{QT["surface_soft"]}; color:{QT["text"]}; }}
QPushButton {{ background:{QT["surface_alt"]}; color:{QT["text"]}; border:1px solid {QT["line"]}; border-radius:10px; padding:10px 12px; font-weight:600; }}
QPushButton:hover {{ background:{QT["surface_soft"]}; }}
QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QTableView {{ background:{QT["surface"]}; color:{QT["text"]}; border:1px solid {QT["line"]}; border-radius:10px; padding:8px 10px; selection-background-color:{QT["accent_soft"]}; }}
QHeaderView::section {{ background:{QT["surface_alt"]}; color:{QT["text_soft"]}; border:none; border-bottom:1px solid {QT["line"]}; padding:8px; font-weight:600; }}
QCheckBox {{ color:{QT["text_soft"]}; spacing:8px; }}
QCheckBox::indicator {{ width:14px; height:14px; border-radius:4px; border:1px solid {QT["line"]}; background:{QT["surface_alt"]}; }}
QCheckBox::indicator:checked {{ background:{QT["accent"]}; border:1px solid {QT["accent_deep"]}; }}
QTableView {{ alternate-background-color:{QT["surface_soft"]}; }}
QStatusBar {{ background:{QT["panel"]}; color:{QT["text_soft"]}; }}
"""
