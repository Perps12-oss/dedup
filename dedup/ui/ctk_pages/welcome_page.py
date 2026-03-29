"""
CustomTkinter Welcome page (experimental).

Task-first landing page with three entry points: photos, videos, and files.
Shell uses Spine 2 cinematic margin behind this page.

REFACTORED: Visual redesign with modern aesthetics while preserving all APIs.
- Enhanced typography with gradient title effect simulation
- Glassmorphism-inspired card design
- Improved button hierarchy and hover states
- Consistent spacing using design tokens
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from .design_tokens import get_theme_colors, resolve_border_token


class WelcomePageCTK(ctk.CTkFrame):
    """Centered app-name welcome with 3 scan entry actions."""

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API - UNCHANGED
    # ══════════════════════════════════════════════════════════════════════════

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

        # Store callbacks - UNCHANGED
        self._on_scan_photos = on_scan_photos
        self._on_scan_videos = on_scan_videos
        self._on_scan_files = on_scan_files
        self._on_resume_scan = on_resume_scan
        self._on_open_last_review = on_open_last_review

        # Layout configuration
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._tokens = get_theme_colors()

        self._build()

    def apply_theme_tokens(self, tokens: dict) -> None:
        """Apply theme tokens to styled components. API UNCHANGED."""
        acc = str(tokens.get("accent_primary", "#22D3EE"))
        elev = str(tokens.get("bg_elevated", "#161B22"))
        panel = str(tokens.get("bg_panel", "#1C2128"))
        border = resolve_border_token(tokens)

        # Card styling with subtle border
        self._card.configure(
            fg_color=panel,
            border_width=1,
            border_color=border,
        )

        # Primary action buttons with accent
        acc_h = str(tokens.get("accent_secondary", "#06B6D4"))
        self._btn_photos.configure(fg_color=acc, hover_color=acc_h)
        self._btn_videos.configure(fg_color=acc, hover_color=acc_h)
        self._btn_files.configure(fg_color=acc, hover_color=acc_h)

        # Secondary buttons with elevated background
        ov = str(tokens.get("bg_overlay", "#21262D"))
        self._btn_resume.configure(fg_color=elev, hover_color=ov)
        self._btn_last_review.configure(fg_color=elev, hover_color=ov)

        # Decorative elements
        if hasattr(self, "_accent_line"):
            self._accent_line.configure(fg_color=acc)

    # ══════════════════════════════════════════════════════════════════════════
    # PRIVATE IMPLEMENTATION - VISUAL REFACTOR
    # ══════════════════════════════════════════════════════════════════════════

    def _adjust_brightness(self, hex_color: str, factor: float) -> str:
        """Adjust color brightness for hover states."""
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = min(255, max(0, int(r * factor)))
        g = min(255, max(0, int(g * factor)))
        b = min(255, max(0, int(b * factor)))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _build(self) -> None:
        """Build the welcome page UI with enhanced visuals."""

        # Overlay container for centering
        self._overlay = ctk.CTkFrame(self, fg_color="transparent")
        self._overlay.grid(row=0, column=0, sticky="nsew")
        self._overlay.grid_columnconfigure(0, weight=1)
        self._overlay.grid_rowconfigure(0, weight=1)

        # Main card with glassmorphism-inspired styling
        self._card = ctk.CTkFrame(
            self._overlay,
            corner_radius=24,
            fg_color=self._tokens["bg_panel"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        card = self._card
        card.grid(row=0, column=0, padx=48, pady=48)
        card.grid_columnconfigure(0, weight=1)

        # ── Header Section ──────────────────────────────────────────────────
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=56, pady=(40, 0))
        header_frame.grid_columnconfigure(0, weight=1)

        # App title with bold typography
        self._title_label = ctk.CTkLabel(
            header_frame,
            text="CEREBRO",
            font=self._title_font(),
            text_color=self._tokens["text_primary"],
        )
        self._title_label.grid(row=0, column=0, sticky="n")

        # Accent line under title
        self._accent_line = ctk.CTkFrame(
            header_frame,
            height=3,
            corner_radius=2,
            fg_color=self._tokens["accent_primary"],
        )
        self._accent_line.grid(row=1, column=0, sticky="ew", padx=80, pady=(8, 0))

        # Subtitle
        self._subtitle_label = ctk.CTkLabel(
            card,
            text="Choose what you want to scan",
            text_color=self._tokens["text_secondary"],
            font=ctk.CTkFont(size=17, weight="normal"),
        )
        self._subtitle_label.grid(row=1, column=0, padx=56, pady=(16, 32))

        # ── Primary Actions Section ─────────────────────────────────────────
        actions_frame = ctk.CTkFrame(card, fg_color="transparent")
        actions_frame.grid(row=2, column=0, sticky="ew", padx=56)
        actions_frame.grid_columnconfigure(0, weight=1)

        # Primary scan buttons with icons
        button_config = {
            "height": 54,
            "corner_radius": 16,
            "font": ctk.CTkFont(size=17, weight="bold"),
            "fg_color": self._tokens["accent_primary"],
            "hover_color": self._tokens["accent_secondary"],
            "text_color": ("#FFFFFF", "#0A0E14"),
        }

        self._btn_photos = ctk.CTkButton(
            actions_frame,
            text="📷  Scan Photos",
            command=self._on_scan_photos,
            **button_config,
        )
        self._btn_photos.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        self._btn_videos = ctk.CTkButton(
            actions_frame,
            text="🎬  Scan Videos",
            command=self._on_scan_videos,
            **button_config,
        )
        self._btn_videos.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        self._btn_files = ctk.CTkButton(
            actions_frame,
            text="📁  Scan Files",
            command=self._on_scan_files,
            **button_config,
        )
        self._btn_files.grid(row=2, column=0, sticky="ew", pady=(0, 24))

        # ── Divider ─────────────────────────────────────────────────────────
        divider_frame = ctk.CTkFrame(card, fg_color="transparent")
        divider_frame.grid(row=3, column=0, sticky="ew", padx=56, pady=(0, 24))
        divider_frame.grid_columnconfigure((0, 2), weight=1)

        ctk.CTkFrame(
            divider_frame,
            height=1,
            fg_color=self._tokens["border_subtle"],
        ).grid(row=0, column=0, sticky="ew", pady=8)

        ctk.CTkLabel(
            divider_frame,
            text="or",
            font=ctk.CTkFont(size=13),
            text_color=self._tokens["text_muted"],
        ).grid(row=0, column=1, padx=16)

        ctk.CTkFrame(
            divider_frame,
            height=1,
            fg_color=self._tokens["border_subtle"],
        ).grid(row=0, column=2, sticky="ew", pady=8)

        # ── Secondary Actions Section ───────────────────────────────────────
        secondary = ctk.CTkFrame(card, fg_color="transparent")
        secondary.grid(row=4, column=0, sticky="ew", padx=56, pady=(0, 44))
        secondary.grid_columnconfigure((0, 1), weight=1)

        secondary_config = {
            "height": 44,
            "corner_radius": 12,
            "font": ctk.CTkFont(size=14, weight="normal"),
            "fg_color": self._tokens["bg_elevated"],
            "text_color": self._tokens["text_secondary"],
            "border_width": 1,
            "border_color": self._tokens["border_subtle"],
        }

        self._btn_resume = ctk.CTkButton(
            secondary,
            text="↻  Resume scan",
            command=self._on_resume_scan,
            **secondary_config,
        )
        self._btn_resume.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self._btn_last_review = ctk.CTkButton(
            secondary,
            text="↗  Open last review",
            command=self._on_open_last_review,
            **secondary_config,
        )
        self._btn_last_review.grid(row=0, column=1, padx=(8, 0), sticky="ew")
