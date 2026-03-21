"""Canvas-based gradient helpers for CEREBRO UI."""

from __future__ import annotations

import tkinter as tk
from typing import Tuple


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


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
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event=None):
        w = self.winfo_width() or 100
        h = self.winfo_height() or 3
        draw_horizontal_gradient(self, w, h, self._c_start, self._c_end)

    def update_colors(self, c_start: str, c_end: str):
        self._c_start = c_start
        self._c_end = c_end
        self._on_resize()
