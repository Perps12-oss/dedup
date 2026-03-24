"""
CustomTkinter Welcome page (experimental).

Task-first landing page with a colorful gradient and three entry points:
photos, videos, and files.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


class WelcomePageCTK(ctk.CTkFrame):
    """Centered app-name welcome with 3 scan entry actions."""

    def __init__(
        self,
        parent,
        *,
        on_scan_photos: Callable[[], None],
        on_scan_videos: Callable[[], None],
        on_scan_files: Callable[[], None],
        on_resume_scan: Callable[[], None],
        on_open_last_review: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_scan_photos = on_scan_photos
        self._on_scan_videos = on_scan_videos
        self._on_scan_files = on_scan_files
        self._on_resume_scan = on_resume_scan
        self._on_open_last_review = on_open_last_review
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build()

    def _build(self) -> None:
        # Layer 1: colorful gradient canvas.
        self._bg = tk.Canvas(self, highlightthickness=0, bd=0)
        self._bg.grid(row=0, column=0, sticky="nsew")
        self.bind("<Configure>", self._on_resize, add="+")

        # Layer 2: centered content over gradient.
        self._overlay = ctk.CTkFrame(self, fg_color="transparent")
        self._overlay.grid(row=0, column=0, sticky="nsew")
        self._overlay.grid_columnconfigure(0, weight=1)
        self._overlay.grid_rowconfigure(0, weight=1)

        card = ctk.CTkFrame(self._overlay, corner_radius=22, fg_color=("#ffffff", "#11151d"))
        card.grid(row=0, column=0, padx=40, pady=40)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="CEREBRO", font=ctk.CTkFont(size=46, weight="bold")).grid(
            row=0, column=0, padx=48, pady=(34, 6), sticky="n"
        )
        ctk.CTkLabel(
            card,
            text="Choose what you want to scan",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=16),
        ).grid(row=1, column=0, padx=48, pady=(0, 24))

        # Three top-level entry points, stacked.
        ctk.CTkButton(
            card,
            text="Scan Photos",
            height=48,
            corner_radius=14,
            command=self._on_scan_photos,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=2, column=0, padx=48, pady=(0, 12), sticky="ew")
        ctk.CTkButton(
            card,
            text="Scan Videos",
            height=48,
            corner_radius=14,
            command=self._on_scan_videos,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=3, column=0, padx=48, pady=(0, 12), sticky="ew")
        ctk.CTkButton(
            card,
            text="Scan Files",
            height=48,
            corner_radius=14,
            command=self._on_scan_files,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=4, column=0, padx=48, pady=(0, 16), sticky="ew")

        secondary = ctk.CTkFrame(card, fg_color="transparent")
        secondary.grid(row=5, column=0, padx=48, pady=(0, 34), sticky="ew")
        secondary.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            secondary,
            text="Resume scan",
            height=36,
            corner_radius=12,
            fg_color="gray35",
            command=self._on_resume_scan,
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(
            secondary,
            text="Open last review",
            height=36,
            corner_radius=12,
            fg_color="gray35",
            command=self._on_open_last_review,
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _on_resize(self, _event=None) -> None:
        self._draw_gradient()

    def _draw_gradient(self) -> None:
        w = max(2, self.winfo_width())
        h = max(2, self.winfo_height())
        self._bg.delete("all")

        # Four-color vertical blend gives a vivid but calm landing backdrop.
        stops = [
            (0.00, _hex_to_rgb("#6a11cb")),
            (0.35, _hex_to_rgb("#2575fc")),
            (0.68, _hex_to_rgb("#00c6ff")),
            (1.00, _hex_to_rgb("#7f53ac")),
        ]
        for y in range(h):
            t = y / max(h - 1, 1)
            for i in range(len(stops) - 1):
                p0, c0 = stops[i]
                p1, c1 = stops[i + 1]
                if p0 <= t <= p1:
                    lt = (t - p0) / max(p1 - p0, 1e-9)
                    col = (
                        _lerp(c0[0], c1[0], lt),
                        _lerp(c0[1], c1[1], lt),
                        _lerp(c0[2], c1[2], lt),
                    )
                    self._bg.create_line(0, y, w, y, fill=_rgb_to_hex(col))
                    break
