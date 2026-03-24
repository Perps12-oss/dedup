"""
Experimental CustomTkinter application shell.

This intentionally starts as a thin scaffold so we can migrate pages one-by-one
without breaking the existing ttk/ttkbootstrap shell.
"""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from ..orchestration.coordinator import ScanCoordinator
from .ctk_action_contracts import KeepPolicy, PostScanRoute, ScanMode, ScanStartPayload
from .ctk_pages.diagnostics_page import DiagnosticsPageCTK
from .ctk_pages.history_page import HistoryPageCTK
from .ctk_pages.mission_page import MissionPageCTK
from .ctk_pages.review_page import ReviewPageCTK
from .ctk_pages.scan_page import ScanPageCTK
from .ctk_pages.settings_page import SettingsPageCTK
from .ctk_pages.themes_page import ThemesPageCTK
from .ctk_pages.welcome_page import WelcomePageCTK
from .utils.formatting import fmt_bytes, fmt_int


class CerebroCTKApp:
    """Minimal CTK shell used as the migration landing zone."""

    APP_NAME = "CEREBRO"
    APP_VERSION = "2.1.0-ctk-exp"

    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title(f"{self.APP_NAME} Dedup Engine v{self.APP_VERSION}")
        self.root.geometry("1180x760")
        self.root.minsize(760, 480)

        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self._coordinator = ScanCoordinator()

        self._pages: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._active_page: str = "Welcome"
        self._content_host: ctk.CTkFrame | None = None
        self._default_keep_policy: KeepPolicy = "newest"
        self._post_scan_route: PostScanRoute = "review"
        self._last_scan_mode: ScanMode = "files"
        self._active_scan_id: str = ""
        self._build_nav()
        self._build_content()
        self._show_page("Welcome")
        self._schedule_scan_status_poll()

    def _build_nav(self) -> None:
        """Left sidebar placeholder for future CTK nav rail."""
        nav = ctk.CTkFrame(self.root, corner_radius=0, width=220)
        nav.grid(row=0, column=0, sticky="nsew")
        nav.grid_rowconfigure(99, weight=1)
        nav.grid_propagate(False)

        ctk.CTkLabel(nav, text="CEREBRO", font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20, 8), sticky="w"
        )
        ctk.CTkLabel(nav, text="CustomTkinter Experimental Shell").grid(
            row=1, column=0, padx=20, pady=(0, 16), sticky="w"
        )

        for i, title in enumerate(
            ["Welcome", "Mission", "Scan", "Review", "History", "Diagnostics", "Themes", "Settings"], start=2
        ):
            btn = ctk.CTkButton(nav, text=title, anchor="w", command=lambda t=title: self._show_page(t))
            btn.grid(row=i, column=0, padx=14, pady=6, sticky="ew")
            self._nav_buttons[title] = btn

    def _build_content(self) -> None:
        """Main CTK content host; page container swaps child frames."""
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
            text=(
                "CTK migration scaffold is active.\n"
                "Next steps: migrate page shells one by one while preserving store/controller contracts."
            ),
            justify="left",
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
        )
        self._pages["Scan"] = ScanPageCTK(
            self._content_host,
            on_start=self._handle_start_scan_payload,
            on_resume=self._resume_scan_latest,
            on_cancel=lambda: self._show_page("Mission"),
        )
        self._pages["Review"] = ReviewPageCTK(self._content_host, on_execute=self._execute_review_lite_deletion)
        self._pages["Review"].set_refresh_callback(self._coordinator.get_last_result)  # type: ignore[attr-defined]
        self._pages["History"] = HistoryPageCTK(
            self._content_host,
            get_history=lambda: self._coordinator.get_history(30),
            on_load_scan=self._open_history_scan_in_review,
        )
        self._pages["Diagnostics"] = self._placeholder_page("Diagnostics CTK page pending migration.")
        self._pages["Themes"] = ThemesPageCTK(self._content_host)
        self._pages["Settings"] = SettingsPageCTK(
            self._content_host,
            database_path=str(self._coordinator.persistence.db_path),
            on_open_themes=lambda: self._show_page("Themes"),
            on_open_diagnostics=lambda: self._show_page("Diagnostics"),
        )

    def _show_page(self, title: str) -> None:
        """Switch visible page frame and sync nav state."""
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
            self._refresh_mission_page()
        elif title == "History":
            hist = self._pages.get("History")
            if isinstance(hist, HistoryPageCTK):
                hist.reload()
        elif title == "Settings":
            st = self._pages.get("Settings")
            if isinstance(st, SettingsPageCTK):
                st.set_database_path(str(self._coordinator.persistence.db_path))
        elif title == "Diagnostics":
            diag = self._pages.get("Diagnostics")
            if isinstance(diag, DiagnosticsPageCTK):
                diag.reload()

    def _start_scan_mode(self, mode: str) -> None:
        """Task-first entry point from Welcome; forwards mode into Scan page."""
        self._show_page("Scan")
        page = self._pages.get("Scan")
        if isinstance(page, ScanPageCTK):
            page.set_mode(mode)

    def _handle_start_scan_payload(self, payload: ScanStartPayload) -> None:
        """Shared start-scan contract for Welcome/Mission/Scan CTK pages."""
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
        # Surface payload in title/state while backend callbacks are wired in future steps.
        self._title_var.set(f"Scan ({mode.title()}) · Keep:{self._default_keep_policy} · After:{self._post_scan_route}")
        if not path:
            page.set_status("Idle (no folder selected)")
            return
        roots = [Path(path)]
        page.set_status("Starting scan...")
        try:
            self._active_scan_id = self._coordinator.start_scan(
                roots=roots,
                on_progress=self._on_scan_progress,
                on_complete=self._on_scan_complete,
                on_error=self._on_scan_error,
                **(payload.get("options") or {}),
            )
            page.set_status(f"Running (scan_id: {self._active_scan_id[:8]}...)")
            page.set_session(session_id=self._active_scan_id[:8] + "...", phase="starting")
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
            self._active_scan_id = self._coordinator.start_scan(
                roots=[],
                resume_scan_id=ids[0],
                on_progress=self._on_scan_progress,
                on_complete=self._on_scan_complete,
                on_error=self._on_scan_error,
            )
            page.set_status(f"Running (resumed: {self._active_scan_id[:8]}...)")
            page.set_session(session_id=self._active_scan_id[:8] + "...", phase="resuming")
        except Exception as ex:
            page.set_status(f"Resume failed: {ex}")

    def _open_last_review(self) -> None:
        review = self._pages.get("Review")
        if isinstance(review, ReviewPageCTK):
            review.load_result(self._coordinator.get_last_result())
            review.apply_default_policy(self._default_keep_policy)
        self._show_page("Review")

    def _open_history_scan_in_review(self, scan_id: str) -> None:
        result = self._coordinator.load_scan(scan_id)
        if result is None:
            return
        review = self._pages.get("Review")
        if isinstance(review, ReviewPageCTK):
            review.load_result(result)
            review.apply_default_policy(self._default_keep_policy)
        self._show_page("Review")

    def _refresh_mission_page(self) -> None:
        page = self._pages.get("Mission")
        if not isinstance(page, MissionPageCTK):
            return
        last = self._coordinator.get_last_result()
        if last:
            page.set_last_scan_snapshot(
                files=fmt_int(last.files_scanned),
                groups=fmt_int(len(last.duplicate_groups)),
                reclaim=fmt_bytes(last.total_reclaimable_bytes),
            )
        else:
            page.set_last_scan_snapshot(files="—", groups="—", reclaim="—")
        n_res = len(self._coordinator.get_resumable_scan_ids())
        page.set_resume_hint("None" if n_res == 0 else f"{n_res} session(s)")
        hist = self._coordinator.get_history(6)
        lines: list[str] = []
        for h in hist:
            sid = str(h.get("scan_id", ""))
            short = (sid[:10] + "…") if len(sid) > 10 else sid or "—"
            lines.append(
                f"{short}  ·  {h.get('status', '—')}  ·  {fmt_int(h.get('files_scanned') or 0)} files"
            )
        page.set_recent_sessions_text(
            "\n".join(lines) if lines else "No saved scans in history yet. Complete a scan to populate this list."
        )

    def _on_scan_complete(self, result) -> None:
        self._active_scan_id = ""
        page = self._pages.get("Scan")
        if isinstance(page, ScanPageCTK):
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
        if self._active_page == "Mission":
            self._refresh_mission_page()
        self._route_after_scan()

    def _on_scan_error(self, error: str) -> None:
        self._active_scan_id = ""
        page = self._pages.get("Scan")
        if isinstance(page, ScanPageCTK):
            page.set_status(f"Error: {error[:120]}")
            page.set_session(session_id=self._active_scan_id[:8] + "..." if self._active_scan_id else "—", phase="error")

    def _on_scan_progress(self, progress) -> None:
        """Progress callback from coordinator worker thread -> UI thread."""
        def apply() -> None:
            page = self._pages.get("Scan")
            if not isinstance(page, ScanPageCTK):
                return
            page.set_metrics(
                files_scanned=int(getattr(progress, "files_found", 0) or 0),
                groups_found=int(getattr(progress, "groups_found", 0) or 0),
                elapsed_s=float(getattr(progress, "elapsed_seconds", 0.0) or 0.0),
                current_file=str(getattr(progress, "current_file", "") or ""),
                total_files=(
                    int(getattr(progress, "files_total", 0) or 0)
                    if getattr(progress, "files_total", None) is not None
                    else None
                ),
            )
            raw_phase = str(getattr(progress, "phase", "") or "").strip()
            sid = self._active_scan_id[:8] + "..." if self._active_scan_id else "pending"
            # Omit phase when empty so we don't stomp "Starting…" with a bogus generic label.
            if raw_phase:
                page.set_session(session_id=sid, phase=raw_phase)
            else:
                page.set_session(session_id=sid)

        self.root.after(0, apply)

    def _schedule_scan_status_poll(self) -> None:
        """Tiny heartbeat until CTK status strip exists."""
        page = self._pages.get("Scan")
        if isinstance(page, ScanPageCTK):
            page.set_scan_busy(self._coordinator.is_scanning)
            if self._coordinator.is_scanning:
                sid = self._active_scan_id[:8] + "..." if self._active_scan_id else "pending"
                page.set_status(f"Running (scan_id: {sid})")
                # Do not touch phase here — progress callbacks own pipeline stage (discovery vs hashing, etc.).
                page.set_session(session_id=sid)
            elif page.get_status().startswith("Running"):
                page.set_status("Idle")
                page.set_session(session_id="—", phase="—")
        self.root.after(1200, self._schedule_scan_status_poll)

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

    def _execute_review_lite_deletion(self, keep_map: dict[str, str]):
        """Execute deletion using CTK review-lite selections."""
        review = self._pages.get("Review")
        result = None
        if isinstance(review, ReviewPageCTK):
            result = review.get_loaded_result()
        if result is None:
            result = self._coordinator.get_last_result()
        if not result:
            return None
        plan = self._coordinator.create_deletion_plan(
            result=result,
            keep_strategy="first",
            group_keep_paths=keep_map,
        )
        if not plan or not plan.groups:
            return None
        return self._coordinator.execute_deletion(plan)

    def _placeholder_page(self, message: str) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self._content_host, corner_radius=0, fg_color="transparent")
        ctk.CTkLabel(page, text=message, text_color=("gray40", "gray70")).grid(
            row=0, column=0, padx=24, pady=24, sticky="nw"
        )
        return page

    def run(self) -> None:
        self.root.mainloop()
