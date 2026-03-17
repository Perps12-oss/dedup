"""
Characterisation tests for ScanPage: hub attach/detach, defer coalesce.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def tk_root():
    """Tk root for widget tests. Skips if Tk unavailable."""
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


def test_attach_hub_registers_six_subscriptions(tk_root):
    """attach_hub subscribes to session, phase, metrics, compatibility, events_log, terminal."""
    from unittest.mock import MagicMock
    from dedup.ui.pages.scan_page import ScanPage
    from dedup.orchestration.coordinator import ScanCoordinator

    coordinator = MagicMock(spec=ScanCoordinator)
    hub = MagicMock()
    subs_called = []
    hub.subscribe = lambda typ, cb: subs_called.append((typ, cb)) or (lambda: None)

    page = ScanPage(
        tk_root, coordinator,
        on_complete=lambda _: None, on_cancel=lambda: None,
        hub=None,
    )
    page.attach_hub(hub)
    assert len(subs_called) == 6
    assert [t for t, _ in subs_called] == [
        "session", "phase", "metrics", "compatibility", "events_log", "terminal"
    ]


def test_detach_hub_clears_unsubs_even_if_one_raises(tk_root):
    """detach_hub calls each unsub; if one raises, others still run and unsubs are cleared."""
    from unittest.mock import MagicMock
    from dedup.ui.pages.scan_page import ScanPage

    coordinator = MagicMock()
    calls = []

    def unsub_ok():
        calls.append("ok")

    def unsub_raises():
        calls.append("raise")
        raise RuntimeError("unsub failed")

    page = ScanPage(tk_root, coordinator, on_complete=lambda _: None, on_cancel=lambda: None, hub=None)
    page._unsubs = [unsub_raises, unsub_ok]
    page.detach_hub()
    assert calls == ["raise", "ok"]
    assert page._unsubs == []
