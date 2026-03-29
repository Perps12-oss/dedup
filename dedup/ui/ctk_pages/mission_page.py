"""
CustomTkinter Mission page (experimental).

First migrated page for the CTK backend. This intentionally mirrors the
high-level intent of the ttk Mission page without full feature parity yet.

REFACTORED: Visual redesign with modern aesthetics while preserving all APIs.
- Card-based layout with subtle depth
- Enhanced metric cards with visual hierarchy
- Improved typography and spacing
- Status indicators with semantic colors
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Any, Callable, Optional

import customtkinter as ctk

from ..ctk_action_contracts import ScanStartPayload
from ..utils.formatting import fmt_bytes, fmt_int
from .design_tokens import get_theme_colors, resolve_border_token
from .ui_utils import safe_callback

if TYPE_CHECKING:
    from ..state.store import UIStateStore


def _quick_scan_options() -> dict:
    """Same defaults as Scan page for files / all-media preset."""
    return {"media_category": "all", "scan_mode": "deep", "include_hidden": False, "scan_subfolders": True}


def _format_session_date(started_at: str) -> str:
    raw = (started_at or "").strip()
    if not raw:
        return "—"
    try:
        if "T" in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, OSError):
        pass
    return raw[:19] if len(raw) > 19 else raw


class MissionPageCTK(ctk.CTkFrame):
    """Mission landing surface for CTK backend."""

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API - UNCHANGED
    # ══════════════════════════════════════════════════════════════════════════

    def __init__(
        self,
        parent,
        *,
        on_start_scan: Callable[[], None],
        on_resume_scan: Callable[[], None],
        on_open_last_review: Callable[[], None],
        on_quick_scan: Callable[[ScanStartPayload], None],
        on_open_scan: Callable[[str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)

        # Callbacks - UNCHANGED
        self._on_start_scan = on_start_scan
        self._on_resume_scan = on_resume_scan
        self._on_open_last_review = on_open_last_review
        self._on_quick_scan = on_quick_scan
        self._on_open_scan = on_open_scan

        # State variables - UNCHANGED
        self._quick_path_var = ctk.StringVar(value="")
        self._last_files_var = ctk.StringVar(value="—")
        self._last_groups_var = ctk.StringVar(value="—")
        self._last_reclaim_var = ctk.StringVar(value="—")
        self._resume_status_var = ctk.StringVar(value="—")
        self._recent_var = ctk.StringVar(value="No recent sessions yet.")
        self._unsub_store: Optional[Callable[[], None]] = None

        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._tokens = get_theme_colors()

        self._build()

    def set_last_scan_snapshot(self, *, files: str, groups: str, reclaim: str) -> None:
        """Set last scan metrics. API UNCHANGED."""
        self._last_files_var.set(files)
        self._last_groups_var.set(groups)
        self._last_reclaim_var.set(reclaim)

    def set_resume_hint(self, text: str) -> None:
        """Set resume status hint. API UNCHANGED."""
        self._resume_status_var.set(text)

    def attach_store(self, store: "UIStateStore") -> None:
        """Sync Mission summary from coordinator-derived MissionState. API UNCHANGED."""
        if self._unsub_store:
            safe_callback(self._unsub_store, context="attach_store unsub")
            self._unsub_store = None

        def on_state(state) -> None:
            m = getattr(state, "mission", None)
            if m is None:
                return
            ls = getattr(m, "last_scan", None)
            if ls is not None:
                self.set_last_scan_snapshot(
                    files=fmt_int(getattr(ls, "files_scanned", 0) or 0),
                    groups=fmt_int(getattr(ls, "duplicate_groups", 0) or 0),
                    reclaim=fmt_bytes(getattr(ls, "reclaimable_bytes", 0) or 0),
                )
            else:
                self.set_last_scan_snapshot(files="—", groups="—", reclaim="—")
            res_ids = getattr(m, "resumable_scan_ids", ()) or ()
            n_res = len(res_ids)
            self.set_resume_hint("None" if n_res == 0 else f"{n_res} session(s)")
            sessions = list(getattr(m, "recent_sessions", ()) or ())
            self._render_recent_sessions(sessions)

        self._unsub_store = store.subscribe(on_state, fire_immediately=True)

    def detach_store(self) -> None:
        """Detach from store subscription. API UNCHANGED."""
        if self._unsub_store:
            safe_callback(self._unsub_store, context="detach_store unsub")
            self._unsub_store = None

    def set_recent_sessions_text(self, text: str) -> None:
        """Legacy: retained for API compatibility; recent list is card-based."""
        self._recent_var.set(text)

    def _render_recent_sessions(self, sessions: list[dict[str, Any]]) -> None:
        """Fill recent sessions with clickable rows."""
        if not hasattr(self, "_recent_list_host"):
            return
        for w in self._recent_list_host.winfo_children():
            w.destroy()
        tk = self._tokens
        if not sessions:
            empty = ctk.CTkFrame(self._recent_list_host, fg_color="transparent")
            empty.pack(fill="x", pady=(4, 12))
            ctk.CTkLabel(empty, text="📭", font=ctk.CTkFont(size=36)).pack(pady=(8, 4))
            ctk.CTkLabel(
                empty,
                text="No recent scans yet",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=tk["text_primary"],
            ).pack()
            ctk.CTkLabel(
                empty,
                text="When you finish a scan, it appears here with date, folder, and a shortcut to open results in Review.",
                text_color=tk["text_muted"],
                font=ctk.CTkFont(size=13),
                wraplength=520,
                justify="center",
            ).pack(pady=(8, 4))
            ctk.CTkLabel(
                empty,
                text="Start from Home or Scan, or browse History for older runs.",
                text_color=tk["text_secondary"],
                font=ctk.CTkFont(size=12),
                wraplength=520,
                justify="center",
            ).pack(pady=(0, 12))
            return
        for d in sessions[:8]:
            sid = str(d.get("scan_id", "") or "")
            roots = d.get("roots") or []
            folder = str(roots[0]) if roots else "—"
            if len(folder) > 72:
                folder = folder[:34] + "…" + folder[-34:]
            dupes = int(d.get("duplicates_found") or 0)
            files_n = int(d.get("files_scanned") or 0)
            when = _format_session_date(str(d.get("started_at", "") or ""))

            row = ctk.CTkFrame(
                self._recent_list_host,
                corner_radius=10,
                fg_color=tk["bg_elevated"],
                border_width=1,
                border_color=tk["border_subtle"],
            )
            row.pack(fill="x", pady=6)
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", padx=10, pady=10)
            left = ctk.CTkFrame(inner, fg_color="transparent")
            left.pack(side="left", fill="both", expand=True)

            ctk.CTkLabel(
                left,
                text=when,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=tk["text_primary"],
                anchor="w",
            ).pack(anchor="w")
            ctk.CTkLabel(
                left,
                text=folder,
                font=ctk.CTkFont(size=12),
                text_color=tk["text_secondary"],
                anchor="w",
                wraplength=480,
                justify="left",
            ).pack(anchor="w", pady=(4, 0))
            ctk.CTkLabel(
                left,
                text=f"{fmt_int(files_n)} files scanned · {fmt_int(dupes)} duplicate groups",
                font=ctk.CTkFont(size=11),
                text_color=tk["text_muted"],
                anchor="w",
            ).pack(anchor="w", pady=(4, 0))

            if sid and self._on_open_scan:
                ctk.CTkButton(
                    inner,
                    text="Open in Review",
                    width=130,
                    height=32,
                    corner_radius=8,
                    fg_color=tk["accent_primary"],
                    hover_color=tk["accent_secondary"],
                    text_color=("#FFFFFF", "#0A0E14"),
                    command=lambda s=sid: self._on_open_scan(s),
                ).pack(side="right", padx=(8, 0))

    def apply_theme_tokens(self, tokens: dict) -> None:
        """Apply theme tokens to styled components. API UNCHANGED."""
        panel = str(tokens.get("bg_panel", "#1C2128"))
        elev = str(tokens.get("bg_elevated", "#161B22"))
        acc = str(tokens.get("accent_primary", "#22D3EE"))
        border = resolve_border_token(tokens)

        for f in self._themed_sections:
            f.configure(fg_color=panel, border_color=border)
        for f in self._metric_cards:
            f.configure(fg_color=elev, border_color=border)

        self._cta_start.configure(fg_color=acc)
        self._cta_resume.configure(fg_color=acc)
        self._cta_review.configure(fg_color=elev)
        self._quick_start_btn.configure(fg_color=acc)

        txt_sec = str(tokens.get("text_secondary", "#94A3B8"))
        if hasattr(self, "_recent_list_host"):
            self._recent_list_host.configure(fg_color="transparent")
        if hasattr(self, "_quick_path_entry"):
            self._quick_path_entry.configure(fg_color=elev, border_color=border)
        if hasattr(self, "_quick_browse_btn"):
            self._quick_browse_btn.configure(fg_color=elev, border_color=border, text_color=txt_sec)

    # ══════════════════════════════════════════════════════════════════════════
    # PRIVATE IMPLEMENTATION - VISUAL REFACTOR
    # ══════════════════════════════════════════════════════════════════════════

    def _build(self) -> None:
        """Build Mission page with enhanced visuals."""
        self._themed_sections: list[ctk.CTkFrame] = []
        self._metric_cards: list[ctk.CTkFrame] = []

        # Scrollable container for responsive layout
        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
        )
        scroll.grid(row=0, column=0, rowspan=4, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1)

        # ── Hero Section ────────────────────────────────────────────────────
        hero = ctk.CTkFrame(
            scroll,
            corner_radius=16,
            fg_color=self._tokens["bg_panel"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._themed_sections.append(hero)
        hero.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 16))
        hero.grid_columnconfigure(0, weight=1)

        # Hero header with icon
        header_row = ctk.CTkFrame(hero, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 0))

        ctk.CTkLabel(
            header_row,
            text="🎯",
            font=ctk.CTkFont(size=32),
        ).pack(side="left", padx=(0, 12))

        title_frame = ctk.CTkFrame(header_row, fg_color="transparent")
        title_frame.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            title_frame,
            text="Home",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_frame,
            text="Start a scan, resume interrupted work, or open your last review.",
            font=ctk.CTkFont(size=14),
            text_color=self._tokens["text_secondary"],
        ).pack(anchor="w", pady=(4, 0))

        # CTA buttons row
        cta = ctk.CTkFrame(hero, fg_color="transparent")
        cta.grid(row=1, column=0, sticky="w", padx=24, pady=(20, 24))

        cta_primary_config = {
            "width": 180,
            "height": 44,
            "corner_radius": 12,
            "font": ctk.CTkFont(size=14, weight="bold"),
            "fg_color": self._tokens["accent_primary"],
            "text_color": ("#FFFFFF", "#0A0E14"),
        }

        self._cta_start = ctk.CTkButton(
            cta,
            text="▶  Start New Scan",
            command=self._on_start_scan,
            **cta_primary_config,
        )
        self._cta_start.pack(side="left", padx=(0, 12))

        self._cta_resume = ctk.CTkButton(
            cta,
            text="↻  Resume Interrupted",
            command=self._on_resume_scan,
            **cta_primary_config,
        )
        self._cta_resume.pack(side="left", padx=(0, 12))

        self._cta_review = ctk.CTkButton(
            cta,
            text="📊  Open Last Review",
            width=180,
            height=44,
            corner_radius=12,
            font=ctk.CTkFont(size=14, weight="normal"),
            fg_color=self._tokens["bg_elevated"],
            text_color=self._tokens["text_secondary"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
            command=self._on_open_last_review,
        )
        self._cta_review.pack(side="left")

        # ── Metrics Row ─────────────────────────────────────────────────────
        metrics_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        metrics_frame.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 16))
        metrics_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="metric")

        self._metric_card(
            metrics_frame,
            col=0,
            icon="⚙️",
            title="Engine Status",
            rows=[
                ("Health", "Healthy", "success"),
                ("Pipeline", "Durable", "info"),
                ("Resume", self._resume_status_var, None),
            ],
        )

        self._metric_card(
            metrics_frame,
            col=1,
            icon="📈",
            title="Last Scan",
            rows=[
                ("Files", self._last_files_var, None),
                ("Groups", self._last_groups_var, None),
                ("Reclaimable", self._last_reclaim_var, "warning"),
            ],
        )

        self._metric_card(
            metrics_frame,
            col=2,
            icon="🛡️",
            title="Trash Protection",
            rows=[
                ("Status", "Active", "success"),
                ("Revalidation", "Enabled", "success"),
                ("Audit", "Enabled", "success"),
            ],
        )

        # ── Recent Sessions Section ─────────────────────────────────────────
        recent = ctk.CTkFrame(
            scroll,
            corner_radius=16,
            fg_color=self._tokens["bg_panel"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._themed_sections.append(recent)
        recent.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))
        recent.grid_columnconfigure(0, weight=1)

        # Section header
        recent_header = ctk.CTkFrame(recent, fg_color="transparent")
        recent_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))

        ctk.CTkLabel(
            recent_header,
            text="📋  Recent scans",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(side="left")

        self._recent_list_host = ctk.CTkScrollableFrame(
            recent,
            fg_color="transparent",
            height=220,
        )
        self._recent_list_host.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 16))
        self._recent_list_host.grid_columnconfigure(0, weight=1)

        # ── Quick Scan Section ──────────────────────────────────────────────
        quick = ctk.CTkFrame(
            scroll,
            corner_radius=16,
            fg_color=self._tokens["bg_panel"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._themed_sections.append(quick)
        quick.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 24))
        quick.grid_columnconfigure(0, weight=1)

        # Section header
        quick_header = ctk.CTkFrame(quick, fg_color="transparent")
        quick_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 8))

        ctk.CTkLabel(
            quick_header,
            text="⚡  Quick Scan",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(side="left")

        ctk.CTkLabel(
            quick,
            text="All-files preset with standard options. For custom settings, use the Scan page.",
            font=ctk.CTkFont(size=13),
            text_color=self._tokens["text_muted"],
            wraplength=640,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 16))

        # Path input
        path_frame = ctk.CTkFrame(quick, fg_color="transparent")
        path_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        path_frame.grid_columnconfigure(0, weight=1)

        self._quick_path_entry = ctk.CTkEntry(
            path_frame,
            textvariable=self._quick_path_var,
            placeholder_text="Select a folder to scan…",
            height=44,
            corner_radius=10,
            font=ctk.CTkFont(size=14),
            fg_color=self._tokens["bg_elevated"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._quick_path_entry.grid(row=0, column=0, sticky="ew")

        # Action buttons
        qb = ctk.CTkFrame(quick, fg_color="transparent")
        qb.grid(row=3, column=0, sticky="w", padx=20, pady=(0, 20))

        self._quick_browse_btn = ctk.CTkButton(
            qb,
            text="📂  Browse…",
            width=130,
            height=40,
            corner_radius=10,
            font=ctk.CTkFont(size=13),
            fg_color=self._tokens["bg_elevated"],
            text_color=self._tokens["text_secondary"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
            command=self._quick_browse,
        )
        self._quick_browse_btn.pack(side="left", padx=(0, 12))

        self._quick_start_btn = ctk.CTkButton(
            qb,
            text="⚡  Start Quick Scan",
            width=170,
            height=40,
            corner_radius=10,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=self._tokens["accent_primary"],
            text_color=("#FFFFFF", "#0A0E14"),
            command=self._quick_start,
        )
        self._quick_start_btn.pack(side="left")

    def _metric_card(
        self,
        parent: ctk.CTkFrame,
        col: int,
        icon: str,
        title: str,
        rows: list[tuple[str, str | ctk.StringVar, str | None]],
    ) -> None:
        """Build a metric card with status indicators."""
        card = ctk.CTkFrame(
            parent,
            corner_radius=14,
            fg_color=self._tokens["bg_elevated"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._metric_cards.append(card)
        card.grid(row=0, column=col, sticky="ew", padx=8, pady=0)
        card.grid_columnconfigure(0, weight=1)

        # Card header
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 12))

        ctk.CTkLabel(
            header,
            text=f"{icon}  {title}",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(anchor="w")

        # Metric rows
        for key, value, status_type in rows:
            row_frame = ctk.CTkFrame(card, fg_color="transparent")
            row_frame.pack(fill="x", padx=16, pady=3)

            ctk.CTkLabel(
                row_frame,
                text=key,
                font=ctk.CTkFont(size=13),
                text_color=self._tokens["text_muted"],
            ).pack(side="left")

            # Determine value color based on status
            if status_type == "success":
                value_color = self._tokens["success"]
            elif status_type == "warning":
                value_color = self._tokens["warning"]
            elif status_type == "info":
                value_color = self._tokens["accent_primary"]
            else:
                value_color = self._tokens["text_primary"]

            if isinstance(value, ctk.StringVar):
                ctk.CTkLabel(
                    row_frame,
                    textvariable=value,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=value_color,
                ).pack(side="right")
            else:
                ctk.CTkLabel(
                    row_frame,
                    text=value,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=value_color,
                ).pack(side="right")

        # Bottom padding
        ctk.CTkFrame(card, height=12, fg_color="transparent").pack()

    def _quick_browse(self) -> None:
        """Open folder selection dialog. Logic UNCHANGED."""
        path = filedialog.askdirectory(title="Select Folder for Quick Scan")
        if path:
            self._quick_path_var.set(str(Path(path).resolve()))

    def _quick_start(self) -> None:
        """Start quick scan with selected folder. Logic UNCHANGED."""
        raw = self._quick_path_var.get().strip()
        if not raw:
            messagebox.showwarning("Quick Scan", "Choose a folder first.", parent=self.winfo_toplevel())
            return
        payload: ScanStartPayload = {
            "mode": "files",
            "path": raw,
            "options": _quick_scan_options(),
            "keep_policy": "newest",
            "post_scan_route": "review",
        }
        self._on_quick_scan(payload)
