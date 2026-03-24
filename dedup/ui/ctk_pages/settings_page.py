"""
CustomTkinter Settings page (experimental).

Minimal device-oriented readouts; advanced options stay on the classic shell for now.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk


class SettingsPageCTK(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        *,
        database_path: str,
        on_open_themes: Callable[[], None],
        on_open_diagnostics: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_open_themes = on_open_themes
        self._on_open_diagnostics = on_open_diagnostics
        self._db_path = database_path
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def set_database_path(self, path: str) -> None:
        self._db_path = path
        if hasattr(self, "_db_var"):
            self._db_var.set(path)

    def _build(self) -> None:
        top = ctk.CTkFrame(self, corner_radius=12)
        top.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Settings", font=ctk.CTkFont(size=26, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4)
        )
        ctk.CTkLabel(
            top,
            text="Lightweight CTK panel. Full preferences remain available in the classic UI path.",
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 16))

        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="Data", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 8)
        )
        ctk.CTkLabel(card, text="Scan history database", text_color=("gray40", "gray70")).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 4)
        )
        self._db_var = ctk.StringVar(value=self._db_path)
        ctk.CTkLabel(
            card,
            textvariable=self._db_var,
            text_color=("gray20", "gray85"),
            anchor="w",
            justify="left",
            wraplength=700,
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))

        ctk.CTkLabel(card, text="Look & feel", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=3, column=0, sticky="w", padx=16, pady=(0, 8)
        )
        nav_row = ctk.CTkFrame(card, fg_color="transparent")
        nav_row.grid(row=4, column=0, sticky="w", padx=16, pady=(0, 16))
        ctk.CTkButton(nav_row, text="Open Themes…", width=160, command=self._on_open_themes).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            nav_row,
            text="Open Diagnostics…",
            width=170,
            fg_color="gray35",
            command=self._on_open_diagnostics,
        ).pack(side="left")
