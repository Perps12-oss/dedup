"""EmptyState — placeholder shown when a section has no content."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable

from ..theme.design_system import font_tuple, SPACING


class EmptyState(ttk.Frame):
    """Centered icon + heading + sub message + optional CTA button."""

    def __init__(self, parent, icon: str = "○",
                 heading: str = "Nothing here yet",
                 message: str = "",
                 action_label: str = "",
                 on_action: Optional[Callable] = None,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        inner = ttk.Frame(self)
        inner.grid(row=0, column=0)

        ttk.Label(inner, text=icon, font=font_tuple("empty_icon"),
                  style="Muted.TLabel").pack(pady=(0, SPACING["md"]))
        ttk.Label(inner, text=heading, font=font_tuple("section_title")).pack()
        if message:
            ttk.Label(inner, text=message, style="Muted.TLabel",
                      font=font_tuple("body"), wraplength=320,
                      justify="center").pack(pady=(SPACING["sm"], 0))
        if action_label and on_action:
            ttk.Button(inner, text=action_label, style="Ghost.TButton",
                       command=on_action).pack(pady=(SPACING["lg"], 0))

    def hide(self):
        self.grid_remove()

    def show(self):
        self.grid()
