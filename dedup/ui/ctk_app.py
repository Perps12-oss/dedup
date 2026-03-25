"""
CustomTkinter application shell — same orchestration contracts as CerebroApp (ttk).

ProjectionHub → UIStateStore, ScanController, ReviewController, and ToastManager are shared
with the classic UI; only widgets differ.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from .. import __version__
from ..engine.models import ScanResult
from ..orchestration.coordinator import ScanCoordinator
from .components.toast_manager import ToastManager
from .controller.review_controller import ReviewController
from .controller.scan_controller import ScanController
from .ctk_action_contracts import KeepPolicy, PostScanRoute, ScanMode, ScanStartPayload
from .ctk_pages.diagnostics_page import DiagnosticsPageCTK
from .ctk_pages.history_page import HistoryPageCTK
from .ctk_pages.mission_page import MissionPageCTK
from .ctk_pages.review_page import ReviewPageCTK
from .ctk_pages.scan_page import ScanPageCTK
from .ctk_pages.settings_page import SettingsPageCTK
from .ctk_pages.themes_page import ThemesPageCTK
from .ctk_pages.welcome_page import WelcomePageCTK
from .projections.history_projection import build_history_from_coordinator
from .projections.hub import ProjectionHub
from .state.hub_adapter import ProjectionHubStoreAdapter
from .state.store import LastScanSummaryState, MissionState, UIStateStore
from .utils.formatting import fmt_bytes
from .utils.ui_state import UIState


class CerebroCTKApp:
    """CustomTkinter shell with the same hub/store/controller stack as the classic UI."""

    APP_NAME = "CEREBRO"
    APP_VERSION = __version__

    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title(f"{self.APP_NAME} Dedup Engine v{self.APP_VERSION}")
        self.root.geometry("1180x760")
        self.root.minsize(760, 480)

        self.state = UIState()
        self._coordinator = ScanCoordinator()
        self.store = UIStateStore(tk_root=self.root)
        self.hub = ProjectionHub(event_bus=self.coordinator.event_bus, tk_root=self.root)
        self._hub_store_adapter = ProjectionHubStoreAdapter(self.hub, self.store)
        self._hub_store_adapter.start()
        self.store.set_ui_mode("advanced" if self.state.settings.advanced_mode else "simple")

        # Theme manager for CTK themes
        from .theme.theme_manager import get_theme_manager
        self._tm = get_theme_manager()

        self._toast = ToastManager(self.root)
        self._last_scan_toast_id: str | None = None
        self._scan_controller = ScanController(self.coordinator, self.store)

        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self._pages: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._active_page: str = "Welcome"
        self._content_host: ctk.CTkFrame | None = None
        self._default_keep_policy: KeepPolicy = "newest"
        self._post_scan_route: PostScanRoute = "review"
        self._last_scan_mode: ScanMode = "files"
        self._active_scan_id: str = ""
        self._review_controller: ReviewController | None = None

        self._build_nav()
        self._build_content()
        self._wire_pages()
        self._show_page("Welcome")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _toast_notify(self, msg: str, ms: int = 3200) -> None:
        self._toast.show(msg, ms=ms, reduced_motion=bool(self.state.settings.reduced_motion))

    def _wire_pages(self) -> None:
        scan = self._pages.get("Scan")
        if isinstance(scan, ScanPageCTK):
            scan.attach_store(self.store)
        mission = self._pages.get("Mission")
        if isinstance(mission, MissionPageCTK):
            mission.attach_store(self.store)
        diag = self._pages.get("Diagnostics")
        if isinstance(diag, DiagnosticsPageCTK):
            diag.attach_store(self.store)

        review = self._pages.get("Review")
        if isinstance(review, ReviewPageCTK):
            self._review_controller = ReviewController(
                self.coordinator,
                self.store,
                callbacks=review,
                toast_notify=lambda m, ms: self._toast_notify(m, ms),
            )
            review.set_review_controller(self._review_controller)

    def _push_mission_store(self) -> None:
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
        recent_sessions: list = []
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

    def _push_history_store(self) -> None:
        try:
            proj = build_history_from_coordinator(self.coordinator)
            self.store.set_history(proj)
        except Exception:
            pass

    def _build_nav(self) -> None:
        nav = ctk.CTkFrame(self.root, corner_radius=0, width=220)
        nav.grid(row=0, column=0, sticky="nsew")
        nav.grid_rowconfigure(99, weight=1)
        nav.grid_propagate(False)

        ctk.CTkLabel(nav, text="CEREBRO", font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20, 8), sticky="w"
        )
        ctk.CTkLabel(nav, text="CustomTkinter · hub + store", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, padx=20, pady=(0, 16), sticky="w"
        )

        for i, title in enumerate(
            ["Welcome", "Mission", "Scan", "Review", "History", "Diagnostics", "Themes", "Settings"], start=2
        ):
            btn = ctk.CTkButton(nav, text=title, anchor="w", command=lambda t=title: self._show_page(t))
            btn.grid(row=i, column=0, padx=14, pady=6, sticky="ew")
            self._nav_buttons[title] = btn

    def _build_content(self) -> None:
        content = ctk.CTkFrame(self.root, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(3, weight=1)

        self._title_var = ctk.StringVar(value="Welcome")
        ctk.CTkLabel(content, textvariable=self._title_var, font=ctk.CTkFont(size=28, weight="bold")).grid(
            row=0, column=0, padx=24, pady=(24, 8), sticky="w"
        )
        ctk.CTkLabel(
            content,
            text="Live scan state: ProjectionHub → UIStateStore (same pipeline as the ttk shell).",
            justify="left",
            text_color=("gray35", "gray65"),
        ).grid(row=1, column=0, padx=24, pady=(0, 16), sticky="w")

        self._content_host = ctk.CTkFrame(content, fg_color="transparent")
        self._content_host.grid(row=3, column=0, padx=0, pady=(0, 0), sticky="nsew")
        self._content_host.grid_columnconfigure(0, weight=1)
        self._content_host.grid_rowconfigure(0, weight=1)

        self._pages["Welcome"] = WelcomePageCTK(
            self._content_host,
            on_scan_photos=lambda: self._start_scan_mode("photos"),
            on_scan_videos=lambda: self._start_scan_mode("videos"),
            on_scan_files=lambda: self._start_scan_mode("files"),
            on_resume_scan=self._resume_scan_latest,
            on_open_last_review=self._open_last_review,
        )
        self._pages["Mission"] = MissionPageCTK(
            self._content_host,
            on_start_scan=lambda: self._start_scan_mode("files"),
            on_resume_scan=self._resume_scan_latest,
            on_open_last_review=self._open_last_review,
            on_quick_scan=self._handle_mission_quick_scan,
        )
        self._pages["Scan"] = ScanPageCTK(
            self._content_host,
            on_start=self._handle_start_scan_payload,
            on_resume=self._resume_scan_latest,
            on_cancel=self._on_scan_cancel,
        )
        self._pages["Review"] = ReviewPageCTK(self._content_host, store=self.store)
        self._pages["Review"].set_refresh_callback(self._coordinator.get_last_result)  # type: ignore[attr-defined]
        self._pages["History"] = HistoryPageCTK(
            self._content_host,
            get_history=lambda: self._coordinator.get_history(30),
            on_load_scan=self._open_history_scan_in_review,
        )
        self._pages["Diagnostics"] = DiagnosticsPageCTK(self._content_host, coordinator=self._coordinator)
        self._pages["Themes"] = ThemesPageCTK(
            self._content_host,
            on_theme_change=self._on_theme_change,
            on_preference_changed=self._on_theme_preference_changed,
            on_toast=self._toast_notify,
        )
        self._pages["Settings"] = SettingsPageCTK(
            self._content_host,
            state=self.state,
            database_path=str(self._coordinator.persistence.db_path),
            on_open_themes=lambda: self._show_page("Themes"),
            on_open_diagnostics=lambda: self._show_page("Diagnostics"),
            on_settings_changed=self._on_settings_changed,
            on_toast=self._toast_notify,
        )

    def _show_page(self, title: str) -> None:
        if self._content_host is None or title not in self._pages:
            return
        for name, page in self._pages.items():
            if name == title:
                page.grid(row=0, column=0, sticky="nsew")
            else:
                page.grid_forget()
        self._active_page = title
        self._title_var.set(title)
        for name, btn in self._nav_buttons.items():
            btn.configure(fg_color=("gray75", "gray25") if name == title else ("#3a7ebf", "#1f538d"))
        if title == "Mission":
            self._push_mission_store()
        elif title == "History":
            self._push_history_store()
            hist = self._pages.get("History")
            if isinstance(hist, HistoryPageCTK):
                hist.reload()
        elif title == "Settings":
            st = self._pages.get("Settings")
            if isinstance(st, SettingsPageCTK):
                st.set_database_path(str(self._coordinator.persistence.db_path))
                st.on_show()
        elif title == "Themes":
            th = self._pages.get("Themes")
            if isinstance(th, ThemesPageCTK):
                th.on_show()
        elif title == "Diagnostics":
            diag = self._pages.get("Diagnostics")
            if isinstance(diag, DiagnosticsPageCTK):
                diag.reload()

    def _start_scan_mode(self, mode: str) -> None:
        self._last_scan_mode = mode if mode in ("photos", "videos", "files") else "files"
        self._show_page("Scan")
        page = self._pages.get("Scan")
        if isinstance(page, ScanPageCTK):
            page.set_mode(mode)
            page.apply_decision_defaults(self._default_keep_policy, self._post_scan_route)
            self._title_var.set(
                f"Scan ({self._last_scan_mode.title()}) · Keep:{self._default_keep_policy} · After:{self._post_scan_route}"
            )

    def _handle_mission_quick_scan(self, payload: ScanStartPayload) -> None:
        merged: ScanStartPayload = {
            "mode": payload["mode"],
            "path": payload["path"],
            "options": payload["options"],
            "keep_policy": self._default_keep_policy,
            "post_scan_route": self._post_scan_route,
        }
        self._handle_start_scan_payload(merged)

    def _noop_progress(self, _progress) -> None:
        """Progress UI is driven by ProjectionHub → store → ScanPageCTK.attach_store."""

    def _handle_start_scan_payload(self, payload: ScanStartPayload) -> None:
        mode = payload.get("mode", "files")
        path = payload.get("path", "")
        keep_policy = payload.get("keep_policy", "newest")
        post_scan_route = payload.get("post_scan_route", "review")
        self._last_scan_mode = mode
        self._default_keep_policy = keep_policy
        self._post_scan_route = post_scan_route
        self._show_page("Scan")
        page = self._pages.get("Scan")
        if not isinstance(page, ScanPageCTK):
            return
        page.set_mode(mode)
        if path:
            page.set_target_path(path)
        page.apply_decision_defaults(keep_policy, post_scan_route)
        self._title_var.set(f"Scan ({mode.title()}) · Keep:{self._default_keep_policy} · After:{self._post_scan_route}")
        if not path:
            page.set_status("Idle (no folder selected)")
            return
        page.set_status("Starting scan...")
        try:
            self._active_scan_id = self._scan_controller.handle_start_scan(
                Path(path),
                payload.get("options") or {},
                on_progress=self._noop_progress,
                on_complete=self._on_scan_complete,
                on_error=self._on_scan_error,
                on_cancel=self._on_scan_cancelled_worker,
            )
            page.set_status(f"Running (scan_id: {self._active_scan_id[:8]}...)")
            page.set_session(session_id=self._active_scan_id[:8] + "...", phase="starting")
            page.set_scan_busy(True)
        except Exception as ex:
            page.set_status(f"Error starting scan: {ex}")

    def _resume_scan_latest(self) -> None:
        self._show_page("Scan")
        self._title_var.set("Scan (Resume)")
        ids = self._coordinator.get_resumable_scan_ids() or []
        page = self._pages.get("Scan")
        if not isinstance(page, ScanPageCTK):
            return
        if not ids:
            page.set_status("No resumable scans found")
            return
        try:
            self._active_scan_id = self._scan_controller.handle_start_resume(
                ids[0],
                on_progress=self._noop_progress,
                on_complete=self._on_scan_complete,
                on_error=self._on_scan_error,
                on_cancel=self._on_scan_cancelled_worker,
            )
            page.set_status(f"Running (resumed: {self._active_scan_id[:8]}...)")
            page.set_session(session_id=self._active_scan_id[:8] + "...", phase="resuming")
            page.set_scan_busy(True)
        except Exception as ex:
            page.set_status(f"Resume failed: {ex}")

    def _on_scan_cancel(self) -> None:
        page = self._pages.get("Scan")
        if self._coordinator.is_scanning:
            self._scan_controller.handle_cancel()
            self._active_scan_id = ""
            if isinstance(page, ScanPageCTK):
                page.set_status("Cancelled")
                page.set_session(session_id="—", phase="cancelled")
            return
        self._show_page("Mission")

    def _open_last_review(self) -> None:
        review = self._pages.get("Review")
        if isinstance(review, ReviewPageCTK):
            review.load_result(self._coordinator.get_last_result())
            review.apply_default_policy(self._default_keep_policy)
        self._show_page("Review")

    def _open_history_scan_in_review(self, scan_id: str) -> None:
        result = self._coordinator.load_scan(scan_id)
        if result is None:
            sid = (scan_id[:18] + "…") if len(scan_id) > 18 else scan_id
            messagebox.showwarning(
                "Could not open scan",
                "Saved scan data could not be loaded. It may have been removed or is from an incompatible store.\n\n"
                f"Scan id: {sid}",
                parent=self.root,
            )
            return
        review = self._pages.get("Review")
        if isinstance(review, ReviewPageCTK):
            review.load_result(result)
            review.apply_default_policy(self._default_keep_policy)
        self._show_page("Review")

    def _on_scan_cancelled_worker(self) -> None:
        self.root.after(0, self._apply_scan_cancelled_ui)

    def _apply_scan_cancelled_ui(self) -> None:
        page = self._pages.get("Scan")
        if isinstance(page, ScanPageCTK):
            page.set_scan_busy(False)

    def _on_scan_complete(self, result: ScanResult) -> None:
        self.root.after(0, lambda r=result: self._apply_scan_complete(r))

    def _apply_scan_complete(self, result: ScanResult) -> None:
        self._active_scan_id = ""
        page = self._pages.get("Scan")
        if isinstance(page, ScanPageCTK):
            page.set_scan_busy(False)
            page.set_status(f"Completed: {len(result.duplicate_groups)} groups")
            page.set_session(session_id=result.scan_id[:8] + "...", phase="complete")
            route = (self._post_scan_route or "review").lower()
            route_label = {
                "mission": "Go to Mission",
                "scan": "Stay on Scan",
                "review": "Open Review",
            }.get(route, "Open Review")
            page.set_review_readiness(
                groups_found=len(result.duplicate_groups),
                reclaim_text=fmt_bytes(getattr(result, "total_reclaimable_bytes", 0) or 0),
                route_label=route_label,
                on_route=self._route_after_scan,
            )
        self._push_mission_store()
        if result.scan_id != self._last_scan_toast_id:
            self._last_scan_toast_id = result.scan_id
            try:
                self._toast_notify(
                    f"Scan complete — {len(result.duplicate_groups):,} duplicate group(s).",
                    ms=4500,
                )
            except Exception:
                pass
        self._route_after_scan()

    def _on_scan_error(self, error: str) -> None:
        self.root.after(0, lambda e=error: self._apply_scan_error(e))

    def _apply_scan_error(self, error: str) -> None:
        self._active_scan_id = ""
        page = self._pages.get("Scan")
        if isinstance(page, ScanPageCTK):
            page.set_scan_busy(False)
            page.set_status(f"Error: {error[:120]}")
            page.set_session(session_id="—", phase="error")

    def _route_after_scan(self) -> None:
        route = (self._post_scan_route or "review").lower()
        if route == "mission":
            self._show_page("Mission")
            return
        if route == "scan":
            self._show_page("Scan")
            return
        review = self._pages.get("Review")
        if isinstance(review, ReviewPageCTK):
            review.load_result(self._coordinator.get_last_result())
            review.apply_default_policy(self._default_keep_policy)
        self._show_page("Review")

    def _on_theme_change(self, key: str) -> None:
        """Handle theme selection change - persist theme_key to settings."""
        self.state.settings.theme_key = key
        self.state.save()
        self._toast_notify(f"Theme: {key}")

    def _on_theme_preference_changed(self) -> None:
        """Handle theme preference changes from Themes page - persist custom gradients."""
        # Save custom gradient stops to settings if they exist
        custom_stops = self._tm.get_custom_gradient_stops()
        if custom_stops:
            self.state.settings.custom_gradient_stops = [[float(pos), str(col)] for pos, col in custom_stops]
        else:
            self.state.settings.custom_gradient_stops = None
        self.state.save()

    def _on_settings_changed(self) -> None:
        """Handle settings changes from Settings page."""
        # Settings are already saved; refresh any UI that depends on them
        self.store.set_ui_mode("advanced" if self.state.settings.advanced_mode else "simple")

    def _on_close(self) -> None:
        if self._coordinator.is_scanning:
            if not messagebox.askyesno("Scan in progress", "A scan is active. Cancel and exit?", parent=self.root):
                return
            self._coordinator.cancel_scan()
        try:
            self.hub.shutdown()
        except Exception:
            pass
        try:
            self._hub_store_adapter.stop()
        except Exception:
            pass
        try:
            st = str(self.root.state() or "")
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
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
