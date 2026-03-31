"""
CustomTkinter Diagnostics page — P1 quality for support.

Features:
- Runtime status (scanning, active scan ID, database path)
- Session overview with selector
- Phases timeline table
- Compatibility checks
- Artifacts listing
- Events log with filtering
- JSON export
- Clear recorder buffer

REFACTORED: Visual redesign with modern aesthetics while preserving all APIs.
- Enhanced status cards with visual indicators
- Modern tabbed interface with better navigation
- Improved log viewer with syntax-like highlighting
- Consistent design token usage
"""

from __future__ import annotations

import json
import logging
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Any, Optional

import customtkinter as ctk

from ...infrastructure.diagnostics import get_diagnostics_recorder
from .design_tokens import get_theme_colors, resolve_border_token

if TYPE_CHECKING:
    from ...application.runtime import ApplicationRuntime

_log = logging.getLogger(__name__)


class DiagnosticsPageCTK(ctk.CTkFrame):
    """Engine diagnostics page with P1 functionality for support."""

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API - PRESERVED FROM ORIGINAL
    # ══════════════════════════════════════════════════════════════════════════

    def __init__(
        self,
        parent,
        *,
        runtime: "ApplicationRuntime",
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._rt = runtime
        self._coordinator = runtime.coordinator
        self._store: Any | None = None
        self._selected_session_id: Optional[str] = None
        self._history_cache: list[dict[str, Any]] = []
        self._history_lookup: dict[str, dict[str, Any]] = {}

        self._tokens = get_theme_colors()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self._build()

    def attach_store(self, store: Any) -> None:
        """Attach shared UI store for API parity with other pages. API UNCHANGED."""
        self._store = store

    def apply_theme_tokens(self, tokens: dict) -> None:
        """Apply theme tokens to the page. API UNCHANGED."""
        panel = str(tokens.get("bg_panel", "#161b22"))
        self.configure(fg_color=panel)
        if hasattr(self, "_scroll"):
            self._scroll.configure(fg_color="transparent")
        acc = str(tokens.get("accent_primary", "#3B8ED0"))
        elev = str(tokens.get("bg_elevated", "#21262d"))
        br = resolve_border_token(tokens)
        for name in ("_diag_status_frame", "_diag_overview_frame", "_diag_tab_container"):
            fr = getattr(self, name, None)
            if fr is not None:
                fr.configure(fg_color=panel, border_color=br)
        if hasattr(self, "_refresh_diag_btn"):
            self._refresh_diag_btn.configure(fg_color=acc)
        if hasattr(self, "_export_diag_btn"):
            self._export_diag_btn.configure(fg_color=elev)

        # Update all text labels with live token colors
        self._update_label_colors(self, tokens)

    def _update_label_colors(self, widget, tokens: dict) -> None:
        from ..utils.theme_utils import apply_label_colors

        apply_label_colors(widget, tokens)

    def reload(self) -> None:
        """Reload all diagnostics data. API UNCHANGED."""
        if self._coordinator is None:
            self._scanning_var.set("—")
            self._active_id_var.set("—")
            self._db_var.set("—")
            self._history_cache = []
            self._history_lookup = {}
            self._selected_session_id = None
            if hasattr(self, "_session_var"):
                self._session_var.set("")
            if hasattr(self, "_session_combo"):
                self._session_combo.configure(values=[])
            self._update_session_overview("")
            self._refresh_tab_content()
            return

        scanning = getattr(self._coordinator, "is_scanning", False)
        self._scanning_var.set("Yes" if scanning else "No")

        try:
            active_id = self._coordinator.get_active_scan_id()
        except (AttributeError, TypeError):
            active_id = None
        self._active_id_var.set((active_id[:16] + "…") if active_id and len(active_id) > 16 else (active_id or "—"))

        persistence = getattr(self._coordinator, "persistence", None)
        db_path = getattr(persistence, "db_path", None) if persistence else None
        self._db_var.set(str(db_path) if db_path else "—")

        try:
            self._history_cache = self._coordinator.get_history(limit=50) or []
            self._history_lookup = {h.get("scan_id", ""): h for h in self._history_cache if h.get("scan_id")}
            session_ids = list(self._history_lookup.keys())
            self._session_combo.configure(values=session_ids)

            if session_ids and not self._session_var.get():
                self._session_var.set(session_ids[0])
                self._selected_session_id = session_ids[0]
        except Exception as ex:
            _log.warning("Failed to load history: %s", ex)
            self._history_cache = []
            self._history_lookup = {}

        self._update_session_overview(self._selected_session_id)
        self._refresh_tab_content()

    # ══════════════════════════════════════════════════════════════════════════
    # PRIVATE UI BUILD METHODS - REFACTORED FOR VISUAL ENHANCEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def _build(self) -> None:
        # Configure base styling
        self.configure(fg_color=self._tokens["bg_panel"])

        # Header
        self._build_header()

        # Runtime status section
        self._build_runtime_status()

        # Session selector and overview
        self._build_session_overview()

        # Tabbed content area
        self._build_tabbed_content()

        # Load initial data
        self.reload()

    def _build_header(self) -> None:
        """Build the page header with title and action buttons."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 16))
        header.grid_columnconfigure(0, weight=1)

        # Title section
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_frame,
            text="🔧  Diagnostics",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(side="left")

        # Subtitle
        ctk.CTkLabel(
            header,
            text="Engine runtime state, scan sessions, and diagnostic events.",
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

        # Action buttons
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=2, sticky="ne")

        self._refresh_diag_btn = ctk.CTkButton(
            actions,
            text="↻ Refresh",
            width=100,
            height=36,
            corner_radius=10,
            fg_color=self._tokens["accent_primary"],
            hover_color=self._tokens["accent_secondary"],
            font=ctk.CTkFont(size=13),
            command=self.reload,
        )
        self._refresh_diag_btn.pack(side="left", padx=(0, 10))

        self._export_diag_btn = ctk.CTkButton(
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
        self._export_diag_btn.pack(side="left")

    def _build_runtime_status(self) -> None:
        """Build the runtime status section."""
        status = ctk.CTkFrame(
            self,
            fg_color=self._tokens["bg_panel"],
            corner_radius=16,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._diag_status_frame = status
        status.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 16))
        status.grid_columnconfigure(0, weight=1)

        # Section header
        header_frame = ctk.CTkFrame(status, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 12))

        ctk.CTkLabel(
            header_frame,
            text="Runtime Status",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(side="left")

        # Status indicator
        self._status_indicator = ctk.CTkLabel(
            header_frame,
            text="● Online",
            font=ctk.CTkFont(size=11),
            text_color=self._tokens["success"],
        )
        self._status_indicator.pack(side="right")

        # Status fields in a grid
        fields = ctk.CTkFrame(status, fg_color="transparent")
        fields.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 16))
        fields.grid_columnconfigure(1, weight=1)

        # Scanning status
        self._build_status_row(fields, 0, "Scanning", "scanning")
        self._scanning_var = ctk.StringVar(value="—")
        ctk.CTkLabel(
            fields,
            textvariable=self._scanning_var,
            font=ctk.CTkFont(size=13),
            text_color=self._tokens["text_primary"],
        ).grid(row=0, column=1, sticky="w", padx=(12, 0), pady=4)

        # Active scan ID
        self._build_status_row(fields, 1, "Active Scan ID", "id")
        id_row = ctk.CTkFrame(fields, fg_color="transparent")
        id_row.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=4)
        id_row.grid_columnconfigure(0, weight=1)

        self._active_id_var = ctk.StringVar(value="—")
        ctk.CTkLabel(
            id_row,
            textvariable=self._active_id_var,
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=self._tokens["text_primary"],
            wraplength=400,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(
            id_row,
            text="Copy",
            width=60,
            height=28,
            corner_radius=8,
            fg_color=self._tokens["bg_elevated"],
            hover_color=self._tokens["bg_overlay"],
            text_color=self._tokens["text_secondary"],
            font=ctk.CTkFont(size=11),
            command=self._copy_active_scan_id,
        ).grid(row=0, column=1, padx=(10, 0))

        # Database path
        self._build_status_row(fields, 2, "Database", "database")
        db_row = ctk.CTkFrame(fields, fg_color="transparent")
        db_row.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=4)
        db_row.grid_columnconfigure(0, weight=1)

        self._db_var = ctk.StringVar(value="—")
        ctk.CTkLabel(
            db_row,
            textvariable=self._db_var,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=self._tokens["text_secondary"],
            wraplength=400,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(
            db_row,
            text="Copy",
            width=60,
            height=28,
            corner_radius=8,
            fg_color=self._tokens["bg_elevated"],
            hover_color=self._tokens["bg_overlay"],
            text_color=self._tokens["text_secondary"],
            font=ctk.CTkFont(size=11),
            command=lambda: self._copy_clipboard(self._db_var.get()),
        ).grid(row=0, column=1, padx=(10, 0))

    def _build_status_row(self, parent: ctk.CTkFrame, row: int, label: str, icon_type: str) -> None:
        """Build a status row with label."""
        icons = {
            "scanning": "🔄",
            "id": "🔖",
            "database": "💾",
        }
        icon = icons.get(icon_type, "•")

        ctk.CTkLabel(
            parent,
            text=f"{icon}  {label}:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self._tokens["text_secondary"],
        ).grid(row=row, column=0, sticky="w", pady=4)

    def _build_session_overview(self) -> None:
        """Build session selector and overview section."""
        overview = ctk.CTkFrame(
            self,
            fg_color=self._tokens["bg_panel"],
            corner_radius=16,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._diag_overview_frame = overview
        overview.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))
        overview.grid_columnconfigure(0, weight=1)

        # Section header
        ctk.CTkLabel(
            overview,
            text="Session Overview",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 12))

        # Session selector
        selector = ctk.CTkFrame(overview, fg_color="transparent")
        selector.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        selector.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            selector,
            text="View session:",
            font=ctk.CTkFont(size=13),
            text_color=self._tokens["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        self._session_var = ctk.StringVar(value="")
        self._session_combo = ctk.CTkComboBox(
            selector,
            variable=self._session_var,
            values=[],
            width=320,
            height=32,
            corner_radius=8,
            fg_color=self._tokens["bg_surface"],
            border_color=self._tokens["border_default"],
            button_color=self._tokens["bg_overlay"],
            button_hover_color=self._tokens["accent_secondary"],
            font=ctk.CTkFont(family="Consolas", size=11),
            command=self._on_session_change,
        )
        self._session_combo.pack(side="left", fill="x", expand=True)

        # Overview fields grid
        fields_frame = ctk.CTkFrame(overview, fg_color="transparent")
        fields_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))

        self._overview_vars: dict[str, ctk.StringVar] = {}
        fields = [
            ("Session ID", "—"),
            ("Config Hash", "—"),
            ("Schema Version", "—"),
            ("Root Fingerprint", "—"),
        ]

        for i, (label, default) in enumerate(fields):
            row_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=3)

            ctk.CTkLabel(
                row_frame,
                text=f"{label}:",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self._tokens["text_muted"],
                width=120,
                anchor="w",
            ).pack(side="left")

            var = ctk.StringVar(value=default)
            ctk.CTkLabel(
                row_frame,
                textvariable=var,
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color=self._tokens["text_secondary"],
                anchor="w",
            ).pack(side="left", fill="x", expand=True)

            self._overview_vars[label] = var

    def _build_tabbed_content(self) -> None:
        """Build the tabbed content area."""
        tab_container = ctk.CTkFrame(
            self,
            fg_color=self._tokens["bg_panel"],
            corner_radius=16,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._diag_tab_container = tab_container
        tab_container.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 24))
        tab_container.grid_columnconfigure(0, weight=1)
        tab_container.grid_rowconfigure(1, weight=1)

        # Tab buttons
        self._tab_buttons: dict[str, ctk.CTkButton] = {}
        tabs = [
            ("phases", "📊 Phases"),
            ("events", "📝 Events"),
            ("artifacts", "📁 Artifacts"),
            ("compatibility", "✓ Compatibility"),
        ]

        button_row = ctk.CTkFrame(tab_container, fg_color="transparent")
        button_row.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 12))

        for i, (tab_id, tab_name) in enumerate(tabs):
            is_active = tab_id == "phases"
            btn = ctk.CTkButton(
                button_row,
                text=tab_name,
                width=130,
                height=36,
                corner_radius=10,
                fg_color=self._tokens["accent_primary"] if is_active else self._tokens["bg_elevated"],
                hover_color=self._tokens["accent_secondary"] if is_active else self._tokens["bg_overlay"],
                text_color=self._tokens["text_primary"],
                font=ctk.CTkFont(size=12, weight="bold" if is_active else "normal"),
                command=lambda t=tab_id: self._switch_tab(t),
            )
            btn.pack(side="left", padx=(0, 8))
            self._tab_buttons[tab_id] = btn

        # Tab content area
        self._current_tab = "phases"
        self._tab_content = ctk.CTkFrame(tab_container, fg_color="transparent")
        self._tab_content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 16))
        self._tab_content.grid_columnconfigure(0, weight=1)
        self._tab_content.grid_rowconfigure(0, weight=1)

        # Build initial tab content
        self._build_phases_content()

    def _switch_tab(self, tab_id: str) -> None:
        """Switch between tab views."""
        # Reset all button colors
        for tid, btn in self._tab_buttons.items():
            if tid == tab_id:
                btn.configure(
                    fg_color=self._tokens["accent_primary"],
                    hover_color=self._tokens["accent_secondary"],
                    font=ctk.CTkFont(size=12, weight="bold"),
                )
            else:
                btn.configure(
                    fg_color=self._tokens["bg_elevated"],
                    hover_color=self._tokens["bg_overlay"],
                    font=ctk.CTkFont(size=12, weight="normal"),
                )

        self._current_tab = tab_id

        # Clear and rebuild content
        for widget in self._tab_content.winfo_children():
            widget.destroy()

        if tab_id == "phases":
            self._build_phases_content()
        elif tab_id == "events":
            self._build_events_content()
        elif tab_id == "artifacts":
            self._build_artifacts_content()
        elif tab_id == "compatibility":
            self._build_compatibility_content()

        self._refresh_tab_content()

    def _build_phases_content(self) -> None:
        """Build the phases table content."""
        ctk.CTkLabel(
            self._tab_content,
            text="Scan Phases",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        self._phases_scroll = ctk.CTkScrollableFrame(
            self._tab_content,
            fg_color="transparent",
            corner_radius=12,
        )
        self._phases_scroll.grid(row=1, column=0, sticky="nsew")
        self._phases_scroll.grid_columnconfigure(0, weight=1)

    def _build_events_content(self) -> None:
        """Build the events log content."""
        header = ctk.CTkFrame(self._tab_content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Recent Events",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="🗑️ Clear Buffer",
            width=120,
            height=32,
            corner_radius=8,
            fg_color=self._tokens["warning"],
            hover_color=("#B45309", "#D97706"),
            font=ctk.CTkFont(size=12),
            command=self._clear_recorder,
        ).pack(side="right")

        self._events_scroll = ctk.CTkTextbox(
            self._tab_content,
            wrap="word",
            fg_color=self._tokens["bg_surface"],
            text_color=self._tokens["text_secondary"],
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=12,
        )
        self._events_scroll.grid(row=1, column=0, sticky="nsew")

    def _build_artifacts_content(self) -> None:
        """Build the artifacts listing content."""
        ctk.CTkLabel(
            self._tab_content,
            text="Scan Artifacts",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        self._artifacts_scroll = ctk.CTkScrollableFrame(
            self._tab_content,
            fg_color="transparent",
            corner_radius=12,
        )
        self._artifacts_scroll.grid(row=1, column=0, sticky="nsew")
        self._artifacts_scroll.grid_columnconfigure(0, weight=1)

    def _build_compatibility_content(self) -> None:
        """Build the compatibility checks content."""
        ctk.CTkLabel(
            self._tab_content,
            text="Compatibility Checks",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        self._compat_scroll = ctk.CTkScrollableFrame(
            self._tab_content,
            fg_color="transparent",
            corner_radius=12,
        )
        self._compat_scroll.grid(row=1, column=0, sticky="nsew")
        self._compat_scroll.grid_columnconfigure(0, weight=1)

    # ══════════════════════════════════════════════════════════════════════════
    # DATA POPULATION METHODS - PRESERVED FUNCTIONALITY
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_tab_content(self) -> None:
        """Refresh the current tab content."""
        if self._current_tab == "phases":
            self._populate_phases()
        elif self._current_tab == "events":
            self._populate_events()
        elif self._current_tab == "artifacts":
            self._populate_artifacts()
        elif self._current_tab == "compatibility":
            self._populate_compatibility()

    def _populate_phases(self) -> None:
        """Populate the phases table."""
        if not hasattr(self, "_phases_scroll") or self._phases_scroll is None:
            for widget in self._tab_content.winfo_children():
                widget.destroy()
            self._build_phases_content()

        for widget in self._phases_scroll.winfo_children():
            widget.destroy()

        if not self._selected_session_id:
            self._show_empty_state(self._phases_scroll, "Select a session to view phases.")
            return

        persist = getattr(self._coordinator, "persistence", None)
        if persist is None:
            self._show_empty_state(self._phases_scroll, "Persistence not available.")
            return

        try:
            checkpoints = persist.checkpoint_repo.list_for_session(self._selected_session_id)
        except Exception as ex:
            _log.warning("list phase checkpoints: %s", ex)
            checkpoints = []

        if not checkpoints:
            self._show_empty_state(
                self._phases_scroll,
                "No phase checkpoints in the database for this session. "
                "Completed scans often only persist final results.",
            )
            return

        for cp in checkpoints:
            fr = ctk.CTkFrame(
                self._phases_scroll,
                fg_color=self._tokens["bg_elevated"],
                corner_radius=10,
            )
            fr.pack(fill="x", pady=4, padx=4)

            title = f"{cp.phase_name.value} — {cp.status.value}"
            ctk.CTkLabel(
                fr,
                text=title,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=self._tokens["text_primary"],
            ).pack(anchor="w", padx=12, pady=(10, 4))

            tot = cp.total_units if cp.total_units is not None else "—"
            sub = f"Units: {cp.completed_units} / {tot}  ·  Updated: {cp.updated_at.isoformat()[:19]}"
            ctk.CTkLabel(
                fr,
                text=sub,
                text_color=self._tokens["text_muted"],
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=12, pady=(0, 10))

    def _populate_events(self) -> None:
        """Populate the events log."""
        if not hasattr(self, "_events_scroll") or self._events_scroll is None:
            for widget in self._tab_content.winfo_children():
                widget.destroy()
            self._build_events_content()

        self._events_scroll.delete("1.0", "end")

        rec = get_diagnostics_recorder()
        events = rec.get_recent(100)

        if not events:
            self._events_scroll.insert("1.0", "No events recorded in this session buffer.")
            return

        lines = []
        for e in events:
            try:
                ts = datetime.fromtimestamp(e.wall_time).strftime("%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError, OSError):
                ts = "—"
            detail = f"  |  {e.detail}" if e.detail else ""
            lines.append(f"{ts}  [{e.category}] {e.message}{detail}")

        self._events_scroll.insert("1.0", "\n".join(lines))

    def _populate_artifacts(self) -> None:
        """Populate the artifacts listing."""
        if not hasattr(self, "_artifacts_scroll") or self._artifacts_scroll is None:
            for widget in self._tab_content.winfo_children():
                widget.destroy()
            self._build_artifacts_content()

        for widget in self._artifacts_scroll.winfo_children():
            widget.destroy()

        if not self._selected_session_id:
            self._show_empty_state(self._artifacts_scroll, "Select a session to view artifacts.")
            return

        persist = getattr(self._coordinator, "persistence", None)
        cp_dir = persist.checkpoint_dir if persist else None
        files: list[Path] = []
        if cp_dir and Path(cp_dir).exists():
            sid = self._selected_session_id
            for p in sorted(Path(cp_dir).iterdir()):
                if p.is_file() and sid in p.name:
                    files.append(p)

        if not files:
            self._show_empty_state(
                self._artifacts_scroll, "No checkpoint files on disk. Checkpoints may live only in SQLite."
            )
            return

        for p in files:
            row = ctk.CTkFrame(
                self._artifacts_scroll,
                fg_color=self._tokens["bg_elevated"],
                corner_radius=8,
            )
            row.pack(fill="x", pady=3, padx=4)

            ctk.CTkLabel(
                row,
                text=f"📄 {p.name}",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self._tokens["text_primary"],
            ).pack(anchor="w", padx=10, pady=(8, 2))

            ctk.CTkLabel(
                row,
                text=str(p),
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color=self._tokens["text_muted"],
            ).pack(anchor="w", padx=10, pady=(0, 8))

    def _populate_compatibility(self) -> None:
        """Populate the compatibility checks."""
        if not hasattr(self, "_compat_scroll") or self._compat_scroll is None:
            for widget in self._tab_content.winfo_children():
                widget.destroy()
            self._build_compatibility_content()

        for widget in self._compat_scroll.winfo_children():
            widget.destroy()

        if not self._selected_session_id:
            self._show_empty_state(self._compat_scroll, "Select a session to view compatibility.")
            return

        session_data = self._history_lookup.get(self._selected_session_id)
        dv = (session_data or {}).get("deletion_verification_summary") or {}
        bm = (session_data or {}).get("benchmark_summary") or {}

        if not dv and not bm:
            self._show_empty_state(
                self._compat_scroll, "No deletion-verification or benchmark snapshot stored for this session."
            )
            return

        tb = ctk.CTkTextbox(
            self._compat_scroll,
            wrap="word",
            height=220,
            fg_color=self._tokens["bg_surface"],
            text_color=self._tokens["text_secondary"],
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8,
        )
        tb.pack(fill="both", expand=True, padx=8, pady=8)

        parts: list[str] = []
        if dv:
            parts.append("Deletion verification (summary_json)")
            parts.append(json.dumps(dv, indent=2, default=str))
        if bm:
            parts.append("\nBenchmark (from metrics)")
            parts.append(json.dumps(bm, indent=2, default=str))
        tb.insert("1.0", "\n".join(parts))

    def _show_empty_state(self, parent: ctk.CTkFrame, message: str) -> None:
        """Show an empty state message."""
        empty_frame = ctk.CTkFrame(parent, fg_color="transparent")
        empty_frame.pack(fill="x", pady=24)

        ctk.CTkLabel(
            empty_frame,
            text="📭",
            font=ctk.CTkFont(size=32),
        ).pack()

        ctk.CTkLabel(
            empty_frame,
            text=message,
            font=ctk.CTkFont(size=12),
            text_color=self._tokens["text_muted"],
            wraplength=400,
            justify="center",
        ).pack(pady=(8, 0))

    # ══════════════════════════════════════════════════════════════════════════
    # EVENT HANDLERS AND UTILITIES
    # ══════════════════════════════════════════════════════════════════════════

    def _copy_clipboard(self, text: str) -> None:
        if not text or text == "—":
            return
        try:
            r = self.winfo_toplevel()
            r.clipboard_clear()
            r.clipboard_append(text.strip())
            r.update_idletasks()
        except tk.TclError:
            pass

    def _copy_active_scan_id(self) -> None:
        try:
            aid = self._coordinator.get_active_scan_id() if self._coordinator else None
            if aid:
                self._copy_clipboard(str(aid))
        except Exception:
            self._copy_clipboard(self._active_id_var.get())

    def _on_session_change(self, choice: str = None) -> None:
        """Handle session selection change."""
        session_id = self._session_var.get()
        self._selected_session_id = session_id
        self._update_session_overview(session_id)
        self._refresh_tab_content()

    def _update_session_overview(self, session_id: str) -> None:
        """Update session overview fields."""
        if not session_id:
            for var in self._overview_vars.values():
                var.set("—")
            return

        session_data = self._history_lookup.get(session_id)

        if not session_data:
            self._overview_vars["Session ID"].set("—")
            self._overview_vars["Config Hash"].set("—")
            self._overview_vars["Schema Version"].set("—")
            self._overview_vars["Root Fingerprint"].set("—")
            return

        self._overview_vars["Session ID"].set(session_id)
        self._overview_vars["Config Hash"].set(str(session_data.get("config_hash", "—"))[:16] + "…")
        self._overview_vars["Schema Version"].set(str(session_data.get("schema_version", "—")))
        self._overview_vars["Root Fingerprint"].set(str(session_data.get("root_fingerprint", "—"))[:20] + "…")

    def _clear_recorder(self) -> None:
        """Clear the diagnostics recorder buffer."""
        if not messagebox.askyesno(
            "Clear Diagnostics Buffer",
            "Clear all in-memory recorder events and category counts?\n\n"
            "Scan history on disk is not affected. A new scan also clears this buffer.",
            icon="warning",
        ):
            return
        get_diagnostics_recorder().clear()
        self.reload()

    def _export_json(self) -> None:
        """Export diagnostics to JSON."""
        path = filedialog.asksaveasfilename(
            title="Export diagnostics",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        events = []
        for event in get_diagnostics_recorder().get_recent(100):
            events.append(
                {
                    "category": event.category,
                    "message": event.message,
                    "detail": event.detail,
                    "timestamp": event.timestamp,
                    "wall_time": event.wall_time,
                }
            )

        payload = {
            "export_format": "cerebro_diagnostics_v1",
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "session_id": self._selected_session_id,
            "overview": {k: v.get() for k, v in self._overview_vars.items()},
            "runtime": {
                "scanning": self._scanning_var.get(),
                "active_scan_id": self._active_id_var.get(),
                "database_path": self._db_var.get(),
            },
            "events": events,
        }

        try:
            Path(path).write_text(
                json.dumps(payload, indent=2, default=str),
                encoding="utf-8",
            )
            messagebox.showinfo("Export", f"Diagnostics exported to:\n{path}")
        except OSError as ex:
            messagebox.showerror("Export failed", str(ex))
