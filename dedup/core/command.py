"""Command pattern for ViewModel actions (can_execute + execute)."""

from __future__ import annotations

from typing import Callable, List, Optional


class Command:
    """
    UI action with optional guard. Call notify_can_execute_changed() when
    can_execute transitions (e.g. after async state updates).
    """

    __slots__ = ("_execute", "_can_execute", "_on_changed")

    def __init__(
        self,
        execute: Callable[[], None],
        can_execute: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._execute = execute
        self._can_execute = can_execute
        self._on_changed: List[Callable[[], None]] = []

    def can_execute(self) -> bool:
        if self._can_execute is None:
            return True
        try:
            return bool(self._can_execute())
        except Exception:
            return False

    def execute(self) -> None:
        if not self.can_execute():
            return
        self._execute()

    def subscribe_can_execute_changed(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._on_changed.append(cb)

        def unsub() -> None:
            try:
                self._on_changed.remove(cb)
            except ValueError:
                pass

        return unsub

    def notify_can_execute_changed(self) -> None:
        for cb in list(self._on_changed):
            try:
                cb()
            except Exception:
                pass
