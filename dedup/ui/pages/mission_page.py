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
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state.store import UIStateStore

from ..components import MetricCard, SectionCard, EmptyState, Badge
from ..viewmodels.mission_vm import MissionVM
from ..utils.formatting import fmt_bytes, fmt_int, fmt_duration, fmt_dt
from ..utils.icons import IC
from ..theme.design_system import font_tuple, SPACING

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
                 on_request_refresh: Optional[Callable[[], None]] = None,
                 on_open_last_review: Optional[Callable[[], None]] = None,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.on_start_scan = on_start_scan
        self.on_resume_scan = on_resume_scan
        self.coordinator = coordinator
        self._on_request_refresh = on_request_refresh
        self._on_open_last_review = on_open_last_review or (lambda: None)
        self.vm = MissionVM()
        self._selected_path: Optional[Path] = None
        self._store_unsub: Optional[Callable[[], None]] = None
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(4, weight=1)
        pad = SPACING["page"]

        # ── Mission Control: page title and subtitle ──────────────────
        hdr = ttk.Frame(self, padding=(pad, pad, pad, SPACING["md"]))
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(hdr, text=f"{IC.MISSION}  Mission Control",
                  font=font_tuple("page_title")).pack(side="left")
        ttk.Label(hdr, text="Readiness · Launch · Recent sessions",
                  style="Muted.TLabel",
                  font=font_tuple("page_subtitle")).pack(side="left", padx=(SPACING["lg"], 0), pady=3)

        # ── Hero: Start New Scan, Resume, Open Last Review ────────────
        hero = ttk.Frame(self, padding=(pad, 0, pad, SPACING["lg"]))
        hero.grid(row=1, column=0, columnspan=2, sticky="ew")
        hero.columnconfigure(0, weight=1)
        self._welcome_var = tk.StringVar(value="")
        self._welcome_lbl = ttk.Label(
            hero,
            textvariable=self._welcome_var,
            style="Muted.TLabel",
            font=font_tuple("body"),
        )
        self._welcome_lbl.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, SPACING["sm"]))
        ttk.Button(hero, text=f"{IC.SCAN}  Start New Scan",
                   style="Accent.TButton",
                   command=self._on_start).grid(row=1, column=0, sticky="w", padx=(0, SPACING["sm"]))
        ttk.Button(hero, text=f"{IC.RESUME}  Resume",
                   style="Ghost.TButton",
                   command=self._on_resume).grid(row=1, column=1, sticky="w", padx=SPACING["sm"])
        self._open_review_btn = ttk.Button(hero, text=f"{IC.REVIEW}  Open Last Review",
                                           style="Ghost.TButton",
                                           command=self._on_open_last_review)
        self._open_review_btn.grid(row=1, column=2, sticky="w")
        self._tour_btn = ttk.Button(hero, text="Watch Tour",
                                    style="Ghost.TButton",
                                    command=self._show_quick_tour)
        self._tour_btn.grid(row=2, column=0, sticky="w", pady=(SPACING["sm"], 0))

        # ── Readiness row: Engine Status + Last Scan ───────────────────
        self._engine_card = SectionCard(self, title=f"{IC.SHIELD}  Engine Status")
        self._engine_card.grid(row=2, column=0, sticky="nsew", padx=(pad, SPACING["md"]), pady=SPACING["md"])
        self._build_engine_card()

        self._last_scan_card = SectionCard(self, title=f"{IC.HISTORY}  Last Scan")
        self._last_scan_card.grid(row=2, column=1, sticky="nsew", padx=(SPACING["md"], pad), pady=SPACING["md"])
        self._build_last_scan_card()

        # ── Quick Start + Capabilities ────────────────────────────────
        qs_card = SectionCard(self, title=f"{IC.SCAN}  Quick Start")
        qs_card.grid(row=3, column=0, sticky="nsew", padx=(pad, SPACING["md"]), pady=SPACING["md"])
        self._build_quick_start(qs_card.body)

        cap_card = SectionCard(self, title=f"{IC.INFO}  Capabilities")
        cap_card.grid(row=3, column=1, sticky="nsew", padx=(SPACING["md"], pad), pady=SPACING["md"])
        self._cap_body = cap_card.body
        self._build_capabilities(cap_card.body)

        # ── Recent Sessions (full width, scannable) ──────────────────
        recent_card = SectionCard(self, title=f"{IC.HISTORY}  Recent Sessions")
        recent_card.grid(row=4, column=0, columnspan=2, sticky="nsew",
                         padx=pad, pady=(0, pad))
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
                      font=font_tuple("data_label")).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=default)
            ttk.Label(b, textvariable=var, style="Panel.TLabel",
                      font=font_tuple("data_value")).grid(row=i, column=1, sticky="w", padx=(SPACING["md"], 0))
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
                       padding=(0, SPACING["lg"]), font=font_tuple("body"))
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
                  font=font_tuple("data_label")).grid(row=1, column=0, sticky="w", pady=(SPACING["md"], 0))
        ttk.Combobox(opts, textvariable=self._media_var, state="readonly",
                     values=[get_category_label(c) for c in cats],
                     width=12).grid(row=1, column=1, sticky="w",
                                    pady=(SPACING["md"], 0), padx=(SPACING["sm"], 0))

        # Recent folders chips
        self._recent_frame = ttk.Frame(body, style="Panel.TFrame")
        self._recent_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        # Action buttons (Start Scan uses selected path; Resume from hero or here)
        btn_f = ttk.Frame(body, style="Panel.TFrame")
        btn_f.grid(row=4, column=0, sticky="ew", pady=(SPACING["lg"], 0))
        btn_f.columnconfigure(0, weight=1)
        btn_f.columnconfigure(1, weight=1)
        ttk.Button(btn_f, text=f"{IC.SCAN}  Start Scan",
                   style="Accent.TButton",
                   command=self._on_start).grid(row=0, column=0, sticky="ew", padx=(0, SPACING["sm"]))
        self._resume_btn = ttk.Button(btn_f, text=f"{IC.RESUME}  Resume",
                                      style="Ghost.TButton",
                                      command=self._on_resume,
                                      state="disabled")
        self._resume_btn.grid(row=0, column=1, sticky="ew", padx=(SPACING["sm"], 0))

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
                      font=font_tuple("data_value"), width=3).pack(side="left")
            ttk.Label(row, text=label, style="Panel.TLabel",
                      font=font_tuple("data_label")).pack(side="left", padx=(SPACING["sm"], 0))
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
    # Store subscription (Step 8: migrate to store)
    # ----------------------------------------------------------------
    def attach_store(self, store: "UIStateStore") -> None:
        """Subscribe to UIStateStore; render from store.mission when present."""
        if self._store_unsub:
            self._store_unsub()
        def on_state(state):
            mission = getattr(state, "mission", None)
            if mission is not None:
                self.vm.refresh_from_mission_state(state)
                self._update_engine_card()
                self._update_last_scan()
                self._update_capabilities()
                self._update_recent_sessions()
                self._update_recent_folders()
                has_resumable = bool(self.vm.resumable_scan_ids)
                self._resume_btn.configure(state="normal" if has_resumable else "disabled")
        self._store_unsub = store.subscribe(on_state, fire_immediately=False)

    def detach_store(self) -> None:
        if self._store_unsub:
            self._store_unsub()
            self._store_unsub = None

    # ----------------------------------------------------------------
    # Logic
    # ----------------------------------------------------------------
    def on_show(self):
        if self._on_request_refresh:
            self._on_request_refresh()
        else:
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
        resumable = set(getattr(self.vm, "resumable_scan_ids", None) or self.coordinator.get_resumable_scan_ids() or [])
        if not self.vm.recent_sessions:
            self._welcome_var.set(
                "Welcome to CEREBRO\nYour first scan takes 2 minutes. No data leaves your device."
            )
            self._tour_btn.grid()
            return
        self._tour_btn.grid_remove()
        self._welcome_var.set("")
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
        return

    def _show_quick_tour(self) -> None:
        messagebox.showinfo(
            "CEREBRO Quick Tour",
            "Scan -> Review -> Cleanup\n\n"
            "1) Start Scan to discover duplicates.\n"
            "2) Use Decision Studio to choose keep/delete safely.\n"
            "3) Execute cleanup with preview and audit protections."
        )

    def _update_recent_folders(self):
        for w in self._recent_frame.winfo_children():
            w.destroy()
        if self.vm.recent_folders:
            ttk.Label(self._recent_frame, text="Recent:", style="Panel.Muted.TLabel",
                      font=font_tuple("data_label")).pack(side="left")
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
