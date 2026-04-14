from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk

from theme import SPACING, THEME, TYPOGRAPHY, badge_palette, panel_palette


def text_token(variant: str) -> dict[str, object]:
    variants = {
        "body": {"bg": THEME["surface"], "fg": THEME["ink"], "font": TYPOGRAPHY["body"], "select": THEME["selection_soft"]},
        "soft": {"bg": THEME["surface_soft"], "fg": THEME["ink"], "font": TYPOGRAPHY["body"], "select": THEME["selection_soft"]},
        "panel": {"bg": THEME["panel"], "fg": THEME["ink"], "font": TYPOGRAPHY["body"], "select": THEME["selection_soft"]},
        "log": {"bg": THEME["console_bg"], "fg": THEME["console_fg"], "font": TYPOGRAPHY["mono"], "select": "#223041"},
    }
    return variants.get(variant, variants["body"])


def build_scrolled_text(parent, *, height=None, variant: str = "body"):
    token = text_token(variant)
    shell = tk.Frame(parent, bg=token["bg"], bd=0)
    shell.grid_rowconfigure(0, weight=1)
    shell.grid_columnconfigure(0, weight=1)
    text = tk.Text(
        shell,
        wrap="word",
        relief="flat",
        borderwidth=0,
        padx=10,
        pady=10,
        bg=token["bg"],
        fg=token["fg"],
        insertbackground=token["fg"],
        selectbackground=token["select"],
        selectforeground=token["fg"],
        font=token["font"],
        highlightthickness=0,
        bd=0,
        spacing1=3,
        spacing3=7,
    )
    if height:
        text.configure(height=height)
    text.configure(state="disabled")
    text.grid(row=0, column=0, sticky="nsew")
    ybar = ttk.Scrollbar(shell, orient="vertical", command=text.yview, style="App.Vertical.TScrollbar")
    ybar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
    text.configure(yscrollcommand=ybar.set)
    bind_scrollable(shell, lambda step: text.yview_scroll(step, "units"))
    bind_scrollable(text, lambda step: text.yview_scroll(step, "units"))
    return shell, text


def build_scrolled_listbox(parent, *, bg: str | None = None):
    shell = tk.Frame(parent, bg=bg or THEME["surface"], bd=0)
    shell.grid_rowconfigure(0, weight=1)
    shell.grid_columnconfigure(0, weight=1)
    lst = tk.Listbox(
        shell,
        relief="flat",
        borderwidth=0,
        activestyle="none",
        bg=bg or THEME["surface"],
        fg=THEME["ink"],
        selectbackground=THEME["selection_soft"],
        selectforeground=THEME["ink"],
        highlightthickness=0,
        bd=0,
        font=TYPOGRAPHY["body"],
        selectborderwidth=0,
    )
    lst.grid(row=0, column=0, sticky="nsew")
    ybar = ttk.Scrollbar(shell, orient="vertical", command=lst.yview, style="App.Vertical.TScrollbar")
    ybar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
    lst.configure(yscrollcommand=ybar.set)
    bind_scrollable(shell, lambda step: lst.yview_scroll(step, "units"))
    bind_scrollable(lst, lambda step: lst.yview_scroll(step, "units"))
    return shell, lst


def build_tree_shell(parent, tree: ttk.Treeview, *, bg: str | None = None):
    shell = tk.Frame(parent, bg=bg or THEME["surface"], bd=0)
    shell.grid_rowconfigure(0, weight=1)
    shell.grid_columnconfigure(0, weight=1)
    tree.grid(in_=shell, row=0, column=0, sticky="nsew")
    ybar = ttk.Scrollbar(shell, orient="vertical", command=tree.yview, style="App.Vertical.TScrollbar")
    ybar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
    xbar = ttk.Scrollbar(shell, orient="horizontal", command=tree.xview, style="App.Horizontal.TScrollbar")
    xbar.grid(row=1, column=0, sticky="ew", pady=(4, 0))
    tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
    bind_scrollable(shell, lambda step: tree.yview_scroll(step, "units"))
    bind_scrollable(tree, lambda step: tree.yview_scroll(step, "units"))
    return shell


def _wheel_steps(delta) -> int:
    try:
        value = int(delta)
    except Exception:
        return 0
    if value == 0:
        return 0
    return -1 if value > 0 else 1


def _scrollable_registry(root: tk.Misc) -> dict[str, object]:
    registry = getattr(root, "_scrollable_mousewheel_registry", None)
    if registry is None:
        registry = {}
        setattr(root, "_scrollable_mousewheel_registry", registry)
    return registry


def _register_scrollable(root: tk.Misc, widget: tk.Misc, callback) -> None:
    _scrollable_registry(root)[str(widget)] = callback


