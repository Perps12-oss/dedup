"""
CEREBRO ThemeManager
====================
Applies a token-based theme to the running tkinter application via ttk.Style.
Uses a 'clam' base for full cross-platform colour control.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, List

from .theme_registry import THEMES, DEFAULT_THEME, get_theme
from .theme_tokens import ThemeDict

_INSTANCE: Optional["ThemeManager"] = None


def get_theme_manager() -> "ThemeManager":
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ThemeManager()
    return _INSTANCE


class ThemeManager:
    """
    Singleton that owns theme state and applies it to ttk.Style.
    Observers can subscribe to theme changes to update custom Canvas widgets.
    """

    def __init__(self):
        self._current_key: str = DEFAULT_THEME
        self._tokens: ThemeDict = get_theme(DEFAULT_THEME)
        self._observers: List[Callable[[ThemeDict], None]] = []

    @property
    def tokens(self) -> ThemeDict:
        return self._tokens

    @property
    def current_key(self) -> str:
        return self._current_key

    def subscribe(self, callback: Callable[[ThemeDict], None]) -> None:
        self._observers.append(callback)

    def unsubscribe(self, callback: Callable[[ThemeDict], None]) -> None:
        self._observers = [o for o in self._observers if o is not callback]

    def apply(self, theme_key: str, root: tk.Tk) -> None:
        self._current_key = theme_key
        self._tokens = get_theme(theme_key)
        self._configure_styles(root)
        self._apply_tk_defaults(root)
        for cb in self._observers:
            try:
                cb(self._tokens)
            except Exception:
                pass

    def _configure_styles(self, root: tk.Tk) -> None:
        t = self._tokens
        style = ttk.Style(root)
        style.theme_use("clam")

        bg = t["bg_base"]
        panel = t["bg_panel"]
        elev = t["bg_elevated"]
        sidebar = t["bg_sidebar"]
        bsoft = t["border_soft"]
        bstrong = t["border_strong"]
        fg = t["text_primary"]
        fg2 = t["text_secondary"]
        fgm = t["text_muted"]
        acc = t["accent_primary"]
        sel = t["selection_bg"]
        success = t["success"]
        warning = t["warning"]
        danger = t["danger"]

        # Root window
        root.configure(background=bg)

        # ---- Base widgets ----
        style.configure("TFrame",        background=bg)
        style.configure("TLabel",        background=bg,    foreground=fg,  font=("Segoe UI", 9))
        style.configure("TEntry",        fieldbackground=elev, foreground=fg, insertcolor=fg,
                        bordercolor=bstrong, lightcolor=bsoft, darkcolor=bsoft)
        style.configure("TCombobox",     fieldbackground=elev, foreground=fg,
                        selectbackground=sel, selectforeground=fg,
                        bordercolor=bstrong, arrowcolor=fg2)
        style.configure("TCheckbutton",  background=bg, foreground=fg, indicatorcolor=elev,
                        indicatorbackground=elev)
        style.configure("TRadiobutton",  background=bg, foreground=fg, indicatorcolor=elev)
        style.configure("TSpinbox",      fieldbackground=elev, foreground=fg, bordercolor=bstrong)
        style.configure("TScrollbar",    background=panel, troughcolor=bg,
                        arrowcolor=fg2, bordercolor=bsoft)
        style.configure("TSeparator",    background=bsoft)
        style.configure("TProgressbar",  background=acc,  troughcolor=elev,
                        bordercolor=bsoft, lightcolor=acc, darkcolor=acc)
        style.configure("TNotebook",     background=bg,   bordercolor=bsoft, tabmargins=0)
        style.configure("TNotebook.Tab", background=panel, foreground=fg2, padding=[12, 4],
                        bordercolor=bsoft)

        style.map("TNotebook.Tab",
                  background=[("selected", elev)],
                  foreground=[("selected", fg)])
        style.map("TCheckbutton",
                  indicatorcolor=[("selected", acc)])
        style.map("TEntry",
                  bordercolor=[("focus", acc)])

        # ---- Panel frames ----
        style.configure("Panel.TFrame",   background=panel)
        style.configure("Sidebar.TFrame", background=sidebar)
        style.configure("Elevated.TFrame",background=elev)
        style.configure("Card.TFrame",    background=panel, relief="flat")
        style.configure("Strip.TFrame",   background=sidebar)

        # ---- Labels on panels ----
        style.configure("Panel.TLabel",   background=panel,   foreground=fg)
        style.configure("Sidebar.TLabel", background=sidebar, foreground=fg)
        style.configure("Elevated.TLabel",background=elev,    foreground=fg)
        style.configure("Muted.TLabel",   background=bg,      foreground=fgm)
        style.configure("Secondary.TLabel",background=bg,     foreground=fg2)
        style.configure("Panel.Muted.TLabel",   background=panel, foreground=fgm)
        style.configure("Panel.Secondary.TLabel",background=panel, foreground=fg2)
        style.configure("Elevated.Secondary.TLabel",background=elev, foreground=fg2)
        style.configure("Elevated.Muted.TLabel",background=elev, foreground=fgm)
        style.configure("Accent.TLabel",  background=bg,      foreground=acc)
        style.configure("Panel.Accent.TLabel",background=panel,foreground=acc)
        style.configure("Success.TLabel", background=bg,      foreground=success)
        style.configure("Warning.TLabel", background=bg,      foreground=warning)
        style.configure("Danger.TLabel",  background=bg,      foreground=danger)
        style.configure("Panel.Success.TLabel", background=panel, foreground=success)
        style.configure("Panel.Warning.TLabel", background=panel, foreground=warning)
        style.configure("Panel.Danger.TLabel",  background=panel, foreground=danger)

        # ---- LabelFrame ----
        style.configure("TLabelframe",       background=panel, bordercolor=bstrong,
                        foreground=fg2, relief="solid")
        style.configure("TLabelframe.Label", background=panel, foreground=fg2)

        # ---- Buttons ----
        style.configure("TButton", background=elev, foreground=fg,
                        bordercolor=bstrong, lightcolor=bsoft, darkcolor=bsoft,
                        relief="flat", padding=[10, 4])
        style.map("TButton",
                  background=[("active", bstrong), ("pressed", acc)],
                  foreground=[("pressed", fg)])

        style.configure("Accent.TButton", background=acc, foreground=bg,
                        bordercolor=acc, relief="flat", padding=[12, 5],
                        font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton",
                  background=[("active", t["gradient_end"]), ("pressed", t["gradient_start"])],
                  foreground=[("active", bg)])

        style.configure("Danger.TButton", background=danger, foreground=bg,
                        bordercolor=danger, relief="flat", padding=[12, 5])
        style.map("Danger.TButton",
                  background=[("active", t.get("danger_hover", danger))])

        style.configure("Ghost.TButton", background=bg, foreground=fg2,
                        bordercolor=bsoft, relief="flat", padding=[8, 3])
        style.map("Ghost.TButton",
                  background=[("active", panel)],
                  foreground=[("active", fg)])

        style.configure("Nav.TButton", background=sidebar, foreground=fg2,
                        bordercolor=sidebar, relief="flat", padding=[12, 8],
                        font=("Segoe UI", 9))
        style.map("Nav.TButton",
                  background=[("active", t["nav_active_bg"]), ("disabled", sidebar)],
                  foreground=[("active", t["nav_active_fg"]), ("disabled", t["nav_active_fg"])])

        # ---- Treeview (DataTable) ----
        style.configure("Treeview",
                        background=panel, foreground=fg,
                        fieldbackground=panel, bordercolor=bsoft,
                        rowheight=28, font=("Segoe UI", 9))
        style.configure("Treeview.Heading",
                        background=sidebar, foreground=fg2,
                        bordercolor=bsoft, relief="flat",
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview",
                  background=[("selected", sel)],
                  foreground=[("selected", fg)])
        style.map("Treeview.Heading",
                  background=[("active", elev)])

        # ---- Paned window ----
        style.configure("TPanedwindow", background=bg)
        style.configure("Sash", sashrelief="flat", sashthickness=4, background=bsoft)

    def _apply_tk_defaults(self, root: tk.Tk) -> None:
        """Apply theme tokens to raw Tk widgets via option_add (Listbox, Canvas, etc.)."""
        t = self._tokens
        bg = t["bg_base"]
        fg = t["text_primary"]
        panel = t["bg_panel"]
        sel = t["selection_bg"]
        root.option_add("*Background", bg)
        root.option_add("*Foreground", fg)
        root.option_add("*HighlightBackground", bg)
        root.option_add("*HighlightColor", fg)
        root.option_add("*Listbox*Background", panel)
        root.option_add("*Listbox*Foreground", fg)
        root.option_add("*Listbox*SelectBackground", sel)
        root.option_add("*Listbox*SelectForeground", fg)
        root.option_add("*Canvas*Background", panel)
        root.option_add("*Canvas*HighlightBackground", panel)

    def t(self, key: str) -> str:
        """Shorthand token lookup."""
        return self._tokens.get(key, self._tokens.get("danger", "#ff00ff"))
