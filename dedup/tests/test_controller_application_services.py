"""
Controller intents with mocked application services (see `docs/TODO_POST_PHASE3.md` P2).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dedup.ui.controller.review_controller import ReviewController
from dedup.ui.controller.scan_controller import ScanController
from dedup.ui.state.store import UIStateStore


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"Tk unavailable: {e}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


class TestScanControllerWithMockService:
    def test_handle_start_scan_delegates_to_scan_service(self, tk_root):
        store = UIStateStore(tk_root=tk_root)
        scan_svc = MagicMock()
        scan_svc.start_scan.return_value = "scan-abc"

        ctrl = ScanController(scan_svc, store)
        path = Path("/tmp/dedup_test_scan_root")
        path.mkdir(parents=True, exist_ok=True)
        try:
            sid = ctrl.handle_start_scan(
                path,
                {"hash_algorithm": "md5"},
                on_progress=lambda p: None,
                on_complete=lambda r: None,
                on_error=lambda e: None,
            )
        finally:
            try:
                path.rmdir()
            except OSError:
                pass

        assert sid == "scan-abc"
        scan_svc.start_scan.assert_called_once()
        args, kwargs = scan_svc.start_scan.call_args
        assert len(args[0]) == 1
        scan_svc.start_scan.reset_mock()

    def test_handle_cancel_calls_service(self, tk_root):
        store = UIStateStore(tk_root=tk_root)
        scan_svc = MagicMock()
        ctrl = ScanController(scan_svc, store)
        ctrl.handle_cancel()
        scan_svc.cancel_scan.assert_called_once()


class TestReviewControllerWithMockService:
    def test_handle_preview_deletion_no_result_sets_message(self, tk_root):
        store = UIStateStore(tk_root=tk_root)
        review_svc = MagicMock()
        cb = MagicMock()
        cb.get_current_result.return_value = None

        ctrl = ReviewController(review_svc, store, callbacks=cb)
        ctrl.handle_preview_deletion()

        cb.set_preview_result.assert_called()
        assert "No scan result" in str(cb.set_preview_result.call_args[0][0])

    def test_handle_set_keep_updates_store(self, tk_root):
        from datetime import datetime

        from dedup.engine.models import DuplicateGroup, FileMetadata, ScanConfig, ScanResult

        store = UIStateStore(tk_root=tk_root)
        review_svc = MagicMock()
        cb = MagicMock()
        f1 = FileMetadata(path="/a/x.jpg", size=10, mtime_ns=1)
        f2 = FileMetadata(path="/a/y.jpg", size=10, mtime_ns=2)
        g = DuplicateGroup(group_id="g1", group_hash="h", files=[f1, f2])
        result = ScanResult(
            scan_id="t1",
            config=ScanConfig(roots=[], min_size_bytes=1),
            started_at=datetime.now(),
            duplicate_groups=[g],
        )
        cb.get_current_result.return_value = result

        ctrl = ReviewController(review_svc, store, callbacks=cb)
        ctrl.handle_set_keep("g1", "/a/y.jpg")

        cb.refresh_review_ui.assert_called()
        sel = store.state.review.selection
        assert sel is not None
        assert sel.keep_selections.get("g1") == "/a/y.jpg"


def test_review_refresh_heroes_noop_after_host_destroyed(tk_root):
    """Regression: hero refresh must not touch Tk after parent destroyed (TODO P1 virtualization)."""
    pytest.importorskip("customtkinter")
    import customtkinter as ctk

    from dedup.ui.ctk_pages.review_page import ReviewPageCTK

    host = ctk.CTkFrame(tk_root)
    page = ReviewPageCTK(host)
    host.destroy()
    tk_root.update_idletasks()
    page._refresh_heroes()
