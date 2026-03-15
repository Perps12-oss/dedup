"""
Review Page — 3-pane duplicate review and deletion workflow.

Layout:
  Top: Provenance Ribbon
  Body:
    Left (3):  Group Navigator (list + filters)
    Center(6): Review Workspace (Table | Gallery | Compare)
    Right (3): Plan Drawer (Safety Panel)
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Optional, List

from ..components import (
    DataTable, SectionCard, SafetyPanel, ProvenanceRibbon,
    EmptyState, FilterBar, StatusRibbon,
)
from ..viewmodels.review_vm import ReviewVM, GroupEntry
from ..utils.formatting import fmt_bytes, fmt_int, truncate_path
from ..utils.icons import IC
from ...orchestration.coordinator import ScanCoordinator
from ...engine.models import ScanResult, DuplicateGroup, DeletionPlan, DeletionResult
from ...engine.thumbnails import generate_thumbnails_async, get_cache_dir
from ...engine.media_types import is_image_extension
from ...infrastructure.utils import format_bytes

_THUMB_SIZE = (64, 64)


class ReviewPage(ttk.Frame):
    """Review & deletion planning page."""

    def __init__(self, parent,
                 coordinator: ScanCoordinator,
                 on_delete_complete: Callable[[DeletionResult], None],
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.coordinator = coordinator
        self.on_delete_complete = on_delete_complete
        self.vm = ReviewVM()
        self._current_result: Optional[ScanResult] = None
        self._thumbnail_refs: list = []
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # ── Page header ──────────────────────────────────────────────
        hdr = ttk.Frame(self, padding=(16, 12, 16, 0))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        ttk.Label(hdr, text=f"{IC.REVIEW}  Review",
                  font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")

        # View mode toggle
        mode_frame = ttk.Frame(hdr, style="Panel.TFrame")
        mode_frame.grid(row=0, column=2, sticky="e")
        self._mode_var = tk.StringVar(value="table")
        for label, val in [("Table", "table"), ("Gallery", "gallery"), ("Compare", "compare")]:
            ttk.Radiobutton(mode_frame, text=label, variable=self._mode_var,
                            value=val, command=self._on_mode_change).pack(side="left", padx=2)

        # ── Provenance ribbon ─────────────────────────────────────────
        self._prov = ProvenanceRibbon(self)
        self._prov.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        # ── 3-pane body ───────────────────────────────────────────────
        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 12))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, minsize=200)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, minsize=200)

        # Left: Group Navigator
        left = SectionCard(body, title=f"{IC.GROUPS}  Groups")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._build_group_navigator(left.body)

        # Center: Review Workspace
        center = SectionCard(body, title=f"{IC.REVIEW}  Workspace")
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 6))
        self._build_workspace(center.body)

        # Right: Plan Drawer
        right_frame = ttk.Frame(body)
        right_frame.grid(row=0, column=2, sticky="nsew")
        right_frame.rowconfigure(0, weight=1)
        right_frame.columnconfigure(0, weight=1)
        self._safety_panel = SafetyPanel(
            right_frame,
            on_dry_run=self._on_dry_run,
            on_execute=self._on_execute,
        )
        self._safety_panel.grid(row=0, column=0, sticky="nsew")

    def _build_group_navigator(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        # Filter bar
        self._filter_bar = FilterBar(
            body,
            on_search=self._on_search,
            filters=[("Filter", ["All", "Reviewed", "Unreviewed"])],
            style="Panel.TFrame",
        )
        self._filter_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self._group_table = DataTable(
            body,
            columns=[
                ("idx",      "#",      32, "center"),
                ("files",    "Files",  40, "center"),
                ("size",     "Size",   70, "e"),
                ("conf",     "Conf",   40, "center"),
            ],
            height=16,
            on_select=self._on_group_select,
        )
        self._group_table.grid(row=1, column=0, sticky="nsew")

    def _build_workspace(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        # Thumbnail strip
        self._thumb_frame = ttk.Frame(body, style="Panel.TFrame")
        self._thumb_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        # Table mode (default)
        self._file_table = DataTable(
            body,
            columns=[
                ("action",  "Action",   60, "center"),
                ("name",    "Name",    160, "w"),
                ("path",    "Path",    200, "w"),
                ("size",    "Size",     70, "e"),
                ("mtime",   "Modified",100, "w"),
                ("type",    "Type",     60, "w"),
                ("status",  "Status",   60, "w"),
            ],
            height=12,
            on_select=self._on_file_select,
            on_double_click=self._on_file_double_click,
        )
        self._file_table.grid(row=1, column=0, sticky="nsew")

        # Action row under table
        act = ttk.Frame(body, style="Panel.TFrame")
        act.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self._keep_btn = ttk.Button(act, text=f"{IC.KEEP}  Keep this",
                                    style="Ghost.TButton",
                                    command=self._on_keep_this)
        self._keep_btn.pack(side="left", padx=(0, 6))

        self._empty_ws = EmptyState(body, icon=IC.REVIEW,
                                    heading="No group selected",
                                    message="Choose a duplicate group from the left panel.")
        self._empty_ws.grid(row=1, column=0, sticky="nsew")
        self._empty_ws.hide()

    # ----------------------------------------------------------------
    # Public
    # ----------------------------------------------------------------
    def load_result(self, result: ScanResult):
        self._current_result = result
        self.vm.load_from_result(result)
        self._prov.update(
            session_id=self.vm.session_id,
            verification=self.vm.verification_level,
            groups=self.vm.total_groups,
            reclaimable_bytes=self.vm.reclaimable_bytes,
        )
        self._refresh_group_list()
        self._safety_panel.update_plan(
            del_count=self.vm.delete_count,
            keep_count=self.vm.keep_count,
            reclaim_bytes=self.vm.reclaimable_bytes,
        )

    def on_show(self):
        pass

    # ----------------------------------------------------------------
    # Group list
    # ----------------------------------------------------------------
    def _refresh_group_list(self):
        self._group_table.clear()
        for i, ge in enumerate(self.vm.filtered_groups()):
            tag = "warn" if ge.has_risk else ""
            self._group_table.insert_row(
                ge.group_id,
                (str(i + 1), str(ge.file_count), fmt_bytes(ge.reclaimable_bytes), ge.confidence),
                tags=(tag,) if tag else (),
            )

    def _on_search(self, text: str):
        self.vm.search_text = text
        self._refresh_group_list()

    def _on_group_select(self, group_id: str):
        self.vm.selected_group_id = group_id
        self._load_workspace(group_id)

    def _load_workspace(self, group_id: str):
        if not self._current_result:
            return
        group = next((g for g in self._current_result.duplicate_groups
                      if g.group_id == group_id), None)
        if not group:
            return

        # Thumbnails
        self._thumbnail_refs.clear()
        for w in self._thumb_frame.winfo_children():
            w.destroy()
        image_paths = [f.path for f in group.files
                       if is_image_extension(Path(f.path).suffix.lower().lstrip("."))]
        if image_paths and self.vm.show_thumbnails:
            def on_thumb(fpath: str, thumb_path):
                def update():
                    if thumb_path and thumb_path.exists():
                        try:
                            from tkinter import PhotoImage
                            img = PhotoImage(file=str(thumb_path))
                            self._thumbnail_refs.append(img)
                            container = ttk.Frame(self._thumb_frame, style="Panel.TFrame",
                                                  padding=2)
                            container.pack(side="left", padx=2)
                            lbl = ttk.Label(container, image=img, style="Panel.TLabel")
                            lbl.image = img
                            lbl.pack()
                        except Exception:
                            pass
                self.after(0, update)
            generate_thumbnails_async(image_paths, on_thumb,
                                      size=_THUMB_SIZE, cache_dir=get_cache_dir(),
                                      max_count=6)

        # File table
        self._file_table.clear()
        keep_path = self.vm.keep_selections.get(group_id, "")
        for f in group.files:
            is_keep = (f.path == keep_path)
            action = f"{IC.KEEP} KEEP" if is_keep else f"{IC.DELETE_TGT} DEL"
            tag = "safe" if is_keep else "warn"
            self._file_table.insert_row(
                f.path,
                (action, f.filename, truncate_path(f.path, 40),
                 fmt_bytes(f.size), "—", Path(f.path).suffix or "—", "OK"),
                tags=(tag,),
            )
        self._empty_ws.hide()
        self._file_table.grid()

    # ----------------------------------------------------------------
    # File actions
    # ----------------------------------------------------------------
    def _on_file_select(self, file_path: str):
        pass

    def _on_file_double_click(self, file_path: str):
        pass

    def _on_keep_this(self):
        gid = self.vm.selected_group_id
        if not gid:
            return
        sel = self._file_table.selection()
        if not sel:
            return
        self.vm.set_keep(gid, sel)
        self._load_workspace(gid)
        self._safety_panel.update_plan(
            del_count=self.vm.delete_count,
            keep_count=self.vm.keep_count,
            reclaim_bytes=self.vm.reclaimable_bytes,
        )

    def _on_mode_change(self):
        self.vm.view_mode = self._mode_var.get()

    # ----------------------------------------------------------------
    # Deletion
    # ----------------------------------------------------------------
    def _create_plan(self) -> Optional[DeletionPlan]:
        if not self._current_result:
            return None
        return self.coordinator.create_deletion_plan(
            self._current_result,
            keep_strategy="first",
            group_keep_paths=self.vm.keep_selections or None,
        )

    def _on_dry_run(self):
        plan = self._create_plan()
        if not plan or not plan.groups:
            self._safety_panel.set_dry_run_result("No files selected.")
            return
        try:
            from ...engine.deletion import preview_deletion
            prev = preview_deletion(plan)
            self._safety_panel.set_dry_run_result(
                f"Dry run: {prev['total_files']} files → {prev['human_readable_size']}")
        except Exception as e:
            self._safety_panel.set_dry_run_result(f"Error: {e}")

    def _on_execute(self):
        plan = self._create_plan()
        if not plan or not plan.groups:
            messagebox.showinfo("Execute Plan", "No files selected for deletion.")
            return
        try:
            from ...engine.deletion import preview_deletion
            prev = preview_deletion(plan)
        except Exception:
            prev = {"total_files": "?", "human_readable_size": "?"}

        if not messagebox.askyesno(
            "Confirm Deletion",
            f"Delete {prev.get('total_files', '?')} duplicate files?\n"
            f"Space reclaimed: {prev.get('human_readable_size', '?')}\n\n"
            f"Files will be moved to Trash.\n\nProceed?",
        ):
            return

        self._safety_panel._execute_btn.configure(state="disabled", text="Executing…")
        self.update()
        result = self.coordinator.execute_deletion(plan)
        self._safety_panel._execute_btn.configure(state="normal", text="Execute Plan")

        if result.failed_files:
            messagebox.showwarning(
                "Deletion Complete",
                f"Deleted: {len(result.deleted_files)}\nFailed: {len(result.failed_files)}")
        else:
            messagebox.showinfo("Deletion Complete",
                                f"Deleted {len(result.deleted_files)} files.")

        self.on_delete_complete(result)
        # Refresh result after deletion
        if result.deleted_files and self._current_result:
            deleted_set = set(result.deleted_files)
            new_groups = []
            for g in self._current_result.duplicate_groups:
                remaining = [f for f in g.files if f.path not in deleted_set]
                if len(remaining) >= 2:
                    from ...engine.models import DuplicateGroup
                    new_groups.append(DuplicateGroup(
                        group_id=g.group_id, group_hash=g.group_hash, files=remaining))
            self._current_result.duplicate_groups = new_groups
            self.load_result(self._current_result)
