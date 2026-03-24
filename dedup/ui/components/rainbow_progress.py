"""
Rainbow-style horizontal progress indicator (Tk Canvas).

Pill-shaped track; fill is a stadium (rounded) clipped to progress fraction.
Shimmer is drawn in a separate layer and updated on a timer without erasing the
track/fill, so the bar does not flicker on every pulse tick.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Optional

from ..theme.gradients import color_at_gradient_position, lerp_color
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

TAG_TRACK = "rpb_track"
TAG_FILL = "rpb_fill"
TAG_SHIMMER = "rpb_shimmer"


class RainbowProgressBar(tk.Frame):
    """Pill-shaped track with rainbow fill clipped to progress fraction."""

    def __init__(self, parent, height: int = 32, **kwargs):
        super().__init__(parent, **kwargs)
        self._height = height
        self._fraction = 0.0
        self._indeterminate = False
        self._pulse = 0.0
        self._after_id: Optional[str] = None
        self._configure_after: Optional[str] = None
        self._tm = get_theme_manager()
        self._fill_right_px = 0
        self._inner_left = 0
        self._inner_top = 0
        self._inner_bot = 0
        self._inner_w = 0
        self._rr = 2

        self._canvas = tk.Canvas(self, height=height, highlightthickness=0, bd=0, bg=self._track_bg())
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Configure>", self._on_configure)

        self._theme_cb = self._on_theme
        self._tm.subscribe(self._theme_cb)
        self.after_idle(self._full_redraw)

    @staticmethod
    def _trough_fill(tokens: ThemeDict) -> str:
        elev = tokens.get("bg_elevated", "#21262d")
        panel = tokens.get("bg_panel", "")
        if panel and elev.lower() == panel.lower():
            return tokens.get("bg_base", tokens.get("border_soft", "#e8e8e8"))
        return elev

    def _track_bg(self) -> str:
        return self._trough_fill(self._tm.tokens)

    def _border_color(self) -> str:
        return self._tm.tokens.get("border_soft", "#444444")

    def _on_theme(self, tokens: ThemeDict) -> None:
        self._canvas.configure(bg=self._trough_fill(tokens))
        self._full_redraw()

    def _on_configure(self, _event=None) -> None:
        if self._configure_after is not None:
            try:
                self.after_cancel(self._configure_after)
            except Exception:
                pass
        self._configure_after = self.after(40, self._deferred_configure)

    def _deferred_configure(self) -> None:
        self._configure_after = None
        self._full_redraw()

    def set_fraction(self, fraction: float, *, indeterminate: bool = False) -> None:
        """0..1 fill. Indeterminate uses a short base fill + edge shimmer (unknown totals)."""
        nf = max(0.0, min(1.0, float(fraction)))
        ni = bool(indeterminate)
        if abs(nf - self._fraction) < 1e-5 and ni == self._indeterminate:
            return
        self._indeterminate = ni
        self._fraction = nf
        need_pulse = self._indeterminate or (0.0 < self._fraction < 1.0)
        if need_pulse:
            self._start_pulse()
        else:
            self._stop_pulse()
        self._redraw_fill_and_shimmer()

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
            self._pulse = (self._pulse + 0.10) % (2 * math.pi)
            self._redraw_shimmer_only()
            self._after_id = self.after(72, tick)

        tick()

    @staticmethod
    def _shine(c: str) -> str:
        return lerp_color(c, "#ffffff", 0.38)

    def _layout(self) -> bool:
        w = max(2, self._canvas.winfo_width())
        h = max(4, self._canvas.winfo_height())
        pad = 2
        x0, y0 = pad, pad
        x1, y1 = w - pad, h - pad
        if x1 <= x0 or y1 <= y0:
            return False

        r = min((y1 - y0) // 2, 14)
        inner_w = (x1 - x0) - 2 * r - 4
        inner_left = x0 + r + 2
        inner_top = y0 + 3
        inner_bot = y1 - 3
        if inner_w < 2:
            return False

        rr = min(r - 1, (inner_bot - inner_top) // 2, 12)
        rr = max(2, rr)

        self._x0, self._y0, self._x1, self._y1 = x0, y0, x1, y1
        self._r_track = r
        self._inner_left = inner_left
        self._inner_top = inner_top
        self._inner_bot = inner_bot
        self._inner_w = inner_w
        self._rr = rr
        return True

    def _full_redraw(self) -> None:
        self._canvas.delete("all")
        if not self._layout():
            return
        x0, y0, x1, y1 = self._x0, self._y0, self._x1, self._y1
        r = self._r_track
        border = self._border_color()
        track = self._track_bg()

        self._canvas.create_arc(
            x0, y0, x0 + 2 * r, y1, start=90, extent=180, fill=track, outline=border, width=1, tags=TAG_TRACK
        )
        self._canvas.create_arc(
            x1 - 2 * r, y0, x1, y1, start=-90, extent=180, fill=track, outline=border, width=1, tags=TAG_TRACK
        )
        self._canvas.create_rectangle(x0 + r, y0, x1 - r, y1, fill=track, outline="", width=0, tags=TAG_TRACK)
        self._canvas.create_line(x0 + r, y0, x1 - r, y0, fill=border, width=1, tags=TAG_TRACK)
        self._canvas.create_line(x0 + r, y1, x1 - r, y1, fill=border, width=1, tags=TAG_TRACK)

        self._redraw_fill_and_shimmer()

    def _redraw_fill_and_shimmer(self) -> None:
        if not self._layout():
            return
        self._canvas.delete(TAG_FILL)
        self._canvas.delete(TAG_SHIMMER)

        il, it, ib = self._inner_left, self._inner_top, self._inner_bot
        inner_w = self._inner_w
        rr = self._rr

        if self._indeterminate:
            base_w = max(12, int(inner_w * 0.06))
            fill_right = il + min(inner_w, base_w)
        else:
            fill_w = max(0, int(inner_w * self._fraction))
            fill_right = il + fill_w

        self._fill_right_px = fill_right

        if fill_right <= il:
            return

        self._draw_stadium_fill(il, it, fill_right, ib, rr, TAG_FILL)

        show_shimmer = self._indeterminate or (0.0 < self._fraction < 1.0)
        if show_shimmer and (fill_right - il) >= 6:
            self._draw_edge_shimmer(il, it, fill_right, ib, inner_w)

    def _redraw_shimmer_only(self) -> None:
        if not self._layout():
            return
        self._canvas.delete(TAG_SHIMMER)
        il, it = self._inner_left, self._inner_top
        fr = self._fill_right_px
        ib = self._inner_bot
        inner_w = self._inner_w
        show_shimmer = self._indeterminate or (0.0 < self._fraction < 1.0)
        if show_shimmer and fr > il + 5:
            self._draw_edge_shimmer(il, it, fr, ib, inner_w)

    def _draw_stadium_fill(self, il: int, it: int, fill_right: int, ib: int, rr: int, tag: str) -> None:
        fill_w = fill_right - il
        if fill_w < 1:
            return
        h = ib - it
        rr = max(1, min(rr, fill_w // 2, h // 2))

        u_end = (fill_w - 1) / max(1, fill_w - 1) if fill_w > 1 else 0.0
        c_left = color_at_gradient_position(_RAINBOW_STOPS, 0.0)
        c_right = color_at_gradient_position(_RAINBOW_STOPS, u_end)

        body_lo = il + rr
        body_hi = fill_right - rr
        if body_hi > body_lo:
            step = max(1, (body_hi - body_lo) // 96)
            xa = body_lo
            while xa < body_hi:
                xb = min(xa + step + 1, body_hi)
                u = (xa - il) / max(1, fill_w - 1)
                col = color_at_gradient_position(_RAINBOW_STOPS, u)
                self._canvas.create_rectangle(xa, it, xb, ib, fill=col, outline="", width=0, tags=tag)
                xa = xb
        self._canvas.create_arc(
            il, it, il + 2 * rr, ib, start=90, extent=180, fill=c_left, outline="", width=0, tags=tag
        )
        self._canvas.create_arc(
            fill_right - 2 * rr, it, fill_right, ib, start=-90, extent=180, fill=c_right, outline="", width=0, tags=tag
        )

    def _draw_edge_shimmer(self, il: int, it: int, fill_right: int, ib: int, inner_w: int) -> None:
        band = max(8, min(28, int(inner_w * 0.07)))
        phase = 0.5 + 0.5 * math.sin(self._pulse)
        span = max(3, int(band * 0.55))
        x1 = fill_right - band + int((band - span) * phase)
        x2 = x1 + span
        x1 = max(il, min(x1, fill_right - 2))
        x2 = max(x1 + 1, min(x2, fill_right))
        u = max(0.0, min(1.0, ((x1 + x2) // 2 - il) / max(1, fill_right - il)))
        base = color_at_gradient_position(_RAINBOW_STOPS, u)
        hi = self._shine(base)
        mid = (x1 + x2) // 2
        self._canvas.create_rectangle(x1, it, mid, ib, fill=hi, outline="", width=0, tags=TAG_SHIMMER)
        self._canvas.create_rectangle(mid, it, x2, ib, fill=base, outline="", width=0, tags=TAG_SHIMMER)

    def destroy(self) -> None:
        try:
            self._tm.unsubscribe(self._theme_cb)
        except Exception:
            pass
        self._stop_pulse()
        if self._configure_after is not None:
            try:
                self.after_cancel(self._configure_after)
            except Exception:
                pass
            self._configure_after = None
        super().destroy()
