"""Settings page MVVM façade (mirrors key AppSettings fields)."""

from __future__ import annotations

from dedup.core.observable import Observable

from ..utils.ui_state import UIState


class SettingsPageViewModel:
    def __init__(self, state: UIState) -> None:
        self._state = state
        s = state.settings
        self.theme_key = Observable(s.theme_key)
        self.density = Observable(s.density)

    def sync_from_inner(self) -> None:
        s = self._state.settings
        self.theme_key.set(s.theme_key)
        self.density.set(s.density)
