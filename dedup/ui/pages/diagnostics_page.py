"""
Diagnostics Page — Deep engine transparency.

Layout:
  Row 0: Session overview strip
  Row 1: Tab bar  [Phases | Artifacts | Compatibility | Events | Integrity]
  Row 2: Active tab content
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from ..components import DataTable, SectionCard, EmptyState
from ..viewmodels.diagnostics_vm import DiagnosticsVM
from ..utils.formatting import fmt_int, fmt_duration, fmt_dt
from ..utils.icons import IC
from ...orchestration.coordinator import ScanCoordinator


class DiagnosticsPage(ttk.Frame):
    """Engine diagnostics page."""

    def __init__(self, parent, coordinator: ScanCoordinator, **kwargs):
        super().__init__(parent, **kwargs)
        self.coordinator = coordinator
        self.vm = DiagnosticsVM()
        self._hub = None
        self._unsubs: List[Callable] = []
        self._build()

    def attach_hub(self, hub) -> None:
        """Subscribe to live projection updates for session/phase/compat/events."""
        self._hub = hub
        self._unsubs.append(hub.subscribe("session", self._on_hub_session))
        self._unsubs.append(hub.subscribe("phase", self._on_hub_phases))
        self._unsubs.append(hub.subscribe("compatibility", self._on_hub_compat))
        self._unsubs.append(hub.subscribe("events_log", self._on_hub_events))

    def detach_hub(self) -> None:
        for unsub in self._unsubs:
            try:
                unsub()
            except Exception:
                pass
        self._unsubs.clear()

    def _on_hub_session(self, proj) -> None:
        self.vm.session = proj

    def _on_hub_phases(self, phases) -> None:
        self.vm.phases = phases

    def _on_hub_compat(self, proj) -> None:
        self.vm.compat = proj

    def _on_hub_events(self, entries) -> None:
        self.vm.events_log = entries

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # ── Page header ──────────────────────────────────────────────
        hdr = ttk.Frame(self, padding=(16, 12, 16, 0))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        ttk.Label(hdr, text=f"{IC.DIAGNOSTICS}  Diagnostics",
                  font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(hdr, text=f"{IC.REFRESH} Refresh",
                   style="Ghost.TButton",
                   command=self._refresh).grid(row=0, column=2, sticky="e")

        # ── Session overview ─────────────────────────────────────────
        ov_card = SectionCard(self, title=f"{IC.INFO}  Session Overview")
        ov_card.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        self._build_overview(ov_card.body)

        # ── Tab notebook ─────────────────────────────────────────────
        self._notebook = ttk.Notebook(self)
        self._notebook.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 12))

        self._tab_phases  = ttk.Frame(self._notebook)
        self._tab_arts    = ttk.Frame(self._notebook)
        self._tab_compat  = ttk.Frame(self._notebook)
        self._tab_events  = ttk.Frame(self._notebook)
        self._tab_integ   = ttk.Frame(self._notebook)

        self._notebook.add(self._tab_phases, text=f"  Phases  ")
        self._notebook.add(self._tab_arts,   text=f"  Artifacts  ")
        self._notebook.add(self._tab_compat, text=f"  Compatibility  ")
        self._notebook.add(self._tab_events, text=f"  Events  ")
        self._notebook.add(self._tab_integ,  text=f"  Integrity  ")

        self._build_phases_tab()
        self._build_artifacts_tab()
        self._build_compat_tab()
        self._build_events_tab()
        self._build_integrity_tab()

    def _build_overview(self, body: ttk.Frame):
        body.columnconfigure(1, weight=1)
        body.columnconfigure(3, weight=1)
        self._ov_vars: dict[str, tk.StringVar] = {}
        fields = [
            ("Session ID",       "—"),
            ("Config Hash",      "—"),
            ("Schema Version",   "—"),
            ("Root Fingerprint", "—"),
        ]
        for i, (label, default) in enumerate(fields):
            col = (i % 2) * 2
            row = i // 2
            ttk.Label(body, text=label + ":", style="Panel.Muted.TLabel",
                      font=("Segoe UI", 8)).grid(row=row, column=col, sticky="w",
                                                 padx=(0, 4), pady=2)
            var = tk.StringVar(value=default)
            ttk.Label(body, textvariable=var, style="Panel.TLabel",
                      font=("Segoe UI", 8, "bold")).grid(row=row, column=col + 1, sticky="w")
            self._ov_vars[label] = var

        # Session selector
        sel_frame = ttk.Frame(body, style="Panel.TFrame")
        sel_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Label(sel_frame, text="View session:", style="Panel.Muted.TLabel",
                  font=("Segoe UI", 8)).pack(side="left")
        self._session_var = tk.StringVar()
        self._session_combo = ttk.Combobox(
            sel_frame, textvariable=self._session_var, state="readonly", width=36)
        self._session_combo.pack(side="left", padx=(6, 0))
        self._session_combo.bind("<<ComboboxSelected>>", self._on_session_change)

    def _build_phases_tab(self):
        tab = self._tab_phases
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self._phases_table = DataTable(
            tab,
            columns=[
                ("phase",    "Phase",       100, "w"),
                ("status",   "Status",       70, "w"),
                ("finalized","Final",        50, "center"),
                ("rows",     "Rows",         70, "e"),
                ("duration", "Duration",     70, "e"),
                ("ckpt",     "Checkpoint",  140, "w"),
                ("resume",   "Resume",       90, "w"),
            ],
            height=14,
        )
        self._phases_table.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def _build_artifacts_tab(self):
        tab = self._tab_arts
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self._arts_table = DataTable(
            tab,
            columns=[
                ("table",  "Table",       180, "w"),
                ("count",  "Rows",         80, "e"),
                ("desc",   "Description", 280, "w"),
            ],
            height=14,
        )
        self._arts_table.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def _build_compat_tab(self):
        tab = self._tab_compat
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self._compat_table = DataTable(
            tab,
            columns=[
                ("phase",    "Phase",        100, "w"),
                ("schema",   "Schema",        60, "center"),
                ("config",   "Config",        60, "center"),
                ("pver",     "Phase Ver",     60, "center"),
                ("artifact", "Artifacts",     60, "center"),
                ("action",   "Resume Action", 120, "w"),
            ],
            height=14,
        )
        self._compat_table.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def _build_events_tab(self):
        tab = self._tab_events
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        # Filter toolbar
        fb = ttk.Frame(tab, style="Panel.TFrame", padding=(8, 4))
        fb.grid(row=0, column=0, sticky="ew")
        self._event_filter_var = tk.StringVar(value="All")
        ttk.Label(fb, text="Severity:", style="Panel.Muted.TLabel",
                  font=("Segoe UI", 8)).pack(side="left")
        ttk.Combobox(fb, textvariable=self._event_filter_var,
                     values=["All", "info", "warning", "error"],
                     state="readonly", width=10).pack(side="left", padx=(4, 0))
        self._events_table = DataTable(
            tab,
            columns=[
                ("ts",    "Time",    80, "w"),
                ("type",  "Type",    100, "w"),
                ("phase", "Phase",   80, "w"),
                ("sev",   "Severity",60, "w"),
                ("detail","Detail",  300, "w"),
            ],
            height=14,
        )
        self._events_table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

    def _build_integrity_tab(self):
        tab = self._tab_integ
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self._integ_table = DataTable(
            tab,
            columns=[
                ("check",  "Check",       200, "w"),
                ("status", "Status",       80, "w"),
                ("detail", "Detail",      320, "w"),
            ],
            height=14,
        )
        self._integ_table.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    # ----------------------------------------------------------------
    def on_show(self):
        self._refresh()

    def _refresh(self):
        # Populate session selector
        try:
            history = self.coordinator.get_history(limit=50) or []
        except Exception:
            history = []
        session_ids = [h.get("scan_id", "") for h in history if h.get("scan_id")]
        self._session_combo["values"] = session_ids
        if session_ids and not self._session_var.get():
            self._session_var.set(session_ids[0])

        session_id = self._session_var.get()
        self.vm.load(self.coordinator, session_id)
        self._update_overview(session_id)
        self._populate_phases()
        self._populate_artifacts()
        self._populate_compat()
        self._populate_events()
        self._populate_integrity()

    def _on_session_change(self, event=None):
        session_id = self._session_var.get()
        self.vm.load(self.coordinator, session_id)
        self._update_overview(session_id)
        self._populate_phases()
        self._populate_artifacts()
        self._populate_compat()

    def _update_overview(self, session_id: str):
        self._ov_vars["Session ID"].set(
            (session_id[:24] + "…") if len(session_id) > 24 else (session_id or "—"))
        self._ov_vars["Config Hash"].set(
            (self.vm.config_hash[:16] + "…") if len(self.vm.config_hash) > 16
            else (self.vm.config_hash or "—"))
        self._ov_vars["Schema Version"].set(
            str(self.vm.schema_version) if self.vm.schema_version else "—")
        self._ov_vars["Root Fingerprint"].set(
            (self.vm.root_fingerprint[:20] + "…") if len(self.vm.root_fingerprint) > 20
            else (self.vm.root_fingerprint or "—"))

    def _populate_phases(self):
        self._phases_table.clear()
        for r in self.vm.phases_table:
            fin = IC.OK if r.finalized else IC.PENDING
            tag = ("safe" if r.resume_action == "safe_resume" else
                   "warn" if r.resume_action == "rebuild_phase" else "danger")
            cts = (r.checkpoint_ts[:19]) if r.checkpoint_ts else ""
            self._phases_table.insert_row(
                r.phase,
                (r.phase, r.integrity, fin, fmt_int(r.rows),
                 fmt_duration(r.duration_s), cts, r.resume_action),
                tags=(tag,),
            )

    def _populate_artifacts(self):
        self._arts_table.clear()
        for r in self.vm.artifacts:
            count_val = getattr(r, "row_count", getattr(r, "count", 0))
            count_str = fmt_int(count_val) if count_val >= 0 else "N/A"
            tag = "warn" if count_val == 0 else ""
            table_name = getattr(r, "table_name", getattr(r, "table", ""))
            desc = getattr(r, "description", getattr(r, "status", ""))
            self._arts_table.insert_row(
                table_name,
                (table_name, count_str, desc),
                tags=(tag,) if tag else (),
            )

    def _populate_compat(self):
        self._compat_table.clear()
        for r in self.vm.compatibility:
            ok = IC.OK
            no = IC.WARN
            tag = ("safe"   if r.resume_action == "safe_resume"    else
                   "warn"   if r.resume_action == "rebuild_phase"  else "danger")
            self._compat_table.insert_row(
                r.phase,
                (r.phase,
                 ok if r.schema_match      else no,
                 ok if r.config_match      else no,
                 ok if r.phase_version_match else no,
                 ok if r.artifact_complete  else no,
                 r.resume_action),
                tags=(tag,),
            )

    def _populate_events(self):
        self._events_table.clear()
        filt = self._event_filter_var.get()
        for ev in self.vm.events[:200]:
            if filt != "All" and getattr(ev, "severity", "info") != filt:
                continue
            sev = getattr(ev, "severity", "info")
            tag = ("warn" if sev == "warning" else "danger" if sev == "error" else "")
            detail = getattr(ev, "detail", "")[:80]
            self._events_table.insert_row(
                str(id(ev)),
                (getattr(ev, "ts", ""), getattr(ev, "event_type", ""),
                 getattr(ev, "phase", ""), sev, detail),
                tags=(tag,) if tag else (),
            )

    def _populate_integrity(self):
        self._integ_table.clear()
        checks = [
            ("Schema version",     "OK", "Migrations applied"),
            ("Session table",      "OK", "scan_sessions accessible"),
            ("Inventory table",    "OK", "inventory_files accessible"),
            ("Phase checkpoints",  "OK", "phase_checkpoints accessible"),
        ]
        try:
            p = self.coordinator.persistence
            if p:
                conn = getattr(p, "conn", None) or (getattr(p, "_get_connection", lambda: None)() if callable(getattr(p, "_get_connection", None)) else None)
                if conn:
                    for table in ("scan_sessions", "inventory_files",
                                  "phase_checkpoints", "full_hashes", "scan_history"):
                        try:
                            conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
                            status = "OK"
                            detail = f"{table} accessible"
                        except Exception as e:
                            status = "ERROR"
                            detail = str(e)[:60]
                        tag = "" if status == "OK" else "danger"
                        self._integ_table.insert_row(
                            table, (table, status, detail), tags=(tag,) if tag else ())
                    return
        except Exception:
            pass
        for check, status, detail in checks:
            self._integ_table.insert_row(check, (check, status, detail))
