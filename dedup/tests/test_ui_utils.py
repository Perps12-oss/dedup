"""Tests for CTK page utilities (resolve_color, theme token helpers)."""

from __future__ import annotations

import pytest

pytest.importorskip("customtkinter")


def test_resolve_color_matches_appearance_tracker() -> None:
    import customtkinter as ctk

    from dedup.ui.ctk_pages.ui_utils import resolve_color

    pair = ("#ffffff", "#000000")
    saved = ctk.AppearanceModeTracker.appearance_mode
    try:
        ctk.AppearanceModeTracker.appearance_mode = 0
        assert resolve_color(pair) == "#ffffff"
        ctk.AppearanceModeTracker.appearance_mode = 1
        assert resolve_color(pair) == "#000000"
    finally:
        ctk.AppearanceModeTracker.appearance_mode = saved


def test_resolve_color_plain_string_unchanged() -> None:
    from dedup.ui.ctk_pages.ui_utils import resolve_color

    assert resolve_color("#abcdef") == "#abcdef"


def test_get_theme_colors_returns_independent_dicts() -> None:
    from dedup.ui.ctk_pages.design_tokens import get_theme_colors

    a = get_theme_colors()
    b = get_theme_colors()
    assert a is not b
    a["bg_base"] = ("#000000", "#000000")
    assert b["bg_base"] != ("#000000", "#000000")


def test_resolve_border_token_prefers_border_soft() -> None:
    from dedup.ui.ctk_pages.design_tokens import resolve_border_default_token, resolve_border_token

    assert resolve_border_token({"border_soft": "#aaaaaa", "border_subtle": "#bbbbbb"}) == "#aaaaaa"
    assert resolve_border_token({"border_subtle": "#bbbbbb"}) == "#bbbbbb"
    assert resolve_border_default_token({"border_strong": "#111111", "border_default": "#222222"}) == "#111111"
    assert resolve_border_default_token({"border_default": "#222222"}) == "#222222"
