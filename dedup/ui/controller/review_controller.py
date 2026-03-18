"""
ReviewController — handles review intents from store + coordinator only.

ReviewPage and SafetyPanel emit intents; controller updates store (review selection)
and uses coordinator for plan/execute. UI refresh is via a single callbacks interface
(no page reference, no lambdas closing over page internals).
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from ...orchestration.coordinator import ScanCoordinator
from ..state.store import UIStateStore, ReviewSelectionState
from ..state.selectors import review_selection


class IReviewCallbacks(Protocol):
    """Contract for review UI callbacks. Implemented by ReviewPage; controller holds this only."""

    def get_current_result(self) -> Any: ...
    def set_preview_result(self, msg: str) -> None: ...
    def refresh_review_ui(self) -> None: ...
    def confirm_deletion(self, plan: Any, prev: dict) -> str: ...
    def on_execute_start(self) -> None: ...
    def on_execute_done(self, result: Any) -> None: ...


class ReviewController:
    """
    Handles review intents. Fed from store and coordinator only.
    Takes a single callbacks object (IReviewCallbacks); no page reference.
    """

    def __init__(
        self,
        coordinator: ScanCoordinator,
        store: UIStateStore,
        callbacks: IReviewCallbacks,
    ):
        self._coordinator = coordinator
        self._store = store
        self._cb = callbacks

    def handle_apply_smart_rule(self, rule: str) -> None:
        """
        Apply auto smart selection across all duplicate groups.
        Supported rules: first | newest | oldest | largest | smallest.
        """
        result = self._cb.get_current_result()
        if not result or not getattr(result, "duplicate_groups", None):
            self._cb.set_preview_result("Smart rule skipped: no scan result.")
            return
        keep_map: dict[str, str] = {}
        for group in result.duplicate_groups:
            files = list(getattr(group, "files", []) or [])
            if len(files) < 2:
                continue
            selected = self._pick_keep_file(files, rule)
            if selected is not None:
                keep_map[str(getattr(group, "group_id", ""))] = selected.path

        state = self._store.state
        sel = review_selection(state)
        selected_id = getattr(sel, "selected_group_id", None)
        self._store.set_review_selection(
            ReviewSelectionState(keep_selections=keep_map, selected_group_id=selected_id)
        )
        self._cb.set_preview_result(f"Smart rule applied: {rule} ({len(keep_map)} groups).")
        self._cb.refresh_review_ui()

    def handle_clear_all_keeps(self) -> None:
        """Clear all keep selections to fully reverse smart/manual choices."""
        state = self._store.state
        sel = review_selection(state)
        selected_id = getattr(sel, "selected_group_id", None)
        self._store.set_review_selection(
            ReviewSelectionState(keep_selections={}, selected_group_id=selected_id)
        )
        self._cb.set_preview_result("Keep selections cleared.")
        self._cb.refresh_review_ui()

    @staticmethod
    def _pick_keep_file(files: list, rule: str):
        if not files:
            return None
        if rule == "newest":
            return max(files, key=lambda f: getattr(f, "mtime_ns", 0))
        if rule == "oldest":
            return min(files, key=lambda f: getattr(f, "mtime_ns", 0))
        if rule == "largest":
            return max(files, key=lambda f: getattr(f, "size", 0))
        if rule == "smallest":
            return min(files, key=lambda f: getattr(f, "size", 0))
        return files[0]

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
        self._cb.refresh_review_ui()

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
        self._cb.refresh_review_ui()

    def handle_preview_deletion(self) -> None:
        """Apply PreviewDeletion intent: build plan from store + current result, run preview, callback."""
        result = self._cb.get_current_result()
        state = self._store.state
        sel = review_selection(state)
        keep_paths = getattr(sel, "keep_selections", None) or {}
        if not result:
            self._cb.set_preview_result("No scan result.")
            return
        plan = self._coordinator.create_deletion_plan(
            result,
            keep_strategy="first",
            group_keep_paths=keep_paths or None,
        )
        if not plan or not getattr(plan, "groups", None):
            self._cb.set_preview_result("No files selected.")
            return
        try:
            from ...engine.deletion import preview_deletion
            prev = preview_deletion(plan)
            self._cb.set_preview_result(
                f"Preview Effects: {prev['total_files']} files → {prev['human_readable_size']}"
            )
        except Exception as e:
            self._cb.set_preview_result(f"Error: {e}")

    def handle_execute_deletion(self) -> None:
        """Apply ExecuteDeletion intent: confirm via callback, run coordinator.execute_deletion, callback."""
        from tkinter import messagebox
        result = self._cb.get_current_result()
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
        choice = self._cb.confirm_deletion(plan, prev)
        if choice == "cancel":
            return
        if choice == "preview":
            self.handle_preview_deletion()
            return
        self._cb.on_execute_start()
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
        self._cb.on_execute_done(result_out)
