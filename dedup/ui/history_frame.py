"""
DEDUP History Frame - View past scans.

Simple list of previous scans with ability to load results.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, List, Dict, Any

from ..orchestration.coordinator import ScanCoordinator
from ..infrastructure.utils import format_bytes, format_duration


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
        on_load_scan: Callable[[str], None]
    ):
        super().__init__(parent, padding="20")
        
        self.coordinator = coordinator
        self.on_load_scan = on_load_scan
        
        self.history_items: List[Dict[str, Any]] = []
        
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
        columns = ("date", "files", "duplicates", "reclaimable", "status")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse"
        )
        
        self.tree.heading("date", text="Date")
        self.tree.heading("files", text="Files Scanned")
        self.tree.heading("duplicates", text="Duplicates")
        self.tree.heading("reclaimable", text="Reclaimable")
        self.tree.heading("status", text="Status")
        
        self.tree.column("date", width=150)
        self.tree.column("files", width=100, anchor="e")
        self.tree.column("duplicates", width=80, anchor="e")
        self.tree.column("reclaimable", width=100, anchor="e")
        self.tree.column("status", width=80)
        
        # Scrollbars
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        # Actions frame
        actions_frame = ttk.Frame(self)
        actions_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        
        self.load_btn = ttk.Button(
            actions_frame,
            text="Load Selected",
            command=self._on_load
        )
        self.load_btn.pack(side=tk.LEFT)
        
        self.delete_btn = ttk.Button(
            actions_frame,
            text="Delete Selected",
            command=self._on_delete
        )
        self.delete_btn.pack(side=tk.LEFT, padx=(10, 0))
        
        ttk.Button(
            actions_frame,
            text="Refresh",
            command=self._refresh
        ).pack(side=tk.RIGHT)
    
    def _refresh(self):
        """Refresh the history list."""
        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Load history
        self.history_items = self.coordinator.get_history(limit=100)
        
        # Populate tree
        for item in self.history_items:
            started = item.get("started_at", "Unknown")
            if started and "T" in started:
                # Format ISO datetime
                started = started.replace("T", " ")[:19]
            
            files = item.get("files_scanned", 0)
            duplicates = item.get("duplicates_found", 0)
            reclaimable = item.get("reclaimable_bytes", 0)
            status = item.get("status", "unknown")
            
            self.tree.insert(
                "",
                "end",
                iid=item["scan_id"],
                values=(
                    started,
                    f"{files:,}",
                    f"{duplicates:,}",
                    format_bytes(reclaimable),
                    status
                )
            )
    
    def _on_load(self):
        """Handle load button."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Load", "Please select a scan to load")
            return
        
        scan_id = selection[0]
        self.on_load_scan(scan_id)
    
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