def _resolve_scrollable(root: tk.Misc, widget) -> object | None:
    registry = _scrollable_registry(root)
    current = widget
    while current is not None:
        path = str(current)
        if path in registry:
            return registry[path]
        try:
            parent_path = current.winfo_parent()
        except Exception:
            break
        if not parent_path:
            break
        try:
            current = root.nametowidget(parent_path)
        except Exception:
            break
    return None


def _handle_scrollable_wheel(root: tk.Misc, event, fallback_step: int | None = None):
    try:
        widget = root.winfo_containing(event.x_root, event.y_root)
    except Exception:
        widget = getattr(event, "widget", None)
    callback = _resolve_scrollable(root, widget or getattr(event, "widget", None))
    if callback is None:
        return None
    step = fallback_step if fallback_step is not None else _wheel_steps(getattr(event, "delta", 0))
    if step == 0:
        return None
    callback(step)
    return "break"


def install_scrollable_mousewheel(root: tk.Misc) -> None:
    if getattr(root, "_scrollable_mousewheel_installed", False):
        return
    root.bind_all("<MouseWheel>", lambda event: _handle_scrollable_wheel(root, event), add="+")
    root.bind_all("<Button-4>", lambda event: _handle_scrollable_wheel(root, event, -1), add="+")
    root.bind_all("<Button-5>", lambda event: _handle_scrollable_wheel(root, event, 1), add="+")
    setattr(root, "_scrollable_mousewheel_installed", True)


def bind_scrollable(widget: tk.Misc, callback) -> None:
    root = widget.winfo_toplevel()
    install_scrollable_mousewheel(root)
    _register_scrollable(root, widget, callback)


def _combo_registry(root: tk.Misc) -> dict[str, ttk.Combobox]:
    registry = getattr(root, "_combobox_mousewheel_registry", None)
    if registry is None:
        registry = {}
        setattr(root, "_combobox_mousewheel_registry", registry)
    return registry


def _set_active_combobox(root: tk.Misc, combo: ttk.Combobox | None):
    setattr(root, "_active_combobox_widget", combo)


def _active_combobox(root: tk.Misc) -> ttk.Combobox | None:
    combo = getattr(root, "_active_combobox_widget", None)
    if combo is not None and combo.winfo_exists():
        return combo
    return None


def _update_active_combobox_from_pointer(root: tk.Misc, event=None):
    widget = None
    try:
        if event is not None and hasattr(event, "x_root") and hasattr(event, "y_root"):
            widget = root.winfo_containing(event.x_root, event.y_root)
    except Exception:
        widget = None
    combo = _resolve_registered_combobox(root, widget)
    if combo is not None:
        _set_active_combobox(root, combo)
    elif widget is None:
        _set_active_combobox(root, None)


def _set_active_wheel_combobox(root: tk.Misc, combo):
    setattr(root, "_active_wheel_combobox_widget", combo)


def _active_wheel_combobox(root: tk.Misc):
    combo = getattr(root, "_active_wheel_combobox_widget", None)
    if combo is not None and combo.winfo_exists():
        return combo
    return None


def _widget_in_subtree(root: tk.Misc, widget, ancestor) -> bool:
    current = widget
    while current is not None:
        if current == ancestor:
            return True
        try:
            parent_path = current.winfo_parent()
        except Exception:
            break
        if not parent_path:
            break
        try:
            current = root.nametowidget(parent_path)
        except Exception:
            break
    return False


def _handle_active_wheel_combobox(root: tk.Misc, event, fallback_step: int | None = None):
    combo = _active_wheel_combobox(root)
    if combo is None:
        return None
    try:
        widget = root.winfo_containing(event.x_root, event.y_root)
    except Exception:
        widget = getattr(event, "widget", None)
    popup_listbox = getattr(combo, "listbox", None)
    if widget is not None and not _widget_in_subtree(root, widget, combo):
        if popup_listbox is None or not _widget_in_subtree(root, widget, popup_listbox):
            return None
    step = fallback_step if fallback_step is not None else _wheel_steps(getattr(event, "delta", 0))
    if step == 0:
        return None
    return combo._scroll(step)


def install_wheelcombobox_mousewheel(root: tk.Misc):
    if getattr(root, "_wheelcombobox_mousewheel_installed", False):
        return
    root.bind_all("<MouseWheel>", lambda event: _handle_active_wheel_combobox(root, event), add="+")
    root.bind_all("<Button-4>", lambda event: _handle_active_wheel_combobox(root, event, -1), add="+")
    root.bind_all("<Button-5>", lambda event: _handle_active_wheel_combobox(root, event, 1), add="+")
    setattr(root, "_wheelcombobox_mousewheel_installed", True)


