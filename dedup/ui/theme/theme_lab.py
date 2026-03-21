"""
Theme Lab — hero preview strip + atmospheric background + widget showcase (Sun Valley–style polish).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from .design_system import font_tuple, get_ui_font_family
from .gradients import draw_horizontal_multi_stop

# Atmospheric multi-stop background (premium-tool vibe: deep blue → violet → magenta)
_LAB_BG_STOPS = [
    (0.0, "#050816"),
    (0.18, "#0f1c3d"),
    (0.38, "#2d1b5e"),
    (0.55, "#5c1a5c"),
    (0.72, "#1e3a5f"),
    (0.88, "#0d2137"),
    (1.0, "#0a1628"),
]


class ThemeLabPanel(ttk.Frame):
    """
    Left / hero column: blurred-gradient-style canvas + floating preview card with ttk + tk widgets.
    """

    def __init__(
        self,
        parent,
        *,
        on_accent_shift: Optional[Callable[[float], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_accent_shift = on_accent_shift
        self._accent_t = tk.DoubleVar(value=0.35)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        host = tk.Frame(self, highlightthickness=0)
        host.grid(row=0, column=0, sticky="nsew")
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)

        self._bg_canvas = tk.Canvas(host, highlightthickness=0, borderwidth=0)
        self._bg_canvas.grid(row=0, column=0, sticky="nsew")
        self._bg_canvas.bind("<Configure>", self._paint_bg, add="+")

        card = ttk.Frame(host, style="Elevated.TFrame", padding=16)
        card.place(relx=0.5, rely=0.48, anchor="center")

        ttk.Label(card, text="Theme Lab", font=font_tuple("section_title")).pack(anchor="w")
        ttk.Label(
            card,
            text="Preview chrome + accent. Adjust hue for the showcase buttons only.",
            style="Muted.TLabel",
            font=font_tuple("caption"),
            wraplength=320,
            justify="left",
        ).pack(anchor="w", pady=(4, 12))

        row1 = ttk.Frame(card)
        row1.pack(fill="x", pady=4)
        ttk.Checkbutton(row1, text="Sample option").pack(side="left", padx=(0, 12))
        ttk.Radiobutton(row1, text="A", value="a").pack(side="left")
        ttk.Radiobutton(row1, text="B", value="b").pack(side="left", padx=4)

        ttk.Entry(row1, width=18).pack(side="right")

        self._preview_accent_btn = tk.Button(
            row1,
            text="Accent",
            font=(get_ui_font_family(), 10, "bold"),
            padx=14,
            pady=6,
            cursor="hand2",
            relief="flat",
            borderwidth=0,
        )
        self._preview_accent_btn.pack(side="right", padx=(12, 0))
        self._ghost_btn = ttk.Button(row1, text="Secondary", style="Ghost.TButton")
        self._ghost_btn.pack(side="right")

        scale_row = ttk.Frame(card)
        scale_row.pack(fill="x", pady=(12, 4))
        ttk.Label(scale_row, text="Accent hue", style="Muted.TLabel").pack(side="left")
        self._hue_scale = ttk.Scale(
            scale_row,
            from_=0.0,
            to=1.0,
            variable=self._accent_t,
            command=self._on_hue_moved,
        )
        self._hue_scale.pack(side="left", fill="x", expand=True, padx=8)

        self._on_hue_moved()

    def _paint_bg(self, event=None) -> None:
        w = max(2, self._bg_canvas.winfo_width())
        h = max(2, self._bg_canvas.winfo_height())
        draw_horizontal_multi_stop(self._bg_canvas, w, h, _LAB_BG_STOPS, segments=160)

    def _on_hue_moved(self, *_args) -> None:
        from .gradient_editor_canvas import hue_shift_hex

        t = float(self._accent_t.get())
        base = "#0078d4"
        col = hue_shift_hex(base, t)
        self._preview_accent_btn.configure(bg=col, activebackground=col, fg="#ffffff", activeforeground="#ffffff")
        if self._on_accent_shift:
            try:
                self._on_accent_shift(t)
            except Exception:
                pass
