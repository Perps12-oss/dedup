"""
CustomTkinter Diagnostics page (experimental).

Read-only view of scan coordinator state and the in-process diagnostics recorder.
Full hub-driven diagnostics remain on the classic ttk shell.
"""

from __future__ import annotations

from datetime import datetime
from tkinter import messagebox
from typing import TYPE_CHECKING, Callable, Optional

import customtkinter as ctk

from ...infrastructure.diagnostics import get_diagnostics_recorder
from ..state.selectors import scan_events_log, scan_session

if TYPE_CHECKING:
    from ...orchestration.coordinator import ScanCoordinator
    from ..state.store import UIStateStore


class DiagnosticsPageCTK(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        *,
        coordinator: ScanCoordinator,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._coordinator = coordinator
        self._unsub_store: Optional[Callable[[], None]] = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self._build()

    def _build(self) -> None:
        top = ctk.CTkFrame(self, corner_radius=12)
        top.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Diagnostics", font=ctk.CTkFont(size=26, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4)
        )
        ctk.CTkLabel(
            top,
            text="Coordinator + recorder + live scan event log (ProjectionHub → store). Phase timelines / JSON export: classic shell.",
            text_color=("gray40", "gray70"),
            wraplength=720,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))
        ctk.CTkButton(top, text="Refresh", width=120, fg_color="gray35", command=self.reload).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 12)
        )

        status = ctk.CTkFrame(self, corner_radius=12)
        status.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        status.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(status, text="Runtime", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 8)
        )
        ctk.CTkLabel(status, text="Scanning", text_color=("gray40", "gray70")).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 4)
        )
        self._scanning_var = ctk.StringVar(value="—")
        ctk.CTkLabel(status, textvariable=self._scanning_var).grid(row=1, column=1, sticky="w", padx=(0, 16), pady=(0, 4))
        ctk.CTkLabel(status, text="Active scan id", text_color=("gray40", "gray70")).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 4)
        )
        self._active_id_var = ctk.StringVar(value="—")
        ctk.CTkLabel(status, textvariable=self._active_id_var, anchor="w").grid(
            row=2, column=1, sticky="ew", padx=(0, 16), pady=(0, 4)
        )
        ctk.CTkLabel(status, text="History DB", text_color=("gray40", "gray70")).grid(
            row=3, column=0, sticky="w", padx=16, pady=(0, 12)
        )
        self._db_var = ctk.StringVar(value="—")
        ctk.CTkLabel(
            status,
            textvariable=self._db_var,
            text_color=("gray30", "gray80"),
            anchor="w",
            wraplength=640,
            justify="left",
        ).grid(row=3, column=1, sticky="ew", padx=(0, 16), pady=(0, 12))

        counts = ctk.CTkFrame(self, corner_radius=12)
        counts.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 12))
        counts.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(counts, text="Recorder (since last buffer clear)", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 6)
        )
        self._counts_var = ctk.StringVar(value="—")
        ctk.CTkLabel(counts, textvariable=self._counts_var, text_color=("gray40", "gray70"), anchor="w", justify="left").grid(
            row=1, column=0, sticky="ew", padx=16, pady=(0, 12)
        )

        log = ctk.CTkFrame(self, corner_radius=12)
        log.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        log.grid_columnconfigure(0, weight=1)
        log.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(log, text="Recent events", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 8)
        )
        self._log_box = ctk.CTkTextbox(log, wrap="word", font=ctk.CTkFont(size=12))
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self._log_box.configure(state="disabled")

    def attach_store(self, store: "UIStateStore") -> None:
        """Mirror engine event log lines from UIStateStore (hub-fed)."""
        self.detach_store()

        def on_state(state) -> None:
            sess = scan_session(state)
            if sess is not None and getattr(sess, "session_id", ""):
                sid = str(sess.session_id)
                self._active_id_var.set((sid[:16] + "…") if len(sid) > 16 else sid)
            ev = scan_events_log(state)
            if ev:
                self._log_box.configure(state="normal")
                self._log_box.delete("1.0", "end")
                self._log_box.insert("1.0", "\n".join(ev[-200:]))
                self._log_box.configure(state="disabled")

        self._unsub_store = store.subscribe(on_state, fire_immediately=False)

    def detach_store(self) -> None:
        if self._unsub_store:
            try:
                self._unsub_store()
            except Exception:
                pass
            self._unsub_store = None

    def _clear_recorder(self) -> None:
        if not messagebox.askyesno(
            "Clear diagnostics buffer",
            "Clear all in-memory recorder events and category counts?\n\n"
            "Scan history on disk is not affected. A new scan also clears this buffer.",
            parent=self.winfo_toplevel(),
        ):
            return
        get_diagnostics_recorder().clear()
        self.reload()

    def reload(self) -> None:
        scanning = self._coordinator.is_scanning
        self._scanning_var.set("Yes" if scanning else "No")
        aid = self._coordinator.get_active_scan_id()
        self._active_id_var.set((aid[:16] + "…") if aid and len(aid) > 16 else (aid or "—"))
        self._db_var.set(str(self._coordinator.persistence.db_path))

        rec = get_diagnostics_recorder()
        cts = rec.get_counts()
        if not cts:
            self._counts_var.set("No events recorded in this session buffer.")
        else:
            parts = [f"{k}: {v}" for k, v in sorted(cts.items())]
            self._counts_var.set("  ·  ".join(parts))

        lines: list[str] = []
        for e in rec.get_recent(100):
            detail = f"  |  {e.detail}" if e.detail else ""
            try:
                ts = datetime.fromtimestamp(e.wall_time).strftime("%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError, OSError):
                ts = "—"
            lines.append(f"{ts}  [{e.category}] {e.message}{detail}")

        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.insert("1.0", "\n".join(lines) if lines else "(empty — events appear when the engine logs warnings/errors here)")
        self._log_box.configure(state="disabled")
