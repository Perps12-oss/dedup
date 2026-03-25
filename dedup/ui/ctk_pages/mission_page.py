"""
CustomTkinter Mission page (experimental).

First migrated page for the CTK backend. This intentionally mirrors the
high-level intent of the ttk Mission page without full feature parity yet.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Callable, Optional

import customtkinter as ctk

from ..ctk_action_contracts import ScanStartPayload
from ..utils.formatting import fmt_bytes, fmt_int

if TYPE_CHECKING:
    from ..state.store import UIStateStore


def _quick_scan_options() -> dict:
    """Same defaults as Scan page for files / all-media preset."""
    return {"media_category": "all", "scan_mode": "deep", "include_hidden": False, "scan_subfolders": True}


class MissionPageCTK(ctk.CTkFrame):
    """Mission landing surface for CTK backend."""

    def __init__(
        self,
        parent,
        *,
        on_start_scan: Callable[[], None],
        on_resume_scan: Callable[[], None],
        on_open_last_review: Callable[[], None],
        on_quick_scan: Callable[[ScanStartPayload], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_start_scan = on_start_scan
        self._on_resume_scan = on_resume_scan
        self._on_open_last_review = on_open_last_review
        self._on_quick_scan = on_quick_scan
        self._quick_path_var = ctk.StringVar(value="")
        self._last_files_var = ctk.StringVar(value="—")
        self._last_groups_var = ctk.StringVar(value="—")
        self._last_reclaim_var = ctk.StringVar(value="—")
        self._resume_status_var = ctk.StringVar(value="—")
        self._recent_var = ctk.StringVar(value="No recent sessions yet.")
        self._unsub_store: Optional[Callable[[], None]] = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self._build()

    def set_last_scan_snapshot(self, *, files: str, groups: str, reclaim: str) -> None:
        self._last_files_var.set(files)
        self._last_groups_var.set(groups)
        self._last_reclaim_var.set(reclaim)

    def set_resume_hint(self, text: str) -> None:
        self._resume_status_var.set(text)

    def attach_store(self, store: "UIStateStore") -> None:
        """Sync Mission summary from coordinator-derived MissionState (same as classic shell)."""
        if self._unsub_store:
            try:
                self._unsub_store()
            except Exception:
                pass
            self._unsub_store = None

        def on_state(state) -> None:
            m = getattr(state, "mission", None)
            if m is None:
                return
            ls = getattr(m, "last_scan", None)
            if ls is not None:
                self.set_last_scan_snapshot(
                    files=fmt_int(getattr(ls, "files_scanned", 0) or 0),
                    groups=fmt_int(getattr(ls, "duplicate_groups", 0) or 0),
                    reclaim=fmt_bytes(getattr(ls, "reclaimable_bytes", 0) or 0),
                )
            else:
                self.set_last_scan_snapshot(files="—", groups="—", reclaim="—")
            res_ids = getattr(m, "resumable_scan_ids", ()) or ()
            n_res = len(res_ids)
            self.set_resume_hint("None" if n_res == 0 else f"{n_res} session(s)")
            lines: list[str] = []
            for d in getattr(m, "recent_sessions", ()) or ():
                sid = str(d.get("scan_id", ""))
                short = (sid[:10] + "…") if len(sid) > 10 else sid or "—"
                lines.append(
                    f"{short}  ·  {d.get('status', '—')}  ·  {fmt_int(d.get('files_scanned') or 0)} files"
                )
            self.set_recent_sessions_text(
                "\n".join(lines)
                if lines
                else "No saved scans in history yet. Complete a scan to populate this list."
            )

        self._unsub_store = store.subscribe(on_state, fire_immediately=True)

    def detach_store(self) -> None:
        if self._unsub_store:
            try:
                self._unsub_store()
            except Exception:
                pass
            self._unsub_store = None

    def _build(self) -> None:
        # Header + CTA row
        hero = ctk.CTkFrame(self, corner_radius=12)
        hero.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        hero.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hero, text="Mission Control", font=ctk.CTkFont(size=28, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=18, pady=(16, 4)
        )
        ctk.CTkLabel(
            hero,
            text="Start a scan, resume interrupted work, or open your last review.",
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 14))

        cta = ctk.CTkFrame(hero, fg_color="transparent")
        cta.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 16))
        ctk.CTkButton(cta, text="Start New Scan", width=170, command=self._on_start_scan).pack(side="left", padx=(0, 8))
        ctk.CTkButton(cta, text="Resume Interrupted", width=170, command=self._on_resume_scan).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(
            cta, text="Open Last Review", width=170, fg_color="gray35", command=self._on_open_last_review
        ).pack(side="left")

        # Readiness row
        ready = ctk.CTkFrame(self, fg_color="transparent")
        ready.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        ready.grid_columnconfigure((0, 1, 2), weight=1)

        self._metric_card(
            ready,
            0,
            "Engine Status",
            [("Health", "Healthy"), ("Pipeline", "Durable"), ("Resume", self._resume_status_var)],
        )
        self._metric_card(
            ready,
            1,
            "Last Scan",
            [("Files", self._last_files_var), ("Groups", self._last_groups_var), ("Reclaimable", self._last_reclaim_var)],
        )
        self._metric_card(
            ready,
            2,
            "Trash Protection",
            [("Status", "Active"), ("Revalidation", "Enabled"), ("Audit", "Enabled")],
        )

        recent = ctk.CTkFrame(self, corner_radius=12)
        recent.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 12))
        recent.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(recent, text="Recent Sessions", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 6)
        )
        recent_box = ctk.CTkTextbox(recent, height=100, wrap="word", activate_scrollbars=True)
        recent_box.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
        recent_box.insert("1.0", self._recent_var.get())
        recent_box.configure(state="disabled")
        self._recent_box = recent_box

        quick = ctk.CTkFrame(self, corner_radius=12)
        quick.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        quick.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(quick, text="Quick Scan", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4)
        )
        ctk.CTkLabel(
            quick,
            text="All-files preset · same defaults as Scan (keep policy / post-scan use the Scan page or last run).",
            text_color=("gray40", "gray70"),
            wraplength=640,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))
        ctk.CTkEntry(quick, textvariable=self._quick_path_var, placeholder_text="Folder to scan…").grid(
            row=2, column=0, sticky="ew", padx=16, pady=(0, 8)
        )
        qb = ctk.CTkFrame(quick, fg_color="transparent")
        qb.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 16))
        ctk.CTkButton(qb, text="Browse…", width=120, fg_color="gray35", command=self._quick_browse).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(qb, text="Start Quick Scan", width=160, command=self._quick_start).pack(side="left")

    def _quick_browse(self) -> None:
        path = filedialog.askdirectory(title="Select Folder for Quick Scan")
        if path:
            self._quick_path_var.set(str(Path(path).resolve()))

    def _quick_start(self) -> None:
        raw = self._quick_path_var.get().strip()
        if not raw:
            messagebox.showwarning("Quick Scan", "Choose a folder first.", parent=self.winfo_toplevel())
            return
        payload: ScanStartPayload = {
            "mode": "files",
            "path": raw,
            "options": _quick_scan_options(),
            "keep_policy": "newest",
            "post_scan_route": "review",
        }
        self._on_quick_scan(payload)

    def set_recent_sessions_text(self, text: str) -> None:
        self._recent_var.set(text)
        if hasattr(self, "_recent_box"):
            self._recent_box.configure(state="normal")
            self._recent_box.delete("1.0", "end")
            self._recent_box.insert("1.0", text)
            self._recent_box.configure(state="disabled")

    def _metric_card(
        self,
        parent: ctk.CTkFrame,
        col: int,
        title: str,
        rows: list[tuple[str, str | ctk.StringVar]],
    ) -> None:
        card = ctk.CTkFrame(parent, corner_radius=12)
        card.grid(row=0, column=col, sticky="ew", padx=6, pady=0)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=14, pady=(12, 8))
        for k, v in rows:
            row_fr = ctk.CTkFrame(card, fg_color="transparent")
            row_fr.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(row_fr, text=k, text_color=("gray40", "gray70")).pack(side="left")
            if isinstance(v, ctk.StringVar):
                ctk.CTkLabel(row_fr, textvariable=v).pack(side="right")
            else:
                ctk.CTkLabel(row_fr, text=v).pack(side="right")
        ctk.CTkLabel(card, text=" ").pack(pady=(0, 4))
