"""
ReviewController — handles review intents from store + coordinator only.

ReviewPage and SafetyPanel emit intents; controller updates store (review selection)
and uses coordinator for plan/execute. UI refresh is via callbacks (no page reference).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ...orchestration.coordinator import ScanCoordinator
from ..state.store import UIStateStore, ReviewSelectionState
from ..state.selectors import review_selection


class ReviewController:
    """
    Handles review intents. Fed from store (review slices) and coordinator only.
    Callbacks: get_current_result, on_preview_result, on_refresh_review_ui,
    on_confirm_deletion, on_execute_done. No page reference.
    """

    def __init__(
        self,
        coordinator: ScanCoordinator,
        store: UIStateStore,
        get_current_result: Callable[[], Any],
        on_preview_result: Callable[[str], None],
        on_refresh_review_ui: Callable[[], None],
        on_confirm_deletion: Callable[[Any, dict], str],
        on_execute_start: Callable[[], None],
        on_execute_done: Callable[[Any], None],
    ):
        self._coordinator = coordinator
        self._store = store
        self._get_current_result = get_current_result
        self._on_preview_result = on_preview_result
        self._on_refresh_review_ui = on_refresh_review_ui
        self._on_confirm_deletion = on_confirm_deletion
        self._on_execute_start = on_execute_start
        self._on_execute_done = on_execute_done

    def handle_set_keep(self, group_id: str, path: str) -> None:
        """Apply SetKeep intent: update store selection, then refresh UI via callback."""
        if not group_id or not path:
            return
        state = self._store.state
        sel = review_selection(state)
        current = getattr(sel, "keep_selections", None) or {}
        new_keep = dict(current)
        new_keep[group_id] = path
        selected_id = getattr(sel, "selected_group_id", None)
        self._store.set_review_selection(
            ReviewSelectionState(keep_selections=new_keep, selected_group_id=selected_id)
        )
        self._on_refresh_review_ui()

    def handle_clear_keep(self, group_id: str) -> None:
        """Apply ClearKeep intent: update store selection, then refresh UI via callback."""
        if not group_id:
            return
        state = self._store.state
        sel = review_selection(state)
        current = getattr(sel, "keep_selections", None) or {}
        if group_id not in current:
            return
        new_keep = dict(current)
        del new_keep[group_id]
        selected_id = getattr(sel, "selected_group_id", None)
        self._store.set_review_selection(
            ReviewSelectionState(keep_selections=new_keep, selected_group_id=selected_id)
        )
        self._on_refresh_review_ui()

    def handle_preview_deletion(self) -> None:
        """Apply PreviewDeletion intent: build plan from store + current result, run preview, callback."""
        result = self._get_current_result()
        state = self._store.state
        sel = review_selection(state)
        keep_paths = getattr(sel, "keep_selections", None) or {}
        if not result:
            self._on_preview_result("No scan result.")
            return
        plan = self._coordinator.create_deletion_plan(
            result,
            keep_strategy="first",
            group_keep_paths=keep_paths or None,
        )
        if not plan or not getattr(plan, "groups", None):
            self._on_preview_result("No files selected.")
            return
        try:
            from ...engine.deletion import preview_deletion
            prev = preview_deletion(plan)
            self._on_preview_result(
                f"Preview Effects: {prev['total_files']} files → {prev['human_readable_size']}"
            )
        except Exception as e:
            self._on_preview_result(f"Error: {e}")

    def handle_execute_deletion(self) -> None:
        """Apply ExecuteDeletion intent: confirm via callback, run coordinator.execute_deletion, callback."""
        from tkinter import messagebox
        result = self._get_current_result()
        state = self._store.state
        sel = review_selection(state)
        keep_paths = getattr(sel, "keep_selections", None) or {}
        if not result:
            messagebox.showinfo("Delete", "No scan result.")
            return
        plan = self._coordinator.create_deletion_plan(
            result,
            keep_strategy="first",
            group_keep_paths=keep_paths or None,
        )
        if not plan or not getattr(plan, "groups", None):
            messagebox.showinfo("Delete", "No files selected for deletion.")
            return
        try:
            from ...engine.deletion import preview_deletion
            prev = preview_deletion(plan)
        except Exception:
            prev = {"total_files": "?", "human_readable_size": "?"}
        choice = self._on_confirm_deletion(plan, prev)
        if choice == "cancel":
            return
        if choice == "preview":
            self.handle_preview_deletion()
            return
        self._on_execute_start()
        result_out = self._coordinator.execute_deletion(plan)
        if result_out.failed_files:
            messagebox.showwarning(
                "Deletion Complete",
                f"Deleted: {len(result_out.deleted_files)}\nFailed: {len(result_out.failed_files)}",
            )
        else:
            messagebox.showinfo(
                "Deletion Complete",
                f"Deleted {len(result_out.deleted_files)} files.",
            )
        self._on_execute_done(result_out)
