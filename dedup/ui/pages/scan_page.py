"""
Scan Page — Live operations console for the durable pipeline.

Layout:
  Row 0: Page header + Cancel button
  Row 1: Status Ribbon        (driven by SessionProjection + CompatibilityProjection)
  Row 2: Phase Timeline       (driven by Dict[phase_name, PhaseProjection])
  Row 3: Live Metrics | Work Saved  (driven by MetricsProjection + ScanVM.work_saved_info)
  Row 4: Phase Detail | Events log  (driven by PhaseProjection + events_log)

Update flow (store-driven):
  ProjectionHub  →  hub→store adapter  →  UIStateStore
    →  ScanPage.subscribe(store)  →  selectors  →  ScanVM snapshot update
      →  _render_*()  update individual widgets (no whole-page repaint)
  When store is attached, display state comes from store only (hub feeds store).
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Dict, List, Optional, TYPE_CHECKING
import time

from ..components import (
    MetricCard, SectionCard, PhaseTimeline, StatusRibbon, EmptyState,
    DegradedBanner, ErrorPanel,
)
from ..viewmodels.scan_vm import ScanVM
from ..projections.session_projection import SessionProjection
from ..projections.phase_projection import PhaseProjection, PHASE_ORDER
from ..projections.metrics_projection import MetricsProjection
from ..projections.compatibility_projection import CompatibilityProjection
from ..utils.formatting import fmt_bytes, fmt_int, fmt_duration, truncate_path
from ..utils.icons import IC
from ..theme.design_system import font_tuple, SPACING
from ...orchestration.coordinator import ScanCoordinator
from ...engine.models import ScanProgress, ScanResult

if TYPE_CHECKING:
    from ..state.store import UIStateStore


def _fixed_width_path(path: str, width: int = 40) -> str:
    """Truncate path to width and pad to fixed length to prevent layout flicker."""
    s = truncate_path(path, width)
    return s[:width].ljust(width)


class ScanPage(ttk.Frame):
    """Live scan monitoring page — driven by ProjectionHub subscriptions."""

    def __init__(
        self,
        parent,
        coordinator: ScanCoordinator,
        on_complete: Callable[[ScanResult], None],
        on_cancel: Callable[[], None],
        on_go_to_review: Optional[Callable[[], None]] = None,
        hub=None,      # ProjectionHub — injected by app.py after creation
        scan_controller=None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.coordinator  = coordinator
        self.on_complete  = on_complete
        self.on_cancel    = on_cancel
        self.on_go_to_review = on_go_to_review
        self._hub         = hub
        self._scan_controller = scan_controller
        self._unsubs: List[Callable] = []
        self._store: Optional["UIStateStore"] = None
        self._unsub_store: Optional[Callable[[], None]] = None

        self.vm           = ScanVM()
        self._after_id: Optional[str] = None
        self._pending_defer: set = set()  # coalesce deferred renders
        self._last_events_snapshot: Optional[tuple] = None  # (len, first, last) to skip no-op refresh
        self._scan_completed = False  # show "Go to Review" when True
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
    # Store wiring — preferred when hub→store adapter is active (2C.2)
    # ------------------------------------------------------------------

    def attach_store(self, store: "UIStateStore") -> None:
        """Subscribe to UIStateStore for scan display. Store is fed by hub adapter. Single authority: when store is attached, hub is detached."""
        self.detach_hub()
        self.detach_store()
        self._store = store

        def on_state(state) -> None:
            from ..state.selectors import (
                scan_session,
                scan_phases,
                scan_metrics,
                scan_compat,
                scan_events_log,
                scan_terminal,
                degraded_state,
            )
            deg = degraded_state(state)
            if deg:
                self._degraded_banner.set_message(deg)
                self._degraded_banner.show()
            else:
                self._degraded_banner.hide()
            session = scan_session(state)
            phases = scan_phases(state)
            metrics = scan_metrics(state)
            compat = scan_compat(state)
            events_log = scan_events_log(state)
            terminal = scan_terminal(state)

            if session is not None:
                self.vm.apply_session_projection(session)
                detail = (session.current_phase or "").replace("_", " ").title()
                if session.status == "running":
                    self._ribbon.set_state("scanning", detail=detail)
                elif session.status == "completed":
                    self._ribbon.set_state("completed", detail="Scan complete")
                elif session.status in ("cancelled", "failed"):
                    self._ribbon.set_state("failed", detail=session.resume_reason or session.status)
            if phases:
                self.vm.apply_phase_projection(phases)
                for pname, proj in phases.items():
                    state_val = getattr(proj, "timeline_state", None)
                    if state_val is not None:
                        self._timeline.set_phase_state(pname, state_val)
            if metrics is not None:
                self.vm.apply_metrics_projection(metrics)
            if compat is not None:
                self.vm.compat = compat
                if getattr(compat, "overall_resume_outcome", None) not in ("unknown", ""):
                    state_map = {
                        "safe_resume": "safe_resume",
                        "rebuild_current_phase": "rebuild_phase",
                        "rebuild_phase": "rebuild_phase",
                        "restart_required": "restart_required",
                    }
                    ribbon_state = state_map.get(compat.overall_resume_outcome, "idle")
                    reason = getattr(compat, "overall_resume_reason", "") or ""
                    self._ribbon.set_state(ribbon_state, detail=reason[:60])
            if events_log is not None:
                self.vm.events_log = events_log

            if terminal is not None and self.vm.is_scanning:
                self.vm.is_scanning = False
                self.vm.session = terminal
                self._progress_bar.stop()
                self._cancel_elapsed()
                if terminal.status == "completed":
                    self._ribbon.set_state("completed", detail="Scan complete")
                    for pname in PHASE_ORDER:
                        self._timeline.set_phase_state(pname, "completed")
                    self._scan_completed = True
                    self._defer(self._update_go_to_review_btn, "go_to_review_btn")
                elif terminal.status == "cancelled":
                    self._ribbon.set_state("idle", label_override="Cancelled")
                elif terminal.status == "failed":
                    err_msg = (terminal.resume_reason or "Scan failed")[:200]
                    self.vm.error_message = err_msg
                    self._ribbon.set_state("failed", detail=err_msg[:60])
                    self._error_panel.set_message(err_msg)
                    self._error_panel.show()
            self._defer(self._render_metrics, "metrics")
            self._defer(self._render_phase_detail, "phase_detail")
            self._defer(self._render_work_saved, "work_saved")
            self._defer(self._render_events, "events")

        self._unsub_store = store.subscribe(on_state, fire_immediately=True)

    def detach_store(self) -> None:
        if self._unsub_store:
            try:
                self._unsub_store()
            except Exception:
                pass
            self._unsub_store = None
        self._store = None

    # ------------------------------------------------------------------
    # Projection callbacks (hub path — used when store is not attached)
    # ------------------------------------------------------------------

    def _defer(self, fn, key: Optional[str] = None) -> None:
        """Schedule a no-arg call on the next idle tick to avoid blocking hub delivery.
        If key is set, only one pending call per key is scheduled (coalesce).
        """
        if key and key in self._pending_defer:
            return
        if key:
            self._pending_defer.add(key)

        def run():
            if key:
                self._pending_defer.discard(key)
            if self.winfo_exists():
                try:
                    fn()
                except Exception:
                    pass
        try:
            self.after_idle(run)
        except Exception:
            if key:
                self._pending_defer.discard(key)

    def _on_session(self, proj: SessionProjection) -> None:
        self.vm.apply_session_projection(proj)
        detail = proj.current_phase.replace("_", " ").title() if proj.current_phase else ""
        if proj.status == "running":
            self._ribbon.set_state("scanning", detail=detail)
        elif proj.status == "completed":
            self._ribbon.set_state("completed", detail="Scan complete")
        elif proj.status in ("cancelled", "failed"):
            self._ribbon.set_state("failed", detail=proj.resume_reason or proj.status)
        self._defer(self._render_phase_detail, "phase_detail")

    def _on_phases(self, phases: Dict[str, PhaseProjection]) -> None:
        self.vm.apply_phase_projection(phases)
        for pname, proj in phases.items():
            self._timeline.set_phase_state(pname, proj.timeline_state)
        self._defer(self._render_phase_detail, "phase_detail")

    def _on_metrics(self, proj: MetricsProjection) -> None:
        self.vm.apply_metrics_projection(proj)
        self._defer(self._render_metrics, "metrics")

    def _on_compat(self, proj: CompatibilityProjection) -> None:
        self.vm.compat = proj
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
        self._defer(self._render_work_saved, "work_saved")

    def _on_events_log(self, entries: List[str]) -> None:
        self.vm.events_log = entries
        self._defer(self._render_events, "events")

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
            self._scan_completed = True
            self._defer(self._update_go_to_review_btn, "go_to_review_btn")
        elif proj.status == "cancelled":
            self._ribbon.set_state("idle", label_override="Cancelled")
        elif proj.status == "failed":
            self._ribbon.set_state("failed",
                                   detail=proj.resume_reason[:60] if proj.resume_reason else "Error")

    # ------------------------------------------------------------------
    # Widget rendering (granular — no whole-page repaint)
    # ------------------------------------------------------------------

    def _render_metrics(self) -> None:
        sm = self.vm.session_metrics
        pm = self.vm.phase_metrics
        rm = self.vm.result_metrics
        # Session Metrics (scan-scope only)
        self._metric_cards["files_total"].update(fmt_int(sm.files_discovered_total))
        self._metric_cards["dirs_scanned"].update(fmt_int(sm.directories_scanned_total))
        # Defensive: never show absurd speed when elapsed is 0 or missing
        speed = sm.discovery_speed if sm.elapsed_total_s > 0 else 0.0
        self._metric_cards["discovery_speed"].update(
            f"{speed:,.0f} files/sec" if speed > 0 else "—"
        )
        self._metric_cards["files_reused"].update(fmt_int(sm.files_reused_total))
        self._metric_cards["dirs_reused"].update(fmt_int(sm.dirs_reused_total))
        self._metric_cards["groups_live"].update(fmt_int(sm.duplicate_groups_total))
        self._metric_cards["elapsed"].update(fmt_duration(sm.elapsed_total_s))

        # Update ribbon detail with live stats when scanning
        if self.vm.is_scanning and pm.phase_name:
            mode_label = sm.run_mode.replace("_", " ").title()
            ribbon_detail = f"Mode: {mode_label}"
            if speed > 0:
                ribbon_detail += f"  |  {speed:,.0f} files/sec"
            ribbon_detail += f"  |  {fmt_int(sm.files_discovered_total)} files"
            self._ribbon.set_state("scanning", detail=ribbon_detail)

        # Current Phase (phase-scope only)
        self._phase_vars["Current phase"].set(
            pm.phase_name.replace("_", " ").title() if pm.phase_name else "—"
        )
        if pm.total_units:
            self._phase_vars["Phase progress"].set(f"{fmt_int(pm.completed_units)} / {fmt_int(pm.total_units)}")
        else:
            self._phase_vars["Phase progress"].set(f"{fmt_int(pm.completed_units)} / —")
        self._phase_vars["Phase units processed"].set(fmt_int(pm.completed_units))
        self._phase_vars["Phase elapsed"].set(fmt_duration(pm.elapsed_phase_s))
        if pm.current_item_label:
            self._phase_vars["Current file"].set(_fixed_width_path(pm.current_item_label, 40))

        # Result Summary — bind to FinalScanResultsSummary (authoritative terminal truth)
        fr = self.vm.final_results
        if fr.results_ready:
            self._result_vars["Duplicate groups"].set(fmt_int(fr.duplicate_groups_total))
            self._result_vars["Duplicate files"].set(fmt_int(fr.duplicate_files_total))
            self._result_vars["Reclaimable"].set(
                fmt_bytes(fr.reclaimable_bytes_total) if fr.reclaimable_bytes_total else "—"
            )
            if fr.verification_level:
                self._result_vars["Verification"].set(fr.verification_level)
        else:
            # Pre-completion: show live duplicate groups if available
            live = sm.duplicate_groups_total
            if live:
                self._result_vars["Duplicate groups"].set(fmt_int(live))

    def _render_phase_detail(self) -> None:
        s = self.vm.session
        active_phase = next(
            (p for p in self.vm.phases.values() if p.status == "running"), None)
        if not self.vm.phase_metrics.phase_name:
            self._phase_vars["Current phase"].set(
                active_phase.display_label if active_phase else (s.current_phase or "—")
            )
        if active_phase:
            self._phase_vars["Phase units processed"].set(fmt_int(active_phase.rows_written))

    def _render_work_saved(self) -> None:
        ws = self.vm.work_saved_info
        for key, var in self._work_vars.items():
            var.set(ws.get(key, "—"))

    def _render_events(self) -> None:
        log = self.vm.events_log
        display = log[:80]
        snapshot = (len(log), display[0] if display else "", display[-1] if display else "")
        if snapshot == self._last_events_snapshot:
            return
        self._last_events_snapshot = snapshot
        self._events_list.delete(0, "end")
        for entry in display:
            self._events_list.insert("end", entry)
        if display:
            self._events_list.see("end")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(7, weight=1)  # Activity Feed row stretches
        pad = SPACING["page"]
        pad_kw = {"padx": pad, "pady": (0, SPACING["md"])}

        # ── Live Scan Studio: page title + Cancel ──────────────────────
        hdr = ttk.Frame(self, padding=(pad, SPACING["lg"], pad, 0))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        self._title_lbl = ttk.Label(
            hdr, text=f"{IC.SCAN}  Live Scan Studio",
            font=font_tuple("page_title"))
        self._title_lbl.grid(row=0, column=0, sticky="w")
        ttk.Label(hdr, text="Session · Phase timeline · Metrics · Activity",
                  style="Muted.TLabel",
                  font=font_tuple("page_subtitle")).grid(row=1, column=0, sticky="w")
        self._cancel_btn = ttk.Button(
            hdr, text=f"{IC.STOPPED}  Cancel",
            style="Ghost.TButton", command=self._on_cancel)
        self._cancel_btn.grid(row=0, column=2, rowspan=2, sticky="e")
        self._go_to_review_btn = ttk.Button(
            hdr, text=f"{IC.REVIEW}  Go to Review",
            style="Accent.TButton", command=self._on_go_to_review)
        self._go_to_review_btn.grid(row=0, column=3, rowspan=2, sticky="e", padx=(SPACING["md"], 0))
        self._go_to_review_btn.grid_remove()

        # ── Degraded banner (store-driven; hidden when no degraded state) ─
        self._degraded_banner = DegradedBanner(self, message="", on_dismiss=lambda: self._degraded_banner.hide())
        self._degraded_banner.grid(row=1, column=0, sticky="ew", **pad_kw)
        self._degraded_banner.hide()

        # ── Scan Target Card (status ribbon) ──────────────────────────
        self._ribbon = StatusRibbon(self)
        self._ribbon.grid(row=2, column=0, sticky="ew", **pad_kw)

        # ── Error panel (shown when vm.error_message set; e.g. scan failed) ─
        self._error_panel = ErrorPanel(
            self, message="",
            retry_label="Back", on_retry=self._on_error_panel_dismiss)
        self._error_panel.grid(row=3, column=0, sticky="ew", **pad_kw)
        self._error_panel.hide()

        # ── Phase Timeline ────────────────────────────────────────────
        tl_card = SectionCard(self, title=f"{IC.ACTIVE}  Phase Timeline")
        tl_card.grid(row=4, column=0, sticky="ew", **pad_kw)
        self._timeline = PhaseTimeline(tl_card.body)
        self._timeline.pack(fill="x")

        # ── Live Metrics Panel ────────────────────────────────────────
        metrics_card = SectionCard(self, title=f"{IC.SPEED}  Live Metrics Panel")
        metrics_card.grid(row=5, column=0, sticky="ew", **pad_kw)
        self._build_live_metrics(metrics_card.body)

        # ── Progress/Session · Health/Compatibility · Result Summary ───
        ops_row = ttk.Frame(self)
        ops_row.grid(row=6, column=0, sticky="ew", **pad_kw)
        ops_row.columnconfigure(0, weight=1)
        ops_row.columnconfigure(1, weight=1)
        ops_row.columnconfigure(2, weight=1)

        phase_card = SectionCard(ops_row, title=f"{IC.ACTIVE}  Progress & Session")
        phase_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["sm"]))
        self._build_phase_detail(phase_card.body)

        self._work_card = SectionCard(ops_row, title=f"{IC.SHIELD}  Health & Compatibility")
        self._work_card.grid(row=0, column=1, sticky="nsew", padx=SPACING["sm"])
        self._build_work_saved(self._work_card.body)

        result_card = SectionCard(ops_row, title=f"{IC.GROUPS}  Result Summary")
        result_card.grid(row=0, column=2, sticky="nsew", padx=(SPACING["sm"], 0))
        self._build_result_summary(result_card.body)

        # ── Activity Feed ─────────────────────────────────────────────
        events_card = SectionCard(self, title=f"{IC.INFO}  Activity Feed")
        events_card.grid(row=7, column=0, sticky="nsew", **pad_kw)
        self._build_events(events_card.body)

    def _build_live_metrics(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)
        self._metric_cards: Dict[str, MetricCard] = {}
        specs = [
            ("files_total",  f"{IC.FILE}  Files Scanned",        "0",            "neutral"),
            ("dirs_scanned", f"{IC.FOLDER} Dirs Scanned",        "0",            "neutral"),
            ("discovery_speed", f"{IC.SPEED}  Discovery Speed",  "—",            "neutral"),
            ("files_reused", f"{IC.SAVED} Files Reused",         "0",            "positive"),
            ("dirs_reused",  f"{IC.SKIPPED} Dirs Reused",        "0",            "positive"),
            ("groups_live",  f"{IC.GROUPS} Duplicate Groups",    "0",            "accent"),
            ("elapsed",      f"{IC.SPEED}  Elapsed Total",       "0s",           "neutral"),
        ]
        card_width = 110
        for i, (key, label, val, variant) in enumerate(specs):
            c = MetricCard(body, label=label, value=val, variant=variant, width=card_width)
            c.grid(row=i // 3, column=i % 3, sticky="nsew", padx=3, pady=3)
            self._metric_cards[key] = c

    def _build_work_saved(self, body: ttk.Frame):
        body.columnconfigure(0, minsize=90)
        body.columnconfigure(1, weight=1, minsize=140)
        self._work_vars: Dict[str, tk.StringVar] = {}
        rows = [
            ("Reuse mode",        "none"),
            ("Dirs skipped",      "0"),
            ("Files reused",      "0"),
            ("Skip ratio",        "—"),
            ("Hash cache hit rate", "—"),
            ("Compatible prior",  "No"),
            ("Compatibility reason", "none"),
            ("Time saved",        "—"),
        ]
        for i, (label, default) in enumerate(rows):
            ttk.Label(body, text=label + ":", style="Panel.Muted.TLabel",
                      font=font_tuple("data_label")).grid(row=i, column=0, sticky="w", pady=1)
            var = tk.StringVar(value=default)
            ttk.Label(body, textvariable=var, style="Panel.TLabel",
                      font=font_tuple("data_value")).grid(
                row=i, column=1, sticky="w", padx=(SPACING["sm"], 0))
            self._work_vars[label] = var

    def _build_phase_detail(self, body: ttk.Frame):
        # Fixed column width so value text doesn't cause container resize/flicker
        body.columnconfigure(0, minsize=92)
        body.columnconfigure(1, weight=1, minsize=240)
        self._phase_vars: Dict[str, tk.StringVar] = {}
        rows = [
            ("Current phase",   "—"),
            ("Phase progress",  "—"),
            ("Phase units processed", "0"),
            ("Phase elapsed",  "0s"),
            ("Current file",   ""),
        ]
        for i, (label, default) in enumerate(rows):
            ttk.Label(body, text=label + ":", style="Panel.Muted.TLabel",
                      font=font_tuple("data_label")).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=default)
            lbl = ttk.Label(body, textvariable=var, style="Panel.TLabel",
                           font=font_tuple("data_value"), wraplength=240)
            lbl.grid(row=i, column=1, sticky="w", padx=(SPACING["md"], 0))
            self._phase_vars[label] = var
        self._progress_bar = ttk.Progressbar(
            body, mode="indeterminate", length=240)
        self._progress_bar.grid(
            row=len(rows), column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _build_result_summary(self, body: ttk.Frame):
        body.columnconfigure(0, minsize=90)
        body.columnconfigure(1, weight=1, minsize=140)
        self._result_vars: Dict[str, tk.StringVar] = {}
        rows = [
            ("Duplicate groups", "—"),
            ("Duplicate files",  "—"),
            ("Reclaimable",      "—"),
            ("Verification",     "—"),
        ]
        for i, (label, default) in enumerate(rows):
            ttk.Label(body, text=label + ":", style="Panel.Muted.TLabel",
                      font=font_tuple("data_label")).grid(row=i, column=0, sticky="w", pady=1)
            var = tk.StringVar(value=default)
            ttk.Label(body, textvariable=var, style="Panel.TLabel",
                      font=font_tuple("data_value")).grid(
                row=i, column=1, sticky="w", padx=(SPACING["sm"], 0))
            self._result_vars[label] = var

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
        if self._scan_controller:
            self._scan_controller.handle_start_scan(
                path,
                options,
                on_progress=self._on_progress_fallback,
                on_complete=self._on_complete_fallback,
                on_error=self._on_error_fallback,
            )
        else:
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
        if self._scan_controller:
            self._scan_controller.handle_start_resume(
                scan_id,
                on_progress=self._on_progress_fallback,
                on_complete=self._on_complete_fallback,
                on_error=self._on_error_fallback,
            )
        else:
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
                           self._phase_vars["Current file"].set(_fixed_width_path(f, 40)))
        else:
            # No hub — fall back to direct progress update
            self.after(0, lambda p=progress: self._update_display_direct(p))

    def _update_display_direct(self, progress: ScanProgress) -> None:
        """Direct update path (no hub). Used only in hub-less mode."""
        from ..projections.metrics_projection import build_metrics_from_progress
        self._on_metrics(build_metrics_from_progress(progress))
        if progress.current_file:
            self._phase_vars["Current file"].set(
                _fixed_width_path(progress.current_file, 40))
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
            # Hub-less fallback: hydrate FinalScanResultsSummary directly from result
            fr = self.vm.final_results
            fr.duplicate_groups_total = len(result.duplicate_groups)
            fr.duplicate_files_total = result.total_duplicates
            fr.reclaimable_bytes_total = result.total_reclaimable_bytes
            fr.files_scanned_total = result.files_scanned
            fr.results_ready = True
            self._result_vars["Duplicate groups"].set(fmt_int(fr.duplicate_groups_total))
            self._result_vars["Duplicate files"].set(fmt_int(fr.duplicate_files_total))
            self._result_vars["Reclaimable"].set(fmt_bytes(fr.reclaimable_bytes_total))
        self._scan_completed = True
        self._defer(self._update_go_to_review_btn, "go_to_review_btn")
        self.after(0, lambda: self.on_complete(result))

    def _on_error_fallback(self, error: str) -> None:
        self.vm.is_scanning = False
        self._progress_bar.stop()
        self._cancel_elapsed()
        self.vm.error_message = error[:200]
        self._ribbon.set_state("failed", detail=error[:60])
        self._error_panel.set_message(self.vm.error_message)
        self._error_panel.show()

    def _on_error_panel_dismiss(self) -> None:
        self.vm.error_message = ""
        self._error_panel.hide()
        self.on_cancel()

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def _on_cancel(self) -> None:
        if not self.vm.is_scanning:
            self.on_cancel()
            return
        if messagebox.askyesno("Cancel Scan", "Cancel the current scan?"):
            if self._scan_controller:
                self._scan_controller.handle_cancel()
            else:
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

    def _update_go_to_review_btn(self) -> None:
        if self._scan_completed and self.on_go_to_review:
            self._cancel_btn.grid_remove()
            self._go_to_review_btn.grid()
        else:
            self._go_to_review_btn.grid_remove()
            self._cancel_btn.grid()

    def _on_go_to_review(self) -> None:
        if self.on_go_to_review:
            self.on_go_to_review()

    def _reset_vm(self) -> None:
        from ..projections.phase_projection import initial_phase_map
        self.vm.reset()
        self.vm.is_scanning = True
        self._scan_completed = False
        self._defer(self._update_go_to_review_btn, "go_to_review_btn")
        self._error_panel.hide()
        self._timeline.reset()
        self._events_list.delete(0, "end")
        for c in self._metric_cards.values():
            c.update("0")
        for v in self._work_vars.values():
            v.set("—")
        for v in self._phase_vars.values():
            v.set("—")
        for v in self._result_vars.values():
            v.set("—")

    def _schedule_elapsed(self) -> None:
        self._after_id = self.after(1000, self._tick_elapsed)

    def _tick_elapsed(self) -> None:
        if not self.vm.is_scanning:
            return
        elapsed = time.time() - self.vm._start_wall
        self._metric_cards["elapsed"].update(fmt_duration(elapsed))
        self._schedule_elapsed()

    def _cancel_elapsed(self) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None

    def on_show(self) -> None:
        pass
