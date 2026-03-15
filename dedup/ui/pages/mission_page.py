"""
Mission Page — Readiness dashboard, launch point, recent sessions.

Layout (2-column grid):
  Row 0: Engine Status Card  |  Last Scan Card
  Row 1: Quick Start         |  Capabilities
  Row 2: Recent Sessions (full-width)
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Callable, Optional

from ..components import MetricCard, SectionCard, EmptyState, Badge
from ..viewmodels.mission_vm import MissionVM
from ..utils.formatting import fmt_bytes, fmt_int, fmt_duration, fmt_dt
from ..utils.icons import IC

try:
    from ...engine.media_types import list_categories, get_category_label
except Exception:
    def list_categories(): return ["all"]
    def get_category_label(c): return c.title()

try:
    from tkinterdnd2 import DND_FILES  # type: ignore
except Exception:
    DND_FILES = None


class MissionPage(ttk.Frame):
    """Mission / home page."""

    def __init__(self, parent,
                 on_start_scan: Callable[[Path, dict], None],
                 on_resume_scan: Callable[[str], None],
                 coordinator,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.on_start_scan = on_start_scan
        self.on_resume_scan = on_resume_scan
        self.coordinator = coordinator
        self.vm = MissionVM()
        self._selected_path: Optional[Path] = None
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        # ── Page header ──────────────────────────────────────────────
        hdr = ttk.Frame(self, padding=(20, 16, 20, 0))
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(hdr, text=f"{IC.MISSION}  Mission",
                  font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(hdr, text="Readiness · Launch · History",
                  style="Muted.TLabel",
                  font=("Segoe UI", 9)).pack(side="left", padx=(12, 0), pady=3)

        # ── Row 1: Engine Status + Last Scan cards ───────────────────
        self._engine_card = SectionCard(self, title=f"{IC.SHIELD}  Engine Status")
        self._engine_card.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=8)
        self._build_engine_card()

        self._last_scan_card = SectionCard(self, title=f"{IC.HISTORY}  Last Scan")
        self._last_scan_card.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=8)
        self._build_last_scan_card()

        # ── Row 2: Quick Start + Capabilities ───────────────────────
        qs_card = SectionCard(self, title=f"{IC.SCAN}  Quick Start")
        qs_card.grid(row=2, column=0, sticky="nsew", padx=(16, 8), pady=8)
        self._build_quick_start(qs_card.body)

        cap_card = SectionCard(self, title=f"{IC.INFO}  Capabilities")
        cap_card.grid(row=2, column=1, sticky="nsew", padx=(8, 16), pady=8)
        self._cap_body = cap_card.body
        self._build_capabilities(cap_card.body)

        # ── Row 3: Recent Sessions ───────────────────────────────────
        recent_card = SectionCard(self, title=f"{IC.HISTORY}  Recent Sessions")
        recent_card.grid(row=3, column=0, columnspan=2, sticky="nsew",
                         padx=16, pady=(0, 16))
        self._build_recent_sessions(recent_card.body)

    # ----------------------------------------------------------------
    def _build_engine_card(self):
        b = self._engine_card.body
        b.columnconfigure(1, weight=1)
        self._eng_rows: dict[str, tk.StringVar] = {}
        fields = [
            ("Pipeline",          "Durable"),
            ("Hash backend",      "—"),
            ("Trash protection",  "ON"),
            ("Resume available",  "—"),
            ("Schema version",    "—"),
        ]
        for i, (label, default) in enumerate(fields):
            ttk.Label(b, text=label + ":", style="Panel.Muted.TLabel",
                      font=("Segoe UI", 8)).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=default)
            ttk.Label(b, textvariable=var, style="Panel.TLabel",
                      font=("Segoe UI", 8, "bold")).grid(row=i, column=1, sticky="w", padx=(8, 0))
            self._eng_rows[label] = var

    def _build_last_scan_card(self):
        b = self._last_scan_card.body
        b.columnconfigure(0, weight=1)
        b.columnconfigure(1, weight=1)
        self._last_metrics: dict[str, MetricCard] = {}
        specs = [
            ("files",   f"{IC.FILE}  Files Scanned",     "—", "neutral"),
            ("groups",  f"{IC.GROUPS} Groups",            "—", "neutral"),
            ("reclaim", f"{IC.RECLAIM} Reclaimable",      "—", "positive"),
            ("dur",     f"{IC.SPEED}  Duration",          "—", "neutral"),
        ]
        for i, (key, label, val, variant) in enumerate(specs):
            c = MetricCard(b, label=label, value=val, variant=variant, width=0)
            c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=4, pady=4)
            self._last_metrics[key] = c

    def _build_quick_start(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)

        # Folder selection drop zone
        dz = ttk.Label(body,
                       text="  Click or drop folder here  ",
                       relief="groove", anchor="center", cursor="hand2",
                       padding=(0, 12), font=("Segoe UI", 9))
        dz.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        dz.bind("<Button-1>", lambda e: self._on_browse())
        self._drop_label = dz
        self._enable_drag_drop(dz)

        # Path entry
        pf = ttk.Frame(body, style="Panel.TFrame")
        pf.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        pf.columnconfigure(0, weight=1)
        self._path_var = tk.StringVar()
        ttk.Entry(pf, textvariable=self._path_var).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(pf, text="Browse…", style="Ghost.TButton",
                   command=self._on_browse).grid(row=0, column=1)

        # Options (compact)
        opts = ttk.Frame(body, style="Panel.TFrame")
        opts.grid(row=2, column=0, sticky="ew")
        self._recurse_var  = tk.BooleanVar(value=True)
        self._hidden_var   = tk.BooleanVar(value=False)
        self._min_size_var = tk.IntVar(value=1024)
        ttk.Checkbutton(opts, text="Subfolders",
                        variable=self._recurse_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(opts, text="Hidden files",
                        variable=self._hidden_var).grid(row=0, column=1, sticky="w", padx=(10, 0))

        # Media filter
        cats = list_categories()
        self._media_var = tk.StringVar(value=get_category_label(cats[0]))
        self._media_map = {get_category_label(c): c for c in cats}
        ttk.Label(opts, text="Type:", style="Panel.Muted.TLabel",
                  font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(opts, textvariable=self._media_var, state="readonly",
                     values=[get_category_label(c) for c in cats],
                     width=12).grid(row=1, column=1, sticky="w",
                                    pady=(6, 0), padx=(4, 0))

        # Recent folders chips
        self._recent_frame = ttk.Frame(body, style="Panel.TFrame")
        self._recent_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        # Action buttons
        btn_f = ttk.Frame(body, style="Panel.TFrame")
        btn_f.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        btn_f.columnconfigure(0, weight=1)
        btn_f.columnconfigure(1, weight=1)
        ttk.Button(btn_f, text=f"{IC.SCAN}  Start Scan",
                   style="Accent.TButton",
                   command=self._on_start).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._resume_btn = ttk.Button(btn_f, text=f"{IC.RESUME}  Resume",
                                      style="Ghost.TButton",
                                      command=self._on_resume,
                                      state="disabled")
        self._resume_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _build_capabilities(self, body: ttk.Frame):
        self._cap_vars: dict[str, tk.StringVar] = {}
        caps = [
            ("xxhash",    "xxhash64 backend"),
            ("blake3",    "blake3 backend"),
            ("pillow",    "Thumbnail preview"),
            ("send2trash","Trash protection"),
            ("durable",   "Durable pipeline"),
            ("revalidation","Pre-delete revalidation"),
            ("audit",     "Audit logging"),
        ]
        for i, (key, label) in enumerate(caps):
            row = ttk.Frame(body, style="Panel.TFrame")
            row.grid(row=i, column=0, sticky="ew", pady=2)
            var = tk.StringVar(value="—")
            ttk.Label(row, textvariable=var,
                      style="Panel.Success.TLabel",
                      font=("Segoe UI", 8, "bold"), width=3).pack(side="left")
            ttk.Label(row, text=label, style="Panel.TLabel",
                      font=("Segoe UI", 8)).pack(side="left", padx=(4, 0))
            self._cap_vars[key] = var

    def _build_recent_sessions(self, body: ttk.Frame):
        from ..components import DataTable
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self._recent_table = DataTable(
            body,
            columns=[
                ("date",       "Date",        140, "w"),
                ("roots",      "Roots",       200, "w"),
                ("files",      "Files",        80, "e"),
                ("groups",     "Groups",       70, "e"),
                ("reclaim",    "Reclaimable",  90, "e"),
                ("status",     "Status",       80, "w"),
            ],
            height=5,
            on_select=self._on_session_select,
            on_double_click=self._on_session_double_click,
        )
        self._recent_table.grid(row=0, column=0, sticky="nsew")

    # ----------------------------------------------------------------
    # Logic
    # ----------------------------------------------------------------
    def on_show(self):
        self._refresh()

    def _refresh(self):
        self.vm.refresh_from_coordinator(self.coordinator)
        self._update_engine_card()
        self._update_last_scan()
        self._update_capabilities()
        self._update_recent_sessions()
        self._update_recent_folders()
        # Enable resume if any resumable
        has_resumable = bool(self.vm.recent_sessions and
                             any(s.get("scan_id") in
                                 set(self.coordinator.get_resumable_scan_ids() or [])
                                 for s in self.vm.recent_sessions))
        self._resume_btn.configure(state="normal" if has_resumable else "disabled")

    def _update_engine_card(self):
        e = self.vm.engine_status
        caps = self.vm.capabilities
        self._eng_rows["Hash backend"].set(e.hash_backend)
        self._eng_rows["Resume available"].set(
            f"{IC.OK} Yes" if e.resume_available else f"{IC.ERROR} No")
        self._eng_rows["Schema version"].set(str(e.schema_version))

    def _update_last_scan(self):
        ls = self.vm.last_scan
        if ls:
            self._last_metrics["files"].update(fmt_int(ls.files_scanned))
            self._last_metrics["groups"].update(fmt_int(ls.duplicate_groups))
            self._last_metrics["reclaim"].update(fmt_bytes(ls.reclaimable_bytes))
            self._last_metrics["dur"].update(fmt_duration(ls.duration_s))

    def _update_capabilities(self):
        caps = self.vm.capabilities_by_name()
        for key, var in self._cap_vars.items():
            if key in ("durable", "revalidation", "audit"):
                var.set(IC.OK)
            elif key in caps:
                var.set(IC.OK if caps[key] else IC.WARN)
            else:
                var.set("—")

    def _update_recent_sessions(self):
        self._recent_table.clear()
        resumable = set(self.coordinator.get_resumable_scan_ids() or [])
        for item in self.vm.recent_sessions[:8]:
            scan_id = item.get("scan_id", "")
            started = fmt_dt(item.get("started_at", ""))
            roots = item.get("roots") or []
            roots_str = ", ".join(Path(r).name for r in roots[:2])
            if len(roots) > 2:
                roots_str += "…"
            files = fmt_int(item.get("files_scanned", 0))
            groups = fmt_int(item.get("duplicates_found", 0))
            reclaim = fmt_bytes(item.get("reclaimable_bytes", 0))
            status = item.get("status", "—")
            if scan_id in resumable:
                status = "resumable"
            tag = "safe" if status == "completed" else (
                "warn" if status in ("interrupted", "resumable") else
                "danger" if status == "failed" else "")
            self._recent_table.insert_row(scan_id, (started, roots_str, files, groups, reclaim, status),
                                          tags=(tag,) if tag else ())

    def _update_recent_folders(self):
        for w in self._recent_frame.winfo_children():
            w.destroy()
        if self.vm.recent_folders:
            ttk.Label(self._recent_frame, text="Recent:", style="Panel.Muted.TLabel",
                      font=("Segoe UI", 8)).pack(side="left")
            for folder in self.vm.recent_folders[:4]:
                name = Path(folder).name or folder
                btn = ttk.Button(self._recent_frame, text=name,
                                 style="Ghost.TButton",
                                 command=lambda f=folder: self._set_path(f))
                btn.pack(side="left", padx=(4, 0))

    def _on_session_select(self, iid: str):
        pass

    def _on_session_double_click(self, iid: str):
        self.on_resume_scan(iid)

    def _on_browse(self):
        path = filedialog.askdirectory(title="Select Folder to Scan")
        if path:
            self._set_path(path)

    def _set_path(self, path: str):
        resolved = str(Path(path).resolve())
        self._path_var.set(resolved)
        self._selected_path = Path(resolved)

    def _enable_drag_drop(self, widget):
        if DND_FILES is None:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            widget.configure(text="  Drop folder here or click to browse  ")
        except Exception:
            pass

    def _on_drop(self, event):
        data = (event.data or "").strip()
        if not data:
            return
        try:
            paths = self.tk.splitlist(data)
        except Exception:
            paths = [data]
        for p in paths:
            candidate = p.strip("{}").strip()
            if candidate:
                path_obj = Path(candidate)
                if path_obj.exists() and path_obj.is_dir():
                    self._set_path(str(path_obj))
                    break

    def _on_start(self):
        path_str = self._path_var.get().strip()
        if not path_str:
            messagebox.showerror("Error", "Please select a folder to scan.")
            return
        path = Path(path_str).resolve()
        if not path.exists() or not path.is_dir():
            messagebox.showerror("Error", f"Invalid path: {path}")
            return
        label = self._media_var.get()
        media_key = self._media_map.get(label, "all")
        options = {
            "min_size": self._min_size_var.get(),
            "include_hidden": self._hidden_var.get(),
            "scan_subfolders": self._recurse_var.get(),
            "media_category": media_key,
        }
        try:
            self.coordinator.add_recent_folder(path)
        except Exception:
            pass
        self.on_start_scan(path, options)

    def _on_resume(self):
        try:
            resumable = self.coordinator.get_resumable_scan_ids() or []
        except Exception:
            resumable = []
        if not resumable:
            messagebox.showinfo("Resume", "No resumable scan found.")
            return
        self.on_resume_scan(resumable[0])
