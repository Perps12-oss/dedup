"""
CustomTkinter application shell — same orchestration contracts as CerebroApp (ttk).

ProjectionHub → UIStateStore, ScanController, ReviewController, and ToastManager are shared
with the classic UI; only widgets differ.
"""

from __future__ import annotations

import logging
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from .. import __version__
from ..application.runtime import ApplicationRuntime
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
from .state.store import LastScanSummaryState, MissionState, UiDegradedFlags, UIStateStore
from .utils.formatting import fmt_bytes
from .utils.ui_state import UIState
from .ctk_shortcuts import CTKShortcutRegistry
from .theme.theme_manager import parse_gradient_stops_from_raw
from .theme.gradients import GradientBar, cinematic_chrome_color, paint_cinematic_backdrop


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
        
        # Accessibility improvements
        self.root.option_add('*tearOff', False)  # Disable tear-off menus
        self.root.focus_set()  # Set initial focus

        self.state = UIState()
        self._coordinator = ScanCoordinator()
        self._runtime = ApplicationRuntime(self._coordinator)
        self.store = UIStateStore(tk_root=self.root)
        self.hub = ProjectionHub(event_bus=self._coordinator.event_bus, tk_root=self.root)
        self._hub_store_adapter = ProjectionHubStoreAdapter(self.hub, self.store)
        self._hub_store_adapter.start()
        self.store.set_ui_mode("advanced" if self.state.settings.advanced_mode else "simple")

        # Theme manager for CTK themes
        from .theme.theme_manager import get_theme_manager
        self._tm = get_theme_manager()
        self._tm.subscribe(self._on_theme_tokens)

        self._toast = ToastManager(self.root)
        self._last_scan_toast_id: str | None = None
        self._scan_controller = ScanController(self._runtime.scan, self.store)

        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self._pages: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._active_page: str = "Welcome"
        self._content_host: ctk.CTkFrame | None = None
        self._nav: ctk.CTkFrame | None = None
        self._content: ctk.CTkFrame | None = None
        self._main_stack: tk.Frame | None = None
        self._cinematic_canvas: tk.Canvas | None = None
        self._default_keep_policy: KeepPolicy = "newest"
        self._post_scan_route: PostScanRoute = "review"
        self._last_scan_mode: ScanMode = "files"
        self._active_scan_id: str = ""
        self._review_controller: ReviewController | None = None

        # Apply persisted theme early so CTk's internal Tk widgets (Canvas in scrollables)
        # inherit correct defaults and don't "flash white" on repaint.
        self._apply_theme_from_settings()

        self._build_nav()
        self._build_content()
        self._wire_pages()
        self._bind_global_shortcuts()
        self._show_page("Welcome")
        try:
            self.root.after(80, self._paint_cinematic_backdrop)
            self.root.after(300, self._paint_cinematic_backdrop)
        except (tk.TclError, RuntimeError) as e:
            _log.warning("Could not schedule cinematic backdrop paint: %s", e)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_theme_from_settings(self) -> None:
        from .theme.theme_registry import DEFAULT_THEME

        key = (self.state.settings.theme_key or "").strip() or DEFAULT_THEME
        stops = parse_gradient_stops_from_raw(self.state.settings.custom_gradient_stops)
        try:
            # This applies tk defaults via option_add (Canvas/Listbox/etc) which CTk relies on internally.
            self._tm.apply(key, self.root, gradient_stops=stops, sun_valley=False)
            self.store.clear_theme_degraded()
        except Exception as e:
            _log.warning("Theme apply failed (degraded styling): %s", e)
            self.store.set_ui_degraded(UiDegradedFlags(theme_apply_failed=True, theme_last_error=str(e)[:400]))

    def _main_chrome_color(self, tokens: dict) -> str:
        """Solid fill for the main column (must match gradient tokens — CTk cannot show Canvas through)."""
        return cinematic_chrome_color(
            tokens,
            reduced=bool(getattr(self.state.settings, "reduced_gradients", False)),
        )

    def _on_theme_tokens(self, tokens: dict) -> None:
        """Apply token changes to CTK surfaces (nav/content)."""
        try:
            bg = str(tokens.get("bg_base", "#0f131c"))
            sidebar = str(tokens.get("bg_sidebar", "#141924"))
            acc = str(tokens.get("accent_primary", "#3B8ED0"))
            chrome = self._main_chrome_color(tokens)
            if hasattr(self, "_top_gradient") and self._top_gradient is not None:
                try:
                    self._top_gradient.configure(bg=bg)
                    # Multi-stop aware (uses tokens["_multi_gradient_stops"] when present)
                    self._top_gradient.update_from_tokens(tokens)
                except Exception as e:
                    _log.warning("Top gradient update failed: %s", e)
            # Root background (CTk + underlying Tk)
            try:
                self.root.configure(fg_color=bg)
            except Exception as e:
                _log.debug("Root fg_color configure: %s", e)
            try:
                self.root.configure(background=bg)
            except Exception as e:
                _log.debug("Root background configure: %s", e)
            if self._nav is not None:
                self._nav.configure(fg_color=sidebar)
            if self._main_stack is not None:
                try:
                    self._main_stack.configure(bg=bg)
                except Exception as e:
                    _log.warning("Main stack bg update failed: %s", e)
            self._paint_cinematic_backdrop()
            # Inset CTk column: solid chrome on top of cinematic margin (not full-bleed CTk over canvas).
            if self._content is not None:
                self._content.configure(fg_color=chrome)
            if self._content_host is not None:
                self._content_host.configure(fg_color="transparent")
            for page in self._pages.values():
                if hasattr(page, "apply_theme_tokens"):
                    try:
                        page.apply_theme_tokens(tokens)
                    except Exception as e:
                        _log.warning("Page apply_theme_tokens failed: %s", e)
            # Nav buttons: keep selection logic but use accent as base.
            for name, btn in self._nav_buttons.items():
                if name == self._active_page:
                    btn.configure(fg_color=("#2B6CB0", acc))
                else:
                    btn.configure(fg_color=("#234E70", "#1f538d"))
        except Exception as e:
            _log.warning("Full theme token pass failed: %s", e)

    def _paint_cinematic_backdrop(self, _event: object = None) -> None:
        """Spine 2: full-area Tk Canvas behind an inset CTk shell (multi-stop wash)."""
        c = self._cinematic_canvas
        if c is None:
            return
        try:
            w = max(2, int(c.winfo_width() or 0))
            h = max(2, int(c.winfo_height() or 0))
            if w < 8 or h < 8:
                return
            paint_cinematic_backdrop(
                c,
                w,
                h,
                self._tm.tokens,
                reduced=bool(getattr(self.state.settings, "reduced_gradients", False)),
            )
        except Exception as e:
            _log.warning("Cinematic backdrop paint failed: %s", e)

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
                self._runtime.review,
                self.store,
                callbacks=review,
                toast_notify=lambda m, ms: self._toast_notify(m, ms),
            )
            review.set_review_controller(self._review_controller)

    def _push_mission_store(self) -> None:
        try:
            raw = self._runtime.history.get_history(limit=8) or []
        except Exception as e:
            _log.warning("Mission history slice failed: %s", e)
            raw = []
        try:
            resumable_ids = tuple(self._runtime.scan.get_resumable_scan_ids() or [])
        except Exception as e:
            _log.warning("Mission resumable IDs failed: %s", e)
            resumable_ids = ()
        try:
            recent_folders = tuple(self._runtime.history.get_recent_folders() or [])[:10]
        except Exception as e:
            _log.warning("Mission recent folders failed: %s", e)
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
            proj = build_history_from_coordinator(self._coordinator)
            self.store.set_history(proj)
        except Exception as e:
            _log.warning("History projection push failed: %s", e)

    def _build_nav(self) -> None:
        # Give nav a real background so child widgets never "flash" white.
        t = self._tm.tokens
        sidebar = str(t.get("bg_sidebar", "#141924"))
        nav = ctk.CTkFrame(self.root, corner_radius=0, width=220, fg_color=sidebar)
        nav.grid(row=0, column=0, sticky="nsew")
        nav.grid_rowconfigure(99, weight=1)
        nav.grid_propagate(False)
        self._nav = nav

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
            # Store shortcuts separately for help display
            shortcuts = {
                "Welcome": None,
                "Mission": "Ctrl+1",
                "Scan": "Ctrl+2", 
                "Review": "Ctrl+3",
                "History": "Ctrl+4",
                "Diagnostics": "Ctrl+5",
                "Themes": "Ctrl+7",
                "Settings": "Ctrl+,"
            }
            # Store shortcut for this button (used in help)
            if shortcuts.get(title):
                btn.shortcut_hint = shortcuts[title]
            self._nav_buttons[title] = btn

    def _build_content(self) -> None:
        t = self._tm.tokens
        bg = str(t.get("bg_base", "#0f131c"))
        chrome = self._main_chrome_color(t)
        # Spine 2: tk.Canvas cinematic fill; CTk sits inset so the gradient shows as a real border.
        rel_inset = 0.058
        main_stack = tk.Frame(self.root, bg=bg, highlightthickness=0, bd=0)
        main_stack.grid(row=0, column=1, sticky="nsew")
        self._main_stack = main_stack

        cnv = tk.Canvas(main_stack, highlightthickness=0, borderwidth=0, bd=0, background=bg)
        cnv.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        cnv.bind("<Configure>", self._paint_cinematic_backdrop)
        self._cinematic_canvas = cnv

        content = ctk.CTkFrame(main_stack, corner_radius=0, fg_color=chrome)
        content.place(relx=rel_inset, rely=rel_inset, relwidth=1.0 - 2 * rel_inset, relheight=1.0 - 2 * rel_inset)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(4, weight=1)
        self._content = content

        # Premium gradient strip (multi-stop) — updates live from theme tokens.
        self._top_gradient = GradientBar(
            content,
            height=6,
            color_start=str(t.get("gradient_start", "#1f6feb")),
            color_end=str(t.get("gradient_end", "#58a6ff")),
            bg=bg,
        )
        self._top_gradient.grid(row=0, column=0, sticky="ew")
        try:
            self._top_gradient.update_from_tokens(self._tm.tokens)
        except Exception as e:
            _log.warning("Initial gradient bar token sync failed: %s", e)

        self._title_var = ctk.StringVar(value="Welcome")
        ctk.CTkLabel(content, textvariable=self._title_var, font=ctk.CTkFont(size=28, weight="bold")).grid(
            row=1, column=0, padx=24, pady=(18, 8), sticky="w"
        )
        ctk.CTkLabel(
            content,
            text="Live scan state: ProjectionHub → UIStateStore (same pipeline as the ttk shell).",
            justify="left",
            text_color=("gray35", "gray65"),
        ).grid(row=2, column=0, padx=24, pady=(0, 16), sticky="w")

        self._content_host = ctk.CTkFrame(content, fg_color="transparent")
        self._content_host.grid(row=4, column=0, padx=0, pady=(0, 0), sticky="nsew")
        self._content_host.grid_columnconfigure(0, weight=1)
        self._content_host.grid_rowconfigure(0, weight=1)

        try:
            self._top_gradient.tkraise()
        except Exception as e:
            _log.debug("Top gradient tkraise: %s", e)

        # Page roots: transparent → inherit main column chrome (see cinematic_chrome_color).
        _tp = {"fg_color": "transparent"}
        self._pages["Welcome"] = WelcomePageCTK(
            self._content_host,
            on_scan_photos=lambda: self._start_scan_mode("photos"),
            on_scan_videos=lambda: self._start_scan_mode("videos"),
            on_scan_files=lambda: self._start_scan_mode("files"),
            on_resume_scan=self._resume_scan_latest,
            on_open_last_review=self._open_last_review,
            **_tp,
        )
        self._pages["Mission"] = MissionPageCTK(
            self._content_host,
            on_start_scan=lambda: self._start_scan_mode("files"),
            on_resume_scan=self._resume_scan_latest,
            on_open_last_review=self._open_last_review,
            on_quick_scan=self._handle_mission_quick_scan,
            **_tp,
        )
        self._pages["Scan"] = ScanPageCTK(
            self._content_host,
            on_start=self._handle_start_scan_payload,
            on_resume=self._resume_scan_latest,
            on_cancel=self._on_scan_cancel,
            **_tp,
        )
        self._pages["Review"] = ReviewPageCTK(self._content_host, store=self.store, **_tp)
        self._pages["Review"].set_refresh_callback(self._runtime.review.get_last_result)  # type: ignore[attr-defined]
        self._pages["History"] = HistoryPageCTK(
            self._content_host,
            get_history=lambda: self._runtime.history.get_history(30),
            on_load_scan=self._open_history_scan_in_review,
            on_resume_scan=self._resume_scan_latest,
            **_tp,
        )
        self._pages["Diagnostics"] = DiagnosticsPageCTK(self._content_host, runtime=self._runtime, **_tp)
        self._pages["Themes"] = ThemesPageCTK(
            self._content_host,
            on_theme_change=self._on_theme_change,
            on_preference_changed=self._on_theme_preference_changed,
            on_toast=self._toast_notify,
            **_tp,
        )
        self._pages["Settings"] = SettingsPageCTK(
            self._content_host,
            state=self.state,
            database_path=str(self._coordinator.persistence.db_path),
            on_open_themes=lambda: self._show_page("Themes"),
            on_open_diagnostics=lambda: self._show_page("Diagnostics"),
            on_settings_changed=self._on_settings_changed,
            on_toast=self._toast_notify,
            **_tp,
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
        # Re-apply token-derived colors after selection changes.
        self._on_theme_tokens(self._tm.tokens)
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
        ids = self._runtime.scan.get_resumable_scan_ids() or []
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
        if self._runtime.scan.is_scanning:
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
            review.load_result(self._runtime.review.get_last_result())
            review.apply_default_policy(self._default_keep_policy)
        self._show_page("Review")

    def _open_history_scan_in_review(self, scan_id: str) -> None:
        result = self._runtime.history.load_scan(scan_id)
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
            except Exception as e:
                _log.warning("Scan complete toast failed: %s", e)
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
            review.load_result(self._runtime.review.get_last_result())
            review.apply_default_policy(self._default_keep_policy)
        self._show_page("Review")

    def _on_theme_change(self, key: str) -> None:
        """Handle theme selection change - persist theme_key to settings."""
        self.state.settings.theme_key = key
        self.state.save()
        # Apply to running CTK app: tk defaults + observers.
        self._apply_theme_from_settings()
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
        try:
            self._on_theme_tokens(self._tm.tokens)
        except Exception as e:
            _log.warning("Settings-changed theme refresh failed: %s", e)

    def _on_close(self) -> None:
        if self._runtime.scan.is_scanning:
            if not messagebox.askyesno("Scan in progress", "A scan is active. Cancel and exit?", parent=self.root):
                return
            self._runtime.scan.cancel_scan()
        try:
            self.hub.shutdown()
        except Exception as e:
            _log.warning("Hub shutdown failed: %s", e)
        try:
            self._hub_store_adapter.stop()
        except Exception as e:
            _log.warning("Hub store adapter stop failed: %s", e)
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
        except Exception as e:
            _log.warning("Persist window geometry on exit failed: %s", e)
        self.root.destroy()

    def _bind_global_shortcuts(self) -> None:
        """Global keyboard shortcuts for navigation and common actions."""
        reg = CTKShortcutRegistry(self.root)
        
        # Navigation shortcuts
        reg.register("<Control-Key-1>", "Mission Control", lambda e: self._show_page("Mission"))
        reg.register("<Control-Key-2>", "Live Scan Studio", lambda e: self._show_page("Scan"))
        reg.register("<Control-Key-3>", "Decision Studio", lambda e: self._show_page("Review"))
        reg.register("<Control-Key-4>", "History", lambda e: self._show_page("History"))
        reg.register("<Control-Key-5>", "Diagnostics", lambda e: self._show_page("Diagnostics"))
        reg.register("<Control-Key-7>", "Themes", lambda e: self._show_page("Themes"))
        reg.register("<Control-comma>", "Settings", lambda e: self._show_page("Settings"))
        
        # Action shortcuts
        reg.register("<Control-Key-o>", "Open last review", lambda e: self._open_last_review())
        reg.register("<Control-Key-r>", "Resume last scan", lambda e: self._resume_scan_latest())
        reg.register("<Control-n>", "New scan", lambda e: self._show_page("Scan"))
        reg.register("<F5>", "Refresh current page", lambda e: self._refresh_current_page())
        
        # Help shortcut
        reg.register("?", "Shortcut help", lambda e: self._show_shortcuts_help())
        
        self._shortcut_registry = reg

    def _refresh_current_page(self) -> None:
        """Refresh the current page if it supports reloading."""
        if hasattr(self, '_active_page'):
            page = self._pages.get(self._active_page)
            if hasattr(page, 'reload'):
                page.reload()

    def _show_shortcuts_help(self) -> None:
        """Show keyboard shortcuts help dialog."""
        from tkinter import messagebox
        
        shortcuts = [
            "Keyboard Shortcuts:",
            "",
            "Navigation:",
        ] + self._shortcut_registry.describe_lines() + [
            "",
            "Page-specific shortcuts:",
            "  Ctrl+O                Open last review (from any page)",
            "  Ctrl+R                Resume last scan (from any page)",
            "  Ctrl+N                Start new scan (from any page)",
            "  F5                   Refresh current page",
            "",
            "Review page:",
            "  Space                 Keep selected file",
            "  Delete               Delete selected file",
            "  Ctrl+A               Select all files",
            "  Ctrl+D               Deselect all files",
            "",
            "Scan page:",
            "  Ctrl+Enter           Start scan",
            "  Escape               Cancel scan",
        ]
        
        messagebox.showinfo(
            "Keyboard Shortcuts",
            "\n".join(shortcuts),
            parent=self.root
        )

    def run(self) -> None:
        self.root.mainloop()
