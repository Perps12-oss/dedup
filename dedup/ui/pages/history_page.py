"""
History Page — Session archive, resume control, long-term visibility.

Layout:
  Row 0: Summary stats bar
  Row 1: Session table (full-width)
  Row 2: Session detail panel (expandable)
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Optional

from ..components import DataTable, SectionCard, MetricCard, EmptyState
from ..viewmodels.history_vm import HistoryVM, SessionEntry
from ..utils.formatting import fmt_bytes, fmt_int, fmt_duration, fmt_dt
from ..utils.icons import IC
from ...orchestration.coordinator import ScanCoordinator
from ...infrastructure.trash import list_dedup_trash, empty_dedup_trash


class HistoryPage(ttk.Frame):
    """Scan history page."""

    def __init__(self, parent,
                 coordinator: ScanCoordinator,
                 on_load_scan: Callable[[str], None],
                 on_resume_scan: Callable[[str], None],
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.coordinator = coordinator
        self.on_load_scan = on_load_scan
        self.on_resume_scan = on_resume_scan
        self.vm = HistoryVM()
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # ── Page header ──────────────────────────────────────────────
        hdr = ttk.Frame(self, padding=(16, 12, 16, 0))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        ttk.Label(hdr, text=f"{IC.HISTORY}  History",
                  font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(hdr, text=f"{IC.REFRESH} Refresh",
                   style="Ghost.TButton",
                   command=self._refresh).grid(row=0, column=2, sticky="e")

        # ── Summary stats strip ──────────────────────────────────────
        stats_card = SectionCard(self, title="Summary")
        stats_card.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        self._build_summary(stats_card.body)

        # ── Session table ─────────────────────────────────────────────
        table_card = SectionCard(self, title=f"{IC.FILE}  Sessions")
        table_card.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 8))
        table_card.body.rowconfigure(1, weight=1)
        self._build_table(table_card.body)

        # ── Detail panel ──────────────────────────────────────────────
        detail_card = SectionCard(self, title=f"{IC.INFO}  Session Detail")
        detail_card.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._build_detail(detail_card.body)

    def _build_summary(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)
        body.columnconfigure(3, weight=1)
        self._summary_cards: dict[str, MetricCard] = {}
        specs = [
            ("total",    f"{IC.FILE}  Total Scans",       "0",  "neutral"),
            ("avg_dur",  f"{IC.SPEED} Avg Duration",      "—",  "neutral"),
            ("avg_rec",  f"{IC.RECLAIM} Avg Reclaimable", "—",  "positive"),
            ("resume",   f"{IC.RESUME} Resumable",        "0",  "accent"),
        ]
        for i, (key, label, val, variant) in enumerate(specs):
            c = MetricCard(body, label=label, value=val, variant=variant, width=0)
            c.grid(row=0, column=i, sticky="nsew", padx=4)
            self._summary_cards[key] = c

    def _build_table(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        # Filter toolbar
        toolbar = ttk.Frame(body, style="Panel.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._resumable_var = tk.BooleanVar(value=False)
        self._failed_var    = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Resumable only",
                        variable=self._resumable_var,
                        command=self._apply_filter).pack(side="left")
        ttk.Checkbutton(toolbar, text="Failed only",
                        variable=self._failed_var,
                        command=self._apply_filter).pack(side="left", padx=(10, 0))
        ttk.Button(toolbar, text=f"{IC.TRASH} Empty Trash",
                   style="Ghost.TButton",
                   command=self._on_empty_trash).pack(side="right")

        self._table = DataTable(
            body,
            columns=[
                ("date",     "Date",        140, "w"),
                ("status",   "Status",       72, "w"),
                ("resume",   "Resume",       60, "center"),
                ("files",    "Files",        80, "e"),
                ("groups",   "Groups",       70, "e"),
                ("reclaim",  "Reclaimable",  90, "e"),
                ("warnings", "Warns",        50, "center"),
            ],
            height=12,
            on_select=self._on_session_select,
        )
        self._table.grid(row=1, column=0, sticky="nsew")

        # Action buttons below table
        act = ttk.Frame(body, style="Panel.TFrame")
        act.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self._load_btn = ttk.Button(act, text=f"{IC.FILE} Load Results",
                                    style="Ghost.TButton",
                                    command=self._on_load,
                                    state="disabled")
        self._load_btn.pack(side="left")
        self._resume_btn = ttk.Button(act, text=f"{IC.RESUME} Resume Scan",
                                      style="Accent.TButton",
                                      command=self._on_resume,
                                      state="disabled")
        self._resume_btn.pack(side="left", padx=(8, 0))
        self._del_btn = ttk.Button(act, text=f"{IC.TRASH} Delete Entry",
                                   style="Ghost.TButton",
                                   command=self._on_delete,
                                   state="disabled")
        self._del_btn.pack(side="right")

    def _build_detail(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        self._detail_vars: dict[str, tk.StringVar] = {}
        fields = [
            ("Session ID", "—"), ("Status", "—"),
            ("Started", "—"),   ("Duration", "—"),
            ("Config Hash", "—"), ("Roots", "—"),
            ("Resume Outcome", "—"), ("Resume Reason", "—"),
        ]
        for i, (label, default) in enumerate(fields):
            col = i % 2
            row = i // 2
            fr = ttk.Frame(body, style="Panel.TFrame")
            fr.grid(row=row, column=col, sticky="ew", padx=4, pady=2)
            ttk.Label(fr, text=label + ":", style="Panel.Muted.TLabel",
                      font=("Segoe UI", 8)).pack(side="left")
            var = tk.StringVar(value=default)
            ttk.Label(fr, textvariable=var, style="Panel.TLabel",
                      font=("Segoe UI", 8, "bold"),
                      wraplength=280).pack(side="left", padx=(4, 0))
            self._detail_vars[label] = var

    # ----------------------------------------------------------------
    def on_show(self):
        self._refresh()

    def _refresh(self):
        self.vm.refresh(self.coordinator)
        self._update_summary()
        self._populate_table()

    def _update_summary(self):
        self._summary_cards["total"].update(fmt_int(self.vm.total_scans))
        self._summary_cards["avg_dur"].update(fmt_duration(self.vm.avg_duration_s))
        self._summary_cards["avg_rec"].update(fmt_bytes(self.vm.avg_reclaim_bytes))
        self._summary_cards["resume"].update(fmt_int(self.vm.resumable_count))

    def _populate_table(self):
        self._table.clear()
        for e in self.vm.filtered_sessions:
            resume_icon = IC.OK if e.is_resumable else "—"
            status_icon = (IC.OK if e.status == "completed" else
                           IC.WARN if e.status in ("interrupted", "resumable") else
                           IC.ERROR if e.status == "failed" else "—")
            tag = ("safe"   if e.status == "completed"  else
                   "warn"   if e.is_resumable             else
                   "danger" if e.status == "failed"       else "")
            roots = ", ".join(Path(r).name for r in e.roots[:2])
            if len(e.roots) > 2:
                roots += "…"
            self._table.insert_row(
                e.scan_id,
                (e.started_at, f"{status_icon} {e.status}", resume_icon,
                 fmt_int(e.files_scanned), fmt_int(e.duplicates_found),
                 fmt_bytes(e.reclaimable_bytes), str(e.warning_count)),
                tags=(tag,) if tag else (),
            )
        self._load_btn.configure(state="disabled")
        self._resume_btn.configure(state="disabled")
        self._del_btn.configure(state="disabled")

    def _apply_filter(self):
        self.vm.show_resumable_only = self._resumable_var.get()
        self.vm.show_failed_only    = self._failed_var.get()
        self._populate_table()

    def _on_session_select(self, scan_id: str):
        self.vm.selected_id = scan_id
        entry = self.vm.selected_session
        if not entry:
            return
        self._update_detail(entry)
        self._load_btn.configure(state="normal")
        self._resume_btn.configure(
            state="normal" if entry.is_resumable else "disabled")
        self._del_btn.configure(state="normal")

    def _update_detail(self, e: SessionEntry):
        self._detail_vars["Session ID"].set(e.scan_id[:20] + "…" if len(e.scan_id) > 20 else e.scan_id)
        self._detail_vars["Status"].set(e.status)
        self._detail_vars["Started"].set(e.started_at)
        self._detail_vars["Duration"].set(fmt_duration(e.duration_s))
        self._detail_vars["Config Hash"].set(e.config_hash[:12] if e.config_hash else "—")
        self._detail_vars["Roots"].set(
            ", ".join(Path(r).name for r in e.roots[:3]) or "—")
        self._detail_vars["Resume Outcome"].set(e.resume_outcome or "—")
        self._detail_vars["Resume Reason"].set(e.resume_reason or "—")

    def _on_load(self):
        if not self.vm.selected_id:
            return
        result = self.coordinator.load_scan(self.vm.selected_id)
        if result:
            self.on_load_scan(self.vm.selected_id)
        else:
            messagebox.showwarning("Load", "Could not load scan results.")

    def _on_resume(self):
        if not self.vm.selected_id:
            return
        entry = self.vm.selected_session
        if not entry or not entry.is_resumable:
            messagebox.showinfo("Resume", "This scan is not resumable.")
            return
        self.on_resume_scan(self.vm.selected_id)

    def _on_delete(self):
        if not self.vm.selected_id:
            return
        if messagebox.askyesno("Delete Entry",
                               "Remove this scan from history?\n"
                               "This does not delete any files."):
            if self.coordinator.delete_scan(self.vm.selected_id):
                self._refresh()
            else:
                messagebox.showerror("Error", "Failed to delete scan entry.")

    def _on_empty_trash(self):
        count, total_bytes, _ = list_dedup_trash()
        if count == 0:
            messagebox.showinfo("Trash", "DEDUP trash is already empty.")
            return
        if messagebox.askyesno("Empty Trash",
                               f"{count} files ({fmt_bytes(total_bytes)}) in DEDUP trash.\n"
                               "Permanently delete? This cannot be undone."):
            deleted, failed = empty_dedup_trash()
            if failed:
                messagebox.showwarning("Trash", f"Deleted: {deleted}, Failed: {failed}")
            else:
                messagebox.showinfo("Trash", f"Deleted {deleted} files permanently.")
