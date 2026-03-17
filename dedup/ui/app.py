"""
CEREBRO Dedup Engine — Main Application
========================================
Modern-classic operations shell with:
  - Fixed left nav rail (6 pages)
  - Persistent top command bar with theme switcher
  - Durable pipeline status strip
  - Toggleable insight drawer
  - 15-theme token system
  - ProjectionHub: canonical state contract between engine and UI
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional

try:
    from tkinterdnd2 import TkinterDnD  # type: ignore
except Exception:
    TkinterDnD = None

from ..orchestration.coordinator import ScanCoordinator
from ..infrastructure.config import load_config, save_config
from ..engine.models import ScanResult, DeletionResult

from .theme.theme_manager import get_theme_manager
from .utils.formatting import fmt_bytes, fmt_int, fmt_duration
from .utils.ui_state import UIState, load_settings, save_settings

from .shell.app_shell import AppShell
from .pages.mission_page import MissionPage
from .pages.scan_page import ScanPage
from .controller.review_controller import ReviewController
from .pages.review_page import ReviewPage
from .pages.history_page import HistoryPage
from .pages.diagnostics_page import DiagnosticsPage
from .pages.settings_page import SettingsPage

from .projections.hub import ProjectionHub
from .state.store import UIStateStore, MissionState, LastScanSummaryState
from .state.hub_adapter import ProjectionHubStoreAdapter


class CerebroApp:
    """
    CEREBRO Dedup Engine — root application controller.

    Owns the Tk root, AppShell, pages, coordinator, and ProjectionHub.

    Projection wiring:
      coordinator.event_bus
        → ProjectionHub (subscribes to all ScanEventType events)
          → StatusStrip.subscribe_to_hub()
          → TopBar.subscribe_to_hub()
          → ScanPage.attach_hub()
          → DiagnosticsPage.attach_hub()  (shares phase + compat projections)

    Pages are intentionally NOT all wired to the hub — only those that consume
    live scan state need it.  Mission, History, Review, and Settings are
    refreshed on demand (page focus, scan completion) to keep wiring simple.
    """

    APP_NAME    = "CEREBRO"
    APP_VERSION = "2.1.0"
    MIN_WIDTH   = 1100
    MIN_HEIGHT  = 700

    def __init__(self):
        # ── Root window ──────────────────────────────────────────────
        if TkinterDnD is not None:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.title(f"{self.APP_NAME} Dedup Engine v{self.APP_VERSION}")
        self.root.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)

        # ── State & config ───────────────────────────────────────────
        self.state    = UIState()
        self.config   = load_config()
        w = getattr(self.state.settings, "window_width",  self.MIN_WIDTH)
        h = getattr(self.state.settings, "window_height", self.MIN_HEIGHT)
        self.root.geometry(f"{max(w, self.MIN_WIDTH)}x{max(h, self.MIN_HEIGHT)}")

        # ── Coordinator ───────────────────────────────────────────────
        self.coordinator = ScanCoordinator()

        # ── Apply initial theme ───────────────────────────────────────
        tm = get_theme_manager()
        tm.apply(self.state.settings.theme_key, self.root)

        # ── Build shell ───────────────────────────────────────────────
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.shell = AppShell(
            self.root,
            state=self.state,
            on_navigate=self._navigate,
            on_theme_change=self._on_theme_change,
        )
        self.shell.grid(row=0, column=0, sticky="nsew")

        # ── Build pages ───────────────────────────────────────────────
        self._build_pages()

        # ── Create ProjectionHub (after root + pages exist) ───────────
        self.hub = ProjectionHub(
            event_bus=self.coordinator.event_bus,
            tk_root=self.root,
        )
        # UIStateStore: canonical consumer of projected live state (Step 1).
        self.store = UIStateStore(tk_root=self.root)
        self._hub_store_adapter = ProjectionHubStoreAdapter(self.hub, self.store)
        self._hub_store_adapter.start()
        self._wire_hub()

        # ── Register app-level state listeners ───────────────────────
        self.state.on("advanced_mode_changed", self._on_advanced_mode)

        # ── Apply persisted UI preferences (drawer, density, etc) ────
        self.shell.apply_preferences()

        # ── Navigate home ─────────────────────────────────────────────
        self._navigate("mission")

        # ── Window close ─────────────────────────────────────────────
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Hub wiring
    # ------------------------------------------------------------------

    def _wire_hub(self) -> None:
        """Connect ProjectionHub to all shell widgets and pages that need live updates."""
        import logging
        _log = logging.getLogger(__name__)
        # Shell widgets — always visible
        try:
            self.shell.status_strip.subscribe_to_hub(self.hub)
        except AttributeError:
            _log.debug("StatusStrip.subscribe_to_hub not available")
        try:
            self.shell.top_bar.subscribe_to_hub(self.hub)
        except AttributeError:
            _log.debug("TopBar.subscribe_to_hub not available")
        try:
            self.shell.status_strip.subscribe_to_store(self.store)
        except AttributeError:
            _log.debug("StatusStrip.subscribe_to_store not available")

        # Scan page — primary live-update consumer
        self._scan.attach_hub(self.hub)

        # Diagnostics page — renders from store (phase, compat, events_log)
        try:
            self._diagnostics.attach_store(self.store)
        except AttributeError:
            _log.debug("DiagnosticsPage.attach_store not available")

        # App-level terminal handler — navigate to review on completion
        def _on_terminal(proj) -> None:
            if proj.status == "completed":
                # Retrieve result and navigate to review
                result = self.coordinator.get_last_result()
                if result:
                    self._review.load_result(result)
                    self._navigate("review")
        self.hub.subscribe("terminal", _on_terminal)

    # ------------------------------------------------------------------
    # Page construction
    # ------------------------------------------------------------------

    def _build_pages(self):
        content = self.shell.content

        self._mission = MissionPage(
            content,
            on_start_scan=self._on_start_scan,
            on_resume_scan=self._on_resume_scan,
            coordinator=self.coordinator,
            on_request_refresh=self._refresh_mission_state,
        )
        self.shell.register_page("mission", self._mission)
        self._mission.attach_store(self.store)

        self._scan = ScanPage(
            content,
            coordinator=self.coordinator,
            on_complete=self._on_scan_complete,
            on_cancel=self._on_scan_cancel,
        )
        self.shell.register_page("scan", self._scan)

        self._review_controller = ReviewController(self.coordinator)
        self._review = ReviewPage(
            content,
            coordinator=self.coordinator,
            on_delete_complete=self._on_delete_complete,
            review_controller=self._review_controller,
        )
        self._review_controller.attach_page(self._review)
        self.shell.register_page("review", self._review)

        self._history = HistoryPage(
            content,
            coordinator=self.coordinator,
            on_load_scan=self._on_load_history_scan,
            on_resume_scan=self._on_resume_scan,
        )
        self.shell.register_page("history", self._history)

        self._diagnostics = DiagnosticsPage(
            content,
            coordinator=self.coordinator,
        )
        self.shell.register_page("diagnostics", self._diagnostics)

        self._settings = SettingsPage(
            content,
            state=self.state,
            on_theme_change=self._on_theme_change,
            on_preference_changed=self._apply_preferences,
        )
        self.shell.register_page("settings", self._settings)

        # Apply persisted preferences to shell
        self._apply_preferences()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate(self, page: str):
        self.shell.show_page(page)
        self._update_page_actions(page)
        self._update_drawer_content(page)

    def _update_page_actions(self, page: str):
        action_map = {
            "mission":     [
                ("New Scan",     "Accent.TButton", lambda: self._navigate("scan")),
                ("Resume",       "Ghost.TButton",  self._on_resume_latest),
            ],
            "scan":        [
                ("Pause",        "Ghost.TButton",  self._on_scan_pause),
                ("Cancel",       "Ghost.TButton",  lambda: self._on_scan_cancel()),
                ("Copy Diag",    "Ghost.TButton",  self._copy_diagnostics),
            ],
            "review":      [
                ("Preview Effects", "Ghost.TButton",  lambda: self._review._on_dry_run()),
                ("DELETE",          "Danger.TButton", lambda: self._review._on_execute()),
            ],
            "history":     [
                ("Refresh",      "Ghost.TButton",  lambda: self._history._refresh()),
                ("Export",       "Ghost.TButton",  lambda: None),
            ],
            "diagnostics": [
                ("Refresh",      "Ghost.TButton",  lambda: self._diagnostics._refresh()),
                ("Export",       "Ghost.TButton",  lambda: None),
            ],
            "settings":    [],
        }
        self.shell.set_page_actions(action_map.get(page, []))

    def _update_drawer_content(self, page: str):
        sections = []
        hub_session = self.hub.session

        if page == "scan":
            sections = [
                ("Session", [
                    ("ID",      hub_session.session_id[:16] or "—"),
                    ("Phase",   hub_session.current_phase or "—"),
                    ("Status",  hub_session.status),
                    ("Resume",  hub_session.resume_outcome_label or "—"),
                ]),
                ("Engine", [
                    ("Health",  hub_session.engine_health),
                    ("Warns",   str(hub_session.warnings_count)),
                    ("Config",  hub_session.config_hash[:12] + "…"
                                if hub_session.config_hash else "—"),
                ]),
            ]
        elif page == "review":
            sections = [
                ("Review", [
                    ("Groups",    str(self._review.vm.total_groups)),
                    ("Delete",    str(self._review.vm.delete_count)),
                    ("Keep",      str(self._review.vm.keep_count)),
                    ("Reclaim",   fmt_bytes(self._review.vm.reclaimable_bytes)),
                ]),
                ("Safety", [
                    ("Mode",      "Trash"),
                    ("Revalidate","ON"),
                    ("Audit",     "ACTIVE"),
                ]),
            ]
        elif page == "history":
            sections = [
                ("Stats", [
                    ("Total",     str(self._history.vm.total_scans)),
                    ("Resumable", str(self._history.vm.resumable_count)),
                ]),
            ]
        elif page == "diagnostics":
            phases = self.hub.phases
            running = next(
                (p for p in phases.values() if p.status == "running"), None)
            sections = [
                ("Live Phase", [
                    ("Current",  running.display_label if running else "—"),
                    ("Status",   running.status if running else "—"),
                ]),
                ("Compat", [
                    ("Outcome",  self.hub.compat.overall_resume_outcome or "—"),
                ]),
            ]
        self.shell.set_drawer_content(sections)

    # ------------------------------------------------------------------
    # Scan lifecycle
    # ------------------------------------------------------------------

    def _on_start_scan(self, path: Path, options: dict):
        self._navigate("scan")
        self._scan.start_scan(path, options)
        self.state.scan_status = "Scanning"

    def _on_resume_scan(self, scan_id: str):
        self._navigate("scan")
        self._scan.start_resume(scan_id)
        self.state.scan_status = "Resuming"

    def _on_resume_latest(self):
        try:
            ids = self.coordinator.get_resumable_scan_ids() or []
        except Exception:
            ids = []
        if ids:
            self._on_resume_scan(ids[0])
        else:
            self._navigate("scan")

    def _on_scan_complete(self, result: ScanResult):
        """
        Called via the ScanPage fallback on_complete callback.
        With hub attached, the terminal projection handler also fires — the hub
        path is primary; this callback fires independently and is safe to call
        twice (ReviewPage.load_result is idempotent on the same result).
        """
        self.state.scan_status = "Completed"
        self.state.scan_phase  = "Results"
        self._review.load_result(result)
        self._navigate("review")

    def _on_scan_pause(self):
        """Stop the scan and return to mission so the user can resume later."""
        if self.coordinator.is_scanning:
            self.coordinator.cancel_scan()
        self.state.scan_status = "Paused"
        self._navigate("mission")

    def _on_scan_cancel(self):
        if self.coordinator.is_scanning:
            self.coordinator.cancel_scan()
        self.state.scan_status = "Cancelled"
        self._navigate("mission")

    def _on_delete_complete(self, result: DeletionResult):
        deleted = len(result.deleted_files)
        failed  = len(result.failed_files)
        self.state.emit("delete_complete", {"deleted": deleted, "failed": failed})

    def _on_load_history_scan(self, scan_id: str):
        result = self.coordinator.load_scan(scan_id)
        if result:
            self._review.load_result(result)
            self._navigate("review")

    def _refresh_mission_state(self) -> None:
        """Build mission slice from coordinator and push to store (Mission page subscribes)."""
        try:
            raw = self.coordinator.get_history(limit=8) or []
        except Exception:
            raw = []
        try:
            resumable_ids = tuple(self.coordinator.get_resumable_scan_ids() or [])
        except Exception:
            resumable_ids = ()
        try:
            recent_folders = tuple(self.coordinator.get_recent_folders() or [])[:10]
        except Exception:
            recent_folders = ()
        last_scan = None
        if raw:
            d = raw[0]
            last_scan = LastScanSummaryState(
                files_scanned=int(d.get("files_scanned") or 0),
                duplicate_groups=int(d.get("duplicates_found") or 0),
                reclaimable_bytes=int(d.get("reclaimable_bytes") or 0),
                duration_s=float(d.get("duration_s") or 0),
            )
        recent_sessions = []
        for d in raw:
            recent_sessions.append({
                "scan_id": d.get("scan_id", ""),
                "started_at": d.get("started_at", ""),
                "roots": d.get("roots") or [],
                "files_scanned": d.get("files_scanned", 0),
                "duplicates_found": d.get("duplicates_found", 0),
                "reclaimable_bytes": d.get("reclaimable_bytes", 0),
                "status": d.get("status", "—"),
                "duration_s": d.get("duration_s", 0),
            })
        self.store.set_mission(MissionState(
            last_scan=last_scan,
            resumable_scan_ids=resumable_ids,
            recent_sessions=tuple(recent_sessions),
            recent_folders=recent_folders,
        ))

    # ------------------------------------------------------------------
    # Theme & settings
    # ------------------------------------------------------------------

    def _on_theme_change(self, key: str):
        self.state.settings.theme_key = key
        tm = get_theme_manager()
        tm.apply(key, self.root)
        self.shell.top_bar.set_current_theme(key)

    def _on_advanced_mode(self, active: bool):
        self.shell.apply_preferences()

    def _apply_preferences(self) -> None:
        """Apply UI preferences from state.settings to shell and pages."""
        self.shell.apply_preferences()

    def _copy_diagnostics(self):
        try:
            sess = self.hub.session
            data  = f"Session: {sess.session_id}\n"
            data += f"Phase:   {sess.current_phase}\n"
            data += f"Status:  {sess.status}\n"
            data += f"Health:  {sess.engine_health}\n"
            data += f"Resume:  {sess.resume_outcome_label}\n"
            data += f"Reason:  {sess.resume_reason}\n"
            self.root.clipboard_clear()
            self.root.clipboard_append(data)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_close(self):
        if self.coordinator.is_scanning:
            if not messagebox.askyesno("Scan in progress",
                                       "A scan is active. Cancel and exit?"):
                return
            self.coordinator.cancel_scan()
        # Shut down hub to stop its poll loop
        try:
            self.hub.shutdown()
        except Exception:
            pass
        # Persist geometry
        try:
            self.state.settings.window_width  = self.root.winfo_width()
            self.state.settings.window_height = self.root.winfo_height()
            self.state.save()
        except Exception:
            pass
        save_config(self.config)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Legacy shim
# ---------------------------------------------------------------------------
DedupApp = CerebroApp


def main():
    app = CerebroApp()
    app.run()


if __name__ == "__main__":
    main()
