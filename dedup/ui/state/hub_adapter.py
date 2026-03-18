"""
ProjectionHub → UIStateStore adapter.

Feeds currently projected live state into the store. Step 1: no new projections.
"""

from __future__ import annotations

import logging
from typing import Callable, List

from .store import UIStateStore

_log = logging.getLogger(__name__)


class ProjectionHubStoreAdapter:
    """Pushes ProjectionHub snapshots into UIStateStore (Tk thread)."""

    def __init__(self, hub, store: UIStateStore) -> None:
        self._hub = hub
        self._store = store
        self._unsubs: List[Callable[[], None]] = []

    def start(self) -> None:
        self.stop()
        self._unsubs.append(self._hub.subscribe("session", self._store.set_session))
        self._unsubs.append(self._hub.subscribe("phase", self._store.set_phases))
        self._unsubs.append(self._hub.subscribe("metrics", self._store.set_metrics))
        self._unsubs.append(self._hub.subscribe("compatibility", self._store.set_compat))
        self._unsubs.append(self._hub.subscribe("events_log", self._store.set_events_log))
        self._unsubs.append(self._hub.subscribe("terminal", self._store.set_terminal))

    def stop(self) -> None:
        for unsub in self._unsubs:
            try:
                unsub()
            except Exception as e:
                _log.debug("HubStoreAdapter unsubscribe failed: %s", e)
        self._unsubs.clear()
