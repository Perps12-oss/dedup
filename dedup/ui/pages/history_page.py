"""
History Page — Session archive, resume control, long-term visibility.

Layout:
  Row 0: Page header
  Row 1: Summary stats bar
  Row 2: Session table (full-width)
  Row 3: Session detail panel

UI Refactor (v4): Aligned to shared 8px design system.
  - Header: stacked title_block with Refresh button top-right (standard pattern).
  - Summary cards: _GAP_XS padding instead of hardcoded 4px.
  - Table toolbar: _GAP_MD gap between filter checkboxes, _GAP_SM bottom gap.
  - Action row below table: _GAP_SM between Load/Resume, Delete pushed right.
  - Session detail panel: right-aligned key labels + _GAP_MD value indent,
    _GAP_XS row gaps (was padx=4, pady=2 per sub-frame).
  - All hardcoded px values replaced with _S() constants.
"""

from __future__ import annotations

import json
import tkinter as tk
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Callable, Optional

import ttkbootstrap as tb

if TYPE_CHECKING:
    from ..state.store import UIStateStore

from ...infrastructure.trash import empty_dedup_trash, list_dedup_trash
from ...orchestration.coordinator import ScanCoordinator
from ..components import DataTable, InlineNotice, MetricCard, SectionCard
from ..theme.design_system import font_tuple
from ..utils.formatting import fmt_bytes, fmt_duration, fmt_int
from ..utils.icons import IC
from ..viewmodels.history_vm import HistoryVM, SessionEntry


# ---------------------------------------------------------------------------
# Spacing helpers — 8-pt grid (shared across all pages)
# ---------------------------------------------------------------------------
def _S(n: int) -> int:
    return n * 4


_PAD_PAGE = _S(6)  # 24px
_GAP_XS = _S(1)  # 4px
_GAP_SM = _S(2)  # 8px
_GAP_MD = _S(4)  # 16px
_GAP_LG = _S(6)  # 24px


