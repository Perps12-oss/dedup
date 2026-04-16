from __future__ import annotations

import inspect
from datetime import datetime
from tkinter import colorchooser

import pytest

from dedup.ui.ctk_pages.history_page import HistoryPageCTK
from dedup.ui.ctk_pages.mission_page import MissionPageCTK
from dedup.ui.ctk_pages.review_page import ReviewPageCTK
from dedup.ui.ctk_pages.scan_page import ScanPageCTK
from dedup.ui.ctk_pages.themes_page import ThemesPageCTK


@pytest.mark.bottleneck_guard
def test_bn005_history_rows_are_reused_instead_of_rebuilt(tk_root):
    data = [
        {
            "scan_id": "s1",
            "status": "completed",
            "started_at": datetime.now().isoformat(),
            "files_scanned": 10,
            "duplicates_found": 2,
            "reclaimable_bytes": 1234,
            "roots": ["C:/tmp/a"],
        },
        {
            "scan_id": "s2",
            "status": "completed",
            "started_at": datetime.now().isoformat(),
            "files_scanned": 20,
            "duplicates_found": 3,
            "reclaimable_bytes": 4567,
            "roots": ["C:/tmp/b"],
        },
    ]
    page = HistoryPageCTK(
        tk_root,
        get_history=lambda: data,
        on_load_scan=lambda _sid: None,
    )
    calls = {"create_row": 0}
    orig = page._create_table_row

    def _wrapped_create(*args, **kwargs):
        calls["create_row"] += 1
        return orig(*args, **kwargs)

    page._create_table_row = _wrapped_create  # type: ignore[method-assign]
    page.reload()
    first = calls["create_row"]
    assert first == len(data)

    page._apply_filters()
    assert calls["create_row"] == first


@pytest.mark.bottleneck_guard
def test_bn006_mission_recent_sessions_skip_rebuild_when_unchanged(tk_root):
    page = MissionPageCTK(
        tk_root,
        on_start_scan=lambda: None,
        on_resume_scan=lambda: None,
        on_open_last_review=lambda: None,
        on_quick_scan=lambda _payload: None,
    )
    sessions = [
        {
            "scan_id": "scan-1",
            "started_at": datetime.now().isoformat(),
            "files_scanned": 50,
            "duplicates_found": 4,
            "roots": ["C:/tmp/a"],
        },
        {
            "scan_id": "scan-2",
            "started_at": datetime.now().isoformat(),
            "files_scanned": 60,
            "duplicates_found": 5,
            "roots": ["C:/tmp/b"],
        },
    ]
    page._render_recent_sessions(sessions)
    before = [id(w) for w in page._recent_list_host.winfo_children()]

    page._render_recent_sessions(sessions)
    after = [id(w) for w in page._recent_list_host.winfo_children()]
    assert before == after


@pytest.mark.bottleneck_guard
def test_bn009_themes_color_pick_updates_single_chip_without_full_rebuild(tk_root, monkeypatch):
    page = ThemesPageCTK(tk_root)
    calls = {"rebuild": 0}

    def _count_rebuild():
        calls["rebuild"] += 1
        return None

    monkeypatch.setattr(page, "_rebuild_stop_rows", _count_rebuild)
    monkeypatch.setattr(colorchooser, "askcolor", lambda **_kwargs: ((0, 255, 0), "#00FF00"))

    page._pick_stop_color(0)
    assert calls["rebuild"] == 0
    assert page._stop_chip_refs[0].cget("background") == "#00FF00"


@pytest.mark.bottleneck_guard
def test_bn010_scan_label_color_update_skips_redundant_configure(tk_root):
    page = ScanPageCTK(
        tk_root,
        on_start=lambda _payload: None,
        on_resume=lambda: None,
        on_cancel=lambda: None,
    )

    class CTkLabel:
        def __init__(self):
            self._color = "#F1F5F9"
            self.configure_calls = 0

        def cget(self, name):
            if name == "text_color":
                return self._color
            return None

        def configure(self, **kwargs):
            if "text_color" in kwargs:
                self._color = kwargs["text_color"]
                self.configure_calls += 1

    class FakeWidget:
        def __init__(self, children):
            self._children = children

        def winfo_children(self):
            return self._children

    lbl = CTkLabel()
    fake = FakeWidget([lbl])
    page._update_label_colors(fake, {"text_primary": "#F1F5F9"})
    assert lbl.configure_calls == 0


@pytest.mark.bottleneck_guard
def test_bn011_review_on_execute_start_has_no_forced_update_idletasks():
    src = inspect.getsource(ReviewPageCTK.on_execute_start)
    assert "update_idletasks" not in src
