"""
Direct tests for `ReviewPageCTK` (store/controller-free paths use mocks).

VM-era ttk tests were removed; this file targets the live CustomTkinter review surface.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from dedup.engine.models import DeletionPolicy, DuplicateGroup, FileMetadata, ScanConfig, ScanResult
from dedup.ui.ctk_pages.review_page import ReviewPageCTK


def _minimal_result_two_files() -> ScanResult:
    g = DuplicateGroup(
        group_id="g1",
        group_hash="hash1",
        files=[
            FileMetadata(path="/keep/a.jpg", size=100, mtime_ns=1),
            FileMetadata(path="/dup/b.jpg", size=100, mtime_ns=0),
        ],
    )
    return ScanResult(
        scan_id="scan-1",
        config=ScanConfig(roots=[]),
        started_at=datetime.now(),
        duplicate_groups=[g],
        total_reclaimable_bytes=100,
    )


@pytest.fixture
def tk_root():
    import customtkinter as ctk

    try:
        root = ctk.CTk()
    except Exception as e:
        pytest.skip(f"CustomTkinter / Tk unavailable: {e}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


def test_load_result_hides_result_panel_until_execution(tk_root):
    page = ReviewPageCTK(tk_root)
    page.load_result(_minimal_result_two_files())
    assert page.get_loaded_result() is not None
    assert not page._result_panel.grid_info()


def test_load_result_empty_no_groups_shows_empty_layout(tk_root):
    r = ScanResult(
        scan_id="e",
        config=ScanConfig(roots=[]),
        started_at=datetime.now(),
        duplicate_groups=[],
        total_reclaimable_bytes=0,
    )
    page = ReviewPageCTK(tk_root)
    page.load_result(r)
    assert page._group_map == {}


def test_group_card_labels_ordinal_prefix_no_widget():
    """Ordinal in group titles is deterministic (no Tk widget tree required)."""
    g = DuplicateGroup(
        group_id="x",
        group_hash="h",
        files=[
            FileMetadata(path="/a.jpg", size=10, mtime_ns=0),
            FileMetadata(path="/b.jpg", size=10, mtime_ns=0),
        ],
    )
    title, _ = ReviewPageCTK._group_card_labels(g, ordinal=1)
    assert title.startswith("#1 ·")


def test_execute_shows_result_panel_when_confirmed(monkeypatch, tk_root):
    calls: list[dict] = []

    def on_exec(km: dict[str, str]):
        calls.append(dict(km))
        from dedup.engine.models import DeletionResult

        return DeletionResult(
            scan_id="scan-1",
            policy=DeletionPolicy.TRASH,
            deleted_files=["/dup/b.jpg"],
            failed_files=[],
            bytes_reclaimed=50,
        )

    page = ReviewPageCTK(tk_root, on_execute=on_exec)
    page.load_result(_minimal_result_two_files())
    monkeypatch.setattr(page, "_confirm_execute", lambda: True)
    page._execute()
    assert calls
    assert page._result_panel.grid_info()


def test_execute_cancel_does_not_show_result_panel(monkeypatch, tk_root):
    page = ReviewPageCTK(tk_root, on_execute=MagicMock())
    page.load_result(_minimal_result_two_files())
    monkeypatch.setattr(page, "_confirm_execute", lambda: False)
    page._execute()
    assert not page._result_panel.grid_info()


def test_review_controller_path_short_circuits_execute(monkeypatch, tk_root):
    page = ReviewPageCTK(tk_root, on_execute=MagicMock())
    page.load_result(_minimal_result_two_files())
    ctrl = MagicMock()
    page.set_review_controller(ctrl)
    page._execute()
    ctrl.handle_execute_deletion.assert_called_once()
    page._review_controller = None