def _register_combobox(root: tk.Misc, combo: ttk.Combobox):
    registry = _combo_registry(root)
    registry[str(combo)] = combo
    try:
        popdown = combo.tk.call("ttk::combobox::PopdownWindow", str(combo))
        registry[f"{popdown}.f.l"] = combo
    except Exception:
        pass


def _resolve_registered_combobox(root: tk.Misc, widget) -> ttk.Combobox | None:
    registry = _combo_registry(root)
    if widget is None:
        return None
    path = str(widget)
    if path in registry and registry[path].winfo_exists():
        return registry[path]
    current = widget
    while current is not None:
        path = str(current)
        if path in registry and registry[path].winfo_exists():
            return registry[path]
        try:
            parent_path = current.winfo_parent()
        except Exception:
            break
        if not parent_path:
            break
        try:
            current = root.nametowidget(parent_path)
        except Exception:
            break
    return None


def _scroll_combobox(combo: ttk.Combobox, step: int):
    values = list(combo.cget("values") or [])
    if not values:
        return "break"
    index = combo.current()
    if index is None or index < 0:
        current = combo.get()
        try:
            index = values.index(current)
        except ValueError:
            index = 0
    new_index = max(0, min(len(values) - 1, index + step))
    if new_index != index:
        combo.current(new_index)
        combo.event_generate("<<ComboboxSelected>>")
    return "break"


def _handle_combobox_wheel(root: tk.Misc, event, fallback_step: int | None = None):
    widget = None
    try:
        widget = root.winfo_containing(event.x_root, event.y_root)
    except Exception:
        widget = getattr(event, "widget", None)
    combo = _resolve_registered_combobox(root, widget or getattr(event, "widget", None))
    if combo is None:
        combo = _active_combobox(root)
    if combo is None:
        return None
    step = fallback_step if fallback_step is not None else _wheel_steps(getattr(event, "delta", 0))
    if step == 0:
        return None
    return _scroll_combobox(combo, step)


def install_combobox_mousewheel(root: tk.Misc):
    if getattr(root, "_combobox_mousewheel_installed", False):
        return
    root.bind_all("<Motion>", lambda event: _update_active_combobox_from_pointer(root, event), add="+")
    root.bind_class("TCombobox", "<MouseWheel>", lambda event: _handle_combobox_wheel(root, event), add="+")
    root.bind_class("TCombobox", "<Button-4>", lambda event: _handle_combobox_wheel(root, event, -1), add="+")
    root.bind_class("TCombobox", "<Button-5>", lambda event: _handle_combobox_wheel(root, event, 1), add="+")
    root.bind_all("<MouseWheel>", lambda event: _handle_combobox_wheel(root, event), add="+")
    root.bind_all("<Button-4>", lambda event: _handle_combobox_wheel(root, event, -1), add="+")
    root.bind_all("<Button-5>", lambda event: _handle_combobox_wheel(root, event, 1), add="+")
    setattr(root, "_combobox_mousewheel_installed", True)


def bind_comboboxes_recursive(parent, *, root: tk.Misc | None = None):
    actual_root = root or parent.winfo_toplevel()
    install_combobox_mousewheel(actual_root)
    for child in parent.winfo_children():
        if isinstance(child, ttk.Combobox):
            _register_combobox(actual_root, child)
            child.bind("<Enter>", lambda _event, combo=child: (_set_active_combobox(actual_root, combo), combo.focus_set()), add="+")
            child.bind("<FocusIn>", lambda _event, combo=child: _set_active_combobox(actual_root, combo), add="+")
            child.bind("<Leave>", lambda _event, combo=child: _set_active_combobox(actual_root, None) if _active_combobox(actual_root) == combo else None, add="+")
            child.bind("<MouseWheel>", lambda event, combo=child: _scroll_combobox(combo, _wheel_steps(getattr(event, "delta", 0))), add="+")
            child.bind("<Button-4>", lambda _event, combo=child: _scroll_combobox(combo, -1), add="+")
            child.bind("<Button-5>", lambda _event, combo=child: _scroll_combobox(combo, 1), add="+")
        bind_comboboxes_recursive(child, root=actual_root)


