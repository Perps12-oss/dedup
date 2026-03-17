"""
UIStateStore — canonical UI-readable state for projected live scan surfaces.

Step 1 scope: store holds projected scan state and intent lifecycle.
Pages that consume live scan state read from the store (migrated incrementally).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional

from ..projections.session_projection import SessionProjection, EMPTY_SESSION
from ..projections.phase_projection import PhaseProjection, initial_phase_map
from ..projections.metrics_projection import MetricsProjection, EMPTY_METRICS
from ..projections.compatibility_projection import CompatibilityProjection, EMPTY_COMPAT

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntentLifecycle:
    """
    Non-optimistic intent lifecycle signal for scan (and later review) actions.
    Shown in UI so users see accepted/failed/completed without fake optimistic state.
    """
    status: str  # "idle" | "accepted" | "failed" | "completed"
    intent_type: str = ""
    message: str = ""


@dataclass(frozen=True)
class ProjectedScanState:
    """Currently projected scan state (canonical consumer of ProjectionHub)."""

    session: SessionProjection = EMPTY_SESSION
    phases: Dict[str, PhaseProjection] = field(default_factory=initial_phase_map)
    metrics: MetricsProjection = EMPTY_METRICS
    compat: CompatibilityProjection = EMPTY_COMPAT
    events_log: List[str] = field(default_factory=list)
    terminal: Optional[SessionProjection] = None
    last_intent: IntentLifecycle = field(
        default_factory=lambda: IntentLifecycle(status="idle")
    )


@dataclass(frozen=True)
class UIAppState:
    """App-wide UI state. Step 1: only projected scan state."""

    scan: ProjectedScanState = field(default_factory=ProjectedScanState)


class UIStateStore:
    """
    Central UI state store. Updates are applied on the Tk main thread.
    """

    def __init__(self, tk_root, initial: Optional[UIAppState] = None) -> None:
        self._root = tk_root
        self._state: UIAppState = initial or UIAppState()
        self._subs: List[Callable[[UIAppState], None]] = []

    @property
    def state(self) -> UIAppState:
        return self._state

    def subscribe(
        self,
        callback: Callable[[UIAppState], None],
        *,
        fire_immediately: bool = True,
    ) -> Callable[[], None]:
        self._subs.append(callback)
        if fire_immediately:
            self._safe_notify_one(callback, self._state)

        def unsub() -> None:
            try:
                self._subs.remove(callback)
            except ValueError:
                pass

        return unsub

    def set_session(self, proj: SessionProjection) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, session=proj)))

    def set_phases(self, phases: Dict[str, PhaseProjection]) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, phases=dict(phases))))

    def set_metrics(self, proj: MetricsProjection) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, metrics=proj)))

    def set_compat(self, proj: CompatibilityProjection) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, compat=proj)))

    def set_events_log(self, entries: List[str]) -> None:
        bounded = list(entries[:500])
        self._set_state(replace(self._state, scan=replace(self._state.scan, events_log=bounded)))

    def set_terminal(self, proj: SessionProjection) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, terminal=proj)))

    def set_intent_lifecycle(self, lifecycle: IntentLifecycle) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, last_intent=lifecycle)))

    def _set_state(self, new_state: UIAppState) -> None:
        if new_state is self._state:
            return
        self._state = new_state
        self._notify_all()

    def _notify_all(self) -> None:
        for cb in list(self._subs):
            self._safe_notify_one(cb, self._state)

    @staticmethod
    def _safe_notify_one(cb: Callable[[UIAppState], None], state: UIAppState) -> None:
        try:
            cb(state)
        except Exception as e:
            _log.warning("UIStateStore subscriber failed: %s", e)
