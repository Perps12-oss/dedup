"""
Review Page — 3-pane duplicate review and deletion workflow.

Layout:
  Top: Provenance Ribbon
  Body:
    Left (3):  Group Navigator (list + filters)
    Center(6): Review Workspace (Table | Gallery | Compare)
    Right (3): Plan Drawer (Safety Panel)

Clear Selection:
  There is no dedicated "Clear Selection" button in the Review UI. To clear a
  group's keep choice, the user may (a) select a different file as KEEP in that
  group, or (b) load a new scan result (load_result resets vm.keep_selections).
  ReviewVM.clear_keep(group_id) exists but is not wired to any UI control.
  Workspace state and plan state are both driven by vm.keep_selections.
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
from ..components.review_workspace import ReviewWorkspaceStack
from ..viewmodels.review_vm import ReviewVM
from ..utils.formatting import fmt_bytes, truncate_path
from ..utils.icons import IC
from ...orchestration.coordinator import ScanCoordinator
from ...engine.models import ScanResult, DuplicateGroup, DeletionPlan, DeletionResult
from ...engine.thumbnails import generate_thumbnails_async, get_cache_dir
from ...engine.media_types import is_image_extension

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
        body.rowconfigure(0, weight=1)

        self._workspace = ReviewWorkspaceStack(
            body,
            on_keep=self._on_set_keep,
        )
        self._workspace.grid(row=0, column=0, sticky="nsew")

    # ----------------------------------------------------------------
    # Public
    # ----------------------------------------------------------------
    def load_result(self, result: ScanResult):
        self._current_result = result
        self.vm.load_result(result)
        self._prov.update(
            session_id=getattr(self.vm.session, "session_id", result.scan_id if result else ""),
            verification=getattr(self.vm.current_group, "verification_level", "full") if self.vm.groups else "full",
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
        for i, ge in enumerate(self.vm.filtered_groups):
            tag = "warn" if ge.has_risk else ""
            self._group_table.insert_row(
                ge.group_id,
                (str(i + 1), str(ge.file_count), fmt_bytes(ge.reclaimable_bytes),
                 ge.confidence_label),
                tags=(tag,) if tag else (),
            )

    def _on_search(self, text: str):
        self.vm.filter_text = text
        self._refresh_group_list()

    def _on_group_select(self, group_id: str):
        self.vm.selected_group_id = group_id
        self._load_workspace(group_id)

    def _load_workspace(self, group_id: str):
        if not self._current_result:
            return
        group = next((g for g in self._current_result.duplicate_groups
                      if g.group_id == group_id), None)
        keep_path = self.vm.keep_selections.get(group_id, "")
        mode = self.vm.view_mode
        self._workspace.load_group(group, keep_path=keep_path, mode=mode)

    def _on_set_keep(self, path: str) -> None:
        """Called when user marks a file as KEEP in any workspace mode."""
        gid = self.vm.selected_group_id
        if not gid or not path:
            return
        self.vm.set_keep(gid, path)
        self._load_workspace(gid)
        self._safety_panel.update_plan(
            del_count=self.vm.delete_count,
            keep_count=self.vm.keep_count,
            reclaim_bytes=self.vm.reclaimable_bytes,
        )

    def _on_mode_change(self) -> None:
        mode = self._mode_var.get()
        self.vm.view_mode = mode
        self._workspace.set_mode(mode)
        gid = self.vm.selected_group_id
        if gid:
            self._load_workspace(gid)

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
                f"Preview Effects: {prev['total_files']} files → {prev['human_readable_size']}")
        except Exception as e:
            self._safety_panel.set_dry_run_result(f"Error: {e}")

    def _show_delete_confirmation(
        self,
        plan: DeletionPlan,
        prev: dict,
    ) -> str:
        """Show confirmation dialog. Returns 'cancel', 'preview', or 'delete'."""
        result = {"choice": "cancel"}
        root = self.winfo_toplevel()
        dlg = tk.Toplevel(root)
        dlg.title("Confirm Deletion")
        dlg.transient(root)
        dlg.grab_set()

        body = ttk.Frame(dlg, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        row = 0

        def _label(text: str, val: str):
            nonlocal row
            ttk.Label(body, text=text + ":", font=("Segoe UI", 9)).grid(
                row=row, column=0, sticky="w", pady=2
            )
            ttk.Label(body, text=val, font=("Segoe UI", 9, "bold")).grid(
                row=row, column=1, sticky="w", padx=(8, 0), pady=2
            )
            row += 1

        total_files = prev.get("total_files", "?")
        human_size = prev.get("human_readable_size", "?")
        _label("Files to delete", str(total_files))
        _label("Files kept", str(self.vm.keep_count))
        _label("Duplicate groups", str(len(plan.groups)))
        _label("Reclaimable space", str(human_size))
        _label("Delete mode", "Trash")
        _label("Revalidation", "ON")
        _label("Audit logging", "ACTIVE")

        ttk.Separator(dlg, orient="horizontal").pack(fill="x", padx=16, pady=8)

        def _done(choice: str):
            result["choice"] = choice
            dlg.grab_release()
            dlg.destroy()

        btn_f = ttk.Frame(dlg, padding=(16, 0, 16, 12))
        btn_f.pack(fill="x")
        ttk.Button(btn_f, text="Cancel", command=lambda: _done("cancel")).pack(
            side="left", padx=4
        )
        ttk.Button(
            btn_f, text="Preview Effects", style="Ghost.TButton",
            command=lambda: _done("preview"),
        ).pack(side="left", padx=4)
        ttk.Button(
            btn_f, text="DELETE", style="Danger.TButton",
            command=lambda: _done("delete"),
        ).pack(side="right", padx=4)

        dlg.wait_window(dlg)
        return result["choice"]

    def _on_execute(self):
        plan = self._create_plan()
        if not plan or not plan.groups:
            messagebox.showinfo("Delete", "No files selected for deletion.")
            return
        try:
            from ...engine.deletion import preview_deletion
            prev = preview_deletion(plan)
        except Exception:
            prev = {"total_files": "?", "human_readable_size": "?"}

        choice = self._show_delete_confirmation(plan, prev)
        if choice == "cancel":
            return
        if choice == "preview":
            self._on_dry_run()
            return

        self._safety_panel._delete_btn.configure(state="disabled", text="Executing…")
        self.update()
        result = self.coordinator.execute_deletion(plan)
        self._safety_panel._delete_btn.configure(state="normal", text="DELETE")

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
