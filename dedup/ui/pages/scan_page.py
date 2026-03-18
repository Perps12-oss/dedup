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
from tkinter import ttk, messagebox, filedialog
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
        on_complete: Callable[[ScanResult], None],
        on_cancel: Callable[[], None],
        on_go_to_review: Optional[Callable[[], None]] = None,
        scan_controller=None,
        coordinator: Optional[ScanCoordinator] = None,
        hub=None,      # ProjectionHub — injected by app.py after creation
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.coordinator  = coordinator  # Optional: fallback when scan_controller not set
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
        self._last_scan_path: Optional[Path] = None
        self._last_scan_options: Optional[dict] = None
        self._last_resume_id: str = ""
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
                    self._state_hint.set("Scan complete. Continue in Decision Studio.")
                    self._interrupt_banner.grid_remove()
                    self._defer(self._update_go_to_review_btn, "go_to_review_btn")
                elif terminal.status == "cancelled":
                    self._ribbon.set_state("idle", label_override="Cancelled")
                    self._state_hint.set("Scan interrupted. You can resume this session from Mission Control.")
                    self._show_interruption_banner("Scan interrupted. Resume where you left off?")
                elif terminal.status == "failed":
                    err_msg = (terminal.resume_reason or "Scan failed")[:200]
                    self.vm.error_message = err_msg
                    self._ribbon.set_state("failed", detail=err_msg[:60])
                    self._state_hint.set("Scan failed. Inspect diagnostics, then retry or resume.")
                    self._show_interruption_banner("Scan interrupted. Resume where you left off?")
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
            self._state_hint.set("Scan complete. Continue in Decision Studio.")
            self._interrupt_banner.grid_remove()
            self._defer(self._update_go_to_review_btn, "go_to_review_btn")
        elif proj.status == "cancelled":
            self._ribbon.set_state("idle", label_override="Cancelled")
            self._state_hint.set("Scan interrupted. You can resume this session from Mission Control.")
            self._show_interruption_banner("Scan interrupted. Resume where you left off?")
        elif proj.status == "failed":
            self._ribbon.set_state("failed",
                                   detail=proj.resume_reason[:60] if proj.resume_reason else "Error")
            self._state_hint.set("Scan failed. Inspect diagnostics, then retry or resume.")
            self._show_interruption_banner("Scan interrupted. Resume where you left off?")

    # ------------------------------------------------------------------
    # Widget rendering (granular — no whole-page repaint)
    # ------------------------------------------------------------------

    def _render_metrics(self) -> None:
        sm = self.vm.session_metrics
        pm = self.vm.phase_metrics
        rm = self.vm.result_metrics
        def _set_metric(key: str, value: str) -> None:
            card = self._metric_cards.get(key)
            if card is not None:
                card.update(value)
        # Session Metrics (scan-scope only)
        _set_metric("files_total", fmt_int(sm.files_discovered_total))
        _set_metric("dirs_scanned", fmt_int(sm.directories_scanned_total))
        # Defensive: never show absurd speed when elapsed is 0 or missing
        speed = sm.discovery_speed if sm.elapsed_total_s > 0 else 0.0
        _set_metric("discovery_speed",
            f"{speed:,.0f} files/sec" if speed > 0 else "—"
        )
        _set_metric("files_reused", fmt_int(sm.files_reused_total))
        _set_metric("dirs_reused", fmt_int(sm.dirs_reused_total))
        _set_metric("groups_live", fmt_int(sm.duplicate_groups_total))
        _set_metric("elapsed", fmt_duration(sm.elapsed_total_s))

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
        if hasattr(self, "_result_vars"):
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
        critical: list[str] = []
        progress: list[str] = []
        details: list[str] = []
        for entry in display:
            zone = self._classify_event_zone(entry)
            if zone == "critical":
                critical.append(entry)
            elif zone == "progress":
                progress.append(entry)
            else:
                details.append(entry)

        self._events_critical.delete(0, "end")
        self._events_progress.delete(0, "end")
        self._events_detail.delete(0, "end")
        for e in critical[:30]:
            self._events_critical.insert("end", e)
        for e in progress[:30]:
            self._events_progress.insert("end", e)
        for e in details[:50]:
            self._events_detail.insert("end", e)

        if critical:
            self._events_critical.see("end")
        if progress:
            self._events_progress.see("end")
        if details:
            self._events_detail.see("end")
        self._details_toggle_var.set(f"Show details ({len(details)})")

    def _classify_event_zone(self, entry: str) -> str:
        text = (entry or "").lower()
        if any(k in text for k in ("error", "warn", "failed", "exception", "critical")):
            return "critical"
        if any(k in text for k in ("scan", "files", "groups", "throughput", "progress", "phase")):
            return "progress"
        return "detail"

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        pad = SPACING["page"]

        hdr = ttk.Frame(self, padding=(pad, pad, pad, 0))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(0, weight=1)
        self._title_lbl = ttk.Label(hdr, text=f"{IC.SCAN}  Live Scan Studio", font=font_tuple("page_title"))
        self._title_lbl.grid(row=0, column=0, sticky="w")
        ttk.Label(
            hdr, text="Configure target, track phases, and monitor live activity in one place.",
            style="Muted.TLabel", font=font_tuple("page_subtitle")
        ).grid(row=1, column=0, sticky="w", pady=(SPACING["xs"], 0))
        self._state_hint = tk.StringVar(value="No active scan. Choose a target below to start.")
        ttk.Label(hdr, textvariable=self._state_hint, style="Muted.TLabel",
                  font=font_tuple("caption")).grid(row=2, column=0, sticky="w", pady=(SPACING["xs"], 0))
        self._cancel_btn = ttk.Button(hdr, text=f"{IC.STOPPED}  Cancel", style="Ghost.TButton", command=self._on_cancel)
        self._cancel_btn.grid(row=0, column=1, rowspan=3, sticky="e")
        self._go_to_review_btn = ttk.Button(
            hdr, text=f"{IC.REVIEW}  Review Results", style="Accent.TButton", command=self._on_go_to_review
        )
        self._go_to_review_btn.grid(row=0, column=2, rowspan=3, sticky="e", padx=(SPACING["sm"], 0))
        self._go_to_review_btn.grid_remove()

        # System state strip
        strip = ttk.Frame(self, padding=(pad, SPACING["sm"], pad, 0))
        strip.grid(row=1, column=0, sticky="ew")
        strip.columnconfigure(0, weight=1)
        self._ribbon = StatusRibbon(strip)
        self._ribbon.grid(row=0, column=0, sticky="ew")

        # Alerts
        self._interrupt_banner = ttk.Frame(self, style="Panel.TFrame", padding=(pad, SPACING["sm"], pad, SPACING["sm"]))
        self._interrupt_banner.grid(row=2, column=0, sticky="ew", padx=pad, pady=(SPACING["sm"], 0))
        self._interrupt_msg = tk.StringVar(value="Scan interrupted. Resume where you left off?")
        ttk.Label(self._interrupt_banner, textvariable=self._interrupt_msg,
                  style="Panel.Warning.TLabel", font=font_tuple("body_bold")).pack(anchor="w")
        _ibtn = ttk.Frame(self._interrupt_banner, style="Panel.TFrame")
        _ibtn.pack(anchor="w", pady=(SPACING["xs"], 0))
        ttk.Button(_ibtn, text="Resume", style="Accent.TButton",
                   command=self._on_resume_interrupted).pack(side="left", padx=(0, SPACING["sm"]))
        ttk.Button(_ibtn, text="Restart", style="Ghost.TButton",
                   command=self._on_restart_interrupted).pack(side="left", padx=(0, SPACING["sm"]))
        ttk.Button(_ibtn, text="Dismiss", style="Ghost.TButton",
                   command=self._on_dismiss_interrupt).pack(side="left")
        self._interrupt_banner.grid_remove()

        self._degraded_banner = DegradedBanner(self, message="", on_dismiss=lambda: self._degraded_banner.hide())
        self._degraded_banner.grid(row=2, column=0, sticky="ew", padx=pad, pady=(SPACING["sm"], 0))
        self._degraded_banner.hide()

        self._error_panel = ErrorPanel(self, message="", retry_label="Back", on_retry=self._on_error_panel_dismiss)
        self._error_panel.grid(row=2, column=0, sticky="ew", padx=pad, pady=(SPACING["sm"], 0))
        self._error_panel.hide()

        # Main two-column dashboard
        main = ttk.Frame(self, padding=(pad, SPACING["md"], pad, pad))
        main.grid(row=3, column=0, sticky="nsew")
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=3)
        main.rowconfigure(2, weight=1)

        # Left rail
        target_card = SectionCard(main, title=f"{IC.FOLDER}  Scan Target")
        target_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["sm"]), pady=(0, SPACING["md"]))
        self._build_scan_target(target_card.body)

        tl_card = SectionCard(main, title=f"{IC.ACTIVE}  Phase Timeline")
        tl_card.grid(row=1, column=0, sticky="ew", padx=(0, SPACING["sm"]), pady=(0, SPACING["md"]))
        self._timeline = PhaseTimeline(tl_card.body)
        self._timeline.pack(fill="x")

        phase_card = SectionCard(main, title=f"{IC.ACTIVE}  Progress & Session")
        phase_card.grid(row=2, column=0, sticky="nsew", padx=(0, SPACING["sm"]))
        self._build_phase_detail(phase_card.body)

        # Right rail
        metrics_card = SectionCard(main, title=f"{IC.SPEED}  Live Metrics")
        metrics_card.grid(row=0, column=1, sticky="ew", pady=(0, SPACING["md"]))
        self._build_live_metrics(metrics_card.body)

        self._work_card = SectionCard(main, title=f"{IC.SHIELD}  Health & Compatibility")
        self._work_card.grid(row=1, column=1, sticky="ew", pady=(0, SPACING["md"]))
        self._build_work_saved(self._work_card.body)

        events_card = SectionCard(main, title=f"{IC.INFO}  Activity Feed")
        events_card.grid(row=2, column=1, sticky="nsew")
        self._build_events(events_card.body)

    def _build_scan_target(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        self._target_path_var = tk.StringVar()
        self._scan_mode_var = tk.StringVar(value="Deep")

        ttk.Label(
            body,
            text="Select one folder root and start from here without returning to Mission.",
            style="Panel.Muted.TLabel",
            font=font_tuple("caption"),
        ).grid(row=0, column=0, sticky="w", pady=(0, SPACING["sm"]))

        target_row = ttk.Frame(body, style="Panel.TFrame")
        target_row.grid(row=1, column=0, sticky="ew", pady=(0, SPACING["sm"]))
        target_row.columnconfigure(0, weight=1)
        ttk.Entry(target_row, textvariable=self._target_path_var).grid(row=0, column=0, sticky="ew", padx=(0, SPACING["sm"]))
        ttk.Button(target_row, text="Browse…", style="Ghost.TButton",
                   command=self._on_browse_target).grid(row=0, column=1)

        mode_row = ttk.Frame(body, style="Panel.TFrame")
        mode_row.grid(row=2, column=0, sticky="w", pady=(0, SPACING["sm"]))
        ttk.Label(mode_row, text="Mode:", style="Panel.Muted.TLabel",
                  font=font_tuple("body")).grid(row=0, column=0, sticky="w", padx=(0, SPACING["sm"]))
        ttk.Combobox(
            mode_row, textvariable=self._scan_mode_var, state="readonly",
            values=["Deep", "Fast"], width=12
        ).grid(row=0, column=1, sticky="w")

        actions = ttk.Frame(body, style="Panel.TFrame")
        actions.grid(row=3, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        actions.columnconfigure(2, weight=1)
        ttk.Button(actions, text=f"{IC.SCAN}  Start Scan", style="Accent.TButton",
                   command=self._on_start_from_target).grid(row=0, column=0, sticky="ew", padx=(0, SPACING["sm"]))
        ttk.Button(actions, text=f"{IC.RESUME}  Resume", style="Ghost.TButton",
                   command=self._on_resume_interrupted).grid(row=0, column=1, sticky="ew", padx=(0, SPACING["sm"]))
        ttk.Button(actions, text=f"{IC.STOPPED}  Cancel", style="Ghost.TButton",
                   command=self._on_cancel).grid(row=0, column=2, sticky="ew")

    def _build_live_metrics(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        self._metric_cards: Dict[str, MetricCard] = {}
        specs = [
            ("files_total",  f"{IC.FILE}  Files Scanned",        "0",            "neutral"),
            ("groups_live",  f"{IC.GROUPS} Duplicate Groups",    "0",            "accent"),
            ("dirs_scanned", f"{IC.FOLDER} Dirs Scanned",        "0",            "neutral"),
            ("discovery_speed", f"{IC.SPEED}  Throughput",       "—",            "neutral"),
            ("elapsed",      f"{IC.SPEED}  Elapsed Total",       "0s",           "neutral"),
        ]
        card_width = 0
        for i, (key, label, val, variant) in enumerate(specs):
            c = MetricCard(body, label=label, value=val, variant=variant, width=card_width)
            c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=SPACING["xs"], pady=SPACING["xs"])
            self._metric_cards[key] = c

    def _build_work_saved(self, body: ttk.Frame):
        body.columnconfigure(0, minsize=90)
        body.columnconfigure(1, weight=1, minsize=140)
        self._work_vars: Dict[str, tk.StringVar] = {}
        rows = [
            ("Reuse mode",        "fresh"),
            ("Hash cache hit rate", "—"),
            ("Compatible prior",  "—"),
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
        body.rowconfigure(1, weight=1)
        body.rowconfigure(3, weight=1)
        body.rowconfigure(5, weight=1)

        ttk.Label(body, text="Critical events", style="Panel.Warning.TLabel",
                  font=font_tuple("data_label")).grid(row=0, column=0, sticky="w", pady=(0, 2))
        crit_wrap = ttk.Frame(body, style="Panel.TFrame")
        crit_wrap.grid(row=1, column=0, sticky="nsew")
        crit_wrap.columnconfigure(0, weight=1)
        crit_wrap.rowconfigure(0, weight=1)
        self._events_critical = tk.Listbox(
            crit_wrap, height=3, selectmode="browse", font=("Segoe UI", 12),
            borderwidth=0, highlightthickness=0, activestyle="none")
        crit_scroll = ttk.Scrollbar(crit_wrap, orient="vertical", command=self._events_critical.yview)
        self._events_critical.configure(yscrollcommand=crit_scroll.set)
        self._events_critical.grid(row=0, column=0, sticky="nsew")
        crit_scroll.grid(row=0, column=1, sticky="ns")

        ttk.Label(body, text="Progress events", style="Panel.TLabel",
                  font=font_tuple("data_label")).grid(row=2, column=0, sticky="w", pady=(8, 2))
        prog_wrap = ttk.Frame(body, style="Panel.TFrame")
        prog_wrap.grid(row=3, column=0, sticky="nsew")
        prog_wrap.columnconfigure(0, weight=1)
        prog_wrap.rowconfigure(0, weight=1)
        self._events_progress = tk.Listbox(
            prog_wrap, height=3, selectmode="browse", font=("Segoe UI", 12),
            borderwidth=0, highlightthickness=0, activestyle="none")
        prog_scroll = ttk.Scrollbar(prog_wrap, orient="vertical", command=self._events_progress.yview)
        self._events_progress.configure(yscrollcommand=prog_scroll.set)
        self._events_progress.grid(row=0, column=0, sticky="nsew")
        prog_scroll.grid(row=0, column=1, sticky="ns")

        ctrl = ttk.Frame(body, style="Panel.TFrame")
        ctrl.grid(row=4, column=0, sticky="ew", pady=(8, 2))
        self._details_visible = tk.BooleanVar(value=False)
        self._details_toggle_var = tk.StringVar(value="Show details (0)")
        ttk.Button(ctrl, textvariable=self._details_toggle_var, style="Ghost.TButton",
                   command=self._toggle_details).pack(side="left")

        self._detail_wrap = ttk.Frame(body, style="Panel.TFrame")
        self._detail_wrap.grid(row=5, column=0, sticky="nsew")
        self._detail_wrap.columnconfigure(0, weight=1)
        self._detail_wrap.rowconfigure(0, weight=1)
        self._events_detail = tk.Listbox(
            self._detail_wrap, height=4, selectmode="browse", font=("Segoe UI", 12),
            borderwidth=0, highlightthickness=0, activestyle="none")
        detail_scroll = ttk.Scrollbar(self._detail_wrap, orient="vertical", command=self._events_detail.yview)
        self._events_detail.configure(yscrollcommand=detail_scroll.set)
        self._events_detail.grid(row=0, column=0, sticky="nsew")
        detail_scroll.grid(row=0, column=1, sticky="ns")
        self._detail_wrap.grid_remove()

    def _toggle_details(self) -> None:
        visible = bool(self._details_visible.get())
        if visible:
            self._detail_wrap.grid_remove()
            self._details_visible.set(False)
        else:
            self._detail_wrap.grid()
            self._details_visible.set(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _on_browse_target(self) -> None:
        path = filedialog.askdirectory(title="Select Folder to Scan")
        if path:
            self._target_path_var.set(str(Path(path).resolve()))

    def _on_start_from_target(self) -> None:
        path_str = self._target_path_var.get().strip()
        if not path_str:
            messagebox.showerror("Start Scan", "Choose a folder target first.")
            return
        path = Path(path_str).resolve()
        if not path.exists() or not path.is_dir():
            messagebox.showerror("Start Scan", f"Invalid path: {path}")
            return
        mode = (self._scan_mode_var.get() or "Deep").lower()
        options = {
            "scan_subfolders": True,
            "include_hidden": False,
            "min_size": 1024 if mode == "deep" else 4096,
            "media_category": "all",
            "scan_mode": mode,
        }
        self.start_scan(path, options)

    def start_scan(self, path: Path, options: dict) -> None:
        self._reset_vm()
        self._last_scan_path = Path(path)
        self._last_scan_options = dict(options or {})
        if hasattr(self, "_target_path_var"):
            self._target_path_var.set(str(path))
        self._title_lbl.configure(text=f"{IC.SCAN}  Scanning — {path.name}")
        self._state_hint.set("Scan running. Activity Feed shows live progress and critical events.")
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
        elif self.coordinator:
            self.coordinator.start_scan(
                roots=[path],
                on_progress=self._on_progress_fallback,
                on_complete=self._on_complete_fallback,
                on_error=self._on_error_fallback,
                **options,
            )

    def start_resume(self, scan_id: str) -> None:
        self._reset_vm()
        self._last_resume_id = scan_id
        self._title_lbl.configure(text=f"{IC.RESUME}  Resuming scan…")
        self._state_hint.set("Resuming interrupted session from checkpoint.")
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
        elif self.coordinator:
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
        self._state_hint.set("Scan complete. Continue in Decision Studio.")
        self._interrupt_banner.grid_remove()
        self._defer(self._update_go_to_review_btn, "go_to_review_btn")
        self.after(0, lambda: self.on_complete(result))

    def _on_error_fallback(self, error: str) -> None:
        self.vm.is_scanning = False
        self._progress_bar.stop()
        self._cancel_elapsed()
        self.vm.error_message = error[:200]
        self._state_hint.set("Scan failed. Review the error and retry.")
        self._show_interruption_banner("Scan interrupted. Resume where you left off?")
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
            elif self.coordinator:
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
        self._events_critical.delete(0, "end")
        self._events_progress.delete(0, "end")
        self._events_detail.delete(0, "end")
        self._details_toggle_var.set("Show details (0)")
        for c in self._metric_cards.values():
            c.update("0")
        for v in self._work_vars.values():
            v.set("—")
        for v in self._phase_vars.values():
            v.set("—")
        if hasattr(self, "_result_vars"):
            for v in self._result_vars.values():
                v.set("—")
        self._state_hint.set("Preparing scan session…")
        self._interrupt_banner.grid_remove()

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

    def _show_interruption_banner(self, text: str) -> None:
        self._interrupt_msg.set(text)
        self._interrupt_banner.grid()

    def _on_dismiss_interrupt(self) -> None:
        self._interrupt_banner.grid_remove()

    def _on_resume_interrupted(self) -> None:
        scan_id = self._last_resume_id
        if not scan_id and self._scan_controller and hasattr(self._scan_controller, "get_resumable_scan_ids"):
            ids = self._scan_controller.get_resumable_scan_ids() or []
            if ids:
                scan_id = ids[0]
        if not scan_id:
            messagebox.showinfo("Resume", "No resumable scan available.")
            return
        self.start_resume(scan_id)
        self._interrupt_banner.grid_remove()

    def _on_restart_interrupted(self) -> None:
        if self._last_scan_path and self._last_scan_options is not None:
            self.start_scan(self._last_scan_path, dict(self._last_scan_options))
            self._interrupt_banner.grid_remove()
            return
        messagebox.showinfo("Restart", "No previous scan request available to restart.")
