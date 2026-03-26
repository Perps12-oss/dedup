"""
ReviewController — handles review intents from store + ReviewApplicationService only.

ReviewPage and SafetyPanel emit intents; controller updates store (review selection)
and uses application services for plan/execute. UI refresh is via a single callbacks interface
(no page reference, no lambdas closing over page internals).
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol

from ...application.services import ReviewApplicationService
from ..state.selectors import review_selection
from ..state.store import ReviewSelectionState, UIStateStore
from ..utils.formatting import fmt_bytes
from ..utils.review_keep import coerce_keep_selections, default_keep_map_from_result


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
    Handles review intents. Fed from store and ReviewApplicationService only.
    Takes a single callbacks object (IReviewCallbacks); no page reference.
    """

    def __init__(
        self,
        review_service: ReviewApplicationService,
        store: UIStateStore,
        callbacks: IReviewCallbacks,
        toast_notify: Optional[Callable[[str, int], None]] = None,
    ):
        self._review = review_service
        self._store = store
        self._cb = callbacks
        self._toast_notify = toast_notify

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
        keep_map = coerce_keep_selections(result, keep_map)
        self._store.set_review_selection(ReviewSelectionState(keep_selections=keep_map, selected_group_id=selected_id))
        self._cb.set_preview_result(
            f"Smart rule applied: {rule} ({len(keep_map)} groups). "
            "You can change any group manually — your pick overrides the rule."
        )
        self._cb.refresh_review_ui()

    def handle_clear_all_keeps(self) -> None:
        """Reset every duplicate group to the default keeper (first file). Manual picks can follow."""
        result = self._cb.get_current_result()
        state = self._store.state
        sel = review_selection(state)
        selected_id = getattr(sel, "selected_group_id", None)
        if not result or not getattr(result, "duplicate_groups", None):
            self._store.set_review_selection(ReviewSelectionState(keep_selections={}, selected_group_id=selected_id))
            self._cb.set_preview_result("No scan result — nothing to reset.")
            self._cb.refresh_review_ui()
            return
        new_keep = default_keep_map_from_result(result)
        self._store.set_review_selection(ReviewSelectionState(keep_selections=new_keep, selected_group_id=selected_id))
        self._cb.set_preview_result(
            "Reset to default keeper (first file) in each duplicate group. "
            "Change any row anytime — overrides Smart Select."
        )
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
        """Apply SetKeep intent: one protected file per group; overrides Smart Select."""
        if not group_id or not path:
            return
        state = self._store.state
        sel = review_selection(state)
        current = getattr(sel, "keep_selections", None) or {}
        new_keep = dict(current)
        new_keep[group_id] = path
        result = self._cb.get_current_result()
        new_keep = coerce_keep_selections(result, new_keep)
        selected_id = getattr(sel, "selected_group_id", None)
        self._store.set_review_selection(ReviewSelectionState(keep_selections=new_keep, selected_group_id=selected_id))
        self._cb.refresh_review_ui()

    def handle_clear_keep(self, group_id: str) -> None:
        """Reset this group's keeper to the default (first file). At least one file stays protected."""
        if not group_id:
            return
        result = self._cb.get_current_result()
        state = self._store.state
        sel = review_selection(state)
        current = getattr(sel, "keep_selections", None) or {}
        if group_id not in current:
            return
        new_keep = dict(current)
        default_path = None
        if result and getattr(result, "duplicate_groups", None):
            for group in result.duplicate_groups:
                if str(getattr(group, "group_id", "")) != group_id:
                    continue
                files = list(getattr(group, "files", []) or [])
                if len(files) >= 2:
                    default_path = files[0].path
                break
        if default_path:
            new_keep[group_id] = default_path
        elif group_id in new_keep:
            del new_keep[group_id]
        new_keep = coerce_keep_selections(result, new_keep)
        selected_id = getattr(sel, "selected_group_id", None)
        self._store.set_review_selection(ReviewSelectionState(keep_selections=new_keep, selected_group_id=selected_id))
        self._cb.refresh_review_ui()

    def handle_preview_deletion(self) -> None:
        """Apply PreviewDeletion intent: build plan from store + current result, run preview, callback."""
        result = self._cb.get_current_result()
        state = self._store.state
        sel = review_selection(state)
        raw = dict(getattr(sel, "keep_selections", None) or {})
        keep_paths = coerce_keep_selections(result, raw)
        if keep_paths != raw:
            selected_id = getattr(sel, "selected_group_id", None)
            self._store.set_review_selection(ReviewSelectionState(keep_selections=keep_paths, selected_group_id=selected_id))
            self._cb.refresh_review_ui()
        if not result:
            self._cb.set_preview_result("No scan result.")
            return
        plan = self._review.create_deletion_plan(
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
            self._cb.set_preview_result(f"Preview Effects: {prev['total_files']} files → {prev['human_readable_size']}")
        except Exception as e:
            self._cb.set_preview_result(f"Error: {e}")

    def handle_execute_deletion(self) -> None:
        """Apply ExecuteDeletion intent: confirm via callback, run coordinator.execute_deletion, callback."""
        from tkinter import messagebox

        result = self._cb.get_current_result()
        state = self._store.state
        sel = review_selection(state)
        raw = dict(getattr(sel, "keep_selections", None) or {})
        keep_paths = coerce_keep_selections(result, raw)
        if keep_paths != raw:
            selected_id = getattr(sel, "selected_group_id", None)
            self._store.set_review_selection(ReviewSelectionState(keep_selections=keep_paths, selected_group_id=selected_id))
            self._cb.refresh_review_ui()
        if not result:
            messagebox.showinfo("Delete", "No scan result.")
            return
        plan = self._review.create_deletion_plan(
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
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning("preview_deletion (execute path) failed: %s", e)
            msg = (
                "Preview could not run, so deletion was not started. "
                f"Fix the issue or use Preview Effects from the bar, then try again.\n\n{e}"
            )
            self._cb.set_preview_result(f"Preview failed: {e}")
            if self._toast_notify:
                self._toast_notify("Preview unavailable — deletion cancelled.", 6500)
            messagebox.showwarning("Preview unavailable", msg)
            return
        if self._toast_notify:
            self._toast_notify(
                "Next: confirm in the dialog — files go to Trash per your safety settings.",
                3200,
            )
        choice = self._cb.confirm_deletion(plan, prev)
        if choice == "cancel":
            return
        if choice == "preview":
            self.handle_preview_deletion()
            return
        n_files = prev.get("total_files", "?")
        size_h = prev.get("human_readable_size", "?")
        if self._toast_notify:
            self._toast_notify(f"Deleting {n_files} files ({size_h})…", 3800)
        self._cb.on_execute_start()
        result_out = self._review.execute_deletion(plan)
        deleted_n = len(result_out.deleted_files)
        failed_n = len(result_out.failed_files)
        reclaimed = getattr(result_out, "bytes_reclaimed", 0) or 0
        reclaim_txt = fmt_bytes(reclaimed) if reclaimed else "—"
        if result_out.failed_files:
            if self._toast_notify:
                self._toast_notify(
                    f"Finished with issues: {deleted_n} removed, {failed_n} failed. Reclaim ~{reclaim_txt}.",
                    6500,
                )
            messagebox.showwarning(
                "Deletion Complete",
                f"Deleted: {deleted_n}\nFailed: {failed_n}",
            )
        else:
            if self._toast_notify:
                self._toast_notify(
                    f"Success: {deleted_n} files moved to Trash. Space reclaimed ~{reclaim_txt}.",
                    5500,
                )
            else:
                messagebox.showinfo(
                    "Deletion Complete",
                    f"Deleted {deleted_n} files.",
                )
        self._cb.on_execute_done(result_out)
