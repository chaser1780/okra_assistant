from __future__ import annotations

QT = {
    "bg": "#070A12",
    "bg_radial": "#111827",
    "bg_alt": "#0A0F1C",
    "panel": "#0D1320",
    "panel_glass": "#111A2A",
    "surface": "#121A29",
    "surface_alt": "#172233",
    "surface_soft": "#1B283A",
    "surface_hover": "#24344A",
    "surface_strong": "#26364A",
    "line": "#314158",
    "line_soft": "#202C3E",
    "text": "#F7FAFC",
    "text_soft": "#C4CDDA",
    "muted": "#8795A8",
    "accent": "#7DD3FC",
    "accent_deep": "#2563EB",
    "accent_soft": "#0F2A3F",
    "accent_glow": "#38BDF8",
    "success": "#34D399",
    "success_soft": "#0D2F26",
    "warning": "#FBBF24",
    "warning_soft": "#332508",
    "danger": "#FB7185",
    "danger_soft": "#3A121B",
    "info": "#A5B4FC",
    "info_soft": "#1B2550",
    "purple": "#C084FC",
    "purple_soft": "#2B1B45",
    "magenta": "#F472B6",
    "magenta_soft": "#36172D",
    "amber": "#F59E0B",
    "amber_soft": "#321F08",
    "rise": "#FF6374",
    "fall": "#18D19C",
    "flat": "#B7C4D7",
    "console_bg": "#03060A",
    "console_text": "#D8E1EC",
    "radius_sm": "8px",
    "radius_md": "10px",
    "radius_lg": "12px",
    "shadow": "rgba(0, 0, 0, 0.36)",
}

TONE = {
    "neutral": {"fg": QT["text_soft"], "bg": QT["surface_alt"], "border": QT["line"]},
    "accent": {"fg": QT["accent"], "bg": QT["accent_soft"], "border": QT["accent_glow"]},
    "success": {"fg": QT["success"], "bg": QT["success_soft"], "border": "#1F6B50"},
    "warning": {"fg": QT["warning"], "bg": QT["warning_soft"], "border": "#765328"},
    "danger": {"fg": QT["danger"], "bg": QT["danger_soft"], "border": "#7A3039"},
    "info": {"fg": QT["info"], "bg": QT["info_soft"], "border": "#2B568A"},
    "purple": {"fg": QT["purple"], "bg": QT["purple_soft"], "border": "#57428B"},
    "magenta": {"fg": QT["magenta"], "bg": QT["magenta_soft"], "border": "#7C315C"},
    "amber": {"fg": QT["amber"], "bg": QT["amber_soft"], "border": "#7A4B13"},
    "rise": {"fg": QT["rise"], "bg": QT["danger_soft"], "border": "#7A3039"},
    "fall": {"fg": QT["fall"], "bg": QT["success_soft"], "border": "#1F6B50"},
}

APP_TITLE = "okra assistant"

