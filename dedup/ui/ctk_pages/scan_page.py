"""
CustomTkinter Scan page (experimental).

Receives a mode preset from Home and centralizes scan command entry points
to reduce duplication with the dashboard.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import TclError, filedialog
from typing import TYPE_CHECKING, Callable, Optional

import customtkinter as ctk

from ..components.ctk_tooltip import CTkToolTip
from ..ctk_action_contracts import KeepPolicy, PostScanRoute, ScanMode, ScanStartPayload
from ..projections.phase_projection import PHASE_LABELS, canonical_phase
from ..state.selectors import scan_metrics, scan_session
from ..utils.formatting import fmt_duration, fmt_int
from .design_tokens import get_theme_colors, resolve_border_token
from .ui_utils import safe_callback

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

# Display labels in UI ↔ internal contract values
_KEEP_OPTIONS: tuple[tuple[str, KeepPolicy], ...] = (
    ("Newest file", "newest"),
    ("Oldest file", "oldest"),
    ("Largest file", "largest"),
    ("Smallest file", "smallest"),
    ("First found", "first"),
)
_KEEP_LABEL_TO_INTERNAL: dict[str, KeepPolicy] = {a: b for a, b in _KEEP_OPTIONS}
_INTERNAL_TO_KEEP_LABEL: dict[str, str] = {b: a for a, b in _KEEP_OPTIONS}

_POST_OPTIONS: tuple[tuple[str, PostScanRoute], ...] = (
    ("Review results", "review"),
    ("Stay on this page", "scan"),
    ("Home", "mission"),
)
_POST_LABEL_TO_INTERNAL: dict[str, PostScanRoute] = {a: b for a, b in _POST_OPTIONS}
_INTERNAL_TO_POST_LABEL: dict[str, str] = {b: a for a, b in _POST_OPTIONS}

_KEEP_POLICY_TOOLTIP = (
    "Which duplicate to keep when you delete extras:\n\n"
    "• Newest file — highest modified time\n"
    "• Oldest file — earliest modified time\n"
    "• Largest / Smallest — by file size on disk\n"
    "• First found — first path encountered during scan (stable order)"
)

_POST_ROUTE_TOOLTIP = (
    "Where to go after the scan finishes:\n\n"
    "• Review results — open the duplicate review screen\n"
    "• Stay on this page — remain on Scan\n"
    "• Home — return to the dashboard"
)


def _shorten_path(path: str, max_len: int = 72) -> str:
    p = (path or "").strip()
    if len(p) <= max_len:
        return p or "—"
    head = max_len // 2 - 2
    tail = max_len - head - 3
    return f"{p[:head]}…{p[-tail:]}"


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
        self._on_cancel_shell = on_cancel
        self._mode: ScanMode = "files"
        self._keep_policy = ctk.StringVar(value=_INTERNAL_TO_KEEP_LABEL["newest"])
        self._post_scan_route = ctk.StringVar(value=_INTERNAL_TO_POST_LABEL["review"])
        self._status_var = ctk.StringVar(value="Idle")
        self._status_dots_var = ctk.StringVar(value="")
        self._scan_dots_after_id: str | None = None
        self._scan_dots_busy = False
        self._folder_display_var = ctk.StringVar(value="—")
        self._phase_var = ctk.StringVar(value="—")
        self._ready_groups_var = ctk.StringVar(value="—")
        self._ready_reclaim_var = ctk.StringVar(value="—")
        self._m_files_var = ctk.StringVar(value="0")
        self._m_groups_var = ctk.StringVar(value="0")
        self._m_elapsed_var = ctk.StringVar(value="0s")
        self._m_current_var = ctk.StringVar(value="—")
        self._pct_var = ctk.StringVar(value="0%")
        self._header_pct_var = ctk.StringVar(value="—")
        self._eta_var = ctk.StringVar(value="ETA: —")
        self._unsub_store: Optional[Callable[[], None]] = None
        self._tokens = get_theme_colors()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build()

    def _build(self) -> None:
        tk = self._tokens
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        self._scroll = scroll

        header = ctk.CTkFrame(
            scroll,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="🔍  Scan Setup",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=tk["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        self._mode_label = ctk.CTkLabel(header, text="Preset: Files", text_color=tk["text_secondary"])
        self._mode_label.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))
        status_row = ctk.CTkFrame(header, fg_color="transparent")
        status_row.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 8))
        ctk.CTkLabel(status_row, textvariable=self._status_var, text_color=tk["text_secondary"]).pack(
            side="left", anchor="w"
        )
        ctk.CTkLabel(
            status_row,
            textvariable=self._status_dots_var,
            text_color=tk["text_secondary"],
            width=28,
            anchor="w",
        ).pack(side="left", padx=(2, 0))

        path_row = ctk.CTkFrame(header, fg_color="transparent")
        path_row.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 6))
        path_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(path_row, text="Folder:", text_color=tk["text_muted"]).grid(row=0, column=0, sticky="nw")
        ctk.CTkLabel(
            path_row,
            textvariable=self._folder_display_var,
            text_color=tk["text_primary"],
            wraplength=720,
            justify="left",
            anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        meta_row = ctk.CTkFrame(header, fg_color="transparent")
        meta_row.grid(row=4, column=0, sticky="w", padx=16, pady=(0, 12))
        ctk.CTkLabel(meta_row, text="Stage:", text_color=tk["text_muted"]).pack(side="left")
        ctk.CTkLabel(meta_row, textvariable=self._phase_var, text_color=tk["text_primary"]).pack(
            side="left", padx=(6, 16)
        )
        ctk.CTkLabel(meta_row, text="Progress:", text_color=tk["text_muted"]).pack(side="left")
        self._header_pct_label = ctk.CTkLabel(
            meta_row,
            textvariable=self._header_pct_var,
            text_color=tk["accent_primary"],
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._header_pct_label.pack(side="left", padx=(6, 0))

        target = ctk.CTkFrame(
            scroll,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        target.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        target.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            target, text="📂  Target Folder", font=ctk.CTkFont(size=18, weight="bold"), text_color=tk["text_primary"]
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))
        self._path_var = ctk.StringVar(value="")
        self._path_var.trace_add("write", lambda *_: self._sync_folder_display())
        ctk.CTkEntry(
            target,
            textvariable=self._path_var,
            placeholder_text="Choose a folder...",
            height=40,
            corner_radius=10,
            fg_color=tk["bg_elevated"],
            border_color=tk["border_subtle"],
            text_color=tk["text_primary"],
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        self._browse_btn = ctk.CTkButton(
            target,
            text="Browse…",
            width=120,
            height=40,
            corner_radius=10,
            fg_color=tk["bg_elevated"],
            hover_color=tk["bg_overlay"],
            text_color=tk["text_secondary"],
            border_width=1,
            border_color=tk["border_subtle"],
            command=self._browse,
        )
        self._browse_btn.grid(row=1, column=1, padx=(0, 16), pady=(0, 10), sticky="e")

        routing = ctk.CTkFrame(
            scroll,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        routing.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 12))
        routing.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            routing,
            text="Deletion preferences",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=tk["text_primary"],
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 10))
        keep_lbl = ctk.CTkFrame(routing, fg_color="transparent")
        keep_lbl.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))
        ctk.CTkLabel(keep_lbl, text="Which copy to keep", text_color=tk["text_secondary"]).pack(side="left")
        tip_k = ctk.CTkLabel(
            keep_lbl,
            text=" ⓘ",
            text_color=tk["text_muted"],
            cursor="hand2",
            font=ctk.CTkFont(size=14),
        )
        tip_k.pack(side="left")
        CTkToolTip(tip_k, _KEEP_POLICY_TOOLTIP, wraplength=340)
        self._keep_menu = ctk.CTkOptionMenu(
            routing,
            variable=self._keep_policy,
            values=[a for a, _ in _KEEP_OPTIONS],
            width=220,
            height=36,
            corner_radius=10,
            fg_color=tk["bg_elevated"],
            button_color=tk["bg_elevated"],
            button_hover_color=tk["accent_secondary"],
            dropdown_fg_color=tk["bg_panel"],
        )
        self._keep_menu.grid(row=1, column=1, sticky="w", padx=(0, 16), pady=(0, 8))
        CTkToolTip(self._keep_menu, _KEEP_POLICY_TOOLTIP, wraplength=340)

        post_lbl = ctk.CTkFrame(routing, fg_color="transparent")
        post_lbl.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 14))
        ctk.CTkLabel(post_lbl, text="When done, go to", text_color=tk["text_secondary"]).pack(side="left")
        tip_p = ctk.CTkLabel(
            post_lbl,
            text=" ⓘ",
            text_color=tk["text_muted"],
            cursor="hand2",
            font=ctk.CTkFont(size=14),
        )
        tip_p.pack(side="left")
        CTkToolTip(tip_p, _POST_ROUTE_TOOLTIP, wraplength=320)
        self._post_menu = ctk.CTkOptionMenu(
            routing,
            variable=self._post_scan_route,
            values=[a for a, _ in _POST_OPTIONS],
            width=220,
            height=36,
            corner_radius=10,
            fg_color=tk["bg_elevated"],
            button_color=tk["bg_elevated"],
            button_hover_color=tk["accent_secondary"],
            dropdown_fg_color=tk["bg_panel"],
        )
        self._post_menu.grid(row=2, column=1, sticky="w", padx=(0, 16), pady=(0, 14))
        CTkToolTip(self._post_menu, _POST_ROUTE_TOOLTIP, wraplength=320)

        actions = ctk.CTkFrame(
            scroll,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        actions.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 12))
        ctk.CTkLabel(
            actions, text="Actions", font=ctk.CTkFont(size=18, weight="bold"), text_color=tk["text_primary"]
        ).pack(anchor="w", padx=16, pady=(12, 8))
        row = ctk.CTkFrame(actions, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))
        self._start_btn = ctk.CTkButton(
            row,
            text="▶  Start Scan",
            width=160,
            height=40,
            corner_radius=10,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=tk["accent_primary"],
            hover_color=tk["accent_secondary"],
            text_color=("#FFFFFF", "#0A0E14"),
            command=self._start,
        )
        self._start_btn.pack(side="left", padx=(0, 8))
        self._resume_btn = ctk.CTkButton(
            row,
            text="Resume",
            width=140,
            height=40,
            corner_radius=10,
            fg_color=tk["bg_elevated"],
            hover_color=tk["bg_overlay"],
            text_color=tk["text_secondary"],
            border_width=1,
            border_color=tk["border_subtle"],
            command=self._on_resume,
        )
        self._resume_btn.pack(side="left", padx=(0, 8))
        self._cancel_btn = ctk.CTkButton(
            row,
            text="Back",
            width=130,
            height=40,
            corner_radius=10,
            fg_color=tk["bg_elevated"],
            hover_color=tk["bg_overlay"],
            text_color=tk["text_secondary"],
            border_width=1,
            border_color=tk["border_subtle"],
            command=self._on_cancel_shell,
        )
        self._cancel_btn.pack(side="left")

        self._ready = ctk.CTkFrame(
            scroll,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._ready.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 12))
        self._ready.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self._ready, text="Results", font=ctk.CTkFont(size=18, weight="bold"), text_color=tk["text_primary"]
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6))
        ctk.CTkLabel(self._ready, text="Groups found", text_color=tk["text_secondary"]).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 4)
        )
        ctk.CTkLabel(self._ready, textvariable=self._ready_groups_var, text_color=tk["text_primary"]).grid(
            row=1, column=1, sticky="w", padx=(0, 16), pady=(0, 4)
        )
        ctk.CTkLabel(self._ready, text="Estimated reclaim", text_color=tk["text_secondary"]).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 8)
        )
        ctk.CTkLabel(self._ready, textvariable=self._ready_reclaim_var, text_color=tk["text_primary"]).grid(
            row=2, column=1, sticky="w", padx=(0, 16), pady=(0, 8)
        )
        self._route_btn = ctk.CTkButton(
            self._ready,
            text="Open Review",
            width=180,
            height=40,
            corner_radius=10,
            fg_color=tk["accent_primary"],
            hover_color=tk["accent_secondary"],
            text_color=("#FFFFFF", "#0A0E14"),
        )
        self._route_btn.grid(row=3, column=0, padx=16, pady=(0, 14), sticky="w")
        self._ready.grid_remove()

        metrics = ctk.CTkFrame(
            scroll,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        metrics.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 12))
        metrics.grid_columnconfigure(0, minsize=180)
        metrics.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            metrics, text="Live Metrics", font=ctk.CTkFont(size=18, weight="bold"), text_color=tk["text_primary"]
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 8))
        ctk.CTkLabel(metrics, text="Files scanned", text_color=tk["text_secondary"]).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 4)
        )
        ctk.CTkLabel(metrics, textvariable=self._m_files_var, anchor="e", text_color=tk["text_primary"]).grid(
            row=1, column=1, sticky="ew", padx=(0, 16), pady=(0, 4)
        )
        ctk.CTkLabel(metrics, text="Groups found", text_color=tk["text_secondary"]).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 4)
        )
        ctk.CTkLabel(metrics, textvariable=self._m_groups_var, anchor="e", text_color=tk["text_primary"]).grid(
            row=2, column=1, sticky="ew", padx=(0, 16), pady=(0, 4)
        )
        ctk.CTkLabel(metrics, text="Elapsed", text_color=tk["text_secondary"]).grid(
            row=3, column=0, sticky="w", padx=16, pady=(0, 4)
        )
        ctk.CTkLabel(metrics, textvariable=self._m_elapsed_var, anchor="e", text_color=tk["text_primary"]).grid(
            row=3, column=1, sticky="ew", padx=(0, 16), pady=(0, 4)
        )
        ctk.CTkLabel(metrics, text="Current file", text_color=tk["text_secondary"]).grid(
            row=4, column=0, sticky="w", padx=16, pady=(0, 12)
        )
        ctk.CTkLabel(metrics, textvariable=self._m_current_var, anchor="e", text_color=tk["text_primary"]).grid(
            row=4, column=1, sticky="ew", padx=(0, 16), pady=(0, 12)
        )

        prog = ctk.CTkFrame(
            scroll,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        prog.grid(row=6, column=0, sticky="ew", padx=20, pady=(0, 12))
        prog.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            prog, text="Progress", font=ctk.CTkFont(size=18, weight="bold"), text_color=tk["text_primary"]
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))
        self._bar = ctk.CTkProgressBar(prog, progress_color=tk["accent_primary"], fg_color=tk["bg_elevated"])
        self._bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._bar.set(0.0)
        meta = ctk.CTkFrame(prog, fg_color="transparent")
        meta.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        ctk.CTkLabel(meta, textvariable=self._pct_var, text_color=tk["text_primary"]).pack(side="left")
        ctk.CTkLabel(meta, textvariable=self._eta_var, text_color=tk["text_secondary"]).pack(side="right")

        self._info = ctk.CTkTextbox(
            scroll,
            height=120,
            wrap="word",
            corner_radius=12,
            fg_color=tk["bg_surface"],
            text_color=tk["text_secondary"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._info.grid(row=7, column=0, sticky="ew", padx=20, pady=(0, 20))
        self._info.insert(
            "end",
            "Select a folder and press Start Scan.\n\n"
            "Set which copy to keep and where to go when the scan finishes before you start.\n",
        )
        self._info.configure(state="disabled")

        self._themed_sections = [header, target, routing, actions, self._ready, metrics, prog]
        self._sync_folder_display()

    def _sync_folder_display(self) -> None:
        raw = self._path_var.get().strip()
        self._folder_display_var.set(_shorten_path(raw) if raw else "—")

    def apply_theme_tokens(self, tokens: dict) -> None:
        """Sync panel surfaces with CEREBRO semantic tokens (CTk defaults do not follow ThemeManager)."""
        panel = str(tokens.get("bg_panel", "#161b22"))
        self.configure(fg_color=panel)
        if hasattr(self, "_scroll"):
            self._scroll.configure(fg_color="transparent", label_fg_color="transparent")
        elev = str(tokens.get("bg_elevated", "#21262d"))
        surf = str(tokens.get("bg_surface", elev))
        acc = str(tokens.get("accent_primary", "#3B8ED0"))
        br = resolve_border_token(tokens)
        txt = str(tokens.get("text_secondary", "#94A3B8"))
        for f in self._themed_sections:
            f.configure(fg_color=panel, border_color=br)
        if hasattr(self, "_header_pct_label"):
            self._header_pct_label.configure(text_color=acc)
        self._start_btn.configure(fg_color=acc)
        self._resume_btn.configure(
            fg_color=elev,
            hover_color=str(tokens.get("bg_overlay", "#21262d")),
            text_color=txt,
            border_color=br,
        )
        self._browse_btn.configure(fg_color=elev, border_color=br)
        self._cancel_btn.configure(fg_color=elev, border_color=br)
        self._route_btn.configure(fg_color=acc)
        self._bar.configure(progress_color=acc, fg_color=elev)
        self._info.configure(fg_color=surf, text_color=txt, border_color=br)

        # Update all text labels with live token colors
        self._update_label_colors(self, tokens)

    def _update_label_colors(self, widget, tokens: dict) -> None:
        """Recursively update all label text colors in widget tree with live tokens."""
        txt_primary = str(tokens.get("text_primary", "#F1F5F9"))
        txt_secondary = str(tokens.get("text_secondary", "#94A3B8"))
        txt_muted = str(tokens.get("text_muted", "#6B7280"))
        acc = str(tokens.get("accent_primary", "#3B8ED0"))

        try:
            for child in widget.winfo_children():
                if child.__class__.__name__ == "CTkLabel":
                    try:
                        current_color = child.cget("text_color")
                        if current_color and isinstance(current_color, tuple) and len(current_color) == 2:
                            new_color = (txt_primary, "#0A0E14")
                            if current_color != new_color:
                                child.configure(text_color=new_color)
                        elif "accent" in str(current_color).lower():
                            if current_color != acc:
                                child.configure(text_color=acc)
                        elif "muted" in str(current_color).lower():
                            if current_color != txt_muted:
                                child.configure(text_color=txt_muted)
                        elif "secondary" in str(current_color).lower():
                            if current_color != txt_secondary:
                                child.configure(text_color=txt_secondary)
                        elif current_color and current_color != txt_primary:
                            child.configure(text_color=txt_primary)
                    except Exception:
                        pass
                elif child.__class__.__name__ in ("CTkFrame", "CTkScrollableFrame"):
                    self._update_label_colors(child, tokens)
        except Exception:
            pass

    def set_scan_busy(self, busy: bool) -> None:
        """Disable start/resume while a scan worker is active (shell syncs via coordinator)."""
        st = "disabled" if busy else "normal"
        self._start_btn.configure(state=st)
        self._resume_btn.configure(state=st)
        self._cancel_btn.configure(
            text="Cancel scan" if busy else "Back",
            state="normal",
        )
        if busy:
            self._start_scan_dots_animation()
        else:
            self._stop_scan_dots_animation()
            self._header_pct_var.set("—")
            self._bar.set(0.0)
            self._pct_var.set("0%")

    def set_target_path(self, path: str) -> None:
        self._path_var.set(path.strip())

    def apply_decision_defaults(self, keep_policy: KeepPolicy, post_scan_route: PostScanRoute) -> None:
        kp = keep_policy if keep_policy in _INTERNAL_TO_KEEP_LABEL else "newest"
        pr = post_scan_route if post_scan_route in _INTERNAL_TO_POST_LABEL else "review"
        self._keep_policy.set(_INTERNAL_TO_KEEP_LABEL[kp])
        self._post_scan_route.set(_INTERNAL_TO_POST_LABEL[pr])

    def set_mode(self, mode: str) -> None:
        """Update page from Home entry point."""
        self._mode = mode if mode in ("photos", "videos", "files") else "files"
        self._mode_label.configure(text=f"Preset: {self._mode.title()}")

    def attach_store(self, store: "UIStateStore") -> None:
        """Drive live metrics/session from UIStateStore (fed by ProjectionHub)."""
        self.detach_store()

        def on_state(state) -> None:
            sess = scan_session(state)
            met = scan_metrics(state)
            if sess is not None and getattr(sess, "session_id", ""):
                phase = getattr(sess, "current_phase", None) or ""
                self.set_session(phase=phase or None)
                st = getattr(sess, "status", "") or ""
                if st == "running":
                    self.set_status("Scanning…")
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

        self._unsub_store = store.subscribe(on_state, fire_immediately=False)
        self._bind_scan_shortcuts()

    def detach_store(self) -> None:
        if self._unsub_store:
            safe_callback(self._unsub_store, context="ScanPageCTK detach_store")
            self._unsub_store = None

    def _browse(self) -> None:
        path = filedialog.askdirectory(title="Select Folder to Scan")
        if path:
            self._path_var.set(str(Path(path).resolve()))

    def _start(self) -> None:
        lbl_k = self._keep_policy.get()
        lbl_p = self._post_scan_route.get()
        keep_policy: KeepPolicy = _KEEP_LABEL_TO_INTERNAL.get(lbl_k, "newest")
        post_scan_route: PostScanRoute = _POST_LABEL_TO_INTERNAL.get(lbl_p, "review")
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

    def _start_scan_dots_animation(self) -> None:
        """Ellipsis pulse next to status while a scan is active (does not replace hub-driven status text)."""
        self._stop_scan_dots_animation()
        self._scan_dots_busy = True
        self._scan_dots_i = 0

        def tick() -> None:
            if not self._scan_dots_busy:
                return
            self._scan_dots_i = (self._scan_dots_i + 1) % 4
            self._status_dots_var.set("." * self._scan_dots_i)
            self._scan_dots_after_id = self.after(500, tick)

        tick()

    def _stop_scan_dots_animation(self) -> None:
        self._scan_dots_busy = False
        aid = getattr(self, "_scan_dots_after_id", None)
        if aid:
            try:
                self.after_cancel(aid)
            except (TclError, ValueError, RuntimeError):
                pass
            self._scan_dots_after_id = None
        self._status_dots_var.set("")

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
        """Update pipeline phase; session_id is accepted for API compatibility but not shown in the UI."""
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
            pct = f"{int(frac * 100):d}%"
            self._pct_var.set(pct)
            self._header_pct_var.set(pct)
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
        self._header_pct_var.set("…")
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

    def _bind_scan_shortcuts(self) -> None:
        """Bind scan page specific keyboard shortcuts."""
        self.bind("<Control-Key-Return>", lambda e: self._start())
        self.bind("<Escape>", lambda e: self._on_cancel_shell())