class WheelCombobox(tk.Frame):
    def __init__(self, parent, *, textvariable=None, values=None, state: str = "readonly", width: int = 12, **kwargs):
        super().__init__(parent, bg=THEME["surface"], bd=0, highlightbackground=THEME["line"], highlightcolor=THEME["line"], highlightthickness=1)
        self._app_root = parent.winfo_toplevel()
        install_wheelcombobox_mousewheel(self._app_root)
        self.var = textvariable or tk.StringVar()
        self.values = list(values or [])
        self.state_value = state
        self.width = width
        self.popup = None
        self.listbox = None

        self.grid_columnconfigure(0, weight=1)
        self.entry = tk.Entry(
            self,
            textvariable=self.var,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            readonlybackground=THEME["surface"],
            disabledbackground=THEME["surface_alt"],
            bg=THEME["surface"],
            fg=THEME["ink"],
            insertbackground=THEME["ink"],
            font=TYPOGRAPHY["body"],
            width=width,
            state="readonly" if state == "readonly" else "normal",
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(10, 4), pady=6)
        self.arrow = tk.Label(self, text="▼", bg=THEME["surface"], fg=THEME["ink_soft"], font=TYPOGRAPHY["small"])
        self.arrow.grid(row=0, column=1, sticky="e", padx=(0, 8))

        for widget in (self, self.entry, self.arrow):
            widget.bind("<Button-1>", self._on_click, add="+")
            widget.bind("<Enter>", lambda _event: _set_active_wheel_combobox(self._app_root, self), add="+")
            widget.bind("<Motion>", lambda _event: _set_active_wheel_combobox(self._app_root, self), add="+")
            widget.bind("<FocusIn>", lambda _event: _set_active_wheel_combobox(self._app_root, self), add="+")
            widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
            widget.bind("<Button-4>", lambda _event: self._scroll(-1), add="+")
            widget.bind("<Button-5>", lambda _event: self._scroll(1), add="+")

    def _on_click(self, _event=None):
        if self.state_value == "disabled":
            return "break"
        self.focus_set()
        self.toggle_popup()
        return "break"

    def _on_mousewheel(self, event):
        step = _wheel_steps(getattr(event, "delta", 0))
        if step == 0:
            return None
        return self._scroll(step)

    def _scroll(self, step: int):
        if self.state_value == "disabled":
            return "break"
        if not self.values:
            return "break"
        index = self.current()
        if index < 0:
            index = 0
        new_index = max(0, min(len(self.values) - 1, index + step))
        if new_index != index:
            self.current(new_index)
            self.event_generate("<<ComboboxSelected>>")
        return "break"

    def _build_popup(self):
        if self.popup and self.popup.winfo_exists():
            return
        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.configure(bg=THEME["surface"])
        shell = tk.Frame(popup, bg=THEME["surface"], bd=0, highlightbackground=THEME["line"], highlightcolor=THEME["line"], highlightthickness=1)
        shell.pack(fill="both", expand=True)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        listbox = tk.Listbox(
            shell,
            relief="flat",
            borderwidth=0,
            activestyle="none",
            bg=THEME["surface"],
            fg=THEME["ink"],
            selectbackground=THEME["selection_soft"],
            selectforeground=THEME["ink"],
            highlightthickness=0,
            bd=0,
            font=TYPOGRAPHY["body"],
            selectborderwidth=0,
        )
        listbox.grid(row=0, column=0, sticky="nsew")
        ybar = ttk.Scrollbar(shell, orient="vertical", command=listbox.yview, style="App.Vertical.TScrollbar")
        ybar.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=ybar.set)
        listbox.bind("<ButtonRelease-1>", self._on_listbox_select, add="+")
        listbox.bind("<Return>", self._on_listbox_select, add="+")
        listbox.bind("<Escape>", lambda _e: self.close_popup(), add="+")
        listbox.bind("<Enter>", lambda _event: _set_active_wheel_combobox(self._app_root, self), add="+")
        listbox.bind("<Motion>", lambda _event: _set_active_wheel_combobox(self._app_root, self), add="+")
        listbox.bind("<MouseWheel>", self._on_listbox_wheel, add="+")
        listbox.bind("<Button-4>", lambda _event: listbox.yview_scroll(-1, "units"), add="+")
        listbox.bind("<Button-5>", lambda _event: listbox.yview_scroll(1, "units"), add="+")
        self.popup = popup
        self.listbox = listbox
        popup.bind("<FocusOut>", lambda _e: self.close_popup(), add="+")

    def _on_listbox_wheel(self, event):
        step = _wheel_steps(getattr(event, "delta", 0))
        if step == 0:
            return None
        self.listbox.yview_scroll(step, "units")
        return "break"

    def toggle_popup(self):
        if self.popup and self.popup.winfo_exists() and self.popup.state() == "normal":
            self.close_popup()
        else:
            self.open_popup()

    def open_popup(self):
        if self.state_value == "disabled":
            return
        self._build_popup()
        if not self.popup or not self.listbox:
            return
        self.listbox.delete(0, "end")
        for item in self.values:
            self.listbox.insert("end", item)
        index = self.current()
        if index >= 0:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(index)
            self.listbox.see(index)

        self.update_idletasks()
        width = max(self.winfo_width(), 180)
        height = min(max(1, len(self.values)), 10) * 28 + 4
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        self.popup.geometry(f"{width}x{height}+{x}+{y}")
        self.popup.deiconify()
        self.popup.lift()
        self.listbox.focus_set()

    def close_popup(self):
        if self.popup and self.popup.winfo_exists():
            self.popup.withdraw()

    def _on_listbox_select(self, _event=None):
        if not self.listbox:
            return "break"
        selection = self.listbox.curselection()
        if not selection:
            return "break"
        self.current(selection[0])
        self.event_generate("<<ComboboxSelected>>")
        self.close_popup()
        return "break"

    def current(self, index: int | None = None):
        if index is None:
            current = self.var.get()
            try:
                return self.values.index(current)
            except ValueError:
                return -1
        if not self.values:
            return -1
        index = max(0, min(len(self.values) - 1, int(index)))
        self.var.set(self.values[index])
        return index

    def get(self):
        return self.var.get()

    def set(self, value: str):
        self.var.set(value)

    def cget(self, key):
        if key == "values":
            return tuple(self.values)
        if key == "state":
            return self.state_value
        return super().cget(key)

    def configure(self, cnf=None, **kwargs):
        opts = {}
        if cnf:
            opts.update(cnf)
        opts.update(kwargs)
        if "values" in opts:
            self.values = list(opts.pop("values") or [])
        if "state" in opts:
            self.state_value = opts.pop("state")
            self.entry.configure(state="readonly" if self.state_value == "readonly" else "normal")
        if "textvariable" in opts:
            self.var = opts.pop("textvariable")
            self.entry.configure(textvariable=self.var)
        if "width" in opts:
            self.width = int(opts.pop("width"))
            self.entry.configure(width=self.width)
        return super().configure(opts)

    config = configure

    def __setitem__(self, key, value):
        self.configure(**{key: value})

    def __getitem__(self, key):
        return self.cget(key)


