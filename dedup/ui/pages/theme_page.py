"""
Themes page — presets, live preview swatches, WCAG contrast summary.

Phase 2 scope: preset grid + contrast readout. Gradient editor / JSON import-export: see PHASE_ROLLOUT.md.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..theme.theme_manager import get_theme_manager
from ..theme.theme_preview import ThemeSwatchGrid
from ..theme.contrast import contrast_ratio, format_ratio, passes_aa_normal
from ..theme.design_system import font_tuple
from ..utils.ui_state import UIState


def _S(n: int) -> int:
    return n * 4


class ThemePage(ttk.Frame):
    """Dedicated surface for theme exploration (beyond TopBar combo)."""

    def __init__(
        self,
        parent,
        *,
        state: UIState,
        on_theme_change: Callable[[str], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._state = state
        self._on_theme_change = on_theme_change
        self._tm = get_theme_manager()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build()
        self._tm.subscribe(self._refresh_contrast)
        self._refresh_contrast(self._tm.tokens)

    def _build(self) -> None:
        pad = _S(6)
        outer = ttk.Frame(self, padding=(pad, pad, pad, pad))
        outer.grid(row=0, column=0, rowspan=2, sticky="nsew")
        outer.columnconfigure(0, weight=1)

        title = ttk.Label(outer, text="Themes", font=font_tuple("page_title"))
        title.grid(row=0, column=0, sticky="w")
        sub = ttk.Label(
            outer,
            text="Choose a preset. Contrast checks use WCAG relative luminance (informative, not legal advice).",
            style="Muted.TLabel",
            font=font_tuple("page_subtitle"),
            wraplength=720,
            justify="left",
        )
        sub.grid(row=1, column=0, sticky="w", pady=(_S(1), _S(4)))

        sw_frame = ttk.LabelFrame(outer, text="Presets (15 + CEREBRO Noir)", padding=_S(2))
        sw_frame.grid(row=2, column=0, sticky="ew", pady=(0, _S(4)))
        self._swatches = ThemeSwatchGrid(
            sw_frame,
            on_select=self._select_theme,
            current_key=self._state.settings.theme_key,
        )
        self._swatches.pack(fill="x")

        cf = ttk.LabelFrame(outer, text="Contrast snapshot (current theme)", padding=_S(2))
        cf.grid(row=3, column=0, sticky="ew")
        self._contrast_lbl = ttk.Label(
            cf,
            text="",
            style="Muted.TLabel",
            font=("Consolas", 10),
            justify="left",
        )
        self._contrast_lbl.pack(anchor="w")

        note = ttk.Label(
            outer,
            text="Gradient editor, custom stops, and JSON import/export are planned in a follow-up sub-phase.",
            style="Muted.TLabel",
            font=font_tuple("caption"),
            wraplength=720,
            justify="left",
        )
        note.grid(row=4, column=0, sticky="w", pady=(_S(4), 0))

    def _select_theme(self, key: str) -> None:
        self._state.settings.theme_key = key
        self._on_theme_change(key)
        self._swatches.set_current(key)

    def _refresh_contrast(self, tokens: dict) -> None:
        bg = tokens.get("bg_base", "#000000")
        fg = tokens.get("text_primary", "#ffffff")
        acc = tokens.get("accent_primary", "#888888")
        r1 = contrast_ratio(fg, bg)
        r2 = contrast_ratio(acc, bg)
        ok1 = "AA text" if passes_aa_normal(r1) else "below AA normal"
        ok2 = "AA text" if passes_aa_normal(r2) else "below AA normal"
        lines = (
            f"text_primary / bg_base   {format_ratio(r1)}  ({ok1})",
            f"accent_primary / bg_base {format_ratio(r2)}  ({ok2})",
        )
        self._contrast_lbl.configure(text="\n".join(lines))

    def on_show(self) -> None:
        self._swatches.set_current(self._state.settings.theme_key)
        self._refresh_contrast(self._tm.tokens)
