"""
Scan Page — Live operations console for the durable pipeline.

Layout:
  Row 0: Page header + Cancel button
  Row 1: Status Ribbon        (driven by SessionProjection + CompatibilityProjection)
  Row 2: Phase Timeline       (driven by Dict[phase_name, PhaseProjection])
  Row 3: Live Metrics | Work Saved  (driven by MetricsProjection + ScanVM.work_saved_info)
  Row 4: Phase Detail | Events log  (driven by PhaseProjection + events_log)

Update flow:
  ProjectionHub  →  on_session / on_phase / on_metrics / on_events
    →  ScanVM snapshot update
      →  _render_*()  update individual widgets (no whole-page repaint)
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Dict, List, Optional
import time

from ..components import (
    MetricCard, SectionCard, PhaseTimeline, StatusRibbon, EmptyState
)
from ..viewmodels.scan_vm import ScanVM
from ..projections.session_projection import SessionProjection
from ..projections.phase_projection import PhaseProjection, PHASE_ORDER
from ..projections.metrics_projection import MetricsProjection
from ..projections.compatibility_projection import CompatibilityProjection
from ..utils.formatting import fmt_bytes, fmt_int, fmt_duration, truncate_path
from ..utils.icons import IC
from ...orchestration.coordinator import ScanCoordinator
from ...engine.models import ScanProgress, ScanResult


class ScanPage(ttk.Frame):
    """Live scan monitoring page — driven by ProjectionHub subscriptions."""

    def __init__(
        self,
        parent,
        coordinator: ScanCoordinator,
        on_complete: Callable[[ScanResult], None],
        on_cancel: Callable[[], None],
        hub=None,      # ProjectionHub — injected by app.py after creation
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.coordinator  = coordinator
        self.on_complete  = on_complete
        self.on_cancel    = on_cancel
        self._hub         = hub
        self._unsubs: List[Callable] = []

        self.vm           = ScanVM()
        self._after_id: Optional[str] = None
        self._build()

    # ------------------------------------------------------------------
    # Hub wiring — called by app.py once hub is available
    # ------------------------------------------------------------------

    def attach_hub(self, hub) -> None:
        """Subscribe to ProjectionHub. Safe to call after __init__."""
        self._hub = hub
        self._unsubs.append(hub.subscribe("session",       self._on_session))
        self._unsubs.append(hub.subscribe("phase",         self._on_phases))
        self._unsubs.append(hub.subscribe("metrics",       self._on_metrics))
        self._unsubs.append(hub.subscribe("compatibility", self._on_compat))
        self._unsubs.append(hub.subscribe("events_log",    self._on_events_log))
        self._unsubs.append(hub.subscribe("terminal",      self._on_terminal))

    def detach_hub(self) -> None:
        for unsub in self._unsubs:
            try:
                unsub()
            except Exception:
                pass
        self._unsubs.clear()

    # ------------------------------------------------------------------
    # Projection callbacks (always on Tk main thread via hub throttle)
    # ------------------------------------------------------------------

    def _on_session(self, proj: SessionProjection) -> None:
        self.vm.session = proj
        # Ribbon reflects resume policy
        ribbon_variant = proj.resume_policy or "idle"
        detail = proj.resume_reason or ""
        if proj.status == "running":
            self._ribbon.set_state(ribbon_variant or "scanning", detail=detail)
        elif proj.status == "completed":
            self._ribbon.set_state("completed", detail="Scan complete")
        elif proj.status in ("cancelled", "failed"):
            self._ribbon.set_state("failed", detail=detail or proj.status)
        self._render_phase_detail()

    def _on_phases(self, phases: Dict[str, PhaseProjection]) -> None:
        self.vm.phases = phases
        # Update timeline
        for pname, proj in phases.items():
            self._timeline.set_phase_state(pname, proj.timeline_state)
        self._render_phase_detail()

    def _on_metrics(self, proj: MetricsProjection) -> None:
        self.vm.metrics = proj
        self._render_metrics()

    def _on_compat(self, proj: CompatibilityProjection) -> None:
        self.vm.compat = proj
        # Push resume info to ribbon if more specific than session projection
        if proj.overall_resume_outcome not in ("unknown", ""):
            state_map = {
                "safe_resume":             "safe_resume",
                "rebuild_current_phase":   "rebuild_phase",
                "rebuild_phase":           "rebuild_phase",
                "restart_required":        "restart_required",
            }
            ribbon_state = state_map.get(proj.overall_resume_outcome, "idle")
            self._ribbon.set_state(ribbon_state,
                                   detail=proj.overall_resume_reason[:60])
        self._render_work_saved()

    def _on_events_log(self, entries: List[str]) -> None:
        self.vm.events_log = entries
        self._render_events()

    def _on_terminal(self, proj: SessionProjection) -> None:
        """Scan finished (any terminal status)."""
        if not self.vm.is_scanning:
            return
        self.vm.is_scanning = False
        self.vm.session      = proj
        self._progress_bar.stop()
        self._cancel_elapsed()
        if proj.status == "completed":
            self._ribbon.set_state("completed", detail="Scan complete")
            for pname in PHASE_ORDER:
                self._timeline.set_phase_state(pname, "completed")
        elif proj.status == "cancelled":
            self._ribbon.set_state("idle", label_override="Cancelled")
        elif proj.status == "failed":
            self._ribbon.set_state("failed",
                                   detail=proj.resume_reason[:60] if proj.resume_reason else "Error")

    # ------------------------------------------------------------------
    # Widget rendering (granular — no whole-page repaint)
    # ------------------------------------------------------------------

    def _render_metrics(self) -> None:
        m = self.vm.metrics
        self._metric_cards["files"].update(fmt_int(m.files_scanned))
        self._metric_cards["skipped"].update(fmt_int(m.files_skipped))
        self._metric_cards["cands"].update(fmt_int(m.candidates))
        self._metric_cards["groups"].update(fmt_int(m.duplicate_groups))
        self._metric_cards["reclaim"].update(
            fmt_bytes(m.reclaimable_bytes) if m.reclaimable_bytes else "—")
        self._metric_cards["elapsed"].update(fmt_duration(m.elapsed_s))
        self._phase_vars["Time"].set(fmt_duration(m.elapsed_s))
        pct = (m.files_scanned / max(1, m.files_scanned + m.files_skipped) * 100
               if (m.files_scanned + m.files_skipped) else 0)
        if pct > 0:
            self._phase_vars["Progress"].set(f"{pct:.0f}%")

    def _render_phase_detail(self) -> None:
        s = self.vm.session
        active_phase = next(
            (p for p in self.vm.phases.values() if p.status == "running"), None)
        self._phase_vars["Phase"].set(
            active_phase.display_label if active_phase else (s.current_phase or "—"))
        if active_phase:
            self._phase_vars["Rows processed"].set(fmt_int(active_phase.rows_written))

    def _render_work_saved(self) -> None:
        ws = self.vm.work_saved_info
        for key, var in self._work_vars.items():
            var.set(ws.get(key, "—"))

    def _render_events(self) -> None:
        self._events_list.delete(0, "end")
        for entry in self.vm.events_log[:100]:
            self._events_list.insert("end", entry)
        # Scroll to bottom so newest events (e.g. "Scan completed") are visible
        if self.vm.events_log:
            self._events_list.see("end")
        # Scroll to bottom so newest events (e.g. "Scan completed") are visible
        if self.vm.events_log:
            self._events_list.see("end")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)
        pad = {"padx": 16, "pady": (0, 8)}

        # ── Page header ──────────────────────────────────────────────
        hdr = ttk.Frame(self, padding=(16, 12, 16, 0))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        self._title_lbl = ttk.Label(
            hdr, text=f"{IC.SCAN}  Scan", font=("Segoe UI", 14, "bold"))
        self._title_lbl.grid(row=0, column=0, sticky="w")
        self._cancel_btn = ttk.Button(
            hdr, text=f"{IC.STOPPED}  Cancel",
            style="Ghost.TButton", command=self._on_cancel)
        self._cancel_btn.grid(row=0, column=2, sticky="e")

        # ── Status ribbon ────────────────────────────────────────────
        self._ribbon = StatusRibbon(self)
        self._ribbon.grid(row=1, column=0, sticky="ew", **pad)

        # ── Phase timeline ───────────────────────────────────────────
        tl_card = SectionCard(self, title="Pipeline")
        tl_card.grid(row=2, column=0, sticky="ew", **pad)
        self._timeline = PhaseTimeline(tl_card.body)
        self._timeline.pack(fill="x")

        # ── Metrics + Work Saved row ─────────────────────────────────
        metrics_row = ttk.Frame(self)
        metrics_row.grid(row=3, column=0, sticky="ew", **pad)
        metrics_row.columnconfigure(0, weight=3)
        metrics_row.columnconfigure(1, weight=2)

        live_card = SectionCard(metrics_row, title=f"{IC.SPEED}  Live Metrics")
        live_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._build_live_metrics(live_card.body)

        self._work_card = SectionCard(metrics_row, title=f"{IC.SAVED}  Work Saved")
        self._work_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._build_work_saved(self._work_card.body)

        # ── Phase detail + Events row ─────────────────────────────────
        detail_row = ttk.Frame(self)
        detail_row.grid(row=4, column=0, sticky="nsew", **pad)
        detail_row.columnconfigure(0, weight=1)
        detail_row.columnconfigure(1, weight=1)
        detail_row.rowconfigure(0, weight=1)

        phase_card = SectionCard(detail_row, title=f"{IC.ACTIVE}  Current Phase")
        phase_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._build_phase_detail(phase_card.body)

        events_card = SectionCard(detail_row, title=f"{IC.INFO}  Events")
        events_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._build_events(events_card.body)

    def _build_live_metrics(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)
        self._metric_cards: Dict[str, MetricCard] = {}
        specs = [
            ("files",   f"{IC.FILE}  Files",       "0",  "neutral"),
            ("skipped", f"{IC.SKIPPED} Skipped",   "0",  "neutral"),
            ("cands",   f"{IC.CANDIDATES} Cands",  "0",  "neutral"),
            ("groups",  f"{IC.GROUPS} Groups",     "0",  "accent"),
            ("reclaim", f"{IC.RECLAIM} Estimate",  "—",  "positive"),
            ("elapsed", f"{IC.SPEED}  Elapsed",    "0s", "neutral"),
        ]
        for i, (key, label, val, variant) in enumerate(specs):
            c = MetricCard(body, label=label, value=val, variant=variant, width=0)
            c.grid(row=i // 3, column=i % 3, sticky="nsew", padx=3, pady=3)
            self._metric_cards[key] = c

    def _build_work_saved(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        self._work_vars: Dict[str, tk.StringVar] = {}
        rows = [
            ("Discovery reused",  "—"),
            ("Size reduction",    "—"),
            ("Files skipped",     "0"),
            ("Time saved",        "—"),
            ("Resume reason",     "—"),
            ("Outcome",           "—"),
        ]
        for i, (label, default) in enumerate(rows):
            ttk.Label(body, text=label + ":", style="Panel.Muted.TLabel",
                      font=("Segoe UI", 8)).grid(row=i, column=0, sticky="w", pady=1)
            var = tk.StringVar(value=default)
            ttk.Label(body, textvariable=var, style="Panel.TLabel",
                      font=("Segoe UI", 8, "bold")).grid(
                row=i, column=1, sticky="w", padx=(4, 0))
            self._work_vars[label] = var

    def _build_phase_detail(self, body: ttk.Frame):
        body.columnconfigure(1, weight=1)
        self._phase_vars: Dict[str, tk.StringVar] = {}
        rows = [
            ("Phase",          "—"),
            ("Progress",       "—"),
            ("Rows processed", "0"),
            ("Time",           "0s"),
            ("Current file",   ""),
        ]
        for i, (label, default) in enumerate(rows):
            ttk.Label(body, text=label + ":", style="Panel.Muted.TLabel",
                      font=("Segoe UI", 8)).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=default)
            ttk.Label(body, textvariable=var, style="Panel.TLabel",
                      font=("Segoe UI", 8), wraplength=220).grid(
                row=i, column=1, sticky="w", padx=(6, 0))
            self._phase_vars[label] = var
        self._progress_bar = ttk.Progressbar(
            body, mode="indeterminate", length=240)
        self._progress_bar.grid(
            row=len(rows), column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _build_events(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self._events_list = tk.Listbox(
            body, height=8, selectmode="browse",
            font=("Consolas", 8), borderwidth=0, highlightthickness=0,
            activestyle="none")
        scroll = ttk.Scrollbar(
            body, orient="vertical", command=self._events_list.yview)
        self._events_list.configure(yscrollcommand=scroll.set)
        self._events_list.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_scan(self, path: Path, options: dict) -> None:
        self._reset_vm()
        self._title_lbl.configure(text=f"{IC.SCAN}  Scanning — {path.name}")
        self._ribbon.set_state("scanning", detail="Initialising…")
        self._progress_bar.start(12)
        self._schedule_elapsed()
        # Still pass on_progress for fallback (pre-hub or no-hub mode)
        self.coordinator.start_scan(
            roots=[path],
            on_progress=self._on_progress_fallback,
            on_complete=self._on_complete_fallback,
            on_error=self._on_error_fallback,
            **options,
        )

    def start_resume(self, scan_id: str) -> None:
        self._reset_vm()
        self._title_lbl.configure(text=f"{IC.RESUME}  Resuming scan…")
        self._ribbon.set_state("info", detail="Checking checkpoints…",
                               label_override="Resume in progress")
        self._progress_bar.start(12)
        self._schedule_elapsed()
        self.coordinator.start_scan(
            roots=[],
            resume_scan_id=scan_id,
            on_progress=self._on_progress_fallback,
            on_complete=self._on_complete_fallback,
            on_error=self._on_error_fallback,
        )

    # ------------------------------------------------------------------
    # Fallback callbacks (used when no hub is attached, or for current_file)
    # ------------------------------------------------------------------

    def _on_progress_fallback(self, progress: ScanProgress) -> None:
        """
        Thin fallback: only update current_file display (not covered by hub).
        All other metrics come through hub projections when available.
        """
        if self._hub:
            if progress.current_file:
                self.after(0, lambda f=progress.current_file:
                           self._phase_vars["Current file"].set(truncate_path(f, 40)))
        else:
            # No hub — fall back to direct progress update
            self.after(0, lambda p=progress: self._update_display_direct(p))

    def _update_display_direct(self, progress: ScanProgress) -> None:
        """Direct update path (no hub). Used only in hub-less mode."""
        from ..projections.metrics_projection import build_metrics_from_progress
        self._on_metrics(build_metrics_from_progress(progress))
        if progress.current_file:
            self._phase_vars["Current file"].set(
                truncate_path(progress.current_file, 40))
        # Phase timeline
        from ..projections.phase_projection import canonical_phase
        canon = canonical_phase(progress.phase or "")
        if canon:
            self._timeline.set_phase_state(canon, "active")

    def _on_complete_fallback(self, result: ScanResult) -> None:
        self.vm.is_scanning = False
        self._progress_bar.stop()
        self._cancel_elapsed()
        if not self._hub:
            self._ribbon.set_state(
                "completed",
                detail=f"{result.files_scanned:,} files scanned")
            for pname in PHASE_ORDER:
                self._timeline.set_phase_state(pname, "completed")
            from ..utils.formatting import fmt_int, fmt_bytes
            self._metric_cards["groups"].update(
                fmt_int(len(result.duplicate_groups)))
            self._metric_cards["reclaim"].update(
                fmt_bytes(result.total_reclaimable_bytes))
        self.after(0, lambda: self.on_complete(result))

    def _on_error_fallback(self, error: str) -> None:
        self.vm.is_scanning = False
        self._progress_bar.stop()
        self._cancel_elapsed()
        if not self._hub:
            self._ribbon.set_state("failed", detail=error[:60])
        self.after(0, lambda: messagebox.showerror("Scan Error", f"Scan failed:\n{error}"))
        self.after(0, self.on_cancel)

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def _on_cancel(self) -> None:
        if not self.vm.is_scanning:
            self.on_cancel()
            return
        if messagebox.askyesno("Cancel Scan", "Cancel the current scan?"):
            self.coordinator.cancel_scan()
            self.vm.is_scanning = False
            self._progress_bar.stop()
            self._cancel_elapsed()
            if not self._hub:
                self._ribbon.set_state("idle", label_override="Cancelled")
            self.on_cancel()

    # ------------------------------------------------------------------
    # Reset + elapsed ticker
    # ------------------------------------------------------------------

    def _reset_vm(self) -> None:
        from ..projections.phase_projection import initial_phase_map
        self.vm.reset()
        self.vm.is_scanning = True
        self._timeline.reset()
        self._events_list.delete(0, "end")
        for c in self._metric_cards.values():
            c.update("0")
        for v in self._work_vars.values():
            v.set("—")
        for v in self._phase_vars.values():
            v.set("—")

    def _schedule_elapsed(self) -> None:
        self._after_id = self.after(1000, self._tick_elapsed)

    def _tick_elapsed(self) -> None:
        if not self.vm.is_scanning:
            return
        elapsed = time.time() - self.vm._start_wall
        self._metric_cards["elapsed"].update(fmt_duration(elapsed))
        self._phase_vars["Time"].set(fmt_duration(elapsed))
        self._schedule_elapsed()

    def _cancel_elapsed(self) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None

    def on_show(self) -> None:
        pass
