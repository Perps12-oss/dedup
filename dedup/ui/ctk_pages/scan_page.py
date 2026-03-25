"""
CustomTkinter Scan page (experimental).

Receives a mode preset from Welcome and centralizes scan command entry points
to reduce duplication with Mission.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable, Optional

import customtkinter as ctk

from ..ctk_action_contracts import KeepPolicy, PostScanRoute, ScanMode, ScanStartPayload
from ..projections.phase_projection import PHASE_LABELS, canonical_phase
from ..state.selectors import scan_metrics, scan_session
from ..utils.formatting import fmt_duration, fmt_int

if TYPE_CHECKING:
    from ..state.store import UIStateStore

# Pipeline stages (engine) vs session activity ("Running" in status) — keep phase column on pipeline only.
_PHASE_EXACT_LABELS: dict[str, str] = {
    "complete": "Complete",
    "cancelled": "Cancelled",
    "error": "Error",
    "resuming": "Resuming",
    "starting": "Starting…",
    # Legacy / generic — never a real pipeline stage; avoid flicker with discovery
    "running": "Starting…",
    "idle": "—",
}


class ScanPageCTK(ctk.CTkFrame):
    """Task-oriented scan setup surface for CTK backend."""

    def __init__(
        self,
        parent,
        *,
        on_start: Callable[[ScanStartPayload], None],
        on_resume: Callable[[], None],
        on_cancel: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_start = on_start
        self._on_resume = on_resume
        self._on_cancel = on_cancel
        self._mode: ScanMode = "files"
        self._keep_policy = ctk.StringVar(value="newest")
        self._post_scan_route = ctk.StringVar(value="review")
        self._status_var = ctk.StringVar(value="Idle")
        self._session_id_var = ctk.StringVar(value="—")
        self._phase_var = ctk.StringVar(value="—")
        self._ready_groups_var = ctk.StringVar(value="—")
        self._ready_reclaim_var = ctk.StringVar(value="—")
        self._m_files_var = ctk.StringVar(value="0")
        self._m_groups_var = ctk.StringVar(value="0")
        self._m_elapsed_var = ctk.StringVar(value="0s")
        self._m_current_var = ctk.StringVar(value="—")
        self._pct_var = ctk.StringVar(value="0%")
        self._eta_var = ctk.StringVar(value="ETA: —")
        self._unsub_store: Optional[Callable[[], None]] = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(7, weight=1)
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=12)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Scan Setup", font=ctk.CTkFont(size=26, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4)
        )
        self._mode_label = ctk.CTkLabel(header, text="Preset: Files", text_color=("gray40", "gray70"))
        self._mode_label.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))
        ctk.CTkLabel(header, textvariable=self._status_var, text_color=("gray40", "gray70")).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 12)
        )

        # Lightweight session bar until CTK status strip is migrated.
        sbar = ctk.CTkFrame(header, fg_color="transparent")
        sbar.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 12))
        ctk.CTkLabel(sbar, text="Session:", text_color=("gray40", "gray70")).pack(side="left")
        ctk.CTkLabel(sbar, textvariable=self._session_id_var).pack(side="left", padx=(6, 14))
        ctk.CTkLabel(sbar, text="Stage:", text_color=("gray40", "gray70")).pack(side="left")
        ctk.CTkLabel(sbar, textvariable=self._phase_var).pack(side="left", padx=(6, 0))

        target = ctk.CTkFrame(self, corner_radius=12)
        target.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        target.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(target, text="Target Folder", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 8)
        )
        self._path_var = ctk.StringVar(value="")
        ctk.CTkEntry(target, textvariable=self._path_var, placeholder_text="Choose a folder...").grid(
            row=1, column=0, sticky="ew", padx=16, pady=(0, 10)
        )
        ctk.CTkButton(target, text="Browse...", width=120, fg_color="gray35", command=self._browse).grid(
            row=1, column=1, padx=(0, 16), pady=(0, 10), sticky="e"
        )

        # Decisions that used to concentrate in Review are moved earlier to Scan setup.
        routing = ctk.CTkFrame(self, corner_radius=12)
        routing.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 12))
        routing.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(routing, text="Decision Defaults", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 10)
        )
        ctk.CTkLabel(routing, text="Default keep policy", text_color=("gray40", "gray70")).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 8)
        )
        ctk.CTkOptionMenu(
            routing,
            variable=self._keep_policy,
            values=["newest", "oldest", "largest", "smallest", "first"],
            width=220,
        ).grid(row=1, column=1, sticky="w", padx=(0, 16), pady=(0, 8))

        ctk.CTkLabel(routing, text="After scan completes", text_color=("gray40", "gray70")).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 14)
        )
        ctk.CTkOptionMenu(
            routing,
            variable=self._post_scan_route,
            values=["review", "scan", "mission"],
            width=220,
        ).grid(row=2, column=1, sticky="w", padx=(0, 16), pady=(0, 14))

        actions = ctk.CTkFrame(self, corner_radius=12)
        actions.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 12))
        ctk.CTkLabel(actions, text="Actions", font=ctk.CTkFont(size=18, weight="bold")).pack(
            anchor="w", padx=16, pady=(12, 8)
        )
        row = ctk.CTkFrame(actions, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))
        self._start_btn = ctk.CTkButton(row, text="Start Scan", width=150, command=self._start)
        self._start_btn.pack(side="left", padx=(0, 8))
        self._resume_btn = ctk.CTkButton(row, text="Resume", width=150, command=self._on_resume)
        self._resume_btn.pack(side="left", padx=(0, 8))
        self._cancel_btn = ctk.CTkButton(row, text="Back", width=150, fg_color="gray35", command=self._on_cancel)
        self._cancel_btn.pack(side="left")

        # Completion summary to avoid forcing users into full Review immediately.
        self._ready = ctk.CTkFrame(self, corner_radius=12)
        self._ready.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 12))
        self._ready.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self._ready, text="Review Readiness", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )
        ctk.CTkLabel(self._ready, text="Groups found", text_color=("gray40", "gray70")).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 4)
        )
        ctk.CTkLabel(self._ready, textvariable=self._ready_groups_var).grid(
            row=1, column=1, sticky="w", padx=(0, 16), pady=(0, 4)
        )
        ctk.CTkLabel(self._ready, text="Estimated reclaim", text_color=("gray40", "gray70")).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 8)
        )
        ctk.CTkLabel(self._ready, textvariable=self._ready_reclaim_var).grid(
            row=2, column=1, sticky="w", padx=(0, 16), pady=(0, 8)
        )
        self._route_btn = ctk.CTkButton(self._ready, text="Open Review", width=170)
        self._route_btn.grid(row=3, column=0, padx=16, pady=(0, 14), sticky="w")
        self._ready.grid_remove()

        # Lightweight live metrics while scan is running.
        metrics = ctk.CTkFrame(self, corner_radius=12)
        metrics.grid(row=6, column=0, sticky="ew", padx=20, pady=(0, 12))
        # Fixed key/value columns prevent "side-to-side" jitter while values change.
        metrics.grid_columnconfigure(0, minsize=180)
        metrics.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(metrics, text="Live Metrics", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 8)
        )
        ctk.CTkLabel(metrics, text="Files scanned", text_color=("gray40", "gray70")).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 4)
        )
        ctk.CTkLabel(metrics, textvariable=self._m_files_var, anchor="e").grid(
            row=1, column=1, sticky="ew", padx=(0, 16), pady=(0, 4)
        )
        ctk.CTkLabel(metrics, text="Groups found", text_color=("gray40", "gray70")).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 4)
        )
        ctk.CTkLabel(metrics, textvariable=self._m_groups_var, anchor="e").grid(
            row=2, column=1, sticky="ew", padx=(0, 16), pady=(0, 4)
        )
        ctk.CTkLabel(metrics, text="Elapsed", text_color=("gray40", "gray70")).grid(
            row=3, column=0, sticky="w", padx=16, pady=(0, 4)
        )
        ctk.CTkLabel(metrics, textvariable=self._m_elapsed_var, anchor="e").grid(
            row=3, column=1, sticky="ew", padx=(0, 16), pady=(0, 4)
        )
        ctk.CTkLabel(metrics, text="Current file", text_color=("gray40", "gray70")).grid(
            row=4, column=0, sticky="w", padx=16, pady=(0, 12)
        )
        ctk.CTkLabel(metrics, textvariable=self._m_current_var, anchor="e").grid(
            row=4, column=1, sticky="ew", padx=(0, 16), pady=(0, 12)
        )

        prog = ctk.CTkFrame(self, corner_radius=12)
        # Keep progress above metrics so it's visible without scrolling.
        prog.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 12))
        prog.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(prog, text="Progress", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 8)
        )
        self._bar = ctk.CTkProgressBar(prog)
        self._bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._bar.set(0.0)
        meta = ctk.CTkFrame(prog, fg_color="transparent")
        meta.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        ctk.CTkLabel(meta, textvariable=self._pct_var).pack(side="left")
        ctk.CTkLabel(meta, textvariable=self._eta_var, text_color=("gray40", "gray70")).pack(side="right")

        self._info = ctk.CTkTextbox(self, wrap="word")
        self._info.grid(row=7, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self._info.insert(
            "end",
            "Preset behavior:\n"
            "- Photos: image-focused category and common defaults\n"
            "- Videos: video-focused category and common defaults\n"
            "- Files: all media/files default\n\n"
            "Flow redistribution in progress:\n"
            "- Default keep-policy is configured here (not Review).\n"
            "- Post-scan destination is configured here.\n",
        )
        self._info.configure(state="disabled")

    def set_scan_busy(self, busy: bool) -> None:
        """Disable start/resume while a scan worker is active (shell syncs via coordinator)."""
        st = "disabled" if busy else "normal"
        self._start_btn.configure(state=st)
        self._resume_btn.configure(state=st)
        self._cancel_btn.configure(
            text="Stop scan" if busy else "Back",
            state="normal",
        )

    def set_target_path(self, path: str) -> None:
        self._path_var.set(path.strip())

    def apply_decision_defaults(self, keep_policy: KeepPolicy, post_scan_route: PostScanRoute) -> None:
        kp = keep_policy if keep_policy in ("newest", "oldest", "largest", "smallest", "first") else "newest"
        pr = post_scan_route if post_scan_route in ("review", "scan", "mission") else "review"
        self._keep_policy.set(kp)
        self._post_scan_route.set(pr)

    def set_mode(self, mode: str) -> None:
        """Update page from Welcome entry point."""
        self._mode = mode if mode in ("photos", "videos", "files") else "files"
        self._mode_label.configure(text=f"Preset: {self._mode.title()}")

    def attach_store(self, store: "UIStateStore") -> None:
        """Drive live metrics/session from UIStateStore (fed by ProjectionHub)."""
        self.detach_store()

        def on_state(state) -> None:
            sess = scan_session(state)
            met = scan_metrics(state)
            if sess is not None and getattr(sess, "session_id", ""):
                sid = str(sess.session_id)
                short = (sid[:8] + "…") if len(sid) > 8 else sid
                phase = getattr(sess, "current_phase", None) or ""
                self.set_session(session_id=short, phase=phase or None)
                st = getattr(sess, "status", "") or ""
                if st == "running":
                    self.set_status(f"Running ({short})")
                elif st == "completed":
                    self.set_status("Completed")
                elif st in ("cancelled", "failed"):
                    self.set_status(st.title())
            if met is not None:
                files_n = int(getattr(met, "files_discovered_total", 0) or 0)
                groups_n = int(getattr(met, "duplicate_groups_live", 0) or 0)
                elapsed = float(getattr(met, "elapsed_s", 0.0) or 0.0)
                cur = str(getattr(met, "current_file", "") or "")
                total_u = getattr(met, "current_phase_total_units", None)
                total_files = int(total_u) if total_u is not None else None
                self.set_metrics(
                    files_scanned=files_n,
                    groups_found=groups_n,
                    elapsed_s=elapsed,
                    current_file=cur,
                    total_files=total_files,
                )
                eta_lbl = met.eta_label
                if eta_lbl and eta_lbl != "—":
                    self._eta_var.set(f"ETA: {eta_lbl}")

        self._unsub_store = store.subscribe(on_state, fire_immediately=True)

    def detach_store(self) -> None:
        if self._unsub_store:
            try:
                self._unsub_store()
            except Exception:
                pass
            self._unsub_store = None

    def _browse(self) -> None:
        path = filedialog.askdirectory(title="Select Folder to Scan")
        if path:
            self._path_var.set(str(Path(path).resolve()))

    def _start(self) -> None:
        keep_policy: KeepPolicy = self._keep_policy.get() if self._keep_policy.get() in {
            "newest",
            "oldest",
            "largest",
            "smallest",
            "first",
        } else "newest"
        post_scan_route: PostScanRoute = self._post_scan_route.get() if self._post_scan_route.get() in {
            "review",
            "scan",
            "mission",
        } else "review"
        payload: ScanStartPayload = {
            "mode": self._mode,
            "path": self._path_var.get().strip(),
            "options": self._default_options_for_mode(self._mode),
            "keep_policy": keep_policy,
            "post_scan_route": post_scan_route,
        }
        self._on_start(payload)

    def set_status(self, text: str) -> None:
        self._status_var.set(text)

    def get_status(self) -> str:
        return str(self._status_var.get() or "")

    @staticmethod
    def _format_pipeline_phase(raw: str) -> str:
        """Map engine progress.phase to a stable UI label (session bar 'Phase:' column)."""
        s = (raw or "").strip()
        if s == "—":
            return "—"
        if not s:
            return "—"
        key = s.lower()
        if key in _PHASE_EXACT_LABELS:
            return _PHASE_EXACT_LABELS[key]
        canon = canonical_phase(key)
        if canon in PHASE_LABELS:
            return PHASE_LABELS[canon]
        return s.replace("_", " ").title()

    def set_session(
        self,
        *,
        session_id: str | None = None,
        phase: str | None = None,
    ) -> None:
        """Update session id and/or pipeline phase (omit either field to leave it unchanged)."""
        if session_id is not None:
            self._session_id_var.set(session_id or "—")
        if phase is not None:
            self._phase_var.set(self._format_pipeline_phase(phase))

    def set_metrics(
        self,
        *,
        files_scanned: int,
        groups_found: int,
        elapsed_s: float,
        current_file: str,
        total_files: int | None = None,
    ) -> None:
        """Render live scan metrics from progress callbacks."""
        self._m_files_var.set(fmt_int(files_scanned))
        self._m_groups_var.set(fmt_int(groups_found))
        self._m_elapsed_var.set(fmt_duration(elapsed_s))
        self._m_current_var.set(Path(current_file).name if current_file else "—")
        self._update_progress(files_scanned=files_scanned, total_files=total_files, elapsed_s=elapsed_s)

    def _update_progress(self, *, files_scanned: int, total_files: int | None, elapsed_s: float) -> None:
        """
        Stage-1 progress behavior:
        - determinate when total is known
        - gentle pulse approximation when total is unknown
        - ETA only when confidence is sufficient
        """
        if total_files and total_files > 0:
            frac = max(0.0, min(1.0, files_scanned / total_files))
            self._bar.set(frac)
            self._pct_var.set(f"{int(frac * 100):d}%")
            rem = max(0, total_files - files_scanned)
            if elapsed_s > 0.6 and files_scanned > 10:
                rate = files_scanned / elapsed_s
                if rate > 0:
                    self._eta_var.set(f"ETA: {fmt_duration(rem / rate)}")
                    return
            self._eta_var.set("ETA: —")
            return

        # Unknown total (common during discovery): keep visible movement without fake percent.
        pulse = min(0.93, 1.0 - pow(2.718281828, -(max(files_scanned, 0) / 6000.0))) if files_scanned > 0 else 0.0
        self._bar.set(pulse)
        self._pct_var.set("…")
        if elapsed_s > 0.6 and files_scanned > 0:
            rate = files_scanned / elapsed_s
            self._eta_var.set(f"~{rate:,.0f} files/s · total unknown")
        else:
            self._eta_var.set("ETA: —")

    def set_review_readiness(
        self,
        *,
        groups_found: int,
        reclaim_text: str,
        route_label: str,
        on_route: Callable[[], None],
    ) -> None:
        """Show completion summary and route action."""
        self._ready_groups_var.set(f"{groups_found:,}")
        self._ready_reclaim_var.set(reclaim_text)
        self._route_btn.configure(text=route_label, command=on_route)
        self._ready.grid()

    def _default_options_for_mode(self, mode: ScanMode) -> dict:
        if mode == "photos":
            return {"media_category": "images", "scan_mode": "deep", "include_hidden": False, "scan_subfolders": True}
        if mode == "videos":
            return {"media_category": "videos", "scan_mode": "deep", "include_hidden": False, "scan_subfolders": True}
        return {"media_category": "all", "scan_mode": "deep", "include_hidden": False, "scan_subfolders": True}
