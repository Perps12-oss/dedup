"""
DEDUP History Frame - View past scans.

Simple list of previous scans with ability to load results.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, List, Dict, Any, Optional

from ..orchestration.coordinator import ScanCoordinator
from ..infrastructure.utils import format_bytes, format_duration
from ..infrastructure.trash import list_dedup_trash, empty_dedup_trash


class HistoryFrame(ttk.Frame):
    """
    Scan history screen.
    
    Displays:
    - List of past scans
    - Scan date, files scanned, duplicates found
    - Load and delete actions
    """
    
    def __init__(
        self,
        parent,
        coordinator: ScanCoordinator,
        on_load_scan: Callable[[str], None],
        on_resume_scan: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(parent, padding="20")
        
        self.coordinator = coordinator
        self.on_load_scan = on_load_scan
        self.on_resume_scan = on_resume_scan
        
        self.history_items: List[Dict[str, Any]] = []
        self._resumable_ids: set = set()
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the UI components."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        
        # Title
        title = ttk.Label(
            self,
            text="Scan History",
            font=("TkDefaultFont", 16, "bold")
        )
        title.grid(row=0, column=0, sticky="w", pady=(0, 10))
        
        # Description
        desc = ttk.Label(
            self,
            text="View and manage previous scans. Click 'Load' to review results.",
            wraplength=500
        )
        desc.grid(row=1, column=0, sticky="w", pady=(0, 10))
        
        # History list
        list_frame = ttk.Frame(self)
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # Treeview for history
        columns = ("date", "roots", "files", "duplicates", "reclaimable", "status")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse"
        )
        
        self.tree.heading("date", text="Date")
        self.tree.heading("roots", text="Roots")
        self.tree.heading("files", text="Files")
        self.tree.heading("duplicates", text="Duplicates")
        self.tree.heading("reclaimable", text="Reclaimable")
        self.tree.heading("status", text="Status")
        
        self.tree.column("date", width=140)
        self.tree.column("roots", width=200)
        self.tree.column("files", width=80, anchor="e")
        self.tree.column("duplicates", width=70, anchor="e")
        self.tree.column("reclaimable", width=90, anchor="e")
        self.tree.column("status", width=72)
        
        # Scrollbars
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_change)

        # Actions frame
        actions_frame = ttk.Frame(self)
        actions_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        
        self.load_btn = ttk.Button(
            actions_frame,
            text="Load Selected",
            command=self._on_load
        )
        self.load_btn.pack(side=tk.LEFT)

        self.resume_btn = ttk.Button(
            actions_frame,
            text="Resume Scan",
            command=self._on_resume
        )
        self.resume_btn.pack(side=tk.LEFT, padx=(10, 0))
        
        self.delete_btn = ttk.Button(
            actions_frame,
            text="Delete Selected",
            command=self._on_delete
        )
        self.delete_btn.pack(side=tk.LEFT, padx=(10, 0))
        
        ttk.Button(
            actions_frame,
            text="Empty Trash",
            command=self._on_empty_trash
        ).pack(side=tk.RIGHT, padx=(10, 0))

        ttk.Button(
            actions_frame,
            text="Refresh",
            command=self._refresh
        ).pack(side=tk.RIGHT)
    
    def _on_selection_change(self, event=None):
        """Enable/disable Resume based on selection."""
        if not self.on_resume_scan:
            self.resume_btn.config(state="disabled")
            return
        sel = self.tree.selection()
        if not sel:
            self.resume_btn.config(state="disabled")
            return
        scan_id = sel[0]
        self.resume_btn.config(state="normal" if scan_id in self._resumable_ids else "disabled")

    def _refresh(self):
        """Refresh the history list."""
        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self._resumable_ids = set(self.coordinator.get_resumable_scan_ids())
        # Load history
        self.history_items = self.coordinator.get_history(limit=100)
        
        # Populate tree
        resumable = set(self.coordinator.get_resumable_scan_ids())
        for item in self.history_items:
            started = item.get("started_at", "Unknown")
            if started and "T" in str(started):
                started = str(started).replace("T", " ")[:19]
            roots = item.get("roots") or []
            roots_str = ", ".join(Path(r).name for r in roots[:2]) if roots else "—"
            if len(roots) > 2:
                roots_str += "…"
            files = item.get("files_scanned", 0)
            duplicates = item.get("duplicates_found", 0)
            reclaimable = item.get("reclaimable_bytes", 0)
            status = item.get("status", "unknown")
            if item.get("scan_id") in resumable:
                status = "resumable"
            self.tree.insert(
                "",
                "end",
                iid=item["scan_id"],
                values=(
                    started,
                    roots_str,
                    f"{files:,}",
                    f"{duplicates:,}",
                    format_bytes(reclaimable),
                    status
                )
            )
        self._on_selection_change()

    def _on_resume(self):
        """Start resuming the selected scan from checkpoint."""
        selection = self.tree.selection()
        if not selection or not self.on_resume_scan:
            return
        scan_id = selection[0]
        if scan_id not in self._resumable_ids:
            messagebox.showinfo("Resume", "No checkpoint found for this scan.")
            return
        self.on_resume_scan(scan_id)
    
    def _on_load(self):
        """Handle load button."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Load", "Please select a scan to load")
            return
        
        scan_id = selection[0]
        self.on_load_scan(scan_id)
    
    def _on_empty_trash(self):
        """Empty DEDUP fallback trash folder (files moved to trash by DEDUP only)."""
        count, total_bytes, _ = list_dedup_trash()
        if count == 0:
            messagebox.showinfo("Empty Trash", "DEDUP trash is already empty.")
            return
        confirm = messagebox.askyesno(
            "Empty Trash",
            f"DEDUP trash contains {count} file(s) ({format_bytes(total_bytes)}).\n\n"
            "Permanently delete these files? This cannot be undone."
        )
        if not confirm:
            return
        deleted, failed = empty_dedup_trash()
        if failed:
            messagebox.showwarning(
                "Empty Trash",
                f"Deleted: {deleted} file(s). Failed: {failed}."
            )
        else:
            messagebox.showinfo("Empty Trash", f"Permanently deleted {deleted} file(s).")

    def _on_delete(self):
        """Handle delete button."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Delete", "Please select a scan to delete")
            return
        
        scan_id = selection[0]
        
        confirm = messagebox.askyesno(
            "Confirm Delete",
            "Delete this scan from history?\n\n"
            "This will only remove the history entry, not any files."
        )
        
        if confirm:
            if self.coordinator.delete_scan(scan_id):
                self._refresh()
                messagebox.showinfo("Deleted", "Scan removed from history")
            else:
                messagebox.showerror("Error", "Failed to delete scan")
    
    def on_show(self):
        """Called when frame is shown."""
        self._refresh()
