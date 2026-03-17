"""
ReviewController — handles review intents; keeps execution logic out of the page.

ReviewPage and SafetyPanel emit intents; this controller performs set_keep,
clear_keep, preview_deletion, and execute_deletion using the attached page's
VM, coordinator, and UI refs. Naming aligned with scan intent/controller style.
"""

from __future__ import annotations

from typing import Any, Optional

from ...orchestration.coordinator import ScanCoordinator


class ReviewController:
    """
    Handles review intents. Attach a review page via attach_page(); then
    handle_set_keep, handle_clear_keep, handle_preview_deletion,
    handle_execute_deletion perform the actions (VM + coordinator + UI).
    """

    def __init__(self, coordinator: ScanCoordinator):
        self._coordinator = coordinator
        self._page: Optional[Any] = None

    def attach_page(self, page: Any) -> None:
        """Attach the ReviewPage (or duck-typed equivalent) for intent handling."""
        self._page = page

    def handle_set_keep(self, group_id: str, path: str) -> None:
        """Apply SetKeep intent: update VM, refresh workspace and safety panel."""
        if not self._page or not group_id or not path:
            return
        vm = getattr(self._page, "vm", None)
        if not vm:
            return
        vm.set_keep(group_id, path)
        _load_workspace(self._page, group_id)
        _update_safety_panel(self._page)

    def handle_clear_keep(self, group_id: str) -> None:
        """Apply ClearKeep intent: clear VM selection, refresh workspace and panel."""
        if not self._page or not group_id:
            return
        vm = getattr(self._page, "vm", None)
        if not vm or group_id not in getattr(vm, "keep_selections", {}):
            return
        vm.clear_keep(group_id)
        _load_workspace(self._page, group_id)
        _update_safety_panel(self._page)

    def handle_preview_deletion(self) -> None:
        """Apply PreviewDeletion intent: dry-run preview, no files changed."""
        if not self._page:
            return
        create_plan = getattr(self._page, "_create_plan", None)
        safety_panel = getattr(self._page, "_safety_panel", None)
        if not create_plan or not safety_panel:
            return
        plan = create_plan()
        if not plan or not getattr(plan, "groups", None):
            safety_panel.set_dry_run_result("No files selected.")
            return
        try:
            from ...engine.deletion import preview_deletion
            prev = preview_deletion(plan)
            safety_panel.set_dry_run_result(
                f"Preview Effects: {prev['total_files']} files → {prev['human_readable_size']}")
        except Exception as e:
            safety_panel.set_dry_run_result(f"Error: {e}")

    def handle_execute_deletion(self) -> None:
        """Apply ExecuteDeletion intent: confirm, run coordinator.execute_deletion, refresh."""
        if not self._page:
            return
        from tkinter import messagebox
        create_plan = getattr(self._page, "_create_plan", None)
        show_confirmation = getattr(self._page, "_show_delete_confirmation", None)
        on_dry_run = getattr(self._page, "_on_dry_run", None)
        safety_panel = getattr(self._page, "_safety_panel", None)
        on_delete_complete = getattr(self._page, "on_delete_complete", None)
        load_result = getattr(self._page, "load_result", None)
        current_result = getattr(self._page, "_current_result", None)
        if not create_plan or not show_confirmation or not safety_panel:
            return
        plan = create_plan()
        if not plan or not getattr(plan, "groups", None):
            messagebox.showinfo("Delete", "No files selected for deletion.")
            return
        try:
            from ...engine.deletion import preview_deletion
            prev = preview_deletion(plan)
        except Exception:
            prev = {"total_files": "?", "human_readable_size": "?"}
        choice = show_confirmation(plan, prev)
        if choice == "cancel":
            return
        if choice == "preview":
            if on_dry_run:
                on_dry_run()
            return
        delete_btn = getattr(safety_panel, "_delete_btn", None)
        if delete_btn:
            delete_btn.configure(state="disabled", text="Executing…")
        self._page.update()
        result = self._coordinator.execute_deletion(plan)
        if delete_btn:
            delete_btn.configure(state="normal", text="DELETE")
        if result.failed_files:
            messagebox.showwarning(
                "Deletion Complete",
                f"Deleted: {len(result.deleted_files)}\nFailed: {len(result.failed_files)}")
        else:
            messagebox.showinfo("Deletion Complete",
                                f"Deleted {len(result.deleted_files)} files.")
        if on_delete_complete:
            on_delete_complete(result)
        if result.deleted_files and current_result and load_result:
            from ...engine.models import DuplicateGroup
            deleted_set = set(result.deleted_files)
            new_groups = []
            for g in current_result.duplicate_groups:
                remaining = [f for f in g.files if f.path not in deleted_set]
                if len(remaining) >= 2:
                    new_groups.append(DuplicateGroup(
                        group_id=g.group_id, group_hash=g.group_hash, files=remaining))
            current_result.duplicate_groups = new_groups
            load_result(current_result)


def _load_workspace(page: Any, group_id: str) -> None:
    workspace = getattr(page, "_workspace", None)
    if not workspace:
        return
    current_result = getattr(page, "_current_result", None)
    if not current_result:
        return
    vm = getattr(page, "vm", None)
    if not vm:
        return
    group = next((g for g in current_result.duplicate_groups if g.group_id == group_id), None)
    if not group:
        return
    keep_path = getattr(vm, "keep_selections", {}).get(group_id, "")
    mode = getattr(vm, "view_mode", "table")
    workspace.load_group(group, keep_path=keep_path, mode=mode)


def _update_safety_panel(page: Any) -> None:
    vm = getattr(page, "vm", None)
    panel = getattr(page, "_safety_panel", None)
    if not vm or not panel:
        return
    panel.update_plan(
        del_count=vm.delete_count,
        keep_count=vm.keep_count,
        reclaim_bytes=vm.reclaimable_bytes,
        risk_flags=vm.risk_flags,
    )
