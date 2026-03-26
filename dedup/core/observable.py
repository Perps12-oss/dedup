"""
Lightweight reactive values for ViewModels.

Threading: subscribers are invoked synchronously on the caller's thread.
Tkinter UI updates must be scheduled with root.after(...) from background threads.
"""

from __future__ import annotations

from typing import Any, Callable, Generic, List, Optional, TypeVar

T = TypeVar("T")
Observer = Callable[[T], None]


class Observable(Generic[T]):
    """A mutable value that notifies subscribers when it changes."""

    __slots__ = ("_value", "_observers")

    def __init__(self, initial: T) -> None:
        self._value = initial
        self._observers: List[Observer] = []

    def get(self) -> T:
        return self._value

    def set(self, value: T) -> None:
        if value == self._value:
            return
        self._value = value
        self._notify()

    def subscribe(self, observer: Observer) -> Callable[[], None]:
        """Register observer; returns unsubscribe callable."""

        self._observers.append(observer)

        def unsubscribe() -> None:
            try:
                self._observers.remove(observer)
            except ValueError:
                pass

        return unsubscribe

    def _notify(self) -> None:
        v = self._value
        for obs in list(self._observers):
            try:
                obs(v)
            except Exception:
                pass

    @property
    def value(self) -> T:
        return self._value

    @value.setter
    def value(self, v: T) -> None:
        self.set(v)


class Property(Observable[T]):
    """Alias for Observable used in ViewModels (read/write property)."""

    pass


def computed(*deps: Observable[Any], compute: Callable[..., T]) -> Observable[T]:
    """
    Create an Observable that updates when any dependency changes.
    Initial value is compute(*(d.get() for d in deps)).
    Usage: computed(a, b, compute=lambda x, y: x + y)
    """

    def recompute(_: Any = None) -> None:
        args = tuple(d.get() for d in deps)
        new_val = compute(*args)
        result.set(new_val)

    initial = compute(*(d.get() for d in deps))
    result: Observable[T] = Observable(initial)
    for d in deps:
        d.subscribe(recompute)
    return result
