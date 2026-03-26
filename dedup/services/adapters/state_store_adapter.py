"""Thin wrapper around UIStateStore for IStateStore."""

from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from dedup.ui.state.store import UIStateStore


class StateStoreAdapter:
    def __init__(self, store: "UIStateStore") -> None:
        self._store = store

    @property
    def state(self) -> Any:
        return self._store.state

    def subscribe(
        self,
        callback: Callable[[Any], None],
        *,
        fire_immediately: bool = True,
    ) -> Callable[[], None]:
        return self._store.subscribe(callback, fire_immediately=fire_immediately)
