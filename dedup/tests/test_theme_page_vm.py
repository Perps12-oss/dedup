"""ThemePageViewModel unit tests (no tk)."""

from unittest.mock import MagicMock

from dedup.models.theme import ThemeTokens
from dedup.services.adapters.theme_manager_adapter import ThemeManagerAdapter
from dedup.ui.theme.theme_manager import get_theme_manager
from dedup.ui.utils.ui_state import UIState
from dedup.ui.viewmodels.theme_page_vm import ThemePageViewModel, build_contrast_summary


def test_build_contrast_summary():
    t = ThemeTokens.from_mapping({"bg_base": "#000000", "text_primary": "#ffffff", "accent_primary": "#888888"})
    s = build_contrast_summary(t)
    assert "text_primary" in s.ratio_label or "—" not in s.ratio_label


def test_theme_page_vm_contrast_updates():
    state = UIState()
    tm = get_theme_manager()
    ad = ThemeManagerAdapter(tm)
    on_theme = MagicMock()
    vm = ThemePageViewModel(state, ad, on_theme_change=on_theme)
    assert vm.contrast_summary.get() is not None
    vm.detach()
