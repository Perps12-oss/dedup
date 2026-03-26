"""Diagnostics page MVVM façade over DiagnosticsVM."""

from __future__ import annotations

from typing import Optional

from dedup.core.observable import Observable

from .diagnostics_vm import DiagnosticsVM


class DiagnosticsPageViewModel:
    def __init__(self, inner: Optional[DiagnosticsVM] = None) -> None:
        self._inner = inner or DiagnosticsVM()
        self.active_tab = Observable(self._inner.active_tab)

    @property
    def inner(self) -> DiagnosticsVM:
        return self._inner

    def sync_from_inner(self) -> None:
        self.active_tab.set(self._inner.active_tab)
