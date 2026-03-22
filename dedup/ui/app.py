"""
CEREBRO Dedup Engine — Main Application
========================================
Modern-classic operations shell with:
  - Fixed left nav rail (Mission, Scan, Review, History, Diagnostics, Themes, Settings)
  - Persistent top command bar with theme switcher
  - Durable pipeline status strip
  - Toggleable insight drawer
  - 15-theme token system
  - ProjectionHub: canonical state contract between engine and UI
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox

try:
    from tkinterdnd2 import TkinterDnD  # type: ignore
except Exception:
    TkinterDnD = None

from ..engine.models import DeletionResult, ScanResult
from ..infrastructure.config import load_config, save_config
from ..orchestration.coordinator import ScanCoordinator
from .components.toast_manager import ToastManager
from .controller.review_controller import ReviewController
from .controller.scan_controller import ScanController
from .pages.diagnostics_page import DiagnosticsPage
from .pages.history_page import HistoryPage
from .pages.mission_page import MissionPage
from .pages.review_page import ReviewPage
from .pages.scan_page import ScanPage
from .pages.settings_page import SettingsPage
from .pages.theme_page import ThemePage
from .projections.history_projection import build_history_from_coordinator
from .projections.hub import ProjectionHub
from .shell.app_shell import AppShell
from .shell.shortcut_registry import ShortcutRegistry
from .state.hub_adapter import ProjectionHubStoreAdapter
from .state.store import LastScanSummaryState, MissionState, UIStateStore
from .theme import design_system
from .theme.theme_manager import get_theme_manager, parse_gradient_stops_from_raw
from .theme.theme_registry import get_theme
from .utils.backdrop import try_apply_mica
from .utils.formatting import fmt_bytes
from .utils.ui_state import UIState


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

    APP_NAME = "CEREBRO"
    APP_VERSION = "2.1.0"

    # Minimum window (56px nav + Review three-pane mins + page padding); users can resize down to here.
    MIN_WIDTH = 580
    MIN_HEIGHT = 320
    # Default first paint ≈ screenshot reference: ~45% × ~65% of primary monitor.
    STARTUP_WIDTH_FRAC = 0.45
    STARTUP_HEIGHT_FRAC = 0.65
    # Avoid absurd defaults on ultra-wide / 5K while staying "small vs screen".
    STARTUP_MAX_W_CAP = 1600
    STARTUP_MAX_H_CAP = 1000
    # If persisted width/height exceeds this fraction of the screen, it was almost certainly
    # maximize / large snap / full-height tile — do not restore (see also _on_close zoomed).
    SAVED_GEOMETRY_LARGE_FRAC = 0.74

    @classmethod
    def _default_startup_geometry(cls, sw: int, sh: int) -> tuple[int, int]:
        """~45% × ~65% of primary monitor (visual reference), clamped to mins, caps, and safe margins."""
        w = int(sw * cls.STARTUP_WIDTH_FRAC)
        h = int(sh * cls.STARTUP_HEIGHT_FRAC)
        w = max(cls.MIN_WIDTH, w)
        h = max(cls.MIN_HEIGHT, h)
        w = min(w, sw - 32)
        h = min(h, sh - 48)
        w = min(w, cls.STARTUP_MAX_W_CAP)
        h = min(h, cls.STARTUP_MAX_H_CAP)
        w = max(cls.MIN_WIDTH, w)
        h = max(cls.MIN_HEIGHT, h)
        return w, h

    def __init__(self):
        # ── Root window ──────────────────────────────────────────────
        if TkinterDnD is not None:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.title(f"{self.APP_NAME} Dedup Engine v{self.APP_VERSION}")
        self.root.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)

        # Hint Tk about DPI scaling to reduce blurry fonts on Windows.
        try:
            self.root.call("tk", "scaling", 1.0)
        except Exception:
            pass

        # ── State & config ───────────────────────────────────────────
        self.state = UIState()
        self.config = load_config()
        sw = max(1, int(self.root.winfo_screenwidth()))
        sh = max(1, int(self.root.winfo_screenheight()))
        default_w, default_h = self._default_startup_geometry(sw, sh)
        w = getattr(self.state.settings, "window_width", 0) or 0
        h = getattr(self.state.settings, "window_height", 0) or 0
        if w <= 0 or h <= 0:
            w, h = default_w, default_h
        else:
            lw = int(sw * self.SAVED_GEOMETRY_LARGE_FRAC)
            lh = int(sh * self.SAVED_GEOMETRY_LARGE_FRAC)
            if w >= lw or h >= lh:
                w, h = default_w, default_h
        # Migrate legacy installer / old auto defaults to proportional startup.
        if (w, h) == (1280, 820):
            w, h = default_w, default_h
        old_style_w = max(900, sw // 2)
        old_style_h = max(560, sh // 2)
        if (w, h) == (old_style_w, old_style_h):
            w, h = default_w, default_h
        prev_compact_w = max(860, sw // 4)
        prev_compact_h = max(480, sh // 4)
        prev_v2_w = max(720, min(sw // 6, 760))
        prev_v2_h = max(380, min(sh // 5, 480))
        prev_v3_w = max(600, min(sw // 8, 640))
        prev_v3_h = max(320, min(sh // 6, 400))
        if (w, h) in (
            (prev_compact_w, prev_compact_h),
            (860, 480),
            (prev_v2_w, prev_v2_h),
            (720, 380),
            (760, 480),
            (prev_v3_w, prev_v3_h),
            (600, 320),
            (640, 400),
        ):
            w, h = default_w, default_h
        # Upgrade prior "tiny default" iterations to the screenshot-based default.
        if 0 < w <= 660 and 0 < h <= 420:
            w, h = default_w, default_h
        geom_w = max(int(w), self.MIN_WIDTH)
        geom_h = max(int(h), self.MIN_HEIGHT)
        sx = int(getattr(self.state.settings, "window_x", -1) or -1)
        sy = int(getattr(self.state.settings, "window_y", -1) or -1)
        if sx >= 0 and sy >= 0:
            x, y = sx, sy
        else:
            x = max(0, (sw - geom_w) // 2)
            y = max(0, (sh - geom_h) // 2)
        self.root.geometry(f"{geom_w}x{geom_h}+{x}+{y}")

        design_system.apply_root_typography(self.root)

        self._toast = ToastManager(self.root)
        self._last_scan_toast_id: str | None = None

        # ── Coordinator ───────────────────────────────────────────────
        self.coordinator = ScanCoordinator()

        # ── Apply initial theme (density affects ttk font sizes / Treeview row height)
        design_system.set_ui_density(self.state.settings.density or "comfortable")
        self._apply_scene_theme()
        try_apply_mica(self.root, self.state.settings.win_mica_backdrop)

        # ── Build shell ───────────────────────────────────────────────
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.shell = AppShell(
            self.root,
            state=self.state,
            on_navigate=self._navigate,
            on_theme_change=self._on_theme_change,
            on_review_delete=self._review_delete_from_rail,
        )
        self.shell.grid(row=0, column=0, sticky="nsew")
        self.shell.status_strip.set_strip_click_handler(self._on_status_strip_click)

        # ── Create store first so ReviewController and store-fed pages can use it ───
        self.store = UIStateStore(tk_root=self.root)

        # ── Create ProjectionHub (after root exists) ──────────────────────────────
        self.hub = ProjectionHub(
            event_bus=self.coordinator.event_bus,
            tk_root=self.root,
        )
        self._hub_store_adapter = ProjectionHubStoreAdapter(self.hub, self.store)
        self._hub_store_adapter.start()
        self.store.set_ui_mode("advanced" if self.state.settings.advanced_mode else "simple")

        # ── Build pages (store is available for Mission, History, Review) ────────
        self._build_pages()
        self._wire_hub()

        # ── Register app-level state listeners ───────────────────────
        self.state.on("advanced_mode_changed", self._on_advanced_mode)
        self.state.on("density_changed", lambda _d=None: self._apply_preferences())

        # ── Navigate home ─────────────────────────────────────────────
        self._navigate("mission")
        self._apply_preferences()
        self._bind_global_shortcuts()

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

        # Scan page — store-driven display (hub feeds store via adapter)
        try:
            self._scan.attach_store(self.store)
        except AttributeError:
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
            on_open_last_review=lambda: self._navigate("review"),
            ui_state=self.state,
        )
        self.shell.register_page("mission", self._mission)
        self._mission.attach_store(self.store)

        self._scan_controller = ScanController(self.coordinator, self.store)
        self._scan = ScanPage(
            content,
            on_complete=self._on_scan_complete,
            on_cancel=self._on_scan_cancel,
            on_go_to_review=self._go_to_review_after_scan,
            scan_controller=self._scan_controller,
            ui_state=self.state,
        )
        self.shell.register_page("scan", self._scan)

        self._review = ReviewPage(
            content,
            on_delete_complete=self._on_delete_complete,
            on_new_scan=lambda: self._navigate("scan"),
            on_view_history=lambda: self._navigate("history"),
            store=self.store,
        )
        self._review_controller = ReviewController(
            self.coordinator,
            self.store,
            callbacks=self._review,
            toast_notify=lambda msg, ms: self._toast.show(msg, ms=ms),
        )
        self._review._review_controller = self._review_controller
        self.shell.register_page("review", self._review)

        self._history = HistoryPage(
            content,
            coordinator=self.coordinator,
            on_load_scan=self._on_load_history_scan,
            on_resume_scan=self._on_resume_scan,
            on_request_refresh=self._refresh_history_state,
        )
        self.shell.register_page("history", self._history)
        self._history.attach_store(self.store)

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

        self._theme_page = ThemePage(
            content,
            state=self.state,
            on_theme_change=self._on_theme_change,
            on_preference_changed=self._apply_preferences,
            on_toast=lambda msg: self._toast_notify(msg, ms=2600),
        )
        self.shell.register_page("themes", self._theme_page)

        # Apply persisted preferences to shell
        self._apply_preferences()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _review_delete_from_rail(self) -> None:
        """Left-rail DELETE — same execute path as former top-bar control."""
        self._review_controller.handle_execute_deletion()

    def _navigate(self, page: str):
        self.shell.show_page(page)
        self._update_page_actions(page)
        self._update_drawer_content(page)

    def _bind_global_shortcuts(self) -> None:
        """Global keyboard layer for studio navigation and shortcut help."""
        reg = ShortcutRegistry(self.root)
        reg.register("<Control-Key-1>", "Mission Control", lambda e: self._navigate("mission"))
        reg.register("<Control-Key-2>", "Live Scan Studio", lambda e: self._navigate("scan"))
        reg.register("<Control-Key-3>", "Decision Studio", lambda e: self._navigate("review"))
        reg.register("<Control-Key-4>", "History", lambda e: self._navigate("history"))
        reg.register("<Control-Key-5>", "Diagnostics", lambda e: self._navigate("diagnostics"))
        reg.register("<Control-Key-7>", "Themes", lambda e: self._navigate("themes"))
        reg.register("<Control-comma>", "Settings", lambda e: self._navigate("settings"))
        reg.register("<Control-backslash>", "Insights drawer", lambda e: self.shell.toggle_drawer())
        reg.register("?", "Shortcut help", lambda e: self._show_shortcuts_help())
        self._shortcut_registry = reg

    def _show_shortcuts_help(self) -> None:
        """Show compact keyboard cheat sheet."""
        global_lines = "\n".join(self._shortcut_registry.describe_lines())
        text = (
            "Global\n"
            f"{global_lines}\n\n"
            "Decision Studio\n"
            "  Ctrl+Left / Ctrl+Right  Previous/Next group\n"
            "  G / T / C               Gallery/Table/Compare mode\n"
            "  Space                   Quick look (selected file)\n"
            "  X                       Quick compare overlay\n"
            "  [ / ]                   Compare previous/next pair\n"
            "  K / Shift+K             Keep selected / Reset keeper to default (first file)\n"
            "  A                       Apply Smart Auto Select\n"
            "  P                       Preview Effects\n"
            "  U                       Undo guidance\n"
            "  Ctrl+Enter              Execute deletion\n"
        )
        messagebox.showinfo("Keyboard Shortcuts", text)

    def _update_page_actions(self, page: str):
        action_map = {
            "mission": [
                ("New Scan", "Accent.TButton", lambda: self._navigate("scan")),
                ("Resume", "Ghost.TButton", self._on_resume_latest),
            ],
            "scan": [
                ("Stop for later", "Ghost.TButton", self._on_scan_pause),
                ("Cancel", "Ghost.TButton", lambda: self._on_scan_cancel()),
                ("Copy Diag", "Ghost.TButton", self._copy_diagnostics),
            ],
            "review": [
                ("Preview Effects", "Ghost.TButton", lambda: self._review_controller.handle_preview_deletion()),
            ],
            "history": [
                ("Refresh", "Ghost.TButton", lambda: self._history.refresh()),
                ("Export", "Ghost.TButton", lambda: self._history.export_sessions_json()),
            ],
            "diagnostics": [
                ("Refresh", "Ghost.TButton", lambda: self._diagnostics.refresh()),
                ("Export", "Ghost.TButton", lambda: self._diagnostics.export_report_json()),
            ],
            "settings": [],
            "themes": [],
        }
        actions = list(action_map.get(page, []))
        if self.store.state.ui_mode == "simple":
            if page == "scan":
                actions = [a for a in actions if a[0] != "Copy Diag"]
            elif page in ("history", "diagnostics"):
                actions = [a for a in actions if a[0] != "Export"]
        self.shell.set_page_actions(actions)
        self.shell.top_bar.set_drawer_toggle_visible(page != "review")
        self.shell.nav_rail.set_review_delete_visible(page == "review")

    def _update_drawer_content(self, page: str):
        sections = []
        hub_session = self.hub.session

        if page == "scan":
            sections = [
                (
                    "Session",
                    [
                        ("ID", hub_session.session_id[:16] or "—"),
                        ("Phase", hub_session.current_phase or "—"),
                        ("Status", hub_session.status),
                        ("Resume", hub_session.resume_outcome_label or "—"),
                    ],
                ),
                (
                    "Engine",
                    [
                        ("Health", hub_session.engine_health),
                        ("Warns", str(hub_session.warnings_count)),
                        ("Config", hub_session.config_hash[:12] + "…" if hub_session.config_hash else "—"),
                    ],
                ),
            ]
        elif page == "review":
            # Stats and safety live on-page (Provenance + Safety panel); skip drawer to avoid duplicate "Insights" bulk.
            sections = []
        elif page == "history":
            sections = [
                (
                    "Stats",
                    [
                        ("Total", str(self._history.vm.total_scans)),
                        ("Resumable", str(self._history.vm.resumable_count)),
                    ],
                ),
            ]
        elif page == "diagnostics":
            phases = self.hub.phases
            running = next((p for p in phases.values() if p.status == "running"), None)
            sections = [
                (
                    "Live Phase",
                    [
                        ("Current", running.display_label if running else "—"),
                        ("Status", running.status if running else "—"),
                    ],
                ),
            ]
            if self.store.state.ui_mode == "advanced":
                sections.append(
                    (
                        "Compat",
                        [
                            ("Outcome", self.hub.compat.overall_resume_outcome or "—"),
                        ],
                    )
                )
        self.shell.set_drawer_content(sections)

    # ------------------------------------------------------------------
    # Scan lifecycle
    # ------------------------------------------------------------------

    def _on_start_scan(self, path: Path, options: dict):
        self._last_scan_toast_id = None
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
        self.state.scan_phase = "Results"
        self._review.load_result(result)
        self._navigate("review")
        if result.scan_id != self._last_scan_toast_id:
            self._last_scan_toast_id = result.scan_id
            try:
                n = len(result.duplicate_groups)
                self._toast_notify(f"Scan complete — {n:,} duplicate group(s). Review opened.", ms=4500)
            except Exception:
                pass

    def _go_to_review_after_scan(self):
        """Go to Review with last scan result (e.g. when user clicks 'Go to Review' on Scan page)."""
        result = self.coordinator.get_last_result()
        if result:
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
        failed = len(result.failed_files)
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
            recent_sessions.append(
                {
                    "scan_id": d.get("scan_id", ""),
                    "started_at": d.get("started_at", ""),
                    "roots": d.get("roots") or [],
                    "files_scanned": d.get("files_scanned", 0),
                    "duplicates_found": d.get("duplicates_found", 0),
                    "reclaimable_bytes": d.get("reclaimable_bytes", 0),
                    "status": d.get("status", "—"),
                    "duration_s": d.get("duration_s", 0),
                }
            )
        self.store.set_mission(
            MissionState(
                last_scan=last_scan,
                resumable_scan_ids=resumable_ids,
                recent_sessions=tuple(recent_sessions),
                recent_folders=recent_folders,
            )
        )

    def _refresh_history_state(self) -> None:
        """Build history slice from coordinator and push to store (History page subscribes)."""
        try:
            proj = build_history_from_coordinator(self.coordinator)
            self.store.set_history(proj)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Theme & settings
    # ------------------------------------------------------------------

    def _apply_scene_theme(self) -> None:
        get_theme_manager().apply(
            self.state.settings.theme_key,
            self.root,
            gradient_stops=parse_gradient_stops_from_raw(self.state.settings.custom_gradient_stops),
            sun_valley=self.state.settings.sun_valley_shell,
        )

    def _toast_notify(self, msg: str, ms: int = 3200) -> None:
        self._toast.show(msg, ms=ms, reduced_motion=bool(self.state.settings.reduced_motion))

    def _on_theme_change(self, key: str):
        self.state.settings.theme_key = key
        self._apply_scene_theme()
        self.shell.top_bar.set_current_theme(key)
        try:
            label = get_theme(key).get("name", key)
            self._toast_notify(f"Theme: {label}", ms=2800)
        except Exception:
            pass

    def _on_advanced_mode(self, active: bool):
        _ = active  # AppSettings.advanced_mode already updated by TopBar toggle
        self._apply_preferences()

    def _on_status_strip_click(self, _event=None):
        """Status strip is read-only telemetry; Advanced mode may use it to open Diagnostics."""
        if self.store.state.ui_mode != "advanced":
            return
        self._navigate("diagnostics")

    def _apply_preferences(self) -> None:
        """Apply UI preferences from state.settings to shell, store ui_mode, and gated chrome."""
        design_system.set_ui_density(self.state.settings.density or "comfortable")
        self._apply_scene_theme()
        try_apply_mica(self.root, self.state.settings.win_mica_backdrop)
        self.shell.apply_preferences()
        m = "advanced" if self.state.settings.advanced_mode else "simple"
        self.store.set_ui_mode(m)
        self.shell.status_strip.set_ui_mode(m)
        self._review.set_ui_mode(m)
        ap = self.shell.active_page
        if ap:
            self._update_page_actions(ap)
            self._update_drawer_content(ap)
        self._mission.sync_chrome()
        self._scan.sync_chrome()

    def _copy_diagnostics(self):
        try:
            sess = self.hub.session
            data = f"Session: {sess.session_id}\n"
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
            if not messagebox.askyesno("Scan in progress", "A scan is active. Cancel and exit?"):
                return
            self.coordinator.cancel_scan()
        # Shut down hub to stop its poll loop
        try:
            self.hub.shutdown()
        except Exception:
            pass
        # Persist geometry (do not save maximize / full-screen client size — that caused huge restarts)
        try:
            st = ""
            try:
                st = str(self.root.state() or "")
            except Exception:
                pass
            if st.lower() == "zoomed":
                self.state.settings.window_width = 0
                self.state.settings.window_height = 0
                self.state.settings.window_x = -1
                self.state.settings.window_y = -1
            else:
                self.state.settings.window_width = self.root.winfo_width()
                self.state.settings.window_height = self.root.winfo_height()
                self.state.settings.window_x = self.root.winfo_x()
                self.state.settings.window_y = self.root.winfo_y()
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
# Public alias for compatibility; CerebroApp is the canonical class name.
DedupApp = CerebroApp


def main():
    app = CerebroApp()
    app.run()


if __name__ == "__main__":
    main()
