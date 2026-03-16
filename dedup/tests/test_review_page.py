"""
Targeted tests for Review page refactor.

Covers:
  - Viewmodel/state (view_mode, keep_selections)
  - Workspace mode selection and thumb sizing
  - Panel action routing (DELETE, Preview Effects)
  - Confirmation dialog intent (cancel/preview/delete branching)
  - Gallery/Compare edge cases
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Module-level helpers (no tk required)
# ---------------------------------------------------------------------------

def test_thumb_size_for_group_adaptive_sizing():
    """Gallery uses adaptive thumb size: 2→220, 3-4→160, 5+→110."""
    from dedup.ui.components.review_workspace import _thumb_size_for_group
    assert _thumb_size_for_group(1) == (220, 220)
    assert _thumb_size_for_group(2) == (220, 220)
    assert _thumb_size_for_group(3) == (160, 160)
    assert _thumb_size_for_group(4) == (160, 160)
    assert _thumb_size_for_group(5) == (110, 110)
    assert _thumb_size_for_group(20) == (110, 110)


def test_thumb_size_large_group_sane():
    """Large groups (20+) still get consistent small thumb size."""
    from dedup.ui.components.review_workspace import _thumb_size_for_group
    assert _thumb_size_for_group(50) == (110, 110)
    assert _thumb_size_for_group(100) == (110, 110)


# ---------------------------------------------------------------------------
# ReviewVM view_mode
# ---------------------------------------------------------------------------

def test_review_vm_view_mode_default():
    from dedup.ui.viewmodels.review_vm import ReviewVM
    vm = ReviewVM()
    assert vm.view_mode == "table"


def test_review_vm_view_mode_mutable():
    from dedup.ui.viewmodels.review_vm import ReviewVM
    vm = ReviewVM()
    vm.view_mode = "gallery"
    assert vm.view_mode == "gallery"
    vm.view_mode = "compare"
    assert vm.view_mode == "compare"


def test_review_vm_clear_keep_removes_selection():
    from dedup.ui.viewmodels.review_vm import ReviewVM
    from dedup.ui.projections.review_projection import ReviewGroupProjection

    def _g(): return ReviewGroupProjection(
        group_id="g1", group_size=512, file_count=2,
        verification_level="full_hash", confidence_label="Exact",
        reclaimable_bytes=1024, review_status="unreviewed",
        risk_flags=(), keeper_candidate="/a/f1.txt",
        thumbnail_capable=False, metadata_summary="g1",
    )
    vm = ReviewVM()
    vm.groups = [_g()]
    vm.set_keep("g1", "/a/f1.txt")
    assert vm.keep_selections.get("g1") == "/a/f1.txt"

    vm.clear_keep("g1")
    assert "g1" not in vm.keep_selections


def test_workspace_stack_clear_selection_button_shown_when_keep(tk_root):
    """Clear selection toolbar is visible when group has a keep choice."""
    from dedup.ui.components.review_workspace import ReviewWorkspaceStack
    from dedup.engine.models import DuplicateGroup, FileMetadata

    called = []
    stack = ReviewWorkspaceStack(tk_root, on_keep=lambda _: None, on_clear_keep=lambda: called.append(1))
    group = DuplicateGroup(
        group_id="g1", group_hash="xx",
        files=[
            FileMetadata(path="/a.jpg", size=100, mtime_ns=0, inode=1),
            FileMetadata(path="/b.jpg", size=100, mtime_ns=0, inode=2),
        ],
    )
    stack.load_group(group, keep_path="/a.jpg", mode="table")
    tk_root.update_idletasks()
    # Clear toolbar should be visible (grid'd) — use winfo_ismapped (winfo_viewable fails when root withdrawn)
    assert stack._clear_toolbar_visible
    stack._clear_btn.invoke()
    assert len(called) == 1

    stack.load_group(group, keep_path="", mode="table")
    tk_root.update_idletasks()
    # Clear toolbar should be hidden when no keep
    assert not stack._clear_toolbar_visible


# ---------------------------------------------------------------------------
# Workspace mode selection
# ---------------------------------------------------------------------------

@pytest.fixture
def tk_root():
    """Tk root for widget tests. Skips if Tk unavailable (e.g. headless CI)."""
    import tkinter as tk
    try:
        root = tk.Tk()
    except (tk.TclError, OSError, Exception) as e:
        pytest.skip(f"Tk unavailable: {e}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


def test_workspace_stack_set_mode_changes_index(tk_root):
    """set_mode maps table/gallery/compare to correct view index."""
    from dedup.ui.components.review_workspace import ReviewWorkspaceStack

    def noop(_: str): pass
    stack = ReviewWorkspaceStack(tk_root, on_keep=noop)
    assert stack._current == 0

    stack.set_mode("table")
    assert stack._current == 0
    stack.set_mode("gallery")
    assert stack._current == 1
    stack.set_mode("compare")
    assert stack._current == 2
    stack.set_mode("unknown")
    assert stack._current == 0


def test_workspace_stack_load_group_passes_mode(tk_root):
    """load_group with mode parameter shows correct view."""
    from dedup.ui.components.review_workspace import ReviewWorkspaceStack
    from dedup.engine.models import DuplicateGroup, FileMetadata

    def noop(_: str): pass
    stack = ReviewWorkspaceStack(tk_root, on_keep=noop)
    group = DuplicateGroup(
        group_id="g1", group_hash="xx",
        files=[
            FileMetadata(path="/a.jpg", size=100, mtime_ns=0, inode=1),
            FileMetadata(path="/b.jpg", size=100, mtime_ns=0, inode=2),
        ],
    )
    stack.load_group(group, keep_path="/a.jpg", mode="gallery")
    assert stack._current == 1
    stack.load_group(group, keep_path="/a.jpg", mode="compare")
    assert stack._current == 2


def test_clear_selection_button_shown_when_keep_set(tk_root):
    """Clear selection toolbar is shown when group has a keep choice."""
    from dedup.ui.components.review_workspace import ReviewWorkspaceStack
    from dedup.engine.models import DuplicateGroup, FileMetadata

    def noop(_: str): pass
    cleared = []

    def on_clear():
        cleared.append(1)

    stack = ReviewWorkspaceStack(tk_root, on_keep=noop, on_clear_keep=on_clear)
    group = DuplicateGroup(
        group_id="g1", group_hash="xx",
        files=[
            FileMetadata(path="/a.jpg", size=100, mtime_ns=0, inode=1),
            FileMetadata(path="/b.jpg", size=100, mtime_ns=0, inode=2),
        ],
    )
    stack.load_group(group, keep_path="", mode="table")
    assert stack._clear_toolbar_visible is False  # hidden when no keep

    stack.load_group(group, keep_path="/a.jpg", mode="table")
    assert stack._clear_toolbar_visible is True  # visible when keep set

    stack._clear_btn.invoke()
    assert len(cleared) == 1


def test_workspace_stack_clear_selection_button(tk_root):
    """Clear selection toolbar appears when group has keep_path; button invokes callback."""
    from dedup.ui.components.review_workspace import ReviewWorkspaceStack
    from dedup.engine.models import DuplicateGroup, FileMetadata

    def noop(_: str): pass
    cleared = []

    def on_clear():
        cleared.append(1)

    stack = ReviewWorkspaceStack(tk_root, on_keep=noop, on_clear_keep=on_clear)
    group = DuplicateGroup(
        group_id="g1", group_hash="xx",
        files=[
            FileMetadata(path="/a.jpg", size=100, mtime_ns=0, inode=1),
            FileMetadata(path="/b.jpg", size=100, mtime_ns=0, inode=2),
        ],
    )
    # No keep_path: toolbar hidden
    stack.load_group(group, keep_path="", mode="table")
    assert stack._clear_toolbar_visible is False

    # With keep_path: toolbar shown
    stack.load_group(group, keep_path="/a.jpg", mode="table")
    assert stack._clear_toolbar_visible is True

    # Click Clear selection
    stack._clear_btn.invoke()
    assert len(cleared) == 1


def test_clear_selection_button_shown_when_keep_set(tk_root):
    """Clear selection toolbar appears when group has a keep choice."""
    from dedup.ui.components.review_workspace import ReviewWorkspaceStack
    from dedup.engine.models import DuplicateGroup, FileMetadata

    def noop(_: str): pass
    cleared = []
    stack = ReviewWorkspaceStack(tk_root, on_keep=noop, on_clear_keep=lambda: cleared.append(1))
    group = DuplicateGroup(
        group_id="g1", group_hash="xx",
        files=[
            FileMetadata(path="/a.jpg", size=100, mtime_ns=0, inode=1),
            FileMetadata(path="/b.jpg", size=100, mtime_ns=0, inode=2),
        ],
    )
    # No keep → toolbar hidden
    stack.load_group(group, keep_path="", mode="table")
    assert stack._clear_toolbar_visible is False  # hidden when no keep
    # With keep → toolbar shown
    stack.load_group(group, keep_path="/a.jpg", mode="table")
    assert stack._clear_toolbar_visible is True
    # Click Clear selection → callback invoked
    stack._clear_btn.invoke()
    assert len(cleared) == 1


# ---------------------------------------------------------------------------
# Compare mode keep state for >2 files
# ---------------------------------------------------------------------------

def test_keep_compare_pair_index_mapping(tk_root):
    """For groups with >2 files, Keep Left/Right map to correct file path."""
    from dedup.ui.components.review_workspace import ReviewWorkspaceStack
    from dedup.engine.models import DuplicateGroup, FileMetadata

    received = []

    def capture(path: str):
        received.append(path)

    stack = ReviewWorkspaceStack(tk_root, on_keep=capture)
    group = DuplicateGroup(
        group_id="g1", group_hash="xx",
        files=[
            FileMetadata(path="/f0.jpg", size=100, mtime_ns=0, inode=1),
            FileMetadata(path="/f1.jpg", size=100, mtime_ns=0, inode=2),
            FileMetadata(path="/f2.jpg", size=100, mtime_ns=0, inode=3),
        ],
    )
    stack._compare.load_group(group, keep_path="")
    stack._compare._pair_index = 0  # showing f0 vs f1
    stack._keep_compare(0)  # Keep Left
    assert "/f0.jpg" in received
    received.clear()
    stack._keep_compare(1)  # Keep Right
    assert "/f1.jpg" in received

    received.clear()
    stack._compare._pair_index = 1  # showing f1 vs f2
    stack._keep_compare(0)  # Keep Left
    assert "/f1.jpg" in received
    received.clear()
    stack._keep_compare(1)  # Keep Right
    assert "/f2.jpg" in received


# ---------------------------------------------------------------------------
# SafetyPanel action routing
# ---------------------------------------------------------------------------

def test_safety_panel_execute_calls_callback(tk_root):
    """DELETE button invokes on_execute callback."""
    from dedup.ui.components.safety_panel import SafetyPanel

    called = []
    panel = SafetyPanel(tk_root, on_execute=lambda: called.append("execute"))
    panel._do_execute()
    assert "execute" in called


def test_safety_panel_preview_calls_callback(tk_root):
    """Preview Effects button invokes on_dry_run callback."""
    from dedup.ui.components.safety_panel import SafetyPanel

    called = []
    panel = SafetyPanel(tk_root, on_dry_run=lambda: called.append("preview"))
    panel._do_dry_run()
    assert "preview" in called


def test_safety_panel_update_plan_disable_delete_when_zero(tk_root):
    """update_plan(del_count=0) disables DELETE button."""
    from dedup.ui.components.safety_panel import SafetyPanel

    panel = SafetyPanel(tk_root)
    panel.update_plan(del_count=0, keep_count=0, reclaim_bytes=0)
    assert "disabled" in str(panel._delete_btn.cget("state")).lower()


def test_safety_panel_update_plan_enable_delete_when_positive(tk_root):
    """update_plan(del_count>0) enables DELETE button."""
    from dedup.ui.components.safety_panel import SafetyPanel

    panel = SafetyPanel(tk_root)
    panel.update_plan(del_count=5, keep_count=2, reclaim_bytes=1024)
    assert "normal" in str(panel._delete_btn.cget("state")).lower()


# ---------------------------------------------------------------------------
# Confirmation dialog intent
# ---------------------------------------------------------------------------

def test_on_execute_cancel_returns_without_executing(tk_root):
    """When confirmation returns 'cancel', no deletion is performed."""
    from unittest.mock import MagicMock, patch
    from dedup.ui.pages.review_page import ReviewPage
    from dedup.engine.models import DeletionPlan

    grp = dict(keep=["/a/file.jpg"], delete=["/b/file.jpg"])
    plan = DeletionPlan(scan_id="t", groups=[grp])
    coordinator = MagicMock()
    coordinator.create_deletion_plan.return_value = plan

    page = ReviewPage(tk_root, coordinator=coordinator, on_delete_complete=lambda _: None)
    page._current_result = MagicMock()
    page._current_result.duplicate_groups = []
    page.vm.groups = [MagicMock()]
    page.vm.groups[0].group_id = "g1"
    page.vm.groups[0].file_count = 2
    page.vm.keep_selections = {"g1": "/a/file.jpg"}

    with patch.object(page, "_show_delete_confirmation") as mock_conf:
        mock_conf.return_value = "cancel"
        page._on_execute()

    coordinator.execute_deletion.assert_not_called()


def test_on_execute_preview_calls_dry_run_not_execute(tk_root):
    """When confirmation returns 'preview', dry run runs, execute does not."""
    from unittest.mock import MagicMock, patch
    from dedup.ui.pages.review_page import ReviewPage

    coordinator = MagicMock()
    page = ReviewPage(tk_root, coordinator=coordinator, on_delete_complete=lambda _: None)
    page._current_result = MagicMock()
    page._current_result.duplicate_groups = [MagicMock()]
    page.vm.groups = [MagicMock()]
    page.vm.groups[0].group_id = "g1"
    page.vm.groups[0].file_count = 2
    page.vm.keep_selections = {"g1": "/a/file.jpg"}
    grp = dict(keep=["/a/file.jpg"], delete=["/b/file.jpg"])
    coordinator.create_deletion_plan.return_value = MagicMock()
    coordinator.create_deletion_plan.return_value.groups = [grp]

    dry_run_called = []
    def track_dry_run():
        dry_run_called.append(1)
    page._on_dry_run = track_dry_run

    with patch.object(page, "_show_delete_confirmation") as mock_conf:
        mock_conf.return_value = "preview"
        page._on_execute()

    assert len(dry_run_called) == 1
    coordinator.execute_deletion.assert_not_called()


def test_on_execute_delete_calls_executor(tk_root):
    """When confirmation returns 'delete', execute_deletion is called."""
    from unittest.mock import MagicMock, patch
    from dedup.ui.pages.review_page import ReviewPage
    from dedup.engine.models import DeletionResult, DeletionPlan

    from dedup.engine.models import DeletionPolicy

    grp = dict(keep=["/a/file.jpg"], delete=["/b/file.jpg"])
    plan = DeletionPlan(scan_id="t", groups=[grp])
    coordinator = MagicMock()
    coordinator.create_deletion_plan.return_value = plan
    coordinator.execute_deletion.return_value = DeletionResult(
        scan_id="t", policy=DeletionPolicy.TRASH,
        deleted_files=["/b/file.jpg"], failed_files=[],
    )

    page = ReviewPage(tk_root, coordinator=coordinator, on_delete_complete=lambda _: None)
    page._current_result = MagicMock()
    page._current_result.duplicate_groups = []
    page.vm.groups = [MagicMock()]
    page.vm.groups[0].group_id = "g1"
    page.vm.groups[0].file_count = 2
    page.vm.keep_selections = {"g1": "/a/file.jpg"}

    with patch.object(page, "_show_delete_confirmation") as mock_conf:
        mock_conf.return_value = "delete"
        page._on_execute()

    coordinator.execute_deletion.assert_called_once()
    assert coordinator.execute_deletion.call_args[0][0] == plan


# ---------------------------------------------------------------------------
# Non-previewable files (Gallery)
# ---------------------------------------------------------------------------

def test_gallery_non_image_gets_placeholder(tk_root):
    """Non-previewable files show 📄 placeholder and metadata in Gallery."""
    from dedup.ui.components.review_workspace import ReviewGalleryView
    from dedup.engine.models import DuplicateGroup, FileMetadata

    def noop(_: str): pass
    view = ReviewGalleryView(tk_root, on_keep=noop)
    group = DuplicateGroup(
        group_id="g1", group_hash="xx",
        files=[
            FileMetadata(path="/doc.pdf", size=2048, mtime_ns=0, inode=1),
            FileMetadata(path="/other.docx", size=4096, mtime_ns=0, inode=2),
        ],
    )
    view.load_group(group, keep_path="")
    tk_root.update_idletasks()

    # Non-image files are added synchronously; each card has 📄 and KEEP/DEL
    assert len(view._cards) == 2
    # Check structure: each card has children (placeholder, size, button)
    for card in view._cards:
        kids = card.winfo_children()
        assert len(kids) >= 3  # icon/label, size, button
