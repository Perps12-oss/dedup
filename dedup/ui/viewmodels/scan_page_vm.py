"""Scan page MVVM façade over ScanVM (observable mirror for future binding)."""

from __future__ import annotations

from typing import Optional

from dedup.core.observable import Observable

from .scan_vm import ScanVM


class ScanPageViewModel:
    def __init__(self, inner: Optional[ScanVM] = None) -> None:
        self._inner = inner or ScanVM()
        self.is_scanning = Observable(self._inner.is_scanning)
        self.current_file = Observable(self._inner.current_file)

    @property
    def inner(self) -> ScanVM:
        return self._inner

    def sync_from_inner(self) -> None:
        self.is_scanning.set(self._inner.is_scanning)
        self.current_file.set(self._inner.current_file)