class SectionCard(tk.Frame):
    def __init__(self, parent, title: str = "", subtitle: str = "", *, tone: str = "surface", padding: int | None = None):
        token = panel_palette(tone)
        pad = padding if padding is not None else SPACING["card_pad"]
        super().__init__(parent, bg=token["bg"], bd=0, highlightbackground=token["line"], highlightcolor=token["line"], highlightthickness=1)
        self.token = token
        self.padding = pad
        self.header = tk.Frame(self, bg=token["bg"])
        self.header.pack(fill="x", padx=pad, pady=(pad, 0))
        self.title_label = tk.Label(self.header, text=title, bg=token["bg"], fg=token["title"], font=TYPOGRAPHY["section"])
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(self.header, text=subtitle, bg=token["bg"], fg=token["subtitle"], font=TYPOGRAPHY["small"], wraplength=960, justify="left")
        if subtitle:
            self.subtitle_label.pack(anchor="w", pady=(4, 0))
        self.body = tk.Frame(self, bg=token["bg"])
        self.body.pack(fill="both", expand=True, padx=pad, pady=(8, pad))

    def set_title(self, text: str):
        self.title_label.configure(text=text)

    def set_subtitle(self, text: str):
        self.subtitle_label.configure(text=text)
        if text and not self.subtitle_label.winfo_manager():
            self.subtitle_label.pack(anchor="w", pady=(4, 0))
        if not text and self.subtitle_label.winfo_manager():
            self.subtitle_label.pack_forget()


def make_badge(parent, *, text: str | None = None, text_var=None, tone: str = "neutral", command=None):
    bg_color, fg_color = badge_palette(tone)
    kwargs = {
        "bg": bg_color,
        "fg": fg_color,
        "font": TYPOGRAPHY["small_strong"],
        "padx": SPACING["badge_x"],
        "pady": SPACING["badge_y"],
        "bd": 0,
        "highlightthickness": 0,
    }
    if command is not None:
        widget = tk.Button(parent, text=text or "", command=command, activebackground=bg_color, activeforeground=fg_color, relief="flat", **kwargs)
    elif text_var is not None:
        widget = tk.Label(parent, textvariable=text_var, **kwargs)
    else:
        widget = tk.Label(parent, text=text or "", **kwargs)
    return widget


