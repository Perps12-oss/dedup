"""
CustomTkinter History page — trustworthy daily driver.

Features:
- Summary stats bar (total scans, avg duration, avg reclaimable)
- Filterable session list with search
- Resumable scan clarity
- Session detail panel
- Export functionality
- Load/Resume/Delete actions

REFACTORED: Visual redesign with modern aesthetics while preserving all APIs.
- Enhanced summary cards with status indicators
- Modern table rows with improved visual hierarchy
- Better filter controls with visual feedback
- Enhanced detail panel with icons
- Consistent design token usage
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable, Optional

import customtkinter as ctk

from ..utils.formatting import fmt_bytes, fmt_duration, fmt_int
from .design_tokens import get_theme_colors, resolve_border_token
from .ui_utils import cancel_after


class HistoryPageCTK(ctk.CTkFrame):
    """Scan history page with full P1 functionality."""

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API - PRESERVED FROM ORIGINAL
    # ══════════════════════════════════════════════════════════════════════════

    def __init__(
        self,
        parent,
        *,
        get_history: Callable[[], list[dict[str, Any]]],
        on_load_scan: Callable[[str], None],
        on_resume_scan: Optional[Callable[[str], None]] = None,
        get_resumable_ids: Optional[Callable[[], list[str]]] = None,
        on_delete_scan: Optional[Callable[[str], bool]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._get_history = get_history
        self._on_load_scan = on_load_scan
        self._on_resume_scan = on_resume_scan
        self._get_resumable_ids = get_resumable_ids or (lambda: [])
        self._on_delete_scan = on_delete_scan
        self._selected_scan_id: Optional[str] = None
        self._scan_data: list[dict[str, Any]] = []
        self._filtered_data: list[dict[str, Any]] = []

        # Filter state
        self._show_resumable_only = ctk.BooleanVar(value=False)
        self._show_failed_only = ctk.BooleanVar(value=False)
        self._search_text = ctk.StringVar(value="")

        self._stat_cards: list[ctk.CTkFrame] = []
        self._search_timer_id: str | int | None = None

        self._tokens = get_theme_colors()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build()

    def apply_theme_tokens(self, tokens: dict) -> None:
        """Apply theme tokens to the page. API UNCHANGED."""
        panel = str(tokens.get("bg_panel", "#161b22"))
        elev = str(tokens.get("bg_elevated", "#21262d"))
        acc = str(tokens.get("accent_primary", "#3B8ED0"))
        br = resolve_border_token(tokens)
        for name in ("_summary_frame", "_table_section", "_detail_frame"):
            fr = getattr(self, name, None)
            if fr is not None:
                fr.configure(fg_color=panel, border_color=br)
        for c in getattr(self, "_stat_cards", []):
            c.configure(fg_color=elev, border_color=br)
        if hasattr(self, "_load_btn"):
            self._load_btn.configure(fg_color=acc)
        if hasattr(self, "_resume_btn"):
            self._resume_btn.configure(fg_color=acc)
        if hasattr(self, "_export_btn"):
            self._export_btn.configure(fg_color=elev)

    def reload(self) -> None:
        """Reload history data and refresh UI. API UNCHANGED."""
        self._scan_data = self._get_history()
        self._apply_filters()
        self._update_summary()

    # ══════════════════════════════════════════════════════════════════════════
    # PRIVATE UI BUILD METHODS - REFACTORED FOR VISUAL ENHANCEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def _build(self) -> None:
        # Configure base styling
        self.configure(fg_color=self._tokens["bg_base"])

        # Header
        self._build_header()

        # Summary stats bar
        self._build_summary()

        # Filters and table
        self._build_table_section()

        # Session detail panel
        self._build_detail_panel()

        # Load initial data
        self.reload()

    def _build_header(self) -> None:
        """Build the page header with title and refresh button."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 16))
        header.grid_columnconfigure(0, weight=1)

        # Title section
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_frame,
            text="📜  Scan History",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(side="left")

        # Subtitle
        ctk.CTkLabel(
            header,
            text="Saved scans from this device. Select a session to view details or load into Review.",
            font=ctk.CTkFont(size=13),
            text_color=self._tokens["text_secondary"],
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        # Accent underline
        accent_line = ctk.CTkFrame(
            header,
            height=3,
            width=80,
            fg_color=self._tokens["accent_primary"],
            corner_radius=2,
        )
        accent_line.grid(row=2, column=0, sticky="w", pady=(12, 0))

        # Refresh button
        ctk.CTkButton(
            header,
            text="↻ Refresh",
            width=100,
            height=36,
            corner_radius=10,
            fg_color=self._tokens["accent_primary"],
            hover_color=self._tokens["accent_secondary"],
            font=ctk.CTkFont(size=13),
            command=self.reload,
        ).grid(row=0, column=1, rowspan=2, sticky="ne")

    def _build_summary(self) -> None:
        """Build the summary statistics bar."""
        summary = ctk.CTkFrame(
            self,
            fg_color=self._tokens["bg_panel"],
            corner_radius=16,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._summary_frame = summary
        summary.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 16))
        summary.grid_columnconfigure(0, weight=1)

        # Summary cards container
        cards = ctk.CTkFrame(summary, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        cards.grid_columnconfigure(0, weight=1)
        cards.grid_columnconfigure(1, weight=1)
        cards.grid_columnconfigure(2, weight=1)

        # Total scans card
        total_card = self._create_stat_card(
            cards, 0, "📊", "Total Scans", "0"
        )
        self._total_label = total_card["value_label"]

        # Avg duration card
        dur_card = self._create_stat_card(
            cards, 1, "⏱️", "Avg Duration", "—"
        )
        self._duration_label = dur_card["value_label"]

        # Avg reclaimable card
        rec_card = self._create_stat_card(
            cards, 2, "💾", "Avg Reclaimable", "—"
        )
        self._reclaim_label = rec_card["value_label"]

    def _create_stat_card(
        self, parent: ctk.CTkFrame, col: int, icon: str, label: str, value: str
    ) -> dict:
        """Create a statistics card with icon, label, and value."""
        card = ctk.CTkFrame(
            parent,
            fg_color=self._tokens["bg_elevated"],
            corner_radius=12,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        padx = (0, 8) if col == 0 else ((8, 0) if col == 2 else (4, 4))
        card.grid(row=0, column=col, sticky="ew", padx=padx)
        self._stat_cards.append(card)

        # Icon
        ctk.CTkLabel(
            card,
            text=icon,
            font=ctk.CTkFont(size=24),
        ).pack(pady=(16, 4))

        # Label
        ctk.CTkLabel(
            card,
            text=label,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self._tokens["text_muted"],
        ).pack(pady=(0, 4))

        # Value
        value_label = ctk.CTkLabel(
            card,
            text=value,
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self._tokens["text_primary"],
        )
        value_label.pack(pady=(0, 16))

        return {"card": card, "value_label": value_label}

    def _build_table_section(self) -> None:
        """Build the filterable table section."""
        table_section = ctk.CTkFrame(
            self,
            fg_color=self._tokens["bg_panel"],
            corner_radius=16,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._table_section = table_section
        table_section.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 16))
        table_section.grid_columnconfigure(0, weight=1)
        table_section.grid_rowconfigure(1, weight=1)

        # Filters toolbar
        self._build_filters(table_section)

        # Scrollable table
        self._scroll = ctk.CTkScrollableFrame(
            table_section,
            fg_color=self._tokens["bg_surface"],
            corner_radius=12,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self._scroll.grid_columnconfigure(0, weight=1)

        # Action buttons
        self._build_action_buttons(table_section)

    def _build_filters(self, parent: ctk.CTkFrame) -> None:
        """Build the filter controls."""
        filters = ctk.CTkFrame(parent, fg_color="transparent")
        filters.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 12))
        filters.grid_columnconfigure(2, weight=1)

        # Filter checkboxes
        checkbox_frame = ctk.CTkFrame(filters, fg_color="transparent")
        checkbox_frame.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ctk.CTkCheckBox(
            checkbox_frame,
            text="Resumable only",
            variable=self._show_resumable_only,
            command=self._apply_filters,
            font=ctk.CTkFont(size=12),
            checkbox_height=20,
            checkbox_width=20,
            corner_radius=6,
            fg_color=self._tokens["accent_primary"],
            hover_color=self._tokens["accent_secondary"],
        ).pack(side="left", padx=(0, 20))

        ctk.CTkCheckBox(
            checkbox_frame,
            text="Failed only",
            variable=self._show_failed_only,
            command=self._apply_filters,
            font=ctk.CTkFont(size=12),
            checkbox_height=20,
            checkbox_width=20,
            corner_radius=6,
            fg_color=self._tokens["warning"],
            hover_color=("#B45309", "#D97706"),
        ).pack(side="left")

        # Search box
        search_frame = ctk.CTkFrame(filters, fg_color="transparent")
        search_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        search_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            search_frame,
            text="🔍",
            font=ctk.CTkFont(size=16),
        ).pack(side="left", padx=(0, 8))

        search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self._search_text,
            placeholder_text="Search by scan ID, root path, or status...",
            height=36,
            corner_radius=10,
            fg_color=self._tokens["bg_surface"],
            border_color=self._tokens["border_default"],
            font=ctk.CTkFont(size=12),
        )
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<Return>", lambda e: self._apply_filters())
        search_entry.bind("<KeyRelease>", self._on_search_key_release)

    def _build_action_buttons(self, parent: ctk.CTkFrame) -> None:
        """Build the action buttons row."""
        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))

        self._load_btn = ctk.CTkButton(
            actions,
            text="📂 Load Results",
            width=130,
            height=36,
            corner_radius=10,
            fg_color=self._tokens["accent_primary"],
            hover_color=self._tokens["accent_secondary"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._load_selected,
            state="disabled",
        )
        self._load_btn.pack(side="left", padx=(0, 10))

        self._resume_btn = ctk.CTkButton(
            actions,
            text="▶️ Resume Scan",
            width=130,
            height=36,
            corner_radius=10,
            fg_color=self._tokens["success"],
            hover_color=("#047857", "#059669"),
            font=ctk.CTkFont(size=13),
            command=self._resume_selected,
            state="disabled",
        )
        self._resume_btn.pack(side="left", padx=(0, 10))

        self._delete_btn = ctk.CTkButton(
            actions,
            text="🗑️ Delete",
            width=100,
            height=36,
            corner_radius=10,
            fg_color=self._tokens["error"],
            hover_color=("#B91C1C", "#DC2626"),
            font=ctk.CTkFont(size=13),
            command=self._delete_selected,
            state="disabled",
        )
        self._delete_btn.pack(side="right")

        self._export_btn = ctk.CTkButton(
            actions,
            text="📤 Export JSON",
            width=120,
            height=36,
            corner_radius=10,
            fg_color=self._tokens["bg_elevated"],
            hover_color=self._tokens["bg_overlay"],
            text_color=self._tokens["text_primary"],
            font=ctk.CTkFont(size=13),
            command=self._export_json,
        )
        self._export_btn.pack(side="right", padx=(0, 10))

    def _build_detail_panel(self) -> None:
        """Build the session detail panel."""
        detail = ctk.CTkFrame(
            self,
            fg_color=self._tokens["bg_panel"],
            corner_radius=16,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._detail_frame = detail
        detail.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 24))
        detail.grid_columnconfigure(0, weight=1)

        # Header
        header_frame = ctk.CTkFrame(detail, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 12))

        ctk.CTkLabel(
            header_frame,
            text="📋 Session Details",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(side="left")

        # Detail fields container - two column layout
        self._detail_container = ctk.CTkFrame(detail, fg_color="transparent")
        self._detail_container.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 16))
        self._detail_container.grid_columnconfigure(0, weight=1)
        self._detail_container.grid_columnconfigure(1, weight=1)

        # Detail labels with icons
        self._detail_vars: dict[str, ctk.StringVar] = {}
        fields = [
            ("Session ID", "🔖", "—"),
            ("Status", "📊", "—"),
            ("Resumable", "🔄", "—"),
            ("Started", "🕐", "—"),
            ("Duration", "⏱️", "—"),
            ("Files Scanned", "📁", "—"),
            ("Duplicates Found", "📑", "—"),
            ("Reclaimable Space", "💾", "—"),
            ("Root Paths", "📂", "—"),
            ("Config Hash", "🔗", "—"),
        ]

        # Split into two columns
        left_fields = fields[:5]
        right_fields = fields[5:]

        for col, field_list in enumerate([left_fields, right_fields]):
            col_frame = ctk.CTkFrame(self._detail_container, fg_color="transparent")
            col_frame.grid(row=0, column=col, sticky="nsew", padx=(0, 16) if col == 0 else 0)

            for i, (label, icon, default) in enumerate(field_list):
                row_frame = ctk.CTkFrame(col_frame, fg_color="transparent")
                row_frame.pack(fill="x", pady=4)

                ctk.CTkLabel(
                    row_frame,
                    text=f"{icon}  {label}:",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=self._tokens["text_muted"],
                    width=140,
                    anchor="w",
                ).pack(side="left")

                var = ctk.StringVar(value=default)
                ctk.CTkLabel(
                    row_frame,
                    textvariable=var,
                    font=ctk.CTkFont(size=12),
                    text_color=self._tokens["text_primary"],
                    wraplength=280,
                    anchor="w",
                ).pack(side="left", fill="x", expand=True)

                self._detail_vars[label] = var

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE POPULATION AND FILTERING METHODS - PRESERVED FUNCTIONALITY
    # ══════════════════════════════════════════════════════════════════════════

    def _on_search_key_release(self, event=None) -> None:
        """Debounce search: cancel pending timer, schedule one apply."""
        cancel_after(self, self._search_timer_id)
        self._search_timer_id = self.after(300, self._apply_filters_debounced)

    def _apply_filters_debounced(self) -> None:
        """Run filters after debounce delay."""
        self._search_timer_id = None
        self._apply_filters()

    def _apply_filters(self) -> None:
        """Apply current filters to scan data."""
        filtered = []
        search = self._search_text.get().lower()
        resumable_only = self._show_resumable_only.get()
        failed_only = self._show_failed_only.get()

        for row in self._scan_data:
            # Status filter
            status = str(row.get("status", "")).lower()
            if resumable_only and "resumable" not in status:
                continue
            if failed_only and "failed" not in status and "error" not in status:
                continue

            # Search filter
            if search:
                searchable = " ".join([
                    str(row.get("scan_id", "")),
                    str(row.get("status", "")),
                    " ".join(row.get("roots", [])),
                ]).lower()
                if search not in searchable:
                    continue

            filtered.append(row)

        self._filtered_data = filtered
        self._populate_table()

    def _populate_table(self) -> None:
        """Populate the scrollable table with filtered data."""
        for widget in self._scroll.winfo_children():
            widget.destroy()

        if not self._filtered_data:
            self._show_empty_state()
            return

        for i, row in enumerate(self._filtered_data):
            self._create_table_row(i, row)

    def _show_empty_state(self) -> None:
        """Show empty state when no scans match filters."""
        empty_frame = ctk.CTkFrame(self._scroll, fg_color="transparent")
        empty_frame.pack(fill="x", pady=32)

        ctk.CTkLabel(
            empty_frame,
            text="📭",
            font=ctk.CTkFont(size=40),
        ).pack()

        ctk.CTkLabel(
            empty_frame,
            text="No scans match current filters",
            font=ctk.CTkFont(size=14),
            text_color=self._tokens["text_muted"],
        ).pack(pady=(12, 0))

    def _create_table_row(self, index: int, data: dict[str, Any]) -> None:
        """Create a single table row with modern styling."""
        row_data = dict(data)
        sid = str(row_data.get("scan_id") or "")
        short = (sid[:12] + "…") if len(sid) > 12 else sid or "—"
        started = str(row_data.get("started_at") or "—")[:19]
        status = str(row_data.get("status") or "—")
        files_n = int(row_data.get("files_scanned") or 0)
        dups = int(row_data.get("duplicates_found") or 0)
        reclaim = int(row_data.get("reclaimable_bytes") or 0)
        roots = row_data.get("roots") or []
        root_hint = ""
        if roots:
            try:
                root_hint = Path(str(roots[0])).name[:40]
            except Exception:
                root_hint = str(roots[0])[:40]

        # Determine status styling
        is_completed = "completed" in status.lower()
        is_resumable = "resumable" in status.lower()
        is_failed = "failed" in status.lower() or "error" in status.lower()

        if is_completed:
            status_color = self._tokens["success"]
            status_icon = "✓"
        elif is_resumable:
            status_color = self._tokens["info"]
            status_icon = "⏸"
        elif is_failed:
            status_color = self._tokens["error"]
            status_icon = "✗"
        else:
            status_color = self._tokens["text_muted"]
            status_icon = "•"

        # Row frame
        row_frame = ctk.CTkFrame(
            self._scroll,
            fg_color=self._tokens["bg_elevated"],
            corner_radius=12,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        row_frame.pack(fill="x", padx=8, pady=4)
        row_frame.grid_columnconfigure(0, weight=1)

        # Make entire row clickable
        def on_click(event=None):
            self._select_scan(sid, row_data)

        row_frame.bind("<Button-1>", on_click)

        # Header with status indicator
        header = ctk.CTkFrame(row_frame, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 6))
        header.bind("<Button-1>", on_click)

        # Session ID
        id_label = ctk.CTkLabel(
            header,
            text=short,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self._tokens["text_primary"],
        )
        id_label.pack(side="left")
        id_label.bind("<Button-1>", on_click)

        # Status badge
        status_badge = ctk.CTkLabel(
            header,
            text=f"  {status_icon} {status}",
            font=ctk.CTkFont(size=12),
            text_color=status_color,
        )
        status_badge.pack(side="left")
        status_badge.bind("<Button-1>", on_click)

        # Meta info
        meta_parts = [
            f"🕐 {started}",
            f"📁 {fmt_int(files_n)} files",
            f"📑 {fmt_int(dups)} groups",
            f"💾 {fmt_bytes(reclaim)}",
        ]
        meta_text = "  ·  ".join(meta_parts)
        if root_hint:
            meta_text += f"\n📂 {root_hint}"

        body = ctk.CTkFrame(row_frame, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=(0, 12))
        body.bind("<Button-1>", on_click)

        meta_label = ctk.CTkLabel(
            body,
            text=meta_text,
            text_color=self._tokens["text_muted"],
            justify="left",
            anchor="w",
            font=ctk.CTkFont(size=11),
        )
        meta_label.pack(anchor="w")
        meta_label.bind("<Button-1>", on_click)

    # ══════════════════════════════════════════════════════════════════════════
    # SELECTION AND DETAIL PANEL METHODS
    # ══════════════════════════════════════════════════════════════════════════

    def _select_scan(self, scan_id: str, data: dict[str, Any]) -> None:
        """Handle scan selection."""
        self._selected_scan_id = scan_id
        self._update_detail_panel(data)

        # Update button states
        self._load_btn.configure(state="normal")
        if self._on_resume_scan and "resumable" in str(data.get("status", "")).lower():
            self._resume_btn.configure(state="normal")
        else:
            self._resume_btn.configure(state="disabled")
        self._delete_btn.configure(state="normal")

    def _update_detail_panel(self, data: dict[str, Any]) -> None:
        """Update the detail panel with selected scan data."""
        # Calculate duration if we have start/end times
        duration_str = "—"
        if data.get("started_at") and data.get("completed_at"):
            try:
                start = datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
                duration = end - start
                duration_str = fmt_duration(duration.total_seconds())
            except Exception:
                pass

        # Update detail fields
        sid = str(data.get("scan_id", ""))
        self._detail_vars["Session ID"].set(sid or "—")
        self._detail_vars["Status"].set(str(data.get("status", "—")))
        try:
            res_ids = set(self._get_resumable_ids() or [])
            self._detail_vars["Resumable"].set("Yes" if sid and sid in res_ids else "No")
        except Exception:
            self._detail_vars["Resumable"].set("—")
        self._detail_vars["Started"].set(str(data.get("started_at", "—"))[:19])
        self._detail_vars["Duration"].set(duration_str)
        self._detail_vars["Files Scanned"].set(fmt_int(data.get("files_scanned", 0)))
        self._detail_vars["Duplicates Found"].set(fmt_int(data.get("duplicates_found", 0)))
        self._detail_vars["Reclaimable Space"].set(fmt_bytes(data.get("reclaimable_bytes", 0)))

        roots = data.get("roots", [])
        if roots:
            root_text = "\n".join(str(r)[:60] for r in roots[:3])
            if len(roots) > 3:
                root_text += f"\n... and {len(roots) - 3} more"
            self._detail_vars["Root Paths"].set(root_text)
        else:
            self._detail_vars["Root Paths"].set("—")

        self._detail_vars["Config Hash"].set(str(data.get("config_hash", "—"))[:16])

    def _update_summary(self) -> None:
        """Update summary statistics."""
        if not self._scan_data:
            self._total_label.configure(text="0")
            self._duration_label.configure(text="—")
            self._reclaim_label.configure(text="—")
            return

        total = len(self._scan_data)
        self._total_label.configure(text=str(total))

        # Calculate averages
        durations = []
        reclaimables = []
        for row in self._scan_data:
            if row.get("started_at") and row.get("completed_at"):
                try:
                    start = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
                    end = datetime.fromisoformat(row["completed_at"].replace("Z", "+00:00"))
                    durations.append((end - start).total_seconds())
                except Exception:
                    pass
            reclaimables.append(row.get("reclaimable_bytes", 0))

        if durations:
            avg_duration = sum(durations) / len(durations)
            self._duration_label.configure(text=fmt_duration(avg_duration))
        else:
            self._duration_label.configure(text="—")

        if reclaimables:
            avg_reclaim = sum(reclaimables) / len(reclaimables)
            self._reclaim_label.configure(text=fmt_bytes(avg_reclaim))
        else:
            self._reclaim_label.configure(text="—")

    # ══════════════════════════════════════════════════════════════════════════
    # ACTION METHODS - PRESERVED FUNCTIONALITY
    # ══════════════════════════════════════════════════════════════════════════

    def _load_selected(self) -> None:
        """Load selected scan into Review."""
        if self._selected_scan_id:
            self._on_load_scan(self._selected_scan_id)

    def _resume_selected(self) -> None:
        """Resume selected scan."""
        if self._selected_scan_id and self._on_resume_scan:
            self._on_resume_scan(self._selected_scan_id)

    def _delete_selected(self) -> None:
        """Delete selected scan entry."""
        if not self._selected_scan_id:
            return

        if messagebox.askyesno(
            "Delete Scan Entry",
            f"Delete scan {self._selected_scan_id[:12]}… from history?\n\n"
            "This removes the saved result entry from the local database. Files on disk are not deleted.",
            icon="warning",
        ):
            if self._on_delete_scan:
                ok = self._on_delete_scan(self._selected_scan_id)
                if ok:
                    self._selected_scan_id = None
                    self._load_btn.configure(state="disabled")
                    self._resume_btn.configure(state="disabled")
                    self._delete_btn.configure(state="disabled")
                    self.reload()
                    messagebox.showinfo("History", "Scan entry removed.")
                else:
                    messagebox.showerror("History", "Could not delete this scan entry.")
            else:
                messagebox.showinfo("History", "Delete is not wired for this build.")

    def _export_json(self) -> None:
        """Export filtered scan history to JSON."""
        if not self._filtered_data:
            messagebox.showinfo("Export", "No scans to export.")
            return

        path = filedialog.asksaveasfilename(
            title="Export scan history",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        payload = {
            "export_format": "cerebro_history_v1",
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "scan_count": len(self._filtered_data),
            "filters": {
                "resumable_only": self._show_resumable_only.get(),
                "failed_only": self._show_failed_only.get(),
                "search_text": self._search_text.get(),
            },
            "scans": self._filtered_data,
        }

        try:
            Path(path).write_text(
                json.dumps(payload, indent=2, default=str),
                encoding="utf-8",
            )
            messagebox.showinfo("Export", f"Exported {len(self._filtered_data)} scan(s) to:\n{path}")
        except OSError as ex:
            messagebox.showerror("Export failed", str(ex))
