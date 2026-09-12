"""
CustomTkinter Review page — redesigned.

Two-row layout (header + body), body is three fixed columns:
- left: scrollable groups with thumbnail cards
- center: large inline side-by-side image comparison
- right: keep / compare selectors and actions
Execution summary and details sit below the three columns (full width).

All image loading is async — no main-thread blocking.
Columns are always in the grid — empty state is an overlay, no grid toggling.
"""

from __future__ import annotations

import logging
import threading
import tkinter
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import customtkinter as ctk

from ...engine.media_types import is_image_extension
from ...engine.models import DeletionResult, ScanResult
from ...engine.thumbnails import generate_thumbnails_async, get_thumbnail_path
from ..state.store import ReviewIndexState, ReviewPlanState, ReviewPreviewState, ReviewSelectionState
from ..utils.formatting import fmt_bytes
from ..utils.review_keep import coerce_keep_selections, default_keep_map_from_result
from ..utils.theme_helpers import theme_pair
from .design_tokens import get_theme_colors, resolve_border_token

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..controller.review_controller import ReviewController
    from ..state.store import UIStateStore

_COMPARE_EMPTY = "\u2014"

_GROUP_THUMB_SIZE = (48, 48)


class ReviewPageCTK(ctk.CTkFrame):
    """CTK review page: groups | comparison | actions."""

    _HERO_MIN = 280
    _HERO_MAX = 900
    _MIDDLE_SELECTION_THRESHOLD = 1000

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def _ui_alive(self) -> bool:
        """False after destroy — avoids configuring widgets from stale callbacks."""
        try:
            return bool(self.winfo_exists())
        except (tkinter.TclError, RuntimeError):
            return False

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(
        self,
        parent,
        *,
        on_execute: Optional[Callable[[dict[str, str]], DeletionResult | None]] = None,
        store: Optional["UIStateStore"] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_execute = on_execute
        self._store = store
        self._review_controller: Optional["ReviewController"] = None
        self._result: ScanResult | None = None
        self._group_map: dict[str, object] = {}
        self._keep_map: dict[str, str] = {}

        # Tk variables
        self._group_var = ctk.StringVar(value="")
        self._keep_var = ctk.StringVar(value="")
        self._compare_var = ctk.StringVar(value="")
        self._summary_var = ctk.StringVar(value="No scan loaded")

        # Callbacks / controller
        self._refresh_callback: Callable[[], None] = lambda: None
        self._compare_path: str | None = None

        # Image refs — prevent garbage collection
        self._ctk_image_refs: list[ctk.CTkImage] = []
        self._group_thumb_refs: dict[str, ctk.CTkImage] = {}
        self._group_thumb_labels: dict[str, ctk.CTkLabel] = {}

        # Async thumbnail cancellation
        self._thumb_cancel_event: threading.Event | None = None

        # Hero sizing
        self._hero_pixel_size = 480
        self._resize_after_id: str | None = None

        # Group row tracking
        self._group_row_frames: dict[str, ctk.CTkFrame] = {}
        self._keep_label_to_path: dict[str, str] = {}
        self._compare_label_to_path: dict[str, str] = {}

        # Theme tokens
        self._tokens = get_theme_colors()

        # Grid: 4 rows (header, body, result, details), 3 columns
        self.grid_columnconfigure(0, weight=0, minsize=200)
        self.grid_columnconfigure(1, weight=1, minsize=360)
        self.grid_columnconfigure(2, weight=0, minsize=280)
        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(3, weight=1)
        self._build()

    # ------------------------------------------------------------------
    # Build layout (called once)
    # ------------------------------------------------------------------

    def _build(self) -> None:
        tk = self._tokens

        # ── Row 0: Header ──
        top = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        top.grid(row=0, column=0, columnspan=3, sticky="ew", padx=20, pady=(20, 12))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top,
            text="Review",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=tk["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(top, textvariable=self._summary_var, text_color=tk["text_secondary"]).grid(
            row=1,
            column=0,
            sticky="w",
            padx=16,
            pady=(0, 12),
        )

        # ── Column 0: Group navigator ──
        self._review_left = ctk.CTkFrame(
            self,
            corner_radius=16,
            width=220,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        left = self._review_left
        left.grid(row=1, column=0, sticky="nsew", padx=(20, 8), pady=(0, 12))
        left.grid_rowconfigure(1, weight=1)
        left.grid_propagate(False)
        ctk.CTkLabel(
            left,
            text="Groups",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=tk["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))
        self._group_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._group_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))

        # ── Column 1: Comparison viewport ──
        self._review_center = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        center = self._review_center
        center.grid(row=1, column=1, sticky="nsew", padx=8, pady=(0, 12))
        center.grid_columnconfigure(0, weight=1)
        center.grid_columnconfigure(1, weight=1)
        center.grid_rowconfigure(1, weight=1)

        # Per-pane labels replace the old single centered "File preview" title.
        self._pane_label_a = ctk.CTkLabel(
            center,
            text="A — ORIGINAL",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=tk["text_secondary"],
            anchor="center",
        )
        self._pane_label_a.grid(row=0, column=0, padx=16, pady=(12, 4), sticky="ew")
        self._pane_label_b = ctk.CTkLabel(
            center,
            text="B — DUPLICATE",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=tk["text_secondary"],
            anchor="center",
        )
        self._pane_label_b.grid(row=0, column=1, padx=16, pady=(12, 4), sticky="ew")

        self._hero_viewport = ctk.CTkFrame(center, fg_color="transparent")
        self._hero_viewport.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=4)
        self._hero_viewport.grid_columnconfigure(0, weight=1)
        self._hero_viewport.grid_columnconfigure(1, weight=0, minsize=1)  # divider column
        self._hero_viewport.grid_columnconfigure(2, weight=1)
        self._hero_viewport.grid_rowconfigure(0, weight=1)
        self._hero_viewport.bind("<Configure>", self._on_hero_viewport_configure)

        self._hero_divider = ctk.CTkFrame(self._hero_viewport, width=1, fg_color=tk["border_subtle"])
        self._hero_divider.grid(row=0, column=1, sticky="ns", padx=4, pady=16)

        self._hero_left_label = ctk.CTkLabel(self._hero_viewport, text="Keep preview")
        self._hero_left_label.grid(row=0, column=0, padx=12, pady=8, sticky="nsew")
        self._hero_left_caption = ctk.StringVar(value="")
        ctk.CTkLabel(center, textvariable=self._hero_left_caption, text_color=tk["text_secondary"]).grid(
            row=2,
            column=0,
            padx=16,
            pady=(6, 14),
        )

        self._hero_right_label = ctk.CTkLabel(self._hero_viewport, text="Compare preview")
        self._hero_right_label.grid(row=0, column=2, padx=12, pady=8, sticky="nsew")
        self._hero_right_caption = ctk.StringVar(value="")
        ctk.CTkLabel(center, textvariable=self._hero_right_caption, text_color=tk["text_secondary"]).grid(
            row=2,
            column=1,
            padx=16,
            pady=(6, 14),
        )

        # ── Column 2: Actions ──
        self._review_right = ctk.CTkFrame(
            self,
            corner_radius=16,
            width=300,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        right = self._review_right
        right.grid(row=1, column=2, sticky="nsew", padx=(8, 20), pady=(0, 12))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(right, text="Keep file", text_color=tk["text_secondary"]).grid(
            row=0,
            column=0,
            sticky="w",
            padx=16,
            pady=(16, 6),
        )
        self._keep_menu = ctk.CTkOptionMenu(
            right,
            variable=self._keep_var,
            values=[""],
            command=self._on_keep_change,
        )
        self._keep_menu.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

        ctk.CTkLabel(right, text="Compare file", text_color=tk["text_secondary"]).grid(
            row=2,
            column=0,
            sticky="w",
            padx=16,
            pady=(4, 6),
        )
        self._compare_menu = ctk.CTkOptionMenu(
            right,
            variable=self._compare_var,
            values=[_COMPARE_EMPTY],
            command=self._on_compare_menu_change,
        )
        self._compare_menu.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))

        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._execute_btn = ctk.CTkButton(
            btn_row,
            text="Move to Trash",
            fg_color=tk["danger"],
            hover_color=tk["danger_hover"],
            text_color=("#FFFFFF", "#0A0E14"),
            command=self._execute,
        )
        self._execute_btn.pack(side="left", padx=(0, 8))
        self._refresh_btn = ctk.CTkButton(
            btn_row,
            text="Refresh Last Scan",
            fg_color=tk["bg_elevated"],
            hover_color=tk["bg_overlay"],
            text_color=tk["text_secondary"],
            border_width=1,
            border_color=tk["border_subtle"],
            command=self._refresh_callback,
        )
        self._refresh_btn.pack(side="left")

        ctk.CTkFrame(right, fg_color="transparent").grid(row=5, column=0, sticky="nsew")

        # ── Row 2: Result panel (hidden) ──
        self._result_panel = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._result_panel.grid_columnconfigure(0, weight=1)
        self._result_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            self._result_panel,
            text="Execution Result",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=tk["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 6))
        ctk.CTkLabel(
            self._result_panel,
            textvariable=self._result_var,
            text_color=tk["text_secondary"],
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

        # ── Row 3: Details textbox ──
        self._details = ctk.CTkTextbox(
            self,
            wrap="word",
            corner_radius=12,
            fg_color=tk["bg_surface"],
            text_color=tk["text_secondary"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._details.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=20, pady=(0, 20))
        self._details.insert("end", "Load a scan result to review duplicate groups.\n")
        self._details.configure(state="disabled")

        # ── Empty-state overlay (placed over center, not grid-toggled) ──
        self._review_empty = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._review_empty.grid_columnconfigure(0, weight=1)
        self._review_empty.grid_rowconfigure(0, weight=1)
        empty_inner = ctk.CTkFrame(self._review_empty, fg_color="transparent")
        empty_inner.grid(row=0, column=0, sticky="nsew", padx=40, pady=48)
        ctk.CTkLabel(
            empty_inner,
            text="No scan to review",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=tk["text_primary"],
        ).pack(pady=(0, 8))
        ctk.CTkLabel(
            empty_inner,
            text="Run a scan from Home or Scan, open a result from History,\nor refresh if you already completed a scan in this session.",
            font=ctk.CTkFont(size=14),
            text_color=tk["text_secondary"],
            wraplength=520,
            justify="center",
        ).pack(pady=(12, 0))

        self._themed_sections = [top, left, center, right, self._result_panel, self._review_empty]

        # Row style presets
        self._group_row_normal = "transparent"
        # Surface-2 (bg_elevated) for hover; surface-3 (bg_overlay) for selected — proper elevation stack.
        self._group_row_hover = self._tokens.get("bg_elevated") or self._tokens["bg_elevated"]
        self._group_row_selected = self._tokens.get("bg_overlay") or self._tokens["bg_elevated"]
        self._group_row_accent_bars: dict[str, ctk.CTkFrame] = {}

        # Start in empty state; hide result panel
        self._result_panel.grid_remove()
        self._layout_review_empty(True)

    # ------------------------------------------------------------------
    # Empty-state overlay (no grid toggling — just place/place_forget)
    # ------------------------------------------------------------------

    def _layout_review_empty(self, show: bool) -> None:
        """Toggle full-page empty state overlay without removing columns from grid."""
        if not hasattr(self, "_review_empty"):
            return
        if show:
            # Place overlay spanning all three columns in row 1
            self._review_empty.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=20, pady=(0, 12))
            self._review_empty.lift()
        else:
            self._review_empty.grid_remove()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def apply_theme_tokens(self, tokens: dict) -> None:
        panel = str(tokens.get("bg_panel", "#161b22"))
        surf = str(tokens.get("bg_surface", str(tokens.get("bg_elevated", "#21262d"))))
        elev = str(tokens.get("bg_elevated", "#21262d"))
        br = resolve_border_token(tokens)
        txt = str(tokens.get("text_secondary", "#94A3B8"))

        self.configure(fg_color=panel)
        if hasattr(self, "_scroll"):
            base = str(tokens.get("bg_base", "#0f131c"))
            self._scroll.configure(fg_color=surf, label_fg_color=base)

        for f in self._themed_sections:
            f.configure(fg_color=panel, border_color=br)

        self._execute_btn.configure(
            fg_color=str(tokens.get("danger", "#E53E3E")),
            hover_color=str(tokens.get("danger_hover", "#9B2C2C")),
        )
        _pane_muted = str(tokens.get("text_secondary", "#94A3B8"))
        for _pl in (getattr(self, "_pane_label_a", None), getattr(self, "_pane_label_b", None)):
            if _pl is not None:
                _pl.configure(text_color=_pane_muted)
        if hasattr(self, "_hero_divider"):
            self._hero_divider.configure(fg_color=resolve_border_token(tokens))
        self._refresh_btn.configure(fg_color=elev, border_color=br)
        self._details.configure(fg_color=surf, text_color=txt, border_color=br)

        # Surface-2 for hover, surface-3 (bg_overlay) for selected — matches elevation system.
        self._group_row_hover = theme_pair(tokens.get("bg_elevated"), self._tokens.get("bg_elevated") or self._tokens["bg_overlay"])
        _overlay = tokens.get("bg_overlay") or tokens.get("bg_elevated")
        self._group_row_selected = theme_pair(_overlay, self._tokens.get("bg_overlay") or self._tokens.get("bg_elevated"))
        # Live-update accent bars to follow the new accent_primary token
        _acc = str(tokens.get("accent_primary") or "#58a6ff")
        for _bar in self._group_row_accent_bars.values():
            try:
                _bar.configure(fg_color=_acc)
            except Exception:
                pass
        cur = self._group_var.get()
        if cur and cur in self._group_row_frames:
            self._highlight_group_row(cur)

    # The rest of the file is truncated for this call; full content is in the local file. This is incomplete.