def build_metric_tile(parent, title_var, value_var, body_var, *, tone: str = "accent", compact: bool = False):
    palette = {
        "accent": (THEME["accent_glow"], THEME["accent_soft"], THEME["info"], THEME["ink"], THEME["ink_soft"]),
        "success": (THEME["success_soft"], "#1D4C3A", THEME["success"], THEME["ink"], THEME["ink_soft"]),
        "warning": (THEME["warning_soft"], "#5C4020", THEME["warning"], THEME["ink"], THEME["ink_soft"]),
        "danger": (THEME["danger_soft"], "#5C2630", THEME["danger"], THEME["ink"], THEME["ink_soft"]),
        "neutral": (THEME["surface_soft"], THEME["line"], THEME["ink_soft"], THEME["ink"], THEME["muted"]),
        "info": (THEME["info_soft"], "#23405F", THEME["info"], THEME["ink"], THEME["ink_soft"]),
    }
    bg_color, line_color, title_color, value_color, body_color = palette.get(tone, palette["accent"])
    pad_x = SPACING["card_pad_small"] if compact else SPACING["card_pad"]
    pad_y = 10 if compact else 14
    title_font = TYPOGRAPHY["small_strong"] if compact else TYPOGRAPHY["body_strong"]
    value_font = TYPOGRAPHY["metric_small"] if compact else TYPOGRAPHY["metric"]
    body_font = TYPOGRAPHY["small"] if compact else TYPOGRAPHY["body"]
    wrap_width = 240 if compact else 320
    card = tk.Frame(parent, bg=bg_color, bd=0, highlightbackground=line_color, highlightcolor=line_color, highlightthickness=1, padx=pad_x, pady=pad_y)
    tk.Label(card, textvariable=title_var, bg=bg_color, fg=title_color, font=title_font).pack(anchor="w")
    tk.Label(card, textvariable=value_var, bg=bg_color, fg=value_color, font=value_font, wraplength=wrap_width, justify="left").pack(anchor="w", pady=(6, 4))
    tk.Label(card, textvariable=body_var, bg=bg_color, fg=body_color, font=body_font, wraplength=wrap_width, justify="left").pack(anchor="w")
    return card


def build_story_tile(parent, title_var, body_var, *, tone: str = "neutral", height: int = 4):
    palette = {
        "accent": (THEME["accent_glow"], THEME["accent_soft"], THEME["info"], THEME["ink"]),
        "success": (THEME["success_soft"], "#1D4C3A", THEME["success"], THEME["ink"]),
        "danger": (THEME["danger_soft"], "#5C2630", THEME["danger"], THEME["ink"]),
        "neutral": (THEME["surface"], THEME["line"], THEME["ink"], THEME["ink_soft"]),
        "info": (THEME["info_soft"], "#23405F", THEME["info"], THEME["ink"]),
    }
    bg_color, line_color, title_color, body_color = palette.get(tone, palette["neutral"])
    card = tk.Frame(parent, bg=bg_color, bd=0, highlightbackground=line_color, highlightcolor=line_color, highlightthickness=1, padx=12, pady=10)
    tk.Label(card, textvariable=title_var, bg=bg_color, fg=title_color, font=TYPOGRAPHY["small_strong"]).pack(anchor="w")
    shell, text = build_scrolled_text(card, height=height, variant="soft" if tone == "neutral" else "body")
    shell.configure(bg=bg_color)
    text.configure(bg=bg_color, fg=body_color, font=TYPOGRAPHY["small"], padx=0, pady=0)
    shell.pack(fill="both", expand=True, pady=(8, 0))
    return card, text


def render_key_values(parent, pairs: list[tuple[str, str]], *, columns: int = 2, bg: str | None = None):
    frame = tk.Frame(parent, bg=bg or parent.cget("bg"))
    for col in range(columns * 2):
        frame.grid_columnconfigure(col, weight=1 if col % 2 else 0)
    for idx, (label, value) in enumerate(pairs):
        row = idx // columns
        col = (idx % columns) * 2
        tk.Label(frame, text=label, bg=frame.cget("bg"), fg=THEME["muted"], font=TYPOGRAPHY["small_strong"]).grid(row=row * 2, column=col, sticky="w", padx=(0, 8), pady=(0 if row == 0 else 6, 2))
        tk.Label(frame, text=value, bg=frame.cget("bg"), fg=THEME["ink"], font=TYPOGRAPHY["body"], wraplength=260, justify="left").grid(row=row * 2 + 1, column=col, columnspan=2, sticky="w", padx=(0, 16))
    return frame


class FilterBar(SectionCard):
    def __init__(self, parent, title: str = "筛选与定位", subtitle: str = "搜索、筛选与排序会即时生效。"):
        super().__init__(parent, title, subtitle, tone="panel", padding=SPACING["card_pad_small"])


