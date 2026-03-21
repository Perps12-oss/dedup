"""Unit tests for virtual navigator scroll math (no Tk)."""

from dedup.ui.components.virtual_navigator import clamp_top, scrollbar_fracs, virtual_navigator_enabled


def test_clamp_top():
    assert clamp_top(5, 100, 16) == 5
    assert clamp_top(-3, 100, 16) == 0
    assert clamp_top(999, 100, 16) == 84
    assert clamp_top(0, 10, 20) == 0
    assert clamp_top(0, 0, 16) == 0


def test_scrollbar_fracs():
    assert scrollbar_fracs(0, 100, 16) == (0.0, 0.16)
    assert scrollbar_fracs(84, 100, 16) == (0.84, 1.0)
    lo, hi = scrollbar_fracs(0, 10, 20)
    assert (lo, hi) == (0.0, 1.0)


def test_virtual_navigator_enabled(monkeypatch):
    monkeypatch.delenv("CEREBRO_VIRTUAL_NAV", raising=False)
    assert virtual_navigator_enabled() is False
    monkeypatch.setenv("CEREBRO_VIRTUAL_NAV", "1")
    assert virtual_navigator_enabled() is True
