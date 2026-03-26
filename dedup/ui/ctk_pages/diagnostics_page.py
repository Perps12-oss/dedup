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

if TYPE_CHECKING:
    from ...application.runtime import ApplicationRuntime

_log = logging.getLogger(__name__)


class DiagnosticsPageCTK(ctk.CTkFrame):
    """Engine diagnostics page with P1 functionality for support."""

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
        self._history_cache: list[dict[str, Any]] = []  # Cache for performance
        self._history_lookup: dict[str, dict[str, Any]] = {}  # Fast lookup by scan_id

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self._build()

    def attach_store(self, store: Any) -> None:
        """Attach shared UI store for API parity with other pages.

        DiagnosticsPageCTK currently pulls runtime/session data from the coordinator,
        but `ctk_app.py` expects every page to expose `attach_store`.
        """
        self._store = store

    def _build(self) -> None:
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

    def apply_theme_tokens(self, tokens: dict) -> None:
        panel = str(tokens.get("bg_panel", "#161b22"))
        acc = str(tokens.get("accent_primary", "#3B8ED0"))
        elev = str(tokens.get("bg_elevated", "#21262d"))
        for name in ("_diag_status_frame", "_diag_overview_frame", "_diag_tab_container"):
            fr = getattr(self, name, None)
            if fr is not None:
                fr.configure(fg_color=panel)
        if hasattr(self, "_refresh_diag_btn"):
            self._refresh_diag_btn.configure(fg_color=acc)
        if hasattr(self, "_export_diag_btn"):
            self._export_diag_btn.configure(fg_color=elev)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Diagnostics",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Engine runtime state, scan sessions, and diagnostic events.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Action buttons
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e", padx=(0, 20))

        self._refresh_diag_btn = ctk.CTkButton(
            actions,
            text="Refresh",
            width=100,
            command=self.reload,
        )
        self._refresh_diag_btn.pack(side="left", padx=(0, 8))

        self._export_diag_btn = ctk.CTkButton(
            actions,
            text="Export JSON",
            width=120,
            fg_color=("gray35", "gray50"),
            command=self._export_json,
        )
        self._export_diag_btn.pack(side="left")

    def _build_runtime_status(self) -> None:
        status = ctk.CTkFrame(self, corner_radius=12)
        self._diag_status_frame = status
        status.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        status.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            status,
            text="Runtime Status",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        # Status fields
        fields = ctk.CTkFrame(status, fg_color="transparent")
        fields.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        fields.grid_columnconfigure(1, weight=1)

        # Scanning status
        ctk.CTkLabel(fields, text="Scanning:", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, sticky="w", pady=2
        )
        self._scanning_var = ctk.StringVar(value="—")
        ctk.CTkLabel(fields, textvariable=self._scanning_var).grid(
            row=0, column=1, sticky="w", padx=(12, 0), pady=2
        )

        # Active scan ID
        ctk.CTkLabel(fields, text="Active scan ID:", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=1, column=0, sticky="w", pady=2
        )
        id_row = ctk.CTkFrame(fields, fg_color="transparent")
        id_row.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=2)
        id_row.grid_columnconfigure(0, weight=1)
        self._active_id_var = ctk.StringVar(value="—")
        ctk.CTkLabel(
            id_row,
            textvariable=self._active_id_var,
            font=ctk.CTkFont(size=11),
            wraplength=400,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            id_row,
            text="Copy",
            width=64,
            command=self._copy_active_scan_id,
        ).grid(row=0, column=1, padx=(8, 0))

        # Database path
        ctk.CTkLabel(fields, text="Database:", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=2, column=0, sticky="w", pady=2
        )
        db_row = ctk.CTkFrame(fields, fg_color="transparent")
        db_row.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=2)
        db_row.grid_columnconfigure(0, weight=1)
        self._db_var = ctk.StringVar(value="—")
        ctk.CTkLabel(
            db_row,
            textvariable=self._db_var,
            font=ctk.CTkFont(size=11),
            wraplength=400,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            db_row,
            text="Copy",
            width=64,
            command=lambda: self._copy_clipboard(self._db_var.get()),
        ).grid(row=0, column=1, padx=(8, 0))

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

    def _build_session_overview(self) -> None:
        overview = ctk.CTkFrame(self, corner_radius=12)
        self._diag_overview_frame = overview
        overview.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 12))
        overview.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            overview,
            text="Session Overview",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        # Session selector
        selector = ctk.CTkFrame(overview, fg_color="transparent")
        selector.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        selector.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(selector, text="View session:").pack(side="left", padx=(0, 8))
        self._session_var = ctk.StringVar(value="")
        self._session_combo = ctk.CTkComboBox(
            selector,
            variable=self._session_var,
            values=[],
            width=300,
            command=self._on_session_change,
        )
        self._session_combo.pack(side="left", fill="x", expand=True)

        # Overview fields
        self._overview_vars: dict[str, ctk.StringVar] = {}
        fields = [
            ("Session ID", "—"),
            ("Config Hash", "—"),
            ("Schema Version", "—"),
            ("Root Fingerprint", "—"),
        ]

        for i, (label, default) in enumerate(fields):
            ctk.CTkLabel(
                overview,
                text=label + ":",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray50", "gray60"),
            ).grid(row=2 + i, column=0, sticky="w", padx=(0, 12), pady=2)

            var = ctk.StringVar(value=default)
            ctk.CTkLabel(
                overview,
                textvariable=var,
                font=ctk.CTkFont(size=11),
                wraplength=500,
                anchor="w",
            ).grid(row=2 + i, column=1, sticky="w", padx=(12, 0), pady=2)

            self._overview_vars[label] = var

    def _build_tabbed_content(self) -> None:
        # Tab view container
        tab_container = ctk.CTkFrame(self, corner_radius=12)
        self._diag_tab_container = tab_container
        tab_container.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        tab_container.grid_columnconfigure(0, weight=1)

        # Custom tab buttons (since CTK doesn't have notebook)
        self._tab_buttons: dict[str, ctk.CTkButton] = {}
        tabs = [
            ("phases", "Phases"),
            ("events", "Events"),
            ("artifacts", "Artifacts"),
            ("compatibility", "Compatibility"),
        ]

        button_row = ctk.CTkFrame(tab_container, fg_color="transparent")
        button_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        button_row.grid_columnconfigure(0, weight=1)

        for i, (tab_id, tab_name) in enumerate(tabs):
            btn = ctk.CTkButton(
                button_row,
                text=tab_name,
                width=120,
                command=lambda t=tab_id: self._switch_tab(t),
            )
            btn.grid(row=0, column=i, padx=(0, 8), sticky="w")
            self._tab_buttons[tab_id] = btn

        # Set default tab
        self._current_tab = "phases"
        self._tab_buttons["phases"].configure(fg_color=("gray60", "gray40"))

        # Tab content area
        self._tab_content = ctk.CTkFrame(tab_container, fg_color="transparent")
        self._tab_content.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self._tab_content.grid_columnconfigure(0, weight=1)

        # Build tab content areas
        self._build_phases_tab()
        self._build_events_tab()
        self._build_artifacts_tab()
        self._build_compatibility_tab()

    def _switch_tab(self, tab_id: str) -> None:
        """Switch between tab views."""
        # Reset all button colors
        for btn in self._tab_buttons.values():
            btn.configure(fg_color=("gray35", "gray50"))

        # Highlight selected tab
        self._tab_buttons[tab_id].configure(fg_color=("gray60", "gray40"))
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

    def _build_phases_tab(self) -> None:
        """Build phases tab content area."""
        pass  # Content built dynamically when tab is selected

    def _build_events_tab(self) -> None:
        """Build events tab content area."""
        pass  # Content built dynamically when tab is selected

    def _build_artifacts_tab(self) -> None:
        """Build artifacts tab content area."""
        pass  # Content built dynamically when tab is selected

    def _build_compatibility_tab(self) -> None:
        """Build compatibility tab content area."""
        pass  # Content built dynamically when tab is selected

    def _build_phases_content(self) -> None:
        """Build the phases table content."""
        ctk.CTkLabel(
            self._tab_content,
            text="Scan Phases",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        # Phases table (scrollable)
        self._phases_scroll = ctk.CTkScrollableFrame(self._tab_content, corner_radius=8)
        self._phases_scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self._phases_scroll.grid_columnconfigure(0, weight=1)

    def _build_events_content(self) -> None:
        """Build the events log content."""
        # Header with filter
        header = ctk.CTkFrame(self._tab_content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Recent Events",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        # Clear button
        ctk.CTkButton(
            header,
            text="Clear Buffer",
            width=120,
            fg_color=("#E67E22", "#D35400"),
            command=self._clear_recorder,
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))

        # Events log
        self._events_scroll = ctk.CTkTextbox(
            self._tab_content,
            wrap="word",
            # Use fixed hex colors so CTk theme switching doesn't remap "grayXX" token names.
            fg_color=("#F3F4F6", "#11151d"),
            text_color=("#111827", "#E5E7EB"),
        )
        self._events_scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))

    def _build_artifacts_content(self) -> None:
        """Build the artifacts listing content."""
        ctk.CTkLabel(
            self._tab_content,
            text="Scan Artifacts",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        # Artifacts list
        self._artifacts_scroll = ctk.CTkScrollableFrame(self._tab_content, corner_radius=8)
        self._artifacts_scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self._artifacts_scroll.grid_columnconfigure(0, weight=1)

    def _build_compatibility_content(self) -> None:
        """Build the compatibility checks content."""
        ctk.CTkLabel(
            self._tab_content,
            text="Compatibility Checks",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        # Compatibility table
        self._compat_scroll = ctk.CTkScrollableFrame(self._tab_content, corner_radius=8)
        self._compat_scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self._compat_scroll.grid_columnconfigure(0, weight=1)

    def _clear_recorder(self) -> None:
        """Clear the diagnostics recorder buffer."""
        if not messagebox.askyesno(
            "Clear Diagnostics Buffer",
            "Clear all in-memory recorder events and category counts?\n\n"
            "Scan history on disk is not affected. A new scan also clears this buffer.",
            icon="warning"
        ):
            return
        get_diagnostics_recorder().clear()
        self.reload()

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

        # Use fast lookup from cache instead of O(n) loop
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
        # Ensure widget exists - create default tab content if needed
        if not hasattr(self, '_phases_scroll') or self._phases_scroll is None:
            # Clear and build phases content first
            for widget in self._tab_content.winfo_children():
                widget.destroy()
            self._build_phases_content()

        # Clear existing content
        for widget in self._phases_scroll.winfo_children():
            widget.destroy()

        if not self._selected_session_id:
            ctk.CTkLabel(
                self._phases_scroll,
                text="Select a session to view phases.",
                text_color=("gray40", "gray70"),
            ).pack(pady=20)
            return

        persist = getattr(self._coordinator, "persistence", None)
        if persist is None:
            ctk.CTkLabel(
                self._phases_scroll,
                text="Persistence not available.",
                text_color=("gray40", "gray70"),
            ).pack(pady=20)
            return
        try:
            checkpoints = persist.checkpoint_repo.list_for_session(self._selected_session_id)
        except Exception as ex:
            _log.warning("list phase checkpoints: %s", ex)
            checkpoints = []

        if not checkpoints:
            ctk.CTkLabel(
                self._phases_scroll,
                text=(
                    "No phase checkpoints in the database for this session. "
                    "Completed scans often only persist final results; run an in-progress or resumable scan to see rows here."
                ),
                text_color=("gray40", "gray70"),
                wraplength=560,
                justify="left",
            ).pack(pady=16, padx=8, anchor="w")
            return

        for cp in checkpoints:
            fr = ctk.CTkFrame(self._phases_scroll, corner_radius=6)
            fr.pack(fill="x", pady=4, padx=4)
            title = f"{cp.phase_name.value} — {cp.status.value}"
            ctk.CTkLabel(fr, text=title, font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(8, 2))
            tot = cp.total_units if cp.total_units is not None else "—"
            sub = f"Units: {cp.completed_units} / {tot}  ·  Updated: {cp.updated_at.isoformat()[:19]}"
            ctk.CTkLabel(
                fr,
                text=sub,
                text_color=("gray40", "gray70"),
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=10, pady=(0, 8))

    def _populate_events(self) -> None:
        """Populate the events log."""
        # Ensure widget exists
        if not hasattr(self, '_events_scroll') or self._events_scroll is None:
            for widget in self._tab_content.winfo_children():
                widget.destroy()
            self._build_events_content()

        # Clear existing content
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
        # Ensure widget exists
        if not hasattr(self, '_artifacts_scroll') or self._artifacts_scroll is None:
            for widget in self._tab_content.winfo_children():
                widget.destroy()
            self._build_artifacts_content()

        # Clear existing content
        for widget in self._artifacts_scroll.winfo_children():
            widget.destroy()

        if not self._selected_session_id:
            ctk.CTkLabel(
                self._artifacts_scroll,
                text="Select a session to view artifacts.",
                text_color=("gray40", "gray70"),
            ).pack(pady=20)
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
            ctk.CTkLabel(
                self._artifacts_scroll,
                text="No checkpoint files on disk whose names include this session id. Checkpoints may live only in SQLite for this run.",
                text_color=("gray40", "gray70"),
                wraplength=520,
                justify="left",
            ).pack(pady=16, padx=8, anchor="w")
            return

        for p in files:
            row = ctk.CTkFrame(self._artifacts_scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=p.name, font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
            ctk.CTkLabel(
                row,
                text=str(p),
                font=ctk.CTkFont(size=10),
                text_color=("gray40", "gray70"),
            ).pack(anchor="w")

    def _populate_compatibility(self) -> None:
        """Populate the compatibility checks."""
        # Ensure widget exists
        if not hasattr(self, '_compat_scroll') or self._compat_scroll is None:
            for widget in self._tab_content.winfo_children():
                widget.destroy()
            self._build_compatibility_content()

        # Clear existing content
        for widget in self._compat_scroll.winfo_children():
            widget.destroy()

        if not self._selected_session_id:
            ctk.CTkLabel(
                self._compat_scroll,
                text="Select a session to view compatibility.",
                text_color=("gray40", "gray70"),
            ).pack(pady=20)
            return

        session_data = self._history_lookup.get(self._selected_session_id)
        dv = (session_data or {}).get("deletion_verification_summary") or {}
        bm = (session_data or {}).get("benchmark_summary") or {}

        if not dv and not bm:
            ctk.CTkLabel(
                self._compat_scroll,
                text="No deletion-verification or benchmark snapshot stored for this session (older runs may omit these fields).",
                text_color=("gray40", "gray70"),
                wraplength=520,
                justify="left",
            ).pack(pady=16, padx=8, anchor="w")
            return

        tb = ctk.CTkTextbox(
            self._compat_scroll,
            wrap="word",
            height=220,
            fg_color=("#F3F4F6", "#11151d"),
            text_color=("#111827", "#E5E7EB"),
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

    def reload(self) -> None:
        """Reload all diagnostics data."""
        # Update runtime status
        scanning = getattr(self._coordinator, 'is_scanning', False)
        self._scanning_var.set("Yes" if scanning else "No")

        active_id = getattr(self._coordinator, 'get_active_scan_id', lambda: "—")()
        self._active_id_var.set((active_id[:16] + "…") if active_id and len(active_id) > 16 else (active_id or "—"))

        persistence = getattr(self._coordinator, 'persistence', None)
        db_path = persistence.db_path if persistence else "—"
        self._db_var.set(str(db_path))

        # Update session selector and cache for performance
        try:
            self._history_cache = self._coordinator.get_history(limit=50) or []
            self._history_lookup = {h.get("scan_id", ""): h for h in self._history_cache if h.get("scan_id")}
            session_ids = list(self._history_lookup.keys())
            self._session_combo.configure(values=session_ids)

            if session_ids and not self._session_var.get():
                self._session_var.set(session_ids[0])
                self._selected_session_id = session_ids[0]
        except Exception:
            self._history_cache = []
            self._history_lookup = {}

        self._update_session_overview(self._selected_session_id)
        self._refresh_tab_content()

    def _export_json(self) -> None:
        """Export diagnostics to JSON."""
        path = filedialog.asksaveasfilename(
            title="Export diagnostics",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        # Convert DiagnosticEntry objects to dictionaries for proper JSON serialization
        events = []
        for event in get_diagnostics_recorder().get_recent(100):
            events.append({
                "category": event.category,
                "message": event.message,
                "detail": event.detail,
                "timestamp": event.timestamp,
                "wall_time": event.wall_time,
            })

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