class ScrollableSections(tk.Frame):
    def __init__(self, parent, *, tone: str = "surface"):
        token = panel_palette(tone)
        super().__init__(parent, bg=token["bg"], bd=0)
        self.token = token
        self.canvas = tk.Canvas(self, bg=token["bg"], highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="App.Vertical.TScrollbar")
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.inner = tk.Frame(self.canvas, bg=token["bg"])
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._sync_scrollregion)
        self.canvas.bind("<Configure>", self._sync_width)
        bind_scrollable(self, lambda step: self.canvas.yview_scroll(step, "units"))
        bind_scrollable(self.canvas, lambda step: self.canvas.yview_scroll(step, "units"))
        bind_scrollable(self.inner, lambda step: self.canvas.yview_scroll(step, "units"))

    def _sync_scrollregion(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)

    def render(self, schema: dict | None):
        self.clear()
        if not schema:
            create_empty_state(self.inner, "暂无详情", "请先在左侧选择一项，右侧会展示结构化详情。").pack(fill="x")
            return
        if schema.get("title"):
            tk.Label(self.inner, text=schema["title"], bg=self.token["bg"], fg=self.token["title"], font=TYPOGRAPHY["title"], wraplength=900, justify="left").pack(anchor="w")
        if schema.get("subtitle"):
            tk.Label(self.inner, text=schema["subtitle"], bg=self.token["bg"], fg=self.token["subtitle"], font=TYPOGRAPHY["small"], wraplength=900, justify="left").pack(anchor="w", pady=(4, 0))
        badges = schema.get("badges") or []
        if badges:
            row = tk.Frame(self.inner, bg=self.token["bg"])
            row.pack(anchor="w", pady=(8, 0))
            for idx, badge in enumerate(badges):
                tone = badge.get("tone", "neutral")
                make_badge(row, text=badge.get("text", ""), tone=tone).pack(side="left", padx=(0 if idx == 0 else 8, 0))
        summary_pairs = schema.get("summary_pairs") or []
        if summary_pairs:
            summary = SectionCard(self.inner, "概览", "先看结论与关键数字，再往下看细节。", tone="soft", padding=SPACING["card_pad_small"])
            summary.pack(fill="x", pady=(8, 0))
            render_key_values(summary.body, summary_pairs, columns=schema.get("summary_columns", 2), bg=summary.body.cget("bg")).pack(fill="x")
        lead = schema.get("lead")
        if lead:
            lead_card = SectionCard(self.inner, "一句话判断", "", tone="accent", padding=SPACING["card_pad_small"])
            lead_card.pack(fill="x", pady=(8, 0))
            tk.Label(lead_card.body, text=lead, bg=lead_card.body.cget("bg"), fg=THEME["ink"], font=TYPOGRAPHY["body"], wraplength=920, justify="left").pack(anchor="w")
        for section in schema.get("sections") or []:
            card = SectionCard(self.inner, section.get("title", ""), section.get("subtitle", ""), tone=section.get("tone", "surface"), padding=SPACING["card_pad_small"])
            card.pack(fill="x", pady=(8, 0))
            render_section(card.body, section)
        raw_text = schema.get("raw_text")
        if raw_text and schema.get("show_raw_text", True):
            card = SectionCard(self.inner, "原始文本", "保留原始长文本，便于核对字段和调试。", tone="surface", padding=SPACING["card_pad_small"])
            card.pack(fill="both", expand=True, pady=(8, 0))
            shell, text = build_scrolled_text(card.body, height=10, variant="body")
            shell.pack(fill="both", expand=True)
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("1.0", raw_text)
            text.configure(state="disabled")


def render_section(parent, section: dict):
    kind = section.get("kind", "text")
    if kind == "text":
        tk.Label(parent, text=section.get("text", "暂无"), bg=parent.cget("bg"), fg=THEME["ink"], font=TYPOGRAPHY["body"], wraplength=920, justify="left").pack(anchor="w")
        return
    if kind == "bullets":
        items = section.get("items") or ["暂无"]
        for item in items:
            tk.Label(parent, text=f"- {item}", bg=parent.cget("bg"), fg=THEME["ink"], font=TYPOGRAPHY["body"], wraplength=920, justify="left").pack(anchor="w", pady=(0, 4))
        return
    if kind == "kv":
        render_key_values(parent, section.get("pairs", []), columns=section.get("columns", 2), bg=parent.cget("bg")).pack(fill="x")
        return
    if kind == "checklist":
        items = section.get("items") or [{"label": "暂无", "status": "muted"}]
        for item in items:
            row = tk.Frame(parent, bg=parent.cget("bg"))
            row.pack(fill="x", pady=(0, 6))
            make_badge(row, text=item.get("status_text", item.get("status", "info")).upper(), tone=item.get("tone", item.get("status", "neutral"))).pack(side="left")
            tk.Label(row, text=item.get("label", ""), bg=parent.cget("bg"), fg=THEME["ink"], font=TYPOGRAPHY["body"], wraplength=820, justify="left").pack(side="left", padx=(10, 0))
            detail = item.get("detail", "")
            if detail:
                tk.Label(parent, text=f"  {detail}", bg=parent.cget("bg"), fg=THEME["muted"], font=TYPOGRAPHY["small"], wraplength=900, justify="left").pack(anchor="w", padx=(10, 0), pady=(0, 6))
        return
    if kind == "bars":
        render_bar_rows(parent, section.get("items", [])).pack(fill="x")
        return