STYLE = f"""
QMainWindow, QWidget {{ background:{QT["bg"]}; color:{QT["text"]}; font-family:"Microsoft YaHei UI", "Segoe UI"; font-size:9.5pt; }}
QMainWindow {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #111827, stop:0.46 {QT["bg"]}, stop:1 #020617); }}
QFrame#TopBar {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(23, 34, 51, 238), stop:1 rgba(13, 19, 32, 246)); border:1px solid {QT["line_soft"]}; border-radius:{QT["radius_lg"]}; }}
QFrame#Sidebar {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {QT["panel_glass"]}, stop:1 #090E18); border:1px solid {QT["line_soft"]}; border-radius:{QT["radius_lg"]}; }}
QFrame#HeroCard, QFrame#MetricCard, QFrame#SurfaceCard, QFrame#TerminalCard {{ background:{QT["surface"]}; border:1px solid {QT["line_soft"]}; border-radius:{QT["radius_md"]}; }}
QFrame#ContentCanvas {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(18, 26, 41, 244), stop:0.54 rgba(10, 15, 28, 246), stop:1 rgba(7, 10, 18, 248)); border:1px solid {QT["line_soft"]}; border-radius:{QT["radius_lg"]}; }}
QGroupBox {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #141E2F, stop:1 #0D1422); border:1px solid {QT["line_soft"]}; border-radius:{QT["radius_md"]}; margin-top:10px; }}
QGroupBox::title {{ subcontrol-origin:margin; left:12px; padding:0 7px; color:{QT["text_soft"]}; font-weight:800; }}
QListWidget#NavList {{ background:transparent; border:none; outline:none; color:{QT["text_soft"]}; }}
QListWidget#NavList::item {{ border-radius:8px; padding:9px 11px; margin:0 0 5px 0; border:1px solid transparent; }}
QListWidget#NavList::item:selected {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {QT["accent_soft"]}, stop:1 #172554); color:{QT["text"]}; border:1px solid {QT["accent_glow"]}; }}
QListWidget#NavList::item:hover {{ background:{QT["surface_hover"]}; color:{QT["text"]}; }}
QPushButton {{ background:{QT["surface_alt"]}; color:{QT["text"]}; border:1px solid {QT["line"]}; border-radius:8px; padding:8px 11px; font-weight:800; }}
QPushButton:hover {{ background:{QT["surface_hover"]}; border-color:{QT["accent_glow"]}; }}
QPushButton:pressed {{ background:{QT["accent_soft"]}; }}
QPushButton:disabled {{ color:{QT["muted"]}; background:{QT["surface"]}; border-color:{QT["line_soft"]}; }}
QPushButton[variant="primary"] {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {QT["accent_deep"]}, stop:1 #0891B2); border:1px solid {QT["accent"]}; color:#F7FBFF; }}
QPushButton[variant="primary"]:hover {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #3B82F6, stop:1 {QT["accent_glow"]}); }}
QPushButton[variant="ghost"] {{ background:transparent; border:1px solid {QT["line_soft"]}; color:{QT["text_soft"]}; }}
QPushButton[variant="danger"] {{ background:{QT["danger_soft"]}; border:1px solid {QT["danger"]}; color:{QT["danger"]}; }}
QPushButton[variant="success"] {{ background:{QT["success_soft"]}; border:1px solid {QT["success"]}; color:{QT["success"]}; }}
QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QTableView {{ background:{QT["surface"]}; color:{QT["text"]}; border:1px solid {QT["line_soft"]}; border-radius:8px; padding:7px 9px; selection-background-color:{QT["accent_soft"]}; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextBrowser:focus, QTableView:focus {{ border:1px solid {QT["accent_glow"]}; }}
QTextBrowser {{ line-height:132%; font-size:9.2pt; background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #111A2A, stop:1 #0B1220); }}
QHeaderView::section {{ background:#172233; color:{QT["text_soft"]}; border:none; border-bottom:1px solid {QT["line"]}; padding:8px; font-weight:800; }}
QCheckBox {{ color:{QT["text_soft"]}; spacing:8px; }}
QCheckBox::indicator {{ width:13px; height:13px; border-radius:4px; border:1px solid {QT["line"]}; background:{QT["surface_alt"]}; }}
QCheckBox::indicator:checked {{ background:{QT["accent"]}; border:1px solid {QT["accent_deep"]}; }}
QTableView {{ alternate-background-color:{QT["surface_soft"]}; gridline-color:{QT["line_soft"]}; }}
QTableView::item {{ padding:5px; border:none; }}
QTableView::item:selected {{ background:{QT["accent_soft"]}; color:{QT["text"]}; }}
QStatusBar {{ background:{QT["panel"]}; color:{QT["text_soft"]}; border-top:1px solid {QT["line_soft"]}; }}
QToolTip {{ background:{QT["surface_alt"]}; color:{QT["text"]}; border:1px solid {QT["accent_glow"]}; border-radius:8px; padding:7px 9px; }}
QScrollBar:vertical {{ background:{QT["bg_alt"]}; width:9px; margin:2px; border-radius:5px; }}
QScrollBar::handle:vertical {{ background:{QT["line"]}; min-height:24px; border-radius:5px; }}
QScrollBar::handle:vertical:hover {{ background:{QT["muted"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}
QScrollBar:horizontal {{ background:{QT["bg_alt"]}; height:9px; margin:2px; border-radius:5px; }}
QScrollBar::handle:horizontal {{ background:{QT["line"]}; min-width:24px; border-radius:5px; }}
QScrollBar::handle:horizontal:hover {{ background:{QT["muted"]}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0px; }}
"""
