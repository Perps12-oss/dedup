"""
ProjectionHub → UIStateStore adapter.

Feeds currently projected live state into the store. Step 1: no new projections.

Metrics: coalesced on the Tk thread (last-wins after a short idle window) so
subscriber churn stays bounded even when ProjectionHub emits frequent updates.
Session / phase / terminal remain immediate (hub already prioritizes them).
"""

from __future__ import annotations

import logging
import tkinter
from typing import Any, Callable, List, Optional

from ..projections.metrics_projection import MetricsProjection
from .store import UIStateStore

_log = logging.getLogger(__name__)

# Additional coalescing after hub-side throttle — reduces store subscribers re-running.
_METRICS_COALESCE_MS = 100


class ProjectionHubStoreAdapter:
    """Pushes ProjectionHub snapshots into UIStateStore (Tk thread)."""

    def __init__(self, hub, store: UIStateStore) -> None:
        self._hub = hub
        self._store = store
        self._unsubs: List[Callable[[], None]] = []
        self._metrics_after_id: Optional[str] = None
        self._pending_metrics: Optional[MetricsProjection] = None

    def start(self) -> None:
        self.stop()
        self._unsubs.append(self._hub.subscribe("session", self._store.set_session))
        self._unsubs.append(self._hub.subscribe("phase", self._store.set_phases))
        self._unsubs.append(self._hub.subscribe("metrics", self._on_metrics_coalesced))
        self._unsubs.append(self._hub.subscribe("compatibility", self._store.set_compat))
        self._unsubs.append(self._hub.subscribe("events_log", self._store.set_events_log))
        self._unsubs.append(self._hub.subscribe("terminal", self._flush_metrics_then_terminal))

    def _on_metrics_coalesced(self, proj: Any) -> None:
        if not isinstance(proj, MetricsProjection):
            self._store.set_metrics(proj)  # type: ignore[arg-type]
            return
        self._pending_metrics = proj
        root = self._store._root
        try:
            if self._metrics_after_id is not None:
                root.after_cancel(self._metrics_after_id)
        except (tkinter.TclError, ValueError, RuntimeError) as e:
            _log.debug("metrics coalesce cancel: %s", e)
        self._metrics_after_id = root.after(_METRICS_COALESCE_MS, self._flush_metrics_only)

    def _flush_metrics_only(self) -> None:
        self._metrics_after_id = None
        if self._pending_metrics is not None:
            self._store.set_metrics(self._pending_metrics)
            self._pending_metrics = None

    def _flush_metrics_then_terminal(self, proj: Any) -> None:
        """Cancel pending coalesce timer, apply pending metrics, then terminal."""
        root = self._store._root
        if self._metrics_after_id is not None:
            try:
                root.after_cancel(self._metrics_after_id)
            except (tkinter.TclError, ValueError, RuntimeError):
                pass
            self._metrics_after_id = None
        if self._pending_metrics is not None:
            self._store.set_metrics(self._pending_metrics)
            self._pending_metrics = None
        self._store.set_terminal(proj)

    def stop(self) -> None:
        for unsub in self._unsubs:
            try:
                unsub()
            except Exception as e:
                _log.debug("HubStoreAdapter unsubscribe failed: %s", e)
        self._unsubs.clear()
        self._pending_metrics = None
        if self._metrics_after_id is not None:
            try:
                self._store._root.after_cancel(self._metrics_after_id)
            except (Exception,):
                pass
            self._metrics_after_id = None
