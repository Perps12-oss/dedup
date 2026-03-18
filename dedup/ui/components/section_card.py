"""SectionCard — a titled panel card used throughout the app."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional

from ..theme.design_system import font_tuple, SPACING


class SectionCard(ttk.Frame):
    """
    Titled card with optional badge/action on header row.
    Content is placed inside `self.body`.
    """

    def __init__(self, parent, title: str = "", badge: str = "",
                 style: str = "Panel.TFrame", **kwargs):
        super().__init__(parent, style=style, **kwargs)
        self.columnconfigure(0, weight=1)

        # Header
        header = ttk.Frame(self, style=style)
        header.grid(row=0, column=0, sticky="ew", padx=SPACING["lg"], pady=(SPACING["lg"], SPACING["xs"]))
        header.columnconfigure(0, weight=1)

        if title:
            self._title_var = tk.StringVar(value=title)
            ttk.Label(header, textvariable=self._title_var,
                      style="Panel.Secondary.TLabel",
                      font=font_tuple("card_title")).grid(row=0, column=0, sticky="w")

        if badge:
            self._badge_var = tk.StringVar(value=badge)
            ttk.Label(header, textvariable=self._badge_var,
                      style="Panel.Muted.TLabel",
                      font=font_tuple("caption")).grid(row=0, column=1, sticky="e", padx=(SPACING["md"], 0))
        else:
            self._badge_var = None

        # Separator
        ttk.Separator(self, orient="horizontal").grid(row=1, column=0, sticky="ew", padx=SPACING["md"])

        # Body
        self.body = ttk.Frame(self, style=style, padding=(SPACING["lg"], SPACING["md"], SPACING["lg"], SPACING["lg"]))
        self.body.grid(row=2, column=0, sticky="nsew")
        self.body.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

    def set_title(self, title: str):
        self._title_var.set(title)

    def set_badge(self, badge: str):
        if self._badge_var:
            self._badge_var.set(badge)
