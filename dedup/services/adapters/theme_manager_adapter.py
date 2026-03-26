"""Wrap ThemeManager as IThemeManager with ThemeTokens model."""

from __future__ import annotations

from typing import Callable, Dict, TYPE_CHECKING

from dedup.models.theme import ThemeTokens

if TYPE_CHECKING:
    from dedup.ui.theme.theme_manager import ThemeManager


class ThemeManagerAdapter:
    def __init__(self, tm: "ThemeManager") -> None:
        self._tm = tm
        self._wrappers: Dict[Callable[[ThemeTokens], None], Callable[[object], None]] = {}

    @property
    def current_key(self) -> str:
        return self._tm.current_key

    def get_tokens(self) -> ThemeTokens:
        return ThemeTokens.from_mapping(self._tm.tokens)

    def subscribe(self, callback: Callable[[ThemeTokens], None]) -> None:
        def _wrap(raw: object) -> None:
            callback(ThemeTokens.from_mapping(raw))  # type: ignore[arg-type]

        self._wrappers[callback] = _wrap
        self._tm.subscribe(_wrap)

    def unsubscribe(self, callback: Callable[[ThemeTokens], None]) -> None:
        w = self._wrappers.pop(callback, None)
        if w is not None:
            try:
                self._tm.unsubscribe(w)  # type: ignore[arg-type]
            except Exception:
                pass
