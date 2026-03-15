"""SectionCard — a titled panel card used throughout the app."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional


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
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))
        header.columnconfigure(0, weight=1)

        if title:
            # Use Panel secondary style for title
            self._title_var = tk.StringVar(value=title)
            ttk.Label(header, textvariable=self._title_var,
                      style="Panel.Secondary.TLabel",
                      font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")

        if badge:
            self._badge_var = tk.StringVar(value=badge)
            ttk.Label(header, textvariable=self._badge_var,
                      style="Panel.Muted.TLabel",
                      font=("Segoe UI", 8)).grid(row=0, column=1, sticky="e", padx=(8, 0))
        else:
            self._badge_var = None

        # Separator
        ttk.Separator(self, orient="horizontal").grid(row=1, column=0, sticky="ew", padx=8)

        # Body
        self.body = ttk.Frame(self, style=style, padding=(12, 8, 12, 12))
        self.body.grid(row=2, column=0, sticky="nsew")
        self.body.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

    def set_title(self, title: str):
        self._title_var.set(title)

    def set_badge(self, badge: str):
        if self._badge_var:
            self._badge_var.set(badge)
