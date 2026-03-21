"""Compact theme preview swatch used in settings page."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .gradients import lerp_color
from .theme_registry import THEMES


class ThemeSwatchGrid(ttk.Frame):
    """Grid of theme swatches; clicking one calls on_select(theme_key)."""

    def __init__(self, parent, on_select: Callable[[str], None], current_key: str = "aurora_slate", **kwargs):
        super().__init__(parent, **kwargs)
        self._on_select = on_select
        self._current = current_key
        self._build()

    def _build(self):
        cols = 5
        for i, (key, t) in enumerate(THEMES.items()):
            swatch = self._make_swatch(key, t)
            row, col = i // cols, i % cols
            swatch.grid(row=row, column=col, padx=4, pady=4, sticky="nw")

    def _make_swatch(self, key: str, t: dict) -> tk.Frame:
        outer = tk.Frame(self, bg=t["border_strong"], padx=1, pady=1)
        inner = tk.Frame(outer, bg=t["bg_panel"], width=64, height=48)
        inner.pack_propagate(False)
        inner.pack()
        # gradient strip at top
        bar = tk.Canvas(inner, height=6, bg=t["bg_panel"], highlightthickness=0)
        bar.pack(fill="x")
        bar.update_idletasks()
        w = 64
        for i in range(w):
            t_val = i / max(w - 1, 1)
            col = lerp_color(t["gradient_start"], t["gradient_end"], t_val)
            bar.create_line(i, 0, i, 6, fill=col)
        # name label
        lbl = tk.Label(
            inner,
            text=t["name"],
            bg=t["bg_panel"],
            fg=t["text_secondary"],
            font=("Segoe UI", 7),
            wraplength=58,
            justify="center",
        )
        lbl.pack(fill="both", expand=True, padx=2)
        for w_ in (outer, inner, lbl):
            w_.bind("<Button-1>", lambda e, k=key: self._on_select(k))
        return outer

    def set_current(self, key: str):
        self._current = key
