"""
CustomTkinter Themes page (experimental).

Appearance mode and built-in CustomTkinter color themes.
"""

from __future__ import annotations

import customtkinter as ctk

# Bundled themes in typical CustomTkinter installs
_COLOR_THEMES = ("blue", "green", "dark-blue")


class ThemesPageCTK(ctk.CTkFrame):
    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def _build(self) -> None:
        top = ctk.CTkFrame(self, corner_radius=12)
        top.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Themes", font=ctk.CTkFont(size=26, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4)
        )
        ctk.CTkLabel(
            top,
            text="Appearance updates immediately. Color theme may look best after switching pages once.",
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 16))

        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text="Appearance", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 10)
        )
        ctk.CTkLabel(card, text="Mode", text_color=("gray40", "gray70")).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 12)
        )
        mode = ctk.CTkSegmentedButton(card, values=["Dark", "Light", "System"], command=self._on_mode)
        mode.grid(row=1, column=1, sticky="w", padx=(0, 16), pady=(0, 12))
        cur_raw = str(ctk.get_appearance_mode() or "dark")
        cur_map = {"dark": "Dark", "light": "Light", "system": "System"}
        mode.set(cur_map.get(cur_raw.lower(), "Dark"))

        ctk.CTkLabel(card, text="Accent theme", text_color=("gray40", "gray70")).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 16)
        )
        self._color_var = ctk.StringVar(value="blue")
        color_menu = ctk.CTkOptionMenu(
            card,
            variable=self._color_var,
            values=list(_COLOR_THEMES),
            command=self._on_color_theme,
            width=200,
        )
        color_menu.grid(row=2, column=1, sticky="w", padx=(0, 16), pady=(0, 16))

    def _on_mode(self, value: str) -> None:
        ctk.set_appearance_mode(value)

    def _on_color_theme(self, _choice: str) -> None:
        theme = self._color_var.get()
        if theme in _COLOR_THEMES:
            ctk.set_default_color_theme(theme)
