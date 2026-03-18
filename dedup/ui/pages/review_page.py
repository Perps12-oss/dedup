"""
Review Page — 3-pane duplicate review and deletion workflow.

Layout:
  Top: Provenance Ribbon
  Body:
    Left (3):  Group Navigator (list + filters)
    Center(6): Review Workspace (Table | Gallery | Compare)
    Right (3): Plan Drawer (Safety Panel)

Clear Selection: The workspace toolbar shows "Clear selection" when the current
group has a keep choice; it calls clear_keep for the selected group. User can
also change keep to another file in the group or load a new scan (load_result
resets vm.keep_selections). Workspace and plan state are driven by vm.keep_selections.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Optional, List

from ..controller.review_controller import ReviewController
from ..components import (
    DataTable, SectionCard, SafetyPanel, ProvenanceRibbon,
    EmptyState, FilterBar, StatusRibbon,
)
from ..components.review_workspace import ReviewWorkspaceStack
from ..viewmodels.review_vm import ReviewVM
from ..utils.formatting import fmt_bytes, truncate_path
from ..utils.icons import IC
from ..theme.design_system import font_tuple, SPACING
from ...orchestration.coordinator import ScanCoordinator
from ...engine.models import ScanResult, DuplicateGroup, DeletionPlan, DeletionResult
from ...engine.thumbnails import generate_thumbnails_async, get_cache_dir
from ...engine.media_types import is_image_extension

_THUMB_SIZE = (64, 64)
# Bounded navigator for scale (Phase 3B): cap visible rows to avoid unbounded Treeview
REVIEW_NAVIGATOR_MAX_ROWS = 2000


class ReviewPage(ttk.Frame):
    """Review & deletion planning page."""

    def __init__(self, parent,
                 coordinator: ScanCoordinator,
                 on_delete_complete: Callable[[DeletionResult], None],
                 review_controller: Optional[ReviewController] = None,
                 store=None,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.coordinator = coordinator
        self.on_delete_complete = on_delete_complete
        self._review_controller = review_controller
        self._store = store
        self.vm = ReviewVM()
        self._current_result: Optional[ScanResult] = None
        self._thumbnail_refs: list = []
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        pad = SPACING["page"]

        # ── Decision Studio: page title + view mode ───────────────────
        hdr = ttk.Frame(self, padding=(pad, SPACING["lg"], pad, 0))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        ttk.Label(hdr, text=f"{IC.REVIEW}  Decision Studio",
                  font=font_tuple("page_title")).grid(row=0, column=0, sticky="w")
        ttk.Label(hdr, text="Groups · Workspace · Decision & Safety",
                  style="Muted.TLabel",
                  font=font_tuple("page_subtitle")).grid(row=1, column=0, sticky="w")

        # View mode: Table | Gallery | Compare
        mode_frame = ttk.Frame(hdr, style="Panel.TFrame")
        mode_frame.grid(row=0, column=2, rowspan=2, sticky="e")
        self._mode_var = tk.StringVar(value="table")
        for label, val in [("Table", "table"), ("Gallery", "gallery"), ("Compare", "compare")]:
            ttk.Radiobutton(mode_frame, text=label, variable=self._mode_var,
                            value=val, command=self._on_mode_change).pack(side="left", padx=SPACING["sm"])

        # ── Provenance ribbon ─────────────────────────────────────────
        self._prov = ProvenanceRibbon(self)
        self._prov.grid(row=1, column=0, sticky="ew", padx=pad, pady=(0, SPACING["md"]))

        # ── 3-pane body: Group Navigator | Workspace | Decision & Safety Rail ─
        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew", padx=pad, pady=(0, pad))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, minsize=200)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, minsize=200)

        # Left: Group Navigator (decision-state per group in decision-state todo)
        left = SectionCard(body, title=f"{IC.GROUPS}  Group Navigator")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["md"]))
        self._build_group_navigator(left.body)

        # Center: Workspace (Gallery / Table / Compare)
        center = SectionCard(body, title=f"{IC.REVIEW}  Workspace")
        center.grid(row=0, column=1, sticky="nsew", padx=SPACING["md"])
        self._build_workspace(center.body)

        # Right: Decision & Safety Rail
        right_frame = ttk.Frame(body)
        right_frame.grid(row=0, column=2, sticky="nsew")
        right_frame.rowconfigure(0, weight=1)
        right_frame.columnconfigure(0, weight=1)
        self._safety_panel = SafetyPanel(
            right_frame,
            on_dry_run=self._on_preview_intent,
            on_execute=self._on_execute_intent,
        )
        self._safety_panel.grid(row=0, column=0, sticky="nsew")

        # Keyboard shortcuts when Review is visible: Ctrl+Right = next group, Ctrl+Left = previous group
        self._bind_key_next = lambda e: self._on_key_next_group()
        self._bind_key_prev = lambda e: self._on_key_prev_group()

    def _build_group_navigator(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        # Filter bar: search + decision-state filter
        from ..components.decision_state import (
            DECISION_STATE_LABELS,
            STATE_UNRESOLVED,
            STATE_READY,
            STATE_WARNING,
        )
        self._filter_bar = FilterBar(
            body,
            on_search=self._on_search,
            filters=[
                ("State", ["All", DECISION_STATE_LABELS[STATE_UNRESOLVED], DECISION_STATE_LABELS[STATE_READY], DECISION_STATE_LABELS[STATE_WARNING]]),
            ],
            style="Panel.TFrame",
        )
        self._filter_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._filter_bar.get_filter(0)  # ensure filter vars exist
        # Wire state filter: map display name back to state key
        self._state_filter_map = {"All": "all", DECISION_STATE_LABELS[STATE_UNRESOLVED]: STATE_UNRESOLVED, DECISION_STATE_LABELS[STATE_READY]: STATE_READY, DECISION_STATE_LABELS[STATE_WARNING]: STATE_WARNING}
        try:
            self._filter_bar._filter_vars[0].trace_add("write", self._on_state_filter_change)
        except Exception:
            pass

        self._group_count_var = tk.StringVar(value="0 groups")
        ttk.Label(body, textvariable=self._group_count_var, style="Panel.Muted.TLabel",
                  font=font_tuple("data_label")).grid(row=1, column=0, sticky="w", pady=(0, 2))

        self._group_table = DataTable(
            body,
            columns=[
                ("idx",      "#",      32, "center"),
                ("state",    "State",  82, "w"),   # decision-state badge label
                ("files",    "Files",  40, "center"),
                ("size",     "Size",   70, "e"),
                ("conf",     "Conf",   40, "center"),
            ],
            height=16,
            on_select=self._on_group_select,
        )
        self._group_table.grid(row=2, column=0, sticky="nsew")
        body.rowconfigure(2, weight=1)

    def _build_workspace(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self._workspace = ReviewWorkspaceStack(
            body,
            on_keep=self._on_set_keep,
            on_clear_keep=self._on_clear_keep,
        )
        self._workspace.grid(row=0, column=0, sticky="nsew")

    # ----------------------------------------------------------------
    # Public
    # ----------------------------------------------------------------
    def load_result(self, result: ScanResult):
        self._current_result = result
        self.vm.load_result(result)
        if self._store:
            from ..state.store import ReviewSelectionState
            self._store.set_review_selection(
                ReviewSelectionState(
                    keep_selections={},
                    selected_group_id=self.vm.selected_group_id,
                )
            )
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
            risk_flags=self.vm.risk_flags,
        )

    def on_show(self):
        self.bind_all("<Control-Right>", self._bind_key_next, add="+")
        self.bind_all("<Control-Left>", self._bind_key_prev, add="+")

    def on_hide(self):
        self.unbind_all("<Control-Right>")
        self.unbind_all("<Control-Left>")

    # ----------------------------------------------------------------
    # Group list
    # ----------------------------------------------------------------
    def _refresh_group_list(self):
        from ..components.decision_state import get_group_decision_state, get_decision_label
        self._group_table.clear()
        groups = self.vm.filtered_groups
        total = len(groups)
        # Scale-out: show at most REVIEW_NAVIGATOR_MAX_ROWS to keep Treeview bounded (Phase 3B)
        display = groups if total <= REVIEW_NAVIGATOR_MAX_ROWS else groups[:REVIEW_NAVIGATOR_MAX_ROWS]
        if total > REVIEW_NAVIGATOR_MAX_ROWS:
            self._group_count_var.set(f"Showing first {REVIEW_NAVIGATOR_MAX_ROWS} of {total} groups")
        else:
            self._group_count_var.set(f"{total} group{'s' if total != 1 else ''}")
        for i, ge in enumerate(display):
            state = get_group_decision_state(ge.group_id, self.vm.keep_selections, ge.has_risk)
            state_label = get_decision_label(state)
            tag = "warn" if ge.has_risk else ""
            self._group_table.insert_row(
                ge.group_id,
                (str(i + 1), state_label, str(ge.file_count), fmt_bytes(ge.reclaimable_bytes),
                 ge.confidence_label),
                tags=(tag,) if tag else (),
            )

    def _on_search(self, text: str):
        self.vm.filter_text = text
        self._refresh_group_list()

    def _on_state_filter_change(self, *_):
        try:
            display = self._filter_bar.get_filter(0)
            self.vm.filter_state = self._state_filter_map.get(display, "all")
        except Exception:
            self.vm.filter_state = "all"
        self._refresh_group_list()

    def _on_key_next_group(self):
        groups = self.vm.filtered_groups
        if not groups or not self.winfo_viewable():
            return
        idx = next((i for i, g in enumerate(groups) if g.group_id == self.vm.selected_group_id), 0)
        if idx + 1 < len(groups):
            self._on_group_select(groups[idx + 1].group_id)
            self._group_table.select(groups[idx + 1].group_id)

    def _on_key_prev_group(self):
        groups = self.vm.filtered_groups
        if not groups or not self.winfo_viewable():
            return
        idx = next((i for i, g in enumerate(groups) if g.group_id == self.vm.selected_group_id), 0)
        if idx > 0:
            self._on_group_select(groups[idx - 1].group_id)
            self._group_table.select(groups[idx - 1].group_id)

    def _on_group_select(self, group_id: str):
        self.vm.selected_group_id = group_id
        if self._store:
            from ..state.store import ReviewSelectionState
            self._store.set_review_selection(
                ReviewSelectionState(
                    keep_selections=dict(self.vm.keep_selections),
                    selected_group_id=group_id,
                )
            )
        self._load_workspace(group_id)

    def _load_workspace(self, group_id: str):
        if not self._current_result:
            return
        group = next((g for g in self._current_result.duplicate_groups
                      if g.group_id == group_id), None)
        keep_path = self.vm.keep_selections.get(group_id, "")
        mode = self.vm.view_mode
        self._workspace.load_group(group, keep_path=keep_path, mode=mode)

    def _on_preview_intent(self) -> None:
        """Emit PreviewDeletion intent; controller handles dry-run if present."""
        if self._review_controller:
            self._review_controller.handle_preview_deletion()
        else:
            self._on_dry_run()

    def _on_execute_intent(self) -> None:
        """Emit ExecuteDeletion intent; controller handles execution if present."""
        if self._review_controller:
            self._review_controller.handle_execute_deletion()
        else:
            self._on_execute()

    def _sync_review_from_store_and_refresh(self) -> None:
        """Sync VM from store.review.selection and refresh workspace + safety panel. No-op if no store."""
        if not self._store:
            return
        from ..state.selectors import review_selection
        state = self._store.state
        sel = review_selection(state)
        if sel is None:
            return
        keep = getattr(sel, "keep_selections", None) or {}
        self.vm.keep_selections = dict(keep)
        sid = getattr(sel, "selected_group_id", None)
        if sid is not None:
            self.vm.selected_group_id = sid
        gid = self.vm.selected_group_id
        if gid:
            self._load_workspace(gid)
        self._safety_panel.update_plan(
            del_count=self.vm.delete_count,
            keep_count=self.vm.keep_count,
            reclaim_bytes=self.vm.reclaimable_bytes,
            risk_flags=self.vm.risk_flags,
        )

    def _on_execute_done(self, result: DeletionResult) -> None:
        """Called by ReviewController after execute_deletion. Re-enable button, notify, refresh result."""
        self.on_delete_complete(result)
        if result.deleted_files and self._current_result:
            from ...engine.models import DuplicateGroup
            deleted_set = set(result.deleted_files)
            new_groups = []
            for g in self._current_result.duplicate_groups:
                remaining = [f for f in g.files if f.path not in deleted_set]
                if len(remaining) >= 2:
                    new_groups.append(DuplicateGroup(
                        group_id=g.group_id, group_hash=g.group_hash, files=remaining))
            self._current_result.duplicate_groups = new_groups
            self.load_result(self._current_result)
        else:
            self._safety_panel.update_plan(
                del_count=self.vm.delete_count,
                keep_count=self.vm.keep_count,
                reclaim_bytes=self.vm.reclaimable_bytes,
                risk_flags=self.vm.risk_flags,
            )
        if self._store:
            from ..state.store import ReviewSelectionState
            self._store.set_review_selection(
                ReviewSelectionState(
                    keep_selections=dict(self.vm.keep_selections),
                    selected_group_id=self.vm.selected_group_id,
                )
            )

    def _on_set_keep(self, path: str) -> None:
        """Emit SetKeep intent or apply directly when no controller."""
        gid = self.vm.selected_group_id
        if not gid or not path:
            return
        if self._review_controller:
            self._review_controller.handle_set_keep(gid, path)
        else:
            self.vm.set_keep(gid, path)
            self._load_workspace(gid)
            self._safety_panel.update_plan(
                del_count=self.vm.delete_count,
                keep_count=self.vm.keep_count,
                reclaim_bytes=self.vm.reclaimable_bytes,
                risk_flags=self.vm.risk_flags,
            )

    def _on_clear_keep(self) -> None:
        """Emit ClearKeep intent or apply directly when no controller."""
        gid = self.vm.selected_group_id
        if not gid or gid not in self.vm.keep_selections:
            return
        if self._review_controller:
            self._review_controller.handle_clear_keep(gid)
        else:
            self.vm.clear_keep(gid)
            self._load_workspace(gid)
            self._safety_panel.update_plan(
                del_count=self.vm.delete_count,
                keep_count=self.vm.keep_count,
                reclaim_bytes=self.vm.reclaimable_bytes,
                risk_flags=self.vm.risk_flags,
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
            ttk.Label(body, text=text + ":", font=font_tuple("body")).grid(
                row=row, column=0, sticky="w", pady=2
            )
            ttk.Label(body, text=val, font=font_tuple("body_bold")).grid(
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
