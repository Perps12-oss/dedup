"""Toolbar — horizontal action bar used in page headers."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import List, Tuple, Optional, Callable

ActionSpec = Tuple[str, str, Callable]  # (label, style, command)


class Toolbar(ttk.Frame):
    """Horizontal button toolbar."""

    def __init__(self, parent, actions: Optional[List[ActionSpec]] = None,
                 style: str = "Panel.TFrame", **kwargs):
        super().__init__(parent, style=style, padding=(4, 2), **kwargs)
        self._buttons: dict[str, ttk.Button] = {}
        for label, btn_style, cmd in (actions or []):
            self.add_button(label, btn_style, cmd)

    def add_button(self, label: str, btn_style: str, command: Callable,
                   side: str = "left") -> ttk.Button:
        btn = ttk.Button(self, text=label, style=btn_style, command=command)
        btn.pack(side=side, padx=2)
        self._buttons[label] = btn
        return btn

    def add_separator(self):
        ttk.Separator(self, orient="vertical").pack(side="left", fill="y", padx=4)

    def set_enabled(self, label: str, enabled: bool):
        if label in self._buttons:
            self._buttons[label].configure(state="normal" if enabled else "disabled")
