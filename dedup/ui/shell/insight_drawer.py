"""
InsightDrawer — toggleable right-side contextual drawer.

Content varies by page:
  - session metadata
  - warnings
  - phase details
  - resume explanation
  - selected group info
  - safety hints
  - developer diagnostics
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Tuple

from ..theme.design_system import SPACING, font_tuple
from ..theme.theme_manager import get_theme_manager
from ..utils.icons import IC

DRAWER_WIDTH = 220


class InsightDrawer(tk.Frame):
    """Right-side contextual insight drawer."""

    def __init__(self, parent, on_close: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, width=DRAWER_WIDTH, **kwargs)
        self._on_close = on_close
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._tm = get_theme_manager()
        self._visible = True
        self._sections: List[_DrawerSection] = []
        self._build()
        self._tm.subscribe(self._apply_colors)
        self._apply_colors(self._tm.tokens)

    def _build(self):
        # Header bar
        self._header = tk.Frame(self, height=36)
        self._header.pack(fill="x")
        self._header.pack_propagate(False)
        self._title_lbl = tk.Label(self._header, text=f"{IC.INFO}  Insights", font=font_tuple("card_title"), anchor="w")
        self._title_lbl.pack(side="left", fill="both", padx=SPACING["lg"])
        close_lbl = tk.Label(
            self._header, text=IC.DRAWER_CLOSE, font=font_tuple("body"), cursor="hand2", padx=SPACING["md"]
        )
        close_lbl.pack(side="right")
        close_lbl.bind("<Button-1>", lambda e: self.hide())
        self._close_lbl = close_lbl

        self._sep = tk.Frame(self, height=1)
        self._sep.pack(fill="x")

        # Scrollable body
        self._canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self._scroll = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scroll.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._scroll.pack(side="right", fill="y")

        self._body = tk.Frame(self._canvas)
        self._body_window = self._canvas.create_window((0, 0), window=self._body, anchor="nw")
        self._body.bind("<Configure>", self._on_body_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_body_configure(self, event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._body_window, width=event.width)

    def clear(self):
        for w in self._body.winfo_children():
            w.destroy()
        self._sections.clear()

    def add_section(self, title: str, rows: List[Tuple[str, str]]) -> "_DrawerSection":
        sec = _DrawerSection(self._body, title, rows)
        sec.pack(fill="x", padx=8, pady=(8, 0))
        self._sections.append(sec)
        self._apply_colors(self._tm.tokens)
        return sec

    def set_kv(self, title: str, key: str, value: str):
        for sec in self._sections:
            if sec.title == title:
                sec.set_kv(key, value)
                return

    def _handle_close_click(self) -> None:
        if self._on_close:
            self._on_close()
        else:
            self.hide()

    def hide(self):
        self._visible = False
        self.pack_forget()
        self.grid_remove()

    def show(self):
        self._visible = True

    @property
    def is_visible(self) -> bool:
        return self._visible

    def _apply_colors(self, t: dict):
        bg = t["bg_sidebar"]
        fg = t["text_primary"]
        t["text_secondary"]
        self.configure(background=bg)
        self._header.configure(background=bg)
        self._title_lbl.configure(background=bg, foreground=fg)
        self._close_lbl.configure(background=bg, foreground=t["text_muted"])
        self._sep.configure(background=t["border_soft"])
        self._canvas.configure(background=bg)
        self._body.configure(background=bg)
        for sec in self._sections:
            sec.apply_colors(t)


class _DrawerSection(tk.Frame):
    def __init__(self, parent, title: str, rows: List[Tuple[str, str]]):
        super().__init__(parent)
        self.title = title
        self._vars: dict[str, tk.StringVar] = {}
        tk.Label(self, text=title.upper(), font=font_tuple("strip")).pack(
            anchor="w", pady=(SPACING["sm"], SPACING["xs"])
        )
        tk.Frame(self, height=1).pack(fill="x", pady=(0, SPACING["sm"]))
        self._grid = tk.Frame(self)
        self._grid.pack(fill="x")
        for k, v in rows:
            self._add_row(k, v)

    def _add_row(self, key: str, value: str):
        row = tk.Frame(self._grid)
        row.pack(fill="x", pady=1)
        tk.Label(row, text=key + ":", font=font_tuple("strip"), anchor="w", width=12).pack(side="left")
        var = tk.StringVar(value=value)
        tk.Label(row, textvariable=var, font=font_tuple("data_value"), anchor="w", wraplength=110).pack(
            side="left", fill="x", expand=True
        )
        self._vars[key] = var

    def set_kv(self, key: str, value: str):
        if key in self._vars:
            self._vars[key].set(value)
        else:
            self._add_row(key, value)

    def apply_colors(self, t: dict):
        bg = t["bg_sidebar"]
        t["text_primary"]
        fg2 = t["text_secondary"]
        t["text_muted"]
        self.configure(background=bg)
        self._grid.configure(background=bg)
        for w in self.winfo_children():
            try:
                w.configure(background=bg)
            except Exception:
                pass
        for row in self._grid.winfo_children():
            row.configure(background=bg)
            for child in row.winfo_children():
                try:
                    child.configure(background=bg, foreground=fg2)
                except Exception:
                    pass
