"""Badge and StatusBadge label components."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional

BADGE_STYLES = {
    "success": "Panel.Success.TLabel",
    "warning": "Panel.Warning.TLabel",
    "danger":  "Panel.Danger.TLabel",
    "info":    "Panel.Accent.TLabel",
    "muted":   "Panel.Muted.TLabel",
    "default": "Panel.Secondary.TLabel",
}


class Badge(ttk.Label):
    """Inline text badge — just a styled label."""
    def __init__(self, parent, text: str = "", variant: str = "default", **kwargs):
        style = BADGE_STYLES.get(variant, BADGE_STYLES["default"])
        super().__init__(parent, text=text, style=style,
                         font=("Segoe UI", 8, "bold"), **kwargs)
        self._var = None

    def set_text(self, text: str):
        self.configure(text=text)


class StatusBadge(ttk.Frame):
    """Dot + text badge for status display."""

    DOT_COLORS = {
        "success": "#3fb950",
        "warning": "#d29922",
        "danger":  "#f85149",
        "info":    "#58a6ff",
        "muted":   "#484f58",
    }

    def __init__(self, parent, text: str = "", variant: str = "muted",
                 style: str = "Panel.TFrame", **kwargs):
        super().__init__(parent, style=style, **kwargs)
        self._dot_canvas = tk.Canvas(self, width=8, height=8,
                                     highlightthickness=0, borderwidth=0)
        self._dot_canvas.pack(side="left", padx=(0, 4))
        self._dot_id = None
        self._text_var = tk.StringVar(value=text)
        label_style = BADGE_STYLES.get(variant, "Panel.Secondary.TLabel")
        ttk.Label(self, textvariable=self._text_var,
                  style=label_style,
                  font=("Segoe UI", 8, "bold")).pack(side="left")
        self.set(text, variant)

    def _get_bg(self) -> str:
        try:
            style = ttk.Style()
            return style.lookup("Panel.TFrame", "background") or "#161b22"
        except Exception:
            return "#161b22"

    def set(self, text: str, variant: str = "muted"):
        bg = self._get_bg()
        self._dot_canvas.configure(bg=bg)
        color = self.DOT_COLORS.get(variant, self.DOT_COLORS["muted"])
        self._dot_canvas.delete("all")
        self._dot_canvas.create_oval(1, 1, 7, 7, fill=color, outline="")
        self._text_var.set(text)
