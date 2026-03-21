"""Badge and StatusBadge label components."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..theme.design_system import font_tuple
from ..theme.theme_manager import get_theme_manager

BADGE_STYLES = {
    "success": "Panel.Success.TLabel",
    "warning": "Panel.Warning.TLabel",
    "danger": "Panel.Danger.TLabel",
    "info": "Panel.Accent.TLabel",
    "muted": "Panel.Muted.TLabel",
    "default": "Panel.Secondary.TLabel",
}

_VARIANT_TOKEN_MAP = {
    "success": "success",
    "warning": "warning",
    "danger": "danger",
    "info": "accent_primary",
    "muted": "text_muted",
}


class Badge(ttk.Label):
    """Inline text badge — just a styled label."""

    def __init__(self, parent, text: str = "", variant: str = "default", **kwargs):
        style = BADGE_STYLES.get(variant, BADGE_STYLES["default"])
        super().__init__(parent, text=text, style=style, font=font_tuple("data_value"), **kwargs)
        self._var = None

    def set_text(self, text: str):
        self.configure(text=text)


class StatusBadge(ttk.Frame):
    """Dot + text badge for status display."""

    def __init__(self, parent, text: str = "", variant: str = "muted", style: str = "Panel.TFrame", **kwargs):
        super().__init__(parent, style=style, **kwargs)
        self._dot_canvas = tk.Canvas(self, width=8, height=8, highlightthickness=0, borderwidth=0)
        self._dot_canvas.pack(side="left", padx=(0, 4))
        self._dot_id = None
        self._text_var = tk.StringVar(value=text)
        label_style = BADGE_STYLES.get(variant, "Panel.Secondary.TLabel")
        ttk.Label(self, textvariable=self._text_var, style=label_style, font=font_tuple("data_value")).pack(side="left")
        self.set(text, variant)

    def _get_bg(self) -> str:
        try:
            s = ttk.Style()
            return s.lookup("Panel.TFrame", "background") or self._token("bg_panel")
        except Exception:
            return self._token("bg_panel")

    @staticmethod
    def _token(name: str) -> str:
        tm = get_theme_manager()
        return tm.tokens.get(name, "#161b22")

    def _dot_color(self, variant: str) -> str:
        token_name = _VARIANT_TOKEN_MAP.get(variant, "text_muted")
        return self._token(token_name)

    def set(self, text: str, variant: str = "muted"):
        bg = self._get_bg()
        self._dot_canvas.configure(bg=bg)
        color = self._dot_color(variant)
        self._dot_canvas.delete("all")
        self._dot_canvas.create_oval(1, 1, 7, 7, fill=color, outline="")
        self._text_var.set(text)
