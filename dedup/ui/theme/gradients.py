"""Canvas-based gradient helpers for CEREBRO UI."""

from __future__ import annotations

import math
import tkinter as tk
from typing import Any, List, Optional, Sequence, Tuple


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def color_at_gradient_position(stops: Sequence[Tuple[float, str]], u: float) -> str:
    """Piecewise-linear color along sorted stops (positions in [0, 1])."""
    if not stops:
        return "#000000"
    if len(stops) == 1:
        return stops[0][1]
    s = sorted(stops, key=lambda x: x[0])
    u = max(0.0, min(1.0, float(u)))
    if u <= s[0][0]:
        return s[0][1]
    if u >= s[-1][0]:
        return s[-1][1]
    for i in range(len(s) - 1):
        t0, c0 = s[i]
        t1, c1 = s[i + 1]
        if t0 <= u <= t1:
            if t1 <= t0:
                return c0
            local = (u - t0) / (t1 - t0)
            return lerp_color(c0, c1, local)
    return s[-1][1]


def draw_horizontal_multi_stop(
    canvas: tk.Canvas,
    width: int,
    height: int,
    stops: Sequence[Tuple[float, str]],
    segments: int = 96,
) -> None:
    """Horizontal strip: color is piecewise-linear between stops."""
    canvas.delete("gradient")
    if len(stops) < 2:
        return
    s = sorted(stops, key=lambda x: x[0])
    step_w = max(1, width // max(8, segments))
    n = max(2, width // step_w)
    for i in range(n):
        u = i / (n - 1) if n > 1 else 0.0
        color = color_at_gradient_position(s, u)
        x0 = i * step_w
        x1 = x0 + step_w + 1
        canvas.create_rectangle(x0, 0, x1, height, fill=color, outline="", tags="gradient")


def lerp_color(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return rgb_to_hex(r, g, b)


def draw_horizontal_gradient(
    canvas: tk.Canvas,
    width: int,
    height: int,
    color_start: str,
    color_end: str,
    steps: int = 64,
) -> None:
    canvas.delete("gradient")
    step_w = max(1, width // steps)
    for i in range(steps):
        t = i / (steps - 1) if steps > 1 else 0
        color = lerp_color(color_start, color_end, t)
        x0 = i * step_w
        x1 = x0 + step_w + 1
        canvas.create_rectangle(x0, 0, x1, height, fill=color, outline="", tags="gradient")


def cinematic_chrome_color(tokens: dict[str, Any], *, reduced: bool) -> str:
    """
    Single hex approximating the gradient wash for CTk surfaces that cannot show a live Canvas through.
    Strong blend toward gradient_mid / gradient_end so the main column reads gold, not flat grey-blue.
    """
    base = str(tokens.get("bg_base", "#0f131c"))
    gm = str(tokens.get("gradient_mid", tokens.get("accent_primary", base)))
    ge = str(tokens.get("gradient_end", gm))
    amt = 0.38 if reduced else 0.64
    a = lerp_color(base, gm, amt)
    return lerp_color(a, ge, 0.26)


def paint_cinematic_backdrop(
    canvas: tk.Canvas,
    width: int,
    height: int,
    tokens: dict[str, Any],
    *,
    reduced: bool,
) -> None:
    """
    Full-area Tk Canvas fill: multi-stop gold / accent wash blended into bg_base.
    Used behind an inset CTk shell (Spine 2) — gradient shows in the outer margin.
    """
    canvas.delete("backdrop")
    w = max(2, int(width))
    h = max(2, int(height))
    base = str(tokens.get("bg_base", "#0f131c"))
    canvas.configure(bg=base)

    if reduced:
        gmid = str(tokens.get("gradient_mid", base))
        c_top = lerp_color(base, gmid, 0.18)
        c_bot = lerp_color(base, gmid, 0.10)
        draw_vertical_gradient(canvas, w, h, c_top, c_bot, steps=56)
        return

    stops_raw = tokens.get("_multi_gradient_stops")
    stops: List[Tuple[float, str]] | None = None
    if isinstance(stops_raw, list) and len(stops_raw) >= 2:
        norm: List[Tuple[float, str]] = []
        for item in stops_raw:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    norm.append((float(item[0]), str(item[1])))
                except (TypeError, ValueError):
                    continue
        if len(norm) >= 2:
            stops = sorted(norm, key=lambda x: x[0])

    if stops is None or len(stops) < 2:
        g0 = str(tokens.get("gradient_start", base))
        g1 = str(tokens.get("gradient_mid", g0))
        g2 = str(tokens.get("gradient_end", base))
        stops = [(0.0, g0), (0.5, g1), (1.0, g2)]

    nbands = max(48, min(96, h // 8))
    band_h = max(1, h // nbands)
    for i in range(nbands + 2):
        y0 = i * band_h
        if y0 >= h:
            break
        y1 = min(h, y0 + band_h + 1)
        uy = ((y0 + y1) * 0.5) / h
        u_wave = uy * 0.72 + 0.14 * math.sin(uy * math.pi)
        u_wave = max(0.0, min(1.0, u_wave))
        sweep = color_at_gradient_position(stops, u_wave)
        col = lerp_color(base, sweep, 0.84)
        canvas.create_rectangle(0, y0, w, y1, fill=col, outline="", tags="backdrop")


def draw_vertical_gradient(
    canvas: tk.Canvas,
    width: int,
    height: int,
    color_start: str,
    color_end: str,
    steps: int = 48,
) -> None:
    canvas.delete("gradient")
    step_h = max(1, height // steps)
    for i in range(steps):
        t = i / (steps - 1) if steps > 1 else 0
        color = lerp_color(color_start, color_end, t)
        y0 = i * step_h
        y1 = y0 + step_h + 1
        canvas.create_rectangle(0, y0, width, y1, fill=color, outline="", tags="gradient")


class GradientBar(tk.Canvas):
    """A thin horizontal gradient bar — used in top bar hero strip."""

    def __init__(self, parent, height: int = 3, color_start: str = "#1f6feb", color_end: str = "#58a6ff", **kwargs):
        super().__init__(parent, height=height, highlightthickness=0, borderwidth=0, **kwargs)
        self._c_start = color_start
        self._c_end = color_end
        self._multi_stops: Optional[List[Tuple[float, str]]] = None
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event=None):
        w = self.winfo_width() or 100
        h = self.winfo_height() or 3
        if self._multi_stops and len(self._multi_stops) >= 2:
            draw_horizontal_multi_stop(self, w, h, self._multi_stops)
        else:
            draw_horizontal_gradient(self, w, h, self._c_start, self._c_end)

    def update_colors(self, c_start: str, c_end: str):
        self._multi_stops = None
        self._c_start = c_start
        self._c_end = c_end
        self._on_resize()

    def update_from_tokens(self, tokens: dict) -> None:
        stops = tokens.get("_multi_gradient_stops")
        if isinstance(stops, list) and len(stops) >= 2:
            norm: List[Tuple[float, str]] = []
            for item in stops:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    try:
                        norm.append((float(item[0]), str(item[1])))
                    except (TypeError, ValueError):
                        continue
            if len(norm) >= 2:
                self._multi_stops = sorted(norm, key=lambda x: x[0])
                self._c_start = self._multi_stops[0][1]
                self._c_end = self._multi_stops[-1][1]
                self._on_resize()
                return
        self._multi_stops = None
        self._c_start = tokens.get("gradient_start", self._c_start)
        self._c_end = tokens.get("gradient_end", self._c_end)
        self._on_resize()
