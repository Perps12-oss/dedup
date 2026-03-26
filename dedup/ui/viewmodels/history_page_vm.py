"""History page MVVM façade over HistoryVM."""

from __future__ import annotations

from typing import Optional

from dedup.core.observable import Observable

from ..projections.history_projection import HistoryProjection
from .history_vm import HistoryVM


class HistoryPageViewModel:
    def __init__(self, inner: Optional[HistoryVM] = None) -> None:
        self._inner = inner or HistoryVM()
        self.history = Observable(self._inner.history)
        self.search_text = Observable(self._inner.search_text)

    @property
    def inner(self) -> HistoryVM:
        return self._inner

    def sync_from_inner(self) -> None:
        self.history.set(self._inner.history)
        self.search_text.set(self._inner.search_text)

    def set_history_projection(self, hp: HistoryProjection) -> None:
        self._inner.history = hp
        self.history.set(hp)
