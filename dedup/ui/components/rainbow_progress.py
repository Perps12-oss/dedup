"""
Rainbow-style horizontal progress indicator (Tk Canvas).

Rounded track, multi-stop gradient fill, optional indeterminate sliding window.
Used on the Scan page with live fraction + ETA text.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Optional

from ..theme.gradients import color_at_gradient_position
from ..theme.theme_manager import get_theme_manager
from ..theme.theme_tokens import ThemeDict

# Rainbow stops (violet → blue → green → yellow → orange → pink)
_RAINBOW_STOPS = (
    (0.0, "#8B5CF6"),
    (0.18, "#3B82F6"),
    (0.38, "#22C55E"),
    (0.58, "#EAB308"),
    (0.78, "#F97316"),
    (1.0, "#EC4899"),
)


class RainbowProgressBar(tk.Frame):
    """Pill-shaped track with rainbow fill clipped to progress fraction."""

    def __init__(self, parent, height: int = 32, **kwargs):
        super().__init__(parent, **kwargs)
        self._height = height
        self._fraction = 0.0
        self._indeterminate = False
        self._pulse = 0.0
        self._after_id: Optional[str] = None
        self._tm = get_theme_manager()

        self._canvas = tk.Canvas(self, height=height, highlightthickness=0, bd=0, bg=self._track_bg())
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Configure>", lambda _e: self._redraw())

        self._theme_cb = self._on_theme
        self._tm.subscribe(self._theme_cb)

    def _track_bg(self) -> str:
        return self._tm.tokens.get("bg_elevated", "#2a2a2a")

    def _border_color(self) -> str:
        return self._tm.tokens.get("border_soft", "#444444")

    def _on_theme(self, tokens: ThemeDict) -> None:
        self._canvas.configure(bg=tokens.get("bg_elevated", self._track_bg()))
        self._redraw()

    def set_fraction(self, fraction: float, *, indeterminate: bool = False) -> None:
        """0..1 fill. Indeterminate runs a sliding rainbow window (unknown totals)."""
        self._indeterminate = bool(indeterminate)
        self._fraction = max(0.0, min(1.0, float(fraction)))
        if self._indeterminate:
            self._start_pulse()
        else:
            self._stop_pulse()
        self._redraw()

    def _stop_pulse(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _start_pulse(self) -> None:
        self._stop_pulse()

        def tick() -> None:
            self._pulse = (self._pulse + 0.15) % (2 * math.pi)
            self._redraw()
            self._after_id = self.after(50, tick)

        tick()

    def _redraw(self, _event=None) -> None:
        self._canvas.delete("all")
        w = max(2, self._canvas.winfo_width())
        h = max(4, self._canvas.winfo_height())
        pad = 2
        x0, y0 = pad, pad
        x1, y1 = w - pad, h - pad
        if x1 <= x0 or y1 <= y0:
            return

        r = min((y1 - y0) // 2, 14)
        border = self._border_color()
        track = self._track_bg()

        self._canvas.create_arc(x0, y0, x0 + 2 * r, y1, start=90, extent=180, fill=track, outline=border, width=1)
        self._canvas.create_arc(x1 - 2 * r, y0, x1, y1, start=-90, extent=180, fill=track, outline=border, width=1)
        self._canvas.create_rectangle(x0 + r, y0, x1 - r, y1, fill=track, outline="", width=0)
        self._canvas.create_line(x0 + r, y0, x1 - r, y0, fill=border, width=1)
        self._canvas.create_line(x0 + r, y1, x1 - r, y1, fill=border, width=1)

        inner_w = (x1 - x0) - 2 * r - 4
        inner_left = x0 + r + 2
        inner_top = y0 + 3
        inner_bot = y1 - 3
        if inner_w < 2:
            return

        if self._indeterminate:
            fw = max(8, int(inner_w * 0.42))
            start = int((inner_w - fw) * (0.5 + 0.5 * math.sin(self._pulse)))
            start = max(0, min(inner_w - fw, start))
            fill_start = inner_left + start
            fill_w = fw
        else:
            fill_w = max(0, int(inner_w * self._fraction))
            fill_start = inner_left

        if fill_w < 1:
            return

        step = max(1, fill_w // 96)
        for i in range(0, fill_w, step):
            u = i / max(1, fill_w - 1) if fill_w > 1 else 0.0
            col = color_at_gradient_position(_RAINBOW_STOPS, u)
            xa = fill_start + i
            xb = min(fill_start + i + step + 1, fill_start + fill_w)
            self._canvas.create_rectangle(xa, inner_top, xb, inner_bot, fill=col, outline="", width=0)

    def destroy(self) -> None:
        try:
            self._tm.unsubscribe(self._theme_cb)
        except Exception:
            pass
        self._stop_pulse()
        super().destroy()