class HistoryPage(ttk.Frame):
    """Scan history page."""

    def __init__(
        self,
        parent,
        coordinator: ScanCoordinator,
        on_load_scan: Callable[[str], None],
        on_resume_scan: Callable[[str], None],
        on_request_refresh: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.coordinator = coordinator
        self.on_load_scan = on_load_scan
        self.on_resume_scan = on_resume_scan
        self._on_request_refresh = on_request_refresh
        self.vm = HistoryVM()
        self._store_unsub: Optional[Callable[[], None]] = None
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        # Table expands; detail strip stays natural height at bottom.
        self.rowconfigure(2, weight=1)

        # ── Page header ───────────────────────────────────────────────
        hdr = ttk.Frame(self, padding=(_PAD_PAGE, _GAP_LG, _PAD_PAGE, _GAP_MD))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(0, weight=1)

        title_block = ttk.Frame(hdr)
        title_block.grid(row=0, column=0, sticky="w")
        ttk.Label(
            title_block,
            text=f"{IC.HISTORY}  History",
            font=font_tuple("page_title"),
        ).pack(side="top", anchor="w")
        ttk.Label(
            title_block,
            text="Sessions · Resume · Archive",
            style="Muted.TLabel",
            font=font_tuple("page_subtitle"),
        ).pack(side="top", anchor="w", pady=(_GAP_XS, 0))

        tb.Button(
            hdr,
            text=f"{IC.REFRESH} Refresh",
            bootstyle="secondary",
            command=self._refresh,
        ).grid(row=0, column=2, sticky="e", padx=(_GAP_MD, 0))

        # ── Summary stats strip ───────────────────────────────────────
        stats_card = SectionCard(self, title="Summary")
        stats_card.grid(row=1, column=0, sticky="ew", padx=_PAD_PAGE, pady=(0, _GAP_MD))
        self._build_summary(stats_card.body)

        # ── Session table ─────────────────────────────────────────────
        table_card = SectionCard(self, title=f"{IC.FILE}  Sessions")
        table_card.grid(row=2, column=0, sticky="nsew", padx=_PAD_PAGE, pady=(0, _GAP_MD))
        table_card.body.rowconfigure(2, weight=1)
        self._load_notice = InlineNotice(
            table_card.body,
            message="",
            variant="warning",
            action_label="Dismiss",
            on_action=lambda: self._load_notice.hide(),
        )
        self._load_notice.grid(row=0, column=0, sticky="ew", pady=(0, _GAP_SM))
        self._load_notice.hide()
        self._build_table(table_card.body)

        # ── Detail panel ──────────────────────────────────────────────
        detail_card = SectionCard(self, title=f"{IC.INFO}  Session Detail")
        detail_card.grid(row=3, column=0, sticky="ew", padx=_PAD_PAGE, pady=(0, _PAD_PAGE))
        self._build_detail(detail_card.body)

    def _build_summary(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)
        body.columnconfigure(3, weight=1)
        self._summary_cards: dict[str, MetricCard] = {}
        specs = [
            ("total", f"{IC.FILE}  Total Scans", "0", "neutral"),
            ("avg_dur", f"{IC.SPEED} Avg Duration", "—", "neutral"),
            ("avg_rec", f"{IC.RECLAIM} Avg Reclaimable", "—", "positive"),
            ("resume", f"{IC.RESUME} Resumable", "0", "accent"),
        ]
        for i, (key, label, val, variant) in enumerate(specs):
            c = MetricCard(body, label=label, value=val, variant=variant, width=0)
            c.grid(row=0, column=i, sticky="nsew", padx=_GAP_XS, pady=_GAP_XS)
            self._summary_cards[key] = c

    def _build_table(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        # Filter toolbar
        toolbar = ttk.Frame(body, style="Panel.TFrame")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, _GAP_SM))
        self._resumable_var = tk.BooleanVar(value=False)
        self._failed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar,
            text="Resumable only",
            variable=self._resumable_var,
            command=self._apply_filter,
        ).pack(side="left")
        ttk.Checkbutton(
            toolbar,
            text="Failed only",
            variable=self._failed_var,
            command=self._apply_filter,
        ).pack(side="left", padx=(_GAP_MD, 0))
        tb.Button(
            toolbar,
            text=f"{IC.TRASH} Empty Trash",
            bootstyle="danger",
            command=self._on_empty_trash,
        ).pack(side="right")

        self._table = DataTable(
            body,
            columns=[
                ("date", "Date", 140, "w"),
                ("status", "Status", 72, "w"),
                ("resume", "Resume", 60, "center"),
                ("files", "Files", 80, "e"),
                ("groups", "Groups", 70, "e"),
                ("reclaim", "Reclaimable", 90, "e"),
                ("warnings", "Warns", 50, "center"),
            ],
            height=6,
            on_select=self._on_session_select,
        )
        self._table.grid(row=2, column=0, sticky="nsew")
        self._table.bind_height_to_parent(body, min_lines=4, max_lines=24, reserve_px=160)

        # Action buttons below table — Load/Resume on left, Delete on right
        act = ttk.Frame(body, style="Panel.TFrame")
        act.grid(row=3, column=0, sticky="ew", pady=(_GAP_SM, 0))
        self._load_btn = tb.Button(
            act,
            text=f"{IC.FILE} Load Results",
            bootstyle="secondary",
            command=self._on_load,
            state="disabled",
        )
        self._load_btn.pack(side="left")
        self._resume_btn = tb.Button(
            act,
            text=f"{IC.RESUME} Resume Scan",
            bootstyle="success",
            command=self._on_resume,
            state="disabled",
        )
        self._resume_btn.pack(side="left", padx=(_GAP_SM, 0))
        self._del_btn = tb.Button(
            act,
            text=f"{IC.TRASH} Delete Entry",
            bootstyle="danger",
            command=self._on_delete,
            state="disabled",
        )
        self._del_btn.pack(side="right")

    def _build_detail(self, body: ttk.Frame):
        # Two-column key/value grid — right-aligned keys, _GAP_MD indent
        body.columnconfigure(0, minsize=120)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, minsize=_GAP_LG)  # gutter
        body.columnconfigure(3, minsize=120)
        body.columnconfigure(4, weight=1)

        self._detail_vars: dict[str, tk.StringVar] = {}
        fields = [
            ("Session ID", "—"),
            ("Status", "—"),
            ("Started", "—"),
            ("Duration", "—"),
            ("Config Hash", "—"),
            ("Roots", "—"),
            ("Resume Outcome", "—"),
            ("Resume Reason", "—"),
            ("Delete Verify", "—"),
            ("Bench", "—"),
        ]
        for i, (label, default) in enumerate(fields):
            lcol = (i % 2) * 3  # 0 or 3
            vcol = lcol + 1
            row = i // 2
            ttk.Label(
                body,
                text=label,
                style="Panel.Muted.TLabel",
                font=font_tuple("data_label"),
                anchor="e",
            ).grid(row=row, column=lcol, sticky="e", padx=(0, _GAP_SM), pady=(_GAP_XS, 0))
            var = tk.StringVar(value=default)
            ttk.Label(
                body,
                textvariable=var,
                style="Panel.TLabel",
                font=font_tuple("data_value"),
                wraplength=280,
            ).grid(row=row, column=vcol, sticky="w", pady=(_GAP_XS, 0))
            self._detail_vars[label] = var

    # ----------------------------------------------------------------
    # Store subscription
    # ----------------------------------------------------------------
    def attach_store(self, store: "UIStateStore") -> None:
        if self._store_unsub:
            self._store_unsub()

        def on_state(state):
            history = getattr(state, "history", None)
            if history is not None:
                self.vm.refresh_from_history(history)
                self._update_summary()
                self._populate_table()

        self._store_unsub = store.subscribe(on_state, fire_immediately=False)

    def detach_store(self) -> None:
        if self._store_unsub:
            self._store_unsub()
            self._store_unsub = None

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------
    def on_show(self):
        if self._on_request_refresh:
            self._on_request_refresh()
        else:
            self.refresh()

    def refresh(self):
        self._refresh()

    def export_sessions_json(self) -> None:
        """Write filtered session rows to JSON (save-as dialog)."""
        sessions = self.vm.filtered_sessions
        if not sessions:
            messagebox.showinfo(
                "Export",
                "No sessions to export — the list is empty or current filters exclude all rows.",
            )
            return
        path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title="Export session history",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        payload = {
            "export_format": "cerebro_history_v1",
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "session_count": len(sessions),
            "filters": {
                "resumable_only": self.vm.show_resumable_only,
                "failed_only": self.vm.show_failed_only,
                "search_text": self.vm.search_text,
            },
            "sessions": [asdict(e) for e in sessions],
        }
        try:
            Path(path).write_text(
                json.dumps(payload, indent=2, default=lambda o: list(o) if isinstance(o, tuple) else o),
                encoding="utf-8",
            )
            messagebox.showinfo("Export", f"Exported {len(sessions)} session(s) to:\n{path}")
        except OSError as ex:
            messagebox.showerror("Export failed", str(ex))

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
            status_icon = (
                IC.OK
                if e.status == "completed"
                else IC.WARN
                if e.status in ("interrupted", "resumable")
                else IC.ERROR
                if e.status == "failed"
                else "—"
            )
            tag = (
                "safe"
                if e.status == "completed"
                else "warn"
                if e.is_resumable
                else "danger"
                if e.status == "failed"
                else ""
            )
            roots = ", ".join(Path(r).name for r in e.roots[:2])
            if len(e.roots) > 2:
                roots += "…"
            self._table.insert_row(
                e.scan_id,
                (
                    e.started_at,
                    f"{status_icon} {e.status}",
                    resume_icon,
                    fmt_int(e.files_scanned),
                    fmt_int(e.duplicates_found),
                    fmt_bytes(e.reclaimable_bytes),
                    str(e.warning_count),
                ),
                tags=(tag,) if tag else (),
            )
        self._load_btn.configure(state="disabled")
        self._resume_btn.configure(state="disabled")
        self._del_btn.configure(state="disabled")

    def _apply_filter(self):
        self.vm.show_resumable_only = self._resumable_var.get()
        self.vm.show_failed_only = self._failed_var.get()
        self._populate_table()

    def _on_session_select(self, scan_id: str):
        self.vm.selected_id = scan_id
        entry = self.vm.selected_session
        if not entry:
            return
        self._update_detail(entry)
        self._load_btn.configure(state="normal")
        self._resume_btn.configure(state="normal" if entry.is_resumable else "disabled")
        self._del_btn.configure(state="normal")

    def _update_detail(self, e: SessionEntry):
        self._detail_vars["Session ID"].set(e.scan_id[:20] + "…" if len(e.scan_id) > 20 else e.scan_id)
        self._detail_vars["Status"].set(e.status)
        self._detail_vars["Started"].set(e.started_at)
        self._detail_vars["Duration"].set(fmt_duration(e.duration_s))
        self._detail_vars["Config Hash"].set(e.config_hash[:12] if e.config_hash else "—")
        self._detail_vars["Roots"].set(", ".join(Path(r).name for r in e.roots[:3]) or "—")
        self._detail_vars["Resume Outcome"].set(e.resume_outcome or "—")
        self._detail_vars["Resume Reason"].set(e.resume_reason or "—")
        verify = e.deletion_verification_summary or {}
        if verify:
            self._detail_vars["Delete Verify"].set(
                f"deleted={verify.get('deleted', 0)}, "
                f"still={verify.get('still_present', 0)}, "
                f"changed={verify.get('changed_after_plan', 0)}, "
                f"failed={verify.get('verification_failed', 0)}"
            )
        else:
            self._detail_vars["Delete Verify"].set("—")
        bench = e.benchmark_summary or {}
        if bench:
            self._detail_vars["Bench"].set(
                f"{bench.get('discovery_reuse_mode', 'none')} "
                f"disc={bench.get('discovery_elapsed_ms', 0)}ms "
                f"total={bench.get('total_elapsed_ms', 0)}ms"
            )
        else:
            self._detail_vars["Bench"].set("—")

    def _on_load(self):
        if not self.vm.selected_id:
            return
        self._load_notice.hide()
        result = self.coordinator.load_scan(self.vm.selected_id)
        if result:
            self.on_load_scan(self.vm.selected_id)
        else:
            self._load_notice.set_message("Could not load scan results.")
            self._load_notice.show()

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
        if messagebox.askyesno("Delete Entry", "Remove this scan from history?\nThis does not delete any files."):
            if self.coordinator.delete_scan(self.vm.selected_id):
                self._refresh()
            else:
                messagebox.showerror("Error", "Failed to delete scan entry.")

    def _on_empty_trash(self):
        count, total_bytes, _ = list_dedup_trash()
        if count == 0:
            messagebox.showinfo("Trash", "DEDUP trash is already empty.")
            return
        if messagebox.askyesno(
            "Empty Trash",
            f"{count} files ({fmt_bytes(total_bytes)}) in DEDUP trash.\nPermanently delete? This cannot be undone.",
        ):
            deleted, failed = empty_dedup_trash()
            if failed:
                messagebox.showwarning("Trash", f"Deleted: {deleted}, Failed: {failed}")
            else:
                messagebox.showinfo("Trash", f"Deleted {deleted} files permanently.")
