"""
CustomTkinter History page — trustworthy daily driver.

Features:
- Summary stats bar (total scans, avg duration, avg reclaimable)
- Filterable session list with search
- Resumable scan clarity
- Session detail panel
- Export functionality
- Load/Resume/Delete actions
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

from ..utils.formatting import fmt_bytes, fmt_int, fmt_duration


class HistoryPageCTK(ctk.CTkFrame):
    """Scan history page with full P1 functionality."""

    def __init__(
        self,
        parent,
        *,
        get_history: Callable[[], list[dict[str, Any]]],
        on_load_scan: Callable[[str], None],
        on_resume_scan: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._get_history = get_history
        self._on_load_scan = on_load_scan
        self._on_resume_scan = on_resume_scan
        self._selected_scan_id: Optional[str] = None
        self._scan_data: list[dict[str, Any]] = []
        self._filtered_data: list[dict[str, Any]] = []
        
        # Filter state
        self._show_resumable_only = ctk.BooleanVar(value=False)
        self._show_failed_only = ctk.BooleanVar(value=False)
        self._search_text = ctk.StringVar(value="")
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build()

    def _build(self) -> None:
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
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        header.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            header,
            text="Scan History",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        
        ctk.CTkLabel(
            header,
            text="Saved scans from this device. Select a session to view details or load into Review.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        
        # Refresh button
        ctk.CTkButton(
            header,
            text="Refresh",
            width=100,
            command=self.reload,
        ).grid(row=0, column=1, sticky="e", padx=(0, 20))

    def _build_summary(self) -> None:
        summary = ctk.CTkFrame(self, corner_radius=12)
        summary.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        summary.grid_columnconfigure(0, weight=1)
        
        # Summary cards container
        cards = ctk.CTkFrame(summary, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        cards.grid_columnconfigure(0, weight=1)
        cards.grid_columnconfigure(1, weight=1)
        cards.grid_columnconfigure(2, weight=1)
        
        # Total scans card
        total_card = ctk.CTkFrame(cards, corner_radius=8)
        total_card.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkLabel(total_card, text="Total Scans", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(8, 2))
        self._total_label = ctk.CTkLabel(total_card, text="0", font=ctk.CTkFont(size=20, weight="bold"))
        self._total_label.pack(pady=(0, 8))
        
        # Avg duration card
        dur_card = ctk.CTkFrame(cards, corner_radius=8)
        dur_card.grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkLabel(dur_card, text="Avg Duration", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(8, 2))
        self._duration_label = ctk.CTkLabel(dur_card, text="—", font=ctk.CTkFont(size=20, weight="bold"))
        self._duration_label.pack(pady=(0, 8))
        
        # Avg reclaimable card
        rec_card = ctk.CTkFrame(cards, corner_radius=8)
        rec_card.grid(row=0, column=2, sticky="ew", padx=(8, 0))
        ctk.CTkLabel(rec_card, text="Avg Reclaimable", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(8, 2))
        self._reclaim_label = ctk.CTkLabel(rec_card, text="—", font=ctk.CTkFont(size=20, weight="bold"))
        self._reclaim_label.pack(pady=(0, 8))

    def _build_table_section(self) -> None:
        table_section = ctk.CTkFrame(self, corner_radius=12)
        table_section.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 12))
        table_section.grid_columnconfigure(0, weight=1)
        table_section.grid_rowconfigure(1, weight=1)
        
        # Filters toolbar
        filters = ctk.CTkFrame(table_section, fg_color="transparent")
        filters.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        filters.grid_columnconfigure(1, weight=1)
        
        # Resumable only checkbox
        ctk.CTkCheckBox(
            filters,
            text="Resumable only",
            variable=self._show_resumable_only,
            command=self._apply_filters,
        ).grid(row=0, column=0, sticky="w")
        
        # Failed only checkbox
        ctk.CTkCheckBox(
            filters,
            text="Failed only",
            variable=self._show_failed_only,
            command=self._apply_filters,
        ).grid(row=0, column=1, sticky="w", padx=(20, 0))
        
        # Search box
        search_frame = ctk.CTkFrame(filters, fg_color="transparent")
        search_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        search_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(search_frame, text="Search:").pack(side="left", padx=(0, 8))
        ctk.CTkEntry(
            search_frame,
            textvariable=self._search_text,
            placeholder_text="Scan ID, root path, or status...",
            command=self._apply_filters,
        ).pack(side="left", fill="x", expand=True)
        
        # Scrollable table
        self._scroll = ctk.CTkScrollableFrame(table_section, corner_radius=8)
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self._scroll.grid_columnconfigure(0, weight=1)
        
        # Action buttons
        actions = ctk.CTkFrame(table_section, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        
        self._load_btn = ctk.CTkButton(
            actions,
            text="Load Results",
            width=120,
            command=self._load_selected,
            state="disabled",
        )
        self._load_btn.pack(side="left", padx=(0, 8))
        
        self._resume_btn = ctk.CTkButton(
            actions,
            text="Resume Scan",
            width=120,
            command=self._resume_selected,
            state="disabled",
        )
        self._resume_btn.pack(side="left", padx=(0, 8))
        
        self._delete_btn = ctk.CTkButton(
            actions,
            text="Delete Entry",
            width=120,
            fg_color=("#E74C3C", "#C0392B"),
            command=self._delete_selected,
            state="disabled",
        )
        self._delete_btn.pack(side="right")
        
        self._export_btn = ctk.CTkButton(
            actions,
            text="Export JSON",
            width=120,
            fg_color=("gray35", "gray50"),
            command=self._export_json,
        )
        self._export_btn.pack(side="right", padx=(0, 8))

    def _build_detail_panel(self) -> None:
        detail = ctk.CTkFrame(self, corner_radius=12)
        detail.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 20))
        detail.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            detail,
            text="Session Details",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))
        
        # Detail fields container
        self._detail_container = ctk.CTkFrame(detail, fg_color="transparent")
        self._detail_container.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._detail_container.grid_columnconfigure(1, weight=1)
        
        # Detail labels
        self._detail_vars: dict[str, ctk.StringVar] = {}
        fields = [
            ("Session ID", "—"),
            ("Status", "—"),
            ("Started", "—"),
            ("Duration", "—"),
            ("Files Scanned", "—"),
            ("Duplicates Found", "—"),
            ("Reclaimable Space", "—"),
            ("Root Paths", "—"),
            ("Config Hash", "—"),
        ]
        
        for i, (label, default) in enumerate(fields):
            ctk.CTkLabel(
                self._detail_container,
                text=label + ":",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray50", "gray60"),
            ).grid(row=i, column=0, sticky="w", padx=(0, 12), pady=2)
            
            var = ctk.StringVar(value=default)
            ctk.CTkLabel(
                self._detail_container,
                textvariable=var,
                font=ctk.CTkFont(size=11),
                wraplength=400,
                anchor="w",
            ).grid(row=i, column=1, sticky="w", pady=2)
            
            self._detail_vars[label] = var

    def reload(self) -> None:
        """Reload history data and refresh UI."""
        self._scan_data = self._get_history()
        self._apply_filters()
        self._update_summary()

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
        # Clear existing rows
        for widget in self._scroll.winfo_children():
            widget.destroy()
        
        if not self._filtered_data:
            ctk.CTkLabel(
                self._scroll, 
                text="No scans match current filters.", 
                text_color=("gray40", "gray70")
            ).pack(pady=20)
            return
        
        # Create rows
        for i, row in enumerate(self._filtered_data):
            self._create_table_row(i, row)

    def _create_table_row(self, index: int, data: dict[str, Any]) -> None:
        """Create a single table row."""
        sid = str(data.get("scan_id") or "")
        short = (sid[:12] + "…") if len(sid) > 12 else sid or "—"
        started = str(data.get("started_at") or "—")[:19]
        status = str(data.get("status") or "—")
        files_n = int(data.get("files_scanned") or 0)
        dups = int(data.get("duplicates_found") or 0)
        reclaim = int(data.get("reclaimable_bytes") or 0)
        roots = data.get("roots") or []
        root_hint = ""
        if roots:
            try:
                root_hint = Path(str(roots[0])).name[:40]
            except Exception:
                root_hint = str(roots[0])[:40]

        # Row frame
        row_frame = ctk.CTkFrame(self._scroll, corner_radius=8)
        row_frame.pack(fill="x", padx=8, pady=4)
        row_frame.grid_columnconfigure(0, weight=1)
        
        # Clickable row area
        def on_click(event=None):
            self._select_scan(sid, data)
            
        row_frame.bind("<Button-1>", on_click)
        
        # Header with status indicator
        header = ctk.CTkFrame(row_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        header.grid_columnconfigure(0, weight=1)
        
        # Status color
        status_color = ("#27AE60", "#2ECC71") if "completed" in status.lower() else ("#E67E22", "#E74C3C")
        ctk.CTkLabel(header, text=short, font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(
            header, 
            text=f"  ·  {status}", 
            text_color=status_color,
            font=ctk.CTkFont(size=11)
        ).pack(side="left")
        
        # Meta info
        meta = (
            f"{started}  ·  {fmt_int(files_n)} files  ·  {fmt_int(dups)} groups  ·  "
            f"{fmt_bytes(reclaim)} reclaimable"
        )
        if root_hint:
            meta += f"\nRoot: {root_hint}"
        
        body = ctk.CTkFrame(row_frame, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            body, 
            text=meta, 
            text_color=("gray40", "gray70"), 
            justify="left", 
            anchor="w",
            font=ctk.CTkFont(size=10)
        ).grid(row=0, column=0, sticky="w")

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
        self._detail_vars["Session ID"].set(str(data.get("scan_id", "—")))
        self._detail_vars["Status"].set(str(data.get("status", "—")))
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
            "This only removes the history entry; scanned files remain untouched.",
            icon="warning"
        ):
            # TODO: Implement deletion via coordinator
            messagebox.showinfo("Not Implemented", "Deletion will be implemented in coordinator.")

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