def render_bar_rows(parent, items: list[dict]):
    frame = tk.Frame(parent, bg=parent.cget("bg"))
    max_value = max([abs(float(item.get("value", 0) or 0)) for item in items] + [1.0])
    for item in items:
        row = tk.Frame(frame, bg=frame.cget("bg"))
        row.pack(fill="x", pady=(0, 8))
        tk.Label(row, text=item.get("label", ""), bg=row.cget("bg"), fg=THEME["ink"], font=TYPOGRAPHY["small_strong"], width=16, anchor="w").pack(side="left")
        canvas = tk.Canvas(row, width=220, height=14, bg=THEME["surface_alt"], highlightthickness=0, bd=0)
        canvas.pack(side="left", padx=(8, 8))
        ratio = abs(float(item.get("value", 0) or 0)) / max_value
        color = badge_palette(item.get("tone", "info"))[1]
        canvas.create_rectangle(0, 0, max(4, int(220 * ratio)), 14, fill=color, width=0)
        tk.Label(row, text=item.get("value_text", str(item.get("value", 0))), bg=row.cget("bg"), fg=THEME["ink"], font=TYPOGRAPHY["small"], anchor="e").pack(side="left")
    return frame


def create_empty_state(parent, title: str, body: str, *, tone: str = "soft", action_text: str | None = None, command=None):
    card = SectionCard(parent, title, body, tone=tone, padding=SPACING["card_pad_small"])
    if action_text and command is not None:
        ttk.Button(card.body, text=action_text, command=command, style="Primary.TButton").pack(anchor="w")
    return card


class ToastHub:
    def __init__(self, root: tk.Misc):
        self.root = root
        self.layer = tk.Frame(root, bg=THEME["bg"])
        self.layer.place(relx=1.0, rely=1.0, anchor="se", x=-18, y=-18)
        self.toasts: list[tk.Frame] = []
        self.history: list[dict] = []
        self.on_history_change = None

    def push(self, title: str, body: str = "", *, tone: str = "info", timeout_ms: int = 5000, action_text: str | None = None, action=None):
        token = panel_palette(tone if tone in {"accent", "success", "warning", "danger", "info"} else "info")
        toast = tk.Frame(self.layer, bg=token["bg"], bd=0, highlightbackground=token["line"], highlightcolor=token["line"], highlightthickness=1)
        toast.pack(anchor="e", pady=(0, 8))
        inner = tk.Frame(toast, bg=token["bg"])
        inner.pack(fill="both", expand=True, padx=14, pady=12)
        top = tk.Frame(inner, bg=token["bg"])
        top.pack(fill="x")
        tk.Label(top, text=title, bg=token["bg"], fg=token["title"], font=TYPOGRAPHY["body_strong"]).pack(side="left", anchor="w")
        dismiss = tk.Button(top, text="x", command=lambda t=toast: self._dismiss(t), bg=token["bg"], fg=token["subtitle"], activebackground=token["bg"], activeforeground=token["title"], relief="flat", bd=0, padx=4, pady=0, font=TYPOGRAPHY["small"])
        dismiss.pack(side="right")
        if body:
            tk.Label(inner, text=body, bg=token["bg"], fg=token["subtitle"], font=TYPOGRAPHY["small"], wraplength=320, justify="left").pack(anchor="w", pady=(4, 0))
        if action_text and action is not None:
            ttk.Button(inner, text=action_text, command=action, style="Ghost.TButton").pack(anchor="e", pady=(8, 0))
        self.toasts.append(toast)
        self.history.insert(0, {"title": title, "body": body, "tone": tone, "time": datetime.now().strftime("%H:%M:%S")})
        self.history = self.history[:8]
        if self.on_history_change:
            self.on_history_change(self.history)
        while len(self.toasts) > 4:
            self._dismiss(self.toasts[0])
        if timeout_ms > 0:
            self.root.after(timeout_ms, lambda t=toast: self._dismiss(t))

    def _dismiss(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
        try:
            toast.destroy()
        except Exception:
            pass
