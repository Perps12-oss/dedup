"""
Interactive horizontal gradient strip: drag stops, live preview.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, List, Optional, Tuple

from .gradients import draw_horizontal_multi_stop

OnStopsChange = Callable[[List[Tuple[float, str]]], None]

_HANDLE_R = 7
_PICK_TOL = 0.04


class DraggableGradientEditor(tk.Canvas):
    """Multi-stop gradient with draggable handles (normalized positions 0–1)."""

    def __init__(
        self,
        parent,
        *,
        height: int = 52,
        on_change: Optional[OnStopsChange] = None,
        **kwargs,
    ) -> None:
        kw = {"height": height, "highlightthickness": 1, "borderwidth": 0}
        kw.update(kwargs)
        super().__init__(parent, **kw)
        self._on_change = on_change
        self._stops: List[Tuple[float, str]] = [(0.0, "#1f6feb"), (1.0, "#58a6ff")]
        self._drag_idx: Optional[int] = None
        self.bind("<Configure>", lambda e: self._redraw(e, notify=False), add="+")
        self.bind("<Button-1>", self._on_down)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_up)

    def set_stops(self, stops: List[Tuple[float, str]], *, silent: bool = False) -> None:
        self._stops = [tuple(x) for x in stops] if stops else [(0.0, "#1f6feb"), (1.0, "#58a6ff")]
        self._redraw(notify=not silent)

    def get_stops(self) -> List[Tuple[float, str]]:
        return list(self._stops)

    def _u_from_event(self, event) -> float:
        w = max(1, self.winfo_width())
        return max(0.0, min(1.0, event.x / w))

    def _hit_index(self, u: float) -> Optional[int]:
        for i, (pos, _) in enumerate(self._stops):
            if abs(pos - u) <= _PICK_TOL:
                return i
        return None

    def _on_down(self, event) -> None:
        u = self._u_from_event(event)
        self._drag_idx = self._hit_index(u)

    def _on_drag(self, event) -> None:
        if self._drag_idx is None:
            return
        u = self._u_from_event(event)
        pos, col = self._stops[self._drag_idx]
        self._stops[self._drag_idx] = (u, col)
        self._redraw(notify=False)

    def _on_up(self, event) -> None:
        if self._drag_idx is not None:
            u = self._u_from_event(event)
            i = self._drag_idx
            self._drag_idx = None
            if 0 <= i < len(self._stops):
                pos, col = self._stops[i]
                self._stops[i] = (max(0.0, min(1.0, u)), col)
            self._redraw(notify=True)

    def _redraw(self, event=None, notify: bool = True) -> None:
        w = max(2, self.winfo_width())
        h = max(2, self.winfo_height())
        srt = sorted(self._stops, key=lambda x: x[0])
        if len(srt) >= 2:
            draw_horizontal_multi_stop(self, w, h, srt, segments=128)
        else:
            self.delete("gradient")
        self.delete("handle")
        for pos, col in self._stops:
            cx = int(pos * w)
            cy = h // 2
            self.create_oval(
                cx - _HANDLE_R,
                cy - _HANDLE_R,
                cx + _HANDLE_R,
                cy + _HANDLE_R,
                fill=col,
                outline="#ffffff",
                width=2,
                tags="handle",
            )
        if notify and self._on_change:
            try:
                self._on_change(list(self._stops))
            except Exception:
                pass


def hue_shift_hex(hex_color: str, delta_hue_01: float) -> str:
    """Rough hue rotation in RGB space for preview (0–1 maps to full twist)."""
    try:
        from colorsys import hls_to_rgb, rgb_to_hls

        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
        hh, lum, sat = rgb_to_hls(r, g, b)
        hh = (hh + delta_hue_01) % 1.0
        r2, g2, b2 = hls_to_rgb(hh, lum, sat)
        return f"#{int(r2 * 255):02x}{int(g2 * 255):02x}{int(b2 * 255):02x}"
    except Exception:
        return hex_color
