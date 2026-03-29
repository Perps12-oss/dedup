"""Cinematic chrome finalization and color adjustment."""

from dedup.ui.theme.cinematic_tokens import adjust_color, finalize_cinematic_tokens
from dedup.ui.theme.theme_registry import DEFAULT_THEME, get_theme
from dedup.ui.theme.theme_tokens import OBSIDIAN_GOLD


def test_adjust_color_darkens() -> None:
    assert adjust_color("#808080", brightness=-16) == "#707070"


def test_finalize_sets_chrome_and_derives_panels() -> None:
    raw = dict(OBSIDIAN_GOLD)
    out = finalize_cinematic_tokens(raw)
    assert out["cinematic_chrome_base"] == "#2A2F2C"
    assert out["cinematic_chrome_dark"].startswith("#")
    assert out["bg_panel"] == adjust_color("#2A2F2C", brightness=-5)
    assert out["bg_elevated"] == adjust_color("#2A2F2C", brightness=-2)
    assert out["bg_elevated"] != out["bg_panel"]


def test_get_theme_always_finalized() -> None:
    t = get_theme(DEFAULT_THEME)
    assert "cinematic_chrome_base" in t
    assert "bg_panel" in t


def test_finalize_fallback_without_chrome_keys() -> None:
    minimal = {
        "name": "Test",
        "mode": "dark",
        "bg_base": "#0d1117",
        "bg_panel": "#161b22",
        "bg_elevated": "#21262d",
        "bg_sidebar": "#0d1117",
        "border_soft": "#21262d",
        "border_strong": "#30363d",
        "text_primary": "#e6edf3",
        "text_secondary": "#8b949e",
        "text_muted": "#7d8590",
        "accent_primary": "#58a6ff",
        "accent_secondary": "#3fb950",
        "gradient_start": "#1f3a5f",
        "gradient_mid": "#1f6feb",
        "gradient_end": "#58a6ff",
        "success": "#3fb950",
        "warning": "#d29922",
        "danger": "#f85149",
        "info": "#58a6ff",
        "selection_bg": "#1f3a5f",
        "focus_ring": "#58a6ff",
        "shadow_soft": "#0d1117",
        "shadow_strong": "#010409",
        "nav_active_bg": "#1f3a5f",
        "nav_active_fg": "#58a6ff",
        "row_alt": "#161b22",
        "tag_safe": "#0d2a16",
        "tag_warn": "#2a1e00",
        "tag_danger": "#2a0d0d",
    }
    out = finalize_cinematic_tokens(minimal)
    assert len(out["cinematic_chrome_base"]) == 7
    assert out["bg_panel"] == adjust_color(out["cinematic_chrome_base"], brightness=-5)
