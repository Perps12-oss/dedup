"""
CustomTkinter Welcome page (experimental).

Task-first landing page with three entry points: photos, videos, and files.
Shell uses Spine 2 cinematic margin behind this page.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk


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
        kwargs.setdefault("fg_color", "transparent")
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
        self._overlay = ctk.CTkFrame(self, fg_color="transparent")
        self._overlay.grid(row=0, column=0, sticky="nsew")
        self._overlay.grid_columnconfigure(0, weight=1)
        self._overlay.grid_rowconfigure(0, weight=1)

        # Transparent: no second opaque layer on top of main-column chrome / canvas story.
        self._card = ctk.CTkFrame(
            self._overlay,
            corner_radius=22,
            fg_color="transparent",
            border_width=0,
        )
        card = self._card
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

        self._btn_photos = ctk.CTkButton(
            card,
            text="Scan Photos",
            height=48,
            corner_radius=14,
            command=self._on_scan_photos,
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self._btn_photos.grid(row=2, column=0, padx=48, pady=(0, 12), sticky="ew")
        self._btn_videos = ctk.CTkButton(
            card,
            text="Scan Videos",
            height=48,
            corner_radius=14,
            command=self._on_scan_videos,
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self._btn_videos.grid(row=3, column=0, padx=48, pady=(0, 12), sticky="ew")
        self._btn_files = ctk.CTkButton(
            card,
            text="Scan Files",
            height=48,
            corner_radius=14,
            command=self._on_scan_files,
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self._btn_files.grid(row=4, column=0, padx=48, pady=(0, 16), sticky="ew")

        secondary = ctk.CTkFrame(card, fg_color="transparent")
        secondary.grid(row=5, column=0, padx=48, pady=(0, 34), sticky="ew")
        secondary.grid_columnconfigure((0, 1), weight=1)
        self._btn_resume = ctk.CTkButton(
            secondary,
            text="Resume scan",
            height=36,
            corner_radius=12,
            fg_color="gray35",
            command=self._on_resume_scan,
            font=ctk.CTkFont(size=13),
        )
        self._btn_resume.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self._btn_last_review = ctk.CTkButton(
            secondary,
            text="Open last review",
            height=36,
            corner_radius=12,
            fg_color="gray35",
            command=self._on_open_last_review,
            font=ctk.CTkFont(size=13),
        )
        self._btn_last_review.grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def apply_theme_tokens(self, tokens: dict) -> None:
        acc = str(tokens.get("accent_primary", "#3B8ED0"))
        elev = str(tokens.get("bg_elevated", "#21262d"))
        self._card.configure(fg_color="transparent", border_width=0)
        self._btn_photos.configure(fg_color=acc)
        self._btn_videos.configure(fg_color=acc)
        self._btn_files.configure(fg_color=acc)
        self._btn_resume.configure(fg_color=elev)
        self._btn_last_review.configure(fg_color=elev)
