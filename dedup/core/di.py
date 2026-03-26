"""Minimal dependency injection container."""

from __future__ import annotations

from threading import Lock
from typing import Any, Callable, Dict, Optional, Type, TypeVar

T = TypeVar("T")

Factory = Callable[[], Any]


class Container:
    """Registers factories or singleton instances by type."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._factories: Dict[Type[Any], Factory] = {}
        self._singletons: Dict[Type[Any], Any] = {}

    def register(self, key: Type[T], factory: Factory, *, singleton: bool = False) -> None:
        with self._lock:

            def make() -> Any:
                if singleton:
                    if key not in self._singletons:
                        self._singletons[key] = factory()
                    return self._singletons[key]
                return factory()

            self._factories[key] = make  # type: ignore[assignment]

    def register_instance(self, key: Type[T], instance: T) -> None:
        with self._lock:
            self._singletons[key] = instance

            def make() -> Any:
                return self._singletons[key]

            self._factories[key] = make

    def resolve(self, key: Type[T]) -> T:
        with self._lock:
            fac = self._factories.get(key)
        if fac is None:
            raise KeyError(f"No registration for {key!r}")
        return fac()  # type: ignore[no-any-return]

    def try_resolve(self, key: Type[T]) -> Optional[T]:
        with self._lock:
            if key not in self._factories:
                return None
        return self.resolve(key)


_global: Optional[Container] = None


def get_container() -> Container:
    global _global
    if _global is None:
        _global = Container()
    return _global


def set_container(c: Optional[Container]) -> None:
    global _global
    _global = c
