"""
MissionPageViewModel — reactive façade over MissionVM for MVVM Mission page.

Keeps a MissionVM instance as the source of truth; observables mirror its fields
after refresh_from_coordinator / refresh_from_mission_state.
"""

from __future__ import annotations

from typing import Any, List, Optional

from dedup.core.observable import Observable

from ...services.interfaces import IStateStore
from .mission_vm import MissionVM


class MissionPageViewModel:
    """UI-thread ViewModel; coordinator and store callbacks run on Tk main thread."""

    def __init__(self, coordinator: Any, store: Optional[IStateStore] = None) -> None:
        self._coord = coordinator
        self._store = store
        self._inner = MissionVM()

        self.engine_status = Observable(self._inner.engine_status)
        self.last_scan = Observable(self._inner.last_scan)
        self.capabilities = Observable(list(self._inner.capabilities))
        self.recent_sessions = Observable(list(self._inner.recent_sessions))
        self.recent_folders = Observable(list(self._inner.recent_folders))
        self.resumable_scan_ids = Observable(list(self._inner.resumable_scan_ids))
        self.ui_mode = Observable("simple")

    @property
    def inner_vm(self) -> MissionVM:
        return self._inner

    def sync_from_inner(self) -> None:
        """Push MissionVM fields into observables (call after inner refresh)."""
        self.engine_status.set(self._inner.engine_status)
        self.last_scan.set(self._inner.last_scan)
        self.capabilities.set(list(self._inner.capabilities))
        self.recent_sessions.set(list(self._inner.recent_sessions))
        self.recent_folders.set(list(self._inner.recent_folders))
        self.resumable_scan_ids.set(list(self._inner.resumable_scan_ids))
        if self._store is not None:
            self.ui_mode.set(getattr(self._store.state, "ui_mode", "simple"))

    def refresh_from_coordinator(self) -> None:
        self._inner.refresh_from_coordinator(self._coord)
        self.sync_from_inner()

    def refresh_from_mission_state(self, state: Any) -> None:
        self._inner.refresh_from_mission_state(state)
        self.sync_from_inner()
        mode = "simple"
        if self._store is not None:
            mode = getattr(self._store.state, "ui_mode", "simple")
        self.ui_mode.set(mode)

    def attach_store(self, store: IStateStore) -> None:
        self._store = store
